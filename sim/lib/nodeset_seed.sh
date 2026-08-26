#!/usr/bin/env bash
# Shared nodeset-seed provenance lookup, sourced (not executed) by any
# experiment script that needs sim/closed-loop-startup's own per-corner
# DC-bias .nodeset seed values -- currently
# sim/closed-loop-psrr/run_pvt_sweep.sh, sim/loop-gain-phase-margin/
# run_pvt_sweep.sh and sim/closed-loop-offset/run_offset_check.sh.
# Extracted in issue #99 because this block was duplicated byte-for-byte
# across the first two scripts (the same shape of duplication
# sim/lib/pvt_preflight.sh was extracted to fix in issue #28); issue #101
# folded in the third (near-duplicate, differing only in its message
# prefix) caller and parameterized that prefix so all three -- and any
# future caller -- can share this file with zero per-caller configuration.
#
# Caller contract:
#   - `set -euo pipefail` before sourcing (this file relies on it: the
#     missing-seed check below `exit 3` directly rather than returning a
#     status, matching the pre-extraction behavior of each script).
#   - Source this AFTER sim/lib/pvt_preflight.sh -- it needs SIM_DIR and
#     REPO_ROOT, which pvt_preflight.sh provides.
#   - Source this file directly from the experiment script's top level (not
#     from inside a function) so `${BASH_SOURCE[1]}` below resolves to the
#     calling script's own path, matching sim/lib/pvt_preflight.sh's own
#     `SCRIPT_DIR` convention.
#
# Provides on return:
#   SEED_CSV, SEED_GIT_SHA -- provenance of the sourced seed record
#   lookup_seed() function -- see its own header comment below
#
# Callers still do their own per-point lookup_seed calls, missing-seed
# failure-point bookkeeping, and records/<id>.md provenance narrative --
# none of that is shared here on purpose (it differs substantively per
# experiment).

# Caller's own basename (e.g. "run_pvt_sweep.sh" or "run_offset_check.sh"),
# derived (not a caller-set contract variable) so every caller's own
# error/log output below is labeled with its own script name rather than a
# hardcoded one.
caller_name="$(basename "${BASH_SOURCE[1]}")"

# Nodeset provenance: the most recent committed sim/closed-loop-startup
# record (see README.md "Nodeset provenance" for why this cross-experiment
# read is necessary and how it is verified per-point, not just trusted).
SEED_CSV="$(ls -1 "${SIM_DIR}/closed-loop-startup/records/"*.csv 2>/dev/null | sort | tail -1 || true)"
if [[ -z "${SEED_CSV}" || ! -f "${SEED_CSV}" ]]; then
  echo "${caller_name}: no sim/closed-loop-startup/records/*.csv found -- this" >&2
  echo "${caller_name}: experiment needs that experiment's DC-bias seed values." >&2
  echo "${caller_name}: run sim/closed-loop-startup/run_pvt_sweep.sh first." >&2
  exit 3
fi
echo "${caller_name}: nodeset seeds sourced from ${SEED_CSV}"
SEED_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- "${SEED_CSV}" 2>/dev/null || echo unknown)"

# lookup_seed CORNER TEMP VDD FIELD
#   Looks up FIELD (fb_final_v, sns1_final_v, sns2_final_v or vref_final_v)
#   from SEED_CSV's row matching corner_label/temp_c/vdd_v, by column name
#   (not position -- robust to that experiment's own CSV schema evolving),
#   requiring status=PASS.
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
