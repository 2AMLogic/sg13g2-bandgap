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

EXP="core-open-loop-bias-pex"
STEM="core_open_loop_bias_pex"
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"

# #272's one-point probe on this same extraction: the sanity anchor.
ANCHOR_VREF_V="1.052999"
ANCHOR_R1_OHM="66123"
ANCHOR_TOL_V="0.0002"
ANCHOR_TOL_OHM="10"

# --- the DUT body (generated, with this bench's per-leg ammeters cut in) ---
python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" \
  --ammeter XM1:3:Vm1 --ammeter XM2A:3:Vm2a --ammeter XM2B:3:Vm2b \
  --ammeter XM3A:3:Vm3a --ammeter XM3B:3:Vm3b --ammeter XM3C:3:Vm3c \
  --sources-out "${WORK}/extraction-sources.json" -o "${WORK}/pex_body.inc"

check_anchors() {  # $1 = report json, $2 = mode label
  python3 "${HARNESS_DIR}/sanity_anchors.py" "$1" --mode "$2" \
    --anchor "vref_v=${ANCHOR_VREF_V}:${ANCHOR_TOL_V}" \
    --anchor "r1_ohm=${ANCHOR_R1_OHM}:${ANCHOR_TOL_OHM}" \
    --hint "off #272's one-point anchor -- the bench, not the extraction, is wrong (issue #278's sanity-gate item)"
}

case "${MODE}" in
--sanity)
  pex_instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" > "${WORK}/body.spice"
  pex_sanity_local '{"supply_v": {"Vvdd": [3.30]}}'
  check_anchors "${WORK}/report.json" "local"
  ;;

--batch)
  pex_batch_dispatch
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
  pex_record_mint "${WORK}/report-merged.json"
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
  echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
  ;;
esac
