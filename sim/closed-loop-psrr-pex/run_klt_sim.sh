#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-psrr-pex on the `klt sim` harness
# (issue #278, the remaining half of #275).
#
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --sanity   # one local corner, vs the committed typ/27/3.30 record
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --batch    # the 45-point PVT grid, on the fleet
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --record   # mint evidence from the merged report
#
# WHY NODESET-SEEDED. This bench measures a frequency-domain quantity, and
# ngspice re-solves the DC operating point for an `ac` analysis from the
# sources' DC values -- a ramp-settled supply (the transient benches'
# convergence path) linearises around a collapsed point, verified on
# ngspice 46 with a nonlinear toy circuit. The bench body therefore keeps
# the hand-transcribed template's own mechanism: a plain DC rail carrying
# the 1 V AC stimulus, and .nodeset seeds from sim/closed-loop-startup's
# newest committed record (27 C row per process corner and supply -- the
# same provenance sim/lib/nodeset_seed.sh established). Seeds are
# convergence AIDS: the enrichment pass checks the landed op against them
# with the old bench's 50 mV tolerance.
#
# WHY PER-PROCESS x PER-SUPPLY. Same two axes as the vref bench: the batch
# runner image's klt 0.5.0 carries one model library and SG13G2's corner
# set spans three per-device-family files (klayout-tools#2668), and the
# seed set is per-supply, so the supply axis lives in per-supply body
# variants -- an `alter`-driven supply axis would clobber the AC stimulus
# (verified on ngspice 46). 15 requests of 3 temperatures each, merged
# deterministically, enriched (sim/harness/enrich_ac_report.py --kind
# psrr), one record via the adapter.
#
# SANITY GATE. No grid until one local corner (typ/27C/3.30V) lands within
# SANITY_TOL_DB of the committed pre-#272 record's psrr_dc (65.2635 dB)
# and SANITY_TOL_V of its vref_op (1.046287 V): the refreshed extraction
# is a real design change, so the gate is a band.
#
# Resumable: a per-variant report that already exists, passed AND carries a
# matching submission identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-psrr-pex"
STEM="closed_loop_psrr_pex"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_ac_runner.sh"

# Sanity anchors: the committed pre-#272 record's typ/27C/3.30V row.
KIND="psrr"
ANCHOR_NAME="psrr_dc_db"
ANCHOR_DB="65.2635"
ANCHOR_DB_TOL="2.0"
ANCHOR_VREF_OP_V="1.046287"
ANCHOR_VREF_TOL_V="0.005"

pex_ac_main
