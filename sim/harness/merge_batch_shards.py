#!/usr/bin/env python3
"""Merge per-process `klt sim` batch reports into one grid-shaped report.

Issue #278. The batch runner image's request schema can carry only ONE
model library, and SG13G2's corner set spans three per-device-family files
(klayout-tools#2668, still open): a five-process grid therefore runs as
five `klt sim --backend batch` requests -- one per process corner, each
sweeping the temperature/supply axes natively -- and this module merges
those reports back into the single grid-shaped report
`klt_sim_evidence.py` consumes. It mirrors the deterministic shard-merge
contract `klt sim`'s own fleet sharding (`remote.hosts > 1`) applies one
level down: corners concatenate in the order the shards were declared,
never in completion order; the overall status/passed/failed/errored counts
are recomputed from the concatenated corners; `environment.remote` becomes
a `fleet[]` array with one entry per request when any request reported a
remote environment.

The merge is a pure JSON transform -- no re-grading, no re-measurement:
each corner keeps the measurements, status, diagnostics and artifact paths
its own report carries (the artifacts stay where their request's `-o`
directory put them; only the merged report references them).

Usage:

    python3 sim/harness/merge_batch_shards.py -o merged.json report-p.json ...

Corners concatenate in argument order -- pass the per-process reports in
`CORNER_LABELS` order (typ bcs wcs sf fs) so the merged CSV reads in the
grid order this repo's committed records use.

Each argument may carry the repo corner label it ran as, `label=path`
(e.g. `sf=report-sf.json`). The per-process bridge's requests name the
process by its HBT section, and `sf`/`fs` share `hbt_typ` with `typ`, so
the repo label is not recoverable from the report alone -- the label, when
given, rewrites every corner's `process` field and `corner_id` prefix back
to this repo's corner grammar before the adapter sees them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _relabel(report: dict, label: str) -> None:
    for corner in report.get("corners", []):
        cid = corner.get("corner_id", "")
        slash = cid.find("/")
        if slash > 0:
            corner["corner_id"] = f"{label}{cid[slash:]}"
        corner["process"] = label


def merge(report_paths: list[str]) -> dict:
    if not report_paths:
        raise SystemExit("merge_batch_shards: no reports given")
    reports = []
    for arg in report_paths:
        if "=" in arg:
            label, path = arg.split("=", 1)
            report = json.loads(Path(path).read_text(encoding="utf-8"))
            _relabel(report, label)
        else:
            report = json.loads(Path(arg).read_text(encoding="utf-8"))
        reports.append(report)
    merged = json.loads(json.dumps(reports[0]))  # deep copy of the first shape
    corners: list[dict] = []
    fleet: list[dict | None] = []
    any_remote = False
    for report in reports:
        corners.extend(report.get("corners", []))
        remote = (report.get("environment") or {}).get("remote")
        fleet.append(remote)
        if remote is not None:
            any_remote = True
    passed = sum(1 for c in corners if c.get("status") == "pass")
    failed = sum(1 for c in corners if c.get("status") == "fail")
    errored = sum(1 for c in corners if c.get("status") == "error")
    if failed:
        status = "fail"
    elif errored:
        status = "error"
    else:
        status = "pass"
    merged["corners"] = corners
    merged["corner_count"] = len(corners)
    merged["passed"] = passed
    merged["failed"] = failed
    merged["errored"] = errored
    merged["status"] = status
    merged.setdefault("environment", {})
    if any_remote:
        merged["environment"]["remote"] = {"fleet": fleet}
    prov = merged.setdefault("provenance", {})
    note = (
        "merged from %d per-process batch reports (issue #278 bridge: the "
        "runner image's single-models.lib request shape cannot vary the "
        "process within one request; klayout-tools#2668)"
        % len(reports)
    )
    if isinstance(prov, dict):
        prov["batch_shard_merge"] = note
    return merged


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("reports", nargs="+", type=str)
    args = ap.parse_args(argv)
    merged = merge(args.reports)
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
