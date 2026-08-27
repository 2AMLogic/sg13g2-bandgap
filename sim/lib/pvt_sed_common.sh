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
#   common_pvt_sed_args() function -- see its own header comment below
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
