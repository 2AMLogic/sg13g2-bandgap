#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-mc (untrimmed-vref mismatch Monte Carlo) on the
# `klt sim` decks transport (issue #403, Part of #273).
#
#   sim/closed-loop-vref-mc/run_klt_sim.sh --sanity   # seed-parity probe: first KLT_SIM_PROBE draws
#   sim/closed-loop-vref-mc/run_klt_sim.sh --batch    # 6 points x N draws, on the fleet
#   sim/closed-loop-vref-mc/run_klt_sim.sh --record   # mint evidence (KLT_SIM_WORK=<batch dir>)
#
# KLT_SIM_N (default 300) and KLT_SIM_SEED (default 20260909, the removed run_mc.sh's) size the
# campaign. Each draw is the template the removed run_mc.sh rendered (testbench/*.spice.tmpl,
# unchanged), `.options rndseed = SEED + draw_index` included, shipped byte-for-byte
# by klt's `decks` requests; sim/harness/vref_mc_klt.py owns the rest, with the removed
# run_mc.sh's parse rules. That script looped `ngspice -b`; it was removed after 1e3baf2f; see git history.
#
# --sanity is the AC1 seed-parity probe (a few decks, never a grid): KLT_SIM_PROBE
# (default 3) nominal draws, backend KLT_SIM_SANITY_BACKEND (default batch), compared
# with the committed pre-trim record's draws at the same seeds.
#
# A deck-list request refuses `--wait-for-capacity`; the capacity wait rides the
# request (batch.capacity_wait_s, KLT_SIM_CAPACITY_WAIT_S, default 1800). A refused
# or failed submit is reported and stops the run: there is NO local fallback. Re-run
# with the same KLT_SIM_WORK to resume (klt --resume skips units whose result verifies).
set -euo pipefail

# shellcheck disable=SC2034  # EXP/STEM are read by pex_runner.sh
EXP="closed-loop-vref-mc"
STEM="closed_loop_vref_mc"
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"

