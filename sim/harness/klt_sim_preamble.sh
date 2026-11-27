# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are shared with the sourcing runner / callees
# The `klt sim` runner preamble, shared by the two runner bases (issue #481):
# `pex_runner.sh` (the SG13G2 PEX / supply / vref benches and their nested
# runners) and `cmos5l_runner.sh` (the four `sim/sg13cmos5l-*` benches). One
# function per duplicated block. Each failure echoes its cause to stderr and
# RETURNS non-zero -- never exits -- so each base keeps its own exit
# (pex_runner.sh runs at source time, top level) or return (cmos5l_runner.sh
# runs inside `cmos5l_main`) at the call site.
#
# Source it from the runner base (both live in sim/harness/):
#   source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/klt_sim_preamble.sh"
# then call the functions from the place that preserves each base's current
# timing: everything at source time in pex_runner.sh, but the batch defaults
# and the resume-safety scaffold from inside `cmos5l_batch` (they were
# --batch-only there). Pass "${BASH_SOURCE[1]}" to klt_sim_dirs from the call
# site: inside a function defined HERE, BASH_SOURCE[1] is the sourcing runner,
# not the bench.
#
# The blocks that set variables the callee scripts read
# (submission_identity.sh's WORK/KLT_BIN/IDENT_ARGS, fixup_batch_report.py's
# FIXUP_UNBOUND, the si_* helpers' WORK/HARNESS_DIR) deliberately leave them
# global; one runner per process, nothing else assigns them.

# --- mode validation ----------------------------------------------------------
klt_sim_mode() {  # MODE
  case "${1}" in
    --sanity|--batch|--record) ;;
    *)
      echo "usage: run_klt_sim.sh --sanity | --batch | --record" >&2
      return 2
      ;;
  esac
}

# --- directory derivation ------------------------------------------------------
klt_sim_dirs() {  # BENCH_SCRIPT ("${BASH_SOURCE[1]}" at the call site)
  SCRIPT_DIR="$(cd "$(dirname "${1}")" && pwd)"
  SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
  HARNESS_DIR="${SIM_DIR}/harness"
  EXP_DIR="${SIM_DIR}/${EXP}"
}

# --- the klt that submits ------------------------------------------------------
# Batch needs one carrying the batch backend (klayout-tools 0.6.0+); the PyPI
# 0.5.0 the dispatch hosts ship as `klt` predates it. Sanity mode works with
# either.
klt_sim_require_klt() {
  KLT_BIN="${KLT_SIM_KLT:-klt}"
  if ! command -v "${KLT_BIN}" >/dev/null 2>&1; then
    echo "run_klt_sim.sh: klt binary '${KLT_BIN}' not found (KLT_SIM_KLT)." >&2
    return 3
  fi
}

# --- PDK resolution ------------------------------------------------------------
# sim/env.sh's own candidates first, then the klt checkout's fetched-PDKs tree
# (the install this repo's extraction flow itself uses on dev hosts), then an
# explicit KLT_SIM_PDK_ROOT.
klt_sim_resolve_pdk() {
  # shellcheck source=../env.sh
  source "${SIM_DIR}/env.sh" >/dev/null
  if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
    local cand
    for cand in "${KLT_SIM_PDK_ROOT:-}" "${HOME}/GitHub/klayout-tools/pdks/ihp-open-pdk"; do
      if [[ -n "${cand}" && -d "${cand}/${PDK}/libs.tech/ngspice" ]]; then
        export PDK_ROOT="${cand}"
        break
      fi
    done
  fi
  if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
    echo "run_klt_sim.sh: no resolvable ${PDK} install (PDK_ROOT / KLT_SIM_PDK_ROOT)." >&2
    return 3
  fi
}

