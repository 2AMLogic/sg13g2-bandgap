#!/usr/bin/env bash
# sg13g2-bandgap -- `klt sim` harness self-test (issue #275).
#
#   sim/harness/probe/run_probe.sh
#
# Runs ONE corner (typ / 27 C / 3.30 V) of sim/core-open-loop-bias's own
# committed claim through `klt sim` instead of through that experiment's
# `run_pvt_sweep.sh` shell loop, then runs `sim/harness/klt_sim_evidence.py`
# over the resulting report into a scratch directory. Nothing it writes is
# committed: this is the standing proof that the harness works, not evidence.
#
# WHY A SINGLE CORNER, AND WHY LOCAL BY DEFAULT. The dispatch hosts this
# repo's agents run on forbid hand-looping `ngspice -b` over a corner grid
# and direct multi-corner work to `klt sim`'s batch backend; a single debug
# corner is explicitly allowed to run locally, which is exactly what the
# default mode is. Do not "helpfully" widen the grid here -- the
# five-experiment grids belong on the batch fleet.
#
# `--batch` (issue #277) runs the SAME one-corner request on the batch
# fleet's runner image instead of locally: the acceptance proof that an
# SG13G2 netlist simulates end-to-end through `klt sim --backend batch`
# now that the image bakes ihp-sg13g2 + OSDI + ngspice 46 (2am's
# `build-ihp-pdk-artifact.py`, launch template v4). The runner image pins
# klt 0.5.0 (see 2am infra/aws/batch-image.md "Why 0.5.0"), whose request
# schema cannot express a multi-file corner bundle -- one `models.lib`
# only, and klayout-tools #2522's per-section libraries are not in it --
# so the batch request splits the typ corner the local request selects
# from the generated bundle across the two channels 0.5.0 does have:
#   - `corners.process: ["hbt_typ"]` + a PDK-RELATIVE `models.lib`
#     (cornerHBT.lib): both hosts resolve it through their own PDK install
#     (`find_pdk`; the image exports PDK_ROOT=/opt/pdk), and the generated
#     bundle cannot ride along instead because `models` is resolved on the
#     executing host -- an operator-local path is meaningless there;
#   - the other two families' sections (mos_tt, res_typ, from the same
#     CORNER_SECTIONS["typ"] entry) become body-level `.lib` selection
#     cards against the image's baked PDK root, which ngspice accepts
#     verbatim (verified: selection-form `.lib` cards are plain-deck
#     syntax; definition-form `.lib NAME ... .endl` blocks are not -- they
#     are only readable in library mode, which is why the bundle itself
#     must never be `.include`d).
# The body's `pre_osdi` cards point at the image's OSDI directory for the
# same off-host reason (options.osdi_preload is refused off-host by
# design: an .osdi is a host-architecture binary). This bridge is
# single-corner-shaped by construction (body cards cannot vary per
# corner); the five-corner grids need the image's klt pin bumped to a
# release carrying #2522 -- see sim/harness/README.md. The submitting
# host's `klt` must itself carry the batch backend (klayout-tools 0.6.0+,
# e.g. a main-checkout venv; the PyPI 0.5.0 this repo's dispatch hosts
# ship as `klt` predates it) -- override the binary with
# KLT_SIM_PROBE_KLT. Cost: one fleet job, one corner, bounded by the
# fleet's own per-job ceiling and shared-budget caps.
#
# What it asserts, in order (both modes):
#   1. sim/harness/klt_corner_bundle.py's corner->section table still agrees
#      with sim/lib/pvt_preflight.sh's own maps.
#   2. ngspice honours a `pre_osdi` card in a `.control` block reached through
#      `.include` -- the one deviation from `klt sim`'s netlist-body contract
#      that an OSDI PDK forces (see the body file's header).
#   3. A nested corner-bundle `.lib` resolves (the multi-file-corner
#      workaround; batch mode: the body-level per-family `.lib` selection
#      cards resolve).
#   4. `klt sim` reproduces sim/core-open-loop-bias's committed
#      typ/27C/3.30V point to within ANCHOR_TOL_V -- i.e. the harness change
#      moves no number.
#   5. klt_sim_evidence.py emits a record/CSV/log/snapshot quadruple that
#      .github/scripts/check_evidence_formats.py's own record checks accept,
#      and whose snapshot inlines the DUT's devices (the D2 rule needs them
#      present, not behind an `.include`).
set -euo pipefail

