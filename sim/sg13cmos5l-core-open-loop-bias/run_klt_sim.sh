#!/usr/bin/env bash
# shellcheck disable=SC2034  # EXP/STEM/KIND/FAMILIES/ANCHORS are read by cmos5l_main
# sg13g2-bandgap -- sg13cmos5l-core-open-loop-bias on the `klt sim` harness
# (issue #337, Part of #322). Converts the legacy run_pvt_sweep.sh loop; the
# loop and every committed record under records/ are untouched.
#
#   sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --sanity   # one local corner vs the legacy typ/27C/3.30V values
#   sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --batch    # the 45-point grid on the fleet (needs a CMOS5L image)
#   sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --record   # mint evidence from the enriched merged report
#
# Five processes x 3 temperatures x 3 supplies, one request per process (the supply rides corners.supply_v).
#
# The mechanics (corner bundle, request/body instantiation, shard merge,
# legacy-verdict enrichment, record minting) are shared by the four
# SG13CMOS5L runners in sim/harness/cmos5l_runner.sh and
# sim/harness/cmos5l_klt.py -- read the former's header first. This file only
# declares the experiment.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../harness/cmos5l_runner.sh
source "${SCRIPT_DIR}/../harness/cmos5l_runner.sh"

EXP="sg13cmos5l-core-open-loop-bias"
STEM="sg13cmos5l_core_open_loop_bias"
KIND="core-open-loop"
FAMILIES="pnp,mos,res"
# Sanity anchors: newest committed legacy record's typ/27C/3.30V row. The
# tolerances absorb the klt-vs-legacy measurement path (6 s.f. `.meas`,
# transient-vs-op, a newer PDK pin), not a design change: a point farther off
# means the bench, not the PDK, is wrong, and no grid is dispatched.
ANCHORS=(
  "vref_v=1.204891:0.001"       # records/20260829-085010-94869af.csv
  "dveb_ptat_v=0.0553653:0.0005"
  "r1_ohm=83643.6:100"
)

cmos5l_main "$@"
