#!/usr/bin/env python3
"""Reproduce the characterization figures from the committed CSVs and reports.

    python3 -I measurements/2026-11-23-characterization-report/spotcheck.py

Run from the repository root. Each output line names the quantity checked.
Nothing is simulated. The output at the audited commit is reproduced in the
report's "Spot-check output" section. The shared re-derivation bodies live in
measurements/lib/spotcheck_common.py; this file pins the record paths this
report quotes.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import spotcheck_common as sc

# --- Record paths quoted by this report (audited commit 275bdc18) ------------
VREF_PVT = "closed-loop-vref-pvt/records/20261122-181757-c5b84561"
PSRR_PEX = "closed-loop-psrr-pex/records/20261004-030337-5553d523"
PSRR_SCH = "closed-loop-psrr/records/20261122-182058-1d0308ad"
IQ = "closed-loop-iq/records/20261122-181711-c5b84561"
STARTUP = "closed-loop-startup/records/20261118-082945-3e600d97"
STARTUP_TTR = "startup-time-to-release/records/20261122-183926-90e8e4dd"
STARTUP_TRIP_PEX = "startup-trip-point-pex/records/20260905-033740-fe97115"
TRIM_COVERAGE = "trim-coverage/records/20261030-061206-03e62489"
TRIM_MC = "closed-loop-vref-trim-mc/records/20261030-070305-03e62489"
BOXTC_TRIM = "closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc"
UNTRIMMED_MC = "closed-loop-vref-mc/records/20261121-194338-b03b10b7"
VREF_PVT_PEX_PRETRIM = "closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa"
VREF_PVT_BOXTC = "closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c"
VREF_PVT_BOXTC_PRETRIM_SCH = "closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc-boxtc"
VREF_PVT_BOXTC_PRETRIM_PEX = "closed-loop-vref-pvt-pex-boxtc/records/20260921-195122-77820fc-boxtc"
BOXTC_PRETRIM_AIDSFREE = "closed-loop-vref-boxtc-pretrim-aidsfree/records/20261002-125922-d770c09-boxtc"
LOOP_GAIN = "loop-gain-phase-margin/records/20261003-180919-2addad0"

sc.vref_pvt(VREF_PVT)
sc.psrr_pex(PSRR_PEX)
# A corner that fails the limit still has a measured PSRR.
psrr = sc.rows(PSRR_SCH + ".csv")
worst = min(psrr, key=lambda row: float(row["psrr_dc_db"]))
db = [float(row["psrr_dc_db"]) for row in psrr]
sc.say("PSRR@DC sch trim-bearing",
       f"{min(db):.3f}..{max(db):.3f} dB; >60 dB: {sum(x > 60 for x in db)}/{len(db)}; "
       f">70 dB: {sum(x > 70 for x in db)}/{len(db)}; worst at "
       f"{worst['corner_label']}/{worst['temp_c']}C/{worst['vdd_v']}V")
sc.supply_grid([VREF_PVT, IQ, PSRR_SCH, STARTUP, PSRR_PEX])
sc.iq(IQ)
sc.startup(STARTUP, STARTUP_TTR, STARTUP_TRIP_PEX)
sc.trim_coverage(TRIM_COVERAGE + "-analysis", TRIM_COVERAGE)
sc.trim_mc(TRIM_MC + "-draws", TRIM_MC)
sc.boxtc_trim(BOXTC_TRIM)
sc.vref_pvt_boxtc(VREF_PVT_BOXTC)
sc.pretrim_history(VREF_PVT_PEX_PRETRIM + "-tc",
                   VREF_PVT_BOXTC_PRETRIM_SCH,
                   VREF_PVT_BOXTC_PRETRIM_PEX,
                   BOXTC_PRETRIM_AIDSFREE)
sc.untrimmed_mc(UNTRIMMED_MC + "-draws", UNTRIMMED_MC, VREF_PVT_PEX_PRETRIM)
sc.loop_gain(LOOP_GAIN)

# Read the same five yield measurements cited for item 6.
yield_report = sc.SIM / "closed-loop-vref-mc/records/20261121-195500-b03b10b7-yield-report.json"
for measurement in json.loads(yield_report.read_text())["measurements"]:
    gate = measurement["sigma_target"]
    counts = measurement["converged_n"]
    sc.say(f"item-6 {measurement['name']}",
           f"{counts['n_converged']}/{counts['n_requested']} converged; "
           f"95% lower bound {gate['lower_bound']:.4f}; target {gate['k']:g} met={gate['met']}")

# Join by point and draw index so CSV row order has no bearing on the comparison.
draws = sc.rows(UNTRIMMED_MC + "-draws.csv")
old_draws = sc.rows("closed-loop-vref-mc/records/20261104-201955-2a0f04d7-draws.csv")
by_key = {(row["point"], row["draw_index"]): row for row in draws}
pairs = [(row, by_key[row["point"], row["draw_index"]]) for row in old_draws]
sc.say("first 300 draws per point",
       f"{sum(a['status'] == b['status'] for a, b in pairs)}/{len(pairs)} matching statuses; "
       f"{sum(a['vref_v'] == b['vref_v'] for a, b in pairs)}/{len(pairs)} identical Vref strings")
control = [row["vref_v"] for row in draws if row["point"] == "negctrl" and row["status"] == "PASS"]
sc.say("deterministic control", f"{len(control)} converged; distinct Vref (V) {sorted(set(control))}")

# Read the four spec-bound corner envelopes cited for item 5.
reports = {
    "output-reference-nominal": VREF_PVT,
    "psrr-dc": PSRR_SCH,
    "iq": IQ,
    "startup": STARTUP_TTR,
}
for row_name, record in reports.items():
    report = json.loads((sc.SIM / (record + "-report.json")).read_text())
    measurement = next(m for m in report["measurements"] if m.get("spec_row") == row_name)
    worst_case = measurement["worst_case"]
    sc.say(f"item-5 envelope {row_name}",
           f"{measurement['status']}; limits {measurement['limits']}; worst {worst_case['value']:.6g} "
           f"at {worst_case['corner_id']} (margin {worst_case['margin']:.6g}); "
           f"corners {report['passed']}/{report['corner_count']} pass")
