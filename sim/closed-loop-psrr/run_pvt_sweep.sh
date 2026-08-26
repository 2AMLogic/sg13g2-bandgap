#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-psrr/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values -- see README.md "Nodeset
# provenance"; a fresh sim/closed-loop-startup/run_pvt_sweep.sh run is NOT
# required if a committed record already exists, which it does in this repo).
#
# Full testbench rationale and what this sweep does and does not claim:
# sim/closed-loop-psrr/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_psrr.spice.tmpl"
SUMMARY_AWK="${EXPERIMENT_DIR}/tools/psrr_summary.awk"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention every closed-loop experiment in this tree uses.
MSENSE_LINE="$(grep -E '^XMSENSE ' "${REPO_ROOT}/design/netlist/bandgap_startup.spice")"
MSENSE_W="$(echo "${MSENSE_LINE}" | grep -oE 'w=[0-9.]+u' | head -1 | sed -e 's/w=//')"
if [[ -z "${MSENSE_W}" ]]; then
  echo "run_pvt_sweep.sh: could not parse XMSENSE's w= from design/netlist/bandgap_startup.spice" >&2
  exit 3
fi

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
DUT_CORE_GIT_SHA="${DUT_GIT_SHA}"
DUT_AMP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_amp.spice 2>/dev/null || echo unknown)"
DUT_STARTUP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_startup.spice 2>/dev/null || echo unknown)"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,vref_op_v,psrr_dc_db,psrr_min_db,psrr_min_freq_hz,psrr_1khz_db,psrr_100khz_db,psrr_1mhz_db" > "${CSV_OUT}"

# Pass criteria:
#   1. .op converged near its own .nodeset seed (|fb_op - fb_seed| <=
#      OP_MATCH_TOL_V) -- confirms the DC bias this AC analysis linearizes
#      around is the intended closed-loop equilibrium, not the degenerate
#      one (same check sim/loop-gain-phase-margin/ performs -- see README
#      "op landed near its seed").
#   2. The .ac sweep actually produced data (a PSRR curve to report).
# This testbench does NOT gate PASS/FAIL on the PSRR *value* itself -- no
# ratified spec target exists to compare against (#13 still open; see
# README "What this testbench claims, and what it does not"), so a point
# "passing" here means "a trustworthy PSRR measurement was produced",
# not "PSRR met some bar".
OP_MATCH_TOL_V="0.05"

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
      ac_out="${CORNERS_OUT}/${corner_id}.ac.txt"

      fb_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
      sns1_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
      sns2_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
      vref_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"

      if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
        # 11 empty trailing fields: fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,
        # vref_op_v,psrr_dc_db,psrr_min_db,psrr_min_freq_hz,psrr_1khz_db,
        # psrr_100khz_db,psrr_1mhz_db.
        echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id} (no seed in ${SEED_CSV})")
        continue
      fi

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
        -e "s|@@FB_SEED@@|${fb_seed}|g" \
        -e "s|@@SNS1_SEED@@|${sns1_seed}|g" \
        -e "s|@@SNS2_SEED@@|${sns2_seed}|g" \
        -e "s|@@VREF_SEED@@|${vref_seed}|g" \
        -e "s|@@AC_OUT@@|${ac_out}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true`: same rationale as every other run_pvt_sweep.sh in this
      # tree -- a single non-convergent corner must not abort the sweep
      # under `set -euo pipefail`.
      fb_op=$(grep -E '^v\(fb\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      sns1_op=$(grep -E '^v\(sns1\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      sns2_op=$(grep -E '^v\(sns2\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      vref_op=$(grep -E '^v\(vref\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)

      verdict=PASS
      psrr_dc=""
      psrr_min=""
      psrr_min_freq=""
      psrr_1khz=""
      psrr_100khz=""
      psrr_1mhz=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${fb_op}" || ! -s "${ac_out}" ]]; then
        verdict=FAIL
      else
        op_delta=$(awk -v a="${fb_op}" -v b="${fb_seed}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        op_ok=$(awk -v d="${op_delta}" -v tol="${OP_MATCH_TOL_V}" 'BEGIN{print (d<=tol)?1:0}')
        read -r psrr_dc psrr_min psrr_min_freq psrr_1khz psrr_100khz psrr_1mhz < <(awk -f "${SUMMARY_AWK}" "${ac_out}")
        if [[ "${op_ok}" != "1" ]]; then
          verdict=FAIL
        fi
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${fb_seed},${fb_op},${sns1_op},${sns2_op},${vref_op},${psrr_dc},${psrr_min},${psrr_min_freq},${psrr_1khz},${psrr_100khz},${psrr_1mhz}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-psrr"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-startup and sim/closed-loop-vref-pvt use"
  echo "  (bandgap_core + bandgap_amp + bandgap_startup, wired exactly as"
  echo "  design/bandgap_top.sch specifies, real devices throughout, loop"
  echo "  NOT broken), a small-signal AC power-supply-rejection curve is"
  echo "  measured by injecting a 1V/0deg AC perturbation directly on vdd"
  echo "  (Vvdd's own ac term) around a DC operating point seeded via"
  echo "  .nodeset from sim/closed-loop-startup's own most recent"
  echo "  per-corner converged transient endpoint (README \"Nodeset"
  echo "  provenance\") and re-verified per point (README \"op landed near"
  echo "  its seed\"). PSRR(f) = -dB(v(vref)) -- see README \"Sign"
  echo "  convention\" for the derivation of why this is the correct"
  echo "  polarity for THIS testbench's own injection convention (larger"
  echo "  PSRR_dB = better rejection)."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice,"
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice (identical device set to"
  echo "  sim/closed-loop-startup, loop NOT broken) plus the Vvdd AC"
  echo "  injection documented in testbench/ and README.md. No fixture"
  echo "  stands in for any real device -- only the AC stimulus is added,"
  echo "  same discipline as every closed-loop experiment in this tree."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies (no fb split -- the loop stays closed)."
  echo "- **Nodeset seed provenance**: \`${SEED_CSV#"${REPO_ROOT}"/}\`"
  echo "  @ \`${SEED_GIT_SHA}\` (sim/closed-loop-startup's own most recent"
  echo "  committed record) -- see README \"Nodeset provenance\"."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (.op landed within"
  echo "  ${OP_MATCH_TOL_V} V of its own .nodeset seed and the .ac sweep"
  echo "  produced a PSRR curve to measure -- NOT a claim that the"
  echo "  measured PSRR value itself meets any target; see README \"What"
  echo "  this testbench claims, and what it does not\")."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_psrr.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + AC sweep data: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #88."
} > "${MD_OUT}"

write_pvt_summary
