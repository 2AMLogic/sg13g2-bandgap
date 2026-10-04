#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-psrr-pex on the `klt sim` harness
# (issue #278, the remaining half of #275).
#
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --sanity   # one local corner, vs the committed typ/27/3.30 record
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --batch    # the 45-point PVT grid, on the fleet
#   sim/closed-loop-psrr-pex/run_klt_sim.sh --record   # mint evidence from the merged report
#
# WHY NODESET-SEEDED. This bench measures a frequency-domain quantity, and
# ngspice re-solves the DC operating point for an `ac` analysis from the
# sources' DC values -- a ramp-settled supply (the transient benches'
# convergence path) linearises around a collapsed point, verified on
# ngspice 46 with a nonlinear toy circuit. The bench body therefore keeps
# the hand-transcribed template's own mechanism: a plain DC rail carrying
# the 1 V AC stimulus, and .nodeset seeds from sim/closed-loop-startup's
# newest committed record (27 C row per process corner and supply -- the
# same provenance sim/lib/nodeset_seed.sh established). Seeds are
# convergence AIDS: the enrichment pass checks the landed op against them
# with the old bench's 50 mV tolerance.
#
# WHY PER-PROCESS x PER-SUPPLY. Same two axes as the vref bench: the batch
# runner image's klt 0.5.0 carries one model library and SG13G2's corner
# set spans three per-device-family files (klayout-tools#2668), and the
# seed set is per-supply, so the supply axis lives in per-supply body
# variants -- an `alter`-driven supply axis would clobber the AC stimulus
# (verified on ngspice 46). 15 requests of 3 temperatures each, merged
# deterministically, enriched (sim/harness/enrich_ac_report.py --kind
# psrr), one record via the adapter.
#
# SANITY GATE. No grid until one local corner (typ/27C/3.30V) lands within
# SANITY_TOL_DB of the committed pre-#272 record's psrr_dc (65.2635 dB)
# and SANITY_TOL_V of its vref_op (1.046287 V): the refreshed extraction
# is a real design change, so the gate is a band.
#
# Resumable: a per-variant report that already exists and passed is not
# re-submitted.
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
EXP="closed-loop-psrr-pex"
STEM="closed_loop_psrr_pex"
EXP_DIR="${SIM_DIR}/${EXP}"

KLT_BIN="${KLT_SIM_KLT:-klt}"
if ! command -v "${KLT_BIN}" >/dev/null 2>&1; then
  echo "run_klt_sim.sh: klt binary '${KLT_BIN}' not found (KLT_SIM_KLT)." >&2
  exit 3
fi

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

BATCH_PDK_ROOT="${KLT_SIM_BATCH_PDK_ROOT:-/opt/pdk}"
BATCH_PROVISION_SCRIPT="${KLT_BATCH_PROVISION_SCRIPT:-${HOME}/GitHub/2am/infra/aws/batch-fleet-provision.sh}"

# Sanity anchors: the committed pre-#272 record's typ/27C/3.30V row.
ANCHOR_PSRR_DC_DB="65.2635"
ANCHOR_PSRR_TOL_DB="2.0"
ANCHOR_VREF_OP_V="1.046287"
ANCHOR_VREF_TOL_V="0.005"

WORK="${KLT_SIM_WORK:-$(mktemp -d -t sg13g2-klt-${EXP}-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_klt_sim.sh: work dir ${WORK}"

CORNER_LABELS=(typ bcs wcs sf fs)
VDDS=(2.97 3.30 3.63)

# --- the DUT body (generated, top cell) -------------------------------------
python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc"

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

instantiate_body() {  # $1 OSDI dir, $2 PEX body ref, $3 vdd, $4-7 seeds
  sed -e "s|@@OSDI_DIR@@|${1}|g" -e "s|@@PEX_BODY@@|${2}|g" -e "s|@@VDD@@|${3}|g" \
      -e "s|@@FB_SEED@@|${4}|g" -e "s|@@SNS1_SEED@@|${5}|g" \
      -e "s|@@SNS2_SEED@@|${6}|g" -e "s|@@VREF_SEED@@|${7}|g" \
    "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"
}

