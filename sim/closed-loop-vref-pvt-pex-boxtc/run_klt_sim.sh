#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-pvt-pex-boxtc on the `klt sim` harness
# (issue #278, the remaining half of #275).
#
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --sanity  # one local corner, vs the schematic twin
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --batch  # the 120-point box-TC grid, on the fleet
#   sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --record  # mint evidence from the merged report
#
# WHY PER-PROCESS x PER-SUPPLY. Two axes cannot ride one request here: the
# process axis because the batch runner image's klt 0.5.0 carries one model
# library and SG13G2's corner set spans three per-device-family files
# (klayout-tools#2668; the per-process bridge sim/harness/probe/run_probe.sh
# --batch proved), and the supply axis because this bench's rail source is
# the PWL ramp that IS its convergence path -- `alter` would clobber it --
# so the ramp target is substituted into a per-supply body variant. The
# grid therefore runs as 15 requests (5 processes x 3 supplies) of 3
# temperatures each, merged deterministically
# (sim/harness/merge_batch_shards.py), enriched with the derived columns
# and the per-point closed-loop verdict
# (sim/harness/enrich_pvt_report.py), and the adapter mints one record.
#
# SANITY GATE. No grid is dispatched until one local corner (typ/27C/3.30V)
# lands within SANITY_TOL_V of the schematic twin's committed value at the
# same point (sim/closed-loop-vref-pvt's newest record): the refreshed
# extraction is a real design change (#272's trim-bearing ladder), so the
# gate is a band, not the core bench's exact anchor -- the old extraction's
# committed pex-vs-schematic deltas ran 1.0-3.5 mV and this gate allows
# +/-5 mV. "A first refreshed grid point far from the anchor means the
# template, not the extraction, is wrong" (#278's sanity-gate item).
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
EXP="closed-loop-vref-pvt-pex-boxtc"
STEM="closed_loop_vref_pvt_pex_boxtc"
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

# Sanity anchor: sim/closed-loop-vref-pvt's newest committed record,
# typ/27C/3.30V vref_3ms (the trim-bearing schematic twin, 20261001
# record), +/- the band below.
ANCHOR_VREF_V="1.04728"
ANCHOR_TOL_V="0.005"

WORK="${KLT_SIM_WORK:-$(mktemp -d -t sg13g2-klt-${EXP}-XXXXXX)}"
mkdir -p "${WORK}"
echo "run_klt_sim.sh: work dir ${WORK}"

CORNER_LABELS=(typ bcs wcs sf fs)
VDDS=(2.97 3.30 3.63)

# --- the DUT body (generated, top cell) -------------------------------------
python3 "${SIM_DIR}/tools/gen_pex_netlist_body.py" --cell top -o "${WORK}/pex_body.inc"

instantiate_body() {  # $1 = OSDI dir, $2 = PEX body include ref, $3 = vdd
  sed -e "s|@@OSDI_DIR@@|${1}|g" -e "s|@@PEX_BODY@@|${2}|g" -e "s|@@VDD@@|${3}|g" \
    "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"
}

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

case "${MODE}" in
--sanity)
  python3 "${HARNESS_DIR}/klt_corner_bundle.py" -o "${WORK}/sg13g2_corners.lib"
  instantiate_body "${OSDI_DIR}" "${WORK}/pex_body.inc" 3.30 > "${WORK}/body.spice"
  python3 - "${EXP_DIR}/testbench/${STEM}.request.json.tmpl" "${WORK}/body.spice" \
    "${WORK}/sg13g2_corners.lib" "${WORK}/request.json" <<'PY'
