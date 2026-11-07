#!/usr/bin/env python3
"""`klt sim` decks plumbing for sim/closed-loop-vref-trim-mc (issue #423, Part of #412).

The trim-domain mismatch Monte Carlo is a seeded two-stage campaign whose
second stage depends on the first: per (point, draw) a FIT of three 27 C decks
(trim_code 0/1/255) picks `code*` for that die, and a VERIFY of three decks
(-40/27/125 C at `code*`) measures the trimmed line. `corners.params` cannot
vary the code per sample and `monte_carlo` is not used (the seed is a
parse-time `.options rndseed` in the deck, die identity across a draw's six
decks), so the campaign rides klt's pre-composed `decks` transport: klt ships
each deck byte-for-byte and returns the raw ngspice output; this module owns
everything else.

* `prepare --stage fit`   renders the fit decks and the `decks` requests;
* `codes`                 parses the fit logs host-side and computes `code*`
                          with the exact formula run_trim_mc.sh used;
* `prepare --stage verify` renders the verify decks for the draws that fit;
* `assemble`              parses the verify logs, writes the per-draw CSV
                          (`-draws.csv`, header unchanged), the digest, the
                          negative-control gate and a corner-shaped report
                          for sim/harness/klt_sim_evidence.py;
* `spec`                  fills the record spec's `msense_w`;
* `prepare --stage attrib` / `assemble-attrib`
                          the controlled mismatch decomposition (issue #303): one
                          untrimmed 27 C deck per (variant, draw), where a variant
                          switches device GROUPS' mismatch off with the PDK's own
                          per-instance `mm_ok=0` parameter (the draw identity is kept:
                          the RNG is still consumed, only the sigma multiplier is 0);
* `rule`                  fits the re-aim code-offset rule from a plain-trim draws CSV
                          and `prepare --stage reaim` renders the verify decks at it.

Every parse rule is a line-for-line port of run_trim_mc.sh (kept as the
point-definition reference; it must not be run as a grid on a dispatch host).
A deck that failed or timed out becomes a FAIL row, as in the script; a unit
that never came back at all (no result tree) refuses the whole record: a
partial draw set is never recorded. No simulator is launched from here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

POINTS = ("nominal", "negctrl", "bcs", "wcs")
CORNER_OF = {"nominal": "typ", "negctrl": "typ", "bcs": "bcs", "wcs": "wcs"}
MODE_OF = {"nominal": "mismatch", "negctrl": "negctrl", "bcs": "mismatch", "wcs": "mismatch"}
DIGEST_LABEL_OF = {"nominal": "typ_mismatch", "negctrl": "typ_negctrl",
                   "bcs": "bcs_mismatch", "wcs": "wcs_mismatch"}
# sim/lib/pvt_preflight.sh
HBT = {"typ": "hbt_typ", "bcs": "hbt_bcs", "wcs": "hbt_wcs"}
MOS = {"typ": "mos_tt", "bcs": "mos_ff", "wcs": "mos_ss"}
RES = {"typ": "res_typ", "bcs": "res_bcs", "wcs": "res_wcs"}

VDD = "3.30"
TEMP_TRIM_C = 27
VERIFY_TEMPS = (-40, 27, 125)
FIT_CODES = (0, 1, 255)
VREF_TARGET_V = 1.050
TRIM_BUDGET_PCT = 0.5
UNIT_TIMEOUT_S = 300
DRAWS_PER_REQUEST = 100
SANITY_POINTS = ("negctrl", "nominal")

DRAWS_HEADER = ("point,mismatch_mode,draw_index,seed,corner_label,fit0_vref_v,fit1_vref_v,"
                "fit255_vref_v,unit_v,lin_resid_v,code_star,verify_status,vref_27c_v,"
                "vref_n40c_v,vref_125c_v,dev_27c_pct,dev_n40c_pct,dev_125c_pct,max_dev_pct,"
                "within_0p5,railed")
DIGEST_HEADER = ["corner_label", "hbt_section", "mos_section", "res_section", "temp_c", "vdd_v",
                 "msense_w", "status", "n_draws", "n_pass", "frac_within_0p5_pct",
                 "three_sigma_max_dev_pct", "worst_max_dev_pct", "mean_code_star",
                 "sigma_code_star", "min_code_star", "max_code_star", "n_railed",
                 "mean_unit_mv", "sigma_unit_mv", "mean_lin_resid_uv"]

BAD_LOG = re.compile(r"Unable to find definition of model|couldn't be loaded|Unknown model type|"
                     r"Simulation interrupted", re.IGNORECASE)
SEED_FIELDS = (("@@FB_SEED@@", "fb_final_v"), ("@@SNS1_SEED@@", "sns1_final_v"),
               ("@@SNS2_SEED@@", "sns2_final_v"), ("@@VREF_SEED@@", "vref_final_v"))


# --------------------------------------------------------------- rendering

def sections(point: str) -> tuple[str, str, str]:
    corner = CORNER_OF[point]
    suffix = "_mismatch" if MODE_OF[point] == "mismatch" else ""
    return HBT[corner] + suffix, MOS[corner] + suffix, RES[corner] + suffix


# --- mismatch attribution (issue #303) --------------------------------------
# Instance-name groups of the DUT (the template's X-cards). A group's mismatch is
# switched off by appending `mm_ok=0` to its cards: the PDK's MOS and resistor
# subcircuits take `mm_ok` as a per-instance parameter that is the sigma multiplier of
# every agauss/gauss in the card (`agauss(x, s, (mm_ok != 1 ? 0 : 1))`), so the draw
# stream is consumed identically and every OTHER device keeps its exact draw. The
# bipolars (XQ*) carry no mismatch expression in the PDK's HBT mismatch library at all
# (npn13G2 takes mm_ok too: qarea = agauss(1, 0.1, mm_ok != 1 ? 0 : 1), a 10 % sigma emitter-area
# draw per device independent of Nx -- found by the `none` control, which first read nonzero
# spread when the bipolars were wrongly assumed mismatch-free).
ATTRIB_GROUPS = {
    "amp_input": r"XMP[12]",
    "amp_bias_load": r"XMTAIL|XMP[34]",
    "amp_mirror_nmos": r"XMN[1-4]",
    "core_mirror": r"XM1|XM2[AB]|XM3[ABC]",
    "r_core": r"XR[12]",
    "r_ladder": r"XRU\d+",
    "startup": r"XRPU|XMSENSE|XMKFB",
    "bipolar": r"XQ[123]",
}
NO_MISMATCH_CARDS = r"XXTRIM"   # the ladder subckt call (its own cards are in r_ladder)
# Diagnostic controls: `none` with one family's section swapped for its plain (no-mismatch) twin,
# to localise any residual spread that mm_ok=0 does not remove.
DIAG_VARIANTS = ["none_plainres", "none_plainmos", "none_plainhbt", "none_plainall"]
CAMPAIGN_DIAG = ["none_plainall"]   # the only diagnostic in the full campaign (a hard gate)
ATTRIB_CODE = 128      # untrimmed: the mid-scale default code
ATTRIB_TEMP_C = 27


def attrib_variants() -> list[str]:
    """negctrl: plain sections. none: mismatch sections, every group's mm_ok=0 (must be exactly
    zero-spread; NOT equal to negctrl -- the mismatch-section resistor card shifts the mean by a
    deterministic ~1 mV). none_plainall: plain sections for every family (must equal negctrl).
    The other none_plain* diagnostics are run on demand (KLT_SIM_VARIANTS). all: the full draw. only_<g>: one group on. loo_<g>: all but g on."""
    return (["negctrl", "none"] + CAMPAIGN_DIAG + ["all"] + [f"only_{g}" for g in ATTRIB_GROUPS]
            + [f"loo_{g}" for g in ATTRIB_GROUPS])


def groups_on(variant: str) -> set[str]:
    if variant in ("negctrl", "none", *DIAG_VARIANTS):
        return set()
    if variant == "all":
        return set(ATTRIB_GROUPS)
    kind, _, g = variant.partition("_")
    if kind == "only" and g in ATTRIB_GROUPS:
        return {g}
    if kind == "loo" and g in ATTRIB_GROUPS:
        return set(ATTRIB_GROUPS) - {g}
    raise SystemExit(f"unknown attribution variant: {variant}")


def apply_mm_ok(text: str, on: set[str]) -> str:
    """Append ` mm_ok=0` to every X-card whose group is off. Every X-card must belong to
    a group (or be a known mismatch-free card): an unassigned card fails loudly, so a
    template edit cannot silently leave a device outside the decomposition."""
    out = []
    for line in text.split("\n"):
        tok = line.split(None, 1)[0] if line.strip() else ""
        if tok.startswith("X"):
            grp = next((g for g, rx in ATTRIB_GROUPS.items() if re.fullmatch(rx, tok)), None)
            if grp is None and not re.fullmatch(NO_MISMATCH_CARDS, tok):
                raise SystemExit(f"attribution: X-card {tok} belongs to no ATTRIB_GROUPS group")
            if grp is not None and grp not in on:
                line = line.rstrip() + " mm_ok=0"
        out.append(line)
    return "\n".join(out)


def render_attrib_deck(template: str, ctx: dict, variant: str, draw: int) -> str:
    point = "negctrl" if variant == "negctrl" else "nominal"
    text = render_deck(template, ctx, point, draw, ATTRIB_TEMP_C, ATTRIB_CODE, "attrib")
    text = text.replace(f"point={point}", f"point={variant}", 1)
    if variant == "negctrl":
        return text
    text = apply_mm_ok(text, groups_on(variant))
    if variant in DIAG_VARIANTS:
        hbt, mos, res = sections("nominal")
        fam = {"none_plainres": [("cornerRES.lib", res)], "none_plainmos": [("cornerMOShv.lib", mos)],
               "none_plainhbt": [("cornerHBT.lib", hbt)],
               "none_plainall": [("cornerRES.lib", res), ("cornerMOShv.lib", mos), ("cornerHBT.lib", hbt)]}[variant]
        for lib, sec in fam:
            old = f'{lib}" {sec}'
            if old not in text:
                raise SystemExit(f"diagnostic variant {variant}: {old!r} not in deck")
            text = text.replace(old, f'{lib}" {sec.removesuffix("_mismatch")}', 1)
    return text


def attrib_id(variant: str, draw: int) -> str:
    return f"attrib_{variant}_{draw}"


def fit_id(point: str, draw: int, code: int) -> str:
    return f"fit_{point}_{draw}_c{code}"


def verify_id(point: str, draw: int, temp: int, code: int) -> str:
    return f"verify_{point}_{draw}_t{temp}_c{code}"


def load_seeds(seed_csv: str) -> dict:
    seeds: dict = {}
    with open(seed_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "PASS":
                seeds[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row
    return seeds


def render_deck(template: str, ctx: dict, point: str, draw: int, temp: int, code: int,
                stage: str) -> str:
    """The template filled exactly as run_trim_mc.sh's render_netlist() fills it."""
    corner = CORNER_OF[point]
    row = ctx["seeds"].get((corner, str(temp), VDD))
    if row is None:
        raise SystemExit(f"no PASS seed row for {corner}/{temp}C/{VDD}V in {ctx['seed_csv']}")
    hbt, mos, res = sections(point)
    mapping = {
        "@@PDK_ROOT@@": ctx["pdk_root"], "@@PDK@@": ctx["pdk"], "@@OSDI_DIR@@": ctx["osdi_dir"],
        "@@TEMP_C@@": str(temp), "@@VDD@@": VDD, "@@CORNER_LABEL@@": corner,
        "@@HBT_SECTION@@": hbt, "@@MOS_SECTION@@": mos, "@@RES_SECTION@@": res,
        "@@MSENSE_W@@": ctx["msense_w"], "@@TRIM_CODE@@": str(code),
        "@@SEED@@": str(ctx["seed"] + draw), "@@DRAW_INDEX@@": str(draw),
        "@@POINT_LABEL@@": point, "@@STAGE@@": stage, "@@MISMATCH_MODE@@": MODE_OF[point],
        "@@DUT_GIT_SHA@@": ctx["dut_sha"],
    }
    mapping.update({token: row[field] for token, field in SEED_FIELDS})
    text = template
    for token, value in mapping.items():
        text = text.replace(token, value)
    left = sorted({w for w in text.split() if w.startswith("@@") and w.endswith("@@")})
    if left:
        raise SystemExit(f"deck template has unfilled placeholders: {left}")
    return text


