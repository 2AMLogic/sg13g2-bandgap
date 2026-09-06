# psrr_summary.awk -- thin wrapper over ../../lib/db_summary_common.awk
# (issue #194); contributes no program logic of its own, only this header.
#
# Reports, from a `wrdata`-format AC sweep file (columns: freq psrr_db freq
# phase_deg, one row per swept frequency, ascending -- ngspice's `wrdata`
# repeats the x-axis vector before each real-valued y-vector, which is why
# the frequency column appears twice):
#   - the DC (lowest-frequency) PSRR value,
#   - the worst-case (minimum) PSRR across the whole 1 Hz-1 GHz sweep, and
#     the frequency it occurs at,
#   - PSRR interpolated (log10(freq)-linear, matching
#     ../../loop-gain-phase-margin/tools/find_crossover.awk's own
#     interpolation convention) at three representative frequencies: 1 kHz,
#     100 kHz and 1 MHz.
#
# Usage: awk -v extremum=min -f ../../lib/db_summary_common.awk \
#            -f psrr_summary.awk <wrdata-file>
# Prints one line:
#   "<dc_psrr_db> <min_psrr_db> <min_psrr_freq_hz> <psrr_1khz_db> <psrr_100khz_db> <psrr_1mhz_db>"
# Any of the three interpolated fields prints as "NA" if the requested
# frequency falls outside the swept range (should not happen for this
# testbench's fixed 1 Hz-1 GHz sweep, but handled defensively).
