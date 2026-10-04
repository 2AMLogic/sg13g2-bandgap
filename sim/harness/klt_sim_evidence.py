#!/usr/bin/env python3
"""Turn a `klt sim` corner-sweep report into this repo's evidence records.

Issue #275. `klt sim` is the corner-grid harness this repo is moving to (see
`sim/harness/README.md` for the decision and the batch-fleet status); its JSON
report is a *response document*, not evidence in this repo's sense. This
module is the adapter between the two, and it is deliberately generic over
experiments: every one of the 23 `sim/*` experiments emits the same
append-only quadruple, so there is exactly one translation to write.

    klt sim report.json                 ->  sim/<exp>/records/<id>.csv
    + per-corner artifacts/             ->  sim/<exp>/records/<id>.md
                                            sim/<exp>/corners/<id>/<pt>.log
                                            sim/<exp>/netlist-snapshots/<id>/<pt>.spice

Three things the translation is not allowed to fudge, because
`.github/scripts/check_evidence_formats.py` checks all three (see
`sim/README.md` § "Summary record format"):

1. **The corner id.** `klt sim` names a point `typ/3.300V/27C`; this repo's
   grammar is `<process>_<temp>c_<supply>v` (`typ_27c_3.30v`), and the
   supply/temperature spellings must match the CSV's own `vdd_v`/`temp_c`
   cells exactly or check C fails on a set difference. :func:`corner_id`
   derives all three from one place.

2. **The netlist snapshot must be self-contained.** The deck `klt sim`
   generates (`corner.cir`) only `.include`s the netlist body, so the
   snapshot it would copy verbatim holds *no device instances at all* -- the
   D2 freshness rule parses the snapshot's own text for the DUT's devices and
   would report "snapshots inline none of its instances", silently
   downgrading a hard freshness check to a note. :func:`inline_deck` splices
   every local `.include`/`.lib` into the snapshot, recursively, so the
   committed artifact is the full deck that ran.

3. **No absolute host paths in committed evidence.** The same
   `inline_deck` rewrites any surviving path under `$PDK_ROOT` to a
   `${PDK_ROOT}`-relative form, the convention `sim/env.sh` already
   establishes, so a record does not pin one machine's directory layout.
   (`klt sim`'s own report does this for its `environment.models_lib` field
   too -- klayout-tools #1261/#1274, the same concern.)

Everything *narrative* in a record -- the Claim, the Devices/provenance
paragraph, the corner-matrix sentence -- is per-experiment prose and comes
from a spec JSON next to the experiment, never from this module. The adapter
owns the mechanics and the parts CI checks; the experiment owns its own
argument.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

#: Relative-path forms `inline_deck` leaves alone: a model library under the
#: PDK is referenced, never inlined (it is megabytes, host-resolved, and
#: already pinned by identity in `sim/pdk.json` plus the report's own
#: `environment.models_lib_sha256`).
PDK_ROOT_PLACEHOLDER = "${PDK_ROOT}"

_INCLUDE_RE = re.compile(r'^\s*\.include\s+"?([^"\s]+)"?\s*$', re.IGNORECASE)
_LIB_RE = re.compile(r'^\s*\.lib\s+"?([^"\s]+)"?(?:\s+(\S+))?\s*$', re.IGNORECASE)
_SECTION_RE = r'^\s*\.lib\s+{section}\s*$'
_ENDL_RE = r'^\s*\.endl(\s+{section})?\s*$'


def corner_id(corner: dict) -> tuple[str, str, str, str]:
    """`klt sim` corner -> (repo corner id, corner_label, temp_c, vdd_v).

    The three cell spellings are returned alongside the id so the CSV row and
    the `corners/`/`netlist-snapshots/` filenames are minted from one
    derivation -- check C compares the two sets and a drift between them is
    exactly the failure that would produce.
    """
    label = corner.get("process") or "nom"
    temp = corner.get("temperature_c")
    temp_cell = f"{temp:g}" if isinstance(temp, (int, float)) else str(temp)
    supplies = corner.get("supply_v") or {}
    if len(supplies) != 1:
        raise SystemExit(
            "klt_sim_evidence.py: this repo's corner-id grammar carries exactly one "
            f"supply token, but corner {corner.get('corner_id')!r} sweeps "
            f"{len(supplies)} rail(s): {sorted(supplies)}"
        )
    vdd_cell = f"{next(iter(supplies.values())):.2f}"
    return f"{label}_{temp_cell}c_{vdd_cell}v", label, temp_cell, vdd_cell


def _pdk_relative(path: str, pdk_root: str | None) -> str:
    if pdk_root and os.path.isabs(path):
        try:
            rel = os.path.relpath(path, pdk_root)
        except ValueError:
            return path
        if not rel.startswith(os.pardir):
            return f"{PDK_ROOT_PLACEHOLDER}/{rel}"
    return path


def inline_deck(
    deck_path: Path,
    pdk_root: str | None,
    *,
    _depth: int = 0,
    _seen: tuple[Path, ...] = (),
) -> list[str]:
    """Read a generated corner deck and return it with local includes spliced in.

    A `.include` of a readable local file is replaced by that file's own
    inlined text (recursively, with a cycle guard). A `.lib FILE SECTION`
    whose FILE is readable and local is replaced by that section's *body* --
    which is how the generated `.lib <bundle> typ` card becomes the three
    per-family PDK `.lib` cards the equivalent `run_pvt_sweep.sh` snapshot
    would have carried inline (see `klt_corner_bundle.py` for why the bundle
    exists). Anything not readable, and anything under `$PDK_ROOT`, is kept
    as a card with its path made `${PDK_ROOT}`-relative.
    """
    if _depth > 8:
        raise SystemExit(f"klt_sim_evidence.py: include nesting too deep at {deck_path}")
    out: list[str] = []
    for raw in deck_path.read_text(encoding="utf-8").splitlines():
        inc = _INCLUDE_RE.match(raw)
        lib = None if inc else _LIB_RE.match(raw)
        target: Path | None = None
        if inc:
            target = (deck_path.parent / inc.group(1)).resolve()
        elif lib and lib.group(2):
            target = (deck_path.parent / lib.group(1)).resolve()

        under_pdk = bool(
            pdk_root and target and str(target).startswith(os.path.abspath(pdk_root) + os.sep)
        )
        if target is None or under_pdk or not target.is_file() or target in _seen:
            if inc:
                out.append(f'.include "{_pdk_relative(inc.group(1), pdk_root)}"')
            elif lib:
                section = f" {lib.group(2)}" if lib.group(2) else ""
                out.append(f'.lib "{_pdk_relative(lib.group(1), pdk_root)}"{section}')
            else:
                out.append(raw)
            continue

        if inc:
            out.append(f"* --- inlined .include {target.name} (klt_sim_evidence.py) ---")
            out.extend(inline_deck(target, pdk_root, _depth=_depth + 1, _seen=_seen + (target,)))
            out.append(f"* --- end {target.name} ---")
        else:
            section = lib.group(2)
            out.append(f"* --- inlined .lib {target.name} {section} (klt_sim_evidence.py) ---")
            out.extend(
                _lib_section_body(
                    target, section, pdk_root, _depth=_depth + 1, _seen=_seen + (target,)
                )
            )
            out.append(f"* --- end {target.name} {section} ---")
    return out


def _lib_section_body(
    lib_path: Path,
    section: str,
    pdk_root: str | None,
    *,
    _depth: int,
    _seen: tuple[Path, ...],
) -> list[str]:
    start = re.compile(_SECTION_RE.format(section=re.escape(section)), re.IGNORECASE)
    end = re.compile(_ENDL_RE.format(section=re.escape(section)), re.IGNORECASE)
    lines = lib_path.read_text(encoding="utf-8").splitlines()
    inside = False
    body: list[str] = []
    for raw in lines:
        if not inside:
            if start.match(raw):
                inside = True
            continue
        if end.match(raw):
            break
        body.append(raw)
    if not inside:
        raise SystemExit(
            f"klt_sim_evidence.py: {lib_path} declares no `.lib {section}` section"
        )
    # The section body may itself hold `.lib`/`.include` cards (the corner
    # bundle's whole purpose) -- rewrite their paths under the same
    # `${PDK_ROOT}`-relative rule rather than inlining a PDK model library.
    resolved: list[str] = []
    for raw in body:
        inc = _INCLUDE_RE.match(raw)
        lib = None if inc else _LIB_RE.match(raw)
        if inc:
            resolved.append(f'.include "{_pdk_relative(inc.group(1), pdk_root)}"')
        elif lib:
            tail = f" {lib.group(2)}" if lib.group(2) else ""
            resolved.append(f'.lib "{_pdk_relative(lib.group(1), pdk_root)}"{tail}')
        else:
            resolved.append(raw)
    return resolved


def record_id(repo_root: Path, stamp: str | None = None) -> str:
    import datetime

    sha = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    short = sha.stdout.strip() or "unknown"
    when = stamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{when}-{short}"


def measurement_names(report: dict) -> list[str]:
    """Measurement column order: the request's own order, not a set's."""
    names: list[str] = []
    for corner in report.get("corners", []):
        for entry in corner.get("measurements", []):
            if entry.get("name") not in names:
                names.append(entry["name"])
    return names


def corner_passed(corner: dict, required: list[str]) -> bool:
    """A point PASSes when `klt sim` graded it `pass` and every measurement
    this experiment's spec declares `pass_requires` actually came back.

    The second half mirrors what every `run_pvt_sweep.sh` already does by
    hand (`-n "${vref:-}" && …`): a corner whose solve "succeeded" but whose
    probed quantity is absent is not evidence for anything.
    """
    if corner.get("status") != "pass":
        return False
    got = {m["name"]: m.get("value") for m in corner.get("measurements", [])}
    return all(got.get(name) is not None for name in required)


def build_csv(report: dict, spec: dict, names: list[str]) -> tuple[list[dict], int]:
    extra = spec.get("extra_columns") or {}
    rows: list[dict] = []
    passed = 0
    for corner in report.get("corners", []):
        _cid, label, temp_cell, vdd_cell = corner_id(corner)
        ok = corner_passed(corner, spec.get("pass_requires") or [])
        passed += int(ok)
        row = {
            "corner_label": label,
            **{col: values.get(label, "") for col, values in extra.items()},
            "temp_c": temp_cell,
            "vdd_v": vdd_cell,
            "status": "PASS" if ok else "FAIL",
        }
        got = {m["name"]: m.get("value") for m in corner.get("measurements", [])}
        for name in names:
            value = got.get(name)
            row[name] = "" if value is None else f"{value:.6e}"
        rows.append(row)
    return rows, passed


def build_md(
    report: dict,
    spec: dict,
    rid: str,
    passed: int,
    total: int,
    failed: list[str],
) -> str:
    import datetime

    env = report.get("environment") or {}
    provenance = report.get("provenance") or {}
    deck = provenance.get("deck") or {}
    # `environment.models_lib` is `{path, scope}` and `klt sim` deliberately
    # redacts `path` to null when the library sits outside the repo
    # (klayout-tools #1261/#1274 — an absolute path there would leak the
    # author's home directory into committed evidence). The generated corner
    # bundle always does sit outside the repo, so name it by the identity that
    # survives: `provenance.deck`'s name plus its content hash.
    models_lib = env.get("models_lib")
    models_path = models_lib.get("path") if isinstance(models_lib, dict) else models_lib
    models_desc = models_path or (
        f"`{deck.get('name')}` (outside the repo; `klt sim` redacts the path, so it is "
        "identified by content hash only — regenerate it with "
        "`sim/harness/klt_corner_bundle.py`)"
        if deck.get("name")
        else "not recorded"
    )
    # `backend` is not a field of the report, so it is never asserted here.
    # A remote/batch run leaves `environment.remote` behind; a local one leaves
    # nothing, which is reported as exactly that rather than guessed at.
    remote = env.get("remote")
    backend_desc = (
        f"dispatched off-host (`environment.remote`: {json.dumps(remote, sort_keys=True)})"
        if remote
        else "no off-host dispatch recorded in the report (`environment.remote` absent)"
    )
    lines = [f"# Record {rid}", ""]
    for field in ("Experiment", "Claim"):
        lines.append(f"- **{field}**: {spec[field]}")
    for field in ("Devices", "Netlist provenance"):
        if spec.get(field):
            lines.append(f"- **{field}**: {spec[field]}")
    lines.append(f"- **PDK**: {spec['PDK']}")
    lines.append(
        "- **Harness**: `klt sim` corner matrix (not a `run_pvt_sweep.sh` shell"
        f" loop) -- request `{spec['request']}`, adapted to this record by"
        " `sim/harness/klt_sim_evidence.py` (issue #275); see"
        " `sim/harness/README.md`. Model library"
        f" {models_desc}, sha256 `{env.get('models_lib_sha256')}`."
        f" `klt` `{provenance.get('klt_version') or 'not recorded'}`;"
        f" {backend_desc}."
    )
    lines.append(f"- **ngspice**: `{env.get('engine_version') or 'see report'}`")
    noun = "point" if total == 1 else "points"
    lines.append(f"- **Corner matrix run**: {spec['Corner matrix run']} = {total} {noun}.")
    lines.append(
        f"- **Result**: {passed}/{total} {noun} PASS (`klt sim` graded the corner"
        " `pass` and every measurement this experiment requires came back --"
        " see `pass_requires` in the spec beside the request)."
    )
    if failed:
        lines.append(f"- **Failed points**: {' '.join(failed)}")
    lines.append("- **Links**:")
    lines.append(f"  - `klt sim` request: `{spec['request']}`")
    lines.append(f"  - Per-point generated netlists: `netlist-snapshots/{rid}/`")
    lines.append(f"  - Per-point raw ngspice logs: `corners/{rid}/`")
    lines.append(f"  - Parsed CSV: `records/{rid}.csv`")
    for link in spec.get("extra_links") or []:
        lines.append(f"  - {link}")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"- **Timestamp / author**: {stamp}, {spec.get('author', 'Loom Builder (agent)')}.")
    lines.append("")
    return "\n".join(lines)


def emit(
    report: dict,
    spec: dict,
    experiment: Path,
    repo_root: Path,
    rid: str,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    names = measurement_names(report)
    rows, passed = build_csv(report, spec, names)
    total = len(rows)
    if not total:
        raise SystemExit("klt_sim_evidence.py: report holds no corners")
    failed = [
        corner_id(c)[0] for c in report["corners"] if not corner_passed(c, spec.get("pass_requires") or [])
    ]
    pdk_root = spec.get("pdk_root") or os.environ.get("PDK_ROOT")

    corners_out = experiment / "corners" / rid
    snaps_out = experiment / "netlist-snapshots" / rid
    records_out = experiment / "records"
    if dry_run:
        print(f"would write {records_out}/{rid}.{{md,csv}}, {corners_out}/, {snaps_out}/")
        print(f"  {passed}/{total} PASS; measurement columns: {', '.join(names)}")
        return passed, total

    for directory in (corners_out, snaps_out, records_out):
        directory.mkdir(parents=True, exist_ok=True)

    for corner in report["corners"]:
        cid = corner_id(corner)[0]
        artifacts = corner.get("artifacts") or {}
        log = artifacts.get("log")
        deck = artifacts.get("deck")
        if not log or not Path(log).is_file():
            raise SystemExit(
                f"klt_sim_evidence.py: corner {cid} has no readable ngspice log -- re-run "
                "the request with options.keep_artifacts true (a record must ship its raw "
                "simulator output)"
            )
        shutil.copyfile(log, corners_out / f"{cid}.log")
        if not deck or not Path(deck).is_file():
            raise SystemExit(f"klt_sim_evidence.py: corner {cid} has no readable generated deck")
        text = "\n".join(inline_deck(Path(deck), pdk_root)) + "\n"
        (snaps_out / f"{cid}.spice").write_text(text, encoding="utf-8")

    with (records_out / f"{rid}.csv").open("w", newline="", encoding="utf-8") as handle:
        # LF line endings: this repo's committed records are all bash-written
        # LF files; python's csv default (CRLF) would make every klt-minted
        # record the odd one out in diffs.
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (records_out / f"{rid}.md").write_text(
        build_md(report, spec, rid, passed, total, failed), encoding="utf-8"
    )
    return passed, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="klt sim JSON report")
    parser.add_argument("--spec", required=True, help="per-experiment record spec JSON")
    parser.add_argument("--experiment", required=True, help="sim/<experiment> directory")
    parser.add_argument("--record-id", help="override the minted <date>-<time>-<sha> id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    experiment = Path(args.experiment).resolve()
    repo_root = Path(__file__).resolve().parents[2]
    rid = args.record_id or record_id(repo_root)

    passed, total = emit(report, spec, experiment, repo_root, rid, dry_run=args.dry_run)
    print(f"klt_sim_evidence.py: {passed}/{total} PASS -> {experiment.name}/records/{rid}.md")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
