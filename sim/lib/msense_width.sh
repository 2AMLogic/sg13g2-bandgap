#!/usr/bin/env bash
# Shared MSENSE-width extraction, sourced (not executed) by the experiment
# scripts under sim/*/ that bake the live XMSENSE transistor's w= value into
# a record; `git grep read_msense_width` for the current set. Extracted in
# issue #105 because this 5-line grep/parse block was duplicated
# byte-for-byte across all eight -- the same shape of duplication
# sim/lib/pvt_preflight.sh (#28) and sim/lib/nodeset_seed.sh (#99/#101)
# were extracted to fix.
#
# Caller contract:
#   - `set -euo pipefail` before sourcing (this file relies on it: see
#     read_msense_width's own header comment below for exactly how).
#   - Needs REPO_ROOT -- set it yourself, or source this after
#     sim/lib/pvt_preflight.sh, which provides it.
#   - Call `read_msense_width <netlist>` as a plain statement, NOT inside a
#     command substitution (i.e. NOT `X="$(read_msense_width ...)"`) --
#     command substitution runs in a subshell that disables `set -e`
#     propagation for the commands inside this function on bash < 4.4
#     without `shopt -s inherit_errexit`, which would silently change the
#     pre-extraction behavior on a malformed/missing w= (see below).
#   - Two call shapes are supported: source this file at the experiment
#     script's top level and call `read_msense_width` there (e.g.
#     sim/closed-loop-offset/run_offset_check.sh:38, a plain call, and
#     sim/closed-loop-iq/run_klt_sim.sh:37, an `&&` list), or source and call
#     it from inside a shared runner function
#     (sim/harness/cmos5l_runner.sh's cmos5l_main does both, with the call
#     at :88 a plain call that sim/sg13cmos5l-closed-loop-startup/
#     run_klt_sim.sh reaches by delegation). Either way
#     the diagnostic prefix -- `${BASH_SOURCE[1]}` inside
#     read_msense_width -- names the file containing the call expression,
#     not the file where the `source` statement ran, matching
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
#   this file's own header comment above) to the parsed width including its
#   unit suffix (w=7u gives MSENSE_W=7u), or prints a message naming the immediate calling file and
#   `exit 3`s if XMSENSE's w= cannot be parsed. The name comes from
#   `${BASH_SOURCE[1]}` (matching sim/lib/nodeset_seed.sh's caller_name
#   convention): the file containing the call expression, not the file where
#   the `source` statement ran -- moving the call into a shared runner
#   function makes the runner, not the bench, the named file.
#
#   Distinct failure paths on a malformed netlist (no XMSENSE line, or an
#   XMSENSE line with no w= field), all under the caller's `set -euo
#   pipefail`; a parseable w= returns 0 with MSENSE_W set in every shape:
#     - Plain statement (function invoked as a simple command, as inside
#       sim/harness/cmos5l_runner.sh's cmos5l_main): this function runs in
#       the caller's own shell, the failing `grep`/pipe assignment itself
#       is subject to `set -e` exactly as pre-extraction, and the script
#       exits immediately -- status 1, nothing on stderr.
#     - Non-final command of an `&&` list (e.g. the
#       `( cd "${REPO_ROOT}" && read_msense_width ... && printf ... )`
#       subshell in sim/closed-loop-iq/run_klt_sim.sh:37, or the same
#       shape inside a shared runner function): bash suppresses errexit inside a function invoked there,
#       so the failed assignment merely leaves MSENSE_W empty and control
#       reaches the explicit "could not parse" message below -- status 3,
#       stderr prefixed with the file containing the call expression
#       (run_klt_sim.sh for the bench's own list; the runner, e.g.
#       pex_runner.sh, once the list lives in it).
#   Which path fires is decided by bash's errexit rules at the call site,
#   not by anything in this function. Preserving the assignment-then-check
#   ordering (rather than "fixing" it to always print the message) is what
#   keeps this extraction's observable behavior byte-for-byte identical to
#   the pre-extraction block.
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
