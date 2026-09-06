#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-psrr-pex/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values, exactly as sim/closed-loop-psrr
# does -- see README.md "Nodeset provenance").
#
# Does NOT require `klt` to run -- klt was used once, offline (issue #187), to
# produce the committed layout/bandgap_top/bandgap_top.pex.spice this
# testbench re-encodes; see README.md "Cold-start invocation" for how to
# regenerate that input.
#
# Full testbench rationale and what this sweep does and does not claim:
# sim/closed-loop-psrr-pex/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

# DUT_NETLIST/DUT_GIT_SHA below stamps the ONE schematic file this bench
# still splices verbatim (XQ1/XQ2/XQ3 -- bipolar devices, not extracted).
# Every MOS/resistor device and every wire parasitic instead comes from the
# layout-extracted layout/bandgap_top/bandgap_top.pex.spice -- its own git
# sha is stamped separately below as LAYOUT_GIT_SHA, matching
# sim/closed-loop-vref-pvt-pex/run_pvt_sweep.sh's convention.
DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_psrr_pex.spice.tmpl"
# Deliberately the SIBLING experiment's summariser, not a copy: this bench's
# whole point is a like-for-like comparison against sim/closed-loop-psrr, and
# two copies of the DC/min/interpolation logic could silently drift apart and
# make that comparison meaningless. Same reason sim/lib/*.sh exists.
SUMMARY_AWK="${SIM_DIR}/closed-loop-psrr/tools/psrr_summary.awk"
COMMON_AWK="${SIM_DIR}/lib/db_summary_common.awk"

# This bench's every MOS/resistor device carries geometry baked in from the
# extraction at template-authoring time (matching every other *-pex
# experiment in this tree) -- no @@MSENSE_W@@ template token, unlike the
# schematic-level sim/closed-loop-psrr.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice
LAYOUT_GIT_SHA="$(dut_git_sha layout/bandgap_top/bandgap_top.pex.spice)"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,vref_op_v,psrr_dc_db,psrr_min_db,psrr_min_freq_hz,psrr_1khz_db,psrr_100khz_db,psrr_1mhz_db" > "${CSV_OUT}"

# Pass criteria -- identical to sim/closed-loop-psrr's (see that script's own
# comment for the full rationale):
#   1. .op converged near its own .nodeset seed (|fb_op - fb_seed| <=
#      OP_MATCH_TOL_V).
#   2. The .ac sweep actually produced data.
# This testbench does NOT gate PASS/FAIL on the PSRR *value* itself -- no
# ratified spec target exists to compare against (#125 still open), so a
# point "passing" here means "a trustworthy PSRR measurement was produced",
# not "PSRR met some bar".
OP_MATCH_TOL_V="0.05"

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"
      ac_out="${CORNERS_OUT}/${corner_id}.ac.txt"

      fb_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
      sns1_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
      sns2_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
      vref_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"

      if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
        # 11 empty trailing fields: fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,
        # vref_op_v,psrr_dc_db,psrr_min_db,psrr_min_freq_hz,psrr_1khz_db,
        # psrr_100khz_db,psrr_1mhz_db.
        echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id} (no seed in ${SEED_CSV})")
        continue
      fi

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@FB_SEED@@|${fb_seed}|g" \
        -e "s|@@SNS1_SEED@@|${sns1_seed}|g" \
        -e "s|@@SNS2_SEED@@|${sns2_seed}|g" \
        -e "s|@@VREF_SEED@@|${vref_seed}|g" \
        -e "s|@@AC_OUT@@|${ac_out}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
        -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
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
        read -r psrr_dc psrr_min psrr_min_freq psrr_1khz psrr_100khz psrr_1mhz < <(awk -v extremum=min -f "${COMMON_AWK}" -f "${SUMMARY_AWK}" "${ac_out}")
        if [[ "${op_ok}" != "1" ]]; then
          verdict=FAIL
        fi
      fi

      tally_verdict "${verdict}" "${corner_id}"
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${verdict},${fb_seed},${fb_op},${sns1_op},${sns2_op},${vref_op},${psrr_dc},${psrr_min},${psrr_min_freq},${psrr_1khz},${psrr_100khz},${psrr_1mhz}" >> "${CSV_OUT}"
    done
  done
done