def make_ctx(a: argparse.Namespace, local: bool) -> dict:
    return {
        "seeds": load_seeds(a.seed_csv), "seed_csv": a.seed_csv, "seed": a.seed, "pdk": a.pdk,
        "pdk_root": a.local_pdk_root if local else a.batch_pdk_root,
        "osdi_dir": a.local_osdi_dir if local else a.batch_osdi_dir,
        "msense_w": a.msense_w, "dut_sha": a.dut_sha,
    }


def write_requests(work: Path, stage: str, units: list[dict], a: argparse.Namespace) -> None:
    """Chunk UNITS ({point, draw, id, text}) into one decks request per
    (point, DRAWS_PER_REQUEST draws); write decks + requests + a manifest."""
    (work / "decks").mkdir(parents=True, exist_ok=True)
    groups: dict[tuple[str, int], list[dict]] = {}
    for u in units:
        groups.setdefault((u["point"], u["draw"] // a.draws_per_request), []).append(u)
    manifest = []
    for (point, chunk), members in sorted(groups.items()):
        stem = f"request-{stage}-{point}-{chunk:02d}"
        entries = []
        for u in members:
            rel = f"decks/{u['id']}.spice"
            (work / rel).write_text(u["text"])
            entries.append({"id": u["id"], "deck": rel, "timeout_s": UNIT_TIMEOUT_S})
        # models.pdk_root names the runner image's baked root: the decks' absolute
        # `.lib` paths sit under it, so klt ships them verbatim (and accepts a path
        # that does not exist on this host as runner-valid).
        req = {"engine": "ngspice", "backend": "batch",
               "models": {"pdk": a.pdk, "pdk_root": a.batch_pdk_root},
               "decks": entries, "options": {"timeout_s": UNIT_TIMEOUT_S},
               "batch": {"provision_script_path": a.provision,
                         "capacity_wait_s": a.capacity_wait_s}}
        (work / f"{stem}.json").write_text(json.dumps(req, indent=2) + "\n")
        manifest.append({"request": f"{stem}.json", "stem": stem, "point": point,
                         "ids": [u["id"] for u in members]})
    (work / f"manifest-{stage}.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared {len(units)} {stage} decks in {len(manifest)} requests")


def prepare(a: argparse.Namespace) -> None:
    work = Path(a.work)
    template = Path(a.template).read_text()
    if a.stage == "sanity":
        # Two draw-0, code-0, 27 C decks: negctrl (the gate -- no mismatch draw, so it
        # is deterministic across hosts) and nominal (informational -- the mismatch
        # draw is a function of the host's RNG, see check_sanity).
        ctx = make_ctx(a, local=a.sanity_backend == "local")
        (work / "decks").mkdir(parents=True, exist_ok=True)
        entries = []
        for point in SANITY_POINTS:
            rel = f"decks/sanity-{point}.spice"
            (work / rel).write_text(render_deck(template, ctx, point, 0, TEMP_TRIM_C, 0, "fit"))
            entries.append({"id": f"sanity-{point}", "deck": rel, "timeout_s": UNIT_TIMEOUT_S})
        req = {"engine": "ngspice", "backend": a.sanity_backend, "decks": entries,
               "models": {"pdk_root": a.local_pdk_root},
               "options": {"timeout_s": UNIT_TIMEOUT_S}}
        if a.sanity_backend == "batch":
            req["models"] = {"pdk": a.pdk, "pdk_root": a.batch_pdk_root}
            req["batch"] = {"provision_script_path": a.provision,
                            "capacity_wait_s": a.capacity_wait_s}
        (work / "request-sanity.json").write_text(json.dumps(req, indent=2) + "\n")
        return
    ctx = make_ctx(a, local=False)
    units = []
    if a.stage == "attrib":
        for variant in (a.variants.split(",") if a.variants else attrib_variants()):
            for draw in range(a.n):
                units.append({"point": variant, "draw": draw, "id": attrib_id(variant, draw),
                              "text": render_attrib_deck(template, ctx, variant, draw)})
    elif a.stage == "fit":
        for point in POINTS:
            for draw in range(a.n):
                for code in FIT_CODES:
                    units.append({"point": point, "draw": draw, "id": fit_id(point, draw, code),
                                  "text": render_deck(template, ctx, point, draw, TEMP_TRIM_C,
                                                      code, "fit")})
    else:
        codes = json.loads(Path(a.codes).read_text())
        for point in POINTS:
            for draw in range(a.n):
                code = codes[f"{point}|{draw}"]["code_star"]
                if code == -1:
                    continue
                for temp in VERIFY_TEMPS:
                    units.append({"point": point, "draw": draw,
                                  "id": verify_id(point, draw, temp, code),
                                  "text": render_deck(template, ctx, point, draw, temp, code,
                                                      "verify")})
    write_requests(work, a.stage, units, a)


# ----------------------------------------------------------------- parsing

def op_value(text: str, node: str) -> str | None:
    """extract_op_voltage: the first `v(node) = <value>` line's value token."""
    m = re.search(rf"^v\({re.escape(node)}\)\s*=\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else None


class Results:
    """Per-unit results of one stage, read from klt's `<outdir>/<request stem>/<id>/` trees."""

    def __init__(self, art_root: Path, manifest: list[dict]):
        self.art_root, self.where = art_root, {}
        for entry in manifest:
            for uid in entry["ids"]:
                self.where[uid] = art_root / entry["stem"] / uid

    def unit(self, uid: str) -> tuple[str | None, bool]:
        """(stdout text or None if the unit never came back, run ok)."""
        d = self.where[uid]
        out = d / "stdout.bin"
        if not out.is_file():
            return None, False
        status = None
        rec = d / "unit.json"
        if rec.is_file():
            try:
                status = (json.loads(rec.read_text()).get("result") or {}).get("status")
            except ValueError:
                status = None
        return out.read_bytes().decode("utf-8", "replace"), status != "timeout"

    def op(self, uid: str) -> tuple[str, str | None]:
        """op_status_of_log: ('OK'|'BAD', raw vref token). A deck that timed
        out, hit a model error, or printed no vref is BAD; a unit with no
        result tree at all is a missing unit, refused by `require_complete`."""
        text, ran = self.unit(uid)
        if text is None or not ran or BAD_LOG.search(text):
            return "BAD", None
        v = op_value(text, "vref")
        return ("OK", v) if v is not None else ("BAD", None)

    def engine_version(self) -> str | None:
        """First engine_version any request's own report.json recorded."""
        for rep in sorted(self.art_root.glob("*/report.json")):
            try:
                v = (json.loads(rep.read_text()).get("environment") or {}).get("engine_version")
            except (OSError, ValueError):
                continue
            if v:
                return v
        return None

    def require_complete(self, what: str) -> None:
        missing = [u for u in self.where if self.unit(u)[0] is None]
        if missing:
            raise SystemExit(
                f"{what}: {len(missing)} of {len(self.where)} units never came back "
                f"(first: {missing[0]}) -- a partial draw set is never recorded; re-run the "
                "stage (klt sim --resume) so every unit has a result")


def reaim(code: int, rule: dict) -> int:
    """The re-aim rule of DR-0014 (S2): final code = code* + round(k0 + k1*code*), clipped."""
    return max(0, min(255, code + round(rule["k0"] + rule["k1"] * code)))


def codes(a: argparse.Namespace) -> None:
    work = Path(a.work)
    rule = json.loads(Path(a.rule).read_text()) if getattr(a, "rule", None) else None
    manifest = json.loads((work / "manifest-fit.json").read_text())
    res = Results(Path(a.artifacts), manifest)
    res.require_complete("fit stage")
    out: dict = {}
    for point in POINTS:
        for draw in range(a.n):
            (s0, v0), (s1, v1), (s255, v255) = (res.op(fit_id(point, draw, c)) for c in FIT_CODES)
            code = -1
            if s0 == "OK" and s255 == "OK":
                unit = (float(v255) - float(v0)) / 255
                ideal = (VREF_TARGET_V - float(v0)) / unit if unit != 0 else 128
                code = clip_round(ideal)
            entry = {"v0": v0, "v1": v1, "v255": v255, "code_star": code}
            if rule is not None and code != -1:
                entry["code_fit"] = code
                entry["code_star"] = reaim(code, rule)
            out[f"{point}|{draw}"] = entry
    (work / getattr(a, "out", "codes.json")).write_text(json.dumps(out, indent=2) + "\n")
    n_fail = sum(v["code_star"] == -1 for v in out.values())
    print(f"fit: {len(out)} draws, {n_fail} failed to fit (verify FAIL rows)"
          + (f"; re-aimed with k0={rule['k0']} k1={rule['k1']}" if rule else ""))


def clip_round(ideal: float) -> int:
    """awk: c = (ideal<0) ? int(ideal-0.5) : int(ideal+0.5); clipped to 0..255."""
    c = int(ideal - 0.5) if ideal < 0 else int(ideal + 0.5)
    return max(0, min(255, c))


# ------------------------------------------------------------------ re-aim rule

def fit_rule(a: argparse.Namespace) -> None:
    """Fit DR-0014's S2 rule m = round(k0 + k1*code*) on the typ-mismatch point of a PLAIN
    trim draws CSV, by the same grid and criterion (mean + 3sd of the per-die max deviation)
    sim/tools/project_trim_strategies.py used, with knob A's shape read from the same
    Jacobian record. The rule is a projection used only to CHOOSE (k0, k1); the re-aimed
    campaign then MEASURES the result on every point (bcs/wcs are out of sample)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import project_trim_strategies as pts  # noqa: E402

    shape = pts.knob_shapes(Path(a.jacobian_csv))["typ"]["A"]
    dies = []
    with open(a.draws_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["point"] == "nominal" and r["verify_status"] == "PASS":
                dies.append(([float(r["vref_n40c_v"]), float(r["vref_27c_v"]),
                              float(r["vref_125c_v"])], float(r["unit_v"]), int(r["code_star"])))

    def dev(v):
        return 100.0 * max(abs(x - VREF_TARGET_V) for x in v) / VREF_TARGET_V

    def projected(k0: float, k1: float) -> list[float]:
        out = []
        for v, unit, code in dies:
            m = max(-code, min(255 - code, round(k0 + k1 * code)))
            out.append(dev([x + m * unit * sh for x, sh in zip(v, shape)]))
        return out

    best, best_score = (0.0, 0.0), None
    for k0 in [x / 4 for x in range(-64, 65)]:
        for k1 in [x / 400 for x in range(-60, 21)]:
            st = pts.stats(projected(k0, k1))
            if best_score is None or st["mean_plus_3sd"] < best_score:
                best, best_score = (k0, k1), st["mean_plus_3sd"]
    base, tuned = pts.stats(projected(0.0, 0.0)), pts.stats(projected(*best))
    out = {"k0": best[0], "k1": best[1], "form": "m = round(k0 + k1*code_star)",
           "fitted_on": "nominal (typ mismatch) only; bcs/wcs out of sample",
           "n_fit_dies": len(dies), "knob_a_shape": shape, "jacobian_csv": a.jacobian_csv,
           "draws_csv": a.draws_csv,
           "projected_three_sigma_pct": {"no_rule": base["three_sigma"], "rule": tuned["three_sigma"]},
           "projected_mean_plus_3sd_pct": {"no_rule": base["mean_plus_3sd"],
                                           "rule": tuned["mean_plus_3sd"]},
           "dr0014_rule": {"k0": 8.00, "k1": -0.0600}}
    Path(a.output).write_text(json.dumps(out, indent=2) + "\n")
    print(f"rule: k0={best[0]} k1={best[1]} (n={len(dies)}); projected mean+3sd "
          f"{base['mean_plus_3sd']:.3f}% -> {tuned['mean_plus_3sd']:.3f}%")


# ---------------------------------------------------------------- assembly

def g9(x: float) -> str:
    return f"{x:.9g}"


def draw_row(a: argparse.Namespace, point: str, draw: int, fit: dict, res: Results) -> list[str]:
    v0, v1, v255, code = fit["v0"], fit["v1"], fit["v255"], fit["code_star"]
    unit = resid = ""
    status = "FAIL"
    v27 = vn40 = v125 = ""
    if v0 is not None and v255 is not None and code != -1:
        unit = g9((float(v255) - float(v0)) / 255)
        if v1 is not None:
            resid = g9(float(v1) - (float(v0) + float(unit)))
        ops = {t: res.op(verify_id(point, draw, t, code)) for t in VERIFY_TEMPS}
        if all(s == "OK" for s, _ in ops.values()):
            status = "PASS"
            v27, vn40, v125 = ops[27][1], ops[-40][1], ops[125][1]
    dev27 = devn40 = dev125 = maxdev = ""
    within, railed = "0", "0"
    if status == "PASS":
        devs = [abs(100 * (float(v) - VREF_TARGET_V) / VREF_TARGET_V) for v in (v27, vn40, v125)]
        m = max(devs)
        dev27, devn40, dev125, maxdev = (f"{x:.6f}" for x in (*devs, m))
        within = "1" if m <= 0.5 else "0"
        railed = "1" if code in (0, 255) else "0"
    def na(v):  # the script echoes its NA sentinel for an unparsed fit value
        return "NA" if v is None else v
    return [point, MODE_OF[point], str(draw), str(a.seed + draw), CORNER_OF[point],
            na(v0), na(v1), na(v255), unit, resid, str(code), status, v27, vn40, v125,
            dev27, devn40, dev125, maxdev, within, railed]


def num(s: str) -> float:
    return float(s) if s else 0.0


def digest_row(a: argparse.Namespace, point: str, rows: list[list[str]]) -> tuple[list[str], dict]:
    """The awk digest block of run_trim_mc.sh, on the written (rounded) strings."""
    mine = [r for r in rows if r[0] == point]
    ok = [r for r in mine if r[11] == "PASS"]
    n_draws, np_ = len(mine), len(ok)
    if np_ == 0:
        stats = [n_draws, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        fmt = ["%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d", "%d"]
        cells = [f % s for f, s in zip(fmt, stats)]
        named = dict(zip(DIGEST_HEADER[8:], map(float, cells)))
    else:
        md = [float(r[18]) for r in ok]
        mean = sum(md) / np_
        sigma = math.sqrt(sum((d - mean) ** 2 for d in md) / (np_ - 1)) if np_ > 1 else 0.0
        worst = max(md)
        cs = [float(r[10]) for r in ok]
        cm = sum(cs) / np_
        csd = math.sqrt(max(0.0, sum(c * c for c in cs) - np_ * cm * cm) / (np_ - 1)) if np_ > 1 else 0.0
        us = [num(r[8]) * 1000 for r in ok]
        um = sum(us) / np_
        usd = math.sqrt(max(0.0, sum(u * u for u in us) - np_ * um * um) / (np_ - 1)) if np_ > 1 else 0.0
        rmean = sum(num(r[9]) * 1e6 for r in ok) / np_
        w05 = sum(r[19] == "1" for r in ok)
        rail = sum(r[20] == "1" for r in ok)
        cells = [f"{n_draws}", f"{np_}", f"{100 * w05 / np_:.4f}", f"{3 * sigma:.6f}",
                 f"{worst:.6f}", f"{cm:.3f}", f"{csd:.3f}", f"{int(min(cs))}", f"{int(max(cs))}",
                 f"{rail}", f"{um:.4f}", f"{usd:.4f}", f"{rmean:.2f}"]
        named = dict(zip(DIGEST_HEADER[8:], map(float, cells)))
    status = "PASS" if cells[1] == cells[0] else "FAIL"
    if MODE_OF[point] == "mismatch" and float(cells[3]) > TRIM_BUDGET_PCT:
        status = "FAIL"
    hbt, mos, res = sections(point)
    row = [DIGEST_LABEL_OF[point], hbt, mos, res, str(TEMP_TRIM_C), VDD, a.msense_w, status, *cells]
    return row, {"status": status, "measurements": named,
                 "claim_fail": MODE_OF[point] == "mismatch" and float(cells[3]) > TRIM_BUDGET_PCT}


def assemble(a: argparse.Namespace) -> None:
    work = Path(a.work)
    fits = json.loads((work / "codes.json").read_text())
    manifest = json.loads((work / "manifest-verify.json").read_text())
    res = Results(Path(a.artifacts), manifest)
    res.require_complete("verify stage")
    rows = [draw_row(a, p, d, fits[f"{p}|{d}"], res) for p in POINTS for d in range(a.n)]

    # Negative control (hard gate): trimmed negctrl vref identical at every draw and temperature.
    spread = {tuple(r[12:15]) for r in rows if r[0] == "negctrl" and r[11] == "PASS"}
    if len(spread) != 1:
        raise SystemExit(f"NEGATIVE CONTROL FAILED -- trimmed negctrl draws show {len(spread)} "
                         "distinct values (expected exactly 1). Driver bug, not noise. "
                         "No record is written.")
    print("negative control confirmed -- exactly zero spread across all draws and temperatures.")

    draws_csv = Path(a.draws_out)
    with draws_csv.open("w", newline="") as fh:
        fh.write(DRAWS_HEADER + "\n")
        csv.writer(fh, lineterminator="\n").writerows(rows)

    corners, claim_fail = [], []
    rep = work / "rep"
    rep.mkdir(exist_ok=True)
    local = make_ctx(a, local=True)
    template = Path(a.template).read_text()
    for point in POINTS:
        row, info = digest_row(a, point, rows)
        label = DIGEST_LABEL_OF[point]
        if info["claim_fail"]:
            claim_fail.append(label)
        cid = f"{label}_{TEMP_TRIM_C}c_{VDD}v"
        code0 = fits[f"{point}|0"]["code_star"]
        if code0 != -1:
            src, (temp, code, stage) = verify_id(point, 0, TEMP_TRIM_C, code0), (TEMP_TRIM_C, code0, "verify")
        else:
            src, (temp, code, stage) = fit_id(point, 0, 0), (TEMP_TRIM_C, 0, "fit")
        log = res.unit(src)[0] or ""
        (rep / f"{cid}.log").write_text(log)
        # The representative deck, re-rendered with host-resolvable PDK/OSDI paths
        # (the fleet ran the identical deck against the image's baked root).
        (rep / f"{cid}.spice").write_text(render_deck(template, local, point, 0, temp, code, stage))
        corners.append({
            "corner_id": f"{label}/{VDD}V/{TEMP_TRIM_C}C", "process": label,
            "temperature_c": TEMP_TRIM_C, "supply_v": {"Vvdd": float(VDD)},
            "status": "pass" if info["status"] == "PASS" else "fail",
            "measurements": [{"name": k, "value": v} for k, v in info["measurements"].items()],
            "artifacts": {"log": str(rep / f"{cid}.log"), "deck": str(rep / f"{cid}.spice")},
        })
        print(f"{label}: {row[8:]}")
    # klt announces each fleet job on stderr ("batch job <id> submitting"); the
    # wrapper keeps that stream, which survives a --resume pass that rewrites the
    # per-request reports.
    job_ids: list[str] = []
    if a.job_log and Path(a.job_log).is_file():
        for jid in re.findall(r"batch job (\S+) submitting", Path(a.job_log).read_text()):
            if jid not in job_ids:
                job_ids.append(jid)
    report = {
        "status": "pass" if all(c["status"] == "pass" for c in corners) else "fail",
        "passed": sum(c["status"] == "pass" for c in corners),
        "failed": sum(c["status"] == "fail" for c in corners), "errored": 0,
        "corner_count": len(corners), "corners": corners,
        "environment": {"engine_version": res.engine_version(),
                        "remote": {"job_ids": job_ids, "n_verify_decks": len(res.where)} if job_ids else None},
        "provenance": {"klt_version": a.klt_version},
        "claim_failed_points": claim_fail,
    }
    Path(a.report_out).write_text(json.dumps(report, indent=2) + "\n")
    print(f"assembled {len(rows)} draws -> {draws_csv.name}; report {a.report_out}")


# ------------------------------------------------------ attribution assembly

def attrib_table(a: argparse.Namespace, res: "Results") -> tuple[list[dict], dict]:
    """Per (variant, draw): vref, input-referred offset sns2-sns1, status. A deck that
    failed is a FAIL row that stays in the table; statistics are quoted pairwise-complete
    (the draws that converged in EVERY variant) and the dropped draws are listed."""
    rows = []
    for variant in attrib_variants():
        for draw in range(a.n):
            uid = attrib_id(variant, draw)
            text, ran = res.unit(uid)
            status, vref, sns1, sns2 = "FAIL", None, None, None
            if text is not None and ran and not BAD_LOG.search(text):
                vref, sns1, sns2 = (op_value(text, n) for n in ("vref", "sns1", "sns2"))
                if None not in (vref, sns1, sns2):
                    status = "PASS"
            rows.append({"variant": variant, "draw": draw, "seed": a.seed + draw, "status": status,
                         "vref_v": vref, "vos_mv": (None if status != "PASS" else
                                                    1e3 * (float(sns2) - float(sns1)))})
    by = {}
    for r in rows:
        by.setdefault(r["variant"], {})[r["draw"]] = r
    failed = sorted({(v, d) for v, ds in by.items() for d, r in ds.items() if r["status"] != "PASS"})
    bad_draws = {d for _, d in failed}
    good = [d for d in range(a.n) if d not in bad_draws]
    return rows, {"by": by, "failed": failed, "good": good}


def variance(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def attrib_summary(a: argparse.Namespace, rows: list[dict], info: dict) -> dict:
    by, good = info["by"], info["good"]

    def series(variant: str, key: str) -> list[float]:
        return [float(by[variant][d][key]) for d in good]

    out = {"n_draws": a.n, "n_good": len(good), "failed": info["failed"], "variants": {}}
    ref = sum(series("none", "vref_v")) / len(good)
    for variant in attrib_variants():
        v, o = series(variant, "vref_v"), series(variant, "vos_mv")
        out["variants"][variant] = {
            "mean_vref_v": sum(v) / len(v), "sigma_vref_mv": 1e3 * math.sqrt(variance(v)),
            "sigma_vref_pct": 100 * math.sqrt(variance(v)) / ref,
            "sigma_vos_mv": math.sqrt(variance(o)), "var_vref_mv2": 1e6 * variance(v),
            "var_vos_mv2": variance(o)}
    var_all, vos_all = out["variants"]["all"]["var_vref_mv2"], out["variants"]["all"]["var_vos_mv2"]
    sum_only = sum(out["variants"][f"only_{g}"]["var_vref_mv2"] for g in ATTRIB_GROUPS)
    sum_only_vos = sum(out["variants"][f"only_{g}"]["var_vos_mv2"] for g in ATTRIB_GROUPS)
    out["reconciliation"] = {
        "var_all_mv2": var_all, "sum_only_var_mv2": sum_only, "ratio_sum_only_over_all": sum_only / var_all,
        "var_vos_all_mv2": vos_all, "sum_only_var_vos_mv2": sum_only_vos,
        "ratio_vos_sum_only_over_all": sum_only_vos / vos_all}
    out["shares"] = {}
    for g in ATTRIB_GROUPS:
        only, loo = out["variants"][f"only_{g}"], out["variants"][f"loo_{g}"]
        out["shares"][g] = {
            "share_only_pct": 100 * only["var_vref_mv2"] / sum_only,
            "share_of_all_only_pct": 100 * only["var_vref_mv2"] / var_all,
            "share_loo_pct": 100 * (var_all - loo["var_vref_mv2"]) / var_all,
            "share_vos_only_pct": 100 * only["var_vos_mv2"] / sum_only_vos,
            "sigma_only_vref_mv": only["sigma_vref_mv"], "sigma_only_vos_mv": only["sigma_vos_mv"]}
    # Controls: negctrl and `none` (mismatch sections, every group mm_ok=0) must each be exactly
    # zero-spread, and none_plainall must equal negctrl draw for draw. `none` is NOT required to
    # equal negctrl: the mismatch-section resistor card moves the mean by a deterministic ~1 mV
    # (reported as none_minus_negctrl_mv, never hidden).
    neg, none, pall = (series(v, "vref_v") for v in ("negctrl", "none", "none_plainall"))
    out["controls"] = {"negctrl_distinct_values": len({f"{x!r}" for x in neg}),
                       "none_distinct_values": len({f"{x!r}" for x in none}),
                       "plainall_equals_negctrl": pall == neg,
                       "none_minus_negctrl_mv": 1e3 * (none[0] - neg[0])}
    return out


def assemble_attrib(a: argparse.Namespace) -> None:
    work = Path(a.work)
    manifest = json.loads((work / "manifest-attrib.json").read_text())
    res = Results(Path(a.artifacts), manifest)
    res.require_complete("attrib stage")
    rows, info = attrib_table(a, res)
    summary = attrib_summary(a, rows, info)
    ctl = summary["controls"]
    if ctl["negctrl_distinct_values"] != 1 or ctl["none_distinct_values"] != 1 or not ctl["plainall_equals_negctrl"]:
        raise SystemExit(f"ATTRIBUTION CONTROLS FAILED: {ctl}. Driver bug, not noise. No record is written.")
    print("controls confirmed: negctrl and `none` (mismatch sections, every group mm_ok=0) are "
          "exactly zero-spread; none_plainall == negctrl draw for draw.")
    with Path(a.draws_out).open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["variant", "draw_index", "seed", "status", "vref_v", "vos_mv"])
        for r in rows:
            w.writerow([r["variant"], r["draw"], r["seed"], r["status"], r["vref_v"] or "NA",
                        "NA" if r["vos_mv"] is None else f"{r['vos_mv']:.6f}"])
    summary["engine_version"] = res.engine_version()
    job_ids: list[str] = []
    if a.job_log and Path(a.job_log).is_file():
        for jid in re.findall(r"batch job (\S+) submitting", Path(a.job_log).read_text()):
            if jid not in job_ids:
                job_ids.append(jid)
    summary["job_ids"] = job_ids
    Path(a.report_out).write_text(json.dumps(summary, indent=2) + "\n")
    s = summary
    print(f"attrib: {s['n_good']}/{s['n_draws']} draws converged in every variant; "
          f"sigma_all={s['variants']['all']['sigma_vref_pct']:.3f}% "
          f"sum-only/all={s['reconciliation']['ratio_sum_only_over_all']:.3f}")
    for g in ATTRIB_GROUPS:
        print(f"  {g:16s} only {s['shares'][g]['share_only_pct']:5.1f}%  loo {s['shares'][g]['share_loo_pct']:5.1f}%")


def unit_um(tok: str) -> float:
    """SPICE length token (2u, 37.2u, 0.5u, 1411.3u) -> micrometres."""
    m = re.fullmatch(r"([0-9.eE+-]+)([um]?)", tok)
    if not m:
        raise SystemExit(f"unparsed dimension: {tok}")
    return float(m.group(1)) * {"u": 1.0, "m": 1e3, "": 1e6}[m.group(2)]


def group_geometry(template: str) -> dict:
    """Per attribution group: its cards and drawn area (um^2; W*L*ng*m for MOS, W*L*m for the
    resistors -- the body drawn area, not the contacted footprint)."""
    out = {g: {"cards": [], "area_um2": 0.0} for g in ATTRIB_GROUPS}
    for line in template.split("\n"):
        toks = line.split()
        if not toks or not toks[0].startswith("X"):
            continue
        g = next((g for g, rx in ATTRIB_GROUPS.items() if re.fullmatch(rx, toks[0])), None)
        if g is None:
            continue
        kv = dict(t.split("=", 1) for t in toks if "=" in t)
        if "w" not in kv:      # a bipolar: sized by emitter count Nx, not by drawn area
            out[g]["cards"].append(f"{toks[0]} Nx={kv.get('Nx', '1')}")
            out[g]["nx"] = out[g].get("nx", 0) + float(kv.get("Nx", 1))
            continue
        area = 0.0 if "@@" in kv["w"] else unit_um(kv["w"]) * unit_um(kv["l"])
        area *= float(kv.get("ng", 1)) * float(kv.get("m", 1))
        out[g]["cards"].append(f"{toks[0]} w={kv['w']} l={kv['l']}" + (f" ng={kv['ng']}" if "ng" in kv else ""))
        out[g]["area_um2"] += area
    return out


def record_attrib(a: argparse.Namespace) -> None:
    summary = json.loads(Path(a.report).read_text())
    geom = group_geometry(Path(a.template).read_text())
    rid, out = a.record_id, Path(a.records_dir)
    v, sh, rc, ctl = summary["variants"], summary["shares"], summary["reconciliation"], summary["controls"]
    with (out / f"{rid}.csv").open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["group", "n_cards", "area_um2", "sigma_only_vref_mv", "share_only_pct",
                    "share_loo_pct", "sigma_only_vos_mv", "share_vos_only_pct"])
        for g in ATTRIB_GROUPS:
            w.writerow([g, len(geom[g]["cards"]), f"{geom[g]['area_um2']:.1f}",
                        f"{sh[g]['sigma_only_vref_mv']:.4f}", f"{sh[g]['share_only_pct']:.2f}",
                        f"{sh[g]['share_loo_pct']:.2f}", f"{sh[g]['sigma_only_vos_mv']:.4f}",
                        f"{sh[g]['share_vos_only_pct']:.2f}"])
    lines = [f"# Record {rid}", "",
             f"- **Experiment**: closed-loop-vref-trim-mc -- mismatch contribution breakdown (issue #303)",
             f"- **Claim**: attribution of the UNTRIMMED 27 C spread of vref (typ corner, 3.30 V, "
             f"trim code {ATTRIB_CODE}) to device groups of the {a.label} core. One controlled variation at a time: "
             "a group's mismatch is switched off with the PDK's per-instance `mm_ok=0` (the draw stream is "
             "consumed identically, so every other device keeps its exact draw). `only_<g>` = group g's "
             "mismatch alone; `loo_<g>` = everything but g; `all` = the full draw; `none` = mismatch sections with "
             "every group off; `negctrl` = plain sections.",
             f"- **Seed / N**: seed={a.seed}, N={summary['n_draws']} draws per variant, {len(v)} variants "
             f"({summary['n_draws'] * len(v)} decks, one `.op` each), batch backend.",
             f"- **Template / DUT**: `{a.template_rel}` @ `{a.dut_sha}`.",
             f"- **Engine**: `{summary.get('engine_version')}`; fleet jobs: {', '.join(summary.get('job_ids') or ['(none logged)'])}.",
             "- **Convergence**: "
             + (f"{summary['n_good']}/{summary['n_draws']} draws converged in every variant. "
                f"Failed (variant, draw) decks, all kept as FAIL rows in the draws CSV and excluded "
                f"pairwise-complete from the statistics below: {summary['failed']}."
                if summary["failed"] else
                f"all {summary['n_draws']} draws converged in every variant (0 failed decks); no draw is excluded."),
             f"- **Controls**: negctrl distinct vref values = {ctl['negctrl_distinct_values']}; `none` distinct values = "
             f"{ctl['none_distinct_values']}; `none_plainall` == negctrl draw for draw: {ctl['plainall_equals_negctrl']}; "
             f"`none` sits {ctl['none_minus_negctrl_mv']:+.3f} mV from negctrl (the mismatch-section resistor card's "
             "deterministic nominal shift). Hard gates: the record is not written otherwise.",
             "- **Bipolars**: the PDK's `npn13G2` mismatch subcircuit (`sg13g2_hbt_mod_mismatch.lib`) draws "
             "`qarea = agauss(1, 0.1, mm_ok != 1 ? 0 : 1)`: a 10 % one-sigma emitter-area mismatch per device, "
             "the same for Nx=1 and Nx=8 (it does not scale with area). The first campaign attempt assumed the "
             "bipolars were mismatch-free; its `none` control read nonzero spread and the diagnostic variants "
             "(`none_plainres/mos/hbt/all`) localised it to the HBT section. Treat the bipolar rows as a property "
             "of this model, not of the silicon.",
             "", "## Result", "",
             f"All-mismatch spread of vref at 27 C, code {ATTRIB_CODE}: sigma = {v['all']['sigma_vref_mv']:.2f} mV "
             f"= {v['all']['sigma_vref_pct']:.3f} % (3 sigma = {3 * v['all']['sigma_vref_pct']:.2f} %); input-referred "
             f"offset sigma (sns2-sns1) = {v['all']['sigma_vos_mv']:.3f} mV.", "",
             "| group | cards | area (um^2) | sigma alone (mV vref) | share of sum-of-parts | leave-one-out share | sigma Vos alone (mV) | Vos share |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for g in sorted(ATTRIB_GROUPS, key=lambda g: -sh[g]["share_only_pct"]):
        lines.append(f"| {g} | {len(geom[g]['cards'])} | {(f"Nx total {geom[g]['nx']:.0f}" if 'nx' in geom[g] else f"{geom[g]['area_um2']:.0f}")} | {sh[g]['sigma_only_vref_mv']:.2f} | "
                     f"{sh[g]['share_only_pct']:.1f} % | {sh[g]['share_loo_pct']:.1f} % | "
                     f"{sh[g]['sigma_only_vos_mv']:.3f} | {sh[g]['share_vos_only_pct']:.1f} % |")
    lines += ["", f"Reconciliation: sum of the single-group variances = {rc['sum_only_var_mv2']:.2f} mV^2 vs all-mismatch "
              f"{rc['var_all_mv2']:.2f} mV^2 (ratio {rc['ratio_sum_only_over_all']:.3f}); on the input-referred offset the "
              f"ratio is {rc['ratio_vos_sum_only_over_all']:.3f}. Shares are quoted over the sum of the parts; the "
              "leave-one-out column is a second estimate and is NOT additive: the leave-one-out shares sum to "
              f"{sum(sh[g]['share_loo_pct'] for g in ATTRIB_GROUPS):.0f} % (additive would be 100 %), and the resistor groups show "
              "a material leave-one-out share against ~0 alone. That is interaction (the PDK resistor card's "
              "mismatch draw also moves the nominal, see Controls), not sampling noise (the covariance "
              "sampling error at N=300 is ~1 mV^2). Sizing decisions here rest on the `only` shares, which reconcile "
              "with the all-mismatch variance; the leave-one-out column is reported, not relied on.", "",
              "## Groups", ""]
    for g in ATTRIB_GROUPS:
        lines.append(f"- `{g}`: {', '.join(geom[g]['cards'][:6])}" + (f", ... ({len(geom[g]['cards'])} cards)" if len(geom[g]['cards']) > 6 else ""))
    lines += ["", "## Links", "", f"- Digest: `records/{rid}.csv`", f"- Per-draw data (every draw, every variant, FAIL rows included): `records/{rid}-draws.csv`",
              "- Runner: `sim/closed-loop-vref-trim-mc/run_klt_sim.sh` with `KLT_SIM_CAMPAIGN=attrib`",
              f"- **Timestamp / author**: {a.timestamp}, Loom Builder (agent), issue #303."]
    (out / f"{rid}.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {rid}.md / .csv")


# ---------------------------------------------- failed draws + population summary

def failed_draws(a: argparse.Namespace) -> None:
    """One CSV row per verify-FAIL draw: which deck failed and how (read from the unit
    records), so a non-converged draw is explained, never just counted."""
    work = Path(a.work)
    fits = json.loads((work / "codes.json").read_text())
    res = Results(Path(a.artifacts), json.loads((work / "manifest-verify.json").read_text()))
    rows = []
    with open(a.draws_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["verify_status"] == "PASS":
                continue
            point, draw, code = r["point"], int(r["draw_index"]), int(r["code_star"])
            bad = []
            if code != -1:
                for t in VERIFY_TEMPS:
                    uid = verify_id(point, draw, t, code)
                    text, ran = res.unit(uid)
                    st = None
                    rec = res.where[uid] / "unit.json"
                    if rec.is_file():
                        st = (json.loads(rec.read_text()).get("result") or {}).get("status")
                    s_, _ = res.op(uid)
                    if s_ != "OK":
                        bad.append(f"{t}C:{st or 'no-result'}")
            rows.append([point, draw, r["seed"], code, ";".join(bad) or "fit-stage", fits[f"{point}|{draw}"]["v0"]])
    with open(a.output, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["point", "draw_index", "seed", "code_star", "failed_decks", "fit0_vref_v"])
        w.writerows(rows)
    print(f"{len(rows)} failed draws -> {a.output}")


def summarize(a: argparse.Namespace) -> None:
    """Per point: the pass-only 3-sigma line AND a bounding line with every failed draw filled
    at the worst passing deviation of its point, so the dropped draws cannot hide upward."""
    by: dict[str, list[dict]] = {}
    with open(a.draws_csv, newline="") as fh:
        for r in csv.DictReader(fh):
            by.setdefault(r["point"], []).append(r)
    out = {}
    for point, rows in by.items():
        ok = [float(r["max_dev_pct"]) for r in rows if r["verify_status"] == "PASS"]
        n, npass = len(rows), len(ok)
        sd = math.sqrt(variance(ok))
        mean = sum(ok) / npass
        worst = max(ok)
        filled = ok + [worst] * (n - npass)
        out[point] = {"n_draws": n, "n_pass": npass, "n_failed": n - npass,
                      "mean_max_dev_pct": mean, "three_sigma_pct": 3 * sd,
                      "mean_plus_3sd_pct": mean + 3 * sd, "worst_pct": worst,
                      "frac_within_0p5_pct": 100 * sum(x <= 0.5 for x in ok) / npass,
                      "three_sigma_bound_failed_at_worst_pct": 3 * math.sqrt(variance(filled)),
                      "mean_code": sum(int(r["code_star"]) for r in rows if r["verify_status"] == "PASS") / npass}
    Path(a.output).write_text(json.dumps(out, indent=2) + "\n")
    for p, v in out.items():
        print(f"{p}: n={v['n_draws']} pass={v['n_pass']} 3sigma={v['three_sigma_pct']:.3f}% "
              f"bound(failed@worst)={v['three_sigma_bound_failed_at_worst_pct']:.3f}% "
              f"mean+3sd={v['mean_plus_3sd_pct']:.3f}% worst={v['worst_pct']:.3f}% "
              f"within0.5={v['frac_within_0p5_pct']:.1f}%")


def spec(a: argparse.Namespace) -> None:
    data = json.loads(Path(a.spec).read_text())
    extra = data.get("extra_columns") or {}
    extra["msense_w"] = {DIGEST_LABEL_OF[p]: a.msense_w for p in POINTS}
    data["extra_columns"] = extra
    data["Corner matrix run"] = data["Corner matrix run"].replace("@@N@@", str(a.n))
    data["Claim"] = data["Claim"].replace("@@N@@", str(a.n))
    if getattr(a, "rule", None):
        rule = json.loads(Path(a.rule).read_text())
        note = (f" RE-AIMED (issue #303): the verify code is code* + round({rule['k0']} + {rule['k1']}*code*), "
                f"clipped to 0..255 -- DR-0014's zero-cost S2 code-offset rule, refit on the typ-mismatch point "
                f"of the plain campaign ({rule['n_fit_dies']} dies) and applied unchanged to bcs/wcs (out of sample); "
                "the fit stage is the plain campaign's, so the dies are identical. The rule's own constants are "
                "chosen by projection (knob-A shape from the Jacobian record); the verified result is measured.")
        data["Claim"] += note
        data["Corner matrix run"] += note
    Path(a.output).write_text(json.dumps(data, indent=2) + "\n")


def check_sanity(a: argparse.Namespace) -> None:
    """Gate: negctrl draw 0 / code 0 / 27 C must land on the committed record's
    fit0 (same engine, PDK, OSDI and renderer => same number). The nominal
    mismatch draw 0 is printed against its committed value but does not gate:
    `.options rndseed` draws come from the host's RNG, and the committed record's
    draws were produced on another platform (the same deck, run here, lands
    elsewhere while the negctrl matches to every printed digit)."""
    rows = {}
    with open(a.anchor_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["draw_index"] == "0":
                rows[row["point"]] = row
    for point in SANITY_POINTS:
        if point not in rows or int(rows[point]["seed"]) != a.seed:
            raise SystemExit(f"sanity gate: the anchor record has no {point} draw 0 at --seed "
                             f"{a.seed}; run the sanity gate at the record's seed")
    got = {}
    for point in SANITY_POINTS:
        text = (Path(a.artifacts) / f"sanity-{point}" / "stdout.bin").read_text(errors="replace")
        got[point] = None if BAD_LOG.search(text) else op_value(text, "vref")
        delta = abs(float(got[point]) - float(rows[point]["fit0_vref_v"])) if got[point] else None
        gate = "gate" if point == "negctrl" else "informational: RNG-dependent"
        print(f"  sanity {point} vref(draw 0, code 0, 27C) = {got[point]} (committed "
              f"{rows[point]['fit0_vref_v']}, delta {'n/a' if delta is None else f'{delta:.3g}'}) [{gate}]")
    if got["negctrl"] is None:
        raise SystemExit("sanity gate: no vref came back from the negctrl anchor deck")
    if abs(float(got["negctrl"]) - float(rows["negctrl"]["fit0_vref_v"])) > a.tol:
        raise SystemExit("sanity gate: negctrl is off the committed draw-0 record -- the bench "
                         "(deck, PDK, OSDI or engine) is wrong; no grid is dispatched")
    print("  sanity gate: PASS")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, *names):
        for n in names:
            p.add_argument(f"--{n}", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--stage", choices=("sanity", "fit", "verify", "attrib"), required=True)
    common(p, "work", "template", "seed-csv", "msense-w", "dut-sha", "pdk", "local-pdk-root",
           "local-osdi-dir")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--codes")
    p.add_argument("--variants", help="attrib only: comma list of variants (diagnostics); default all")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--batch-osdi-dir", default="/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi")
    p.add_argument("--provision")
    p.add_argument("--sanity-backend", choices=("local", "batch"), default="local")
    p.add_argument("--draws-per-request", type=int, default=DRAWS_PER_REQUEST)
    p.add_argument("--capacity-wait-s", type=float, default=1800)
    p.set_defaults(fn=prepare)

    p = sub.add_parser("codes")
    common(p, "work", "artifacts")
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--rule", help="re-aim rule JSON (from `rule`); shifts code* by round(k0+k1*code*)")
    p.add_argument("--out", default="codes.json")
    p.set_defaults(fn=codes)

    p = sub.add_parser("assemble")
    common(p, "work", "artifacts", "fit-artifacts", "template", "seed-csv", "msense-w",
           "dut-sha", "pdk", "local-pdk-root", "local-osdi-dir", "draws-out", "report-out")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--klt-version", default=None)
    p.add_argument("--job-log")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--batch-osdi-dir", default="/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi")
    p.set_defaults(fn=assemble)

    p = sub.add_parser("assemble-attrib")
    common(p, "work", "artifacts", "draws-out", "report-out")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--job-log")
    p.set_defaults(fn=assemble_attrib)

    p = sub.add_parser("record-attrib")
    common(p, "report", "template", "records-dir", "record-id", "label", "template-rel", "dut-sha", "timestamp")
    p.add_argument("--seed", type=int, required=True)
    p.set_defaults(fn=record_attrib)

    p = sub.add_parser("failed-draws")
    common(p, "work", "artifacts", "draws-csv", "output")
    p.set_defaults(fn=failed_draws)

    p = sub.add_parser("summary")
    common(p, "draws-csv", "output")
    p.set_defaults(fn=summarize)

    p = sub.add_parser("rule")
    common(p, "draws-csv", "jacobian-csv")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=fit_rule)

    p = sub.add_parser("spec")
    p.add_argument("spec")
    p.add_argument("--msense-w", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--rule", help="re-aim rule JSON: states the rule in the record's Claim")
    p.set_defaults(fn=spec)

    p = sub.add_parser("check-sanity")
    common(p, "artifacts", "anchor-csv")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--tol", type=float, default=5e-4)
    p.set_defaults(fn=check_sanity)

    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
