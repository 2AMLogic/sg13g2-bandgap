#!/usr/bin/env python3
"""Spot-check output drift gate for the characterization reports.

    python3 .github/scripts/check_spotcheck_outputs.py
    python3 .github/scripts/check_spotcheck_outputs.py --root DIR

Issue #516. Each `measurements/*-characterization-report/` commits, in its
README.md's `## Reproducing the spot-check` section, the stdout of its own
`spotcheck.py` as the evidence that the numbers the report quotes match the
committed CSVs. Nothing else re-ran it: an edit to the shared
`measurements/lib/spotcheck_common.py`, a CSV re-mint or a record repoint
could silently drift a committed block — worst in the historical reports
nobody re-reads — while CI stayed green.

This gate re-derives every block. For each report directory that has a
`spotcheck.py` it runs `python3 -I spotcheck.py` with the repository root as
cwd (exactly the command the README documents; the scripts are stdlib-only
CSV readers, never a simulator) and requires the first ```text fence under
the section heading to match stdout line for line. Line endings and a
missing final newline are normalised on both sides — the block's content is
the evidence — but any changed line fails with a unified diff naming the
report. A missing section, a missing (or unclosed) fence and a non-zero
spotcheck exit each fail; a report directory without a `spotcheck.py` (the
2026-09 one predates the convention) is noted and skipped.

Re-derivation only: this gate never edits a README, never mints evidence and
never runs a simulator. When it fails the remedy is human, never automatic:
re-run the command the README shows, find out what moved, and re-record
honestly (a new dated report if the inputs moved under it — a silent block
edit is exactly the drift this gate exists to catch).
"""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from itertools import zip_longest
from pathlib import Path

from _ci_common import Report, add_root_arg, resolve_root

#: The README section that documents how to reproduce the committed block.
SECTION_HEADING = "## Reproducing the spot-check"

#: The fence the block is committed in; the ```sh command fence above it is
#: not evidence and is skipped.
FENCE_OPEN = "```text"
FENCE_CLOSE = "```"

SPOTCHECK_NAME = "spotcheck.py"

#: Per-report run cap: the real scripts are fast CSV readers; a hang is a
#: defect to surface, not a CI job to park.
RUN_TIMEOUT_S = 300


def extract_block(readme_text: str) -> "tuple[list[str] | None, str | None]":
    """Lines of the first ```text fence under the heading, or (None, why).

    The scan stops at the next markdown heading, so a ```text fence that
    belongs to a later section is never mistaken for the section's block.
    """
    lines = readme_text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip() == SECTION_HEADING), None
    )
    if start is None:
        return None, f"no '{SECTION_HEADING}' section"
    fence = next(
        (i for i in range(start + 1, len(lines))
         if lines[i].lstrip().startswith("#") or lines[i].strip() == FENCE_OPEN),
        None,
    )
    if fence is None or lines[fence].strip() != FENCE_OPEN:
        return None, f"no '{FENCE_OPEN}' fence under '{SECTION_HEADING}'"
    end = next(
        (i for i in range(fence + 1, len(lines)) if lines[i].strip() == FENCE_CLOSE),
        None,
    )
    if end is None:
        return None, f"the '{FENCE_OPEN}' fence under '{SECTION_HEADING}' is never closed"
    return lines[fence + 1:end], None


def run_spotcheck(root: Path, report_dir: Path,
                  report: Report) -> "subprocess.CompletedProcess | None":
    """Run the report's spotcheck.py as its README documents; None on failure."""
    where = str(report_dir.relative_to(root))
    try:
        proc = subprocess.run(
            [sys.executable or "python3", "-I", str(report_dir / SPOTCHECK_NAME)],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        report.problem(
            f"{where}: spotcheck.py did not finish within {RUN_TIMEOUT_S}s — "
            "the committed output block cannot be re-derived"
        )
        return None
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        tail = f"; stderr: {stderr[-1]}" if stderr else ""
        report.problem(
            f"{where}: spotcheck.py exited {proc.returncode} — the committed "
            f"output block cannot be re-derived{tail}"
        )
        return None
    return proc


def check_report(root: Path, report_dir: Path, report: Report) -> None:
    where = str(report_dir.relative_to(root))
    proc = run_spotcheck(root, report_dir, report)
    if proc is None:
        return
    try:
        readme_text = (report_dir / "README.md").read_text(encoding="utf-8")
    except OSError as exc:
        report.problem(f"{where}: unreadable README.md: {exc}")
        return
    expected, why = extract_block(readme_text)
    if expected is None:
        report.problem(f"{where}/README.md: {why}")
        return
    actual = proc.stdout.splitlines()
    if expected != actual:
        changed = sum(1 for a, b in zip_longest(expected, actual) if a != b)
        print(f"\n{where}: committed spot-check block vs live spotcheck.py stdout:")
        for line in difflib.unified_diff(
            expected, actual,
            fromfile=f"{where}/README.md (committed block)",
            tofile=f"{where}/spotcheck.py (live stdout)",
            lineterm="",
        ):
            print(line)
        report.problem(
            f"{where}: committed spot-check output block DRIFTED from live "
            f"spotcheck.py stdout ({changed} of {len(expected)} line(s) differ; "
            "see diff above)"
        )
        return
    report.checked += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_root_arg(parser)
    args = parser.parse_args(argv)
    root = resolve_root(args)

    report = Report(annotate=True)
    report_dirs = sorted((root / "measurements").glob("*-characterization-report"))
    if not report_dirs:
        report.problem("measurements/: no *-characterization-report directories found")
    for report_dir in report_dirs:
        if not (report_dir / SPOTCHECK_NAME).is_file():
            report.note(f"measurements/{report_dir.name}: no spotcheck.py — skipped")
            continue
        check_report(root, report_dir, report)
    return report.finish(
        "spotcheck-output",
        f"OK: {report.checked} characterization report spot-check block(s) "
        "match live spotcheck.py stdout",
    )


if __name__ == "__main__":
    raise SystemExit(main())
