#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   JOBS=8 sim/trim-knob-jacobian/run_knob_jacobian.sh
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
# Second-trim-knob JACOBIAN bench (issue #267). The 1-point R1 trim this
# block carries converts a die's 27 C level error into post-trim temperature
# drift at a measured rate (+0.0775 %/code deterministic,
# sim/closed-loop-vref-boxtc-trim/; +0.0577 %/code across the mismatch
# population, sim/closed-loop-vref-trim-mc/). #267 asks whether a SECOND
# trim knob can break that coupling. Whether a candidate knob can is a
# question about its (level, drift) COLUMN: two knobs whose columns are
# parallel span one degree of freedom between them, however much area the
# second one costs. This bench measures that column, on the real
# trim-bearing closed loop, for each candidate:
#
#   knob A  trim_code   the as-built R1-side ladder (the reference column)
#   knob B  r2 series   a real rppd trim element in SERIES with R2 -- the
#                       "second ladder on R2 / joint R1-R2 code" candidate,
#                       its length swept instead of code-decoded (R2 itself
#                       is never re-sized; a drawn ladder on that branch
#                       does exactly this)
#   knob C  gctat       a VBE/R CTAT current injected into the output branch
#                       (the "VBE-offset / curvature trim" candidate),
#                       modeled behaviorally as a VCCS: I = gctat*v(cb3)
#   knob D  ggain       a trim applied as a SCALING of the whole reference
#                       (an output gain stage / VBE multiplier), modeled
#                       behaviorally as a VCCS: I = ggain*v(vref)
#
# Knobs C and D are deliberately behavioral -- see README.md "What this
# testbench claims, and what it does not". The evaluation that consumes
# these columns is design/bandgap_trim_second_knob.md.
#
# Writes append-only evidence under netlist-snapshots/<record-id>/,
# corners/<record-id>/ and records/<record-id>.{md,csv,-jacobian.csv} --
# see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_trim_knob_jacobian.spice.tmpl"

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

alias_dut_git_shas TRIM=design/netlist/bandgap_trim.spice AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

# ---------------------------------------------------------- the knob grid
# Each knob point is  id|trim_code|r2_trim_l|gctat_gm|ggain_gm  and differs
# from `base` in exactly ONE of the four. Every setting is sized to move the
# 27 C level by about +/-20 mV (~8 LSBs of the as-built ladder): large
# enough that the secant is far above any solver noise, small enough to stay
# in each knob's linear regime -- which the two-magnitude B/C/D points and
# the two-sided A points let the analysis below VERIFY rather than assume.
#
#   a_lo/a_hi   code 128 -/+ 8                     (+/- 19.5 mV at typ/27C)
#   b_1/b_2     rppd w=2u l=4.42u / 8.84u in series with R2 (+606 / +1178
#               ohm on a 10.72 kohm R2, so -20.6 / -38 mV) -- one-sided,
#               because a series element can only ADD to R2 and `base` is
#               the as-built core with no such element at all
#   c_1/c_2     gctat = 4.164e-7 / 8.328e-7 S      (R_c = 2.40 / 1.20 Mohm;
#               +21.0 / +41.9 mV -- one-sided, the as-built core has no
#               such branch, so `base` IS gctat=0)
#   d_1/d_2     ggain = 2.765e-7 / 5.530e-7 S      (+20.9 / +42.6 mV --
#               one-sided for the same reason)
#
# `none` in the r2_trim_l field renders knob B's card as a comment and
# leaves XR2's mid-node at cb2, so EVERY snapshot of this record carries
# byte-identical DUT device cards (only nodes differ) -- the invariant
# .github/scripts/check_evidence_formats.py's D2 DUT-signature check
# enforces, and the reason knob B adds a device instead of re-sizing R2.
KNOB_POINTS=(
  "base|128|none|0|0"
  "a_lo|120|none|0|0"
  "a_hi|136|none|0|0"
  "b_1|128|4.42u|0|0"
  "b_2|128|8.84u|0|0"
  "c_1|128|none|4.164e-7|0"
  "c_2|128|none|8.328e-7|0"
  "d_1|128|none|0|2.765e-7"
  "d_2|128|none|0|5.530e-7"
)

