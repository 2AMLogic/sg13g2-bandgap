# zout_summary.awk -- scans a `wrdata`-format AC sweep file (columns:
# freq zout_db freq phase_deg, one row per swept frequency, ascending --
# ngspice's `wrdata` repeats the x-axis vector before each real-valued
# y-vector, same layout ../../closed-loop-psrr/tools/psrr_summary.awk reads)
# and reports:
#   - the DC (lowest-frequency) closed-loop output impedance |Zout|, in dB
#     relative to 1 ohm,
#   - the PEAK (maximum) |Zout| across the whole 1 Hz-1 GHz sweep, and the
#     frequency it occurs at -- the headline number for this experiment,
#     analogous to psrr_summary.awk's worst-case MINIMUM (this bench's
#     "worst case" is a peak, not a dip: a resonance in the loop's return
#     difference 1+T(jw) makes closed-loop output impedance rise, not fall),
#   - Zout interpolated (log10(freq)-linear, matching
#     ../../loop-gain-phase-margin/tools/find_crossover.awk's own
#     interpolation convention) at three representative frequencies: 1 kHz,
#     100 kHz and 1 MHz, for direct side-by-side comparison against
#     ../../closed-loop-psrr-pex/tools's own PSRR numbers at the same
#     frequencies.
#
# Usage: awk -f zout_summary.awk <wrdata-file>
# Prints one line:
#   "<dc_zout_db> <peak_zout_db> <peak_zout_freq_hz> <zout_1khz_db> <zout_100khz_db> <zout_1mhz_db>"
# Any of the three interpolated fields prints as "NA" if the requested
# frequency falls outside the swept range (should not happen for this
# testbench's fixed 1 Hz-1 GHz sweep, but handled defensively).
BEGIN {
  n = 0
  ntargets = 3
  target[0] = 1e3
  target[1] = 1e5
  target[2] = 1e6
}
{
  f[n] = $1
  db[n] = $2
  n++
}
END {
  if (n == 0) {
    print "NA NA NA NA NA NA"
    exit
  }
  dc_db = db[0]
  peak_db = db[0]
  peak_f = f[0]
  for (i = 0; i < n; i++) {
    if (db[i] > peak_db) {
      peak_db = db[i]
      peak_f = f[i]
    }
  }
  for (t = 0; t < ntargets; t++) {
    tf = target[t]
    out[t] = "NA"
    if (tf >= f[0] && tf <= f[n - 1]) {
      for (i = 1; i < n; i++) {
        if (f[i - 1] <= tf && f[i] >= tf) {
          lf0 = log(f[i - 1]) / log(10)
          lf1 = log(f[i]) / log(10)
          lft = log(tf) / log(10)
          frac = (lf1 == lf0) ? 0 : (lft - lf0) / (lf1 - lf0)
          out[t] = db[i - 1] + frac * (db[i] - db[i - 1])
          break
        }
      }
    }
  }
  printf "%.4f %.4f %.6e %s %s %s\n", dc_db, peak_db, peak_f, out[0], out[1], out[2]
}
