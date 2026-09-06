# db_summary_common.awk -- shared parse/DC/extremum/interpolate core for the
# wrdata-format AC-sweep summary scripts under sim/*/tools/. Extracted for
# issue #194 from the near-identical logic previously duplicated between
# sim/closed-loop-psrr/tools/psrr_summary.awk and
# sim/closed-loop-zout-pex/tools/zout_summary.awk -- diffing the two showed
# the only functional difference between them was the extremum comparison
# operator (`>` vs `<`); the parse, the DC pickoff, the log10(freq)-linear
# interpolation at three fixed target frequencies, and the printf format
# were all byte-for-byte identical. Mirrors the sim/lib/*.sh shared-helper
# convention (sim/lib/pvt_verdict_common.sh, sim/lib/pvt_sed_common.sh,
# etc.) already used by every run_pvt_sweep.sh.
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
#   - Invoke with `-v extremum=min` or `-v extremum=max` (checked in this
#     file's own BEGIN block; `-v` assignments happen before every BEGIN
#     rule runs, regardless of `-f` file order, so this works no matter
#     which `-f` file is listed first), e.g.:
#       awk -v extremum=min -f db_summary_common.awk -f psrr_summary.awk \
#           <wrdata-file>
#     Use `min` for a worst-case dip (e.g. PSRR), `max` for a worst-case
#     peak (e.g. closed-loop Zout). Any other value aborts with a message
#     to stderr and a nonzero exit.
#   - The caller's own file (e.g. psrr_summary.awk) is expected to
#     contribute no program logic of its own -- it exists solely to carry
#     its own domain-specific header comment (the "why this metric, why
#     these numbers matter" rationale, which is genuinely different per
#     experiment and stays out of this shared file on purpose) for
#     `awk -f <caller>.awk <file>`-style documentation/discoverability.
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
