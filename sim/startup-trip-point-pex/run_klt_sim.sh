#!/usr/bin/env bash
# sg13g2-bandgap -- startup-trip-point-pex on the `klt sim` harness
# (issue #387). Converts the legacy run_pvt_sweep.sh loop, which hand-launches
# 45 ngspice runs and so cannot be run on a dispatch host; the loop and every
# committed record under records/ are untouched.
#
#   sim/startup-trip-point-pex/run_klt_sim.sh --sanity   # one local corner, vs the committed typ/27C/3.30V row
#   sim/startup-trip-point-pex/run_klt_sim.sh --batch    # the 45-point PVT grid, on the fleet
#   sim/startup-trip-point-pex/run_klt_sim.sh --record   # mint evidence (KLT_SIM_WORK = the --batch work dir)
#
# Built on sim/harness/pex_runner.sh like the other PEX runners. Differences:
#  - the DUT body is the legacy hybrid netlist (X-subckt re-encoding of the
#    extracted devices, see the body template), not gen_pex_netlist_body.py
#    output -- that generator has no standalone startup cell. check_wires
#    gates every mode on the body's wire R/C values still matching the
#    committed bandgap_startup.pex.spice, so a re-extraction cannot be
#    simulated stale silently.
#  - the dc sweep stop and two `.meas` levels scale with the supply, so the
#    grid is one request per (process x supply), supply pinned (#387).
#  - the six-criteria verdict is applied by `cmos5l_klt.py enrich --kind
#    trip-point` (kind-generic: sim/lib/pvt_verdict_common.sh's formula).
#
# SANITY GATE. No grid until one local corner (typ/27C/3.30V) lands within
# tolerance of the committed record's row: the refreshed extraction may move
# the figures a little, so the gate is a band, not an equality.
set -euo pipefail

EXP="startup-trip-point-pex"
STEM="startup_trip_point_pex"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"

# Sanity anchors: records/20260905-033740-fe97115.csv, typ/27C/3.30V.
ANCHORS=("det_on_v=3.299999:0.01" "fb_on_v=0.000267:0.01" "vtrip_v=0.562206:0.01"
         "det_off_v=0.000262:0.01" "fb_off_v=3.3:0.01")

PEX_SPICE="${REPO_ROOT}/layout/bandgap_startup/bandgap_startup.pex.spice"
PEX_REPORT="${REPO_ROOT}/layout/bandgap_startup/pex_extract_report.json"

check_wires() {
  python3 - "${PEX_SPICE}" "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" <<'PY'
import re, sys
pex, body = sys.argv[1:3]
def cards(path, upper):
    out = []
    for line in open(path):
        t = line.split()
        if len(t) == 4 and re.match(r"[RrCc](det|fb|vdd|vss)(_t[0-9]+)?$", t[0], re.I):
            out.append((t[0].upper() if upper else t[0].upper(), float(t[3])))
    return out
have = sorted(v for _, v in cards(pex, True))
want = sorted(v for _, v in cards(body, False))
pool = list(have)
missing = []
for v in want:
    for i, h in enumerate(pool):
        if abs(h - v) <= 1e-9 * max(abs(v), 1.0):
            del pool[i]
            break
    else:
        missing.append(v)
if missing:
    raise SystemExit(f"wire gate: body wire values not in {pex}: {missing} -- re-transcribe "
                     "with sim/tools/dump_pex_wire_parasitics.py --wires-only")
print(f"  wire gate: {len(want)} body wire cards all present in the committed extraction")
PY
}

capture_sources() {
  python3 - "${REPO_ROOT}" "${EXTRACTION_SOURCES}" "${PEX_SPICE}" "${PEX_REPORT}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "sim" / "harness"))
import extraction_binding as xb
root = Path(sys.argv[1])
entries, _ = xb.capture([Path(p) for p in sys.argv[3:]], root)
xb.assert_unchanged(entries, root)
xb.write_captured(entries, Path(sys.argv[2]))
PY
}

case "${MODE}" in
--sanity)
  check_wires
  capture_sources
  pex_instantiate_body "${OSDI_DIR}" "" VDD=3.30 > "${WORK}/body.spice"
  PEX_SANITY_VDD=3.3 pex_sanity_local '{"supply_v": {"Vvdd": [3.30]}}'
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/cmos5l_klt.py" enrich --kind trip-point \
      report.json -o report-enriched.json )
  anchor_args=(); for a in "${ANCHORS[@]}"; do anchor_args+=(--anchor "$a"); done
  python3 "${HARNESS_DIR}/cmos5l_klt.py" check-anchors "${WORK}/report-enriched.json" "${anchor_args[@]}"
  ;;

--batch)
  check_wires
  capture_sources
  pex_batch_dispatch --pin-supply-rail Vvdd
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/cmos5l_klt.py" enrich --kind trip-point \
      report-merged.json -o report-enriched.json )
  python3 - "${WORK}/report-enriched.json" <<'PY'
import json, pathlib, sys
r = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(f"merged grid: {r['status']}  passed={r['passed']} failed={r['failed']} errored={r['errored']}")
for c in r["corners"]:
    if c["status"] != "pass":
        print(f"  {c['corner_id']}: {c['status']} {str(c.get('diagnostics'))[:160]}")
PY
  echo "run_klt_sim.sh: enriched report at ${WORK}/report-enriched.json"
  echo "                 mint evidence with: KLT_SIM_WORK=${WORK} run_klt_sim.sh --record"
  ;;

--record)
  pex_record_mint "${WORK}/report-enriched.json"
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
  echo "  next: delete this experiment's #309 waiver entry in sim/evidence-freshness-waivers.json"
  ;;
esac
