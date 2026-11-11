#!/usr/bin/env python3
"""Self-test for `check_selftests_wired.py`.

    python3 .github/scripts/test_check_selftests_wired.py

Hermetic: each case builds a throwaway git repo in a temp dir and runs the
checker as a subprocess. Stdlib only; needs `git`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_selftests_wired.py"


def run_case(files: list[str], workflow: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        subprocess.run(["git", "-C", d, "init", "-q"], check=True)
        wf = root / ".github/workflows/hygiene.yml"
        wf.parent.mkdir(parents=True)
        wf.write_text(workflow)
        for f in files:
            p = root / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("")
        subprocess.run(["git", "-C", d, "add", "-A", "-f"], check=True)
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", d], capture_output=True, text=True
        )


class WiredGuard(unittest.TestCase):
    def test_wired_passes(self):
        r = run_case(["a/test_x.py"], "run: python3 a/test_x.py\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_unwired_fails_and_names_file(self):
        r = run_case(["a/test_x.py", "b/test_y.py"], "run: python3 a/test_x.py\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("b/test_y.py", r.stdout)
        self.assertNotIn("a/test_x.py", r.stdout)

    def test_nested_path_detected(self):
        r = run_case(["p/q/r/test_deep.py"], "run: echo nothing\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("p/q/r/test_deep.py", r.stdout)

    def test_same_basename_does_not_mask(self):
        r = run_case(["a/test_x.py", "b/test_x.py"], "run: python3 a/test_x.py\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("b/test_x.py", r.stdout)

    def test_path_suffix_does_not_mask(self):
        # `xa/test_x.py` in the workflow must not satisfy `a/test_x.py`.
        r = run_case(["a/test_x.py"], "run: python3 xa/test_x.py\n")
        self.assertEqual(r.returncode, 1)

    def test_non_test_files_ignored(self):
        r = run_case(["a/helper.py", "a/testy.py"], "run: true\n")
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
