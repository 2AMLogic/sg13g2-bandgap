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

Every merge must state the grid it was asked for (`--expect-process`,
`--expect-supplies`, `--expect-temps`, or `--expect-grid FILE` for a smaller
or irregular campaign). Shards are validated first (empty shard, unknown
status, duplicate ids, inconsistent counts) and the merged identities are
compared with the expected grid; any problem aborts with named diagnostics
before the output file is written. `--allow-incomplete` instead writes a
`status=incomplete` diagnostic report that `klt_sim_evidence.py` refuses.
A shard whose corners carry no supply axis (PWL-ramp benches) is declared
with its supply: `label@2.97=path`.

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


KNOWN_STATUSES = ("pass", "fail", "error")


class ShardError(SystemExit):
    """Raised with every named diagnostic at once, before any file is written."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__(
            "merge_batch_shards: refusing to publish ("
            + str(len(problems))
            + " problem(s))\n  - "
            + "\n  - ".join(problems)
        )


def _relabel(report: dict, label: str) -> None:
    for corner in report.get("corners", []):
        cid = corner.get("corner_id", "")
        slash = cid.find("/")
        if slash > 0:
            corner["corner_id"] = f"{label}{cid[slash:]}"
        corner["process"] = label


def point_identity(corner: dict, supply_hint: float | None = None) -> str | None:
    """Normalized point identity, the same grammar as
    `klt_sim_evidence.corner_id` (`<process>_<temp>c_<vdd:.2f>v`).

    `supply_hint` stands in for a supply the corner does not carry (the
    PWL-ramp benches bake the supply into the body, so their shards carry no
    `supply_v` axis; the shard's declared supply identifies the point).
    Returns None when the point cannot be identified.
    """
    label = corner.get("process")
    temp = corner.get("temperature_c")
    if not label or not isinstance(temp, (int, float)) or isinstance(temp, bool):
        return None
    supplies = corner.get("supply_v") or {}
    if len(supplies) == 1:
        vdd = next(iter(supplies.values()))
    elif not supplies and supply_hint is not None:
        vdd = supply_hint
    else:
        return None
    if not isinstance(vdd, (int, float)) or isinstance(vdd, bool):
        return None
    return f"{label}_{temp:g}c_{vdd:.2f}v"


def validate_shard(report: object, name: str) -> list[str]:
    """Structural problems of one (already relabelled) shard report."""
    if not isinstance(report, dict):
        return [f"{name}: report is not a JSON object"]
    problems: list[str] = []
    status = report.get("status")
    if status not in KNOWN_STATUSES:
        problems.append(f"{name}: unknown report status {status!r} (expected one of {KNOWN_STATUSES})")
    corners = report.get("corners")
    if not isinstance(corners, list):
        return problems + [f"{name}: report has no 'corners' list"]
    if not corners:
        problems.append(
            f"{name}: empty shard (no corners; status={status!r}) -- a shard that returned "
            "no points is a failed run, never a pass"
        )
        return problems
    counts = {k: 0 for k in KNOWN_STATUSES}
    seen: set[str] = set()
    for i, corner in enumerate(corners):
        if not isinstance(corner, dict):
            problems.append(f"{name}: corner #{i} is not a JSON object")
            continue
        cid = corner.get("corner_id")
        if not isinstance(cid, str) or not cid:
            problems.append(f"{name}: corner #{i} has no corner_id")
            cid = f"#{i}"
        elif cid in seen:
            problems.append(f"{name}: duplicate corner_id {cid!r} within the shard")
        seen.add(cid)
        cs = corner.get("status")
        if cs in counts:
            counts[cs] += 1
        else:
            problems.append(
                f"{name}: corner {cid} has unknown status {cs!r} (expected one of {KNOWN_STATUSES})"
            )
    for key, label in (("passed", "pass"), ("failed", "fail"), ("errored", "error")):
        if key in report and report[key] != counts[label]:
            problems.append(
                f"{name}: inconsistent count: {key}={report[key]!r} but the corners hold {counts[label]}"
            )
    if "corner_count" in report and report["corner_count"] != len(corners):
        problems.append(
            f"{name}: inconsistent count: corner_count={report['corner_count']!r} "
            f"but the report holds {len(corners)} corner(s)"
        )
    if status in KNOWN_STATUSES:
        actual_clean = counts["fail"] == 0 and counts["error"] == 0 and sum(counts.values()) == len(corners)
        if (status == "pass") != actual_clean:
            problems.append(
                f"{name}: inconsistent status {status!r} for corners "
                f"pass={counts['pass']} fail={counts['fail']} error={counts['error']}"
            )
    return problems


def expected_from_axes(processes: list[str], supplies: list[float], temps: list[float]) -> list[str]:
    """Cartesian expected grid in this repo's normalized identity grammar."""
    return [f"{p}_{t:g}c_{v:.2f}v" for p in processes for v in supplies for t in temps]


def load_expected(path: str) -> list[str]:
    """`{"points": ["typ_27c_3.30v", ...]}` or `{"axes": {"process": [...],
    "supply_v": [...], "temperature_c": [...]}}` (or a bare list of points)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "axes" in data:
        ax = data["axes"]
        return expected_from_axes(ax["process"], ax["supply_v"], ax["temperature_c"])
    if isinstance(data, dict):
        data = data.get("points")
    if not isinstance(data, list) or not data or not all(isinstance(x, str) for x in data):
        raise SystemExit(f"merge_batch_shards: {path}: expected grid must be a non-empty list of point ids")
    return data


def check_grid(identities: list[str], expected: list[str], where: str) -> tuple[list[str], list[str], list[str]]:
    """(problems, missing, unexpected) of returned identities vs expected grid."""
    problems: list[str] = []
    if len(set(expected)) != len(expected):
        dup = sorted({x for x in expected if expected.count(x) > 1})
        problems.append(f"{where}: expected grid repeats point(s) {dup}")
    dups = sorted({x for x in identities if identities.count(x) > 1})
    if dups:
        problems.append(f"{where}: duplicate normalized point identities {dups}")
    missing = [x for x in dict.fromkeys(expected) if x not in set(identities)]
    unexpected = [x for x in dict.fromkeys(identities) if x not in set(expected)]
    if missing:
        problems.append(
            f"{where}: {len(missing)} requested point(s) missing (omitted shard or lost rows): {missing}"
        )
    if unexpected:
        problems.append(f"{where}: {len(unexpected)} returned point(s) not in the requested grid: {unexpected}")
    return problems, missing, unexpected


def merge(
    report_paths: list[str],
    expected: list[str] | None = None,
    allow_incomplete: bool = False,
) -> dict:
    if not report_paths:
        raise SystemExit("merge_batch_shards: no reports given")
    if not expected:
        raise SystemExit(
            "merge_batch_shards: no expected grid given -- a merged campaign must account for "
            "every requested point (pass --expect-process/--expect-supplies/--expect-temps or "
            "--expect-grid)"
        )
    reports = []
    hints: list[float | None] = []
    problems: list[str] = []
    for arg in report_paths:
        spec, path = arg.split("=", 1) if "=" in arg else (None, arg)
        label, _, sup = (spec or "").partition("@")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        if label and isinstance(report, dict):
            _relabel(report, label)
        problems.extend(validate_shard(report, Path(path).name))
        reports.append(report)
        hints.append(float(sup) if sup else None)
    if problems:
        raise ShardError(problems)
    merged = json.loads(json.dumps(reports[0]))  # deep copy of the first shape
    corners: list[dict] = []
    identities: list[str] = []
    fleet: list[dict | None] = []
    any_remote = False
    for arg, report, hint in zip(report_paths, reports, hints):
        for corner in report["corners"]:
            ident = point_identity(corner, hint)
            if ident is None:
                problems.append(
                    f"{arg}: corner {corner.get('corner_id')!r} has no identifiable "
                    "process/temperature/supply (give the shard its supply as label@vdd=path)"
                )
            else:
                identities.append(ident)
        corners.extend(report["corners"])
        remote = (report.get("environment") or {}).get("remote")
        fleet.append(remote)
        if remote is not None:
            any_remote = True
    if problems:
        raise ShardError(problems)
    grid_problems, missing, unexpected = check_grid(identities, expected, "merged grid")
    dup_problems = [p for p in grid_problems if "duplicate" in p or "repeats" in p]
    if dup_problems or (grid_problems and not allow_incomplete):
        raise ShardError(grid_problems)
    passed = sum(1 for c in corners if c.get("status") == "pass")
    failed = sum(1 for c in corners if c.get("status") == "fail")
    errored = sum(1 for c in corners if c.get("status") == "error")
    if failed:
        status = "fail"
    elif errored:
        status = "error"
    else:
        status = "pass"
    complete = not (missing or unexpected)
    if not complete:
        status = "incomplete"
    merged["corners"] = corners
    merged["corner_count"] = len(corners)
    merged["passed"] = passed
    merged["failed"] = failed
    merged["errored"] = errored
    merged["status"] = status
    merged["grid"] = {
        "expected": list(expected),
        "complete": complete,
        "missing": missing,
        "unexpected": unexpected,
    }
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


def _csv(kind):
    def parse(text: str) -> list:
        return [kind(x) for x in text.split(",") if x != ""]

    return parse


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--expect-grid", metavar="JSON", help="expected-grid file (points or axes)")
    ap.add_argument("--expect-process", type=_csv(str), help="expected repo corner labels, comma-separated")
    ap.add_argument("--expect-supplies", type=_csv(float), help="expected supplies (V), comma-separated")
    ap.add_argument("--expect-temps", type=_csv(float), help="expected temperatures (C), comma-separated")
    ap.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="write a missing/unexpected-point grid as an explicitly incomplete "
        "(status=incomplete) diagnostic report that the adapter will not publish",
    )
    ap.add_argument("reports", nargs="+", type=str)
    args = ap.parse_args(argv)
    axes = (args.expect_process, args.expect_supplies, args.expect_temps)
    if args.expect_grid:
        expected = load_expected(args.expect_grid)
    elif all(axes):
        expected = expected_from_axes(*axes)
    else:
        ap.error("an expected grid is required: --expect-grid, or all of --expect-process/--expect-supplies/--expect-temps (comma-separated)")
    merged = merge(args.reports, expected, args.allow_incomplete)
    args.output.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
