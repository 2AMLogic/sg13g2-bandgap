#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/closed-loop-vref-trim-mc/run_trim_mc.sh --seed 20260930 --n 300
#
# Options: --seed S (default 20260930)  --n N (default 300, >= 300 per the
# issue's Test Plan)  --parallel P (default 8)
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (per-corner .nodeset DC-bias seed values -- see README.md).
#
# Trim-domain mismatch Monte Carlo campaign (issue #229): the trimmed
# +/-0.5% line evidence DR-0011's Output-reference row obligates ("a
# trim-domain mismatch Monte Carlo demonstrating the +/-0.5% trimmed line
# over -40...125 C after a modeled 1-point 27 C trim"). For each of N
# seeded device-mismatch draws (the SAME _mismatch corner-lib sections and
# .options rndseed parse-time discipline sim/closed-loop-vref-mc uses --
# this is that campaign's trim-domain twin), a modeled 1-point 27 C trim:
#   1. FIT (3 .op draws at 27 C, trim_code 0/1/255): vref(code) is linear
#      in code by construction (the PTAT loop current is independent of
#      the output branch), so a=vref(0), unit=vref(1)-vref(0) determine
#      every code; the code-255 point MEASURES the linearity residual
#      rather than assuming it.
#   2. code* = clip(round((1.050 - a)/unit), 0, 255) -- the code a 1-point
#      wafer-sort trim at 27 C would pick for THIS die, targeting the
#      1.050 V TC-null point (DR-0011: never 1.2 V).
#   3. VERIFY (3 .op draws at code*, temps -40/27/125 C): the trimmed
#      die's vref; the trimmed line is max_T |vref(T)-1.050|/1.050.
# Die identity is preserved across all six netlists of a draw (same
# rndseed + same device instance list; only .param trim_code and
# .options temp differ -- see the template's own header).
#
# Writes append-only evidence under netlist-snapshots/<record-id>/,
# corners/<record-id>/ (ONE representative netlist+log per POINT -- draw
# 0's 27 C verify stage, see README.md "Evidence volume") and
# records/<record-id>.{md,csv,-draws.csv} -- see sim/README.md.
set -euo pipefail

SEED=20260930
N=300
PARALLEL=8
while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --n) N="$2"; shift 2 ;;
    --parallel) PARALLEL="$2"; shift 2 ;;
    *) echo "run_trim_mc.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

alias_dut_git_shas TRIM=design/netlist/bandgap_trim.spice AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_trim_mc.spice.tmpl"

# Points: the nominal mismatch point + its negative control (same seeds,
# plain sections, must trim to EXACTLY the same vref every draw) + the
# bcs/wcs corner points. All at the nominal 3.30 V supply (the supply axis
# is held fixed exactly as sim/closed-loop-vref-mc holds it, for the same
# stated reason). The 1-point trim happens at 27 C at the die's OWN
# corner; verification spans -40/27/125 C.
POINT_LABELS=(nominal negctrl bcs wcs)
declare -A CORNER_OF=( [nominal]=typ [negctrl]=typ [bcs]=bcs [wcs]=wcs )
declare -A MODE_OF=( [nominal]=mismatch [negctrl]=negctrl [bcs]=mismatch [wcs]=mismatch )
declare -A DIGEST_LABEL_OF=( [nominal]=typ_mismatch [negctrl]=typ_negctrl [bcs]=bcs_mismatch [wcs]=wcs_mismatch )
VDD="3.30"
TEMP_TRIM_C=27
VERIFY_TEMPS=(-40 27 125)
FIT_CODES=(0 1 255)
VREF_TARGET_V="1.050"
TRIM_BUDGET_PCT="0.5"

echo "run_trim_mc.sh: seed=${SEED} n=${N} parallel=${PARALLEL}"

SCRATCH_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sg13g2-vref-trim-mc.XXXXXX")"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT
mkdir -p "${SCRATCH_DIR}/netlists" "${SCRATCH_DIR}/logs"

DRAWS_CSV="${RECORDS_DIR}/${RECORD_ID}-draws.csv"
echo "point,mismatch_mode,draw_index,seed,corner_label,fit0_vref_v,fit1_vref_v,fit255_vref_v,unit_v,lin_resid_v,code_star,verify_status,vref_27c_v,vref_n40c_v,vref_125c_v,dev_27c_pct,dev_n40c_pct,dev_125c_pct,max_dev_pct,within_0p5,railed" > "${DRAWS_CSV}"

