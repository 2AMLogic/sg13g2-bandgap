# shellcheck shell=bash
# shellcheck disable=SC2034  # variables are shared with the sourcing runner / callees
# Shared body of the four SG13CMOS5L `run_klt_sim.sh` runners (issue #337,
# Part of #322). Source it, set the experiment variables below, then call
# `cmos5l_main "$@"`.
#
#   sim/<exp>/run_klt_sim.sh --sanity   # one LOCAL corner (typ/27C/3.30V) vs the legacy anchor
#   sim/<exp>/run_klt_sim.sh --batch    # the 45-point grid on the Spot batch fleet
#   sim/<exp>/run_klt_sim.sh --record   # mint evidence from the enriched merged report
#
# Caller variables (all required unless noted):
#   EXP        experiment directory name under sim/
#   STEM       testbench file stem (underscored)
#   KIND       core-open-loop | trip-point | closed-loop (sim/harness/cmos5l_klt.py)
#   FAMILIES   pnp,mos,res | mos,res -- the corner families the bench instantiates
#   ANCHORS    bash array of `name=value:tol` sanity anchors (committed legacy
#              record, typ/27C/3.30V)
#   MSENSE_NETLIST   (optional) design netlist whose XMSENSE w= the body takes
#
# WHY THIS SHAPE (same reasoning as the SG13G2 siblings, sim/harness/README.md):
# the dispatch hosts direct multi-corner work to `klt sim`'s batch backend and
# allow single corners only locally. --sanity is that one allowed local corner
# and it is a GATE: no grid is dispatched until it lands on the experiment's
# own committed legacy value. The runner image's single-models.lib request
# cannot vary the process within one request (klayout-tools#2668), so --batch
# sends one request per process (or per process x supply, see the request
# template), merges them with the grid stated explicitly, and re-grades each
# point with the legacy verdict (cmos5l_klt.py enrich).
#
# WHAT THIS RUNNER CANNOT DO TODAY. The batch image bakes `ihp-sg13g2` only
# (sim/pdk-sg13cmos5l.json deferred_requirements.provisioning), so --batch
# refuses unless KLT_SIM_CMOS5L_BATCH_READY=1 asserts that a CMOS5L-provisioned
# image exists. There is deliberately no local-grid fallback. The conversion
# was committed WITHOUT running any of these modes (issue #337 scope).
set -euo pipefail

