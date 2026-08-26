#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-pvt/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/closed-loop-vref-pvt/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention sim/closed-loop-startup/run_pvt_sweep.sh uses -- this
# sweep always exercises whatever the schematic currently specifies.
MSENSE_LINE="$(grep -E '^XMSENSE ' "${REPO_ROOT}/design/netlist/bandgap_startup.spice")"
MSENSE_W="$(echo "${MSENSE_LINE}" | grep -oE 'w=[0-9.]+u' | head -1 | sed -e 's/w=//')"
if [[ -z "${MSENSE_W}" ]]; then
  echo "run_pvt_sweep.sh: could not parse XMSENSE's w= from design/netlist/bandgap_startup.spice" >&2
  exit 3
fi

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
DUT_CORE_GIT_SHA="${DUT_GIT_SHA}"
DUT_AMP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_amp.spice 2>/dev/null || echo unknown)"
DUT_STARTUP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_startup.spice 2>/dev/null || echo unknown)"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_2ms_v,vref_3ms_v,vref_settle_delta_v" > "${CSV_OUT}"

# Pass criteria -- the same loop-closure/startup-release/not-railed bar
# sim/closed-loop-startup uses (a prerequisite: a railed or unclosed loop
# has no meaningful "vref" to report), PLUS a settledness check specific to
# this experiment's own DC/vref claim.
DET_RELEASE_FRAC="0.2"
I_MKFB_RELEASE_A="50e-9"
DVSNS_CLOSE_V="0.020"
FB_RAIL_MARGIN_V="0.05"
# vref must not move by more than 1 mV between t=2ms and t=3ms -- confirms
# the value reported is a genuine settled DC point, not a still-slewing
# transient snapshot. 1 mV is a tight bound relative to the ~1.1-1.2 V vref
# itself (well under 0.1%) while still well above ngspice's own tran
# solver's default numerical noise floor at this timescale.
SETTLE_TOL_V="0.001"

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

      sed \
        -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
        -e "s|@@PDK@@|${PDK}|g" \
        -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@TEMP_C@@|${temp}|g" \
        -e "s|@@VDD@@|${vdd}|g" \
        -e "s|@@CORNER_LABEL@@|${corner}|g" \
        -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true` on each: same rationale as sim/closed-loop-startup's own
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
      vref_2ms=$(grep -E '^v_vref_2ms' "${log}" | head -1 | awk '{print $3}' || true)
      vref_3ms=$(grep -E '^v_vref_3ms' "${log}" | head -1 | awk '{print $3}' || true)

      verdict=PASS
      dvsns_v=""
      settle_delta=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_v}" || -z "${i_mkfb_a}" || -z "${sns1_v}" || -z "${sns2_v}" || -z "${fb_v}" || -z "${vref_2ms}" || -z "${vref_3ms}" ]]; then
        verdict=FAIL
      else
        dvsns_v=$(awk -v a="${sns1_v}" -v b="${sns2_v}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        settle_delta=$(awk -v a="${vref_2ms}" -v b="${vref_3ms}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        verdict=$(awk -v det_v="${det_v}" -v i_mkfb_a="${i_mkfb_a}" \
                      -v vdd="${vdd}" -v det_frac="${DET_RELEASE_FRAC}" -v i_thresh="${I_MKFB_RELEASE_A}" \
                      -v dvsns="${dvsns_v}" -v dvsns_thresh="${DVSNS_CLOSE_V}" \
                      -v fb="${fb_v}" -v rail_margin="${FB_RAIL_MARGIN_V}" \
                      -v sdelta="${settle_delta}" -v sdelta_thresh="${SETTLE_TOL_V}" \
          'BEGIN{
             i_abs = (i_mkfb_a < 0) ? -i_mkfb_a : i_mkfb_a;
             startup_released = (det_v <= det_frac*vdd) && (i_abs <= i_thresh);
             loop_closed = (dvsns <= dvsns_thresh);
             not_railed = (fb >= rail_margin) && (fb <= vdd - rail_margin);
             settled = (sdelta <= sdelta_thresh);
             ok = startup_released && loop_closed && not_railed && settled;
             print ok ? "PASS" : "FAIL";
           }')
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_2ms},${vref_3ms},${settle_delta}" >> "${CSV_OUT}"
    done
  done
