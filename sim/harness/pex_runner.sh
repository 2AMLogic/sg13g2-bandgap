# shellcheck shell=bash
# Shared driver for the PEX `klt sim` runners (issue #366): closed-loop-
# vref-pvt-pex, closed-loop-vref-pvt-pex-boxtc, closed-loop-psrr-pex,
# closed-loop-zout-pex and core-open-loop-bias-pex. Each experiment's
# run_klt_sim.sh keeps only its config and the steps that are genuinely its
# own (sanity anchors, enrichment, record companions) and sources this file.
#
# Source it, from the experiment's run_klt_sim.sh, AFTER setting
#   EXP    experiment directory name        STEM   testbench file stem
#   VDDS   (optional) per-supply body variants; leave unset when the bench
#          sweeps the supply natively (see pex_merge_call.sh)
#   BODY_TEMPLATE  (optional, a schematic-DUT bench) the body template --
#          typically the experiment's own with placeholders pre-filled --
#          that --batch hands the request generator
# Sourcing validates the CLI mode (positional args pass through), resolves
# klt / the PDK / the OSDI models, and sets: MODE SCRIPT_DIR SIM_DIR REPO_ROOT
# HARNESS_DIR EXP_DIR KLT_BIN PDK_ROOT OSDI_DIR BATCH_PDK_ROOT BATCH_LIB_ROOT
# BATCH_PROVISION_SCRIPT IDENT_ARGS FIXUP_UNBOUND WORK CORNER_LABELS.
# Then the runner defines its anchors and a `case "${MODE}"` using the
# pex_* helpers below. No simulation is launched from here directly.

MODE="${1:-}"
case "${MODE}" in
  --sanity|--batch|--record) ;;
  *)
    echo "usage: run_klt_sim.sh --sanity | --batch | --record" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
HARNESS_DIR="${SIM_DIR}/harness"
EXP_DIR="${SIM_DIR}/${EXP}"

# The `klt` that submits. Batch needs one carrying the batch backend
# (klayout-tools 0.6.0+); the PyPI 0.5.0 the dispatch hosts ship as `klt`
# predates it. Sanity mode works with either.
KLT_BIN="${KLT_SIM_KLT:-klt}"
if ! command -v "${KLT_BIN}" >/dev/null 2>&1; then
  echo "run_klt_sim.sh: klt binary '${KLT_BIN}' not found (KLT_SIM_KLT)." >&2
  exit 3
fi

# PDK resolution: sim/env.sh's own candidates first, then the klt checkout's
# fetched-PDKs tree (the install this repo's extraction flow itself uses on
# dev hosts), then an explicit KLT_SIM_PDK_ROOT.
source "${SIM_DIR}/env.sh" >/dev/null
source "${HARNESS_DIR}/pex_merge_call.sh"
if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  for _cand in "${KLT_SIM_PDK_ROOT:-}" \
               "${HOME}/GitHub/klayout-tools/pdks/ihp-open-pdk"; do
    if [[ -n "${_cand}" && -d "${_cand}/${PDK}/libs.tech/ngspice" ]]; then
      export PDK_ROOT="${_cand}"
      break
    fi
  done
fi
if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_klt_sim.sh: no resolvable ${PDK} install (PDK_ROOT / KLT_SIM_PDK_ROOT)." >&2
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"
if [[ ! -f "${OSDI_DIR}/psp103.osdi" ]]; then
  echo "run_klt_sim.sh: OSDI models missing in ${OSDI_DIR} -- run sim/tools/build-osdi.sh." >&2
  exit 3
fi

# The batch runner image's baked PDK root (2am infra/aws/batch-image-pins.env
# BAKED_PDK_ROOT) and the provision script `klt` shells out to on this host.
# BATCH_PDK_ROOT is the runner root for what klt does NOT rewrite: the OSDI
# paths in the body's `.control` block, and the paths in a returned report.
# BATCH_LIB_ROOT is the root of the body's selection-form `.lib` cards. klt
# 0.8.x refuses an absolute runner path there ("not under $PDK_ROOT") and
# accepts one under the SUBMITTING host's $PDK_ROOT, which it rewrites for the
# runner -- so it is the local PDK root, never the runner's, and not overridable.
BATCH_PDK_ROOT="${KLT_SIM_BATCH_PDK_ROOT:-/opt/pdk}"
BATCH_LIB_ROOT="${PDK_ROOT}"
BATCH_PROVISION_SCRIPT="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"

# Resume safety (#332): a saved report is reused only when its committed
# submission identity matches the inputs about to be submitted
# (sim/harness/submission_identity.py). Legacy/stale reports are refused;
# KLT_SIM_ALLOW_UNBOUND_REPORTS=1 / KLT_SIM_REDISPATCH_STALE=1 are the opt-ins.
source "${HARNESS_DIR}/submission_identity.sh"
KLT_VERSION_DECL="$("${KLT_BIN}" --version 2>&1 | head -1 || true)"
IDENT_ARGS=(--declare "klt_bin=${KLT_BIN}" --declare "klt_version=${KLT_VERSION_DECL}"
  --declare "pdk=${PDK}" --declare "batch_pdk_root=${BATCH_PDK_ROOT}"
  --declare "batch_lib_root=submitter-pdk-root"
  --extra "${EXP_DIR}/testbench/${STEM}.request.json.tmpl"
  --extra "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"
  --extra "${BATCH_PROVISION_SCRIPT}"
  --extra "${HARNESS_DIR}/klt_corner_bundle.py"
  --extra "${SIM_DIR}/tools/gen_pex_netlist_body.py")
FIXUP_UNBOUND=()
[[ "${KLT_SIM_ALLOW_UNBOUND_REPORTS:-}" == 1 ]] && FIXUP_UNBOUND=(--allow-unbound)

