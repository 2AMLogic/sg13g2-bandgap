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
* ``--bench startup_release``: the ladder mode (issue #468). The verdict is read
  at *every* checkpoint of a fixed-time ladder, not at one timepoint, so the
  bench can report the earliest checkpoint from which the release criteria hold
  continuously to the end of the window. It derives ``dvsns_<N>u_v`` at every
  checkpoint, ``checkpoint_verdicts`` (the semicolon-joined
  ``<N>u:<PASS|FAIL|MISSING>`` trajectory) and ``release_time_us``, the three
  columns ``sim/startup-time-to-release/run_pvt_sweep.sh`` derives in bash.

All three re-grade a corner ``fail`` with the same startup_not_released /
loop_not_closed / fb_railed criteria and constants as pvt_closed_loop_verdict
-- ``startup_release`` applies them once per checkpoint rather than once.

``release_time_us`` is a **suffix-of-PASS** rule, not "the first checkpoint that
happens to PASS": the earliest checkpoint such that it *and every later
checkpoint through the last one* all PASS, else ``NOT_RELEASED``. A corner that
transiently satisfies the release criteria and then regresses is therefore not
misreported as released early. This is the definition
``sim/startup-time-to-release/README.md`` states; it differs from that bench's
legacy bash in one corner case, deliberately -- the bash let a ``MISSING``
checkpoint pass through its running-start tracker, so a ladder like
``PASS;MISSING;PASS`` reported ``NOT_RELEASED`` there and reports the last
checkpoint here. Either way the corner is graded ``fail`` (a ``MISSING``
checkpoint is itself a failure), so only the reported number differs.

The ladder is never hardcoded (issue #210's single-source-of-truth property):
:func:`ladder_checkpoints` reads it back off the ``det_<N>u_v`` measurement
names the request asked for, so adding or removing a checkpoint is an edit to
the request template alone.

Usage:

    python3 sim/harness/enrich_supply_bench_report.py --bench iq report-merged.json -o enriched.json
    python3 sim/harness/enrich_supply_bench_report.py --bench startup_release report-merged.json -o enriched.json
"""

from __future__ import annotations

import argparse
import json
import re
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

#: The ladder bench's own name, kept out of :data:`BENCHES` because it is not a
#: fixed-checkpoint signal map: every column it derives is a function of the
#: ladder, which only the report itself knows.
LADDER_BENCH = "startup_release"

#: The five release-criteria signals, per checkpoint, in this repo's klt CSV
#: naming (the legacy template's ngspice `.meas` names are `v_det_<N>u` etc.;
#: see the request template's own `_comment` on the two namespaces).
LADDER_SIGNALS = ("det_{t}u_v", "i_mkfb_{t}u_a", "fb_{t}u_v", "sns1_{t}u_v", "sns2_{t}u_v")

NOT_RELEASED = "NOT_RELEASED"

_LADDER_RE = re.compile(r"^det_(\d+)u_v$")

_SEE = "(see sim/harness/enrich_supply_bench_report.py)"


def ladder_checkpoints(corner: dict) -> list[int]:
    r"""The checkpoint ladder (microseconds, ascending), read off the corner.

    `det_<N>u_v` is the probe every checkpoint carries, so its measurement
    names are the ladder. Deriving it here rather than hardcoding it keeps the
    request template the single source of truth (issue #210). `det_early_v`
    (t=20 us) never matches: "early" is not `\d+`.
    """
    found = set()
    for entry in corner.get("measurements", []):
        hit = _LADDER_RE.match(str(entry.get("name", "")))
        if hit:
            found.add(int(hit.group(1)))
    return sorted(found)


def release_time_us(verdicts: list[tuple[int, str]]) -> int | str:
    """Suffix-of-PASS: the earliest checkpoint from which every verdict PASSes.

    `NOT_RELEASED` when no such suffix exists -- including when the final
    checkpoint itself does not PASS, which is what makes this a settled-release
    measurement rather than a transient-crossing one.
    """
    for index, (checkpoint, _) in enumerate(verdicts):
        if all(v == "PASS" for _, v in verdicts[index:]):
            return checkpoint
    return NOT_RELEASED


def _fail(corner: dict, code: str, message: str) -> None:
    corner["status"] = "fail"
    corner["diagnostics"] = [{"code": code, "message": message}]


def _enrich_ladder_corner(corner: dict, cwd: Path) -> None:
    """Grade one corner of the ladder bench (`--bench startup_release`)."""
    inject_baked_supply(corner, cwd)
    got = _meas_map(corner)
    checkpoints = ladder_checkpoints(corner)
    if not checkpoints:
        _fail(corner, "derived_columns_missing",
              "no det_<N>u_v checkpoint measurements -- not a ladder report")
        return
    vdd = _corner_vdd(corner)
    if vdd is None:
        # The two fixed-checkpoint benches above tolerate an unresolvable
        # supply by skipping the vdd-dependent criteria. This one cannot: the
        # release threshold IS a fraction of vdd, so a release time graded
        # without it would be a number with no meaning behind it.
        _fail(corner, "derived_columns_missing",
              "corner supply not resolvable (no V token in corner_id and no baked PWL ramp)")
        return

    verdicts: list[tuple[int, str]] = []
    derived: list[dict] = []
    missing: list[int] = []
    last_criteria: list[str] = []
    for checkpoint in checkpoints:
        names = [name.format(t=checkpoint) for name in LADDER_SIGNALS]
        if any(name not in got for name in names):
            verdicts.append((checkpoint, "MISSING"))
            missing.append(checkpoint)
            last_criteria = ["checkpoint_missing"]
            continue
        det, i_mkfb, fb, sns1, sns2 = (got[name] for name in names)
        dvsns = abs(sns1 - sns2)
        derived.append({
            "name": f"dvsns_{checkpoint}u_v", "value": dvsns,
            "spice": f"derived: |sns1 - sns2| at t={checkpoint}u {_SEE}",
        })
        # The same three criteria, same constants, as pvt_closed_loop_verdict
        # -- evaluated per checkpoint instead of once at a final time.
        failed = []
        if not (det <= DET_RELEASE_FRAC * vdd and abs(i_mkfb) <= I_MKFB_RELEASE_A):
            failed.append("startup_not_released")
        if dvsns > DVSNS_CLOSE_V:
            failed.append("loop_not_closed")
        if not (FB_RAIL_MARGIN_V <= fb <= vdd - FB_RAIL_MARGIN_V):
            failed.append("fb_railed")
        verdicts.append((checkpoint, "FAIL" if failed else "PASS"))
        last_criteria = failed

    release = release_time_us(verdicts)
    derived.append({
        "name": "release_time_us", "value": release,
        "spice": f"derived: earliest checkpoint with an all-PASS suffix, else {NOT_RELEASED} {_SEE}",
    })
    derived.append({
        "name": "checkpoint_verdicts",
        "value": ";".join(f"{checkpoint}u:{verdict}" for checkpoint, verdict in verdicts),
        "spice": f"derived: per-checkpoint closed-loop verdict trajectory {_SEE}",
    })
    corner["measurements"].extend(derived)

    problems: list[str] = []
    if missing:
        problems.append(
            "checkpoint_missing at " + ",".join(f"{c}u" for c in missing)
            + " (a corner that did not converge that far leaves its meas lines unprinted)"
        )
    if release == NOT_RELEASED:
        problems.append("never_released"
                        + (f" (last checkpoint: {'; '.join(last_criteria)})" if last_criteria else "")
                        + " -- see checkpoint_verdicts for the full trajectory")
    if problems:
        _fail(corner, "closed_loop_verdict", "; ".join(problems))


def _recount(report: dict, corners: list) -> dict:
    """Recompute the report-level grade and counts from the graded corners."""
    report["corners"] = corners
    report["passed"] = sum(1 for c in corners if c.get("status") == "pass")
    report["failed"] = sum(1 for c in corners if c.get("status") == "fail")
    report["errored"] = sum(1 for c in corners if c.get("status") == "error")
    report["corner_count"] = len(corners)
    report["status"] = "fail" if report["failed"] else ("error" if report["errored"] else "pass")
    return report


def enrich(report: dict, bench: str) -> dict:
    if bench == LADDER_BENCH:
        corners = report.get("corners", [])
        cwd = Path.cwd()
        for corner in corners:
            if corner.get("status") == "pass":
                _enrich_ladder_corner(corner, cwd)
        return _recount(report, corners)
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
    return _recount(report, corners)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--bench", required=True, choices=sorted({*BENCHES, LADDER_BENCH}))
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
