# shellcheck shell=bash
# The AC-bench half of the PEX runners (issue #366): closed-loop-zout-pex and
# closed-loop-psrr-pex, nodeset-seeded per-process x per-supply benches whose
# reports are enriched by sim/harness/enrich_ac_report.py. Source it AFTER
# pex_runner.sh, with
#   KIND            enrich_ac_report.py --kind (zout|psrr)
#   ANCHOR_NAME     the measurement name gated on (e.g. zout_dc_db)
#   ANCHOR_DB / ANCHOR_DB_TOL   its sanity band (dB)
#   ANCHOR_VREF_OP_V / ANCHOR_VREF_TOL_V   the vref_op band (V)
# set, then call `pex_ac_main`. The gate itself is
# sim/harness/sanity_anchors.py (issue #458); these are its anchor values.

# --- node seeds: sim/closed-loop-startup's newest committed record ----------
# Newest by NAME, not mtime: the records are timestamp-prefixed, and a fresh
# clone's checkout mtimes are arbitrary, which `ls -t` once made depend on
# the order git happened to write files (#628).
SEED_CSV="$(ls "${SIM_DIR}"/closed-loop-startup/records/*.csv \
  | grep -v -e '-tc.csv' -e '-vs-schematic' | sort | tail -1)"
if [[ -z "${SEED_CSV}" ]]; then
  echo "run_klt_sim.sh: no seed record in ${SIM_DIR}/closed-loop-startup/records/" >&2
  exit 3
fi
SEEDS_OF() {  # $1 corner label, $2 vdd -> prints fb sns1 sns2 vref seeds (27C row)
  # Columns addressed by header name: the 2026-11-18 klu re-run record
  # (73c420a2) dropped the msense_w column the old positional $8/$11-14
  # read assumed, so the positional read silently matched nothing against
  # it (#628). Reads both that schema and the older msense_w one.
  awk -F, -v c="$1" -v v="$2" '
    NR==1 { for (i = 1; i <= NF; i++) col[$i] = i; next }
    $(col["corner_label"]) == c && $(col["vdd_v"]) == v && \
    $(col["temp_c"]) == "27" && $(col["status"]) == "PASS" \
      { print $(col["fb_final_v"]), $(col["sns1_final_v"]), \
               $(col["sns2_final_v"]), $(col["vref_final_v"]); exit }' "${SEED_CSV}"
}

check_anchors() {  # $1 = enriched report json
  python3 "${HARNESS_DIR}/sanity_anchors.py" "$1" \
    --anchor "${ANCHOR_NAME}=${ANCHOR_DB}:${ANCHOR_DB_TOL}" \
    --anchor "vref_op_v=${ANCHOR_VREF_OP_V}:${ANCHOR_VREF_TOL_V}" \
    --hint "off the committed record's band (issue #278's sanity-gate item)"
}

pex_ac_main() {
  # --- the DUT body (generated, top cell) -----------------------------------
  python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc" \
    --sources-out "${WORK}/extraction-sources.json"
  case "${MODE}" in
  --sanity)
    local FB S1 S2 VR
    read -r FB S1 S2 VR <<< "$(SEEDS_OF typ 3.30)"
    if [[ -z "${FB:-}" ]]; then
      echo "run_klt_sim.sh: no typ/27C/3.30 seed row in ${SEED_CSV}" >&2
      exit 3
    fi
    pex_instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" VDD=3.30 \
      FB_SEED="${FB}" SNS1_SEED="${S1}" SNS2_SEED="${S2}" VREF_SEED="${VR}" \
      > "${WORK}/body.spice"
    pex_sanity_local
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report.json \
        --kind "${KIND}" -o report-enriched.json )
    check_anchors "${WORK}/report-enriched.json"
    ;;
  --batch)
    pex_batch_dispatch --seed-csv "${SEED_CSV}" --supply-word supply
    # From WORK: the merged reports' per-corner LOG paths are relative to it.
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report-merged.json \
        --kind "${KIND}" --seed-csv "${SEED_CSV}" -o report-enriched.json )
    ;;
  --record)
    pex_record_mint "${WORK}/report-enriched.json"
    echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
    echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
    ;;
  esac
}
