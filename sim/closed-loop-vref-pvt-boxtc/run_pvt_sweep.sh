#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-pvt-boxtc/run_pvt_sweep.sh
#
# Optional: JOBS=N (default 1) runs the 120 independent per-point ngspice
# processes with bounded N-way concurrency. This only affects wall-clock
# time -- same netlists, same logs, same rows, same emission order as the
# sequential default (per-point results land in per-point files and are
# appended to the CSV in grid order after every point settles), the same
# contract sim/closed-loop-vref-mc's own --parallel flag established.
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/closed-loop-vref-pvt-boxtc/README.md.
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

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_boxtc.spice.tmpl"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

# THIS EXPERIMENT'S REASON TO EXIST -- the fine temperature grid. The
# official 3-point endpoint grid (sim/lib/pvt_preflight.sh's default
# TEMPS=(-40 27 125)) understates TC once the R1=511um retune nulls the
# first-order slope and vref(T) bows through an interior extremum
# (measurements/2026-08-tc-retune README Sec 4b). This sweep re-samples
# the SAME netlist at the 8 temperatures that scratch analysis used
# (-40/-20/0/27/50/75/100/125 C) so the box method
# ((vmax-vmin)/(vref(27C)*165)) reads the curve's true sampled extrema.
TEMPS=(-40 -20 0 27 50 75 100 125)
TEMP_SPAN_C=165

# JOBS: bounded concurrency over independent single-point ngspice batch
# processes (default 1 = fully sequential, byte-identical to every other
# run_pvt_sweep.sh in this tree). Wall-clock-only knob -- see header.
JOBS="${JOBS:-1}"
if [[ "${JOBS}" -lt 1 ]]; then
  echo "run_pvt_sweep.sh: JOBS must be >= 1 (got '${JOBS}')." >&2
  exit 3
fi

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_2ms_v,vref_3ms_v,vref_settle_delta_v,vbeq3_2ms_v,vbeq3_3ms_v" > "${CSV_OUT}"

# Same pass criteria as sim/closed-loop-vref-pvt (startup-release,
# loop-closure, not-railed AND vref-settled within 1 mV between t=2ms and
# t=3ms) -- see that script's own comment for the full rationale. A point
# that fails any criterion contributes no vref to the box, exactly as a
# failed point contributes no endpoint to the official TC there.
SETTLE_TOL_V="0.001"

# Column indices into this experiment's own CSV (differs from the -pex
# sibling only in the msense_w column this schematic bench carries).
VREF_3MS_COL=16
STATUS_COL=8

# Per-point scratch rows: each point writes its own CSV line + verdict to
# ROWS_DIR/<corner_id>.{row,verdict}; the driver below appends them to the
# real CSV in grid order once every point has settled, so JOBS>1 and
# JOBS=1 emit byte-identical records. Lives under TMPDIR (working-set
# contract), never under this experiment's append-only evidence dirs.
ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/boxtc-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

# run_one_point CORNER TEMP VDD
#   Renders one netlist, runs one ngspice batch, extracts the same
#   measures sim/closed-loop-vref-pvt extracts, computes the same verdict,
#   and writes this point's CSV row + verdict to ROWS_DIR. Never exits
#   non-zero: an internal failure leaves the row/verdict files absent,
#   which the driver records as this point's verdict = FAIL (matching how
#   extract_measure()'s non-convergent-corner fallback resolves to empty
#   strings -> FAIL downstream).
run_one_point() {
  local corner="$1" temp="$2" vdd="$3"
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  next_corner_id "${corner}" "${temp}" "${vdd}"

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

  printf '%s\n' "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_2ms},${vref_3ms},${settle_delta},${vbeq3_2ms},${vbeq3_3ms}" > "${ROWS_DIR}/${corner_id}.row"
  printf '%s\n' "${verdict}" > "${ROWS_DIR}/${corner_id}.verdict"
}

# The grid, in deterministic emission order (corner x temp x vdd).
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      GRID+=("${corner}|${temp}|${vdd}")
    done
  done
done

for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd <<<"${point}"
  if [[ "${JOBS}" -le 1 ]]; then
    run_one_point "${corner}" "${temp}" "${vdd}"
  else
    while [[ "$(jobs -rp | wc -l)" -ge "${JOBS}" ]]; do
      sleep 2
    done
    run_one_point "${corner}" "${temp}" "${vdd}" &
  fi
done
if [[ "${JOBS}" -gt 1 ]]; then
  wait || true
fi

