#!/usr/bin/env python3
"""`klt sim` plumbing for sim/trim-coverage (issue #416, Part of #412).

The trim-coverage bench is a deterministic .op sweep over a TRIM CODE axis:
15 (process x supply) groups at 27 C x 11 codes, plus the step's temperature
probe (typ/3.30V at -40/125 C, codes 128/129) -- 169 points. The shared PEX
helpers (gen_pex_batch_requests.py, merge_batch_shards.py's label grammar)
know process x supply x temperature only, so this module adds the code axis
without touching them:

* the code rides the request's `corners.params.trim_code` (klayout-tools
  #3035), a top-level `.param` in the body;
* `prepare` writes one request + body variant per (process, supply,
  temperature) -- the supply and the .nodeset seeds are baked into the body
  (the seeds differ per variant) -- and a manifest + expected-grid file;
* `merge` (run after the runner's fixup_batch_report.py pass over each shard)
  relabels every point as `<process>_code<N>` (the grammar the committed
  records use for corner_label), injects the shard's supply, and merges with
  the grid stated explicitly (merge_batch_shards.merge);
* `enrich` forms dvsns_v, adds trim_code as a column and re-grades each point
  with the closed-loop verdict (sim/lib/pvt_verdict_common.sh's three
  criteria -- an .op has no settling pair);
* `spec` expands the record spec's per-label columns over the code labels;
* `analysis` computes the ladder-coverage gates (resolution, range, binary
  weights, curvature, monotonicity) per group from the minted record's CSV,
  a line-for-line port of run_trim_coverage.sh's awk block.

Pure JSON/CSV transforms plus request/body text substitution: no simulator
is launched from here.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import klt_corner_bundle as bundle  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402

CODES = (0, 1, 2, 4, 8, 16, 32, 64, 128, 129, 255)
VDDS = (2.97, 3.30, 3.63)
TEMP_TRIM_C = 27
PROBE_TEMPS = (-40, 125)
PROBE_CODES = (128, 129)
VREF_TARGET_V = 1.050
RANGE_FLOOR_PCT = 15.0
RES_CAP_PCT = 0.25

# sim/lib/pvt_verdict_common.sh
DET_RELEASE_FRAC = 0.2
I_MKFB_RELEASE_A = 50e-9
DVSNS_CLOSE_V = 0.020
FB_RAIL_MARGIN_V = 0.05

SEED_FIELDS = (("@@FB_SEED@@", "fb_final_v"), ("@@SNS1_SEED@@", "sns1_final_v"),
               ("@@SNS2_SEED@@", "sns2_final_v"), ("@@VREF_SEED@@", "vref_final_v"))


def shard_plan() -> list[tuple[str, float, int, tuple[int, ...]]]:
    """(label, vdd, temp_c, codes) per request, in grid order."""
    plan = [(label, vdd, TEMP_TRIM_C, CODES) for label in bundle.CORNER_SECTIONS for vdd in VDDS]
    plan += [("typ", 3.30, t, PROBE_CODES) for t in PROBE_TEMPS]
    return plan


def shard_id(label: str, vdd: float, temp: int) -> str:
    t = f"m{-temp}" if temp < 0 else str(temp)
    return f"{label}-{vdd:.2f}".replace(".", "p") + f"-t{t}"


def point_id(label: str, code: int, temp: float, vdd: float) -> str:
    return f"{label}_code{code}_{temp:g}c_{vdd:.2f}v"


def expected_points() -> list[str]:
    return [point_id(label, code, temp, vdd)
            for label, vdd, temp, codes in shard_plan() for code in codes]


def load_seeds(seed_csv: str) -> dict:
    seeds: dict = {}
    with open(seed_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "PASS":
                seeds[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row
    return seeds


def seed_row(seeds: dict, label: str, temp: int, vdd: float, seed_csv: str) -> dict:
    row = seeds.get((label, str(temp), f"{vdd:.2f}"))
    if row is None:
        raise SystemExit(f"no PASS seed row for {label}/{temp}C/{vdd:.2f}V in {seed_csv}")
    return row


def fill(text: str, mapping: dict[str, str]) -> str:
    for token, value in mapping.items():
        text = text.replace(token, value)
    return text


def body_text(template: str, osdi: str, label: str, vdd: float, temp: int,
              msense_w: str, seeds: dict, seed_csv: str) -> str:
    row = seed_row(seeds, label, temp, vdd, seed_csv)
    mapping = {"@@OSDI_DIR@@": osdi, "@@VDD@@": f"{vdd}", "@@MSENSE_W@@": msense_w}
    mapping.update({token: row[field] for token, field in SEED_FIELDS})
    text = fill(template, mapping)
    left = sorted({w for w in text.split() if w.startswith("@@") and w.endswith("@@")})
    if left:
        raise SystemExit(f"body template has unfilled placeholders: {left}")
    return text


def prepare(a: argparse.Namespace) -> None:
    work = Path(a.work)
    req_tmpl = Path(a.request_template).read_text()
    body_tmpl = Path(a.body_template).read_text()
    seeds = load_seeds(a.seed_csv)

    if a.mode == "sanity":
        # One typ/27C/3.30V point at the default code: the anchor.
        body = work / "body.spice"
        body.write_text(body_text(body_tmpl, a.osdi_dir, "typ", 3.30, TEMP_TRIM_C,
                                  a.msense_w, seeds, a.seed_csv))
        req = json.loads(req_tmpl.replace("@@BODY@@", str(body))
                         .replace("@@CORNER_BUNDLE@@", a.bundle))
        req["corners"]["process"] = ["typ"]
        req["corners"]["temperature_c"] = [TEMP_TRIM_C]
        req["corners"]["params"] = {"trim_code": [128]}
        (work / "request.json").write_text(json.dumps(req, indent=2) + "\n")
        return

    models_dir = f"{a.batch_pdk_root}/{a.pdk}/libs.tech/ngspice/models"
    osdi = f"{a.batch_osdi_root}/{a.pdk}/libs.tech/ngspice/osdi"
    rows: list[str] = []
    for label, vdd, temp, codes in shard_plan():
        hbt, mos, res = bundle.CORNER_SECTIONS[label]
        sid = shard_id(label, vdd, temp)
        text = body_text(body_tmpl, osdi, label, vdd, temp, a.msense_w, seeds, a.seed_csv)
        text += f"""
