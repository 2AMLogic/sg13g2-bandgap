#!/usr/bin/env bash
# sg13g2-bandgap -- core-open-loop-bias-pex on the `klt sim` harness
# (issue #278, the remaining half of #275).
#
#   sim/core-open-loop-bias-pex/run_klt_sim.sh --sanity   # one local corner, vs #272's anchor
#   sim/core-open-loop-bias-pex/run_klt_sim.sh --batch    # the 45-point PVT grid, on the fleet
#   sim/core-open-loop-bias-pex/run_klt_sim.sh --record   # mint evidence from a merged report
#
# WHY THIS SHAPE. The dispatch hosts this repo's agents run on direct
# multi-corner work to `klt sim`'s batch backend and allow single corners
# only to the local engine -- `--sanity` is that one allowed local corner,
# and it is a GATE: the grid is not dispatched until it reproduces #272's
# own one-point probe on this same extraction (vref 1.052999 V, R1_eff
# 66123 ohm at typ/27C/3.30V), because "a first refreshed grid point far
# from 1.0530 V means the template, not the extraction, is wrong" (#278's
# own sanity-gate item).
#
# THE PER-PROCESS BATCH BRIDGE. The batch runner image pins klt 0.5.0,
# whose request schema carries ONE model library -- and SG13G2's corner
# set spans three per-device-family files, so a five-process grid cannot
# vary the process within one request (klayout-tools#2668; see
# sim/harness/README.md "The batch fleet"). This runner therefore sends
# one request per process corner, exactly the single-corner bridge
# sim/harness/probe/run_probe.sh --batch proved, widened over the
# temperature/supply axes the request schema does sweep natively:
#   - `corners.process: [<hbt section>]` + a PDK-relative cornerHBT.lib
#     through `models` (resolved on the runner through its own PDK
#     install);
#   - the MOS-hv/resistor sections for that same corner as body-level
#     `.lib` selection cards against the image's baked PDK root;
#   - the supply axis rides `corners.supply_v` (this bench's rail source
#     is a plain alterable DC source), the temperature axis
#     `corners.temperature_c`.
# The five reports are merged deterministically
# (sim/harness/merge_batch_shards.py) and the adapter mints one record.
#
# Resumable: a per-process report that already exists and passed is not
# re-submitted, so an interrupted grid continues where it stopped.
set -euo pipefail

MODE="${1:-}"
case "${MODE}" in
  --sanity|--batch|--record) ;;
  *)
    echo "usage: run_klt_sim.sh --sanity | --batch | --record" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
HARNESS_DIR="${SIM_DIR}/harness"
EXP="core-open-loop-bias-pex"
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
BATCH_PDK_ROOT="${KLT_SIM_BATCH_PDK_ROOT:-/opt/pdk}"
BATCH_PROVISION_SCRIPT="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"

# #272's one-point probe on this same extraction: the sanity anchor.
ANCHOR_VREF_V="1.052999"
ANCHOR_R1_OHM="66123"
ANCHOR_TOL_V="0.0002"
ANCHOR_TOL_OHM="10"

WORK="${KLT_SIM_WORK:-$(mktemp -d -t sg13g2-klt-${EXP}-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_klt_sim.sh: work dir ${WORK}"

CORNER_LABELS=(typ bcs wcs sf fs)

# --- the DUT body (generated, with this bench's per-leg ammeters cut in) ---
python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" \
  --ammeter XM1:3:Vm1 --ammeter XM2A:3:Vm2a --ammeter XM2B:3:Vm2b \
  --ammeter XM3A:3:Vm3a --ammeter XM3B:3:Vm3b --ammeter XM3C:3:Vm3c \
  -o "${WORK}/pex_body.inc"

instantiate_body() {  # $1 = OSDI dir, $2 = PEX body reference for the include
  sed -e "s|@@OSDI_DIR@@|${1}|g" -e "s|@@PEX_BODY@@|${2}|g" \
    "${EXP_DIR}/testbench/core_open_loop_bias_pex.body.spice.tmpl"
}

