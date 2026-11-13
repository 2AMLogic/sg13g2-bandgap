# Shared resume/dispatch helper for the per-shard batch runners (#332).
# Source it AFTER setting WORK, HARNESS_DIR, KLT_BIN and the IDENT_ARGS array
# (--extra FILE / --declare key=value flags for the shard identity).
#
#   si_shard REQUEST REPORT ARTIFACTS DESC
#
# Reuses REPORT only if its committed submission identity matches REQUEST's
# current inputs; refuses stale/unbound reports; otherwise dispatches, writing
# the identity sidecar only after the submission completed.
# All paths are relative to WORK. See sim/harness/submission_identity.py.
#
# Every batch submission waits for fleet capacity instead of failing the step
# (issue #387): the Spot fleet is vCPU-budgeted and shared with ci-spot, so a
# burst of shards is refused with `batch_no_capacity` the moment the budget is
# full. `--wait-for-capacity SECONDS` re-launches the same job with jittered
# backoff rather than returning a refusal, which is what the dispatch hosts'
# rules require of a batch `klt sim`. Override the window with
# KLT_SIM_CAPACITY_WAIT_S (0 = one attempt, the pre-#387 behaviour).
SI_CAPACITY_WAIT_S="${KLT_SIM_CAPACITY_WAIT_S:-600}"

si_shard() {
  local request="$1" report="$2" artifacts="$3" desc="$4" rc=0
  python3 "${HARNESS_DIR}/submission_identity.py" check \
    "${WORK}/${request}" "${WORK}/${report}" "${IDENT_ARGS[@]}" || rc=$?
  case "${rc}" in
    0) echo "run_klt_sim.sh: ${desc} already complete (identity verified), skipping"; return 0 ;;
    1) ;;
    *) echo "run_klt_sim.sh: refusing to reuse ${report}; see message above." >&2; exit 4 ;;
  esac
  echo "run_klt_sim.sh: dispatching ${desc}"
  python3 "${HARNESS_DIR}/submission_identity.py" begin \
    "${WORK}/${request}" "${WORK}/${report}" "${IDENT_ARGS[@]}"
  # A variant whose run grades error/fail still writes its report (the
  # merge + enrichment surface what failed); only a submission that wrote NO
  # report is fatal (commit refuses and the shard stays unbound).
  ( cd "${WORK}" && "${KLT_BIN}" sim "${request}" --backend batch \
      --wait-for-capacity "${SI_CAPACITY_WAIT_S}" \
      --format json -o "${artifacts}" > "${report}" ) || \
    echo "run_klt_sim.sh: ${desc} graded non-pass -- recorded, continuing"
  python3 "${HARNESS_DIR}/submission_identity.py" commit "${WORK}/${report}" || \
    echo "run_klt_sim.sh: ${desc}: identity NOT committed; a resume will refuse this report" >&2
}