BATCH_MODE=0
if [[ "${1:-}" == "--batch" ]]; then
  BATCH_MODE=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: run_probe.sh [--batch]" >&2
  exit 2
fi
# The `klt` that submits. Batch mode needs one carrying the batch backend
# (0.6.0+); local mode works with the PyPI 0.5.0 the dispatch hosts ship.
KLT_BIN="${KLT_SIM_PROBE_KLT:-klt}"
# The runner image's baked PDK root (2am batch-image-pins.env BAKED_PDK_ROOT)
# and the provision script `klt` shells out to on this host.
BATCH_PDK_ROOT="${KLT_SIM_PROBE_BATCH_PDK_ROOT:-/opt/pdk}"
BATCH_PROVISION_SCRIPT="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SIM_DIR="$(cd "${HARNESS_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

# Committed anchor: sim/core-open-loop-bias/records/20261001-082455-f748685.csv,
# row `typ,hbt_typ,mos_tt,res_typ,27,3.30,PASS,...`. The trim-bearing
# schematic core at the ratified default code (trim_code=128, issue #264).
ANCHOR_VREF_V="1.052707"
ANCHOR_R1_OHM="66057.04"
ANCHOR_TOL_V="0.00002"
ANCHOR_TOL_OHM="2.0"

# shellcheck source=../../env.sh
source "${SIM_DIR}/env.sh"
command -v "${KLT_BIN}" >/dev/null 2>&1 \
  || { echo "run_probe.sh: klt binary '${KLT_BIN}' not found (KLT_SIM_PROBE_KLT)." >&2; exit 3; }
if [[ "${BATCH_MODE}" -eq 0 ]]; then
  # Local preflights: this host must itself resolve the PDK, ngspice, and the
  # compiled OSDI models, because the local engine runs here.
  if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
    echo "run_probe.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see above." >&2
    exit 3
  fi
  command -v ngspice >/dev/null 2>&1 \
    || { echo "run_probe.sh: ngspice not on PATH." >&2; exit 3; }
  if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
    echo "run_probe.sh: OSDI device models missing -- run sim/tools/build-osdi.sh first." >&2
    exit 3
  fi
  OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"
else
  # Batch preflights: the PDK, ngspice, and the OSDI models live on the
  # runner image; this host only submits (S3 job contract via the fleet's
  # provision script -- an aws PROFILE name, never a credential).
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_probe.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    echo "             (KLT_BATCH_PROVISION_SCRIPT) -- see klt sim docs, 'Batch backend'." >&2
    exit 3
  fi
  OSDI_DIR="${BATCH_PDK_ROOT}/${PDK:-ihp-sg13g2}/libs.tech/ngspice/osdi"
  echo "run_probe.sh: batch mode (image PDK root ${BATCH_PDK_ROOT})"
fi

WORK="${KLT_SIM_PROBE_WORK:-$(mktemp -d -t sg13g2-klt-sim-probe-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_probe.sh: work dir ${WORK}"

# --- 1. corner-section table has not drifted from the shell maps -------------
python3 "${HARNESS_DIR}/klt_corner_bundle.py" --check-preflight "${SIM_DIR}/lib/pvt_preflight.sh"
if [[ "${BATCH_MODE}" -eq 0 ]]; then
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
fi

# --- netlist body + the trim ladder, spliced from the design netlist ---------
# The ladder is taken straight out of design/netlist/bandgap_core.spice rather
# than copied into the body, so the probe's DUT provenance is the committed
# schematic by construction.
python3 - "${REPO_ROOT}/design/netlist/bandgap_core.spice" "${WORK}/bandgap_trim.inc" <<'PY'
import pathlib, re, sys
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"^\.subckt bandgap_trim\b.*?^\.ends\s*$", src, re.M | re.S)
if match is None:
    raise SystemExit("run_probe.sh: no `.subckt bandgap_trim` block in the design netlist")
