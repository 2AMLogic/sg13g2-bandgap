#!/usr/bin/env python3
"""Re-derive every number quoted in README.md from the committed sim/ CSVs.

    python3 -I measurements/2026-11-21-recognition-rebase-characterization-report/spotcheck.py

Read-only: opens committed CSVs, prints one labelled line per quoted figure.
Nothing is simulated. The output at the audited commit is reproduced in the
report's "Spot-check output" section. The shared re-derivation bodies live in
measurements/lib/spotcheck_common.py; this file pins the record paths this
report quotes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import spotcheck_common as sc

# --- Record paths quoted by this report (audited commit f5f3e950) ------------
VREF_PVT = "closed-loop-vref-pvt/records/20261001-085908-e5507b2"
PSRR_PEX = "closed-loop-psrr-pex/records/20261121-104700-f5f3e950"
PSRR_SCH = "closed-loop-psrr/records/20261113-085406-9d568b91"
IQ = "closed-loop-iq/records/20261118-072122-3e600d97"
STARTUP = "closed-loop-startup/records/20261118-082945-3e600d97"
STARTUP_TTR = "startup-time-to-release/records/20261001-085905-e5507b2"
STARTUP_TRIP_PEX = "startup-trip-point-pex/records/20261121-104844-f5f3e950"
TRIM_COVERAGE = "trim-coverage/records/20261030-061206-03e62489"
TRIM_MC = "closed-loop-vref-trim-mc/records/20261030-070305-03e62489"
BOXTC_TRIM = "closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc"
UNTRIMMED_MC = "closed-loop-vref-mc/records/20261104-201955-2a0f04d7"
VREF_PVT_PEX_PRETRIM = "closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa"
VREF_PVT_BOXTC = "closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c"
VREF_PVT_BOXTC_PRETRIM_SCH = "closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc-boxtc"
VREF_PVT_BOXTC_PRETRIM_PEX = "closed-loop-vref-pvt-pex-boxtc/records/20260921-195122-77820fc-boxtc"
BOXTC_PRETRIM_AIDSFREE = "closed-loop-vref-boxtc-pretrim-aidsfree/records/20261002-125922-d770c09-boxtc"
LOOP_GAIN = "loop-gain-phase-margin/records/20261003-180919-2addad0"

ZOUT_PEX = "closed-loop-zout-pex/records/20261121-104753-f5f3e950"


def zout_pex(rec):
    ok = [x for x in sc.rows(rec + ".csv") if x["status"] == "PASS"]
    d = [sc.f(x, "zout_dc_db") for x in ok]
    w = min(ok, key=lambda x: sc.f(x, "zout_dc_db"))
    sc.say("Zout@DC PEX trim-bearing (rebased extraction)",
           f"{len(ok)}/{len(sc.rows(rec + '.csv'))} PASS; {min(d):.4f}..{max(d):.4f} dB; "
           f"worst {sc.f(w, 'zout_dc_db'):.4f} dB at {w['corner_label']}/{w['temp_c']}C/{w['vdd_v']}V")


sc.vref_pvt(VREF_PVT)
sc.psrr_pex(PSRR_PEX)
zout_pex(ZOUT_PEX)
sc.psrr_sch(PSRR_SCH)
sc.supply_grid([VREF_PVT, IQ, PSRR_SCH, STARTUP, PSRR_PEX, ZOUT_PEX])
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