# Cross-bench comparison against sim/closed-loop-psrr's own current (newest)
# record -- per-point ΔPSRR(DC) and ΔPSRR(worst-case), computed here so the
# record below can report it directly rather than requiring a follow-up
# manual pass (same convention sim/closed-loop-vref-pvt-pex established).
SCHEMATIC_RECORDS_DIR="${SIM_DIR}/closed-loop-psrr/records"
SCHEMATIC_CSV="$(find "${SCHEMATIC_RECORDS_DIR}" -maxdepth 1 -name '*.csv' 2>/dev/null | sort | tail -1 || true)"
DELTA_OUT="${RECORDS_DIR}/${RECORD_ID}-vs-schematic.csv"
echo "corner_label,temp_c,vdd_v,psrr_dc_schematic_db,psrr_dc_pex_db,delta_psrr_dc_db,psrr_min_schematic_db,psrr_min_pex_db,delta_psrr_min_db,verdict_schematic,verdict_pex" > "${DELTA_OUT}"
max_abs_dc_delta="0"
max_abs_dc_delta_point=""
max_abs_min_delta="0"
max_abs_min_delta_point=""
if [[ -n "${SCHEMATIC_CSV}" ]]; then
  while IFS=, read -r corner _hbt _mos _res temp vdd _msense sverdict _fbseed _fbop _sns1 _sns2 _vref sdc smin _sminf _s1k _s100k _s1m; do
    [[ "${corner}" == "corner_label" ]] && continue
    pex_row=$(awk -F, -v c="${corner}" -v t="${temp}" -v v="${vdd}" '$1==c && $5==t && $6==v {print}' "${CSV_OUT}")
    [[ -z "${pex_row}" ]] && continue
    pverdict=$(echo "${pex_row}" | awk -F, '{print $7}')
    pdc=$(echo "${pex_row}" | awk -F, '{print $13}')
    pmin=$(echo "${pex_row}" | awk -F, '{print $14}')
    if [[ -n "${sdc}" && -n "${pdc}" && -n "${smin}" && -n "${pmin}" ]]; then
      ddc=$(awk -v a="${sdc}" -v b="${pdc}" 'BEGIN{printf "%.4f", b-a}')
      dmin=$(awk -v a="${smin}" -v b="${pmin}" 'BEGIN{printf "%.4f", b-a}')
      echo "${corner},${temp},${vdd},${sdc},${pdc},${ddc},${smin},${pmin},${dmin},${sverdict},${pverdict}" >> "${DELTA_OUT}"
      absdc=$(awk -v d="${ddc}" 'BEGIN{print (d<0)?-d:d}')
      absmin=$(awk -v d="${dmin}" 'BEGIN{print (d<0)?-d:d}')
      if [[ "$(awk -v a="${absdc}" -v b="${max_abs_dc_delta}" 'BEGIN{print (a>b)?1:0}')" == "1" ]]; then
        max_abs_dc_delta="${absdc}"
        max_abs_dc_delta_point="${corner}_${temp}c_${vdd}v"
      fi
      if [[ "$(awk -v a="${absmin}" -v b="${max_abs_min_delta}" 'BEGIN{print (a>b)?1:0}')" == "1" ]]; then
        max_abs_min_delta="${absmin}"
        max_abs_min_delta_point="${corner}_${temp}c_${vdd}v"
      fi
    fi
  done < "${SCHEMATIC_CSV}"