WORK="${KLT_SIM_WORK:-$(mktemp -d -t sg13g2-klt-${EXP}-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_klt_sim.sh: work dir ${WORK}"

CORNER_LABELS=(typ bcs wcs sf fs)

# pex_instantiate_body OSDI_DIR PEX_BODY_REF [KEY=VALUE ...]
# The body template with @@OSDI_DIR@@, @@PEX_BODY@@ and each @@KEY@@ filled.
pex_instantiate_body() {
  local args=(-e "s|@@OSDI_DIR@@|${1}|g" -e "s|@@PEX_BODY@@|${2}|g") kv
  shift 2
  for kv in "$@"; do args+=(-e "s|@@${kv%%=*}@@|${kv#*=}|g"); done
  sed "${args[@]}" "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"
}

# pex_sanity_local [CORNERS_JSON]  (needs body.spice in WORK)
# One local typ/27C corner: request.json -> report.json, both in WORK.
# CORNERS_JSON is merged over the request's `corners` (e.g. a fixed supply rail).
pex_sanity_local() {
  local extra="${1:-}"
  [[ -n "${extra}" ]] || extra='{}'
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
  python3 - "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" "${WORK}/body.spice" \
    "${WORK}/sg13g2_corners.lib" "${WORK}/request.json" "${extra}" <<'PY'
import json, pathlib, sys
tmpl, body, bundle, out, extra = sys.argv[1:6]
req = json.loads(pathlib.Path(tmpl).read_text().replace("@@BODY@@", body).replace("@@CORNER_BUNDLE@@", bundle))
req["corners"]["process"] = ["typ"]
req["corners"].update(json.loads(extra))
req["corners"]["temperature_c"] = [27]
pathlib.Path(out).write_text(json.dumps(req, indent=2) + "\n")
PY
  ( cd "${WORK}" && "${KLT_BIN}" sim request.json --backend local --format json \
      -o artifacts > report.json )
}

# pex_batch_dispatch [EXTRA gen_pex_batch_requests.py ARGS ...]
# The --batch body: provision check, the local sanity gate, per-variant
# requests (one per process x VDDS entry, or per process when VDDS is unset),
# fleet submission (resumable, #332), and the record-side report fixup that
# repoints decks at locally resolvable files (the runner's staged include and
# the image's baked PDK paths do not exist here, and the adapter would ship
# device-less snapshots). Leaves WORK/report-merged.json.
pex_batch_dispatch() {
  local label vdd vid v
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  # The gate: no grid before the local sanity anchor passes.
  echo "run_klt_sim.sh: sanity gate before dispatch"
  "${SCRIPT_DIR}/run_klt_sim.sh" --sanity

  local gen=(python3 "${HARNESS_DIR}/gen_pex_batch_requests.py"
    --request-template "${EXP_DIR}/testbench/${STEM}.request.json.tmpl"
    --body-template "${BODY_TEMPLATE:-${EXP_DIR}/testbench/${STEM}.body.spice.tmpl}"
    --lib-root "${BATCH_LIB_ROOT}" --provision-script "${BATCH_PROVISION_SCRIPT}"
    --pdk "${PDK}" --work "${WORK}"
    --osdi "${BATCH_PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi")
  [[ -n "${VDDS[*]-}" ]] && gen+=(--supplies "${VDDS[@]}")
  "${gen[@]}" "$@"

  # Each request's body includes the generated PEX body by its bare staged
  # name; klt stages the include closure from the body's own directory.
  for label in "${CORNER_LABELS[@]}"; do
    if [[ -n "${VDDS[*]-}" ]]; then
      for vdd in "${VDDS[@]}"; do
        vid="-$(echo "${vdd}" | tr '.' 'p')"
        si_shard "request-${label}${vid}.json" "report-${label}${vid}.json" \
          "artifacts-${label}${vid}" "${label}/${vdd}V (3 points, one fleet job)"
      done
    else
      si_shard "request-${label}.json" "report-${label}.json" "artifacts-${label}" \
        "${label} (one fleet job)"
    fi
  done

  for label in "${CORNER_LABELS[@]}"; do
    for v in "${VDDS[@]-}"; do
      vid="${v:+-$(echo "${v}" | tr '.' 'p')}"
      sed "s|\"${BATCH_PDK_ROOT}/|\"${PDK_ROOT}/|g" "${WORK}/body-${label}${vid}.spice" \
        > "${WORK}/body-fixed-${label}${vid}.spice"
      python3 "${HARNESS_DIR}/fixup_batch_report.py" "${WORK}/report-${label}${vid}.json" \
        "${FIXUP_UNBOUND[@]}" --body "${WORK}/body-fixed-${label}${vid}.spice" \
        --runner-pdk-root "${BATCH_PDK_ROOT}" --local-pdk-root "${PDK_ROOT}" \
        --decks-out "${WORK}/decks-fixed-${label}${vid}" \
        -o "${WORK}/report-${label}${vid}-fixed.json"
    done
  done

  pex_merge_shards "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" "${WORK}" \
    "${WORK}/report-merged.json"
}

# pex_record_mint REPORT
# Mint evidence from REPORT. The adapter runs from WORK: the merged report's
# per-corner artifact paths are relative to the work dir the batch requests
# wrote into; the record's outputs go to the (absolute) experiment directory.
pex_record_mint() {
  # The generator's --sources-out file binds the record to the extraction it
  # was built from; klt_sim_evidence.py refuses an unbound PEX record.
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "$1" \
      --extraction-sources "${WORK}/extraction-sources.json" \
      --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
      --experiment "${EXP_DIR}" )
}
