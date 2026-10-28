# shellcheck shell=bash
# Shared `--sanity | --batch | --record` flow for the closed-loop Iq and Startup
# `klt sim` runners (issue #414): schematic-DUT PWL-ramp benches whose reports are
# enriched by sim/harness/enrich_supply_bench_report.py. Source it AFTER
# pex_runner.sh, with
#   ENRICH_BENCH   iq | startup (enrich_supply_bench_report.py --bench)
#   BODY_TEMPLATE  the body template with @@MSENSE_W@@ pre-filled
#   MSENSE_W       the live startup netlist's XMSENSE width
#   ANCHORS        array of "measurement=value:tolerance" sanity anchors, read
#                  on the single local typ/27C/3.30V corner (compared as
#                  magnitudes: ngspice reports i(Vvdd) negative)
# then call `supply_bench_main`.

check_anchors() {  # $1 = report json
  python3 - "$1" "${ANCHORS[@]}" <<'PY'
import json, pathlib, sys
report = json.loads(pathlib.Path(sys.argv[1]).read_text())
if report["status"] != "pass":
    raise SystemExit(f"sanity gate: klt sim graded the run {report['status']!r}")
(corner,) = report["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
bad = False
for spec in sys.argv[2:]:
    name, rest = spec.split("=")
    anchor, tol = (float(x) for x in rest.split(":"))
    value = got.get(name)
    if value is None:
        raise SystemExit(f"sanity gate: {name} did not come back")
    delta = abs(abs(value) - anchor)
    ok = delta <= tol
    bad |= not ok
    print(f"  sanity {name} = {value!r} (anchor {anchor}, delta {delta:.3g}) {'ok' if ok else 'FAIL'}")
if bad:
    raise SystemExit("sanity gate: off the committed typ/27C/3.30V record's band -- the bench is wrong")
print("  sanity gate: PASS")
PY
}

supply_bench_main() {
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "unused" VDD=3.30 MSENSE_W="${MSENSE_W}" > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_supply_bench_report.py" --bench "${ENRICH_BENCH}" \
      "${WORK}/report-merged.json" -o "${WORK}/report-enriched.json"
    ;;
  --record)
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
        --report "${WORK}/report-enriched.json" \
        --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
        --experiment "${EXP_DIR}" )
    ;;
  esac
}
