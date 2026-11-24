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
import subprocess
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
                expected = path.read_text()
                seed = re.search(r"^\* [^\n]*; seeds from ([\w.-]+\.csv)$", expected, re.M)
                self.assertIsNotNone(seed, "missing seed filename in deck header")
                seed_csv = HERE.parent.parent / "closed-loop-startup" / "records" / seed[1]
                actual = gen(corner, temp, vdd, variant, bool(lg), seed_csv=seed_csv)
                self.assertEqual(norm(actual), norm(expected))

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

    def test_resize_rejects_reused_instance_name(self):
        xmp1 = "XMP1 d1 sns2 tail vdd sg13_hv_pmos w=20u l=1u"
        xmp2 = "XMP2 d2 sns1 tail vdd sg13_hv_pmos w=20u l=1u"
        lines = [".subckt bandgap_trim in out sub", xmp1, ".ends", xmp1, xmp2]
        _, transforms = g.VARIANTS["p12-w2"]
        with self.assertRaisesRegex(SystemExit, "duplicate instance XMP1"):
            for transform in transforms:
                lines = transform(lines, {})


class EmitResultTests(unittest.TestCase):
    """run_probe.sh's consolidated log parser (issue #707): the two
    back-to-back `python3 -` grab() heredocs are one emit_result helper now.
    These run the helper's embedded python directly, with the same argv shape
    `python3 - "$@"` gives it."""

    @classmethod
    def setUpClass(cls):
        text = (HERE / "run_probe.sh").read_text(encoding="utf-8")
        fn = text.index("emit_result() {")
        heredoc = text.index("<<'PY'", fn)
        cls.payload = text[heredoc + len("<<'PY'\n"):text.index("\nPY\n", heredoc)]

    def emit(self, log_text, *args):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "x.log"
            log.write_text(log_text, encoding="utf-8")
            return subprocess.run([sys.executable, "-", str(log), *args],
                                  input=self.payload, capture_output=True,
                                  text=True)

    def test_psrr_result_line_shape(self):
        log_text = ("psrr_dc_probe_db = 5.9685e+01\n"
                    "vref_dc_phase_deg = 1.5e+00\n"
                    "v(fb) = 2.49e+00\nv(vref) = 1.05e+00\n"
                    "i(vvdd) = -1.2e-04\n")
        r = self.emit(
            log_text,
            "psrr_dc_db=psrr_dc_probe_db = ([0-9.eE+-]+)",
            "vref_dc_phase_deg=vref_dc_phase_deg = ([0-9.eE+-]+)",
            "fb_op_v=v\\(fb\\) = ([0-9.eE+-]+)",
            "vref_op_v=v\\(vref\\) = ([0-9.eE+-]+)",
            "iq_a=i\\(vvdd\\) = (-?[0-9.eE+-]+)",
            "--", "corner=bcs", "temp=125", "vdd=3.63", "variant=asbuilt",
            "psrr_dc_db={psrr_dc_db}", "vref_dc_phase_deg={vref_dc_phase_deg}",
            "fb_op_v={fb_op_v}", "vref_op_v={vref_op_v}", "iq_a={iq_a}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            r.stdout,
            "RESULT corner=bcs temp=125 vdd=3.63 variant=asbuilt "
            "psrr_dc_db=5.9685e+01 vref_dc_phase_deg=1.5e+00 "
            "fb_op_v=2.49e+00 vref_op_v=1.05e+00 iq_a=-1.2e-04\n")

    def test_missing_grab_exits_naming_the_field(self):
        r = self.emit("nothing to parse here\n",
                      "fb_op_v=v\\(fb\\) = ([0-9.eE+-]+)",
                      "--", "fb_op_v={fb_op_v}")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fb_op_v", r.stderr)

    def test_one_definition_two_call_sites_no_stray_grab(self):
        text = (HERE / "run_probe.sh").read_text(encoding="utf-8")
        self.assertEqual(text.count("emit_result() {"), 1)
        self.assertEqual(text.count('emit_result "${STEM}.log"'), 2)
        self.assertNotIn("def grab(", text)


if __name__ == "__main__":
    unittest.main()
