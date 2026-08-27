#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-startup/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/closed-loop-startup/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_startup.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention sim/startup-core-handover/run_pvt_sweep.sh uses -- this
# sweep always exercises whatever the schematic currently specifies.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,det_early_v,fb_early_v,fb_final_v,sns1_final_v,sns2_final_v,vref_final_v,det_final_v,i_mkfb_final_a,dvsns_final_v" > "${CSV_OUT}"

# Same corner-label vocabulary as every other PVT sweep in this tree
# (CORNER_LABELS/TEMPS/VDDS/HBT_SECTION_OF/RES_SECTION_OF/MOS_SECTION_OF
# come from sim/lib/pvt_preflight.sh).

# Pass criteria -- three independent claims (startup released, loop closed,
# not railed), all required, at the end of the transient (fully ramped +
# settled): DET_RELEASE_FRAC/I_MKFB_RELEASE_A/DVSNS_CLOSE_V/
# FB_RAIL_MARGIN_V and the verdict formula itself come from
# sim/lib/pvt_verdict_common.sh -- see that file's own header comment for
# the full rationale behind each threshold.

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
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true` on each: unlike every prior PVT sweep in this tree, this
      # experiment's DUT (the real, not-yet-loop-gain-tuned error amplifier)
      # can genuinely fail to converge at an early, near-singular instant on
      # the vdd ramp at a marginal PVT corner (see the template's own
      # rshunt/gmin comment) -- when that happens, ngspice's `.measure`
      # lines below never print, so `grep` finds no match and exits 1. Under
      # this script's `set -euo pipefail`, an unguarded `grep` failure here
      # would abort the ENTIRE sweep on the first non-convergent corner,
      # silently losing every other point's evidence -- worse than recording
      # that one corner as FAIL and continuing. The `-z` checks below already
      # treat an empty variable as FAIL; `|| true` just lets execution reach
      # them instead of dying first.
      det_early=$(grep -E '^v_det_early' "${log}" | head -1 | awk '{print $3}' || true)
      fb_early=$(grep -E '^v_fb_early' "${log}" | head -1 | awk '{print $3}' || true)
      fb_final=$(grep -E '^v_fb_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns1_final=$(grep -E '^v_sns1_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns2_final=$(grep -E '^v_sns2_v' "${log}" | head -1 | awk '{print $3}' || true)
      vref_final=$(grep -E '^v_vref_v' "${log}" | head -1 | awk '{print $3}' || true)
      det_final=$(grep -E '^v_det_v' "${log}" | head -1 | awk '{print $3}' || true)
      i_mkfb_final=$(grep -E '^i_mkfb_v' "${log}" | head -1 | awk '{print $3}' || true)

      verdict=PASS
      dvsns_final=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_final}" || -z "${i_mkfb_final}" || -z "${sns1_final}" || -z "${sns2_final}" || -z "${fb_final}" ]]; then
        verdict=FAIL
      else
        dvsns_final=$(awk -v a="${sns1_final}" -v b="${sns2_final}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        verdict=$(pvt_closed_loop_verdict "${det_final}" "${i_mkfb_final}" "${fb_final}" "${dvsns_final}" "${vdd}")
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${det_early},${fb_early},${fb_final},${sns1_final},${sns2_final},${vref_final},${det_final},${i_mkfb_final},${dvsns_final}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-startup"
  echo "- **Claim**: co-simulating bandgap_core + bandgap_amp + bandgap_startup"
  echo "  in one netlist (design/bandgap_top.sch's own wiring: core.fb <-"
  echo "  amp.out, core.sns1 -> amp.in_n, core.sns2 -> amp.in_p, startup"
  echo "  shares sns1 and fb with the core), with vdd itself ramped 0 -> VDD"
  echo "  over 200 us, the assembled block self-starts and settles to a"
  echo "  closed-loop operating point across the full temperature x supply x"
  echo "  HBT/MOS/resistor-process-corner PVT grid: the startup circuit fully"
  echo "  releases (v(det) <= ${DET_RELEASE_FRAC}*vdd, |i(XMKFB)| <="
  echo "  ${I_MKFB_RELEASE_A} A), the real error amplifier closes the loop"
  echo "  (|sns1-sns2| <= ${DVSNS_CLOSE_V} V), and fb settles to a real"
  echo "  interior equilibrium rather than railing to either supply (fb"
  echo "  within [${FB_RAIL_MARGIN_V} V, vdd-${FB_RAIL_MARGIN_V} V]). This is"
  echo "  the first genuinely closed-loop testbench in this tree -- every"
  echo "  prior PVT-sweep testbench (sim/core-open-loop-bias,"
  echo "  sim/startup-core-handover, and their -pex variants) substituted an"
  echo "  ideal diode-connected-replica current fixture for the not-yet-built"
  echo "  amplifier (design/README.md, issue #9's scope cut). No ratified"
  echo "  spec row exists yet (#13); this record is closed-loop"
  echo "  infrastructure/plumbing evidence -- the assembled block starts and"
  echo "  settles -- not a claim against any spec accuracy/PSRR/Iq target."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, same convention"
  echo "  sim/startup-core-handover uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice (three npn13G2"
  echo "  legs, three sg13_hv_pmos mirror legs, two rppd resistors),"
  echo "  design/netlist/bandgap_amp.spice (five sg13_hv_pmos, four"
  echo "  sg13_hv_nmos -- the error amplifier issue #58 adds) and"
  echo "  design/netlist/bandgap_startup.spice (rhigh pull-up, two"
  echo "  sg13_hv_nmos switches). No fixture stands in for the servo loop"
  echo "  in this experiment -- see the README's comparison against every"
  echo "  prior experiment in this tree."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies, plus the Vmkfb ammeter documented in testbench/ and"
  echo "  README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure and not-railed criteria above, not merely a clean"
  echo "  ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_startup.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #58."
} > "${MD_OUT}"

write_pvt_summary