JOBS="${JOBS:-1}"
if [[ "${JOBS}" -lt 1 ]]; then
  echo "run_knob_jacobian.sh: JOBS must be >= 1 (got '${JOBS}')." >&2
  exit 3
fi

VREF_TARGET_V="1.050"     # DR-0011: the trim targets 1.050 V, never 1.2 V

# Gate thresholds -- see README.md "Pass/fail criteria".
PTAT_RATIO_TOL_PCT="5"    # knob A's measured ratio vs the dT/T prediction
COLLINEAR_TOL="0.02"      # |ratio_B - ratio_A| at or under this => parallel columns
INDEPENDENT_FLOOR="0.30"  # |ratio_C - ratio_A| at or above this => a real 2nd DOF
LEVEL_ONLY_CAP="0.05"     # |ratio_D| at or under this => a level-only knob
LIN_DEV_CAP_PCT="10"      # 2x-magnitude point's ratio vs the 1x point's

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,knob_id,trim_code,r2_trim_l,gctat_gm,ggain_gm,fb_v,sns1_v,sns2_v,det_v,i_mkfb_a,dvsns_v,vref_v,vbeq3_v" > "${CSV_OUT}"

ROWS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/knobjac-rows-${RECORD_ID}.XXXXXX")"
trap 'rm -rf "${ROWS_DIR}"' EXIT

lookup_seeds() {
  local corner="$1" temp="$2" vdd="$3"
  FB_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
  SNS1_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
  SNS2_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
  VREF_SEED="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"
  if [[ -z "${FB_SEED}" || -z "${SNS1_SEED}" || -z "${SNS2_SEED}" || -z "${VREF_SEED}" ]]; then
    echo "run_knob_jacobian.sh: no PASS seed row for ${corner}/${temp}C/${vdd}V in ${SEED_CSV} -- run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
    exit 3
  fi
}

# run_one_point CORNER TEMP VDD KNOB_SPEC
run_one_point() {
  local corner="$1" temp="$2" vdd="$3" spec="$4"
  local knob code r2l gctat ggain
  IFS='|' read -r knob code r2l gctat ggain <<<"${spec}"
  local r2_mid_node r2_series_card
  if [[ "${r2l}" == "none" ]]; then
    r2_mid_node="cb2"
    r2_series_card="* (knob B inactive at this point: no series element on the R2 branch)"
  else
    r2_mid_node="r2t"
    r2_series_card="XR2T r2t cb2 sub! rppd w=2u l=${r2l} m=1 b=0"
  fi
  local hbt_section="${HBT_SECTION_OF[${corner}]}"
  local res_section="${RES_SECTION_OF[${corner}]}"
  local mos_section="${MOS_SECTION_OF[${corner}]}"
  local corner_id="${corner}_${knob}_${temp}c_${vdd}v"
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
    -e "s|@@KNOB_ID@@|${knob}|g" \
    -e "s|@@TRIM_CODE@@|${code}|g" \
    -e "s|@@R2_TRIM_L@@|${r2l}|g" \
    -e "s|@@R2_MID_NODE@@|${r2_mid_node}|g" \
    -e "s|@@R2_SERIES_CARD@@|${r2_series_card}|g" \
    -e "s|@@GCTAT_GM@@|${gctat}|g" \
    -e "s|@@GGAIN_GM@@|${ggain}|g" \
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

  printf '%s\n' "${corner}_${knob},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${knob},${code},${r2l},${gctat},${ggain},${fb_v},${sns1_v},${sns2_v},${det_v},${i_mkfb_a},${dvsns_v},${vref_v},${vbeq3_v}" > "${ROWS_DIR}/${corner_id}.row"
  printf '%s\n' "${verdict}" > "${ROWS_DIR}/${corner_id}.verdict"
}

