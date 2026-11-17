#!/usr/bin/env python3
"""Self-test for `check_spotcheck_outputs.py`.

    python3 .github/scripts/test_check_spotcheck_outputs.py

Same discipline as `test_check_report_dependencies.py`: a checker that never
fails is indistinguishable from no checker at all. Each case builds a
synthetic `measurements/` tree in a temp directory — a report whose README
commits its `spotcheck.py` output block, plus a scriptless legacy neighbour —
introduces exactly one defect (or one change that must NOT fail) and asserts
the verdict and a specific message. Case 0 asserts the undamaged tree passes,
so each failure is attributable to the injected defect rather than the
fixture.

Black-box on purpose: the checker runs as a subprocess, as CI runs it.
Stdlib only, no PDK, no simulator, no network.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_spotcheck_outputs.py"

REPORT_DIR = "measurements/2026-01-01-characterization-report"
LEGACY_DIR = "measurements/2026-01-02-characterization-report"

#: What the fixture spotcheck.py prints, and what its README commits.
BLOCK = [
    "figure one: vref 1.04060..1.05052 V",
    "figure two: 45/45 PASS; worst bcs/125C/3.63V",
    "figure three: trim-MC 3*sigma(max_dev) 2.399%",
]

FAILING_PY = ("import sys\n"
              "sys.stderr.write('boom: committed csv missing\\n')\n"
              "sys.exit(1)\n")


def script_printing(lines: list[str]) -> str:
    """A spotcheck.py whose whole job is to print `lines`."""
    body = "for line in [\n" + "".join(f"    {l!r},\n" for l in lines) + "]:\n    print(line)\n"
    return body


SPOTCHECK_PY = script_printing(BLOCK)


def write(t: Path, rel: str, data: str) -> None:
    path = t / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8"))


def readme(block: list[str], *, section: bool = True, fence: bool = True,
           closed: bool = True, head_fence: bool = False,
           tail_fence: bool = False, eol: str = "\n",
           final_newline: bool = True) -> str:
    """A report README shape-matching the real ones, one knob per defect."""
    parts = ["# Fixture characterization report\n\n"]
    if head_fence:
        parts += ["An unrelated block quoted in the intro:\n\n",
                  "```text\nfigure zero: decoy\n```\n\n"]
    parts += ["Prose quoting the figures.\n\n"]
    if section:
        parts += ["## Reproducing the spot-check\n\n",
                  "```sh\n",
                  f"python3 -I {REPORT_DIR}/spotcheck.py\n",
                  "```\n\n",
                  "Output at the audited commit `00000000`:\n\n"]
        if fence:
            parts += ["```text\n"]
            parts += [line + "\n" for line in block]
            if closed:
                parts += ["```\n"]
        parts += ["\n"]
    parts += ["## Later section\n\nNothing quoted here.\n"]
    if tail_fence:
        parts += ["\n```text\nfigure nine: also a decoy\n```\n"]
    text = "".join(parts)
    if eol != "\n":
        text = text.replace("\n", eol)
    if not final_newline and text.endswith(eol):
        text = text[:-len(eol)]
    return text


def build(t: Path, *, readme_text: str | None = None,
          script: str = SPOTCHECK_PY) -> None:
    write(t, f"{REPORT_DIR}/spotcheck.py", script)
    write(t, f"{REPORT_DIR}/README.md", readme_text or readme(BLOCK))
    write(t, f"{LEGACY_DIR}/README.md", "# Legacy report\n\nNo spotcheck here.\n")


def run_checker(t: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), "--root", str(t)],
                          capture_output=True, text=True)


def expect(case: str, proc: subprocess.CompletedProcess, *,
           passes: bool, message_fragment: str) -> bool:
    ok = (proc.returncode == 0) == passes and message_fragment in (proc.stdout + proc.stderr)
    print(f"  {'ok  ' if ok else 'FAIL'} {case}")
    if not ok:
        print(f"       rc={proc.returncode}")
        print("       stdout:", proc.stdout.strip()[:600])
        print("       stderr:", proc.stderr.strip()[:600])
    return ok


def main() -> int:
    failures = 0

    def case(name: str, *, passes: bool, fragment: str,
             readme_text: str | None = None, script: str = SPOTCHECK_PY) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            build(t, readme_text=readme_text, script=script)
            failures += not expect(name, run_checker(t), passes=passes,
                                   message_fragment=fragment)

    case("case 0: undamaged tree passes", passes=True, fragment="OK:")
    case("case 0b: the scriptless legacy report is skipped with a note",
         passes=True, fragment="no spotcheck.py")

    # ---- the acceptance-criteria defect classes ----
    case("case 1: a drifted block digit fails, naming the report",
         passes=False,
         fragment=f"{REPORT_DIR}: committed spot-check output block DRIFTED",
         readme_text=readme([BLOCK[0], "figure two: 44/45 PASS; worst bcs/125C/3.63V",
                             BLOCK[2]]))
    case("case 2: a missing 'Reproducing the spot-check' section fails",
         passes=False, fragment="no '## Reproducing the spot-check' section",
         readme_text=readme(BLOCK, section=False))
    case("case 3: no ```text fence under the section fails (a later one does not count)",
         passes=False, fragment="no '```text' fence under",
         readme_text=readme(BLOCK, fence=False, tail_fence=True))
    case("case 4: an unclosed fence fails",
         passes=False, fragment="never closed",
         readme_text=readme(BLOCK, closed=False))
    case("case 5: a non-zero spotcheck exit fails",
         passes=False, fragment="spotcheck.py exited 1", script=FAILING_PY)
    case("case 5b: the non-zero exit surfaces the script's stderr",
         passes=False, fragment="boom: committed csv missing", script=FAILING_PY)

    # ---- differences that are NOT drift (line-ending / fence-scope noise) ----
    case("case 6: CRLF line endings in the README fence still match",
         passes=True, fragment="OK:", readme_text=readme(BLOCK, eol="\r\n"))
    case("case 7: a missing final newline after the fence still matches",
         passes=True, fragment="OK:", readme_text=readme(BLOCK, final_newline=False))
    case("case 8: decoy ```text fences outside the section are ignored",
         passes=True, fragment="OK:",
         readme_text=readme(BLOCK, head_fence=True, tail_fence=True))
    case("case 8b: a drift under the heading still fails with decoys present",
         passes=False, fragment="DRIFTED",
         readme_text=readme([BLOCK[0], "figure two: 44/45 PASS; worst bcs/125C/3.63V",
                             BLOCK[2]], head_fence=True, tail_fence=True))

    # ---- more ways a block and a script can disagree ----
    case("case 9: an extra stdout line the block does not have fails",
         passes=False, fragment="DRIFTED",
         script=script_printing(BLOCK + ["figure four: newly minted"]))
    case("case 10: a trailing-whitespace change inside a block line fails",
         passes=False, fragment="DRIFTED",
         readme_text=readme([BLOCK[0] + "  ", *BLOCK[1:]]))
    case("case 11: an empty fence against non-empty stdout fails",
         passes=False, fragment="DRIFTED", readme_text=readme([]))

    if failures:
        print(f"\n{failures} case(s) failed", file=sys.stderr)
        return 1
    print("OK: all spotcheck-output checker self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
