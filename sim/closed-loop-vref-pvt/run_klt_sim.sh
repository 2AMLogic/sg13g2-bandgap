#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-pvt (schematic DUT) on the `klt sim`
# harness (issue #467, the bench behind the ratified Output-reference
# nominal row and the sanity anchor every other vref bench cites).
#
#   sim/closed-loop-vref-pvt/run_klt_sim.sh --sanity  # one local corner, vs this bench's own committed record
#   sim/closed-loop-vref-pvt/run_klt_sim.sh --batch   # the 45-point PVT grid, on the fleet (resumable)
#   sim/closed-loop-vref-pvt/run_klt_sim.sh --record  # mint evidence from the enriched report
#
# This is the schematic twin of sim/closed-loop-vref-pvt-pex/run_klt_sim.sh
# and shares its driver (sim/harness/pex_runner.sh + pex_vref_runner.sh's
# anchor check): the grid runs as 15 requests (5 processes x 3 supplies) of
# 3 temperatures each, merged deterministically before the adapter. The DUT
# is the schematic, carried verbatim in the body template, so there is no
# extraction and no generated body. The legacy run_pvt_sweep.sh still exists
# as the point-definition reference only: it is a legacy writer that cannot
# mint new records and must not be run as a grid on a dispatch host.
#
# SANITY GATE. One local typ/27C/3.30V corner must land on this bench's own
# committed record's vref_3ms (1.04728 V, 20261001-085908-e5507b2): same
# DUT, fixture, solver options and measurement as the committed grid, so
# the band is tight -- a miss means the wrapper, not the DUT, is wrong.
#
# Resumable: a per-variant report that passed AND carries a matching
# submission identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-vref-pvt"
STEM="closed_loop_vref_pvt"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_vref_runner.sh"

# XMSENSE's width from the live startup netlist, as every closed-loop bench does.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
( cd "${REPO_ROOT}" && read_msense_width "design/netlist/bandgap_startup.spice" \
    && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
MSENSE_W="$(<"${WORK}/msense_w.txt")"
BODY_TEMPLATE="${WORK}/body.spice.tmpl"
sed "s|@@MSENSE_W@@|${MSENSE_W}|g" "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" > "${BODY_TEMPLATE}"
IDENT_ARGS+=(--extra "${REPO_ROOT}/design/netlist/bandgap_startup.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_core.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_amp.spice")

# Sanity anchor: this bench's own newest committed record, typ/27C/3.30V
# vref_3ms (trim-bearing, 20261001 refresh) -- the same anchor
# closed-loop-vref-pvt-pex and -boxtc gate against.
ANCHOR_VREF_V="1.04728"
ANCHOR_TOL_V="0.0005"

pex_record_companion() {
  # The endpoint-method derivation is shared with this bench's twin:
  # sim/harness/pex_vref_runner.sh's pex_endpoint_tc_companion (issue #496).
  pex_endpoint_tc_companion
}

schematic_vref_main
