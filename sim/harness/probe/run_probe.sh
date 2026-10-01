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
# WHY A SINGLE CORNER, AND WHY LOCAL. The dispatch hosts this repo's agents
# run on forbid hand-looping `ngspice -b` over a corner grid and direct
# multi-corner work to `klt sim`'s batch backend; a single debug corner is
# explicitly allowed to run locally, which is exactly what this is. Do not
# "helpfully" widen the grid here -- the five-experiment grids belong on the
# batch fleet, and sim/harness/README.md records what still blocks that.
#
# What it asserts, in order:
#   1. sim/harness/klt_corner_bundle.py's corner->section table still agrees
#      with sim/lib/pvt_preflight.sh's own maps.
#   2. ngspice honours a `pre_osdi` card in a `.control` block reached through
#      `.include` -- the one deviation from `klt sim`'s netlist-body contract
#      that an OSDI PDK forces (see the body file's header).
#   3. A nested corner-bundle `.lib` resolves (the multi-file-corner
#      workaround).
#   4. `klt sim` reproduces sim/core-open-loop-bias's committed
#      typ/27C/3.30V point to within ANCHOR_TOL_V -- i.e. the harness change
#      moves no number.
#   5. klt_sim_evidence.py emits a record/CSV/log/snapshot quadruple that
#      .github/scripts/check_evidence_formats.py's own record checks accept,
#      and whose snapshot inlines the DUT's devices (the D2 rule needs them
#      present, not behind an `.include`).
set -euo pipefail

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
if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_probe.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see above." >&2
  exit 3
fi
for tool in ngspice klt; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "run_probe.sh: ${tool} not on PATH." >&2; exit 3; }
done
if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_probe.sh: OSDI device models missing -- run sim/tools/build-osdi.sh first." >&2
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"

WORK="${KLT_SIM_PROBE_WORK:-$(mktemp -d -t sg13g2-klt-sim-probe-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_probe.sh: work dir ${WORK}"

# --- 1. corner-section table has not drifted from the shell maps -------------
python3 "${HARNESS_DIR}/klt_corner_bundle.py" --check-preflight "${SIM_DIR}/lib/pvt_preflight.sh"
python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"

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

sed -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
    -e "s|@@TRIM_SUBCKT@@|${WORK}/bandgap_trim.inc|g" \
    "${SCRIPT_DIR}/core_open_loop_bias.body.spice" > "${WORK}/body.spice"

sed -e "s|@@BODY@@|${WORK}/body.spice|g" \
    -e "s|@@CORNER_BUNDLE@@|${WORK}/sg13g2_corners.lib|g" \
    "${SCRIPT_DIR}/request.json.tmpl" > "${WORK}/request.json"

# --- 2/3/4. one corner through klt sim --------------------------------------
# `--backend local` is explicit on purpose: the dispatch hosts export
# KLT_SIM_BACKEND=batch, and a one-corner debug probe is the case that is
# meant to stay local.
klt sim "${WORK}/request.json" --backend local --format json \
  -o "${WORK}/artifacts" > "${WORK}/report.json"

python3 - "${WORK}/report.json" "${ANCHOR_VREF_V}" "${ANCHOR_TOL_V}" \
           "${ANCHOR_R1_OHM}" "${ANCHOR_TOL_OHM}" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
anchor_v, tol_v, anchor_r, tol_r = (float(a) for a in sys.argv[2:6])
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
print("  nested corner-bundle .lib resolution: ok")
PY

# --- 5. the evidence adapter, into a scratch experiment tree -----------------
SCRATCH_EXP="${WORK}/scratch-experiment"
mkdir -p "${SCRATCH_EXP}/testbench"
cp "${SCRIPT_DIR}/core_open_loop_bias.body.spice" "${SCRATCH_EXP}/testbench/"
cp "${SCRIPT_DIR}/request.json.tmpl" "${SCRATCH_EXP}/testbench/"
: > "${SCRATCH_EXP}/run_probe_placeholder.sh"
cp "${SCRIPT_DIR}/record-spec.json" "${WORK}/record-spec.json"

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
