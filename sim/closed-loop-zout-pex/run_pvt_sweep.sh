#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-zout-pex/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values, exactly as
# sim/closed-loop-psrr-pex does -- see README.md "Nodeset provenance").
#
# Does NOT require `klt` to run -- klt was used once, offline (issue #187), to
# produce the committed layout/bandgap_top/bandgap_top.pex.spice this
# testbench re-encodes; see sim/closed-loop-psrr-pex/README.md "Cold-start
# invocation" for how to regenerate that input.
#
# Full testbench rationale and what this sweep does and does not claim:
# sim/closed-loop-zout-pex/README.md. Issue #191 context: this is the
# independent confirmation probe for sim/closed-loop-psrr-pex's own
# 27.1-31.6 MHz worst-case PSRR dip.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

# DUT_NETLIST/DUT_GIT_SHA below stamps the ONE schematic file this bench
# still splices verbatim (XQ1/XQ2/XQ3 -- bipolar devices, not extracted).
# Every MOS/resistor device and every wire parasitic instead comes from the
# layout-extracted layout/bandgap_top/bandgap_top.pex.spice -- its own git
# sha is stamped separately below as LAYOUT_GIT_SHA, matching
# sim/closed-loop-psrr-pex/run_pvt_sweep.sh's convention.
DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_zout_pex.spice.tmpl"
SUMMARY_AWK="${EXPERIMENT_DIR}/tools/zout_summary.awk"
COMMON_AWK="${SIM_DIR}/lib/db_summary_common.awk"

# This bench's every MOS/resistor device carries geometry baked in from the
# extraction at template-authoring time (matching every other *-pex
# experiment in this tree) -- no @@MSENSE_W@@ template token, unlike the
# schematic-level sim/closed-loop-psrr.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice
LAYOUT_GIT_SHA="$(dut_git_sha layout/bandgap_top/bandgap_top.pex.spice)"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,vref_op_v,zout_dc_db,zout_peak_db,zout_peak_freq_hz,zout_1khz_db,zout_100khz_db,zout_1mhz_db" > "${CSV_OUT}"

# Pass criteria -- identical shape to sim/closed-loop-psrr-pex's (see that
# script's own comment for the full rationale):
#   1. .op converged near its own .nodeset seed (|fb_op - fb_seed| <=
#      OP_MATCH_TOL_V).
#   2. The .ac sweep actually produced data.
# This testbench does NOT gate PASS/FAIL on the Zout *value* itself -- no
# spec target exists for closed-loop output impedance at all (this is a
# confirmation probe, not a spec-conformance bench) -- a point "passing"
# here means "a trustworthy Zout(f) measurement was produced", not "Zout met
# some bar".
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
        # vref_op_v,zout_dc_db,zout_peak_db,zout_peak_freq_hz,zout_1khz_db,
        # zout_100khz_db,zout_1mhz_db.
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

      fb_op=$(extract_op_voltage fb "${log}")
      sns1_op=$(extract_op_voltage sns1 "${log}")
      sns2_op=$(extract_op_voltage sns2 "${log}")
      vref_op=$(extract_op_voltage vref "${log}")

      verdict=PASS
      zout_dc=""
      zout_peak=""
      zout_peak_freq=""
      zout_1khz=""
      zout_100khz=""
      zout_1mhz=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${fb_op}" || ! -s "${ac_out}" ]]; then
        verdict=FAIL
      else
        op_delta=$(abs_diff "${fb_op}" "${fb_seed}")
        op_ok=$(awk -v d="${op_delta}" -v tol="${OP_MATCH_TOL_V}" 'BEGIN{print (d<=tol)?1:0}')
        read -r zout_dc zout_peak zout_peak_freq zout_1khz zout_100khz zout_1mhz < <(awk -v extremum=max -f "${COMMON_AWK}" -f "${SUMMARY_AWK}" "${ac_out}")
        if [[ "${op_ok}" != "1" ]]; then
          verdict=FAIL
        fi
      fi

      tally_verdict "${verdict}" "${corner_id}"
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${verdict},${fb_seed},${fb_op},${sns1_op},${sns2_op},${vref_op},${zout_dc},${zout_peak},${zout_peak_freq},${zout_1khz},${zout_100khz},${zout_1mhz}" >> "${CSV_OUT}"
    done
  done
done

