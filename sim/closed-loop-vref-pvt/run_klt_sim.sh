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
  # Informal TC companion (endpoint method, same disclaimer as the
  # committed records): derived from the adapter's minted CSV.
  CSV="$(ls -t "${EXP_DIR}"/records/*.csv | grep -v -e '-tc.csv' | head -1)"
  python3 - "${CSV}" "${CSV%.csv}-tc.csv" <<'PY'
import csv, pathlib, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = list(csv.DictReader(src.open()))
by = {(r["corner_label"], float(r["vdd_v"]), int(float(r["temp_c"]))): r for r in rows}
with dst.open("w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["corner_label", "vdd_v", "vref_neg40_v", "vref_27_v", "vref_125_v", "tc_ppm_per_c"])
    for corner in ("typ", "bcs", "wcs", "sf", "fs"):
        for vdd in (2.97, 3.30, 3.63):
            try:
                n40 = float(by[(corner, vdd, -40)]["vref_3ms_v"])
                v27 = float(by[(corner, vdd, 27)]["vref_3ms_v"])
                p125 = float(by[(corner, vdd, 125)]["vref_3ms_v"])
            except (KeyError, ValueError):
                continue
            tc = 1e6 * (p125 - n40) / (165 * v27)
            w.writerow([corner, f"{vdd}", f"{n40:.6e}", f"{v27:.6e}", f"{p125:.6e}", f"{tc:.3f}"])
print(f"tc companion: {dst}")
PY
}

# pex_vref_main generates the PEX body and states the extraction; the
# schematic has neither, so this is its body-less twin.
schematic_vref_main() {
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "unused" VDD=3.30 MSENSE_W="${MSENSE_W}" > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json"
    ;;
  --record)
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
        --report "${WORK}/report-enriched.json" \
        --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
        --experiment "${EXP_DIR}" )
    pex_record_companion
    ;;
  esac
}

schematic_vref_main
