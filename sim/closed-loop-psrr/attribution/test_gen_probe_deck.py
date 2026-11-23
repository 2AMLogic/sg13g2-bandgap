#!/usr/bin/env python3
"""Self-test of gen_probe_deck.py (issue #682). Stdlib only: no simulator, no PDK.

Guards the refactor onto the shared sim/harness modules: every committed deck
under decks/ must regenerate byte-for-byte (only the `wrdata <abs>.ac.txt`
output path is normalized), CORNER_SECTIONS is the harness's single table,
FAIL seed rows are never used, and `+`-stacked quiet-*/resize variants commute.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "harness"))
import gen_probe_deck as g  # noqa: E402
import klt_corner_bundle  # noqa: E402

DECK_RE = re.compile(r"^(lg_)?(.+)_([a-z]+)_(-?[0-9.]+)c_([0-9.]+)v\.spice$")
WRDATA_RE = re.compile(r"^(wrdata )\S+\.ac\.txt", re.M)


def norm(text: str) -> str:
    return WRDATA_RE.sub(r"\1<AC_OUT>", text)


def gen(corner, temp, vdd, variant, loop_gain=False, seed_csv=None) -> str:
    """Run g.main() into a temp file and return the deck text."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "deck.spice"
        argv = ["gen_probe_deck.py", "--corner", corner, "--temp", str(temp),
                "--vdd", str(vdd), "--variant", variant, "--token-paths",
                "-o", str(out)] + (["--loop-gain"] if loop_gain else [])
        saved = (sys.argv, g.newest_seed_csv)
        sys.argv = argv
        if seed_csv is not None:
            g.newest_seed_csv = lambda: str(seed_csv)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                g.main()
        finally:
            sys.argv, g.newest_seed_csv = saved
        return out.read_text()


class GenProbeDeck(unittest.TestCase):
    def test_committed_decks_regenerate_byte_for_byte(self):
        decks = sorted((HERE / "decks").glob("*.spice"))
        self.assertTrue(decks)
        for path in decks:
            m = DECK_RE.match(path.name)
            self.assertIsNotNone(m, path.name)
            lg, variant, corner, temp, vdd = m.groups()
            with self.subTest(deck=path.name):
                self.assertEqual(norm(gen(corner, temp, vdd, variant, bool(lg))),
                                 norm(path.read_text()))

    def test_corner_sections_is_the_harness_table(self):
        self.assertIs(g.CORNER_SECTIONS, klt_corner_bundle.CORNER_SECTIONS)

    def test_fail_seed_rows_are_skipped(self):
        hdr = ("corner_label,temp_c,vdd_v,status,fb_final_v,sns1_final_v,"
               "sns2_final_v,vref_final_v\n")
        with tempfile.TemporaryDirectory() as td:
            only_fail = Path(td) / "f.csv"
            only_fail.write_text(hdr + "bcs,125,3.63,FAIL,9.1,9.2,9.3,9.4\n")
            with self.assertRaises(SystemExit):
                gen("bcs", 125, 3.63, "asbuilt", seed_csv=only_fail)
            both = Path(td) / "b.csv"
            both.write_text(hdr + "bcs,125,3.63,FAIL,9.1,9.2,9.3,9.4\n"
                            "bcs,125,3.63,PASS,1.1,1.2,1.3,1.4\n")
            deck = gen("bcs", 125, 3.63, "asbuilt", seed_csv=both)
            self.assertIn("v(fb)=1.1", deck)
            self.assertNotRegex(deck, r"(?m)^\.nodeset .*9\.1")

    def test_stacked_variants_commute(self):
        for a, b in (("corepmos-l2", "quiet-core"), ("xmp34-l2", "quiet-p34")):
            with self.subTest(pair=(a, b)):
                x = gen("bcs", 125, 3.63, f"{a}+{b}")
                y = gen("bcs", 125, 3.63, f"{b}+{a}")
                # headers differ only in the variant-name/description order
                self.assertEqual(norm(x).split("\n", 4)[4], norm(y).split("\n", 4)[4])

    def test_resize_scales_each_devices_own_wl(self):
        deck = gen("bcs", 125, 3.63, "corepmos-l2")
        self.assertRegex(deck, r"(?m)^XM1 sns1 fb vdd vdd sg13_hv_pmos w=20u l=2u")
        self.assertRegex(deck, r"(?m)^XM2A sns2 fb vdd vdd sg13_hv_pmos w=18u l=2u")


if __name__ == "__main__":
    unittest.main()
