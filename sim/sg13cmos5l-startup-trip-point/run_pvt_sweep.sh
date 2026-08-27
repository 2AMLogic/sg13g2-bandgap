#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
#                                            # AND a sibling ihp-sg13g2/ -- see
#                                            # sim/pdk-sg13cmos5l.json
#                                            # "sibling_checkout_requirement"
#   export PDK=ihp-sg13cmos5l
#   sim/sg13cmos5l-startup-trip-point/run_pvt_sweep.sh
#
# Requires ngspice on PATH. This PDK ships its OSDI device models prebuilt --
# see sim/pdk-sg13cmos5l.json "osdi_toolchain". Full testbench rationale and
# what this sweep does and does not claim:
# sim/sg13cmos5l-startup-trip-point/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/sg13cmos5l/netlist/bandgap_startup.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_sg13cmos5l_startup_trip_point.spice.tmpl"

echo "corner_label,mos_section,res_section,temp_c,vdd_v,status,det_on_v,fb_on_v,vtrip_v,det_off_v,fb_off_v" > "${CSV_OUT}"

# design/sg13cmos5l/bandgap_startup.sch contains no bipolar device (same as
# SG13G2's own startup circuit), so this experiment never references a PNP
# or HBT corner section -- only CORNER_LABELS/TEMPS/VDDS/RES_SECTION_OF/
# MOS_SECTION_OF from sim/lib/pvt_preflight.sh (shared with SG13G2's own
# sim/startup-trip-point, since the front-end MOS/resistor devices and
# their corner-lib section names are literally shared between the two
# PDKs -- see sim/pdk-sg13cmos5l.json "relationship_to_ihp_sg13g2").
for corner in "${CORNER_LABELS[@]}"; do
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      total=$((total + 1))
      corner_id="${corner}_${temp}c_${vdd}v"
      netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
      log="${CORNERS_OUT}/${corner_id}.log"

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

      # Same four pass criteria sim/startup-trip-point uses (see that
      # experiment's own script for the rationale):
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

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${mos_section},${res_section},${temp},${vdd},${verdict},${det_on},${fb_on},${vtrip},${det_off},${fb_off}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: sg13cmos5l-startup-trip-point"
  echo "- **Claim**: sg13g2-bandgap's SG13CMOS5L bandgap_startup circuit"
  echo "  (design/sg13cmos5l/bandgap_startup.sch, issue #68 -- a direct port"
  echo "  of SG13G2's own bandgap_startup.sch with only the symbol-library"
  echo "  path changed, same device sizes) engages at cold start (core sense"
  echo "  node at 0 V => det pulled to >= 80% of vdd, fb held below 100 mV,"
  echo "  i.e. the PMOS mirror is forced on) and disengages once the core is"
  echo "  running (core sense node near vdd => det below 20% of vdd and fb"
  echo "  released above 80% of vdd), with a well-defined trip point strictly"
  echo "  inside (0, vdd), across the full temperature x supply x"
  echo "  MOS/resistor-process-corner grid. Infrastructure/plumbing evidence"
  echo "  for issue #65, NOT a claim against any ratified spec row (this"
  echo "  repo's spec/ tracks no ratified SG13CMOS5L accuracy target yet)."
  echo "- **Devices**: all real PDK compact models -- sg13_hv_nmos (PSP103.6"
  echo "  via psp103.osdi) x2 and rhigh (r3_cmc via r3_cmc.osdi). Shipped"
  echo "  prebuilt by this PDK checkout (see sim/pdk-sg13cmos5l.json"
  echo "  \"osdi_toolchain\") -- no compile step needed."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/sg13cmos5l/netlist/bandgap_startup.spice @ \`${DUT_GIT_SHA}\`),"
  echo "  device-for-device, plus the sns1 stimulus source and the 10 Mohm fb"
  echo "  pull-up fixture documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-sg13cmos5l.json\` (git commit pin, not a tagged release)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- shipped prebuilt by this PDK"
  echo "  checkout; see \`sim/pdk-sg13cmos5l.json\` \"osdi_toolchain\"."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (MOS-hv"
  echo "  x resistor sections) x temperature {-40, 27, 125} C x supply"
  echo "  {2.97, 3.30, 3.63} V = ${total} points. Supply grid is the 3.3V"
  echo "  HV-flavor analog rail only, see"
  echo "  \`sim/pdk-sg13cmos5l.json\` \"supply_rails\"."
  echo "- **Result**: ${passed}/${total} points PASS (all four criteria above, not"
  echo "  merely a clean ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_sg13cmos5l_startup_trip_point.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #65."
} > "${MD_OUT}"

write_pvt_summary
