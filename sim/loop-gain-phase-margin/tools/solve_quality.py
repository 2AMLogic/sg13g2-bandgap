#!/usr/bin/env python3
"""AC solve-quality gate for the loop-gain bench (issue #289).

One definition, two callers: run_pvt_sweep.sh (through the `check` CLI below,
over the bench's own `wrdata` file) and tools/klt_trim_axis.py (imported). A
sweep whose response fails the gate is NOT reported as a margin.

WHY. Issue #271 found that a single AC sweep of this deck can return a
numerically corrupted loop-gain response (the AC matrix spans a very wide
conductance range: 1 mOhm / 1 TOhm trim straps, a 1e9 H loop-break inductor)
and that the bench's hard bar (PM > 0 at the first falling crossing) cannot
tell such a sweep from a real one. The corrupted solves show point-to-point
jumps of 4-25 dB in |T| between 10 and 200 MHz.

THE METRIC. `ripple_db` = max over the band 10-200 MHz of
|mag_db[n] - median(mag_db[n-1], mag_db[n], mag_db[n+1])|. A smooth response
on a log grid departs from its 3-point median by a fraction of slope x step;
an isolated noisy point departs by dB.

THE THRESHOLD, RIPPLE_MAX_DB = 1.0 dB, was calibrated on every committed
`*.ac.txt` that carries this deck's loop gain (dec 30 and dec 300 grids):
clean solves read <= 0.6643 dB, corrupted solves >= 4.0985 dB (see
README "Solve-quality gate"). 1.0 dB sits in that gap. Limits: this detects
the observed signature (isolated multi-dB jumps in 10-200 MHz). It does NOT
claim to detect every possible solver corruption -- corruption outside that
band, or a smooth-but-wrong response, passes. The `temperature limiting
function received NaN` ngspice message is deliberately NOT a criterion: it
appears in about half of the clean solves too.

Other rejection reasons (fail closed): no data, non-finite / unparseable
values, a sweep that does not span 1 Hz..~1 GHz, too few points in the band.

CLI (the shell bench's interface):
    solve_quality.py check <ac.txt>
prints one line: `<OK|REJECT> <ripple_db|-> <reason|none>`; exit status 0.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

RIPPLE_BAND_HZ = (1e7, 2e8)
RIPPLE_MAX_DB = 1.0
MIN_BAND_POINTS = 5
SWEEP_MIN_HZ_MAX = 1.5     # first swept frequency must be <= this
SWEEP_MAX_HZ_MIN = 0.9e9   # last swept frequency must be >= this

Row = tuple[float, float, float]  # (freq_hz, mag_db, phase_deg)


def ripple_db(rows: list[Row]) -> float:
    """Max |mag - 3-point median| over RIPPLE_BAND_HZ, in dB (0.0 if < 3 points)."""
    lo, hi = RIPPLE_BAND_HZ
    mags = [m for f, m, _ in rows if lo <= f <= hi]
    worst = 0.0
    for n in range(1, len(mags) - 1):
        med = sorted(mags[n - 1:n + 2])[1]
        worst = max(worst, abs(mags[n] - med))
    return worst


def assess(rows: list[Row] | None) -> tuple[bool, float | None, str]:
    """(ok, ripple_db or None, reason). reason is "none" when ok."""
    if not rows:
        return False, None, "no_data"
    for f, m, p in rows:
        if not (math.isfinite(f) and math.isfinite(m) and math.isfinite(p)):
            return False, None, "non_finite"
    if rows[0][0] > SWEEP_MIN_HZ_MAX or rows[-1][0] < SWEEP_MAX_HZ_MIN:
        return False, None, "truncated_sweep"
    lo, hi = RIPPLE_BAND_HZ
    if sum(1 for f, _, _ in rows if lo <= f <= hi) < MIN_BAND_POINTS:
        return False, None, "insufficient_band_points"
    ripple = ripple_db(rows)
    if ripple > RIPPLE_MAX_DB:
        return False, ripple, "ripple_exceeds_threshold"
    return True, ripple, "none"


def read_ac_txt(path: Path) -> list[Row] | None:
    """Parse a `wrdata` file (freq mag freq phase). None if missing/empty;
    unparseable fields become NaN so `assess` rejects them as non_finite."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    rows: list[Row] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1]), float(parts[3])))
        except ValueError:
            rows.append((math.nan, math.nan, math.nan))
    return rows or None


def decide(quality_ok: bool, op_ok: bool, status: str, pm_deg: float | None,
           notch_marginal: bool, pm_min_deg: float = 0.0) -> tuple[str, bool, bool]:
    """The bench's pass logic with the quality gate in front.

    Returns (verdict, crossing_ok, marginal_used). A rejected solve is FAIL
    and never reaches the PM / marginal-notch checks, so the marginal-notch
    exception cannot rescue it. A found crossing is judged PM > pm_min_deg
    (low-but-positive margins pass); only a NONE status may use the notch
    guard band.
    """
    if not quality_ok:
        return "FAIL", False, False
    marginal_used = False
    if status == "FOUND":
        crossing_ok = pm_deg is not None and pm_deg > pm_min_deg
    else:
        crossing_ok = notch_marginal
        marginal_used = crossing_ok
    return ("PASS" if (op_ok and crossing_ok) else "FAIL"), crossing_ok, marginal_used


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "check":
        print("usage: solve_quality.py check <ac.txt>", file=sys.stderr)
        return 2
    ok, ripple, reason = assess(read_ac_txt(Path(argv[2])))
    print(f"{'OK' if ok else 'REJECT'} {'-' if ripple is None else f'{ripple:.4f}'} {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
