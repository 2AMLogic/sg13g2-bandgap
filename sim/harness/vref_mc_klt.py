#!/usr/bin/env python3
"""`klt sim` decks plumbing for sim/closed-loop-vref-mc (issue #403, Part of #273).

The legacy run_mc.sh named below was removed after 1e3baf2f; see git history.
The untrimmed-vref mismatch Monte Carlo is 6 points x N seeded `.op` draws.
Each draw is a pre-composed deck (the template run_mc.sh rendered, with
`.options rndseed = SEED + draw_index` written at parse time), shipped
byte-for-byte by klt's `decks` transport, so the per-draw seeding rule is
reproduced exactly by construction (see sim/harness/README.md, "Seed parity").
This module owns everything else:

* `prepare`  renders the decks and the `decks` requests (one per point/chunk);
* `assemble` parses the returned logs with run_mc.sh's rules, writes the
             per-draw CSV (`-draws.csv`, header unchanged), the digest, the
             negative-control gate and a corner-shaped report for
             sim/harness/klt_sim_evidence.py;
* `spec`     fills the record spec's `msense_w` / `@@N@@`.

A deck that failed or timed out becomes a FAIL row (as in run_mc.sh); a unit
that never came back refuses the whole record: a partial draw set is never
recorded. No simulator is launched from here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trim_mc_klt import (BAD_LOG, SEED_FIELDS, Results, make_ctx,  # noqa: E402
                         op_value, sections_for)

POINTS = ("nominal", "negctrl", "bcs_n40", "bcs_125", "wcs_n40", "wcs_125")
CORNER_OF = {"nominal": "typ", "negctrl": "typ", "bcs_n40": "bcs", "bcs_125": "bcs",
             "wcs_n40": "wcs", "wcs_125": "wcs"}
TEMP_OF = {"nominal": 27, "negctrl": 27, "bcs_n40": -40, "bcs_125": 125,
           "wcs_n40": -40, "wcs_125": 125}
MODE_OF = {p: ("negctrl" if p == "negctrl" else "mismatch") for p in POINTS}
# The corner -> model-section maps (HBT/MOS/RES) live in trim_mc_klt and are
# reached only through its sections_for (issue #463): one copy of that mapping
# for the family. `sections` below still resolves the point against THIS
# module's own CORNER_OF/MODE_OF, which is a different, 6-point set.
VDD = "3.30"
UNIT_TIMEOUT_S = 300
DRAWS_PER_REQUEST = 100

DRAWS_HEADER = ("point,mismatch_mode,draw_index,seed,corner_label,hbt_section,mos_section,"
                "res_section,temp_c,vdd_v,msense_w,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,"
                "dvsns_v,vref_v")
DIGEST_HEADER = ["corner_label", "hbt_section", "mos_section", "res_section", "temp_c", "vdd_v",
                 "msense_w", "status", "n_draws", "n_pass", "mean_vref_v", "sigma_vref_v",
                 "three_sigma_over_mean_pct", "min_vref_v", "max_vref_v", "frac_within_1pct",
                 "frac_within_0p5pct"]


def digest_label(point: str) -> str:
    return f"{CORNER_OF[point]}_{MODE_OF[point]}"


def sections(point: str) -> tuple[str, str, str]:
    return sections_for(CORNER_OF[point], MODE_OF[point])


def unit_id(point: str, draw: int) -> str:
    return f"mc_{point}_{draw}"


def render_deck(template: str, ctx: dict, point: str, draw: int) -> str:
    """The template filled exactly as run_mc.sh's pass 1 fills it."""
    corner, temp = CORNER_OF[point], TEMP_OF[point]
    row = ctx["seeds"].get((corner, str(temp), VDD))
    if row is None:
        raise SystemExit(f"no PASS seed row for {corner}/{temp}C/{VDD}V in {ctx['seed_csv']}")
    hbt, mos, res = sections(point)
    mapping = {
        "@@PDK_ROOT@@": ctx["pdk_root"], "@@PDK@@": ctx["pdk"], "@@OSDI_DIR@@": ctx["osdi_dir"],
        "@@TEMP_C@@": str(temp), "@@VDD@@": VDD, "@@CORNER_LABEL@@": corner,
        "@@HBT_SECTION@@": hbt, "@@MOS_SECTION@@": mos, "@@RES_SECTION@@": res,
        "@@MSENSE_W@@": ctx["msense_w"], "@@SEED@@": str(ctx["seed"] + draw),
        "@@DRAW_INDEX@@": str(draw), "@@POINT_LABEL@@": point,
        "@@MISMATCH_MODE@@": MODE_OF[point], "@@DUT_GIT_SHA@@": ctx["dut_sha"],
    }
    mapping.update({token: row[field] for token, field in SEED_FIELDS})
    text = template
    for token, value in mapping.items():
        text = text.replace(token, value)
    left = sorted({w for w in text.split() if w.startswith("@@") and w.endswith("@@")})
    if left:
        raise SystemExit(f"deck template has unfilled placeholders: {left}")
    return text


