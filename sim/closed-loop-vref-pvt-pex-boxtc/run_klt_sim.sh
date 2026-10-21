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
# Resumable: a per-variant report that already exists, passed AND carries a
# matching submission identity (#332) is not re-submitted.
set -euo pipefail

EXP="closed-loop-vref-pvt-pex-boxtc"
STEM="closed_loop_vref_pvt_pex_boxtc"
VDDS=(2.97 3.30 3.63)
source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_runner.sh"
source "${HARNESS_DIR}/pex_vref_runner.sh"

# Sanity anchor: sim/closed-loop-vref-pvt's newest committed record,
# typ/27C/3.30V vref_3ms (the trim-bearing schematic twin, 20261001
# record), +/- the band below.
ANCHOR_VREF_V="1.04728"
ANCHOR_TOL_V="0.005"

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

pex_vref_main