cmos5l_main() {
  local MODE="${1:-}"
  case "${MODE}" in
    --sanity|--batch|--record) ;;
    *) echo "usage: run_klt_sim.sh --sanity | --batch | --record" >&2; return 2 ;;
  esac

  local SCRIPT_DIR SIM_DIR HARNESS_DIR EXP_DIR
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
  HARNESS_DIR="${SIM_DIR}/harness"
  EXP_DIR="${SIM_DIR}/${EXP}"
  local TB="${EXP_DIR}/testbench"
  local CMOS5L_PY="${HARNESS_DIR}/cmos5l_klt.py"

  local KLT_BIN="${KLT_SIM_KLT:-klt}"
  if ! command -v "${KLT_BIN}" >/dev/null 2>&1; then
    echo "run_klt_sim.sh: klt binary '${KLT_BIN}' not found (KLT_SIM_KLT)." >&2
    return 3
  fi

  # PDK resolution. This runner is SG13CMOS5L-only, so PDK is forced (an
  # inherited ihp-sg13g2 would silently run the wrong variant); PDK_ROOT
  # follows sim/env.sh's candidates, then KLT_SIM_PDK_ROOT.
  export PDK=ihp-sg13cmos5l
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
  local MODELS_DIR="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"
  # The MOS/resistor corner libs are symlinks into the sibling ihp-sg13g2/
  # checkout (sim/pdk-sg13cmos5l.json sibling_checkout_requirement): a dangling
  # link means the sibling is missing.
  if [[ ! -r "${MODELS_DIR}/cornerMOShv.lib" || ! -r "${MODELS_DIR}/cornerRES.lib" ]]; then
    echo "run_klt_sim.sh: ${MODELS_DIR}/cornerMOShv.lib or cornerRES.lib unreadable --" >&2
    echo "             the sibling ihp-sg13g2/ checkout is missing (dangling symlinks)." >&2
    return 3
  fi
  local OSDI_DIR="${SG13CMOS5L_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"
  if [[ ! -f "${OSDI_DIR}/psp103.osdi" ]]; then
    echo "run_klt_sim.sh: OSDI models missing in ${OSDI_DIR} (sim/pdk-sg13cmos5l.json osdi_toolchain)." >&2
    return 3
  fi

  # Fail-closed mapping checks, before anything is generated: the corner map
  # must still agree with the legacy scripts and with the installed libs.
  python3 "${CMOS5L_PY}" check-mapping --models-dir "${MODELS_DIR}" >&2

  local WORK="${KLT_SIM_WORK:-}"
  if [[ -z "${WORK}" ]]; then
    if [[ "${MODE}" == "--record" ]]; then
      echo "run_klt_sim.sh: --record needs KLT_SIM_WORK (the --batch work dir)." >&2
      return 2
    fi
    WORK="$(mktemp -d -t "sg13g2-klt-${EXP}-XXXXXX")"
  fi
  mkdir -p "${WORK}"
  echo "run_klt_sim.sh: work dir ${WORK}"

  local MSENSE_W=""
  if [[ -n "${MSENSE_NETLIST:-}" ]]; then
    if [[ "${MODE}" == "--record" && -f "${WORK}/msense_w.txt" ]]; then
      MSENSE_W="$(<"${WORK}/msense_w.txt")"
    else
      # XMSENSE's width from the live schematic netlist, as the legacy sweep does.
      # shellcheck source=../lib/msense_width.sh
      source "${SIM_DIR}/lib/msense_width.sh"
      read_msense_width "${MSENSE_NETLIST}"
      printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt"
    fi
  fi
  local MSENSE_ARGS=()
  [[ -n "${MSENSE_W}" ]] && MSENSE_ARGS=(--msense-w "${MSENSE_W}")

  local ANCHOR_ARGS=() a
  for a in "${ANCHORS[@]}"; do ANCHOR_ARGS+=(--anchor "${a}"); done

  case "${MODE}" in
  --sanity)
    cmos5l_sanity
    ;;
  --batch)
    cmos5l_batch
    ;;
  --record)
    cmos5l_record
    ;;
  esac
}

cmos5l_sanity() {
  python3 "${CMOS5L_PY}" bundle -o "${WORK}/sg13cmos5l_corners.lib" --families "${FAMILIES}"
  python3 "${CMOS5L_PY}" prepare --mode sanity --kind "${KIND}" --families "${FAMILIES}" \
    --request-template "${TB}/${STEM}.request.json.tmpl" \
    --body-template "${TB}/${STEM}.body.spice.tmpl" \
    --work "${WORK}" --osdi-dir "${OSDI_DIR}" --bundle "${WORK}/sg13cmos5l_corners.lib" \
    "${MSENSE_ARGS[@]}"
  "${KLT_BIN}" sim "${WORK}/request.json" --backend local --format json \
    -o "${WORK}/artifacts" > "${WORK}/report.json"
  python3 "${CMOS5L_PY}" check-anchors "${WORK}/report.json" "${ANCHOR_ARGS[@]}"
}

