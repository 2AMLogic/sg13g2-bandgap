#!/usr/bin/env bash
# Shared PVT-sweep sed-template-substitution args, sourced (not executed) by
# every experiment's run_pvt_sweep.sh -- all 14 scripts under sim/*/
# render their per-point netlist from a .spice.tmpl via a `sed -e ... -e ...`
# call, and six of those `-e` clauses (@@PDK_ROOT@@, @@PDK@@, @@OSDI_DIR@@,
# @@TEMP_C@@, @@VDD@@, @@CORNER_LABEL@@) were byte-identical, token order
# included, across every one of them. Extracted in issue #108 because this
# was the same shape of duplication sim/lib/pvt_preflight.sh (#28/#103) and
# sim/lib/msense_width.sh (#105) were extracted to fix.
#
# Caller contract:
#   - Source this AFTER sim/lib/pvt_preflight.sh -- it needs PDK_ROOT, PDK
#     and OSDI_DIR, which pvt_preflight.sh provides.
#   - Source this file directly from the experiment script's top level (its
#     one function, unlike pvt_preflight.sh's and msense_width.sh's helpers,
#     does not itself need `${BASH_SOURCE[1]}` -- but this matches the
#     sourcing convention of every other sim/lib/*.sh file).
#   - Call `common_pvt_sed_args "${temp}" "${vdd}" "${corner}"` once per PVT
#     point, immediately before the `sed` invocation it feeds, then splice
#     `"${COMMON_SED_ARGS[@]}"` into that `sed` call alongside the script's
#     own remaining, experiment-specific `-e` clauses. Token order between
#     COMMON_SED_ARGS and a script's own `-e` clauses does not matter: every
#     `@@...@@` placeholder is a distinct literal string, so `sed` applies
#     all substitutions independently regardless of `-e` order.
#
# Provides on return:
#   common_pvt_sed_args() function  -- see its own header comment below
#   next_corner_id() function       -- see its own header comment below
#   extract_measure() function      -- see its own header comment below
#   extract_op_voltage() function   -- see its own header comment below
#   abs_diff() function             -- see its own header comment below
#   is_new_max() function           -- see its own header comment below
#   latest_records_csv() function   -- see its own header comment below
#
# Callers still own the rest of their `sed` call (their own script-specific
# tokens like @@HBT_SECTION@@, @@MSENSE_W@@, @@LAYOUT_GIT_SHA@@, seed
# tokens, or @@VDD_HALF@@/@@VDD_OFF@@) and the TEMPLATE/netlist paths --
# none of that is shared here on purpose (it differs substantively per
# experiment).

# common_pvt_sed_args TEMP_C VDD CORNER_LABEL
#   Populates COMMON_SED_ARGS (caller-visible, not local -- matches
#   sim/lib/pvt_preflight.sh's run_pvt_point() convention of this file's own
#   header comment above) with the six `-e` clauses shared by every PVT
#   sweep's template-render `sed` call: the three PDK/build-environment
#   substitutions (@@PDK_ROOT@@, @@PDK@@, @@OSDI_DIR@@, read from PDK_ROOT,
#   PDK and OSDI_DIR -- all three set by sim/lib/pvt_preflight.sh) and the
#   three per-point substitutions (@@TEMP_C@@, @@VDD@@, @@CORNER_LABEL@@,
#   from this function's own TEMP_C/VDD/CORNER_LABEL arguments).
common_pvt_sed_args() {
  local temp_c="$1" vdd="$2" corner_label="$3"
  COMMON_SED_ARGS=(
    -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g"
    -e "s|@@PDK@@|${PDK}|g"
    -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g"
    -e "s|@@TEMP_C@@|${temp_c}|g"
    -e "s|@@VDD@@|${vdd}|g"
    -e "s|@@CORNER_LABEL@@|${corner_label}|g"
  )
}

