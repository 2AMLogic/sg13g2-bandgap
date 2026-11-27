#!/usr/bin/env python3
"""Self-test for the klt-sim harness transformers (issue #297). Stdlib only.

These modules turn `klt sim` reports into the numbers that become
append-only evidence, so they get the same "a checker that cannot fail is no
checker" treatment as the evidence-format checker. Every fixture is tiny and
lives in memory or a temporary directory: no ngspice, no PDK, no network, and
nothing under sim/ is written.

    python3 sim/harness/test_harness_transformers.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boxtc_companion as bxc  # noqa: E402
import enrich_ac_report as ear  # noqa: E402
import enrich_pvt_report as epr  # noqa: E402
import enrich_supply_bench_report as esb  # noqa: E402
import extraction_binding as xb  # noqa: E402
import fixup_batch_report as fbr  # noqa: E402
import klt_sim_evidence as kse  # noqa: E402
from test_evidence_store import FakeStore  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402
import tc_companion as tcc  # noqa: E402


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # resolve(): inline_deck compares resolved include targets against
        # the PDK root, so the fixture root must already be canonical.
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_json(self, rel: str, obj: dict) -> Path:
        return self.write(rel, json.dumps(obj))


# --------------------------------------------------------------------------
# merge_batch_shards.merge
# --------------------------------------------------------------------------


def shard(process: str, statuses: list[str], remote: dict | None = None) -> dict:
    corners = [
        {
            "corner_id": f"{process}/3.300V/{t}C",
            "process": process,
            "temperature_c": t,
            "supply_v": {"Vvdd": 3.3},
            "status": s,
            "measurements": [{"name": "vref_v", "value": 1.2 + k * 1e-3}],
        }
        for k, (t, s) in enumerate(zip((-40, 27, 125), statuses))
    ]
    return report_of(corners, remote)


def report_of(corners: list[dict], remote: dict | None = None) -> dict:
    n = lambda st: sum(1 for c in corners if c["status"] == st)  # noqa: E731
    report = {
        "status": "fail" if n("fail") else ("error" if n("error") else "pass"),
        "corner_count": len(corners),
        "passed": n("pass"),
        "failed": n("fail"),
        "errored": n("error"),
        "corners": corners,
        "provenance": {"klt_version": "0.5.0"},
    }
    if remote is not None:
        report["environment"] = {"remote": remote}
    return report


def want(process: str, n: int = 3) -> list[str]:
    """Normalized expected identities of `shard(process, ...)`'s first n temps."""
    return [f"{process}_{t:g}c_3.30v" for t in (-40, 27, 125)[:n]]


class MergeTests(TempDirCase):
    def test_corners_concatenate_in_argument_order_not_file_order(self) -> None:
        a = self.write_json("z-first.json", shard("hbt_typ", ["pass", "pass"]))
        b = self.write_json("a-second.json", shard("hbt_wcs", ["pass"]))
        exp = want("hbt_typ", 2) + want("hbt_wcs", 1)
        merged = mbs.merge([str(a), str(b)], exp)
        self.assertEqual(
            [c["corner_id"] for c in merged["corners"]],
            ["hbt_typ/3.300V/-40C", "hbt_typ/3.300V/27C", "hbt_wcs/3.300V/-40C"],
        )
        reversed_ = mbs.merge([str(b), str(a)], exp)
        self.assertEqual(reversed_["corners"][0]["corner_id"], "hbt_wcs/3.300V/-40C")

    def test_label_rewrites_process_and_corner_id_prefix(self) -> None:
        # sf/fs share hbt_typ with typ: only the label recovers the repo name.
        typ = self.write_json("typ.json", shard("hbt_typ", ["pass"]))
        sf = self.write_json("sf.json", shard("hbt_typ", ["pass", "pass"]))
        merged = mbs.merge([f"typ={typ}", f"sf={sf}"], want("typ", 1) + want("sf", 2))
        self.assertEqual(
            [(c["process"], c["corner_id"]) for c in merged["corners"]],
            [
                ("typ", "typ/3.300V/-40C"),
                ("sf", "sf/3.300V/-40C"),
                ("sf", "sf/3.300V/27C"),
            ],
        )

    def test_summary_counts_and_status_recomputed(self) -> None:
        p = self.write_json("p.json", shard("typ", ["pass", "pass", "pass"]))
        e = self.write_json("e.json", shard("bcs", ["pass", "error"]))
        f = self.write_json("f.json", shard("wcs", ["fail"]))
        keys = ("corner_count", "passed", "failed", "errored", "status")
        merged = mbs.merge([str(p), str(e)], want("typ") + want("bcs", 2))
        self.assertEqual(
            {k: merged[k] for k in keys},
            {"corner_count": 5, "passed": 4, "failed": 0, "errored": 1, "status": "error"},
        )
        # fail outranks error, whatever order the shards come in
        exp = want("wcs", 1) + want("bcs", 2) + want("typ")
        merged = mbs.merge([str(f), str(e), str(p)], exp)
        self.assertEqual(
            {k: merged[k] for k in keys},
            {"corner_count": 6, "passed": 4, "failed": 1, "errored": 1, "status": "fail"},
        )
        merged = mbs.merge([str(p)], want("typ"))
        self.assertEqual((merged["status"], merged["passed"]), ("pass", 3))
        self.assertTrue(merged["grid"]["complete"])

    def test_remote_becomes_fleet_array_with_a_slot_per_shard(self) -> None:
        local = self.write_json("l.json", shard("typ", ["pass"]))
        r1 = self.write_json("r1.json", shard("bcs", ["pass"], remote={"job_id": "j1"}))
        merged = mbs.merge([str(local), str(r1)], want("typ", 1) + want("bcs", 1))
        self.assertEqual(merged["environment"]["remote"], {"fleet": [None, {"job_id": "j1"}]})
        all_local = mbs.merge([str(local)], want("typ", 1))
        self.assertNotIn("remote", all_local["environment"])

    def test_diagnostics_and_metrics_cover_all_shards(self) -> None:
        first = shard("typ", ["pass", "pass"])
        warning = {"code": "singular_matrix", "severity": "warning"}
        first["corners"][0]["diagnostics"] = [warning]
        first["corners"][1]["diagnostics"] = []
        first["diagnostic_counts"] = {
            "by_code": {"singular_matrix": 1},
            "by_severity": {"warning": 1},
            "corners_with_diagnostics": 1,
        }
        first["metrics"] = {"sim__corner__count": 2, "shard_only": 12}
        second = shard("wcs", ["fail", "error"])
        second["corners"][1]["diagnostics"] = [
            warning,
            {"code": "simulation_failed", "severity": "error"},
        ]
        a = self.write_json("first.json", first)
        b = self.write_json("second.json", second)
        merged = mbs.merge([str(a), str(b)], want("typ", 2) + want("wcs", 2))
        self.assertEqual(
            merged["diagnostic_counts"],
            {
                "by_code": {"singular_matrix": 2, "simulation_failed": 1},
                "by_severity": {"warning": 2, "error": 1},
                "corners_with_diagnostics": 2,
            },
        )
        self.assertEqual(
            merged["metrics"],
            {
                "sim__corner__count": 4,
                "sim__corner__passed_count": 2,
                "sim__corner__failed_count": 1,
                "sim__corner__errored_count": 1,
                "sim__corner__inconclusive_count": 0,
            },
        )

    def test_refresh_after_regrade_without_declared_measurements(self) -> None:
        path = self.write_json("typ.json", shard("typ", ["pass"]))
        merged = mbs.merge([str(path)], want("typ", 1))
        self.assertEqual(
            merged["diagnostic_counts"],
            {"by_code": {}, "by_severity": {}, "corners_with_diagnostics": 0},
        )
        epr.enrich(merged)  # missing operands turn the pass into a fail
        mbs.refresh_rollup(merged)
        self.assertEqual(merged["metrics"]["sim__corner__passed_count"], 0)
        self.assertEqual(merged["metrics"]["sim__corner__failed_count"], 1)
        self.assertEqual(
            merged["diagnostic_counts"],
            {
                "by_code": {"derived_columns_missing": 1},
                "by_severity": {"unknown": 1},
                "corners_with_diagnostics": 1,
            },
        )

    def test_refresh_counts_inconclusive_from_corner_status(self) -> None:
        path = self.write_json("typ.json", shard("typ", ["pass"]))
        merged = mbs.merge([str(path)], want("typ", 1))
        merged["corners"][0]["status"] = "inconclusive"
        mbs.refresh_rollup(merged)
        self.assertEqual(merged["metrics"]["sim__corner__passed_count"], 0)
        self.assertEqual(merged["metrics"]["sim__corner__inconclusive_count"], 1)

    def test_provenance_note_counts_shards_and_keeps_existing_fields(self) -> None:
        paths = [str(self.write_json(f"{n}.json", shard(n, ["pass"]))) for n in ("a", "b", "c")]
        prov = mbs.merge(paths, want("a", 1) + want("b", 1) + want("c", 1))["provenance"]
        self.assertEqual(prov["klt_version"], "0.5.0")
        self.assertIn("merged from 3 per-process batch reports", prov["batch_shard_merge"])

    def test_no_reports_is_an_error(self) -> None:
        with self.assertRaises(SystemExit):
            mbs.merge([], want("typ"))

    def test_expected_grid_is_mandatory(self) -> None:
        p = self.write_json("p.json", shard("typ", ["pass"]))
        with self.assertRaises(SystemExit):
            mbs.merge([str(p)], None)


class RollupMergeTests(TempDirCase):
    """Issue #629: the merged report re-aggregates the request-declared
    measurements[] rollup across every corner, by klt sim's own rule, so the
    committed report is a citable grid envelope."""

    @staticmethod
    def rollup_shard(process: str, points: list[tuple[int, str, dict]]) -> dict:
        corners = []
        for temp, status, m in points:
            corners.append(
                {
                    "corner_id": f"{process}/3.300V/{temp}C",
                    "process": process,
                    "temperature_c": temp,
                    "supply_v": {"Vvdd": 3.3},
                    "status": "fail" if m.get("status") == "fail" else status,
                    "measurements": [dict(m, name="vref_v")],
                }
            )
        n = lambda s: sum(1 for c in corners if c["status"] == s)  # noqa: E731
        return {
            "schema_version": 3,
            "status": "fail" if n("fail") else ("error" if n("error") else "pass"),
            "corner_count": len(corners),
            "passed": n("pass"),
            "failed": n("fail"),
            "errored": n("error"),
            "corners": corners,
            "measurements": [
                {
                    "name": "vref_v",
                    "unit": "V",
                    "limits": {"min": 0.882, "max": 1.218},
                    "status": "pass",
                    "spec_row": "output-reference-nominal",
                }
            ],
            "coverage": {"measurements_declared": 1, "measurements_with_limits": 1},
        }

    def test_rollup_reaggregates_across_shards_with_worst_case(self) -> None:
        a = self.write_json(
            "a.json",
            self.rollup_shard("typ", [(-40, "pass", {"value": 1.05, "status": "pass", "margin": 0.168}),
                                      (27, "pass", {"value": 1.06, "status": "pass", "margin": 0.158})]),
        )
        b = self.write_json(
            "b.json",
            self.rollup_shard("wcs", [(-40, "fail", {"value": 1.30, "status": "fail", "margin": -0.082})]),
        )
        merged = mbs.merge(
            [str(a), str(b)], ["typ_-40c_3.30v", "typ_27c_3.30v", "wcs_-40c_3.30v"]
        )
        (entry,) = merged["measurements"]
        self.assertEqual(entry["name"], "vref_v")
        self.assertEqual(entry["status"], "fail")
        self.assertEqual(entry["spec_row"], "output-reference-nominal")
        self.assertEqual(entry["limits"], {"min": 0.882, "max": 1.218})
        self.assertEqual(
            entry["worst_case"],
            {"corner_id": "wcs/3.300V/-40C", "value": 1.30, "margin": -0.082},
        )
        cov = merged["coverage"]
        self.assertEqual(cov["corners_simulated"], 3)
        self.assertEqual(cov["measurements_declared"], 1)
        self.assertEqual(cov["measurements_with_limits"], 1)
        self.assertFalse(cov["nothing_checked"])
        self.assertEqual(len(cov["checked"]), 6)  # 3 corners x 2 bounds

    def test_all_passing_corners_roll_up_pass(self) -> None:
        a = self.write_json(
            "a.json",
            self.rollup_shard("typ", [(-40, "pass", {"value": 1.05, "status": "pass", "margin": 0.1})]),
        )
        b = self.write_json(
            "b.json",
            self.rollup_shard("wcs", [(125, "pass", {"value": 1.04, "status": "pass", "margin": 0.09})]),
        )
        merged = mbs.merge([str(a), str(b)], ["typ_-40c_3.30v", "wcs_125c_3.30v"])
        self.assertEqual(merged["measurements"][0]["status"], "pass")
        self.assertEqual(
            merged["measurements"][0]["worst_case"]["corner_id"], "wcs/3.300V/125C"
        )

    def test_shards_disagreeing_on_declaration_refuse_the_merge(self) -> None:
        a = self.write_json(
            "a.json",
            self.rollup_shard("typ", [(-40, "pass", {"value": 1.05, "status": "pass", "margin": 0.1})]),
        )
        other = self.rollup_shard(
            "wcs", [(125, "pass", {"value": 1.04, "status": "pass", "margin": 0.1})]
        )
        other["measurements"][0]["limits"] = {"max": 1.218}
        b = self.write_json("b.json", other)
        with self.assertRaises(mbs.ShardError) as ctx:
            mbs.merge([str(a), str(b)], ["typ_-40c_3.30v", "wcs_125c_3.30v"])
        self.assertIn("disagree on the declared measurements", "\n".join(ctx.exception.problems))

    def test_unlimited_rollup_counts_zero_limited(self) -> None:
        shard = self.rollup_shard("typ", [(-40, "pass", {"value": 1.05, "status": "pass", "margin": None})])
        del shard["measurements"][0]["limits"]
        a = self.write_json("a.json", shard)
        merged = mbs.merge([str(a)], ["typ_-40c_3.30v"])
        self.assertEqual(merged["coverage"]["measurements_with_limits"], 0)
        self.assertEqual(merged["coverage"]["checked"], [])
        self.assertFalse(merged["coverage"]["nothing_checked"])


