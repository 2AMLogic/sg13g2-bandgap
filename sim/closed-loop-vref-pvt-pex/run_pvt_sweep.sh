#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-pvt-pex/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Does NOT require `klt` to run -- klt was used once, offline, to
# produce the committed layout/bandgap_top/bandgap_top.pex.spice this
# testbench re-encodes (see README.md "Cold-start invocation" for how to
# regenerate that input). Full testbench rationale and what this sweep does
# and does not claim: sim/closed-loop-vref-pvt-pex/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

# DUT_NETLIST/DUT_GIT_SHA below stamps the ONE schematic file this bench
# still splices verbatim (XQ1/XQ2/XQ3 -- bipolar devices, not extracted).
# Every MOS/resistor device instead comes from the layout-extracted
# layout/bandgap_top/bandgap_top.pex.spice -- its own git sha is stamped
# separately below as LAYOUT_GIT_SHA, matching
# sim/core-open-loop-bias-pex/run_pvt_sweep.sh's convention.
DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_pex.spice.tmpl"

# This bench's every MOS/resistor device carries geometry baked in from the
# extraction at template-authoring time (matching
# sim/core-open-loop-bias-pex's own convention) -- no @@MSENSE_W@@ template
# token, unlike the schematic-level sim/closed-loop-vref-pvt.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice
LAYOUT_GIT_SHA="$(dut_git_sha layout/bandgap_top/bandgap_top.pex.spice)"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_2ms_v,vref_3ms_v,vref_settle_delta_v,vbeq3_2ms_v,vbeq3_3ms_v" > "${CSV_OUT}"

