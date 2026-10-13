#!/usr/bin/env python3
"""SG13CMOS5L glue for the `klt sim` harness (issue #337, Part of #322).

The four SG13CMOS5L experiments (`sim/sg13cmos5l-*`) only had legacy
`run_pvt_sweep.sh` loops. This module is the SG13CMOS5L-specific half of
their `run_klt_sim.sh` runners; the generic half (corner-id grammar, record
mechanics, shard merge, deck fixup) is reused unchanged from the sibling
modules. It owns four things, each of which the SG13G2 harness cannot lend:

1. **The corner mapping.** SG13G2's `klt_corner_bundle.CORNER_SECTIONS` pairs
   an *HBT* section (`cornerHBT.lib`: hbt_typ/hbt_bcs/hbt_wcs) with the MOS
   and resistor sections. SG13CMOS5L has no HBT -- only `pnpMPA`, whose
   process file is `cornerPNP.lib` with sections `typ`, `stat`, `bcs`, `wcs`
   (read directly from the installed checkout; no skewed section). So the
   triple here is (pnpMPA, MOS-hv, resistor) = :data:`CORNER_SECTIONS`:

   ====  =========  =========  =========
   label pnpMPA     MOS-hv     resistor
   ====  =========  =========  =========
   typ   typ        mos_tt     res_typ
   bcs   bcs        mos_ff     res_bcs
   wcs   wcs        mos_ss     res_wcs
   sf    typ        mos_sf     res_typ
   fs    typ        mos_fs     res_typ
   ====  =========  =========  =========

   `cornerMOShv.lib` and `cornerRES.lib` inside the SG13CMOS5L tree are
   symlinks into the sibling `ihp-sg13g2/` checkout (sim/pdk-sg13cmos5l.json
   "relationship_to_ihp_sg13g2"), so those two columns are the SG13G2 ones;
   the first column is CMOS5L's own. The mapping is not trusted by assertion:
   :func:`check_legacy_mapping` re-derives it from the legacy scripts that
   produced every committed record (`PNP_SECTION_OF` in each
   `run_pvt_sweep.sh`, `MOS_SECTION_OF`/`RES_SECTION_OF` in
   `sim/lib/pvt_preflight.sh`) and :func:`check_pdk_sections` checks every
   section name exists in the installed `*.lib` files.

2. **Request / body instantiation** (`prepare`): one local sanity request, or
   the batch shard set with per-shard bodies and a manifest the runner loops.

3. **The per-point verdicts** (`enrich`): the legacy pass/fail formulas that
   `klt sim`'s presence-only grading cannot express (see `enrich_pvt_report`
   for the SG13G2 equivalent), with the same constants.

4. **The merge** (`merge`): the shard reports back into one grid-shaped
   report, with the expected grid stated explicitly (#327).

Nothing here runs a simulation, and nothing here writes under `sim/<exp>/`.
Batch execution of these experiments additionally needs a CMOS5L-provisioned
runner image, which does not exist yet (sim/pdk-sg13cmos5l.json
"deferred_requirements.provisioning"); `run_klt_sim.sh --batch` refuses
without an explicit acknowledgement for that reason.

CLI:

    cmos5l_klt.py bundle -o FILE [--families pnp,mos,res|mos,res]
    cmos5l_klt.py check-mapping [--models-dir DIR]
    cmos5l_klt.py prepare --mode sanity|batch --kind K --request-template T
                          --body-template B --work DIR --osdi-dir D ...
    cmos5l_klt.py merge --manifest M --request-template T -o OUT
    cmos5l_klt.py enrich --kind K REPORT -o OUT
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_pvt_report as epr  # noqa: E402
import klt_corner_bundle as kcb  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]

#: Experiment kinds -> how the batch grid is sharded (see :func:`shard_plan`).
#:   core-open-loop  one request per process; supply rides `corners.supply_v`
#:   trip-point      one request per (process, supply); levels baked in, supply
#:                   still pinned through `corners.supply_v`
#:   closed-loop     one request per (process, supply); supply baked into a PWL
#:                   ramp, so the request has no supply axis
KINDS = ("core-open-loop", "trip-point", "closed-loop")

#: The grid's supplies (V): the 3.3 V HV-flavor analog rail +-10% only
#: (sim/pdk-sg13cmos5l.json "supply_rails"); equals `VDDS` in
#: sim/lib/pvt_preflight.sh (guarded by the fixture tests).
SUPPLIES = (2.97, 3.30, 3.63)

CORNER_LABELS = ("typ", "bcs", "wcs", "sf", "fs")

#: Per-family corner libraries, in the order every legacy template emitted
#: them (PNP, MOS-hv, resistor).
CMOS5L_LIBS = ("cornerPNP.lib", "cornerMOShv.lib", "cornerRES.lib")

#: This repo's corner label -> (pnpMPA section in cornerPNP.lib, MOS-hv
#: section in cornerMOShv.lib, resistor section in cornerRES.lib). See the
#: module docstring for provenance. sf/fs fall back to the typ pnpMPA section
#: because cornerPNP.lib has no skewed section (the same shape as SG13G2's
#: cornerHBT.lib), exactly as the legacy `PNP_SECTION_OF` maps do.
CORNER_SECTIONS: dict[str, tuple[str, str, str]] = {
    "typ": ("typ", "mos_tt", "res_typ"),
    "bcs": ("bcs", "mos_ff", "res_bcs"),
    "wcs": ("wcs", "mos_ss", "res_wcs"),
    "sf": ("typ", "mos_sf", "res_typ"),
    "fs": ("typ", "mos_fs", "res_typ"),
}

#: Section triple column -> the record-spec `extra_columns` name.
EXTRA_COLUMN_NAMES = ("pnp_section", "mos_section", "res_section")

#: The legacy sweeps that define a PNP map (the experiments that instantiate
#: pnpMPA). Startup-trip-point has none: it contains no bipolar device.
LEGACY_PNP_SCRIPTS = (
    "sg13cmos5l-core-open-loop-bias/run_pvt_sweep.sh",
    "sg13cmos5l-closed-loop-startup/run_pvt_sweep.sh",
    "sg13cmos5l-closed-loop-startup-pex/run_pvt_sweep.sh",
)


# --------------------------------------------------------------------------
# corner mapping: derivation checks
# --------------------------------------------------------------------------

_MAP_RE = re.compile(r"declare -A (\w+)=\((.*?)\)")


def parse_shell_map(text: str, name: str) -> dict[str, str]:
    """`declare -A NAME=( [k]=v ... )` -> dict (first definition wins)."""
    for match in _MAP_RE.finditer(text):
        if match.group(1) != name:
            continue
        out: dict[str, str] = {}
        for token in match.group(2).split():
            key, _, value = token.partition("]=")
            out[key.lstrip("[")] = value
        return out
    return {}


def check_legacy_mapping(sim_dir: Path = SIM_DIR) -> list[str]:
    """Problems (empty = consistent) between :data:`CORNER_SECTIONS` and the
    legacy scripts that generated every committed SG13CMOS5L record."""
    problems: list[str] = []
    pre = (sim_dir / "lib" / "pvt_preflight.sh").read_text(encoding="utf-8")
    mos = parse_shell_map(pre, "MOS_SECTION_OF")
    res = parse_shell_map(pre, "RES_SECTION_OF")
    labels_line = re.search(r"^CORNER_LABELS=\((.*?)\)", pre, re.M)
    if not labels_line or tuple(labels_line.group(1).split()) != CORNER_LABELS:
        problems.append("CORNER_LABELS differ from pvt_preflight.sh")
    vdds_line = re.search(r"^VDDS=\((.*?)\)", pre, re.M)
    if not vdds_line or tuple(float(v) for v in vdds_line.group(1).split()) != SUPPLIES:
        problems.append("SUPPLIES differ from pvt_preflight.sh VDDS")
    for label, (_pnp, m, r) in CORNER_SECTIONS.items():
        if mos.get(label) != m:
            problems.append(f"{label}: MOS section {m!r} != pvt_preflight.sh {mos.get(label)!r}")
        if res.get(label) != r:
            problems.append(f"{label}: RES section {r!r} != pvt_preflight.sh {res.get(label)!r}")
    expected_pnp = {label: t[0] for label, t in CORNER_SECTIONS.items()}
    for rel in LEGACY_PNP_SCRIPTS:
        text = (sim_dir / rel).read_text(encoding="utf-8")
        legacy = parse_shell_map(text, "PNP_SECTION_OF")
        if legacy != expected_pnp:
            problems.append(f"{rel}: PNP_SECTION_OF {legacy} != CORNER_SECTIONS {expected_pnp}")
    return problems


def lib_sections(path: Path) -> set[str]:
    """Section names a ngspice `.lib` file defines (`.LIB name` ... `.ENDL`)."""
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^\s*\.lib\s+(\S+)\s*$", raw, re.I)
        if match:
            names.add(match.group(1))
    return names


def check_pdk_sections(models_dir: Path) -> list[str]:
    """Problems if any mapped section is absent from the installed libs."""
    problems: list[str] = []
    for index, lib in enumerate(CMOS5L_LIBS):
        path = models_dir / lib
        if not path.is_file():
            problems.append(f"missing corner library {path}")
            continue
        have = lib_sections(path)
        for label, triple in CORNER_SECTIONS.items():
            if triple[index] not in have:
                problems.append(f"{lib}: no section {triple[index]!r} (needed by corner {label})")
    return problems


def families_for(spec: str) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """`pnp,mos,res` or `mos,res` -> (libs, sections-by-label) for that subset."""
    wanted = [f.strip() for f in spec.split(",") if f.strip()]
    index = {"pnp": 0, "mos": 1, "res": 2}
    if not wanted or any(f not in index for f in wanted) or wanted != sorted(wanted, key=index.get):
        raise SystemExit(f"cmos5l_klt.py: bad --families {spec!r} (order: pnp,mos,res; subset allowed)")
    libs = tuple(CMOS5L_LIBS[index[f]] for f in wanted)
    sections = {label: tuple(t[index[f]] for f in wanted) for label, t in CORNER_SECTIONS.items()}
    return libs, sections


def render_bundle(models_dir: str, families: str = "pnp,mos,res") -> str:
    libs, sections = families_for(families)
    return kcb.render_bundle(models_dir, sections, libs)


# --------------------------------------------------------------------------
# request / body instantiation
# --------------------------------------------------------------------------


def _fmt(value: float) -> str:
    return f"{value:g}"


def vid(vdd: float) -> str:
    return f"{vdd:.2f}".replace(".", "p")


def substitutions(kind: str, vdd: float, msense_w: str | None) -> dict[str, str]:
    """Placeholder -> value for one supply. `@@VDD_HALF@@`/`@@VDD_OFF@@` use
    the legacy script's own `%.4f` awk formatting."""
    sub = {"@@VDD@@": _fmt(vdd)}
    if kind == "trip-point":
        sub["@@VDD_HALF@@"] = f"{vdd / 2:.4f}"
        sub["@@VDD_OFF@@"] = f"{vdd - 0.05:.4f}"
    if msense_w is not None:
        sub["@@MSENSE_W@@"] = msense_w
    return sub


