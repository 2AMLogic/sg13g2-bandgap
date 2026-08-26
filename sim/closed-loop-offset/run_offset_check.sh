#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-offset/run_offset_check.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values -- see README.md).
#
# NOT a PVT sweep and NOT a Monte Carlo mismatch study -- see
# sim/closed-loop-offset/README.md for what this deterministic
# input-referred-offset SENSITIVITY probe does and does not claim. Runs a
# small, deliberately informal set of (corner, Vos) points -- three
# representative PVT corners x three Vos values (0, +VOS, -VOS) = 9 runs --
# not the full 45-point grid every other sim/ experiment in this tree uses.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_offset.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention every closed-loop experiment in this tree uses.
MSENSE_LINE="$(grep -E '^XMSENSE ' "${REPO_ROOT}/design/netlist/bandgap_startup.spice")"
MSENSE_W="$(echo "${MSENSE_LINE}" | grep -oE 'w=[0-9.]+u' | head -1 | sed -e 's/w=//')"
if [[ -z "${MSENSE_W}" ]]; then
  echo "run_offset_check.sh: could not parse XMSENSE's w= from design/netlist/bandgap_startup.spice" >&2
  exit 3
fi

# Nodeset provenance: the most recent committed sim/closed-loop-startup
# record -- same cross-experiment read sim/loop-gain-phase-margin/ and
# sim/closed-loop-psrr/ both use (see their READMEs' "Nodeset provenance").
SEED_CSV="$(ls -1 "${SIM_DIR}/closed-loop-startup/records/"*.csv 2>/dev/null | sort | tail -1 || true)"
if [[ -z "${SEED_CSV}" || ! -f "${SEED_CSV}" ]]; then
  echo "run_offset_check.sh: no sim/closed-loop-startup/records/*.csv found -- this" >&2
  echo "run_offset_check.sh: experiment needs that experiment's DC-bias seed values." >&2
  echo "run_offset_check.sh: run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
  exit 3
fi
echo "run_offset_check.sh: nodeset seeds sourced from ${SEED_CSV}"
SEED_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- "${SEED_CSV}" 2>/dev/null || echo unknown)"

lookup_seed() {
  local corner="$1" temp="$2" vdd="$3" field="$4"
  awk -F, -v c="${corner}" -v t="${temp}" -v v="${vdd}" -v field="${field}" '
    NR==1 {
      for (i=1;i<=NF;i++) { if ($i=="corner_label") ci=i; if ($i=="temp_c") ti=i;
                             if ($i=="vdd_v") vi=i; if ($i=="status") si=i;
                             if ($i==field) fi=i }
      next
    }
    $ci==c && $ti==t && $vi==v && $si=="PASS" { print $fi }
  ' "${SEED_CSV}"
}

DUT_CORE_GIT_SHA="${DUT_GIT_SHA}"
DUT_AMP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_amp.spice 2>/dev/null || echo unknown)"
DUT_STARTUP_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_startup.spice 2>/dev/null || echo unknown)"

# Three representative PVT points (NOT the full 45-point grid -- see
# README "Scope: three points, not a PVT sweep"): nominal, and the two
# temperature/supply extremes closed-loop-startup's own record already
# names as its coldest/lowest-vdd and hottest/highest-vdd PASS points.
POINT_CORNERS=(typ wcs bcs)
POINT_HBT=(hbt_typ hbt_wcs hbt_bcs)
POINT_MOS=(mos_tt mos_ss mos_ff)
POINT_RES=(res_typ res_wcs res_bcs)
POINT_TEMPS=(27 -40 125)
POINT_VDDS=(3.30 2.97 3.63)

# Deterministic offset probe values: an arbitrarily chosen, round +/-5mV
# stimulus used to extract the vref SENSITIVITY to an amplifier
# input-referred offset (dVref/dVos) -- NOT a claim about this design's
# actual expected offset magnitude (unknown without Monte Carlo mismatch
# data this repo does not have -- see README).
VOS_TAGS=(0 pos neg)
VOS_VALUES=(0.000 0.005 -0.005)

echo "point_corner,vos_tag,corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,vos_v,status,fb_seed_v,fb_op_v,sns1_op_v,sns1_amp_op_v,sns2_op_v,vref_op_v,loop_err_v" > "${CSV_OUT}"