# Same pass criteria and settledness bound as sim/closed-loop-vref-pvt --
# see that script's own comment for the full rationale (this bench
# co-simulates the identical topology, just with layout-extracted device
# geometry and real wire parasitics in place of schematic defaults).
SETTLE_TOL_V="0.001"

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true` on each: a marginal PVT corner can genuinely fail to
      # converge at the near-singular early instant on the vdd ramp, in
      # which case ngspice's .measure lines never print and grep finds no
      # match -- same rationale as every other closed-loop run_pvt_sweep.sh
      # in this tree.
      fb_v=$(grep -E '^v_fb_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns1_v=$(grep -E '^v_sns1_v' "${log}" | head -1 | awk '{print $3}' || true)
      sns2_v=$(grep -E '^v_sns2_v' "${log}" | head -1 | awk '{print $3}' || true)
      det_v=$(grep -E '^v_det_v' "${log}" | head -1 | awk '{print $3}' || true)
      i_mkfb_a=$(grep -E '^i_mkfb_v' "${log}" | head -1 | awk '{print $3}' || true)
      vref_2ms=$(grep -E '^v_vref_2ms' "${log}" | head -1 | awk '{print $3}' || true)
      vref_3ms=$(grep -E '^v_vref_3ms' "${log}" | head -1 | awk '{print $3}' || true)
      vbeq3_2ms=$(grep -E '^v_vbeq3_2ms' "${log}" | head -1 | awk '{print $3}' || true)
      vbeq3_3ms=$(grep -E '^v_vbeq3_3ms' "${log}" | head -1 | awk '{print $3}' || true)

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
        verdict=$(pvt_closed_loop_verdict "${det_v}" "${i_mkfb_a}" "${fb_v}" "${dvsns_v}" "${vdd}" "${settle_delta}" "${SETTLE_TOL_V}")
      fi

      tally_verdict "${verdict}" "${corner_id}"
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_2ms},${vref_3ms},${settle_delta},${vbeq3_2ms},${vbeq3_3ms}" >> "${CSV_OUT}"
    done
  done
done

# Informal TC computation, same endpoint method and disclaimer as
# sim/closed-loop-vref-pvt/run_pvt_sweep.sh -- see that script's own comment.
TC_OUT="${RECORDS_DIR}/${RECORD_ID}-tc.csv"
echo "corner_label,vdd_v,vref_neg40_v,vref_27_v,vref_125_v,tc_ppm_per_c" > "${TC_OUT}"
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    v_n40=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="-40" && $7=="PASS" {print $15}' "${CSV_OUT}")
    v_27=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="27" && $7=="PASS" {print $15}' "${CSV_OUT}")
    v_125=$(awk -F, -v c="${corner}" -v v="${vdd}" '$1==c && $6==v && $5=="125" && $7=="PASS" {print $15}' "${CSV_OUT}")
    if [[ -n "${v_n40}" && -n "${v_27}" && -n "${v_125}" ]]; then
      tc=$(awk -v a="${v_n40}" -v b="${v_27}" -v c="${v_125}" 'BEGIN{printf "%.3f", 1e6*(c-a)/(165*b)}')
      echo "${corner},${vdd},${v_n40},${v_27},${v_125},${tc}" >> "${TC_OUT}"
    fi
  done
done

# Cross-bench comparison against sim/closed-loop-vref-pvt's own current
# (newest) record -- per-point Δvref, computed here so the record below can
# report it directly rather than requiring a follow-up manual pass (issue
# #186's own acceptance criteria).
SCHEMATIC_RECORDS_DIR="${SIM_DIR}/closed-loop-vref-pvt/records"
SCHEMATIC_CSV="$(find "${SCHEMATIC_RECORDS_DIR}" -maxdepth 1 -name '*.csv' ! -name '*-tc.csv' 2>/dev/null | sort | tail -1 || true)"
DELTA_OUT="${RECORDS_DIR}/${RECORD_ID}-vs-schematic.csv"
echo "corner_label,temp_c,vdd_v,vref_schematic_v,vref_pex_v,delta_vref_v,verdict_schematic,verdict_pex" > "${DELTA_OUT}"
max_abs_delta="0"
max_abs_delta_point=""
if [[ -n "${SCHEMATIC_CSV}" ]]; then
  while IFS=, read -r corner _hbt _mos _res temp vdd _msense sverdict _fb _sns1 _sns2 _det _imkfb _dvsns _svref_2 svref_3 _sdelta _vbeq3_2 _vbeq3_3; do
    [[ "${corner}" == "corner_label" ]] && continue
    pex_row=$(awk -F, -v c="${corner}" -v t="${temp}" -v v="${vdd}" '$1==c && $5==t && $6==v {print}' "${CSV_OUT}")
    [[ -z "${pex_row}" ]] && continue
    pverdict=$(echo "${pex_row}" | awk -F, '{print $7}')
    pvref=$(echo "${pex_row}" | awk -F, '{print $15}')
    if [[ -n "${svref_3}" && -n "${pvref}" ]]; then
      delta=$(awk -v a="${svref_3}" -v b="${pvref}" 'BEGIN{d=b-a; print d}')
      absd=$(awk -v d="${delta}" 'BEGIN{print (d<0)?-d:d}')
      echo "${corner},${temp},${vdd},${svref_3},${pvref},${delta},${sverdict},${pverdict}" >> "${DELTA_OUT}"
      is_max=$(awk -v a="${absd}" -v b="${max_abs_delta}" 'BEGIN{print (a>b)?1:0}')
      if [[ "${is_max}" == "1" ]]; then
        max_abs_delta="${absd}"
        max_abs_delta_point="${corner}_${temp}c_${vdd}v"
      fi
    fi
  done < "${SCHEMATIC_CSV}"
fi

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-pvt-pex (issue #186, T1 tracker"
  echo "  #4 item 7)"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-vref-pvt uses (bandgap_core + bandgap_amp +"
  echo "  bandgap_startup, wired exactly as design/bandgap_top.sch"
  echo "  specifies), vref's DC operating-point value across the full PVT"
  echo "  grid, confirmed settled (|vref(3ms)-vref(2ms)| <= ${SETTLE_TOL_V} V)"
  echo "  at a genuine closed-loop operating point (startup released, loop"
  echo "  closed within ${DVSNS_CLOSE_V} V, fb not railed) -- but with"
  echo "  every MOS/resistor device's geometry and real wire parasitics"
  echo "  taken from \`klt extract --deck sg13g2 --parasitics\` against the"
  echo "  routed, ASSEMBLED \`layout/bandgap_top/bandgap_top.gds\` instead of"
  echo "  the schematic's as-drawn defaults. This is post-layout (PEX)"
  echo "  evidence for T1 tracker #4 item 7's post-layout-simulation bar --"
  echo "  see this directory's README.md for exactly what is and is not"
  echo "  extracted/modelled. NOT a claim against any ratified spec row"
  echo "  (none is ratified yet -- see #125); also computes an INFORMAL"
  echo "  temperature coefficient (endpoint method,"
  echo "  records/${RECORD_ID}-tc.csv) and VBE(Q3), same disclaimers as"
  echo "  sim/closed-loop-vref-pvt."
  echo "- **Devices**: XM1/XM2A/XM2B/XM3A/XM3B/XM3C/XR1/XR2 (bandgap_core),"
  echo "  XMTAIL/XMP1-4/XMN1-4 (bandgap_amp), XRPU/XMSENSE/XMKFB"
  echo "  (bandgap_startup) -- all 17 MOS + 3 resistor devices extracted"
  echo "  from \`layout/bandgap_top/bandgap_top.pex.spice\` (layout git sha"
  echo "  \`${LAYOUT_GIT_SHA}\`), instance-for-instance matching"
  echo "  design/netlist/bandgap_core.spice, bandgap_amp.spice and"
  echo "  bandgap_startup.spice (same models, same nominal w/l/ng/m -- the"
  echo "  extraction only adds as/ad/ps/pd). XQ1/XQ2/XQ3 (npn13G2) are NOT"
  echo "  extracted -- klt's sg13g2 deck still does not recognise bipolar"
  echo "  devices (klayout-tools, filed generically) -- spliced verbatim"
  echo "  from \`design/netlist/bandgap_core.spice\` (schematic git sha"
  echo "  \`${DUT_CORE_GIT_SHA}\`), wired to the extraction's own real net"
  echo "  names. See README.md for the full account, including the three"
  echo "  merged-net-label pins (fb, sns1, sns2)."
  echo "- **Netlist provenance**: layout"
  echo "  (\`layout/bandgap_top/bandgap_top.pex.spice\` @ \`${LAYOUT_GIT_SHA}\`)"
  echo "  for every MOS/resistor device; schematic"
  echo "  (\`design/netlist/bandgap_core.spice\` @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  \`design/netlist/bandgap_amp.spice\` @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  \`design/netlist/bandgap_startup.spice\` @ \`${DUT_STARTUP_GIT_SHA}\`)"
  echo "  for XQ1/XQ2/XQ3 only."
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
  echo "  - Template: \`testbench/tb_closed_loop_vref_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - TC summary CSV: \`records/${RECORD_ID}-tc.csv\`"
  echo "  - Cross-bench delta vs. schematic: \`records/${RECORD_ID}-vs-schematic.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #186."
  echo
  echo "## Informal TC summary (not a spec claim -- see disclaimer above)"
  echo
  echo "| corner | vdd | vref(-40C) | vref(27C) | vref(125C) | TC (ppm/C) |"
  echo "|---|---|---|---|---|---|"
  tail -n +2 "${TC_OUT}" | while IFS=, read -r c v vn v27 v125 tc; do
    echo "| ${c} | ${v} | ${vn} | ${v27} | ${v125} | ${tc} |"
  done
  echo
  echo "## Cross-bench comparison vs. sim/closed-loop-vref-pvt (schematic-level)"
  echo
  if [[ -n "${SCHEMATIC_CSV}" ]]; then
    echo "Schematic-level reference: \`$(basename "${SCHEMATIC_CSV}")\`."
    echo "Per-point \`vref\` at \`t=3ms\` (settled), every point present in"
    echo "both records:"
    echo
    echo "**Max |Δvref| across all compared points: ${max_abs_delta} V**"
    if [[ -n "${max_abs_delta_point}" ]]; then
      echo "(at \`${max_abs_delta_point}\`)."
    fi
    echo
    echo "Full per-point comparison: \`records/${RECORD_ID}-vs-schematic.csv\`."
  else
    echo "No sim/closed-loop-vref-pvt record found to compare against."
  fi
  echo
  echo "## VBE(Q3) per PVT point"
  echo
  echo "\`v(cb3)\` at \`t=3ms\` (settled), one row per PASSing point. Full"
  echo "data: \`records/${RECORD_ID}.csv\` columns"
  echo "\`vbeq3_2ms_v\`/\`vbeq3_3ms_v\`."
  echo
  echo "| corner | temp (C) | vdd (V) | VBE(Q3) at 3ms (V) |"
  echo "|---|---|---|---|"
  awk -F, 'NR>1 && $7=="PASS" {printf "| %s | %s | %s | %s |\n", $1, $5, $6, $18}' "${CSV_OUT}"
} > "${MD_OUT}"

write_pvt_summary
