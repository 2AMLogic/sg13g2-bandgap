#!/usr/bin/env python3
"""Self-test for `check_report_regression.py`.

    python3 .github/scripts/test_check_report_regression.py

A checker that never fails is indistinguishable from no checker at all, so
each case below builds a throwaway two-commit git repo in a temp directory —
`main` holds the base reports, `topic` holds the PR-head mutation — runs the
checker as a subprocess against `--base-ref main`, and asserts the verdict
and the message. The headline case replays the issue-#591 shape that motivated
the guard: a fresh, well-formed LVS re-mint whose error_count moves 4 → 1022
(`category_error_counts` net.unmatched 0 → 504) must fail.

Hermetic: stdlib only, temp dirs, no PDK, no network. Needs `git`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_report_regression.py"

LVS = "layout/cell/lvs_report.json"
DRC = "layout/cell/drc_report.json"
WAIVERS = "layout/report-regression-waivers.json"


def lvs_doc(error_count=4, nets_matched=253, devices_matched=263, category=None):
    """The base LVS report: the pre-#591 bandgap_core mint's headline shape."""
    return {
        "schema_version": 1,
        "status": "match" if error_count == 0 else "mismatch",
        "error_count": error_count,
        "counts": {
            "nets": {"layout": 257, "reference": 257, "matched": nets_matched},
            "devices": {"layout": 263, "reference": 266, "matched": devices_matched},
        },
        "category_error_counts": (
            dict(category) if category is not None
            else {"device.unmatched": 3, "topology": 1}
        ),
    }


def drc_doc(violation_count=18, rule_counts=None):
    """The base DRC report shape (one rule class, issue-#572-style markers)."""
    return {
        "schema_version": 1,
        "status": "clean" if violation_count == 0 else "violations",
        "violation_count": violation_count,
        "rule_counts": (
            dict(rule_counts) if rule_counts is not None
            else {"metal1.enclosing.cont.1": violation_count}
        ),
    }


def lvs_regressed_591():
    """The PR-#591 head shape: 4 → 1022 errors, pairing cascade collapsed."""
    return lvs_doc(
        error_count=1022, nets_matched=2, devices_matched=6,
        category={"device.unmatched": 517, "net.unmatched": 504, "topology": 1},
    )


#: The exact predicates that regress in `lvs_regressed_591()` (topology 1 → 1
#: does not), and therefore exactly what a valid waiver must name.
REGRESSED_591_EXPECTED = {
    "lvs.error_count": 1022,
    "lvs.nets.matched": 2,
    "lvs.devices.matched": 6,
    "lvs.category_error_counts.device.unmatched": 517,
    "lvs.category_error_counts.net.unmatched": 504,
}


def write(root: Path, rel: str, payload) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def write_raw(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=check
    )


def commit_all(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
        "commit", "-q", "--allow-empty", "-m", message)


