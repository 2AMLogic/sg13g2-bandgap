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
#   BODY_TEMPLATE  (optional) the body template -- defaults to the
#          experiment's own ${EXP_DIR}/testbench/${STEM}.body.spice.tmpl.
#          Set BEFORE sourcing to make the submission identity below hash
#          the override too (the shared-wrapper case, issue #472); the
#          schematic benches call pex_schematic_dut_setup (below) after
#          sourcing instead, which renders their WORK copy with the live
#          XMSENSE width, and the identity stays on their own committed
#          template
#   PEX_BATCH_MAX_IN_FLIGHT  (optional) submit --batch's per-variant requests
#          concurrently, as one `klt sim --batch-set` with this many in
#          flight, instead of one blocking `klt sim` per request (#402);
#          PEX_BATCH_SET_OUTDIR (default `batch-set`) names its output dir
# Sourcing validates the CLI mode (positional args pass through), resolves
# klt / the PDK / the OSDI models, and sets: MODE SCRIPT_DIR SIM_DIR REPO_ROOT
# HARNESS_DIR EXP_DIR KLT_BIN PDK_ROOT OSDI_DIR BATCH_PDK_ROOT BATCH_LIB_ROOT
# BATCH_PROVISION_SCRIPT IDENT_ARGS FIXUP_UNBOUND WORK CORNER_LABELS.
# Then the runner defines its anchors and a `case "${MODE}"` using the
# pex_* helpers below. No simulation is launched from here directly.

# The `klt sim` runner preamble below the mode check is shared with
# cmos5l_runner.sh (sim/harness/klt_sim_preamble.sh, issue #481): each block
# is a sourced function that returns non-zero, and this base -- which runs at
# source time, top level -- turns a failure into its `exit` here. Only what
# is genuinely PEX-runner-specific stays in this file: the pex_merge_call.sh
# sourcing, CORNER_LABELS, BATCH_LIB_ROOT, and the PEX --extra/--declare list
# appended to the shared IDENT_ARGS.
# shellcheck source=klt_sim_preamble.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/klt_sim_preamble.sh"

MODE="${1:-}"
klt_sim_mode "${MODE}" || exit $?

klt_sim_dirs "${BASH_SOURCE[1]}"

klt_sim_require_klt || exit $?

klt_sim_resolve_pdk || exit $?
source "${HARNESS_DIR}/pex_merge_call.sh"

klt_sim_require_osdi SG13G2_OSDI_DIR " -- run sim/tools/build-osdi.sh." || exit $?

# BATCH_LIB_ROOT is the root of the body's selection-form `.lib` cards. klt
# 0.8.x refuses an absolute runner path there ("not under $PDK_ROOT") and
# accepts one under the SUBMITTING host's $PDK_ROOT, which it rewrites for the
# runner -- so it is the local PDK root, never the runner's, and not overridable.
BATCH_LIB_ROOT="${PDK_ROOT}"
klt_sim_batch_defaults

# One body template for all three uses below -- the identity declaration's
# --extra, the sanity instantiation and the batch request generator.
# Default: the experiment's own per-stem committed template; an experiment
# whose DUT wrapper is byte-identical to a sibling's points the override at
# that shared template instead (issue #472).
BODY_TEMPLATE="${BODY_TEMPLATE:-${EXP_DIR}/testbench/${STEM}.body.spice.tmpl}"

# The schematic benches' record spec (#670): harness state, set unconditionally
# at source time and reset by pex_schematic_dut_setup -- a caller's exported
# RECORD_SPEC or _SCHEMATIC_RECORD_SPEC never reaches schematic_record_mint.
_SCHEMATIC_RECORD_SPEC="${EXP_DIR}/testbench/${STEM}.record-spec.json"

klt_sim_resume_scaffold
IDENT_ARGS+=(
  --declare "batch_lib_root=submitter-pdk-root"
  --extra "${EXP_DIR}/testbench/${STEM}.request.json.tmpl"
  --extra "${BODY_TEMPLATE}"
  --extra "${BATCH_PROVISION_SCRIPT}"
  --extra "${HARNESS_DIR}/klt_corner_bundle.py"
  --extra "${HARNESS_DIR}/seed_deck.py"
  --extra "${SIM_DIR}/tools/gen_pex_netlist_body.py")