class GridContractTests(TempDirCase):
    """Defect injection for issue #327: nothing incomplete becomes PASS."""

    def refused(self, paths: list[str], expected: list[str], needle: str, **kw) -> None:
        with self.assertRaises(mbs.ShardError) as ctx:
            mbs.merge(paths, expected, **kw)
        self.assertIn(needle, "\n".join(ctx.exception.problems))

    def test_empty_error_shard_cannot_become_pass(self) -> None:
        good = self.write_json("g.json", shard("typ", ["pass"]))
        empty = self.write_json(
            "e.json", {"status": "error", "corner_count": 0, "passed": 0, "failed": 0, "errored": 0, "corners": []}
        )
        self.refused([str(good), str(empty)], want("typ", 1), "empty shard")

    def test_unknown_corner_status_fails_validation(self) -> None:
        bad = shard("typ", ["pass", "pass"])
        bad["corners"][1]["status"] = "skipped"
        p = self.write_json("b.json", bad)
        self.refused([str(p)], want("typ", 2), "unknown status 'skipped'")

    def test_unknown_report_status_fails_validation(self) -> None:
        bad = shard("typ", ["pass"])
        bad["status"] = "weird"
        p = self.write_json("b.json", bad)
        self.refused([str(p)], want("typ", 1), "unknown report status")

    def test_duplicate_corner_within_shard(self) -> None:
        bad = shard("typ", ["pass", "pass"])
        bad["corners"][1]["corner_id"] = bad["corners"][0]["corner_id"]
        p = self.write_json("b.json", bad)
        self.refused([str(p)], want("typ", 2), "duplicate corner_id")

    def test_duplicate_normalized_identities_across_shards(self) -> None:
        a = self.write_json("a.json", shard("hbt_typ", ["pass"]))
        b = self.write_json("b.json", shard("hbt_typ", ["pass"]))
        # same raw process in both shards: identities collide after merge
        self.refused([str(a), str(b)], want("hbt_typ", 1), "duplicate normalized point identities")
        # a label that disagrees with the shard but collides with another one
        self.refused([f"typ={a}", f"typ={b}"], want("typ", 1), "duplicate normalized point identities")

    def test_inconsistent_counts_and_status(self) -> None:
        for key, value, needle in (
            ("corner_count", 9, "corner_count=9"),
            ("passed", 1, "passed=1"),
            ("errored", 1, "errored=1"),
            ("status", "error", "inconsistent status"),
        ):
            bad = shard("typ", ["pass", "pass"])
            bad[key] = value
            p = self.write_json(f"{key}.json", bad)
            self.refused([str(p)], want("typ", 2), needle)
        masked = shard("typ", ["pass", "fail"])
        masked["status"] = "pass"
        masked["failed"] = 1
        p = self.write_json("masked.json", masked)
        self.refused([str(p)], want("typ", 2), "inconsistent status")

    def test_missing_point_detected_even_when_all_returned_points_pass(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass", "pass", "pass"]))
        b = self.write_json("b.json", shard("bcs", ["pass", "pass"]))  # 27/125 only 2 of 3
        self.refused([str(a), str(b)], want("typ") + want("bcs"), "requested point(s) missing")
        self.refused([str(a)], want("typ") + want("bcs"), "bcs_-40c_3.30v")  # omitted shard

    def test_unexpected_point_blocks_publication(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass", "pass", "pass"]))
        self.refused([str(a)], want("typ", 2), "not in the requested grid")

    def test_nothing_written_before_diagnostics(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass"]))
        out = self.tmp / "merged.json"
        rc = None
        with self.assertRaises(SystemExit):
            rc = mbs.main(["-o", str(out), "--expect-process", "typ", "--expect-supplies", "3.3",
                           "--expect-temps=-40,27", str(a)])
        self.assertIsNone(rc)
        self.assertFalse(out.exists())

    def test_allow_incomplete_writes_diagnostic_the_adapter_refuses(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass"]))
        merged = mbs.merge([str(a)], want("typ", 2), allow_incomplete=True)
        self.assertEqual(merged["status"], "incomplete")
        self.assertFalse(merged["grid"]["complete"])
        self.assertEqual(merged["grid"]["missing"], ["typ_27c_3.30v"])
        # enrichers recompute status from corners; the grid block must still block
        merged["status"] = "pass"
        with self.assertRaises(SystemExit) as ctx:
            kse.verify_grid(merged)
        self.assertIn("incomplete", str(ctx.exception))

    def test_failed_and_errored_points_are_preserved_not_dropped(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass", "fail", "error"]))
        merged = mbs.merge([str(a)], want("typ"))
        self.assertEqual([c["status"] for c in merged["corners"]], ["pass", "fail", "error"])
        self.assertEqual(merged["status"], "fail")
        self.assertTrue(merged["grid"]["complete"])

    def test_valid_smaller_grid_with_its_own_explicit_grid(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass", "pass"]))
        grid = self.write_json("grid.json", {"points": want("typ", 2)})
        out = self.tmp / "m.json"
        self.assertEqual(mbs.main(["-o", str(out), "--expect-grid", str(grid), str(a)]), 0)
        merged = json.loads(out.read_text())
        self.assertEqual((merged["status"], merged["corner_count"]), ("pass", 2))
        axes = self.write_json(
            "axes.json", {"axes": {"process": ["typ"], "supply_v": [3.3], "temperature_c": [-40, 27]}}
        )
        self.assertEqual(mbs.load_expected(str(axes)), want("typ", 2))

    def test_supply_hint_identifies_corners_without_a_supply_axis(self) -> None:
        # PWL-ramp benches: shards carry no supply_v; ids repeat across shards
        def novdd(proc: str) -> dict:
            r = shard(proc, ["pass"])
            for c in r["corners"]:
                c["supply_v"] = {}
                c["corner_id"] = f"{proc}/novdd/{c['temperature_c']}C"
            return r

        a = self.write_json("a.json", novdd("hbt_typ"))
        b = self.write_json("b.json", novdd("hbt_typ"))
        exp = ["typ_-40c_2.97v", "typ_-40c_3.30v"]
        merged = mbs.merge([f"typ@2.97={a}", f"typ@3.30={b}"], exp)
        self.assertTrue(merged["grid"]["complete"])
        self.refused([f"typ={a}"], exp, "no identifiable")

    def test_identity_matches_adapter_grammar(self) -> None:
        for corner in (
            {"process": "typ", "temperature_c": 27, "supply_v": {"Vvdd": 3.3}},
            {"process": "wcs", "temperature_c": -40.0, "supply_v": {"V": 2.97}},
        ):
            self.assertEqual(mbs.point_identity(corner), kse.corner_id(corner)[0])


class AdapterGridTests(TempDirCase):
    def test_adapter_blocks_missing_point_with_all_passing(self) -> None:
        r = shard("typ", ["pass", "pass"])
        with self.assertRaises(SystemExit) as ctx:
            kse.verify_grid(r, want("typ"))
        self.assertIn("missing", str(ctx.exception))

    def test_adapter_uses_embedded_grid_and_accepts_complete(self) -> None:
        a = self.write_json("a.json", shard("typ", ["pass"]))
        merged = mbs.merge([str(a)], want("typ", 1))
        kse.verify_grid(merged)
        merged["corners"][0]["temperature_c"] = 85  # tampered after merge
        with self.assertRaises(SystemExit):
            kse.verify_grid(merged)

    def test_adapter_rejects_empty_error_report(self) -> None:
        with self.assertRaises(SystemExit):
            kse.verify_grid({"status": "error", "corners": []})

    def test_report_without_a_grid_is_checked_for_structure_only(self) -> None:
        kse.verify_grid(shard("typ", ["pass", "fail"]))


# --------------------------------------------------------------------------
# fixup_batch_report.fixup
# --------------------------------------------------------------------------


class FixupTests(TempDirCase):
    def run_fixup(self, deck_text: str, *, relative: bool = False) -> tuple[dict, str]:
        deck = self.write("work/decks/typ_27.cir", deck_text)
        ref = "decks/typ_27.cir" if relative else str(deck)
        report = self.write_json(
            "work/report.json",
            {"corners": [{"corner_id": "typ/3.300V/27C", "artifacts": {"deck": ref}}]},
        )
        out = fbr.fixup(
            report, Path("/local/body-typ.spice"), "/opt/pdk", "/home/u/pdk", self.tmp / "fixed"
        )
        new_deck = Path(out["corners"][0]["artifacts"]["deck"])
        return out, new_deck.read_text(encoding="utf-8")

    def test_quoted_runner_include_repointed_at_local_body(self) -> None:
        _, text = self.run_fixup('.include "/var/tmp/eda-job-42/inputs/netlist.cir"\n.end\n')
        self.assertEqual(text, '.include "/local/body-typ.spice"\n.end\n')

    def test_bare_runner_include_repointed_at_local_body(self) -> None:
        _, text = self.run_fixup("  .include /var/tmp/eda-job-42/inputs/netlist.cir\n.end\n")
        self.assertEqual(text, "  .include /local/body-typ.spice\n.end\n")

    def test_runner_pdk_root_rewritten_to_local(self) -> None:
        _, text = self.run_fixup(
            '.lib "/opt/pdk/ihp-sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt\n'
        )
        self.assertEqual(
            text, '.lib "/home/u/pdk/ihp-sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt\n'
        )

    def test_other_includes_untouched(self) -> None:
        deck = '.include "/somewhere/else.cir"\n.include "/opt/pdkx/foo.lib"\n'
        _, text = self.run_fixup(deck)
        self.assertEqual(text, deck)

    def test_relative_deck_resolved_against_report_dir_and_artifact_repointed(self) -> None:
        out, text = self.run_fixup(
            '.include "/var/tmp/eda-job-1/inputs/netlist.cir"\n', relative=True
        )
        self.assertEqual(text, '.include "/local/body-typ.spice"\n')
        self.assertEqual(
            out["corners"][0]["artifacts"]["deck"], str(self.tmp / "fixed" / "typ_3.300V_27C.cir")
        )
        # the original deck is a runner artifact: never edited in place
        self.assertIn(
            "eda-job-1", (self.tmp / "work/decks/typ_27.cir").read_text(encoding="utf-8")
        )

    def test_missing_or_absent_deck_left_alone(self) -> None:
        report = self.write_json(
            "r.json",
            {
                "corners": [
                    {"corner_id": "a", "artifacts": {"deck": str(self.tmp / "nope.cir")}},
                    {"corner_id": "b", "artifacts": {}},
                ]
            },
        )
        out = fbr.fixup(report, Path("/b.spice"), "/opt/pdk", "/p", self.tmp / "fixed")
        self.assertEqual(out["corners"][0]["artifacts"]["deck"], str(self.tmp / "nope.cir"))
        self.assertEqual(out["corners"][1]["artifacts"], {})


# --------------------------------------------------------------------------
# enrich_pvt_report.enrich
# --------------------------------------------------------------------------


def pvt_corner(cid: str = "typ/3.30V/27C", status: str = "pass", **over: float) -> dict:
    meas = {
        "sns1_v": 0.700,
        "sns2_v": 0.695,      # dvsns 5 mV
        "vref_2ms_v": 1.2000,
        "vref_3ms_v": 1.2004,  # settle 0.4 mV
        "det_v": 0.10,         # <= 0.2 * 3.3
        "i_mkfb_a": 1e-9,
        "fb_v": 1.0,
    }
    meas.update(over)
    return {
        "corner_id": cid,
        "status": status,
        "measurements": [{"name": k, "value": v} for k, v in meas.items() if v is not None],
    }


def meas(corner: dict) -> dict[str, float]:
    return {m["name"]: m["value"] for m in corner["measurements"]}


class EnrichTests(TempDirCase):
    def enrich_one(self, corner: dict) -> tuple[dict, dict]:
        report = epr.enrich({"status": "pass", "corners": [corner]})
        return report, report["corners"][0]

    def assert_verdict(self, corner: dict, expected_fail: list[str]) -> None:
        _, c = self.enrich_one(corner)
        if expected_fail:
            self.assertEqual(c["status"], "fail")
            self.assertEqual(c["diagnostics"][0]["code"], "closed_loop_verdict")
            self.assertEqual(c["diagnostics"][0]["message"], "; ".join(expected_fail))
        else:
            self.assertEqual(c["status"], "pass", c.get("diagnostics"))

    def test_derived_columns_appended(self) -> None:
        _, c = self.enrich_one(pvt_corner())
        got = meas(c)
        self.assertAlmostEqual(got["dvsns_v"], 0.005, places=12)
        self.assertAlmostEqual(got["vref_settle_delta_v"], 0.0004, places=12)
        derived = [m for m in c["measurements"] if m["name"] in ("dvsns_v", "vref_settle_delta_v")]
        self.assertTrue(all(m["spice"].startswith("derived: ") for m in derived))
        self.assertEqual(c["status"], "pass")

    def test_derived_columns_are_absolute_values(self) -> None:
        _, c = self.enrich_one(pvt_corner(sns1_v=0.695, sns2_v=0.700, vref_3ms_v=1.1996))
        got = meas(c)
        self.assertGreater(got["dvsns_v"], 0)
        self.assertGreater(got["vref_settle_delta_v"], 0)

    def test_loop_closure_boundary(self) -> None:
        self.assert_verdict(pvt_corner(sns1_v=0.7199, sns2_v=0.700), [])
        self.assert_verdict(pvt_corner(sns1_v=0.7201, sns2_v=0.700), ["loop_not_closed"])

    def test_settle_boundary(self) -> None:
        self.assert_verdict(pvt_corner(vref_3ms_v=1.20099), [])
        self.assert_verdict(pvt_corner(vref_3ms_v=1.20101), ["not_settled"])

    def test_startup_release_uses_corner_vdd(self) -> None:
        # 0.2 * 3.30 V = 0.66 V
        self.assert_verdict(pvt_corner(det_v=0.65), [])
        self.assert_verdict(pvt_corner(det_v=0.67), ["startup_not_released"])
        self.assert_verdict(pvt_corner(i_mkfb_a=-60e-9), ["startup_not_released"])
        # same det at a 3.63 V corner is released (0.726 V threshold)
        self.assert_verdict(pvt_corner(cid="typ/3.63V/27C", det_v=0.67), [])

    def test_fb_rail_window(self) -> None:
        self.assert_verdict(pvt_corner(fb_v=0.049), ["fb_railed"])
        self.assert_verdict(pvt_corner(fb_v=3.30 - 0.049), ["fb_railed"])
        self.assert_verdict(pvt_corner(fb_v=0.051), [])

    def test_every_tripped_criterion_is_named(self) -> None:
        self.assert_verdict(
            pvt_corner(det_v=3.0, sns1_v=0.9, fb_v=0.0, vref_3ms_v=1.3),
            ["startup_not_released", "loop_not_closed", "fb_railed", "not_settled"],
        )

    def test_missing_operand_fails_with_its_own_code(self) -> None:
        _, c = self.enrich_one(pvt_corner(vref_2ms_v=None))
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["code"], "derived_columns_missing")
        self.assertNotIn("dvsns_v", meas(c))

    def test_non_pass_corner_not_regraded(self) -> None:
        _, c = self.enrich_one(pvt_corner(status="error", sns1_v=0.9))
        self.assertEqual(c["status"], "error")
        self.assertNotIn("dvsns_v", meas(c))

    def test_top_level_counts_recomputed(self) -> None:
        report = epr.enrich(
            {
                "status": "pass",
                "passed": 99,
                "corners": [
                    pvt_corner(),
                    pvt_corner(cid="wcs/3.30V/125C", sns1_v=0.9),
                    pvt_corner(cid="bcs/3.30V/-40C", status="error"),
                ],
            }
        )
        self.assertEqual(
            {k: report[k] for k in ("corner_count", "passed", "failed", "errored", "status")},
            {"corner_count": 3, "passed": 1, "failed": 1, "errored": 1, "status": "fail"},
        )
        report = epr.enrich({"corners": [pvt_corner(), pvt_corner(status="error")]})
        self.assertEqual(report["status"], "error")

    def test_novdd_corner_takes_supply_from_included_body_pwl(self) -> None:
        self.write("body.spice", "Vvdd vdd 0 PWL(0 0 10u 3.63)\n")
        deck = self.write("deck.cir", '.include "body.spice"\n')
        c = pvt_corner(cid="typ/novdd/27C", det_v=0.70)  # released only at 3.63 V
        c["artifacts"] = {"deck": str(deck)}
        _, out = self.enrich_one(c)
        self.assertEqual(out["corner_id"], "typ/3.63V/27C")
        self.assertEqual(out["supply_v"], {"Vvdd": 3.63})
        self.assertEqual(out["status"], "pass", out.get("diagnostics"))


# --------------------------------------------------------------------------
# klt_sim_evidence record shaping
# --------------------------------------------------------------------------


class EnrichSupplyBenchTests(unittest.TestCase):
    """enrich_supply_bench_report.enrich (issue #414): the Iq and Startup benches."""

    @staticmethod
    def corner(bench: str, **over: float) -> dict:
        if bench == "iq":
            m = {"fb_v": 1.0, "sns1_v": 0.700, "sns2_v": 0.695, "det_v": 0.1,
                 "i_mkfb_a": 1e-9, "iq_2ms_a": -2.8e-5, "iq_3ms_a": -2.8e-5, "iq_avg_a": -2.8e-5}
        else:
            m = {"fb_final_v": 1.0, "sns1_final_v": 0.700, "sns2_final_v": 0.695,
                 "det_final_v": 0.1, "i_mkfb_final_a": 1e-9, "vref_final_v": 1.04}
        m.update(over)
        return {"corner_id": "typ/3.30V/27C", "status": "pass",
                "measurements": [{"name": k, "value": v} for k, v in m.items()]}

    def run_one(self, bench: str, **over: float) -> dict:
        report = esb.enrich({"status": "pass", "corners": [self.corner(bench, **over)]}, bench)
        return report["corners"][0]

    def test_iq_reports_magnitudes_and_derived_columns(self) -> None:
        c = self.run_one("iq", iq_3ms_a=-2.80005e-5)
        got = meas(c)
        self.assertEqual(c["status"], "pass", c.get("diagnostics"))
        self.assertAlmostEqual(got["iq_avg_a"], 2.8e-5, places=12)
        self.assertAlmostEqual(got["iq_settle_delta_a"], 5e-10, places=14)
        self.assertAlmostEqual(got["dvsns_v"], 0.005, places=12)

    def test_iq_not_settled_over_100na(self) -> None:
        c = self.run_one("iq", iq_3ms_a=-2.82e-5)
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["message"], "not_settled")

    @staticmethod
    def graded_iq_report(
        value: float, margin: float, corner_status: str = "pass",
        graded_sample: str | None = None,
    ) -> dict:
        """A merged iq report whose request grades ``iq_avg_a`` against limits.

        The shape klt sim plus the shard merger produce since issue #629:
        corner measurements carry klt's own grading (``status``/``margin``
        derived from the *signed* value against the request's limits) and the
        declared rollup carries those ``limits``. Issue #646: the enricher
        must leave such a measurement's value exactly as graded, so value,
        limits, margin and status keep re-deriving each other in the
        committed envelope.

        ``graded_sample`` (issue #720) also grades ``iq_2ms_a`` or
        ``iq_3ms_a`` against the same limits, as a request that limits a time
        sample does; all three readings share ``value``.
        """
        meas_status = "pass" if margin >= 0 else "fail"
        measurements = [
            {"name": "fb_v", "value": 1.0, "unit": None, "status": "pass", "margin": None},
            {"name": "sns1_v", "value": 0.700, "unit": None, "status": "pass", "margin": None},
            {"name": "sns2_v", "value": 0.695, "unit": None, "status": "pass", "margin": None},
            {"name": "det_v", "value": 0.1, "unit": None, "status": "pass", "margin": None},
            {"name": "i_mkfb_a", "value": 1e-9, "unit": None, "status": "pass", "margin": None},
            {"name": "iq_2ms_a", "value": value, "unit": None, "status": "pass", "margin": None},
            {"name": "iq_3ms_a", "value": value, "unit": None, "status": "pass", "margin": None},
            {"name": "iq_avg_a", "value": value, "unit": "A", "status": meas_status, "margin": margin},
        ]
        rollup = [{
            "name": "iq_avg_a", "unit": "A", "limits": {"min": -5e-05},
            "status": meas_status, "spec_row": "iq",
            "worst_case": {"corner_id": "bcs/3.63V/125C", "value": value, "margin": margin},
        }]
        if graded_sample is not None:
            reading = next(m for m in measurements if m["name"] == graded_sample)
            reading.update(unit="A", status=meas_status, margin=margin)
            rollup.append(dict(rollup[0], name=graded_sample))
        return {
            "status": corner_status,
            "corners": [{"corner_id": "bcs/3.63V/125C", "status": corner_status,
                         "measurements": measurements}],
            "measurements": rollup,
        }

    def test_iq_limit_bearing_measurement_keeps_graded_sign(self) -> None:
        report = self.graded_iq_report(-4.2e-5, margin=-4.2e-5 - (-5e-5))
        out = esb.enrich(report, "iq")
        c = out["corners"][0]
        self.assertEqual(c["status"], "pass", c.get("diagnostics"))
        m = [m for m in c["measurements"] if m["name"] == "iq_avg_a"][0]
        # the graded value ships as klt sim reported it -- sign kept
        self.assertAlmostEqual(m["value"], -4.2e-5, places=15)
        self.assertNotIn("magnitude", m.get("spice", ""))
        # value/limits/margin re-derive the status: margin == value - min >= 0
        self.assertAlmostEqual(m["margin"], m["value"] - (-5e-5), places=15)
        self.assertGreaterEqual(m["margin"], 0.0)
        self.assertEqual(m["status"], "pass")
        # the limit-less magnitude behaviour is unchanged in the same report
        self.assertAlmostEqual(meas(c)["iq_2ms_a"], 4.2e-5, places=15)
        self.assertAlmostEqual(meas(c)["iq_3ms_a"], 4.2e-5, places=15)
        # end to end: the adapter re-derives the committed rollup from these
        # corners, and it stays as re-derivable as the corner itself
        mbs.refresh_rollup(out)
        entry = out["measurements"][0]
        self.assertEqual(entry["limits"], {"min": -5e-05})
        self.assertEqual(entry["status"], "pass")
        worst = entry["worst_case"]
        self.assertAlmostEqual(worst["value"], -4.2e-5, places=15)
        self.assertAlmostEqual(worst["margin"], worst["value"] - entry["limits"]["min"], places=15)

    def test_iq_limit_bearing_envelope_re_derives_a_fail(self) -> None:
        # the same fixture 10x over the bound, as klt would have graded it:
        # corner fail, and value + limits still re-derive that verdict
        report = self.graded_iq_report(-5e-4, margin=-5e-4 - (-5e-5), corner_status="fail")
        out = esb.enrich(report, "iq")
        c = out["corners"][0]
        self.assertEqual(c["status"], "fail")
        self.assertNotIn("dvsns_v", meas(c))  # a graded-fail corner is not regraded
        m = [m for m in c["measurements"] if m["name"] == "iq_avg_a"][0]
        self.assertAlmostEqual(m["value"], -5e-4, places=15)
        self.assertAlmostEqual(m["margin"], m["value"] - (-5e-5), places=15)
        self.assertLess(m["margin"], 0.0)  # the derived check fails
        self.assertEqual(m["status"], "fail")

    def test_iq_settle_delta_is_independent_of_the_graded_sample(self) -> None:
        for graded in (None, "iq_2ms_a", "iq_3ms_a"):
            with self.subTest(graded=graded):
                report = self.graded_iq_report(-42e-6, 8e-6, graded_sample=graded)
                c = esb.enrich(report, "iq")["corners"][0]
                self.assertEqual(c["status"], "pass", c.get("diagnostics"))
                self.assertEqual(meas(c)["iq_settle_delta_a"], 0.0)
                self.assertAlmostEqual(meas(c)["iq_avg_a"], -42e-6, places=15)
                for name in ("iq_2ms_a", "iq_3ms_a"):
                    m = next(m for m in c["measurements"] if m["name"] == name)
                    if name == graded:
                        self.assertAlmostEqual(m["value"], -42e-6, places=15)
                        self.assertEqual(m["margin"], 8e-6)
                    else:
                        self.assertAlmostEqual(m["value"], 42e-6, places=15)

    def test_iq_graded_sample_settle_delta_is_the_signed_difference(self) -> None:
        for graded, other in (("iq_2ms_a", "iq_3ms_a"), ("iq_3ms_a", "iq_2ms_a")):
            for drift, status in ((5e-8, "pass"), (2e-7, "fail")):
                with self.subTest(graded=graded, drift=drift):
                    report = self.graded_iq_report(-42e-6, 8e-6, graded_sample=graded)
                    reading = next(m for m in report["corners"][0]["measurements"] if m["name"] == other)
                    reading["value"] = -42e-6 - drift
                    c = esb.enrich(report, "iq")["corners"][0]
                    self.assertAlmostEqual(meas(c)["iq_settle_delta_a"], drift, places=15)
                    self.assertEqual(c["status"], status, c.get("diagnostics"))
                    if status == "fail":
                        self.assertEqual(c["diagnostics"][0]["message"], "not_settled")

    def test_startup_verdict_criteria(self) -> None:
        self.assertEqual(self.run_one("startup")["status"], "pass")
        self.assertAlmostEqual(meas(self.run_one("startup"))["dvsns_final_v"], 0.005, places=12)
        c = self.run_one("startup", det_final_v=2.0, fb_final_v=3.3)
        self.assertEqual(c["diagnostics"][0]["message"], "startup_not_released; fb_railed")
        c = self.run_one("startup", sns2_final_v=0.6)
        self.assertEqual(c["diagnostics"][0]["message"], "loop_not_closed")

    def test_missing_operand_fails(self) -> None:
        corner = self.corner("startup")
        corner["measurements"] = [m for m in corner["measurements"] if m["name"] != "fb_final_v"]
        c = esb.enrich({"status": "pass", "corners": [corner]}, "startup")["corners"][0]
        self.assertEqual(c["diagnostics"][0]["code"], "derived_columns_missing")


class EnrichStartupReleaseLadderTests(unittest.TestCase):
    """enrich_supply_bench_report, `--bench startup_release` (issue #468).

    The checkpoint-ladder mode: per-checkpoint verdicts, `dvsns_<N>u_v` at
    every checkpoint, and `release_time_us` under the suffix-of-PASS rule
    `sim/startup-time-to-release/README.md` defines. The reference
    implementation these replace is that bench's own
    `run_pvt_sweep.sh` (lines 108-163), which stays in the tree.
    """

    LADDER = (100, 200, 2000)

    @staticmethod
    def ladder_corner(
        checkpoints: tuple[int, ...] = LADDER,
        cid: str = "typ/3.30V/27C",
        status: str = "pass",
        **over: float | None,
    ) -> dict:
        """A ladder corner whose every checkpoint PASSes, plus `over`.

        `over` keys are measurement names (`det_200u_v`, ...); a `None` value
        drops that measurement, which is how a non-convergent corner's
        unprinted `meas` line is modelled.
        """
        values: dict[str, float | None] = {}
        for checkpoint in checkpoints:
            values[f"det_{checkpoint}u_v"] = 0.10      # <= 0.2 * 3.30
            values[f"i_mkfb_{checkpoint}u_a"] = 1e-9   # <= 50 nA
            values[f"fb_{checkpoint}u_v"] = 1.0        # inside [0.05, 3.25]
            values[f"sns1_{checkpoint}u_v"] = 0.700
            values[f"sns2_{checkpoint}u_v"] = 0.695    # dvsns 5 mV <= 20 mV
        values.update(over)
        return {
            "corner_id": cid,
            "status": status,
            "measurements": [
                {"name": k, "value": v} for k, v in values.items() if v is not None
            ],
        }

    def run_one(self, **kwargs) -> dict:
        corner = self.ladder_corner(**kwargs)
        return esb.enrich({"status": "pass", "corners": [corner]}, "startup_release")["corners"][0]

    # -- the ladder is read off the report, never hardcoded (issue #210) ----

    def test_ladder_is_read_off_det_measurement_names_and_sorted_numerically(self) -> None:
        corner = self.ladder_corner(checkpoints=(100, 900, 1000, 2000))
        corner["measurements"].append({"name": "det_early_v", "value": 0.3})
        # numeric sort, not lexical: a lexical sort would put 1000 before 900
        self.assertEqual(esb.ladder_checkpoints(corner), [100, 900, 1000, 2000])

    def test_a_report_with_no_ladder_is_refused(self) -> None:
        corner = {"corner_id": "typ/3.30V/27C", "status": "pass",
                  "measurements": [{"name": "fb_final_v", "value": 1.0}]}
        c = esb.enrich({"status": "pass", "corners": [corner]}, "startup_release")["corners"][0]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["code"], "derived_columns_missing")

    # -- the ladder walk ---------------------------------------------------

    def test_ladder_walk_derives_dvsns_at_every_checkpoint(self) -> None:
        c = self.run_one()
        got = meas(c)
        self.assertEqual(c["status"], "pass", c.get("diagnostics"))
        for checkpoint in self.LADDER:
            self.assertAlmostEqual(got[f"dvsns_{checkpoint}u_v"], 0.005, places=12)
        derived = [m for m in c["measurements"] if m["name"].startswith("dvsns_")]
        self.assertEqual(len(derived), len(self.LADDER))
        self.assertTrue(all(m["spice"].startswith("derived: ") for m in derived))

    def test_checkpoint_verdicts_trajectory_spelling(self) -> None:
        c = self.run_one(det_200u_v=3.0)
        self.assertEqual(meas(c)["checkpoint_verdicts"], "100u:PASS;200u:FAIL;2000u:PASS")

    # -- release_time_us: a suffix-of-PASS rule ----------------------------

    def test_release_time_is_the_first_checkpoint_of_the_all_pass_suffix(self) -> None:
        self.assertEqual(meas(self.run_one())["release_time_us"], 100)
        # not released at 100u, released from 200u onward
        self.assertEqual(meas(self.run_one(det_100u_v=3.0))["release_time_us"], 200)

    def test_transient_pass_then_regression_is_not_reported_as_early_release(self) -> None:
        """The whole point of the suffix rule: 100u PASSes but 200u does not."""
        c = self.run_one(det_200u_v=3.0)
        self.assertEqual(meas(c)["release_time_us"], 2000)  # NOT 100

    def test_not_released_when_the_final_checkpoint_fails(self) -> None:
        c = self.run_one(det_2000u_v=3.0)
        self.assertEqual(meas(c)["release_time_us"], esb.NOT_RELEASED)
        self.assertEqual(c["status"], "fail")
        self.assertIn("never_released", c["diagnostics"][0]["message"])
        self.assertIn("startup_not_released", c["diagnostics"][0]["message"])

    def test_release_time_helper_is_pure_and_total(self) -> None:
        self.assertEqual(esb.release_time_us([(100, "PASS"), (200, "PASS")]), 100)
        self.assertEqual(esb.release_time_us([(100, "FAIL"), (200, "PASS")]), 200)
        self.assertEqual(esb.release_time_us([(100, "PASS"), (200, "FAIL")]), esb.NOT_RELEASED)
        self.assertEqual(esb.release_time_us([]), esb.NOT_RELEASED)

    # -- a MISSING checkpoint ---------------------------------------------

    def test_missing_checkpoint_is_named_and_fails_the_corner(self) -> None:
        """A corner that did not converge that far leaves a `meas` line unprinted."""
        c = self.run_one(sns2_200u_v=None)
        got = meas(c)
        self.assertEqual(got["checkpoint_verdicts"], "100u:PASS;200u:MISSING;2000u:PASS")
        self.assertNotIn("dvsns_200u_v", got)        # no operands, no derived column
        self.assertIn("dvsns_100u_v", got)           # the rest of the ladder still walks
        self.assertEqual(c["status"], "fail")
        self.assertIn("checkpoint_missing at 200u", c["diagnostics"][0]["message"])

    def test_missing_checkpoint_does_not_break_the_later_suffix(self) -> None:
        """Documented divergence from the legacy bash, which reported NOT_RELEASED here.

        `run_pvt_sweep.sh` let a MISSING checkpoint pass through its
        running-start tracker without resetting it, so `PASS;MISSING;PASS`
        reported `NOT_RELEASED`. The rule README.md states -- the earliest
        checkpoint with an all-PASS suffix -- gives 2000u. The corner is
        graded `fail` either way, so only the reported number differs.
        """
        c = self.run_one(sns2_200u_v=None)
        self.assertEqual(meas(c)["release_time_us"], 2000)
        self.assertEqual(c["status"], "fail")

    # -- the criteria are pvt_closed_loop_verdict's, per checkpoint ---------

    def assert_checkpoint_verdict(self, expected: str, **over: float) -> None:
        got = meas(self.run_one(**over))
        self.assertEqual(got["checkpoint_verdicts"].split(";")[0], f"100u:{expected}")

    def test_startup_release_uses_corner_vdd_at_each_checkpoint(self) -> None:
        self.assert_checkpoint_verdict("PASS", det_100u_v=0.65)   # 0.2 * 3.30 = 0.66
        self.assert_checkpoint_verdict("FAIL", det_100u_v=0.67)
        self.assert_checkpoint_verdict("FAIL", i_mkfb_100u_a=-60e-9)
        self.assert_checkpoint_verdict("PASS", i_mkfb_100u_a=-40e-9)  # magnitude
        # the same det at a 3.63 V corner is released (0.726 V threshold)
        got = meas(self.run_one(cid="typ/3.63V/27C", det_100u_v=0.67))
        self.assertEqual(got["checkpoint_verdicts"].split(";")[0], "100u:PASS")

    def test_loop_closure_and_rail_window_boundaries(self) -> None:
        self.assert_checkpoint_verdict("PASS", sns1_100u_v=0.7199, sns2_100u_v=0.700)
        self.assert_checkpoint_verdict("FAIL", sns1_100u_v=0.7201, sns2_100u_v=0.700)
        self.assert_checkpoint_verdict("FAIL", fb_100u_v=0.049)
        self.assert_checkpoint_verdict("PASS", fb_100u_v=0.051)
        self.assert_checkpoint_verdict("FAIL", fb_100u_v=3.30 - 0.049)

    def test_constants_are_the_shared_closed_loop_ones(self) -> None:
        self.assertEqual(
            (epr.DET_RELEASE_FRAC, epr.I_MKFB_RELEASE_A, epr.DVSNS_CLOSE_V, epr.FB_RAIL_MARGIN_V),
            (0.2, 50e-9, 0.020, 0.05),
        )

    # -- supply resolution -------------------------------------------------

    def test_unresolvable_supply_is_refused_rather_than_graded(self) -> None:
        """The release threshold IS a fraction of vdd; without it there is no verdict."""
        c = self.run_one(cid="typ/novdd/27C")
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["code"], "derived_columns_missing")
        self.assertIn("supply not resolvable", c["diagnostics"][0]["message"])

    def test_non_pass_corner_is_not_regraded(self) -> None:
        c = self.run_one(status="error")
        self.assertEqual(c["status"], "error")
        self.assertNotIn("release_time_us", meas(c))

    def test_top_level_counts_recomputed(self) -> None:
        report = esb.enrich(
            {
                "status": "pass",
                "passed": 99,
                "corners": [
                    self.ladder_corner(),
                    self.ladder_corner(cid="wcs/2.97V/125C", det_2000u_v=3.0),
                    self.ladder_corner(cid="bcs/3.63V/-40C", status="error"),
                ],
            },
            "startup_release",
        )
        self.assertEqual(
            {k: report[k] for k in ("corner_count", "passed", "failed", "errored", "status")},
            {"corner_count": 3, "passed": 1, "failed": 1, "errored": 1, "status": "fail"},
        )


# --------------------------------------------------------------------------
# enrich_pvt_report's shared verdict check and recount (issue #657)
# --------------------------------------------------------------------------


class ClosedLoopVerdictHelperTests(unittest.TestCase):
    """enrich_pvt_report.closed_loop_verdict_failures: the one copy of
    pvt_closed_loop_verdict's 3-criteria form that every klt-path enricher
    calls, so the constants' drift guard covers all of them."""

    def failures(self, det: float | None = 0.10, i_mkfb: float | None = 1e-9,
                 dvsns: float | None = 0.005, fb: float | None = 1.0,
                 vdd: float | None = 3.30) -> list[str]:
        return epr.closed_loop_verdict_failures(det, i_mkfb, dvsns, fb, vdd)

    def test_healthy_point_passes(self) -> None:
        self.assertEqual(self.failures(), [])

    def test_each_criterion_is_named_in_the_standard_order(self) -> None:
        self.assertEqual(self.failures(det=3.0, i_mkfb=1e-6, dvsns=0.1, fb=0.0),
                         ["startup_not_released", "loop_not_closed", "fb_railed"])
        self.assertEqual(self.failures(det=3.0), ["startup_not_released"])
        self.assertEqual(self.failures(dvsns=0.1), ["loop_not_closed"])
        self.assertEqual(self.failures(fb=0.0), ["fb_railed"])

    def test_release_scales_with_supply_and_tolerates_sign(self) -> None:
        self.assertEqual(self.failures(det=0.66), [])                 # 0.2 * 3.30, inclusive
        self.assertEqual(self.failures(det=0.67), ["startup_not_released"])
        self.assertEqual(self.failures(det=0.67, vdd=3.63), [])        # 0.726 at 3.63 V
        self.assertEqual(self.failures(i_mkfb=-50e-9), [])             # magnitude, inclusive
        self.assertEqual(self.failures(i_mkfb=-60e-9), ["startup_not_released"])

    def test_closure_and_rail_boundaries_are_inclusive(self) -> None:
        self.assertEqual(self.failures(dvsns=0.020), [])
        self.assertEqual(self.failures(dvsns=0.0201), ["loop_not_closed"])
        self.assertEqual(self.failures(fb=0.05), [])
        self.assertEqual(self.failures(fb=0.049), ["fb_railed"])
        self.assertEqual(self.failures(fb=3.25), [])
        self.assertEqual(self.failures(fb=3.2501), ["fb_railed"])

    def test_a_none_operand_skips_only_its_own_criterion(self) -> None:
        # Every caller's own null-guard, in one place: a criterion with no
        # operand is not graded, and does not stop the others being graded.
        self.assertEqual(self.failures(det=None, i_mkfb=None), [])
        self.assertEqual(self.failures(dvsns=None), [])
        self.assertEqual(self.failures(fb=None), [])
        self.assertEqual(epr.closed_loop_verdict_failures(None, None, None, None, None), [])
        # an unresolvable supply skips the two vdd-dependent criteria only
        self.assertEqual(self.failures(det=3.0, fb=0.0, vdd=None), [])
        self.assertEqual(self.failures(dvsns=0.1, vdd=None), ["loop_not_closed"])

    _SHELL_TOKEN_RE = re.compile(
        r'''("(?:\\.|[^"\\])*")|('[^']*')|((?:^|(?<=[ \t;&|()]))#[^\n]*)''',
        re.M,
    )
    _QUOTED_ASSIGN_RE = re.compile(
        r'''^['"]([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\n]+\])?\+?=).*['"]$''',
        re.S,
    )
    _QUOTED_IDENT_RE = re.compile(
        r'''^['"]([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\n]+\])?)['"]$''',
    )

    @classmethod
    def _has_shell_constant_assignment(cls, text: str, name: str) -> bool:
        """True if shell source *text* assigns or declares *name* anywhere
        (indented blocks, compound lines, readonly/export/declare/typeset/local/
        unset, parameter default-assignment, printf -v / read, or (( ... )))."""
        def scrub_no_single(m: re.Match[str]) -> str:
            dq, sq, _comment = m.groups()
            if dq is not None:
                return dq
            if sq is not None:
                qa = cls._QUOTED_ASSIGN_RE.match(sq)
                if qa:
                    return f'"{qa.group(1)}"'
                qi = cls._QUOTED_IDENT_RE.match(sq)
                return f'"{qi.group(1)}"' if qi else "''"
            return ""

        def scrub_both(m: re.Match[str]) -> str:
            dq, sq, _comment = m.groups()
            q = dq or sq
            if q is not None:
                qa = cls._QUOTED_ASSIGN_RE.match(q)
                if qa:
                    return f'"{qa.group(1)}"'
                qi = cls._QUOTED_IDENT_RE.match(q)
                return f'"{qi.group(1)}"' if qi else '""'
            return ""

        no_single = re.sub(r"\\\n[ \t]*", " ", cls._SHELL_TOKEN_RE.sub(scrub_no_single, text))
        if re.search(rf"\$\{{{name}:?=(?!=)", no_single):
            return True

        unquoted = re.sub(r"\\\n[ \t]*", " ", cls._SHELL_TOKEN_RE.sub(scrub_both, text))
        stmt = r"(?:^|[;&|(){}]|\b(?:then|do|else|elif)\b)[ \t]*"
        val = r"[^ \t;&|()\n]*"
        lhs = rf"{name}(?:\[[^\]\n]+\])?"
        patterns = (
            stmt + rf"(?:env[ \t]+)?(?:[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\n]+\])?\+?={val}[ \t]+)*{lhs}\+?=(?!=)",
            stmt
            + r"(?:(?:builtin|command)[ \t]+)?(?:readonly|export|declare|typeset|local|unset)\b"
            + rf'(?:[ \t]+(?:[-+][a-zA-Z]+|--|"?[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]\n]+\])?(?:\+?={val})?"?))*'
            + rf'[ \t]+"?{lhs}(?:\+?=(?!=)"?|"?(?=$|[ \t;&|()]))',
            stmt + rf"(?:printf[ \t]+-v[ \t]+{name}\b|read\b[^;&|()\n]*[ \t]+{name}\b)",
            rf"\(\([^)\n]*\b{name}[ \t]*[-+*/%&|^]?=(?!=)",
        )
        return any(re.search(p, unquoted, re.M) for p in patterns)

    _PY_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", -1)

    @classmethod
    def _python_source_scrubbed(cls, text: str) -> str:
        """*text* with comments and string-literal contents blanked (line and
        column layout preserved), so line-anchored name matching cannot fire
        inside prose, comments, or literals."""
        blank_types = {tokenize.COMMENT, tokenize.STRING, cls._PY_FSTRING_MIDDLE}
        spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(text).readline):
                if tok.type in blank_types:
                    spans.append((tok.start, tok.end))
        except (tokenize.TokenError, IndentationError):
            pass  # scrub what parsed; an over-match fails loudly, never silently
        lines = text.splitlines(keepends=True)
        for (r0, c0), (r1, c1) in spans:
            for row_n in range(r0, min(r1, len(lines)) + 1):
                row = lines[row_n - 1]
                a = c0 if row_n == r0 else 0
                b = min(c1 if row_n == r1 else len(row), len(row))
                if b > a:
                    lines[row_n - 1] = (
                        row[:a]
                        + "".join(ch if ch == "\n" else " " for ch in row[a:b])
                        + row[b:]
                    )
        return "".join(lines)

    @classmethod
    def _has_python_constant_assignment(cls, text: str, name: str) -> bool:
        """True if Python source *text* binds *name* anywhere: indented or
        after a semicolon, annotated ``NAME: float =``, augmented with a
        single- or multi-character operator (``NAME +=``, ``NAME //=``,
        ``NAME **=``, ``NAME >>=``, ``NAME <<=``, ...), walrus ``NAME :=``,
        plain ``NAME =``, or chained / tuple targets with *name* anywhere in
        the target list (``OTHER = NAME = v``, ``A, NAME = ...``,
        ``NAME, M = ...``, ``A, NAME, B = ...``). Comments and strings never
        count. Keyword-argument spellings at the start of a continuation
        line can trip the plain and tuple forms — a use, but unusual enough
        that failing loudly suits a one-home guard."""
        scrubbed = cls._python_source_scrubbed(text)
        anchor = r"(?:^|;)[ \t]*"
        if re.search(
            rf"{anchor}{name}[ \t]*(?::[^=\n]+)?[ \t]*(?:(?:[-+*/%&|^@]|//|\*\*|>>|<<)=|=(?!=))",
            scrubbed,
            re.M,
        ):
            return True
        if re.search(rf"\b{name}[ \t]*:=", scrubbed):  # walrus binds wherever it appears
            return True
        # Target lists anchored at a statement boundary: simple (optionally
        # starred) targets around *name*, so name-first and name-middle tuple
        # unpacking binds too. Non-simple prefixes (``a.b, NAME = ...``,
        # ``d[k], NAME = ...``) still fall through to the legacy comma-
        # anchored arm, keeping detection a strict superset of the #689 guard.
        target = r"\*?[A-Za-z_][A-Za-z0-9_]*"
        return bool(
            re.search(rf"[=,][ \t]*{name}[ \t]*=(?!=)", scrubbed, re.M)
            or re.search(
                rf"(?:^|;|=)[ \t]*(?:{target}[ \t]*,[ \t]*)*{name}"
                rf"(?:[ \t]*,[ \t]*{target})*[ \t]*=(?!=)",
                scrubbed,
                re.M,
            )
        )

    @classmethod
    def _python_constant_homes(cls, sim: Path, name: str) -> list[str]:
        return [
            str(p.relative_to(sim))
            for p in sorted(sim.rglob("*.py"))
            if cls._has_python_constant_assignment(p.read_text(encoding="utf-8"), name)
        ]

    @classmethod
    def _shell_constant_homes(cls, sim: Path, name: str) -> list[str]:
        return [
            str(p.relative_to(sim))
            for p in sorted(sim.rglob("*.sh"))
            if cls._has_shell_constant_assignment(p.read_text(encoding="utf-8"), name)
        ]

    def test_the_constants_have_one_home(self) -> None:
        """Both drift tests pin enrich_pvt_report's constants against
        pvt_verdict_common.sh; a second assignment elsewhere sits outside them."""
        harness = Path(__file__).resolve().parent
        sim = harness.parent
        for name in ("DET_RELEASE_FRAC", "I_MKFB_RELEASE_A", "DVSNS_CLOSE_V", "FB_RAIL_MARGIN_V"):
            with self.subTest(constant=name):
                self.assertEqual(self._python_constant_homes(sim, name),
                                 ["harness/enrich_pvt_report.py"])
            with self.subTest(constant=name, surface="shell"):
                self.assertEqual(self._shell_constant_homes(sim, name),
                                 ["lib/pvt_verdict_common.sh"])

    def test_shell_one_home_guard_catches_indented_and_declared_assignments(self) -> None:
        constants = ("DET_RELEASE_FRAC", "I_MKFB_RELEASE_A", "DVSNS_CLOSE_V", "FB_RAIL_MARGIN_V")
        with tempfile.TemporaryDirectory() as td:
            sim = Path(td)
            (sim / "lib").mkdir()
            (sim / "lib" / "pvt_verdict_common.sh").write_text(
                "".join(f'{c}="0.2"\n' for c in constants),
                encoding="utf-8",
            )
            (sim / "bench").mkdir()
            (sim / "bench" / "uses_only.sh").write_text(
                "# DET_RELEASE_FRAC=0.8\n"
                "  # readonly I_MKFB_RELEASE_A=1\n"
                'echo "  v(det) <= ${DET_RELEASE_FRAC}*vdd" # DVSNS_CLOSE_V=0.5\n'
                'echo "(note) FB_RAIL_MARGIN_V=0.5"\n'
                '[[ "${DET_RELEASE_FRAC}" == "0.2" ]]\n',
                encoding="utf-8",
            )
            for name in constants:
                self.assertEqual(self._shell_constant_homes(sim, name),
                                 ["lib/pvt_verdict_common.sh"])

            cases = [
                ("harness/indented_if.sh", "DET_RELEASE_FRAC", "if true; then\n  DET_RELEASE_FRAC=0.8\nfi\n"),
                ("harness/top_readonly.sh", "DET_RELEASE_FRAC", "readonly DET_RELEASE_FRAC=0.8\n"),
                ("bench/tab_indented.sh", "I_MKFB_RELEASE_A", '\tI_MKFB_RELEASE_A="1e-6"\n'),
                ("bench/declare_ro.sh", "DVSNS_CLOSE_V", '  declare -r DVSNS_CLOSE_V="0.1"\n'),
                ("bench/export_inline.sh", "FB_RAIL_MARGIN_V", "if true; then export FB_RAIL_MARGIN_V=0.2; fi\n"),
                ("zzz/local_shadow.sh", "DET_RELEASE_FRAC", "f() {\n  local DET_RELEASE_FRAC=0.8\n}\n"),
                ("zzz/quoted_decl.sh", "DET_RELEASE_FRAC", 'readonly "FOO=a ; b" "DET_RELEASE_FRAC=0.8"\n'),
                ("zzz/continued_decl.sh", "I_MKFB_RELEASE_A", "readonly \\\n  I_MKFB_RELEASE_A=1e-6\n"),
                ("zzz/param_default.sh", "DVSNS_CLOSE_V", ': "${DVSNS_CLOSE_V:=0.1}"\n'),
            ]
            for rel, name, body in cases:
                with self.subTest(rel=rel, constant=name):
                    rogue = sim / rel
                    rogue.parent.mkdir(parents=True, exist_ok=True)
                    rogue.write_text(body, encoding="utf-8")
                    try:
                        with self.assertRaises(AssertionError) as cm:
                            self.assertEqual(
                                self._shell_constant_homes(sim, name),
                                ["lib/pvt_verdict_common.sh"],
                            )
                        self.assertIn(rel, str(cm.exception))
                    finally:
                        rogue.unlink()

    def test_python_one_home_guard_catches_indented_annotated_augmented_chained(self) -> None:
        constants = ("DET_RELEASE_FRAC", "I_MKFB_RELEASE_A", "DVSNS_CLOSE_V", "FB_RAIL_MARGIN_V")
        with tempfile.TemporaryDirectory() as td:
            sim = Path(td)
            (sim / "harness").mkdir()
            (sim / "harness" / "enrich_pvt_report.py").write_text(
                "".join(f"{c} = 0.2\n" for c in constants),
                encoding="utf-8",
            )
            (sim / "tools").mkdir()
            (sim / "tools" / "uses_only.py").write_text(
                "# DET_RELEASE_FRAC = 0.8\n"
                'uses = f"{DVSNS_CLOSE_V=} {FB_RAIL_MARGIN_V!r}"\n'
                'doc = """\n'
                "    I_MKFB_RELEASE_A = 1e-6\n"
                "DET_RELEASE_FRAC = 0.8\n"
                '"""\n'
                "if DET_RELEASE_FRAC == 0.2 and I_MKFB_RELEASE_A <= 50e-9:\n"
                "    print(DVSNS_CLOSE_V, FB_RAIL_MARGIN_V)\n"
                "kwarg_call = call(DET_RELEASE_FRAC, x=1)\n",
                encoding="utf-8",
            )
            for name in constants:
                self.assertEqual(self._python_constant_homes(sim, name),
                                 ["harness/enrich_pvt_report.py"])

            cases = [
                ("harness/indented_if.py", "DET_RELEASE_FRAC", "if True:\n    DET_RELEASE_FRAC = 0.8\n"),
                ("tools/annotated.py", "I_MKFB_RELEASE_A", "I_MKFB_RELEASE_A: float = 50e-9\n"),
                ("loop-gain-phase-margin/tools/augmented.py", "DVSNS_CLOSE_V", "DVSNS_CLOSE_V += 0.001\n"),
                ("closed-loop-psrr/attribution/chained.py", "FB_RAIL_MARGIN_V", "MARGIN = FB_RAIL_MARGIN_V = 0.05\n"),
                ("harness/nested/global_shadow.py", "DET_RELEASE_FRAC",
                 "def f():\n    global DET_RELEASE_FRAC\n    DET_RELEASE_FRAC = 0.8\n"),
                ("zzz/semicolon.py", "I_MKFB_RELEASE_A", "x = 1; I_MKFB_RELEASE_A = 50e-9\n"),
                ("zzz/walrus.py", "DVSNS_CLOSE_V", "if (DVSNS_CLOSE_V := 0.020) <= 0.020:\n    pass\n"),
                ("zzz/tuple_target.py", "FB_RAIL_MARGIN_V", "MARGIN, FB_RAIL_MARGIN_V = 0.05, 0.05\n"),
                ("zzz/augmented_floordiv.py", "DET_RELEASE_FRAC", "DET_RELEASE_FRAC //= 2\n"),
                ("zzz/augmented_pow.py", "I_MKFB_RELEASE_A", "I_MKFB_RELEASE_A **= 2\n"),
                ("zzz/augmented_rshift.py", "DVSNS_CLOSE_V", "DVSNS_CLOSE_V >>= 1\n"),
                ("zzz/augmented_lshift.py", "FB_RAIL_MARGIN_V", "FB_RAIL_MARGIN_V <<= 1\n"),
                ("zzz/tuple_target_first.py", "DET_RELEASE_FRAC", "DET_RELEASE_FRAC, MARGIN = 0.8, 0.05\n"),
                ("zzz/tuple_target_middle.py", "DVSNS_CLOSE_V", "LOW, DVSNS_CLOSE_V, HIGH = 0.01, 0.020, 0.1\n"),
            ]
            for rel, name, body in cases:
                with self.subTest(rel=rel, constant=name):
                    rogue = sim / rel
                    rogue.parent.mkdir(parents=True, exist_ok=True)
                    rogue.write_text(body, encoding="utf-8")
                    try:
                        with self.assertRaises(AssertionError) as cm:
                            self.assertEqual(
                                self._python_constant_homes(sim, name),
                                ["harness/enrich_pvt_report.py"],
                            )
                        self.assertIn(rel, str(cm.exception))
                    finally:
                        rogue.unlink()


class RecountReportHelperTests(unittest.TestCase):
    """enrich_pvt_report.recount_report: the report-level tally every enricher
    ends with (issue #657)."""

    @staticmethod
    def corners(*statuses: str) -> list[dict]:
        return [{"status": s} for s in statuses]

    def test_counts_and_grade_come_from_the_corners(self) -> None:
        corners = self.corners("pass", "fail", "error", "pass")
        report = epr.recount_report(
            {"passed": 99, "provenance": {"klt_version": "0.5.0"}}, corners)
        self.assertIs(report["corners"], corners)
        self.assertEqual(
            {k: report[k] for k in ("passed", "failed", "errored", "corner_count", "status")},
            {"passed": 2, "failed": 1, "errored": 1, "corner_count": 4, "status": "fail"},
        )
        self.assertEqual(report["provenance"], {"klt_version": "0.5.0"})

    def test_grade_precedence_and_the_empty_report(self) -> None:
        grade = lambda *s: epr.recount_report({}, self.corners(*s))["status"]  # noqa: E731
        self.assertEqual(grade("pass", "pass"), "pass")
        self.assertEqual(grade("pass", "error"), "error")
        self.assertEqual(grade("error", "fail"), "fail")
        self.assertEqual(grade(), "pass")

    def test_corners_default_to_the_report_own_list(self) -> None:
        report = {"corners": self.corners("pass", "fail"), "passed": 0}
        self.assertIs(epr.recount_report(report), report)
        self.assertEqual((report["passed"], report["failed"], report["status"]), (1, 1, "fail"))
        self.assertEqual(epr.recount_report({})["corners"], [])


# --------------------------------------------------------------------------
# enrich_ac_report.enrich
# --------------------------------------------------------------------------


class EnrichAcReportTests(TempDirCase):
    """enrich_ac_report.enrich (issue #278): the PSRR/Zout benches' enricher.
    Its supply injection and closed-loop verdict run over enrich_pvt_report's
    shared helpers (issue #657); the log-side columns are its own."""

    VDD = 3.30

    def setUp(self) -> None:
        super().setUp()
        self._n = 0
        self.write_body()
        self.deck = self.write("deck.cir", '.include "body.spice"\n')

    def write_body(self, seed_fb: float = 2.5) -> None:
        self.write("body.spice",
                   f"Vvdd vdd 0 DC {self.VDD}\n.nodeset v(fb)={seed_fb} v(sns1)=0.7\n")

    def corner(self, status: str = "pass", cid: str = "typ/novdd/27C", **op: float) -> dict:
        """A PSRR corner over a deck+bode whose baked supply is 3.30 V.

        `op` keys are the log's op prints (`fb`, `sns1`, `sns2`, `det`, ...);
        the defaults are a healthy closed loop.
        """
        self._n += 1
        values = {"fb": 2.5, "sns1": 0.700, "sns2": 0.695,
                  "vref": 1.047, "det": 0.10, "imkfb": 1e-9}
        values.update(op)
        log = "".join(f"v({k}) = {v:e}\n" for k, v in values.items() if k != "imkfb")
        log += f"i(vmkfb) = {values['imkfb']:e}\n"
        log += ("Index   frequency       psrr_db\n"
                "0       1.0e+03        6.0e+01\n"
                "1       1.0e+05        4.0e+01\n"
                "2       1.0e+06        8.0e+01\n")
        return {
            "corner_id": cid, "process": "typ", "temperature_c": 27, "status": status,
            "artifacts": {"deck": str(self.deck),
                          "log": str(self.write(f"log-{self._n}.log", log))},
            "measurements": [{"name": f"psrr_{f}_lin", "value": 1e-3}
                             for f in ("dc", "1khz", "100khz", "1mhz")],
        }

    def run_enrich(self, *corners: dict) -> dict:
        report = ear.enrich({"status": "pass", "passed": 99, "corners": list(corners)}, "psrr")
        return report

    def test_baked_supply_is_injected_on_passing_and_failing_corners(self) -> None:
        failing = self.corner(status="fail", fb=3.3)
        failing["diagnostics"] = [{"code": "spec_limit", "message": "psrr_dc_db < 40"}]
        out = self.run_enrich(self.corner(), failing)
        for c in out["corners"]:
            self.assertEqual(c["corner_id"], "typ/3.30V/27C")
            self.assertEqual(c["supply_v"], {"Vvdd": 3.30})
        passing, kept = out["corners"]
        self.assertEqual(passing["status"], "pass", passing.get("diagnostics"))
        # an already-failing corner keeps klt's own diagnostics, but still
        # gets its columns: they are the log's own facts
        self.assertEqual(kept["diagnostics"],
                         [{"code": "spec_limit", "message": "psrr_dc_db < 40"}])
        self.assertIn("psrr_dc_db", meas(kept))
        self.assertEqual(
            {k: out[k] for k in ("corner_count", "passed", "failed", "errored", "status")},
            {"corner_count": 2, "passed": 1, "failed": 1, "errored": 0, "status": "fail"},
        )

    def test_each_deck_is_spliced_once(self) -> None:
        """The one splice both injects the baked supply and yields the seeds:
        no second read of the deck and its include closure (issue #657)."""
        with mock.patch.object(ear, "_splice_deck", wraps=ear._splice_deck) as splice:
            self.run_enrich(self.corner(), self.corner(cid="bcs/novdd/-40C"))
        self.assertEqual(splice.call_count, 2)

    def test_log_side_and_derived_columns_are_appended(self) -> None:
        c = self.run_enrich(self.corner())["corners"][0]
        got = meas(c)
        for name in ("fb_op_v", "sns1_op_v", "sns2_op_v", "vref_op_v", "det_op_v", "i_vmkfb_a"):
            self.assertIn(name, got)
        self.assertEqual(got["fb_seed_v"], 2.5)
        for f in ("dc", "1khz", "100khz", "1mhz"):
            self.assertAlmostEqual(got[f"psrr_{f}_db"], 60.0, places=12)
        # PSRR's worst case is its minimum, read off the printed sweep
        self.assertEqual((got["psrr_min_db"], got["psrr_min_freq_hz"]), (40.0, 1.0e5))
        self.assertEqual(c["status"], "pass", c.get("diagnostics"))

    def test_closed_loop_criteria_are_named_in_the_standard_order(self) -> None:
        self.write_body(seed_fb=3.3)   # the railed op IS the seed: no op-match complaint
        c = self.run_enrich(self.corner(det=3.0, sns2=0.80, fb=3.3))["corners"][0]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["code"], "ac_bench_verdict")
        self.assertEqual(c["diagnostics"][0]["message"],
                         "startup_not_released; loop_not_closed; fb_railed")

    def test_op_match_is_named_before_the_loop_criteria(self) -> None:
        c = self.run_enrich(self.corner(fb=2.6, sns2=0.80))["corners"][0]
        self.assertEqual(c["diagnostics"][0]["message"],
                         "op_landed_far_from_seed; loop_not_closed")

    def test_verdict_follows_the_shared_constants(self) -> None:
        with mock.patch.object(epr, "DET_RELEASE_FRAC", 0.0):
            c = self.run_enrich(self.corner())["corners"][0]
        self.assertEqual(c["status"], "fail")
        self.assertEqual(c["diagnostics"][0]["message"], "startup_not_released")

    def test_supply_comes_from_the_corner_id_when_no_deck_is_baked(self) -> None:
        c = self.corner(cid="typ/2.97V/27C", det=0.61)     # above 0.2 * 2.97 = 0.594
        c["artifacts"].pop("deck")
        message = self.run_enrich(c)["corners"][0]["diagnostics"][0]["message"]
        self.assertEqual(message, "startup_not_released")
        c = self.corner(cid="typ/3.63V/27C", det=0.61)     # below 0.726: released at 3.63 V
        c["artifacts"].pop("deck")
        self.assertEqual(self.run_enrich(c)["corners"][0]["status"], "pass")

    def test_a_missing_log_names_the_absent_columns_and_fails_the_corner(self) -> None:
        c = self.corner()
        c["artifacts"].pop("log")
        out = self.run_enrich(c)["corners"][0]
        self.assertEqual(out["status"], "fail")
        message = out["diagnostics"][0]["message"]
        self.assertIn("missing op print fb_op_v", message)
        self.assertIn("no AC sweep table in the log", message)


