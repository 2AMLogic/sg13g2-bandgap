#!/usr/bin/env bash
# sg13g2-bandgap -- trim-coverage (the trim-ladder range / resolution /
# linearity bench behind DR-0011's ratified Trim row, kept by DR-0014) on the
# `klt sim` harness (issue #416, Part of #412).
#
#   sim/trim-coverage/run_klt_sim.sh --sanity   # one typ/27C/3.30V/code-128 point vs the committed record
#   sim/trim-coverage/run_klt_sim.sh --batch    # the 169-point grid, on the fleet
#   sim/trim-coverage/run_klt_sim.sh --record   # mint evidence from the enriched report (KLT_SIM_WORK=<batch dir>)
#
# The grid is 17 requests: 15 (process x supply) groups at 27 C, each sweeping
# the 11 trim codes natively through `corners.params.trim_code`, plus the two
# typ/3.30V step-temperature probes (-40 and 125 C, codes 128/129). The
# supply and the .nodeset seeds are baked into a per-variant body (the seeds
# differ per variant); the runner image's single-models.lib carries one process
# per request (klayout-tools#2668). Mechanics: sim/harness/trim_coverage_klt.py.
# The old run_trim_coverage.sh is kept as the point-definition reference only:
# it must not be run as a grid on a dispatch host.
#
# SANITY GATE. One typ/27C/3.30V/code-128 point must land on the newest
# committed record's vref (1.047278 V); no grid is dispatched before it does.
# It runs locally by default (a single unit). A host whose ngspice cannot load
# the SG13G2 OSDI models (ngspice < 44 against v0.4 modules -- loom-worker-3 had
# ngspice-42, issue #416) sets KLT_SIM_SANITY_BACKEND=batch: still ONE point,
# on the fleet, never a local grid.
#
# HOST SETUP, as in sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh: a runner
# image whose klt differs from the host's needs KLT_SIM_SUBMIT_KLT (a wrapper
# running `uvx --from klayout-tools==X klt "$@"`). klt >= 0.8 wants the body's
# `.lib` paths under the SUBMITTING host's $PDK_ROOT (it rewrites them for the
# runner) -- BATCH_LIB_ROOT, set by pex_runner.sh, no override needed. The OSDI
# paths sit in the body's `.control` block, which klt does not rewrite, so they
# always name the runner image's baked root, KLT_SIM_BATCH_OSDI_ROOT (default
# /opt/pdk).
#
# Resumable: a per-request report that passed AND carries a matching submission
# identity (#332) is not re-submitted.
set -euo pipefail

# shellcheck disable=SC2034  # EXP/STEM are read by pex_runner.sh
EXP="trim-coverage"
STEM="trim_coverage"
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"

TC_PY="${HARNESS_DIR}/trim_coverage_klt.py"
BATCH_OSDI_ROOT="${KLT_SIM_BATCH_OSDI_ROOT:-/opt/pdk}"
SEED_CSV="$(ls -1 "${SIM_DIR}/closed-loop-startup/records/"*.csv | sort | tail -1)"
ANCHOR_VREF_V="1.047278"   # records/20260930-195507-9530863.csv typ_code128 27C 3.30V
ANCHOR_TOL_V="0.0005"

# XMSENSE's width from the live startup netlist, as every closed-loop bench does.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
if [[ "${MODE}" == "--record" && -f "${WORK}/msense_w.txt" ]]; then
  MSENSE_W="$(<"${WORK}/msense_w.txt")"
