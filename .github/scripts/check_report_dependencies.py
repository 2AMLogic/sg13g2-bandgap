#!/usr/bin/env python3
"""Dependency-drift checker for the actively cited characterization report.

    python3 .github/scripts/check_report_dependencies.py
    python3 .github/scripts/check_report_dependencies.py --root DIR

`check_signoff_manifest.py` re-hashes the item-8 report (T1 "Characterization
report") and so catches an edited report. It cannot catch the other way the
report stops being true: its bytes stay put while the design, the spec or the
evidence it summarizes moves on (issue #315). This script closes that gap. It
is stdlib-only and PDK-free: it hashes and parses committed files, never runs
a simulator, never writes anything and never mints an attestation.

Which report is checked. Only the report the block manifest **actively
cites** for item 8 (`manifests/<block>.json` -> `evidence["8"]` -> envelope ->
its `provenance.input.path`). Its dependency inventory is the file
`dependencies.json` beside that envelope. A superseded report is a historical
snapshot: it is never required to track newer inputs, and an inventory beside
one is noted, not checked.

What the inventory records, and what is checked against it:

1. `report` / `report_sha256` — the report bytes the inventory was written
   for. They must still hash the same, and match the envelope's recorded
   hash: a new report needs a new inventory, not a reused one.
2. `dut[]` — the audited design-under-test inputs (`path`, `sha256`). Any
   change fails, naming the experiments whose "current" claim rested on that
   file. Only the listed netlists are hashed — a README or helper script
   under `design/` is not a DUT input.
3. `spec.table` — the governing specification table, as a **per-row digest**
   of the markdown table that follows `heading` in `source`. Rows are
   normalised (cells stripped, whitespace collapsed), so prose edits
   elsewhere in that file, or re-flowing the table, change nothing; a changed
   bound, an added row or a removed row fails, naming the row and the
   experiments that back it.
   `spec.decision_records[]` pins each cited record's `Status:` word (the
   report quotes it); `spec.absent[]` lists repo-relative globs the report
   states match nothing (e.g. a declined record number).
4. `experiments[]` — each `sim/<slug>` the report summarizes, with its
   `selected_record`, the record files it reads (`files`, path -> sha256),
   the spec rows it backs, and its `freshness`:
   - the selected record must be the **newest** record of that experiment
     under the repository's established ordering (`sorted(records/*.md)`,
     last wins — the same rule `check_evidence_formats.py` freshness uses);
     a newer record fails, naming the rows it would change;
   - the report text must cite the selected record id (or, for evidence
     it cites by directory, the experiment path `sim/<slug>/`);
   - `freshness: "current"` must not name a record that
     `sim/evidence-freshness-waivers.json` waives as run on a superseded
     DUT (a `design/...` check) — that would be an overclaim;
   - `freshness: "stale"` is an **honest disclosure** and passes: it must
     carry a `disclosure` phrase that appears in the report (compared
     case-insensitively with markdown emphasis and whitespace normalised),
     and a `waiver_issue`, if given, must match a live waiver for that
     record.
   Experiments not listed are not looked at: a new record elsewhere in
   `sim/` does not force a new report.

Every inventory path must be repository-relative and stay inside the
repository; absolute, escaping, missing or malformed entries fail. When this
check fails the remedy is always the same and never automatic: write a new
dated report (the old one stays untouched as history), its
`dependencies.json`, its envelope, the manifest pin and the regenerated
signoff verdict. A new report may (and must) disclose stale or failing
evidence honestly; a completed audit is not a circuit-performance pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from _ci_common import Report, sha256_file as _sha256_file_bare

#: T1 item whose cited report this script tracks.
ITEM_ID = "8"

#: The inventory's file name, beside the cited envelope.
INVENTORY_NAME = "dependencies.json"

SCHEMA_VERSION = 1

FRESHNESS_VALUES = {"current", "stale"}

SIM_WAIVER_FILE = "sim/evidence-freshness-waivers.json"

_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
_STATUS_RE = re.compile(r"^\s*-\s*\*\*Status\*\*\s*:\s*([A-Za-z-]+)", re.MULTILINE)
_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    """`sha256:`-prefixed digest, matching the manifest's `content_hash` form."""
    return "sha256:" + _sha256_file_bare(path)