# Cross-bench comparison against sim/closed-loop-psrr-pex's own current
# (newest) record -- per-point [zout_peak_freq_hz vs. psrr_min_freq_hz],
# computed here so the record below can report the correlation this
# confirmation probe exists to check directly, rather than requiring a
# follow-up manual pass (same convention sim/closed-loop-psrr-pex's own
# "-vs-schematic.csv" companion established).
PSRR_PEX_RECORDS_DIR="${SIM_DIR}/closed-loop-psrr-pex/records"
PSRR_PEX_CSV="$(latest_records_csv "${PSRR_PEX_RECORDS_DIR}")"
DELTA_OUT="${RECORDS_DIR}/${RECORD_ID}-vs-psrr-pex.csv"
echo "corner_label,temp_c,vdd_v,psrr_min_freq_hz,psrr_min_db,zout_peak_freq_hz,zout_peak_db,freq_ratio_zout_over_psrr,verdict_psrr_pex,verdict_zout_pex" > "${DELTA_OUT}"
if [[ -n "${PSRR_PEX_CSV}" ]]; then
  while IFS=, read -r corner _hbt _mos _res temp vdd pverdict _fbseed _fbop _sns1 _sns2 _vref _pdc pmin pminf _p1k _p100k _p1m; do
    [[ "${corner}" == "corner_label" ]] && continue
    zout_row=$(awk -F, -v c="${corner}" -v t="${temp}" -v v="${vdd}" '$1==c && $5==t && $6==v {print}' "${CSV_OUT}")
    [[ -z "${zout_row}" ]] && continue
    zverdict=$(echo "${zout_row}" | awk -F, '{print $7}')
    zpeak=$(echo "${zout_row}" | awk -F, '{print $14}')
    zpeakf=$(echo "${zout_row}" | awk -F, '{print $15}')
    if [[ -n "${pminf}" && -n "${zpeakf}" ]]; then
      ratio=$(awk -v a="${pminf}" -v b="${zpeakf}" 'BEGIN{if (a+0==0) {print "NA"} else {printf "%.4f", b/a}}')
      echo "${corner},${temp},${vdd},${pminf},${pmin},${zpeakf},${zpeak},${ratio},${pverdict},${zverdict}" >> "${DELTA_OUT}"
    fi
  done < "${PSRR_PEX_CSV}"
fi

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-zout-pex (issue #191 -- independent"
  echo "  confirmation of sim/closed-loop-psrr-pex's 27.1-31.6 MHz"
  echo "  worst-case-PSRR dip)"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-psrr-pex uses (bandgap_core + bandgap_amp +"
  echo "  bandgap_startup, wired exactly as design/bandgap_top.sch"
  echo "  specifies, loop NOT broken, same layout-extracted device/"
  echo "  parasitic block), a small-signal AC closed-loop OUTPUT-IMPEDANCE"
  echo "  curve is measured by injecting a 1A/0deg AC test current directly"
  echo "  at vref (vdd left as a plain, unperturbed DC source -- NOT the"
  echo "  stimulus in this bench) around a DC operating point seeded via"
  echo "  .nodeset from sim/closed-loop-startup's own most recent per-corner"
  echo "  converged transient endpoint and re-verified per point"
  echo "  (|fb_op - fb_seed| <= ${OP_MATCH_TOL_V} V). Zout(f) = v(vref)/"
  echo "  i(Itest), numerically equal to v(vref) in ohms since Itest's AC"
  echo "  magnitude is exactly 1A. This is a DIFFERENT transfer function"
  echo "  than PSRR (different stimulus port entirely) that shares the same"
  echo "  1/(1+T(jw)) return-difference denominator -- see README.md 'Why an"
  echo "  output-impedance probe' for why a peak here at the same frequency"
  echo "  as sim/closed-loop-psrr-pex's own dip is evidence for a genuine"
  echo "  loop resonance rather than a vdd-injection-path artifact."
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
  echo "  benches use (same choice, same rationale, as"
  echo "  sim/closed-loop-psrr-pex)."
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
  echo "  produced a Zout curve to measure -- NOT a claim that the measured"
  echo "  Zout value itself meets any target; no such target exists)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_zout_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + AC sweep data: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Cross-bench comparison vs. closed-loop-psrr-pex: \`records/${RECORD_ID}-vs-psrr-pex.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #191."
  echo
  echo "## Cross-bench comparison vs. sim/closed-loop-psrr-pex (same PEX netlist)"
  echo
  if [[ -n "${PSRR_PEX_CSV}" ]]; then
    echo "PSRR-PEX reference: \`$(basename "${PSRR_PEX_CSV}")\`."
    echo
    echo "Full per-point [psrr_min_freq_hz vs. zout_peak_freq_hz] comparison:"
    echo "\`records/${RECORD_ID}-vs-psrr-pex.csv\`."
  else
    echo "No sim/closed-loop-psrr-pex record found to compare against."
  fi
  echo
  echo "## Zout per PVT point"
  echo
  echo "| corner | temp (C) | vdd (V) | Zout DC (dB-ohm) | peak Zout (dB-ohm) | at (Hz) |"
  echo "|---|---|---|---|---|---|"
  awk -F, 'NR>1 && $7=="PASS" {printf "| %s | %s | %s | %s | %s | %s |\n", $1, $5, $6, $13, $14, $15}' "${CSV_OUT}"
} > "${MD_OUT}"

write_pvt_summary
