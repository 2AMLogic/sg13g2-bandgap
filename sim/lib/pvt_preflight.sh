#!/usr/bin/env bash
# Shared PVT-sweep preflight, sourced (not executed) by each experiment's
# run_pvt_sweep.sh -- e.g. sim/core-open-loop-bias/run_pvt_sweep.sh and
# sim/startup-trip-point/run_pvt_sweep.sh. Extracted in issue #28 because
# this block was duplicated byte-for-byte across both scripts.
#
# Caller contract:
#   - `set -euo pipefail` before sourcing (this file relies on it: the PDK /
#     ngspice / OSDI checks below `exit 3` directly rather than returning a
#     status, matching the pre-extraction behavior of each script).
#   - Set DUT_NETLIST to the DUT netlist path (relative to the repo root,
#     suitable as a git pathspec) used to derive DUT_GIT_SHA -- the one value
#     that legitimately differs between experiments, e.g.
#     design/netlist/bandgap_core.spice vs design/netlist/bandgap_startup.spice.
#   - Source this file directly from the experiment script's top level (not
#     from inside a function) so `${BASH_SOURCE[1]}` below resolves to the
#     calling script's own path.
#
# Provides on return:
#   SCRIPT_DIR, SIM_DIR, REPO_ROOT, EXPERIMENT_DIR -- path resolution
#   PDK_ROOT, PDK                                  -- via sim/env.sh
#   OSDI_DIR                                       -- OSDI models preflighted
#   DUT_GIT_SHA, REPO_GIT_SHA, RECORD_ID
#   CORNERS_OUT, SNAPSHOTS_OUT, RECORDS_DIR, CSV_OUT, MD_OUT (dirs created)
#   NGSPICE_VERSION
#   total=0, passed=0, failed_points=()
#   run_pvt_point() function -- see its own header comment below
#
# Callers still define their own CSV header, corner-label -> section maps,
# per-point measurement extraction, pass/fail criteria, and records/<id>.md
# narrative -- none of that is shared here on purpose (it differs
# substantively per experiment).

if [[ -z "${DUT_NETLIST:-}" ]]; then
  echo "pvt_preflight.sh: DUT_NETLIST must be set before sourcing this file." >&2
  exit 3
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
EXPERIMENT_DIR="${SCRIPT_DIR}"

# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_pvt_sweep.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see sim/env.sh output above." >&2
  exit 3
fi

if ! command -v ngspice >/dev/null 2>&1; then
  echo "run_pvt_sweep.sh: ngspice not found on PATH." >&2
  exit 3
fi

# Preflight: every PVT-sweep testbench in sim/ instantiates real OSDI-backed
# compact models (PSP103 MOS, r3_cmc resistors, and/or npn13G2 HBTs), so it
# is worthless without the OSDI models. Fail here with an actionable message
# rather than producing dozens of log files full of "Unable to find
# definition of model".
if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_pvt_sweep.sh: OSDI device models missing or not loadable." >&2
  echo "run_pvt_sweep.sh: run  sim/tools/build-osdi.sh  first (see sim/README.md)." >&2
  "${SIM_DIR}/tools/build-osdi.sh" --check >&2 || true
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"

DUT_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- "${DUT_NETLIST}" 2>/dev/null || echo unknown)"
REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"

CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
mkdir -p "${CORNERS_OUT}" "${SNAPSHOTS_OUT}" "${RECORDS_DIR}"

CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.csv"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"

NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

total=0
passed=0
failed_points=()

# run_pvt_point NETLIST LOG
#   Runs one ngspice batch invocation against NETLIST, logging to LOG, then
#   scans the log for the model-load-failure signature every PVT sweep in
#   this repo treats as a hard failure of the point in its own right (a
#   missing/unloadable OSDI model does not always produce a non-zero ngspice
#   exit, so `rc` alone is not sufficient). Extracted in issue #48 because
#   this pair of blocks was duplicated byte-for-byte across all 5
#   run_pvt_sweep.sh scripts (the same failure mode pvt_preflight.sh itself
#   was extracted to fix in issue #28).
#
# Sets on return (caller-visible, not local -- matches this file's own
# "Provides on return" convention above):
#   rc           -- ngspice's exit status
#   model_error  -- 1 if the log matched a model-load-failure signature, else 0
#
# Callers still do their own per-point measurement extraction and pass/fail
# criteria from LOG after calling this -- that differs per experiment and
# stays in each run_pvt_sweep.sh.
run_pvt_point() {
  local netlist="$1"
  local log="$2"

  set +e
  ngspice -b "${netlist}" > "${log}" 2>&1
  rc=$?
  set -e

  model_error=0
  if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type" "${log}"; then
    model_error=1
  fi
}