pathlib.Path(sys.argv[2]).write_text(match.group(0) + "\n", encoding="utf-8")
PY

if [[ "${BATCH_MODE}" -eq 0 ]]; then
  sed -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@TRIM_SUBCKT@@|${WORK}/bandgap_trim.inc|g" \
      "${SCRIPT_DIR}/core_open_loop_bias.body.spice" > "${WORK}/body.spice"
  sed -e "s|@@BODY@@|${WORK}/body.spice|g" \
      -e "s|@@CORNER_BUNDLE@@|${WORK}/sg13g2_corners.lib|g" \
      "${SCRIPT_DIR}/request.json.tmpl" > "${WORK}/request.json"
else
  # Batch body: OSDI cards name the image's baked directory, and the trim
  # ladder rides the include closure as a bare name beside the body (klt
  # stages `.include` targets flat into the job's inputs/ and rewrites the
  # directives; ngspice resolves a relative `.include` against the directory
  # of the file carrying it, and the staged files land side by side there).
  sed -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
      -e "s|@@TRIM_SUBCKT@@|bandgap_trim.inc|g" \
      "${SCRIPT_DIR}/core_open_loop_bias.body.spice" > "${WORK}/body.spice"
  sed -e "s|@@BODY@@|${WORK}/body.spice|g" \
      -e "s|@@CORNER_BUNDLE@@|UNUSED-BATCH-REWRITTEN-BELOW|g" \
      "${SCRIPT_DIR}/request.json.tmpl" > "${WORK}/request.json"
  # Rewrite the request for the 0.5.0 runner (header comment explains the
  # split) and append the body-level `.lib` selection cards for the two
  # families the request's single models.lib cannot reach. All three
  # sections come from CORNER_SECTIONS["typ"] -- the same table assertion 1
  # just proved against pvt_preflight.sh.
  python3 - "${WORK}/request.json" "${WORK}/body.spice" "${BATCH_PDK_ROOT}" \
    "${BATCH_PROVISION_SCRIPT}" "${HARNESS_DIR}" <<'PY'
import importlib.util, json, os, pathlib, sys

request_path, body_path, pdk_root, provision_script, harness_dir = sys.argv[1:6]
spec = importlib.util.spec_from_file_location(
    "klt_corner_bundle", pathlib.Path(harness_dir) / "klt_corner_bundle.py"
)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
hbt, mos, res = bundle.CORNER_SECTIONS["typ"]
pdk = os.environ.get("PDK", "ihp-sg13g2")
models_dir = f"{pdk_root}/{pdk}/libs.tech/ngspice/models"