sections_for() {
  # sets hbt_section/mos_section/res_section for point $1
  local corner="${CORNER_OF[$1]}" mode="${MODE_OF[$1]}"
  if [[ "${mode}" == "mismatch" ]]; then
    hbt_section="${HBT_SECTION_OF[${corner}]}_mismatch"
    mos_section="${MOS_SECTION_OF[${corner}]}_mismatch"
    res_section="${RES_SECTION_OF[${corner}]}_mismatch"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
  fi
}

render_netlist() {
  # render_netlist OUT NETLIST-POINT DRAW TEMP CODE STAGE
  local out="$1" point="$2" draw="$3" temp="$4" code="$5" stage="$6"
  local corner="${CORNER_OF[${point}]}"
  local draw_seed=$((SEED + draw))
  sections_for "${point}"

  local fb_seed sns1_seed sns2_seed vref_seed
  fb_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" fb_final_v)"
  sns1_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" sns1_final_v)"
  sns2_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" sns2_final_v)"
  vref_seed="$(lookup_seed "${corner}" "${temp}" "${VDD}" vref_final_v)"
  if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
    echo "run_trim_mc.sh: no PASS seed row for ${corner}/${temp}C/${VDD}V in ${SEED_CSV} -- run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
    exit 3
  fi

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
    -e "s|@@TRIM_CODE@@|${code}|g" \
    -e "s|@@SEED@@|${draw_seed}|g" \
    -e "s|@@DRAW_INDEX@@|${draw}|g" \
    -e "s|@@POINT_LABEL@@|${point}|g" \
    -e "s|@@STAGE@@|${stage}|g" \
    -e "s|@@MISMATCH_MODE@@|${MODE_OF[${point}]}|g" \
    -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} trim=${DUT_TRIM_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
    "${TEMPLATE}" > "${out}"
}

op_status_of_log() {
  local log="$1"
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type|Simulation interrupted" "${log}" 2>/dev/null; then
    echo BAD; return
  fi
  local v
  v=$(extract_op_voltage vref "${log}")
  if [[ -z "${v}" ]]; then echo BAD; else echo OK; fi
}

# ------------------------------------------------------- Phase 1: FIT pass
FIT_MANIFEST="${SCRATCH_DIR}/fit_manifest.txt"
: > "${FIT_MANIFEST}"
for point in "${POINT_LABELS[@]}"; do
  for ((draw=0; draw<N; draw++)); do
    for code in "${FIT_CODES[@]}"; do
      netlist="${SCRATCH_DIR}/netlists/fit_${point}_${draw}_c${code}.spice"
      render_netlist "${netlist}" "${point}" "${draw}" "${TEMP_TRIM_C}" "${code}" "fit"
      echo "${netlist} ${SCRATCH_DIR}/logs/fit_${point}_${draw}_c${code}.log" >> "${FIT_MANIFEST}"
    done
  done
done
FIT_TOTAL=$(wc -l < "${FIT_MANIFEST}" | tr -d ' ')
echo "run_trim_mc.sh: fit pass -- ${FIT_TOTAL} netlists, ${PARALLEL}-way parallel..."
xargs -P "${PARALLEL}" -n2 bash -c 'ngspice -b "$0" > "$1" 2>&1; echo $? > "$1.rc"; exit 0' < "${FIT_MANIFEST}"

# ------------------------------------------------ code* per (point, draw)
# vref(code) is linear in code to first order with a small measured
# second-order concavity (sim/trim-coverage/ records it at ~-1.4 LSB at
# full scale, every corner -- the M3 finite-ro sublinearity of the
# output branch). The per-die fit therefore uses the {0,255} CHORD
# (a = vref(0), unit = (vref(255)-vref(0))/255), whose interpolation
# error against the true curve is bounded by ~1/4 of the full-scale
# curvature (~0.36 LSB) instead of the {0,1}-tangent line's ~1.45 LSB;
# the code-1 row stays as the per-die low-code sanity check.
CODES_FILE="${SCRATCH_DIR}/code_star.tsv"
: > "${CODES_FILE}"
for point in "${POINT_LABELS[@]}"; do
  for ((draw=0; draw<N; draw++)); do
    v0=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c0.log" 2>/dev/null || true)
    v1=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c1.log" 2>/dev/null || true)
    v255=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c255.log" 2>/dev/null || true)
    s0=$(op_status_of_log "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c0.log")
    s1=$(op_status_of_log "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c1.log")
    s255=$(op_status_of_log "${SCRATCH_DIR}/logs/fit_${point}_${draw}_c255.log")
    echo -e "${point}\t${draw}\t${v0:-NA}\t${v1:-NA}\t${v255:-NA}\t${s0}\t${s1}\t${s255}" >> "${CODES_FILE}"
  done
done

