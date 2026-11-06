#!/usr/bin/env python3
"""Fail if a tracked `test_*.py` self-test is not run by `hygiene.yml`.

    python3 .github/scripts/check_selftests_wired.py [--root DIR]

A committed self-test that no workflow step runs guards nothing: a regression
in the code it covers reaches `main` unseen. This lists every git-tracked
`test_*.py` (any depth) and requires its full repo-relative path to appear in
`.github/workflows/hygiene.yml`. Full-path match on purpose: a bare basename
would let `foo/test_x.py` mask an unwired `bar/test_x.py`.

Stdlib only; needs `git` on PATH. Exit 0 = all wired, 1 = orphan(s) found.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath

WORKFLOW = ".github/workflows/hygiene.yml"


def tracked_selftests(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    return sorted(
        p for p in out.split("\0")
        if p and PurePosixPath(p).name.startswith("test_") and p.endswith(".py")
    )


def find_unwired(tests: list[str], workflow_text: str) -> list[str]:
    """Tests whose full repo-relative path is not a token in the workflow."""
    wired = set()
    for line in workflow_text.splitlines():
        wired.update(line.replace("'", " ").replace('"', " ").split())
    return [t for t in tests if t not in wired]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = ap.parse_args(argv)
    wf = args.root / WORKFLOW
    if not wf.is_file():
        print(f"FAIL: {WORKFLOW} not found under {args.root}")
        return 1
    tests = tracked_selftests(args.root)
    unwired = find_unwired(tests, wf.read_text())
    for t in unwired:
        print(f"::error file={WORKFLOW}::self-test not run by hygiene.yml: {t}")
    if unwired:
        print(f"FAIL: {len(unwired)} of {len(tests)} tracked self-tests are not wired into {WORKFLOW}")
        return 1
    print(f"OK: all {len(tests)} tracked self-tests are wired into {WORKFLOW}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