request = json.loads(pathlib.Path(request_path).read_text(encoding="utf-8"))
# PDK-relative lib: joined against the RESOLVED VARIANT directory on each
# host (find_pdk on both ends), never against the request's directory.
request["backend"] = "batch"
request["models"] = {"pdk": pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
request["corners"]["process"] = [hbt]
request["batch"] = {"provision_script_path": provision_script}
pathlib.Path(request_path).write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

body = pathlib.Path(body_path)
body.write_text(
    body.read_text(encoding="utf-8")
    + f"""
* Batch mode only (issue #277): the two families the request's single
* models.lib (klt 0.5.0 on the runner) cannot reach, as selection-form
* `.lib` cards against the image's baked PDK root. Same CORNER_SECTIONS
* entry the deck's own card selects the HBT family from.
.lib "{models_dir}/cornerMOShv.lib" {mos}
.lib "{models_dir}/cornerRES.lib" {res}
""",
    encoding="utf-8",
)
PY
fi

# --- 2/3/4. one corner through klt sim --------------------------------------
if [[ "${BATCH_MODE}" -eq 0 ]]; then
  # `--backend local` is explicit on purpose: the dispatch hosts export
  # KLT_SIM_BACKEND=batch, and a one-corner debug probe is the case that is
  # meant to stay local.
  "${KLT_BIN}" sim "${WORK}/request.json" --backend local --format json \
    -o "${WORK}/artifacts" > "${WORK}/report.json"
else
  # One fleet job: spot acquisition + boot + one corner. Default poll budget
  # is options.timeout_s*corners + 120s job + 1800s slack -- minutes, not
  # seconds; the artifacts tree (per-corner log + deck) is pulled back so
  # assertions 2/3/5 run on what the instance actually wrote.
  "${KLT_BIN}" sim "${WORK}/request.json" --backend batch --format json \
    -o "${WORK}/artifacts" > "${WORK}/report.json"
  python3 - "${WORK}/report.json" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
remote = (report.get("environment") or {}).get("remote") or {}
for key in ("job_id", "ami_id", "instance_type", "state", "exit_code"):
    print(f"  batch {key}: {remote.get(key)}")
PY
fi

python3 - "${WORK}/report.json" "${ANCHOR_VREF_V}" "${ANCHOR_TOL_V}" \
           "${ANCHOR_R1_OHM}" "${ANCHOR_TOL_OHM}" "${BATCH_MODE}" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
anchor_v, tol_v, anchor_r, tol_r = (float(a) for a in sys.argv[2:6])
batch_mode = sys.argv[6] == "1"
if report["status"] != "pass":
    raise SystemExit(f"run_probe.sh: klt sim graded the run {report['status']!r}")
(corner,) = report["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
for name, anchor, tol in (("vref_v", anchor_v, tol_v), ("r1_ohm", anchor_r, tol_r)):
    value = got.get(name)
    if value is None:
        raise SystemExit(f"run_probe.sh: measurement {name} did not come back")
    delta = abs(value - anchor)
    verdict = "ok" if delta <= tol else "FAIL"
    print(f"  {name:9s} = {value!r} (anchor {anchor}, delta {delta:.3g}) {verdict}")
    if delta > tol:
        raise SystemExit(
            f"run_probe.sh: {name} is {delta:.3g} off the committed anchor -- the "
            "harness is moving a number it must not move"
        )
log = pathlib.Path(corner["artifacts"]["log"]).read_text(encoding="utf-8")
if "osdi" not in log.lower() and "Unable to find definition of model" in log:
    raise SystemExit("run_probe.sh: OSDI preload from the included .control block did not take")
print("  OSDI preload via an included .control block: ok")
if batch_mode:
    print("  body-level per-family .lib selection cards: ok")
else:
    print("  nested corner-bundle .lib resolution: ok")
PY

# --- 5. the evidence adapter, into a scratch experiment tree -----------------
SCRATCH_EXP="${WORK}/scratch-experiment"
mkdir -p "${SCRATCH_EXP}/testbench"
cp "${SCRIPT_DIR}/core_open_loop_bias.body.spice" "${SCRATCH_EXP}/testbench/"
cp "${SCRIPT_DIR}/request.json.tmpl" "${SCRATCH_EXP}/testbench/"
: > "${SCRATCH_EXP}/run_probe_placeholder.sh"
cp "${SCRIPT_DIR}/record-spec.json" "${WORK}/record-spec.json"

if [[ "${BATCH_MODE}" -eq 1 ]]; then
  # Assertion 5 runs the adapter over the report the instance produced. The
  # pulled deck's `.include` of the staged netlist names the INSTANCE's job
  # directory, which does not exist here -- repoint it at the local batch
  # body (whose own relative includes resolve beside it in this work dir, and
  # which is byte-for-byte the body that was staged). The spec also learns
  # the image's PDK root, so the snapshot's `${PDK_ROOT}`-relative rewrite
  # targets the paths the deck actually carries.
  python3 - "${WORK}/report.json" "${WORK}/body.spice" "${WORK}/record-spec.json" \
    "${WORK}/request.json" "${BATCH_PDK_ROOT}" <<'PY'
import json, pathlib, re, sys
report_path, body_path, spec_path, request_path, pdk_root = sys.argv[1:6]
report = json.loads(pathlib.Path(report_path).read_text(encoding="utf-8"))
label = (json.loads(pathlib.Path(request_path).read_text(encoding="utf-8"))
         ["corners"]["process"][0])
include_re = re.compile(r"^(\s*\.include\s+)(\S+)(.*)$", re.IGNORECASE)
for corner in report.get("corners", []):
    deck = (corner.get("artifacts") or {}).get("deck")
    if not deck or not pathlib.Path(deck).is_file():
        continue
    lines = []
    for line in pathlib.Path(deck).read_text(encoding="utf-8").splitlines():
        match = include_re.match(line)
        if match and pathlib.PurePath(match.group(2)).name == "netlist.cir":
            line = match.group(1) + body_path + match.group(3)
        lines.append(line)
    pathlib.Path(deck).write_text("\n".join(lines) + "\n", encoding="utf-8")
spec = json.loads(pathlib.Path(spec_path).read_text(encoding="utf-8"))
spec["pdk_root"] = pdk_root
# The batch corner label is the HBT section name (the process axis carries
# it -- see the header); relabel the spec's per-corner column maps so the
# CSV's section columns still populate from the same "typ" row.
for values in (spec.get("extra_columns") or {}).values():
    if "typ" in values:
        values[label] = values["typ"]
pathlib.Path(spec_path).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
PY
fi

python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
  --report "${WORK}/report.json" \
  --spec "${WORK}/record-spec.json" \
  --experiment "${SCRATCH_EXP}" \
  --record-id "20260101-000000-0000000"

python3 - "${SCRATCH_EXP}" "${REPO_ROOT}" <<'PY'
import pathlib, sys
exp = pathlib.Path(sys.argv[1])
rid = "20260101-000000-0000000"
sys.path.insert(0, str(pathlib.Path(sys.argv[2]) / ".github" / "scripts"))
from _ci_common import Report  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "cef", pathlib.Path(sys.argv[2]) / ".github" / "scripts" / "check_evidence_formats.py"
)
cef = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cef)