class CornerIdTests(unittest.TestCase):
    def test_grammar_and_cell_spellings(self) -> None:
        self.assertEqual(
            kse.corner_id({"process": "typ", "temperature_c": 27, "supply_v": {"Vvdd": 3.3}}),
            ("typ_27c_3.30v", "typ", "27", "3.30"),
        )
        self.assertEqual(
            kse.corner_id({"process": "wcs", "temperature_c": -40.0, "supply_v": {"V": 2.97}}),
            ("wcs_-40c_2.97v", "wcs", "-40", "2.97"),
        )
        self.assertEqual(
            kse.corner_id({"temperature_c": 12.5, "supply_v": {"V": 3.625}})[0], "nom_12.5c_3.62v"
        )

    def test_exactly_one_supply_rail(self) -> None:
        for supplies in ({}, {"Vvdd": 3.3, "Vaux": 1.2}):
            with self.subTest(supplies=supplies), self.assertRaises(SystemExit):
                kse.corner_id({"process": "typ", "temperature_c": 27, "supply_v": supplies})


class RecordShapeTests(unittest.TestCase):
    REPORT = {
        "corners": [
            {
                "process": "typ",
                "temperature_c": 27,
                "supply_v": {"Vvdd": 3.3},
                "status": "pass",
                "measurements": [
                    {"name": "vref_v", "value": 1.234567891},
                    {"name": "iq_a", "value": 1.5e-6},
                ],
            },
            {
                "process": "wcs",
                "temperature_c": 125,
                "supply_v": {"Vvdd": 2.97},
                "status": "pass",
                "measurements": [{"name": "vref_v", "value": 1.2}, {"name": "tc_ppm", "value": None}],
            },
            {
                "process": "bcs",
                "temperature_c": -40,
                "supply_v": {"Vvdd": 3.63},
                "status": "fail",
                "measurements": [{"name": "vref_v", "value": 1.2}, {"name": "iq_a", "value": 2e-6}],
            },
        ]
    }

    def test_measurement_columns_keep_first_seen_order(self) -> None:
        self.assertEqual(kse.measurement_names(self.REPORT), ["vref_v", "iq_a", "tc_ppm"])

    def test_corner_passed_needs_status_and_required_measurements(self) -> None:
        typ, wcs, bcs = self.REPORT["corners"]
        self.assertTrue(kse.corner_passed(typ, ["vref_v", "iq_a"]))
        self.assertFalse(kse.corner_passed(wcs, ["iq_a"]))      # absent
        self.assertFalse(kse.corner_passed(wcs, ["tc_ppm"]))    # present but null
        self.assertFalse(kse.corner_passed(bcs, []))            # graded fail

    def test_csv_rows_six_significant_figures_and_blank_for_missing(self) -> None:
        names = kse.measurement_names(self.REPORT)
        spec = {"pass_requires": ["iq_a"], "extra_columns": {"trim": {"typ": "128"}}}
        rows, passed = kse.build_csv(self.REPORT, spec, names)
        self.assertEqual(passed, 1)
        self.assertEqual(
            rows[0],
            {
                "corner_label": "typ",
                "trim": "128",
                "temp_c": "27",
                "vdd_v": "3.30",
                "status": "PASS",
                "vref_v": "1.234568e+00",
                "iq_a": "1.500000e-06",
                "tc_ppm": "",
            },
        )
        self.assertEqual(list(rows[0]), list(rows[1]))  # one header for every row
        self.assertEqual((rows[1]["status"], rows[1]["iq_a"], rows[1]["trim"]), ("FAIL", "", ""))
        self.assertEqual((rows[2]["status"], rows[2]["temp_c"]), ("FAIL", "-40"))

    def test_categorical_cells_are_written_verbatim(self) -> None:
        """A derived column need not be a number (issue #468).

        `startup-time-to-release`'s `release_time_us` is a checkpoint in
        microseconds **or** the string `NOT_RELEASED`, and `checkpoint_verdicts`
        is a `<N>u:<PASS|FAIL|MISSING>` trajectory -- both spellings its legacy
        `run_pvt_sweep.sh` CSV already used. Six-significant-figure formatting
        would raise on either, so the mint would die on the first
        non-convergent corner.
        """
        self.assertEqual(kse._cell(1.234567891), "1.234568e+00")
        self.assertEqual(kse._cell(100), "1.000000e+02")
        self.assertEqual(kse._cell(None), "")
        self.assertEqual(kse._cell("NOT_RELEASED"), "NOT_RELEASED")
        self.assertEqual(kse._cell("100u:PASS;200u:MISSING"), "100u:PASS;200u:MISSING")

    def test_categorical_measurements_ride_through_build_csv(self) -> None:
        report = {
            "corners": [
                {
                    "process": "typ", "temperature_c": 27, "supply_v": {"Vvdd": 3.3},
                    "status": "pass",
                    "measurements": [
                        {"name": "release_time_us", "value": 100},
                        {"name": "checkpoint_verdicts", "value": "100u:PASS;2000u:PASS"},
                    ],
                },
                {
                    "process": "wcs", "temperature_c": 125, "supply_v": {"Vvdd": 2.97},
                    "status": "fail",
                    "measurements": [
                        {"name": "release_time_us", "value": "NOT_RELEASED"},
                        {"name": "checkpoint_verdicts", "value": "100u:FAIL;2000u:MISSING"},
                    ],
                },
            ]
        }
        names = kse.measurement_names(report)
        rows, passed = kse.build_csv(report, {"pass_requires": names}, names)
        self.assertEqual(passed, 1)
        self.assertEqual(rows[0]["release_time_us"], "1.000000e+02")
        self.assertEqual(rows[0]["checkpoint_verdicts"], "100u:PASS;2000u:PASS")
        self.assertEqual(rows[1]["release_time_us"], "NOT_RELEASED")
        self.assertEqual(rows[1]["status"], "FAIL")