def request_for(entries: list[dict], a: argparse.Namespace, backend: str | None) -> dict:
    req = {"engine": "ngspice", "decks": entries, "options": {"timeout_s": UNIT_TIMEOUT_S}}
    if backend == "local":
        req.update(backend="local", models={"pdk_root": a.local_pdk_root})
        return req
    # models.pdk_root names the runner image's baked root: the decks' absolute `.lib`
    # paths sit under it, so klt ships them verbatim.
    req.update(backend="batch", models={"pdk": a.pdk, "pdk_root": a.batch_pdk_root},
               batch={"provision_script_path": a.provision,
                      "capacity_wait_s": a.capacity_wait_s})
    return req


def prepare(a: argparse.Namespace) -> None:
    work = Path(a.work)
    template = Path(a.template).read_text()
    (work / "decks").mkdir(parents=True, exist_ok=True)
    if a.probe:
        # Seed-parity probe (AC1): the first --probe draws of the nominal point, on one request.
        ctx = make_ctx(a, local=a.probe_backend == "local")
        entries = []
        for d in range(a.probe):
            rel = f"decks/{unit_id('nominal', d)}.spice"
            (work / rel).write_text(render_deck(template, ctx, "nominal", d))
            entries.append({"id": unit_id("nominal", d), "deck": rel, "timeout_s": UNIT_TIMEOUT_S})
        (work / "request-probe.json").write_text(
            json.dumps(request_for(entries, a, a.probe_backend), indent=2) + "\n")
        return
    ctx = make_ctx(a, local=False)
    manifest = []
    for point in POINTS:
        for chunk in range(0, a.n, a.draws_per_request):
            stem = f"request-mc-{point}-{chunk // a.draws_per_request:02d}"
            entries, ids = [], []
            for d in range(chunk, min(chunk + a.draws_per_request, a.n)):
                uid = unit_id(point, d)
                rel = f"decks/{uid}.spice"
                (work / rel).write_text(render_deck(template, ctx, point, d))
                entries.append({"id": uid, "deck": rel, "timeout_s": UNIT_TIMEOUT_S})
                ids.append(uid)
            (work / f"{stem}.json").write_text(json.dumps(request_for(entries, a, None), indent=2) + "\n")
            manifest.append({"request": f"{stem}.json", "stem": stem, "point": point, "ids": ids})
    (work / "manifest-mc.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared {a.n * len(POINTS)} decks in {len(manifest)} requests")


def parse_draw(res: Results, point: str, draw: int) -> dict:
    """run_mc.sh pass 3 for one draw (the rc check is the unit's own run status)."""
    text, ran = res.unit(unit_id(point, draw))
    text = text or ""
    got = {k: op_value(text, k) for k in ("fb", "sns1", "sns2", "vref", "det")}
    m = re.search(r"^i\(vmkfb\)\s*=\s*(\S+)", text, re.MULTILINE | re.IGNORECASE)
    got["i_mkfb"] = m.group(1) if m else None
    ok = ran and not BAD_LOG.search(text) and all(v is not None for v in got.values())
    return {**got, "ok": ok, "text": text}


def fmt_v(x: float) -> str:
    return f"{x:.7g}"