check_anchors() {  # $1 = enriched report json
  python3 - "$1" "${ANCHOR_PSRR_DC_DB}" "${ANCHOR_PSRR_TOL_DB}" \
                 "${ANCHOR_VREF_OP_V}" "${ANCHOR_VREF_TOL_V}" <<'PY'
import json, pathlib, sys
r = json.loads(pathlib.Path(sys.argv[1]).read_text())
a_db, t_db, a_v, t_v = (float(x) for x in sys.argv[2:6])
if r["status"] != "pass":
    raise SystemExit(f"sanity gate: run graded {r['status']!r}")
(corner,) = r["corners"]
got = {m["name"]: m.get("value") for m in corner["measurements"]}
ok = True
for name, anchor, tol, unit in (("psrr_dc_db", a_db, t_db, "dB"),
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

enrich_local() {  # $1 = raw report -> enriched report (local run, artifacts resolvable)
  python3 "${HARNESS_DIR}/enrich_ac_report.py" "$1" --kind psrr -o "${1%.json}-enriched.json"
}

case "${MODE}" in
--sanity)
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
  read -r FB S1 S2 VR <<< "$(SEEDS_OF typ 3.30)"
  if [[ -z "${FB:-}" ]]; then
    echo "run_klt_sim.sh: no typ/27C/3.30 seed row in ${SEED_CSV}" >&2
    exit 3
  fi
  instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" 3.30 "${FB}" "${S1}" "${S2}" "${VR}" \
    > "${WORK}/body.spice"
  python3 - "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" "${WORK}/body.spice" \
    "${WORK}/sg13g2_corners.lib" "${WORK}/request.json" <<'PY'
import json, pathlib, sys
tmpl, body, bundle, out = sys.argv[1:5]
req = json.loads(pathlib.Path(tmpl).read_text().replace("@@BODY@@", body).replace("@@CORNER_BUNDLE@@", bundle))
req["corners"]["process"] = ["typ"]
req["corners"]["temperature_c"] = [27]
pathlib.Path(out).write_text(json.dumps(req, indent=2) + "\n")
PY
  ( cd "${WORK}" && "${KLT_BIN}" sim request.json --backend local --format json \
      -o artifacts > report.json )
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report.json \
      --kind psrr -o report-enriched.json )
  check_anchors "${WORK}/report-enriched.json"
  ;;

--batch)
  if [[ ! -x "${BATCH_PROVISION_SCRIPT}" ]]; then
    echo "run_klt_sim.sh: batch provision script not executable at ${BATCH_PROVISION_SCRIPT}" >&2
    exit 3
  fi
  echo "run_klt_sim.sh: sanity gate before dispatch"
  "${SCRIPT_DIR}/run_klt_sim.sh" --sanity

  python3 - "${HARNESS_DIR}/klt_corner_bundle.py" \
    "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" \
    "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" \
    "${BATCH_PDK_ROOT}" "${BATCH_PROVISION_SCRIPT}" "${PDK}" "${WORK}" \
    "${BATCH_PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi" "${SEED_CSV}" <<'PY'
import csv, importlib.util, json, pathlib, sys

(bundle_py, req_tmpl_path, body_tmpl_path, pdk_root, provision, pdk, work,
 osdi, seed_csv) = sys.argv[1:10]
spec = importlib.util.spec_from_file_location("klt_corner_bundle", bundle_py)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

