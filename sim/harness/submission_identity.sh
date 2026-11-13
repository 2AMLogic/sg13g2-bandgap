# Shared resume/dispatch helper for the per-shard batch runners (#332).
# Source it AFTER setting WORK, HARNESS_DIR, KLT_BIN and the IDENT_ARGS array
# (--extra FILE / --declare key=value flags for the shard identity).
#
#   si_shard REQUEST REPORT ARTIFACTS DESC            one shard, submitted now
#
#   si_set_reset                                      start a concurrent set
#   si_set_add REQUEST REPORT DESC                    ... enqueue each shard
#   si_set_dispatch OUTDIR MAX_IN_FLIGHT              ... submit them together
#
# Reuses REPORT only if its committed submission identity matches REQUEST's
# current inputs; refuses stale/unbound reports; otherwise dispatches, writing
# the identity sidecar only after the submission completed.
#
# si_shard submits one request per `klt sim` invocation, so a campaign of N
# shards is N sequential fleet round-trips: the 120-point closed-loop-vref-pvt-
# boxtc grid is 15 independent requests and took 7+ h that way (issue #402).
# The si_set_* trio hands the whole campaign to ONE `klt sim --batch-set`
# (klayout-tools #2869) instead, which keeps up to MAX_IN_FLIGHT requests in
# flight at once, preflights every member before submitting any, and waits out
# a capacity refusal per member. Identity handling is unchanged: each enqueued
# shard is `begin`-ed before the set is submitted and `commit`-ed from the
# member report the set wrote, so a resume skips exactly the shards si_shard
# would have skipped.
#
# KLT_SIM_SUBMIT_KLT (optional) is the client that submits to the fleet -- e.g. a
# `uvx --from klayout-tools==X klt` wrapper pinned to the runner image's klt, which
# refuses a client of a different version; the sanity gate keeps using KLT_BIN.
# KLT_SIM_CAPACITY_WAIT_S (default 600) is the per-member `--wait-for-capacity`
# budget and KLT_SIM_CAPACITY_RETRIES (default 4) the set's `--capacity-retries`:
# the batch fleet is vCPU-budgeted, so a burst is refused with
# `batch_no_capacity` unless the submit is told to wait it out.
# KLT_SIM_MAX_CONCURRENT_JOBS (optional) bounds how many of a MEMBER's own
# shard jobs run at once. The real bound on a campaign is the fleet's shared
# vCPU budget, not the client: `remote.hosts` shards one request into that
# many single-corner jobs, so MAX_IN_FLIGHT x hosts jobs are wanted at once
# and a burst past the budget is refused. Capping both keeps the campaign
# inside the budget instead of losing the overflow shards to an exhausted
# capacity wait.
# KLT_SIM_SET_RESUME=1 adds `--resume`, re-attaching each member to the shard
# jobs its previous run recorded instead of relaunching them.
# All paths are relative to WORK. See sim/harness/submission_identity.py.

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
  ( cd "${WORK}" && "${KLT_SIM_SUBMIT_KLT:-${KLT_BIN}}" sim "${request}" --backend batch \
      --wait-for-capacity "${KLT_SIM_CAPACITY_WAIT_S:-600}" \
      --format json -o "${artifacts}" > "${report}" ) || \
    echo "run_klt_sim.sh: ${desc} graded non-pass -- recorded, continuing"
  python3 "${HARNESS_DIR}/submission_identity.py" commit "${WORK}/${report}" || \
    echo "run_klt_sim.sh: ${desc}: identity NOT committed; a resume will refuse this report" >&2
}

# --- concurrent set dispatch (issue #402) ------------------------------------
# si_set_add enqueues the shards that still need running (the same identity
# check si_shard makes) and si_set_dispatch submits them in one `klt sim
# --batch-set`. Keep the three arrays index-aligned.

si_set_reset() {
  SI_SET_REQUESTS=()
  SI_SET_REPORTS=()
  SI_SET_DESCS=()
}

