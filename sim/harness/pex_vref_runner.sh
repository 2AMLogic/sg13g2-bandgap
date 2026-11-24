# shellcheck shell=bash
# The vref-transient half of the PEX runners (issue #366): closed-loop-vref-
# pvt-pex and closed-loop-vref-pvt-pex-boxtc, PWL-ramp benches whose reports
# are enriched by sim/harness/enrich_pvt_report.py. Source it AFTER
# pex_runner.sh, with
#   ANCHOR_VREF_V / ANCHOR_TOL_V   the sanity band on typ/27C/3.30V vref_3ms
# set, define `pex_record_companion` (run after the record is minted, to write
# the experiment's TC companion CSV), then call `pex_vref_main` (or, for the schematic twins that have no
# extraction, `schematic_vref_main`, which needs MSENSE_W from
# pex_schematic_dut_setup in sim/harness/pex_runner.sh). The gate
# itself is sim/harness/sanity_anchors.py (issue #458).
#
# All four vref benches delegate their companion hook: the two box-method
# benches to the shared `pex_boxtc_companion` below (issue #465), and the two
# endpoint-method benches to the shared `pex_endpoint_tc_companion` (issue
# #496), instead of re-typing the formula. The two *methods* remain distinct
# derivations -- box = worst-case spread (`-boxtc.csv`,
# sim/harness/boxtc_companion.py), endpoint = two-point slope (`-tc.csv`,
# sim/harness/tc_companion.py) -- each with its own module, helper and
# companion file.

# Every vref bench's verdict is graded by enrich_pvt_report.py itself, so
# the module rides the submission identity of each bench that sources this
# file (#661). Sourced after pex_runner.sh, which builds IDENT_ARGS.
IDENT_ARGS+=(--extra "${HARNESS_DIR}/enrich_pvt_report.py")

check_anchors() {  # $1 = report json
  python3 "${HARNESS_DIR}/sanity_anchors.py" "$1" \
    --anchor "vref_3ms_v=${ANCHOR_VREF_V}:${ANCHOR_TOL_V}" \
    --hint "off the schematic twin's committed typ/27C/3.30V band -- the bench, not the extraction, is wrong (issue #278's sanity-gate item)"
}

pex_boxtc_companion() {
  # Box-method TC companion per (corner, vdd) group -- same formula,
  # disclosure and justification policy as the committed records (box =
  # (vmax-vmin)/(span*v27), span = 165 C over the -40..125 grid). The
  # derivation itself lives in sim/harness/boxtc_companion.py, which the
  # harness self-test covers; this picks the newest minted record, skipping
  # the companions a previous run derived from it.
  CSV="$(ls -t "${EXP_DIR}"/records/*.csv | grep -v -e '-boxtc.csv' -e '-tc.csv' | head -1)"
  python3 "${HARNESS_DIR}/boxtc_companion.py" "${CSV}" "${CSV%.csv}-boxtc.csv"
}

pex_endpoint_tc_companion() {
  # Endpoint-method TC companion per (corner, vdd) group -- the two-point
  # slope over the -40/125 C endpoints, same disclaimer as the committed
  # records. The derivation itself lives in sim/harness/tc_companion.py,
  # which the harness self-test covers; this picks the newest minted record,
  # skipping the companions a previous run derived from it. The
  # -vs-schematic exclusion is a no-op on the schematic bench: only the
  # extracted benches mint those.
  CSV="$(ls -t "${EXP_DIR}"/records/*.csv | grep -v -e '-tc.csv' -e '-vs-schematic' | head -1)"
  python3 "${HARNESS_DIR}/tc_companion.py" "${CSV}" "${CSV%.csv}-tc.csv"
}

pex_vref_main() {
  # --- the DUT body (generated, top cell) -----------------------------------
  python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc" \
    --sources-out "${WORK}/extraction-sources.json"
  _vref_main "${WORK}/pex_body.inc" pex_record_mint
}

# (Shared by the schematic benches, issue #512.) pex_vref_main generates the PEX body and states the extraction; the
# schematic has neither, so this is its body-less twin.
schematic_vref_main() {
  _vref_main "unused" schematic_record_mint MSENSE_W="${MSENSE_W}"
}

# _vref_main BODY_REF RECORD_MINT [EXTRA pex_instantiate_body KEY=VALUE ...]
# The shared --sanity | --batch | --record flow behind pex_vref_main and
# schematic_vref_main, mirroring _ac_main in pex_ac_runner.sh (issues
# #650/#707): BODY_REF is the DUT include the body template takes ("unused"
# on the schematic benches), RECORD_MINT the record-side twin (pex_record_mint
# / schematic_record_mint), and each EXTRA KEY=VALUE pair rides the --sanity
# instantiation (the schematic's MSENSE_W fill).
_vref_main() {
  local body_ref="$1" record_mint="$2"
  shift 2
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "${body_ref}" VDD=3.30 "$@" > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json"
    ;;
  --record)
    "${record_mint}" "${WORK}/report-enriched.json"
    pex_record_companion
    ;;
  esac
}
