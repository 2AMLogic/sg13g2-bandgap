#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-boxtc-trim/run_pvt_sweep.sh
#
# Optional: JOBS=N (default 1) bounded N-way concurrency (wall-clock only).
# Optional: TRIM_CODES="128 127 129" scopes the code axis (record mints a
# new <record-id>; the default full axis is documented in README.md).
#
# Post-trim box-method temperature-coefficient bench (issue #229 --
# DR-0011's obligated post-trim TC re-measurement), .op-grid variant with
# per-corner transient validation:
#
#   GRID points run as .nodeset-seeded .op draws (the sim/closed-loop-
#   vref-mc technique): each (corner, code, temp, supply) point is one
#   fast operating point through the aids-free trim-bearing netlist, and
#   the box TC per (corner x code, supply) group is computed over the
#   same 8-temperature grid {-40,-20,0,27,50,75,100,125} C as
#   sim/closed-loop-vref-pvt-boxtc.
#   VALIDATION points (one per process corner, code 128, 27 C, 3.30 V)
#   run the FULL transient fixture (200us ramp, 3ms hold, the #222
#   settledness convention) and must agree with the same point's .op to
#   <= 0.1 mV -- the tran<->op equivalence this bench's aids-free
#   netlist was verified against (see README "Solver options"), now
#   demonstrated per corner inside the record itself.
#
# PHYSICS FRAMING (see design/bandgap_trim_network.md Sec 3): a
# correctly-trimmed die sits at its OWN TC-null; the residual
# trim-induced TC comes from the sub-code mis-aim (+/-1/2 LSB
# quantization + <~0.4 LSB chord-fit aim), i.e. <=~1 code off null.
# Codes {127, 128, 129} (the +/-1-code band) run on the FULL corner x
# supply grid -- the claim gate. Codes {0, 64, 192, 255} (far codes and
# rails, the ungated sensitivity-slope bounds) run on
# {typ, bcs, wcs} x 3.30 V.
#
# Writes append-only evidence under corners/<record-id>/,
# netlist-snapshots/<record-id>/ and records/<record-id>.{md,csv,-boxtc.csv,-trimdtc.csv,-validate.csv}
# -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TRAN_TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_boxtc_trim.spice.tmpl"
OP_TEMPLATE="${SIM_DIR}/trim-coverage/testbench/tb_trim_coverage.spice.tmpl"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

alias_dut_git_shas TRIM=design/netlist/bandgap_trim.spice AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

TEMPS=(-40 -20 0 27 50 75 100 125)
TEMP_SPAN_C=165
TRIM_CODES_STR="${TRIM_CODES:-128 127 129 0 64 192 255}"
read -r -a TRIM_CODES <<< "${TRIM_CODES_STR}"
NEAR_CODES=(127 128 129)
FAR_CODES=(0 64 192 255)
FAR_CORNERS=(typ bcs wcs)
FAR_VDDS=(3.30)

TRIM_TC_HEADROOM_PCT="0.175"
TRIM_TC_SPAN_C="98"
GATE_DELTA_PPM_CAP=$(awk -v h="${TRIM_TC_HEADROOM_PCT}" -v s="${TRIM_TC_SPAN_C}" 'BEGIN{printf "%.2f", h*1e4/s}')
VALIDATE_TOL_V="0.0001"

JOBS="${JOBS:-1}"
if [[ "${JOBS}" -lt 1 ]]; then
  echo "run_pvt_sweep.sh: JOBS must be >= 1 (got '${JOBS}')." >&2
  exit 3
fi

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,trim_code,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_v,vbeq3_v" > "${CSV_OUT}"

ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/boxtct-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