si_set_add() {  # REQUEST REPORT DESC
  local request="$1" report="$2" desc="$3" rc=0
  python3 "${HARNESS_DIR}/submission_identity.py" check \
    "${WORK}/${request}" "${WORK}/${report}" "${IDENT_ARGS[@]}" || rc=$?
  case "${rc}" in
    0) echo "run_klt_sim.sh: ${desc} already complete (identity verified), skipping"; return 0 ;;
    1) ;;
    *) echo "run_klt_sim.sh: refusing to reuse ${report}; see message above." >&2; exit 4 ;;
  esac
  # Bind the shard to its inputs BEFORE the set is submitted, exactly as
  # si_shard does; the matching commit happens in si_set_dispatch.
  python3 "${HARNESS_DIR}/submission_identity.py" begin \
    "${WORK}/${request}" "${WORK}/${report}" "${IDENT_ARGS[@]}"
  SI_SET_REQUESTS+=("${request}")
  SI_SET_REPORTS+=("${report}")
  SI_SET_DESCS+=("${desc}")
}

si_set_dispatch() {  # OUTDIR MAX_IN_FLIGHT
  local outdir="$1" in_flight="$2" rc=0 i stem member
  local -a resume=() concurrent=()
  if [[ ${#SI_SET_REQUESTS[@]} -eq 0 ]]; then
    echo "run_klt_sim.sh: every shard is already complete; nothing to submit"
    return 0
  fi
  [[ "${KLT_SIM_SET_RESUME:-}" == 1 ]] && resume=(--resume)
  [[ -n "${KLT_SIM_MAX_CONCURRENT_JOBS:-}" ]] && \
    concurrent=(--max-concurrent-jobs "${KLT_SIM_MAX_CONCURRENT_JOBS}")
  echo "run_klt_sim.sh: submitting ${#SI_SET_REQUESTS[@]} request(s) concurrently" \
       "(--batch-set, at most ${in_flight} in flight):"
  printf '  - %s\n' "${SI_SET_DESCS[@]}"
  # One client, N requests: the fleet does the work. A member that errors or
  # measures a failure is reported and kept (the merge is what refuses a
  # partial grid), so a non-zero exit here is not fatal on its own.
  ( cd "${WORK}" && "${KLT_SIM_SUBMIT_KLT:-${KLT_BIN}}" sim \
      --batch-set "${SI_SET_REQUESTS[@]}" \
      --max-in-flight "${in_flight}" \
      --wait-for-capacity "${KLT_SIM_CAPACITY_WAIT_S:-600}" \
      --capacity-retries "${KLT_SIM_CAPACITY_RETRIES:-4}" \
      "${concurrent[@]}" "${resume[@]}" \
      --format json -o "${outdir}" > "${outdir}.json" ) || rc=$?
  [[ ${rc} -eq 0 ]] || echo "run_klt_sim.sh: --batch-set exited ${rc};" \
    "per-member status is in ${WORK}/${outdir}.json" >&2

  # Harvest: `--batch-set` writes each member's full single-request report to
  # <outdir>/<request stem>/report.json. Copy it to the per-shard path the
  # fixup/merge steps expect -- its artifact paths stay relative to WORK, the
  # directory the set ran in -- then commit that shard's identity.
  for i in "${!SI_SET_REQUESTS[@]}"; do
    stem="$(basename "${SI_SET_REQUESTS[$i]}" .json)"
    member="${WORK}/${outdir}/${stem}/report.json"
    if [[ ! -s "${member}" ]]; then
      echo "run_klt_sim.sh: ${SI_SET_DESCS[$i]}: the set returned no report" \
           "(expected ${member}); shard left unbound" >&2
      continue
    fi
    cp "${member}" "${WORK}/${SI_SET_REPORTS[$i]}"
    python3 "${HARNESS_DIR}/submission_identity.py" commit "${WORK}/${SI_SET_REPORTS[$i]}" || \
      echo "run_klt_sim.sh: ${SI_SET_DESCS[$i]}: identity NOT committed;" \
           "a resume will refuse this report" >&2
  done
  return "${rc}"
}
