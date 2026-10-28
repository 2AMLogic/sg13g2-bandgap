#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-trim-mc (the trim-domain mismatch Monte
# Carlo behind DR-0011's trimmed +/-0.5% line, kept by DR-0014) on the `klt sim`
# decks transport (issue #423, Part of #412).
#
#   sim/closed-loop-vref-trim-mc/run_klt_sim.sh --sanity   # 2 local decks vs the committed record
#   sim/closed-loop-vref-trim-mc/run_klt_sim.sh --batch    # N draws x 4 points x 6 decks, on the fleet
#   sim/closed-loop-vref-trim-mc/run_klt_sim.sh --record   # mint evidence (KLT_SIM_WORK=<batch dir>)
#
# KLT_SIM_N (default 300, >= 300 per the issue's Test Plan) and KLT_SIM_SEED
# (default 20260930) size the campaign. Each draw's six decks are the template
# run_trim_mc.sh rendered (testbench/*.spice.tmpl, unchanged), shipped
# byte-for-byte by klt's `decks` requests; sim/harness/trim_mc_klt.py owns the
# rest. Two stages, because stage 2 depends on stage 1:
#   1. FIT     per (point, draw): codes 0/1/255 at 27 C        -> klt sim --batch-set
#   2. code*   computed HERE from the fit logs (the script's formula)
#   3. VERIFY  per (point, draw): code* at -40/27/125 C        -> klt sim --batch-set
#   4. assemble the per-draw CSV, digest and negative-control gate; a failed or
#      timed-out deck is a verify-FAIL row, a unit that never came back refuses
#      the whole record (a partial draw set is never recorded).
# The old run_trim_mc.sh loops `ngspice -b` and is kept as the point-definition
# reference only: it must not be run as a grid on a dispatch host.
#
# SANITY GATE. Two draw-0/code-0/27 C decks run on the local backend (two units,
# not a grid): negctrl must land on the committed record's fit0 (the gate: no
# mismatch draw, so it is deterministic across hosts); nominal is printed against
# its committed value but is informational -- a `.options rndseed` mismatch draw
# comes from the host's RNG, and the committed record was produced on another
# platform. A host whose ngspice cannot load the SG13G2 OSDI models sets
# KLT_SIM_SANITY_BACKEND=batch: still two units, on the fleet, never a local grid.
#
# A deck-list request refuses `--wait-for-capacity`; the capacity wait rides the
# request (batch.capacity_wait_s, KLT_SIM_CAPACITY_WAIT_S, default 1800). A
# refused or failed submit is reported and stops the run: there is NO local
# fallback. Re-run with the same KLT_SIM_WORK to resume (klt --resume skips units
# whose result tree already verifies).
set -euo pipefail

# shellcheck disable=SC2034  # EXP/STEM are read by pex_runner.sh
EXP="closed-loop-vref-trim-mc"
STEM="trim_mc"
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"

TM_PY="${HARNESS_DIR}/trim_mc_klt.py"
TEMPLATE="${EXP_DIR}/testbench/tb_closed_loop_vref_trim_mc.spice.tmpl"
N="${KLT_SIM_N:-300}"
SEED="${KLT_SIM_SEED:-20260930}"
BATCH_OSDI_ROOT="${KLT_SIM_BATCH_OSDI_ROOT:-/opt/pdk}"
BATCH_OSDI_DIR="${BATCH_OSDI_ROOT}/${PDK}/libs.tech/ngspice/osdi"
CAPACITY_WAIT_S="${KLT_SIM_CAPACITY_WAIT_S:-1800}"
SEED_CSV="$(ls -1 "${SIM_DIR}/closed-loop-startup/records/"*.csv | sort | tail -1)"
ANCHOR_CSV="${EXP_DIR}/records/20260930-232155-affdefe-draws.csv"   # the committed #229 record
ANCHOR_SEED=20260930

# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
if [[ "${MODE}" == "--record" && -f "${WORK}/msense_w.txt" ]]; then
  MSENSE_W="$(<"${WORK}/msense_w.txt")"