fi

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-psrr-pex (T1 tracker #4 item 7)"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-psrr uses (bandgap_core + bandgap_amp +"
  echo "  bandgap_startup, wired exactly as design/bandgap_top.sch"
  echo "  specifies, loop NOT broken), a small-signal AC power-supply-"
  echo "  rejection curve is measured by injecting a 1V/0deg AC"
  echo "  perturbation on vdd around a DC operating point seeded via"
  echo "  .nodeset from sim/closed-loop-startup's own most recent per-corner"
  echo "  converged transient endpoint and re-verified per point"
  echo "  (|fb_op - fb_seed| <= ${OP_MATCH_TOL_V} V) -- but with every"
  echo "  MOS/resistor device's geometry AND the block's real wire"
  echo "  parasitics taken from \`klt extract --deck sg13g2 --parasitics\`"
  echo "  against the routed, ASSEMBLED \`layout/bandgap_top/bandgap_top.gds\`"
  echo "  instead of the schematic's as-drawn defaults. PSRR(f) ="
  echo "  -dB(v(vref)), same sign convention sim/closed-loop-psrr derives"
  echo "  (larger PSRR_dB = better rejection). This is post-layout (PEX)"
  echo "  evidence for T1 tracker #4 item 7's post-layout-simulation bar."
  echo "  NOT a claim against spec/porting-plan.md Sec 6's still-unratified"
  echo "  \`PSRR @ DC > 60 dB\` draft target row (#125) -- and NOT a claim"
  echo "  that the measured PSRR meets any bar; a PASS here means a"
  echo "  trustworthy measurement was produced at a verified closed-loop"
  echo "  operating point."
  echo "- **Devices**: XM1/XM2A/XM2B/XM3A/XM3B/XM3C/XR1/XR2 (bandgap_core),"
  echo "  XMTAIL/XMP1-4/XMN1-4 (bandgap_amp), XRPU/XMSENSE/XMKFB"
  echo "  (bandgap_startup) -- all 17 MOS + 3 resistor devices extracted"
  echo "  from \`layout/bandgap_top/bandgap_top.pex.spice\` (layout git sha"
  echo "  \`${LAYOUT_GIT_SHA}\`), instance-for-instance matching"
  echo "  design/netlist/bandgap_core.spice, bandgap_amp.spice and"
  echo "  bandgap_startup.spice (same models, same nominal w/l/ng/m -- the"
  echo "  extraction only adds as/ad/ps/pd). XQ1/XQ2/XQ3 (npn13G2) are NOT"
  echo "  extracted -- klt's sg13g2 deck still does not recognise bipolar"
  echo "  devices -- spliced verbatim from"
  echo "  \`design/netlist/bandgap_core.spice\` (schematic git sha"
  echo "  \`${DUT_CORE_GIT_SHA}\`), wired to the extraction's own real net"
  echo "  names. See README.md for the full account, including why this"
  echo "  bench ties the extracted ground capacitances' far plate (vsubs)"
  echo "  to vss rather than through the 1 TOhm DC tie the transient PEX"
  echo "  benches use."
  echo "- **Netlist provenance**: layout"
  echo "  (\`layout/bandgap_top/bandgap_top.pex.spice\` @ \`${LAYOUT_GIT_SHA}\`)"
  echo "  for every MOS/resistor device and every wire parasitic; schematic"
  echo "  (\`design/netlist/bandgap_core.spice\` @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  \`design/netlist/bandgap_amp.spice\` @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  \`design/netlist/bandgap_startup.spice\` @ \`${DUT_STARTUP_GIT_SHA}\`)"
  echo "  for XQ1/XQ2/XQ3 only."
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
  echo "  produced a PSRR curve to measure -- NOT a claim that the measured"
  echo "  PSRR value itself meets any target)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_psrr_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + AC sweep data: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Cross-bench delta vs. schematic: \`records/${RECORD_ID}-vs-schematic.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), T1 tracker #4 item 7."
  echo
  echo "## Cross-bench comparison vs. sim/closed-loop-psrr (schematic-level)"
  echo
  if [[ -n "${SCHEMATIC_CSV}" ]]; then
    echo "Schematic-level reference: \`$(basename "${SCHEMATIC_CSV}")\`."
    echo
    echo "**Max |ΔPSRR(DC)| across all compared points: ${max_abs_dc_delta} dB**"
    if [[ -n "${max_abs_dc_delta_point}" ]]; then
      echo "(at \`${max_abs_dc_delta_point}\`)."
    fi
    echo
    echo "**Max |ΔPSRR(worst-case)| across all compared points: ${max_abs_min_delta} dB**"
    if [[ -n "${max_abs_min_delta_point}" ]]; then
      echo "(at \`${max_abs_min_delta_point}\`)."
    fi
    echo
    echo "Full per-point comparison: \`records/${RECORD_ID}-vs-schematic.csv\`."
  else
    echo "No sim/closed-loop-psrr record found to compare against."
  fi
  echo
  echo "## PSRR per PVT point"
  echo
  echo "| corner | temp (C) | vdd (V) | PSRR DC (dB) | worst PSRR (dB) | at (Hz) |"
  echo "|---|---|---|---|---|---|"
  awk -F, 'NR>1 && $7=="PASS" {printf "| %s | %s | %s | %s | %s | %s |\n", $1, $5, $6, $13, $14, $15}' "${CSV_OUT}"
} > "${MD_OUT}"

write_pvt_summary