class InlineDeckTests(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.pdk = self.tmp / "pdk"
        self.model = self.write("pdk/models/cornerMOS.lib", ".lib mos_tt\n.model x nmos\n.endl\n")

    def test_local_include_spliced_recursively(self) -> None:
        self.write("work/sub/inner.spice", "R2 b 0 1k\n")
        self.write("work/body.spice", 'XQ1 a b c npn\n.include "sub/inner.spice"\n')
        deck = self.write("work/corner.cir", "* deck\n.include body.spice\n.end\n")
        out = kse.inline_deck(deck, str(self.pdk))
        self.assertEqual(
            out,
            [
                "* deck",
                "* --- inlined .include body.spice (klt_sim_evidence.py) ---",
                "XQ1 a b c npn",
                "* --- inlined .include inner.spice (klt_sim_evidence.py) ---",
                "R2 b 0 1k",
                "* --- end inner.spice ---",
                "* --- end body.spice ---",
                ".end",
            ],
        )

    def test_pdk_paths_redacted_never_inlined(self) -> None:
        deck = self.write(
            "work/corner.cir",
            f'.lib "{self.model}" mos_tt\n.include {self.pdk}/models/missing.spice\n',
        )
        out = kse.inline_deck(deck, str(self.pdk))
        self.assertEqual(
            out,
            [
                '.lib "${PDK_ROOT}/models/cornerMOS.lib" mos_tt',
                '.include "${PDK_ROOT}/models/missing.spice"',
            ],
        )
        self.assertFalse(any(str(self.tmp) in line for line in out))

    def test_local_lib_section_inlined_with_pdk_cards_redacted(self) -> None:
        self.write(
            "work/bundle.lib",
            ".lib typ\n"
            f'.lib "{self.model}" mos_tt\n'
            f".include {self.pdk}/models/hbt.spice\n"
            ".endl typ\n"
            ".lib wcs\nshould-not-appear\n.endl wcs\n",
        )
        deck = self.write("work/corner.cir", ".lib bundle.lib typ\n")
        out = kse.inline_deck(deck, str(self.pdk))
        self.assertEqual(
            out,
            [
                "* --- inlined .lib bundle.lib typ (klt_sim_evidence.py) ---",
                '.lib "${PDK_ROOT}/models/cornerMOS.lib" mos_tt',
                '.include "${PDK_ROOT}/models/hbt.spice"',
                "* --- end bundle.lib typ ---",
            ],
        )

    def test_pre_osdi_pdk_paths_in_deck_include_and_lib(self) -> None:
        self.write(
            "work/sub/body.spice",
            f'.control\n\tPRE_OSDI  "{self.pdk}/osdi/my model.osdi"\n.endc\n',
        )
        self.write(
            "work/sub/bundle.lib",
            ".lib typ\npre_osdi '../../pdk/osdi/relative.osdi'\n.endl typ\n",
        )
        deck = self.write(
            "work/corner.cir",
            f"pre_osdi {self.pdk}/osdi/top.osdi\n.include sub/body.spice\n.lib sub/bundle.lib typ\n",
        )
        out = kse.inline_deck(deck, str(self.pdk))
        self.assertIn("pre_osdi ${PDK_ROOT}/osdi/top.osdi", out)
        self.assertIn('\tPRE_OSDI  "${PDK_ROOT}/osdi/my model.osdi"', out)
        self.assertIn("pre_osdi '${PDK_ROOT}/osdi/relative.osdi'", out)
        self.assertNotIn(str(self.pdk), "\n".join(out))

    def test_pre_osdi_placeholders_pass_through(self) -> None:
        cards = ['  pre_osdi "${PDK_ROOT}/a.osdi"', "pre_osdi $PDK_ROOT/b.osdi"]
        deck = self.write("pdk/test.cir", "\n".join(cards))
        for root in (None, str(self.pdk)):
            with self.subTest(root=root):
                self.assertEqual(kse.inline_deck(deck, root), cards)

    def test_pre_osdi_external_paths_pass_through(self) -> None:
        override = self.tmp / "pdkx" / "override.osdi"
        override.parent.mkdir()
        override.write_bytes(b"\xff\x00")
        cards = [f'\tpre_osdi "{override}"  ', "pre_osdi /opt/pdk/osdi/runner.osdi"]
        deck = self.write("work/corner.cir", "\n".join(cards))
        self.assertEqual(kse.inline_deck(deck, str(self.pdk)), cards)

        card = f"pre_osdi {self.pdk}/osdi/top.osdi"
        deck = self.write("work/corner.cir", card)
        self.assertEqual(kse.inline_deck(deck, None), [card])

    def test_missing_local_include_fails_with_chain(self) -> None:
        self.write("work/body.spice", '.include "missing-dut.spice"\n')
        deck = self.write("work/corner.cir", ".include body.spice\n")
        with self.assertRaises(SystemExit) as cm:
            kse.inline_deck(deck, str(self.pdk))
        msg = str(cm.exception)
        self.assertIn("missing-dut.spice", msg)
        self.assertIn("corner.cir", msg)
        self.assertIn("body.spice", msg)

    def test_missing_include_outside_pdk_fails(self) -> None:
        deck = self.write("work/corner.cir", '.include "/nonexistent/x.spice"\n')
        with self.assertRaises(SystemExit):
            kse.inline_deck(deck, str(self.pdk))
        with self.assertRaises(SystemExit):
            kse.inline_deck(deck, None)

    def test_placeholder_pdk_reference_retained(self) -> None:
        deck = self.write("work/corner.cir", '.include "${PDK_ROOT}/models/x.spice"\n')
        self.assertEqual(
            kse.inline_deck(deck, None), ['.include "${PDK_ROOT}/models/x.spice"']
        )

    def test_unreadable_include_fails(self) -> None:
        bad = self.tmp / "work" / "bad.spice"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_bytes(b"\xff\xfe\x00bad")
        deck = self.write("work/corner.cir", ".include bad.spice\n")
        with self.assertRaises(SystemExit) as cm:
            kse.inline_deck(deck, None)
        self.assertIn("bad.spice", str(cm.exception))

    def test_include_cycle_fails_with_chain(self) -> None:
        self.write("work/a.spice", ".include b.spice\nRA a 0 1\n")
        self.write("work/b.spice", ".include a.spice\nRB b 0 1\n")
        deck = self.write("work/corner.cir", ".include a.spice\n")
        with self.assertRaises(SystemExit) as cm:
            kse.inline_deck(deck, None)
        msg = str(cm.exception)
        self.assertIn("cycle", msg)
        self.assertIn("a.spice -> ", msg)

    def test_top_level_self_include_is_a_cycle(self) -> None:
        deck = self.write("work/corner.cir", ".include corner.cir\n")
        with self.assertRaises(SystemExit) as cm:
            kse.inline_deck(deck, None)
        self.assertIn("cycle", str(cm.exception))

    def test_lib_section_nested_local_include_inlined(self) -> None:
        self.write("work/dut.spice", "XQ1 a b c npn\n")
        self.write(
            "work/bundle.lib",
            f'.lib typ\n.include dut.spice\n.lib "{self.model}" mos_tt\n.endl typ\n',
        )
        deck = self.write("work/corner.cir", ".lib bundle.lib typ\n")
        out = kse.inline_deck(deck, str(self.pdk))
        self.assertIn("XQ1 a b c npn", out)
        self.assertIn('.lib "${PDK_ROOT}/models/cornerMOS.lib" mos_tt', out)

    def test_lib_section_missing_nested_include_fails(self) -> None:
        self.write("work/bundle.lib", ".lib typ\n.include gone.spice\n.endl typ\n")
        deck = self.write("work/corner.cir", ".lib bundle.lib typ\n")
        with self.assertRaises(SystemExit) as cm:
            kse.inline_deck(deck, str(self.pdk))
        msg = str(cm.exception)
        self.assertIn("gone.spice", msg)
        self.assertIn("bundle.lib", msg)


class ExtractionBindingTests(TempDirCase):
    """Issue #309: PEX records bind the extraction hashes captured at generation."""

    def setUp(self) -> None:
        super().setUp()
        self.pex = self.write("layout/c/c.pex.spice", "R1 a b 1\n")
        self.design = self.write("design/netlist/c.spice", "XM1 a b c d m\n")

    def test_capture_hashes_the_bytes_read(self) -> None:
        entries, blobs = xb.capture([self.pex, self.design], self.tmp)
        self.assertEqual([e["path"] for e in entries], ["layout/c/c.pex.spice", "design/netlist/c.spice"])
        self.assertEqual(entries[0]["sha256"], xb.sha256_bytes(blobs["layout/c/c.pex.spice"]))

    def test_source_changing_during_generation_is_rejected(self) -> None:
        entries, _ = xb.capture([self.pex], self.tmp)
        self.pex.write_text("R1 a b 2\n", encoding="utf-8")
        with self.assertRaises(xb.BindingError):
            xb.assert_unchanged(entries, self.tmp)

    def test_missing_and_escaping_sources_rejected(self) -> None:
        with self.assertRaises(xb.BindingError):
            xb.capture([self.tmp / "layout/c/none.pex.spice"], self.tmp)
        outside = self.tmp.parent / "outside.spice"
        with self.assertRaises(xb.BindingError):
            xb.capture([outside], self.tmp)
        with self.assertRaises(xb.BindingError):
            xb.capture([], self.tmp)

    def test_load_captured_rejects_bad_documents(self) -> None:
        good = {"schema": xb.SCHEMA, "sources": [{"path": "a/b", "sha256": "0" * 64}]}
        for bad in (
            {"schema": "other", "sources": good["sources"]},
            {"schema": xb.SCHEMA, "sources": [{"path": "../x", "sha256": "0" * 64}]},
            {"schema": xb.SCHEMA, "sources": [{"path": "/x", "sha256": "0" * 64}]},
            {"schema": xb.SCHEMA, "sources": [{"path": "a", "sha256": "zz"}]},
            {"schema": xb.SCHEMA, "sources": []},
        ):
            f = self.write("bad.json", json.dumps(bad))
            with self.assertRaises(xb.BindingError, msg=str(bad)):
                xb.load_captured([f], self.tmp)
        f = self.write("good.json", json.dumps(good))
        self.assertEqual(xb.load_captured([f], self.tmp)[0]["path"], "a/b")

    def test_multiple_sources_merge_and_conflict(self) -> None:
        a = self.write("a.json", json.dumps({"schema": xb.SCHEMA, "sources": [{"path": "x", "sha256": "1" * 64}]}))
        b = self.write("b.json", json.dumps({"schema": xb.SCHEMA, "sources": [{"path": "y", "sha256": "2" * 64}]}))
        c = self.write("c.json", json.dumps({"schema": xb.SCHEMA, "sources": [{"path": "x", "sha256": "3" * 64}]}))
        self.assertEqual([e["path"] for e in xb.load_captured([a, b], self.tmp)], ["x", "y"])
        with self.assertRaises(xb.BindingError):
            xb.load_captured([a, c], self.tmp)

    def test_record_field_lists_every_source(self) -> None:
        entries, _ = xb.capture([self.pex, self.design], self.tmp)
        text = "\n".join(xb.record_field_lines(entries))
        for entry in entries:
            self.assertIn(f"`{entry['path']}` sha256:{entry['sha256']}", text)

    def test_pex_detection_and_emit_requires_binding(self) -> None:
        self.assertTrue(kse.is_pex({}, Path("sim/closed-loop-vref-pvt-pex")))
        self.assertTrue(kse.is_pex({}, Path("sim/closed-loop-vref-pvt-pex-boxtc")))
        self.assertFalse(kse.is_pex({}, Path("sim/closed-loop-vref-pvt")))
        self.assertFalse(kse.is_pex({"pex": False}, Path("sim/x-pex")))
        report = {"corners": [{"process": "typ", "temperature_c": 27, "supply_v": {"vdd": 3.3},
                               "status": "pass", "measurements": []}]}
        exp = self.tmp / "sim" / "demo-pex"
        with self.assertRaises(SystemExit):
            kse.emit(report, {}, exp, self.tmp, "rid")
        self.assertFalse(exp.exists())

    def test_emit_rejects_drifted_source_before_writing(self) -> None:
        entries, _ = xb.capture([self.pex], self.tmp)
        self.pex.write_text("R1 a b 9\n", encoding="utf-8")
        report = {"corners": [{"process": "typ", "temperature_c": 27, "supply_v": {"vdd": 3.3},
                               "status": "pass", "measurements": []}]}
        exp = self.tmp / "sim" / "demo-pex"
        with self.assertRaises(SystemExit):
            kse.emit(report, {}, exp, self.tmp, "rid", extraction=entries)
        self.assertFalse(exp.exists())

    def test_md_carries_binding_only_when_given(self) -> None:
        entries, _ = xb.capture([self.pex], self.tmp)
        spec = {"Experiment": "e", "Claim": "c", "PDK": "p", "request": "r",
                "Corner matrix run": "m"}
        with_binding = kse.build_md({}, spec, "rid", 1, 1, [], entries)
        without = kse.build_md({}, spec, "rid", 1, 1, [])
        self.assertIn("Extraction sources", with_binding)
        self.assertIn("layout/c/c.pex.spice", with_binding)
        self.assertNotIn("Extraction sources", without)


class PublicationTests(TempDirCase):
    """Issue #328: append-only, collision-safe, staged publication."""

    SPEC = {"Experiment": "e", "Claim": "c", "PDK": "p", "request": "r",
            "Corner matrix run": "m", "pass_requires": ["vref"]}

    def corner(self, temp: int, *, status: str = "pass", log: bool = True, deck: bool = True) -> dict:
        art: dict = {}
        if log:
            art["log"] = str(self.write(f"work/{temp}.log", f"log {temp}\n"))
        if deck:
            art["deck"] = str(self.write(f"work/{temp}.cir", f"* deck {temp}\nR1 a b 1\n"))
        return {"corner_id": f"typ/3.300V/{temp}C", "process": "typ", "temperature_c": temp,
                "supply_v": {"vdd": 3.3}, "status": status,
                "measurements": [{"name": "vref", "value": 1.2}], "artifacts": art}

    def report(self, *corners: dict) -> dict:
        bad = any(c["status"] != "pass" for c in corners)
        return {"status": "fail" if bad else "pass", "corners": list(corners)}

    def emit(self, report: dict, rid: str = "rid1") -> tuple[int, int]:
        return kse.emit(report, self.SPEC, self.exp, self.tmp, rid, store=FakeStore())

    def setUp(self) -> None:
        super().setUp()
        self.exp = self.tmp / "sim" / "demo"

    def tree(self) -> dict[str, bytes]:
        out = {}
        if self.exp.exists():
            out.update({str(p.relative_to(self.exp)): p.read_bytes()
                        for p in sorted(self.exp.rglob("*")) if p.is_file()})
        mdir = self.tmp / "manifests"
        if mdir.exists():
            out.update({"@" + str(p.relative_to(mdir)): p.read_bytes()
                        for p in sorted(mdir.rglob("*")) if p.is_file()})
        return out

    def test_pass_publishes_manifest_and_record_only(self) -> None:
        self.assertEqual(self.emit(self.report(self.corner(27), self.corner(85))), (2, 2))
        t = self.tree()
        self.assertEqual(
            sorted(t),
            [
                "@artifacts/demo-rid1.manifest.json",
                "records/rid1-report.json",
                "records/rid1.csv",
                "records/rid1.md",
            ],
        )
        # issue #629: the run's own report is committed beside the record,
        # as-written (no host paths to scrub in this fixture-less report).
        self.assertEqual(json.loads(t["records/rid1-report.json"]), self.report(self.corner(27), self.corner(85)))
        self.assertTrue(t["records/rid1.csv"].startswith(b"corner_label,temp_c,vdd_v,status,vref\n"))
        self.assertIn(b"typ,27,3.30,PASS,1.200000e+00\n", t["records/rid1.csv"])
        names = [e["name"] for e in json.loads(t["@artifacts/demo-rid1.manifest.json"])["entries"]]
        self.assertEqual(names, [
            "sim/demo/corners/rid1/typ_27c_3.30v.log", "sim/demo/corners/rid1/typ_85c_3.30v.log",
            "sim/demo/netlist-snapshots/rid1/typ_27c_3.30v.spice",
            "sim/demo/netlist-snapshots/rid1/typ_85c_3.30v.spice"])
        self.assertEqual([p.name for p in self.exp.iterdir() if p.name.startswith(".")], [])

    def test_fail_corner_is_recorded(self) -> None:
        self.assertEqual(self.emit(self.report(self.corner(27), self.corner(85, status="fail"))), (1, 2))
        t = self.tree()
        self.assertIn(b"typ,85,3.30,FAIL", t["records/rid1.csv"])
        self.assertIn(b"**Failed points**: typ_85c_3.30v", t["records/rid1.md"])

    def test_rerun_of_existing_id_changes_nothing(self) -> None:
        rep = self.report(self.corner(27))
        self.emit(rep)
        before = self.tree()
        with self.assertRaises(SystemExit) as ctx:
            self.emit(rep)
        self.assertIn("already exists", str(ctx.exception))
        self.assertEqual(self.tree(), before)

    def test_any_single_existing_path_blocks_publication(self) -> None:
        for rel in ("records/rid1.csv", "records/rid1.md"):
            with self.subTest(existing=rel):
                self.exp = self.tmp / "sim" / ("demo-" + rel.replace("/", "_"))
                path = self.exp / rel
                path.parent.mkdir(parents=True)
                path.write_bytes(b"precious")
                before = self.tree()
                with self.assertRaises(SystemExit):
                    self.emit(self.report(self.corner(27)))
                self.assertEqual(self.tree(), before)
                self.assertEqual(path.read_bytes(), b"precious")
                self.assertEqual([p.name for p in self.exp.iterdir() if p.name.startswith(".")], [])

    def test_missing_deck_on_first_corner_copies_nothing(self) -> None:
        with self.assertRaises(SystemExit):
            self.emit(self.report(self.corner(27, deck=False), self.corner(85)))
        self.assertFalse(self.exp.exists())

    def test_unresolved_nested_include_publishes_nothing(self) -> None:
        self.emit(self.report(self.corner(27)), "old")
        before = self.tree()
        bad = self.corner(85)
        self.write("work/85.cir", '* deck\n.include "missing-dut.spice"\n')
        with self.assertRaises(SystemExit) as ctx:
            self.emit(self.report(self.corner(27), bad), "new")
        self.assertIn("missing-dut.spice", str(ctx.exception))
        self.assertIn("typ_85c_3.30v", str(ctx.exception))
        self.assertEqual(self.tree(), before)
        self.assertEqual([p.name for p in self.exp.iterdir() if p.name.startswith(".")], [])

    def test_missing_later_log_leaves_no_record_and_keeps_prior(self) -> None:
        self.emit(self.report(self.corner(27)), "old")
        before = self.tree()
        with self.assertRaises(SystemExit):
            self.emit(self.report(self.corner(27), self.corner(85, log=False)), "new")
        self.assertEqual(self.tree(), before)

    def test_failure_during_staging_is_cleaned_up(self) -> None:
        rep = self.report(self.corner(27), self.corner(85))
        real = kse.shutil.copyfile
        calls = []

        def flaky(src, dst, *a, **k):
            calls.append(src)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst, *a, **k)

        kse.shutil.copyfile = flaky
        try:
            with self.assertRaises(SystemExit):
                self.emit(rep)
        finally:
            kse.shutil.copyfile = real
        self.assertEqual(self.tree(), {})
        self.assertEqual([p.name for p in self.exp.rglob(".*")], [])
        self.assertFalse((self.tmp / ".evidence-scratch").exists())
        self.emit(rep)  # the id was released, not burned

    def test_bad_ids_rejected(self) -> None:
        for bad in ("", ".", "..", "../x", "a/b", "a\\b", ".hidden", "a..b", "/abs", "x y"):
            with self.subTest(rid=bad):
                with self.assertRaises(SystemExit):
                    self.emit(self.report(self.corner(27)), bad)
        self.assertFalse(self.exp.exists())
        self.assertFalse((self.tmp / "sim" / "x").exists())

    def test_duplicate_normalised_corners_rejected(self) -> None:
        twin = self.corner(27)
        twin["corner_id"] = "typ/3.300V/27.0C"  # distinct to klt, same repo id
        with self.assertRaises(SystemExit) as ctx:
            self.emit(self.report(self.corner(27), twin))
        self.assertIn("not unique", str(ctx.exception))
        self.assertFalse(self.exp.exists())

    def test_reservation_blocks_a_concurrent_publisher(self) -> None:
        # A live publisher holds the id by its empty CSV placeholder.
        (self.exp / "records").mkdir(parents=True)
        (self.exp / "records" / "rid1.csv").write_bytes(b"")
        with self.assertRaises(SystemExit):
            self.emit(self.report(self.corner(27)))
        self.assertEqual(self.tree(), {"records/rid1.csv": b""})

    def test_binding_recheck_before_commit_leaves_nothing(self) -> None:
        pex = self.write("layout/c/c.pex.spice", "R1 a b 1\n")
        entries, _ = xb.capture([pex], self.tmp)
        real = xb.verify_captured
        seen = []

        def drifting(*a, **k):
            seen.append(1)
            if len(seen) >= 2:  # passes up front, drifts during staging
                raise xb.BindingError("source drifted")
            return real(*a, **k)

        xb.verify_captured = drifting
        try:
            with self.assertRaises(SystemExit):
                kse.emit(self.report(self.corner(27)), self.SPEC, self.exp, self.tmp, "rid1",
                         extraction=entries, store=FakeStore())
        finally:
            xb.verify_captured = real
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.tree(), {})