def normalise_text(text: str) -> str:
    """Lower-case, drop markdown emphasis/code marks, collapse whitespace."""
    return " ".join(re.sub(r"[*`]", "", text).lower().split())


def _normalise_row(cells: list[str]) -> str:
    return " | ".join(" ".join(cell.split()) for cell in cells)


def spec_table_rows(text: str, heading: str) -> dict[str, str] | None:
    """Per-row sha256 of the first markdown table under `heading`.

    Returns {first-cell: "sha256:<hex>"} for every body row (the header and
    the `|---|` separator are skipped), or None when the heading or its table
    is absent. The digest covers the normalised row (cells stripped,
    internal whitespace collapsed), so re-flowing the table or editing prose
    around it does not change it, but any changed cell does.
    """
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip().startswith(heading)), None
    )
    if start is None:
        return None
    table: list[list[str]] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            break
        if stripped.startswith("|"):
            table.append([c.strip() for c in stripped.strip("|").split("|")])
        elif table:
            break
    if len(table) < 2:
        return None
    rows: dict[str, str] = {}
    for cells in table[1:]:
        if all(_SEPARATOR_CELL_RE.match(c) for c in cells if c):
            continue
        key = " ".join(cells[0].split())
        rows[key] = "sha256:" + hashlib.sha256(
            _normalise_row(cells).encode("utf-8")
        ).hexdigest()
    return rows


def decision_record_status(text: str) -> str | None:
    """First word of a decision record's `- **Status**:` bullet, lower-cased."""
    match = _STATUS_RE.search(text)
    return match.group(1).lower() if match else None


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


def _hash_matches(root: Path, rel: Any, pin: Any, what: str, report: Report,
                  where: str) -> tuple[bool, str]:
    """Return (ok, kind) where kind is '', 'missing', 'changed' or 'malformed'."""
    path = contained(root, rel, what, report, where)
    if path is None:
        return False, "malformed"
    if not isinstance(pin, str) or not _SHA_RE.match(pin):
        report.problem(f"{where}: {what} {rel} has malformed sha256 {pin!r}")
        return False, "malformed"
    if not path.is_file():
        report.problem(f"{where}: MISSING DEPENDENCY — {what} {rel} does not exist")
        return False, "missing"
    if sha256_file(path) != pin:
        return False, "changed"
    return True, ""


def _remedy() -> str:
    return (
        "Remedy: write a new dated report (leave this one unchanged as history), its "
        f"{INVENTORY_NAME}, envelope, manifest pin and regenerated signoff verdict"
    )


def _affected(experiments: list[dict], *, row: str | None = None,
              dut: str | None = None) -> str:
    names = []
    for exp in experiments:
        if row is not None and row in (exp.get("spec_rows") or []):
            names.append(exp.get("path"))
        if dut is not None and exp.get("freshness") == "current" and dut in (exp.get("dut") or []):
            names.append(exp.get("path"))
    return ", ".join(str(n) for n in names) if names else "none listed"


def load_sim_waivers(root: Path) -> dict[str, list[dict]]:
    path = root / SIM_WAIVER_FILE
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # check_evidence_formats.py owns the waiver file's validity.
        return {}
    by_record: dict[str, list[dict]] = {}
    for entry in raw.get("waivers", []) if isinstance(raw, dict) else []:
        if isinstance(entry, dict) and isinstance(entry.get("report"), str):
            by_record.setdefault(entry["report"], []).append(entry)
    return by_record


