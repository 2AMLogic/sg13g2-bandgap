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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lvs_reference as lvr

RHIGH_LINE = "XRPU vdd det sub! rhigh w=1u l=1411.3u {bm}"  # bandgap_top's RPU
RPPD_LINE = "XR1 vref tn0 sub! rppd w=2u l=37.2u {bm}"  # bandgap_core's R1


def _convert(line: str, pdk: str) -> str:
    return lvr._convert_device_line(line, pdk)


def _expect_value_error(line: str, pdk: str, *substrings: str) -> None:
    try:
        _convert(line, pdk)
    except ValueError as e:
        message = str(e)
        for substring in substrings:
            assert substring in message, (
                f"ValueError raised but missing {substring!r}:\n{message}"
            )
        return
    raise AssertionError(f"expected ValueError for {line!r} (pdk={pdk}), got none")


def case_guard_rejects_b1_cmos5l_rppd():
    _expect_value_error(
        RPPD_LINE.format(bm="m=1 b=1"), "sg13cmos5l", "rppd b=1", "on line:"
    )


def case_guard_rejects_b1_cmos5l_rhigh():
    _expect_value_error(
        RHIGH_LINE.format(bm="m=1 b=1"), "sg13cmos5l", "rhigh b=1", "on line:"
    )


def case_guard_rejects_b1_sg13g2_rhigh():
    _expect_value_error(
        RHIGH_LINE.format(bm="m=1 b=1"), "sg13g2", "rhigh b=1", "on line:"
    )


def case_guard_rejects_m2_cmos5l_rppd():
    _expect_value_error(
        RPPD_LINE.format(bm="m=2 b=0"), "sg13cmos5l", "rppd m=2", "on line:"
    )


def case_guard_rejects_m2_cmos5l_rhigh():
    _expect_value_error(
        RHIGH_LINE.format(bm="m=2 b=0"), "sg13cmos5l", "rhigh m=2", "on line:"
    )


def case_guard_rejects_m2_sg13g2_rhigh():
    _expect_value_error(
        RHIGH_LINE.format(bm="m=2 b=0"), "sg13g2", "rhigh m=2", "on line:"
    )


def case_accepts_explicit_b0_m1():
    line = RHIGH_LINE.format(bm="m=1 b=0")
    assert _convert(line, "sg13g2") == "RPU vdd det 1999501.666667 rhigh L=1411.3U W=1U"
    assert _convert(line, "sg13cmos5l") == "RPU vdd det 1999501.7 rhigh L=1411.3U W=1U"


def case_runset_resistor_cards():
    # The runset reads a substrate node followed immediately by the model.
    assert _convert(RHIGH_LINE.format(bm=""), "sg13g2-runset") == (
        "RPU vdd det sub! rhigh l=1411.3u w=1u"
    )
    assert _convert(RPPD_LINE.format(bm=""), "sg13g2-runset") == (
        "R1 vref tn0 sub! rppd l=37.2u w=2u"
    )


def case_accepts_absent_b_m():
    # Absent b/m default to the allowed values (the symbols' own defaults).
    _convert(RPPD_LINE.format(bm=""), "sg13cmos5l")
    _convert(RHIGH_LINE.format(bm=""), "sg13cmos5l")
    _convert(RHIGH_LINE.format(bm=""), "sg13g2")


def case_accepts_float_spelled_b0_m1():
    # Float compare, not string compare: `1.0`/`0.0` are the allowed values.
    _convert(RHIGH_LINE.format(bm="m=1.0 b=0.0"), "sg13g2")
    _convert(RPPD_LINE.format(bm="m=1.0 b=0.0"), "sg13cmos5l")


def case_non_numeric_b_m_fail_loudly():
    for pdk in ("sg13g2", "sg13cmos5l"):
        for param in ("b", "m"):
            line = RHIGH_LINE.format(bm=f"{param}={{unresolved}}")
            _expect_value_error(line, pdk, f"rhigh {param}=", line, "non-numeric")


def case_guard_rejects_b1_sg13g2_rppd():
    _expect_value_error(
        RPPD_LINE.format(bm="m=1 b=1"), "sg13g2", "rppd b=1", "on line:"
    )


def case_guard_rejects_m2_sg13g2_rppd():
    _expect_value_error(
        RPPD_LINE.format(bm="m=2 b=0"), "sg13g2", "rppd m=2", "on line:"
    )


def case_pin_rppd():
    assert round(lvr._rppd_ohms(1.0, 10.0), 6) == 2654.493042
    assert round(lvr._rppd_ohms(2.0, 37.2), 6) == 4856.535394  # bandgap_core R1


def case_pin_rhigh():
    assert round(lvr._rhigh_ohms(1.0, 10.0), 6) == 14326.666667
    assert round(lvr._rhigh_ohms(1.0, 1411.3), 6) == 1999501.666667  # bandgap_top RPU


CASES = [
    ("guard rejects b=1 (cmos5l rppd)", case_guard_rejects_b1_cmos5l_rppd),
    ("guard rejects b=1 (cmos5l rhigh)", case_guard_rejects_b1_cmos5l_rhigh),
    ("guard rejects b=1 (sg13g2 rhigh)", case_guard_rejects_b1_sg13g2_rhigh),
    ("guard rejects m=2 (cmos5l rppd)", case_guard_rejects_m2_cmos5l_rppd),
    ("guard rejects m=2 (cmos5l rhigh)", case_guard_rejects_m2_cmos5l_rhigh),
    ("guard rejects m=2 (sg13g2 rhigh)", case_guard_rejects_m2_sg13g2_rhigh),
    ("accepts explicit b=0 m=1", case_accepts_explicit_b0_m1),
    ("accepts absent b/m", case_accepts_absent_b_m),
    ("accepts float-spelled b=0.0 m=1.0", case_accepts_float_spelled_b0_m1),
    ("non-numeric b/m fail loudly", case_non_numeric_b_m_fail_loudly),
    ("runset retains the substrate tie", case_runset_resistor_cards),
    ("guard rejects b=1 (sg13g2 rppd)", case_guard_rejects_b1_sg13g2_rppd),
    ("guard rejects m=2 (sg13g2 rppd)", case_guard_rejects_m2_sg13g2_rppd),
    ("rppd formula at two geometries", case_pin_rppd),
    ("rhigh formula at two geometries", case_pin_rhigh),
]


def main() -> int:
    failures = 0
    for name, case in CASES:
        try:
            case()
        except Exception as e:  # noqa: BLE001 -- one bad case must not kill the run
            failures += 1
            print(f"  FAIL {name}\n       {e!r}", file=sys.stderr)
        else:
            print(f"  ok   {name}")
    if failures:
        print(f"\n{failures}/{len(CASES)} self-test case(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nOK: {len(CASES)}/{len(CASES)} self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
