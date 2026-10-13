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

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_pvt_report as epr  # noqa: E402
import extraction_binding as xb  # noqa: E402
import fixup_batch_report as fbr  # noqa: E402
import klt_sim_evidence as kse  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402
import submission_identity as si  # noqa: E402


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
        return kse.emit(report, self.SPEC, self.exp, self.tmp, rid)

    def setUp(self) -> None:
        super().setUp()
        self.exp = self.tmp / "sim" / "demo"

    def tree(self) -> dict[str, bytes]:
        if not self.exp.exists():
            return {}
        return {str(p.relative_to(self.exp)): p.read_bytes()
                for p in sorted(self.exp.rglob("*")) if p.is_file()}

    def test_pass_publishes_current_layout(self) -> None:
        self.assertEqual(self.emit(self.report(self.corner(27), self.corner(85))), (2, 2))
        t = self.tree()
        self.assertEqual(
            sorted(t),
            ["corners/rid1/typ_27c_3.30v.log", "corners/rid1/typ_85c_3.30v.log",
             "netlist-snapshots/rid1/typ_27c_3.30v.spice",
             "netlist-snapshots/rid1/typ_85c_3.30v.spice",
             "records/rid1.csv", "records/rid1.md"],
        )
        self.assertTrue(t["records/rid1.csv"].startswith(b"corner_label,temp_c,vdd_v,status,vref\n"))
        self.assertIn(b"typ,27,3.30,PASS,1.200000e+00\n", t["records/rid1.csv"])
        self.assertIn(b"* deck 27", t["netlist-snapshots/rid1/typ_27c_3.30v.spice"])
        self.assertEqual(t["corners/rid1/typ_85c_3.30v.log"], b"log 85\n")
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
        for rel in ("records/rid1.csv", "records/rid1.md",
                    "corners/rid1/x.log", "netlist-snapshots/rid1/x.spice"):
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
                         extraction=entries)
        finally:
            xb.verify_captured = real
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.tree(), {})


# --------------------------------------------------------------------------
# submission identity / resumable shards (#332)
# --------------------------------------------------------------------------

HARNESS = Path(__file__).resolve().parent
MOCK_KLT = """#!/usr/bin/env bash
# mock `klt`: counts submissions, writes a passing report, runs no simulator
if [[ "$1" == "--version" ]]; then echo "mock-klt 1.0"; exit 0; fi
echo "$2" >> "${MOCK_COUNT}"
echo '{"status": "pass", "corners": [{"corner_id": "typ/27C", "artifacts": {"deck": "deck.cir"}}]}'
"""


