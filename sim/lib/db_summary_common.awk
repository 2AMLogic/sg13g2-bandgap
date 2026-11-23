# db_summary_common.awk -- shared parse/DC/extremum/interpolate summariser
# for wrdata-format AC sweeps. Extracted for issue #194 from the
# near-identical logic then duplicated between two per-experiment wrapper
# files (header-only companions to this file, one per AC bench) -- diffing
# them showed the only functional difference was the extremum comparison
# operator (`>` vs `<`); the parse, the DC pickoff, the log10(freq)-linear
# interpolation at three fixed target frequencies, and the printf format
# were all byte-for-byte identical. Those wrappers were removed with their
# sweep-script callers in #460 after the klt sim conversion (#438) moved
# the AC summary into sim/harness/enrich_ac_report.py; this file is now
# invoked directly. Mirrors the sim/lib/*.sh shared-helper convention
# (sim/lib/pvt_verdict_common.sh, sim/lib/pvt_sed_common.sh, etc.).
# (sim/loop-gain-phase-margin/tools/find_crossover.awk does a meaningfully
# different unity-gain-crossing search, not this DC/extremum/3-point-
# interpolation shape, so it is deliberately NOT folded in here.)
#
# Input: a `wrdata`-format AC sweep file (columns: freq db-value freq
# phase-deg, one row per swept frequency, ascending -- ngspice's `wrdata`
# repeats the x-axis vector before each real-valued y-vector, which is why
# the frequency column appears twice; only the first two columns are read
# here).
#
# Caller contract:
#   - Invoke directly with `-v extremum=min` or `-v extremum=max` (checked
#     in this file's own BEGIN block), e.g.:
#       awk -v extremum=min -f sim/lib/db_summary_common.awk <wrdata-file>
#     Use `min` for a worst-case dip (e.g. PSRR), `max` for a worst-case
#     peak (e.g. closed-loop Zout). Any other value aborts with a message
#     to stderr and a nonzero exit.
#
# Prints one line to stdout, matching every prior caller's own printf
# format exactly (byte-identical -- see issue #194's verification
# requirement):
#   "<dc_db> <extremum_db> <extremum_freq_hz> <db_1khz> <db_100khz> <db_1mhz>"
# Any of the three interpolated fields prints as "NA" if the requested
# frequency falls outside the swept range (should not happen for either
# caller's fixed 1 Hz-1 GHz sweep, but handled defensively).
BEGIN {
  if (extremum != "min" && extremum != "max") {
    print "db_summary_common.awk: -v extremum=min|max is required (got \"" extremum "\")" > "/dev/stderr"
    bad_extremum = 1
    exit 1
  }
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
  # awk runs END even after a BEGIN-time `exit` -- re-exit immediately so a
  # bad `extremum` aborts the program instead of falling through to the
  # empty-input branch below and printing a misleading "NA ..." line.
  if (bad_extremum) {
    exit 1
  }
  if (n == 0) {
    print "NA NA NA NA NA NA"
    exit
  }
  dc_db = db[0]
  extremum_db = db[0]
  extremum_f = f[0]
  for (i = 0; i < n; i++) {
    if ((extremum == "min" && db[i] < extremum_db) || (extremum == "max" && db[i] > extremum_db)) {
      extremum_db = db[i]
      extremum_f = f[i]
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
  printf "%.4f %.4f %.6e %s %s %s\n", dc_db, extremum_db, extremum_f, out[0], out[1], out[2]
}
