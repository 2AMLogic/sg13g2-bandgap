#!/usr/bin/env python3
"""Signoff-manifest freshness and verdict-of-record checker for sg13g2-bandgap.

    python3 .github/scripts/check_signoff_manifest.py
    python3 .github/scripts/check_signoff_manifest.py --root DIR --klt BIN

`manifests/README.md` is the authoritative convention; this script is its
enforcement. It re-runs `klt signoff --manifest` over the committed block
manifest (read-only grading of committed envelope JSON — it never runs the
PDK, klayout, ngspice, and never mints evidence) and requires:

1. the grade itself succeeds — exit 0 (tier T1) and exit 3 (graded, not
   yet T1) are both valid verdicts; only a crash, exit 1, or exit 4
   (`refused`) fails;
2. the committed `<manifest-stem>.signoff.json` report is structurally
   identical to the fresh output — a committed verdict that no longer
   matches what the manifest + cited envelopes grade to today has rotted,
   and rot fails rather than passing silently;
3. every evidence entry that pins a `content_hash` is fresh three ways:
   the cited envelope parses, its recorded
   `provenance.input.content_hash` equals the manifest's pin, and the
   sha256 of the artifact that envelope names (its top-level `file` field,
   resolved next to the envelope) still equals that same hash — so a
   manifest citing an artifact that has since changed (a regenerated GDS
   without a re-run report) fails.

Entries cited without a pin are noted, not failed: `klt lvs` envelopes
record no `provenance.input` block (upstream JSON contract), so an LVS
citation cannot pin; its freshness is enforced by
`check_evidence_formats.py`'s layout-report staleness gate instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

#: `klt signoff --manifest` exit codes that are valid grades (see
#: klayout_tools/cli/signoff_cmd.py: 0 = tier T1, 3 = graded, not-T1).
VALID_GRADE_EXITS = {0, 3}


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []
        self.checked = 0

    def problem(self, msg: str) -> None:
        print(f"::error::{msg}")
        self.problems.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run_grade(klt: str, root: Path, manifest: Path) -> tuple[int, Any]:
    """Run `klt signoff --manifest <manifest> --format json` from root."""
    proc = subprocess.run(
        [klt, "signoff", "--manifest", str(manifest), "--format", "json"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


def first_difference(fresh: Any, committed: Any, path: str = "$") -> str:
    """Locate the first structural difference between two parsed reports."""
    if type(fresh) is not type(committed):
        return f"{path}: type {type(committed).__name__} != fresh {type(fresh).__name__}"
    if isinstance(fresh, dict):
        for key in sorted(set(fresh) | set(committed)):
            if key not in committed:
                return f"{path}.{key}: present in fresh grade, missing from committed report"
            if key not in fresh:
                return f"{path}.{key}: present in committed report, missing from fresh grade"
            sub = first_difference(fresh[key], committed[key], f"{path}.{key}")
            if sub:
                return sub
        return ""
    if isinstance(fresh, list):
        if len(fresh) != len(committed):
            return f"{path}: length {len(committed)} != fresh {len(fresh)}"
        for i, (a, b) in enumerate(zip(fresh, committed)):
            sub = first_difference(a, b, f"{path}[{i}]")
            if sub:
                return sub
        return ""
    if fresh != committed:
        return f"{path}: committed {committed!r} != fresh {fresh!r}"
    return ""


def _check_entry(root: Path, label: str, entry: Any, report: Report) -> None:
    """Validate one evidence entry: a path string or {file, content_hash?}."""
    if isinstance(entry, str):
        file_rel, pin = entry, None
    elif isinstance(entry, dict) and isinstance(entry.get("file"), str):
        file_rel, pin = entry["file"], entry.get("content_hash")
    else:
        report.problem(f"{label}: entry must be a path string or {{file, content_hash?}}")
        return
    envelope_path = root / file_rel
    if not envelope_path.is_file():
        report.problem(f"{label}: cited envelope {file_rel} does not exist")
        return
    try:
        envelope = json.loads(envelope_path.read_text())
    except json.JSONDecodeError as exc:
        report.problem(f"{label}: cited envelope {file_rel} is not valid JSON: {exc}")
        return
    if pin is None:
        report.note(
            f"{label}: cited without a content_hash pin (envelope status "
            f"{envelope.get('status')!r}) — freshness enforced by "
            "check_evidence_formats.py instead"
        )
        return
    recorded = (envelope.get("provenance") or {}).get("input", {}) or {}
    actual_pin = recorded.get("content_hash")
    if actual_pin != pin:
        report.problem(
            f"{label}: pinned content_hash {pin} != envelope's recorded "
            f"provenance.input.content_hash {actual_pin}"
        )
        return
    named = envelope.get("file")
    if not isinstance(named, str) or not named:
        report.problem(
            f"{label}: envelope {file_rel} names no input 'file' to freshness-check"
        )
        return
    artifact = (envelope_path.parent / named).resolve()
    if not artifact.is_file():
        # Some verbs record the input as a repo-rooted path (e.g. `klt erc`
        # names the GDS it graded as `layout/<cell>/<cell>.gds`), not a
        # sibling of the envelope. Try that reading before declaring the
        # pinned citation dangling.
        rooted = (root / named).resolve()
        if rooted.is_file():
            artifact = rooted
    try:
        artifact_hash = sha256_file(artifact)
    except (OSError, FileNotFoundError):
        report.problem(
            f"{label}: envelope's input artifact {artifact} does not exist — "
            "the pinned citation has nothing fresh to point at"
        )
        return
    if artifact_hash != pin:
        report.problem(
            f"{label}: STALE — artifact {artifact} now hashes to {artifact_hash}, "
            f"but the citation (and its envelope) pin {pin}; re-run the check "
            "that produces this envelope and update both, or the manifest is "
            "citing an artifact revision that no longer exists"
        )
        return
    report.checked += 1


def check_citations(root: Path, manifest_path: Path, manifest: dict, report: Report) -> None:
    evidence = manifest.get("evidence", {})
    if not isinstance(evidence, dict):
        report.problem(f"manifest {manifest_path}: 'evidence' must be a JSON object")
        return
    for item_id, entry in sorted(evidence.items(), key=lambda kv: int(kv[0])):
        # Upstream `klt signoff` grades item 11 ("Power delivery
        # (structural)", klayout-tools#2025) through a compound citation: a
        # LIST of ordinary entries, each resolved by the same machinery a
        # single entry uses. Accept that shape here so the freshness gate
        # covers every element of the compound, not just single entries.
        if isinstance(entry, list):
            if not entry:
                report.problem(
                    f"manifest evidence['{item_id}']: empty citation list — "
                    "citing nothing is the uncited case, not a compound citation"
                )
                continue
            for i, element in enumerate(entry):
                _check_entry(root, f"manifest evidence['{item_id}'][{i}]", element, report)
        else:
            _check_entry(root, f"manifest evidence['{item_id}']", entry, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    parser.add_argument("--manifest", default=None, help="block manifest (default: auto-detect)")
    parser.add_argument("--klt", default="klt", help="klt binary (default: PATH; $KLT_BIN overrides)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    klt = args.klt if args.klt != "klt" else (__import__("os").environ.get("KLT_BIN") or "klt")

    manifests_dir = root / "manifests"
    manifest_paths = (
        [Path(args.manifest).resolve()]
        if args.manifest
        else sorted(manifests_dir.glob("*.json"))
    )
    manifest_paths = [
        p for p in manifest_paths if not p.name.endswith(".signoff.json")
    ]
    if not manifest_paths:
        print(f"::error::no block manifest found under {manifests_dir}")
        return 1

    report = Report()
    for manifest_path in manifest_paths:
        report_path = manifest_path.with_name(manifest_path.stem + ".signoff.json")
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            report.problem(f"{manifest_path.name}: unreadable manifest: {exc}")
            continue
        for field in ("block", "kind"):
            if not manifest.get(field):
                report.problem(f"{manifest_path.name}: required field '{field}' missing")

        rc, stdout = run_grade(klt, root, manifest_path)
        if rc not in VALID_GRADE_EXITS:
            report.problem(
                f"{manifest_path.name}: klt signoff exited {rc} (expected 0 or 3) — "
                "the grade itself failed"
            )
            continue
        try:
            fresh = json.loads(stdout)
        except json.JSONDecodeError as exc:
            report.problem(f"{manifest_path.name}: klt stdout is not valid JSON: {exc}")
            continue

        if not report_path.is_file():
            report.problem(
                f"{manifest_path.name}: no committed verdict-of-record at {report_path.name} — "
                "run klt signoff and commit its output next to the manifest"
            )
            continue
        try:
            committed = json.loads(report_path.read_text())
        except json.JSONDecodeError as exc:
            report.problem(f"{report_path.name}: committed report is not valid JSON: {exc}")
            continue
        diff = first_difference(fresh, committed)
        if diff:
            report.problem(
                f"{report_path.name}: ROTTED — committed verdict of record no longer "
                f"matches a fresh grade (first difference at {diff}). Re-run "
                f"`klt signoff --manifest {manifest_path.relative_to(root)} --format json` "
                "and commit the new report."
            )
            continue
        check_citations(root, manifest_path, manifest, report)
        report.note(
            f"{manifest_path.name}: verdict of record current "
            f"(tier={committed.get('tier')}, T1 {committed.get('t1_met_count')}/"
            f"{committed.get('t1_item_count')} met)"
        )

    for note in report.notes:
        print(f"note: {note}")

    if report.problems:
        print(f"\n{len(report.problems)} signoff-manifest problem(s):", file=sys.stderr)
        for problem in report.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"OK: {report.checked} pinned citation(s) fresh, verdict of record current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