klt_sim_work_dir "${MODE}" || exit $?

CORNER_LABELS=(typ bcs wcs sf fs)

# pex_instantiate_body OSDI_DIR PEX_BODY_REF [KEY=VALUE ...]
# The body template with @@OSDI_DIR@@, @@PEX_BODY@@ and each @@KEY@@ filled.
pex_instantiate_body() {
  local args=(-e "s|@@OSDI_DIR@@|${1}|g" -e "s|@@PEX_BODY@@|${2}|g") kv
  shift 2
  for kv in "$@"; do args+=(-e "s|@@${kv%%=*}@@|${kv#*=}|g"); done
  sed "${args[@]}" "${BODY_TEMPLATE}"
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
  klt_sim_require_provision || exit $?
  # The gate: no grid before the local sanity anchor passes.
  echo "run_klt_sim.sh: sanity gate before dispatch"
  "${SCRIPT_DIR}/run_klt_sim.sh" --sanity

  local generator="${HARNESS_DIR}/gen_pex_batch_requests.py"
  local -a IDENT_ARGS=("${IDENT_ARGS[@]}" --extra "${generator}")
  local gen=(python3 "${generator}"
    --request-template "${EXP_DIR}/testbench/${STEM}.request.json.tmpl"
    --body-template "${BODY_TEMPLATE}"
    --lib-root "${BATCH_LIB_ROOT}" --provision-script "${BATCH_PROVISION_SCRIPT}"
    --pdk "${PDK}" --work "${WORK}"
    --osdi "${BATCH_PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi")
  [[ -n "${VDDS[*]-}" ]] && gen+=(--supplies "${VDDS[@]}")
  "${gen[@]}" "$@"

  # Each request's body includes the generated PEX body by its bare staged
  # name; klt stages the include closure from the body's own directory.
  #
  # PEX_BATCH_MAX_IN_FLIGHT set (the experiment opts in): the whole campaign
  # goes to one `klt sim --batch-set` with that many requests in flight at
  # once, so the shards run concurrently on the fleet rather than one fleet
  # round-trip after another (issue #402). Unset: the historical one-request-
  # at-a-time path, unchanged.
  if [[ -n "${PEX_BATCH_MAX_IN_FLIGHT:-}" ]]; then
    si_set_reset
  fi
  for label in "${CORNER_LABELS[@]}"; do
    if [[ -n "${VDDS[*]-}" ]]; then
      for vdd in "${VDDS[@]}"; do
        vid="-$(echo "${vdd}" | tr '.' 'p')"
        if [[ -n "${PEX_BATCH_MAX_IN_FLIGHT:-}" ]]; then
          si_set_add "request-${label}${vid}.json" "report-${label}${vid}.json" \
            "${label}/${vdd}V"
        else
          si_shard "request-${label}${vid}.json" "report-${label}${vid}.json" \
            "artifacts-${label}${vid}" "${label}/${vdd}V (3 points, one fleet job)"
        fi
      done
    elif [[ -n "${PEX_BATCH_MAX_IN_FLIGHT:-}" ]]; then
      si_set_add "request-${label}.json" "report-${label}.json" "${label}"
    else
      si_shard "request-${label}.json" "report-${label}.json" "artifacts-${label}" \
        "${label} (one fleet job)"
    fi
  done
  if [[ -n "${PEX_BATCH_MAX_IN_FLIGHT:-}" ]]; then
    si_set_dispatch "${PEX_BATCH_SET_OUTDIR:-batch-set}" "${PEX_BATCH_MAX_IN_FLIGHT}" || true
  fi

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

# schematic_record_mint REPORT
# The schematic twin of pex_record_mint: same adapter call, same WORK-
# relative artifact paths, but no extraction to bind -- the DUT is the
# committed schematic, so there is no --extraction-sources.
schematic_record_mint() {
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "$1" \
      --spec "${_SCHEMATIC_RECORD_SPEC}" \
      --experiment "${EXP_DIR}" )
}

