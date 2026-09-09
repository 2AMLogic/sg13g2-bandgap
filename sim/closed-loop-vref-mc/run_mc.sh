#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-mc/run_mc.sh --seed 20260909 --n 300
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values -- see README.md).
#
# Untrimmed vref device-MISMATCH MONTE CARLO campaign (issue #215, T1 tracker
# #4 item 6 evidence): N draws of hbt_typ_mismatch/mos_tt_mismatch/
# res_typ_mismatch (and their bcs/wcs siblings) at the nominal point plus a
# deterministic negative control and four process corners -- see README.md
# for the full methodology and what this evidence does and does not claim.
#
# Writes append-only evidence under netlist-snapshots/<record-id>/ and
# corners/<record-id>/ (ONE representative netlist+log per POINT below, not
# per draw -- see README.md "Evidence volume") and
# records/<record-id>.{md,csv,-draws.csv} -- see sim/README.md and this
# experiment's own README.md for why the per-draw data lives in a second,
# non-structurally-checked CSV rather than in the corner-id-matched digest
# CSV every other sim/ experiment's records/<record-id>.csv is.
set -euo pipefail

SEED=20260909
N=300
PARALLEL=8
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --n) N="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    *) echo "run_mc.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_mc.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention every closed-loop experiment in this tree uses.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# Nodeset provenance: the most recent committed sim/closed-loop-startup
# record -- same cross-experiment read sim/closed-loop-offset/,
# sim/loop-gain-phase-margin/ and sim/closed-loop-psrr/ all use.
# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

# --------------------------------------------------------------- Evidence
# volume (#26): per-draw netlists/logs are NOT committed -- only ONE
# representative (draw index 0) netlist+log per POINT below (6 points) is
# copied into the committed netlist-snapshots/<record-id>/ and
# corners/<record-id>/ dirs (matching sim/README.md's corner-id-matched
# digest CSV contract every other experiment satisfies). All N*6 draws'
# working netlists/logs live under a throwaway scratch dir, deleted on
# exit -- see README.md "Evidence volume" for the full rationale.
SCRATCH_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sg13g2-vref-mc.XXXXXX")"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT
mkdir -p "${SCRATCH_DIR}/netlists" "${SCRATCH_DIR}/logs"

DRAWS_CSV="${RECORDS_DIR}/${RECORD_ID}-draws.csv"
echo "point,mismatch_mode,draw_index,seed,corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_v" > "${DRAWS_CSV}"

# The six points this campaign runs: the nominal point (mismatch AND its
# negative control, same N draws each -- issue #215's own requirement) plus
# the four required process-corner x temperature points (bcs/wcs x
# -40C/125C, all at the nominal 3.30V supply -- the PVT axis this campaign
# holds fixed while mismatch is swept is supply, since sim/closed-loop-
# vref-pvt/ and sim/closed-loop-iq/ already cover the full supply corner
# independently and deterministically; combining supply corners AND N>=300
# mismatch draws per point would multiply this campaign's own runtime by
# 3x for no incremental evidence value this issue asks for).
POINT_LABELS=(nominal negctrl bcs_n40 bcs_125 wcs_n40 wcs_125)
declare -A CORNER_OF=( [nominal]=typ [negctrl]=typ [bcs_n40]=bcs [bcs_125]=bcs [wcs_n40]=wcs [wcs_125]=wcs )
declare -A TEMP_OF=( [nominal]=27 [negctrl]=27 [bcs_n40]=-40 [bcs_125]=125 [wcs_n40]=-40 [wcs_125]=125 )
declare -A MODE_OF=( [nominal]=mismatch [negctrl]=negctrl [bcs_n40]=mismatch [bcs_125]=mismatch [wcs_n40]=mismatch [wcs_125]=mismatch )
VDD="3.30"

# corner_label used in the digest CSV/netlist-snapshot/corners-log filenames
# -- "<pdk-corner>_<mode>", e.g. "typ_mismatch", "typ_negctrl",
# "bcs_mismatch" (used at two different temperatures -- still a unique
# corner id once combined with temp_c, same as any two-temperature PVT
# point in this tree's other experiments).
declare -A DIGEST_LABEL_OF
for point in "${POINT_LABELS[@]}"; do
  DIGEST_LABEL_OF[${point}]="${CORNER_OF[${point}]}_${MODE_OF[${point}]}"