class ResumeIdentityTests(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.klt = self.write("bin/klt", MOCK_KLT)
        self.klt.chmod(0o755)
        self.count = self.tmp / "count.txt"
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.tmpl = self.write("tmpl/body.tmpl", "* template v1\n.include @@PEX@@\n")
        self.extraction = "R1 a b 1\n"
        self.make_inputs()

    def make_inputs(self, template=None, extraction=None, body_extra="", measure="vref_v",
                    axis=(-40, 27)) -> None:
        """Mimic a runner's regeneration of body / PEX include / request."""
        if template is not None:
            self.tmpl.write_text(template, encoding="utf-8")
        (self.work / "pex_body.inc").write_text(extraction or self.extraction, encoding="utf-8")
        body = self.tmpl.read_text().replace("@@PEX@@", "pex_body.inc") + body_extra
        (self.work / "body-typ.spice").write_text(body, encoding="utf-8")
        req = {"netlist": str(self.work / "body-typ.spice"),
               "corners": {"temperature_c": list(axis)},
               "measurements": [{"name": measure, "spice": f".meas tran {measure} find v(a) at=1m"}]}
        (self.work / "request-typ.json").write_text(json.dumps(req), encoding="utf-8")

    def shard(self, **env) -> subprocess.CompletedProcess:
        script = (
            f'set -euo pipefail; WORK="{self.work}"; HARNESS_DIR="{HARNESS}"; KLT_BIN="{self.klt}"; '
            f'IDENT_ARGS=(--declare "klt_version=mock" --extra "{self.tmpl}"); '
            f'source "{HARNESS}/submission_identity.sh"; '
            'si_shard request-typ.json report-typ.json artifacts-typ "typ (test)"'
        )
        e = {**os.environ, "MOCK_COUNT": str(self.count)}
        e.pop(si.ENV_ALLOW_LEGACY, None)
        e.pop(si.ENV_REDISPATCH, None)
        e.update(env)
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e)

    def submissions(self) -> int:
        return len(self.count.read_text().split()) if self.count.exists() else 0

    def first_run(self) -> None:
        r = self.shard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 1)
        self.assertTrue(si.sidecar_path(self.work / "report-typ.json").is_file())

    def test_unchanged_resume_reuses_without_redispatch(self) -> None:
        self.first_run()
        self.make_inputs()  # regeneration is byte-identical
        r = self.shard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 1)
        self.assertIn("skipping", r.stdout)

    def test_mutations_invalidate_reuse(self) -> None:
        cases = {
            "template": dict(template="* template v2\n.include @@PEX@@\n"),
            "included extraction": dict(extraction="R1 a b 2\n"),
            "request measurement": dict(measure="vref_other"),
            "request axis": dict(axis=(-40, 27, 125)),
            "generated body": dict(body_extra=".param x=1\n"),
        }
        for name, mut in cases.items():
            with self.subTest(name):
                self.setUp()
                self.first_run()
                self.make_inputs(**mut)
                r = self.shard()
                self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
                self.assertEqual(self.submissions(), 1)  # refused, not silently reused
                self.assertIn("different inputs", r.stderr)
                self.assertIn("new work dir", r.stderr.lower())
                self.tearDown()

    def test_stale_redispatch_opt_in_resubmits_and_rebinds(self) -> None:
        self.first_run()
        self.make_inputs(extraction="R1 a b 2\n")
        r = self.shard(**{si.ENV_REDISPATCH: "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 2)
        self.assertEqual(self.shard().returncode, 0)  # now bound to the new inputs
        self.assertEqual(self.submissions(), 2)

    def test_declared_identity_change_invalidates(self) -> None:
        self.first_run()
        r = subprocess.run(
            [sys.executable, str(HARNESS / "submission_identity.py"), "check",
             str(self.work / "request-typ.json"), str(self.work / "report-typ.json"),
             "--declare", "klt_version=other", "--extra", str(self.tmpl)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, si.EXIT_REFUSE)
        self.assertIn("declared", r.stderr)

    def test_legacy_report_without_sidecar_is_refused_not_trusted(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "pass"}')
        r = self.shard()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(self.submissions(), 0)
        self.assertIn("no committed submission identity", r.stderr)

    def test_legacy_report_explicit_opt_in_reuses_with_warning(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "pass"}')
        r = self.shard(**{si.ENV_ALLOW_LEGACY: "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 0)
        self.assertIn("UNBOUND", r.stdout)

    def test_sidecar_only_written_after_submission_completes(self) -> None:
        report = self.work / "report-typ.json"
        si.begin(self.work / "request-typ.json", report, [], {})
        self.assertFalse(si.sidecar_path(report).exists())
        self.assertTrue(si.pending_path(report).exists())
        # a pending identity never authorises reuse
        report.write_text('{"status": "pass"}')
        rc, _ = si.check(self.work / "request-typ.json", report, [], {}, env={})
        self.assertEqual(rc, si.EXIT_REFUSE)
        # no report written => commit refuses and no sidecar appears
        report.unlink()
        with self.assertRaises(si.IdentityError):
            si.commit(report)
        self.assertFalse(si.sidecar_path(report).exists())

    def test_inputs_changing_during_submission_are_not_committed(self) -> None:
        report = self.work / "report-typ.json"
        si.begin(self.work / "request-typ.json", report, [], {})
        report.write_text('{"status": "pass"}')
        (self.work / "pex_body.inc").write_text("R1 a b 99\n")
        with self.assertRaises(si.IdentityError):
            si.commit(report)
        self.assertFalse(si.sidecar_path(report).exists())

    def test_non_pass_report_is_redispatched(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "fail"}')
        self.assertEqual(self.shard().returncode, 0)
        self.assertEqual(self.submissions(), 1)

    def test_fixup_snapshots_original_submitted_body_not_regenerated(self) -> None:
        self.first_run()
        report = self.work / "report-typ.json"
        deck = self.work / "deck.cir"
        deck.write_text('.include "/var/tmp/eda-job-1/inputs/netlist.cir"\n')
        # the world moves on after submission: body, include, template regenerate
        self.make_inputs(template="* CHANGED\n.include @@PEX@@\n", extraction="R1 a b 777\n")
        out = self.tmp / "fixed"
        rc = fbr.main([str(report), "--runner-pdk-root", "/opt/pdk", "--local-pdk-root", "/p",
                       "--decks-out", str(out), "-o", str(self.tmp / "fixed.json")])
        self.assertEqual(rc, 0)
        fixed = json.loads((self.tmp / "fixed.json").read_text())
        deck_text = Path(fixed["corners"][0]["artifacts"]["deck"]).read_text()
        body_path = Path(deck_text.split('"')[1])
        self.assertIn("template v1", body_path.read_text())
        self.assertNotIn("CHANGED", body_path.read_text())
        self.assertEqual((body_path.parent / "pex_body.inc").read_text(), self.extraction)

    def test_fixup_refuses_tampered_snapshot_and_unbound_report(self) -> None:
        self.first_run()
        report = self.work / "report-typ.json"
        (si.snapshot_dir(report) / "closure" / "pex_body.inc").write_text("tampered")
        with self.assertRaises(SystemExit):
            fbr.main([str(report), "--local-pdk-root", "/p", "--decks-out",
                      str(self.tmp / "o"), "-o", str(self.tmp / "o.json")])
        legacy = self.work / "report-legacy.json"
        legacy.write_text('{"status": "pass", "corners": []}')
        body = self.write("b.spice", "x")
        with self.assertRaises(SystemExit):  # regenerated --body alone is not accepted
            fbr.main([str(legacy), "--body", str(body), "--local-pdk-root", "/p",
                      "--decks-out", str(self.tmp / "o2"), "-o", str(self.tmp / "o2.json")])
        self.assertEqual(fbr.main([str(legacy), "--body", str(body), "--allow-unbound",
                                   "--local-pdk-root", "/p", "--decks-out", str(self.tmp / "o3"),
                                   "-o", str(self.tmp / "o3.json")]), 0)


# --------------------------------------------------------------------------
# PWL-ramp PEX runners' merge call (issue #331): the real shell helper both
# runners source, driven against synthetic fixed shard reports.
# --------------------------------------------------------------------------

SIM_DIR = Path(__file__).resolve().parent.parent
LABELS = ("typ", "bcs", "wcs", "sf", "fs")
HBT = {"typ": "hbt_typ", "bcs": "hbt_bcs", "wcs": "hbt_wcs", "sf": "hbt_typ", "fs": "hbt_typ"}
SUPPLIES = ("2.97", "3.30", "3.63")
PEX_RUNNERS = {
    "closed-loop-vref-pvt-pex": "closed_loop_vref_pvt_pex",
    "closed-loop-psrr-pex": "closed_loop_psrr_pex",
}


class PexMergeCallTests(TempDirCase):
    def template(self, exp: str) -> Path:
        return SIM_DIR / exp / "testbench" / f"{PEX_RUNNERS[exp]}.request.json.tmpl"

    def temps(self, exp: str) -> list:
        return json.loads(self.template(exp).read_text())["corners"]["temperature_c"]

    def shards(self, exp: str, skip: tuple = (), dup: tuple = ()) -> Path:
        """Per-(label, vdd) `-fixed` reports as the runner leaves them: no
        supply axis (the ramp is baked in); vref_v encodes the shard's vdd."""
        d = self.tmp / "work"
        d.mkdir(exist_ok=True)
        for label in LABELS:
            for vdd in SUPPLIES:
                if (label, vdd) in skip:
                    continue
                corners = [
                    {
                        "corner_id": f"{HBT[label]}/novdd/{t:g}C",
                        "process": HBT[label],
                        "temperature_c": t,
                        "status": "pass",
                        "measurements": [{"name": "vref_v", "value": float(vdd)}],
                    }
                    for t in self.temps(exp)
                ]
                if (label, vdd) in dup:
                    corners = corners + corners[:1]
                rep = report_of(corners)
                (d / f"report-{label}-{vdd.replace('.', 'p')}-fixed.json").write_text(json.dumps(rep))
        return d

    def call(self, exp: str, work: Path, fn: str = "pex_merge_shards") -> subprocess.CompletedProcess:
        out = self.tmp / "report-merged.json"
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'source "$HARNESS_DIR/pex_merge_call.sh"; '
            f'CORNER_LABELS=({" ".join(LABELS)}); VDDS=({" ".join(SUPPLIES)}); '
            f'{fn} "{self.template(exp)}" "{work}" "{out}"'
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    def test_complete_grid_merges_then_reaches_enrichment(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                r = self.call(exp, work)
                self.assertEqual(r.returncode, 0, r.stderr)
                merged = json.loads((self.tmp / "report-merged.json").read_text())
                n = len(LABELS) * len(SUPPLIES) * len(self.temps(exp))
                self.assertEqual(merged["corner_count"], n)
                self.assertTrue(merged["grid"]["complete"])
                self.assertEqual(len(merged["grid"]["expected"]), n)
                enriched = self.tmp / "report-enriched.json"
                e = subprocess.run(
                    [sys.executable, str(SIM_DIR / "harness" / "enrich_pvt_report.py"),
                     str(self.tmp / "report-merged.json"), "-o", str(enriched)],
                    capture_output=True, text=True, cwd=self.tmp,
                )
                self.assertEqual(e.returncode, 0, e.stderr)
                self.assertTrue(enriched.exists())
                (self.tmp / "report-merged.json").unlink()

    def test_supply_hint_matches_each_shards_declared_supply(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                r = self.call(exp, work, "pex_merge_args")
                self.assertEqual(r.returncode, 0, r.stderr)
                args = r.stdout.splitlines()
                shard_args = [a for a in args if "@" in a]
                self.assertEqual(len(shard_args), len(LABELS) * len(SUPPLIES))
                for a in shard_args:
                    spec, path = a.split("=", 1)
                    label, vdd = spec.split("@")
                    self.assertTrue(path.endswith(f"report-{label}-{vdd.replace('.', 'p')}-fixed.json"), a)
                # End to end: every merged corner's baked vdd (vref_v) equals
                # the supply identity the hint gave it.
                self.assertEqual(self.call(exp, work).returncode, 0)
                merged = json.loads((self.tmp / "report-merged.json").read_text())
                ids = merged["grid"]["expected"]
                for c, ident in zip(merged["corners"], ids):
                    self.assertTrue(ident.endswith(f"_{c['measurements'][0]['value']:.2f}v"), ident)
                axes = args[args.index("--expect-process") + 1], args[args.index("--expect-supplies") + 1]
                self.assertEqual(axes, (",".join(LABELS), ",".join(SUPPLIES)))
                self.assertIn(
                    "--expect-temps=" + ",".join(f"{t:g}" for t in self.temps(exp)), args)
                (self.tmp / "report-merged.json").unlink()

    def test_omitted_shard_rejected_before_publication(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                (work / "report-wcs-3p63-fixed.json").unlink()
                r = self.call(exp, work)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_shard_missing_a_point_rejected(self) -> None:
        exp = "closed-loop-vref-pvt-pex"
        work = self.shards(exp)
        f = work / "report-fs-2p97-fixed.json"
        rep = json.loads(f.read_text())
        rep["corners"].pop()
        f.write_text(json.dumps(report_of(rep["corners"])))
        r = self.call(exp, work)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing", r.stderr)
        self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_duplicate_identities_rejected(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp, dup=(("typ", "3.30"),))
                r = self.call(exp, work)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("duplicate", r.stderr)
                self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_runners_no_longer_call_merger_without_a_grid(self) -> None:
        for exp in PEX_RUNNERS:
            text = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
            self.assertIn("pex_merge_shards", text)
            self.assertNotIn("merge_batch_shards.py", text.replace("(sim/harness/merge_batch_shards.py)", ""))


if __name__ == "__main__":
    unittest.main()