# code* (rounded, clipped) into a side table: point_draw -> code
CODE_STAR_FILE="${SCRATCH_DIR}/code_star_of.tsv"
awk -F'\t' -v tgt="${VREF_TARGET_V}" '
  {
    point=$1; draw=$2; v0=$3; v1=$4; v255=$5; s0=$6; s1=$7; s255=$8
    if (s0=="OK" && s255=="OK" && v0!="NA" && v255!="NA") {
      unit = (v255 - v0)/255
      ideal = (unit != 0) ? (tgt - v0)/unit : 128
      c = (ideal < 0) ? int(ideal - 0.5) : int(ideal + 0.5)
      if (c < 0) c = 0
      if (c > 255) c = 255
    } else {
      c = -1   # fit failed -- verify stages will fail downstream
    }
    print point "\t" draw "\t" c
  }' "${CODES_FILE}" > "${CODE_STAR_FILE}"

# --------------------------------------------------- Phase 2: VERIFY pass
VERIFY_MANIFEST="${SCRATCH_DIR}/verify_manifest.txt"
: > "${VERIFY_MANIFEST}"
for point in "${POINT_LABELS[@]}"; do
  for ((draw=0; draw<N; draw++)); do
    code=$(awk -F'\t' -v p="${point}" -v d="${draw}" '$1==p && $2==d {print $3; exit}' "${CODE_STAR_FILE}")
    if [[ "${code}" == "-1" ]]; then continue; fi
    for temp in "${VERIFY_TEMPS[@]}"; do
      netlist="${SCRATCH_DIR}/netlists/verify_${point}_${draw}_t${temp}_c${code}.spice"
      render_netlist "${netlist}" "${point}" "${draw}" "${temp}" "${code}" "verify"
      echo "${netlist} ${SCRATCH_DIR}/logs/verify_${point}_${draw}_t${temp}_c${code}.log" >> "${VERIFY_MANIFEST}"
    done
  done
done
VERIFY_TOTAL=$(wc -l < "${VERIFY_MANIFEST}" | tr -d ' ')
echo "run_trim_mc.sh: verify pass -- ${VERIFY_TOTAL} netlists, ${PARALLEL}-way parallel..."
xargs -P "${PARALLEL}" -n2 bash -c 'ngspice -b "$0" > "$1" 2>&1; echo $? > "$1.rc"; exit 0' < "${VERIFY_MANIFEST}"