def apply(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    return text


def leftover_placeholders(text: str, allowed: tuple[str, ...] = ()) -> list[str]:
    return sorted({m for m in re.findall(r"@@[A-Z_]+@@", text) if m not in allowed})


def shard_plan(kind: str) -> list[tuple[str, float | None]]:
    """(label, supply or None) per batch shard, in `CORNER_LABELS` order."""
    if kind not in KINDS:
        raise SystemExit(f"cmos5l_klt.py: unknown kind {kind!r}")
    if kind == "core-open-loop":
        return [(label, None) for label in CORNER_LABELS]
    return [(label, vdd) for label in CORNER_LABELS for vdd in SUPPLIES]


def shard_id(label: str, vdd: float | None) -> str:
    return label if vdd is None else f"{label}-{vid(vdd)}"


def build_body(body_template: str, osdi_dir: str, kind: str, vdd: float,
               msense_w: str | None) -> str:
    text = apply(body_template.replace("@@OSDI_DIR@@", osdi_dir),
                 substitutions(kind, vdd, msense_w))
    left = leftover_placeholders(text)
    if left:
        raise SystemExit(f"cmos5l_klt.py: body template placeholders left unresolved: {left}")
    return text


def batch_family_cards(models_dir: str, families: str, label: str) -> tuple[str, str]:
    """(request `models.lib` PDK-relative path, body `.lib` cards).

    The runner's request carries ONE model library (klayout-tools#2668), so
    the FIRST family rides `models`/`corners.process` and every remaining
    family is a body-level selection `.lib` card against the image's baked
    PDK root -- the per-process bridge the SG13G2 runners use, with CMOS5L's
    PNP file in the HBT file's place.
    """
    libs, sections = families_for(families)
    triple = sections[label]
    cards = "".join(
        f'.lib "{models_dir}/{lib}" {section}\n'
        for lib, section in zip(libs[1:], triple[1:], strict=True)
    )
    return f"libs.tech/ngspice/models/{libs[0]}", cards


def prepare_sanity(args: argparse.Namespace) -> None:
    work = Path(args.work)
    template = json.loads(Path(args.request_template).read_text(encoding="utf-8"))
    vdd = 3.30
    body = build_body(Path(args.body_template).read_text(encoding="utf-8"), args.osdi_dir,
                      args.kind, vdd, args.msense_w)
    (work / "body.spice").write_text(body, encoding="utf-8")
    req = json.loads(apply(json.dumps(template), {
        **substitutions(args.kind, vdd, args.msense_w),
        "@@BODY@@": str(work / "body.spice"),
        "@@CORNER_BUNDLE@@": args.bundle,
    }))
    req["corners"]["process"] = ["typ"]
    req["corners"]["temperature_c"] = [27]
    if "supply_v" in req["corners"]:
        req["corners"]["supply_v"] = {"Vvdd": [vdd]}
    left = leftover_placeholders(json.dumps(req))
    if left:
        raise SystemExit(f"cmos5l_klt.py: request placeholders left unresolved: {left}")
    (work / "request.json").write_text(json.dumps(req, indent=2) + "\n", encoding="utf-8")


def prepare_batch(args: argparse.Namespace) -> None:
    work = Path(args.work)
    template_text = Path(args.request_template).read_text(encoding="utf-8")
    template = json.loads(template_text)
    body_template = Path(args.body_template).read_text(encoding="utf-8")
    models_dir = f"{args.batch_pdk_root}/{args.pdk}/libs.tech/ngspice/models"
    osdi = f"{args.batch_pdk_root}/{args.pdk}/libs.tech/ngspice/osdi"
    declared = tuple(template["corners"]["process"])
    if declared != CORNER_LABELS:
        raise SystemExit(f"cmos5l_klt.py: request processes {declared} != {CORNER_LABELS}")
    rows: list[str] = []
    for label, vdd in shard_plan(args.kind):
        sid = shard_id(label, vdd)
        use_vdd = vdd if vdd is not None else 3.30
        body = build_body(body_template, osdi, args.kind, use_vdd, args.msense_w)
        lib_path, cards = batch_family_cards(models_dir, args.families, label)
        process_section = families_for(args.families)[1][label][0]
        body += (
            "\n* Batch mode only (issue #337 per-process bridge): the families the request's\n"
            "* single models.lib cannot reach, as selection-form `.lib` cards against the\n"
            "* image's baked PDK root. Same CORNER_SECTIONS entry the request's models.lib\n"
            f"* selects the first family from. Corner: {label}.\n{cards}"
        )
        body_path = work / f"body-{sid}.spice"
        body_path.write_text(body, encoding="utf-8")
        fixed = body.replace(f'"{args.batch_pdk_root}/', f'"{args.local_pdk_root}/')
        (work / f"body-fixed-{sid}.spice").write_text(fixed, encoding="utf-8")
        req = json.loads(apply(json.dumps(template), {
            **substitutions(args.kind, use_vdd, args.msense_w),
            "@@BODY@@": str(body_path),
            "@@CORNER_BUNDLE@@": "UNUSED-BATCH",
        }))
        req["backend"] = "batch"
        req["models"] = {"pdk": args.pdk, "lib": lib_path}
        req["corners"]["process"] = [process_section]
        if vdd is not None and "supply_v" in req["corners"]:
            req["corners"]["supply_v"] = {"Vvdd": [vdd]}
        req["batch"] = {"provision_script_path": args.provision}
        left = leftover_placeholders(json.dumps(req))
        if left:
            raise SystemExit(f"cmos5l_klt.py: request placeholders left unresolved: {left}")
        (work / f"request-{sid}.json").write_text(json.dumps(req, indent=2) + "\n", encoding="utf-8")
        rows.append("\t".join([
            sid, label, "-" if vdd is None else _fmt(vdd),
            f"request-{sid}.json", f"report-{sid}.json", f"artifacts-{sid}",
            f"body-fixed-{sid}.spice", f"report-{sid}-fixed.json", f"decks-fixed-{sid}",
        ]))
    (work / "manifest.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------


def merge_manifest(manifest: Path, request_template: Path, work: Path) -> dict:
    """Merge the fixed shard reports named by the manifest, stating the grid.

    The expected grid comes from the request template's own process and
    temperature axes plus its supply axis (or :data:`SUPPLIES` for the PWL
    benches that carry none) -- never from the manifest being merged, so a
    dropped shard cannot shrink its own expectation.
    """
    template = json.loads(request_template.read_text(encoding="utf-8"))
    corners = template["corners"]
    processes = list(corners["process"])
    temps = list(corners["temperature_c"])
    supplies = list((corners.get("supply_v") or {}).get("Vvdd") or SUPPLIES)
    if tuple(processes) != CORNER_LABELS:
        raise SystemExit(f"cmos5l_klt.py merge: request processes {processes} != {list(CORNER_LABELS)}")
    expected = mbs.expected_from_axes(processes, supplies, temps)
    args: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        sid, label, vdd, _req, _rep, _art, _body, fixed, _decks = line.split("\t")
        hint = "" if vdd == "-" else f"@{vdd}"
        args.append(f"{label}{hint}={work / fixed}")
    return mbs.merge(args, expected)


# --------------------------------------------------------------------------
# enrich: derived columns + legacy verdicts
# --------------------------------------------------------------------------


def _meas(corner: dict) -> dict[str, float]:
    return epr._meas_map(corner)


def _vdd_of(corner: dict) -> float | None:
    supplies = corner.get("supply_v") or {}
    if len(supplies) == 1:
        value = next(iter(supplies.values()))
        return float(value) if isinstance(value, (int, float)) else None
    return epr._corner_vdd(corner)


def _fail(corner: dict, code: str, message: str) -> None:
    corner["status"] = "fail"
    corner["diagnostics"] = list(corner.get("diagnostics") or []) + [
        {"code": code, "message": message}
    ]


def verdict_trip_point(m: dict[str, float], vdd: float) -> list[str]:
    """Failed-criterion names (empty = PASS): `pvt_trip_point_verdict`'s six
    criteria from sim/lib/pvt_verdict_common.sh, verbatim."""
    failed: list[str] = []
    if not m["det_on_v"] >= 0.8 * vdd:
        failed.append("det_on_not_engaged")
    if not m["fb_on_v"] <= 0.1:
        failed.append("fb_on_not_driving_mirror")
    if not m["vtrip_v"] > 0:
        failed.append("vtrip_not_above_zero")
    if not m["vtrip_v"] < vdd:
        failed.append("vtrip_not_below_vdd")
    if not m["det_off_v"] <= 0.2 * vdd:
        failed.append("det_off_not_released")
    if not m["fb_off_v"] >= 0.8 * vdd:
        failed.append("fb_off_not_released")
    return failed


def verdict_closed_loop(m: dict[str, float], vdd: float, dvsns: float) -> list[str]:
    """Failed-criterion names: `pvt_closed_loop_verdict`'s 3-criteria form
    (no settledness term -- the startup-release check is the settledness
    claim for the closed-loop-startup* variants)."""
    failed: list[str] = []
    if not (m["det_final_v"] <= epr.DET_RELEASE_FRAC * vdd
            and abs(m["i_mkfb_final_a"]) <= epr.I_MKFB_RELEASE_A):
        failed.append("startup_not_released")
    if dvsns > epr.DVSNS_CLOSE_V:
        failed.append("loop_not_closed")
    if not (epr.FB_RAIL_MARGIN_V <= m["fb_final_v"] <= vdd - epr.FB_RAIL_MARGIN_V):
        failed.append("fb_railed")
    return failed


REQUIRED_FOR_VERDICT = {
    "trip-point": ("det_on_v", "fb_on_v", "vtrip_v", "det_off_v", "fb_off_v"),
    "closed-loop": ("sns1_final_v", "sns2_final_v", "det_final_v", "i_mkfb_final_a", "fb_final_v"),
    "core-open-loop": (),
}


def enrich(report: dict, kind: str, cwd: Path | None = None) -> dict:
    """Re-grade every corner with the legacy verdict; append derived columns.

    A corner that `klt sim` already graded non-pass is left as is (a failed
    point stays failed, and keeps whatever it measured). A corner whose
    verdict operands are missing is FAILED with `verdict_operands_missing`,
    never passed on partial data. Counts are recomputed.
    """
    if kind not in KINDS:
        raise SystemExit(f"cmos5l_klt.py: unknown kind {kind!r}")
    cwd = cwd or Path.cwd()
    corners = report.get("corners", [])
    for corner in corners:
        if kind == "closed-loop":
            # Every corner, not only passing ones: a failed point still needs
            # a supply token for the adapter's corner-id grammar.
            epr.inject_baked_supply(corner, cwd)
        if corner.get("status") != "pass":
            continue
        got = _meas(corner)
        needed = REQUIRED_FOR_VERDICT[kind]
        absent = [k for k in needed if k not in got]
        if absent:
            _fail(corner, "verdict_operands_missing", "absent: " + ", ".join(absent))
            continue
        vdd = _vdd_of(corner)
        if kind != "core-open-loop" and vdd is None:
            _fail(corner, "verdict_operands_missing", "supply not identifiable")
            continue
        if kind == "trip-point":
            failed = verdict_trip_point(got, vdd)
        elif kind == "closed-loop":
            dvsns = abs(got["sns1_final_v"] - got["sns2_final_v"])
            corner["measurements"].append({
                "name": "dvsns_final_v",
                "value": dvsns,
                "spice": "derived: |sns1_final_v - sns2_final_v| (see sim/harness/cmos5l_klt.py)",
            })
            failed = verdict_closed_loop(got, vdd, dvsns)
        else:
            failed = []
        if failed:
            _fail(corner, f"{kind.replace('-', '_')}_verdict", "; ".join(failed))
    report["corners"] = corners
    report["passed"] = sum(1 for c in corners if c.get("status") == "pass")
    report["failed"] = sum(1 for c in corners if c.get("status") == "fail")
    report["errored"] = sum(1 for c in corners if c.get("status") == "error")
    report["corner_count"] = len(corners)
    report["status"] = "fail" if report["failed"] else ("error" if report["errored"] else "pass")
    return report


def check_anchors(report: dict, anchors: list[tuple[str, float, float]], mode: str = "local") -> list[str]:
    """Sanity-gate problems for a one-corner report vs committed anchors.

    `anchors` are `(measurement, value, abs_tol)` taken from the experiment's
    newest committed legacy record at typ/27C/3.30V. A missing measurement,
    a non-pass grade or a value off its anchor is a problem; an empty list is
    the only pass.
    """
    problems: list[str] = []
    if report.get("status") != "pass":
        problems.append(f"sanity gate ({mode}): klt sim graded the run {report.get('status')!r}")
    corners = report.get("corners") or []
    if len(corners) != 1:
        return problems + [f"sanity gate ({mode}): expected exactly one corner, got {len(corners)}"]
    got = {m["name"]: m.get("value") for m in corners[0].get("measurements", [])}
    for name, anchor, tol in anchors:
        value = got.get(name)
        if value is None:
            problems.append(f"sanity gate ({mode}): measurement {name} did not come back")
            continue
        delta = abs(value - anchor)
        if delta > tol:
            problems.append(
                f"sanity gate ({mode}): {name} = {value!r} is {delta:.3g} from anchor {anchor} (tol {tol})"
            )
    return problems


def parse_anchor(text: str) -> tuple[str, float, float]:
    try:
        name, rest = text.split("=", 1)
        value, tol = rest.split(":", 1)
        return name, float(value), float(tol)
    except ValueError:
        raise SystemExit(f"cmos5l_klt.py: bad --anchor {text!r} (want name=value:tol)") from None


def augment_spec(spec: dict, msense_w: str | None) -> dict:
    """Record-spec copy with the per-run `msense_w` column (closed-loop-startup).

    XMSENSE's width is read from the live schematic netlist at run time, as
    the legacy script does, so it cannot live in the committed static spec.
    """
    out = json.loads(json.dumps(spec))
    if msense_w is not None:
        out["extra_columns"]["msense_w"] = {label: msense_w for label in CORNER_LABELS}
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bundle", help="write the generated SG13CMOS5L corner bundle .lib")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--pdk-root", default=os.environ.get("PDK_ROOT"))
    p.add_argument("--pdk", default=os.environ.get("PDK") or "ihp-sg13cmos5l")
    p.add_argument("--families", default="pnp,mos,res")

    p = sub.add_parser("check-mapping", help="assert the corner map against the legacy scripts (and a PDK)")
    p.add_argument("--models-dir")
    p.add_argument("--sim-dir", default=str(SIM_DIR))

    p = sub.add_parser("prepare", help="write the sanity request or the batch shard set")
    p.add_argument("--mode", choices=("sanity", "batch"), required=True)
    p.add_argument("--kind", choices=KINDS, required=True)
    p.add_argument("--families", default="pnp,mos,res")
    p.add_argument("--request-template", required=True)
    p.add_argument("--body-template", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--osdi-dir", help="local OSDI dir (sanity mode)")
    p.add_argument("--msense-w")
    p.add_argument("--bundle", help="generated corner bundle path (sanity mode)")
    p.add_argument("--pdk", default="ihp-sg13cmos5l")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--local-pdk-root")
    p.add_argument("--provision")

    p = sub.add_parser("merge", help="merge the fixed shard reports named by a manifest")
    p.add_argument("--manifest", required=True)
    p.add_argument("--request-template", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("enrich", help="derived columns + legacy verdict on a merged report")
    p.add_argument("--kind", choices=KINDS, required=True)
    p.add_argument("report")
    p.add_argument("-o", "--output", required=True)

    p = sub.add_parser("check-anchors", help="sanity gate: one-corner report vs committed anchors")
    p.add_argument("report")
    p.add_argument("--anchor", action="append", required=True, metavar="NAME=VALUE:TOL")

    p = sub.add_parser("spec", help="write the record-spec copy the adapter consumes")
    p.add_argument("spec")
    p.add_argument("--msense-w")
    p.add_argument("-o", "--output", required=True)

    args = ap.parse_args(argv)

    if args.cmd == "bundle":
        if not args.pdk_root:
            raise SystemExit("cmos5l_klt.py bundle: PDK_ROOT unset and --pdk-root not given")
        models = Path(args.pdk_root) / args.pdk / "libs.tech" / "ngspice" / "models"
        if not models.is_dir():
            raise SystemExit(f"cmos5l_klt.py bundle: no such models dir: {models}")
        Path(args.output).write_text(render_bundle(str(models), args.families), encoding="utf-8")
        return 0
    if args.cmd == "check-mapping":
        problems = check_legacy_mapping(Path(args.sim_dir))
        if args.models_dir:
            problems += check_pdk_sections(Path(args.models_dir))
        if problems:
            print("cmos5l_klt.py: corner mapping problems:\n  - " + "\n  - ".join(problems),
                  file=sys.stderr)
            return 1
        print(f"cmos5l_klt.py: CORNER_SECTIONS consistent ({len(CORNER_SECTIONS)} corner labels)")
        return 0
    if args.cmd == "prepare":
        if args.mode == "sanity":
            if not (args.osdi_dir and args.bundle):
                raise SystemExit("cmos5l_klt.py prepare --mode sanity needs --osdi-dir and --bundle")
            prepare_sanity(args)
        else:
            if not (args.local_pdk_root and args.provision):
                raise SystemExit("cmos5l_klt.py prepare --mode batch needs --local-pdk-root and --provision")
            prepare_batch(args)
        return 0
    if args.cmd == "merge":
        merged = merge_manifest(Path(args.manifest), Path(args.request_template), Path(args.work))
        Path(args.output).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        return 0
    if args.cmd == "enrich":
        report = enrich(json.loads(Path(args.report).read_text(encoding="utf-8")), args.kind)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for c in report["corners"]:
            if c.get("status") != "pass":
                diag = "; ".join(d.get("message", "") for d in c.get("diagnostics", []))
                print(f"  {c.get('corner_id')}: {c['status']} {diag[:100]}")
        print(f"enriched: {report['status']} passed={report['passed']} "
              f"failed={report['failed']} errored={report['errored']}")
        return 0
    if args.cmd == "check-anchors":
        problems = check_anchors(json.loads(Path(args.report).read_text(encoding="utf-8")),
                                 [parse_anchor(a) for a in args.anchor])
        if problems:
            raise SystemExit("\n".join(problems) + "\n  -- the bench, not the PDK pin, is the first suspect "
                             "(issue #337 sanity gate); no grid is dispatched")
        print("  sanity gate: PASS")
        return 0
    if args.cmd == "spec":
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        Path(args.output).write_text(json.dumps(augment_spec(spec, args.msense_w), indent=2) + "\n",
                                     encoding="utf-8")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
