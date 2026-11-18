#!/usr/bin/env python3
"""Self-test for `lvs_reference.py`'s symbol-formula resistor guard (issue #582).

    python3 layout/test_lvs_reference.py

The `.sym` ``value=`` formulae the resistor helpers transcribe carry bend
(``@b``) and multiplier (``@m``) terms the transcription drops -- valid only
for ``b=0``/``m=1``. Before #582 that precondition lived in docstrings only;
now `_require_formula_preconditions` enforces it in both formula branches of
`_convert_device_line`. These cases prove the guard rejects a bent or
multiplied resistor loudly (naming model, parameter and line), accepts the
explicit, absent and float-spelled allowed values, leaves the flat-sheet
sg13g2 flavours unguarded (they never used the formula), and pins each
formula helper's value at one (w, l) point so a constant cannot drift
silently. White-box: `lvs_reference` imports stdlib only (os/re), so the
module is imported directly -- no klayout, no PDK, no network.
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
    # The committed netlists' only spelling today: explicit `m=1 b=0`.
    out = _convert(RHIGH_LINE.format(bm="m=1 b=0"), "sg13g2")
    # Pinned card shape too (`.1f` value, model as positional token, L=/W=):
    # the sg13g2 rhigh formula at w=1u l=1411.3u is 1999501.666..., `.1f` ->
    # "1999501.7" (issue #563's +4.2% finding, kept pinned here) -- the same
    # bytes bandgap_startup.lvs_reference.spice's RPU card carries.
    assert out == "RPU vdd det 1999501.7 rhigh L=1411.3U W=1U", out


def case_accepts_absent_b_m():
    # Absent b/m default to the allowed values (the symbols' own defaults).
    _convert(RPPD_LINE.format(bm=""), "sg13cmos5l")
    _convert(RHIGH_LINE.format(bm=""), "sg13cmos5l")
    _convert(RHIGH_LINE.format(bm=""), "sg13g2")


def case_accepts_float_spelled_b0_m1():
    # Float compare, not string compare: `1.0`/`0.0` are the allowed values.
    _convert(RHIGH_LINE.format(bm="m=1.0 b=0.0"), "sg13g2")
    _convert(RPPD_LINE.format(bm="m=1.0 b=0.0"), "sg13cmos5l")


def case_non_numeric_m_fails_loudly():
    # A braced/unresolved parameter (xschem `m={m}`) must not silently pass.
    _expect_value_error(
        RHIGH_LINE.format(bm="m={m} b=0"), "sg13g2", "rhigh m=", "on line:"
    )


def case_flat_sheet_sg13g2_rppd_not_guarded():
    # `rppd` on sg13g2 stays on the flat sheet table (not in
    # `_SG13G2_RES_OHMS`) -- it never used a formula, so no precondition
    # guard: a bent/multiplied call is accepted (and valued flat, unchanged:
    # 260 Ohm/sq * 37.2/2 = 4836.0, R1's committed card value).
    out = _convert(RPPD_LINE.format(bm="b=1 m=2"), "sg13g2")
    assert out == "R1 vref tn0 4836.0 rppd L=37.2U W=2U", out


def case_pin_cmos5l_rppd():
    # 70 uOhm*m end term + 260 Ohm/sq over (w + 6 nm), at w=1u l=10u:
    # 70.0 + 2600/1.006. Pinned to 6 decimals -- any constant drift moves
    # earlier digits.
    assert round(lvr._cmos5l_rppd_ohms(1.0, 10.0), 6) == 2654.493042


def case_pin_cmos5l_rhigh():
    # 160 uOhm*m end term + 1360 Ohm/sq over (w - 40 nm), at w=1u l=10u:
    # 160.0 + 13600/0.96.
    assert round(lvr._cmos5l_rhigh_ohms(1.0, 10.0), 6) == 14326.666667


def case_pin_sg13g2_rhigh():
    # Same constants as the CMOS5L sibling, at bandgap_top's RPU point
    # (w=1u l=1411.3u): 160.0 + 1360*1411.3/0.96 -- issue #563's corrected
    # reference value.
    assert round(lvr._sg13g2_rhigh_ohms(1.0, 1411.3), 6) == 1999501.666667


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
    ("non-numeric m fails loudly", case_non_numeric_m_fails_loudly),
    ("flat-sheet sg13g2 rppd not guarded", case_flat_sheet_sg13g2_rppd_not_guarded),
    ("pins _cmos5l_rppd_ohms at (1u, 10u)", case_pin_cmos5l_rppd),
    ("pins _cmos5l_rhigh_ohms at (1u, 10u)", case_pin_cmos5l_rhigh),
    ("pins _sg13g2_rhigh_ohms at RPU's (1u, 1411.3u)", case_pin_sg13g2_rhigh),
]


def main() -> int:
    failures = 0
    for name, case in CASES:
        try:
            case()
        except AssertionError as e:
            failures += 1
            print(f"  FAIL {name}\n       {e}", file=sys.stderr)
        else:
            print(f"  ok   {name}")
    if failures:
        print(f"\n{failures}/{len(CASES)} self-test case(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nOK: {len(CASES)}/{len(CASES)} self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