def run_case(mutate_head=None, mutate_base=None, extra: tuple[str, ...] = (),
             base_ref: str = "main") -> subprocess.CompletedProcess:
    """Build the two-commit fixture repo and run the checker over it.

    `main` commit: the base reports (mutated first by `mutate_base` for
    corrupt-base cases). `topic` commit: the head, after `mutate_head`.
    `base_ref` is the comparison base handed to the checker: a ref name (the
    pull_request path, the default) or the sentinel `"@BASE_SHA"` — the
    merge-group path (issue #614), where the workflow passes the queue's
    trial-merge base as a raw sha.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        git(root, "init", "-q", "-b", "main")
        write(root, LVS, lvs_doc())
        write(root, DRC, drc_doc())
        write(root, WAIVERS, {"waivers": []})
        write(root, "README.md", "fixture\n")
        if mutate_base is not None:
            mutate_base(root)
        commit_all(root, "base")
        git(root, "checkout", "-q", "-b", "topic")
        if mutate_head is not None:
            mutate_head(root)
        commit_all(root, "head")
        if base_ref == "@BASE_SHA":
            base_ref = git(root, "rev-parse", "main").stdout.strip()
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), "--base-ref", base_ref, *extra],
            capture_output=True, text=True,
        )


def output(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout + proc.stderr


class ReportRegression(unittest.TestCase):
    # -- baseline ------------------------------------------------------------

    def test_unchanged_reports_pass(self):
        def mutate(root):
            write(root, "README.md", "a non-report change\n")
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("no committed lvs/drc report changed", output(r))

    # -- the issue-#591 shape --------------------------------------------------

    def test_lvs_regression_591_shape_fails(self):
        r = run_case(lambda root: write(root, LVS, lvs_regressed_591()))
        self.assertEqual(r.returncode, 1, output(r))
        text = output(r)
        self.assertIn("lvs.error_count regressed 4 → 1022", text)
        self.assertIn("lvs.nets.matched regressed 253 → 2", text)
        self.assertIn("lvs.devices.matched regressed 263 → 6", text)
        self.assertIn("lvs.category_error_counts.net.unmatched regressed 0 → 504", text)
        self.assertIn("lvs.category_error_counts.device.unmatched regressed 3 → 517", text)

    def test_lvs_matched_drop_alone_fails(self):
        def mutate(root):
            doc = lvs_doc(nets_matched=100)
            doc["category_error_counts"] = {}
            write(root, LVS, doc)
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("lvs.nets.matched regressed 253 → 100", output(r))

    def test_lvs_improvement_passes(self):
        def mutate(root):
            write(root, LVS, lvs_doc(error_count=0, nets_matched=257, devices_matched=266,
                                     category={}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))

    def test_lvs_equal_passes(self):
        def mutate(root):
            doc = lvs_doc()
            doc["provenance"] = {"klt_version": "0.30.13"}  # re-mint, same counts
            write(root, LVS, doc)
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("no regression against", output(r))

    # -- per-class edge cases ----------------------------------------------------

    def test_category_key_only_in_head_fails(self):
        def mutate_base(root):
            doc = lvs_doc()
            del doc["category_error_counts"]
            write(root, LVS, doc)
        def mutate_head(root):
            write(root, LVS, lvs_doc(category={"net.unmatched": 504}))
        r = run_case(mutate_head, mutate_base)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("lvs.category_error_counts.net.unmatched regressed 0 → 504", output(r))

    def test_category_class_vanishing_is_improvement(self):
        def mutate(root):
            write(root, LVS, lvs_doc(category={"topology": 1}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))

    def test_drc_new_rule_class_fails(self):
        def mutate(root):
            write(root, DRC, drc_doc(violation_count=23,
                                     rule_counts={"metal1.enclosing.cont.1": 18,
                                                  "via1.width.1": 5}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("drc.violation_count regressed 18 → 23", output(r))
        self.assertIn("drc.rule_counts.via1.width.1 regressed 0 → 5", output(r))

    def test_drc_improvement_passes(self):
        def mutate(root):
            write(root, DRC, drc_doc(violation_count=0, rule_counts={}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))

    # -- non-integer per-class values (issue #601) ------------------------------

    def test_lvs_bad_class_value_beside_a_good_one_fails(self):
        def mutate(root):
            write(root, LVS, lvs_doc(category={"device.unmatched": "many", "topology": 1}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn(
            "category_error_counts.device.unmatched is 'many', not an integer", output(r))

    def test_lvs_bad_class_value_as_sole_entry_fails(self):
        def mutate(root):
            write(root, LVS, lvs_doc(category={"device.unmatched": "many"}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("category_error_counts.device.unmatched is 'many'", output(r))
        self.assertIn("no usable integer values", output(r))

    def test_drc_bad_rule_value_beside_a_good_one_fails(self):
        def mutate(root):
            write(root, DRC, drc_doc(rule_counts={"metal1.enclosing.cont.1": 18,
                                                  "via1.width.1": "lots"}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("rule_counts.via1.width.1 is 'lots', not an integer", output(r))

    def test_drc_bad_rule_value_as_sole_entry_fails(self):
        def mutate(root):
            write(root, DRC, drc_doc(rule_counts={"metal1.enclosing.cont.1": "lots"}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("rule_counts.metal1.enclosing.cont.1 is 'lots'", output(r))
        self.assertIn("no usable integer values", output(r))

    def test_bool_rule_value_is_not_an_integer(self):
        def mutate(root):
            write(root, DRC, drc_doc(rule_counts={"metal1.enclosing.cont.1": True}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("rule_counts.metal1.enclosing.cont.1 is True, not an integer", output(r))

    def test_null_class_value_is_not_an_integer(self):
        def mutate(root):
            write(root, LVS, lvs_doc(category={"device.unmatched": None, "topology": 1}))
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("category_error_counts.device.unmatched is None, not an integer",
                      output(r))

    def test_bad_base_class_value_notes_and_still_compares_against_zero(self):
        def mutate_base(root):
            write(root, LVS, lvs_doc(category={"device.unmatched": "many", "topology": 1}))

        def mutate_head(root):
            write(root, LVS, lvs_doc(category={"device.unmatched": 5, "topology": 1}))
        r = run_case(mutate_head, mutate_base)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("merge-base category_error_counts.device.unmatched is 'many'", output(r))
        self.assertIn("lvs.category_error_counts.device.unmatched regressed 0 → 5", output(r))

    def test_class_mapping_absent_at_head_keeps_missing_note(self):
        def mutate(root):
            doc = lvs_doc()
            del doc["category_error_counts"]
            write(root, LVS, doc)
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("category_error_counts mapping missing at the working-tree side",
                      output(r))

    def test_head_only_error_count_names_the_implicit_zero(self):
        def mutate_base(root):
            doc = lvs_doc()
            del doc["error_count"]
            write(root, LVS, doc)

        def mutate_head(root):
            write(root, LVS, lvs_doc())
        r = run_case(mutate_head, mutate_base)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn(
            "lvs.error_count reads 4 at the working tree but the merge base recorded "
            "no value", output(r))

    # -- waiver discipline -----------------------------------------------------

    def test_waived_regression_passes_with_note(self):
        def mutate(root):
            write(root, LVS, lvs_regressed_591())
            write(root, WAIVERS, {"waivers": [{
                "report": LVS,
                "expected": dict(REGRESSED_591_EXPECTED),
                "issue": "#600",
                "reason": "deliberate: kept until the klayout-tools#6313 re-mint lands",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("REGRESSED (waived, #600)", output(r))

    def test_waiver_with_stale_value_fails(self):
        def mutate(root):
            write(root, LVS, lvs_regressed_591())
            expected = dict(REGRESSED_591_EXPECTED)
            expected["lvs.error_count"] = 999  # the report re-minted past the waiver
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": expected, "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("records lvs.error_count=999 but the report now reads 1022", output(r))

    def test_waiver_missing_a_regressed_predicate_fails(self):
        def mutate(root):
            write(root, LVS, lvs_regressed_591())
            write(root, WAIVERS, {"waivers": [{
                "report": LVS,
                "expected": {"lvs.error_count": 1022},
                "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("omits regressing predicate(s)", output(r))
        self.assertIn("lvs.category_error_counts.net.unmatched (0 → 504)", output(r))

    def test_waiver_naming_a_non_regressing_value_fails(self):
        def mutate(root):
            write(root, LVS, lvs_regressed_591())
            expected = dict(REGRESSED_591_EXPECTED)
            expected["lvs.category_error_counts.topology"] = 1  # 1 → 1, not a regression
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": expected, "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("names value(s) that no longer regress", output(r))

    def test_obsolete_waiver_fails(self):
        def mutate(root):
            write(root, LVS, lvs_doc(error_count=0, nets_matched=257, devices_matched=266,
                                     category={}))
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": {"lvs.error_count": 1022},
                "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("waiver is obsolete", output(r))

    def test_unused_waiver_fails(self):
        def mutate(root):
            write(root, "README.md", "unrelated\n")
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": {"lvs.error_count": 1022},
                "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("matches no report this run compared", output(r))

    def test_waiver_missing_issue_is_schema_error(self):
        def mutate(root):
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": {"lvs.error_count": 1022}, "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("missing required key(s): issue", output(r))

    def test_waiver_with_unknown_predicate_is_schema_error(self):
        def mutate(root):
            write(root, WAIVERS, {"waivers": [{
                "report": LVS, "expected": {"pex.netlist_sha256": 7},
                "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("names unknown predicate(s)", output(r))

    def test_waiver_for_unguarded_report_is_schema_error(self):
        def mutate(root):
            write(root, WAIVERS, {"waivers": [{
                "report": "layout/sg13cmos5l-bandgap_top/lvs_report.json",
                "expected": {"lvs.error_count": 7}, "issue": "#600", "reason": "x",
            }]})
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("is not a report this checker guards", output(r))

    # -- structural outcomes ---------------------------------------------------

    def test_new_report_is_a_note_not_a_skip(self):
        def mutate(root):
            write(root, "layout/cell2/lvs_report.json", lvs_doc())
        r = run_case(mutate)
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("new report — no merge-base revision to compare", output(r))

    def test_unparseable_base_copy_fails(self):
        def mutate_base(root):
            write_raw(root, LVS, "{ this is not json")
        def mutate_head(root):
            write(root, LVS, lvs_doc())  # re-minted over an unreadable historical copy
        r = run_case(mutate_head, mutate_base)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("merge-base revision", output(r))
        self.assertIn("does not parse as JSON", output(r))

    def test_unparseable_head_copy_fails(self):
        def mutate(root):
            write_raw(root, LVS, "{ this is not json")
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("working-tree copy does not parse as JSON", output(r))

    def test_deleted_report_fails(self):
        def mutate(root):
            (root / LVS).unlink()
        r = run_case(mutate)
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("deleted relative to main", output(r))

    def test_no_merge_base_skips_loudly_unless_required(self):
        r = run_case(extra=("--base-ref", "no-such-ref"))
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("SKIP: no merge base with no-such-ref", output(r))

        r = run_case(extra=("--base-ref", "no-such-ref", "--require-regression-base"))
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("no merge base with no-such-ref", output(r))

    # -- merge-group wiring (issue #614, ported from sky130-comparator#332) ----
    # On merge_group runs the workflow passes the queue's trial-merge base as
    # a raw sha; an absent/empty base_sha fails in the workflow before the
    # checker runs. The cases below pin the checker contract that wiring
    # relies on: a raw sha compares exactly like the named ref (the unchanged
    # pull_request path every case above exercises), and an empty base handed
    # to the checker anyway fails closed under --require-regression-base.

    def test_merge_group_base_sha_compares_like_a_ref(self):
        def mutate(root):
            write(root, LVS, lvs_regressed_591())
        r = run_case(mutate, base_ref="@BASE_SHA")
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("lvs.error_count regressed 4 → 1022", output(r))

    def test_merge_group_base_sha_clean_range_passes(self):
        def mutate(root):
            write(root, "README.md", "a non-report change\n")
        r = run_case(mutate, base_ref="@BASE_SHA")
        self.assertEqual(r.returncode, 0, output(r))
        self.assertIn("no committed lvs/drc report changed", output(r))

    def test_merge_group_empty_base_sha_fails_closed(self):
        r = run_case(extra=("--base-ref", "", "--require-regression-base"))
        self.assertEqual(r.returncode, 1, output(r))
        self.assertIn("no merge base with", output(r))


if __name__ == "__main__":
    unittest.main()