render_op() {
  # render_op OUT CORNER TEMP VDD CODE
  local out="$1" corner="$2" temp="$3" vdd="$4" code="$5"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  # .nodeset seeds: sim/closed-loop-startup's seed grid is the 3-point
  # {-40, 27, 125} C; this bench's 8-temp grid falls back to the NEAREST
  # seeded temperature (-20/-40, 0/-40, 50/27, 75/125, 100/125). The
  # .nodeset is a Newton-Raphson initial-guess HINT only (the same
  # convention sim/closed-loop-vref-mc states for its mismatch draws,
  # which converge near-but-not-at their seeds by design), and the
  # tran<->op validation points pin the method at the seeded temps.
  local seed_temp="${temp}"
  case "${temp}" in
    -20|-40) seed_temp=-40 ;;
    0) seed_temp=-40 ;;
    50|27) seed_temp=27 ;;
    75|100|125) seed_temp=125 ;;
  esac
  if [[ -z "$(lookup_seed "${corner}" "${seed_temp}" "${vdd}" fb_final_v)" ]]; then
    seed_temp=27
  fi
  local fb_seed sns1_seed sns2_seed vref_seed
  fb_seed="$(lookup_seed "${corner}" "${seed_temp}" "${vdd}" fb_final_v)"
  sns1_seed="$(lookup_seed "${corner}" "${seed_temp}" "${vdd}" sns1_final_v)"
  sns2_seed="$(lookup_seed "${corner}" "${seed_temp}" "${vdd}" sns2_final_v)"
  vref_seed="$(lookup_seed "${corner}" "${seed_temp}" "${vdd}" vref_final_v)"
  if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
    echo "run_pvt_sweep.sh: no PASS seed row for ${corner}/${seed_temp}C/${vdd}V -- run sim/closed-loop-startup first." >&2
    exit 3
  fi
  common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
  sed \
    "${COMMON_SED_ARGS[@]}" \
    -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
    -e "s|@@MOS_SECTION@@|${mos_section}|g" \
    -e "s|@@RES_SECTION@@|${res_section}|g" \
    -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
    -e "s|@@FB_SEED@@|${fb_seed}|g" \
    -e "s|@@SNS1_SEED@@|${sns1_seed}|g" \
    -e "s|@@SNS2_SEED@@|${sns2_seed}|g" \
    -e "s|@@VREF_SEED@@|${vref_seed}|g" \
    -e "s|@@TRIM_CODE@@|${code}|g" \
    -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} trim=${DUT_TRIM_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
    "${OP_TEMPLATE}" > "${out}"
}