# ------------------------------------------------------ Per-draw assembly
echo "run_trim_mc.sh: assembling per-draw rows..."
for point in "${POINT_LABELS[@]}"; do
  sections_for "${point}"
  for ((draw=0; draw<N; draw++)); do
    draw_seed=$((SEED + draw))
    v0=$(awk -F'\t' -v p="${point}" -v d="${draw}" '$1==p && $2==d {print $3; exit}' "${CODES_FILE}")
    v1=$(awk -F'\t' -v p="${point}" -v d="${draw}" '$1==p && $2==d {print $4; exit}' "${CODES_FILE}")
    v255=$(awk -F'\t' -v p="${point}" -v d="${draw}" '$1==p && $2==d {print $5; exit}' "${CODES_FILE}")
    code=$(awk -F'\t' -v p="${point}" -v d="${draw}" '$1==p && $2==d {print $3; exit}' "${CODE_STAR_FILE}")

    unit=""; resid=""
    verify_status=FAIL
    v27=""; vn40=""; v125=""
    if [[ "${v0}" != "NA" && "${v255}" != "NA" && "${code}" != "-1" ]]; then
      unit=$(awk -v a="${v0}" -v b="${v255}" 'BEGIN{printf "%.9g", (b-a)/255}')
      if [[ "${v1}" != "NA" ]]; then
        resid=$(awk -v l="${v1}" -v a="${v0}" -v u="${unit}" 'BEGIN{printf "%.9g", l-(a+u)}')
      fi
      s27=$(op_status_of_log "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t27_c${code}.log" 2>/dev/null || echo BAD)
      sn40=$(op_status_of_log "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t-40_c${code}.log" 2>/dev/null || echo BAD)
      s125=$(op_status_of_log "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t125_c${code}.log" 2>/dev/null || echo BAD)
      if [[ "${s27}" == "OK" && "${sn40}" == "OK" && "${s125}" == "OK" ]]; then
        verify_status=PASS
        v27=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t27_c${code}.log")
        vn40=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t-40_c${code}.log")
        v125=$(extract_op_voltage vref "${SCRATCH_DIR}/logs/verify_${point}_${draw}_t125_c${code}.log")
      fi
    fi

    dev27=""; devn40=""; dev125=""; maxdev=""; within="0"; railed="0"
    if [[ "${verify_status}" == "PASS" ]]; then
      read -r dev27 devn40 dev125 maxdev within <<< "$(awk -v tgt="${VREF_TARGET_V}" -v a="${v27}" -v b="${vn40}" -v c="${v125}" 'BEGIN{
        da = 100*(a-tgt)/tgt; if (da<0) da=-da
        db = 100*(b-tgt)/tgt; if (db<0) db=-db
        dc = 100*(c-tgt)/tgt; if (dc<0) dc=-dc
        m = da; if (db>m) m=db; if (dc>m) m=dc
        w = (m<=0.5) ? 1 : 0
        printf "%.6f %.6f %.6f %.6f %d", da, db, dc, m, w
      }')"
      if [[ "${code}" == "0" || "${code}" == "255" ]]; then railed="1"; fi
    fi

    echo "${point},${MODE_OF[${point}]},${draw},${draw_seed},${CORNER_OF[${point}]},${v0:-},${v1:-},${v255:-},${unit:-},${resid:-},${code},${verify_status},${v27:-},${vn40:-},${v125:-},${dev27:-},${devn40:-},${dev125:-},${maxdev:-},${within},${railed}" >> "${DRAWS_CSV}"
  done

  # Representative evidence per point: draw 0's 27 C verify-stage netlist
  # and log (see README.md "Evidence volume").
  digest_label="${DIGEST_LABEL_OF[${point}]}"
  corner_id="${digest_label}_${TEMP_TRIM_C}c_${VDD}v"
  code0=$(awk -F'\t' -v p="${point}" -v d="0" '$1==p && $2==d {print $3; exit}' "${CODE_STAR_FILE}")
  if [[ "${code0}" != "-1" ]]; then
    cp "${SCRATCH_DIR}/netlists/verify_${point}_0_t${TEMP_TRIM_C}_c${code0}.spice" "${SNAPSHOTS_OUT}/${corner_id}.spice"
    cp "${SCRATCH_DIR}/logs/verify_${point}_0_t${TEMP_TRIM_C}_c${code0}.log" "${CORNERS_OUT}/${corner_id}.log"
  else
    cp "${SCRATCH_DIR}/netlists/fit_${point}_0_c0.spice" "${SNAPSHOTS_OUT}/${corner_id}.spice"
    cp "${SCRATCH_DIR}/logs/fit_${point}_0_c0.log" "${CORNERS_OUT}/${corner_id}.log"
  fi
done

# --------------------------------------------------------- Negative control
# Same hard gate as sim/closed-loop-vref-mc: the negative control's
# trimmed vref must be EXACTLY identical at every draw and every verify
# temperature -- any spread is a driver bug, not sampling noise.
negctrl_spread=$(awk -F, '$1=="negctrl" && $12=="PASS" {print $13","$14","$15}' "${DRAWS_CSV}" | sort -u | wc -l | tr -d ' ')
if [[ "${negctrl_spread}" != "1" ]]; then
  echo "run_trim_mc.sh: NEGATIVE CONTROL FAILED -- trimmed negctrl draws show nonzero spread (${negctrl_spread} distinct values). Driver bug, not noise. Aborting." >&2
  exit 1
fi
echo "run_trim_mc.sh: negative control confirmed -- exactly zero spread across all draws and temperatures."

# ---------------------------------------------------------- Per-point digest
echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,n_draws,n_pass,frac_within_0p5_pct,three_sigma_max_dev_pct,worst_max_dev_pct,mean_code_star,sigma_code_star,min_code_star,max_code_star,n_railed,mean_unit_mv,sigma_unit_mv,mean_lin_resid_uv" > "${CSV_OUT}"

