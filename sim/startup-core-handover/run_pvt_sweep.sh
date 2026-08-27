#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/startup-core-handover/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/startup-core-handover/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_startup_core_handover.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice
# rather than hardcoded in the template, so this sweep always exercises
# whatever the schematic currently specifies -- load-bearing for issue #24,
# which reruns this exact sweep both before and after resizing XMSENSE.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates two DUTs, so alias it as the core half and compute
# the startup half's SHA separately.
alias_dut_git_shas STARTUP=design/netlist/bandgap_startup.spice

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,det_early_v,fb_early_v,det_final_v,fb_final_v,sns1_final_v,vref_final_v,i_mkfb_final_a" > "${CSV_OUT}"

# Same corner-label vocabulary as sim/core-open-loop-bias (all five
# cornerMOShv.lib process sections, the HBT axis included since the core's
# real npn13G2 legs are DUT devices here too). CORNER_LABELS/TEMPS/VDDS/
# HBT_SECTION_OF/RES_SECTION_OF/MOS_SECTION_OF come from
# sim/lib/pvt_preflight.sh (shared across all 5 run_pvt_sweep.sh scripts as
# of issue #51).

# Release criteria: at the end of the transient (fully ramped + settled),
# v(det) should have dropped well below vdd/2 (the same "released" sense
# sim/startup-trip-point uses) AND XMKFB's own contribution to the shared
# fb node (i_mkfb, measured through the Vmkfb ammeter) should have decayed
# to a small fraction of the ~5 uA/leg design current -- i.e. the startup
# circuit is no longer meaningfully perturbing the core's own bias point,
# not just "det looks low". 1% of 5 uA = 50 nA.
DET_RELEASE_FRAC="0.2"
I_MKFB_RELEASE_A="50e-9"

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      total=$((total + 1))
      corner_id="${corner}_${temp}c_${vdd}v"
      netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
      log="${CORNERS_OUT}/${corner_id}.log"

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      det_early=$(grep -E '^v_det_early' "${log}" | head -1 | awk '{print $3}')
      fb_early=$(grep -E '^v_fb_early' "${log}" | head -1 | awk '{print $3}')
      det_final=$(grep -E '^v_det_v' "${log}" | head -1 | awk '{print $3}')
      fb_final=$(grep -E '^v_fb_v' "${log}" | head -1 | awk '{print $3}')
      sns1_final=$(grep -E '^v_sns1_v' "${log}" | head -1 | awk '{print $3}')
      vref_final=$(grep -E '^v_vref_v' "${log}" | head -1 | awk '{print $3}')
      i_mkfb_final=$(grep -E '^i_mkfb_v' "${log}" | head -1 | awk '{print $3}')

      verdict=PASS
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_final}" || -z "${i_mkfb_final}" ]]; then
        verdict=FAIL
      else
        verdict=$(awk -v det_final="${det_final}" -v i_mkfb_final="${i_mkfb_final}" \
                      -v vdd="${vdd}" -v det_frac="${DET_RELEASE_FRAC}" -v i_thresh="${I_MKFB_RELEASE_A}" \
          'BEGIN{
             i_abs = (i_mkfb_final < 0) ? -i_mkfb_final : i_mkfb_final;
             ok = (det_final <= det_frac*vdd) && (i_abs <= i_thresh);
             print ok ? "PASS" : "FAIL";
           }')
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${det_early},${fb_early},${det_final},${fb_final},${sns1_final},${vref_final},${i_mkfb_final}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: startup-core-handover"
  echo "- **Claim**: co-simulating bandgap_core + bandgap_startup in one"
  echo "  netlist (sharing the real sns1 and fb nodes, no externally-swept"
  echo "  stimulus on either), with vdd itself ramped 0 -> VDD over 200 us,"
  echo "  XMKFB (the startup circuit's fb pull-down) releases the shared fb"
  echo "  node once the core reaches its ramped-up, settled operating point:"
  echo "  v(det) <= ${DET_RELEASE_FRAC}*vdd and |i(XMKFB)| <= ${I_MKFB_RELEASE_A} A"
  echo "  (1% of the 5 uA/leg open-loop design current) at the end of the"
  echo "  transient (t=2ms), across the full temperature x supply x"
  echo "  HBT/MOS/resistor-process-corner PVT grid. Direct, load-bearing"
  echo "  evidence for issue #24 -- supersedes the cross-bench comparison"
  echo "  sim/startup-trip-point/README.md documents (two separate DC"
  echo "  benches, not a co-simulation)."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, not hardcoded --"
  echo "  see this experiment's README for why)."
  echo "- **Devices**: all real PDK compact models, both DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice (three npn13G2"
  echo "  legs, three sg13_hv_pmos mirror legs, two rppd resistors) and"
  echo "  design/netlist/bandgap_startup.spice (rhigh pull-up, two"
  echo "  sg13_hv_nmos switches)."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, plus the open-loop mirror-bias fixture (XM0 +"
  echo "  Ibias, identical to sim/core-open-loop-bias's own) and the Vmkfb"
  echo "  ammeter documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (both the v(det) and"
  echo "  |i(XMKFB)| release criteria above, not merely a clean ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_startup_core_handover.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #24."
} > "${MD_OUT}"

write_pvt_summary
