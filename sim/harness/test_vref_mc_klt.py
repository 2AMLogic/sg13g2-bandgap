#!/usr/bin/env python3
"""Self-test of sim/harness/vref_mc_klt.py (issue #403). Stdlib only: no simulator, no PDK."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vref_mc_klt as vm  # noqa: E402

TEMPLATE = ("* point=@@POINT_LABEL@@ draw=@@DRAW_INDEX@@ temp=@@TEMP_C@@\n.options rndseed=@@SEED@@\n"
            ".nodeset v(fb)=@@FB_SEED@@ v(sns1)=@@SNS1_SEED@@ v(sns2)=@@SNS2_SEED@@ v(vref)=@@VREF_SEED@@\n"
            ".lib \"@@PDK_ROOT@@/@@PDK@@/m.lib\" @@HBT_SECTION@@ @@MOS_SECTION@@ @@RES_SECTION@@\n"
            "w=@@MSENSE_W@@ @@OSDI_DIR@@ @@DUT_GIT_SHA@@ @@VDD@@ @@CORNER_LABEL@@ @@MISMATCH_MODE@@\n")


def ctx():
    row = {"fb_final_v": "2.5", "sns1_final_v": "0.7", "sns2_final_v": "0.7", "vref_final_v": "1.05"}
    seeds = {(c, str(t), "3.30"): row for c, t in
             (("typ", 27), ("bcs", -40), ("bcs", 125), ("wcs", -40), ("wcs", 125))}
    return {"seeds": seeds, "seed_csv": "x.csv", "seed": 20260909, "pdk": "p", "pdk_root": "/r",
            "osdi_dir": "/o", "msense_w": "10u", "dut_sha": "sha"}


class RenderTests(unittest.TestCase):
    def test_seed_is_base_plus_draw_index(self):
        for d in (0, 2, 299):
            deck = vm.render_deck(TEMPLATE, ctx(), "nominal", d)
            self.assertIn(f".options rndseed={20260909 + d}\n", deck)

    def test_sections_and_temperature_per_point(self):
        self.assertIn("hbt_typ_mismatch mos_tt_mismatch res_typ_mismatch",
                      vm.render_deck(TEMPLATE, ctx(), "nominal", 0))
        self.assertIn("hbt_typ mos_tt res_typ\n", vm.render_deck(TEMPLATE, ctx(), "negctrl", 0))
        self.assertIn("temp=-40", vm.render_deck(TEMPLATE, ctx(), "wcs_n40", 0))
        self.assertIn("hbt_wcs_mismatch", vm.render_deck(TEMPLATE, ctx(), "wcs_125", 0))

    def test_unfilled_placeholder_refused(self):
        with self.assertRaises(SystemExit):
            vm.render_deck(TEMPLATE + "@@NOPE@@\n", ctx(), "nominal", 0)


class VerdictTests(unittest.TestCase):
    G = {"fb": "2.5", "sns1": "0.70", "sns2": "0.705", "det": "0.008", "i_mkfb": "1e-13"}

    def test_closed_loop_pass(self):
        self.assertTrue(vm.closed_loop_ok(self.G))

    def test_open_loop_and_railed_fail(self):
        self.assertFalse(vm.closed_loop_ok({**self.G, "sns2": "0.80"}))
        self.assertFalse(vm.closed_loop_ok({**self.G, "fb": "3.29"}))
        self.assertFalse(vm.closed_loop_ok({**self.G, "det": "1.0"}))


class StatTests(unittest.TestCase):
    def row(self, point, v, status="PASS"):
        r = [""] * 19
        r[0], r[11], r[18] = point, status, str(v)
        return r

    def test_zero_spread_negctrl(self):
        cells = vm.stat_block([self.row("negctrl", 1.047) for _ in range(5)], "negctrl")
        self.assertEqual(cells[:2], ["5", "5"])
        self.assertEqual(cells[3], "0.000000")

    def test_failed_draw_counts_in_n_draws_only(self):
        rows = [self.row("nominal", 1.0), self.row("nominal", 1.1), self.row("nominal", "", "FAIL")]
        cells = vm.stat_block(rows, "nominal")
        self.assertEqual(cells[:2], ["3", "2"])


if __name__ == "__main__":
    unittest.main()
