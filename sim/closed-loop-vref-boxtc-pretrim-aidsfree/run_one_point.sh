#!/usr/bin/env bash
# sg13g2-bandgap -- issue #269 aids A/B, one point per invocation.
#
#   sim/closed-loop-vref-boxtc-pretrim-aidsfree/run_one_point.sh \
#       <RECORD_ID> <CORNER> <TEMP_C> <VDD> <aided|aidsfree>
#
# Deliberately NOT a run_pvt_sweep.sh-shaped grid loop: this dispatch host's
# rules forbid hand-looping `ngspice -b` over a corner grid (CLAUDE.md), and
# direct multi-corner/Monte Carlo work to `klt sim`'s batch backend instead
# -- which cannot run this PDK's grids today (sim/harness/README.md
# "What still blocks the grids", issue #277/#278) and, separately, cannot
# correctly sweep THIS testbench's ramped `Vvdd` at all (`klt sim`'s
# per-corner override is a scalar `alter Vvdd=<v>` card, which has no effect
# on a source declared with an explicit PWL waveform -- confirmed against
# plain ngspice directly during this issue's own investigation; see the PR
# description and klayout-tools#2706, the upstream friction issue it files).
#
# So this script runs exactly ONE explicit (corner, temp, vdd, aids) point
# per invocation -- the "a single corner, a debug probe, one operating
# point" case those same host rules carry as the standing exception -- and
# is invoked by hand, once per point, rather than from an internal loop.
# Each call appends one row to the record's own CSV/log/snapshot files
# (append-only, matching every other sim/*/records/ convention); nothing
# here loops over a grid.
#
# Cold start:
#   export PDK_ROOT=/path/to/ihp-open-pdk
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh
#   sim/closed-loop-vref-boxtc-pretrim-aidsfree/run_one_point.sh \
#       20261002-125922-d770c09 bcs 125 3.63 aidsfree
#
# See README.md for which points this issue's own record actually covers
# and why, and finalize_record.py for the step that turns the accumulated
# per-point rows into records/<id>.md + .csv once every point for that
# record id has been run.
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: run_one_point.sh <RECORD_ID> <CORNER> <TEMP_C> <VDD> <aided|aidsfree>" >&2
  exit 3
fi
RECORD_ID="$1"
CORNER="$2"
TEMP_C="$3"
VDD="$4"
AIDS_LABEL="$5"
if [[ "${AIDS_LABEL}" != "aided" && "${AIDS_LABEL}" != "aidsfree" ]]; then
  echo "run_one_point.sh: aids label must be 'aided' or 'aidsfree', got '${AIDS_LABEL}'" >&2
  exit 3
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
EXPERIMENT_DIR="${SCRIPT_DIR}"

# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"
if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_one_point.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see sim/env.sh output above." >&2
  exit 3
fi
command -v ngspice >/dev/null 2>&1 || { echo "run_one_point.sh: ngspice not on PATH." >&2; exit 3; }
if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_one_point.sh: OSDI device models missing -- run sim/tools/build-osdi.sh first." >&2
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"

# This experiment's own corner->section map -- copied from
# sim/lib/pvt_preflight.sh's HBT_SECTION_OF/MOS_SECTION_OF/RES_SECTION_OF
# (not sourced from it directly: that file also defines CORNER_LABELS/
# VDDS/TEMPS and a run_pvt_point()/write_pvt_summary() grid-sweep contract
# this deliberately single-point script does not use).
declare -A HBT_SECTION_OF=( [typ]=hbt_typ [bcs]=hbt_bcs [wcs]=hbt_wcs [sf]=hbt_typ [fs]=hbt_typ )
declare -A MOS_SECTION_OF=( [typ]=mos_tt [bcs]=mos_ff [wcs]=mos_ss [sf]=mos_sf [fs]=mos_fs )
declare -A RES_SECTION_OF=( [typ]=res_typ [bcs]=res_bcs [wcs]=res_wcs [sf]=res_typ [fs]=res_typ )
if [[ -z "${HBT_SECTION_OF[${CORNER}]:-}" ]]; then
  echo "run_one_point.sh: unknown corner label '${CORNER}' (expected one of: ${!HBT_SECTION_OF[*]})" >&2
  exit 3
fi

# design/netlist/bandgap_core.spice's git sha AS OF THE HISTORICAL, PRE-#229
# record this A/B's "aided" leg reproduces
# (sim/closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc.md's own
# "Netlist provenance" field) -- not this worktree's live HEAD, which is the
# whole point (see README.md "Why a historical DUT").
DUT_GIT_SHA="d83f7c4"

MSENSE_LINE="$(grep -E '^XMSENSE ' "${REPO_ROOT}/design/netlist/bandgap_startup.spice")"
MSENSE_W="$(echo "${MSENSE_LINE}" | grep -oE 'w=[0-9.]+u' | head -1 | sed -e 's/w=//')"
if [[ -z "${MSENSE_W}" ]]; then
  echo "run_one_point.sh: could not parse XMSENSE's w= from design/netlist/bandgap_startup.spice" >&2
  exit 3
fi

SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
ROWS_OUT="${EXPERIMENT_DIR}/.rows/${RECORD_ID}"
mkdir -p "${SNAPSHOTS_OUT}" "${CORNERS_OUT}" "${ROWS_OUT}"

