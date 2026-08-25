v {xschem version=3.4.8RC file_version=1.3
* bandgap_startup (SG13CMOS5L) -- current-sensing, self-disabling startup
* kick for the pnpMPA-based core, phase 2/4 of the SG13CMOS5L port
* (issue #68; see design/sg13cmos5l/README.md).
*
* Ported from ../bandgap_startup.sch (SG13G2, issue #9/#22/#24), per this
* issue's own scope note: that schematic uses no bipolar device, so DR-0001's
* BVCEO/BVEBO Consequences-section constraint on bipolar devices in the
* startup path never bound it, and DR-0004's equivalent constraint for
* pnpMPA (bf ~= 1.10, low-gain but not a BVCEO/BVEBO concern here either)
* likewise does not bind THIS circuit -- neither variant instantiates a
* bipolar device at all.
*
* PORT VERIFICATION (not assumed -- checked against
* design/sg13cmos5l/bandgap_core.sch's actual sense nodes/pin set):
*   - bandgap_core (SG13CMOS5L)'s "sns1" is Q1's pnpMPA EMITTER, directly
*     driven by mirror leg M1's drain (no series resistor) -- structurally
*     identical position to ../bandgap_core.sch's "sns1" (npn13G2 Q1's
*     collector/base node, mirror M1's drain). Both swing ~0V in the
*     degenerate (mirror-off, fb~=vdd) state up to ~1 VBE/VEB (~0.7-0.8V)
*     once the core's mirror conducts -- confirmed against
*     design/sg13cmos5l/README.md's own measured op-point:
*     sns1=0.7810V at the 5uA design current (typ, 27C) -- essentially the
*     same magnitude ../bandgap_core.sch's own sns1 op-point uses (~0.78V
*     region per that schematic's header), so the SAME qualitative 0V-to-
*     ~0.78V swing MSENSE's gate relies on transfers unchanged.
*   - "fb" polarity also transfers unchanged: both cores' PMOS mirror legs
*     (M1-M3, sg13_hv_pmos, gate=fb) carry current that DECREASES as fb
*     rises toward vdd (less |Vgs| overdrive) -- so MKFB pulling fb LOW
*     during the degenerate state (this circuit's whole job) turns the
*     core's mirror ON in both variants, not just SG13G2's.
*   - sg13cmos5l_pr/rhigh.sym and sg13cmos5l_pr/sg13_hv_nmos.sym are
*     confirmed (by reading the installed PDK directly) to be the SAME
*     device as sg13g2_pr's own (relative symlinks into a sibling
*     ihp-sg13g2 checkout -- see design/sg13cmos5l/README.md "Tooling/PDK
*     friction encountered" for the upstream-filed gap this reflects) --
*     so RPU/MSENSE/MKFB's electrical behavior is identical to
*     ../bandgap_startup.sch's for any given W/L, not merely similar.
*
* SIZING: kept identical to ../bandgap_startup.sch's CURRENT (post-#24-
* resize) values, not the original pre-#24 W=2u MSENSE that #24 found
* insufficient release margin at wcs/sf/125C corners -- starting from the
* validated fix rather than re-deriving from scratch, since the underlying
* device (sg13_hv_nmos) and the sense-node swing (~0.78V VEB vs ~0.78V VBE)
* are both confirmed equivalent above. This is NOT independently re-swept
* against pnpMPA's own PVT grid (#65's job) -- see
* design/sg13cmos5l/README.md's own informal-check account for what WAS
* checked in this environment.
*   RPU:     rhigh, w=1u, l=1411.3u (R~=2Mohm) -- unchanged from
*            ../bandgap_startup.sch.
*   MSENSE:  sg13_hv_nmos, W=10u L=0.5u -- unchanged (the #24-resized value,
*            not the original W=2u).
*   MKFB:    sg13_hv_nmos, W=2u L=0.5u -- unchanged.
*
* Pins: vdd, vss, sns1, fb
}
G {}
K {}
V {}
S {}
E {}
C {sg13cmos5l_pr/rhigh.sym} 0 0 0 0 {name=RPU model=rhigh body=sub! spiceprefix=X w=1u l=1411.3u b=0 m=1}
N 0 -30 0 -50 {}
C {lab_pin.sym} 0 -50 0 0 {name=l1 lab=vdd}
N 0 30 0 50 {}
C {lab_pin.sym} 0 50 0 0 {name=l2 lab=det}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 400 0 0 0 {name=MSENSE model=sg13_hv_nmos w=10u l=0.5u ng=1 m=1}
N 420 -30 440 -50 {}
C {lab_pin.sym} 440 -50 0 0 {name=l3 lab=det}
N 380 0 360 0 {}
C {lab_pin.sym} 360 0 0 0 {name=l4 lab=sns1}
N 420 30 440 50 {}
C {lab_pin.sym} 440 50 0 0 {name=l5 lab=vss}
N 420 0 440 0 {}
C {lab_pin.sym} 440 0 0 0 {name=l6 lab=vss}
C {sg13cmos5l_pr/sg13_hv_nmos.sym} 800 0 0 0 {name=MKFB model=sg13_hv_nmos w=2u l=0.5u ng=1 m=1}
N 820 -30 840 -50 {}
C {lab_pin.sym} 840 -50 0 0 {name=l7 lab=fb}
N 780 0 760 0 {}
C {lab_pin.sym} 760 0 0 0 {name=l8 lab=det}
N 820 30 840 50 {}
C {lab_pin.sym} 840 50 0 0 {name=l9 lab=vss}
N 820 0 840 0 {}
C {lab_pin.sym} 840 0 0 0 {name=l10 lab=vss}
C {iopin.sym} -200 0 0 0 {name=p1 lab=vdd}
C {iopin.sym} -200 200 0 0 {name=p2 lab=vss}
C {iopin.sym} 200 -100 0 0 {name=p3 lab=sns1}
C {iopin.sym} 1000 -30 0 0 {name=p4 lab=fb}
