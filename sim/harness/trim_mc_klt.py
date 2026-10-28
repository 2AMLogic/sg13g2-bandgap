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
* `spec`                  fills the record spec's `msense_w`.

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
    if a.stage == "fit":
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


def codes(a: argparse.Namespace) -> None:
    work = Path(a.work)
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
            out[f"{point}|{draw}"] = {"v0": v0, "v1": v1, "v255": v255, "code_star": code}
    (work / "codes.json").write_text(json.dumps(out, indent=2) + "\n")
    n_fail = sum(v["code_star"] == -1 for v in out.values())
    print(f"fit: {len(out)} draws, {n_fail} failed to fit (verify FAIL rows)")


def clip_round(ideal: float) -> int:
    """awk: c = (ideal<0) ? int(ideal-0.5) : int(ideal+0.5); clipped to 0..255."""
    c = int(ideal - 0.5) if ideal < 0 else int(ideal + 0.5)
    return max(0, min(255, c))


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
    job_ids: list[str] = []
    for root in (Path(a.fit_artifacts), Path(a.artifacts)):
        try:
            for req in json.loads((root / "set-manifest.json").read_text()).get("requests", []):
                job_ids.extend(req.get("job_ids") or [])
        except (OSError, ValueError):
            pass
    report = {
        "status": "pass" if all(c["status"] == "pass" for c in corners) else "fail",
        "passed": sum(c["status"] == "pass" for c in corners),
        "failed": sum(c["status"] == "fail" for c in corners), "errored": 0,
        "corner_count": len(corners), "corners": corners,
        "environment": {"engine_version": res.engine_version(),
                        "remote": {"job_ids": job_ids, "n_decks": len(res.where)} if job_ids else None},
        "provenance": {"klt_version": a.klt_version},
        "claim_failed_points": claim_fail,
    }
    Path(a.report_out).write_text(json.dumps(report, indent=2) + "\n")
    print(f"assembled {len(rows)} draws -> {draws_csv.name}; report {a.report_out}")


def spec(a: argparse.Namespace) -> None:
    data = json.loads(Path(a.spec).read_text())
    extra = data.get("extra_columns") or {}
    extra["msense_w"] = {DIGEST_LABEL_OF[p]: a.msense_w for p in POINTS}
    data["extra_columns"] = extra
    data["Corner matrix run"] = data["Corner matrix run"].replace("@@N@@", str(a.n))
    data["Claim"] = data["Claim"].replace("@@N@@", str(a.n))
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
    p.add_argument("--stage", choices=("sanity", "fit", "verify"), required=True)
    common(p, "work", "template", "seed-csv", "msense-w", "dut-sha", "pdk", "local-pdk-root",
           "local-osdi-dir")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--codes")
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
    p.set_defaults(fn=codes)

    p = sub.add_parser("assemble")
    common(p, "work", "artifacts", "fit-artifacts", "template", "seed-csv", "msense-w",
           "dut-sha", "pdk", "local-pdk-root", "local-osdi-dir", "draws-out", "report-out")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--klt-version", default=None)
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--batch-osdi-dir", default="/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi")
    p.set_defaults(fn=assemble)

    p = sub.add_parser("spec")
    p.add_argument("spec")
    p.add_argument("--msense-w", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("-o", "--output", required=True)
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
