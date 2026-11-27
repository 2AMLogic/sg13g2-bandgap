#!/usr/bin/env python3
"""Self-test for `lvs_reference.py`'s symbol-formula resistor guard (issue #582).

    python3 layout/test_lvs_reference.py

The IHP symbols include bend and multiplier terms. The plain-element
converter evaluates their formulae for straight, single resistors only
(``b=0``, ``m=1``). These cases check that guard, the model values at two
geometries each, and the card format for each output dialect.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lvs_reference as lvr

RHIGH_LINE = "XRPU vdd det sub! rhigh w=1u l=1411.3u {bm}"  # bandgap_top's RPU
RPPD_LINE = "XR1 vref tn0 sub! rppd w=2u l=37.2u {bm}"  # bandgap_core's R1
LINES = {"rhigh": RHIGH_LINE, "rppd": RPPD_LINE}
PDKS = ("sg13g2", "sg13cmos5l")


def _convert(line: str, pdk: str) -> str:
    return lvr._convert_device_line(line, pdk)


class ResistorGuardTest(unittest.TestCase):
    def assert_rejects(self, line: str, pdk: str, *substrings: str) -> None:
        with self.assertRaises(ValueError) as ctx:
            _convert(line, pdk)
        message = str(ctx.exception)
        for substring in substrings:
            self.assertIn(substring, message)

    def test_guard_rejects_bends_and_multipliers(self):
        invalid = {"b=1": "m=1 b=1", "m=2": "m=2 b=0"}
        for pdk in PDKS:
            for model, template in LINES.items():
                for setting, bm in invalid.items():
                    with self.subTest(pdk=pdk, model=model, setting=setting):
                        expected = f"{model} {setting}", "on line:"
                        self.assert_rejects(template.format(bm=bm), pdk, *expected)

    def test_non_numeric_b_m_fail_loudly(self):
        for pdk in PDKS:
            for param in ("b", "m"):
                with self.subTest(pdk=pdk, param=param):
                    line = RHIGH_LINE.format(bm=f"{param}={{unresolved}}")
                    expected = f"rhigh {param}=", line, "non-numeric"
                    self.assert_rejects(line, pdk, *expected)

    def test_accepts_explicit_b0_m1(self):
        line = RHIGH_LINE.format(bm="m=1 b=0")
        self.assertEqual(
            _convert(line, "sg13g2"), "RPU vdd det 1999501.666667 rhigh L=1411.3U W=1U"
        )
        self.assertEqual(
            _convert(line, "sg13cmos5l"), "RPU vdd det 1999501.7 rhigh L=1411.3U W=1U"
        )

    def test_accepts_absent_b_m(self):
        # Absent b/m default to the allowed values (the symbols' own defaults).
        accepted = (
            ("sg13cmos5l", "rppd"),
            ("sg13cmos5l", "rhigh"),
            ("sg13g2", "rhigh"),
        )
        for pdk, model in accepted:
            with self.subTest(pdk=pdk, model=model):
                _convert(LINES[model].format(bm=""), pdk)

    def test_accepts_float_spelled_b0_m1(self):
        # Float compare, not string compare: `1.0`/`0.0` are the allowed values.
        for pdk, model in (("sg13g2", "rhigh"), ("sg13cmos5l", "rppd")):
            with self.subTest(pdk=pdk, model=model):
                _convert(LINES[model].format(bm="m=1.0 b=0.0"), pdk)

    def test_runset_resistor_cards(self):
        # The runset reads a substrate node followed immediately by the model.
        self.assertEqual(
            _convert(RHIGH_LINE.format(bm=""), "sg13g2-runset"),
            "RPU vdd det sub! rhigh l=1411.3u w=1u",
        )
        self.assertEqual(
            _convert(RPPD_LINE.format(bm=""), "sg13g2-runset"),
            "R1 vref tn0 sub! rppd l=37.2u w=2u",
        )


class ResistorFormulaTest(unittest.TestCase):
    def test_pin_rppd(self):
        self.assertEqual(round(lvr._rppd_ohms(1.0, 10.0), 6), 2654.493042)
        # bandgap_core R1
        self.assertEqual(round(lvr._rppd_ohms(2.0, 37.2), 6), 4856.535394)

    def test_pin_rhigh(self):
        self.assertEqual(round(lvr._rhigh_ohms(1.0, 10.0), 6), 14326.666667)
        # bandgap_top RPU
        self.assertEqual(round(lvr._rhigh_ohms(1.0, 1411.3), 6), 1999501.666667)


if __name__ == "__main__":
    unittest.main()