def draw_rows(a: argparse.Namespace, res: Results) -> list[list[str]]:
    rows = []
    for point in POINTS:
        hbt, mos, rs = sections(point)
        for d in range(a.n):
            g = parse_draw(res, point, d)
            status, dv = "FAIL", ""
            if g["ok"]:
                dv = fmt_v(abs(float(g["sns1"]) - float(g["sns2"])))
                # pvt_closed_loop_verdict: loop closed and not railed.
                status = "PASS" if closed_loop_ok(g) else "FAIL"
            rows.append([point, MODE_OF[point], str(d), str(a.seed + d), CORNER_OF[point], hbt,
                         mos, rs, str(TEMP_OF[point]), VDD, a.msense_w, status,
                         g["fb"] or "", g["sns1"] or "", g["sns2"] or "", g["det"] or "",
                         g["i_mkfb"] or "", dv, g["vref"] or ""])
    return rows


def closed_loop_ok(g: dict) -> bool:
    """sim/lib/pvt_verdict_common.sh pvt_closed_loop_verdict() (3-criteria form), ported with
    its constants: DET_RELEASE_FRAC 0.2, I_MKFB_RELEASE_A 50e-9, DVSNS_CLOSE_V 0.020,
    FB_RAIL_MARGIN_V 0.05."""
    vdd = float(VDD)
    det, i_mkfb, fb = float(g["det"]), abs(float(g["i_mkfb"])), float(g["fb"])
    dvsns = abs(float(g["sns1"]) - float(g["sns2"]))
    return (det <= 0.2 * vdd and i_mkfb <= 50e-9 and dvsns <= 0.020
            and 0.05 <= fb <= vdd - 0.05)


def stat_block(rows: list[list[str]], point: str) -> list[str]:
    mine = [r for r in rows if r[0] == point]
    ok = [float(r[18]) for r in mine if r[11] == "PASS"]
    n, np_ = len(mine), len(ok)
    if np_ == 0:
        return [str(n), "0", "0", "0", "0", "0", "0", "0", "0"]
    mean = sum(ok) / np_
    sigma = math.sqrt(sum((v - mean) ** 2 for v in ok) / (np_ - 1)) if np_ > 1 else 0.0
    three = 100 * 3 * sigma / mean if mean else 0.0
    w1 = sum((100 * abs(v - mean) / mean if mean else 0.0) <= 1.0 for v in ok)
    w05 = sum((100 * abs(v - mean) / mean if mean else 0.0) <= 0.5 for v in ok)
    return [str(n), str(np_), f"{mean:.6f}", f"{sigma:.6f}", f"{three:.4f}", f"{min(ok):.6f}",
            f"{max(ok):.6f}", f"{w1 / np_:.4f}", f"{w05 / np_:.4f}"]


def assemble(a: argparse.Namespace) -> None:
    work = Path(a.work)
    manifest = json.loads((work / "manifest-mc.json").read_text())
    res = Results(Path(a.artifacts), manifest)
    res.require_complete("mc stage")
    rows = draw_rows(a, res)

    # Negative control hard gate: exactly zero spread across PASS draws.
    neg = {r[18] for r in rows if r[0] == "negctrl" and r[11] == "PASS"}
    if not neg:
        raise SystemExit("negative control has no PASS draws -- cannot confirm zero spread")
    if len(neg) != 1:
        raise SystemExit(f"NEGATIVE CONTROL FAILED -- {len(neg)} distinct vref values "
                         "(expected exactly 1). Driver bug, not noise. No record is written.")
    print(f"negative control confirmed -- exactly zero spread (vref={next(iter(neg))} V).")

    # Record only a complete draw set: every point must carry all N draws.
    for p in POINTS:
        if sum(r[0] == p for r in rows) != a.n:
            raise SystemExit(f"point {p} does not carry {a.n} draws -- refusing to record")

    with Path(a.draws_out).open("w", newline="") as fh:
        fh.write(DRAWS_HEADER + "\n")
        csv.writer(fh, lineterminator="\n").writerows(rows)

    rep = work / "rep"
    rep.mkdir(exist_ok=True)
    local = make_ctx(a, local=True)
    template = Path(a.template).read_text()
    corners = []
    for point in POINTS:
        cells = stat_block(rows, point)
        status = "PASS" if cells[0] == cells[1] else "FAIL"
        label, temp = digest_label(point), TEMP_OF[point]
        cid = f"{label}_{temp}c_{VDD}v"
        (rep / f"{cid}.log").write_text(res.unit(unit_id(point, 0))[0] or "")
        (rep / f"{cid}.spice").write_text(render_deck(template, local, point, 0))
        corners.append({
            "corner_id": f"{label}/{VDD}V/{temp}C", "process": label, "temperature_c": temp,
            "supply_v": {"Vvdd": float(VDD)}, "status": "pass" if status == "PASS" else "fail",
            "measurements": [{"name": k, "value": float(v)}
                             for k, v in zip(DIGEST_HEADER[8:], cells)],
            "artifacts": {"log": str(rep / f"{cid}.log"), "deck": str(rep / f"{cid}.spice")},
        })
        print(f"{label}@{temp}C: {cells}")
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
                        "remote": {"job_ids": job_ids, "n_decks": len(res.where)} if job_ids else None},
        "provenance": {"klt_version": a.klt_version},
    }
    Path(a.report_out).write_text(json.dumps(report, indent=2) + "\n")
    print(f"assembled {len(rows)} draws -> {a.draws_out}; report {a.report_out}")


