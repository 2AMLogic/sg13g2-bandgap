#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-pvt-pex-boxtc/run_pvt_sweep.sh
#
# Optional: JOBS=N (default 1) runs the 120 independent per-point ngspice
# processes with bounded N-way concurrency. This only affects wall-clock
# time -- same netlists, same logs, same rows, same emission order as the
# sequential default (per-point results land in per-point files and are
# appended to the CSV in grid order after every point settles), the same
# contract sim/closed-loop-vref-mc's own --parallel flag established.
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Does NOT require `klt` to run -- klt was used once, offline, to
# produce the committed layout/bandgap_top/bandgap_top.pex.spice this
# testbench re-encodes (see README.md "Cold-start invocation" for how to
# regenerate that input). Full testbench rationale and what this sweep
# does and does not claim: sim/closed-loop-vref-pvt-pex-boxtc/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

# DUT_NETLIST/DUT_GIT_SHA below stamps the ONE schematic file this bench
# still splices verbatim (XQ1/XQ2/XQ3 -- bipolar devices, not extracted),
# matching sim/closed-loop-vref-pvt-pex's own convention.
DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_pex_boxtc.spice.tmpl"

alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice
LAYOUT_GIT_SHA="$(dut_git_sha layout/bandgap_top/bandgap_top.pex.spice)"

# THIS EXPERIMENT'S REASON TO EXIST -- the fine temperature grid, same
# rationale as sim/closed-loop-vref-pvt-boxtc (the schematic-level
# sibling): the official 3-point endpoint grid understates TC once the
# R1=511um retune nulls the first-order slope and vref(T) bows through an
# interior extremum, and the only box-method numbers that existed before
# this bench were pre-layout and scratch-harness. This sweep samples the
# SAME post-layout netlist at 8 temperatures
# (-40/-20/0/27/50/75/100/125 C) so the box method
# ((vmax-vmin)/(vref(27C)*165)) reads the curve's true sampled extrema at
# the post-layout level issue #222's ratified-row claim needs.
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

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_2ms_v,vref_3ms_v,vref_settle_delta_v,vbeq3_2ms_v,vbeq3_3ms_v" > "${CSV_OUT}"

# Same pass criteria as sim/closed-loop-vref-pvt-pex -- see that
# script's own comment for the full rationale.
SETTLE_TOL_V="0.001"

# Column indices into this experiment's own CSV (no msense_w column --
# every MOS/resistor device here carries extraction-baked geometry, same
# as the official PEX bench).
VREF_3MS_COL=15
STATUS_COL=7

# Per-point scratch rows -- same mechanism as
# sim/closed-loop-vref-pvt-boxtc (see that script's comment).
ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/boxtc-pex-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

# run_one_point CORNER TEMP VDD -- same never-exit-nonzero contract as
# sim/closed-loop-vref-pvt-boxtc's own function (an internal failure
# leaves the row/verdict files absent -> the driver records FAIL).
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
    -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
    -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
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

  printf '%s\n' "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_2ms},${vref_3ms},${settle_delta},${vbeq3_2ms},${vbeq3_3ms}" > "${ROWS_DIR}/${corner_id}.row"
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

# Ordered emission + tally -- same mechanism as
# sim/closed-loop-vref-pvt-boxtc (see that script's comment).
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
    echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# Box-method TC per (corner_label, vdd) group -- same formula, disclosure
# and justification policy as sim/closed-loop-vref-pvt-boxtc (see that
# script's own comment block).
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

