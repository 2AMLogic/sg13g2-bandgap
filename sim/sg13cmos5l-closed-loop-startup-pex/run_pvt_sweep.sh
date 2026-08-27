#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
#                                            # AND a sibling ihp-sg13g2/ -- see
#                                            # sim/pdk-sg13cmos5l.json
#                                            # "sibling_checkout_requirement"
#   export PDK=ihp-sg13cmos5l
#   sim/sg13cmos5l-closed-loop-startup-pex/run_pvt_sweep.sh
#
# Requires ngspice on PATH. This PDK ships its OSDI device models prebuilt --
# see sim/pdk-sg13cmos5l.json "osdi_toolchain". Does NOT require `klt` to run
# this script -- klt was used once, offline, to produce the committed
# layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.pex.spice this sweep
# splices the schematic-sourced bipolar/resistor devices into (see
# README.md's "Cold-start invocation" for the regeneration command and the
# klayout-tools#1440 caveat on why --parasitics could not be used).
#
# Full testbench rationale and what this sweep does and does not model:
# sim/sg13cmos5l-closed-loop-startup-pex/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/sg13cmos5l/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

LAYOUT_GDS="layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.gds"
LAYOUT_GIT_SHA="$(dut_git_sha "${LAYOUT_GDS}")"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_sg13cmos5l_closed_loop_startup_pex.spice.tmpl"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment splices in schematic-sourced bipolar/resistor devices from all
# three DUTs' netlists (bandgap_core for XQ1-3/XR1-2, bandgap_startup for
# XRPU), so alias core as the primary and compute the startup half's SHA
# separately -- same pattern sim/sg13cmos5l-closed-loop-startup uses for its
# three co-simulated schematics. bandgap_amp contributes no schematic-sourced
# device here (fully extracted), so no separate SHA is tracked for it.
alias_dut_git_shas STARTUP=design/sg13cmos5l/netlist/bandgap_startup.spice

echo "corner_label,pnp_section,mos_section,res_section,temp_c,vdd_v,status,det_early_v,fb_early_v,fb_final_v,sns1_final_v,sns2_final_v,vref_final_v,det_final_v,i_mkfb_final_a,dvsns_final_v" > "${CSV_OUT}"

# PNP_SECTION_OF: cornerPNP.lib section names, same map (and same sf/fs->typ
# fallback rationale) as sim/sg13cmos5l-core-open-loop-bias/run_pvt_sweep.sh
# -- see that script's own comment. CORNER_LABELS/TEMPS/VDDS/RES_SECTION_OF/
# MOS_SECTION_OF come from sim/lib/pvt_preflight.sh.
declare -A PNP_SECTION_OF=( [typ]=typ [bcs]=bcs [wcs]=wcs [sf]=typ [fs]=typ )