def spec(a: argparse.Namespace) -> None:
    data = json.loads(Path(a.spec).read_text())
    extra = data.get("extra_columns") or {}
    extra["msense_w"] = {digest_label(p): a.msense_w for p in POINTS}
    data["extra_columns"] = extra
    for k in ("Corner matrix run", "Claim"):
        data[k] = data[k].replace("@@N@@", str(a.n))
    Path(a.output).write_text(json.dumps(data, indent=2) + "\n")


def check_probe(a: argparse.Namespace) -> None:
    """AC1 probe: the probe draws vs the committed record's draws at the same seed."""
    anchor = {}
    with open(a.anchor_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["point"] == "nominal":
                anchor[int(row["draw_index"])] = row
    worst = 0.0
    for d in range(a.probe):
        text = (Path(a.artifacts) / "request-probe" / unit_id("nominal", d) / "stdout.bin")
        text = text.read_text(errors="replace") if text.is_file() else \
            (Path(a.artifacts) / unit_id("nominal", d) / "stdout.bin").read_text(errors="replace")
        v = op_value(text, "vref")
        ref = anchor[d]
        delta = abs(float(v) - float(ref["vref_v"])) if v else float("nan")
        worst = max(worst, delta) if v else worst
        print(f"  probe draw {d} (seed {ref['seed']}): vref={v} committed={ref['vref_v']} delta={delta:.3g}")
    print(f"  worst |delta| = {worst:.3g} V")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, *names):
        for n in names:
            p.add_argument(f"--{n}", required=True)

    p = sub.add_parser("prepare")
    common(p, "work", "template", "seed-csv", "msense-w", "dut-sha", "pdk", "local-pdk-root",
           "local-osdi-dir")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--probe", type=int, default=0)
    p.add_argument("--probe-backend", choices=("local", "batch"), default="batch")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--batch-osdi-dir", default="/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi")
    p.add_argument("--provision")
    p.add_argument("--draws-per-request", type=int, default=DRAWS_PER_REQUEST)
    p.add_argument("--capacity-wait-s", type=float, default=1800)
    p.set_defaults(fn=prepare)

    p = sub.add_parser("assemble")
    common(p, "work", "artifacts", "template", "seed-csv", "msense-w", "dut-sha", "pdk",
           "local-pdk-root", "local-osdi-dir", "draws-out", "report-out")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--klt-version", default=None)
    p.add_argument("--job-log")
    p.add_argument("--batch-pdk-root", default="/opt/pdk")
    p.add_argument("--batch-osdi-dir", default="/opt/pdk/ihp-sg13g2/libs.tech/ngspice/osdi")
    p.set_defaults(fn=assemble)

    p = sub.add_parser("spec")
    p.add_argument("spec")
    p.add_argument("--msense-w", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=spec)

    p = sub.add_parser("check-probe")
    common(p, "artifacts", "anchor-csv")
    p.add_argument("--probe", type=int, default=3)
    p.set_defaults(fn=check_probe)

    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
