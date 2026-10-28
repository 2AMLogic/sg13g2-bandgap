#!/usr/bin/env python3
"""Enrich a merged closed-loop-iq / closed-loop-startup report (issue #414).

The Iq and Startup benches are the same closed-loop topology as the vref
benches (see enrich_pvt_report.py), so they share its verdict constants and
supply-injection helper, but their measurements and settledness criterion
differ, so they get their own small pass over the merged report:

* ``--bench iq``: the verdict is read at t=3 ms, the supply-current columns are
  reported as magnitudes (ngspice's passive sign convention reports i(Vvdd)
  negative while the supply delivers current), ``dvsns_v`` and
  ``iq_settle_delta_a`` (|iq_3ms - iq_2ms|) are derived, and a point is also
  graded ``not_settled`` when that delta exceeds 100 nA.
* ``--bench startup``: the verdict is read at t=2 ms, ``dvsns_final_v`` is
  derived, and there is no settledness criterion (the legacy bench has none).

Both re-grade a corner ``fail`` with the same startup_not_released /
loop_not_closed / fb_railed criteria and constants as pvt_closed_loop_verdict.

Usage:

    python3 sim/harness/enrich_supply_bench_report.py --bench iq report-merged.json -o enriched.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from enrich_pvt_report import (
    DET_RELEASE_FRAC,
    DVSNS_CLOSE_V,
    FB_RAIL_MARGIN_V,
    I_MKFB_RELEASE_A,
    _corner_vdd,
    _meas_map,
    inject_baked_supply,
)

IQ_SETTLE_TOL_A = 1e-7

BENCHES = {
    "iq": {
        "fb": "fb_v", "sns1": "sns1_v", "sns2": "sns2_v", "det": "det_v", "i_mkfb": "i_mkfb_a",
        "dvsns": "dvsns_v",
        "magnitudes": ("iq_2ms_a", "iq_3ms_a", "iq_avg_a"),
    },
    "startup": {
        "fb": "fb_final_v", "sns1": "sns1_final_v", "sns2": "sns2_final_v",
        "det": "det_final_v", "i_mkfb": "i_mkfb_final_a",
        "dvsns": "dvsns_final_v",
        "magnitudes": (),
    },
}


def enrich(report: dict, bench: str) -> dict:
    cfg = BENCHES[bench]
    corners = report.get("corners", [])
    cwd = Path.cwd()
    for corner in corners:
        if corner.get("status") != "pass":
            continue
        inject_baked_supply(corner, cwd)
        got = _meas_map(corner)
        needed = [cfg[k] for k in ("fb", "sns1", "sns2", "det", "i_mkfb")] + list(cfg["magnitudes"])
        if any(k not in got for k in needed):
            corner["status"] = "fail"
            corner["diagnostics"] = [{"code": "derived_columns_missing", "message": "operands absent"}]
            continue
        for m in corner["measurements"]:
            if m["name"] in cfg["magnitudes"] and isinstance(m.get("value"), (int, float)):
                m["value"] = abs(m["value"])
                m["spice"] = m.get("spice", "") + " ; magnitude (see sim/harness/enrich_supply_bench_report.py)"
        got = _meas_map(corner)
        dvsns = abs(got[cfg["sns1"]] - got[cfg["sns2"]])
        derived = [{
            "name": cfg["dvsns"], "value": dvsns,
            "spice": "derived: |sns1 - sns2| (see sim/harness/enrich_supply_bench_report.py)",
        }]
        settle = None
        if bench == "iq":
            settle = abs(got["iq_3ms_a"] - got["iq_2ms_a"])
            derived.append({
                "name": "iq_settle_delta_a", "value": settle,
                "spice": "derived: |iq_3ms_a - iq_2ms_a| (see sim/harness/enrich_supply_bench_report.py)",
            })
        corner["measurements"].extend(derived)
        vdd = _corner_vdd(corner)
        failed: list[str] = []
        det, i_mkfb, fb = got[cfg["det"]], got[cfg["i_mkfb"]], got[cfg["fb"]]
        if vdd is not None and not (det <= DET_RELEASE_FRAC * vdd and abs(i_mkfb) <= I_MKFB_RELEASE_A):
            failed.append("startup_not_released")
        if dvsns > DVSNS_CLOSE_V:
            failed.append("loop_not_closed")
        if vdd is not None and not (FB_RAIL_MARGIN_V <= fb <= vdd - FB_RAIL_MARGIN_V):
            failed.append("fb_railed")
        if settle is not None and settle > IQ_SETTLE_TOL_A:
            failed.append("not_settled")
        if failed:
            corner["status"] = "fail"
            corner["diagnostics"] = [{"code": "closed_loop_verdict", "message": "; ".join(failed)}]
    report["corners"] = corners
    report["passed"] = sum(1 for c in corners if c.get("status") == "pass")
    report["failed"] = sum(1 for c in corners if c.get("status") == "fail")
    report["errored"] = sum(1 for c in corners if c.get("status") == "error")
    report["corner_count"] = len(corners)
    report["status"] = "fail" if report["failed"] else ("error" if report["errored"] else "pass")
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--bench", required=True, choices=sorted(BENCHES))
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args(argv)
    report = enrich(json.loads(args.report.read_text(encoding="utf-8")), args.bench)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for c in report["corners"]:
        if c.get("status") != "pass":
            diag = "; ".join(d.get("message", "") for d in c.get("diagnostics", []))
            print(f"  {c.get('corner_id')}: {c['status']} {diag[:100]}")
    print(f"enriched: {report['status']} passed={report['passed']} "
          f"failed={report['failed']} errored={report['errored']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
