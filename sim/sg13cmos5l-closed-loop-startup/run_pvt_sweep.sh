#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
#                                            # AND a sibling ihp-sg13g2/ -- see
#                                            # sim/pdk-sg13cmos5l.json
#                                            # "sibling_checkout_requirement"
#   export PDK=ihp-sg13cmos5l
#   sim/sg13cmos5l-closed-loop-startup/run_pvt_sweep.sh
#
# Requires ngspice on PATH. This PDK ships its OSDI device models prebuilt --
# see sim/pdk-sg13cmos5l.json "osdi_toolchain". Full testbench rationale and
# what this sweep does and does not claim:
# sim/sg13cmos5l-closed-loop-startup/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/sg13cmos5l/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_sg13cmos5l_closed_loop_startup.spice.tmpl"

# XMSENSE's W is read from the live
# design/sg13cmos5l/netlist/bandgap_startup.spice, same convention
# sim/closed-loop-startup/run_pvt_sweep.sh uses -- this sweep always
# exercises whatever the schematic currently specifies.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/sg13cmos5l/netlist/bandgap_startup.spice"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
alias_dut_git_shas AMP=design/sg13cmos5l/netlist/bandgap_amp.spice STARTUP=design/sg13cmos5l/netlist/bandgap_startup.spice

echo "corner_label,pnp_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,det_early_v,fb_early_v,fb_final_v,sns1_final_v,sns2_final_v,vref_final_v,det_final_v,i_mkfb_final_a,dvsns_final_v" > "${CSV_OUT}"

# PNP_SECTION_OF: cornerPNP.lib section names, same map (and same sf/fs->typ
# fallback rationale) as sim/sg13cmos5l-core-open-loop-bias/run_pvt_sweep.sh
# -- see that script's own comment. CORNER_LABELS/TEMPS/VDDS/RES_SECTION_OF/
# MOS_SECTION_OF come from sim/lib/pvt_preflight.sh.
declare -A PNP_SECTION_OF=( [typ]=typ [bcs]=bcs [wcs]=wcs [sf]=typ [fs]=typ )

# Pass criteria -- three independent claims (startup released, loop closed,
# not railed), all required, at the end of the transient (fully ramped +
# settled). Identical bar sim/closed-loop-startup uses for the SG13G2 core:
# DET_RELEASE_FRAC/I_MKFB_RELEASE_A/DVSNS_CLOSE_V/FB_RAIL_MARGIN_V and the
# verdict formula itself come from sim/lib/pvt_verdict_common.sh -- see that
# file's own header comment for the full rationale behind each threshold.

for corner in "${CORNER_LABELS[@]}"; do
  pnp_section="${PNP_SECTION_OF[${corner}]}"
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
        -e "s|@@PNP_SECTION@@|${pnp_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true` on each: the real, not-yet-loop-gain-tuned error amplifier
      # can genuinely fail to converge at an early, near-singular instant on
      # the vdd ramp at a marginal PVT corner (see the template's own
      # rshunt/gmin comment). When that happens ngspice's `.measure` lines
      # never print, so `grep` finds no match and exits 1; under this
      # script's `set -euo pipefail`, an unguarded failure here would abort
      # the entire sweep on the first non-convergent corner. Same pattern
      # sim/closed-loop-startup uses.
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
      echo "${corner},${pnp_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${det_early},${fb_early},${fb_final},${sns1_final},${sns2_final},${vref_final},${det_final},${i_mkfb_final},${dvsns_final}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: sg13cmos5l-closed-loop-startup"
  echo "- **Claim**: co-simulating SG13CMOS5L's bandgap_core + bandgap_amp +"
  echo "  bandgap_startup (design/sg13cmos5l/, issues #64/#68) in one"
  echo "  netlist (design/sg13cmos5l/bandgap_top.sch's own wiring: core.fb <-"
  echo "  amp.out, core.sns1 -> amp.in_n, core.sns2 -> amp.in_p, startup"
  echo "  shares sns1 and fb with the core), with vdd itself ramped 0 -> VDD"
  echo "  over 200 us, the assembled block self-starts and settles to a"
  echo "  closed-loop operating point across the full temperature x supply x"
  echo "  pnpMPA/MOS/resistor-process-corner PVT grid: the startup circuit"
  echo "  fully releases (v(det) <= ${DET_RELEASE_FRAC}*vdd, |i(XMKFB)| <="
  echo "  ${I_MKFB_RELEASE_A} A), the real error amplifier closes the loop"
  echo "  (|sns1-sns2| <= ${DVSNS_CLOSE_V} V), and fb settles to a real"
  echo "  interior equilibrium rather than railing to either supply (fb"
  echo "  within [${FB_RAIL_MARGIN_V} V, vdd-${FB_RAIL_MARGIN_V} V]). This is"
  echo "  the formal, PVT-cornered sim/ counterpart to"
  echo "  design/sg13cmos5l/README.md's own single-nominal-corner informal"
  echo "  closed-loop check (issue #68). No ratified spec row exists yet for"
  echo "  SG13CMOS5L (spec/porting-plan-sg13cmos5l.md, \"Status: engineering"
  echo "  input, not a ratified decision\"); this record is closed-loop"
  echo "  infrastructure/plumbing evidence -- the assembled block starts and"
  echo "  settles -- not a claim against any spec accuracy/PSRR/Iq target."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/sg13cmos5l/netlist/bandgap_startup.spice at run time, same"
  echo "  convention sim/closed-loop-startup uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/sg13cmos5l/netlist/bandgap_core.spice (three"
  echo "  pnpMPA legs, three sg13_hv_pmos mirror legs, two rppd resistors),"
  echo "  design/sg13cmos5l/netlist/bandgap_amp.spice (five sg13_hv_pmos,"
  echo "  four sg13_hv_nmos) and design/sg13cmos5l/netlist/bandgap_startup.spice"
  echo "  (rhigh pull-up, two sg13_hv_nmos switches). No fixture stands in"
  echo "  for the servo loop in this experiment -- see"
  echo "  sim/sg13cmos5l-core-open-loop-bias/README.md for the fixture this"
  echo "  removes."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/sg13cmos5l/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/sg13cmos5l/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/sg13cmos5l/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/sg13cmos5l/bandgap_top.sch"
  echo "  specifies, plus the Vmkfb ammeter documented in testbench/ and"
  echo "  README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-sg13cmos5l.json\` (git commit pin, not a tagged release)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- shipped prebuilt by this PDK"
  echo "  checkout; see \`sim/pdk-sg13cmos5l.json\` \"osdi_toolchain\"."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (pnpMPA x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points. Supply grid is the"
  echo "  3.3V HV-flavor analog rail only, see \`sim/pdk-sg13cmos5l.json\`"
  echo "  \"supply_rails\"."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure and not-railed criteria above, not merely a clean"
  echo "  ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_sg13cmos5l_closed_loop_startup.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #65."
} > "${MD_OUT}"

write_pvt_summary
