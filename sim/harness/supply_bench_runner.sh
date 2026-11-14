# shellcheck shell=bash
# Shared `--sanity | --batch | --record` flow for the closed-loop Iq and Startup
# `klt sim` runners (issue #414): schematic-DUT PWL-ramp benches whose reports are
# enriched by sim/harness/enrich_supply_bench_report.py. Source it AFTER
# pex_runner.sh, with
#   ENRICH_BENCH   iq | startup (enrich_supply_bench_report.py --bench)
#   BODY_TEMPLATE  the body template with @@MSENSE_W@@ pre-filled
#   MSENSE_W       the live startup netlist's XMSENSE width
#   ANCHORS        array of "measurement=value:tolerance" sanity anchors, read
#                  on the single local typ/27C/3.30V corner
# then call `supply_bench_main`.
#
# The gate itself is sim/harness/sanity_anchors.py (issue #458), called with
# `--magnitude`: these benches' supply-current anchors are magnitudes, because
# ngspice's passive sign convention reports i(Vvdd) negative. This is the only
# family that needs that switch.

check_anchors() {  # $1 = report json
  local ANCHOR_ARGS=() a
  for a in "${ANCHORS[@]}"; do ANCHOR_ARGS+=(--anchor "${a}"); done
  python3 "${HARNESS_DIR}/sanity_anchors.py" "$1" "${ANCHOR_ARGS[@]}" --magnitude \
    --hint "off the committed typ/27C/3.30V record's band -- the bench is wrong"
}

supply_bench_main() {
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "unused" VDD=3.30 MSENSE_W="${MSENSE_W}" > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_supply_bench_report.py" --bench "${ENRICH_BENCH}" \
      "${WORK}/report-merged.json" -o "${WORK}/report-enriched.json"
    ;;
  --record)
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
        --report "${WORK}/report-enriched.json" \
        --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
        --experiment "${EXP_DIR}" )
    ;;
  esac
}
