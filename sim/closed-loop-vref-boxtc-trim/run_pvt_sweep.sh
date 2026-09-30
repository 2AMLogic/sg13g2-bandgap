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
# Optional: TRIM_CODES="128 64 192" to scope a re-run to a subset of the
# code axis (the record mints a new <record-id>; the full-axis default is
# documented in README.md).
#
# Post-trim box-method temperature-coefficient bench (issue #229 --
# DR-0011's obligated post-trim TC re-measurement: "a post-trim TC
# re-measurement bounding the trim-induced TC degradation (DR-0010's
# +/-0.5% budget carries ~0.17% headroom for it -- an estimate to verify,
# not a measurement)"). Same transient fixture, solver options,
# settledness convention and every .measure as
# sim/closed-loop-vref-pvt-boxtc (issue #222) -- this bench re-points that
# experiment at the trim-bearing core and sweeps the trim code:
#
#   code 128 -- the schematic default (total R1_eff ~= the pre-trim 511 um
#               single instance): the TC-null baseline, expected to
#               reproduce the committed pre-trim box-TC evidence.
#   code 64/192 -- one quarter of the ladder each side of default: the
#               +/-64-code band the trim-domain MC's code* distribution
#               actually lands in (see sim/closed-loop-vref-trim-mc/).
#   code 0/255 -- the rails: the worst-case trim-induced TC the ladder can
#               produce at all, bounding the sensitivity even for dies
#               outside the covered population.
#
# Writes append-only evidence under corners/<record-id>/,
# netlist-snapshots/<record-id>/ and records/<record-id>.{md,csv,-boxtc.csv}
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
TRIM_CODES_STR="${TRIM_CODES:-128 64 192 0 255}"
read -r -a TRIM_CODES <<< "${TRIM_CODES_STR}"
CODE_DEFAULT=128

# The +/-0.5% trimmed budget's headroom for trim-induced TC drift
# (DR-0011's derived table: 0.20% TC drift + 0.125% quantization leaves
# ~0.175%): the claim gate checks the codes the MC's code* population
# actually uses (the +/-64 band) stay inside it over the 98 C span from
# the 27 C trim point to either rail.
TRIM_TC_HEADROOM_PCT="0.175"
TRIM_TC_SPAN_C="98"

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

# The grid: corner x code x temp x vdd (code before temp so all temps of
# one (corner, code) group land adjacently in the CSV).
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${TRIM_CODES[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for vdd in "${VDDS[@]}"; do
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
for corner in "${CORNER_LABELS[@]}"; do
  for code in "${TRIM_CODES[@]}"; do
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

# ------------------------------------------------- Trim-induced TC deltas
# Per (corner, vdd): box TC at each code vs the code-128 baseline, and the
# drift-vs-headroom check over the +/-64-code band (the code* population
# the trim MC actually observes -- cross-referenced in the record prose).
DELT_OUT="${RECORDS_DIR}/${RECORD_ID}-trimdtc.csv"
echo "corner_label,vdd_v,box_tc_128_ppm_c,box_tc_64_ppm_c,box_tc_192_ppm_c,box_tc_0_ppm_c,box_tc_255_ppm_c,worst_band_code,worst_band_dtc_ppm_c,band_drift_pct,headroom_pct,headroom_status" > "${DELT_OUT}"
headroom_fail=0
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    read -r tc128 tc64 tc192 tc0 tc255 <<< "$(awk -F, -v c="${corner}" -v vdd_in="${vdd}" -v o="${BOXT_OUT}" '
      NR>1 && $1 ~ ("^"c"_code") && $3==vdd_in { tc[$2]=$11 }
      END { printf "%.3f %.3f %.3f %.3f %.3f", tc[128], tc[64], tc[192], tc[0], tc[255] }' "${BOXT_OUT}")"
    worst_code="none"; worst_dtc="0"
    if [[ -n "${tc64:-}" || -n "${tc192:-}" ]]; then
      if awk -v a="${tc64:-0}" -v b="${tc192:-0}" 'BEGIN{exit !(a>=b)}'; then
        worst_code=64; worst_dtc=$(awk -v a="${tc64:-0}" -v b="${tc128:-0}" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.3f", d}')
      else
        worst_code=192; worst_dtc=$(awk -v a="${tc192:-0}" -v b="${tc128:-0}" 'BEGIN{d=a-b; if(d<0)d=-d; printf "%.3f", d}')
      fi
    fi
    band_pct=$(awk -v dtc="${worst_dtc}" -v span="${TRIM_TC_SPAN_C}" 'BEGIN{printf "%.4f", 1e-4*dtc*span}')
    hs=OK
    if awk -v a="${band_pct}" -v b="${TRIM_TC_HEADROOM_PCT}" 'BEGIN{exit !(a>b)}'; then
      hs=FAIL
      headroom_fail=$((headroom_fail+1))
    fi
    echo "${corner},${vdd},${tc128:-},${tc64:-},${tc192:-},${tc0:-},${tc255:-},${worst_code},${worst_dtc},${band_pct},${TRIM_TC_HEADROOM_PCT},${hs}" >> "${DELT_OUT}"
  done
done

WORST_BOX=$(awk -F, 'NR>1 && $4==$5 && $11+0 > m { m = $11+0; line = $1"/"$3"V = "sprintf("%.1f", $11)" ppm/C" } END { print line }' "${BOXT_OUT}")
WORST_BAND=$(awk -F, 'NR>1 && $10+0 > m { m=$10+0; line = $1"/"$2"V @code"$8" = +"sprintf("%.1f", $9)" ppm/C vs code-128 ("$10"% of 1.050V over 98C)" } END { print line }' "${DELT_OUT}")

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-boxtc-trim (issue #229)"
  echo "- **Claim**: the post-trim box-method TC re-measurement DR-0011's"
  echo "  +/-0.5% trimmed budget obligates: through the same closed-loop"
  echo "  transient fixture as sim/closed-loop-vref-pvt-boxtc (issue #222),"
  echo "  on the trim-bearing core, vref's box TC is measured on the same"
  echo "  8-temperature grid at trim codes {128 (default/baseline),"
  echo "  64, 192 (the +/-64-code band the trim-domain MC's code*"
  echo "  population lands in), 0, 255 (the rails)}. The record bounds the"
  echo "  trim-induced TC degradation (box TC at band codes minus the"
  echo "  code-128 baseline) against the ~0.175% headroom DR-0011's budget"
  echo "  table carries for it over the 98 C span from the 27 C trim point."
  echo "  NOT a claim against a different target -- the ratified TC row"
  echo "  (< 50 ppm/C target) is unchanged."
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
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} x"
  echo "  trim code {${TRIM_CODES_STR}} x temperature"
  echo "  {-40, -20, 0, 27, 50, 75, 100, 125} C x supply {2.97, 3.30, 3.63} V"
  echo "  = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed AND settledness criteria above). Worst"
  echo "  box-method group across complete groups: ${WORST_BOX}."
  echo "  Worst +/-64-band trim-induced TC: ${WORST_BAND};"
  echo "  ${headroom_fail}/15 groups FAIL the 0.175%-headroom gate"
  echo "  (see records/${RECORD_ID}-trimdtc.csv)."
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