# pex_schematic_dut_setup [--dut-template PATH] [--record-spec PATH]
#                         [EXTRA_IDENT_FILE ...]
# (Shared by the six schematic-DUT benches, issue #650 -- the block every one
# of them used to re-type after sourcing this file and its family runner.)
# XMSENSE's width from the live startup netlist (sim/lib/msense_width.sh,
# cached in WORK/msense_w.txt), the experiment's committed body template
# rendered with @@MSENSE_W@@ into WORK -- the post-source BODY_TEMPLATE
# override the header above documents, so the identity keeps hashing the
# committed template -- and the three schematic netlists plus each
# EXTRA_IDENT_FILE (the report enricher whose output the record binds to)
# appended to IDENT_ARGS. A render source other than the committed template
# (the PSRR bench's PROPOSAL variants, #631) is the explicit --dut-template
# flag, never an ambient DUT_TEMPLATE variable (#670), and rides the identity
# from here. --record-spec names the spec schematic_record_mint binds records
# with; unknown flags are refused. Call it AFTER sourcing this file and
# BEFORE the family runner's main.
pex_schematic_dut_setup() {
  local default_dut="${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"
  local dut_template="${default_dut}"
  local extra_ident=()
  # Harness state, not caller environment (#670): the reset keeps an
  # inherited _SCHEMATIC_RECORD_SPEC (or one left by an earlier call) from
  # renaming minted evidence; --record-spec is the only override.
  _SCHEMATIC_RECORD_SPEC="${EXP_DIR}/testbench/${STEM}.record-spec.json"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dut-template|--record-spec)
        # A missing, empty or dash-prefixed value is a swallowed flag, not
        # a path; a dash-leading filename is spelled ./-name.
        if [[ $# -lt 2 || -z "$2" || "$2" == -* ]]; then
          echo "pex_schematic_dut_setup: $1 needs a value (got '${2-}')" >&2
          return 2
        fi
        # Anchor to the caller's directory now: the mint later runs from WORK.
        local val="$2"
        [[ "${val}" == /* ]] || val="${PWD}/${val}"
        if [[ "$1" == "--dut-template" ]]; then
          dut_template="${val}"
        else
          _SCHEMATIC_RECORD_SPEC="${val}"
        fi
        shift 2
        ;;
      -*)
        echo "pex_schematic_dut_setup: unknown option $1" >&2
        return 2
        ;;
      *)
        extra_ident+=("$1")
        shift
        ;;
    esac
  done
  # XMSENSE's width from the live startup netlist, as every closed-loop bench does.
  # shellcheck source=../lib/msense_width.sh
  source "${SIM_DIR}/lib/msense_width.sh"
  ( cd "${REPO_ROOT}" && read_msense_width "design/netlist/bandgap_startup.spice" \
      && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
  MSENSE_W="$(<"${WORK}/msense_w.txt")"
  BODY_TEMPLATE="${WORK}/body.spice.tmpl"
  sed "s|@@MSENSE_W@@|${MSENSE_W}|g" "${dut_template}" > "${BODY_TEMPLATE}"
  local f
  IDENT_ARGS+=(--extra "${REPO_ROOT}/design/netlist/bandgap_startup.spice"
    --extra "${REPO_ROOT}/design/netlist/bandgap_core.spice"
    --extra "${REPO_ROOT}/design/netlist/bandgap_amp.spice")
  # A non-default render source is bound to the identity here (#670): the
  # committed template already rides IDENT_ARGS from source time, and
  # re-adding it would trip submission_identity.py's duplicate --extra name.
  # Compare resolved files, so a relative spelling of the committed
  # template is still recognised as the default.
  if [[ "$(readlink -f -- "${dut_template}")" != "$(readlink -f -- "${default_dut}")" ]]; then
    IDENT_ARGS+=(--extra "${dut_template}")
  fi
  # ${arr[@]+...}: an empty array is unbound under set -u on Bash < 4.4.
  for f in ${extra_ident[@]+"${extra_ident[@]}"}; do IDENT_ARGS+=(--extra "${f}"); done
}
