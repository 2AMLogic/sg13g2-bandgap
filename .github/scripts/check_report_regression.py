#!/usr/bin/env python3
"""DRC/LVS report regression guard for sg13g2-bandgap.

    python3 .github/scripts/check_report_regression.py
    python3 .github/scripts/check_report_regression.py --require-regression-base

Issue #594: the evidence ladder checks that a report is *fresh* (its recorded
input hashes match, `check_evidence_formats.py`) and *well-formed*, but nothing
compared a re-minted report's outcome against the report it replaces. A re-mint
that is fresh, well-formed, correctly hash-pinned and **much worse** passed
every gate — PR #591 moved `layout/bandgap_core/lvs_report.json` from 4 to
1022 error-severity findings with the full checker suite green, because the
regression was only visible by diffing the committed artifact against its own
merge base. This script is that diff, as a gate.

For every committed change to a guarded report (the `bandgap_*` cells'
`lvs_report.json` / `drc_report.json` — the `sg13cmos5l-*` cells are excluded
until wanted there), the merge-base revision of the same file is read with
`git show <merge-base>:<path>` — the same plumbing
`check_evidence_formats.py::check_append_only` uses — and the headline counts
are compared:

- LVS: `error_count` up, `counts.devices.matched` or `counts.nets.matched`
  down, or any `category_error_counts[class]` up (per-class, so a 0 → 504
  `net.unmatched` move is caught even if a total were masked);
- DRC: `violation_count` up, or any `rule_counts[rule]` up (a rule absent in
  the base counts as 0, so a brand-new violation class fails).

A class/rule present only at one side is resolved exactly as the predicates
say: absent in the base counts as 0 (any positive head value fails). A
class/rule value that is not an integer never disappears quietly either: at
the working-tree side it is a failure — a report whose counts cannot be
read cannot be compared — and at the merge base it is a note, the head
value for that class still comparing against an implicit 0. A headline
field that exists only at the merge base is skipped with a loud note; a
head-only error_count/violation_count fails against an implicit 0 with a
message that says the base recorded no value. A per-class mapping the base
carried but the head does not is a note that distinguishes an absent
mapping from one present with no usable integer values. A report that is
new (no merge-base revision) is a note; a merge-base copy that does not
parse is a failure — the comparison cannot run and must not read as a
pass. Deletion of a guarded report is a failure too: the guard compares
replaced reports and cannot vouch for a deletion.

A deliberate regression stays expressible through
`layout/report-regression-waivers.json` (same discipline as
`layout/evidence-freshness-waivers.json`): an entry names the exact report,
the exact new value of **every** regressed predicate, a tracking issue and a
reason. It **self-expires**: on the next re-mint the named values no longer
match, and on any PR where the report no longer regresses the entry is
obsolete — either way the checker fails until the entry is deleted, so a
waiver cannot outlive the regression it describes. Unused waivers (the report
unchanged) fail as well.

Like the append-only check, the git plumbing itself (not a checkout, no
merge base, diff failure) is a loud skip-note by default; CI passes
`--require-regression-base` so a shallow or unresolvable checkout cannot
skip-as-pass.

Stdlib only, no venv, no PDK, no `klt`: bare runner, seconds, never mints
evidence. It reads two revisions of a JSON file per changed report and
nothing else.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from _ci_common import Report

WAIVER_FILE = "layout/report-regression-waivers.json"
WAIVER_REQUIRED_KEYS = ("report", "expected", "issue", "reason")

#: The reports this guard compares: each cell directory's LVS and DRC report.
#: The `sg13cmos5l-*` cells are deliberately excluded (issue #594 scope:
#: add them when wanted); `pex_extract_report.json` / `erc_report.json` are
#: out of scope for the same reason.
REPORT_RE = re.compile(r"^layout/(?!sg13cmos5l-)[^/]+/(?:lvs|drc)_report\.json$")

#: A waiver's `expected` maps predicate keys to the exact new (head) values.
PREDICATE_KEY_RE = re.compile(
    r"^(?:lvs\.error_count"
    r"|lvs\.nets\.matched"
    r"|lvs\.devices\.matched"
    r"|lvs\.category_error_counts\.\S+"
    r"|drc\.violation_count"
    r"|drc\.rule_counts\.\S+)$"
)

#: Predicates where a *lower* head value is the regression (matched counts).
LOWER_IS_BAD = {"lvs.nets.matched", "lvs.devices.matched"}


def _int(value: object) -> bool:
    """True for a real integer (JSON numbers), excluding bools."""
    return isinstance(value, int) and not isinstance(value, bool)


def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout.strip()


# --- waiver file --------------------------------------------------------------


def load_waivers(root: Path, report: Report, waiver_file: str = WAIVER_FILE) -> dict[str, dict]:
    """Parse the regression-waiver file, keying valid entries by report path.

    Mirrors `check_evidence_formats.py::load_waivers`: every schema defect is a
    reported failure (not a silent skip), the tracking issue must be
    `#<number>`, and `expected` must be a non-empty mapping of known predicate
    keys to integer values.
    """
    path = root / waiver_file
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.fail(waiver_file, f"is not valid JSON: {exc}")
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("waivers"), list):
        report.fail(waiver_file, "must be a JSON object with a 'waivers' list")
        return {}
    waivers: dict[str, dict] = {}
    for entry in raw["waivers"]:
        if not isinstance(entry, dict):
            report.fail(waiver_file, f"waiver entry is not an object: {entry!r}")
            continue
        missing = [k for k in WAIVER_REQUIRED_KEYS if not entry.get(k)]
        if missing:
            report.fail(waiver_file, f"waiver entry missing required key(s): {', '.join(missing)}")
            continue
        if not re.match(r"^#\d+$", str(entry["issue"])):
            report.fail(
                waiver_file,
                f"waiver for {entry['report']} has issue {entry['issue']!r}; expected '#<number>'",
            )
            continue
        rel = entry["report"]
        if not isinstance(rel, str) or not REPORT_RE.match(rel):
            report.fail(
                waiver_file,
                f"waiver names {rel!r}, which is not a report this checker guards "
                f"(expected layout/<cell>/lvs_report.json or drc_report.json; "
                "sg13cmos5l-* cells are out of scope)",
            )
            continue
        expected = entry["expected"]
        if not isinstance(expected, dict) or not expected:
            report.fail(
                waiver_file, f"waiver for {rel} needs a non-empty 'expected' mapping of new values"
            )
            continue
        bad_keys = [k for k in expected if not PREDICATE_KEY_RE.match(str(k))]
        if bad_keys:
            report.fail(
                waiver_file,
                f"waiver for {rel} names unknown predicate(s): {', '.join(map(str, bad_keys))}",
            )
            continue
        bad_vals = [k for k, v in expected.items() if not _int(v)]
        if bad_vals:
            report.fail(
                waiver_file,
                f"waiver for {rel} has non-integer expected value(s) for: {', '.join(map(str, bad_vals))}",
            )
            continue
        if rel in waivers:
            report.fail(waiver_file, f"two waiver entries name {rel}; one entry per report")
            continue
        waivers[rel] = entry
    return waivers


def report_unused_waivers(
    report: Report,
    waivers: dict[str, dict],
    consulted: set[str],
    waiver_file: str,
) -> None:
    """A waiver whose report this run never compared hides nothing — fail it."""
    for rel, waiver in sorted(waivers.items()):
        if rel not in consulted:
            report.fail(
                f"{waiver_file} [{rel}]",
                f"waiver matches no report this run compared against its merge base "
                f"(tracked at {waiver['issue']}) — a waiver that guards nothing hides nothing",
            )


# --- per-report predicates ----------------------------------------------------


def collect_lvs(doc: dict, side: str, rel: str, report: Report) -> tuple[dict[str, int], bool]:
    """The comparable integer predicates of an LVS report revision, and whether
    `category_error_counts` was present as a mapping at all."""
    preds: dict[str, int] = {}
    value = doc.get("error_count")
    if _int(value):
        preds["lvs.error_count"] = value
    elif value is not None:
        report.note(f"{rel}: {side} error_count is {value!r}, not an integer — not compared")

    counts = doc.get("counts")
    if isinstance(counts, dict):
        for name, key in (("nets", "lvs.nets.matched"), ("devices", "lvs.devices.matched")):
            sub = counts.get(name)
            if isinstance(sub, dict):
                value = sub.get("matched")
                if _int(value):
                    preds[key] = value
                elif value is not None:
                    report.note(
                        f"{rel}: {side} counts.{name}.matched is {value!r}, "
                        "not an integer — not compared"
                    )

    cat = doc.get("category_error_counts")
    if isinstance(cat, dict):
        for cls, value in cat.items():
            if _int(value):
                preds[f"lvs.category_error_counts.{cls}"] = value
            elif side == "working-tree":
                report.fail(
                    rel,
                    f"{side} category_error_counts.{cls} is {value!r}, not an integer "
                    "— the per-class comparison cannot run and must not read as a pass",
                )
            else:
                report.note(
                    f"{rel}: {side} category_error_counts.{cls} is {value!r}, not an "
                    "integer — not compared; a head value for this class compares "
                    "against an implicit 0",
                )

    if isinstance(cat, dict) is False and cat is not None:
        report.note(f"{rel}: {side} category_error_counts is not a mapping — not compared")
    return preds, isinstance(cat, dict)


def collect_drc(doc: dict, side: str, rel: str, report: Report) -> tuple[dict[str, int], bool]:
    """The comparable integer predicates of a DRC report revision, and whether
    `rule_counts` was present as a mapping at all."""
    preds: dict[str, int] = {}
    value = doc.get("violation_count")
    if _int(value):
        preds["drc.violation_count"] = value
    elif value is not None:
        report.note(f"{rel}: {side} violation_count is {value!r}, not an integer — not compared")

    rules = doc.get("rule_counts")
    if isinstance(rules, dict):
        for rule, value in rules.items():
            if _int(value):
                preds[f"drc.rule_counts.{rule}"] = value
            elif side == "working-tree":
                report.fail(
                    rel,
                    f"{side} rule_counts.{rule} is {value!r}, not an integer — the "
                    "per-class comparison cannot run and must not read as a pass",
                )
            else:
                report.note(
                    f"{rel}: {side} rule_counts.{rule} is {value!r}, not an integer — "
                    "not compared; a head value for this rule compares against an "
                    "implicit 0",
                )
    elif rules is not None:
        report.note(f"{rel}: {side} rule_counts is not a mapping — not compared")
    return preds, isinstance(rules, dict)


def regressions(
    rel: str,
    base: dict[str, int],
    head: dict[str, int],
    report: Report,
    head_mapping_present: bool,
) -> dict[str, tuple[int, int]]:
    """Pair the two revisions' predicates; return `{key: (base, head)} regressions`.

    Per-class predicates (category_error_counts / rule_counts) use the
    union of both sides with a base-default of 0, so a class that appears
    only at head fails on any positive value and a class that disappears is
    an improvement. Matched counts are compared only when both sides carry
    them (a field that exists in one revision only is not comparable). A
    per-class mapping the base carried but the head did not is a note,
    worded by whether the head mapping is absent or present with no usable
    integer values.
    """
    out: dict[str, tuple[int, int]] = {}
    for key, head_value in sorted(head.items()):
        if key in LOWER_IS_BAD:
            base_value = base.get(key)
            if base_value is None:
                report.note(f"{rel}: {key} missing at the merge base — not comparable")
            elif head_value < base_value:
                out[key] = (base_value, head_value)
        else:
            base_value = base.get(key, 0)
            if head_value > base_value:
                out[key] = (base_value, head_value)
    for key in sorted(base):
        if key in head:
            continue
        if key in LOWER_IS_BAD or key in ("lvs.error_count", "drc.violation_count"):
            report.note(
                f"{rel}: {key} present only at the merge base ({base[key]}) — not compared"
            )
    for prefix in ("lvs.category_error_counts", "drc.rule_counts"):
        base_has = any(k.startswith(prefix) for k in base)
        head_has = any(k.startswith(prefix) for k in head)
        if base_has and not head_has:
            name = prefix.split(".", 1)[1]
            if head_mapping_present:
                report.note(
                    f"{rel}: {name} mapping present at the working-tree side but "
                    "carries no usable integer values — per-class check skipped"
                )
            else:
                report.note(
                    f"{rel}: {name} mapping missing at the working-tree side — "
                    "per-class check skipped"
                )
    return out


# --- the check ----------------------------------------------------------------


def check_regression(root: Path, base_ref: str, required: bool, report: Report) -> None:
    code, _ = _git(root, "rev-parse", "--git-dir")
    if code != 0:
        message = "not a git checkout — report regression check cannot run"
        report.fail("regression", message) if required else report.note(f"SKIP: {message}")
        return

    code, base = _git(root, "merge-base", base_ref, "HEAD")
    if code != 0 or not base:
        message = f"no merge base with {base_ref} — report regression check cannot run"
        report.fail("regression", message) if required else report.note(f"SKIP: {message}")
        return

    code, out = _git(root, "diff", "--name-status", "--diff-filter=ADMRC", f"{base}...HEAD")
    if code != 0:
        message = f"git diff against {base[:12]} failed"
        report.fail("regression", message) if required else report.note(f"SKIP: {message}")
        return

    waivers = load_waivers(root, report)
    consulted: set[str] = set()
    compared = 0

    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0][0], parts[1]
        extra = parts[2] if len(parts) > 2 else None

        if status == "D" and REPORT_RE.match(path):
            report.fail(
                path,
                f"deleted relative to {base_ref} ({base[:12]}) — the regression guard "
                "compares replaced reports and cannot vouch for a deletion",
            )
            continue
        if status == "R" and REPORT_RE.match(path):
            report.fail(
                path,
                f"moved relative to {base_ref} ({base[:12]}) (renamed to {extra}) — the "
                "regression guard compares replaced reports and a moved report has no "
                "merge-base revision at its new path",
            )
            continue
        if status in ("A", "R", "C"):
            new_path = extra if status in ("R", "C") else path
            if REPORT_RE.match(new_path):
                report.note(
                    f"{new_path}: new report — no merge-base revision to compare; "
                    "the regression guard starts from this commit"
                )
            continue
        if status != "M" or not REPORT_RE.match(path):
            continue

        head_path = root / path
        try:
            head_doc = json.loads(head_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            report.fail(path, f"working-tree copy does not parse as JSON: {exc}")
            continue
        code, base_text = _git(root, "show", f"{base}:{path}")
        if code != 0:
            report.fail(path, f"git show {base[:12]}:{path} failed — the merge-base "
                              "revision cannot be read; the comparison cannot run")
            continue
        try:
            base_doc = json.loads(base_text)
        except json.JSONDecodeError as exc:
            report.fail(
                path,
                f"merge-base revision ({base[:12]}) does not parse as JSON: {exc} — "
                "the quality comparison cannot run",
            )
            continue
        if not isinstance(head_doc, dict) or not isinstance(base_doc, dict):
            report.fail(path, "report revision is not a JSON object — comparison cannot run")
            continue

        compared += 1
        kind = "lvs" if path.endswith("lvs_report.json") else "drc"
        collect = collect_lvs if kind == "lvs" else collect_drc
        base_preds, _ = collect(base_doc, "merge-base", path, report)
        head_preds, head_mapping_present = collect(head_doc, "working-tree", path, report)
        fired = regressions(path, base_preds, head_preds, report, head_mapping_present)
        consulted.add(path)  # consulted whether or not it regressed

        if not fired:
            report.note(f"{path}: no regression against {base[:12]}")
        waiver = waivers.get(path)
        if fired and waiver is None:
            for key, (base_value, head_value) in sorted(fired.items()):
                if key in ("lvs.error_count", "drc.violation_count") and key not in base_preds:
                    report.fail(
                        path,
                        f"{key} reads {head_value} at the working tree but the merge "
                        f"base recorded no value (compared against an implicit 0) "
                        f"relative to {base_ref} ({base[:12]}) — waive deliberately "
                        f"via {WAIVER_FILE} naming the exact new value and the "
                        "tracking issue",
                    )
                else:
                    report.fail(
                        path,
                        f"{key} regressed {base_value} → {head_value} relative to {base_ref} "
                        f"({base[:12]}) — waive deliberately via {WAIVER_FILE} naming the exact "
                        "new value and the tracking issue",
                    )
        elif fired and waiver is not None:
            expected = {str(k): v for k, v in waiver["expected"].items()}
            fired_heads = {k: v for k, (_, v) in fired.items()}
            missing = sorted(set(fired) - set(expected))
            wrong = sorted(
                k for k in set(fired) & set(expected) if expected[k] != fired[k][1]
            )
            extra = sorted(set(expected) - set(fired))
            if missing or wrong or extra:
                detail = []
                if missing:
                    detail.append(
                        "omits regressing predicate(s) " + ", ".join(
                            f"{k} ({fired[k][0]} → {fired[k][1]})" for k in missing
                        )
                    )
                if wrong:
                    detail.append(
                        "records " + ", ".join(
                            f"{k}={expected[k]} but the report now reads {fired[k][1]}"
                            for k in wrong
                        )
                    )
                if extra:
                    detail.append(
                        "names value(s) that no longer regress: " + ", ".join(
                            f"{k}={expected[k]}" for k in extra
                        )
                    )
                report.fail(
                    f"{WAIVER_FILE} [{path}]",
                    "; ".join(detail) + " — a waiver must name exactly the regressed "
                    f"value(s) (tracked at {waiver['issue']})",
                )
            else:
                report.note(
                    f"REGRESSED (waived, {waiver['issue']}): {path} "
                    + ", ".join(f"{k} {b} → {h}" for k, (b, h) in sorted(fired.items()))
                    + f" — {waiver['reason']}"
                )
        elif not fired and waiver is not None:
            report.fail(
                f"{WAIVER_FILE} [{path}]",
                f"waiver is obsolete — {path} no longer regresses against {base[:12]}; "
                f"delete this entry (tracked at {waiver['issue']})",
            )

    report_unused_waivers(report, waivers, consulted, WAIVER_FILE)
    report.checked = compared
    if compared == 0:
        report.note(f"regression: no committed lvs/drc report changed since {base[:12]}")


# --- entry point --------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None, help="repo root (default: this script's repo)")
    parser.add_argument("--base-ref", default="origin/main", help="regression comparison base")
    parser.add_argument(
        "--require-regression-base",
        action="store_true",
        help="fail (rather than skip) when the merge base cannot be resolved",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    report = Report()

    check_regression(root, args.base_ref, args.require_regression_base, report)

    return report.finish(
        "regression",
        f"OK: {report.checked} report revision(s) compared against the merge base under {root}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
