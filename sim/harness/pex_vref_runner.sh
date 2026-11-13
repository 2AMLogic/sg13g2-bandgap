# shellcheck shell=bash
# The vref-transient half of the PEX runners (issue #366): closed-loop-vref-
# pvt-pex and closed-loop-vref-pvt-pex-boxtc, PWL-ramp benches whose reports
# are enriched by sim/harness/enrich_pvt_report.py. Source it AFTER
# pex_runner.sh, with
#   ANCHOR_VREF_V / ANCHOR_TOL_V   the sanity band on typ/27C/3.30V vref_3ms
# set, define `pex_record_companion` (run after the record is minted, to write
# the experiment's TC companion CSV), then call `pex_vref_main`. The gate
# itself is sim/harness/sanity_anchors.py (issue #458).

check_anchors() {  # $1 = report json
  python3 "${HARNESS_DIR}/sanity_anchors.py" "$1" \
    --anchor "vref_3ms_v=${ANCHOR_VREF_V}:${ANCHOR_TOL_V}" \
    --hint "off the schematic twin's committed typ/27C/3.30V band -- the bench, not the extraction, is wrong (issue #278's sanity-gate item)"
}

pex_vref_main() {
  # --- the DUT body (generated, top cell) -----------------------------------
  python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc" \
    --sources-out "${WORK}/extraction-sources.json"
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" VDD=3.30 > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json"
    ;;
  --record)
    pex_record_mint "${WORK}/report-enriched.json"
    pex_record_companion
    ;;
  esac
}
