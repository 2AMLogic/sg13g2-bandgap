#!/usr/bin/env bash
# shellcheck disable=SC2034  # EXP/STEM/KIND/FAMILIES/ANCHORS are read by cmos5l_main
# sg13g2-bandgap -- sg13cmos5l-closed-loop-startup-pex on the `klt sim` harness
# (issue #337, Part of #322). Converts the legacy run_pvt_sweep.sh loop; the
# loop and every committed record under records/ are untouched.
#
#   sim/sg13cmos5l-closed-loop-startup-pex/run_klt_sim.sh --sanity   # one local corner vs the legacy typ/27C/3.30V values
#   sim/sg13cmos5l-closed-loop-startup-pex/run_klt_sim.sh --batch    # the 45-point grid on the fleet (needs a CMOS5L image)
#   sim/sg13cmos5l-closed-loop-startup-pex/run_klt_sim.sh --record   # mint evidence from the enriched merged report
#
# Hybrid PEX bench: extracted MOS geometry hand-transcribed into the body, no wire parasitics. --record needs
# captured extraction-source hashes (#309), which this conversion does not create: the adapter refuses an
# unbound PEX record by design (sim/pdk-sg13cmos5l.json deferred_requirements.pex_binding).
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

EXP="sg13cmos5l-closed-loop-startup-pex"
STEM="sg13cmos5l_closed_loop_startup_pex"
KIND="closed-loop"
FAMILIES="pnp,mos,res"
# Sanity anchors: newest committed legacy record's typ/27C/3.30V row. The
# tolerances absorb the klt-vs-legacy measurement path (6 s.f. `.meas`,
# transient-vs-op, a newer PDK pin), not a design change: a point farther off
# means the bench, not the PDK, is wrong, and no grid is dispatched.
ANCHORS=(
  "vref_final_v=1.19709:0.005"  # records/20260905-033836-fe97115.csv
  "fb_final_v=2.49704:0.02"
)

cmos5l_main "$@"