# Ordered emission + tally. total is the grid size (next_corner_id's own
# counter ran in subshells under JOBS>1, so it is recomputed here rather
# than trusted); passed/failed_points come from the per-point verdict
# files, in grid order.
total=0
passed=0
failed_points=()
for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd <<<"${point}"
  corner_id="${corner}_${temp}c_${vdd}v"
  total=$((total + 1))
  if [[ -f "${ROWS_DIR}/${corner_id}.row" ]]; then
    cat "${ROWS_DIR}/${corner_id}.row" >> "${CSV_OUT}"
    verdict="$(cat "${ROWS_DIR}/${corner_id}.verdict")"
  else
    # The point's own subshell died before writing its row -- record it
    # as a FAIL with empty measurements, never silently drop a grid point.
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# Box-method TC per (corner_label, vdd) group -- this experiment's claim.
#   box_tc_ppm_per_c = 1e6 * (vmax - vmin) / (165 * vref(27C))
# over the group's PASS points' settled vref (vref_3ms), with vmin/vmax's
# grid temperatures recorded so the record can name where the sampled
# extrema sit. endpoint_tc_ppm_per_c repeats the official 3-point formula
# (1e6*(vref(125C)-vref(-40C))/(165*vref(27C))) on this same run's data so
# the two methods read side-by-side from one committed record.
# n_pass/n_grid disclose any group a non-converged point shrank -- the
# record's prose below justifies every such exclusion from THIS run's own
# committed neighbors (issue #222 AC 3), never from a scratch re-run.
BOXT_OUT="${RECORDS_DIR}/${RECORD_ID}-boxtc.csv"
echo "corner_label,vdd_v,n_pass,n_grid,vmin_v,vmin_temp_c,vmax_v,vmax_temp_c,vref_27c_v,box_tc_ppm_per_c,endpoint_tc_ppm_per_c" > "${BOXT_OUT}"
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    awk -F, -v c="${corner}" -v vdd_in="${vdd}" -v vcol="${VREF_3MS_COL}" -v scol="${STATUS_COL}" \
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
          line = sprintf("%s,%s,%d,%d,%.5g,%d,%.5g,%d,%.5g,%.3f", c, vdd_in, n_pass, n_grid, vmin, tmin, vmax, tmax, v27, box)
          if (vn40 != "" && v125 != "")
            line = line sprintf(",%.3f", 1e6 * (v125 - vn40) / (span * v27))
          else
            line = line ","
          print line >> out
        }
      }' "${CSV_OUT}"
  done
done

# Worst box-method corner across all complete groups (max box_tc where
# n_pass == n_grid), for the record's headline line.
WORST_BOX=$(awk -F, 'NR>1 && $3==$4 && $10+0 > m { m = $10+0; line = $1"/"$2"V = "sprintf("%.1f", $10)" ppm/C (vmin "$5" @"$6"C, vmax "$7" @"$8"C)" } END { print line }' "${BOXT_OUT}")

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-pvt-boxtc (issue #222)"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology and"
  echo "  the SAME per-point netlist sim/closed-loop-vref-pvt uses (device"
  echo "  set, fixture, solver options and every .measure identical -- see"
  echo "  that experiment's template; only the temperature grid differs),"
  echo "  vref's box-method temperature coefficient across the full"
  echo "  corner x supply grid on a temperature grid fine enough to sample"
  echo "  the interior extremum the post-retune vref(T) bows through:"
  echo "  box_tc = (vmax - vmin)/(vref(27C)*${TEMP_SPAN_C}C) over the 8-point"
  echo "  grid {-40,-20,0,27,50,75,100,125} C"
  echo "  (measurements/2026-08-tc-retune README Sec 4b's grid, now a"
  echo "  committed testbench per that section's own follow-up note)."
  echo "  Endpoint-method TC is computed on the same run for side-by-side"
  echo "  comparison. This closes the evidence gap issue #222 files: the"
  echo "  stretch column's box-method status no longer rests on a scratch"
  echo "  harness. NOT a claim against a different target -- the ratified"
  echo "  TC row (README.md, DR 0007/0008) is unchanged by this record."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, same convention"
  echo "  sim/closed-loop-vref-pvt uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice, "
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice -- identical device set to"
  echo "  sim/closed-loop-vref-pvt. No fixture stands in for the servo"
  echo "  loop."
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
  echo "- **JOBS**: ${JOBS} (wall-clock concurrency only -- see run_pvt_sweep.sh"
  echo "  header; results and emission order are identical to the sequential"
  echo "  default)."
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature"
  echo "  {-40, -20, 0, 27, 50, 75, 100, 125} C x supply {2.97, 3.30, 3.63} V"
  echo "  = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed AND settledness criteria above)."
  echo "  Worst box-method corner across complete groups:"
  echo "  ${WORST_BOX}."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
    echo "  Box-method groups a failed point shrank are disclosed by"
    echo "  n_pass < n_grid in records/${RECORD_ID}-boxtc.csv; each such"
    echo "  exclusion is justified from THIS record's own committed"
    echo "  flanking points (see the experiment README's 'Non-converged"
    echo "  points' section for the bounding argument), never from a"
    echo "  scratch re-run -- issue #222 AC 3."
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_vref_boxtc.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Box-method TC summary CSV: \`records/${RECORD_ID}-boxtc.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
