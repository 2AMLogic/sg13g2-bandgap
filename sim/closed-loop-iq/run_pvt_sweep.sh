#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-iq/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/closed-loop-iq/README.md.
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

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_iq.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention sim/closed-loop-vref-pvt/run_pvt_sweep.sh uses -- this
# sweep always exercises whatever the schematic currently specifies.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,iq_2ms_a,iq_3ms_a,iq_avg_a,iq_settle_delta_a" > "${CSV_OUT}"

# Pass criteria -- the same loop-closure/startup-release/not-railed bar
# sim/closed-loop-startup and sim/closed-loop-vref-pvt use (DET_RELEASE_FRAC/
# I_MKFB_RELEASE_A/DVSNS_CLOSE_V/FB_RAIL_MARGIN_V and the verdict formula
# itself come from sim/lib/pvt_verdict_common.sh -- see that file's own
# header comment for the full rationale; a railed or unclosed loop has no
# meaningful quiescent operating point to report), PLUS a settledness check
# specific to this experiment's own Iq claim.
# The total vdd current must not move by more than 100 nA between t=2ms and
# t=3ms -- confirms the reported Iq is a genuine settled quiescent value,
# not a still-slewing transient snapshot. 100 nA is a tight bound relative
# to this design's own measured Iq scale (tens of uA -- well under 1%)
# while still comfortably above ngspice's own tran solver's default
# numerical noise floor at this timescale. Same discipline as
# sim/closed-loop-vref-pvt's SETTLE_TOL_V, expressed in amps instead of
# volts because this experiment's headline quantity is a current.
SETTLE_TOL_A="1e-7"

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

      # `|| true` on each: same rationale as sim/closed-loop-vref-pvt's own
      # run_pvt_sweep.sh -- a marginal PVT corner can genuinely fail to
      # converge at the near-singular early instant on the vdd ramp, in
      # which case ngspice's .measure lines never print and grep finds no
      # match. Under `set -euo pipefail`, letting that grep failure abort
      # the script would lose every other point's evidence.
      fb_v=$(grep -E '^v_fb_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns1_v=$(grep -E '^v_sns1_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns2_v=$(grep -E '^v_sns2_v' "${log}" | head -1 | awk '{print $3}' || true)
      det_v=$(grep -E '^v_det_v' "${log}" | head -1 | awk '{print $3}' || true)
      i_mkfb_a=$(grep -E '^i_mkfb_v' "${log}" | head -1 | awk '{print $3}' || true)
      iq_2ms=$(grep -E '^i_vdd_2ms' "${log}" | head -1 | awk '{print $3}' || true)
      iq_3ms=$(grep -E '^i_vdd_3ms' "${log}" | head -1 | awk '{print $3}' || true)
      iq_avg=$(grep -E '^i_vdd_avg' "${log}" | head -1 | awk '{print $3}' || true)

      verdict=PASS
      dvsns_v=""
      settle_delta=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_v}" || -z "${i_mkfb_a}" || -z "${sns1_v}" || -z "${sns2_v}" || -z "${fb_v}" || -z "${iq_2ms}" || -z "${iq_3ms}" || -z "${iq_avg}" ]]; then
        verdict=FAIL
      else
        dvsns_v=$(awk -v a="${sns1_v}" -v b="${sns2_v}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        settle_delta=$(awk -v a="${iq_2ms}" -v b="${iq_3ms}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        verdict=$(pvt_closed_loop_verdict "${det_v}" "${i_mkfb_a}" "${fb_v}" "${dvsns_v}" "${vdd}" "${settle_delta}" "${SETTLE_TOL_A}")
      fi

      # Iq is reported as a magnitude: Vvdd is an independent voltage
      # source, so ngspice's passive sign convention reports i(Vvdd)
      # negative while it delivers (rather than absorbs) current to the
      # circuit -- the same sign-handling convention this template's own
      # i(Vmkfb) measurement needs (see run_pvt_sweep.sh's i_abs above).
      iq_2ms_abs=""
      iq_3ms_abs=""
      iq_avg_abs=""
      if [[ -n "${iq_2ms}" ]]; then
        iq_2ms_abs=$(awk -v a="${iq_2ms}" 'BEGIN{print (a<0)?-a:a}')
      fi
      if [[ -n "${iq_3ms}" ]]; then
        iq_3ms_abs=$(awk -v a="${iq_3ms}" 'BEGIN{print (a<0)?-a:a}')
      fi
      if [[ -n "${iq_avg}" ]]; then
        iq_avg_abs=$(awk -v a="${iq_avg}" 'BEGIN{print (a<0)?-a:a}')
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${iq_2ms_abs},${iq_3ms_abs},${iq_avg_abs},${settle_delta}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-iq"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-startup and sim/closed-loop-vref-pvt use"
  echo "  (bandgap_core + bandgap_amp + bandgap_startup, wired exactly as"
  echo "  design/bandgap_top.sch specifies, real devices throughout, no"
  echo "  ideal current-source/fixture standing in for any block), total"
  echo "  vdd quiescent supply current (Iq) across the full temperature x"
  echo "  supply x HBT/MOS/resistor-process-corner PVT grid, confirmed"
  echo "  settled (|i(Vvdd)(3ms)-i(Vvdd)(2ms)| <= ${SETTLE_TOL_A} A, not"
  echo "  merely a transient snapshot) at a genuine closed-loop operating"
  echo "  point (startup released, loop closed within ${DVSNS_CLOSE_V} V, fb"
  echo "  not railed -- the same three criteria sim/closed-loop-startup and"
  echo "  sim/closed-loop-vref-pvt use, reapplied here at t=3ms as a"
  echo "  prerequisite for trusting the Iq reading). This does NOT compare"
  echo "  the measured Iq against spec/porting-plan.md Sec 6's draft"
  echo "  (unratified, #13) '< 50 uA' Iq target as a pass/fail verdict --"
  echo "  see the README's own disclaimer. Reported as evidence only."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, same convention"
  echo "  sim/closed-loop-vref-pvt uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice, "
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice -- identical device set to"
  echo "  sim/closed-loop-startup and sim/closed-loop-vref-pvt, see"
  echo "  sim/closed-loop-startup/README.md for the full device inventory."
  echo "  No fixture stands in for the servo loop; Vvdd (the supply source"
  echo "  every testbench in this tree already has) is the ammeter this"
  echo "  experiment reads, not an added fixture."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed AND settledness criteria above)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_iq.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #95."
  echo
  echo "## Iq summary (evidence only -- NOT a spec-conformance verdict, see"
  echo "disclaimer above)"
  echo
  min_iq=$(tail -n +2 "${CSV_OUT}" | awk -F, '$8=="PASS" && $17!="" {print $17}' | sort -g | head -1)
  max_iq=$(tail -n +2 "${CSV_OUT}" | awk -F, '$8=="PASS" && $17!="" {print $17}' | sort -g | tail -1)
  if [[ -n "${min_iq}" && -n "${max_iq}" ]]; then
    echo "Across ${passed} PASS points, the settled quiescent Iq (\`iq_avg_a\`,"
    echo "averaged over [2ms,3ms]) ranges **${min_iq} A - ${max_iq} A**."
  else
    echo "No PASS points -- no Iq range to summarize."
  fi
} > "${MD_OUT}"

write_pvt_summary
