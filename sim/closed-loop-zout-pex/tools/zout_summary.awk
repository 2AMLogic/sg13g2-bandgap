# zout_summary.awk -- thin wrapper over ../../lib/db_summary_common.awk
# (issue #194); contributes no program logic of its own, only this header.
#
# Reports, from a `wrdata`-format AC sweep file (columns: freq zout_db freq
# phase_deg, one row per swept frequency, ascending -- same layout
# ../../closed-loop-psrr/tools/psrr_summary.awk reads):
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
# Usage: awk -v extremum=max -f ../../lib/db_summary_common.awk \
#            -f zout_summary.awk <wrdata-file>
# Prints one line:
#   "<dc_zout_db> <peak_zout_db> <peak_zout_freq_hz> <zout_1khz_db> <zout_100khz_db> <zout_1mhz_db>"
# Any of the three interpolated fields prints as "NA" if the requested
# frequency falls outside the swept range (should not happen for this
# testbench's fixed 1 Hz-1 GHz sweep, but handled defensively).
