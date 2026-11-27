# shellcheck shell=bash
# The AC-bench half of the PEX runners (issue #366): closed-loop-zout-pex and
# closed-loop-psrr-pex, nodeset-seeded per-process x per-supply benches whose
# reports are enriched by sim/harness/enrich_ac_report.py. Source it AFTER
# pex_runner.sh, with
#   KIND            enrich_ac_report.py --kind (zout|psrr)
#   ANCHOR_NAME     the measurement name gated on (e.g. zout_dc_db)
#   ANCHOR_DB / ANCHOR_DB_TOL   its sanity band (dB)
#   ANCHOR_VREF_OP_V / ANCHOR_VREF_TOL_V   the vref_op band (V)
# set, then call `pex_ac_main` (or, for the schematic twin that has no
# extraction -- closed-loop-psrr -- `schematic_ac_main`, which needs
# MSENSE_W from pex_schematic_dut_setup). The gate itself is
# sim/harness/sanity_anchors.py (issue #458); these are its anchor values.

# The enricher below imports its verdict constants and the 3-criteria
# closed-loop check from enrich_pvt_report.py, so that module rides every
# AC bench's submission identity too (#661). Sourced after pex_runner.sh,
# which builds IDENT_ARGS.
IDENT_ARGS+=(--extra "${HARNESS_DIR}/enrich_pvt_report.py")

# --- node seeds: sim/closed-loop-startup's newest committed record ----------
klt_sim_newest_seed_csv || exit $?
# SEEDS_OF CORNER VDD -> prints fb sns1 sns2 vref seeds (27C row), each read
# from the PASS row by its header name, as sim/lib/nodeset_seed.sh's
# lookup_seed does: the startup record's schema evolves (73c420a2 dropped
# msense_w, which a positional read of the row never found again, issue
# #740). Prints nothing and returns 3 -- naming the cause on stderr -- when a
# column or the row is missing, or a seed is not a finite decimal voltage.
SEEDS_OF() {
  LC_ALL=C awk -F, -v c="$1" -v v="$2" '
    function refuse(why) {
      printf "run_klt_sim.sh: %s\n", why > "/dev/stderr"
      verdict = 1
      exit 3
    }
    BEGIN {
      record = ARGV[1]
      nk = split("corner_label temp_c vdd_v status", key, " ")
      ns = split("fb_final_v sns1_final_v sns2_final_v vref_final_v", seed, " ")
    }
    NR == 1 {
      for (i = 1; i <= NF; i++) col[$i] = i
      for (i = 1; i <= nk; i++) if (!(key[i] in col)) refuse("no " key[i] " column in " record)
      for (i = 1; i <= ns; i++) if (!(seed[i] in col)) refuse("no " seed[i] " column in " record)
      next
    }
    $(col[key[1]]) == c && $(col[key[2]]) == "27" && $(col[key[3]]) == v && $(col[key[4]]) == "PASS" {
      row = c "/27C/" v " PASS row in " record
      for (i = 1; i <= ns; i++) {
        value = $(col[seed[i]])
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        if (value == "") refuse(row " has an empty " seed[i])
        if (value !~ /^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$/ ||
            tolower(sprintf("%g", value + 0)) ~ /inf/)
          refuse(row " has an invalid " seed[i])
        voltage[i] = value
      }
      print voltage[1], voltage[2], voltage[3], voltage[4]
      verdict = 1
      exit 0
    }
    END { if (!verdict) refuse("no " c "/27C/" v " seed row in " record) }
  ' "${SEED_CSV}"
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
  _ac_main "${WORK}/pex_body.inc" pex_record_mint
}

# (Shared by the schematic twin, issue #650.) No generated body and no
# extraction: the DUT rides in the body template pex_schematic_dut_setup
# rendered with @@MSENSE_W@@, so the body reference is "unused" and the
# record mints unbound (schematic_record_mint).
schematic_ac_main() {
  _ac_main "unused" schematic_record_mint MSENSE_W="${MSENSE_W}"
}

# _ac_main BODY_REF RECORD_MINT [EXTRA pex_instantiate_body KEY=VALUE ...]
# The shared --sanity | --batch | --record flow behind pex_ac_main and
# schematic_ac_main: BODY_REF is the DUT include the template's @@PEX_BODY@@
# takes ("unused" on the schematic bench), RECORD_MINT the record-side twin
# (pex_record_mint / schematic_record_mint), and each EXTRA KEY=VALUE pair
# rides pex_instantiate_body (the schematic's MSENSE_W fill).
_ac_main() {
  local body_ref="$1" record_mint="$2"
  shift 2
  case "${MODE}" in
  --sanity)
    local FB S1 S2 VR seeds
    seeds="$(SEEDS_OF typ 3.30)" || exit $?
    read -r FB S1 S2 VR <<< "${seeds}"
    pex_instantiate_body "${OSDI_DIR}" "${body_ref}" VDD=3.30 \
      FB_SEED="${FB}" SNS1_SEED="${S1}" SNS2_SEED="${S2}" VREF_SEED="${VR}" \
      "$@" > "${WORK}/body.spice"
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
    "${record_mint}" "${WORK}/report-enriched.json"
    echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
    if [[ "${record_mint}" == pex_record_mint ]]; then
      # PEX-only follow-up: the #275 freshness waiver this mint retires.
      echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
    fi
    ;;
  esac
}
