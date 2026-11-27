#!/usr/bin/env bash
# Shared nodeset-seed provenance lookup, sourced (not executed) by the
# experiment scripts that need sim/closed-loop-startup's own per-corner
# DC-bias .nodeset seed values; `git grep nodeset_seed` for the current set.
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
#     REPO_ROOT, which pvt_preflight.sh provides, and its dut_git_sha()
#     for the seed record's own provenance lookup.
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
# The *-tc.csv / *-vs-schematic* companions a previous enrichment derives
# from a record are skipped, and the sort is the C locale's -- the same
# lookup sim/harness/seed_deck.py's newest_seed_csv (#486/#707) and
# sim/harness/pex_ac_runner.sh make. Record ids lead with a UTC timestamp,
# so the last remaining filename in byte order is the newest seed. Under
# en_US.UTF-8 a companion can sort after its seed, so an unfiltered
# `sort | tail -1` can select the companion (#739).
SEED_CSV="$(
  cands=()
  for cand in "${SIM_DIR}/closed-loop-startup/records/"*.csv; do
    [[ -f "${cand}" ]] || continue
    case "${cand##*/}" in *-tc.csv|*-vs-schematic*) continue ;; esac
    cands+=("${cand}")
  done
  if [[ ${#cands[@]} -gt 0 ]]; then
    printf '%s\n' "${cands[@]}" | LC_ALL=C sort | tail -1
  fi
)"
if [[ -z "${SEED_CSV}" || ! -f "${SEED_CSV}" ]]; then
  echo "${caller_name}: no sim/closed-loop-startup/records/*.csv found -- this" >&2
  echo "${caller_name}: experiment needs that experiment's DC-bias seed values." >&2
  echo "${caller_name}: run sim/closed-loop-startup/run_klt_sim.sh first." >&2
  exit 3
fi
echo "${caller_name}: nodeset seeds sourced from ${SEED_CSV}"
SEED_GIT_SHA="$(dut_git_sha "${SEED_CSV}")"

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
