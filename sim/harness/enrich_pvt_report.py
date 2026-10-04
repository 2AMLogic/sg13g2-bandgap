#!/usr/bin/env python3
"""Enrich a merged PVT report with derived columns and the closed-loop verdict.

Issue #278. Two things the `klt sim` request schema cannot express on the
runner image's klt 0.5.0, both of which this repo's committed
`run_pvt_sweep.sh` benches have always done per point:

1. **Derived columns.** `dvsns_v` (|sns1-sns2|, the loop-closure residual)
   and `vref_settle_delta_v` (|vref(3ms)-vref(2ms)|) are differences of two
   reported values. The harness README's precision disposition prefers a
   derived `.meas ... find par('...')` for those -- but a resident-vector
   `.save` list (required on the 3 ms benches, issue #278 work item 3)
   disables `par()` inside `.meas find` (ngspice 46 rewrites the
   expression to an internal `pa_<n>` parameter that is then not a resident
   vector; verified). The committed box-TC records already form `box_tc`
   from 6-s.f. operands the same way, so the practice is established and
   disclosed; this module is its single home for the klt path.

2. **The closed-loop verdict.** sim/lib/pvt_verdict_common.sh's
   `pvt_closed_loop_verdict` -- startup released (det <= 0.2*vdd AND
   |i_mkfb| <= 50 nA), loop closed (dvsns <= 20 mV), fb not railed
   (0.05 <= fb <= vdd-0.05), settled (delta <= 1 mV). `klt sim`'s own
   grading knows only measurement presence; a point that converged but
   landed in the degenerate all-off equilibrium would otherwise read PASS.
   This module re-grades each point with the same four criteria and the
   same constants, and marks the corner `fail` with a diagnostic naming
   which criterion tripped.

Pure JSON transform over the merged report: appends measurement entries
(derivation noted in each entry's `spice` field), re-grades, recomputes the
top-level counts. The adapter mints the record from the enriched report.

Usage:

    python3 sim/harness/enrich_pvt_report.py report-merged.json -o enriched.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DET_RELEASE_FRAC = 0.2
I_MKFB_RELEASE_A = 50e-9
DVSNS_CLOSE_V = 0.020
FB_RAIL_MARGIN_V = 0.05
SETTLE_TOL_V = 0.001

# sim/lib/pvt_preflight.sh's grid: the supply of a corner id like
# "typ/2.970V/-40C" is the V field; the verdict's vdd term needs it.
_CORNER_RE = None


def _corner_vdd(corner: dict) -> float | None:
    cid = corner.get("corner_id", "")
    try:
        return float(cid.split("/")[1].rstrip("V"))
    except (IndexError, ValueError):
        return None


def _meas_map(corner: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in corner.get("measurements", []):
        v = m.get("value")
        if isinstance(v, (int, float)):
            out[m["name"]] = float(v)
    return out


_VDD_PWL_RE = re.compile(r"^Vvdd\s+vdd\s+0\s+PWL\(0\s+0\s+[0-9.]+u?\s+([-+0-9.eE]+)", re.M | re.I)


def enrich(report: dict) -> dict:
    corners = report.get("corners", [])
    cwd = Path.cwd()
    for corner in corners:
        got = _meas_map(corner)
        if corner.get("status") != "pass":
            continue
        # These benches bake the supply into the body's PWL ramp (an
        # `alter`-driven supply axis would clobber the ramp), so the
        # request carries no supply axis and the corner id has no V token.
        # The adapter's corner-id grammar requires exactly one supply:
        # inject the baked ramp target, read off the corner's own deck.
        deck_ref = (corner.get("artifacts") or {}).get("deck")
        if deck_ref and "/novdd/" in corner.get("corner_id", ""):
            dp = Path(deck_ref)
            if not dp.is_absolute():
                dp = cwd / dp
            if dp.exists():
                import re as _re
                m = _VDD_PWL_RE.search(dp.read_text(encoding="utf-8", errors="replace"))
                if not m:
                    for line in dp.read_text(encoding="utf-8", errors="replace").splitlines():
                        inc = _re.match(r'^\s*\.include\s+"?([^"\s]+)"?', line, _re.I)
                        if inc:
                            bp = Path(inc.group(1))
                            if not bp.is_absolute():
                                bp = dp.parent / bp
                            if bp.exists():
                                m = _VDD_PWL_RE.search(bp.read_text(encoding="utf-8", errors="replace"))
                            if m:
                                break
                if m:
                    vdd = float(m.group(1))
                    corner["supply_v"] = {"Vvdd": vdd}
                    corner["corner_id"] = corner["corner_id"].replace("/novdd/", f"/{vdd:.2f}V/")
        needed = ("sns1_v", "sns2_v", "vref_2ms_v", "vref_3ms_v")
        if any(k not in got for k in needed):
            corner["status"] = "fail"
            corner["diagnostics"] = [
                {"code": "derived_columns_missing", "message": "operands absent"}
            ]
            continue
        dvsns = abs(got["sns1_v"] - got["sns2_v"])
        settle = abs(got["vref_3ms_v"] - got["vref_2ms_v"])
        corner["measurements"].extend(
            [
                {
                    "name": "dvsns_v",
                    "value": dvsns,
                    "spice": "derived: |sns1_v - sns2_v| (see sim/harness/enrich_pvt_report.py)",
                },
                {
                    "name": "vref_settle_delta_v",
                    "value": settle,
                    "spice": "derived: |vref_3ms_v - vref_2ms_v| (see sim/harness/enrich_pvt_report.py)",
                },
            ]
        )
        vdd = _corner_vdd(corner)
        failed: list[str] = []
        det = got.get("det_v")
        i_mkfb = got.get("i_mkfb_a")
        fb = got.get("fb_v")
        if vdd is not None and det is not None and i_mkfb is not None:
            if not (det <= DET_RELEASE_FRAC * vdd and abs(i_mkfb) <= I_MKFB_RELEASE_A):
                failed.append("startup_not_released")
        if dvsns > DVSNS_CLOSE_V:
            failed.append("loop_not_closed")
        if vdd is not None and fb is not None:
            if not (FB_RAIL_MARGIN_V <= fb <= vdd - FB_RAIL_MARGIN_V):
                failed.append("fb_railed")
        if settle > SETTLE_TOL_V:
            failed.append("not_settled")
        if failed:
            corner["status"] = "fail"
            corner["diagnostics"] = [
                {
                    "code": "closed_loop_verdict",
                    "message": "; ".join(failed),
                }
            ]
    passed = sum(1 for c in corners if c.get("status") == "pass")
    failed = sum(1 for c in corners if c.get("status") == "fail")
    errored = sum(1 for c in corners if c.get("status") == "error")
    report["corners"] = corners
    report["passed"] = passed
    report["failed"] = failed
    report["errored"] = errored
    report["corner_count"] = len(corners)
    report["status"] = "fail" if failed else ("error" if errored else "pass")
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args(argv)
    report = enrich(json.loads(args.report.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for c in report["corners"]:
        if c.get("status") != "pass":
            diag = "; ".join(d.get("message", "") for d in c.get("diagnostics", []))
            print(f"  {c.get('corner_id')}: {c['status']} {diag[:100]}")
    print(
        f"enriched: {report['status']} passed={report['passed']} "
        f"failed={report['failed']} errored={report['errored']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