seeds = {}
for row in csv.DictReader(open(seed_csv)):
    if row["status"] == "PASS":
        seeds[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row

req_tmpl = pathlib.Path(req_tmpl_path)
body_tmpl = pathlib.Path(body_tmpl_path)
base = json.loads(req_tmpl.read_text())
models_dir = f"{pdk_root}/{pdk}/libs.tech/ngspice/models"
out = pathlib.Path(work)

for label, (hbt, mos, res) in bundle.CORNER_SECTIONS.items():
    for vdd in (2.97, 3.30, 3.63):
        vid = f"{vdd:.2f}".replace(".", "p")
        # Bake the 125 C row: the seeds are one set per (corner, supply)
        # shared by the three temperatures a request sweeps, and the hot
        # corner is the stiff one -- the fs/125 point singular-matrixed
        # from the 27 C seed on the refreshed extraction while every other
        # point converged from either. A 27 C-vs-125 C seed difference is
        # ~30-60 mV of initial guess, immaterial to the points that
        # converge and decisive for the one that does not; the op-match
        # check itself uses the per-temperature reference via --seed-csv.
        for temp_row in ("125", "27"):
            row = seeds.get((label, temp_row, f"{vdd:g}")) or seeds.get((label, temp_row, f"{vdd:.2f}"))
            if row is not None:
                break
        if row is None:
            raise SystemExit(f"no 27C seed row for {label}/{vdd} in {seed_csv}")
        body_text = (
            body_tmpl.read_text()
            .replace("@@OSDI_DIR@@", osdi)
            .replace("@@PEX_BODY@@", "pex_body.inc")
            .replace("@@VDD@@", f"{vdd}")
            .replace("@@FB_SEED@@", row["fb_final_v"])
            .replace("@@SNS1_SEED@@", row["sns1_final_v"])
            .replace("@@SNS2_SEED@@", row["sns2_final_v"])
            .replace("@@VREF_SEED@@", row["vref_final_v"])
            + f"""
* Batch mode only (issue #278 per-process bridge): the two families the
* request's single models.lib (klt 0.5.0 on the runner) cannot reach, as
* selection-form `.lib` cards against the image's baked PDK root. Same
* CORNER_SECTIONS entry the request's models.lib selects the HBT family
* from. Corner: {label}; supply: {vdd} V.
.lib "{models_dir}/cornerMOShv.lib" {mos}
.lib "{models_dir}/cornerRES.lib" {res}
"""
        )
        (out / f"body-{label}-{vid}.spice").write_text(body_text)
        req = json.loads(
            json.dumps(base)
            .replace("@@BODY@@", str(out / f"body-{label}-{vid}.spice"))
            .replace("@@CORNER_BUNDLE@@", "UNUSED-BATCH")
        )
        req["backend"] = "batch"
        req["models"] = {"pdk": pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
        req["corners"]["process"] = [hbt]
        req["batch"] = {"provision_script_path": provision}
        (out / f"request-{label}-{vid}.json").write_text(json.dumps(req, indent=2) + "\n")
print("per-variant requests written")
PY

  for label in "${CORNER_LABELS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      vid="$(echo "${vdd}" | tr '.' 'p')"
      report="${WORK}/report-${label}-${vid}.json"
      if [[ -s "${report}" ]] && python3 -c "
import json,sys; r=json.load(open('${report}')); sys.exit(0 if r['status']=='pass' else 1)" 2>/dev/null; then
        echo "run_klt_sim.sh: ${label}/${vdd}V already complete, skipping"
        continue
      fi
      echo "run_klt_sim.sh: dispatching ${label}/${vdd}V (3 points, one fleet job)"
      ( cd "${WORK}" && "${KLT_BIN}" sim "request-${label}-${vid}.json" --backend batch \
          --format json -o "artifacts-${label}-${vid}" > "report-${label}-${vid}.json" ) || \
        echo "run_klt_sim.sh: ${label}/${vdd}V graded non-pass -- recorded, continuing"
    done
  done

  # Record-side fixup (same as the transient benches) before the merge.
  for label in "${CORNER_LABELS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      vid="$(echo "${vdd}" | tr '.' 'p')"
      sed "s|\"${BATCH_PDK_ROOT}/|\"${PDK_ROOT}/|g" "${WORK}/body-${label}-${vid}.spice" \
        > "${WORK}/body-fixed-${label}-${vid}.spice"
      python3 "${HARNESS_DIR}/fixup_batch_report.py" "${WORK}/report-${label}-${vid}.json" \
        --body "${WORK}/body-fixed-${label}-${vid}.spice" \
        --runner-pdk-root "${BATCH_PDK_ROOT}" --local-pdk-root "${PDK_ROOT}" \
        --decks-out "${WORK}/decks-fixed-${label}-${vid}" \
        -o "${WORK}/report-${label}-${vid}-fixed.json"
    done
  done

  python3 "${HARNESS_DIR}/merge_batch_shards.py" -o "${WORK}/report-merged.json" \
    $(for label in "${CORNER_LABELS[@]}"; do
        for vdd in "${VDDS[@]}"; do
          vid="$(echo "${vdd}" | tr '.' 'p')"
          echo "${label}=${WORK}/report-${label}-${vid}-fixed.json"
        done
      done)
  # From WORK: the merged reports' per-corner LOG paths are relative to it.
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/enrich_ac_report.py" report-merged.json \
      --kind psrr --seed-csv "${SEED_CSV}" -o report-enriched.json )
  ;;

--record)
  ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
      --report "${WORK}/report-enriched.json" \
      --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
      --experiment "${EXP_DIR}" )
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
  echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
  ;;
esac