# Pass criteria (deliberately NOT "op landed near its Vos=0 seed" -- an
# offset probe is EXPECTED to shift the operating point away from that
# seed; that shift is the effect under test. See README "Pass/fail
# criteria"):
#   1. .op converges (ngspice exit 0, no model-load error).
#   2. The loop is still genuinely closed around its OWN (possibly
#      Vos-shifted) equilibrium: |v(sns2) - v(sns1_amp)| <= LOOP_ERR_TOL_V
#      -- confirms the amplifier's own high gain is still forcing its two
#      inputs together despite the injected offset, i.e. this is a real
#      closed-loop operating point, not a railed/divergent one.
#   3. vref lands in a plausible in-range band (not railed to a supply or
#      to 0V).
LOOP_ERR_TOL_V="0.02"
VREF_MIN_V="0.3"

for pi in "${!POINT_CORNERS[@]}"; do
  corner="${POINT_CORNERS[$pi]}"
  hbt_section="${POINT_HBT[$pi]}"
  mos_section="${POINT_MOS[$pi]}"
  res_section="${POINT_RES[$pi]}"
  temp="${POINT_TEMPS[$pi]}"
  vdd="${POINT_VDDS[$pi]}"

  fb_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
  sns1_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
  sns2_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
  vref_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"

  for vi in "${!VOS_TAGS[@]}"; do
    total=$((total + 1))
    vos_tag="${VOS_TAGS[$vi]}"
    vos="${VOS_VALUES[$vi]}"
    corner_label="${corner}_vos${vos_tag}"
    corner_id="${corner_label}_${temp}c_${vdd}v"
    netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
    log="${CORNERS_OUT}/${corner_id}.log"

    if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
      echo "${corner},${vos_tag},${corner_label},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${vos},FAIL,,,,,,," >> "${CSV_OUT}"
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
      -e "s|@@VOS@@|${vos}|g" \
      -e "s|@@POINT_LABEL@@|${corner_label}|g" \
      -e "s|@@CORNER_LABEL@@|${corner}|g" \
      -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
      -e "s|@@FB_SEED@@|${fb_seed}|g" \
      -e "s|@@SNS1_SEED@@|${sns1_seed}|g" \
      -e "s|@@SNS2_SEED@@|${sns2_seed}|g" \
      -e "s|@@VREF_SEED@@|${vref_seed}|g" \
      -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
      "${TEMPLATE}" > "${netlist}"

    run_pvt_point "${netlist}" "${log}"

    fb_op=$(grep -E '^v\(fb\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
    sns1_op=$(grep -E '^v\(sns1\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
    sns1_amp_op=$(grep -E '^v\(sns1_amp\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
    sns2_op=$(grep -E '^v\(sns2\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
    vref_op=$(grep -E '^v\(vref\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)

    verdict=PASS
    loop_err=""
    if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
      verdict=FAIL
    elif [[ -z "${sns2_op}" || -z "${sns1_amp_op}" || -z "${vref_op}" ]]; then
      verdict=FAIL
    else
      loop_err=$(awk -v a="${sns2_op}" -v b="${sns1_amp_op}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
      loop_ok=$(awk -v d="${loop_err}" -v tol="${LOOP_ERR_TOL_V}" 'BEGIN{print (d<=tol)?1:0}')
      vref_ok=$(awk -v v="${vref_op}" -v vdd="${vdd}" -v vmin="${VREF_MIN_V}" 'BEGIN{print (v>=vmin && v<=vdd)?1:0}')
      if [[ "${loop_ok}" != "1" || "${vref_ok}" != "1" ]]; then
        verdict=FAIL
      fi
    fi

    if [[ "${verdict}" == "PASS" ]]; then
      passed=$((passed + 1))
    else
      failed_points+=("${corner_id}")
    fi
    echo "${corner},${vos_tag},${corner_label},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${vos},${verdict},${fb_seed},${fb_op},${sns1_op},${sns1_amp_op},${sns2_op},${vref_op},${loop_err}" >> "${CSV_OUT}"
  done
done

# Derived sensitivity summary: dVref/dVos = (vref(+VOS) - vref(-VOS)) /
# (2*VOS) per point, computed from the just-written CSV (not itself a
# pass/fail criterion -- see README "What this testbench claims").
SENSITIVITY_SUMMARY="$(awk -F, -v OFS=', ' '
  NR==1 { next }
  $11!="PASS" { next }
  { key=$1; if ($2=="0") base[key]=$17; if ($2=="pos") pos[key]=$17; if ($2=="neg") neg[key]=$17;
    vosv[key]=($2=="pos")?$10:vosv[key] }
  END {
    for (k in pos) {
      if ((k in neg) && (k in base)) {
        vos = vosv[k]; if (vos=="") vos=0.005
        sens = (pos[k]-neg[k])/(2*vos)
        printf "%s: dVref/dVos=%.4f V/V (vref: Vos=0 %.6f V, +Vos %.6f V, -Vos %.6f V)\n", k, sens, base[k], pos[k], neg[k]
      }
    }
  }
' "${CSV_OUT}")"
echo "run_offset_check.sh: sensitivity summary:"
echo "${SENSITIVITY_SUMMARY}"

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-offset"
  echo "- **Claim**: NOT a Monte Carlo / statistical mismatch claim (out of"
  echo "  scope -- see README). Through the SAME co-simulated closed-loop"
  echo "  topology sim/closed-loop-vref-pvt uses (bandgap_core +"
  echo "  bandgap_amp + bandgap_startup, wired exactly as"
  echo "  design/bandgap_top.sch specifies, loop NOT broken), a"
  echo "  deterministic DC offset source Vos is inserted in series between"
  echo "  the shared sns1 node and bandgap_amp's own inverting input"
  echo "  (in_n/XMP2 gate only), modeling an amplifier input-referred"
  echo "  offset. Sweeping Vos in {0, +5mV, -5mV} at three representative"
  echo "  PVT points (NOT the full 45-point grid -- see README \"Scope\")"
  echo "  and comparing the resulting vref measures this design's own"
  echo "  vref SENSITIVITY to an amplifier input offset (dVref/dVos), not"
  echo "  this amplifier's actual real offset (unknown without Monte Carlo"
  echo "  mismatch data -- tracked separately, #4 checklist item 6, N/A"
  echo "  per #5)."
  echo "- **Sensitivity summary (dVref/dVos, this run)**:"
  if [[ -n "${SENSITIVITY_SUMMARY}" ]]; then
    while IFS= read -r line; do
      [[ -n "${line}" ]] && echo "  - ${line}"
    done <<< "${SENSITIVITY_SUMMARY}"
  else
    echo "  - (no complete +/-Vos pair converged -- see Failed points below)"
  fi
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice,"
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice, loop NOT broken, plus the"
  echo "  Vos offset-probe fixture documented in testbench/ and README.md."
  echo "  No fixture stands in for any real device -- only the offset"
  echo "  probe is added, same discipline as every closed-loop experiment"
  echo "  in this tree."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies except for the deliberate sns1/sns1_amp offset probe."
  echo "- **Nodeset seed provenance**: \`${SEED_CSV#"${REPO_ROOT}"/}\`"
  echo "  @ \`${SEED_GIT_SHA}\` (sim/closed-loop-startup's own most recent"
  echo "  committed record) -- used as a Newton-Raphson initial-guess hint"
  echo "  only, not an acceptance criterion here (see README \"Pass/fail"
  echo "  criteria\")."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: 3 representative PVT points (typ/27C/3.30V,"
  echo "  wcs/-40C/2.97V, bcs/125C/3.63V -- NOT the full 45-point grid,"
  echo "  deliberately -- see README \"Scope: three points, not a PVT"
  echo "  sweep\") x 3 deterministic Vos probe values (0, +5mV, -5mV) ="
  echo "  ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (.op converged, the"
  echo "  loop is genuinely closed around its own equilibrium"
  echo "  (|sns2-sns1_amp| <= ${LOOP_ERR_TOL_V} V), and vref landed in a"
  echo "  plausible in-range band -- NOT a claim about a target offset or"
  echo "  mismatch magnitude; see README \"What this testbench claims, and"
  echo "  what it does not\")."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_offset.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #88."
} > "${MD_OUT}"

write_pvt_summary
