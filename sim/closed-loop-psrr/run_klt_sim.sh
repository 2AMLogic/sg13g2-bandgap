#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-psrr (schematic DUT) on the `klt sim` harness
# (issue #415, part of #412). Replaces hand-running run_pvt_sweep.sh (removed in #438; see git history), whose
# `ngspice -b` grid dispatch hosts forbid.
#
#   sim/closed-loop-psrr/run_klt_sim.sh --sanity  # one local corner, vs the newest committed record
#   sim/closed-loop-psrr/run_klt_sim.sh --batch   # the 45-point PVT grid, on the batch fleet
#   sim/closed-loop-psrr/run_klt_sim.sh --record  # mint evidence from the enriched report
#
# Cold start: set PDK_ROOT/PDK and run sim/tools/build-osdi.sh once (sim/env.sh),
# then `--sanity`, `--batch` (which runs the sanity gate first), `--record`.
# A report from a partial grid is refused by the shard merger (it requires the
# full declared grid), so a partial run cannot be recorded as a refresh.
#
# This is the schematic twin of sim/closed-loop-psrr-pex/run_klt_sim.sh: same
# nodeset-seeded AC bench (sim/closed-loop-startup's newest record seeds the op;
# see that wrapper for why a ramp-settled supply does not transfer to `ac`),
# same 15 requests (5 processes x 3 supplies) of 3 temperatures each, same
# enrichment (sim/harness/enrich_ac_report.py --kind psrr). The DUT is the
# schematic, carried in the body template instead of a generated PEX include.
#
# SANITY GATE. No grid until one local corner (typ/27C/3.30V) lands within
# ANCHOR_DB_TOL dB of the newest committed record's psrr_dc (66.0695 dB) and
# ANCHOR_VREF_TOL_V of its vref_op (1.047278 V): the same DUT, so a tight band.
#
# Resumable: a per-variant report that passed AND carries a matching submission
# identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-psrr"
STEM="closed_loop_psrr"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_ac_runner.sh"

# The schematic DUT: XMSENSE's width, the width-rendered WORK body
# template and the three netlists, plus this bench's enricher, in the
# submission identity (issue #650).
pex_schematic_dut_setup "${HARNESS_DIR}/enrich_ac_report.py"

# Sanity anchors: the newest committed record's typ/27C/3.30V row (20261001-085737-e5507b2).
KIND="psrr"
ANCHOR_NAME="psrr_dc_db"
ANCHOR_DB="66.0695"
ANCHOR_DB_TOL="0.1"
ANCHOR_VREF_OP_V="1.047278"
ANCHOR_VREF_TOL_V="0.002"

# The --sanity | --batch | --record flow is pex_ac_runner.sh's, via the
# extraction-less twin (issue #650).
schematic_ac_main