cmos5l_batch() {
  local BATCH_PDK_ROOT="${KLT_SIM_BATCH_PDK_ROOT:-/opt/pdk}"
  local PROVISION="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"
  if [[ "${KLT_SIM_CMOS5L_BATCH_READY:-}" != 1 ]]; then
    echo "run_klt_sim.sh: refusing --batch. The batch runner image bakes ihp-sg13g2 only" >&2
    echo "             (sim/pdk-sg13cmos5l.json deferred_requirements.provisioning); no" >&2
    echo "             authorized SG13CMOS5L execution path exists yet and there is NO" >&2
    echo "             local-grid fallback. Set KLT_SIM_CMOS5L_BATCH_READY=1 only once a" >&2
    echo "             CMOS5L-provisioned image is demonstrated." >&2
    return 5
  fi
  if [[ ! -x "${PROVISION}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${PROVISION}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    return 3
  fi
  echo "run_klt_sim.sh: sanity gate before dispatch"
  cmos5l_sanity

  # Resume safety (#332): a saved report is reused only when its committed
  # submission identity matches the inputs about to be submitted.
  # shellcheck source=submission_identity.sh
  source "${HARNESS_DIR}/submission_identity.sh"
  local KLT_VERSION_DECL
  KLT_VERSION_DECL="$("${KLT_BIN}" --version 2>&1 | head -1 || true)"
  IDENT_ARGS=(--declare "klt_bin=${KLT_BIN}" --declare "klt_version=${KLT_VERSION_DECL}"
    --declare "pdk=${PDK}" --declare "batch_pdk_root=${BATCH_PDK_ROOT}"
    --declare "msense_w=${MSENSE_W}"
    --extra "${TB}/${STEM}.request.json.tmpl"
    --extra "${TB}/${STEM}.body.spice.tmpl"
    --extra "${PROVISION}"
    --extra "${CMOS5L_PY}"
    --extra "${HARNESS_DIR}/klt_corner_bundle.py")
  local FIXUP_UNBOUND=()
  [[ "${KLT_SIM_ALLOW_UNBOUND_REPORTS:-}" == 1 ]] && FIXUP_UNBOUND=(--allow-unbound)

  python3 "${CMOS5L_PY}" prepare --mode batch --kind "${KIND}" --families "${FAMILIES}" \
    --request-template "${TB}/${STEM}.request.json.tmpl" \
    --body-template "${TB}/${STEM}.body.spice.tmpl" \
    --work "${WORK}" --pdk "${PDK}" --batch-pdk-root "${BATCH_PDK_ROOT}" \
    --local-pdk-root "${PDK_ROOT}" --provision "${PROVISION}" "${MSENSE_ARGS[@]}"

  local sid label vdd req rep art body fixed decks desc
  while IFS=$'\t' read -r sid label vdd req rep art body fixed decks; do
    desc="${label}"
    [[ "${vdd}" != "-" ]] && desc="${label}/${vdd}V"
    si_shard "${req}" "${rep}" "${art}" "${desc} (one fleet job)"
  done < "${WORK}/manifest.tsv"

  # Record-side fixup: repoint each report's decks at locally resolvable
  # files (the runner's staged include and the image's baked PDK paths do
  # not exist here, and the adapter would ship device-less snapshots).
  while IFS=$'\t' read -r sid label vdd req rep art body fixed decks; do
    python3 "${HARNESS_DIR}/fixup_batch_report.py" "${WORK}/${rep}" \
      "${FIXUP_UNBOUND[@]}" --body "${WORK}/${body}" \
      --runner-pdk-root "${BATCH_PDK_ROOT}" --local-pdk-root "${PDK_ROOT}" \
      --decks-out "${WORK}/${decks}" -o "${WORK}/${fixed}"
  done < "${WORK}/manifest.tsv"

  python3 "${CMOS5L_PY}" merge --manifest "${WORK}/manifest.tsv" \
    --request-template "${TB}/${STEM}.request.json.tmpl" --work "${WORK}" \
    -o "${WORK}/report-merged.json"
  ( cd "${WORK}" && python3 "${CMOS5L_PY}" enrich --kind "${KIND}" \
      "${WORK}/report-merged.json" -o "${WORK}/report-enriched.json" )
  echo "run_klt_sim.sh: enriched report at ${WORK}/report-enriched.json"
  echo "                 mint evidence with: KLT_SIM_WORK=${WORK} run_klt_sim.sh --record"
}

cmos5l_record() {
  python3 "${CMOS5L_PY}" spec "${TB}/${STEM}.record-spec.json" "${MSENSE_ARGS[@]}" \
    -o "${WORK}/record-spec.json"
  local EXTRACTION_ARGS=()
  # A PEX experiment cannot publish without captured extraction-source hashes
  # (#309); this conversion does not create that binding (deferred, see
  # sim/pdk-sg13cmos5l.json deferred_requirements.pex_binding), so the adapter
  # refuses an unbound PEX record unless an operator supplies a real capture.
  [[ -n "${KLT_SIM_EXTRACTION_SOURCES:-}" ]] && EXTRACTION_ARGS=(--extraction-sources "${KLT_SIM_EXTRACTION_SOURCES}")
  # Run the adapter from WORK: the merged report's per-corner artifact paths
  # are relative to the work dir the batch requests wrote into.
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-enriched.json" \
      --spec "${WORK}/record-spec.json" \
      --experiment "${EXP_DIR}" "${EXTRACTION_ARGS[@]}" )
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
}