done

echo "run_mc.sh: seed=${SEED} n=${N} parallel=${PARALLEL}"

MANIFEST="${SCRATCH_DIR}/manifest.txt"
: > "${MANIFEST}"

# ---------------------------------------------------------------- Pass 1:
# generate every draw's netlist (cheap -- plain sed, no ngspice) and record
# its (netlist, log) pair in MANIFEST for pass 2's parallel execution.
for point in "${POINT_LABELS[@]}"; do
  corner="${CORNER_OF[${point}]}"
  temp="${TEMP_OF[${point}]}"
  mode="${MODE_OF[${point}]}"

  if [[ "${mode}" == "mismatch" ]]; then
    hbt_section="${HBT_SECTION_OF[${corner}]}_mismatch"
    mos_section="${MOS_SECTION_OF[${corner}]}_mismatch"
    res_section="${RES_SECTION_OF[${corner}]}_mismatch"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
  fi

  fb_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" fb_final_v)"
  sns1_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" sns1_final_v)"
  sns2_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" sns2_final_v)"
  vref_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" vref_final_v)"
  if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
    echo "run_mc.sh: no PASS seed row for ${corner}/${temp}C/${VDD}V in ${SEED_CSV} -- run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
    exit 3
  fi

  for ((draw_index = 0; draw_index < N; draw_index++)); do
    draw_seed=$((SEED + draw_index))
    netlist="${SCRATCH_DIR}/netlists/${point}_${draw_index}.spice"
    log="${SCRATCH_DIR}/logs/${point}_${draw_index}.log"

    common_pvt_sed_args "${temp}" "${VDD}" "${corner}"
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
      -e "s|@@SEED@@|${draw_seed}|g" \
      -e "s|@@DRAW_INDEX@@|${draw_index}|g" \
      -e "s|@@POINT_LABEL@@|${point}|g" \
      -e "s|@@MISMATCH_MODE@@|${mode}|g" \
      -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
      "${TEMPLATE}" > "${netlist}"

    echo "${netlist} ${log}" >> "${MANIFEST}"
  done
done

TOTAL_DRAWS=$(wc -l < "${MANIFEST}" | tr -d ' ')
echo "run_mc.sh: generated ${TOTAL_DRAWS} draw netlists across ${#POINT_LABELS[@]} points -- simulating with ${PARALLEL}-way parallelism..."

# ---------------------------------------------------------------- Pass 2:
# run every draw's .op. Bounded parallelism via xargs -P/-n2 (the
# ngspice-per-process cost here is a single fast .op against an already-
# nodeset-seeded operating point, not sim/closed-loop-vref-pvt's 3ms
# startup-ramp transient -- see the testbench template's own header for the
# measured runtime difference this makes tractable at N>=300). The inner
# command always exits 0 (its own ngspice exit status is captured to
# "<log>.rc" instead) so one non-convergent draw cannot abort the whole
# campaign under this script's own `set -e`.
xargs -P "${PARALLEL}" -n2 bash -c 'ngspice -b "$0" > "$1" 2>&1; echo $? > "$1.rc"; exit 0' < "${MANIFEST}"

echo "run_mc.sh: simulation pass complete -- parsing results..."