def check_inventory(root: Path, inv_path: Path, report_path: Path,
                    envelope_hash: Any, report: Report) -> None:
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
    for key, kind in (("dut", list), ("spec", dict), ("experiments", list)):
        if not isinstance(inv.get(key), kind):
            report.problem(f"{where}: required field '{key}' missing or not a {kind.__name__}")
            return
    experiments = [e for e in inv["experiments"] if isinstance(e, dict)]
    if len(experiments) != len(inv["experiments"]):
        report.problem(f"{where}: every experiments[] entry must be an object")
        return

    # 1. the report bytes this inventory was written for
    report_rel = str(report_path.relative_to(root))
    if inv.get("report") != report_rel:
        report.problem(
            f"{where}: inventory is for report {inv.get('report')!r}, but the "
            f"actively cited report is {report_rel}"
        )
        return
    actual_report_hash = sha256_file(report_path)
    if inv.get("report_sha256") != actual_report_hash:
        report.problem(
            f"{where}: inventory audits report bytes {inv.get('report_sha256')} but "
            f"{report_rel} now hashes to {actual_report_hash}; a changed report "
            "needs its dependency inventory re-audited"
        )
    if envelope_hash != actual_report_hash:
        report.problem(
            f"{where}: the cited envelope records {envelope_hash}, not the "
            f"report's {actual_report_hash}"
        )
    report_text = normalise_text(report_path.read_text(encoding="utf-8"))

    # 2. DUT inputs
    dut_paths = set()
    for i, entry in enumerate(inv["dut"]):
        w = f"{where}: dut[{i}]"
        if not isinstance(entry, dict):
            report.problem(f"{w}: must be an object {{path, sha256}}")
            continue
        dut_paths.add(entry.get("path"))
        ok, kind = _hash_matches(root, entry.get("path"), entry.get("sha256"),
                                 "DUT input", report, w)
        if kind == "changed":
            report.problem(
                f"{w}: DUT INPUT CHANGED — {entry['path']} no longer hashes to the "
                f"audited {entry['sha256']}; current-design claims affected: "
                f"{_affected(experiments, dut=entry['path'])}. {_remedy()}"
            )
        elif ok:
            report.checked += 1

    # 3. specification inputs
    spec = inv["spec"]
    table = spec.get("table")
    spec_rows: set[str] = set()
    if not isinstance(table, dict) or not isinstance(table.get("rows"), dict):
        report.problem(f"{where}: spec.table must be {{source, heading, rows}}")
    else:
        w = f"{where}: spec.table"
        src = contained(root, table.get("source"), "spec source", report, w)
        heading = table.get("heading")
        if src is not None and isinstance(heading, str) and heading.strip():
            spec_rows = set(table["rows"])
            if not src.is_file():
                report.problem(f"{w}: MISSING DEPENDENCY — spec source {table['source']} does not exist")
            else:
                current = spec_table_rows(src.read_text(encoding="utf-8"), heading)
                if current is None:
                    report.problem(
                        f"{w}: MISSING DEPENDENCY — no table under heading "
                        f"{heading!r} in {table['source']}"
                    )
                else:
                    for row, digest in sorted(table["rows"].items()):
                        if row not in current:
                            report.problem(
                                f"{w}: spec row {row!r} no longer exists in "
                                f"{table['source']}; experiments affected: "
                                f"{_affected(experiments, row=row)}. {_remedy()}"
                            )
                        elif current[row] != digest:
                            report.problem(
                                f"{w}: SPEC ROW CHANGED — {row!r} in {table['source']} "
                                f"differs from the audited row (bound or wording); "
                                f"experiments affected: {_affected(experiments, row=row)}. "
                                f"{_remedy()}"
                            )
                        else:
                            report.checked += 1
                    for row in sorted(set(current) - set(table["rows"])):
                        report.problem(
                            f"{w}: spec row {row!r} was added to {table['source']} and "
                            f"the report has no entry for it. {_remedy()}"
                        )
        elif src is not None:
            report.problem(f"{w}: heading must be a non-empty string")

    for i, entry in enumerate(spec.get("decision_records") or []):
        w = f"{where}: spec.decision_records[{i}]"
        if not isinstance(entry, dict):
            report.problem(f"{w}: must be an object {{path, status}}")
            continue
        path = contained(root, entry.get("path"), "decision record", report, w)
        if path is None:
            continue
        if not path.is_file():
            report.problem(f"{w}: MISSING DEPENDENCY — decision record {entry['path']} does not exist")
            continue
        status = decision_record_status(path.read_text(encoding="utf-8"))
        if status != str(entry.get("status", "")).lower():
            report.problem(
                f"{w}: DECISION RECORD STATUS CHANGED — {entry['path']} is now "
                f"{status!r}, the report quotes {entry.get('status')!r}. {_remedy()}"
            )
        else:
            report.checked += 1

    for i, pattern in enumerate(spec.get("absent") or []):
        w = f"{where}: spec.absent[{i}]"
        if not isinstance(pattern, str) or not pattern.strip() or Path(pattern).is_absolute() \
                or ".." in Path(pattern).parts:
            report.problem(f"{w}: must be a repository-relative glob, got {pattern!r}")
            continue
        found = sorted(str(p.relative_to(root)) for p in root.glob(pattern))
        if found:
            report.problem(
                f"{w}: the report states nothing matches {pattern!r}, but "
                f"{', '.join(found)} now exists. {_remedy()}"
            )
        else:
            report.checked += 1

    # 4. experiments summarized
    waivers = load_sim_waivers(root)
    for i, exp in enumerate(experiments):
        w = f"{where}: experiments[{i}]"
        exp_dir = contained(root, exp.get("path"), "experiment", report, w)
        if exp_dir is None:
            continue
        w = f"{where}: {exp['path']}"
        rows = exp.get("spec_rows")
        if not isinstance(rows, list):
            report.problem(f"{w}: spec_rows must be a list (empty for supplementary evidence)")
            rows = []
        rows_txt = ", ".join(rows) if rows else "supplementary, no spec row"
        for row in rows:
            if spec_rows and row not in spec_rows:
                report.problem(f"{w}: spec_rows names {row!r}, which is not an audited spec row")
        for d in exp.get("dut") or []:
            if d not in dut_paths:
                report.problem(f"{w}: dut names {d!r}, which is not in the inventory's dut[]")
        records_dir = exp_dir / "records"
        if not records_dir.is_dir():
            report.problem(f"{w}: MISSING DEPENDENCY — {exp['path']}/records does not exist")
            continue
        selected = exp.get("selected_record")
        if not isinstance(selected, str) or not selected or "/" in selected:
            report.problem(f"{w}: selected_record must be a bare record id, got {selected!r}")
            continue
        if not (records_dir / f"{selected}.md").is_file():
            report.problem(f"{w}: MISSING DEPENDENCY — selected record {selected}.md does not exist")
            continue
        newest = sorted(records_dir.glob("*.md"))[-1].stem
        if newest != selected:
            report.problem(
                f"{w}: NEWER RECORD — {newest} now supersedes the selected record "
                f"{selected} (rows: {rows_txt}); the report no longer cites the newest "
                f"evidence. {_remedy()}"
            )
        files = exp.get("files")
        if not isinstance(files, dict) or not files:
            report.problem(f"{w}: files must be a non-empty object of path -> sha256")
        else:
            for rel, pin in sorted(files.items()):
                ok, kind = _hash_matches(root, rel, pin, "record file", report, w)
                if kind == "changed":
                    report.problem(
                        f"{w}: record file {rel} no longer hashes to the audited "
                        f"{pin} (sim/ evidence is append-only)"
                    )
                elif ok:
                    report.checked += 1
        if normalise_text(selected) not in report_text and \
                normalise_text(exp["path"].rstrip("/") + "/") not in report_text:
            report.problem(
                f"{w}: the report cites neither the selected record {selected} nor "
                f"the experiment {exp['path']}/"
            )

        record_rel = f"{exp['path']}/records/{selected}.md"
        rec_waivers = waivers.get(record_rel, [])
        dut_waivers = [x for x in rec_waivers if str(x.get("check", "")).startswith("design/")]
        freshness = exp.get("freshness")
        if freshness not in FRESHNESS_VALUES:
            report.problem(f"{w}: freshness must be one of {sorted(FRESHNESS_VALUES)}, got {freshness!r}")
            continue
        if freshness == "current":
            if dut_waivers:
                report.problem(
                    f"{w}: OVERCLAIM — marked current, but {SIM_WAIVER_FILE} waives "
                    f"{selected} as run on a superseded DUT "
                    f"({', '.join(str(x.get('issue')) for x in dut_waivers)}); disclose it "
                    "as stale instead"
                )
            for x in rec_waivers:
                if x not in dut_waivers:
                    report.note(
                        f"{w}: {selected} carries a '{x.get('check')}' waiver "
                        f"({x.get('issue')}) — not a DUT-staleness waiver, noted only"
                    )
            continue
        disclosure = exp.get("disclosure")
        if not isinstance(disclosure, str) or not disclosure.strip():
            report.problem(f"{w}: a stale entry must carry the report's disclosure phrase")
        elif normalise_text(disclosure) not in report_text:
            report.problem(
                f"{w}: stale-evidence disclosure {disclosure!r} does not appear in the report"
            )
        issue = exp.get("waiver_issue")
        if issue is not None and not any(str(x.get("issue")) == str(issue) for x in dut_waivers):
            report.problem(
                f"{w}: disclosure cites waiver {issue}, but {SIM_WAIVER_FILE} carries "
                f"no DUT-staleness waiver for {record_rel} under {issue}"
            )
        report.note(f"{w}: {selected} disclosed as stale (rows: {rows_txt})")