else
  ( cd "${REPO_ROOT}" && read_msense_width "design/netlist/bandgap_startup.spice" \
      && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
  MSENSE_W="$(<"${WORK}/msense_w.txt")"
fi
IDENT_ARGS+=(--extra "${TC_PY}" --extra "${SEED_CSV}" --declare "msense_w=${MSENSE_W}"
  --extra "${REPO_ROOT}/design/netlist/bandgap_core.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_trim.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_amp.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_startup.spice")

tc_sanity() {
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
  python3 "${TC_PY}" prepare --mode sanity \
    --request-template "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" \
    --body-template "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" \
    --work "${WORK}" --seed-csv "${SEED_CSV}" --msense-w "${MSENSE_W}" \
    --osdi-dir "${OSDI_DIR}" --bundle "${WORK}/sg13g2_corners.lib"
  local backend="${KLT_SIM_SANITY_BACKEND:-local}"
  if [[ "${backend}" == batch ]]; then
    # One point on the fleet needs the batch-shaped request (baked PDK root).
    python3 - "${WORK}" "${BATCH_LIB_ROOT}" "${PDK}" "${BATCH_PROVISION_SCRIPT}" "${BATCH_OSDI_ROOT}" <<'PY'
import json, pathlib, re, sys
work, root, pdk, prov, osdi_root = (pathlib.Path(sys.argv[1]), *sys.argv[2:6])
body = (work / "body.spice").read_text()
osdi_local = re.search(r"pre_osdi\s+(\S+)/psp103\.osdi", body).group(1)
body = body.replace(osdi_local, f"{osdi_root}/{pdk}/libs.tech/ngspice/osdi")
models = f"{root}/{pdk}/libs.tech/ngspice/models"
body += f'\n.lib "{models}/cornerMOShv.lib" mos_tt\n.lib "{models}/cornerRES.lib" res_typ\n'
(work / "body-sanity-batch.spice").write_text(body)
req = json.loads((work / "request.json").read_text())
req["netlist"] = str(work / "body-sanity-batch.spice")
req["backend"] = "batch"
req["models"] = {"pdk": pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
req["corners"]["process"] = ["hbt_typ"]
req["batch"] = {"provision_script_path": prov}
(work / "request.json").write_text(json.dumps(req, indent=2) + "\n")
PY
    ( cd "${WORK}" && "${KLT_SIM_SUBMIT_KLT:-${KLT_BIN}}" sim request.json --backend batch \
        --format json -o artifacts > report.json ) || true
  else
    ( cd "${WORK}" && "${KLT_BIN}" sim request.json --backend local --format json \
        -o artifacts > report.json ) || true
  fi
  python3 - "${WORK}/report.json" "${ANCHOR_VREF_V}" "${ANCHOR_TOL_V}" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
anchor_v, tol_v = float(sys.argv[2]), float(sys.argv[3])
if report.get("status") != "pass":
    raise SystemExit(f"sanity gate: klt sim graded the run {report.get('status')!r}: "
                     f"{[c.get('diagnostics') for c in report.get('corners', [])]}")
(corner,) = report["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
value = got.get("vref_v")
if value is None:
    raise SystemExit("sanity gate: vref_v did not come back")
delta = abs(value - anchor_v)
print(f"  sanity vref(code 128) = {value!r} (anchor {anchor_v}, delta {delta:.3g}) "
      f"{'ok' if delta <= tol_v else 'FAIL'}")
if delta > tol_v:
    raise SystemExit("sanity gate: off the committed typ/27C/3.30V code-128 record -- "
                     "the bench is wrong; no grid is dispatched")
print("  sanity gate: PASS")
PY
}

tc_batch() {
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  echo "run_klt_sim.sh: sanity gate before dispatch"
  tc_sanity

  python3 "${TC_PY}" prepare --mode batch \
    --request-template "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" \
    --body-template "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" \
    --work "${WORK}" --seed-csv "${SEED_CSV}" --msense-w "${MSENSE_W}" \
    --pdk "${PDK}" --batch-pdk-root "${BATCH_LIB_ROOT}" --batch-osdi-root "${BATCH_OSDI_ROOT}" \
    --provision "${BATCH_PROVISION_SCRIPT}"

  local sid label vdd temp req rep art body fixed decks codes
  while IFS=$'\t' read -r sid label vdd temp req rep art body fixed decks codes; do
    si_shard "${req}" "${rep}" "${art}" "${label}/${vdd}V/${temp}C codes ${codes} (one fleet job)"
  done < "${WORK}/manifest.tsv"

  # Record-side fixup: repoint each report's decks at locally resolvable files.
  while IFS=$'\t' read -r sid label vdd temp req rep art body fixed decks codes; do
    sed "s|\"${BATCH_PDK_ROOT}/|\"${PDK_ROOT}/|g" "${WORK}/body-${sid}.spice" > "${WORK}/${body}"
    python3 "${HARNESS_DIR}/fixup_batch_report.py" "${WORK}/${rep}" \
      "${FIXUP_UNBOUND[@]}" --body "${WORK}/${body}" \
      --runner-pdk-root "${BATCH_PDK_ROOT}" --local-pdk-root "${PDK_ROOT}" \
      --decks-out "${WORK}/${decks}" -o "${WORK}/${fixed}"
  done < "${WORK}/manifest.tsv"

  python3 "${TC_PY}" merge --manifest "${WORK}/manifest.tsv" --work "${WORK}" \
    --expect-grid "${WORK}/expected-grid.json" -o "${WORK}/report-merged.json"
  ( cd "${WORK}" && python3 "${TC_PY}" enrich "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json" )
  echo "run_klt_sim.sh: enriched report at ${WORK}/report-enriched.json"
  echo "                 mint evidence with: KLT_SIM_WORK=${WORK} run_klt_sim.sh --record"
}

tc_record() {
  python3 "${TC_PY}" spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
    --msense-w "${MSENSE_W}" -o "${WORK}/record-spec.json"
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-enriched.json" \
      --spec "${WORK}/record-spec.json" \
      --experiment "${EXP_DIR}" )
  local csv
  local f
  for f in "${EXP_DIR}"/records/*.csv; do   # ids sort by timestamp: the last is the new record
    [[ "${f}" == *-analysis.csv ]] || csv="${f}"
  done
  python3 "${TC_PY}" analysis "${csv}" -o "${csv%.csv}-analysis.csv"
}

case "${MODE}" in
--sanity) tc_sanity ;;
--batch) tc_batch ;;
--record) tc_record ;;
esac
