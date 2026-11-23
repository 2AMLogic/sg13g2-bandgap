#!/usr/bin/env bash
# sg13g2-bandgap -- startup-time-to-release (schematic DUT) on the `klt sim` harness
# (issue #468, part of #412). Replaces hand-running run_pvt_sweep.sh, whose local
# `ngspice -b` grid dispatch hosts forbid -- that script is deleted (#520; git
# history keeps it as the point-definition reference, this bench's own history).
# It was already barred from minting a record:
# `.github/scripts/check_evidence_formats.py` refuses a record dated 20261023 or
# later without an artifact manifest, and only this path writes one.
#
#   sim/startup-time-to-release/run_klt_sim.sh --sanity  # one local corner, vs the newest committed record
#   sim/startup-time-to-release/run_klt_sim.sh --batch   # the 45-point grid, on the batch fleet
#   sim/startup-time-to-release/run_klt_sim.sh --record  # mint evidence from the enriched report
#
# Cold start: set PDK_ROOT/PDK and run sim/tools/build-osdi.sh once (sim/env.sh),
# then `--sanity`, `--batch` (which runs the sanity gate first), `--record`.
# A report from a partial grid is refused by the shard merger (it requires the
# full declared grid), so a partial run cannot be recorded as a refresh.
#
# This is the time-to-release twin of sim/closed-loop-startup/run_klt_sim.sh and
# shares its driver (sim/harness/pex_runner.sh + supply_bench_runner.sh) and
# host-setup caveats (klt version pin for the runner,
# KLT_SIM_BATCH_PDK_ROOT='$PDK_ROOT'): the grid runs as 15 requests (5 processes
# x 3 supplies) of 3 temperatures each, sharded over the fleet. The DUT is the
# schematic, carried in the body template, and is device-for-device the same
# assembly closed-loop-startup simulates.
#
# WHAT IS THIS BENCH'S OWN: the checkpoint ladder. The request measures the five
# release-criteria signals at eleven fixed times (100..1000, 2000 us) instead of
# one final time, and `enrich_supply_bench_report.py --bench startup_release`
# turns that into `dvsns_<N>u_v`, `checkpoint_verdicts` and `release_time_us`
# under the suffix-of-PASS rule README.md defines. The ladder is declared in the
# request template alone; nothing here or in the enricher hardcodes it (#210).
#
# SANITY GATE. One local typ/27C/3.30V corner must land on the newest committed
# record's 2 ms values (records/20261001-085905-e5507b2.csv). `release_time_us`
# is deliberately NOT an anchor: it reads 100 -- the ladder floor -- on all 45
# rows of that record, so it would pass on a badly wrong bench. `i_mkfb_2000u_a`
# is 9.7e-14 A there, numerically zero against the 50 nA threshold, so an
# absolute tolerance on it means nothing either. `fb_2000u_v` is the strong one:
# 2.49682 V is the SAME value sim/closed-loop-startup anchors its own
# `fb_final_v` on, which is the cross-validation point run_pvt_sweep.sh's header
# calls out -- agreeing with it ties the two benches together.
#
# Resumable: a per-variant report that passed AND carries a matching submission
# identity (#332) is not re-submitted.
set -euo pipefail

EXP="startup-time-to-release"
STEM="startup_time_to_release"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/supply_bench_runner.sh"

# The schematic DUT: XMSENSE's width, the width-rendered WORK body
# template and the three netlists, plus this bench's enricher, in the
# submission identity (issue #650).
pex_schematic_dut_setup "${HARNESS_DIR}/enrich_supply_bench_report.py"

ENRICH_BENCH="startup_release"
# Sanity anchors: the newest committed record's typ/27C/3.30V row
# (records/20261001-085905-e5507b2.csv) at the 2000u checkpoint.
ANCHORS=("det_2000u_v=0.00854001:0.0002" "fb_2000u_v=2.49682:0.005")

supply_bench_main
