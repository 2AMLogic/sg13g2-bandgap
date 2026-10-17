#!/usr/bin/env python3
"""Shared scaffolding for `.github/scripts`' CI evidence checkers.

Not an entry point itself -- imported by all four `check_*.py` checkers
(`check_evidence_formats`, `check_signoff_manifest`, `check_report_dependencies`,
`check_design_source_dependencies`), which independently redefined the same
`Report` collector, `sha256_file()` helper, manifest discovery and end-of-run
printout before this module existed (issues #260, #342).

What is shared:

- `Report` -- problem/note collector with an end-of-run `finish()` printout.
  `check_signoff_manifest.py` and the two dependency checkers construct
  `Report(annotate=True)` so each problem also prints immediately as a GitHub
  Actions inline annotation (``::error::<msg>``); `check_evidence_formats.py`
  defers everything to the end-of-run printout and uses the `Report()` default.
- `sha256_file()` -- bare hex digest, streamed in 1 MiB chunks;
  `sha256_prefixed()` -- the same with a `"sha256:"` prefix, the form the
  manifests' `content_hash` pins use.
- `SHA_PIN_RE` / `contained()` / `check_pin()` -- the manifests' `sha256:<hex>`
  pin format, repo-relative path containment, and the containment -> pin-format
  -> existence -> hash-match sequence the two dependency checkers share. Each
  checker words its own MISSING/CHANGED message from the returned kind.
- `add_manifest_args()` / `resolve_root()` / `discover_manifests()` -- the
  `--root`/`--manifest` options and block-manifest discovery shared by the
  three manifest-driven checkers.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

#: A manifest content-hash pin: lower-case hex digest with the `sha256:` prefix.
SHA_PIN_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class Report:
    """Collects problems and notes, printing each problem once at most.

    `check_evidence_formats.py` calls `fail(where, message)`, which joins the
    two into a single `"<where>: <message>"` string. `check_signoff_manifest.py`
    calls `problem(message)` with an already-composed message. Both funnel
    into the same underlying list; `annotate=True` additionally prints each
    one immediately as a `::error::` GitHub Actions annotation as it is
    added, which `check_signoff_manifest.py` relies on and
    `check_evidence_formats.py` does not.
    """

    def __init__(self, *, annotate: bool = False) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []
        self.checked = 0
        self.annotate = annotate

    def _add(self, message: str) -> None:
        if self.annotate:
            print(f"::error::{message}")
        self.problems.append(message)

    def fail(self, where: "str | Path", message: str) -> None:
        self._add(f"{where}: {message}")

    def problem(self, message: str) -> None:
        self._add(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def finish(self, label: str, ok_message: str) -> int:
        """Print notes, then either the problem block (stderr) or `ok_message`.

        Returns the process exit code (1 with problems, else 0).
        """
        for note in self.notes:
            print(f"note: {note}")
        if self.problems:
            print(f"\n{len(self.problems)} {label} problem(s):", file=sys.stderr)
            for problem in self.problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print(ok_message)
        return 0


def sha256_file(path: Path) -> str:
    """Return the bare hex sha256 digest of `path`, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_prefixed(path: Path) -> str:
    """Return `"sha256:" + sha256_file(path)`, the manifests' `content_hash` form."""
    return "sha256:" + sha256_file(path)


def contained(root: Path, rel: Any, what: str, report: Report, where: str) -> Path | None:
    """Resolve a repo-relative path, rejecting malformed/absolute/escaping ones."""
    if not isinstance(rel, str) or not rel.strip():
        report.problem(f"{where}: {what} must be a non-empty repository-relative path, got {rel!r}")
        return None
    if Path(rel).is_absolute():
        report.problem(f"{where}: {what} {rel!r} is absolute")
        return None
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        report.problem(f"{where}: {what} {rel!r} escapes the repository")
        return None
    return resolved


def check_pin(root: Path, rel: Any, pin: Any, what: str, report: Report,
              where: str) -> tuple[bool, str]:
    """Check a repo-relative file against its `sha256:` pin; return (ok, kind).

    `kind` is '' (matches), 'malformed' (bad path or pin; already reported),
    'missing' or 'changed'. The last two are NOT reported here: callers word
    their own message for them.
    """
    path = contained(root, rel, what, report, where)
    if path is None:
        return False, "malformed"
    if not isinstance(pin, str) or not SHA_PIN_RE.match(pin):
        report.problem(f"{where}: {what} {rel} has malformed sha256 {pin!r}")
        return False, "malformed"
    if not path.is_file():
        return False, "missing"
    if sha256_prefixed(path) != pin:
        return False, "changed"
    return True, ""


def add_manifest_args(parser: argparse.ArgumentParser) -> None:
    """Add the `--root` / `--manifest` options shared by the manifest checkers."""
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    parser.add_argument("--manifest", default=None, help="block manifest (default: auto-detect)")


def resolve_root(args: argparse.Namespace) -> Path:
    """Repo root from `--root`, else the repo containing `.github/scripts`."""
    return Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]


def discover_manifests(args: argparse.Namespace) -> "tuple[Path, list[Path]] | None":
    """Return `(root, block_manifest_paths)`, or None after printing an error.

    Uses `--manifest` if given, else `manifests/*.json`; `*.signoff.json`
    verdict-of-record files are never block manifests.
    """
    root = resolve_root(args)
    manifests_dir = root / "manifests"
    paths = (
        [Path(args.manifest).resolve()] if args.manifest else sorted(manifests_dir.glob("*.json"))
    )
    paths = [p for p in paths if not p.name.endswith(".signoff.json")]
    if not paths:
        print(f"::error::no block manifest found under {manifests_dir}")
        return None
    return root, paths