def active_reports(root: Path, manifest_paths: list[Path],
                   report: Report) -> list[tuple[Path, Path, Any]]:
    """(envelope, report, recorded hash) for every item-8 citation."""
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
        entries = entry if isinstance(entry, list) else [entry]
        for e in entries:
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
            recorded = ((envelope.get("provenance") or {}).get("input") or {}) \
                if isinstance(envelope, dict) else {}
            inp = recorded.get("path") if isinstance(recorded, dict) else None
            if isinstance(inp, dict) and inp.get("scope") == "repo":
                report_path = contained(root, inp.get("path"), "report", report, where)
            elif isinstance(inp, str):
                report_path = contained(
                    root, str(envelope_path.parent.relative_to(root.resolve()) / inp),
                    "report", report, where,
                )
            else:
                report.problem(f"{where}: envelope {rel} names no provenance.input.path report")
                continue
            if report_path is None:
                continue
            if not report_path.is_file():
                report.problem(f"{where}: MISSING DEPENDENCY — report {report_path} does not exist")
                continue
            out.append((envelope_path, report_path, recorded.get("content_hash")))
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
    active_inventories: set[Path] = set()
    for envelope_path, report_path, recorded_hash in active_reports(root, manifest_paths, report):
        inv_path = envelope_path.parent / INVENTORY_NAME
        active_inventories.add(inv_path.resolve())
        if not inv_path.is_file():
            report.problem(
                f"{inv_path.relative_to(root)}: MISSING — the actively cited item-{ITEM_ID} "
                f"report {report_path.relative_to(root)} has no dependency inventory"
            )
            continue
        check_inventory(root, inv_path, report_path, recorded_hash, report)
        report.note(f"{inv_path.relative_to(root)}: checked (actively cited for item {ITEM_ID})")

    for other in sorted((root / "measurements").glob(f"*/{INVENTORY_NAME}")):
        if other.resolve() not in active_inventories:
            report.note(
                f"{other.relative_to(root)}: not actively cited — a historical snapshot, "
                "not required to track newer inputs; not checked"
            )

    for note in report.notes:
        print(f"note: {note}")
    if report.problems:
        print(f"\n{len(report.problems)} report-dependency problem(s):", file=sys.stderr)
        for problem in report.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"OK: {report.checked} report dependency input(s) match the active item-{ITEM_ID} inventory")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