total=0
passed=0
failed_points=()
claim_fail_points=()
for point in "${POINT_LABELS[@]}"; do
  total=$((total + 1))
  sections_for "${point}"
  digest_label="${DIGEST_LABEL_OF[${point}]}"
  corner_id="${digest_label}_${TEMP_TRIM_C}c_${VDD}v"

  read -r n_draws n_pass frac05 tsig worst cmean csig cmin cmax nrail umean usig rmean <<< "$(awk -F, -v p="${point}" '
    $1==p { n++ }
    $1==p && $12=="PASS" { np++; md[np]=$19; sum+=$19; c=$11; cs+=c; css+=c*c; if (np==1||c<cmin) cmin=c; if (np==1||c>cmax) cmax=c; u=$9*1000; us+=u; uss+=u*u; r+=$10*1e6; rn++; if ($21==1) rail++; if ($20==1) w05++ }
    END {
      if (np==0) { printf "%d 0 0 0 0 0 0 0 0 0 0 0 0", n; exit }
      mean = sum/np
      ssq = 0; for (i=1;i<=np;i++) { d=md[i]-mean; ssq+=d*d }
      sigma = (np>1) ? sqrt(ssq/(np-1)) : 0
      worst = md[1]; for (i=1;i<=np;i++) if (md[i]>worst) worst=md[i]
      cm = cs/np; cssd = (np>1) ? sqrt((css-np*cm*cm)/(np-1)) : 0
      um = us/np; ussd = (np>1) ? sqrt((uss-np*um*um)/(np-1)) : 0
      printf "%d %d %.4f %.6f %.6f %.3f %.3f %d %d %d %.4f %.4f %.2f", n, np, 100*w05/np, 3*sigma, worst, cm, cssd, cmin, cmax, rail, um, ussd, r/rn
    }' "${DRAWS_CSV}")"

  point_status=PASS
  if [[ "${n_pass}" != "${n_draws}" ]]; then
    point_status=FAIL
  fi
  tally_verdict "${point_status}" "${corner_id}"

  # The claim gate (mismatch points only): 3-sigma of the per-draw
  # max-temperature deviation must sit inside the +/-0.5% trimmed line --
  # the trimmed-line counterpart of the untrimmed +/-16% (3-sigma) line.
  if [[ "${MODE_OF[${point}]}" == "mismatch" ]]; then
    if awk -v a="${tsig}" -v b="${TRIM_BUDGET_PCT}" 'BEGIN{exit !(a>b)}'; then
      point_status="FAIL(3sigma>${TRIM_BUDGET_PCT}%)"
      claim_fail_points+=("${digest_label}")
    fi
  fi

  echo "${digest_label},${hbt_section},${mos_section},${res_section},${TEMP_TRIM_C},${VDD},${MSENSE_W},${point_status},${n_draws},${n_pass},${frac05},${tsig},${worst},${cmean},${csig},${cmin},${cmax},${nrail},${umean},${usig},${rmean}" >> "${CSV_OUT}"
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: closed-loop-vref-trim-mc (issue #229)"
  echo "- **Claim**: after a modeled 1-point 27 C trim (per-die trim code"
  echo "  chosen at the die's own corner from a 3-code linearity-verified"
  echo "  fit, targeting DR-0011's 1.050 V TC-null point), the closed-loop"
  echo "  vref of N=${N} seeded device-mismatch draws stays inside the"
  echo "  +/-0.5% trimmed line over -40...125 C -- the trimmed-line evidence"
  echo "  DR-0011's Output-reference row obligates. Digest CSV carries each"
  echo "  point's frac_within_0.5%, 3-sigma and worst per-draw deviation,"
  echo "  the code* distribution (mean/sigma/min/max, railed count) and the"
  echo "  measured per-die trim unit (mV) with its linearity residual."
  echo "  Negative control: same seeds against plain sections trim to"
  echo "  EXACTLY zero spread (hard gate, as in sim/closed-loop-vref-mc)."
  echo "- **Devices**: all real PDK compact models; the DUT is the"
  echo "  trim-bearing bandgap_core (R1 base l=37.2u + XXTRIM ladder, 255"
  echo "  binary-weighted rppd units + strap links, all inside the"
  echo "  mismatch draw -- the ladder's own mismatch is part of the"
  echo "  trim-domain evidence), plus bandgap_amp and bandgap_startup"
  echo "  verbatim."
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
  echo "- **Seed / N / parallelism**: seed=${SEED}, N=${N} per point,"
  echo "  ${PARALLEL}-way."
  echo "- **Corner matrix run**: points {typ mismatch, typ negative control,"
  echo "  bcs mismatch, wcs mismatch} x 6 netlists per draw (3 fit codes at"
  echo "  27 C + code* at {-40, 27, 125} C) = $(( (FIT_TOTAL + VERIFY_TOTAL) ))"
  echo "  netlist runs over ${N} draws per point."
  echo "- **Result**: ${passed}/${total} points PASS (per-draw convergence"
  echo "  + negative-control zero-spread gates);"
  if [[ ${#claim_fail_points[@]} -gt 0 ]]; then
    echo "  3-sigma claim gate FAILED for: ${claim_fail_points[*]}"
  else
    echo "  3-sigma of max-temperature deviation inside +/-0.5% at every"
    echo "  mismatch point (see digest CSV)."
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_closed_loop_vref_trim_mc.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed digest CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Per-draw data: \`records/${RECORD_ID}-draws.csv\`"
  echo "  - Sizing derivation: \`design/bandgap_trim_network.md\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