import json, pathlib, sys
tmpl, body, bundle, out = sys.argv[1:5]
req = json.loads(pathlib.Path(tmpl).read_text().replace("@@BODY@@", body).replace("@@CORNER_BUNDLE@@", bundle))
req["corners"]["process"] = ["typ"]
req["corners"]["temperature_c"] = [27]
pathlib.Path(out).write_text(json.dumps(req, indent=2) + "\n")
PY
  "${KLT_BIN}" sim "${WORK}/request.json" --backend local --format json \
    -o "${WORK}/artifacts" > "${WORK}/report.json"
  check_anchors "${WORK}/report.json"
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
    for vdd in (2.97, 3.30, 3.63):
        vid = f"{vdd:.2f}".replace(".", "p")
        body_text = (
            body_tmpl.read_text()
            .replace("@@OSDI_DIR@@", osdi)
            .replace("@@PEX_BODY@@", "pex_body.inc")
            .replace("@@VDD@@", f"{vdd}")
            + f"""
* Batch mode only (issue #278 per-process bridge): the two families the
* request's single models.lib (klt 0.5.0 on the runner) cannot reach, as
* selection-form `.lib` cards against the image's baked PDK root. Same
* CORNER_SECTIONS entry the request's models.lib selects the HBT family
* from. Corner: {label}; ramp target: {vdd} V.
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
      # A variant whose run grades error/fail still writes its report (the
      # merge + enrichment surface what failed); only a submission that
      # wrote NO report is fatal, checked after the loop.
      ( cd "${WORK}" && "${KLT_BIN}" sim "request-${label}-${vid}.json" --backend batch \
          --format json -o "artifacts-${label}-${vid}" > "report-${label}-${vid}.json" ) || \
        echo "run_klt_sim.sh: ${label}/${vdd}V graded non-pass -- recorded, continuing"
    done
  done

  # Record-side fixup: repoint each report's decks at locally resolvable
  # files (the runner's staged include and the image's baked PDK paths do
  # not exist here, and the adapter would ship device-less snapshots).
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
  python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
    -o "${WORK}/report-enriched.json"
  ;;

--record)
  python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
    --report "${WORK}/report-enriched.json" \
    --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
    --experiment "${EXP_DIR}"
  # Box-method TC companion per (corner, vdd) group -- same formula,
  # disclosure and justification policy as the committed records (box =
  # (vmax-vmin)/(span*v27), span = 165 C over the -40..125 grid).
  CSV="$(ls -t "${EXP_DIR}"/records/*.csv | grep -v -e '-boxtc.csv' -e '-tc.csv' | head -1)"
  python3 - "${CSV}" "${CSV%.csv}-boxtc.csv" <<'PY'
import csv, pathlib, sys
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
rows = list(csv.DictReader(src.open()))
groups: dict[tuple[str, str], list[dict]] = {}
for r in rows:
    groups.setdefault((r["corner_label"], r["vdd_v"]), []).append(r)
with dst.open("w", newline="") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["corner_label", "vdd_v", "n_pass", "n_grid", "vmin_v", "vmin_temp_c",
                "vmax_v", "vmax_temp_c", "vref_27c_v", "box_tc_ppm_per_c",
                "endpoint_tc_ppm_per_c"])
    for corner in ("typ", "bcs", "wcs", "sf", "fs"):
        for vdd in ("2.97", "3.30", "3.63"):
            grp = [r for r in groups.get((corner, vdd), [])
                   if r["status"] == "PASS"]
            n_grid = len(groups.get((corner, vdd), []))
            if not grp:
                continue
            pts = [(float(r["temp_c"]), float(r["vref_3ms_v"])) for r in grp]
            v27 = next((v for t, v in pts if t == 27), None)
            if v27 is None:
                continue
            (tmin, vmin), (tmax, vmax) = min(pts, key=lambda p: p[1]), max(pts, key=lambda p: p[1])
            box = 1e6 * (vmax - vmin) / (165 * v27)
            row = [corner, vdd, len(grp), n_grid, f"{vmin:.5g}", int(tmin),
                   f"{vmax:.5g}", int(tmax), f"{v27:.5g}", f"{box:.3f}"]
            vn40 = next((v for t, v in pts if t == -40), None)
            v125 = next((v for t, v in pts if t == 125), None)
            row.append(f"{1e6 * (v125 - vn40) / (165 * v27):.3f}"
                       if vn40 is not None and v125 is not None else "")
            w.writerow(row)
print(f"boxtc companion: {dst}")
PY
  echo "run_klt_sim.sh: record minted under ${EXP_DIR}/records/"
  echo "  next: delete this experiment's #275 waiver entry in sim/evidence-freshness-waivers.json"
  ;;
esac
