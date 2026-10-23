#!/usr/bin/env python3
"""Self-test for `check_artifact_manifests.py` (issue #379).

    python3 .github/scripts/test_check_artifact_manifests.py

Each case builds a throwaway git repo holding one valid stored-run manifest,
injects exactly one defect and asserts the checker rejects it with a specific
message; case 0 proves the undamaged repo passes. Black-box (subprocess), stdlib
only, no broker and no network.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_artifact_manifests.py"
BENCH = "demo"
RID = "20260101-000000-abcdef1"
NAME = f"sim/{BENCH}/corners/{RID}/typ_27c_3.30v.log"
MANIFEST = f"manifests/artifacts/{BENCH}-{RID}.manifest.json"


def entry(name: str = NAME, seed: str = "a") -> dict:
    sha = hashlib.sha256(seed.encode()).hexdigest()
    return {"sha256": sha, "size": 12, "kind": "evidence",
            "producer": {"tool": "klt", "version": "0.1", "loom.repo": "o/r", "commit": None},
            "uri": f"artifact:evidence/o__r/{sha[:2]}/{sha}", "name": name}


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_manifest(root: Path, entries: list[dict], rel: str = MANIFEST) -> None:
    write(root, rel, json.dumps({"schema_version": 1, "entries": entries}))


def build(root: Path) -> None:
    git(root, "init", "-q")
    write_manifest(root, [entry(), entry(f"sim/{BENCH}/netlist-snapshots/{RID}/typ_27c_3.30v.spice", "b")])
    write(root, "manifests/artifacts/README.md", "# manifests\n")
    write(root, f"sim/{BENCH}/records/{RID}.md", "# Record\n")


def mutate_entry(root: Path, **changes) -> None:
    path = root / MANIFEST
    doc = json.loads(path.read_text())
    doc["entries"][0].update(changes)
    path.write_text(json.dumps(doc))


def case_valid(_root):
    return None


def case_s3_uri(root):
    mutate_entry(root, uri="s3://bucket/evidence/x")
    return "uri must be artifact:<key>"


def case_other_scheme(root):
    mutate_entry(root, uri="https://example.invalid/x")
    return "uri must be artifact:<key>"


def case_uri_key_not_sha(root):
    mutate_entry(root, uri="artifact:evidence/o__r/zz/" + "0" * 64)
    return "uri key does not end in the entry's sha256"


def case_bad_sha(root):
    mutate_entry(root, sha256="XYZ")
    return "sha256 must be 64 lowercase hex digits"


def case_unknown_field(root):
    mutate_entry(root, bucket="b")
    return "unknown field(s) bucket"


def case_missing_field(root):
    path = root / MANIFEST
    doc = json.loads(path.read_text())
    del doc["entries"][0]["producer"]
    path.write_text(json.dumps(doc))
    return "missing producer"


def case_non_canonical_name(root):
    mutate_entry(root, name=f"sim/{BENCH}/corners/{RID}/../../x.log")
    return "name must be sim/"


def case_name_of_another_run(root):
    mutate_entry(root, name=f"sim/{BENCH}/corners/20250101-000000-abcdef1/x.log")
    return "name must be sim/"


def case_duplicate_name(root):
    write_manifest(root, [entry(), entry(seed="c")])
    return "duplicate name"


def case_no_entries(root):
    write_manifest(root, [])
    return "has no entries"


def case_not_json(root):
    write(root, MANIFEST, "{nope")
    return "not valid JSON"


def case_stray_file(root):
    write(root, "manifests/artifacts/notes.txt", "x")
    return "only <bench>-<run-id>.manifest.json"


def case_stored_bytes_also_committed(root):
    write(root, NAME, "the raw log\n")
    return "is committed in the tree"


def case_scratch_tracked(root):
    write(root, f".evidence-scratch/{BENCH}-{RID}/corners/a.log", "raw\n")
    return "scratch directory"


def case_bucket_in_manifests(root):
    write(root, "manifests/artifacts/README.md", "stored at s3://some-bucket/x\n")
    return "names a storage location"


def case_account_arn_in_manifests(root):
    write(root, "manifests/other.json", '{"role": "arn:aws:iam::123456789012:role/x"}\n')
    return "names a storage location"


CASES = [
    ("undamaged repo passes", case_valid),
    ("uri is an s3:// bucket uri", case_s3_uri),
    ("uri has another scheme", case_other_scheme),
    ("uri key does not end in the sha256", case_uri_key_not_sha),
    ("sha256 is malformed", case_bad_sha),
    ("entry carries an unknown field", case_unknown_field),
    ("entry misses a required field", case_missing_field),
    ("name is not canonical", case_non_canonical_name),
    ("name belongs to another run", case_name_of_another_run),
    ("duplicate entry name", case_duplicate_name),
    ("manifest has no entries", case_no_entries),
    ("manifest is not JSON", case_not_json),
    ("stray file in manifests/artifacts/", case_stray_file),
    ("a stored object's bytes are also committed", case_stored_bytes_also_committed),
    ("the scratch directory is tracked", case_scratch_tracked),
    ("a bucket uri in a manifests/ file", case_bucket_in_manifests),
    ("an AWS account arn in a manifests/ file", case_account_arn_in_manifests),
]


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for index, (name, mutate) in enumerate(CASES):
            root = Path(tmpdir) / f"case{index:02d}"
            root.mkdir()
            build(root)
            expected = mutate(root)
            git(root, "add", "-A", "-f")
            proc = subprocess.run([sys.executable, str(CHECKER), "--root", str(root)],
                                  capture_output=True, text=True, check=False)
            output = proc.stdout + proc.stderr
            if expected is None:
                ok = proc.returncode == 0
                detail = "" if ok else f"expected pass, got exit {proc.returncode}:\n{output}"
            else:
                ok = proc.returncode == 1 and expected in output
                detail = "" if ok else f"expected exit 1 with {expected!r}, got {proc.returncode}:\n{output}"
            print(f"  {'ok  ' if ok else 'FAIL'} {name}")
            if not ok:
                failures += 1
                print(detail, file=sys.stderr)
    if failures:
        print(f"\n{failures}/{len(CASES)} self-test case(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nOK: {len(CASES)}/{len(CASES)} self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
