#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-iq (schematic DUT) on the `klt sim` harness (issue #414,
# part of #412). Replaces hand-running run_pvt_sweep.sh (removed in #438; see git history), whose `ngspice -b` grid
# dispatch hosts forbid.
#
#   sim/closed-loop-iq/run_klt_sim.sh --sanity  # one local corner, vs the newest committed record
#   sim/closed-loop-iq/run_klt_sim.sh --batch   # the 45-point grid, on the batch fleet
#   sim/closed-loop-iq/run_klt_sim.sh --record  # mint evidence from the enriched report
#
# Cold start: set PDK_ROOT/PDK and run sim/tools/build-osdi.sh once (sim/env.sh),
# then `--sanity`, `--batch` (which runs the sanity gate first), `--record`.
# A report from a partial grid is refused by the shard merger (it requires the
# full declared grid), so a partial run cannot be recorded as a refresh.
#
# This is the closed-loop-iq twin of sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh and
# shares its driver (sim/harness/pex_runner.sh) and host-setup caveats (klt
# version pin for the runner): the grid runs
# as 15 requests (5 processes x 3 supplies) of 3 temperatures each, sharded over
# the fleet. The DUT is the schematic, carried in the body template.
#
# SANITY GATE. One local typ/27C/3.30V corner must land on the newest committed
# record's value (iq_avg_a 2.80682e-05 A +/- 0.1%).
#
# Resumable: a per-variant report that passed AND carries a matching submission
# identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-iq"
STEM="closed_loop_iq"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/supply_bench_runner.sh"

# The schematic DUT: XMSENSE's width, the width-rendered WORK body
# template and the three netlists, plus this bench's enricher, in the
# submission identity (issue #650).
pex_schematic_dut_setup "${HARNESS_DIR}/enrich_supply_bench_report.py"

ENRICH_BENCH="iq"
# Sanity anchors: the newest committed record's typ/27C/3.30V row (20261001-092257-4fe07ea).
ANCHORS=("iq_avg_a=2.80682e-05:2.8e-8" "fb_v=2.49682:0.005")

supply_bench_main
