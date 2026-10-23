#!/usr/bin/env python3
"""Stored-evidence manifests: schema guard (issue #379, DR-0015).

New `klt sim` evidence no longer lands in git. Its raw bytes go to the fleet
artifact store through `klt artifact put` (`sim/harness/evidence_store.py`);
git keeps one manifest per run, `manifests/artifacts/<bench>-<run-id>.manifest.json`,
plus the run's Markdown/CSV record under `sim/<bench>/records/`. Evidence bytes
are private and manifests are public. This script is the git-side check of that
contract. It reads the committed tree and fails if

* a manifest is malformed: wrong schema, an unknown or missing field, a `uri`
  that is not the logical `artifact:<key>` (an `s3://` bucket uri or any other
  scheme is refused), a key that does not end in the entry's sha256, a `name`
  that is not a canonical `sim/<bench>/...` path of the manifest's own bench
  and run, or a duplicate name;
* a stored object's bytes are also committed: an entry `name` that is a
  tracked path, or any tracked path under the git-ignored scratch directory
  `.evidence-scratch/` where a new run's raw outputs are staged -- the point of
  a manifest is that the bytes are *not* in git, so a blob beside its own
  manifest is the fallback DR-0015 forbids;
* a file under `manifests/` names a storage location (`s3://`, `arn:aws:`);
* `manifests/artifacts/` holds anything but manifests and its README.

It never contacts the broker: schema-valid is not hash-verified. Verify the
bytes with `klt artifact verify <manifest>` from a fleet worker.

Usage: python3 .github/scripts/check_artifact_manifests.py [--root DIR]
Exit status: 0 ok, 1 a problem was found (all printed), 2 git failure.
Stdlib only; needs `git` on PATH.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

MANIFEST_DIR = "manifests/artifacts/"
README = "manifests/artifacts/README.md"
MANIFEST_RE = re.compile(
    r"^manifests/artifacts/(?P<bench>[A-Za-z0-9][A-Za-z0-9._-]*?)-"
    r"(?P<rid>\d{8}-\d{6}-[0-9a-f]{7,40})\.manifest\.json$"
)
SCRATCH_PREFIX = ".evidence-scratch/"

SCHEMA_VERSION = 1
KIND = "evidence"
REQUIRED = ("sha256", "size", "kind", "producer", "uri", "name")
OPTIONAL = ("media_type",)
PRODUCER_FIELDS = ("tool", "version", "loom.repo", "commit")

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
#: The logical uri only the broker resolves; it names no storage location.
URI_RE = re.compile(r"^artifact:([^/\s]\S*)$")
STORAGE_RE = re.compile(r"s3://|arn:aws:")


def canonical_name(name, bench: str, rid: str) -> bool:
    if not (isinstance(name, str) and "\\" not in name and "\0" not in name
            and posixpath.normpath(name) == name):
        return False
    parts = name.split("/")
    return (len(parts) == 5 and parts[0] == "sim" and parts[1] == bench
            and parts[2] in ("corners", "netlist-snapshots") and parts[3] == rid
            and parts[4] not in ("", ".", ".."))


def entry_problems(entry, bench: str, rid: str) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    problems = []
    missing = [f for f in REQUIRED if f not in entry]
    extra = sorted(set(entry) - set(REQUIRED) - set(OPTIONAL))
    if missing:
        problems.append(f"missing {', '.join(missing)}")
    if extra:
        problems.append(f"unknown field(s) {', '.join(extra)}")
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        problems.append("sha256 must be 64 lowercase hex digits")
    size = entry.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        problems.append("size must be a positive integer")
    if entry.get("kind") != KIND:
        problems.append(f"kind must be {KIND!r}")
    producer = entry.get("producer")
    if not isinstance(producer, dict) or set(producer) != set(PRODUCER_FIELDS):
        problems.append(f"producer must carry exactly {', '.join(PRODUCER_FIELDS)}")
    else:
        for f in ("tool", "version", "loom.repo"):
            if not isinstance(producer.get(f), str) or not producer[f]:
                problems.append(f"producer.{f} must be a non-empty string")
        if producer.get("commit") is not None and not isinstance(producer["commit"], str):
            problems.append("producer.commit must be a string or null")
    uri = entry.get("uri")
    m = URI_RE.match(uri) if isinstance(uri, str) else None
    if m is None:
        problems.append("uri must be artifact:<key> (no other scheme)")
    elif isinstance(sha, str) and m.group(1).rsplit("/", 1)[-1] != sha:
        problems.append("uri key does not end in the entry's sha256")
    if "name" in entry and not canonical_name(entry["name"], bench, rid):
        problems.append(
            f"name must be sim/{bench}/(corners|netlist-snapshots)/{rid}/<file>")
    if "media_type" in entry and not isinstance(entry["media_type"], str):
        problems.append("media_type must be a string")
    return problems


def manifest_problems(manifest, bench: str, rid: str) -> list[str]:
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "entries"}
            or manifest.get("schema_version") != SCHEMA_VERSION
            or not isinstance(manifest.get("entries"), list)):
        return [f"not {{schema_version: {SCHEMA_VERSION}, entries: [...]}}"]
    if not manifest["entries"]:
        return ["has no entries"]
    problems = []
    seen = set()
    for i, entry in enumerate(manifest["entries"]):
        problems += [f"entry {i}: {p}" for p in entry_problems(entry, bench, rid)]
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str):
            if name in seen:
                problems.append(f"entry {i}: duplicate name {name!r}")
            seen.add(name)
    return problems


def tracked_files(root: Path) -> list[str]:
    try:
        proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                              capture_output=True, check=False)
    except OSError as exc:
        raise SystemExit(f"check_artifact_manifests.py: cannot run git: {exc}") from None
    if proc.returncode != 0:
        print(f"check_artifact_manifests.py: git ls-files failed: "
              f"{proc.stderr.decode('utf-8', 'replace').strip()}", file=sys.stderr)
        raise SystemExit(2)
    return [p.decode("utf-8", "surrogateescape") for p in proc.stdout.split(b"\0") if p]


def check(root: Path) -> tuple[list[str], int, int]:
    """Return `(problems, manifest_count, entry_count)` for the tracked tree."""
    tracked = tracked_files(root)
    tracked_set = set(tracked)
    problems: list[str] = []
    manifests = entries = 0

    for path in tracked:
        if path.startswith(SCRATCH_PREFIX):
            problems.append(f"{path}: the scratch directory {SCRATCH_PREFIX} holds a new run's "
                            "raw outputs and must never be committed")
    for path in tracked:
        if not path.startswith("manifests/") or not (root / path).is_file():
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable files cannot name a bucket in text
        if STORAGE_RE.search(text):
            problems.append(f"{path}: names a storage location (s3:// or arn:aws:); a manifest "
                            "carries logical artifact: uris only")

    for path in sorted(p for p in tracked if p.startswith(MANIFEST_DIR)):
        if path == README:
            continue
        m = MANIFEST_RE.match(path)
        full = root / path
        if m is None or full.is_symlink():
            problems.append(f"{path}: only <bench>-<run-id>.manifest.json files (and README.md) "
                            "belong in manifests/artifacts/")
            continue
        try:
            manifest = json.loads(full.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: not valid JSON: {exc}")
            continue
        found = manifest_problems(manifest, m.group("bench"), m.group("rid"))
        problems += [f"{path}: {p}" for p in found]
        if found:
            continue
        manifests += 1
        for entry in manifest["entries"]:
            entries += 1
            if entry["name"] in tracked_set:
                problems.append(
                    f"{path}: {entry['name']} is committed in the tree; stored evidence bytes "
                    "must not also be committed (no blob fallback)")
    return problems, manifests, entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    problems, manifests, entries = check(root)
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        print(f"FAIL: {len(problems)} problem(s) in the artifact manifests under {root}",
              file=sys.stderr)
        return 1
    print(f"OK: {manifests} artifact manifest(s), {entries} stored object(s) checked "
          "(schema only; run `klt artifact verify` to check the bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