# Cross-bench comparison against sim/closed-loop-vref-pvt-boxtc's own
# current (newest) box-method record -- per-group schematic-vs-PEX box TC,
# so the post-layout delta of THE METRIC THIS EXPERIMENT MEASURES reads
# directly from committed records (same intent as
# sim/closed-loop-vref-pvt-pex's own -vs-schematic.csv, one level up).
SCHEMATIC_BOXT_DIR="${SIM_DIR}/closed-loop-vref-pvt-boxtc/records"
# The schematic sibling's newest box-method summary -- deliberately NOT
# latest_records_csv(): that helper picks the newest *.csv EXCLUDING a
# summary pattern (its parent-experiment callers want the per-point CSV);
# here the summary itself is the file being compared, so select it
# directly, newest by the same filename-sort convention.
SCHEMATIC_BOXT="$(find "${SCHEMATIC_BOXT_DIR}" -maxdepth 1 -name '*-boxtc.csv' 2>/dev/null | sort | tail -1 || true)"
DELTA_OUT="${RECORDS_DIR}/${RECORD_ID}-vs-schematic-boxtc.csv"
echo "corner_label,vdd_v,box_tc_schematic_ppm_per_c,box_tc_pex_ppm_per_c,delta_ppm_per_c" > "${DELTA_OUT}"
if [[ -n "${SCHEMATIC_BOXT}" ]]; then
  while IFS=, read -r scorner svdd _np _ng _vmin _tmn _vmax _tmx _v27 sbox _sendpt; do
    [[ "${scorner}" == "corner_label" ]] && continue
    prow=$(awk -F, -v c="${scorner}" -v v="${svdd}" '$1==c && $2==v {print $10}' "${BOXT_OUT}")
    if [[ -n "${sbox}" && -n "${prow}" ]]; then
      delta=$(awk -v a="${sbox}" -v b="${prow}" 'BEGIN{printf "%.3f", b-a}')
      echo "${scorner},${svdd},${sbox},${prow},${delta}" >> "${DELTA_OUT}"
    fi
  done < "${SCHEMATIC_BOXT}"
fi

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-pvt-pex-boxtc (issue #222)"
  echo "- **Claim**: through the SAME co-simulated closed-loop post-layout"
  echo "  topology and the SAME per-point netlist sim/closed-loop-vref-pvt-pex"
  echo "  uses (extraction provenance, device set, wire-parasitic network,"
  echo "  fixture, solver options and every .measure identical -- see that"
  echo "  experiment's template; only the temperature grid differs), vref's"
  echo "  box-method temperature coefficient across the full corner x"
  echo "  supply grid on the 8-point temperature grid"
  echo "  {-40,-20,0,27,50,75,100,125} C:"
  echo "  box_tc = (vmax - vmin)/(vref(27C)*${TEMP_SPAN_C}C). The box method"
  echo "  reads the interior extremum the endpoint method averages away;"
  echo "  before this bench the only box-method numbers in the repo were"
  echo "  pre-layout and scratch-harness (issue #222's PEX-level gap -- the"
  echo "  ratified TC row is claimed at both levels). Endpoint-method TC is"
  echo "  computed on the same run for side-by-side comparison, and"
  echo "  records/${RECORD_ID}-vs-schematic-boxtc.csv diffs every group's"
  echo "  box TC against sim/closed-loop-vref-pvt-boxtc's own current"
  echo "  record. NOT a claim against a different target -- the ratified TC"
  echo "  row (README.md, DR 0007/0008) is unchanged by this record."
  echo "- **Devices**: XM1/XM2A/XM2B/XM3A/XM3B/XM3C/XR1/XR2 (bandgap_core),"
  echo "  XMTAIL/XMP1-4/XMN1-4 (bandgap_amp), XRPU/XMSENSE/XMKFB"
  echo "  (bandgap_startup) -- all 17 MOS + 3 resistor devices extracted"
  echo "  from \`layout/bandgap_top/bandgap_top.pex.spice\` (layout git sha"
  echo "  \`${LAYOUT_GIT_SHA}\`), instance-for-instance matching"
  echo "  design/netlist/bandgap_core.spice, bandgap_amp.spice and"
  echo "  bandgap_startup.spice. XQ1/XQ2/XQ3 (npn13G2) are NOT extracted"
  echo "  (klt's sg13g2 deck does not recognise bipolar devices) -- spliced"
  echo "  verbatim from \`design/netlist/bandgap_core.spice\` (schematic git"
  echo "  sha \`${DUT_CORE_GIT_SHA}\`). Identical device set to"
  echo "  sim/closed-loop-vref-pvt-pex -- see that experiment's README for"
  echo "  the full account, including the three merged-net-label pins."
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
  echo "  - Template: \`testbench/tb_closed_loop_vref_pex_boxtc.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Box-method TC summary CSV: \`records/${RECORD_ID}-boxtc.csv\`"
  echo "  - Schematic-vs-PEX box TC comparison:"
  echo "    \`records/${RECORD_ID}-vs-schematic-boxtc.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