# --- OSDI models ---------------------------------------------------------------
klt_sim_require_osdi() {  # OVERRIDE_VAR [MISSING_HINT]
  # Resolves the PDK's OSDI model dir into OSDI_DIR (${OVERRIDE_VAR} wins,
  # else ${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi) and fails unless
  # psp103.osdi is present. MISSING_HINT is appended verbatim to the error
  # (per-PDK: where the models come from).
  OSDI_DIR="${!1:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"
  if [[ ! -f "${OSDI_DIR}/psp103.osdi" ]]; then
    echo "run_klt_sim.sh: OSDI models missing in ${OSDI_DIR}${2:-}" >&2
    return 3
  fi
}

# --- batch defaults ------------------------------------------------------------
# The batch runner image's baked PDK root (2am infra/aws/batch-image-pins.env
# BAKED_PDK_ROOT) and the provision script `klt` shells out to on this host.
# BATCH_PDK_ROOT is the runner root for what klt does NOT rewrite: the OSDI
# paths in the body's `.control` block, and the paths in a returned report.
klt_sim_batch_defaults() {  # [PDK_ROOT_OVERRIDE_VAR]
  # PDK_ROOT_OVERRIDE_VAR (optional) names the caller's own PDK-root override
  # variable, consulted ahead of the generic KLT_SIM_BATCH_PDK_ROOT: the
  # standalone submitters (probe/run_probe.sh, run_klt_trim_axis.sh, issue
  # #503) each document a per-script override name and pass it here instead of
  # being silently retired by the shared function.
  BATCH_PDK_ROOT="${!1:-${KLT_SIM_BATCH_PDK_ROOT:-/opt/pdk}}"
  BATCH_PROVISION_SCRIPT="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"
}

# --- batch provision guard -----------------------------------------------------
# Every runner that dispatches `klt sim --batch-set` refuses to start unless
# the provision script klt shells out to is executable (five re-typed copies
# collapsed here, issue #702; the last two inline checks in sim/ retired onto
# it, issue #707). Returns 3 -- this preamble's return-not-exit contract --
# so cmos5l_runner.sh keeps its `return 3` and the top-level runners keep
# their `|| exit $?`. CALLER_NAME (optional) replaces the diagnostic's
# run_klt_sim.sh prefix, so a standalone caller (sim/harness/probe/run_probe.sh,
# sim/loop-gain-phase-margin/run_klt_trim_axis.sh) names itself.
klt_sim_require_provision() {  # [CALLER_NAME]
  local caller="${1:-run_klt_sim.sh}"
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "${caller}: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    return 3
  fi
}

