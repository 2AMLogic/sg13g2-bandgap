#!/usr/bin/env python3
"""Stale-input checker for the actively cited item-1 design-source audit.

    python3 .github/scripts/check_design_source_dependencies.py
    python3 .github/scripts/check_design_source_dependencies.py --root DIR

`check_signoff_manifest.py` re-hashes `manifests/evidence/design-sources.txt`
(the hand-audited T1 item-1 inventory) and so catches an edited *attestation*.
It cannot notice that the schematics, symbols, netlists or export
configuration the attestation lists have since moved on (issue #324). This
script closes that gap. Stdlib-only and PDK-free: it hashes and globs
committed files; it never runs xschem, never simulates, never writes anything
and never mints or refreshes an attestation.

Which audit is checked. Only the one the block manifest **actively cites** for
item 1 (`manifests/<block>.json` -> `evidence["1"]` -> envelope -> `source`).
Its machine-readable dependency inventory is `<attestation stem>.inventory.json`
beside the attestation. An inventory beside a superseded attestation is a
historical snapshot: noted, never checked, never required to track the design.

What the inventory records, and what is checked:

1. `attestation` / `attestation_sha256` -- the attestation bytes the inventory
   was written for; they must still hash the same, so a regenerated
   attestation needs a re-written inventory.
2. `inputs[]` (`path`, `sha256`, `role`) -- audited schematic / symbol /
   netlist files. Each must exist and hash as recorded. They must also equal,
   path for path and hash for hash, the in-scope hash lines of the
   attestation text (everything before its "Not attested" section), so the
   inventory cannot drift from the hand-audited record.
3. `export_config[]` -- the export configuration the audited command used
   (`design/xschemrc`), hashed the same way.
4. `scope.include` -- non-recursive globs defining the attested source scope.
   A file matching one of them that the inventory does not list (a new cell)
   fails; a listed input that is gone (a deleted cell) fails. `scope.exclude`
   names path prefixes that are explicitly OUT of scope (the SG13CMOS5L
   variant): nothing under them is hashed, listed or glob-matched, so changes
   there never invalidate this audit and they never become attested implicitly.

Hash equality establishes only that the audited inputs are unchanged. It is
NOT a new proof that the committed netlists regenerate from the committed
schematics; only the deliberate, tool-requiring export audit (and the opt-in
`design/check_netlist_drift.sh`) establishes that.

Every path must be repository-relative and stay inside the repository.
Failures name the offending path. The remedy is always explicit and never
automatic: perform a fresh export audit, then update the attestation,
this inventory, the envelope, the manifest pin and the signoff verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from _ci_common import Report, sha256_file as _sha256_file_bare
from check_report_dependencies import contained

ITEM_ID = "1"
INVENTORY_SUFFIX = ".inventory.json"
SCHEMA_VERSION = 1
ROLES = {"schematic", "symbol", "netlist"}
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ATTEST_LINE_RE = re.compile(r"^([0-9a-f]{64})  (\S+)\s*$")
_NOT_ATTESTED_RE = re.compile(r"^## Not attested", re.MULTILINE)


def sha256_file(path: Path) -> str:
    return "sha256:" + _sha256_file_bare(path)


REMEDY = (
    "Remedy: this does NOT prove the export is wrong, only that the audit no longer "
    "describes the committed design. Perform a fresh explicit export audit (run the "
    "recorded xschem export, compare with design/netlist/*.spice; see "
    "design/check_netlist_drift.sh), then update the attestation, this inventory, "
    "the envelope, the manifest pin and the signoff verdict. Nothing refreshes "
    "these automatically."
)


def attested_hash_lines(text: str) -> dict[str, str]:
    """{path: sha256:<hex>} for the in-scope hash lines of the attestation."""
    m = _NOT_ATTESTED_RE.search(text)
    in_scope = text[: m.start()] if m else text
    out: dict[str, str] = {}
    for line in in_scope.splitlines():
        hit = _ATTEST_LINE_RE.match(line)
        if hit:
            out[hit.group(2)] = "sha256:" + hit.group(1)
    return out


def _under(rel: str, prefixes: list[str]) -> bool:
    return any(rel == p.rstrip("/") or rel.startswith(p.rstrip("/") + "/") for p in prefixes)


def _check_entry_hash(root: Path, entry: Any, what: str, where: str,
                      report: Report) -> tuple[str, str] | None:
    """Validate one {path, sha256} entry; return (path, pin) when well-formed."""
    if not isinstance(entry, dict):
        report.problem(f"{where}: must be an object {{path, sha256}}")
        return None
    path = contained(root, entry.get("path"), what, report, where)
    pin = entry.get("sha256")
    if path is None:
        return None
    if not isinstance(pin, str) or not _SHA_RE.match(pin):
        report.problem(f"{where}: {what} {entry['path']} has malformed sha256 {pin!r}")
        return None
    if not path.is_file():
        report.problem(
            f"{where}: MISSING AUDITED INPUT -- {what} {entry['path']} does not exist "
            f"(deleted or renamed since the audit). {REMEDY}"
        )
        return entry["path"], pin
    if sha256_file(path) != pin:
        report.problem(
            f"{where}: AUDITED INPUT CHANGED -- {what} {entry['path']} no longer hashes "
            f"to the audited {pin}. {REMEDY}"
        )
    else:
        report.checked += 1
    return entry["path"], pin


def check_inventory(root: Path, inv_path: Path, attest_path: Path, report: Report) -> None:
    where = str(inv_path.relative_to(root))
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.problem(f"{where}: not valid JSON: {exc}")
        return
    if not isinstance(inv, dict):
        report.problem(f"{where}: must be a JSON object")
        return
    if inv.get("schema_version") != SCHEMA_VERSION:
        report.problem(f"{where}: schema_version must be {SCHEMA_VERSION}, got {inv.get('schema_version')!r}")
        return
    for key, kind in (("inputs", list), ("export_config", list), ("scope", dict)):
        if not isinstance(inv.get(key), kind):
            report.problem(f"{where}: required field '{key}' missing or not a {kind.__name__}")
            return
    scope = inv["scope"]
    include, exclude = scope.get("include"), scope.get("exclude")
    for key, val in (("include", include), ("exclude", exclude)):
        if not isinstance(val, list) or not val or not all(isinstance(v, str) and v.strip() for v in val):
            report.problem(f"{where}: scope.{key} must be a non-empty list of strings")
            return
    if not inv["inputs"]:
        report.problem(f"{where}: inputs must not be empty")
        return

    # 1. the attestation this inventory was written for
    attest_rel = str(attest_path.relative_to(root))
    if inv.get("attestation") != attest_rel:
        report.problem(
            f"{where}: inventory is for attestation {inv.get('attestation')!r}, but the "
            f"actively cited attestation is {attest_rel}"
        )
        return
    actual = sha256_file(attest_path)
    if inv.get("attestation_sha256") != actual:
        report.problem(
            f"{where}: inventory was written for attestation bytes "
            f"{inv.get('attestation_sha256')} but {attest_rel} now hashes to {actual}; "
            "a changed attestation needs its inventory re-written"
        )

    # scope definition sanity: explicit, non-recursive, never reaching out of scope
    for i, prefix in enumerate(exclude):
        if contained(root, prefix.rstrip("/"), "scope.exclude entry", report,
                     f"{where}: scope.exclude[{i}]") is None:
            return
    for i, pattern in enumerate(include):
        w = f"{where}: scope.include[{i}]"
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            report.problem(f"{w}: {pattern!r} must be a repository-relative glob without '..'")
            return
        if "**" in pattern:
            report.problem(f"{w}: {pattern!r} is recursive; the attested scope must be explicit")
            return
        if _under(pattern, exclude):
            report.problem(f"{w}: {pattern!r} lies inside the declared out-of-scope paths")
            return

    # 2. audited inputs
    listed: dict[str, str] = {}
    for i, entry in enumerate(inv["inputs"]):
        w = f"{where}: inputs[{i}]"
        if isinstance(entry, dict) and entry.get("role") not in ROLES:
            report.problem(f"{w}: role must be one of {sorted(ROLES)}, got {entry.get('role')!r}")
            continue
        got = _check_entry_hash(root, entry, "design source", w, report)
        if got is None:
            continue
        if _under(got[0], exclude):
            report.problem(f"{w}: {got[0]} is inside the declared out-of-scope paths")
            continue
        listed[got[0]] = got[1]

    # 2b. inventory must equal the hand-audited record
    recorded = attested_hash_lines(attest_path.read_text(encoding="utf-8"))
    for path in sorted(set(recorded) | set(listed)):
        if path not in listed:
            report.problem(f"{where}: {path} is in the attestation but not in the inventory")
        elif path not in recorded:
            report.problem(f"{where}: {path} is in the inventory but not in the attestation")
        elif recorded[path] != listed[path]:
            report.problem(
                f"{where}: {path} hash differs between inventory ({listed[path]}) and "
                f"attestation ({recorded[path]})"
            )

    # 3. export configuration
    for i, entry in enumerate(inv["export_config"]):
        _check_entry_hash(root, entry, "export configuration", f"{where}: export_config[{i}]", report)

    # 4. additions within the attested source scope
    root_res = root.resolve()
    for pattern in include:
        for found in sorted(root.glob(pattern)):
            if not found.is_file():
                continue
            try:
                rel = str(found.resolve().relative_to(root_res))
            except ValueError:
                report.problem(f"{where}: {found} matches scope.include but resolves outside the repository")
                continue
            rel_link = str(found.relative_to(root))
            if _under(rel_link, exclude):
                continue
            if rel_link not in listed:
                report.problem(
                    f"{where}: UNAUDITED SOURCE -- {rel_link} is inside the attested scope "
                    f"({pattern}) but is not in the audit inventory (a newly added cell). "
                    f"{REMEDY}"
                )
            else:
                report.checked += 1


def active_attestations(root: Path, manifest_paths: list[Path],
                        report: Report) -> list[tuple[Path, Path]]:
    """(envelope, attestation) for every item-1 citation."""
    out = []
    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            report.problem(f"{manifest_path.name}: unreadable manifest: {exc}")
            continue
        entry = (manifest.get("evidence") or {}).get(ITEM_ID) if isinstance(manifest, dict) else None
        if entry is None:
            report.note(f"{manifest_path.name}: no item-{ITEM_ID} citation; nothing to check")
            continue
        for e in entry if isinstance(entry, list) else [entry]:
            where = f"{manifest_path.name} evidence['{ITEM_ID}']"
            rel = e if isinstance(e, str) else (e.get("file") if isinstance(e, dict) else None)
            envelope_path = contained(root, rel, "cited envelope", report, where)
            if envelope_path is None:
                continue
            if not envelope_path.is_file():
                report.problem(f"{where}: cited envelope {rel} does not exist")
                continue
            try:
                envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report.problem(f"{where}: cited envelope {rel} is not valid JSON: {exc}")
                continue
            source = envelope.get("source") if isinstance(envelope, dict) else None
            if not isinstance(source, str) or not source.strip():
                report.problem(f"{where}: envelope {rel} names no 'source' attestation")
                continue
            attest = contained(
                root, str(envelope_path.parent.relative_to(root.resolve()) / source),
                "attestation", report, where,
            )
            if attest is None:
                continue
            if not attest.is_file():
                report.problem(f"{where}: MISSING -- attestation {source} does not exist")
                continue
            out.append((envelope_path, attest))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    parser.add_argument("--manifest", default=None, help="block manifest (default: auto-detect)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    manifests_dir = root / "manifests"
    manifest_paths = (
        [Path(args.manifest).resolve()] if args.manifest else sorted(manifests_dir.glob("*.json"))
    )
    manifest_paths = [p for p in manifest_paths if not p.name.endswith(".signoff.json")]
    if not manifest_paths:
        print(f"::error::no block manifest found under {manifests_dir}")
        return 1

    report = Report(annotate=True)
    active: set[Path] = set()
    for _envelope, attest in active_attestations(root, manifest_paths, report):
        inv_path = attest.with_name(attest.stem + INVENTORY_SUFFIX)
        active.add(inv_path.resolve())
        if not inv_path.is_file():
            report.problem(
                f"{inv_path.relative_to(root)}: MISSING -- the actively cited item-{ITEM_ID} "
                f"attestation {attest.relative_to(root)} has no dependency inventory"
            )
            continue
        check_inventory(root, inv_path, attest, report)
        report.note(f"{inv_path.relative_to(root)}: checked (actively cited for item {ITEM_ID})")

    for other in sorted((root / "manifests").glob(f"**/*{INVENTORY_SUFFIX}")):
        if other.resolve() not in active:
            report.note(
                f"{other.relative_to(root)}: not actively cited -- a historical snapshot, "
                "not required to track the current design; not checked"
            )

    for note in report.notes:
        print(f"note: {note}")
    if report.problems:
        print(f"\n{len(report.problems)} design-source dependency problem(s):", file=sys.stderr)
        for problem in report.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"OK: {report.checked} design-source input(s) match the active item-{ITEM_ID} audit inventory "
          "(unchanged inputs only; not a new export-equivalence proof)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
