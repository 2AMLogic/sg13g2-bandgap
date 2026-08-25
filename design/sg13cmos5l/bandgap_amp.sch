v {xschem version=3.4.8RC file_version=1.3
* bandgap_amp (SG13CMOS5L) -- error amplifier closing the loop for
* design/sg13cmos5l/bandgap_core.sch, phase 2/4 of the SG13CMOS5L port
* (issue #68; see design/sg13cmos5l/README.md).
*
* Ported from ../bandgap_amp.sch (SG13G2, issue #58), per this issue's own
* scope note: that schematic uses no bipolar device (an all-sg13_hv_pmos/
* sg13_hv_nmos OTA), so DR-0001's/DR-0004's bipolar BVCEO/BVEBO
* constraints never bound it in either variant.
*
* PORT VERIFICATION (not assumed -- polarity and input common-mode range
* re-checked against design/sg13cmos5l/bandgap_core.sch's own DC
* operating point, per this issue's own scope note, rather than assuming
* ../bandgap_amp.sch's topology transfers as-is):
*
* -------------------------------------------------------------- polarity
* design/sg13cmos5l/bandgap_core.sch's three legs (M1/M2/M3, gated
* together by "fb") carry equal current I(fb), monotonically DECREASING in
* fb (raising fb lowers each sg13_hv_pmos leg's |Vgs| overdrive) -- the
* SAME mirror-gate relationship ../bandgap_core.sch's own M1-M3 have (both
* cores use identical sg13_hv_pmos mirror legs gated by fb; only the
* diode-connected bipolar leg below each mirror differs: grounded-emitter
* npn13G2 there vs. grounded-collector pnpMPA here). sns1 = VEB(Q1,I)
* directly; sns2 = VEB(Q2,I) + I*R2 (Q2 is the 8x-area leg, so
* VEB(Q2,I) < VEB(Q1,I) by ~VT*ln(8), nearly current-independent -- see
* bandgap_core.sch's own header for the measured dVEB=55.35mV). So, by the
* IDENTICAL algebra ../bandgap_amp.sch's header derives (only VBE relabeled
* VEB):
*   e := sns2 - sns1 ~= I*R2 - VT*ln(8)
* is monotonically INCREASING in I, hence monotonically DECREASING in fb.
* For negative feedback, this amplifier's output must INCREASE with
* e = sns2 - sns1: sns2 is therefore this amplifier's non-inverting input
* (in_p), sns1 the inverting input (in_n) -- the SAME assignment
* ../bandgap_amp.sch uses, confirmed by re-derivation against this core's
* own topology rather than copied on the assumption the two cores' sense
* nodes behave alike. Getting this backwards would make the loop positive
* feedback (rail to a supply rather than settle) -- this is the single
* most safety-critical wiring decision in this schematic and in
* design/sg13cmos5l/bandgap_top.sch's instantiation of it, exactly as
* ../bandgap_amp.sch's own header warns.
*
* ------------------------------------------------------- common-mode check
* design/sg13cmos5l/README.md's own measured op-point (typ, 27C, 5uA
* design current, real pnpMPA/PSP103/r3_cmc devices, no substitutions):
*   sns1 = 0.7810 V, sns2 = 0.7818 V
* -- both sit in the SAME ~0.7-0.8V, one-VEB-above-vss common-mode band
* ../bandgap_amp.sch's header measured for its own (npn13G2 VBE-based)
* sns1/sns2 (~0.7-0.8V, one VBE). This is the low, near-vss common mode a
* PMOS input pair is built for (the same reasoning ../bandgap_amp.sch's
* header cites from sky130-bandgap's own original placeholder amp) -- a
* PMOS input pair therefore transfers unchanged, not merely by analogy but
* by a directly re-measured, near-identical common-mode voltage (0.78V VEB
* here vs ~0.78V VBE there -- pnpMPA's VEB and npn13G2's VBE land in
* practically the same place at this design current, so no input-pair
* polarity flip or level-shift is needed).
*
* ---------------------------------------------------------------- topology
* Unchanged from ../bandgap_amp.sch: single-stage, current-mirror-folded
* OTA, all real sg13_hv_pmos/sg13_hv_nmos devices (3.3V-rated, DR-0002
* inherited unchanged), no bipolar device -- confirmed identical devices to
* SG13G2's own (sg13cmos5l_pr/sg13_hv_pmos.sym and
* sg13cmos5l_pr/sg13_hv_nmos.sym are relative symlinks into a sibling
* ihp-sg13g2 checkout, read directly -- see
* design/sg13cmos5l/README.md "Tooling/PDK friction encountered").
*
*   MTAIL   sg13_hv_pmos, gate=out (this amplifier's own output/fb node),
*           source=vdd, drain=tail. Matched 1:1 (w=10u l=1u) to
*           design/sg13cmos5l/bandgap_core.sch's M1/M2/M3 -- same
*           self-consistency argument as ../bandgap_amp.sch's header,
*           unchanged since this core's M1-M3 use the identical w=10u l=1u
*           geometry.
*   MP1/MP2 sg13_hv_pmos input pair (w=20u l=1u), sources tied to "tail".
*           MP1 gate = in_p (sns2 at the top level), MP2 gate = in_n
*           (sns1) -- see "polarity" above.
*   MN1/MN2 sg13_hv_nmos diode-connected loads (w=10u l=1u) on each input-
*           pair drain (d1, d2).
*   MN3     sg13_hv_nmos, gate=d1 (mirrors MN1 1:1), drain=out.
*   MN4/MP3/MP4
*           MN4 (gate=d2, mirrors MN2 1:1) pulls down internal node "pn";
*           MP3 (diode-connected on pn) supplies that current from vdd;
*           MP4 (gate=pn, mirrors MP3 1:1) sources the same current INTO
*           the output node -- same NMOS-then-PMOS fold as ../bandgap_amp.sch,
*           for the identical reason (output must be able to swing near
*           vdd to fully shut off M1-M3).
*
* No compensation capacitor in this first pass, same as ../bandgap_amp.sch
* -- loop stability not yet measured (out of this issue's scope; #65).
* DR-0004 additionally notes this PDK has no MIM cap (only MoM/MOS caps),
* forward guidance for whichever future phase adds compensation here.
*
* --------------------------------------------------------------- bias order
* Unchanged from ../bandgap_amp.sch: MTAIL's own gate is this amplifier's
* output, which collapses toward vdd right along with bandgap_core's own
* degenerate (zero-current) state -- both this amp and the core come up
* from the same startup kick (design/sg13cmos5l/bandgap_startup.sch's
* MKFB pulling "fb" low), not one bootstrapping the other independently.
* See design/sg13cmos5l/bandgap_top.sch for how the three blocks share
* that one "fb" node.
*
* Pins: vdd, vss, in_p, in_n, out
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} -600 0 0 0 {name=MTAIL model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N -580 -30 -560 -50 {}
C {lab_pin.sym} -560 -50 0 0 {name=l1 lab=vdd}
N -620 0 -640 0 {}
C {lab_pin.sym} -640 0 0 0 {name=l2 lab=out}
N -580 0 -560 0 {}
C {lab_pin.sym} -560 0 0 0 {name=l3 lab=vdd}
N -580 30 -560 50 {}
C {lab_pin.sym} -560 50 0 0 {name=l4 lab=tail}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 0 0 0 0 {name=MP1 model=sg13_hv_pmos w=20u l=1u ng=1 m=1}
N 20 -30 40 -50 {}
C {lab_pin.sym} 40 -50 0 0 {name=l5 lab=tail}
N -20 0 -40 0 {}
C {lab_pin.sym} -40 0 0 0 {name=l6 lab=in_p}
N 20 0 40 0 {}
C {lab_pin.sym} 40 0 0 0 {name=l7 lab=vdd}
N 20 30 40 50 {}
C {lab_pin.sym} 40 50 0 0 {name=l8 lab=d1}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 400 0 0 0 {name=MP2 model=sg13_hv_pmos w=20u l=1u ng=1 m=1}
N 420 -30 440 -50 {}
C {lab_pin.sym} 440 -50 0 0 {name=l9 lab=tail}
N 380 0 360 0 {}
C {lab_pin.sym} 360 0 0 0 {name=l10 lab=in_n}
N 420 0 440 0 {}
C {lab_pin.sym} 440 0 0 0 {name=l11 lab=vdd}
N 420 30 440 50 {}
C {lab_pin.sym} 440 50 0 0 {name=l12 lab=d2}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1200 0 0 0 {name=MP3 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 1220 -30 1240 -50 {}
C {lab_pin.sym} 1240 -50 0 0 {name=l13 lab=vdd}
N 1180 0 1160 0 {}
C {lab_pin.sym} 1160 0 0 0 {name=l14 lab=pn}
N 1220 0 1240 0 {}
C {lab_pin.sym} 1240 0 0 0 {name=l15 lab=vdd}
N 1220 30 1240 50 {}
C {lab_pin.sym} 1240 50 0 0 {name=l16 lab=pn}
C {sg13cmos5l_pr/sg13_hv_pmos.sym} 1600 0 0 0 {name=MP4 model=sg13_hv_pmos w=10u l=1u ng=1 m=1}
N 1620 -30 1640 -50 {}
C {lab_pin.sym} 1640 -50 0 0 {name=l17 lab=vdd}
N 1580 0 1560 0 {}
C {lab_pin.sym} 1560 0 0 0 {name=l18 lab=pn}
N 1620 0 1640 0 {}
C {lab_pin.sym} 1640 0 0 0 {name=l19 lab=vdd}
N 1620 30 1640 50 {}
C {lab_pin.sym} 1640 50 0 0 {name=l20 lab=out}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 0 400 0 0 {name=MN1 model=sg13_hv_nmos w=10u l=1u ng=1 m=1}
N 20 370 40 350 {}
C {lab_pin.sym} 40 350 0 0 {name=l21 lab=d1}
N -20 400 -40 400 {}
C {lab_pin.sym} -40 400 0 0 {name=l22 lab=d1}
N 20 400 40 400 {}
C {lab_pin.sym} 40 400 0 0 {name=l23 lab=vss}
N 20 430 40 450 {}
C {lab_pin.sym} 40 450 0 0 {name=l24 lab=vss}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 400 400 0 0 {name=MN2 model=sg13_hv_nmos w=10u l=1u ng=1 m=1}
N 420 370 440 350 {}
C {lab_pin.sym} 440 350 0 0 {name=l25 lab=d2}
N 380 400 360 400 {}
C {lab_pin.sym} 360 400 0 0 {name=l26 lab=d2}
N 420 400 440 400 {}
C {lab_pin.sym} 440 400 0 0 {name=l27 lab=vss}
N 420 430 440 450 {}
C {lab_pin.sym} 440 450 0 0 {name=l28 lab=vss}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 800 400 0 0 {name=MN3 model=sg13_hv_nmos w=10u l=1u ng=1 m=1}
N 820 370 840 350 {}
C {lab_pin.sym} 840 350 0 0 {name=l29 lab=out}
N 780 400 760 400 {}
C {lab_pin.sym} 760 400 0 0 {name=l30 lab=d1}
N 820 400 840 400 {}
C {lab_pin.sym} 840 400 0 0 {name=l31 lab=vss}
N 820 430 840 450 {}
C {lab_pin.sym} 840 450 0 0 {name=l32 lab=vss}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 1200 400 0 0 {name=MN4 model=sg13_hv_nmos w=10u l=1u ng=1 m=1}
N 1220 370 1240 350 {}
C {lab_pin.sym} 1240 350 0 0 {name=l33 lab=pn}
N 1180 400 1160 400 {}
C {lab_pin.sym} 1160 400 0 0 {name=l34 lab=d2}
N 1220 400 1240 400 {}
C {lab_pin.sym} 1240 400 0 0 {name=l35 lab=vss}
N 1220 430 1240 450 {}
C {lab_pin.sym} 1240 450 0 0 {name=l36 lab=vss}
C {iopin.sym} -900 0 0 0 {name=p1 lab=vdd}
C {iopin.sym} -900 700 0 0 {name=p2 lab=vss}
C {iopin.sym} -900 -100 0 0 {name=p3 lab=in_p}
C {iopin.sym} -900 100 0 0 {name=p4 lab=in_n}
C {iopin.sym} 1900 50 0 0 {name=p5 lab=out}
