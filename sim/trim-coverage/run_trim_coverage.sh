#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/trim-coverage/run_trim_coverage.sh
#
# Optional: JOBS=N (default 1) runs the independent per-point ngspice
# processes with bounded N-way concurrency -- wall-clock only, same
# netlists, same logs, same rows, same emission order as sequential.
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values -- see README.md).
#
# Trim-ladder range / resolution / linearity coverage bench (issue #229 --
# AC1 evidence for DR-0011's ratified Trim row: "1-point at 27 C; range
# >= +/-15%; resolution <= 0.25%/step; magnitude only"). Sweeps the REAL
# ladder (design/bandgap_trim.sch, 255 binary-weighted rppd unit segments,
# strap-decoded trim_code) through the closed loop at one .op per (corner,
# supply, code) and verifies, per corner/supply group at the 27 C trim
# temperature: the measured step (code 128 -> 129), the rail-to-rail span
# vs the default code (both directions >= 15% of 1.050 V), exact binary
# group weights (each single-bit code = 2^b LSBs), full-scale linearity
# residual, and monotonicity -- plus the trim step's temperature
# dependence (VT-proportionality check at typ/3.30V, -40/125 C).
#
# Writes append-only evidence under netlist-snapshots/<record-id>/,
# corners/<record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_trim_coverage.spice.tmpl"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

alias_dut_git_shas TRIM=design/netlist/bandgap_trim.spice AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

# The ratified Trim row binds at the 27 C trim temperature -- the primary
# grid is the full 15 corner/supply groups at 27 C. Codes visited per
# group: 0 (base), each single-bit code 1/2/4/.../128 (per-group binary
# weights), 129 (the direct step measurement, one LSB above the schematic
# default), and 255 (full scale, linearity). The three extra temperature
# points (typ/3.30V at -40/125 C, codes 128+129) measure the trim step's
# temperature dependence for the record's VT-proportionality note.
TEMP_TRIM_C=27
CODES=(0 1 2 4 8 16 32 64 128 129 255)
STEP_TEMP_PROBE_CODES=(128 129)
STEP_TEMP_PROBE_TEMPS=(-40 125)

JOBS="${JOBS:-1}"
if [[ "${JOBS}" -lt 1 ]]; then
  echo "run_trim_coverage.sh: JOBS must be >= 1 (got '${JOBS}')." >&2
  exit 3
fi

VREF_TARGET_V="1.050"     # DR-0011: the trim targets 1.050 V, never 1.2 V
RANGE_FLOOR_PCT="15"      # ratified Trim row: range >= +/-15%
RES_CAP_PCT="0.25"        # ratified Trim row: resolution <= 0.25%/step

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,trim_code,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_v,vbeq3_v" > "${CSV_OUT}"

ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/trimcov-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

lookup_seeds() {
  local corner="$1" temp="$2" vdd="$3"
  FB_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
  SNS1_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
  SNS2_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
  VREF_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"
  if [[ -z "${FB_SEED}" || -z "${SNS1_SEED}" || -z "${SNS2_SEED}" || -z "${VREF_SEED}" ]]; then
    echo "run_trim_coverage.sh: no PASS seed row for ${corner}/${temp}C/${vdd}V in ${SEED_CSV} -- run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
    exit 3
  fi
}

