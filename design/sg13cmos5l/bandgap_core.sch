v {xschem version=3.4.8RC file_version=1.3
* bandgap_core (SG13CMOS5L) -- grounded-collector pnpMPA diode-referenced
* core, phase 1/4 of the SG13CMOS5L port (issue #64).
*
* Per spec/decision-records/0004-cmos5l-bipolar-device-selection.md
* (DR-0004): SG13CMOS5L has no npn13G2-equivalent HBT, only the same
* low-gain pnpMPA (bf ~= 1.10) device DR-0001 read in SG13G2's own model
* deck and rejected as primary there. With no HBT available, this core
* follows gf180-bandgap's and sky130-bandgap's grounded-collector
* parasitic-PNP-pair Brokaw shape instead of re-parameterizing this repo's
* own ../bandgap_core.sch (SG13G2's grounded-EMITTER NPN core) --
* THIS IS NOT A COPY OF EITHER. Supply flavor (3.3V HV) is inherited
* unchanged from DR-0002.
*
* Q2's 8x device is built as 8 parallel UNIT (w=1u l=2u) instances via the
* SPICE `m=8` multiplier, not a single w=8u wide emitter -- see
* spec/decision-records/0005-cmos5l-q2-matched-array-construction.md
* (DR-0005, amends DR-0004): a single w=8u pnpMPA exceeds this PCell's own
* maxW (2.0u, sg13cmos5l_tech.json), so it cannot be PCell-generated at all,
* and 8 parallel unit devices is the standard way to build a matched array
* regardless. DR-0005 also shows (direct model-card read + an ngspice
* cross-check) that sg13cmos5l_pnpMPA_mod.lib's `p` (perimeter) parameter is
* computed but never referenced by any `.model` equation -- only `a` (area)
* matters -- so `m=8` unit devices and the old single w=8u*l=2u device are
* electrically IDENTICAL (both give the model's `area`-scaled is/ikf/isc/rb/
* rc/re the same total 16 um^2 effective area); this schematic's sizing
* below (derived against the old single-device construction) is therefore
* unchanged by this switch, re-confirmed by the PVT re-run DR-0005 records.
*
* Three matched sg13_hv_pmos mirror legs (M1, M2, M3), gate-driven by an
* external error amplifier via "fb" (out of this phase's scope -- see
* design/sg13cmos5l/README.md; #65/#66 are the sim/layout follow-on
* phases, an amp/startup/top follow-up is filed separately):
*
*   Q1 (pnpMPA, w=1u l=2u, unit)   -- branch 1, sensed directly at sns1
*                                     (M1 drain == Q1 emitter, no series R).
*   Q2 (pnpMPA, w=1u l=2u, m=8)    -- branch 2, 8 parallel unit devices
*                                     (area = w*l per device, SPICE `m=8`
*                                     multiplier -- DR-0005), fed through
*                                     PTAT resistor R2 from the M2 mirror
*                                     node "sns2" down to Q2's emitter "e2".
*   Q3 (pnpMPA, w=1u l=2u, unit)   -- output branch, fed through summing
*                                     resistor R1 from the M3 mirror node
*                                     ("vref" directly, no cascode in this
*                                     first pass) down to Q3's emitter "e3".
*
* Each pnpMPA is wired grounded-collector: base tied to collector, that
* shared node tied to vss (the model card's own header, "DUT:
* diode_pp=pnpMPA", suggests this device is characterized exactly this
* way). Current flows from the mirror, into each device's EMITTER
* (forward-active for a PNP), out through base+collector to vss -- the
* mirror image of ../bandgap_core.sch's npn13G2 wiring (base+collector
* tied to the driven node, emitter grounded).
*
* With a future external amplifier forcing sns1 = sns2 (both exposed as
* ports here, same as ../bandgap_core.sch), the servo action drops the
* PTAT delta-VEB(Q1,Q2) entirely across R2 (Q1 has no series resistor),
* giving a PTAT branch current
*   I = dVEB(Q1,Q2) / R2 = VT*ln(8)/R2   (nf=1.015 non-ideality per the
*                                          model card, so slightly above
*                                          the ideal VT*ln(8) -- see sizing)
* mirrored (M1=M2=M3, same W/L) into the output branch, where
*   vref = VEB(Q3) + I*R1
* is the classic Brokaw CTAT+PTAT sum -- VEB(Q3) is pnpMPA's CTAT term
* (diode-connected, ~0.78V at the design current, falling with
* temperature), I*R1 is the PTAT term.
*
* SIZING (INFORMAL, single-nominal-point-derived -- see
* design/sg13cmos5l/README.md "What has and has not been verified" for
* the standalone pnpMPA op-point check this was derived from; #65 owns
* the real PVT-swept sizing pass, matching how #10 later redid
* ../bandgap_core.sch's own first-pass numbers for SG13G2):
*   Design current I ~= 5uA/branch (same nominal current
*   ../bandgap_core.sch's own first pass used, kept for continuity, not
*   independently re-derived for pnpMPA's own error budget).
*   Standalone pnpMPA op-point at 5uA (typ corner, 27C):
*     VEB(w=1u,l=2u)        = 0.780540 V   (Q1, Q3 CTAT term)
*     VEB(w=8u,l=2u m=1)    = 0.725188 V   (Q2, pre-DR-0005 construction)
*     VEB(w=1u,l=2u m=8)    = 0.725188 V   (Q2, DR-0005 construction --
*                                            bit-for-bit identical, direct
*                                            ngspice cross-check in DR-0005)
*     dVEB(Q1,Q2)    = 0.055352 V  (vs. VT*ln(8) ~= 0.053746V ideal --
*                                    the ~3% excess matches the model's
*                                    own nf=1.015 non-ideality factor)
*   R2 = dVEB/I = 0.055352V/5uA ~= 11.07 kOhm
*       -> rppd, w=2u (>=2um precision-resistor recommendation, same as
*          ../bandgap_core.sch), l ~= 85.1um (solved from rppd.sym's own
*          R(w,l) formula, b=0 bends)
*   R1 sized for a provisional vref ~= 1.2V target using the same-size
*   Q3's VEB(1u,2u) = 0.780540V measured above (not yet re-measured with
*   R1/R2 loading -- see caveats below):
*       R1 = (1.2V - 0.780540V)/5uA ~= 83.89 kOhm
*       -> rppd, w=2u, l ~= 647.0um (same formula)
*   Mirror M1=M2=M3: sg13_hv_pmos, W=10u/L=1u (matched across all three
*   legs by construction, same geometry ../bandgap_core.sch uses -- not
*   independently re-sized for pnpMPA's own gain here).
* None of these values are PVT-swept or closed-loop-verified yet -- #65
* is the phase that grounds them in real sim/ evidence the way #10 did
* for ../bandgap_core.sch.
*
* PNPMPA GAIN CAVEAT (DR-0004 Consequences): bf ~= 1.10 means each
* device's base current is a first-order fraction of its emitter
* current, not a second-order correction the way npn13G2's BF ~= 650
* was for the SG13G2 core -- an untrimmed-accuracy budget for this core
* (not attempted this phase) would need to treat base-current error as
* load-bearing, unlike ../bandgap_core.sch.
*
* Pins: vdd, vss, fb, sns1, sns2, vref
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 0 200 0 0 {name=M1 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 20 170 40 150 {}
C {lab_pin.sym} 40 150 0 0 {name=l1 lab=vdd}
N 20 200 40 200 {}
C {lab_pin.sym} 40 200 0 0 {name=l2 lab=vdd}
N -20 200 -40 200 {}
C {lab_pin.sym} -40 200 0 0 {name=l3 lab=fb}
N 20 230 40 250 {}
C {lab_pin.sym} 40 250 0 0 {name=l4 lab=sns1}
C {sg13cmos5l_pr/pnpMPA.sym} 0 600 0 0 {name=Q1 model=pnpMPA spiceprefix=X w=1u l=2u m=1}
N 20 630 40 650 {}
C {lab_pin.sym} 40 650 0 0 {name=l5 lab=vss}
N -20 600 -40 600 {}
C {lab_pin.sym} -40 600 0 0 {name=l6 lab=vss}
N 20 570 40 550 {}
C {lab_pin.sym} 40 550 0 0 {name=l7 lab=sns1}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 400 200 0 0 {name=M2 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 420 170 440 150 {}
C {lab_pin.sym} 440 150 0 0 {name=l9 lab=vdd}
N 420 200 440 200 {}
C {lab_pin.sym} 440 200 0 0 {name=l10 lab=vdd}
N 380 200 360 200 {}
C {lab_pin.sym} 360 200 0 0 {name=l11 lab=fb}
N 420 230 440 250 {}
C {lab_pin.sym} 440 250 0 0 {name=l12 lab=sns2}
C {sg13cmos5l_pr/rppd.sym} 400 400 0 0 {name=R2 model=rppd body=sub! spiceprefix=X w=2u l=85.1u b=0 m=1}
N 400 370 400 350 {}
C {lab_pin.sym} 400 350 0 0 {name=l13 lab=sns2}
N 400 430 400 450 {}
C {lab_pin.sym} 400 450 0 0 {name=l14 lab=e2}
C {sg13cmos5l_pr/pnpMPA.sym} 400 600 0 0 {name=Q2 model=pnpMPA spiceprefix=X w=1u l=2u m=8}
N 420 630 440 650 {}
C {lab_pin.sym} 440 650 0 0 {name=l15 lab=vss}
N 380 600 360 600 {}
C {lab_pin.sym} 360 600 0 0 {name=l16 lab=vss}
N 420 570 440 550 {}
C {lab_pin.sym} 440 550 0 0 {name=l17 lab=e2}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 800 200 0 0 {name=M3 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 820 170 840 150 {}
C {lab_pin.sym} 840 150 0 0 {name=l19 lab=vdd}
N 820 200 840 200 {}
C {lab_pin.sym} 840 200 0 0 {name=l20 lab=vdd}
N 780 200 760 200 {}
C {lab_pin.sym} 760 200 0 0 {name=l21 lab=fb}
N 820 230 840 250 {}
C {lab_pin.sym} 840 250 0 0 {name=l22 lab=vref}
C {sg13cmos5l_pr/rppd.sym} 800 400 0 0 {name=R1 model=rppd body=sub! spiceprefix=X w=2u l=647.0u b=0 m=1}
N 800 370 800 350 {}
C {lab_pin.sym} 800 350 0 0 {name=l23 lab=vref}
N 800 430 800 450 {}
C {lab_pin.sym} 800 450 0 0 {name=l24 lab=e3}
C {sg13cmos5l_pr/pnpMPA.sym} 800 600 0 0 {name=Q3 model=pnpMPA spiceprefix=X w=1u l=2u m=1}
N 820 630 840 650 {}
C {lab_pin.sym} 840 650 0 0 {name=l25 lab=vss}
N 780 600 760 600 {}
C {lab_pin.sym} 760 600 0 0 {name=l26 lab=vss}
N 820 570 840 550 {}
C {lab_pin.sym} 840 550 0 0 {name=l27 lab=e3}
C {iopin.sym} -200 200 0 0 {name=p1 lab=vdd}
C {iopin.sym} -200 600 0 0 {name=p2 lab=vss}
C {iopin.sym} -200 100 0 0 {name=p3 lab=fb}
C {iopin.sym} -200 570 0 0 {name=p4 lab=sns1}
C {iopin.sym} -200 300 0 0 {name=p5 lab=sns2}
C {iopin.sym} 1000 400 0 0 {name=p6 lab=vref}