# --------------------------------------------------------------------------
# boxtc_companion: the box-method TC derivation (issue #465). It used to be
# typed twice, inline, in the two benches that share it -- and
# spec/decision-records/0010-box-method-tc-evidence.md ratifies its output as
# this block's TC evidence, with the design sitting ON the 20 ppm/degC stretch
# line. So the derivation gets a golden test against the committed records it
# produced, unit coverage of the parts a correction would touch, and a guard
# that the duplication cannot come back.
# --------------------------------------------------------------------------

HARNESS = Path(__file__).resolve().parent
SIM_DIR = HARNESS.parent

#: The two box-method benches and the committed record each minted.
BOXTC_BENCHES = {
    "closed-loop-vref-pvt-boxtc": "20260921-194249-77820fc",
    "closed-loop-vref-pvt-pex-boxtc": "20260921-195122-77820fc",
}


def boxtc_rows(points: list[tuple], corner: str = "typ", vdd: str = "3.30") -> list[dict]:
    """Record rows for one (corner, vdd) group from `(temp_c, vref, status)`."""
    return [
        {"corner_label": corner, "vdd_v": vdd, "temp_c": f"{t}",
         "vref_3ms_v": repr(v), "status": s}
        for t, v, s in points
    ]


#: A grid whose extremes are INTERIOR points, so the box method and the
#: endpoint method cannot agree: vref peaks at 50 C and bottoms at 0 C, while
#: -40 C and 125 C sit between them.
INTERIOR_EXTREMA = [
    (-40, 1.0400, "PASS"), (0, 1.0300, "PASS"), (27, 1.0500, "PASS"),
    (50, 1.0600, "PASS"), (125, 1.0450, "PASS"),
]


