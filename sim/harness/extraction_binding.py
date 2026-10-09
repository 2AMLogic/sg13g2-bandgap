#!/usr/bin/env python3
"""Capture and publish the extraction sources a PEX simulation consumed (#309).

A PEX bench is generated from committed extraction netlists
(`layout/**/*.pex.spice`) and, for benches that splice blocks, from further
netlists (`design/**`). Schematic device signatures cannot see a changed wire
resistor or coupling capacitor, so a record must carry the content hashes of
the exact files its bench was generated from. This module owns the mechanics,
shared by the two ends of the pipeline:

* **Bench generation** (`sim/tools/gen_pex_netlist_body.py --sources-out F`)
  calls :func:`capture`, which reads each source *once*, hashes those very
  bytes, and returns them for the generator to consume -- so the hash always
  describes the bytes the bench was built from. :func:`assert_unchanged`
  re-hashes afterwards and rejects a source that moved while the bench was
  being generated.
* **Publication** (`klt_sim_evidence.py --extraction-sources F ...`) loads the
  captured JSON, re-verifies every file still hashes to what was captured
  (:func:`verify_captured`) and only then writes the record's
  `- **Extraction sources**:` field (:func:`record_field_lines`).

Nothing here ever hashes "today's" file on behalf of an older run: the only
way to obtain a binding is to capture it at generation time and carry it
through to publication unchanged.

The CI side of the contract (`.github/scripts/check_evidence_formats.py`)
re-implements the same small grammar on purpose: that checker is stdlib-only
and must not import from `sim/`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "extraction-sources/1"
FIELD_NAME = "Extraction sources"


class BindingError(Exception):
    """A source is missing, escapes the repo, or changed since capture."""


def rel_path(path: Path, repo_root: Path) -> str:
    """Repo-relative POSIX path of `path`; reject anything outside the repo."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        raise BindingError(f"extraction source {path} is outside the repository") from None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(paths: list[Path], repo_root: Path) -> tuple[list[dict], dict[str, bytes]]:
    """Read every source once. Returns `(entries, {rel path: bytes read})`."""
    if not paths:
        raise BindingError("no extraction sources to bind")
    entries: list[dict] = []
    blobs: dict[str, bytes] = {}
    for path in paths:
        rel = rel_path(path, repo_root)
        if rel in blobs:
            continue
        if not path.is_file():
            raise BindingError(f"extraction source {rel} does not exist")
        data = path.read_bytes()
        blobs[rel] = data
        entries.append({"path": rel, "sha256": sha256_bytes(data)})
    return entries, blobs


def assert_unchanged(entries: list[dict], repo_root: Path) -> None:
    """Raise if any captured source no longer hashes to its captured digest."""
    for entry in entries:
        path = repo_root / entry["path"]
        if not path.is_file():
            raise BindingError(f"extraction source {entry['path']} disappeared")
        if sha256_bytes(path.read_bytes()) != entry["sha256"]:
            raise BindingError(
                f"extraction source {entry['path']} changed after its hash was captured"
                " -- regenerate the bench and re-run"
            )


def write_captured(entries: list[dict], out: Path) -> None:
    out.write_text(
        json.dumps({"schema": SCHEMA, "sources": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_captured(files: list[Path], repo_root: Path) -> list[dict]:
    """Merge captured-source JSON files; validate shape, paths and digests."""
    merged: dict[str, str] = {}
    for file in files:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BindingError(f"{file}: unreadable captured sources ({exc})") from None
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
            raise BindingError(f"{file}: not an {SCHEMA} document")
        for entry in raw.get("sources") or []:
            path = str(entry.get("path", ""))
            digest = str(entry.get("sha256", ""))
            parts = Path(path).parts
            if not path or Path(path).is_absolute() or ".." in parts:
                raise BindingError(f"{file}: bad extraction source path {path!r}")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise BindingError(f"{file}: malformed sha256 for {path}")
            if merged.get(path, digest) != digest:
                raise BindingError(f"{path}: captured with two different hashes")
            merged[path] = digest
    if not merged:
        raise BindingError("captured extraction sources are empty")
    entries = [{"path": p, "sha256": h} for p, h in sorted(merged.items())]
    return entries


def verify_captured(entries: list[dict], repo_root: Path) -> None:
    """Publication-time gate: every bound source still matches its capture."""
    assert_unchanged(entries, repo_root)


def record_field_lines(entries: list[dict]) -> list[str]:
    """Markdown for the record's `Extraction sources` field."""
    lines = [
        f"- **{FIELD_NAME}**: content hashes captured when the bench was generated"
        " (issue #309); `check_evidence_formats.py` re-verifies them against the"
        " committed files."
    ]
    for entry in entries:
        lines.append(f"  - `{entry['path']}` sha256:{entry['sha256']}")
    return lines