# --- MSENSE width read/cache ---------------------------------------------------
# XMSENSE's width from the live startup netlist, as every closed-loop bench
# reads it: in --record mode the work dir's cached msense_w.txt wins (the
# record must re-read the value its --batch run dispatched with); otherwise
# read_msense_width runs against REPO_ROOT and the value is cached for the
# later --record pass (three re-typed copies collapsed here, issue #702).
# NETLIST is repo-relative. The failure diagnostic names this file, not the
# bench: read_msense_width's caller_name convention (sim/lib/msense_width.sh)
# is "the file containing the call expression", and the call lives here now.
klt_sim_read_msense_width() {  # NETLIST
  # shellcheck source=../lib/msense_width.sh
  source "${SIM_DIR}/lib/msense_width.sh"
  if [[ "${MODE}" == "--record" && -f "${WORK}/msense_w.txt" ]]; then
    MSENSE_W="$(<"${WORK}/msense_w.txt")"
  else
    ( cd "${REPO_ROOT}" && read_msense_width "${1}" \
        && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
    MSENSE_W="$(<"${WORK}/msense_w.txt")"
  fi
}

# --- startup seed record --------------------------------------------------------
# Sets SEED_CSV to sim/closed-loop-startup's newest committed record, where
# the seeded benches' .nodeset values come from, and returns 3 -- this
# preamble's return-not-exit contract -- when there is none. Newest is by
# filename, never mtime: record ids lead with a UTC timestamp, so in byte
# order the lexicographic tail IS the newest record, whereas a fresh
# checkout stamps every record at once and leaves the choice to checkout
# order (pex_ac_runner.sh's own mtime-ordered pick, issue #740). The
# *-tc.csv / *-vs-schematic* companions a previous enrichment derives from
# a record are skipped and the sort is the C locale's -- the same lookup as
# seed_deck.py's newest_seed_csv (#486/#707). Under en_US.UTF-8 a companion
# can sort after its seed, so an unfiltered `sort | tail -1` can select the
# companion (#739). Pure shell on purpose: the identity coverage probe runs
# these runners with a stubbed python3.
klt_sim_newest_seed_csv() {
  local cand
  local cands=()
  for cand in "${SIM_DIR}/closed-loop-startup/records/"*.csv; do
    [[ -f "${cand}" ]] || continue
    case "${cand##*/}" in *-tc.csv|*-vs-schematic*) continue ;; esac
    cands+=("${cand}")
  done
  if [[ ${#cands[@]} -eq 0 ]]; then
    echo "run_klt_sim.sh: no seed record in ${SIM_DIR}/closed-loop-startup/records/" >&2
    return 3
  fi
  SEED_CSV="$(printf '%s\n' "${cands[@]}" | LC_ALL=C sort | tail -1)"
}

# PATH's most recent commit's short SHA (PATH a repo-relative git pathspec,
# resolved against REPO_ROOT), or "unknown": the same lookup
# sim/lib/pvt_preflight.sh's dut_git_sha() makes for the run_pvt_sweep.sh
# benches (#103), which the `klt sim` runners cannot source -- that file
# preflights a PVT sweep at source time. closed-loop-vref-mc re-typed it
# inline until #739.
dut_git_sha() {  # PATH
  git -C "${REPO_ROOT}" log -1 --format=%h -- "$1" 2>/dev/null || echo unknown
}

# --- resume safety (#332) ------------------------------------------------------
# A saved report is reused only when its committed submission identity matches
# the inputs about to be submitted (sim/harness/submission_identity.py).
# Legacy/stale reports are refused; KLT_SIM_ALLOW_UNBOUND_REPORTS=1 /
# KLT_SIM_REDISPATCH_STALE=1 are the opt-ins. Builds the shared part of
# IDENT_ARGS; each runner base appends its own --declare/--extra items, in the
# order that keeps the committed identity hash stable.
klt_sim_resume_scaffold() {
  # shellcheck source=submission_identity.sh
  source "${HARNESS_DIR}/submission_identity.sh"
  KLT_VERSION_DECL="$("${KLT_BIN}" --version 2>&1 | head -1 || true)"
  IDENT_ARGS=(--declare "klt_bin=${KLT_BIN}" --declare "klt_version=${KLT_VERSION_DECL}"
    --declare "pdk=${PDK}" --declare "batch_pdk_root=${BATCH_PDK_ROOT}")
  FIXUP_UNBOUND=()
  if [[ "${KLT_SIM_ALLOW_UNBOUND_REPORTS:-}" == 1 ]]; then
    FIXUP_UNBOUND=(--allow-unbound)
  fi
}

# --- work dir ------------------------------------------------------------------
# KLT_SIM_WORK if set; else a fresh temp dir -- except --record, which mints
# evidence from the --batch work dir and has none to discover. The shared
# behaviour is cmos5l_runner.sh's guard (issue #481): fail immediately with
# the cause, where pex_runner.sh used to mint an empty temp dir and die later
# inside pex_record_mint on a missing extraction-sources.json. Deliberate.
klt_sim_work_dir() {  # MODE
  WORK="${KLT_SIM_WORK:-}"
  if [[ -z "${WORK}" ]]; then
    if [[ "${1}" == "--record" ]]; then
      echo "run_klt_sim.sh: --record needs KLT_SIM_WORK (the --batch work dir)." >&2
      return 2
    fi
    WORK="$(mktemp -d -t "sg13g2-klt-${EXP}-XXXXXX")"
  fi
  mkdir -p "${WORK}"
  echo "run_klt_sim.sh: work dir ${WORK}"
}