#: The endpoint benches and the newest committed record/companion pair each
#: carries -- the golden-test inputs for the endpoint derivation (issue #496).
TC_BENCHES = {
    "closed-loop-vref-pvt": "20261001-085908-e5507b2",
    "closed-loop-vref-pvt-pex": "20260905-114438-8abe2aa",
}


def endpoint_rows(points: list[tuple], corner: str = "typ",
                  vdd: str = "3.30") -> list[dict]:
    """Record rows for one (corner, vdd) group from `(temp_c, vref_3ms_v)`.

    `vref` may be a float or an already-rendered string -- the way the
    minted records carry it (`1.04695e+00`).
    """
    return [
        {"corner_label": corner, "vdd_v": vdd, "temp_c": f"{t}",
         "vref_3ms_v": v if isinstance(v, str) else repr(v)}
        for t, v in points
    ]


class BoxTcGoldenTests(unittest.TestCase):
    """The derivation still reproduces the committed evidence, byte for byte."""

    def test_committed_companions_regenerate_byte_identically(self) -> None:
        # The acceptance test for the de-duplication (#465): both benches'
        # committed -boxtc.csv must come back out of the shared module
        # unchanged, compared as raw bytes so a CRLF slip fails. sim/*/records/
        # is append-only evidence, so the same call must leave the committed
        # bytes and mtime untouched (guards against an EXP_DIR-relative
        # default). Read-only on sim/ -- output goes to a temp dir.
        for exp, stem in BOXTC_BENCHES.items():
            with self.subTest(exp=exp):
                records = SIM_DIR / exp / "records"
                committed = records / f"{stem}-boxtc.csv"
                before_mtime = committed.stat().st_mtime_ns
                before_bytes = committed.read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    got = Path(tmp) / "companion.csv"
                    bxc.write_companion(records / f"{stem}.csv", got)
                    self.assertEqual(got.read_bytes(), before_bytes)
                self.assertEqual(
                    (committed.stat().st_mtime_ns, committed.read_bytes()),
                    (before_mtime, before_bytes),
                )


