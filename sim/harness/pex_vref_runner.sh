# shellcheck shell=bash
# The vref-transient half of the PEX runners (issue #366): closed-loop-vref-
# pvt-pex and closed-loop-vref-pvt-pex-boxtc, PWL-ramp benches whose reports
# are enriched by sim/harness/enrich_pvt_report.py. Source it AFTER
# pex_runner.sh, with
#   ANCHOR_VREF_V / ANCHOR_TOL_V   the sanity band on typ/27C/3.30V vref_3ms
# set, define `pex_record_companion` (run after the record is minted, to write
# the experiment's TC companion CSV), then call `pex_vref_main`.

check_anchors() {  # $1 = report json
  python3 - "$1" "${ANCHOR_VREF_V}" "${ANCHOR_TOL_V}" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
anchor_v, tol_v = float(sys.argv[2]), float(sys.argv[3])
if report["status"] != "pass":
    raise SystemExit(f"sanity gate: klt sim graded the run {report['status']!r}")
(corner,) = report["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
value = got.get("vref_3ms_v")
if value is None:
    raise SystemExit("sanity gate: vref_3ms_v did not come back")
delta = abs(value - anchor_v)
print(f"  sanity vref_3ms = {value!r} (anchor {anchor_v}, delta {delta:.3g}) "
      f"{'ok' if delta <= tol_v else 'FAIL'}")
if delta > tol_v:
    raise SystemExit(
        "sanity gate: off the schematic twin's committed typ/27C/3.30V band -- "
        "the bench, not the extraction, is wrong (issue #278's sanity-gate item)"
    )
print("  sanity gate: PASS")
PY
}

pex_vref_main() {
  # --- the DUT body (generated, top cell) -----------------------------------
  python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc"
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" VDD=3.30 > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json"
    ;;
  --record)
    pex_record_mint "${WORK}/report-enriched.json"
    pex_record_companion
    ;;
  esac
}