done

# Informal TC computation (issue #86's own claim, not a spec-conformance
# check -- spec/porting-plan.md Sec 6's vref/TC row is a draft target, not
# ratified, per #13). For each (corner_label, vdd) group that has all three
# temperature points PASS, TC is the endpoint-method slope:
#   TC_ppm_per_C = 1e6 * (vref(125C) - vref(-40C)) / (165 * vref(27C))
# 165 = 125 - (-40), the temperature span; vref(27C) is the reference used
# to convert an absolute V/C slope into a relative ppm/C figure, the same
# normalization convention spec/porting-plan.md Sec 6's own target row uses
# ("< 50 ppm/C").
TC_OUT="${RECORDS_DIR}/${RECORD_ID}-tc.csv"
echo "corner_label,vdd_v,vref_neg40_v,vref_27_v,vref_125_v,tc_ppm_per_c" > "${TC_OUT}"
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    v_n40=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="-40" && $8=="PASS" {print $16}' "${CSV_OUT}")
    v_27=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="27" && $8=="PASS" {print $16}' "${CSV_OUT}")
    v_125=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="125" && $8=="PASS" {print $16}' "${CSV_OUT}")
    if [[ -n "${v_n40}" && -n "${v_27}" && -n "${v_125}" ]]; then
      tc=$(awk -v a="${v_n40}" -v b="${v_27}" -v c="${v_125}" 'BEGIN{printf "%.3f", 1e6*(c-a)/(165*b)}')
      echo "${corner},${vdd},${v_n40},${v_27},${v_125},${tc}" >> "${TC_OUT}"
    fi
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-pvt"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-startup uses (bandgap_core + bandgap_amp +"
  echo "  bandgap_startup, wired exactly as design/bandgap_top.sch"
  echo "  specifies, real devices throughout, no ideal feedback fixture),"
  echo "  vref's DC operating-point value across the full temperature x"
  echo "  supply x HBT/MOS/resistor-process-corner PVT grid, confirmed"
  echo "  settled (|vref(3ms)-vref(2ms)| <= ${SETTLE_TOL_V} V, not merely a"
  echo "  transient snapshot) at a genuine closed-loop operating point"
  echo "  (startup released, loop closed within ${DVSNS_CLOSE_V} V, fb not"
  echo "  railed -- the same three criteria sim/closed-loop-startup uses,"
  echo "  reapplied here at t=3ms as a prerequisite for trusting the vref"
  echo "  reading). Also computes an INFORMAL temperature coefficient (TC)"
  echo "  per process-corner/supply group via the endpoint method"
  echo "  (records/${RECORD_ID}-tc.csv) -- see that file and the README's"
  echo "  own disclaimer: this is NOT a claim against"
  echo "  spec/porting-plan.md Sec 6's draft (unratified, #13) vref/TC"
  echo "  target row."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, same convention"
  echo "  sim/closed-loop-startup uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice, "
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice -- identical device set to"
  echo "  sim/closed-loop-startup, see that experiment's README for the"
  echo "  full device inventory. No fixture stands in for the servo loop."
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
  echo "  - Template: \`testbench/tb_closed_loop_vref.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - TC summary CSV: \`records/${RECORD_ID}-tc.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #86."
  echo
  echo "## Informal TC summary (not a spec claim -- see disclaimer above)"
  echo
  echo "| corner | vdd | vref(-40C) | vref(27C) | vref(125C) | TC (ppm/C) |"
  echo "|---|---|---|---|---|---|"
  tail -n +2 "${TC_OUT}" | while IFS=, read -r c v vn v27 v125 tc; do
    echo "| ${c} | ${v} | ${vn} | ${v27} | ${v125} | ${tc} |"
  done
} > "${MD_OUT}"

write_pvt_summary
