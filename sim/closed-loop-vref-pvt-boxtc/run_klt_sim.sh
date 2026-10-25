#!/usr/bin/env bash
# sg13g2-bandgap -- closed-loop-vref-pvt-boxtc (schematic DUT) on the `klt sim`
# harness (issue #273, completing #264's trim-bearing refresh).
#
#   sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --sanity  # one local corner, vs the vref-pvt twin
#   sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --batch   # the 120-point box-TC grid, on the fleet
#   sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --record  # mint evidence from the enriched report
#
# This is the schematic twin of sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh
# and shares its driver (sim/harness/pex_runner.sh + pex_vref_runner.sh's
# anchor check): the grid runs as 15 requests (5 processes x 3 supplies) of 8
# temperatures each, sharded over the fleet, for the reasons stated there
# (klayout-tools#2668 single-models.lib; the PWL ramp is the convergence path
# so the supply cannot ride `alter`). The DUT is the schematic, carried
# verbatim in the body template, so there is no extraction and no generated
# body. The old run_pvt_sweep.sh is kept as the point-definition reference
# only: it must not be run as a grid on a dispatch host.
#
# SANITY GATE. One local typ/27C/3.30V corner must land on the committed
# sim/closed-loop-vref-pvt record's vref_3ms (1.04728 V): the two benches share
# the DUT, fixture, solver options and measurement, so the band is tight.
#
# HOST SETUP seen on 2026-10-25 (issue #273), needed until the runner image and
# the dispatch hosts' klt agree:
#   * the fleet runner ran klt 0.7.0 and refuses a client of another version
#     (host klt was 0.8.1.dev): KLT_SIM_SUBMIT_KLT=<wrapper running
#     `uvx --from klayout-tools==0.7.0 klt "$@"`>. The sanity gate keeps the host klt.
#   * klt >= 0.8 rejects a body `.lib`/OSDI path under an absolute runner root
#     (/opt/pdk) as "not under $PDK_ROOT": KLT_SIM_BATCH_PDK_ROOT='$PDK_ROOT' (literal).
#
# Resumable: a per-variant report that passed AND carries a matching
# submission identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-vref-pvt-boxtc"
STEM="closed_loop_vref_pvt_boxtc"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_vref_runner.sh"

# XMSENSE's width from the live startup netlist, as every closed-loop bench does.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
( cd "${REPO_ROOT}" && read_msense_width "design/netlist/bandgap_startup.spice" \
    && printf '%s' "${MSENSE_W}" > "${WORK}/msense_w.txt" )
MSENSE_W="$(<"${WORK}/msense_w.txt")"
BODY_TEMPLATE="${WORK}/body.spice.tmpl"
sed "s|@@MSENSE_W@@|${MSENSE_W}|g" "${EXP_DIR}/testbench/${STEM}.body.spice.tmpl" > "${BODY_TEMPLATE}"
IDENT_ARGS+=(--extra "${REPO_ROOT}/design/netlist/bandgap_startup.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_core.spice"
  --extra "${REPO_ROOT}/design/netlist/bandgap_amp.spice")

# Sanity anchor: sim/closed-loop-vref-pvt's newest committed record,
# typ/27C/3.30V vref_3ms (trim-bearing, 20261001 refresh), same bench.
ANCHOR_VREF_V="1.04728"
ANCHOR_TOL_V="0.0005"

pex_record_companion() {
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
}

# pex_vref_main generates the PEX body and states the extraction; the
# schematic has neither, so this is its body-less twin.
schematic_vref_main() {
  case "${MODE}" in
  --sanity)
    pex_instantiate_body "${OSDI_DIR}" "unused" VDD=3.30 MSENSE_W="${MSENSE_W}" > "${WORK}/body.spice"
    pex_sanity_local
    check_anchors "${WORK}/report.json"
    ;;
  --batch)
    pex_batch_dispatch --supply-word "ramp target"
    python3 "${HARNESS_DIR}/enrich_pvt_report.py" "${WORK}/report-merged.json" \
      -o "${WORK}/report-enriched.json"
    ;;
  --record)
    ( cd "${WORK}" && python3 "${HARNESS_DIR}/klt_sim_evidence.py" \
        --report "${WORK}/report-enriched.json" \
        --spec "${EXP_DIR}/testbench/${STEM}.record-spec.json" \
        --experiment "${EXP_DIR}" )
    pex_record_companion
    ;;
  esac
}

schematic_vref_main