# The grid: 5 corners x 3 supplies x 3 temperatures x 9 knob points. The
# level leg of every column is read at 27 C (the 1-point trim temperature);
# the drift legs need -40 C and 125 C, so every knob point runs at all
# three temperatures of the shared PVT grid.
GRID=()
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    for temp in "${TEMPS[@]}"; do
      for spec in "${KNOB_POINTS[@]}"; do
        GRID+=("${corner}|${temp}|${vdd}|${spec}")
      done
    done
  done
done

for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd knob code r2l gctat ggain <<<"${point}"
  if [[ "${JOBS}" -le 1 ]]; then
    run_one_point "${corner}" "${temp}" "${vdd}" "${knob}|${code}|${r2l}|${gctat}|${ggain}"
  else
    while [[ "$(jobs -rp | wc -l)" -ge "${JOBS}" ]]; do
      sleep 1
    done
    run_one_point "${corner}" "${temp}" "${vdd}" "${knob}|${code}|${r2l}|${gctat}|${ggain}" &
  fi
done
if [[ "${JOBS}" -gt 1 ]]; then
  wait || true
fi

total=0
passed=0
failed_points=()
for point in "${GRID[@]}"; do
  IFS='|' read -r corner temp vdd knob code r2l gctat ggain <<<"${point}"
  corner_id="${corner}_${knob}_${temp}c_${vdd}v"
  total=$((total + 1))
  if [[ -f "${ROWS_DIR}/${corner_id}.row" ]]; then
    cat "${ROWS_DIR}/${corner_id}.row" >> "${CSV_OUT}"
    verdict="$(cat "${ROWS_DIR}/${corner_id}.verdict")"
  else
    hbt_section="${HBT_SECTION_OF[${corner}]}"
    res_section="${RES_SECTION_OF[${corner}]}"
    mos_section="${MOS_SECTION_OF[${corner}]}"
    echo "${corner}_${knob},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,${knob},${code},${r2l},${gctat},${ggain},,,,,,,," >> "${CSV_OUT}"
    verdict=FAIL
  fi
  if [[ "${verdict}" == "PASS" ]]; then
    passed=$((passed + 1))
  else
    failed_points+=("${corner_id}")
  fi
done

