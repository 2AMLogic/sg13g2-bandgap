#!/usr/bin/env bash
# sg13g2-bandgap -- trim-code axis of loop phase margin through `klt sim`
# (issue #271). Companion to run_pvt_sweep.sh, which measures the 45-point
# PVT grid at the default trim code (128) only.
#
#   sim/loop-gain-phase-margin/run_klt_trim_axis.sh --anchor
#       ONE unit, local engine: code 128 at wcs/125C/2.97V on the bench's own
#       dec-30 grid -- the sanity anchor against
#       records/20261001-085806-e5507b2.csv. Prints the comparison; writes no
#       record. (A single corner is what the dispatch hosts allow locally.)
#
#   sim/loop-gain-phase-margin/run_klt_trim_axis.sh --batch
#       The full plan (tools/klt_trim_axis.py PLAN: 9 requests, one per PVT
#       point x AC grid, each sweeping the trim code) submitted to 2am's EDA
#       batch fleet -- one fleet job per request -- then minted into an
#       append-only record. Requires a `klt` carrying the batch backend
#       (0.6.0+) and 2am's batch-fleet-provision.sh (KLT_BATCH_PROVISION_SCRIPT).
#
#   sim/loop-gain-phase-margin/run_klt_trim_axis.sh --pvt
#       (issue #289) The bench's own 45-point PVT grid (5 process x 3
#       temperature x 3 supply) at trim code 128, solve-quality-gated,
#       through the SAME fleet path as --batch: one `klt sim --backend batch`
#       request per PVT point (the .nodeset seed is per point), then minted
#       into an append-only record (tools/klt_trim_axis.py --plan pvt).
#       Same requirements and environment as --batch.
#
# Never widen --anchor into a grid on a dispatch host: multi-unit runs go to
# the fleet (sim/harness/README.md).
#
# Environment: KLT_TRIM_AXIS_WORK (scratch dir, default mktemp),
# KLT_TRIM_AXIS_ONLY (space-separated subset of point names, batch mode),
# KLT_BATCH_PROVISION_SCRIPT, KLT_TRIM_AXIS_BATCH_PDK_ROOT (default /opt/pdk).
set -euo pipefail

MODE="${1:-}"
case "${MODE}" in
  --anchor|--batch|--pvt) ;;
  *) echo "usage: run_klt_trim_axis.sh --anchor|--batch|--pvt" >&2; exit 2 ;;
esac

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${EXPERIMENT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
TOOL="${EXPERIMENT_DIR}/tools/klt_trim_axis.py"
KLT_BIN="${KLT_TRIM_AXIS_KLT:-klt}"
PROVISION="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"
WORK="${KLT_TRIM_AXIS_WORK:-$(mktemp -d -t sg13g2-trim-axis-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_klt_trim_axis.sh: work dir ${WORK}"

# shellcheck source=../env.sh
source "${SIM_DIR}/env.sh"

if [[ "${MODE}" == "--anchor" ]]; then
  if [[ -z "${PDK_ROOT:-}" ]] || ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
    echo "run_klt_trim_axis.sh: local anchor needs a resolvable PDK + built OSDI models" >&2
    exit 3
  fi
  # KLT_TRIM_AXIS_ANCHOR_DECK=np (default) runs the CONTROL deck -- the bench's
  # own matrix, the one that should reproduce the committed 36.3046 deg;
  # =probe runs the op-probe deck the grid's probe rows use.
  point="wcs_125c_2.97v_bench"
  [[ "${KLT_TRIM_AXIS_ANCHOR_DECK:-np}" == "np" ]] && point="${point}_np"
  python3 "${TOOL}" prepare --work "${WORK}" --target local --only "${point}" --codes 128
  # `--backend local` explicit: the dispatch hosts export KLT_SIM_BACKEND=batch,
  # and a one-unit anchor is the case meant to stay local.
  "${KLT_BIN}" sim "${WORK}/${point}/request.json" --backend local --format json \
    -o "${WORK}/${point}/artifacts" > "${WORK}/${point}/report.json" || true
  python3 "${TOOL}" anchor --report "${WORK}/${point}/report.json"
  exit 0
fi

PLAN_NAME=characterization
[[ "${MODE}" == "--pvt" ]] && PLAN_NAME=pvt

[[ -x "${PROVISION}" ]] || { echo "run_klt_trim_axis.sh: no provision script at ${PROVISION}" >&2; exit 3; }
# shellcheck disable=SC2086
python3 "${TOOL}" prepare --work "${WORK}" --target batch --plan "${PLAN_NAME}" \
  --batch-pdk-root "${KLT_TRIM_AXIS_BATCH_PDK_ROOT:-/opt/pdk}" \
  --provision-script "${PROVISION}" ${KLT_TRIM_AXIS_ONLY:+--only ${KLT_TRIM_AXIS_ONLY}} \
  > "${WORK}/points.txt"

# One fleet job per request. The submitting processes only upload, launch and
# poll S3 -- no simulator runs on this host. At most KLT_TRIM_AXIS_CONCURRENCY
# (default 3) are in flight at once: the fleet's `launch` REFUSES (does not
# queue) a job that would exceed its shared BATCH_MAX_CONCURRENT_INSTANCES,
# and other repos share that cap. A point whose report.json already parses
# with corners in it is skipped, so a re-run after a refused launch only
# resubmits what is missing (same KLT_TRIM_AXIS_WORK).
have_report() {
  python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r.get("corners") else 1)' \
    "$1" 2>/dev/null
}
MAXJ="${KLT_TRIM_AXIS_CONCURRENCY:-3}"
while read -r point; do
  have_report "${WORK}/${point}/report.json" && continue
  while [[ "$(jobs -rp | wc -l)" -ge "${MAXJ}" ]]; do wait -n || true; done
  ( "${KLT_BIN}" sim "${WORK}/${point}/request.json" --backend batch --format json \
      -o "${WORK}/${point}/artifacts" > "${WORK}/${point}/report.json" \
      2> "${WORK}/${point}/submit.stderr" ; echo $? > "${WORK}/${point}/submit.rc" ) &
done < "${WORK}/points.txt"
wait || true

missing=0
for point in $(cat "${WORK}/points.txt"); do
  echo "  ${point}: klt exit $(cat "${WORK}/${point}/submit.rc" 2>/dev/null || echo '?')"
  have_report "${WORK}/${point}/report.json" || missing=$((missing + 1))
done
if [[ "${missing}" -gt 0 && -z "${KLT_TRIM_AXIS_ALLOW_PARTIAL:-}" ]]; then
  echo "run_klt_trim_axis.sh: ${missing} point(s) returned no report -- see */submit.stderr;" >&2
  echo "  re-run with the same KLT_TRIM_AXIS_WORK to resubmit only those. No record minted." >&2
  exit 4
fi

RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
python3 "${TOOL}" record --work "${WORK}" --record-id "${RECORD_ID}" --plan "${PLAN_NAME}"
