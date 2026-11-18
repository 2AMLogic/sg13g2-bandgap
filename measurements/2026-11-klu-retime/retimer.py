#!/usr/bin/env python3
"""SPARSE-vs-KLU wall-clock re-time for sim/closed-loop-iq and
sim/closed-loop-startup (issue #518), run serially on ONE batch-fleet
instance via a `repo-script` job (operator ruling 2026-11-17).

The four timed cells are exactly the four (bench, corner) rows PR #501
reported -- per bench its sanity corner (typ/27C/3.30V) and its hot corner
(typ/125C/2.97V) -- re-timed under both solvers with >=3 repeats each. The
decks are the committed body/request templates of each bench, instantiated
the way run_klt_sim.sh instantiates them; the KLU variant differs from the
SPARSE variant by exactly the `klu` token on the `.options reltol=5e-3`
line and nothing else (asserted below). Each run is a one-corner local
`klt sim` invocation, the scratch-request method the boxtc README
documents; per run the engine wall clock is the klt report corner's
`runtime_s` (the engine wall #501's table used), the process wall around
the whole klt invocation, and the `Using ... as Direct Linear Solver` line
is grepped from that run's own ngspice log and must match the intended
solver.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

BENCHES = {
    "iq": {
        "exp": "sim/closed-loop-iq",
        "stem": "closed_loop_iq",
        "tran": "50n 3m",
        "anchors": {
            "sanity": {"fb_v": 2.49682, "iq_avg_a": 2.80682e-05},
            "hot": {"fb_v": 2.22558, "iq_avg_a": 3.62959e-05},
        },
    },
    "startup": {
        "exp": "sim/closed-loop-startup",
        "stem": "closed_loop_startup",
        "tran": "50n 2m",
        "anchors": {
            "sanity": {"vref_final_v": 1.04728, "fb_final_v": 2.49682},
            "hot": {"vref_final_v": 1.04201, "fb_final_v": 2.22558},
        },
    },
}

CORNERS = {
    "sanity": {"process": "typ", "temp_c": 27, "vdd": "3.30"},
    "hot": {"process": "typ", "temp_c": 125, "vdd": "2.97"},
}

SOLVERS = ("sparse", "klu")
SOLVER_LINE_EXPECT = {
    "sparse": "Using SPARSE 1.3 as Direct Linear Solver",
    "klu": "Using KLU as Direct Linear Solver",
}
CSV_FIELDS = [
    "bench", "corner", "solver", "pass", "status", "corner_id",
    "wall_engine_s", "wall_engine_field", "wall_proc_s", "peak_rss_mb",
    "solver_line", "solver_line_ok",
    "anchor1_name", "anchor1_value", "anchor1_expected", "anchor1_ok",
    "anchor2_name", "anchor2_value", "anchor2_expected", "anchor2_ok",
    "run_dir",
]


def log(msg: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
    print(f"[retimer {stamp}] {msg}", flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def imds_field(name: str) -> str:
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token", method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"})
        tok = urllib.request.urlopen(req, timeout=3).read().decode()
        req = urllib.request.Request(
            f"http://169.254.169.254/latest/meta-data/{name}",
            headers={"X-aws-ec2-metadata-token": tok})
        return urllib.request.urlopen(req, timeout=3).read().decode().strip()
    except Exception:
        return ""


def loadavg() -> str:
    return " ".join(Path("/proc/loadavg").read_text().split()[0:3])


def engine_wall(corner: dict):
    v = corner.get("runtime_s")
    if isinstance(v, (int, float)):
        return float(v), "runtime_s"
    return None, ""


def build_request(tmpl: Path, body: Path, bundle: Path, temp_c: int,
                  tran: str, timeout_s: int) -> dict:
    req = json.loads(tmpl.read_text().replace("@@BODY@@", str(body))
                     .replace("@@CORNER_BUNDLE@@", str(bundle)))
    req["corners"]["process"] = ["typ"]
    req["corners"]["temperature_c"] = [temp_c]
    req["analysis"]["args"] = tran
    req["options"]["timeout_s"] = timeout_s
    return req


def fail(meta, out, code):
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdk-root", default="")
    ap.add_argument("--max-passes", type=int, default=6)
    ap.add_argument("--min-passes", type=int, default=3)
    ap.add_argument("--budget-s", type=int, default=3240)
    ap.add_argument("--timeout-s", type=int, default=1500)
    ap.add_argument("--cells", default="iq/sanity,iq/hot,startup/sanity,startup/hot",
                    help="comma list of bench/corner cells to time")
    ap.add_argument("--validate-tran", default="",
                    help="override every bench's tran args (mechanics validation "
                         "only; gates are recorded but not enforced)")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "work").mkdir(exist_ok=True)
    t0 = time.monotonic()
    validation = bool(args.validate_tran)

    ng_banner = run(["ngspice", "--version"]).stdout
    klu_built = "Compiled with KLU Direct Linear Solver" in ng_banner
    klt_check = run(["klt", "--version"])
    klt_banner = klt_check.stdout.splitlines()[0] if klt_check.returncode == 0 \
        else "klt-missing"

    meta = {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "issue #518: SPARSE vs KLU wall-clock re-time, one serial "
                   "repo-script job on one batch instance (operator ruling 2026-11-17)",
        "cells": args.cells,
        "ngspice_banner": ng_banner.splitlines()[:3],
        "ngspice_klu_built": klu_built,
        "klt_version": klt_banner,
        "nproc": os.cpu_count(),
        "cpu_model": platform.processor() or "",
        "loadavg_start": loadavg(),
        "instance_type": imds_field("instance-type"),
        "instance_id": imds_field("instance-id"),
        "ami_id": imds_field("ami-id"),
        "rs_commit": os.environ.get("RS_COMMIT", ""),
        "rs_source_commit": os.environ.get("RS_SOURCE_COMMIT", ""),
        "rs_src_sha256": os.environ.get("RS_SRC_SHA256", ""),
        "pdk_pin": json.loads((REPO / "sim/pdk.json").read_text()),
        "max_passes": args.max_passes,
        "min_passes": args.min_passes,
        "budget_s": args.budget_s,
        "validate_tran": args.validate_tran,
    }

    pdk_root = args.pdk_root or os.environ.get("RETIME_PDK_ROOT", "") or "/opt/pdk"
    pdk = "ihp-sg13g2"
    ngdir = Path(pdk_root) / pdk / "libs.tech" / "ngspice"
    if not (ngdir / "models").is_dir() or not (ngdir / "osdi" / "psp103.osdi").is_file():
        env = run(["bash", "-c",
                   f"source {REPO}/sim/env.sh >/dev/null; printf '%s' \"${{PDK_ROOT:-}}\""])
        if env.stdout:
            pdk_root = env.stdout
            ngdir = Path(pdk_root) / pdk / "libs.tech" / "ngspice"
    meta["pdk_root"] = pdk_root
    if not (ngdir / "osdi" / "psp103.osdi").is_file():
        meta["error"] = f"no resolvable {pdk} install (looked at {pdk_root} and sim/env.sh)"
        log(meta["error"])
        return fail(meta, out, 3)
    if not klu_built:
        meta["error"] = ("batch image ngspice is NOT compiled with KLU -- image gap; "
                         "issue #518 acceptance criterion 1 says file and park")
        log(meta["error"])
        return fail(meta, out, 4)

    helper = out / "work" / "msense_helper.sh"
    helper.write_text(
        "set -euo pipefail\n"
        f"cd {REPO}\n"
        "REPO_ROOT=\"$PWD\"\n"
        "source sim/lib/msense_width.sh\n"
        "read_msense_width design/netlist/bandgap_startup.spice\n"
        "printf '%s' \"$MSENSE_W\"\n")
    msense = run(["bash", str(helper)])
    if msense.returncode != 0 or not msense.stdout.strip():
        meta["error"] = f"read_msense_width failed: {msense.stderr[-400:]}"
        return fail(meta, out, 3)
    msense_w = msense.stdout.strip()
    meta["msense_w"] = msense_w
    log(f"MSENSE_W={msense_w} pdk_root={pdk_root}")

    bundle = out / "work" / "sg13g2_corners.lib"
    b = run([sys.executable, str(REPO / "sim/harness/klt_corner_bundle.py"),
             "-o", str(bundle), "--pdk-root", pdk_root])
    if b.returncode != 0:
        meta["error"] = f"klt_corner_bundle.py failed: {b.stderr[-400:]}"
        return fail(meta, out, 3)

    wanted = {tuple(x.strip().split("/")) for x in args.cells.split(",") if x.strip()}
    cells = []
    bodies = {}
    for bench, cfg in BENCHES.items():
        tmpl_body = REPO / cfg["exp"] / "testbench" / f"{cfg['stem']}.body.spice.tmpl"
        tmpl_req = REPO / cfg["exp"] / "testbench" / f"{cfg['stem']}.request.json.tmpl"
        raw = tmpl_body.read_text()
        for cid, cor in CORNERS.items():
            if (bench, cid) not in wanted:
                continue
            base = raw
            for key, val in (("OSDI_DIR", str(ngdir / "osdi")), ("VDD", cor["vdd"]),
                             ("MSENSE_W", msense_w)):
                base = base.replace(f"@@{key}@@", val)
            klu = base.replace(".options reltol=5e-3\n", ".options reltol=5e-3 klu\n")
            if base.count(".options reltol=5e-3\n") != 1 or klu == base:
                meta["error"] = f"{bench}/{cid}: .options line substitution failed"
                return fail(meta, out, 3)
            diff = [l for l in difflib.unified_diff(
                base.splitlines(), klu.splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and l[:3] not in ("---", "+++")]
            if sorted(diff) != sorted(["+.options reltol=5e-3 klu", "-.options reltol=5e-3"]):
                meta["error"] = f"{bench}/{cid}: klu body differs by more than the token: {diff}"
                return fail(meta, out, 3)
            tran = args.validate_tran or cfg["tran"]
            for solver in SOLVERS:
                d = out / "work" / f"{bench}-{cid}-{solver}"
                d.mkdir(exist_ok=True)
                body = d / "body.spice"
                body.write_text(klu if solver == "klu" else base)
                bodies[f"{bench}/{cid}/{solver}"] = run(
                    ["sha256sum", str(body)]).stdout.split()[0]
                req = build_request(tmpl_req, body, bundle, cor["temp_c"], tran,
                                    args.timeout_s)
                (d / "request.json").write_text(json.dumps(req, indent=2) + "\n")
            cells.append({"bench": bench, "corner": cid, "cfg": cfg, "cor": cor,
                          "tran": tran})
    if len(cells) * len(SOLVERS) != len(bodies):
        meta["error"] = "cell selection did not resolve"
        return fail(meta, out, 3)
    meta["bodies_sha256"] = bodies
    meta["tran_per_bench"] = {c["bench"]: c["tran"] for c in cells}
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    csv_path = out / "results.csv"
    rows = []
    slowest = 0.0

    def do_pass(p):
        nonlocal slowest
        for cell in cells:
            for solver in SOLVERS:
                elapsed = time.monotonic() - t0
                done = len([r for r in rows if r["bench"] == cell["bench"]
                            and r["corner"] == cell["corner"]
                            and r["solver"] == solver and r["status"] == "pass"])
                if p > args.min_passes and done >= args.min_passes \
                        and elapsed + slowest * 1.2 > args.budget_s:
                    log(f"budget guard: stop before "
                        f"{cell['bench']}/{cell['corner']}/{solver} pass {p} "
                        f"(elapsed {elapsed:.0f}s, slowest {slowest:.0f}s)")
                    return False
                rd = out / "work" / f"{cell['bench']}-{cell['corner']}-{solver}" / f"p{p}"
                rd.mkdir(exist_ok=True)
                (rd / "request.json").write_text((rd.parent / "request.json").read_text())
                log(f"run {cell['bench']}/{cell['corner']}/{solver} pass {p}")
                t1 = time.monotonic()
                r = subprocess.run(
                    ["klt", "sim", "request.json", "--backend", "local",
                     "--format", "json", "-o", "artifacts"],
                    cwd=rd, text=True, capture_output=True)
                wall_proc = time.monotonic() - t1
                (rd / "klt.stdout").write_text(r.stdout)
                (rd / "klt.stderr").write_text(r.stderr)
                row = dict.fromkeys(CSV_FIELDS, "")
                row.update(bench=cell["bench"], corner=cell["corner"], solver=solver,
                           **{"pass": p}, wall_proc_s=f"{wall_proc:.1f}", run_dir=str(rd))
                try:
                    report = json.loads(r.stdout)
                except json.JSONDecodeError:
                    report = None
                if report is not None:
                    (rd / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                    row["status"] = report.get("status", "")
                    corners = report.get("corners") or []
                    if corners:
                        c = corners[0]
                        row["corner_id"] = c.get("corner_id", "")
                        rss = c.get("peak_rss_bytes")
                        if isinstance(rss, (int, float)):
                            row["peak_rss_mb"] = f"{rss / 1048576:.0f}"
                        got = {m.get("name"): m.get("value")
                               for m in c.get("measurements") or []}
                        w, field = engine_wall(c)
                        if w is not None:
                            row["wall_engine_s"] = f"{w:.1f}"
                            row["wall_engine_field"] = field
                            slowest = max(slowest, w)
                        exp = cell["cfg"]["anchors"][cell["corner"]]
                        for i, (name, ev) in enumerate(exp.items(), 1):
                            gv = got.get(name)
                            row[f"anchor{i}_name"] = name
                            row[f"anchor{i}_value"] = gv
                            row[f"anchor{i}_expected"] = repr(ev)
                            row[f"anchor{i}_ok"] = "" if gv is None else (
                                abs(abs(gv) - ev) <= max(abs(ev) * 1e-5, 1e-9))
                    line = ""
                    for lg in sorted(rd.glob("artifacts/**/*.log")):
                        m = re.search(r"Using .* as Direct Linear Solver",
                                      lg.read_text(errors="replace"))
                        if m:
                            line = m.group(0)
                            break
                    row["solver_line"] = line
                    row["solver_line_ok"] = line == SOLVER_LINE_EXPECT[solver]
                else:
                    row["status"] = f"klt-exit-{r.returncode}"
                rows.append(row)
                for junk in list(rd.glob("artifacts/*/corner.cir")) + \
                        list(rd.glob("artifacts/report.json")):
                    junk.unlink()
                with open(csv_path, "w", newline="") as f:
                    wtr = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                    wtr.writeheader()
                    wtr.writerows(rows)
                log(f"done {cell['bench']}/{cell['corner']}/{solver} pass {p}: "
                    f"status={row['status']} engine={row['wall_engine_s']}s "
                    f"solver_ok={row['solver_line_ok']}")
        return True

    for p in range(1, args.max_passes + 1):
        if not do_pass(p):
            break

    meta["loadavg_end"] = loadavg()
    meta["total_elapsed_s"] = round(time.monotonic() - t0, 1)
    summary = {}
    problems = []
    for cell in cells:
        for solver in SOLVERS:
            key = f"{cell['bench']}/{cell['corner']}/{solver}"
            sel = [r for r in rows if r["bench"] == cell["bench"]
                   and r["corner"] == cell["corner"] and r["solver"] == solver]
            ws = [float(r["wall_engine_s"]) for r in sel if r["wall_engine_s"]]
            entry = {"n": len(sel), "n_timed": len(ws)}
            if ws:
                entry.update(min=round(min(ws), 1), median=round(statistics.median(ws), 1),
                             max=round(max(ws), 1),
                             spread=round(max(ws) - min(ws), 1))
            summary[key] = entry
            if validation:
                continue
            if len(ws) < args.min_passes:
                problems.append(f"{key}: only {len(ws)}/{args.min_passes} timed runs")
            for r in sel:
                if r["status"] != "pass":
                    problems.append(f"{key} pass {r['pass']}: status {r['status']}")
                if r.get("solver_line_ok") is False:
                    problems.append(f"{key} pass {r['pass']}: solver line mismatch "
                                    f"{r['solver_line']!r}")
                for i in (1, 2):
                    if r.get(f"anchor{i}_ok") is False:
                        problems.append(
                            f"{key} pass {r['pass']}: anchor {r[f'anchor{i}_name']}="
                            f"{r[f'anchor{i}_value']} off expectation "
                            f"{r[f'anchor{i}_expected']}")
    deltas = {}
    for cell in cells:
        key = f"{cell['bench']}/{cell['corner']}"
        try:
            smin = summary[f"{key}/sparse"]["min"]
            kmin = summary[f"{key}/klu"]["min"]
            deltas[key] = {
                "sparse_min_s": smin, "klu_min_s": kmin,
                "delta_s": round(smin - kmin, 1),
                "ratio_s_over_k": round(smin / kmin, 3) if kmin else None,
                "spread_sparse": summary[f"{key}/sparse"]["spread"],
                "spread_klu": summary[f"{key}/klu"]["spread"],
                "resolved": abs(smin - kmin) > max(summary[f"{key}/sparse"]["spread"],
                                                   summary[f"{key}/klu"]["spread"]),
            }
        except (KeyError, TypeError, ZeroDivisionError):
            pass
    meta["summary"] = summary
    meta["solver_delta"] = deltas
    meta["problems"] = problems
    meta["validation_mode"] = validation
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    log(f"summary: {json.dumps(deltas, indent=1)}")
    if problems and not validation:
        for p in problems:
            log(f"PROBLEM: {p}")
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
