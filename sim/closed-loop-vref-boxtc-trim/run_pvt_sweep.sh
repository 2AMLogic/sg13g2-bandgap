#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-boxtc-trim/run_pvt_sweep.sh
#
# Optional: JOBS=N (default 1) bounded N-way concurrency (wall-clock only,
# same netlists/logs/rows/emission order as sequential -- same contract as
# sim/closed-loop-vref-pvt-boxtc).
#
# Post-trim box-method temperature-coefficient bench (issue #229 --
# DR-0011's obligated post-trim TC re-measurement: "a post-trim TC
# re-measurement bounding the trim-induced TC degradation (DR-0010's
# +/-0.5% budget carries ~0.17% headroom for it -- an estimate to verify,
# not a measurement)"). Same transient fixture, solver options,
# settledness convention and every .measure as
# sim/closed-loop-vref-pvt-boxtc (issue #222) -- this bench re-points that
# experiment at the trim-bearing core and sweeps the trim code.
#
# PHYSICS FRAMING (see design/bandgap_trim_network.md Sec 3): a correctly
# trimmed die sits at its OWN TC-null -- the mismatch population's errors
# are PTAT-shaped (loop-current scaling, R1/R2 ratio, dVBE), and
# correcting the level with R1 restores the die's null ratio to first
# order, whatever code* it lands on. The trim-induced TC that remains
# comes from the SUB-CODE mis-aim: +/-1/2 LSB of quantization plus the
# chord-fit aim error (bounded <~0.4 LSB by sim/trim-coverage/'s measured
# curvature), i.e. |code* - code_null| <=~ 1 code. The grid therefore:
#
#   codes {127, 128, 129}  (+/-1 around the default/null) on the FULL
#       corner x temp x supply grid -- the band real trims land in; the
#       claim gate is the +/-1-code box-TC delta vs code 128.
#   codes {0, 64, 192, 255} (the far codes and rails) on
#       {typ, bcs, wcs} x 3.30 V only -- the TC-vs-code sensitivity slope
#       and its linearity/saturation bound, reported not gated (a
#       correctly-trimmed die never sits there; a MIS-trimmed one is
#       bounded by these).
#
# Writes append-only evidence under corners/<record-id>/,
# netlist-snapshots/<record-id>/ and records/<record-id>.{md,csv,-boxtc.csv,-trimdtc.csv}
# -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_boxtc_trim.spice.tmpl"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

alias_dut_git_shas TRIM=design/netlist/bandgap_trim.spice AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

TEMPS=(-40 -20 0 27 50 75 100 125)
TEMP_SPAN_C=165
CODE_DEFAULT=128

# The +/-1-code band (full grid) and the far codes (scoped grid).
NEAR_CODES=(127 128 129)
FAR_CODES=(0 64 192 255)
FAR_CORNERS=(typ bcs wcs)
FAR_VDDS=(3.30)

# DR-0011's trimmed budget leaves ~0.175% (of 1.050 V) of headroom for
# trim-induced TC drift; the sub-code mis-aim is <=~1 code, so the gate is
# the worst +/-1-code box-TC delta over the 98 C span from the 27 C trim
# point: delta_ppm * 98 / 1e4 %  <=  0.175  <=>  delta_ppm <= 18.75.
TRIM_TC_HEADROOM_PCT="0.175"
TRIM_TC_SPAN_C="98"
GATE_DELTA_PPM_CAP=$(awk -v h="${TRIM_TC_HEADROOM_PCT}" -v s="${TRIM_TC_SPAN_C}" 'BEGIN{printf "%.2f", h*1e4/s}')

JOBS="${JOBS:-1}"
if [[ "${JOBS}" -lt 1 ]]; then
  echo "run_pvt_sweep.sh: JOBS must be >= 1 (got '${JOBS}')." >&2
  exit 3
fi

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,trim_code,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_2ms_v,vref_3ms_v,vref_settle_delta_v,vbeq3_2ms_v,vbeq3_3ms_v" > "${CSV_OUT}"

SETTLE_TOL_V="0.001"
VREF_3MS_COL=17
STATUS_COL=8

ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/boxtct-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