# ------------------------------------------------------- Jacobian analysis
# Per corner/supply group, from THIS run's own PASS rows, with
#   L(k)  = vref(knob k, 27 C)                       -- the level leg
#   Dh(k) = vref(k, 125 C) - vref(k, 27 C)           -- the hot drift leg
#   Dc(k) = vref(k, -40 C) - vref(k, 27 C)           -- the cold drift leg
# each knob's COLUMN is the secant against the baseline point:
#   dlevel(k)  = L(k)  - L(base)
#   ddrift(k)  = Dh(k) - Dh(base)
#   ratio(k)   = ddrift(k) / dlevel(k)      <- the offset-to-drift conversion
# ratio is the quantity an architecture choice turns on: it is the slope of
# knob k's column in the (level, drift) plane, so two knobs with the same
# ratio span ONE degree of freedom and the 2x2 solve for (level, drift) is
# singular. The predictions the gates compare against are first-principles:
#   ratio_ptat = T(125C)/T(27C) - 1 = 0.326503
#     any knob that moves vref by rescaling a VT-proportional term adds
#     drift equal to level*dT/T, because the added volts are themselves PTAT
#   ratio_ctat = (VBE(125C) - VBE(27C)) / VBE(27C)   (measured per group
#     from this run's own base-point vbeq3 column)
#     a knob that moves vref by adding a VBE-proportional term adds drift in
#     the CTAT direction instead -- opposite sign, hence a real second DOF
ANALYSIS_OUT="${RECORDS_DIR}/${RECORD_ID}-jacobian.csv"
echo "corner_label,vdd_v,group_status,n_pass,n_grid,base_vref27_v,base_drift_hot_v,base_drift_hot_pct,ratio_ptat_pred,ratio_ctat_pred,a_dlevel_mv,a_ddrift_mv,a_ratio,a_ratio_lo,a_dev_vs_pred_pct,b_dlevel_mv,b_ddrift_mv,b_ratio,b_ratio_2x,b_minus_a,c_dlevel_mv,c_ddrift_mv,c_ratio,c_ratio_2x,c_lin_dev_pct,c_dev_vs_pred_pct,c_minus_a,d_dlevel_mv,d_ddrift_mv,d_ratio,d_ratio_2x,a_ratio_cold,c_ratio_cold,tc_gain_level_neutral" > "${ANALYSIS_OUT}"
group_fail=0
for corner in "${CORNER_LABELS[@]}"; do
  for vdd in "${VDDS[@]}"; do
    read -r n_pass n_grid base27 bdh bdh_pct rpp rcp adl add ar arlo adev bdl bdd br br2 bma cdl cdd cr cr2 clin cdev cma ddl ddd dr dr2 arc crc tcgain <<< "$(awk -F, -v c="${corner}_" -v vdd_in="${vdd}" -v tgt="${VREF_TARGET_V}" '
      $1 ~ "^"c && $6==vdd_in {
        n_grid++
        if ($8=="PASS") { n_pass++; v[$9 "_" $5]=$20; q[$9 "_" $5]=$21 }
      }
      function lvl(k)  { return v[k "_27"] }
      function dh(k)   { return v[k "_125"] - v[k "_27"] }
      function dc(k)   { return v[k "_-40"] - v[k "_27"] }
      function dlev(k) { return lvl(k) - lvl("base") }
      function ddh(k)  { return dh(k) - dh("base") }
      function ddc(k)  { return dc(k) - dc("base") }
      function rat(k)  { return (dlev(k)!=0) ? ddh(k)/dlev(k) : 0 }
      function ratc(k) { return (dlev(k)!=0) ? ddc(k)/dlev(k) : 0 }
      END {
        split("base a_lo a_hi b_1 b_2 c_1 c_2 d_1 d_2", ks, " ")
        split("-40 27 125", tl, " ")
        ok = 1
        for (i = 1; i <= 9; i++)
          for (j = 1; j <= 3; j++)
            if (v[ks[i] "_" tl[j]] == "") ok = 0
        if (ok && q["base_27"] == "") ok = 0
        if (!ok) {
          # Incomplete group (a non-convergent point): emit zeros, which the
          # caller treats as FAIL via its own n_pass/n_grid and a_ratio checks.
          printf "%d %d", n_pass, n_grid
          for (i = 1; i <= 29; i++) printf " 0"
          exit
        }
        ratio_ptat = 398.15/300.15 - 1
        ratio_ctat = (q["base_125"] - q["base_27"]) / q["base_27"]
        a_r  = rat("a_hi");  a_rlo = rat("a_lo")
        b_r  = rat("b_1");   b_r2  = rat("b_2")
        c_r  = rat("c_1");   c_r2  = rat("c_2")
        d_r  = rat("d_1");   d_r2  = rat("d_2")
        c_lin = (c_r != 0) ? 100*(c_r2-c_r)/c_r : 0
        c_dev = (ratio_ctat != 0) ? 100*(c_r-ratio_ctat)/ratio_ctat : 0
        printf "%d %d %.9g %.9g %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.4f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.4f %.4f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f",
          n_pass, n_grid,
          lvl("base"), dh("base"), 100*dh("base")/tgt,
          ratio_ptat, ratio_ctat,
          1e3*dlev("a_hi"), 1e3*ddh("a_hi"), a_r, a_rlo, 100*(a_r-ratio_ptat)/ratio_ptat,
          1e3*dlev("b_1"), 1e3*ddh("b_1"), b_r, b_r2, b_r-a_r,
          1e3*dlev("c_1"), 1e3*ddh("c_1"), c_r, c_r2, c_lin, c_dev, c_r-a_r,
          1e3*dlev("d_1"), 1e3*ddh("d_1"), d_r, d_r2,
          ratc("a_hi"), ratc("c_1"), a_r-c_r
      }' "${CSV_OUT}")"
    group_status=PASS
    if [[ "${n_pass}" != "${n_grid}" || -z "${ar}" || "${ar}" == "0" ]]; then
      group_status=FAIL
    else
      # G1 knob A's column matches the dT/T prediction
      if awk -v a="${adev#-}" -v cap="${PTAT_RATIO_TOL_PCT}" 'BEGIN{exit !(a>cap)}'; then group_status=FAIL; fi
      # G2 the R2-side knob's column is PARALLEL to knob A's (no new DOF)
      bma_abs="${bma#-}"
      if awk -v a="${bma_abs}" -v cap="${COLLINEAR_TOL}" 'BEGIN{exit !(a>cap)}'; then group_status=FAIL; fi
      # G3 the CTAT knob's column is INDEPENDENT of knob A's (a real 2nd DOF)
      cma_abs="${cma#-}"
      if awk -v a="${cma_abs}" -v f="${INDEPENDENT_FLOOR}" 'BEGIN{exit !(a<f)}'; then group_status=FAIL; fi
      if awk -v a="${cr}" 'BEGIN{exit !(a>0)}'; then group_status=FAIL; fi
      if awk -v a="${clin#-}" -v cap="${LIN_DEV_CAP_PCT}" 'BEGIN{exit !(a>cap)}'; then group_status=FAIL; fi
      # G4 the scaling knob's column is level-only
      if awk -v a="${dr#-}" -v cap="${LEVEL_ONLY_CAP}" 'BEGIN{exit !(a>cap)}'; then group_status=FAIL; fi
    fi
    if [[ "${group_status}" == "FAIL" ]]; then group_fail=$((group_fail+1)); fi
    echo "${corner},${vdd},${group_status},${n_pass},${n_grid},${base27},${bdh},${bdh_pct},${rpp},${rcp},${adl},${add},${ar},${arlo},${adev},${bdl},${bdd},${br},${br2},${bma},${cdl},${cdd},${cr},${cr2},${clin},${cdev},${cma},${ddl},${ddd},${dr},${dr2},${arc},${crc},${tcgain}" >> "${ANALYSIS_OUT}"
  done