# ---------------------------------------------------------------- Pass 3:
# re-derive each draw's (netlist, log) path (same deterministic naming pass
# 1 used) and parse its result into DRAWS_CSV.
for point in "${POINT_LABELS[@]}"; do
  corner="${CORNER_OF[${point}]}"
  temp="${TEMP_OF[${point}]}"
  mode="${MODE_OF[${point}]}"

  if [[ "${mode}" == "mismatch" ]]; then
    hbt_section="${HBT_SECTION_OF[${corner}]}_mismatch"
    mos_section="${MOS_SECTION_OF[${corner}]}_mismatch"
    res_section="${RES_SECTION_OF[${corner}]}_mismatch"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
  fi

  for ((draw_index = 0; draw_index < N; draw_index++)); do
    draw_seed=$((SEED + draw_index))
    netlist="${SCRATCH_DIR}/netlists/${point}_${draw_index}.spice"
    log="${SCRATCH_DIR}/logs/${point}_${draw_index}.log"

    rc=1
    if [[ -f "${log}.rc" ]]; then
      rc="$(cat "${log}.rc")"
    fi
    model_error=0
    if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type" "${log}" 2>/dev/null; then
      model_error=1
    fi

    fb_v=$(extract_op_voltage fb "${log}")
    sns1_v=$(extract_op_voltage sns1 "${log}")
    sns2_v=$(extract_op_voltage sns2 "${log}")
    vref_v=$(extract_op_voltage vref "${log}")
    det_v=$(extract_op_voltage det "${log}")
    # i(vmkfb) has no v(node) form -- same "print" parse shape as
    # extract_op_voltage, different anchor (a current, not a node voltage),
    # not worth its own sim/lib/*.sh extraction for this single caller.
    i_mkfb_a=$(grep -E '^i\(vmkfb\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)

    verdict=PASS
    dvsns_v=""
    if [[ "${rc}" != "0" || ${model_error} -ne 0 ]]; then
      verdict=FAIL
    elif [[ -z "${fb_v}" || -z "${sns1_v}" || -z "${sns2_v}" || -z "${vref_v}" || -z "${det_v}" || -z "${i_mkfb_a}" ]]; then
      verdict=FAIL
    else
      dvsns_v=$(abs_diff "${sns1_v}" "${sns2_v}")
      verdict=$(pvt_closed_loop_verdict "${det_v}" "${i_mkfb_a}" "${fb_v}" "${dvsns_v}" "${VDD}")
    fi

    echo "${point},${mode},${draw_index},${draw_seed},${corner},${hbt_section},${mos_section},${res_section},${temp},${VDD},${MSENSE_W},${verdict},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_v}" >> "${DRAWS_CSV}"
  done

  # Representative (draw index 0) netlist+log for this point, copied into
  # the committed, corner-id-matched evidence dirs -- see README.md
  # "Evidence volume" for why only ONE draw per point is committed here.
  digest_label="${DIGEST_LABEL_OF[${point}]}"
  corner_id="${digest_label}_${temp}c_${VDD}v"
  cp "${SCRATCH_DIR}/netlists/${point}_0.spice" "${SNAPSHOTS_OUT}/${corner_id}.spice"
  cp "${SCRATCH_DIR}/logs/${point}_0.log" "${CORNERS_OUT}/${corner_id}.log"
done

echo "run_mc.sh: wrote ${TOTAL_DRAWS} per-draw rows -> ${DRAWS_CSV}"

# --------------------------------------------------------- Negative control
# hard gate: issue #215 requires the negative control's spread be EXACTLY
# zero -- any nonzero spread here is a driver bug (a mismatch section that
# leaked in, or a seed that is not actually reaching .options before parse),
# not sampling noise, and must fail loudly rather than being silently
# reported as a small number.
negctrl_minmax="$(awk -F, '$1=="negctrl" && $12=="PASS" {print $19}' "${DRAWS_CSV}" | awk '
  NR==1 { min=$1; max=$1 } { if ($1<min) min=$1; if ($1>max) max=$1 } END { printf "%.12g %.12g", min, max }
')"
negctrl_min="${negctrl_minmax%% *}"
negctrl_max="${negctrl_minmax##* }"
if [[ -z "${negctrl_min}" ]]; then
  echo "run_mc.sh: negative control has no PASS draws -- cannot confirm zero spread." >&2
  exit 1
fi
if [[ "${negctrl_min}" != "${negctrl_max}" ]]; then
  echo "run_mc.sh: NEGATIVE CONTROL FAILED -- non-mismatch draws show nonzero spread" >&2
  echo "run_mc.sh: (min=${negctrl_min} max=${negctrl_max}) -- this is a driver bug, not noise. Aborting." >&2
  exit 1
fi
echo "run_mc.sh: negative control confirmed -- exactly zero spread (vref=${negctrl_min} V at every draw)."

# ------------------------------------------------------- Per-point digest
# One row per point (the corner-id-matched CSV sim/README.md's checker
# cross-references against netlist-snapshots/ and corners/), with the
# summary statistics this issue's own acceptance criteria ask for
# (mean/sigma/3sigma-over-mean%/min/max/fraction within +/-1%/+/-0.5% of
# that point's own mean -- informational, NOT a pass/fail against
# spec/porting-plan.md's still-unratified Output-reference row; see
# README.md "What this evidence does and does not claim").
echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,n_draws,n_pass,mean_vref_v,sigma_vref_v,three_sigma_over_mean_pct,min_vref_v,max_vref_v,frac_within_1pct,frac_within_0p5pct" > "${CSV_OUT}"

total=0
passed=0
failed_points=()
for point in "${POINT_LABELS[@]}"; do
  total=$((total + 1))
  digest_label="${DIGEST_LABEL_OF[${point}]}"
  temp="${TEMP_OF[${point}]}"
  corner_id="${digest_label}_${temp}c_${VDD}v"
  hbt_section=$(awk -F, -v p="${point}" '$1==p {print $6; exit}' "${DRAWS_CSV}")
  mos_section=$(awk -F, -v p="${point}" '$1==p {print $7; exit}' "${DRAWS_CSV}")
  res_section=$(awk -F, -v p="${point}" '$1==p {print $8; exit}' "${DRAWS_CSV}")

  read -r n_draws n_pass mean sigma three_sigma_pct vmin vmax frac1 frac05 <<< "$(awk -F, -v p="${point}" '
    $1==p { n++ }
    $1==p && $12=="PASS" { np++; v[np]=$19; sum+=$19 }
    END {
      if (np==0) { printf "%d 0 0 0 0 0 0 0 0", n; exit }
      mean = sum/np
      ssq = 0
      for (i=1;i<=np;i++) { d = v[i]-mean; ssq += d*d }
      sigma = (np>1) ? sqrt(ssq/(np-1)) : 0
      three_sigma_pct = (mean!=0) ? 100*3*sigma/mean : 0
      vmin=v[1]; vmax=v[1]
      w1=0; w05=0
      for (i=1;i<=np;i++) {
        if (v[i]<vmin) vmin=v[i]
        if (v[i]>vmax) vmax=v[i]
        reldev = (mean!=0) ? 100*((v[i]-mean)<0?-(v[i]-mean):(v[i]-mean))/mean : 0
        if (reldev<=1.0) w1++
        if (reldev<=0.5) w05++
      }
      printf "%d %d %.6f %.6f %.4f %.6f %.6f %.4f %.4f", n, np, mean, sigma, three_sigma_pct, vmin, vmax, w1/np, w05/np
    }
  ' "${DRAWS_CSV}")"

  point_status=PASS
  if [[ "${n_pass}" != "${n_draws}" ]]; then
    point_status=FAIL
  fi
  tally_verdict "${point_status}" "${corner_id}"

  echo "${digest_label},${hbt_section},${mos_section},${res_section},${temp},${VDD},${MSENSE_W},${point_status},${n_draws},${n_pass},${mean},${sigma},${three_sigma_pct},${vmin},${vmax},${frac1},${frac05}" >> "${CSV_OUT}"
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-mc"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-vref-pvt and sim/closed-loop-offset both use"
  echo "  (bandgap_core + bandgap_amp + bandgap_startup, wired exactly as"
  echo "  design/bandgap_top.sch specifies, loop NOT broken, real devices"
  echo "  throughout, no ideal feedback fixture), a device-MISMATCH Monte"
  echo "  Carlo campaign (T1 tracker #4 checklist item 6, evidence for the"
  echo "  #150/#128 Output-reference-row escalation): N=${N} draws of"
  echo "  vref's DC operating point per point, seeded"
  echo "  (\`.options rndseed=${SEED}+draw_index\`, draw_index=0..$((N - 1)),"
  echo "  applied identically at every point below) against SG13G2's own"
  echo "  agauss()-based statistical device-mismatch corner-lib sections"
  echo "  (hbt_typ_mismatch/mos_tt_mismatch/res_typ_mismatch at the nominal"
  echo "  point, and their bcs/wcs siblings at the two required process"
  echo "  corners), COMBINED WITH (not instead of) the process-corner axis:"
  echo "  bcs/wcs at -40C and 125C, 3.30V -- the same corner/temp/vdd points"
  echo "  sim/closed-loop-startup's own committed record already names as"
  echo "  PASS, reused here as this campaign's .nodeset DC-bias seed."
  echo "  PLUS a deterministic NEGATIVE CONTROL: the identical N=${N} seeds"
  echo "  0..$((N - 1)) replayed against the PLAIN (non-mismatch)"
  echo "  hbt_typ/mos_tt/res_typ sections at the same nominal point --"
  echo "  confirmed EXACTLY ZERO spread (vref=${negctrl_min} V at every"
  echo "  one of the ${N} negative-control draws; this script hard-fails"
  echo "  before ever reaching this record if that is not so)."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time, same convention"
  echo "  every closed-loop experiment in this tree uses)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice,"
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice -- identical device set to"
  echo "  sim/closed-loop-vref-pvt and sim/closed-loop-offset. No fixture"
  echo "  stands in for any real device."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies."
  echo "- **Nodeset seed provenance**: \`${SEED_CSV#"${REPO_ROOT}"/}\`"
  echo "  @ \`${SEED_GIT_SHA}\` (sim/closed-loop-startup's own most recent"
  echo "  committed record) -- used as a Newton-Raphson initial-guess hint"
  echo "  only, not an acceptance criterion (a real mismatch draw is"
  echo "  expected to converge NEAR, not exactly at, this seed)."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: 1 nominal mismatch point (typ/27C/3.30V) +"
  echo "  1 nominal negative-control point (typ/27C/3.30V, non-mismatch"
  echo "  sections) + 4 process-corner mismatch points (bcs/wcs x"
  echo "  -40C/125C, 3.30V) = 6 points, N=${N} draws each ="
  echo "  $((6 * N)) total .op simulations."
  echo "- **Result**: ${passed}/${total} points PASS (a point PASSes here"
  echo "  when ALL ${N} of its draws individually converge with the loop"
  echo "  genuinely closed and not railed -- see"
  echo "  \`sim/lib/pvt_verdict_common.sh\`'s pvt_closed_loop_verdict();"
  echo "  this is a convergence/loop-closure gate, NOT a pass/fail against"
  echo "  any accuracy target -- see README.md \"What this evidence does"
  echo "  and does not claim\")."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_vref_mc.spice.tmpl\`"
  echo "  - Representative (draw index 0) per-point netlists:"
  echo "    \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Representative (draw index 0) per-point raw ngspice logs:"
  echo "    \`corners/${RECORD_ID}/\`"
  echo "  - Per-point digest CSV (corner-id-matched, per sim/README.md):"
  echo "    \`records/${RECORD_ID}.csv\`"
  echo "  - Per-draw raw CSV (all $((6 * N)) draws, the evidence this"
  echo "    record's statistics are computed from):"
  echo "    \`records/${RECORD_ID}-draws.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #215."
  echo
  echo "## Per-point Monte Carlo statistics (informational -- see disclaimer above)"
  echo
  echo "Untrimmed \`vref\`, N=${N} draws/point, mean/sigma/3sigma-over-mean%/"
  echo "min/max in volts, plus the fraction of draws within +/-1% and"
  echo "+/-0.5% of THAT POINT'S OWN mean (not of any spec target -- see"
  echo "README.md). \`n_pass\` is out of \`n_draws\`=${N}."
  echo
  echo "| point | temp (C) | n_pass/n_draws | mean (V) | sigma (V) | 3sigma/mean (%) | min (V) | max (V) | within +/-1% | within +/-0.5% |"
  echo "|---|---|---|---|---|---|---|---|---|---|"
  awk -F, 'NR>1 {printf "| %s | %s | %s/%s | %s | %s | %s | %s | %s | %s | %s |\n", $1, $5, $10, $9, $11, $12, $13, $14, $15, $16, $17}' "${CSV_OUT}"
} > "${MD_OUT}"

write_pvt_summary
