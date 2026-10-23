# shellcheck shell=bash
# The AC-bench half of the PEX runners (issue #366): closed-loop-zout-pex and
# closed-loop-psrr-pex, nodeset-seeded per-process x per-supply benches whose
# reports are enriched by sim/harness/enrich_ac_report.py. Source it AFTER
# pex_runner.sh, with
#   KIND            enrich_ac_report.py --kind (zout|psrr)
#   ANCHOR_NAME     the measurement name gated on (e.g. zout_dc_db)
#   ANCHOR_DB / ANCHOR_DB_TOL   its sanity band (dB)
#   ANCHOR_VREF_OP_V / ANCHOR_VREF_TOL_V   the vref_op band (V)
# set, then call `pex_ac_main`.

# --- node seeds: sim/closed-loop-startup's newest committed record ----------
SEED_CSV="$(ls -t "${SIM_DIR}"/closed-loop-startup/records/*.csv \
  | grep -v -e '-tc.csv' -e '-vs-schematic' | head -1)"
if [[ -z "${SEED_CSV}" ]]; then
  echo "run_klt_sim.sh: no seed record in ${SIM_DIR}/closed-loop-startup/records/" >&2
  exit 3
fi
SEEDS_OF() {  # $1 corner label, $2 vdd -> prints fb sns1 sns2 vref seeds (27C row)
  awk -F, -v c="$1" -v v="$2" '$1==c && $6==v && $5=="27" && $8=="PASS" {print $11, $12, $13, $14; exit}' "${SEED_CSV}"
}

check_anchors() {  # $1 = enriched report json
  python3 - "$1" "${ANCHOR_NAME}" "${ANCHOR_DB}" "${ANCHOR_DB_TOL}" \
                 "${ANCHOR_VREF_OP_V}" "${ANCHOR_VREF_TOL_V}" <<'PY'
import json, pathlib, sys
r = json.loads(pathlib.Path(sys.argv[1]).read_text())
name_db = sys.argv[2]
a_db, t_db, a_v, t_v = (float(x) for x in sys.argv[3:7])
if r["status"] != "pass":
    raise SystemExit(f"sanity gate: run graded {r['status']!r}")
(corner,) = r["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
ok = True
for name, anchor, tol, unit in ((name_db, a_db, t_db, "dB"),
                                ("vref_op_v", a_v, t_v, "V")):
    value = got.get(name)
    if value is None:
        raise SystemExit(f"sanity gate: {name} did not come back")
    delta = abs(value - anchor)
    print(f"  sanity {name:11s} = {value:.4f} (anchor {anchor}, delta {delta:.3g} {unit}) "
          f"{'ok' if delta <= tol else 'FAIL'}")
    if delta > tol:
        ok = False
if not ok:
    raise SystemExit("sanity gate: off the committed record's band (issue #278's sanity-gate item)")
print("  sanity gate: PASS")
PY
}

pex_ac_main() {
  # --- the DUT body (generated, top cell) -----------------------------------
  python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc" \
    --sources-out "${WORK}/extraction-sources.json"
  case "${MODE}" in
  --sanity)
    local FB S1 S2 VR
    read -r FB S1 S2 VR <<< "$(SEEDS_OF typ 3.30)"
    if [[ -z "${FB:-}" ]]; then
      echo "run_klt_sim.sh: no typ/27C/3.30 seed row in ${SEED_CSV}" >&2
      exit 3
    fi
    pex_instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" VDD=3.30 \
      FB_SEED="${FB}" SNS1_SEED="${S1}" SNS2_SEED="${S2}" VREF_SEED="${VR}" \
      > "${WORK}/body.spice"
    pex_sanity_local
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report.json \
        --kind "${KIND}" -o report-enriched.json )
    check_anchors "${WORK}/report-enriched.json"
    ;;
  --batch)
    pex_batch_dispatch --seed-csv "${SEED_CSV}" --supply-word supply
    # From WORK: the merged reports' per-corner LOG paths are relative to it.
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report-merged.json \
        --kind "${KIND}" --seed-csv "${SEED_CSV}" -o report-enriched.json )
    ;;
  --record)
    pex_record_mint "${WORK}/report-enriched.json"
    echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
    echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
    ;;
  esac
}
