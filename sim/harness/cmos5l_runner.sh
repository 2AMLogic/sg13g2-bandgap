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
#              record, typ/27C/3.30V), gated by sim/harness/sanity_anchors.py
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

# The runner preamble (mode check, directory/klt/PDK/OSDI resolution, work
# dir, batch defaults, resume-safety scaffold) is shared with pex_runner.sh
# (sim/harness/klt_sim_preamble.sh, issue #481); only the SG13CMOS5L-specific
# blocks stay in this file (issue #337). Each shared function returns
# non-zero instead of exiting; `cmos5l_main` turns a failure into its
# `return` here. The batch defaults and the resume scaffold keep their
# --batch-only timing: they are called from `cmos5l_batch`, not from here.
# shellcheck source=klt_sim_preamble.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/klt_sim_preamble.sh"

cmos5l_main() {
  local MODE="${1:-}"
  klt_sim_mode "${MODE}" || return $?

  klt_sim_dirs "${BASH_SOURCE[1]}"
  local TB="${EXP_DIR}/testbench"
  local CMOS5L_PY="${HARNESS_DIR}/cmos5l_klt.py"

  klt_sim_require_klt || return $?

  # PDK resolution. This runner is SG13CMOS5L-only, so PDK is forced (an
  # inherited ihp-sg13g2 would silently run the wrong variant); PDK_ROOT
  # follows sim/env.sh's candidates, then KLT_SIM_PDK_ROOT.
  export PDK=ihp-sg13cmos5l
  klt_sim_resolve_pdk || return $?
  local MODELS_DIR="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"
  # The MOS/resistor corner libs are symlinks into the sibling ihp-sg13g2/
  # checkout (sim/pdk-sg13cmos5l.json sibling_checkout_requirement): a dangling
  # link means the sibling is missing.
  if [[ ! -r "${MODELS_DIR}/cornerMOShv.lib" || ! -r "${MODELS_DIR}/cornerRES.lib" ]]; then
    echo "run_klt_sim.sh: ${MODELS_DIR}/cornerMOShv.lib or cornerRES.lib unreadable --" >&2
    echo "             the sibling ihp-sg13g2/ checkout is missing (dangling symlinks)." >&2
    return 3
  fi
  klt_sim_require_osdi SG13CMOS5L_OSDI_DIR " (sim/pdk-sg13cmos5l.json osdi_toolchain)." || return $?

  # Fail-closed mapping checks, before anything is generated: the corner map
  # must still agree with the legacy scripts and with the installed libs.
  python3 "${CMOS5L_PY}" check-mapping --models-dir "${MODELS_DIR}" >&2

  local WORK
  klt_sim_work_dir "${MODE}" || return $?

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
  python3 "${HARNESS_DIR}/sanity_anchors.py" "${WORK}/report.json" "${ANCHOR_ARGS[@]}" \
    --hint "the bench, not the PDK pin, is the first suspect (issue #337 sanity gate)"
}

cmos5l_batch() {
  # --batch-only timing preserved (#481): these two resolve here, not at
  # source time, so --sanity/--record never touch batch defaults.
  klt_sim_batch_defaults
  if [[ "${KLT_SIM_CMOS5L_BATCH_READY:-}" != 1 ]]; then
    echo "run_klt_sim.sh: refusing --batch. The batch runner image bakes ihp-sg13g2 only" >&2
    echo "             (sim/pdk-sg13cmos5l.json deferred_requirements.provisioning); no" >&2
    echo "             authorized SG13CMOS5L execution path exists yet and there is NO" >&2
    echo "             local-grid fallback. Set KLT_SIM_CMOS5L_BATCH_READY=1 only once a" >&2
    echo "             CMOS5L-provisioned image is demonstrated." >&2
    return 5
  fi
  klt_sim_require_provision || return $?
  echo "run_klt_sim.sh: sanity gate before dispatch"
  cmos5l_sanity

  # Resume safety (#332): the shared scaffold sources submission_identity.sh
  # and builds the common declares; the CMOS5L extras are appended here.
  klt_sim_resume_scaffold
  IDENT_ARGS+=(
    --declare "msense_w=${MSENSE_W}"
    --extra "${TB}/${STEM}.request.json.tmpl"
    --extra "${TB}/${STEM}.body.spice.tmpl"
    --extra "${BATCH_PROVISION_SCRIPT}"
    --extra "${CMOS5L_PY}"
    --extra "${HARNESS_DIR}/klt_corner_bundle.py"
    --extra "${HARNESS_DIR}/enrich_pvt_report.py"
    --extra "${HARNESS_DIR}/seed_deck.py")

  python3 "${CMOS5L_PY}" prepare --mode batch --kind "${KIND}" --families "${FAMILIES}" \
    --request-template "${TB}/${STEM}.request.json.tmpl" \
    --body-template "${TB}/${STEM}.body.spice.tmpl" \
    --work "${WORK}" --pdk "${PDK}" --batch-pdk-root "${BATCH_PDK_ROOT}" \
    --local-pdk-root "${PDK_ROOT}" --provision "${BATCH_PROVISION_SCRIPT}" "${MSENSE_ARGS[@]}"

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