report = Report()
cef.check_record(exp / "records" / f"{rid}.md", exp, report)
if report.problems:
    for problem in report.problems:
        print("  record-format FAIL:", problem)
    raise SystemExit("run_probe.sh: the adapter's record does not satisfy check_record()")
print("  check_record() on the adapter's output: ok")

snapshot = (exp / "netlist-snapshots" / rid).glob("*.spice")
snapshot = next(iter(sorted(snapshot)))
devices = cef.spice_instances(snapshot.read_text(encoding="utf-8"))
dut = cef.spice_instances(
    (pathlib.Path(sys.argv[2]) / "design" / "netlist" / "bandgap_core.spice").read_text(
        encoding="utf-8"
    )
)
absent = [name for name in dut if name not in devices]
print(f"  snapshot inlines {len(devices)} instances; {len(absent)} of the DUT's are absent")
if absent:
    raise SystemExit(
        "run_probe.sh: the snapshot does not inline the DUT's own devices, so the D2 "
        f"freshness rule cannot see them (first missing: {absent[:5]})"
    )
if "${PDK_ROOT}" not in snapshot.read_text(encoding="utf-8"):
    raise SystemExit("run_probe.sh: snapshot carries no ${PDK_ROOT}-relative model-library card")
print("  snapshot is self-contained and host-path-free: ok")
PY

echo "run_probe.sh: PASS (work dir kept at ${WORK})"
