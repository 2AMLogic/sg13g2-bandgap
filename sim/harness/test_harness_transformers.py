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
            "status": s,
            "measurements": [{"name": "vref_v", "value": 1.2 + k * 1e-3}],
        }
        for k, (t, s) in enumerate(zip((-40, 27, 125), statuses))
    ]
    report = {
        "status": "pass",
        "corner_count": len(corners),
        "passed": len(corners),
        "failed": 0,
        "errored": 0,
        "corners": corners,
        "provenance": {"klt_version": "0.5.0"},
    }
    if remote is not None:
        report["environment"] = {"remote": remote}
    return report


class MergeTests(TempDirCase):
    def test_corners_concatenate_in_argument_order_not_file_order(self) -> None:
        a = self.write_json("z-first.json", shard("hbt_typ", ["pass", "pass"]))
        b = self.write_json("a-second.json", shard("hbt_wcs", ["pass"]))
        merged = mbs.merge([str(a), str(b)])
        self.assertEqual(
            [c["corner_id"] for c in merged["corners"]],
            ["hbt_typ/3.300V/-40C", "hbt_typ/3.300V/27C", "hbt_wcs/3.300V/-40C"],
        )
        reversed_ = mbs.merge([str(b), str(a)])
        self.assertEqual(reversed_["corners"][0]["corner_id"], "hbt_wcs/3.300V/-40C")

    def test_label_rewrites_process_and_corner_id_prefix(self) -> None:
        # sf/fs share hbt_typ with typ: only the label recovers the repo name.
        typ = self.write_json("typ.json", shard("hbt_typ", ["pass"]))
        sf = self.write_json("sf.json", shard("hbt_typ", ["pass", "pass"]))
        merged = mbs.merge([f"typ={typ}", f"sf={sf}"])
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
        merged = mbs.merge([str(p), str(e)])
        self.assertEqual(
            {k: merged[k] for k in ("corner_count", "passed", "failed", "errored", "status")},
            {"corner_count": 5, "passed": 4, "failed": 0, "errored": 1, "status": "error"},
        )
        # fail outranks error, whatever order the shards come in
        merged = mbs.merge([str(f), str(e), str(p)])
        self.assertEqual(
            {k: merged[k] for k in ("corner_count", "passed", "failed", "errored", "status")},
            {"corner_count": 6, "passed": 4, "failed": 1, "errored": 1, "status": "fail"},
        )
        merged = mbs.merge([str(p)])
        self.assertEqual((merged["status"], merged["passed"]), ("pass", 3))

    def test_remote_becomes_fleet_array_with_a_slot_per_shard(self) -> None:
        local = self.write_json("l.json", shard("typ", ["pass"]))
        r1 = self.write_json("r1.json", shard("bcs", ["pass"], remote={"job_id": "j1"}))
        merged = mbs.merge([str(local), str(r1)])
        self.assertEqual(merged["environment"]["remote"], {"fleet": [None, {"job_id": "j1"}]})
        all_local = mbs.merge([str(local)])
        self.assertNotIn("remote", all_local["environment"])

    def test_provenance_note_counts_shards_and_keeps_existing_fields(self) -> None:
        paths = [str(self.write_json(f"{n}.json", shard(n, ["pass"]))) for n in ("a", "b", "c")]
        prov = mbs.merge(paths)["provenance"]
        self.assertEqual(prov["klt_version"], "0.5.0")
        self.assertIn("merged from 3 per-process batch reports", prov["batch_shard_merge"])

    def test_no_reports_is_an_error(self) -> None:
        with self.assertRaises(SystemExit):
            mbs.merge([])


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

    def test_unreadable_or_outside_pdk_kept_as_card(self) -> None:
        deck = self.write("work/corner.cir", '.include "/nonexistent/x.spice"\n')
        self.assertEqual(kse.inline_deck(deck, str(self.pdk)), ['.include "/nonexistent/x.spice"'])

    def test_include_cycle_is_guarded(self) -> None:
        self.write("work/a.spice", ".include b.spice\nRA a 0 1\n")
        self.write("work/b.spice", ".include a.spice\nRB b 0 1\n")
        deck = self.write("work/corner.cir", ".include a.spice\n")
        out = kse.inline_deck(deck, None)
        self.assertEqual(out.count("RA a 0 1"), 1)
        self.assertEqual(out.count("RB b 0 1"), 1)
        self.assertIn('.include "a.spice"', out)  # the back-edge stays a card


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


if __name__ == "__main__":
    unittest.main()