class BoxTcFormulaTests(unittest.TestCase):
    """The parts of the derivation a correction would land on."""

    def one(self, points: list[tuple], **kw) -> list:
        rows = bxc.companion_rows(boxtc_rows(points, **kw))
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_box_is_the_worst_case_spread_not_the_endpoint_slope(self) -> None:
        # The whole point of the box method: the extremes are wherever they
        # fall on the grid, not at its ends. Here they are interior, so a
        # regression to an endpoint derivation changes the reported number.
        row = self.one(INTERIOR_EXTREMA)
        _, _, _, _, vmin, tmin, vmax, tmax, v27, box, endpoint = row
        self.assertEqual((float(vmin), tmin), (1.03, 0))
        self.assertEqual((float(vmax), tmax), (1.06, 50))
        self.assertAlmostEqual(float(box), 1e6 * (1.06 - 1.03) / (165 * 1.05), places=3)
        # ... and the endpoint figure is carried alongside, not instead of it.
        self.assertAlmostEqual(
            float(endpoint), 1e6 * (1.045 - 1.040) / (165 * 1.05), places=3
        )
        self.assertNotAlmostEqual(float(box), float(endpoint), places=1)

    def test_span_is_the_165_degree_grid(self) -> None:
        # The committed records disclose a 165 degC span (-40..125). It is the
        # formula's denominator, so it is a named constant, not a literal
        # repeated per copy.
        self.assertEqual(bxc.SPAN_C, 165)
        row = self.one([(-40, 1.0, "PASS"), (27, 1.0, "PASS"), (125, 1.1, "PASS")])
        self.assertAlmostEqual(float(row[9]), 1e6 * 0.1 / (165 * 1.0), places=3)

    def test_failing_points_are_excluded_from_the_number_but_disclosed(self) -> None:
        # A FAIL point must not set vmin/vmax -- it never converged -- but
        # n_grid still reports it, so n_pass/n_grid discloses the coverage
        # behind the figure.
        row = self.one([
            (-40, 0.5, "FAIL"), (0, 1.04, "PASS"), (27, 1.05, "PASS"),
            (125, 1.06, "PASS"),
        ])
        self.assertEqual((row[2], row[3]), (3, 4))        # n_pass, n_grid
        self.assertEqual(float(row[4]), 1.04)             # vmin, not the 0.5 FAIL
        self.assertEqual(row[10], "")                     # -40 C absent: no endpoint

    def test_group_without_a_passing_27c_point_is_omitted(self) -> None:
        # v27 is the denominator. Without it the derivation has no value, so
        # the group is omitted rather than reported from a substitute.
        for points in (
            [(-40, 1.04, "PASS"), (125, 1.06, "PASS")],                  # no 27 C
            [(-40, 1.04, "PASS"), (27, 1.05, "FAIL"), (125, 1.06, "PASS")],
        ):
            with self.subTest(points=points):
                self.assertEqual(bxc.companion_rows(boxtc_rows(points)), [])

    def test_group_with_no_passing_point_is_omitted(self) -> None:
        self.assertEqual(
            bxc.companion_rows(boxtc_rows([(27, 1.05, "FAIL")])), []
        )

    def test_absent_group_is_skipped_not_reported_empty(self) -> None:
        rows = bxc.companion_rows(boxtc_rows(INTERIOR_EXTREMA, corner="wcs", vdd="2.97"))
        self.assertEqual([(r[0], r[1]) for r in rows], [("wcs", "2.97")])

    def test_rows_follow_the_committed_grid_order(self) -> None:
        # Row order is part of the committed CSV's shape: corner-major over
        # (typ, bcs, wcs, sf, fs) x (2.97, 3.30, 3.63).
        rows: list[dict] = []
        for corner in reversed(bxc.CORNERS):
            for vdd in reversed(bxc.VDDS):
                rows += boxtc_rows(INTERIOR_EXTREMA, corner=corner, vdd=vdd)
        got = [(r[0], r[1]) for r in bxc.companion_rows(rows)]
        self.assertEqual(got, [(c, v) for c in bxc.CORNERS for v in bxc.VDDS])

    def test_header_matches_the_committed_companions(self) -> None:
        for exp, stem in BOXTC_BENCHES.items():
            with self.subTest(exp=exp):
                committed = (SIM_DIR / exp / "records" / f"{stem}-boxtc.csv").read_text()
                self.assertEqual(committed.splitlines()[0], ",".join(bxc.HEADER))

    def test_companion_is_newline_terminated_not_crlf(self) -> None:
        # csv.writer defaults to \r\n; the committed records are \n.
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "r.csv", Path(tmp) / "c.csv"
            with src.open("w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(["corner_label", "vdd_v", "temp_c", "vref_3ms_v", "status"])
                for t, v, s in INTERIOR_EXTREMA:
                    w.writerow(["typ", "3.30", t, v, s])
            bxc.write_companion(src, dst)
            self.assertNotIn(b"\r", dst.read_bytes())


class BoxTcSeamTests(TempDirCase):
    """The shell side: one shared implementation, and it stays shared."""

    def test_both_box_benches_delegate_to_the_shared_companion(self) -> None:
        for exp in BOXTC_BENCHES:
            with self.subTest(exp=exp):
                script = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
                self.assertIn("pex_boxtc_companion", hook)
                # The formula must not be re-typed here -- that is the
                # duplication #465 removed. No inline heredoc, no formula.
                self.assertNotIn("python3 - ", hook)
                self.assertNotIn("1e6", hook)
                self.assertNotIn("csv.writer", hook)
                self.assertIn('source "${HARNESS_DIR}/pex_vref_runner.sh"', script)

    def test_the_shared_companion_defers_the_formula_to_the_module(self) -> None:
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        body = runner.split("pex_boxtc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("boxtc_companion.py", body)
        self.assertNotIn("1e6", body)
        # The input filter is the box benches' own: it drops both companion
        # kinds. The two helpers' filters differ on purpose (#496): the
        # endpoint helper drops -vs-schematic instead.
        self.assertIn("grep -v -e '-boxtc.csv' -e '-tc.csv'", body)

    def test_the_endpoint_bench_keeps_its_own_different_body(self) -> None:
        # Reframed for #496: its premise -- the endpoint bench re-types its
        # own endpoint-method body -- became false by design when that body
        # moved into sim/harness/tc_companion.py. What remains true is the
        # separation it guarded: the endpoint bench delegates to the
        # *endpoint* companion, never the box one.
        script = (SIM_DIR / "closed-loop-vref-pvt-pex" / "run_klt_sim.sh").read_text()
        hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("pex_endpoint_tc_companion", hook)
        self.assertNotIn("pex_boxtc_companion", hook)
        self.assertNotIn("boxtc_companion", hook)

    def test_the_trim_bench_box_derivation_matches_the_module(self) -> None:
        # closed-loop-vref-boxtc-trim carries a third copy of the box
        # derivation: an awk body inside run_pvt_sweep.sh, which does not
        # source pex_vref_runner.sh, so the pex_boxtc_companion seam cannot
        # reach it (#474; delegating it is out of scope there). The copy is
        # load-bearing -- its -boxtc.csv feeds the trim-induced-TC gate that
        # DR-0013 cites -- so a correction applied to boxtc_companion.py
        # alone would silently leave the bench reporting the old derivation.
        # Until the bench delegates, this tripwire makes that divergence red.
        script = (SIM_DIR / "closed-loop-vref-boxtc-trim" / "run_pvt_sweep.sh").read_text()

        # The span is parsed from the bench and compared to the module's:
        # restating 165 on both sides would check nothing.
        span = re.search(r"TEMP_SPAN_C[ \t]*=[ \t]*([0-9]+)", script)
        self.assertIsNotNone(
            span,
            "TEMP_SPAN_C= is gone from the trim bench; its awk span must "
            "still equal boxtc_companion.SPAN_C "
            f"({bxc.SPAN_C}). boxtc_companion.py is the one place to "
            "correct the box derivation.")
        self.assertEqual(
            int(span.group(1)), bxc.SPAN_C,
            f"the trim bench's box span (TEMP_SPAN_C={span.group(1)}) no "
            f"longer equals boxtc_companion.SPAN_C ({bxc.SPAN_C}): correct "
            "boxtc_companion.py first, then this bench.")
        self.assertIn(
            '-v span="${TEMP_SPAN_C}"', script,
            "the trim bench's awk no longer takes its span from "
            "TEMP_SPAN_C; boxtc_companion.py is the one place to correct "
            "the box derivation.")

        # The box awk itself: same formula shape and PASS filter as the
        # module's group loop.
        awk_m = re.search(r"'(.*?)' \"\$\{CSV_OUT\}\"",
                          script.split('-v span="${TEMP_SPAN_C}"', 1)[1],
                          re.DOTALL)
        self.assertIsNotNone(
            awk_m,
            "the trim bench's box-TC awk is gone or no longer writes to "
            "${CSV_OUT}; boxtc_companion.py is the one place to correct "
            "the box derivation.")
        awk_prog = awk_m.group(1)
        self.assertIn(
            "1e6 * (vmax - vmin) / (span * v27)", awk_prog,
            "the trim bench's box formula drifted from the module's "
            "1e6 * (vmax - vmin) / (span * v27); boxtc_companion.py is the "
            "one place to correct the derivation.")
        self.assertIn(
            '$scol == "PASS"', awk_prog,
            "the trim bench's box derivation dropped the PASS-point filter; "
            "boxtc_companion.py is the one place to correct the derivation.")

        # Same rounding the module emits: %.5g voltages, %d integer
        # temperatures and counts, %.3f box_tc_ppm_per_c -- positionally, in
        # the companion header's column order.
        fmt = re.search(r'printf "([^"]+)"', awk_prog)
        self.assertIsNotNone(
            fmt,
            "the trim bench's box printf is gone; its companion rounding "
            "must match boxtc_companion.py's emission.")
        convs = fmt.group(1).split("\\n")[0].split(",")
        self.assertEqual(
            convs,
            ["%s", "%s", "%s", "%d", "%d",
             "%.5g", "%d", "%.5g", "%d", "%.5g", "%.3f"],
            "the trim bench's companion rounding drifted from "
            "boxtc_companion.py's (%.5g voltages, %d temperatures/counts, "
            "%.3f box_tc_ppm_per_c): correct boxtc_companion.py first, "
            "then this bench.")

    def test_shared_companion_picks_the_record_over_its_own_companions(self) -> None:
        # `ls -t` picks the newest CSV, so a companion derived by an earlier
        # run -- which is newer than the record -- must be filtered out, or
        # the derivation would consume its own output.
        records = self.tmp / "records"
        records.mkdir()
        exp, stem = next(iter(BOXTC_BENCHES.items()))
        committed = SIM_DIR / exp / "records"
        (records / f"{stem}.csv").write_bytes((committed / f"{stem}.csv").read_bytes())
        # Companions, all newer than the record, all of which must be skipped.
        for name in (f"{stem}-boxtc.csv", f"{stem}-tc.csv",
                     f"{stem}-vs-schematic-boxtc.csv"):
            (records / name).write_text("corner_label,garbage\nbad,row\n")
            os.utime(records / name, (time.time() + 10, time.time() + 10))
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'EXP_DIR="{self.tmp}"; '
            f'source "$HARNESS_DIR/pex_vref_runner.sh"; pex_boxtc_companion'
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (records / f"{stem}-boxtc.csv").read_text(),
            (committed / f"{stem}-boxtc.csv").read_text(),
        )


class EndpointTcGoldenTests(unittest.TestCase):
    """The endpoint derivation still reproduces the committed evidence."""

    def test_committed_companions_regenerate_byte_identically(self) -> None:
        # The acceptance test for the de-duplication (#496): both benches'
        # committed -tc.csv must come back out of the shared module
        # unchanged, byte for byte -- including the header and the absence
        # of CRLF, which the raw-bytes comparison enforces. sim/*/records/
        # is append-only evidence, so the same call must leave the committed
        # bytes and mtime untouched (guards against an EXP_DIR-relative
        # default). Read-only on sim/ -- output goes to a temp dir.
        for exp, stem in TC_BENCHES.items():
            with self.subTest(exp=exp):
                records = SIM_DIR / exp / "records"
                committed = records / f"{stem}-tc.csv"
                before_mtime = committed.stat().st_mtime_ns
                before_bytes = committed.read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    got = Path(tmp) / "companion.csv"
                    tcc.write_companion(records / f"{stem}.csv", got)
                    self.assertEqual(got.read_bytes(), before_bytes)
                self.assertEqual(
                    (committed.stat().st_mtime_ns, committed.read_bytes()),
                    (before_mtime, before_bytes),
                )


class EndpointTcFormulaTests(unittest.TestCase):
    """The parts of the derivation a correction would land on."""

    def one(self, points: list[tuple], **kw) -> list:
        rows = tcc.companion_rows(endpoint_rows(points, **kw))
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_tc_is_the_two_endpoint_slope(self) -> None:
        # 1e6 * (v125 - vn40) / (165 * v27): the grid's endpoints, not the
        # box method's worst-case spread -- interior extrema must not move
        # the number. (The INTERIOR_EXTREMA grid, without status: the
        # endpoint derivation does not read it.)
        row = self.one([(-40, 1.0400), (0, 1.0300), (27, 1.0500),
                        (50, 1.0600), (125, 1.0450)])
        self.assertEqual(row[:2], ["typ", "3.30"])
        self.assertAlmostEqual(
            float(row[5]), 1e6 * (1.045 - 1.04) / (165 * 1.05), places=3)
        self.assertNotAlmostEqual(
            float(row[5]), 1e6 * (1.06 - 1.03) / (165 * 1.05), places=1)

    def test_values_pass_through_verbatim_not_rerendered(self) -> None:
        # The committed convention: the record's own strings are echoed, not
        # re-rendered through Python floats -- vdd_v as `3.30`, voltages at
        # the record's precision. This is exactly the regression the inline
        # hook this module replaces would have minted (#496).
        row = self.one([(-40, "1.04695e+00"), (27, "1.04705e+00"),
                        (125, "1.04201e+00")])
        self.assertEqual(row, ["typ", "3.30", "1.04695e+00", "1.04705e+00",
                               "1.04201e+00", "-28.594"])

    def test_span_is_the_165_degree_grid(self) -> None:
        # The committed companions disclose a 165 degC span (-40..125). It
        # is the formula's denominator, so it is a named constant, not a
        # literal repeated per copy.
        self.assertEqual(tcc.SPAN_C, 165)
        row = self.one([(-40, 1.04), (27, 1.05), (125, 1.14)])
        self.assertAlmostEqual(float(row[5]), 1e6 * 0.1 / (165 * 1.05),
                               places=3)

    def test_group_missing_an_endpoint_temperature_is_omitted(self) -> None:
        # No denominator (27 C), or a missing slope endpoint: the derivation
        # has no value, so the group is omitted rather than reported from a
        # substitute or a crash (the old hook's
        # `except (KeyError, ValueError): continue`).
        for points in (
            [(-40, 1.047), (125, 1.042)],        # no 27 C: no denominator
            [(27, 1.047), (125, 1.042)],         # no -40 C
            [(-40, 1.047), (27, 1.047)],         # no 125 C
        ):
            with self.subTest(points=points):
                self.assertEqual(tcc.companion_rows(endpoint_rows(points)), [])

    def test_unparseable_voltage_is_omitted_not_crashed(self) -> None:
        self.assertEqual(
            tcc.companion_rows(
                endpoint_rows([(-40, 1.047), (27, "not-a-number"),
                               (125, 1.042)])
            ),
            [],
        )

    def test_rows_follow_the_committed_grid_order(self) -> None:
        # Row order is part of the committed CSV's shape: corner-major over
        # (typ, bcs, wcs, sf, fs) x (2.97, 3.30, 3.63).
        rows: list[dict] = []
        for corner in reversed(tcc.CORNERS):
            for vdd in reversed(tcc.VDDS):
                rows += endpoint_rows([(-40, 1.04695), (27, 1.04705),
                                       (125, 1.04201)],
                                      corner=corner, vdd=vdd)
        got = [(r[0], r[1]) for r in tcc.companion_rows(rows)]
        self.assertEqual(got, [(c, v) for c in tcc.CORNERS for v in tcc.VDDS])

    def test_header_matches_the_committed_companions(self) -> None:
        for exp, stem in TC_BENCHES.items():
            with self.subTest(exp=exp):
                committed = (SIM_DIR / exp / "records" / f"{stem}-tc.csv").read_text()
                self.assertEqual(committed.splitlines()[0], ",".join(tcc.HEADER))

    def test_companion_is_newline_terminated_not_crlf(self) -> None:
        # csv.writer defaults to \r\n; the committed companions are \n. The
        # inline hook this module replaces had exactly this bug (#496).
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "r.csv", Path(tmp) / "c.csv"
            with src.open("w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(["corner_label", "vdd_v", "temp_c", "vref_3ms_v"])
                for t, v in [(-40, 1.04695), (27, 1.04705), (125, 1.04201)]:
                    w.writerow(["typ", "3.30", t, repr(v)])
            tcc.write_companion(src, dst)
            self.assertNotIn(b"\r", dst.read_bytes())


class EndpointTcSeamTests(TempDirCase):
    """The shell side: one shared implementation, and it stays shared."""

    ENDPOINT_BENCHES = ("closed-loop-vref-pvt", "closed-loop-vref-pvt-pex")

    def test_both_endpoint_benches_delegate_to_the_shared_companion(self) -> None:
        for exp in self.ENDPOINT_BENCHES:
            with self.subTest(exp=exp):
                script = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
                self.assertIn("pex_endpoint_tc_companion", hook)
                # The formula must not be re-typed here -- that is the
                # duplication #496 removed. No inline heredoc, no formula.
                self.assertNotIn("python3 - ", hook)
                self.assertNotIn("1e6", hook)
                self.assertNotIn("csv.writer", hook)
                self.assertIn('source "${HARNESS_DIR}/pex_vref_runner.sh"', script)

    def test_the_shared_companion_defers_the_formula_to_the_module(self) -> None:
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        body = runner.split("pex_endpoint_tc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("tc_companion.py", body)
        self.assertNotIn("1e6", body)
        # The input filter is the endpoint benches' own: it drops the
        # companion kind and the extracted benches' -vs-schematic artifacts
        # (a no-op on the schematic twin). The two helpers' filters differ
        # on purpose (#496).
        self.assertIn("grep -v -e '-tc.csv' -e '-vs-schematic'", body)

    def test_the_two_tc_companions_stay_separate_derivations(self) -> None:
        # The endpoint and box methods must not collapse into one module or
        # one helper: different column sets, different companions, and a
        # ratified decision record behind one of them (#465).
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        endpoint = runner.split("pex_endpoint_tc_companion() {", 1)[1].split("\n}\n", 1)[0]
        box = runner.split("pex_boxtc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("${HARNESS_DIR}/tc_companion.py", endpoint)
        self.assertIn("-tc.csv", endpoint)
        self.assertNotIn("boxtc_companion", endpoint)
        self.assertIn("${HARNESS_DIR}/boxtc_companion.py", box)
        self.assertIn("-boxtc.csv", box)
        self.assertNotIn("${HARNESS_DIR}/tc_companion.py", box)

    def test_shared_companion_picks_the_record_over_its_own_companions(self) -> None:
        # `ls -t` picks the newest CSV, so a companion derived by an earlier
        # run -- which is newer than the record -- must be filtered out, or
        # the derivation would consume its own output.
        records = self.tmp / "records"
        records.mkdir()
        exp, stem = next(iter(TC_BENCHES.items()))
        committed = SIM_DIR / exp / "records"
        (records / f"{stem}.csv").write_bytes((committed / f"{stem}.csv").read_bytes())
        # Companions, all newer than the record, all of which must be skipped.
        for name in (f"{stem}-tc.csv", f"{stem}-vs-schematic.csv"):
            (records / name).write_text("corner_label,garbage\nbad,row\n")
            os.utime(records / name, (time.time() + 10, time.time() + 10))
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'EXP_DIR="{self.tmp}"; '
            f'source "$HARNESS_DIR/pex_vref_runner.sh"; pex_endpoint_tc_companion'
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (records / f"{stem}-tc.csv").read_text(),
            (committed / f"{stem}-tc.csv").read_text(),
        )


# --------------------------------------------------------------------------
# Loud failure when a derivation omits every group (issue #510). Both
# companions key their grid axes by the record's own strings (#496's
# pass-through convention) and omit any group whose key misses the grid, so
# a drifted key used to mint a header-only CSV and exit 0 -- empty evidence
# published as if it were derived. main() must refuse instead: non-zero
# exit, stderr naming the keys the record actually carried.
#
# Each companion is run the way the shell hooks run it -- `sys.executable
# <script>` -- because the exit status is the contract: the script hands
# main()'s return value to sys.exit, and an in-process call to main() never
# sees it (issue #746: a `return 7` passed every test).
# --------------------------------------------------------------------------


def write_record(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


RECORD_FIELDS = ["corner_label", "vdd_v", "temp_c", "vref_3ms_v", "status"]

#: The endpoint grid, as a healthy record writes it.
ENDPOINT_POINTS = [(-40, 1.04695), (27, 1.04705), (125, 1.04201)]

#: Each companion command by method: the script, the companion it writes,
#: the header that companion must carry, a record that derives, a record
#: whose every group misses the grid, and the keys the refusal must name.
TC_COMMANDS = {
    "endpoint": {
        "script": "tc_companion.py",
        "companion": "record-tc.csv",
        "header": tcc.HEADER,
        "deriving": endpoint_rows(ENDPOINT_POINTS),
        "key_miss": endpoint_rows([(float(t), v) for t, v in ENDPOINT_POINTS]),
        "missed_keys": ("typ/3.30/-40.0", "typ/3.30/27.0", "typ/3.30/125.0"),
    },
    "box": {
        "script": "boxtc_companion.py",
        "companion": "record-boxtc.csv",
        "header": bxc.HEADER,
        "deriving": boxtc_rows(INTERIOR_EXTREMA),
        "key_miss": boxtc_rows(INTERIOR_EXTREMA, vdd="3.31"),
        "missed_keys": ("typ/3.31",),
    },
}


def run_cli(script: str, argv: list[str]) -> subprocess.CompletedProcess:
    """Run a companion script the way the shell hooks do; the result carries the exit status."""
    return subprocess.run(
        [sys.executable, str(HARNESS / script), *argv],
        capture_output=True, text=True)


class TcCompanionCliTests(TempDirCase):
    """Both companion commands refuse an empty derivation (#510)."""

    def record_and_companion(self, method: str) -> tuple[Path, Path]:
        """A `record.csv` and companion path that only this method's runs touch."""
        work = self.tmp / method
        work.mkdir()
        return work / "record.csv", work / TC_COMMANDS[method]["companion"]

    def test_key_miss_exits_nonzero_naming_the_record_keys(self) -> None:
        # The issue's own example: `temperature_c` arrives as a string, so
        # temp_c renders "-40.0" and matches none of TEMPS. The box module
        # keys groups by (corner, vdd) and matches temperature numerically,
        # so there a drifted vdd is what empties every group. Either way the
        # refusal must say what the record carried.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["key_miss"])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "key-miss record still exited 0")
                self.assertIn("header-only", r.stderr)
                for key in spec["missed_keys"]:
                    self.assertIn(key, r.stderr)
                # And the refusal leaves no header-only artifact on disk
                # (#536): records/ is append-only evidence, and a companion
                # whose body is empty is one `git add -A` away from being
                # committed as derived.
                self.assertFalse(dst.exists(), "refused run left the companion on disk")

    def test_empty_record_is_a_distinct_refusal(self) -> None:
        # A record with a header and no rows read: also no evidence, but a
        # different defect than a key miss, and the message says which.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, [])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "empty record still exited 0")
                self.assertIn("no rows", r.stderr)
                self.assertNotIn("keys the record carried", r.stderr)
                self.assertFalse(dst.exists(), "refused run left the companion on disk")

    def test_a_refusal_preserves_a_preexisting_companion_intact(self) -> None:
        # Edge #536 leaves to the Builder: the companion path already holds
        # an earlier good derivation when a rerun refuses. main() refuses
        # before the destination is ever opened, so the prior companion is
        # never touched: a refused run leaves the path exactly as it found
        # it -- no header-only shell, no destroyed prior evidence.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["deriving"])
                first = run_cli(spec["script"], [str(src), str(dst)])
                self.assertEqual(first.returncode, 0, first.stderr)
                prior = dst.read_bytes()
                write_record(src, RECORD_FIELDS, [])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "empty record still exited 0")
                self.assertEqual(dst.read_bytes(), prior)

    def test_a_deriving_record_still_exits_zero(self) -> None:
        # The check must not turn a healthy derivation into a failure.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["deriving"])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    dst.read_text().splitlines()[0], ",".join(spec["header"]))


if __name__ == "__main__":
    unittest.main()