# run_one_point CORNER TEMP VDD CODE
run_one_point() {
  local corner="$1" temp="$2" vdd="$3" code="$4"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  local corner_id="${corner}_code${code}_${temp}c_${vdd}v"
  local netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
  local log="${CORNERS_OUT}/${corner_id}.log"

  lookup_seeds "${corner}" "${temp}" "${vdd}"

  common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
  sed \
    "${COMMON_SED_ARGS[@]}" \
    -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
    -e "s|@@MOS_SECTION@@|${mos_section}|g" \
    -e "s|@@RES_SECTION@@|${res_section}|g" \
    -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
    -e "s|@@FB_SEED@@|${FB_SEED}|g" \
    -e "s|@@SNS1_SEED@@|${SNS1_SEED}|g" \
    -e "s|@@SNS2_SEED@@|${SNS2_SEED}|g" \
    -e "s|@@VREF_SEED@@|${VREF_SEED}|g" \
    -e "s|@@TRIM_CODE@@|${code}|g" \
    -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} trim=${DUT_TRIM_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
    "${TEMPLATE}" > "${netlist}"

  ngspice -b "${netlist}" > "${log}" 2>&1 || true

  local rc_ok=1
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|Simulation interrupted" "${log}" 2>/dev/null; then
    rc_ok=0
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
  if [[ "${rc_ok}" -ne 1 ]]; then
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

# The grid: 15 corner/supply groups x 11 codes at 27 C, plus the step's
# temperature probe (typ/3.30V x {-40,125} C x {128,129}).
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    for code in "${CODES[@]}"; do
      GRID+=("${corner}|${TEMP_TRIM_C}|${vdd}|${code}")
    done
  done
done
for temp in "${STEP_TEMP_PROBE_TEMPS[@]}"; do
  for code in "${STEP_TEMP_PROBE_CODES[@]}"; do
    GRID+=("typ|${temp}|3.30|${code}")
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
    echo "${corner}_code${code},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,${code},,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# ------------------------------------------------- Ladder coverage analysis
# Per corner/supply group at 27 C, from THIS run's own PASS rows:
#   lsb      = vref(129) - vref(128)                      (the direct step)
#   up_span  = vref(255) - vref(128)   (max up-correction)
#   down_span= vref(128) - vref(0)     (max down-correction)
#   weight_b = vref(2^b) - vref(0)     (each binary group, b = 0..7)
#   fs_resid = vref(255) - (vref(0) + 255*(vref(1)-vref(0)))  (linearity)
# Gates (README "What this bench claims"):
#   resolution  lsb/1.050 V               <= 0.25%
#   range       up_span/1.050, down_span/1.050 >= 15% each
#   binary      |weight_b - 2^b*unit| <= 0.005*2^b*unit   (unit = vref(1)-vref(0))
#   linearity   |fs_resid|                <= 0.25*lsb
#   monotonic   vref strictly increasing over visited codes
ANALYSIS_OUT="${RECORDS_DIR}/${RECORD_ID}-analysis.csv"
echo "corner_label,vdd_v,group_status,n_pass,n_grid,unit_v,lsb_v,lsb_pct_of_target,up_span_v,up_span_pct,down_span_v,down_span_pct,worst_weight_dev_pct,fs_resid_v,fs_resid_lsb,monotonic" > "${ANALYSIS_OUT}"
group_fail=0
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    read -r n_pass n_grid unit lsb lsb_pct up up_pct down down_pct wdev fsr fsr_lsb mono <<< "$(awk -F, -v c="${corner}_code" -v vdd_in="${vdd}" -v tgt="${VREF_TARGET_V}" '
      $1 ~ "^"c && $6==vdd_in {
        n_grid++
        if ($8=="PASS") { n_pass++; v[$9]=$17; code[n_pass]=$9; seq[$9]=n_pass }
      }
      END {
        unit=""; lsb=""; up=""; down=""; wdev=""; fsr=""; mono="yes"
        if (v[1]!="" && v[255]!="") {
          unit = v[1]-v[0]
          lsb = v[129]-v[128]
          up = v[255]-v[128]
          down = v[128]-v[0]
          worst = 0
          split("1 2 4 8 16 32 64 128", bits, " ")
          for (bi in bits) {
            b = bits[bi]
            if (v[b]!="") {
              dev = (v[b]-v[0]) - b*unit
              rel = (b*unit!=0) ? 100*dev/(b*unit) : 0
              if (rel<0) rel=-rel
              if (rel>worst) worst=rel
            }
          }
          wdev = worst
          fsr = v[255] - (v[0] + 255*unit)
          # Monotonicity over the ASCENDING visit order of the code list
          # (0,1,2,4,...,128,129,255 -- always ascending in code), so a
          # plain walk of that order checks vref strictly increasing; no
          # asort/asorti (gawk-only) to stay BSD-awk compatible.
          split("0 1 2 4 8 16 32 64 128 129 255", order, " ")
          prev = ""
          for (i=1; i<=11; i++) {
            cv = v[order[i]]
            if (cv!="") {
              if (prev!="" && cv<=prev) mono="no"
              prev = cv
            }
          }
          printf "%d %d %.9g %.9g %.6f %.9g %.6f %.9g %.6f %.4f %.9g %.4f %s", n_pass, n_grid, unit, lsb, 100*lsb/tgt, up, 100*up/tgt, down, 100*down/tgt, wdev, fsr, (lsb!=0?fsr/lsb:0), mono
        } else {
          printf "%d %d 0 0 0 0 0 0 0 0 0 0 incomplete", n_pass, n_grid
        }
      }' "${CSV_OUT}")"
    group_status=PASS
    if [[ "${n_pass}" != "${n_grid}" || "${unit}" == "0" || -z "${unit}" ]]; then
      group_status=FAIL
    else
      if awk -v a="${lsb_pct}" -v cap="${RES_CAP_PCT}" 'BEGIN{exit !(a>cap)}'; then group_status=FAIL; fi
      if awk -v a="${up_pct}" -v f="${RANGE_FLOOR_PCT}" 'BEGIN{exit !(a<f)}'; then group_status=FAIL; fi
      if awk -v a="${down_pct}" -v f="${RANGE_FLOOR_PCT}" 'BEGIN{exit !(a<f)}'; then group_status=FAIL; fi
      if awk -v a="${wdev}" 'BEGIN{exit !(a>0.5)}'; then group_status=FAIL; fi
      fsr_lsb_abs="${fsr_lsb#-}"
      if awk -v a="${fsr_lsb_abs}" 'BEGIN{exit !(a>0.25)}'; then group_status=FAIL; fi
      if [[ "${mono}" != "yes" ]]; then group_status=FAIL; fi
    fi
    if [[ "${group_status}" == "FAIL" ]]; then group_fail=$((group_fail+1)); fi
    echo "${corner},${vdd},${group_status},${n_pass},${n_grid},${unit},${lsb},${lsb_pct},${up},${up_pct},${down},${down_pct},${wdev},${fsr},${fsr_lsb},${mono}" >> "${ANALYSIS_OUT}"
  done
done

# Headline numbers for the record: worst resolution / worst span across
# groups, the typ/3.30V default-code vref (equivalence to the pre-trim
# core), and the step's temperature dependence.
WORST_LSB_PCT=$(awk -F, 'NR>1 && $8+0>m {m=$8+0} END{printf "%.4f", m}' "${ANALYSIS_OUT}")
WORST_UP_PCT=$(awk -F, 'NR>1 && $10+0<m {m=$10+0} END{printf "%.4f", m}' "${ANALYSIS_OUT}")
WORST_DOWN_PCT=$(awk -F, 'NR>1 && $12+0<m {m=$12+0} END{printf "%.4f", m}' "${ANALYSIS_OUT}")
TYP_VREF_128=$(awk -F, '$1=="typ_code128" && $5=="27" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
TYP_VREF_129=$(awk -F, '$1=="typ_code129" && $5=="27" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
TYP_VREF_0=$(awk -F, '$1=="typ_code0" && $5=="27" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
TYP_VREF_255=$(awk -F, '$1=="typ_code255" && $5=="27" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
STEP_27=$(awk -v a="${TYP_VREF_128}" -v b="${TYP_VREF_129}" 'BEGIN{printf "%.6f", b-a}')
STEP_N40=$(awk -F, '$1=="typ_code129" && $5=="-40" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
STEP_N40_128=$(awk -F, '$1=="typ_code128" && $5=="-40" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
STEP_125=$(awk -F, '$1=="typ_code129" && $5=="125" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
STEP_125_128=$(awk -F, '$1=="typ_code128" && $5=="125" && $6=="3.30" {print $16; exit}' "${CSV_OUT}")
STEP_N40_V=$(awk -v a="${STEP_N40_128}" -v b="${STEP_N40}" 'BEGIN{printf "%.6f", (a==""||b=="")?"":b-a}')
STEP_125_V=$(awk -v a="${STEP_125_128}" -v b="${STEP_125}" 'BEGIN{printf "%.6f", (a==""||b=="")?"":b-a}')

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: trim-coverage (issue #229)"
  echo "- **Claim**: the committed trim ladder (design/bandgap_trim.sch, 255"
  echo "  binary-weighted rppd unit segments, strap-decoded trim_code, default"
  echo "  128) realizes DR-0011's ratified Trim row at the 27 C trim point"
  echo "  through the real closed loop: resolution <= 0.25%/step (worst"
  echo "  group ${WORST_LSB_PCT}% of the 1.050 V target), range >= +/-15%"
  echo "  (worst up ${WORST_UP_PCT}%, worst down ${WORST_DOWN_PCT}%), exact"
  echo "  binary group weights (worst deviation from 2^b LSBs within 0.5%),"
  echo "  monotonic, and full-scale-linear to within a quarter LSB -- across"
  echo "  the full {typ,bcs,wcs,sf,fs} x {2.97,3.30,3.63} V grid at 27 C."
  echo "  Also: the default code 128 reproduces the pre-trim core's"
  echo "  operating point (typ/27C/3.30V vref = ${TYP_VREF_128} V vs the"
  echo "  committed pre-trim evidence's 1.047338 V -- the R1=511um"
  echo "  single-instance circuit this ladder supersedes), and the trim step"
  echo "  tracks the PTAT loop current (step = ${STEP_27} mV at 27 C,"
  echo "  ${STEP_N40_V} mV at -40 C, ${STEP_125_V} mV at 125 C)."
  echo "- **Devices**: all real PDK compact models; the DUT is the"
  echo "  trim-bearing bandgap_core (R1 base l=37.2u + XXTRIM ladder), the"
  echo "  ladder's subcircuit copied device-for-device from"
  echo "  design/netlist/bandgap_trim.spice, plus bandgap_amp and"
  echo "  bandgap_startup verbatim. No fixture stands in for the servo loop;"
  echo "  the straps are the ladder's own decoded links, not a synthetic"
  echo "  trim source."
  echo "- **Netlist provenance**: schematic (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_trim.spice @ \`${DUT_TRIM_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch specifies."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **JOBS**: ${JOBS} (wall-clock concurrency only)."
  echo "- **Corner matrix run**: ${#CORNER_LABELS[@]} process corners x"
  echo "  ${#VDDS[@]} supplies x ${#CODES[@]} codes at 27 C"
  echo "  + ${#STEP_TEMP_PROBE_TEMPS[@]} step-temperature probes = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed criteria); ${group_fail}/15 corner/supply"
  echo "  groups FAIL the ladder-coverage gates above (see"
  echo "  records/${RECORD_ID}-analysis.csv)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_trim_coverage.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Ladder-coverage analysis: \`records/${RECORD_ID}-analysis.csv\`"
  echo "  - Sizing derivation: \`design/bandgap_trim_network.md\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
