# find_crossover.awk -- scans a `wrdata`-format AC sweep file (columns:
# freq mag_db freq phase_deg, one row per swept frequency, ascending --
# ngspice's `wrdata` repeats the x-axis vector before each real-valued
# y-vector, which is why the frequency column appears twice) for the FIRST
# unity-gain (0 dB) crossing of a MAGNITUDE-DECREASING transition (gain
# falling through 0 dB, the physically meaningful crossover for a loop that
# starts with positive DC gain in this convention -- see
# ../README.md "Sign convention"), linearly interpolating both the
# crossover frequency (in log10(freq) space, since the sweep is
# log-spaced -- `ac dec`) and the phase at that frequency (linear between
# the two bracketing rows).
#
# Usage: awk -f find_crossover.awk <wrdata-file>
# Prints one line: "<status> <freq_hz> <phase_deg> <dc_gain_db> <n_crossings>"
#   status: FOUND (a falling 0 dB crossing exists) or NONE (it does not --
#     e.g. DC gain itself is already below 0 dB, or the sweep never drops
#     below 0 dB in the swept range).
#   n_crossings counts ALL 0 dB crossings (both directions) found in the
#     sweep, for transparency -- a value > 1 means the magnitude response
#     is non-monotonic near 0 dB (common here: this design's own resonant
#     peak followed by a steep rolloff produces exactly one extra
#     re-crossing pair at higher frequency -- see the README). Only the
#     FIRST falling crossing is reported as the phase-margin point, the
#     conservative/standard convention.
BEGIN { n = 0 }
{
  f[n] = $1; mag[n] = $2; ph[n] = $4; n++
}
END {
  if (n == 0) { print "NONE 0 0 0 0"; exit }
  dc_gain = mag[0]
  ncross = 0
  found = 0
  for (i = 1; i < n; i++) {
    if ((mag[i-1] >= 0 && mag[i] < 0) || (mag[i-1] < 0 && mag[i] >= 0)) {
      ncross++
      if (!found && mag[i-1] >= 0 && mag[i] < 0) {
        # linear interpolation in log10(freq) for the crossover frequency;
        # linear interpolation in the bracketing rows' own values for phase.
        lf0 = log(f[i-1]) / log(10)
        lf1 = log(f[i]) / log(10)
        frac = mag[i-1] / (mag[i-1] - mag[i])
        lfc = lf0 + frac * (lf1 - lf0)
        fc = 10 ^ lfc
        pc = ph[i-1] + frac * (ph[i] - ph[i-1])
        found = 1
      }
    }
  }
  if (found) {
    printf "FOUND %.6e %.4f %.4f %d\n", fc, pc, dc_gain, ncross
  } else {
    printf "NONE 0 0 %.4f %d\n", dc_gain, ncross
  }
}
