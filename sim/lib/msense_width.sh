#!/usr/bin/env bash
# Shared MSENSE-width extraction, sourced (not executed) by any experiment
# script that needs the live XMSENSE transistor's w= value from a startup
# netlist -- currently sim/closed-loop-iq/run_pvt_sweep.sh,
# sim/closed-loop-psrr/run_pvt_sweep.sh,
# sim/closed-loop-vref-pvt/run_pvt_sweep.sh,
# sim/closed-loop-startup/run_pvt_sweep.sh,
# sim/loop-gain-phase-margin/run_pvt_sweep.sh,
# sim/startup-core-handover/run_pvt_sweep.sh,
# sim/closed-loop-offset/run_offset_check.sh and
# sim/sg13cmos5l-closed-loop-startup/run_pvt_sweep.sh (the only one of the
# eight reading design/sg13cmos5l/netlist/bandgap_startup.spice instead of
# design/netlist/bandgap_startup.spice). Extracted in issue #105 because this
# 5-line grep/parse block was duplicated byte-for-byte across all eight --
# the same shape of duplication sim/lib/pvt_preflight.sh (#28) and
# sim/lib/nodeset_seed.sh (#99/#101) were extracted to fix.
#
# Caller contract:
#   - `set -euo pipefail` before sourcing (this file relies on it: see
#     read_msense_width's own header comment below for exactly how).
#   - Source this AFTER sim/lib/pvt_preflight.sh -- it needs REPO_ROOT, which
#     pvt_preflight.sh provides.
#   - Call `read_msense_width <netlist>` as a plain statement, NOT inside a
#     command substitution (i.e. NOT `X="$(read_msense_width ...)"`) --
#     command substitution runs in a subshell that disables `set -e`
#     propagation for the commands inside this function on bash < 4.4
#     without `shopt -s inherit_errexit`, which would silently change the
#     pre-extraction behavior on a malformed/missing w= (see below).
#   - Source this file directly from the experiment script's top level (not
#     from inside a function) so `${BASH_SOURCE[1]}` inside
#     read_msense_width resolves to the calling script's own path, matching
#     sim/lib/pvt_preflight.sh's SCRIPT_DIR and sim/lib/nodeset_seed.sh's
#     caller_name conventions.
#
# Provides on return:
#   read_msense_width() function -- see its own header comment below
#
# Callers still decide what to do with MSENSE_W after the call (bake it into
# a CSV header, a testbench template substitution, a records/<id>.md
# narrative line) -- none of that is shared here on purpose (it differs
# per experiment only in that each already handles MSENSE_W independently).

# read_msense_width NETLIST
#   Reads NETLIST's (a repo-relative path, resolved against REPO_ROOT)
#   XMSENSE line and parses its w= value. Sets MSENSE_W (caller-visible, not
#   local -- matches sim/lib/pvt_preflight.sh's run_pvt_point() convention of
#   this file's own header comment above) to the parsed width (without the
#   trailing "u"), or prints a message naming the caller's own script (via
#   `${BASH_SOURCE[1]}`, matching sim/lib/nodeset_seed.sh's caller_name
#   convention) and `exit 3`s if XMSENSE's w= cannot be parsed.
#
#   Called as a plain statement (see caller contract above), this function
#   runs in the caller's own shell, so a failing `grep`/pipe inside it is
#   still subject to the caller's `set -euo pipefail` exactly as it was
#   pre-extraction: a missing XMSENSE line, or an XMSENSE line with no w=
#   field, fails the grep/pipe assignment itself and the script exits
#   immediately via `set -e` -- the explicit "could not parse" message below
#   is reachable only if a later maintenance change relaxes that pipeline
#   (e.g. drops -o from grep) to where it can produce an empty MSENSE_W
#   without itself failing first. Preserving this exact ordering (rather
#   than "fixing" it to always print the message) is what keeps this
#   extraction's observable behavior byte-for-byte identical to the
#   pre-extraction block.
read_msense_width() {
  local netlist="$1"
  local caller_name
  caller_name="$(basename "${BASH_SOURCE[1]}")"

  local msense_line
  msense_line="$(grep -E '^XMSENSE ' "${REPO_ROOT}/${netlist}")"
  MSENSE_W="$(echo "${msense_line}" | grep -oE 'w=[0-9.]+u' | head -1 | sed -e 's/w=//')"
  if [[ -z "${MSENSE_W}" ]]; then
    echo "${caller_name}: could not parse XMSENSE's w= from ${netlist}" >&2
    exit 3
  fi
}