run_one_point() {
  local corner="$1" temp="$2" vdd="$3" code="$4"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  local corner_id="${corner}_code${code}_${temp}c_${vdd}v"
  local netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
  local log="${CORNERS_OUT}/${corner_id}.log"

  common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
  sed \
    "${COMMON_SED_ARGS[@]}" \
    -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
    -e "s|@@MOS_SECTION@@|${mos_section}|g" \
    -e "s|@@RES_SECTION@@|${res_section}|g" \
    -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
    -e "s|@@TRIM_CODE@@|${code}|g" \
    -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} trim=${DUT_TRIM_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
    "${TEMPLATE}" > "${netlist}"

  run_pvt_point "${netlist}" "${log}"

  local fb_v sns1_v sns2_v det_v i_mkfb_a vref_2ms vref_3ms vbeq3_2ms vbeq3_3ms
  fb_v=$(extract_measure '^v_fb_v' "${log}")
  sns1_v=$(extract_measure '^v_sns1_v' "${log}")
  sns2_v=$(extract_measure '^v_sns2_v' "${log}")
  det_v=$(extract_measure '^v_det_v' "${log}")
  i_mkfb_a=$(extract_measure '^i_mkfb_v' "${log}")
  vref_2ms=$(extract_measure '^v_vref_2ms' "${log}")
  vref_3ms=$(extract_measure '^v_vref_3ms' "${log}")
  vbeq3_2ms=$(extract_measure '^v_vbeq3_2ms' "${log}")
  vbeq3_3ms=$(extract_measure '^v_vbeq3_3ms' "${log}")

  local verdict=PASS dvsns_v="" settle_delta=""
  if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
    verdict=FAIL
  elif [[ -z "${det_v}" || -z "${i_mkfb_a}" || -z "${sns1_v}" || -z "${sns2_v}" || -z "${fb_v}" || -z "${vref_2ms}" || -z "${vref_3ms}" ]]; then
    verdict=FAIL
  else
    dvsns_v=$(abs_diff "${sns1_v}" "${sns2_v}")
    settle_delta=$(abs_diff "${vref_2ms}" "${vref_3ms}")
    verdict=$(pvt_closed_loop_verdict "${det_v}" "${i_mkfb_a}" "${fb_v}" "${dvsns_v}" "${vdd}" "${settle_delta}" "${SETTLE_TOL_V}")
  fi

  printf '%s\n' "${corner}_code${code},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${code},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_2ms},${vref_3ms},${settle_delta},${vbeq3_2ms},${vbeq3_3ms}" > "${ROWS_DIR}/${corner_id}.row"
  printf '%s\n' "${verdict}" > "${ROWS_DIR}/${corner_id}.verdict"
}