# Pass criteria -- identical bar sim/sg13cmos5l-closed-loop-startup uses
# (see that script's own comment for the full rationale behind each
# threshold): unchanged here since post-layout MOS geometry does not alter
# what "started up" and "closed the loop" mean.
DET_RELEASE_FRAC="0.2"
I_MKFB_RELEASE_A="50e-9"
DVSNS_CLOSE_V="0.020"
FB_RAIL_MARGIN_V="0.05"

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
        -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true` on each: the real, not-yet-loop-gain-tuned error amplifier
      # can genuinely fail to converge at an early, near-singular instant on
      # the vdd ramp at a marginal PVT corner (see the template's own
      # rshunt/gmin comment). Same guard sim/sg13cmos5l-closed-loop-startup
      # uses.
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
        verdict=$(awk -v det_final="${det_final}" -v i_mkfb_final="${i_mkfb_final}" \
                      -v vdd="${vdd}" -v det_frac="${DET_RELEASE_FRAC}" -v i_thresh="${I_MKFB_RELEASE_A}" \
                      -v dvsns="${dvsns_final}" -v dvsns_thresh="${DVSNS_CLOSE_V}" \
                      -v fb="${fb_final}" -v rail_margin="${FB_RAIL_MARGIN_V}" \
          'BEGIN{
             i_abs = (i_mkfb_final < 0) ? -i_mkfb_final : i_mkfb_final;
             startup_released = (det_final <= det_frac*vdd) && (i_abs <= i_thresh);
             loop_closed = (dvsns <= dvsns_thresh);
             not_railed = (fb >= rail_margin) && (fb <= vdd - rail_margin);
             ok = startup_released && loop_closed && not_railed;
             print ok ? "PASS" : "FAIL";
           }')
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${pnp_section},${mos_section},${res_section},${temp},${vdd},${verdict},${det_early},${fb_early},${fb_final},${sns1_final},${sns2_final},${vref_final},${det_final},${i_mkfb_final},${dvsns_final}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: sg13cmos5l-closed-loop-startup-pex (issue #84)"
  echo "- **Claim**: co-simulating SG13CMOS5L's bandgap_core + bandgap_amp +"
  echo "  bandgap_startup with every MOS device's geometry (w/l + real drawn"
  echo "  junction as/ad/ps/pd) taken from the routed"
  echo "  \`layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.gds\`"
  echo "  extraction instead of the schematic's as-drawn (junction-less)"
  echo "  defaults, wired exactly as design/sg13cmos5l/bandgap_top.sch"
  echo "  specifies, with vdd itself ramped 0 -> VDD over 200 us, the"
  echo "  assembled block still self-starts and settles to a closed-loop"
  echo "  operating point across the full temperature x supply x"
  echo "  pnpMPA/MOS/resistor-process-corner PVT grid: the startup circuit"
  echo "  fully releases (v(det) <= ${DET_RELEASE_FRAC}*vdd, |i(XMKFB)| <="
  echo "  ${I_MKFB_RELEASE_A} A), the real error amplifier closes the loop"
  echo "  (|sns1-sns2| <= ${DVSNS_CLOSE_V} V), and fb settles to a real"
  echo "  interior equilibrium rather than railing to either supply (fb"
  echo "  within [${FB_RAIL_MARGIN_V} V, vdd-${FB_RAIL_MARGIN_V} V]). This is"
  echo "  post-layout (PEX) evidence for issue #84 -- see this directory's"
  echo "  README.md for exactly what is and is not extracted/modelled (no"
  echo "  wire/metal parasitics -- klt's sg13cmos5l deck's --parasitics"
  echo "  support is currently broken, klayout-tools#1440; bipolar and"
  echo "  resistor devices are still schematic-sourced, not extracted --"
  echo "  klayout-tools#1242/#1415). No ratified spec row exists yet for"
  echo "  SG13CMOS5L (spec/porting-plan-sg13cmos5l.md, \"Status: engineering"
  echo "  input, not a ratified decision\"); this record is closed-loop"
  echo "  infrastructure/plumbing evidence -- the assembled block starts and"
  echo "  settles on post-layout geometry -- not a claim against any spec"
  echo "  accuracy/PSRR/Iq target."
  echo "- **Devices**: XM1/XM2/XM3 (core), XMTAIL/XMP1-4/XMN1-4 (amp),"
  echo "  XMSENSE/XMKFB (startup) -- all 14 MOS devices, geometry from"
  echo "  \`layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.pex.spice\`"
  echo "  (\`klt extract --deck sg13cmos5l\` -- no --parasitics, see"
  echo "  README.md, layout git sha \`${LAYOUT_GIT_SHA}\`), re-encoded as"
  echo "  X-subckt calls to the real sg13_hv_pmos/sg13_hv_nmos compact"
  echo "  models. XQ1-XQ3 (pnpMPA) and XR1/XR2 (rppd) still spliced verbatim"
  echo "  from design/sg13cmos5l/netlist/bandgap_core.spice (schematic git"
  echo "  sha \`${DUT_CORE_GIT_SHA}\`) -- the sg13cmos5l extraction deck does"
  echo "  not recognise bipolar or resistor devices (klayout-tools#1242,"
  echo "  #1415). XRPU (rhigh) spliced verbatim from"
  echo "  design/sg13cmos5l/netlist/bandgap_startup.spice (schematic git sha"
  echo "  \`${DUT_STARTUP_GIT_SHA}\`), same reason. No wire (metal)"
  echo "  parasitics are modelled anywhere in this netlist -- every net is"
  echo "  the same idealized zero-impedance node the schematic-level"
  echo "  sim/sg13cmos5l-closed-loop-startup testbench already uses; see"
  echo "  README.md for why (klayout-tools#1440)."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-sg13cmos5l.json\` (git commit pin, not a tagged release)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- shipped prebuilt by this PDK"
  echo "  checkout; see \`sim/pdk-sg13cmos5l.json\` \"osdi_toolchain\"."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (pnpMPA x MOS-hv x resistor sections -- see"
  echo "  sim/sg13cmos5l-closed-loop-startup/README.md for the pairing,"
  echo "  unchanged here) x temperature {-40, 27, 125} C x supply {2.97,"
  echo "  3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure and not-railed criteria above, not merely a clean"
  echo "  ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_sg13cmos5l_closed_loop_startup_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Extraction inputs:"
  echo "    \`layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.pex.spice\`,"
  echo "    \`layout/sg13cmos5l-bandgap_top/pex_extract_report.json\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #84."
} > "${MD_OUT}"

write_pvt_summary