VM_PY="${HARNESS_DIR}/vref_mc_klt.py"
TEMPLATE="${EXP_DIR}/testbench/tb_closed_loop_vref_mc.spice.tmpl"
N="${KLT_SIM_N:-300}"
SEED="${KLT_SIM_SEED:-20260909}"
PROBE="${KLT_SIM_PROBE:-3}"
BATCH_OSDI_DIR="${BATCH_PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi"
CAPACITY_WAIT_S="${KLT_SIM_CAPACITY_WAIT_S:-1800}"
SEED_CSV="$(ls -1 "${SIM_DIR}/closed-loop-startup/records/"*.csv | sort | tail -1)"
ANCHOR_CSV="$(ls -1 "${EXP_DIR}/records/"*-draws.csv | sort | head -1)"   # the committed pre-trim record

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
DUT_SHA="core=$(dut_git_sha design/netlist/bandgap_core.spice) amp=$(dut_git_sha design/netlist/bandgap_amp.spice) startup=$(dut_git_sha design/netlist/bandgap_startup.spice) seeds=${SEED_CSV##*/}@$(dut_git_sha "${SEED_CSV#"${REPO_ROOT}/"}")"
SUBMIT_KLT="${KLT_SIM_SUBMIT_KLT:-${KLT_BIN}}"

vm_prepare() {
  python3 "${VM_PY}" prepare --work "${WORK}" --template "${TEMPLATE}" \
    --seed-csv "${SEED_CSV}" --msense-w "${MSENSE_W}" --dut-sha "${DUT_SHA}" --pdk "${PDK}" \
    --local-pdk-root "${PDK_ROOT}" --local-osdi-dir "${OSDI_DIR}" \
    --batch-pdk-root "${BATCH_PDK_ROOT}" --batch-osdi-dir "${BATCH_OSDI_DIR}" \
    --provision "${BATCH_PROVISION_SCRIPT}" --capacity-wait-s "${CAPACITY_WAIT_S}" \
    --seed "${SEED}" --n "${N}" "$@"
}

vm_sanity() {
  local backend="${KLT_SIM_SANITY_BACKEND:-batch}"
  rm -rf "${WORK}/artifacts-probe"
  vm_prepare --probe "${PROBE}" --probe-backend "${backend}"
  ( cd "${WORK}" && "${SUBMIT_KLT}" sim request-probe.json --backend "${backend}" \
      --format json -o artifacts-probe > report-probe.json ) || true
  python3 "${VM_PY}" check-probe --artifacts "${WORK}/artifacts-probe" \
    --anchor-csv "${ANCHOR_CSV}" --probe "${PROBE}"
}

vm_batch() {
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  vm_prepare
  local rc=0
  echo "run_klt_sim.sh: $(ls "${WORK}"/request-mc-*.json | wc -l) requests on the fleet"
  ( cd "${WORK}" && "${SUBMIT_KLT}" sim --batch-set request-mc-*.json --max-in-flight 4 \
      --resume --format json -o artifacts-mc > report-mc.json \
      2> >(tee -a klt-stderr.log >&2) ) || rc=$?
  # exit_code 4 = some unit errored/timed out (a FAIL row); anything else nonzero or a
  # refusal means the request did not run: report it, never run it locally.
  python3 - "${WORK}/report-mc.json" "${rc}" <<'PY'
import json, pathlib, sys
path, rc = pathlib.Path(sys.argv[1]), int(sys.argv[2])
try:
    rep = json.loads(path.read_text())
except ValueError:
    raise SystemExit(f"run_klt_sim.sh: batch submit failed (klt exit {rc}), no report: {path}\n"
                     "  no local fallback -- fix the cause and re-run with the same KLT_SIM_WORK to resume")
bad = [r for r in rep.get("requests", []) if r.get("error") or r.get("exit_code") not in (0, 4)]
if rep.get("refused_codes") or bad:
    raise SystemExit(f"run_klt_sim.sh: batch submit failed: refused_codes={rep.get('refused_codes')} "
                     f"requests={[(r['request'], r.get('exit_code'), r.get('error')) for r in bad][:3]}\n"
                     "  no local fallback -- re-run with the same KLT_SIM_WORK to resume")
PY
  python3 "${VM_PY}" assemble --work "${WORK}" --artifacts "${WORK}/artifacts-mc" \
    --template "${TEMPLATE}" --seed-csv "${SEED_CSV}" --msense-w "${MSENSE_W}" \
    --dut-sha "${DUT_SHA}" --pdk "${PDK}" --local-pdk-root "${PDK_ROOT}" \
    --local-osdi-dir "${OSDI_DIR}" --seed "${SEED}" --n "${N}" \
    --klt-version "${KLT_VERSION_DECL}" --job-log "${WORK}/klt-stderr.log" \
    --draws-out "${WORK}/draws.csv" --report-out "${WORK}/report-assembled.json"
  echo "run_klt_sim.sh: mint evidence with: KLT_SIM_WORK=${WORK} KLT_SIM_N=${N} run_klt_sim.sh --record"
}

vm_record() {
  local rid
  rid="$(date -u +%Y%m%d-%H%M%S)-$(git -C "${REPO_ROOT}" rev-parse --short HEAD)"
  python3 "${VM_PY}" spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
    --msense-w "${MSENSE_W}" --n "${N}" -o "${WORK}/record-spec.json"
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-assembled.json" --spec "${WORK}/record-spec.json" \
      --experiment "${EXP_DIR}" --record-id "${rid}" ) || [[ -f "${EXP_DIR}/records/${rid}.md" ]]
  cp "${WORK}/draws.csv" "${EXP_DIR}/records/${rid}-draws.csv"
  echo "run_klt_sim.sh: per-draw data -> records/${rid}-draws.csv"
}

case "${MODE}" in
--sanity) vm_sanity ;;
--batch) vm_batch ;;
--record) vm_record ;;
esac