# The grid: near codes on the full corner x temp x vdd grid; far codes on
# the scoped {typ,bcs,wcs} x 3.30V grid (see header PHYSICS FRAMING).
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${NEAR_CODES[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for vdd in "${VDDS[@]}"; do
        GRID+=("${corner}|${temp}|${vdd}|${code}")
      done
    done
  done
done
for corner in "${FAR_CORNERS[@]}"; do
  for code in "${FAR_CODES[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for vdd in "${FAR_VDDS[@]}"; do
        GRID+=("${corner}|${temp}|${vdd}|${code}")
      done
    done
  done
done

for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd code <<<"${point}"
  if [[ "${JOBS}" -le 1 ]]; then
    run_one_point "${corner}" "${temp}" "${vdd}" "${code}"
  else
    while [[ "$(jobs -rp | wc -l)" -ge "${JOBS}" ]]; do
      sleep 2
    done
    run_one_point "${corner}" "${temp}" "${vdd}" "${code}" &
  fi
done
if [[ "${JOBS}" -gt 1 ]]; then
  wait || true
fi

total=0
passed=0
failed_points=()
for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd code <<<"${point}"
  corner_id="${corner}_code${code}_${temp}c_${vdd}v"
  total=$((total + 1))
  if [[ -f "${ROWS_DIR}/${corner_id}.row" ]]; then
    cat "${ROWS_DIR}/${corner_id}.row" >> "${CSV_OUT}"
    verdict="$(cat "${ROWS_DIR}/${corner_id}.verdict")"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    echo "${corner}_code${code},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,${code},,,,,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# Box-method TC per (corner x code, vdd) group -- the same formula as
# sim/closed-loop-vref-pvt-boxtc, one group per (corner, code, supply).
BOXT_OUT="${RECORDS_DIR}/${RECORD_ID}-boxtc.csv"
echo "corner_label,trim_code,vdd_v,n_pass,n_grid,vmin_v,vmin_temp_c,vmax_v,vmax_temp_c,vref_27c_v,box_tc_ppm_per_c,endpoint_tc_ppm_per_c" > "${BOXT_OUT}"
ALL_CODE_LABELS=("${NEAR_CODES[@]}" "${FAR_CODES[@]}")
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${ALL_CODE_LABELS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      awk -F, -v c="${corner}_code${code}" -v code_in="${code}" -v vdd_in="${vdd}" -v vcol="${VREF_3MS_COL}" -v scol="${STATUS_COL}" \
        -v span="${TEMP_SPAN_C}" -v out="${BOXT_OUT}" '
        $1==c && $6==vdd_in {
          n_grid++
          if ($scol == "PASS") {
            rv = $vcol; t = $5
            n_pass++
            if (t == 27) v27 = rv
            if (n_pass == 1 || rv < vmin) { vmin = rv; tmin = t }
            if (n_pass == 1 || rv > vmax) { vmax = rv; tmax = t }
            if (t == -40) vn40 = rv
            if (t == 125) v125 = rv
          }
        }
        END {
          if (n_pass > 0 && v27 != "") {
            box = 1e6 * (vmax - vmin) / (span * v27)
            line = sprintf("%s,%s,%s,%d,%d,%.5g,%d,%.5g,%d,%.5g,%.3f", c, code_in, vdd_in, n_pass, n_grid, vmin, tmin, vmax, tmax, v27, box)
            if (vn40 != "" && v125 != "")
              line = line sprintf(",%.3f", 1e6 * (v125 - vn40) / (span * v27))
            else
              line = line ","
            print line >> out
          }
        }' "${CSV_OUT}"
    done
  done
done

# ---------------------------------------- Trim-induced TC (the claim gate)
# Per (corner, vdd) on the FULL grid: the +/-1-code box-TC delta vs the
# code-128 baseline (the sub-code mis-aim band), gated at
# GATE_DELTA_PPM_CAP; the far-code deltas ride along, ungated, as the
# sensitivity slope and its saturation bound.
DELT_OUT="${RECORDS_DIR}/${RECORD_ID}-trimdtc.csv"
echo "corner_label,vdd_v,scope,box_tc_128_ppm_c,delta_code,box_tc_code_ppm_c,delta_ppm_c,drift_pct_of_target,gate_ppm_c,gate_status" > "${DELT_OUT}"
headroom_fail=0
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    tc128=$(awk -F, -v c="${corner}_code128" -v vdd_in="${vdd}" 'NR>1 && $1==c && $3==vdd_in {print $11; exit}' "${BOXT_OUT}")
    [[ -z "${tc128}" ]] && continue
    for code in "${NEAR_CODES[@]}"; do
      [[ "${code}" == "128" ]] && continue
      tcc=$(awk -F, -v c="${corner}_code${code}" -v vdd_in="${vdd}" 'NR>1 && $1==c && $3==vdd_in {print $11; exit}' "${BOXT_OUT}")
      [[ -z "${tcc}" ]] && continue
      delta=$(awk -v a="${tcc}" -v b="${tc128}" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.3f", d}')
      drift=$(awk -v d="${delta}" -v s="${TRIM_TC_SPAN_C}" 'BEGIN{printf "%.4f", d*s/1e4}')
      hs=OK
      if awk -v a="${delta}" -v b="${GATE_DELTA_PPM_CAP}" 'BEGIN{exit !(a>b)}'; then
        hs=FAIL
        headroom_fail=$((headroom_fail+1))
      fi
      echo "${corner},${vdd},near,${tc128},${code},${tcc},${delta},${drift},${GATE_DELTA_PPM_CAP},${hs}" >> "${DELT_OUT}"
    done
  done
done
for corner in "${FAR_CORNERS[@]}"; do
  for vdd in "${FAR_VDDS[@]}"; do
    tc128=$(awk -F, -v c="${corner}_code128" -v vdd_in="${vdd}" 'NR>1 && $1==c && $3==vdd_in {print $11; exit}' "${BOXT_OUT}")
    [[ -z "${tc128}" ]] && continue
    for code in "${FAR_CODES[@]}"; do
      tcc=$(awk -F, -v c="${corner}_code${code}" -v vdd_in="${vdd}" 'NR>1 && $1==c && $3==vdd_in {print $11; exit}' "${BOXT_OUT}")
      [[ -z "${tcc}" ]] && continue
      delta=$(awk -v a="${tcc}" -v b="${tc128}" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.3f", d}')
      drift=$(awk -v d="${delta}" -v s="${TRIM_TC_SPAN_C}" 'BEGIN{printf "%.4f", d*s/1e4}')
      echo "${corner},${vdd},far,${tc128},${code},${tcc},${delta},${drift},${GATE_DELTA_PPM_CAP},n/a" >> "${DELT_OUT}"
    done
  done
done

WORST_BOX=$(awk -F, 'NR>1 && $4==$5 && $11+0 > m { m = $11+0; line = $1"/"$3"V = "sprintf("%.1f", $11)" ppm/C" } END { print line }' "${BOXT_OUT}")
WORST_NEAR=$(awk -F, 'NR>1 && $3=="near" && $7+0 > m { m=$7+0; line = $1"/"$2"V code"$5" vs 128: +"sprintf("%.2f", $7)" ppm/C ("$8"% over 98C, cap "$9")" } END { print line }' "${DELT_OUT}")

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-boxtc-trim (issue #229)"
  echo "- **Claim**: the post-trim box-method TC re-measurement DR-0011's"
  echo "  +/-0.5% trimmed budget obligates, bounding the trim-induced TC"
  echo "  degradation. A correctly-trimmed die sits at its OWN TC-null"
  echo "  (the mismatch population's errors are PTAT-shaped; correcting"
  echo "  the level with R1 restores the null ratio -- see"
  echo "  design/bandgap_trim_network.md Sec 3), so the residual"
  echo "  trim-induced TC comes from the sub-code mis-aim (+/-1/2 LSB"
  echo "  quantization + <~0.4 LSB chord-fit aim), i.e. <=~1 code off"
  echo "  null. This bench measures the box-method TC on the same"
  echo "  8-temperature grid as sim/closed-loop-vref-pvt-boxtc at codes"
  echo "  {127, 128, 129} (the +/-1-code band, full corner x supply grid)"
  echo "  and gates the +/-1-code delta vs the code-128 baseline at"
  echo "  ${GATE_DELTA_PPM_CAP} ppm/C (the ~0.175% headroom DR-0011's budget"
  echo "  carries, over the 98 C span from the 27 C trim point). Codes"
  echo "  {0, 64, 192, 255} on {typ, bcs, wcs}/3.30 V bound the"
  echo "  TC-vs-code sensitivity slope and its saturation (reported,"
  echo "  ungated -- a correctly-trimmed die never sits there; a"
  echo "  mis-trimmed one is bounded by them). NOT a claim against a"
  echo "  different target -- the ratified TC row (< 50 ppm/C) is"
  echo "  unchanged."
  echo "- **Devices**: all real PDK compact models; the DUT is the"
  echo "  trim-bearing bandgap_core (R1 base l=37.2u + XXTRIM ladder),"
  echo "  ladder subcircuit copied device-for-device from"
  echo "  design/netlist/bandgap_trim.spice, plus bandgap_amp and"
  echo "  bandgap_startup verbatim -- identical fixture and measures to"
  echo "  sim/closed-loop-vref-pvt-boxtc."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_trim.spice @ \`${DUT_TRIM_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **JOBS**: ${JOBS} (wall-clock concurrency only)."
  echo "- **Corner matrix run**: {typ, bcs, wcs, sf, fs} x {2.97, 3.30,"
  echo "  3.63} V x 8 temperatures x codes {127, 128, 129} (full grid)"
  echo "  + {typ, bcs, wcs} x 3.30 V x codes {0, 64, 192, 255}"
  echo "  = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed AND settledness criteria above). Worst"
  echo "  box-method group across complete groups: ${WORST_BOX}. Worst"
  echo "  +/-1-code trim-induced delta: ${WORST_NEAR};"
  echo "  ${headroom_fail} near-band group(s) FAIL the ${GATE_DELTA_PPM_CAP} ppm/C"
  echo "  headroom gate (see records/${RECORD_ID}-trimdtc.csv)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
    echo "  Box-method groups a failed point shrank are disclosed by"
    echo "  n_pass < n_grid in records/${RECORD_ID}-boxtc.csv; each such"
    echo "  exclusion is justified from THIS record's own committed"
    echo "  flanking points, never from a scratch re-run."
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_vref_boxtc_trim.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Box-method TC summary CSV: \`records/${RECORD_ID}-boxtc.csv\`"
  echo "  - Trim-induced TC deltas: \`records/${RECORD_ID}-trimdtc.csv\`"
  echo "  - Trim-domain MC: \`sim/closed-loop-vref-trim-mc/\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