# corner-id grammar (sim/README.md): <process>_<temp>c_<supply>v, parsed by
# rsplit("_", 2) -- so the aids axis has to live INSIDE the process token,
# not appended after the supply token, or check_evidence_formats.py's
# corner-id parser misreads the supply cell. "bcs_aided"/"bcs_aidsfree" are
# both valid process tokens under that grammar (PROCESS_TOKEN_RE allows
# underscores), so CORNER_LABEL below is "<corner>_<aids>", e.g. "bcs_aided".
CORNER_LABEL="${CORNER}_${AIDS_LABEL}"
CORNER_ID="${CORNER_LABEL}_${TEMP_C}c_${VDD}v"
NETLIST="${SNAPSHOTS_OUT}/${CORNER_ID}.spice"
LOG="${CORNERS_OUT}/${CORNER_ID}.log"
TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_closed_loop_vref_boxtc_pretrim_ab.spice.tmpl"

AIDS_OPTIONS=""
if [[ "${AIDS_LABEL}" == "aided" ]]; then
  AIDS_OPTIONS="rshunt=1e9 gmin=1e-9 "
fi

sed \
  -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
  -e "s|@@PDK@@|${PDK}|g" \
  -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
  -e "s|@@TEMP_C@@|${TEMP_C}|g" \
  -e "s|@@VDD@@|${VDD}|g" \
  -e "s|@@CORNER_LABEL@@|${CORNER}|g" \
  -e "s|@@HBT_SECTION@@|${HBT_SECTION_OF[${CORNER}]}|g" \
  -e "s|@@MOS_SECTION@@|${MOS_SECTION_OF[${CORNER}]}|g" \
  -e "s|@@RES_SECTION@@|${RES_SECTION_OF[${CORNER}]}|g" \
  -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
  -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
  -e "s|@@AIDS_LABEL@@|${AIDS_LABEL}|g" \
  -e "s|@@AIDS_OPTIONS@@|${AIDS_OPTIONS}|g" \
  "${TEMPLATE}" > "${NETLIST}"

set +e
ngspice -b "${NETLIST}" > "${LOG}" 2>&1
RC=$?
set -e

extract_measure() {
  grep -E "^${1}" "${LOG}" | head -1 | awk '{print $3}' || true
}
v_fb_v=$(extract_measure '^v_fb_v')
v_sns1_v=$(extract_measure '^v_sns1_v')
v_sns2_v=$(extract_measure '^v_sns2_v')
v_det_v=$(extract_measure '^v_det_v')
i_mkfb_a=$(extract_measure '^i_mkfb_v')
v_vref_2ms=$(extract_measure '^v_vref_2ms')
v_vref_3ms=$(extract_measure '^v_vref_3ms')
v_vbeq3_2ms=$(extract_measure '^v_vbeq3_2ms')
v_vbeq3_3ms=$(extract_measure '^v_vbeq3_3ms')

DVSNS_CLOSE_V="0.020"
FB_RAIL_MARGIN_V="0.05"
DET_RELEASE_FRAC="0.2"
I_MKFB_RELEASE_A="50e-9"
SETTLE_TOL_V="0.001"

VERDICT="FAIL"
DVSNS_V=""
SETTLE_DELTA=""
if [[ ${RC} -eq 0 && -n "${v_det_v}" && -n "${i_mkfb_a}" && -n "${v_sns1_v}" \
      && -n "${v_sns2_v}" && -n "${v_fb_v}" && -n "${v_vref_2ms}" && -n "${v_vref_3ms}" ]]; then
  DVSNS_V=$(awk -v a="${v_sns1_v}" -v b="${v_sns2_v}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
  SETTLE_DELTA=$(awk -v a="${v_vref_2ms}" -v b="${v_vref_3ms}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
  VERDICT=$(awk -v det_v="${v_det_v}" -v i_mkfb_a="${i_mkfb_a}" -v vdd="${VDD}" \
      -v det_frac="${DET_RELEASE_FRAC}" -v i_thresh="${I_MKFB_RELEASE_A}" \
      -v dvsns="${DVSNS_V}" -v dvsns_thresh="${DVSNS_CLOSE_V}" \
      -v fb="${v_fb_v}" -v rail_margin="${FB_RAIL_MARGIN_V}" \
      -v sdelta="${SETTLE_DELTA}" -v sdelta_thresh="${SETTLE_TOL_V}" \
    'BEGIN{
       i_abs = (i_mkfb_a < 0) ? -i_mkfb_a : i_mkfb_a;
       startup_released = (det_v <= det_frac*vdd) && (i_abs <= i_thresh);
       loop_closed = (dvsns <= dvsns_thresh);
       not_railed = (fb >= rail_margin) && (fb <= vdd - rail_margin);
       settled = (sdelta <= sdelta_thresh);
       ok = startup_released && loop_closed && not_railed && settled;
       print ok ? "PASS" : "FAIL";
     }')
fi

ROW_FILE="${ROWS_OUT}/${CORNER_ID}.row"
printf '%s\n' "${CORNER_LABEL},${CORNER},${AIDS_LABEL},${TEMP_C},${VDD},${MSENSE_W},${VERDICT},${v_fb_v},${v_sns1_v},${v_sns2_v},${v_det_v},${i_mkfb_a},${DVSNS_V},${v_vref_2ms},${v_vref_3ms},${SETTLE_DELTA},${v_vbeq3_2ms},${v_vbeq3_3ms}" > "${ROW_FILE}"

echo "run_one_point.sh: ${CORNER_ID} -> ${VERDICT} (vref_3ms=${v_vref_3ms:-<none>})"
