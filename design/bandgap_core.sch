v {xschem version=3.4.8RC file_version=1.3
* bandgap_core -- grounded-emitter npn13G2 (SiGe:C HBT) diode-referenced core
* (issue #9), per DR-0001 (spec/decision-records/0001-bipolar-device-selection.md)
* and DR-0002 (spec/decision-records/0002-supply-voltage-scope.md).
*
* THIS IS NOT A RE-PARAMETERIZED COPY of gf180-bandgap's or sky130-bandgap's
* grounded-collector PNP-pair Brokaw/Kuijk core (spec/porting-plan.md Sec 5).
* npn13G2 is an NPN device, so the diode-connected sensing devices here sit
* base-tied-to-collector, EMITTER grounded -- the mirror pushes current into
* each device's collector/base node from above, the mirror image of the
* PNP siblings' base/collector-grounded, emitter-driven-from-above core.
*
* Three matched sg13_hv_pmos mirror legs (M1, M2, M3; DR-0002: 3.3V HV
* flavor), gate-driven by an external error amplifier via "fb" (the
* amplifier itself, and the top-level integration wiring it to this core,
* are follow-on scope -- see design/README.md and the issue this PR closes
* for the explicit follow-up-issue note; gf180-bandgap and sky130-bandgap
* both decomposed core/amp/startup/top across separate issues too, this
* repo follows the same split rather than a single all-in-one schematic).
*
*   Q1 (npn13G2, Nx=1)  -- branch 1, unit device, sensed directly at sns1
*                          (M1 drain, no series resistor).
*   Q2 (npn13G2, Nx=8)  -- branch 2, 8x drawn (native Nx emitter-multiplicity
*                          parameter -- porting-plan.md Sec 2/Sec 5 notes
*                          this is closer to gf180's directly-sizable device
*                          than sky130's fixed-geometry PNP array), fed
*                          through PTAT resistor R2 from the M2 mirror node
*                          "sns2" down to Q2's collector/base node.
*   Q3 (npn13G2, Nx=1)  -- output branch, fed through summing resistor R1
*                          from the M3 mirror node (== "vref" directly, no
*                          cascode in this first pass -- see below) down to
*                          Q3's collector/base node.
*
* With a future external amplifier forcing sns1 = sns2 (this core exposes
* both as ports for that loop -- amplifier is out of this issue's scope),
* the amplifier's servo action drops the PTAT delta-VBE(Q1,Q2) entirely
* across R2 (Q1 has no series resistor), giving a PTAT branch current
*   I = dVBE(Q1,Q2) / R2 = VT*ln(Nx2/Nx1)/R2 = VT*ln(8)/R2
* mirrored (M1=M2=M3, same W/L) into the output branch, where
*   vref = VBE(Q3) + I*R1
* is the classic Brokaw CTAT+PTAT sum -- VBE(Q3) is this HBT's CTAT term
* (diode-connected, ~0.7-0.8V, falling with temperature), I*R1 is the PTAT
* term, sized (provisionally -- see below) to null the first-order TC the
* same way both sibling cores do, adapted to npn13G2's real device numbers
* per spec/porting-plan.md Sec 6 (IC07 anchor: ~3.8uA typ at VBE=0.7V,
* Nx=1, used below to pick the branch design current).
*
* BVCEO/BVEBO SAFETY (DR-0001 Consequences; porting-plan.md Sec 3): Q1-Q3
* are diode-connected (Vbc=0 by construction) with Vce = Vbe ~= 0.7-0.8V at
* the design current -- far below npn13G2's BVCEO target/min of 1.6V/1.4V,
* and never reverse-biased (Veb ~= 0, forward operation only), so no
* breakdown margin issue exists for these three core devices under any
* PVT corner this schematic's topology can reach. No cascode is used on
* the M1-M3 mirror in this first pass (unlike gf180's core, which cascodes
* its PMOS mirror purely for PSRR -- see spec/porting-plan.md Sec 5 on why
* that framing does not transfer as a "PSRR nicety" here): the mirror
* devices themselves are sg13_hv_pmos (3.3V-rated), and their Vds here
* (VDD minus a ~0.7-0.8V branch node) stays well inside that rating without
* one. A future cascode/output-stage revision, if added for PSRR, would
* still need to keep any BIPOLAR device it adds within the same BVCEO/BVEBO
* ceiling -- this core's own three devices already satisfy that constraint
* by construction (diode-connected, low Vce), so the constraint currently
* binds on nothing in this schematic; flagged here per the issue's
* "traceable design intent" ask, not because anything here is at risk.
*
* SIZING (PROVISIONAL, matching the sibling repos' own first-pass sizing
* practice, e.g. gf180 DR-0001-era bandgap_core.sch -- not yet simulation-
* verified; #10 (PVT testbenches) is the issue that grounds these numbers
* in actual sim/ evidence):
*   Design current I ~= 5uA/branch (anchored near npn13G2's own IC07
*   process-spec target current, 3.8uA typ/2.6-5.2uA range at VBE=0.7V,
*   Nx=1 -- spec/porting-plan.md Sec 6), giving:
*     R2 = VT*ln(8)/I ~= 25.85mV*2.079/5uA ~= 10.75 kOhm
*         -> rppd, w=2um (>=2um per the process spec's precision-resistor
*            recommendation, spec/porting-plan.md Sec 2), l ~= 82.7um
*            (solved from rppd.sym's own R(w,l) formula, b=0 bends)
*     R1 sized for a provisional vref ~= 1.2V target with VBE(Q3) ~= 0.75V
*         assumed (not yet simulated): R1 = (1.2 - 0.75)/5uA = 90 kOhm
*         -> rppd, w=2um, l ~= 694.5um (same formula)
*   Mirror M1=M2=M3: sg13_hv_pmos, W=10u/L=1u (W/L=10, matched across all
*   three legs by construction -- mirror accuracy depends on this match,
*   not on the absolute W/L chosen here).
* None of these values are simulation-grounded yet -- #10 will re-derive
* them against the actual VBIC model card and PVT corners the way gf180's
* #55/#61/#96/#147 chain did for its own core (see that repo's
* design/bandgap_core.sch header for the shape of that process).
*
* Pins: vdd, vss, fb, sns1, sns2, vref
}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_hv_pmos.sym} 0 200 0 0 {name=M1 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 20 170 40 150 {}
C {lab_pin.sym} 40 150 0 0 {name=l1 lab=vdd}
N 20 200 40 200 {}
C {lab_pin.sym} 40 200 0 0 {name=l2 lab=vdd}
N -20 200 -40 200 {}
C {lab_pin.sym} -40 200 0 0 {name=l3 lab=fb}
N 20 230 40 250 {}
C {lab_pin.sym} 40 250 0 0 {name=l4 lab=sns1}
C {sg13g2_pr/npn13G2.sym} 0 600 0 0 {name=Q1 model=npn13G2 spiceprefix=X Nx=1}
N 20 570 40 550 {}
C {lab_pin.sym} 40 550 0 0 {name=l5 lab=sns1}
N -20 600 -40 600 {}
C {lab_pin.sym} -40 600 0 0 {name=l6 lab=sns1}
N 20 630 40 650 {}
C {lab_pin.sym} 40 650 0 0 {name=l7 lab=vss}
N 20 600 40 600 {}
C {lab_pin.sym} 40 600 0 0 {name=l8 lab=vss}
C {sg13g2_pr/sg13_hv_pmos.sym} 400 200 0 0 {name=M2 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 420 170 440 150 {}
C {lab_pin.sym} 440 150 0 0 {name=l9 lab=vdd}
N 420 200 440 200 {}
C {lab_pin.sym} 440 200 0 0 {name=l10 lab=vdd}
N 380 200 360 200 {}
C {lab_pin.sym} 360 200 0 0 {name=l11 lab=fb}
N 420 230 440 250 {}
C {lab_pin.sym} 440 250 0 0 {name=l12 lab=sns2}
C {sg13g2_pr/rppd.sym} 400 400 0 0 {name=R2 model=rppd body=sub! spiceprefix=X w=2u l=82.7u b=0 m=1}
N 400 370 400 350 {}
C {lab_pin.sym} 400 350 0 0 {name=l13 lab=sns2}
N 400 430 400 450 {}
C {lab_pin.sym} 400 450 0 0 {name=l14 lab=cb2}
C {sg13g2_pr/npn13G2.sym} 400 600 0 0 {name=Q2 model=npn13G2 spiceprefix=X Nx=8}
N 420 570 440 550 {}
C {lab_pin.sym} 440 550 0 0 {name=l15 lab=cb2}
N 380 600 360 600 {}
C {lab_pin.sym} 360 600 0 0 {name=l16 lab=cb2}
N 420 630 440 650 {}
C {lab_pin.sym} 440 650 0 0 {name=l17 lab=vss}
N 420 600 440 600 {}
C {lab_pin.sym} 440 600 0 0 {name=l18 lab=vss}
C {sg13g2_pr/sg13_hv_pmos.sym} 800 200 0 0 {name=M3 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 820 170 840 150 {}
C {lab_pin.sym} 840 150 0 0 {name=l19 lab=vdd}
N 820 200 840 200 {}
C {lab_pin.sym} 840 200 0 0 {name=l20 lab=vdd}
N 780 200 760 200 {}
C {lab_pin.sym} 760 200 0 0 {name=l21 lab=fb}
N 820 230 840 250 {}
C {lab_pin.sym} 840 250 0 0 {name=l22 lab=vref}
C {sg13g2_pr/rppd.sym} 800 400 0 0 {name=R1 model=rppd body=sub! spiceprefix=X w=2u l=694.5u b=0 m=1}
N 800 370 800 350 {}
C {lab_pin.sym} 800 350 0 0 {name=l23 lab=vref}
N 800 430 800 450 {}
C {lab_pin.sym} 800 450 0 0 {name=l24 lab=cb3}
C {sg13g2_pr/npn13G2.sym} 800 600 0 0 {name=Q3 model=npn13G2 spiceprefix=X Nx=1}
N 820 570 840 550 {}
C {lab_pin.sym} 840 550 0 0 {name=l25 lab=cb3}
N 780 600 760 600 {}
C {lab_pin.sym} 760 600 0 0 {name=l26 lab=cb3}
N 820 630 840 650 {}
C {lab_pin.sym} 840 650 0 0 {name=l27 lab=vss}
N 820 600 840 600 {}
C {lab_pin.sym} 840 600 0 0 {name=l28 lab=vss}
C {iopin.sym} -200 200 0 0 {name=p1 lab=vdd}
C {iopin.sym} -200 600 0 0 {name=p2 lab=vss}
C {iopin.sym} -200 100 0 0 {name=p3 lab=fb}
C {iopin.sym} -200 570 0 0 {name=p4 lab=sns1}
C {iopin.sym} -200 300 0 0 {name=p5 lab=sns2}
C {iopin.sym} 1000 400 0 0 {name=p6 lab=vref}