check_anchors() {  # $1 = report json, $2 = mode label
  python3 - "$1" "${ANCHOR_VREF_V}" "${ANCHOR_TOL_V}" "${ANCHOR_R1_OHM}" "${ANCHOR_TOL_OHM}" "$2" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
anchor_v, tol_v, anchor_r, tol_r, mode = sys.argv[2:7]
if report["status"] != "pass":
    raise SystemExit(f"sanity gate ({mode}): klt sim graded the run {report['status']!r}")
(corner,) = report["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
ok = True
for name, anchor, tol in (("vref_v", float(anchor_v), float(tol_v)),
                          ("r1_ohm", float(anchor_r), float(tol_r))):
    value = got.get(name)
    if value is None:
        raise SystemExit(f"sanity gate ({mode}): measurement {name} did not come back")
    delta = abs(value - anchor)
    verdict = "ok" if delta <= tol else "FAIL"
    print(f"  sanity {name:8s} = {value!r} (anchor {anchor}, delta {delta:.3g}) {verdict}")
    if delta > tol:
        ok = False
if not ok:
    raise SystemExit(
        f"sanity gate ({mode}): off #272's one-point anchor -- the bench, not "
        "the extraction, is wrong (issue #278's sanity-gate item)"
    )
print(f"  sanity gate ({mode}): PASS")
PY
}

case "${MODE}" in
--sanity)
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
  instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" > "${WORK}/body.spice"
  python3 - "${EXP_DIR}/testbench/core_open_loop_bias_pex.request.json.tmpl" "${WORK}/body.spice" \
    "${WORK}/sg13g2_corners.lib" "${WORK}/request.json" <<'PY'
import json, pathlib, sys
tmpl, body, bundle, out = sys.argv[1:5]
req = json.loads(pathlib.Path(tmpl).read_text().replace("@@BODY@@", body).replace("@@CORNER_BUNDLE@@", bundle))
req["corners"]["process"] = ["typ"]
req["corners"]["supply_v"] = {"Vvdd": [3.30]}
req["corners"]["temperature_c"] = [27]
pathlib.Path(out).write_text(json.dumps(req, indent=2) + "\n")
PY
  "${KLT_BIN}" sim "${WORK}/request.json" --backend local --format json \
    -o "${WORK}/artifacts" > "${WORK}/report.json"
  check_anchors "${WORK}/report.json" "local"
  ;;

--batch)
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  # --- the gate: no grid before the local sanity anchor passes -----------
  echo "run_klt_sim.sh: sanity gate before dispatch"
  "${SCRIPT_DIR}/run_klt_sim.sh" --sanity

  python3 - "${HARNESS_DIR}/klt_corner_bundle.py" "${EXP_DIR}/testbench/core_open_loop_bias_pex.request.json.tmpl" \
    "${EXP_DIR}/testbench/core_open_loop_bias_pex.body.spice.tmpl" \
    "${BATCH_PDK_ROOT}" "${BATCH_PROVISION_SCRIPT}" "${PDK}" "${WORK}" \
    "${BATCH_PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi" <<'PY'
import importlib.util, json, pathlib, sys

bundle_py, req_tmpl_path, body_tmpl_path, pdk_root, provision, pdk, work, osdi = sys.argv[1:9]
spec = importlib.util.spec_from_file_location("klt_corner_bundle", bundle_py)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

req_tmpl = pathlib.Path(req_tmpl_path)
body_tmpl = pathlib.Path(body_tmpl_path)
base = json.loads(req_tmpl.read_text())
models_dir = f"{pdk_root}/{pdk}/libs.tech/ngspice/models"
out = pathlib.Path(work)