done

N_GROUPS=$(( ${#CORNER_LABELS[@]} * ${#VDDS[@]} ))

# Headline numbers for the record: the worst (most adverse) value of each
# gated quantity across all corner/supply groups.
WORST_A_DEV=$(awk -F, 'NR>1 {d=$15+0; if (d<0) d=-d; if (d>m) m=d} END{printf "%.3f", m}' "${ANALYSIS_OUT}")
WORST_BMA=$(awk -F, 'NR>1 {d=$20+0; if (d<0) d=-d; if (d>m) m=d} END{printf "%.5f", m}' "${ANALYSIS_OUT}")
WORST_CMA=$(awk -F, 'NR>1 {d=$27+0; if (d<0) d=-d; if (m=="" || d<m) m=d} END{printf "%.5f", m}' "${ANALYSIS_OUT}")
WORST_D=$(awk -F, 'NR>1 {d=$30+0; if (d<0) d=-d; if (d>m) m=d} END{printf "%.5f", m}' "${ANALYSIS_OUT}")
A_RATIO_TYP=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $13; exit}' "${ANALYSIS_OUT}")
B_RATIO_TYP=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $18; exit}' "${ANALYSIS_OUT}")
C_RATIO_TYP=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $23; exit}' "${ANALYSIS_OUT}")
D_RATIO_TYP=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $30; exit}' "${ANALYSIS_OUT}")
PTAT_PRED=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $9; exit}' "${ANALYSIS_OUT}")
CTAT_PRED=$(awk -F, '$1=="typ" && $2=="3.30" {printf "%.5f", $10; exit}' "${ANALYSIS_OUT}")

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: trim-knob-jacobian (issue #267)"
  echo "- **Claim**: the (level, drift) column of each candidate second trim"
  echo "  knob, measured on the real trim-bearing closed loop about the"
  echo "  code-128 / 27 C baseline, across {typ,bcs,wcs,sf,fs} x"
  echo "  {2.97,3.30,3.63} V x {-40,27,125} C. At typ/3.30 V the measured"
  echo "  offset-to-drift conversion ratios are: **A (as-built R1 ladder)"
  echo "  ${A_RATIO_TYP}**, **B (R2-side ladder) ${B_RATIO_TYP}**,"
  echo "  **C (VBE/R CTAT injection) ${C_RATIO_TYP}**, **D (reference"
  echo "  scaling) ${D_RATIO_TYP}**, against first-principles predictions"
  echo "  dT/T = ${PTAT_PRED} (A and B) and dVBE/VBE = ${CTAT_PRED} (C)."
  echo "  So: **the R2-side knob is parallel to the as-built ladder** (worst"
  echo "  |ratio_B - ratio_A| across groups ${WORST_BMA}, gate <="
  echo "  ${COLLINEAR_TOL}) and supplies NO second degree of freedom, while"
  echo "  **the CTAT injection is independent** (worst |ratio_C - ratio_A|"
  echo "  ${WORST_CMA}, gate >= ${INDEPENDENT_FLOOR}) and **reference"
  echo "  scaling is level-only** (worst |ratio_D| ${WORST_D}, gate <="
  echo "  ${LEVEL_ONLY_CAP}). Knob A's own ratio tracks dT/T to within"
  echo "  ${WORST_A_DEV}% at every group, which is why the coupling #267"
  echo "  reports is a property of the knob's temperature SHAPE and not of"
  echo "  the ladder's construction."
  echo "- **Devices**: all real PDK compact models; the DUT is the"
  echo "  trim-bearing bandgap_core (R1 base l=37.2u + XXTRIM ladder) with"
  echo "  the ladder's subcircuit copied device-for-device from"
  echo "  design/netlist/bandgap_trim.spice, plus bandgap_amp and"
  echo "  bandgap_startup verbatim; the loop is NOT broken. Knobs A and B"
  echo "  move REAL devices: the ladder's own decoded straps for A, and for B"
  echo "  an rppd segment of R1/R2's own w=2u geometry class added in series"
  echo "  with R2 (R2's own card is never re-sized -- a drawn ladder on that"
  echo "  branch does exactly this, and it keeps every snapshot's DUT"
  echo "  signature identical)."
  echo "  **Knobs C and D are behavioral VCCS elements** (GCTAT, GGAIN) --"
  echo "  they model a knob of that temperature SHAPE acting on the real"
  echo "  loop, NOT a circuit that generates it; the branch that would,"
  echo "  and its area / quiescent-current / mismatch / PSRR cost, is"
  echo "  evaluated in design/bandgap_trim_second_knob.md and is not a"
  echo "  claim of this record."
  echo "- **Netlist provenance**: schematic (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_trim.spice @ \`${DUT_TRIM_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch specifies."
  echo "- **Nodeset seeds**: \`${SEED_CSV##*/}\` @ \`${SEED_GIT_SHA}\`"
  echo "  (sim/closed-loop-startup's own most recent record)."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **JOBS**: ${JOBS} (wall-clock concurrency only)."
  echo "- **Corner matrix run**: ${#CORNER_LABELS[@]} process corners x"
  echo "  ${#VDDS[@]} supplies x ${#TEMPS[@]} temperatures x"
  echo "  ${#KNOB_POINTS[@]} knob points = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (startup-release,"
  echo "  loop-closure, not-railed criteria); ${group_fail}/${N_GROUPS}"
  echo "  corner/supply groups FAIL the Jacobian gates (see"
  echo "  records/${RECORD_ID}-jacobian.csv)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_trim_knob_jacobian.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Per-group Jacobian analysis: \`records/${RECORD_ID}-jacobian.csv\`"
  echo "  - Evaluation that consumes these columns: \`design/bandgap_trim_second_knob.md\`"
  echo "  - The coupling this bench explains: \`sim/closed-loop-vref-boxtc-trim/\`,"
  echo "    \`sim/closed-loop-vref-trim-mc/\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
} > "${MD_OUT}"

write_pvt_summary