else
  ( cd "${REPO_ROOT}" && read_msense_width "design/netlist/bandgap_startup.spice" \
      && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
  MSENSE_W="$(<"${WORK}/msense_w.txt")"
fi

dut_git_sha() { git -C "${REPO_ROOT}" log -1 --format=%h -- "$1" 2>/dev/null || echo unknown; }
DUT_SHA="core=$(dut_git_sha design/netlist/bandgap_core.spice) trim=$(dut_git_sha design/netlist/bandgap_trim.spice) amp=$(dut_git_sha design/netlist/bandgap_amp.spice) startup=$(dut_git_sha design/netlist/bandgap_startup.spice) seeds=${SEED_CSV##*/}@$(dut_git_sha "${SEED_CSV#"${REPO_ROOT}/"}")"
SUBMIT_KLT="${KLT_SIM_SUBMIT_KLT:-${KLT_BIN}}"

# tm_prepare STAGE [extra trim_mc_klt.py prepare args...]
tm_prepare() {
  local stage="$1"; shift
  python3 "${TM_PY}" prepare --stage "${stage}" --work "${WORK}" --template "${TEMPLATE}" \
    --seed-csv "${SEED_CSV}" --msense-w "${MSENSE_W}" --dut-sha "${DUT_SHA}" --pdk "${PDK}" \
    --local-pdk-root "${PDK_ROOT}" --local-osdi-dir "${OSDI_DIR}" \
    --batch-pdk-root "${BATCH_PDK_ROOT}" --batch-osdi-dir "${BATCH_OSDI_DIR}" \
    --provision "${BATCH_PROVISION_SCRIPT}" --capacity-wait-s "${CAPACITY_WAIT_S}" \
    --seed "${SEED}" --n "${N}" "$@"
}

tm_sanity() {
  local backend="${KLT_SIM_SANITY_BACKEND:-local}"
  rm -rf "${WORK}/artifacts-sanity"
  tm_prepare sanity --sanity-backend "${backend}" --seed "${ANCHOR_SEED}"
  ( cd "${WORK}" && "${SUBMIT_KLT}" sim request-sanity.json --backend "${backend}" \
      --format json -o artifacts-sanity > report-sanity.json ) || true
  python3 "${TM_PY}" check-sanity --artifacts "${WORK}/artifacts-sanity" \
    --anchor-csv "${ANCHOR_CSV}" --seed "${ANCHOR_SEED}"
}

# tm_stage STAGE: submit every request-STAGE-*.json as one fleet set.
tm_stage() {
  local stage="$1" rc=0
  echo "run_klt_sim.sh: ${stage} stage -- $(ls "${WORK}"/request-"${stage}"-*.json | wc -l) requests on the fleet"
  ( cd "${WORK}" && "${SUBMIT_KLT}" sim --batch-set request-"${stage}"-*.json --max-in-flight 4 \
      --resume --format json -o "artifacts-${stage}" > "report-${stage}.json" \
      2> >(tee -a klt-stderr.log >&2) ) || rc=$?
  # Unit-level failures (timeouts, engine errors) are verify-FAIL rows; a request the
  # fleet refused or never ran is a submit failure: report it, never run it locally.
  python3 - "${WORK}/report-${stage}.json" "${rc}" <<'PY'
import json, pathlib, sys
path, rc = pathlib.Path(sys.argv[1]), int(sys.argv[2])
try:
    rep = json.loads(path.read_text())
except ValueError:
    raise SystemExit(f"run_klt_sim.sh: batch submit failed (klt exit {rc}), no report: {path}\n"
                     "  no local fallback -- fix the cause and re-run with the same KLT_SIM_WORK to resume")
# exit_code 4 is "some unit errored or timed out" (a verify-FAIL row, below); anything else
# nonzero, an error envelope, or a refusal code means the request itself did not run.
bad = [r for r in rep.get("requests", []) if r.get("error") or r.get("exit_code") not in (0, 4)]
if rep.get("refused_codes") or bad:
    raise SystemExit(f"run_klt_sim.sh: batch submit failed: refused_codes={rep.get('refused_codes')} "
                     f"requests={[(r['request'], r.get('exit_code'), r.get('error')) for r in bad][:3]}\n"
                     "  no local fallback -- re-run with the same KLT_SIM_WORK to resume")
PY
}

tm_batch() {
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  echo "run_klt_sim.sh: sanity gate before dispatch"
  tm_sanity

  tm_prepare fit
  tm_stage fit
  python3 "${TM_PY}" codes --work "${WORK}" --artifacts "${WORK}/artifacts-fit" --n "${N}"
  tm_prepare verify --codes "${WORK}/codes.json"
  tm_stage verify

  python3 "${TM_PY}" assemble --work "${WORK}" --artifacts "${WORK}/artifacts-verify" \
    --fit-artifacts "${WORK}/artifacts-fit" --template "${TEMPLATE}" --seed-csv "${SEED_CSV}" \
    --msense-w "${MSENSE_W}" --dut-sha "${DUT_SHA}" --pdk "${PDK}" \
    --local-pdk-root "${PDK_ROOT}" --local-osdi-dir "${OSDI_DIR}" \
    --seed "${SEED}" --n "${N}" --klt-version "${KLT_VERSION_DECL}" --job-log "${WORK}/klt-stderr.log" \
    --draws-out "${WORK}/draws.csv" --report-out "${WORK}/report-assembled.json"
  echo "run_klt_sim.sh: assembled report at ${WORK}/report-assembled.json"
  echo "                 mint evidence with: KLT_SIM_WORK=${WORK} KLT_SIM_N=${N} run_klt_sim.sh --record"
}

tm_record() {
  local rid
  rid="$(date -u +%Y%m%d-%H%M%S)-$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
  python3 "${TM_PY}" spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
    --msense-w "${MSENSE_W}" --n "${N}" -o "${WORK}/record-spec.json"
  # The adapter exits 1 when a point is graded FAIL (the 3-sigma claim gate fails at the
  # mismatch points, as in the committed #229 record): the record is still minted.
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-assembled.json" \
      --spec "${WORK}/record-spec.json" \
      --experiment "${EXP_DIR}" --record-id "${rid}" ) || [[ -f "${EXP_DIR}/records/${rid}.md" ]]
  cp "${WORK}/draws.csv" "${EXP_DIR}/records/${rid}-draws.csv"
  echo "run_klt_sim.sh: per-draw data -> records/${rid}-draws.csv"
}

case "${MODE}" in
--sanity) tm_sanity ;;
--batch) tm_batch ;;
--record) tm_record ;;
esac