run_one_op_point() {
  local corner="$1" temp="$2" vdd="$3" code="$4"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  local corner_id="${corner}_code${code}_${temp}c_${vdd}v"
  local netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
  local log="${CORNERS_OUT}/${corner_id}.log"

  render_op "${netlist}" "${corner}" "${temp}" "${vdd}" "${code}"

  set +e
  timeout 300 ngspice -b "${netlist}" > "${log}" 2>&1
  local rc=$?
  set -e
  local model_error=0
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type" "${log}"; then
    model_error=1
  fi

  local fb_v sns1_v sns2_v vref_v det_v vbeq3_v i_mkfb_a
  fb_v=$(extract_op_voltage fb "${log}")
  sns1_v=$(extract_op_voltage sns1 "${log}")
  sns2_v=$(extract_op_voltage sns2 "${log}")
  vref_v=$(extract_op_voltage vref "${log}")
  det_v=$(extract_op_voltage det "${log}")
  vbeq3_v=$(extract_op_voltage cb3 "${log}")
  i_mkfb_a=$(grep -E '^i\(vmkfb\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)

  local verdict=PASS dvsns_v=""
  if [[ "${rc}" -ne 0 || "${model_error}" -ne 0 ]]; then
    verdict=FAIL
  elif [[ -z "${fb_v}" || -z "${sns1_v}" || -z "${sns2_v}" || -z "${vref_v}" || -z "${det_v}" || -z "${i_mkfb_a}" ]]; then
    verdict=FAIL
  else
    dvsns_v=$(abs_diff "${sns1_v}" "${sns2_v}")
    verdict=$(pvt_closed_loop_verdict "${det_v}" "${i_mkfb_a}" "${fb_v}" "${dvsns_v}" "${vdd}")
  fi

  printf '%s\n' "${corner}_code${code},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${code},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_v},${vbeq3_v}" > "${ROWS_DIR}/${corner_id}.row"
  printf '%s\n' "${verdict}" > "${ROWS_DIR}/${corner_id}.verdict"
}

run_one_tran_validation() {
  local corner="$1"
  local temp="27" vdd="3.30" code="128"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  local corner_id="${corner}_tranval_${temp}c_${vdd}v"
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
    "${TRAN_TEMPLATE}" > "${netlist}"

  set +e
  timeout 600 ngspice -b "${netlist}" > "${log}" 2>&1
  local rc=$?
  set -e

  local vref_3ms vref_2ms vref_op
  vref_3ms=$(extract_measure '^v_vref_3ms' "${log}")
  vref_2ms=$(extract_measure '^v_vref_2ms' "${log}")
  # The .op row may not exist yet at validation time (grid order under
  # JOBS>1); read the op point's own row file, waiting bounded.
  vref_op=""
  local op_row="${ROWS_DIR}/${corner}_code128_${temp}c_${vdd}v.row"
  local waited=0
  while [[ -z "${vref_op}" && ${waited} -lt 120 ]]; do
    if [[ -f "${op_row}" ]]; then
      vref_op=$(awk -F, '{print $16}' "${op_row}")
    fi
    if [[ -z "${vref_op}" ]]; then sleep 5; waited=$((waited + 5)); fi
  done

  local verdict=FAIL delta=""
  if [[ "${rc}" -eq 0 && -n "${vref_3ms}" && -n "${vref_2ms}" && -n "${vref_op}" ]]; then
    local settle
    settle=$(abs_diff "${vref_2ms}" "${vref_3ms}")
    delta=$(abs_diff "${vref_3ms}" "${vref_op}")
    if awk -v s="${settle}" 'BEGIN{exit !(s<=0.001)}' && awk -v d="${delta}" -v t="${VALIDATE_TOL_V}" 'BEGIN{exit !(d<=t)}'; then
      verdict=PASS
    fi
  fi
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "${corner}_tranval" "${hbt_section}" "${mos_section}" "${res_section}" \
    "${temp}" "${vdd}" "${MSENSE_W}" "${verdict}" "128" "" "" "" "" "" "" "" "${vref_3ms}" \
    > "${ROWS_DIR}/${corner}_tranval_${temp}c_${vdd}v.row"
  printf '%s\n' "${verdict}" > "${ROWS_DIR}/${corner}_tranval_${temp}c_${vdd}v.verdict"
}

# The grid: near codes full grid, far codes scoped (see header).
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${NEAR_CODES[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for vdd in "${VDDS[@]}"; do
        GRID+=("op|${corner}|${temp}|${vdd}|${code}")
      done
    done
  done
done
for corner in "${FAR_CORNERS[@]}"; do
  for code in "${FAR_CODES[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for vdd in "${FAR_VDDS[@]}"; do
        GRID+=("op|${corner}|${temp}|${vdd}|${code}")
      done
    done
  done
done
for corner in "${CORNER_LABELS[@]}"; do
  GRID+=("tran|${corner}|27|3.30|128")
done

for point in "${GRID[@]}"; do
  IFS='|' read -r kind corner temp vdd code <<<"${point}"
  if [[ "${JOBS}" -le 1 ]]; then
    if [[ "${kind}" == "op" ]]; then run_one_op_point "${corner}" "${temp}" "${vdd}" "${code}"; else run_one_tran_validation "${corner}"; fi
  else
    while [[ "$(jobs -rp | wc -l)" -ge "${JOBS}" ]]; do
      sleep 2
    done
    if [[ "${kind}" == "op" ]]; then run_one_op_point "${corner}" "${temp}" "${vdd}" "${code}" & else run_one_tran_validation "${corner}" & fi
  fi
done
if [[ "${JOBS}" -gt 1 ]]; then
  wait || true
fi

total=0
passed=0
failed_points=()
for point in "${GRID[@]}"; do
  IFS='|' read -r kind corner temp vdd code <<<"${point}"
  if [[ "${kind}" == "tran" ]]; then
    corner_id="${corner}_tranval_${temp}c_${vdd}v"
  else
    corner_id="${corner}_code${code}_${temp}c_${vdd}v"
  fi
  total=$((total + 1))
  if [[ -f "${ROWS_DIR}/${corner_id}.row" ]]; then
    cat "${ROWS_DIR}/${corner_id}.row" >> "${CSV_OUT}"
    verdict="$(cat "${ROWS_DIR}/${corner_id}.verdict")"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    echo "${corner%%_*},,${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,${code},,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# Box-method TC per (corner x code, vdd) group over the 8-temp .op grid
# (same formula as sim/closed-loop-vref-pvt-boxtc).
BOXT_OUT="${RECORDS_DIR}/${RECORD_ID}-boxtc.csv"
echo "corner_label,trim_code,vdd_v,n_pass,n_grid,vmin_v,vmin_temp_c,vmax_v,vmax_temp_c,vref_27c_v,box_tc_ppm_per_c" > "${BOXT_OUT}"
ALL_CODE_LABELS=("${NEAR_CODES[@]}" "${FAR_CODES[@]}")
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${ALL_CODE_LABELS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      awk -F, -v c="${corner}_code${code}" -v code_in="${code}" -v vdd_in="${vdd}" -v vcol="16" -v scol="8" \
        -v span="${TEMP_SPAN_C}" -v out="${BOXT_OUT}" '
        $1==c && $6==vdd_in {
          n_grid++
          if ($scol == "PASS") {
            rv = $vcol; t = $5
            n_pass++
            if (t == 27) v27 = rv
            if (n_pass == 1 || rv < vmin) { vmin = rv; tmin = t }
            if (n_pass == 1 || rv > vmax) { vmax = rv; tmax = t }
          }
        }
        END {
          if (n_pass > 0 && v27 != "") {
            box = 1e6 * (vmax - vmin) / (span * v27)
            printf "%s,%s,%s,%d,%d,%.5g,%d,%.5g,%d,%.5g,%.3f\n", c, code_in, vdd_in, n_pass, n_grid, vmin, tmin, vmax, tmax, v27, box >> out
          }
        }' "${CSV_OUT}"
    done
  done
done

# ------------------------------------------------- Trim-induced TC (gate)
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
WORST_NEAR=$(awk -F, 'NR>1 && $3=="near" && $7+0 > m { m=$7+0; line = $1"/"$2"V @code"$5" vs 128: +"sprintf("%.2f", $7)" ppm/C ("$8"% over 98C, cap "$9")" } END { print line }' "${DELT_OUT}")

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
  echo "  null. This bench measures the box-method TC"
  echo "  ((vmax-vmin)/(vref(27C)*165 C)) on the same 8-temperature grid"
  echo "  as sim/closed-loop-vref-pvt-boxtc at codes {127, 128, 129} (the"
  echo "  +/-1-code band, full corner x supply grid) and gates the"
  echo "  +/-1-code delta vs the code-128 baseline at ${GATE_DELTA_PPM_CAP} ppm/C (the"
  echo "  ~0.175% headroom DR-0011's budget carries, over the 98 C span"
  echo "  from the 27 C trim point). Codes {0, 64, 192, 255} on"
  echo "  {typ, bcs, wcs}/3.30 V bound the TC-vs-code sensitivity slope"
  echo "  and its saturation (reported, ungated). NOT a claim against a"
  echo "  different target -- the ratified TC row (< 50 ppm/C) is"
  echo "  unchanged."
  echo "- **Method**: the grid runs as .nodeset-seeded .op points (the"
  echo "  sim/closed-loop-vref-mc technique -- see the experiment README);"
  echo "  the transient fixture (200us ramp, 3ms hold, the #222"
  echo "  settledness convention) is validated per process corner at"
  echo "  code 128/27C/3.30V and must agree with the .op to"
  echo "  <= ${VALIDATE_TOL_V} V -- see the *_tranval_* rows in the parsed CSV."
  echo "- **Devices**: all real PDK compact models; the DUT is the"
  echo "  trim-bearing bandgap_core (R1 base l=37.2u + XXTRIM ladder),"
  echo "  ladder subcircuit copied device-for-device from"
  echo "  design/netlist/bandgap_trim.spice, plus bandgap_amp and"
  echo "  bandgap_startup verbatim."
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
  echo "  + 5 transient validation points = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS. Worst box-method"
  echo "  group across complete groups: ${WORST_BOX}. Worst +/-1-code"
  echo "  trim-induced delta: ${WORST_NEAR};"
  echo "  ${headroom_fail} near-band group(s) FAIL the ${GATE_DELTA_PPM_CAP} ppm/C"
  echo "  headroom gate (see records/${RECORD_ID}-trimdtc.csv)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
    echo "  Groups a failed point shrank are disclosed by n_pass < n_grid"
    echo "  in records/${RECORD_ID}-boxtc.csv; each exclusion is justified"
    echo "  from THIS record's own committed flanking points, never a"
    echo "  scratch re-run."
  fi
  echo "- **Links**:"
  echo "  - Templates: \`testbench/tb_closed_loop_vref_boxtc_trim.spice.tmpl\` (validation transient), \`../trim-coverage/testbench/tb_trim_coverage.spice.tmpl\` (grid .op)"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Box-method TC summary CSV: \`records/${RECORD_ID}-boxtc.csv\`"
  echo "  - Trim-induced TC deltas: \`records/${RECORD_ID}-trimdtc.csv\`"
  echo "  - Trim-domain MC: \`sim/closed-loop-vref-trim-mc/\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
