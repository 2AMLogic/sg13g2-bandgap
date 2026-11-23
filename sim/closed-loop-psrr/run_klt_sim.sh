#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-psrr (schematic DUT) on the `klt sim` harness
# (issue #415, part of #412). Replaces hand-running run_pvt_sweep.sh (removed in #438; see git history), whose
# `ngspice -b` grid dispatch hosts forbid.
#
#   sim/closed-loop-psrr/run_klt_sim.sh --sanity  # one local corner, vs the newest committed record
#   sim/closed-loop-psrr/run_klt_sim.sh --batch   # the 45-point PVT grid, on the batch fleet
#   sim/closed-loop-psrr/run_klt_sim.sh --record  # mint evidence from the enriched report
#
#   PSRR_VARIANT=<name> <any mode>  # run the same bench on a bench-local
#                                   # PROPOSAL body from variants/<name>.*
#                                   # instead of the as-built DUT (issue
#                                   # #631): variant body template, variant
#                                   # sanity anchors, variant record spec.
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

# Variant selection (issue #631): PSRR_VARIANT=<name> runs the SAME bench on
# a bench-local PROPOSAL body under variants/ instead of the as-built DUT --
# so a candidate can be grid-verified before any committed-design change.
# The variant carries its own body template, its own sanity anchors (its
# typ/27C/3.30V point is NOT the as-built record's) and its own record spec
# (so a minted record names the variant, not the as-built DUT). Unset: the
# as-built path set up above, unchanged.
VARIANT=""
if [[ -n "${PSRR_VARIANT:-}" ]]; then
  VARIANT="${PSRR_VARIANT}"
  for ext in body.spice.tmpl anchors.env record-spec.json; do
    if [[ ! -f "${EXP_DIR}/variants/${VARIANT}.${ext}" ]]; then
      echo "run_klt_sim.sh: unknown or incomplete PSRR_VARIANT '${VARIANT}' (no" \
           "${EXP_DIR}/variants/${VARIANT}.${ext})" >&2
      exit 3
    fi
  done
  # Re-render the body from the variant template and bind it to the identity.
  sed "s|@@MSENSE_W@@|${MSENSE_W}|g" "${EXP_DIR}/variants/${VARIANT}.body.spice.tmpl" > "${BODY_TEMPLATE}"
  IDENT_ARGS+=(--extra "${EXP_DIR}/variants/${VARIANT}.body.spice.tmpl")
  # Read by schematic_record_mint: a minted record names the variant.
  RECORD_SPEC="${EXP_DIR}/variants/${VARIANT}.record-spec.json"
  # shellcheck source=/dev/null
  source "${EXP_DIR}/variants/${VARIANT}.anchors.env"
  echo "run_klt_sim.sh: PSRR_VARIANT=${VARIANT} (proposal body, variant sanity anchors)"
fi

# Sanity anchors: the newest committed record's typ/27C/3.30V row (20261001-085737-e5507b2).
# (A PSRR_VARIANT run replaces these from variants/<name>.anchors.env above.)
KIND="psrr"
ANCHOR_NAME="psrr_dc_db"
if [[ -z "${VARIANT}" ]]; then
  ANCHOR_DB="66.0695"
  ANCHOR_DB_TOL="0.1"
  ANCHOR_VREF_OP_V="1.047278"
  ANCHOR_VREF_TOL_V="0.002"
fi

# The --sanity | --batch | --record flow is pex_ac_runner.sh's, via the
# extraction-less twin (issue #650).
schematic_ac_main
