#!/usr/bin/env python3
"""Shared scaffolding for `.github/scripts`' CI evidence checkers.

Not an entry point itself — imported by `check_evidence_formats.py` and
`check_signoff_manifest.py`, which independently redefined the same `Report`
collector and `sha256_file()` helper before this module existed (issue #260).

The two call sites differ in exactly two ways, both preserved here rather
than papered over:

1. `check_signoff_manifest.py` wants each problem to also print immediately
   as a GitHub Actions inline annotation (``::error::<msg>``); construct
   `Report(annotate=True)` for that. `check_evidence_formats.py` defers
   everything to the end-of-run printout, so it uses the `Report()` default.
2. `sha256_file()` here adopts `check_evidence_formats.py`'s convention
   (streamed in 1 MiB chunks, bare hex digest, no `"sha256:"` prefix) since
   it has the larger number of call sites; `check_signoff_manifest.py`'s one
   call site prepends `"sha256:"` itself where it needs that form.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


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


def sha256_file(path: Path) -> str:
    """Return the bare hex sha256 digest of `path`, streamed in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
