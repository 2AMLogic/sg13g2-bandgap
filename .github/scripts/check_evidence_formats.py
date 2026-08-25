#!/usr/bin/env python3
"""Evidence-format and freshness checker for sg13g2-bandgap.

    python3 .github/scripts/check_evidence_formats.py
    python3 .github/scripts/check_evidence_formats.py --require-append-only

`sim/README.md` (evidence-record convention) and `layout/README.md` (DRC/LVS/PEX
reports) are the authoritative conventions; this script is their enforcement. It
is deliberately independent of the code that *writes* evidence (each
experiment's `run_pvt_sweep.sh`, and `klt` itself) — a checker that reused the
producer's own rendering could not notice the producer drifting away from the
convention.

Stdlib only, no venv, no PDK, no `klt`, no ngspice: this runs on a bare runner in
seconds and never mints evidence (per `CLAUDE.md`, `sim/` results are deliberate,
append-only evidence — CI checks their *shape*, it does not produce them).

What is checked
---------------

**A. `sim/<slug>/` experiment structure** — a `README.md` (the documented
cold-start invocation), at least one `run_*.sh`, and a `testbench/` holding at
least one netlist or template.

**B. `sim/<slug>/records/<record-id>.md` + `.csv`** —

- the filename is a well-formed `<YYYYMMDD>-<HHMMSS>-<short-sha>`, the `.csv`
  sibling exists, and the `# Record <record-id>` heading repeats it exactly;
- the required record fields are present and non-empty (`REQUIRED_FIELDS`), plus
  at least one netlist-provenance field (`Netlist provenance` or `Devices`);
- the `Timestamp / author` field carries a UTC ISO-8601 timestamp;
- `netlist-snapshots/<record-id>/` and `corners/<record-id>/` exist and are
  non-empty, and every per-point filename in them parses under the corner-id
  grammar in `sim/README.md` (`<process>_<temp>c_<supply>v`);
- **the three per-point views agree**: the set of corner ids named by the raw
  logs, by the netlist snapshots, and by the CSV's own
  `corner_label`/`temp_c`/`vdd_v` columns are identical — a record cannot claim
  a PVT point it has no netlist or no log for, and cannot silently drop one;
- **the headline matches the data**: `- **Result**: N/M points PASS` is checked
  against the CSV, where `M` is the row count and `N` the number of rows whose
  `status` column reads `PASS`. This is the anti-overclaim check — a record
  cannot say 45/45 while its own parsed data says otherwise.

**C. `layout/<cell>/` DRC/LVS/extract/PEX reports** — each report parses, carries
`schema_version` / `status` / `provenance.deck.content_hash` / `klt_version`,
uses a known status vocabulary, is internally consistent (a `clean` DRC has zero
violations; a `match` LVS has zero mismatches), and — for DRC — enumerates its
deck coverage gaps, which the evidence ladder requires to travel with the
verdict rather than be dropped from it.

**D. Freshness ("staleness is failure")** — every report records the sha256 of
the input it was produced from. Those recorded hashes are re-derived from the
committed files and must match: a report produced against a superseded GDS (or a
PEX netlist that no longer matches its own report) is stale evidence, and stale
evidence fails. Known-stale reports may be waived only through
`layout/evidence-freshness-waivers.json`, which requires a tracking issue and
records the exact stale hash — so a waiver **self-expires**: once the evidence is
regenerated the recorded hash no longer matches and the checker fails until the
waiver is deleted.

**E. Append-only evidence** — nothing under `sim/*/records/`,
`sim/*/netlist-snapshots/` or `sim/*/corners/` may be modified or deleted
relative to the merge base. A correction is a new `<record-id>`, never an edit.

What is deliberately *not* checked: the prose inside a record field (a record is
a human/agent-written argument, not a form), and the pass/fail *verdict* of the
DRC/LVS reports. This repo's LVS legitimately reads `mismatch` today for reasons
documented in `layout/README.md`; CI's job is to keep that verdict honest and
fresh, not to demand a verdict the deck cannot yet produce.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# --- sim/ convention constants (sim/README.md) -------------------------------

RECORDS_DIR = "records"
SNAPSHOT_DIR = "netlist-snapshots"
CORNERS_DIR = "corners"

#: `<YYYYMMDD>-<HHMMSS>-<short-git-sha>`, e.g. `20260821-115433-5f66bd5`.
RECORD_ID_RE = re.compile(r"^(?P<date>\d{8})-(?P<time>\d{6})-(?P<sha>[0-9a-f]{7,40})$")

#: A top-level record field: `- **Name**: value`. Indented bullets continue the
#: field above rather than opening a new one.
FIELD_RE = re.compile(r"^- \*\*(?P<name>[^*]+?)\*\*:(?P<value>.*)$")

#: Present in every record committed to this repo, and required by
#: `sim/README.md`'s "Summary record format".
REQUIRED_FIELDS: tuple[str, ...] = (
    "Experiment",
    "Claim",
    "PDK",
    "ngspice",
    "Corner matrix run",
    "Result",
    "Links",
    "Timestamp / author",
)

#: At least one of these must be present: pre-layout records name the schematic
#: netlist they ran ("Netlist provenance"); the PEX records carry the same
#: provenance per device, under "Devices", because each device has a different
#: source (extracted vs. spliced-in schematic).
PROVENANCE_FIELDS: tuple[str, ...] = ("Netlist provenance", "Devices")

#: `- **Result**: 45/45 points PASS (...)`.
RESULT_RE = re.compile(r"^\s*(?P<passed>\d+)\s*/\s*(?P<total>\d+)\s+points?\s+PASS\b")

#: A UTC ISO-8601 instant, e.g. `2026-08-21T23:13:09Z`.
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

# corner-id grammar: `<process>_<temp>c_<supply>v`, split on the last two
# underscores so `<process>` may itself carry an underscore-joined family
# prefix. SG13G2 ships per-device-family corner files with their own section
# vocabularies, so the process token vocabulary is deliberately open.
PROCESS_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TEMP_TOKEN_RE = re.compile(r"^-?\d+(?:\.\d+)?c$")
SUPPLY_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?v$")

CSV_REQUIRED_COLUMNS: tuple[str, ...] = ("corner_label", "temp_c", "vdd_v", "status")
CSV_STATUS_VALUES = frozenset({"PASS", "FAIL"})

# --- layout/ report constants (layout/README.md) -----------------------------

SHA256_RE = re.compile(r"^(?:sha256:)?(?P<hex>[0-9a-f]{64})$")

DRC_STATUSES = frozenset({"clean", "violations"})
LVS_STATUSES = frozenset({"match", "mismatch"})
PEX_STATUSES = frozenset({"extracted"})

WAIVER_FILE = "layout/evidence-freshness-waivers.json"
WAIVER_REQUIRED_KEYS = ("report", "check", "recorded_hash", "issue", "reason")

# --- append-only constants ---------------------------------------------------

APPEND_ONLY_RE = re.compile(
    r"^sim/[^/]+/(?:%s)/" % "|".join(re.escape(d) for d in (RECORDS_DIR, SNAPSHOT_DIR, CORNERS_DIR))
)


class Report:
    """Collects problems as `<path>: <message>` and prints them once."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []
        self.checked = 0

    def fail(self, where: str | Path, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def note(self, message: str) -> None:
        self.notes.append(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_corner_id(corner_id: str) -> str | None:
    """Return an error message if `corner_id` violates the grammar, else None."""
    parts = corner_id.rsplit("_", 2)
    if len(parts) != 3:
        return "expected <process>_<temp>c_<supply>v"
    process, temp, supply = parts
    if not PROCESS_TOKEN_RE.match(process):
        return f"process token {process!r} is not lowercase alphanumeric"
    if not TEMP_TOKEN_RE.match(temp):
        return f"temperature token {temp!r} is not <number>c"
    if not SUPPLY_TOKEN_RE.match(supply):
        return f"supply token {supply!r} is not <number>v"
    return None


def parse_fields(text: str) -> dict[str, str]:
    """Read the `- **Name**: value` fields of a record, joining continuations."""
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = FIELD_RE.match(line)
        if match:
            current = match.group("name").strip()
            fields.setdefault(current, []).append(match.group("value").strip())
        elif current is not None and line.startswith("  "):
            fields[current].append(line.strip())
        elif not line.strip():
            continue
        else:
            current = None
    return {name: " ".join(v for v in values if v).strip() for name, values in fields.items()}


def corner_ids_from_csv(csv_path: Path, report: Report) -> tuple[list[str], int, int] | None:
    """Return (corner ids, pass count, row count) parsed from a record CSV."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        report.fail(csv_path, "no data rows — a record must carry its parsed per-point data")
        return None
    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in (rows[0].keys())]
    if missing:
        report.fail(csv_path, f"missing required column(s): {', '.join(missing)}")
        return None

    corner_ids: list[str] = []
    passed = 0
    for index, row in enumerate(rows, start=2):  # line 1 is the header
        status = (row["status"] or "").strip()
        if status not in CSV_STATUS_VALUES:
            report.fail(csv_path, f"line {index}: status {status!r} is not one of PASS/FAIL")
        if status == "PASS":
            passed += 1
        corner_ids.append(
            "{label}_{temp}c_{vdd}v".format(
                label=(row["corner_label"] or "").strip(),
                temp=(row["temp_c"] or "").strip(),
                vdd=(row["vdd_v"] or "").strip(),
            )
        )
    return corner_ids, passed, len(rows)


def check_record(record_md: Path, experiment: Path, report: Report) -> None:
    record_id = record_md.stem
    report.checked += 1

    if not RECORD_ID_RE.match(record_id):
        report.fail(record_md, "filename is not a <YYYYMMDD>-<HHMMSS>-<short-sha> record id")
        return

    csv_path = record_md.with_suffix(".csv")
    if not csv_path.is_file():
        report.fail(record_md, f"no machine-readable sibling {csv_path.name}")

    text = record_md.read_text(encoding="utf-8")
    heading = text.splitlines()[0].strip() if text.strip() else ""
    if heading != f"# Record {record_id}":
        report.fail(record_md, f"first heading is {heading!r}, expected '# Record {record_id}'")

    fields = parse_fields(text)
    for name in REQUIRED_FIELDS:
        if name not in fields:
            report.fail(record_md, f"missing required field '- **{name}**:'")
        elif not fields[name]:
            report.fail(record_md, f"field '- **{name}**:' is empty")
    if not any(name in fields and fields[name] for name in PROVENANCE_FIELDS):
        report.fail(
            record_md,
            "no netlist-provenance field — needs one of: "
            + ", ".join(f"'- **{n}**:'" for n in PROVENANCE_FIELDS),
        )

    stamp = fields.get("Timestamp / author", "")
    if stamp and not TIMESTAMP_RE.search(stamp):
        report.fail(record_md, "'Timestamp / author' carries no UTC ISO-8601 instant (…Z)")

    snapshots_dir = experiment / SNAPSHOT_DIR / record_id
    corners_dir = experiment / CORNERS_DIR / record_id
    snapshot_ids: set[str] = set()
    log_ids: set[str] = set()

    if not corners_dir.is_dir():
        report.fail(record_md, f"no raw per-point logs at {corners_dir}")
    else:
        logs = sorted(corners_dir.glob("*.log"))
        if not logs:
            report.fail(corners_dir, "holds no *.log — a record must ship its raw simulator output")
        for log in logs:
            problem = parse_corner_id(log.stem)
            if problem:
                report.fail(log, f"corner id does not parse: {problem}")
            else:
                log_ids.add(log.stem)

    if not snapshots_dir.is_dir():
        report.fail(record_md, f"no per-point netlist snapshots at {snapshots_dir}")
    else:
        snapshots = sorted(snapshots_dir.glob("*.spice"))
        if not snapshots:
            report.fail(snapshots_dir, "holds no *.spice netlist snapshots")
        for snapshot in snapshots:
            problem = parse_corner_id(snapshot.stem)
            if problem:
                report.fail(snapshot, f"corner id does not parse: {problem}")
            else:
                snapshot_ids.add(snapshot.stem)

    if log_ids and snapshot_ids and log_ids != snapshot_ids:
        _report_set_difference(report, record_md, "raw logs", log_ids, "netlist snapshots", snapshot_ids)

    if not csv_path.is_file():
        return
    parsed = corner_ids_from_csv(csv_path, report)
    if parsed is None:
        return
    csv_ids, passed, total = parsed

    duplicates = sorted({cid for cid in csv_ids if csv_ids.count(cid) > 1})
    if duplicates:
        report.fail(csv_path, f"duplicate corner id(s): {', '.join(duplicates)}")

    if log_ids and set(csv_ids) != log_ids:
        _report_set_difference(report, csv_path, "CSV rows", set(csv_ids), "raw logs", log_ids)

    result = fields.get("Result", "")
    match = RESULT_RE.match(result)
    if not match:
        report.fail(record_md, "'Result' does not start with '<passed>/<total> points PASS'")
        return
    claimed_pass = int(match.group("passed"))
    claimed_total = int(match.group("total"))
    if claimed_total != total:
        report.fail(
            record_md,
            f"'Result' claims {claimed_total} points but {csv_path.name} has {total} data rows",
        )
    if claimed_pass != passed:
        report.fail(
            record_md,
            f"'Result' claims {claimed_pass} PASS but {csv_path.name} has {passed} PASS row(s)",
        )


def _report_set_difference(
    report: Report, where: Path, left_name: str, left: set[str], right_name: str, right: set[str]
) -> None:
    only_left = sorted(left - right)
    only_right = sorted(right - left)
    detail = []
    if only_left:
        detail.append(f"only in {left_name}: {', '.join(only_left)}")
    if only_right:
        detail.append(f"only in {right_name}: {', '.join(only_right)}")
    report.fail(where, f"{left_name} and {right_name} disagree on PVT points — " + "; ".join(detail))


def check_sim(root: Path, report: Report) -> None:
    sim = root / "sim"
    if not sim.is_dir():
        report.fail(sim, "missing — sim/ is where this repo's evidence lives")
        return

    pdk_json = sim / "pdk.json"
    if not pdk_json.is_file():
        report.fail(pdk_json, "missing — every record must trace to a pinned PDK revision")
    else:
        try:
            pinned = json.loads(pdk_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.fail(pdk_json, f"is not valid JSON: {exc}")
        else:
            for key in ("source", "release_tag", "tarball_sha256"):
                if not pinned.get(key):
                    report.fail(pdk_json, f"missing or empty pin field {key!r}")

    experiments = sorted(p for p in sim.iterdir() if p.is_dir() and (p / RECORDS_DIR).is_dir())
    if not experiments:
        report.fail(sim, "no experiment directory holds a records/ tree")
        return

    for experiment in experiments:
        rel = experiment.relative_to(root)
        if not (experiment / "README.md").is_file():
            report.fail(rel, "no README.md — an experiment must document its cold-start invocation")
        if not sorted(experiment.glob("run_*.sh")):
            report.fail(rel, "no run_*.sh cold-start entry point")
        testbench = experiment / "testbench"
        if not testbench.is_dir() or not any(testbench.iterdir()):
            report.fail(rel, "no testbench/ holding the netlist or generation template")

        records = sorted((experiment / RECORDS_DIR).glob("*.md"))
        if not records:
            report.fail(rel / RECORDS_DIR, "holds no *.md evidence records")
        for record_md in records:
            check_record(record_md, experiment, report)


# --- layout/ reports ---------------------------------------------------------


def load_waivers(root: Path, report: Report) -> dict[tuple[str, str], dict]:
    path = root / WAIVER_FILE
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.fail(WAIVER_FILE, f"is not valid JSON: {exc}")
        return {}
    waivers: dict[tuple[str, str], dict] = {}
    for entry in raw.get("waivers", []):
        missing = [k for k in WAIVER_REQUIRED_KEYS if not entry.get(k)]
        if missing:
            report.fail(WAIVER_FILE, f"waiver entry missing required key(s): {', '.join(missing)}")
            continue
        if not re.match(r"^#\d+$", str(entry["issue"])):
            report.fail(
                WAIVER_FILE,
                f"waiver for {entry['report']} has issue {entry['issue']!r}; expected '#<number>'",
            )
            continue
        waivers[(entry["report"], entry["check"])] = entry
    return waivers


def check_hash(
    report: Report,
    root: Path,
    report_rel: str,
    check_name: str,
    recorded: str | None,
    input_path: Path,
    waivers: dict[tuple[str, str], dict],
    used_waivers: set[tuple[str, str]],
) -> None:
    """Assert `recorded` is the sha256 of `input_path`, honouring waivers."""
    where = f"{report_rel} [{check_name}]"
    if recorded is None:
        report.fail(where, "records no input hash — freshness cannot be established")
        return
    match = SHA256_RE.match(str(recorded).strip())
    if not match:
        report.fail(where, f"recorded hash {recorded!r} is not a sha256 digest")
        return
    recorded_hex = match.group("hex")
    if not input_path.is_file():
        report.fail(where, f"input {input_path.relative_to(root)} does not exist")
        return
    actual = sha256_file(input_path)
    key = (report_rel, check_name)
    waiver = waivers.get(key)

    if recorded_hex == actual:
        if waiver is not None:
            used_waivers.add(key)
            report.fail(
                f"{WAIVER_FILE} [{report_rel} / {check_name}]",
                "waiver is obsolete — the evidence is fresh again; delete this entry "
                f"(tracked at {waiver['issue']})",
            )
        return

    if waiver is not None:
        used_waivers.add(key)
        waived_hex = SHA256_RE.match(str(waiver["recorded_hash"]).strip())
        if not waived_hex or waived_hex.group("hex") != recorded_hex:
            report.fail(
                f"{WAIVER_FILE} [{report_rel} / {check_name}]",
                f"waiver records hash {waiver['recorded_hash']!r} but the report now records "
                f"sha256:{recorded_hex} — re-check the waiver instead of leaving it stale",
            )
            return
        report.note(
            f"STALE (waived, {waiver['issue']}): {report_rel} [{check_name}] was produced against "
            f"sha256:{recorded_hex[:12]}…, but {input_path.relative_to(root)} is now "
            f"sha256:{actual[:12]}… — {waiver['reason']}"
        )
        return

    report.fail(
        where,
        f"STALE: produced against sha256:{recorded_hex}, but {input_path.relative_to(root)} is "
        f"now sha256:{actual} — regenerate the report, or waive it in {WAIVER_FILE} with a "
        "tracking issue",
    )


def _common_report_checks(report: Report, rel: str, data: dict) -> None:
    if not isinstance(data.get("schema_version"), int):
        report.fail(rel, "missing integer 'schema_version'")
    provenance = data.get("provenance")
    if not isinstance(provenance, dict):
        report.fail(rel, "missing 'provenance' object")
        return
    if not provenance.get("klt_version"):
        report.fail(rel, "missing 'provenance.klt_version' — the engine must be named")
    deck = provenance.get("deck")
    if not isinstance(deck, dict):
        report.fail(rel, "missing 'provenance.deck' object")
        return
    if not deck.get("name"):
        report.fail(rel, "missing 'provenance.deck.name'")
    if not SHA256_RE.match(str(deck.get("content_hash", "")).strip()):
        report.fail(rel, "'provenance.deck.content_hash' is not a sha256 digest — the deck a "
                         "verdict came from must be identified by content")


def check_layout(root: Path, report: Report) -> None:
    layout = root / "layout"
    if not layout.is_dir():
        report.fail("layout", "missing")
        return

    waivers = load_waivers(root, report)
    used_waivers: set[tuple[str, str]] = set()

    cells = sorted(p for p in layout.iterdir() if p.is_dir() and any(p.glob("*.gds")))
    if not cells:
        report.fail("layout", "no cell directory holds a *.gds")
        return

    for cell_dir in cells:
        cell = cell_dir.name
        gds = cell_dir / f"{cell}.gds"
        if not gds.is_file():
            report.fail(str(cell_dir.relative_to(root)), f"no {cell}.gds matching the directory name")
            continue

        for name in ("drc_report.json", "lvs_report.json"):
            if not (cell_dir / name).is_file():
                report.fail(str((cell_dir / name).relative_to(root)), "missing — a committed "
                            "layout must ship its latest verdict")

        for path in sorted(cell_dir.glob("*_report.json")):
            rel = str(path.relative_to(root))
            report.checked += 1
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                report.fail(rel, f"is not valid JSON: {exc}")
                continue
            _common_report_checks(report, rel, data)
            status = data.get("status")

            if path.name == "drc_report.json":
                if status not in DRC_STATUSES:
                    report.fail(rel, f"status {status!r} not in {sorted(DRC_STATUSES)}")
                count = data.get("violation_count")
                if not isinstance(count, int):
                    report.fail(rel, "missing integer 'violation_count'")
                elif (status == "clean") != (count == 0):
                    report.fail(rel, f"status {status!r} contradicts violation_count {count}")
                coverage = data.get("coverage")
                if not isinstance(coverage, dict) or "rules_skipped" not in coverage:
                    report.fail(rel, "missing 'coverage.rules_skipped' — deck coverage gaps must "
                                     "be enumerated alongside the verdict")
                check_hash(report, root, rel, "input gds",
                           (data.get("provenance") or {}).get("input", {}).get("content_hash")
                           if isinstance((data.get("provenance") or {}).get("input"), dict) else None,
                           gds, waivers, used_waivers)

            elif path.name == "lvs_report.json":
                if status not in LVS_STATUSES:
                    report.fail(rel, f"status {status!r} not in {sorted(LVS_STATUSES)}")
                if not data.get("engine"):
                    report.fail(rel, "missing 'engine' — the LVS engine must be named")
                count = data.get("mismatch_count")
                if not isinstance(count, int):
                    report.fail(rel, "missing integer 'mismatch_count'")
                elif (status == "match") != (count == 0):
                    report.fail(rel, f"status {status!r} contradicts mismatch_count {count}")
                counts = data.get("counts")
                if not isinstance(counts, dict) or not {"nets", "devices"} <= set(counts):
                    report.fail(rel, "missing 'counts.nets'/'counts.devices'")
                env = data.get("environment") if isinstance(data.get("environment"), dict) else {}
                check_hash(report, root, rel, "layout", env.get("layout_sha256"), gds,
                           waivers, used_waivers)
                reference = data.get("reference")
                if reference:
                    check_hash(report, root, rel, "reference netlist",
                               env.get("reference_sha256"), cell_dir / str(reference),
                               waivers, used_waivers)
                else:
                    report.fail(rel, "missing 'reference' — the netlist compared against")

            elif path.name == "extract_report.json":
                # A plain (non-parasitic) `klt extract` report, committed as
                # the machine-readable evidence behind a cell's documented
                # deck-coverage gaps — `warnings`/`ignored_layers`/
                # `unmodelled_poly`/`voltage_domain_warnings`/
                # `unbiased_pmos_body_nets` (layout/sg13cmos5l-bandgap_core,
                # issue #66). Same status vocabulary and same two freshness
                # anchors as the PEX report below: a gap list produced
                # against a superseded GDS is exactly as stale as a verdict
                # produced against one.
                if status not in PEX_STATUSES:
                    report.fail(rel, f"status {status!r} not in {sorted(PEX_STATUSES)}")
                netlist = data.get("netlist_path")
                if not netlist:
                    report.fail(rel, "missing 'netlist_path'")
                else:
                    check_hash(report, root, rel, "extracted netlist",
                               data.get("netlist_sha256"), cell_dir / str(netlist),
                               waivers, used_waivers)
                provenance_input = (data.get("provenance") or {}).get("input")
                check_hash(report, root, rel, "input gds",
                           provenance_input.get("content_hash")
                           if isinstance(provenance_input, dict) else None,
                           gds, waivers, used_waivers)

            elif path.name == "pex_extract_report.json":
                if status not in PEX_STATUSES:
                    report.fail(rel, f"status {status!r} not in {sorted(PEX_STATUSES)}")
                netlist = data.get("netlist_path")
                if not netlist:
                    report.fail(rel, "missing 'netlist_path'")
                else:
                    check_hash(report, root, rel, "extracted netlist",
                               data.get("netlist_sha256"), cell_dir / str(netlist),
                               waivers, used_waivers)
                provenance_input = (data.get("provenance") or {}).get("input")
                check_hash(report, root, rel, "input gds",
                           provenance_input.get("content_hash")
                           if isinstance(provenance_input, dict) else None,
                           gds, waivers, used_waivers)

    for key, waiver in sorted(waivers.items()):
        if key not in used_waivers:
            report.fail(
                f"{WAIVER_FILE} [{key[0]} / {key[1]}]",
                f"waiver matches no report/check that this checker runs (tracked at "
                f"{waiver['issue']}) — a waiver that guards nothing hides nothing",
            )


# --- append-only -------------------------------------------------------------


def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout.strip()


def check_append_only(root: Path, base_ref: str, required: bool, report: Report) -> None:
    code, _ = _git(root, "rev-parse", "--git-dir")
    if code != 0:
        message = "not a git checkout — append-only evidence check cannot run"
        report.fail("append-only", message) if required else report.note(f"SKIP: {message}")
        return

    code, base = _git(root, "merge-base", base_ref, "HEAD")
    if code != 0 or not base:
        message = f"no merge base with {base_ref} — append-only evidence check cannot run"
        report.fail("append-only", message) if required else report.note(f"SKIP: {message}")
        return

    code, out = _git(root, "diff", "--name-status", "--diff-filter=MDR", f"{base}...HEAD")
    if code != 0:
        message = f"git diff against {base[:12]} failed"
        report.fail("append-only", message) if required else report.note(f"SKIP: {message}")
        return

    offenders = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        if APPEND_ONLY_RE.match(path):
            offenders.append(f"{status} {path}")
    for offender in sorted(offenders):
        report.fail(
            offender.split(" ", 1)[1],
            "committed evidence was modified or deleted relative to "
            f"{base_ref} ({offender.split(' ', 1)[0]}) — sim/ evidence is append-only; "
            "mint a new <record-id> instead",
        )
    if not offenders:
        report.note(f"append-only: no committed evidence changed since {base[:12]}")


# --- entry point -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    parser.add_argument("--base-ref", default="origin/main", help="append-only comparison base")
    parser.add_argument(
        "--require-append-only",
        action="store_true",
        help="fail (rather than skip) when the merge base cannot be resolved",
    )
    parser.add_argument("--skip-append-only", action="store_true", help="skip the git-based check")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    report = Report()

    check_sim(root, report)
    check_layout(root, report)
    if not args.skip_append_only:
        check_append_only(root, args.base_ref, args.require_append_only, report)

    for note in report.notes:
        print(f"note: {note}")

    if report.problems:
        print(f"\n{len(report.problems)} evidence-format problem(s):", file=sys.stderr)
        for problem in report.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"OK: {report.checked} evidence artifact(s) checked under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