for label, (hbt, mos, res) in bundle.CORNER_SECTIONS.items():
    body_text = (
        body_tmpl.read_text()
        .replace("@@OSDI_DIR@@", osdi)
        .replace("@@PEX_BODY@@", "pex_body.inc")
        + f"""
* Batch mode only (issue #278 per-process bridge): the two families the
* request's single models.lib (klt 0.5.0 on the runner) cannot reach, as
* selection-form `.lib` cards against the image's baked PDK root. Same
* CORNER_SECTIONS entry the request's models.lib selects the HBT family
* from. Corner: {label}
.lib "{models_dir}/cornerMOShv.lib" {mos}
.lib "{models_dir}/cornerRES.lib" {res}
"""
    )
    (out / f"body-{label}.spice").write_text(body_text)
    req = json.loads(
        json.dumps(base)
        .replace("@@BODY@@", str(out / f"body-{label}.spice"))
        .replace("@@CORNER_BUNDLE@@", "UNUSED-BATCH")
    )
    req["backend"] = "batch"
    req["models"] = {"pdk": pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
    req["corners"]["process"] = [hbt]
    req["batch"] = {"provision_script_path": provision}
    (out / f"request-{label}.json").write_text(json.dumps(req, indent=2) + "\n")
print("per-process requests written")
PY

  # Each request's body includes the generated PEX body by its bare staged
  # name; klt stages the include closure from the body's own directory.
  for label in "${CORNER_LABELS[@]}"; do
    report="${WORK}/report-${label}.json"
    if [[ -s "${report}" ]] && python3 -c "
import json,sys; r=json.load(open('${report}')); sys.exit(0 if r['status']=='pass' else 1)" 2>/dev/null; then
      echo "run_klt_sim.sh: ${label} already complete, skipping"
      continue
    fi
    echo "run_klt_sim.sh: dispatching ${label} ($(python3 -c "
import json; r=json.load(open('${WORK}/request-${label}.json'));
print(len(r['corners']['supply_v']['Vvdd'])*len(r['corners']['temperature_c']))") points, one fleet job)"
    ( cd "${WORK}" && "${KLT_BIN}" sim "request-${label}.json" --backend batch \
        --format json -o "artifacts-${label}" > "report-${label}.json" ) || \
      echo "run_klt_sim.sh: ${label} graded non-pass -- recorded, continuing"
  done

  # Record-side fixup: repoint each report's decks at locally resolvable
  # files (the runner's staged include and the image's baked PDK paths do
  # not exist here, and the adapter would ship device-less snapshots).
  for label in "${CORNER_LABELS[@]}"; do
    sed "s|\"${BATCH_PDK_ROOT}/|\"${PDK_ROOT}/|g" "${WORK}/body-${label}.spice" \
      > "${WORK}/body-fixed-${label}.spice"
    python3 "${HARNESS_DIR}/fixup_batch_report.py" "${WORK}/report-${label}.json" \
      --body "${WORK}/body-fixed-${label}.spice" \
      --runner-pdk-root "${BATCH_PDK_ROOT}" --local-pdk-root "${PDK_ROOT}" \
      --decks-out "${WORK}/decks-fixed-${label}" \
      -o "${WORK}/report-${label}-fixed.json"
  done

  python3 "${HARNESS_DIR}/merge_batch_shards.py" -o "${WORK}/report-merged.json" \
    "typ=${WORK}/report-typ-fixed.json" "bcs=${WORK}/report-bcs-fixed.json" "wcs=${WORK}/report-wcs-fixed.json" \
    "sf=${WORK}/report-sf-fixed.json" "fs=${WORK}/report-fs-fixed.json"
  python3 - "${WORK}/report-merged.json" <<'PY'
import json, pathlib, sys
r = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(f"merged grid: {r['status']}  passed={r['passed']} failed={r['failed']} errored={r['errored']}")
for c in r["corners"]:
    if c["status"] != "pass":
        print(f"  {c['corner_id']}: {c['status']} {str(c.get('error'))[:120]}")
PY
  echo "run_klt_sim.sh: merged report at ${WORK}/report-merged.json"
  echo "                 mint evidence with: run_klt_sim.sh --record"
  ;;

--record)
  # Run the adapter from WORK: the merged report's per-corner artifact paths
  # are relative to the work dir the batch requests wrote into, and the
  # record's outputs go to the (absolute) experiment directory either way.
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-merged.json" \
      --spec "${EXP_DIR}/testbench/core_open_loop_bias_pex.record-spec.json" \
      --experiment "${EXP_DIR}" )
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
  echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
  ;;
esac
