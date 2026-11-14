#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-pvt-pex-boxtc on the `klt sim` harness
# (issue #278, the remaining half of #275).
#
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --sanity  # one local corner, vs the schematic twin
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --batch  # the 120-point box-TC grid, on the fleet
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --record  # mint evidence from the merged report
#
# WHY PER-PROCESS x PER-SUPPLY. Two axes cannot ride one request here: the
# process axis because the batch runner image's klt 0.5.0 carries one model
# library and SG13G2's corner set spans three per-device-family files
# (klayout-tools#2668; the per-process bridge sim/harness/probe/run_probe.sh
# --batch proved), and the supply axis because this bench's rail source is
# the PWL ramp that IS its convergence path -- `alter` would clobber it --
# so the ramp target is substituted into a per-supply body variant. The
# grid therefore runs as 15 requests (5 processes x 3 supplies) of 3
# temperatures each, merged deterministically
# (sim/harness/merge_batch_shards.py), enriched with the derived columns
# and the per-point closed-loop verdict
# (sim/harness/enrich_pvt_report.py), and the adapter mints one record.
#
# SANITY GATE. No grid is dispatched until one local corner (typ/27C/3.30V)
# lands within SANITY_TOL_V of the schematic twin's committed value at the
# same point (sim/closed-loop-vref-pvt's newest record): the refreshed
# extraction is a real design change (#272's trim-bearing ladder), so the
# gate is a band, not the core bench's exact anchor -- the old extraction's
# committed pex-vs-schematic deltas ran 1.0-3.5 mV and this gate allows
# +/-5 mV. "A first refreshed grid point far from the anchor means the
# template, not the extraction, is wrong" (#278's sanity-gate item).
#
# Resumable: a per-variant report that already exists, passed AND carries a
# matching submission identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-vref-pvt-pex-boxtc"
STEM="closed_loop_vref_pvt_pex_boxtc"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_vref_runner.sh"

# Sanity anchor: sim/closed-loop-vref-pvt's newest committed record,
# typ/27C/3.30V vref_3ms (the trim-bearing schematic twin, 20261001
# record), +/- the band below.
ANCHOR_VREF_V="1.04728"
ANCHOR_TOL_V="0.005"

pex_record_companion() {
  # The box-method derivation is shared with this bench's twin:
  # sim/harness/pex_vref_runner.sh's pex_boxtc_companion (issue #465).
  pex_boxtc_companion
}

pex_vref_main
