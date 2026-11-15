#!/usr/bin/env python3
"""Self-test of sim/harness/vref_mc_klt.py (issue #403). Stdlib only: no simulator, no PDK."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trim_mc_klt as tm  # noqa: E402
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


class SharedSeamTests(unittest.TestCase):
    """Issue #463: this module must reach the shared Monte Carlo plumbing through
    trim_mc_klt rather than re-typing it. A re-typed copy drifts silently --
    both harnesses keep running and minting passing evidence against *different*
    PDK corner sections -- so identity, not equality, is what is asserted."""

    #: Names this module is required to take from trim_mc_klt, not define.
    IMPORTED = ("sections_for", "make_ctx", "op_value", "Results", "BAD_LOG", "SEED_FIELDS")
    #: Names it must not hold a copy of; it reaches these through sections_for.
    NOT_COPIED = IMPORTED + ("HBT", "MOS", "RES", "load_seeds")

    def test_shared_names_are_imported_not_re_implemented(self):
        for name in self.IMPORTED:
            self.assertIs(getattr(vm, name, None), getattr(tm, name),
                          f"{name} must be the trim_mc_klt object, not a local copy")

    def test_no_shared_name_is_shadowed_by_a_local_copy(self):
        # Catches a re-typed definition even for a name this module does not
        # import today (the HBT/MOS/RES corner->section maps, load_seeds).
        for name in self.NOT_COPIED:
            own = vars(vm).get(name, None)
            if own is not None:
                self.assertIs(own, getattr(tm, name),
                              f"{name} must be trim_mc_klt's, not re-typed here")

    def test_sections_resolves_against_this_modules_own_point_set(self):
        # The trap the shared derivation has to avoid: the point sets differ, so
        # `sections` must stay local even though the derivation is shared.
        self.assertEqual(vm.sections("bcs_125"),
                         ("hbt_bcs_mismatch", "mos_ff_mismatch", "res_bcs_mismatch"))
        self.assertEqual(vm.sections("negctrl"), ("hbt_typ", "mos_tt", "res_typ"))
        with self.assertRaises(KeyError):
            tm.sections("bcs_125")      # a vref-only point
        with self.assertRaises(KeyError):
            vm.sections("bcs")          # a trim-only point


if __name__ == "__main__":
    unittest.main()
