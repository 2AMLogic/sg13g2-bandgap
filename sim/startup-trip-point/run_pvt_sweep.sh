#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/startup-trip-point/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds -- every device in design/netlist/bandgap_startup.spice is OSDI-gated,
# so this experiment cannot run at all without them. Full testbench rationale
# and what this sweep does and does not claim: sim/startup-trip-point/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_startup.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_startup_trip_point.spice.tmpl"

echo "corner_label,mos_section,res_section,temp_c,vdd_v,status,det_on_v,fb_on_v,vtrip_v,det_off_v,fb_off_v" > "${CSV_OUT}"

# Same corner-label vocabulary as sim/core-open-loop-bias (see that
# experiment's README for the pairing rationale), minus the HBT axis: the
# startup circuit contains no bipolar device. CORNER_LABELS/TEMPS/VDDS/
# RES_SECTION_OF/MOS_SECTION_OF come from sim/lib/pvt_preflight.sh (shared
# across all 5 run_pvt_sweep.sh scripts as of issue #51); this experiment
# simply never references that file's HBT_SECTION_OF map.
for corner in "${CORNER_LABELS[@]}"; do
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"

      vdd_half=$(awk -v v="${vdd}" 'BEGIN{printf "%.4f", v/2}')
      # ngspice's `meas ... at=` refuses the exact end point of a dc sweep
      # ("out of interval"), so the "core fully up" end state is measured one
      # sweep step short of vdd.
      vdd_off=$(awk -v v="${vdd}" 'BEGIN{printf "%.4f", v-0.05}')

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@VDD_HALF@@|${vdd_half}|g" \
        -e "s|@@VDD_OFF@@|${vdd_off}|g" \
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      det_on=$(grep -E '^v\(det\)' "${log}" | head -1 | awk '{print $3}')
      fb_on=$(grep -E '^v\(fb\)' "${log}" | head -1 | awk '{print $3}')
      vtrip=$(grep -E '^vtrip' "${log}" | head -1 | awk '{print $3}')
      det_off=$(grep -E '^det_off' "${log}" | head -1 | awk '{print $3}')
      fb_off=$(grep -E '^fb_off' "${log}" | head -1 | awk '{print $3}')

      # Pass criteria, all four checked explicitly (not just "ngspice exited 0"):
      #   1. cold start engages: det pulled to >= 80% of vdd with sns1 = 0
      #   2. cold start drives the mirror: fb held below 100 mV
      #   3. a disengage trip point exists strictly inside (0, vdd)
      #   4. running core disengages: det below 20% of vdd, fb released above 80%
      verdict=PASS
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_on}" || -z "${fb_on}" || -z "${vtrip}" || -z "${det_off}" || -z "${fb_off}" ]]; then
        verdict=FAIL
      else
        verdict=$(awk -v det_on="${det_on}" -v fb_on="${fb_on}" -v vtrip="${vtrip}" \
                      -v det_off="${det_off}" -v fb_off="${fb_off}" -v vdd="${vdd}" \
          'BEGIN{
             ok = (det_on >= 0.8*vdd) && (fb_on <= 0.1) \
                  && (vtrip > 0) && (vtrip < vdd) \
                  && (det_off <= 0.2*vdd) && (fb_off >= 0.8*vdd);
             print ok ? "PASS" : "FAIL";
           }')
      fi

      tally_verdict "${verdict}" "${corner_id}"
      echo "${corner},${mos_section},${res_section},${temp},${vdd},${verdict},${det_on},${fb_on},${vtrip},${det_off},${fb_off}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: startup-trip-point"
  echo "- **Claim**: sg13g2-bandgap's bandgap_startup circuit engages at cold"
  echo "  start (core sense node at 0 V => det pulled to >= 80% of vdd, fb held"
  echo "  below 100 mV, i.e. the PMOS mirror is forced on) and disengages once"
  echo "  the core is running (core sense node near vdd => det below 20% of"
  echo "  vdd and fb released above 80% of vdd), with a well-defined trip"
  echo "  point strictly inside (0, vdd), across the full temperature x supply"
  echo "  x MOS/resistor-process-corner grid. Infrastructure/plumbing evidence"
  echo "  for issue #22, NOT a claim against any ratified spec row (none is"
  echo "  ratified yet -- see #125)."
  echo "- **Devices**: all real PDK compact models -- sg13_hv_nmos (PSP103.6"
  echo "  via psp103.osdi) x2 and rhigh (r3_cmc via r3_cmc.osdi). Before"
  echo "  issue #22 built the OSDI models, this netlist could not be simulated"
  echo "  at all: every device in it is OSDI-gated."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_startup.spice @ \`${DUT_GIT_SHA}\`),"
  echo "  device-for-device, plus the sns1 stimulus source and the 10 Mohm fb"
  echo "  pull-up fixture documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (MOS-hv"
  echo "  x resistor sections) x temperature {-40, 27, 125} C x supply"
  echo "  {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (all four criteria above, not"
  echo "  merely a clean ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_startup_trip_point.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #22."
} > "${MD_OUT}"

write_pvt_summary
