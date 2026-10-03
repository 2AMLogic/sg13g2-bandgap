#!/usr/bin/env python3
"""Trim-code axis of loop phase margin, through `klt sim` (issue #271).

`run_pvt_sweep.sh` measures this experiment's 45-point PVT grid at ONE trim
code (the schematic default, 128). Issue #271 asks the follow-on question the
issue-#264 refresh raised: does phase margin move with the trim code (more or
fewer of the 255 ladder segments in the `vref`->`cb3` branch), and is the
36.3 deg the 20261001-085806-e5507b2 record reads at `wcs`/125C/2.97V a floor
or a sample of a steeper trend? That is a code x corner grid, so it runs
through `klt sim` (the dispatch hosts forbid hand-looping `ngspice -b`; see
sim/harness/README.md), one request per PVT point, each request sweeping the
trim code.

Three subcommands, driven by `run_klt_trim_axis.sh`:

  prepare  render one netlist body + `klt sim` request per planned PVT point
           (from this experiment's own testbench/tb_loop_gain.spice.tmpl, so
           the DUT and the loop-break fixture are the bench's own, verbatim)
  record   turn the returned reports + rawfiles into this repo's append-only
           record quadruple (records/<id>.{md,csv}, corners/<id>/,
           netlist-snapshots/<id>/), computing the loop gain with the bench's
           own tools/find_crossover.awk
  anchor   check one report against the committed code-128 anchor point

HOW THE TEMPLATE BECOMES A `klt sim` BODY (each change is fixture, not DUT):

* `.options temp=... tnom=27` -> `.options tnom=27`: `klt sim` emits the
  corner's `.temp` card itself.
* The template's `.control` block (op / print / ac / wrdata) is replaced by a
  `.control` block holding only its `pre_osdi` lines -- the same OSDI-preload
  deviation from `klt sim`'s body contract sim/harness documents (#2666).
  `klt sim` appends its own `.control` block with the analysis.
* An operating-point probe fixture is added (see OP_PROBE below): `.meas` is
  the only measurement form the batch runner's klt 0.5.0 accepts, and
  `.MEASURE` has no `op` type, so the bench's "op landed near its seed" check
  is carried through the AC run itself.
* `.save` limits the rawfile to the six vectors this bench reads.

HOW THE TRIM CODE IS SWEPT. `corners.supply_v`'s keys sweep together by index
and each becomes an `alter <key>=<value>` before the analysis. The eight
binary straps `RS0`-`RS7` inside the ladder subcircuit are plain resistors
(`{1e-3 + 1e12*<bit>}`: 1 mOhm closed, 1 TOhm open), so keying the axis on
their flattened names (`r.xxtrim.rs<b>`) sets the code per unit exactly as
`.param trim_code=<code>` would. Code 128 alters every strap to the value
the template's own default already gives it.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import solve_quality  # noqa: E402  (shared with run_pvt_sweep.sh; issue #289)
from solve_quality import RIPPLE_BAND_HZ, RIPPLE_MAX_DB, ripple_db  # noqa: E402,F401

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
SIM_DIR = EXPERIMENT_DIR.parent
REPO_ROOT = SIM_DIR.parent
TEMPLATE = EXPERIMENT_DIR / "testbench" / "tb_loop_gain.spice.tmpl"
CROSSOVER_AWK = EXPERIMENT_DIR / "tools" / "find_crossover.awk"

# Pass criteria: run_pvt_sweep.sh's own (see its header comment), behind the
# solve-quality gate of tools/solve_quality.py (issue #289) -- the SAME module
# the shell bench calls, so both paths apply one metric and one threshold.
OP_MATCH_TOL_V = 0.05
PM_MIN_DEG = 0.0
NOTCH_GUARD_DB = 1.0

# The committed anchor this characterization hangs off:
# records/20261001-085806-e5507b2.csv, row wcs/125/2.97 (code 128).
ANCHOR = {
    "record": "sim/loop-gain-phase-margin/records/20261001-085806-e5507b2.csv",
    "fb_op_v": 2.183124,
    "dc_gain_db": 46.3857,
    "phase_margin_deg": 36.3046,
    "crossover_hz": 3.016466e07,
}

CORNER_SECTIONS = {
    "typ": ("hbt_typ", "mos_tt", "res_typ"),
    "bcs": ("hbt_bcs", "mos_ff", "res_bcs"),
    "wcs": ("hbt_wcs", "mos_ss", "res_wcs"),
    "sf": ("hbt_typ", "mos_sf", "res_typ"),
    "fs": ("hbt_typ", "mos_fs", "res_typ"),
}

CODES = [0, 32, 64, 96, 128, 160, 192, 224, 255]
GRIDS = {
    # The bench's own grid (run_pvt_sweep.sh / the template: `ac dec 30 1 1e9`).
    "bench": "dec 30 1 1e9",
    # 10x finer, same span -- issue #271's "finer frequency grid around the
    # crossover/notch" (the span is kept so dc_gain_db stays comparable).
    "fine": "dec 300 1 1e9",
}

# One request (= one batch job) per PVT point x grid x deck variant: the
# .nodeset seed is a per-PVT-point constant baked into the body, so a request
# cannot span points. Points: the anchor; its two same-process/same-temperature
# supply neighbours; and the four next-lowest phase margins in
# 20261001-085806-e5507b2 (83.9, 86.2, 87.1, 87.2 deg). Fine grid: the anchor
# at every code, plus its 3.30 V neighbour at the two ends and the middle of
# the code range, as the like-for-like contrast.
#
# Deck variants. "probe" carries the OP PROBE fixture (the bench's op check).
# "np" (no probe) is the CONTROL: the bench's own matrix, element for element,
# with no added node -- because the anchor's 36.3 deg turned out to move when
# an electrically inert element is added (README "Trim-code axis"), the record
# must carry the unperturbed deck as well. An "np" row has no op readout of
# its own; its op check is that its DC loop gain equals its "probe" twin's
# (same point, code and grid), whose op IS checked against the seed.
PLAN = [
    ("wcs", "125", "2.97", "bench", CODES, "probe"),
    ("wcs", "125", "3.30", "bench", CODES, "probe"),
    ("wcs", "125", "3.63", "bench", CODES, "probe"),
    ("wcs", "-40", "3.63", "bench", CODES, "probe"),
    ("wcs", "27", "3.63", "bench", CODES, "probe"),
    ("wcs", "-40", "3.30", "bench", CODES, "probe"),
    ("fs", "-40", "3.63", "bench", CODES, "probe"),
    ("wcs", "125", "2.97", "fine", CODES, "probe"),
    ("wcs", "125", "3.30", "fine", [0, 128, 255], "probe"),
    ("wcs", "125", "2.97", "bench", CODES, "np"),
    ("wcs", "125", "2.97", "fine", CODES, "np"),
]
# Full-PVT plan (issue #289): the bench's own 45-point grid (5 process x 3
# temperature x 3 supply) at the default trim code, one request per PVT point
# (the .nodeset seed is a per-point constant), probe deck only -- its op check
# is the bench's own. `--plan pvt` selects it; `--plan characterization`
# (default) is the issue-#271 trim-axis PLAN above, preserved unchanged.
DEFAULT_CODE = 128
PVT_TEMPS = ["-40", "27", "125"]
PVT_VDDS = ["2.97", "3.30", "3.63"]
PVT_PLAN = [
    (corner, temp, vdd, "bench", [DEFAULT_CODE], "probe")
    for corner in CORNER_SECTIONS for temp in PVT_TEMPS for vdd in PVT_VDDS
]
PLANS = {"characterization": PLAN, "pvt": PVT_PLAN}

# |dc_gain(np) - dc_gain(probe twin)| at or below this (dB) = same equilibrium.
# find_crossover.awk prints dc_gain_db to 4 decimals; the two decks share every
# DUT element, so the expected difference is 0.0000.
TWIN_DC_GAIN_TOL_DB = 0.001

STRAP_KEYS = [f"r.xxtrim.rs{bit}" for bit in range(8)]
STRAP_CLOSED_OHM = 1e-3
STRAP_OPEN_OHM = 1e12

OP_PROBE = """\
* ------------------------------------------- OP PROBE FIXTURE (issue #271)
* The bench's "op landed near its seed" check reads the DC operating point
* with `op` + `print`. Through `klt sim` that is not expressible: one
* analysis per request (AC here), measurements are `.meas` cards only (the
* batch runner's klt 0.5.0 predates `measurements[].expr`), and `.MEASURE`
* has no `op` type. So the DC bias is carried through the AC run instead:
* `acs` is an isolated node driven by its own 1 V AC / 0 V DC source, and each
* B-source below outputs V(node)*V(acs). Linearized about the operating
* point, its AC response is V(node)_dc * 1 + V(acs)_dc * v_ac(node) =
* V(node)_dc exactly (V(acs)_dc = 0), flat in frequency, real-valued. The
* B-sources only SENSE their controlling node (infinite input impedance) and
* drive nothing but their own 1 MOhm load, so the DUT is not perturbed; and
* `acs` reaches nothing but these B-sources, so Vacs adds no excitation to
* the loop Vtest measures.
Vacs acs 0 dc 0 ac 1
Bop_fb op_fb 0 V = V(fb_load)*V(acs)
Rop_fb op_fb 0 1e6
Bop_sns1 op_sns1 0 V = V(sns1)*V(acs)
Rop_sns1 op_sns1 0 1e6
Bop_sns2 op_sns2 0 V = V(sns2)*V(acs)
Rop_sns2 op_sns2 0 1e6
Bop_vref op_vref 0 V = V(vref)*V(acs)
Rop_vref op_vref 0 1e6

* Rawfile contents: the two loop-break nodes (T = V(fb_src)/V(fb_load)) and
* the four op probes. Nothing else is read, and a full `save all` rawfile at
* the fine grid would be ~100x larger.
.save v(fb_src) v(fb_load) v(op_fb) v(op_sns1) v(op_sns2) v(op_vref)
"""

MEASUREMENTS = [
    ("fb_op_v", ".meas ac fb_op_v find v(op_fb) at=1", "V"),
    ("sns1_op_v", ".meas ac sns1_op_v find v(op_sns1) at=1", "V"),
    ("sns2_op_v", ".meas ac sns2_op_v find v(op_sns2) at=1", "V"),
    ("vref_op_v", ".meas ac vref_op_v find v(op_vref) at=1", "V"),
    ("fb_src_db_1hz", ".meas ac fb_src_db_1hz find vdb(fb_src) at=1", "dB"),
    ("fb_load_db_1hz", ".meas ac fb_load_db_1hz find vdb(fb_load) at=1", "dB"),
]

def point_name(corner: str, temp: str, vdd: str, grid: str, variant: str) -> str:
    return f"{corner}_{temp}c_{vdd}v_{grid}" + ("_np" if variant == "np" else "")


def code_label(corner: str, code: int, grid: str, variant: str) -> str:
    return (f"{corner}_code{code}" + ("_np" if variant == "np" else "")
            + ("_fine" if grid == "fine" else ""))


def strap_values(code: int) -> dict[str, float]:
    if not 0 <= code <= 255:
        raise SystemExit(f"klt_trim_axis.py: trim code {code} outside 0..255")
    return {
        key: (STRAP_OPEN_OHM if (code >> bit) & 1 else STRAP_CLOSED_OHM)
        for bit, key in enumerate(STRAP_KEYS)
    }


def code_from_straps(supply: dict) -> int:
    code = 0
    for bit, key in enumerate(STRAP_KEYS):
        value = supply.get(key)
        if value is None:
            raise SystemExit(f"klt_trim_axis.py: report corner lacks strap key {key}")
        if value > 1.0:
            code |= 1 << bit
    return code


def git_short(path: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%h", "--", path],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip() or "unknown"


def seed_csv() -> Path:
    csvs = sorted((SIM_DIR / "closed-loop-startup" / "records").glob("*.csv"))
    if not csvs:
        raise SystemExit("klt_trim_axis.py: no sim/closed-loop-startup/records/*.csv seed record")
    return csvs[-1]


def lookup_seeds(corner: str, temp: str, vdd: str) -> dict[str, str]:
    with seed_csv().open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row["corner_label"], row["temp_c"], row["vdd_v"], row["status"]) == (
                corner, temp, vdd, "PASS"
            ):
                return {
                    "fb": row["fb_final_v"],
                    "sns1": row["sns1_final_v"],
                    "sns2": row["sns2_final_v"],
                    "vref": row["vref_final_v"],
                }
    raise SystemExit(f"klt_trim_axis.py: no PASS seed row for {corner}/{temp}/{vdd}")


def msense_width() -> str:
    text = (REPO_ROOT / "design" / "netlist" / "bandgap_startup.spice").read_text(encoding="utf-8")
    match = re.search(r"^XMSENSE\s.*?\bw=(\S+)", text, re.M)
    if match is None:
        raise SystemExit("klt_trim_axis.py: cannot parse XMSENSE w= from bandgap_startup.spice")
    return match.group(1)


def render_body(corner: str, temp: str, vdd: str, pdk_root: str, pdk: str, osdi_dir: str,
                probe: bool = True) -> str:
    hbt, mos, res = CORNER_SECTIONS[corner]
    seeds = lookup_seeds(corner, temp, vdd)
    seed_rel = os.path.relpath(seed_csv(), REPO_ROOT)
    subs = {
        "CORNER_LABEL": corner,
        "TEMP_C": temp,
        "VDD": vdd,
        "PDK": pdk,
        "PDK_ROOT": pdk_root,
        "OSDI_DIR": osdi_dir,
        "HBT_SECTION": hbt,
        "MOS_SECTION": mos,
        "RES_SECTION": res,
        "MSENSE_W": msense_width(),
        "FB_SEED": seeds["fb"],
        "SNS1_SEED": seeds["sns1"],
        "SNS2_SEED": seeds["sns2"],
        "VREF_SEED": seeds["vref"],
        "AC_OUT": "(not used: klt sim writes the rawfile)",
        "DUT_GIT_SHA": (
            f"core={git_short('design/netlist/bandgap_core.spice')} "
            f"amp={git_short('design/netlist/bandgap_amp.spice')} "
            f"startup={git_short('design/netlist/bandgap_startup.spice')} "
            f"seeds={Path(seed_rel).name}@{git_short(seed_rel)}"
        ),
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in subs.items():
        text = text.replace(f"@@{key}@@", value)
    leftover = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", text)))
    if leftover:
        raise SystemExit(f"klt_trim_axis.py: unsubstituted template tokens {leftover}")

    lines = text.splitlines()
    out: list[str] = [
        "* klt sim netlist BODY rendered by sim/loop-gain-phase-margin/tools/klt_trim_axis.py",
        "* (issue #271) from testbench/tb_loop_gain.spice.tmpl. Fixture-only changes vs the",
        "* template: `.options temp=` dropped (klt sim emits `.temp`), the analysis",
        "* `.control` block reduced to its pre_osdi lines, the OP PROBE fixture and a",
        "* `.save` card added, `.end` dropped. DUT devices and the loop break: verbatim.",
        "*",
    ]
    temp_options = re.compile(r"^\.options\s+temp=\S+\s+tnom=27\s*$")
    in_control = False
    preload: list[str] = []
    replaced_temp = False
    for line in lines:
        if temp_options.match(line):
            out.append("* temperature: klt sim's own per-corner `.temp` card (issue #271)")
            out.append(".options tnom=27")
            replaced_temp = True
            continue
        if line.strip() == ".control":
            in_control = True
            continue
        if in_control:
            if line.strip().startswith("pre_osdi"):
                preload.append(line.strip())
            if line.strip() == ".endc":
                in_control = False
            continue
        if line.strip() == ".end":
            continue
        out.append(line)
    if not replaced_temp or len(preload) != 4:
        raise SystemExit("klt_trim_axis.py: template shape changed (temp options / pre_osdi)")
    out.append("")
    if probe:
        out.append(OP_PROBE.rstrip())
    else:
        out.append("* CONTROL deck (variant np, issue #271): NO op-probe fixture -- the bench's")
        out.append("* own matrix, element for element. `.save` only selects rawfile vectors.")
        out.append(".save v(fb_src) v(fb_load)")
    out.append("")
    out.append("* OSDI preload only -- klt sim appends its own .control (alter + analysis).")
    out.append(".control")
    out.extend(preload)
    out.append(".endc")
    return "\n".join(out) + "\n"


def build_request(body_path: Path, grid: str, codes: list[int], temp: str, batch: dict | None,
                  probe: bool = True) -> dict:
    straps = {key: [] for key in STRAP_KEYS}
    for code in codes:
        for key, value in strap_values(code).items():
            straps[key].append(value)
    request = {
        "_comment": (
            "Generated by sim/loop-gain-phase-margin/tools/klt_trim_axis.py (issue #271). "
            "corners.supply_v carries the TRIM CODE, not a rail: the eight keys are the "
            "ladder's binary straps (r.xxtrim.rs0..rs7), swept together by index, one "
            "index per code. VDD is fixed in the body with the per-point .nodeset seed."
        ),
        "engine": "ngspice",
        "netlist": str(body_path),
        "netlist_source": "schematic",
        "corners": {"supply_v": straps, "temperature_c": [float(temp)]},
        "analysis": {"kind": "ac", "args": GRIDS[grid]},
        "measurements": [
            {"name": name, "spice": card, "unit": unit} for name, card, unit in MEASUREMENTS
            if probe or "op_" not in card
        ],
        "options": {"timeout_s": 600, "keep_artifacts": True, "waveforms": True},
    }
    if batch is not None:
        request["backend"] = "batch"
        request["batch"] = batch
    return request


def cmd_prepare(args: argparse.Namespace) -> None:
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    pdk = os.environ.get("PDK", "ihp-sg13g2")
    if args.target == "batch":
        pdk_root = args.batch_pdk_root
        batch = {"provision_script_path": args.provision_script}
    else:
        pdk_root = os.environ.get("PDK_ROOT") or ""
        if not pdk_root:
            raise SystemExit("klt_trim_axis.py: PDK_ROOT unset (source sim/env.sh)")
        batch = None
    osdi_dir = os.environ.get("SG13G2_OSDI_DIR") if args.target == "local" else None
    osdi_dir = osdi_dir or f"{pdk_root}/{pdk}/libs.tech/ngspice/osdi"
    names = []
    for corner, temp, vdd, grid, codes, variant in PLANS[args.plan]:
        name = point_name(corner, temp, vdd, grid, variant)
        if args.only and name not in args.only:
            continue
        if args.codes:
            codes = [int(c) for c in args.codes.split(",")]
        probe = variant == "probe"
        point_dir = work / name
        point_dir.mkdir(parents=True, exist_ok=True)
        body = point_dir / "body.spice"
        body.write_text(render_body(corner, temp, vdd, pdk_root, pdk, osdi_dir, probe),
                        encoding="utf-8")
        request = build_request(body, grid, codes, temp, batch, probe)
        (point_dir / "request.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
        meta = {"corner": corner, "temp": temp, "vdd": vdd, "grid": grid, "codes": codes,
                "variant": variant, "target": args.target, "pdk_root": pdk_root,
                "plan": args.plan}
        (point_dir / "point.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        names.append(name)
    print("\n".join(names))


# --------------------------------------------------------------------- record


def read_ascii_raw(path: Path) -> tuple[list[str], list[list[complex]]]:
    """Parse an ngspice ASCII rawfile (complex, one plot) into names + columns."""
    lines = path.read_text(encoding="utf-8").splitlines()
    names: list[str] = []
    nvars = npoints = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("No. Variables:"):
            nvars = int(line.split(":")[1])
        elif line.startswith("No. Points:"):
            npoints = int(line.split(":")[1])
        elif line.startswith("Variables:"):
            for j in range(nvars):
                names.append(lines[i + 1 + j].split()[1])
            i += nvars
        elif line.startswith("Values:"):
            i += 1
            break
        i += 1
    cols: list[list[complex]] = [[] for _ in names]
    tokens: list[str] = []
    for line in lines[i:]:
        tokens.extend(line.split())
    # Each point: "<index> <v0>" then nvars-1 values, each "re,im".
    k = 0
    for _ in range(npoints):
        k += 1  # point index
        for v in range(nvars):
            re_s, _, im_s = tokens[k].partition(",")
            cols[v].append(complex(float(re_s), float(im_s or 0.0)))
            k += 1
    return names, cols


def loop_gain_rows(names: list[str], cols: list[list[complex]]) -> list[tuple[float, float, float]]:
    """(freq, mag_db, phase_deg) of T = V(fb_src)/V(fb_load), phase unwrapped
    point-to-point from the first sample -- the template's own
    `db(...)` / `cph(...)*180/PI` definition."""
    idx = {name.lower(): n for n, name in enumerate(names)}
    freq = cols[0]
    src = cols[idx["v(fb_src)"]]
    load = cols[idx["v(fb_load)"]]
    rows = []
    prev = None
    for f, a, b in zip(freq, src, load):
        try:
            t = a / b
            mag_db = 20.0 * math.log10(abs(t))
            ph = math.atan2(t.imag, t.real)
        except (ZeroDivisionError, ValueError):
            rows.append((f.real, math.nan, math.nan))  # rejected as non_finite
            continue
        if prev is not None:
            while ph - prev > math.pi:
                ph -= 2 * math.pi
            while ph - prev < -math.pi:
                ph += 2 * math.pi
        prev = ph
        rows.append((f.real, mag_db, ph * 180.0 / math.pi))
    return rows


def write_ac_txt(rows: list[tuple[float, float, float]], path: Path) -> None:
    # ngspice `wrdata` column layout (freq mag freq phase), as the bench writes.
    with path.open("w", encoding="utf-8") as handle:
        for f, m, p in rows:
            handle.write(f" {f:.8e}  {m:.8e}  {f:.8e}  {p:.8e}\n")


def crossover(ac_txt: Path) -> list[str]:
    out = subprocess.run(["awk", "-f", str(CROSSOVER_AWK), str(ac_txt)],
                         capture_output=True, text=True, check=True)
    return out.stdout.split()


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "klt_sim_evidence", SIM_DIR / "harness" / "klt_sim_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_text(deck: Path, body: Path, pdk_root: str, adapter) -> str:
    """The unit's generated deck with the body inlined and host paths made
    ${PDK_ROOT}-relative. A batch deck `.include`s the body under the fleet
    instance's own job directory; repoint that at the local body (byte-for-byte
    the file that was staged) before inlining, as sim/harness/probe does."""
    tmp = deck.with_suffix(".snapshot-src.cir")
    text = deck.read_text(encoding="utf-8").splitlines()
    fixed = []
    for line in text:
        m = re.match(r'^(\s*\.include\s+)"?([^"\s]+)"?(.*)$', line, re.I)
        if m and Path(m.group(2)).name in ("netlist.cir", body.name):
            line = f"{m.group(1)}{body}{m.group(3)}"
        fixed.append(line)
    tmp.write_text("\n".join(fixed) + "\n", encoding="utf-8")
    lines = adapter.inline_deck(tmp, pdk_root)
    tmp.unlink()
    rendered = "\n".join(lines) + "\n"
    if pdk_root:
        rendered = rendered.replace(pdk_root.rstrip("/"), "${PDK_ROOT}")
    # klt's own `write <rawfile>` names the executing host's scratch path.
    rendered = re.sub(r"^(write\s+)(\S+)", lambda m: m.group(1) + Path(m.group(2)).name,
                      rendered, flags=re.M)
    return rendered


def analyse_unit(corner: dict, meta: dict, point_dir: Path) -> dict:
    code = code_from_straps(corner.get("supply_v") or {})
    got = {m["name"]: m.get("value") for m in corner.get("measurements", [])}
    arts = corner.get("artifacts") or {}
    result = {"code": code, "klt_status": corner.get("status"), "got": got, "arts": arts,
              "diagnostics": corner.get("diagnostics") or []}
    raw = arts.get("raw")
    if not raw or not Path(raw).is_file():
        result["rows"] = None
        return result
    names, cols = read_ascii_raw(Path(raw))
    result["rows"] = loop_gain_rows(names, cols)
    idx = {name.lower(): n for n, name in enumerate(names)}
    result["raw_fb_op"] = cols[idx["v(op_fb)"]][0].real if "v(op_fb)" in idx else None
    return result


def cmd_record(args: argparse.Namespace) -> None:
    work = Path(args.work).resolve()
    exp = Path(args.experiment).resolve()
    rid = args.record_id
    adapter = load_adapter()
    corners_dir = exp / "corners" / rid
    snaps_dir = exp / "netlist-snapshots" / rid
    for d in (corners_dir, snaps_dir):
        if d.exists():
            raise SystemExit(f"klt_trim_axis.py: {d} exists -- records are append-only")
    corners_dir.mkdir(parents=True)
    snaps_dir.mkdir(parents=True)

    header = ["corner_label", "hbt_section", "mos_section", "res_section", "temp_c", "vdd_v",
              "msense_w", "status", "trim_code", "ac_grid", "deck", "op_check", "fb_seed_v",
              "fb_op_v", "sns1_op_v", "sns2_op_v", "vref_op_v", "dc_gain_db", "crossover_hz",
              "phase_margin_deg", "n_crossings", "notch_min_db", "notch_min_hz",
              "notch_margin_flag", "ripple_db", "quality", "reject_reason"]
    rows: list[dict] = []
    jobs: list[dict] = []
    width = msense_width()

    # Pass 1: every unit -> a row with its loop-gain numbers; status deferred.
    for c, temp, vdd, grid, _codes, variant in PLANS[args.plan]:
        name = point_name(c, temp, vdd, grid, variant)
        point_dir = work / name
        report_path = point_dir / "report.json"
        if not report_path.is_file():
            continue
        meta = json.loads((point_dir / "point.json").read_text(encoding="utf-8"))
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise SystemExit(f"klt_trim_axis.py: {report_path} is not a klt sim report "
                             f"(see {point_dir / 'submit.stderr'})")
        env = report.get("environment") or {}
        remote = env.get("remote") or {}
        jobs.append({"point": name, "status": report.get("status"),
                     "engine": env.get("engine_version"),
                     **{k: remote.get(k) for k in ("provider", "job_id", "instance_type",
                                                   "availability_zone", "ami_id", "state",
                                                   "exit_code", "elapsed_seconds")}})
        seeds = lookup_seeds(c, temp, vdd)
        hbt, mos, res = CORNER_SECTIONS[c]
        for corner in report.get("corners", []):
            unit = analyse_unit(corner, meta, point_dir)
            label = code_label(c, unit["code"], grid, variant)
            cid = f"{label}_{temp}c_{vdd}v"
            got = unit["got"]
            row = {"corner_label": label, "hbt_section": hbt, "mos_section": mos,
                   "res_section": res, "temp_c": temp, "vdd_v": vdd, "msense_w": width,
                   "trim_code": unit["code"], "ac_grid": GRIDS[grid].replace(" ", "_"),
                   "deck": variant, "op_check": "seed" if variant == "probe" else "twin_dc_gain",
                   "fb_seed_v": seeds["fb"],
                   "_cid": cid, "_klt": unit["klt_status"], "_grid": grid, "_variant": variant,
                   "_point": (c, temp, vdd)}
            for key in ("fb_op_v", "sns1_op_v", "sns2_op_v", "vref_op_v"):
                v = got.get(key)
                row[key] = "" if v is None else f"{v:.6e}"
            for key in ("dc_gain_db", "crossover_hz", "phase_margin_deg", "n_crossings",
                        "notch_min_db", "notch_min_hz", "notch_margin_flag", "ripple_db",
                        "reject_reason"):
                row[key] = ""
            # Solve-quality gate (issue #289), before any margin is read.
            q_ok, q_ripple, q_reason = solve_quality.assess(unit["rows"])
            row["_q_ok"] = q_ok
            row["quality"] = "ok" if q_ok else "inconclusive"
            row["reject_reason"] = "" if q_ok else q_reason
            if q_ripple is not None:
                row["ripple_db"] = f"{q_ripple:.4f}"
            if unit["rows"] is not None:
                ac_txt = corners_dir / f"{cid}.ac.txt"
                write_ac_txt(unit["rows"], ac_txt)
            if unit["rows"] is not None and q_reason != "non_finite":
                status, fc, pm, dc_gain, ncross, nmin, nmin_hz = crossover(ac_txt)
                # A rejected solve keeps dc_gain / n_crossings / notch_* as
                # DIAGNOSTICS only; it never publishes crossover or margin.
                row.update({"dc_gain_db": dc_gain, "n_crossings": ncross, "notch_min_db": nmin,
                            "notch_min_hz": nmin_hz,
                            "notch_margin_flag": "marginal" if abs(float(nmin)) <= NOTCH_GUARD_DB
                            else "clear", "_found": status, "_pm": pm})
                if q_ok and status == "FOUND":
                    row.update({"crossover_hz": fc, "phase_margin_deg": pm})
            rows.append(row)
            log = unit["arts"].get("log")
            if log and Path(log).is_file():
                shutil.copyfile(log, corners_dir / f"{cid}.log")
            else:
                (corners_dir / f"{cid}.log").write_text(
                    f"klt sim returned no log artifact for this unit (status {unit['klt_status']})\n"
                    + json.dumps(unit["diagnostics"], indent=2) + "\n", encoding="utf-8")
            deck = unit["arts"].get("deck")
            body = point_dir / "body.spice"
            if deck and Path(deck).is_file():
                snap = snapshot_text(Path(deck), body, meta["pdk_root"], adapter)
            else:
                snap = body.read_text(encoding="utf-8").replace(
                    meta["pdk_root"].rstrip("/") + "/", "${PDK_ROOT}/")
            (snaps_dir / f"{cid}.spice").write_text(snap, encoding="utf-8")

    if not rows:
        raise SystemExit("klt_trim_axis.py: no report.json found under the work dir")

    # Pass 2: run_pvt_sweep.sh's criteria behind the solve-quality gate
    # (solve_quality.decide). The control deck's op check is taken from its
    # probe twin: the twin must itself be a clean solve whose own op check
    # against the seed passed, and the control's DC loop gain must equal it.
    twins = {(r["_point"], r["trim_code"], r["_grid"]): r for r in rows if r["_variant"] == "probe"}

    def probe_op_ok(r) -> bool:
        return bool(r["fb_op_v"]) and (
            abs(float(r["fb_op_v"]) - float(r["fb_seed_v"])) <= OP_MATCH_TOL_V)

    failed: list[str] = []
    marginal: list[str] = []
    inconclusive: list[str] = []
    for row in rows:
        cid = row["_cid"]
        if row["_klt"] != "pass" or not row["dc_gain_db"]:
            row["status"] = "FAIL"
            if row["quality"] != "ok":
                inconclusive.append(f"{cid} ({row['reject_reason']}, klt status {row['_klt']})")
            failed.append(f"{cid} (klt status {row['_klt']}, no loop-gain data)")
            continue
        if row["_variant"] == "probe":
            op_ok = probe_op_ok(row)
        else:
            twin = twins.get((row["_point"], row["trim_code"], row["_grid"]))
            op_ok = bool(twin and twin["dc_gain_db"] and twin["_q_ok"] and probe_op_ok(twin)) and (
                abs(float(row["dc_gain_db"]) - float(twin["dc_gain_db"])) <= TWIN_DC_GAIN_TOL_DB)
        verdict, cross_ok, marginal_used = solve_quality.decide(
            row["_q_ok"], op_ok, row["_found"],
            float(row["_pm"]) if row["_found"] == "FOUND" else None,
            row["notch_margin_flag"] == "marginal", PM_MIN_DEG)
        row["status"] = verdict
        if not row["_q_ok"]:
            inconclusive.append(f"{cid} ({row['reject_reason']}, ripple_db={row['ripple_db'] or 'n/a'})")
        elif marginal_used and verdict == "PASS":
            marginal.append(f"{cid} (notch_min={row['notch_min_db']} dB)")
        if verdict == "FAIL":
            failed.append(f"{cid} (quality={row['quality']} op_ok={op_ok} crossing_ok={cross_ok})")

    csv_path = exp / "records" / f"{rid}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    (exp / "records" / f"{rid}.jobs.json").write_text(json.dumps(jobs, indent=2) + "\n",
                                                      encoding="utf-8")
    passed = sum(1 for r in rows if r["status"] == "PASS")
    write_md(exp / "records" / f"{rid}.md", rid, rows, passed, failed, marginal, jobs, args,
             inconclusive)
    print(f"klt_trim_axis.py: record {rid}: {passed}/{len(rows)} points PASS")


def write_md(path: Path, rid: str, rows, passed, failed, marginal, jobs, args,
             inconclusive) -> None:
    seed_rel = os.path.relpath(seed_csv(), REPO_ROOT)
    engines = sorted({j.get("engine") or "unknown" for j in jobs})
    backends = sorted({"batch" if j.get("job_id") else "local" for j in jobs})
    points = sorted({(r["corner_label"].split("_code")[0], r["temp_c"], r["vdd_v"]) for r in rows})
    if args.plan == "pvt":
        lines = [
            f"# Record {rid}",
            "",
            "- **Experiment**: loop-gain-phase-margin (full PVT grid at trim code 128,",
            "  solve-quality-gated, issue #289)",
            "- **Claim**: the SAME closed-loop Middlebrook loop-gain bench as",
            "  run_pvt_sweep.sh (testbench/tb_loop_gain.spice.tmpl, unchanged DUT and",
            "  loop break) at the bench's own 45-point PVT grid -- process {typ, bcs,",
            "  wcs, sf, fs} x temperature {-40, 27, 125} C x supply {2.97, 3.30, 3.63}",
            "  V -- at the default trim code 128, run through `klt sim` (one request per",
            "  PVT point, since the .nodeset seed is per point) instead of a local",
            "  `ngspice -b` loop. Every unit passes the solve-quality gate below before",
            "  a margin is read. Rows are the `probe` deck (the OP PROBE fixture carries",
            "  the bench's op check); it is not byte-identical in matrix to",
            "  run_pvt_sweep.sh's deck (README \"Solve-quality gate\").",
        ]
    else:
        lines = [
            f"# Record {rid}",
            "",
            "- **Experiment**: loop-gain-phase-margin (trim-code axis, issue #271)",
        ]
    if args.plan != "pvt":
        lines += [
            "- **Claim**: the SAME closed-loop Middlebrook loop-gain bench as this",
            "  experiment's 45-point records (testbench/tb_loop_gain.spice.tmpl,",
            "  unchanged DUT and loop break), re-run with the TRIM CODE as an axis:",
            "  at each listed PVT point the ladder's eight binary straps are set per",
            f"  code ({', '.join(str(c) for c in CODES)}) and the loop gain",
            "  T = V(fb_src)/V(fb_load) is measured by AC analysis. Phase margin,",
            "  crossover, crossing count and notch minimum come from the bench's own",
            "  tools/find_crossover.awk over T; `ripple_db` (README \"Trim-code axis\")",
            "  is the largest single-point departure of |T| from its 3-point median",
            "  in 10-200 MHz. Two AC grids: the bench's `dec 30` and a 10x finer",
            "  `dec 300` (rows labelled `_fine`). Two deck variants (CSV `deck`):",
            "  `probe` carries the OP PROBE fixture that reads the DC bias for the",
            "  bench's op check; `np` (rows labelled `_np`) is the CONTROL -- the",
            "  bench's own matrix with no added element -- whose op check is that its",
            f"  DC loop gain equals its probe twin's to {TWIN_DC_GAIN_TOL_DB} dB",
            "  (CSV `op_check`).",
        ]
    lines += [
        "- **Harness**: `klt sim` via tools/klt_trim_axis.py (run_klt_trim_axis.sh),",
        f"  backend: {', '.join(backends)}; one request per PVT point, trim code"
        + (" fixed at 128" if args.plan == "pvt" else " swept")
        + " by `alter` of the strap resistors (`corners.supply_v` keys",
        "  r.xxtrim.rs0..rs7). Per-request job ids, instance types and engine",
        f"  versions: `records/{rid}.jobs.json`.",
        "- **XMSENSE width this run used**: w=" + msense_width(),
        "- **Devices**: all real PDK compact models, all three DUTs copied",
        "  verbatim from design/netlist/bandgap_core.spice,",
        "  design/netlist/bandgap_amp.spice and design/netlist/bandgap_startup.spice",
        "  (via the bench template) plus the Lbreak/Vtest loop-break fixture and,",
        "  on `probe` rows only, the OP PROBE fixture (isolated B-sources reading",
        "  the DC bias through the AC run -- see tools/klt_trim_axis.py). The ladder's `RS<b>`",
        "  straps are the design's own behavioural mask-option cards, set per",
        "  code by `alter`.",
        "- **Netlist provenance**: schematic",
        f"  (design/netlist/bandgap_core.spice @ `{git_short('design/netlist/bandgap_core.spice')}`,",
        f"  design/netlist/bandgap_amp.spice @ `{git_short('design/netlist/bandgap_amp.spice')}`,",
        f"  design/netlist/bandgap_startup.spice @ `{git_short('design/netlist/bandgap_startup.spice')}`).",
        f"- **Nodeset seed provenance**: `{seed_rel}` @ `{git_short(seed_rel)}`",
        "  (code-128 closed-loop endpoints; the same seed serves every code at a",
        "  point, and the op check below is the bench's own, unchanged).",
        "- **PDK**: `ihp-sg13g2` -- pinned release: see `sim/pdk.json`",
        "  (batch: the fleet runner image's baked copy; local: `${PDK_ROOT}`).",
        "- **OSDI models**: PSP103 / r3_cmc / mosvar, preloaded with `pre_osdi`",
        "  from the executing host's PDK tree.",
        f"- **ngspice**: {', '.join(f'`{e}`' for e in engines)}",
        "- **Corner matrix run**: PVT points "
        + ", ".join(f"{c}/{t}C/{v}V" for c, t, v in points)
        + ("" if args.plan == "pvt" else " x trim code")
        + f"; {len(rows)} points total (see CSV `trim_code`/`ac_grid`).",
        f"- **Result**: {passed}/{len(rows)} points PASS (solve-quality gate, then run_pvt_sweep.sh's own",
        f"  criteria: .op within {OP_MATCH_TOL_V} V of the .nodeset seed (np rows: the",
        "  twin DC-gain check above),",
        f"  AND either a falling 0 dB crossing with phase margin > {PM_MIN_DEG:g} deg",
        f"  or a notch minimum within +-{NOTCH_GUARD_DB} dB of 0 dB).",
    ]
    lines += [
        f"- **Solve-quality gate (issue #289)**: every unit's AC response is checked",
        f"  before any margin is read (tools/solve_quality.py, the module",
        f"  run_pvt_sweep.sh also calls): finite, spans 1 Hz-1 GHz, >= "
        f"{solve_quality.MIN_BAND_POINTS} points in 10-200 MHz, and `ripple_db` <=",
        f"  {RIPPLE_MAX_DB:g} dB. A unit that fails is `quality=inconclusive` (CSV",
        "  `quality`/`reject_reason`), status FAIL, with `crossover_hz` and",
        "  `phase_margin_deg` blank (its dc_gain/crossing/notch columns are",
        "  diagnostics only; the raw `.ac.txt` and log are kept), and the",
        "  marginal-notch exception is not consulted. No retry was attempted:",
        "  rejection is fail-closed. The gate detects the observed",
        "  isolated-jump signature in 10-200 MHz; it does not claim to detect every",
        "  possible solver corruption (README \"Solve-quality gate\").",
        f"  Quality: {sum(1 for r in rows if r['quality'] == 'ok')} ok, "
        f"{sum(1 for r in rows if r['quality'] != 'ok')} inconclusive of {len(rows)}.",
    ]
    if inconclusive:
        lines.append("- **Inconclusive points (rejected, no margin published)**: "
                     + "; ".join(inconclusive))
    if marginal:
        lines.append("- **Marginal-notch points**: " + "; ".join(marginal))
    if failed:
        lines.append("- **Failed points**: " + "; ".join(failed))
    lines += [
        "- **Links**:",
        "  - Template: `testbench/tb_loop_gain.spice.tmpl`; body/request generator:",
        "    `tools/klt_trim_axis.py`",
        f"  - Per-point decks (body inlined): `netlist-snapshots/{rid}/`",
        f"  - Per-point ngspice logs + loop-gain data: `corners/{rid}/`",
        f"  - Parsed CSV: `records/{rid}.csv`; batch job ledger: `records/{rid}.jobs.json`",
        "- **Timestamp / author**: "
        + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        + ", Loom Builder (agent), issue " + ("#289." if args.plan == "pvt" else "#271."),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_anchor(args: argparse.Namespace) -> None:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    (corner,) = [c for c in report["corners"]
                 if code_from_straps(c.get("supply_v") or {}) == 128] or [None]
    if corner is None:
        raise SystemExit("klt_trim_axis.py: no code-128 unit in that report")
    unit = analyse_unit(corner, {}, Path(args.report).parent)
    if unit["rows"] is None:
        raise SystemExit(f"klt_trim_axis.py: no rawfile (klt status {unit['klt_status']})")
    tmp = Path(args.report).with_name("anchor.ac.txt")
    write_ac_txt(unit["rows"], tmp)
    status, fc, pm, dc_gain, ncross, nmin, nmin_hz = crossover(tmp)
    fb = unit["got"].get("fb_op_v")
    if fb is not None:
        print(f"  fb_op_v          {fb!r} (raw {unit['raw_fb_op']:.7g}; anchor {ANCHOR['fb_op_v']})")
    else:
        print("  fb_op_v          (np deck: no op probe)")
    print(f"  dc_gain_db       {dc_gain} (anchor {ANCHOR['dc_gain_db']})")
    print(f"  crossover_hz     {fc} (anchor {ANCHOR['crossover_hz']:.6e})")
    print(f"  phase_margin_deg {pm} (anchor {ANCHOR['phase_margin_deg']})")
    print(f"  n_crossings {ncross}  notch_min_db {nmin} @ {nmin_hz}  ripple_db {ripple_db(unit['rows']):.4f}")
    q_ok, _q_ripple, q_reason = solve_quality.assess(unit["rows"])
    if q_ok:
        print("  solve quality    ok -- an ACCEPTABLE margin (compare, do not equate, with the anchor)")
    else:
        print(f"  solve quality    REJECT ({q_reason}) -- this REPRODUCES the corrupted artifact the "
              "committed anchor row carries; its margin is not an accepted result")


def cmd_ripple_scan(args: argparse.Namespace) -> None:
    """`ripple_db` (same definition as the record column) for every committed
    `*.ac.txt` in a record's corners/ dir -- run_pvt_sweep.sh's own `wrdata`
    files included -- so a solve-quality reading of an EXISTING record is
    reproducible from committed data alone."""
    results = []
    for ac in sorted(Path(args.corners).glob("*.ac.txt")):
        rows = []
        for line in ac.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 4:
                rows.append((float(parts[0]), float(parts[1]), float(parts[3])))
        results.append((ripple_db(rows), ac.name[:-len(".ac.txt")]))
    for value, name in sorted(results, reverse=True):
        print(f"{value:8.4f}  {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--work", required=True)
    p.add_argument("--target", choices=("local", "batch"), required=True)
    p.add_argument("--only", nargs="*")
    p.add_argument("--plan", choices=tuple(PLANS), default="characterization",
                   help="characterization: issue #271 trim-axis PLAN; pvt: the 45-point "
                        "PVT grid at code 128 (issue #289)")
    p.add_argument("--codes", help="override the code list, e.g. 128 (single-unit local anchor)")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--provision-script",
                   default=os.path.expanduser("~/GitHub/2am/infra/aws/batch-fleet-provision.sh"))
    p.set_defaults(func=cmd_prepare)
    r = sub.add_parser("record")
    r.add_argument("--work", required=True)
    r.add_argument("--experiment", default=str(EXPERIMENT_DIR))
    r.add_argument("--record-id", required=True)
    r.add_argument("--plan", choices=tuple(PLANS), default="characterization")
    r.set_defaults(func=cmd_record)
    a = sub.add_parser("anchor")
    a.add_argument("--report", required=True)
    a.set_defaults(func=cmd_anchor)
    s = sub.add_parser("ripple-scan")
    s.add_argument("corners", help="a record's corners/<record-id>/ directory")
    s.set_defaults(func=cmd_ripple_scan)
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