* Batch mode only (the per-process bridge, issue #278): the two families the
* request's single models.lib cannot reach, as selection-form `.lib` cards
* against the image's baked PDK root. Corner: {label}; supply: {vdd:.2f} V;
* temperature: {temp} C.
.lib "{models_dir}/cornerMOShv.lib" {mos}
.lib "{models_dir}/cornerRES.lib" {res}
"""
        body = work / f"body-{sid}.spice"
        body.write_text(text)
        req = json.loads(req_tmpl.replace("@@BODY@@", str(body))
                         .replace("@@CORNER_BUNDLE@@", "UNUSED-BATCH"))
        req["backend"] = "batch"
        req["models"] = {"pdk": a.pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
        req["corners"]["process"] = [hbt]
        req["corners"]["temperature_c"] = [temp]
        req["corners"]["params"] = {"trim_code": list(codes)}
        req["batch"] = {"provision_script_path": a.provision}
        (work / f"request-{sid}.json").write_text(json.dumps(req, indent=2) + "\n")
        rows.append("\t".join([
            sid, label, f"{vdd:.2f}", str(temp), f"request-{sid}.json", f"report-{sid}.json",
            f"artifacts-{sid}", f"body-fixed-{sid}.spice", f"report-{sid}-fixed.json",
            f"decks-fixed-{sid}", ",".join(map(str, codes)),
        ]))
    (work / "manifest.tsv").write_text("\n".join(rows) + "\n")
    (work / "expected-grid.json").write_text(
        json.dumps({"points": expected_points()}, indent=2) + "\n")
    print(f"prepared {len(rows)} requests / {len(expected_points())} points")


def merge(a: argparse.Namespace) -> None:
    work = Path(a.work)
    paths: list[str] = []
    for line in Path(a.manifest).read_text().splitlines():
        sid, label, vdd, temp, _req, _rep, _art, _body, fixed, _decks, _codes = line.split("\t")
        report = json.loads((work / fixed).read_text())
        for corner in report.get("corners", []):
            code = (corner.get("params") or {}).get("trim_code")
            if code is None:
                raise SystemExit(f"{fixed}: corner {corner.get('corner_id')!r} carries no "
                                 "params.trim_code echo -- worker image predates corners.params?")
            new = f"{label}_code{int(code)}"
            rest = corner["corner_id"][corner["corner_id"].find("/"):]
            # the shard carries no supply axis: name it in the id, or the same
            # code at three supplies collides (as inject_baked_supply does)
            rest = rest.replace("/novdd/", f"/{float(vdd):.2f}V/", 1)
            corner["corner_id"] = f"{new}{rest}"
            corner["process"] = new
            corner["supply_v"] = {"Vvdd": float(vdd)}
        out = work / f"relabelled-{sid}.json"
        out.write_text(json.dumps(report, indent=2) + "\n")
        paths.append(str(out))
    expected = mbs.load_expected(a.expect_grid)
    merged = mbs.merge(paths, expected)
    Path(a.output).write_text(json.dumps(merged, indent=2) + "\n")
    print(f"merged {len(merged['corners'])} points: {merged['status']}")


def _meas(corner: dict) -> dict[str, float]:
    return {m["name"]: float(m["value"]) for m in corner.get("measurements", [])
            if isinstance(m.get("value"), (int, float))}


def enrich(a: argparse.Namespace) -> None:
    report = json.loads(Path(a.report).read_text())
    for corner in report["corners"]:
        code = (corner.get("params") or {}).get("trim_code")
        got = _meas(corner)
        if corner.get("status") != "pass":
            continue
        need = ("sns1_v", "sns2_v", "fb_v", "det_v", "i_mkfb_a", "vref_v")
        if code is None or any(k not in got for k in need):
            corner["status"] = "fail"
            corner["diagnostics"] = [{"code": "derived_columns_missing", "message": "operands absent"}]
            continue
        dvsns = abs(got["sns1_v"] - got["sns2_v"])
        corner["measurements"].extend([
            {"name": "dvsns_v", "value": dvsns,
             "spice": "derived: |sns1_v - sns2_v| (see sim/harness/trim_coverage_klt.py)"},
            {"name": "trim_code", "value": float(code),
             "spice": "the request's corners.params.trim_code for this point"},
        ])
        vdd = next(iter(corner["supply_v"].values()))
        failed: list[str] = []
        if not (got["det_v"] <= DET_RELEASE_FRAC * vdd and abs(got["i_mkfb_a"]) <= I_MKFB_RELEASE_A):
            failed.append("startup_not_released")
        if dvsns > DVSNS_CLOSE_V:
            failed.append("loop_not_closed")
        if not (FB_RAIL_MARGIN_V <= got["fb_v"] <= vdd - FB_RAIL_MARGIN_V):
            failed.append("fb_railed")
        if failed:
            corner["status"] = "fail"
            corner["diagnostics"] = [{"code": "closed_loop_verdict", "message": "; ".join(failed)}]
    cs = report["corners"]
    report["passed"] = sum(c["status"] == "pass" for c in cs)
    report["failed"] = sum(c["status"] == "fail" for c in cs)
    report["errored"] = sum(c["status"] == "error" for c in cs)
    report["corner_count"] = len(cs)
    report["status"] = "fail" if report["failed"] else ("error" if report["errored"] else "pass")
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    print(f"enriched: {report['status']} passed={report['passed']} failed={report['failed']} "
          f"errored={report['errored']}")


def spec(a: argparse.Namespace) -> None:
    data = json.loads(Path(a.spec).read_text())
    extra = data.get("extra_columns") or {}
    out: dict = {}
    for col, per_label in extra.items():
        out[col] = {f"{label}_code{c}": v for label, v in per_label.items() for c in CODES}
    out["msense_w"] = {f"{label}_code{c}": a.msense_w for label in bundle.CORNER_SECTIONS for c in CODES}
    data["extra_columns"] = out
    Path(a.output).write_text(json.dumps(data, indent=2) + "\n")


def analysis(a: argparse.Namespace) -> None:
    rows = list(csv.DictReader(Path(a.csv).open()))
    header = ["corner_label", "vdd_v", "group_status", "n_pass", "n_grid", "unit_v", "lsb_v",
              "lsb_pct_of_target", "up_span_v", "up_span_pct", "down_span_v", "down_span_pct",
              "worst_weight_dev_pct", "fs_resid_v", "fs_resid_lsb", "monotonic"]
    out = [header]
    group_fail = 0
    for label in bundle.CORNER_SECTIONS:
        for vdd in VDDS:
            grp = [r for r in rows if r["corner_label"].startswith(f"{label}_code")
                   and r["corner_label"].split("_code")[0] == label
                   and r["vdd_v"] == f"{vdd:.2f}" and float(r["temp_c"]) == TEMP_TRIM_C]
            n_grid = len(grp)
            v = {int(round(float(r["trim_code"]))): float(r["vref_v"])
                 for r in grp if r["status"] == "PASS"}
            n_pass = len(v)
            status = "PASS"
            if 1 in v and 255 in v and 0 in v and 128 in v and 129 in v:
                unit = v[1] - v[0]
                lsb = v[129] - v[128]
                up, down = v[255] - v[128], v[128] - v[0]
                worst = 0.0
                for b in (1, 2, 4, 8, 16, 32, 64, 128):
                    if b in v and b * unit != 0:
                        worst = max(worst, abs(100 * ((v[b] - v[0]) - b * unit) / (b * unit)))
                fsr = v[255] - (v[0] + 255 * unit)
                fsr_lsb = fsr / lsb if lsb else 0.0
                seq = [v[c] for c in CODES if c in v]
                mono = "yes" if all(y > x for x, y in zip(seq, seq[1:])) else "no"
                lsb_pct, up_pct, down_pct = (100 * x / VREF_TARGET_V for x in (lsb, up, down))
                if (n_pass != n_grid or unit == 0 or lsb_pct > RES_CAP_PCT
                        or up_pct < RANGE_FLOOR_PCT or down_pct < RANGE_FLOOR_PCT
                        or worst > 0.5 or abs(fsr_lsb) > 2 or mono != "yes"):
                    status = "FAIL"
                cells = [f"{unit:.9g}", f"{lsb:.9g}", f"{lsb_pct:.6f}", f"{up:.9g}", f"{up_pct:.6f}",
                         f"{down:.9g}", f"{down_pct:.6f}", f"{worst:.4f}", f"{fsr:.9g}",
                         f"{fsr_lsb:.4f}", mono]
            else:
                status = "FAIL"
                cells = ["0"] * 10 + ["incomplete"]
            group_fail += status == "FAIL"
            out.append([label, f"{vdd:.2f}", status, str(n_pass), str(n_grid)] + cells)
    with Path(a.output).open("w", newline="") as fh:
        csv.writer(fh, lineterminator="\n").writerows(out)
    print(f"ladder-coverage analysis: {Path(a.output).name}: {group_fail}/15 groups FAIL the gates")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--mode", choices=("sanity", "batch"), required=True)
    p.add_argument("--request-template", required=True)
    p.add_argument("--body-template", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--seed-csv", required=True)
    p.add_argument("--msense-w", required=True)
    p.add_argument("--osdi-dir")
    p.add_argument("--bundle")
    p.add_argument("--pdk")
    p.add_argument("--batch-pdk-root")
    p.add_argument("--batch-osdi-root", default="/opt/pdk")
    p.add_argument("--provision")
    p.set_defaults(fn=prepare)

    p = sub.add_parser("merge")
    p.add_argument("--manifest", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--expect-grid", required=True)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=merge)

    p = sub.add_parser("enrich")
    p.add_argument("report")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=enrich)

    p = sub.add_parser("spec")
    p.add_argument("spec")
    p.add_argument("--msense-w", required=True)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=spec)

    p = sub.add_parser("analysis")
    p.add_argument("csv")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=analysis)

    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