# next_corner_id CORNER TEMP_C VDD
#   Sets corner_id/netlist/log (caller-visible, not local -- matches this
#   file's own common_pvt_sed_args() and sim/lib/pvt_preflight.sh's
#   run_pvt_point() convention) for the next PVT point and increments
#   `total` (set to 0 by sim/lib/pvt_preflight.sh, sourced first per that
#   file's caller contract). Extracted in issue #122 because this exact
#   4-line block -- `total=$((total + 1))` plus the corner_id/netlist/log
#   assignments it feeds -- was byte-identical, confirmed by hashing each
#   script's own copy, across all 14 run_pvt_sweep.sh scripts under sim/*/,
#   as the first statement in each script's own per-point loop body (most
#   callers follow it immediately with common_pvt_sed_args(); a few instead
#   compute their own per-point locals like vdd_half/vdd_off first -- either
#   way, this call must come first in the loop body, since it is what
#   defines the point's own corner_id/netlist/log for everything after it).
#
#   CORNER_ID's format string (`${corner}_${temp}c_${vdd}v`) and NETLIST/LOG's
#   paths (under SNAPSHOTS_OUT/CORNERS_OUT, both set by
#   sim/lib/pvt_preflight.sh) become part of the on-disk netlist/log
#   filenames and CSV/record output every committed evidence record already
#   references, so this call must be made with the exact same CORNER/TEMP_C/
#   VDD values, in the exact same per-point loop position, every caller's
#   own pre-extraction inline block used.
next_corner_id() {
  local corner="$1" temp_c="$2" vdd="$3"
  total=$((total + 1))
  corner_id="${corner}_${temp_c}c_${vdd}v"
  netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
  log="${CORNERS_OUT}/${corner_id}.log"
}

# extract_measure NAME LOGFILE
#   Prints the value ngspice's `.measure` directive NAME wrote to LOGFILE --
#   the first matching line's third whitespace-delimited field (ngspice's own
#   `.measure` output format: `<name> = <value>` or `<name> = <value> at=...`,
#   so field 3 is always the value regardless of which form printed). Extracted
#   in issue #196 because this exact
#   `grep -E "^${1}" "${2}" | head -1 | awk '{print $3}' || true` one-liner
#   was duplicated 66 times across 10 run_pvt_sweep.sh scripts under sim/*/ --
#   same shape of duplication next_corner_id() above (#122) and every other
#   sim/lib/*.sh helper this file's own header comment lists was extracted to
#   fix.
#
#   The trailing `|| true` is the one behavioral subtlety worth stating once,
#   here, instead of re-explaining it at each of the 66 call sites (as roughly
#   a third of them used to, with drifting wording): a PVT corner that fails
#   to converge (a marginal corner hitting a near-singular instant on the vdd
#   ramp, for example) leaves ngspice's `.measure` line for NAME unprinted, so
#   `grep` finds no match and exits 1. Under the caller's own
#   `set -euo pipefail`, an unguarded `grep` failure inside a bare
#   `x=$(...)` assignment would abort the ENTIRE sweep script on the first
#   non-convergent corner, silently losing every other point's evidence --
#   worse than recording that one corner as FAIL and continuing. `|| true`
#   lets the pipeline report success regardless, so a non-match simply
#   resolves to an empty string; every caller's own downstream `-z` check
#   already treats that empty value as this point's verdict going to FAIL.
#
#   NAME is spliced into a `grep -E` pattern unquoted-anchored (`^${1}`), so
#   pass a literal `.measure` name (e.g. `v_fb_v`), not caller-controlled or
#   regex-metacharacter-bearing input.
extract_measure() {
  local name="$1" logfile="$2"
  grep -E "^${name}" "${logfile}" | head -1 | awk '{print $3}' || true
}

# extract_op_voltage NODE LOGFILE
#   Prints the value ngspice's `.op` analysis wrote to LOGFILE for node
#   NODE -- the first matching line's second `=`-delimited field, whitespace
#   stripped (ngspice's own `.op` node-voltage output format:
#   `v(node) = <value>`, so field 2 of an `awk -F'='` split is the value,
#   with `tr -d ' '` needed because that field carries a leading space `.op`
#   always emits before the value). Extracted in issue #198 because this
#   exact `grep -E "^v\(${1}\)" "${2}" | head -1 | awk -F'=' '{print $2}' |
#   tr -d ' ' || true` idiom was duplicated, comment included, across 4
#   run_pvt_sweep.sh scripts under sim/*/ -- same shape of duplication
#   extract_measure() above (#196/#197) was extracted to fix, but for `.op`
#   node-voltage lines (`v(node)=...`) rather than `.measure` lines, a
#   distinct output format needing its own parse (`awk -F'='` + `tr -d ' '`
#   here vs. plain `awk '{print $3}'` there).
#
#   The trailing `|| true` carries the identical rationale extract_measure()
#   documents above for the same construct: a PVT corner whose `.op` fails
#   to converge leaves NODE's voltage line unprinted, so `grep` finds no
#   match and exits 1, and under the caller's own `set -euo pipefail` an
#   unguarded failure inside a bare `x=$(...)` assignment would abort the
#   entire sweep on the first non-convergent corner. `|| true` lets the
#   pipeline report success regardless, resolving a non-match to an empty
#   string that every caller's own downstream `-z` check already treats as
#   that point's verdict going to FAIL.
#
#   NODE is spliced into a `grep -E` pattern unquoted-anchored
#   (`^v\(${1}\)`), so pass a literal node name (e.g. `fb`, `fb_load`), not
#   caller-controlled or regex-metacharacter-bearing input. NODE need not
#   match the caller's own variable name it assigns the result to -- e.g.
#   `sim/loop-gain-phase-margin/run_pvt_sweep.sh` calls
#   `fb_op=$(extract_op_voltage fb_load "${log}")`, extracting node
#   `fb_load` into a variable still named `fb_op` to match its sibling
#   scripts' own `fb_op` naming for the same CSV column.
extract_op_voltage() {
  local node="$1" logfile="$2"
  grep -E "^v\(${node}\)" "${logfile}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true
}

# abs_diff A B
#   Prints |A - B|. Extracted in issue #200 because this exact
#   `awk -v a="$a" -v b="$b" 'BEGIN{d=a-b; print (d<0)?-d:d}'` idiom was
#   duplicated across the three `*-pex` PVT-sweep scripts' cross-bench
#   "-vs-*.csv" comparison blocks -- both as a diff of two raw measurements
#   (e.g. `dvsns_v`/`settle_delta` in closed-loop-vref-pvt-pex, `op_delta` in
#   closed-loop-psrr-pex/closed-loop-zout-pex) and, via `abs_diff d 0`, as
#   the plain-absolute-value form (`awk -v d="$d" 'BEGIN{print
#   (d<0)?-d:d}'`) those same scripts used on an already-computed delta
#   (`absd`/`absdc`/`absmin`) -- one function covers both call shapes rather
#   than shipping a second single-argument `abs()` helper.
abs_diff() {
  local a="$1" b="$2"
  awk -v a="${a}" -v b="${b}" 'BEGIN{d=a-b; print (d<0)?-d:d}'
}

# is_new_max CANDIDATE CURRENT
#   Prints `1` if CANDIDATE > CURRENT, else `0`. Extracted in issue #200
#   alongside abs_diff() because this exact `awk -v a="$a" -v b="$b"
#   'BEGIN{print (a>b)?1:0}'` idiom was duplicated across the same three
#   `*-pex` scripts' running-max tracking of their largest per-point
#   cross-bench delta (`max_abs_delta`, `max_abs_dc_delta`,
#   `max_abs_min_delta`).
is_new_max() {
  local candidate="$1" current="$2"
  awk -v a="${candidate}" -v b="${current}" 'BEGIN{print (a>b)?1:0}'
}

# latest_records_csv DIR [EXCLUDE_GLOB]
#   Prints the path of the newest `*.csv` file directly under DIR (not
#   recursive -- `find -maxdepth 1`), or an empty string if DIR doesn't
#   exist or contains none ("newest" by filename sort, matching every
#   caller's own `RECORD_ID`-prefixed timestamp-sortable naming). When
#   EXCLUDE_GLOB is given, files matching it are excluded first (used by
#   closed-loop-vref-pvt-pex to skip its sibling `-tc.csv` summary file).
#   Extracted in issue #200 because this exact `find "$dir" -maxdepth 1
#   -name '*.csv' [! -name EXCLUDE] 2>/dev/null | sort | tail -1 || true`
#   idiom -- used by each `*-pex` script to locate its own cross-bench
#   comparison target (the schematic or sibling-PEX experiment's most
#   recent record) -- was duplicated, `|| true` included, across all three.
latest_records_csv() {
  local dir="$1" exclude="${2:-}"
  if [[ -n "${exclude}" ]]; then
    find "${dir}" -maxdepth 1 -name '*.csv' ! -name "${exclude}" 2>/dev/null | sort | tail -1 || true
  else
    find "${dir}" -maxdepth 1 -name '*.csv' 2>/dev/null | sort | tail -1 || true
  fi
}
