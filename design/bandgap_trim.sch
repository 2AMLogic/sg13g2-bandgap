v {xschem version=3.4.8RC file_version=1.3
* bandgap_trim -- binary-weighted trim ladder on the core's output-branch
* summing resistor (issue #229, the design work DR-0011's Trim row obligates:
* "Trim: 1-point at 27 C; range >= +/-15%; resolution <= 0.25%/step;
* magnitude only").
*
* TOPOLOGY (gf180-bandgap issue #14's ladder, re-sized for this core -- see
* design/bandgap_trim_network.md for the full sizing derivation and the
* coverage argument):
*   255 IDENTICAL rppd unit segments (w=2u, l=3.43u, b=0, m=1) in one
*   series string from "in" to "out", tapped after 1/3/7/15/31/63/127 units
*   into eight binary-weighted groups (weights 1/2/4/8/16/32/64/128). Each
*   group is shunted by one strap RS0..RS7 -- NOT a fabricated device, a
*   behavioral resistor standing in for a metal-option / probe-pad link
*   (1e-3 ohm = link drawn, group shorted out; 1e12 ohm = link cut, group
*   in circuit), decoded from the subcircuit-local parameter trim_code
*   (0..255, default 128):
*     bit_b  = floor(trim_code/2^b) - 2*floor(trim_code/2^(b+1))
*     RS<b>  = 1e-3 ohm  when bit_b = 0  (strap closed, group shorted out)
*           = 1e12 ohm  when bit_b = 1  (strap open, group in circuit)
*   so Rtrim(trim_code) = trim_code * R_unit, monotonic and exact-binary by
*   construction at every corner (integer counts of the identical physical
*   device -- gf180's measured lesson that six DIFFERENTLY-SIZED single
*   resistors do not hold 2^b ratios across PVT does not apply here).
*
* PLACEMENT NOTE: this schematic was laid out programmatically (units in a
* 16-column grid, straps in a column to the right) and connects BY NET
* LABEL -- every device pin carries a short wire stub to a lab_pin naming
* its net (in, t001..t254, out) -- the same label-connectivity convention
* design/bandgap_core.sch uses for its shared nodes. Electrical position in
* the drawing is cosmetic; the unit index -> net mapping is:
*   unit RU<i> spans net(i-1) -> net(i),  net(0)=in, net(255)=out
*   strap RS<b> spans the two tap nodes of its group (see bandgap_trim.sym).
*
* SIZING (typ res corner, 27 C, measured against the r3_cmc model -- full
* derivation in design/bandgap_trim_network.md):
*   R_unit = R(w=2u, l=3.43u) = 478.3 ohm; measured closed-loop trim step
*   I*R_unit = 2.443 mV = 0.2327% of the 1.050 V nominal (<= 0.25%/step),
*   so the code-0..255 span is 1.2217 kohm and the default code 128 leaves
*   127 steps up / 128 steps down = 310.3/312.7 mV = 29.6%/29.8% of vref --
*   well past the ratified +/-15% floor, sized by the CORRELATED-coverage
*   requirement (a die needing +13.3% correction has a current ~14% low and
*   therefore a ~14% smaller trim step; see the design doc), not by the
*   naive voltage window.
*
* Pins: in (from the core's R1 base resistor, node tn0 in bandgap_core.sch),
* out (to Q3's collector/base node cb3), sub (rppd bodies).
}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/rppd.sym} 300 250 0 0 {name=RU1 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 220 300 195 {}
C {lab_pin.sym} 300 195 2 0 {name=l1 lab=in}
N 300 280 300 305 {}
C {lab_pin.sym} 300 305 0 0 {name=l2 lab=t001}
C {sg13g2_pr/rppd.sym} 550 250 0 0 {name=RU2 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 220 550 195 {}
C {lab_pin.sym} 550 195 2 0 {name=l3 lab=t001}
N 550 280 550 305 {}
C {lab_pin.sym} 550 305 0 0 {name=l4 lab=t002}
C {sg13g2_pr/rppd.sym} 800 250 0 0 {name=RU3 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 220 800 195 {}
C {lab_pin.sym} 800 195 2 0 {name=l5 lab=t002}
N 800 280 800 305 {}
C {lab_pin.sym} 800 305 0 0 {name=l6 lab=t003}
C {sg13g2_pr/rppd.sym} 1050 250 0 0 {name=RU4 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 220 1050 195 {}
C {lab_pin.sym} 1050 195 2 0 {name=l7 lab=t003}
N 1050 280 1050 305 {}
C {lab_pin.sym} 1050 305 0 0 {name=l8 lab=t004}
C {sg13g2_pr/rppd.sym} 1300 250 0 0 {name=RU5 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 220 1300 195 {}
C {lab_pin.sym} 1300 195 2 0 {name=l9 lab=t004}
N 1300 280 1300 305 {}
C {lab_pin.sym} 1300 305 0 0 {name=l10 lab=t005}
C {sg13g2_pr/rppd.sym} 1550 250 0 0 {name=RU6 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 220 1550 195 {}
C {lab_pin.sym} 1550 195 2 0 {name=l11 lab=t005}
N 1550 280 1550 305 {}
C {lab_pin.sym} 1550 305 0 0 {name=l12 lab=t006}
C {sg13g2_pr/rppd.sym} 1800 250 0 0 {name=RU7 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 220 1800 195 {}
C {lab_pin.sym} 1800 195 2 0 {name=l13 lab=t006}
N 1800 280 1800 305 {}
C {lab_pin.sym} 1800 305 0 0 {name=l14 lab=t007}
C {sg13g2_pr/rppd.sym} 2050 250 0 0 {name=RU8 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 220 2050 195 {}
C {lab_pin.sym} 2050 195 2 0 {name=l15 lab=t007}
N 2050 280 2050 305 {}
C {lab_pin.sym} 2050 305 0 0 {name=l16 lab=t008}
C {sg13g2_pr/rppd.sym} 2300 250 0 0 {name=RU9 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 220 2300 195 {}
C {lab_pin.sym} 2300 195 2 0 {name=l17 lab=t008}
N 2300 280 2300 305 {}
C {lab_pin.sym} 2300 305 0 0 {name=l18 lab=t009}
C {sg13g2_pr/rppd.sym} 2550 250 0 0 {name=RU10 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 220 2550 195 {}
C {lab_pin.sym} 2550 195 2 0 {name=l19 lab=t009}
N 2550 280 2550 305 {}
C {lab_pin.sym} 2550 305 0 0 {name=l20 lab=t010}
C {sg13g2_pr/rppd.sym} 2800 250 0 0 {name=RU11 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 220 2800 195 {}
C {lab_pin.sym} 2800 195 2 0 {name=l21 lab=t010}
N 2800 280 2800 305 {}
C {lab_pin.sym} 2800 305 0 0 {name=l22 lab=t011}
C {sg13g2_pr/rppd.sym} 3050 250 0 0 {name=RU12 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 220 3050 195 {}
C {lab_pin.sym} 3050 195 2 0 {name=l23 lab=t011}
N 3050 280 3050 305 {}
C {lab_pin.sym} 3050 305 0 0 {name=l24 lab=t012}
C {sg13g2_pr/rppd.sym} 3300 250 0 0 {name=RU13 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 220 3300 195 {}
C {lab_pin.sym} 3300 195 2 0 {name=l25 lab=t012}
N 3300 280 3300 305 {}
C {lab_pin.sym} 3300 305 0 0 {name=l26 lab=t013}
C {sg13g2_pr/rppd.sym} 3550 250 0 0 {name=RU14 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 220 3550 195 {}
C {lab_pin.sym} 3550 195 2 0 {name=l27 lab=t013}
N 3550 280 3550 305 {}
C {lab_pin.sym} 3550 305 0 0 {name=l28 lab=t014}
C {sg13g2_pr/rppd.sym} 3800 250 0 0 {name=RU15 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 220 3800 195 {}
C {lab_pin.sym} 3800 195 2 0 {name=l29 lab=t014}
N 3800 280 3800 305 {}
C {lab_pin.sym} 3800 305 0 0 {name=l30 lab=t015}
C {sg13g2_pr/rppd.sym} 4050 250 0 0 {name=RU16 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 220 4050 195 {}
C {lab_pin.sym} 4050 195 2 0 {name=l31 lab=t015}
N 4050 280 4050 305 {}
C {lab_pin.sym} 4050 305 0 0 {name=l32 lab=t016}
C {sg13g2_pr/rppd.sym} 300 470 0 0 {name=RU17 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 440 300 415 {}
C {lab_pin.sym} 300 415 2 0 {name=l33 lab=t016}
N 300 500 300 525 {}
C {lab_pin.sym} 300 525 0 0 {name=l34 lab=t017}
C {sg13g2_pr/rppd.sym} 550 470 0 0 {name=RU18 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 440 550 415 {}
C {lab_pin.sym} 550 415 2 0 {name=l35 lab=t017}
N 550 500 550 525 {}
C {lab_pin.sym} 550 525 0 0 {name=l36 lab=t018}
C {sg13g2_pr/rppd.sym} 800 470 0 0 {name=RU19 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 440 800 415 {}
C {lab_pin.sym} 800 415 2 0 {name=l37 lab=t018}
N 800 500 800 525 {}
C {lab_pin.sym} 800 525 0 0 {name=l38 lab=t019}
C {sg13g2_pr/rppd.sym} 1050 470 0 0 {name=RU20 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 440 1050 415 {}
C {lab_pin.sym} 1050 415 2 0 {name=l39 lab=t019}
N 1050 500 1050 525 {}
C {lab_pin.sym} 1050 525 0 0 {name=l40 lab=t020}
C {sg13g2_pr/rppd.sym} 1300 470 0 0 {name=RU21 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 440 1300 415 {}
C {lab_pin.sym} 1300 415 2 0 {name=l41 lab=t020}
N 1300 500 1300 525 {}
C {lab_pin.sym} 1300 525 0 0 {name=l42 lab=t021}
C {sg13g2_pr/rppd.sym} 1550 470 0 0 {name=RU22 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 440 1550 415 {}
C {lab_pin.sym} 1550 415 2 0 {name=l43 lab=t021}
N 1550 500 1550 525 {}
C {lab_pin.sym} 1550 525 0 0 {name=l44 lab=t022}
C {sg13g2_pr/rppd.sym} 1800 470 0 0 {name=RU23 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 440 1800 415 {}
C {lab_pin.sym} 1800 415 2 0 {name=l45 lab=t022}
N 1800 500 1800 525 {}
C {lab_pin.sym} 1800 525 0 0 {name=l46 lab=t023}
C {sg13g2_pr/rppd.sym} 2050 470 0 0 {name=RU24 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 440 2050 415 {}
C {lab_pin.sym} 2050 415 2 0 {name=l47 lab=t023}
N 2050 500 2050 525 {}
C {lab_pin.sym} 2050 525 0 0 {name=l48 lab=t024}
C {sg13g2_pr/rppd.sym} 2300 470 0 0 {name=RU25 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 440 2300 415 {}
C {lab_pin.sym} 2300 415 2 0 {name=l49 lab=t024}
N 2300 500 2300 525 {}
C {lab_pin.sym} 2300 525 0 0 {name=l50 lab=t025}
C {sg13g2_pr/rppd.sym} 2550 470 0 0 {name=RU26 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 440 2550 415 {}
C {lab_pin.sym} 2550 415 2 0 {name=l51 lab=t025}
N 2550 500 2550 525 {}
C {lab_pin.sym} 2550 525 0 0 {name=l52 lab=t026}
C {sg13g2_pr/rppd.sym} 2800 470 0 0 {name=RU27 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 440 2800 415 {}
C {lab_pin.sym} 2800 415 2 0 {name=l53 lab=t026}
N 2800 500 2800 525 {}
C {lab_pin.sym} 2800 525 0 0 {name=l54 lab=t027}
C {sg13g2_pr/rppd.sym} 3050 470 0 0 {name=RU28 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 440 3050 415 {}
C {lab_pin.sym} 3050 415 2 0 {name=l55 lab=t027}
N 3050 500 3050 525 {}
C {lab_pin.sym} 3050 525 0 0 {name=l56 lab=t028}
C {sg13g2_pr/rppd.sym} 3300 470 0 0 {name=RU29 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 440 3300 415 {}
C {lab_pin.sym} 3300 415 2 0 {name=l57 lab=t028}
N 3300 500 3300 525 {}
C {lab_pin.sym} 3300 525 0 0 {name=l58 lab=t029}
C {sg13g2_pr/rppd.sym} 3550 470 0 0 {name=RU30 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 440 3550 415 {}
C {lab_pin.sym} 3550 415 2 0 {name=l59 lab=t029}
N 3550 500 3550 525 {}
C {lab_pin.sym} 3550 525 0 0 {name=l60 lab=t030}
C {sg13g2_pr/rppd.sym} 3800 470 0 0 {name=RU31 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 440 3800 415 {}
C {lab_pin.sym} 3800 415 2 0 {name=l61 lab=t030}
N 3800 500 3800 525 {}
C {lab_pin.sym} 3800 525 0 0 {name=l62 lab=t031}
C {sg13g2_pr/rppd.sym} 4050 470 0 0 {name=RU32 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 440 4050 415 {}
C {lab_pin.sym} 4050 415 2 0 {name=l63 lab=t031}
N 4050 500 4050 525 {}
C {lab_pin.sym} 4050 525 0 0 {name=l64 lab=t032}
C {sg13g2_pr/rppd.sym} 300 690 0 0 {name=RU33 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 660 300 635 {}
C {lab_pin.sym} 300 635 2 0 {name=l65 lab=t032}
N 300 720 300 745 {}
C {lab_pin.sym} 300 745 0 0 {name=l66 lab=t033}
C {sg13g2_pr/rppd.sym} 550 690 0 0 {name=RU34 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 660 550 635 {}
C {lab_pin.sym} 550 635 2 0 {name=l67 lab=t033}
N 550 720 550 745 {}
C {lab_pin.sym} 550 745 0 0 {name=l68 lab=t034}
C {sg13g2_pr/rppd.sym} 800 690 0 0 {name=RU35 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 660 800 635 {}
C {lab_pin.sym} 800 635 2 0 {name=l69 lab=t034}
N 800 720 800 745 {}
C {lab_pin.sym} 800 745 0 0 {name=l70 lab=t035}
C {sg13g2_pr/rppd.sym} 1050 690 0 0 {name=RU36 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 660 1050 635 {}
C {lab_pin.sym} 1050 635 2 0 {name=l71 lab=t035}
N 1050 720 1050 745 {}
C {lab_pin.sym} 1050 745 0 0 {name=l72 lab=t036}
C {sg13g2_pr/rppd.sym} 1300 690 0 0 {name=RU37 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 660 1300 635 {}
C {lab_pin.sym} 1300 635 2 0 {name=l73 lab=t036}
N 1300 720 1300 745 {}
C {lab_pin.sym} 1300 745 0 0 {name=l74 lab=t037}
C {sg13g2_pr/rppd.sym} 1550 690 0 0 {name=RU38 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 660 1550 635 {}
C {lab_pin.sym} 1550 635 2 0 {name=l75 lab=t037}
N 1550 720 1550 745 {}
C {lab_pin.sym} 1550 745 0 0 {name=l76 lab=t038}
C {sg13g2_pr/rppd.sym} 1800 690 0 0 {name=RU39 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 660 1800 635 {}
C {lab_pin.sym} 1800 635 2 0 {name=l77 lab=t038}
N 1800 720 1800 745 {}
C {lab_pin.sym} 1800 745 0 0 {name=l78 lab=t039}
C {sg13g2_pr/rppd.sym} 2050 690 0 0 {name=RU40 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 660 2050 635 {}
C {lab_pin.sym} 2050 635 2 0 {name=l79 lab=t039}
N 2050 720 2050 745 {}
C {lab_pin.sym} 2050 745 0 0 {name=l80 lab=t040}
C {sg13g2_pr/rppd.sym} 2300 690 0 0 {name=RU41 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 660 2300 635 {}
C {lab_pin.sym} 2300 635 2 0 {name=l81 lab=t040}
N 2300 720 2300 745 {}
C {lab_pin.sym} 2300 745 0 0 {name=l82 lab=t041}
C {sg13g2_pr/rppd.sym} 2550 690 0 0 {name=RU42 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 660 2550 635 {}
C {lab_pin.sym} 2550 635 2 0 {name=l83 lab=t041}
N 2550 720 2550 745 {}
C {lab_pin.sym} 2550 745 0 0 {name=l84 lab=t042}
C {sg13g2_pr/rppd.sym} 2800 690 0 0 {name=RU43 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 660 2800 635 {}
C {lab_pin.sym} 2800 635 2 0 {name=l85 lab=t042}
N 2800 720 2800 745 {}
C {lab_pin.sym} 2800 745 0 0 {name=l86 lab=t043}
C {sg13g2_pr/rppd.sym} 3050 690 0 0 {name=RU44 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 660 3050 635 {}
C {lab_pin.sym} 3050 635 2 0 {name=l87 lab=t043}
N 3050 720 3050 745 {}
C {lab_pin.sym} 3050 745 0 0 {name=l88 lab=t044}
C {sg13g2_pr/rppd.sym} 3300 690 0 0 {name=RU45 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 660 3300 635 {}
C {lab_pin.sym} 3300 635 2 0 {name=l89 lab=t044}
N 3300 720 3300 745 {}
C {lab_pin.sym} 3300 745 0 0 {name=l90 lab=t045}
C {sg13g2_pr/rppd.sym} 3550 690 0 0 {name=RU46 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 660 3550 635 {}
C {lab_pin.sym} 3550 635 2 0 {name=l91 lab=t045}
N 3550 720 3550 745 {}
C {lab_pin.sym} 3550 745 0 0 {name=l92 lab=t046}
C {sg13g2_pr/rppd.sym} 3800 690 0 0 {name=RU47 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 660 3800 635 {}
C {lab_pin.sym} 3800 635 2 0 {name=l93 lab=t046}
N 3800 720 3800 745 {}
C {lab_pin.sym} 3800 745 0 0 {name=l94 lab=t047}
C {sg13g2_pr/rppd.sym} 4050 690 0 0 {name=RU48 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 660 4050 635 {}
C {lab_pin.sym} 4050 635 2 0 {name=l95 lab=t047}
N 4050 720 4050 745 {}
C {lab_pin.sym} 4050 745 0 0 {name=l96 lab=t048}
C {sg13g2_pr/rppd.sym} 300 910 0 0 {name=RU49 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 880 300 855 {}
C {lab_pin.sym} 300 855 2 0 {name=l97 lab=t048}
N 300 940 300 965 {}
C {lab_pin.sym} 300 965 0 0 {name=l98 lab=t049}
C {sg13g2_pr/rppd.sym} 550 910 0 0 {name=RU50 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 880 550 855 {}
C {lab_pin.sym} 550 855 2 0 {name=l99 lab=t049}
N 550 940 550 965 {}
C {lab_pin.sym} 550 965 0 0 {name=l100 lab=t050}
C {sg13g2_pr/rppd.sym} 800 910 0 0 {name=RU51 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 880 800 855 {}
C {lab_pin.sym} 800 855 2 0 {name=l101 lab=t050}
N 800 940 800 965 {}
C {lab_pin.sym} 800 965 0 0 {name=l102 lab=t051}
C {sg13g2_pr/rppd.sym} 1050 910 0 0 {name=RU52 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 880 1050 855 {}
C {lab_pin.sym} 1050 855 2 0 {name=l103 lab=t051}
N 1050 940 1050 965 {}
C {lab_pin.sym} 1050 965 0 0 {name=l104 lab=t052}
C {sg13g2_pr/rppd.sym} 1300 910 0 0 {name=RU53 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 880 1300 855 {}
C {lab_pin.sym} 1300 855 2 0 {name=l105 lab=t052}
N 1300 940 1300 965 {}
C {lab_pin.sym} 1300 965 0 0 {name=l106 lab=t053}
C {sg13g2_pr/rppd.sym} 1550 910 0 0 {name=RU54 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 880 1550 855 {}
C {lab_pin.sym} 1550 855 2 0 {name=l107 lab=t053}
N 1550 940 1550 965 {}
C {lab_pin.sym} 1550 965 0 0 {name=l108 lab=t054}
C {sg13g2_pr/rppd.sym} 1800 910 0 0 {name=RU55 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 880 1800 855 {}
C {lab_pin.sym} 1800 855 2 0 {name=l109 lab=t054}
N 1800 940 1800 965 {}
C {lab_pin.sym} 1800 965 0 0 {name=l110 lab=t055}
C {sg13g2_pr/rppd.sym} 2050 910 0 0 {name=RU56 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 880 2050 855 {}
C {lab_pin.sym} 2050 855 2 0 {name=l111 lab=t055}
N 2050 940 2050 965 {}
C {lab_pin.sym} 2050 965 0 0 {name=l112 lab=t056}
C {sg13g2_pr/rppd.sym} 2300 910 0 0 {name=RU57 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 880 2300 855 {}
C {lab_pin.sym} 2300 855 2 0 {name=l113 lab=t056}
N 2300 940 2300 965 {}
C {lab_pin.sym} 2300 965 0 0 {name=l114 lab=t057}
C {sg13g2_pr/rppd.sym} 2550 910 0 0 {name=RU58 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 880 2550 855 {}
C {lab_pin.sym} 2550 855 2 0 {name=l115 lab=t057}
N 2550 940 2550 965 {}
C {lab_pin.sym} 2550 965 0 0 {name=l116 lab=t058}
C {sg13g2_pr/rppd.sym} 2800 910 0 0 {name=RU59 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 880 2800 855 {}
C {lab_pin.sym} 2800 855 2 0 {name=l117 lab=t058}
N 2800 940 2800 965 {}
C {lab_pin.sym} 2800 965 0 0 {name=l118 lab=t059}
C {sg13g2_pr/rppd.sym} 3050 910 0 0 {name=RU60 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 880 3050 855 {}
C {lab_pin.sym} 3050 855 2 0 {name=l119 lab=t059}
N 3050 940 3050 965 {}
C {lab_pin.sym} 3050 965 0 0 {name=l120 lab=t060}
C {sg13g2_pr/rppd.sym} 3300 910 0 0 {name=RU61 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 880 3300 855 {}
C {lab_pin.sym} 3300 855 2 0 {name=l121 lab=t060}
N 3300 940 3300 965 {}
C {lab_pin.sym} 3300 965 0 0 {name=l122 lab=t061}
C {sg13g2_pr/rppd.sym} 3550 910 0 0 {name=RU62 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 880 3550 855 {}
C {lab_pin.sym} 3550 855 2 0 {name=l123 lab=t061}
N 3550 940 3550 965 {}
C {lab_pin.sym} 3550 965 0 0 {name=l124 lab=t062}
C {sg13g2_pr/rppd.sym} 3800 910 0 0 {name=RU63 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 880 3800 855 {}
C {lab_pin.sym} 3800 855 2 0 {name=l125 lab=t062}
N 3800 940 3800 965 {}
C {lab_pin.sym} 3800 965 0 0 {name=l126 lab=t063}
C {sg13g2_pr/rppd.sym} 4050 910 0 0 {name=RU64 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 880 4050 855 {}
C {lab_pin.sym} 4050 855 2 0 {name=l127 lab=t063}
N 4050 940 4050 965 {}
C {lab_pin.sym} 4050 965 0 0 {name=l128 lab=t064}
C {sg13g2_pr/rppd.sym} 300 1130 0 0 {name=RU65 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 1100 300 1075 {}
C {lab_pin.sym} 300 1075 2 0 {name=l129 lab=t064}
N 300 1160 300 1185 {}
C {lab_pin.sym} 300 1185 0 0 {name=l130 lab=t065}
C {sg13g2_pr/rppd.sym} 550 1130 0 0 {name=RU66 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 1100 550 1075 {}
C {lab_pin.sym} 550 1075 2 0 {name=l131 lab=t065}
N 550 1160 550 1185 {}
C {lab_pin.sym} 550 1185 0 0 {name=l132 lab=t066}
C {sg13g2_pr/rppd.sym} 800 1130 0 0 {name=RU67 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 1100 800 1075 {}
C {lab_pin.sym} 800 1075 2 0 {name=l133 lab=t066}
N 800 1160 800 1185 {}
C {lab_pin.sym} 800 1185 0 0 {name=l134 lab=t067}
C {sg13g2_pr/rppd.sym} 1050 1130 0 0 {name=RU68 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 1100 1050 1075 {}
C {lab_pin.sym} 1050 1075 2 0 {name=l135 lab=t067}
N 1050 1160 1050 1185 {}
C {lab_pin.sym} 1050 1185 0 0 {name=l136 lab=t068}
C {sg13g2_pr/rppd.sym} 1300 1130 0 0 {name=RU69 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 1100 1300 1075 {}
C {lab_pin.sym} 1300 1075 2 0 {name=l137 lab=t068}
N 1300 1160 1300 1185 {}
C {lab_pin.sym} 1300 1185 0 0 {name=l138 lab=t069}
C {sg13g2_pr/rppd.sym} 1550 1130 0 0 {name=RU70 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 1100 1550 1075 {}
C {lab_pin.sym} 1550 1075 2 0 {name=l139 lab=t069}
N 1550 1160 1550 1185 {}
C {lab_pin.sym} 1550 1185 0 0 {name=l140 lab=t070}
C {sg13g2_pr/rppd.sym} 1800 1130 0 0 {name=RU71 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 1100 1800 1075 {}
C {lab_pin.sym} 1800 1075 2 0 {name=l141 lab=t070}
N 1800 1160 1800 1185 {}
C {lab_pin.sym} 1800 1185 0 0 {name=l142 lab=t071}
C {sg13g2_pr/rppd.sym} 2050 1130 0 0 {name=RU72 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 1100 2050 1075 {}
C {lab_pin.sym} 2050 1075 2 0 {name=l143 lab=t071}
N 2050 1160 2050 1185 {}
C {lab_pin.sym} 2050 1185 0 0 {name=l144 lab=t072}
C {sg13g2_pr/rppd.sym} 2300 1130 0 0 {name=RU73 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 1100 2300 1075 {}
C {lab_pin.sym} 2300 1075 2 0 {name=l145 lab=t072}
N 2300 1160 2300 1185 {}
C {lab_pin.sym} 2300 1185 0 0 {name=l146 lab=t073}
C {sg13g2_pr/rppd.sym} 2550 1130 0 0 {name=RU74 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 1100 2550 1075 {}
C {lab_pin.sym} 2550 1075 2 0 {name=l147 lab=t073}
N 2550 1160 2550 1185 {}
C {lab_pin.sym} 2550 1185 0 0 {name=l148 lab=t074}
C {sg13g2_pr/rppd.sym} 2800 1130 0 0 {name=RU75 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 1100 2800 1075 {}
C {lab_pin.sym} 2800 1075 2 0 {name=l149 lab=t074}
N 2800 1160 2800 1185 {}
C {lab_pin.sym} 2800 1185 0 0 {name=l150 lab=t075}
C {sg13g2_pr/rppd.sym} 3050 1130 0 0 {name=RU76 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 1100 3050 1075 {}
C {lab_pin.sym} 3050 1075 2 0 {name=l151 lab=t075}
N 3050 1160 3050 1185 {}
C {lab_pin.sym} 3050 1185 0 0 {name=l152 lab=t076}
C {sg13g2_pr/rppd.sym} 3300 1130 0 0 {name=RU77 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 1100 3300 1075 {}
C {lab_pin.sym} 3300 1075 2 0 {name=l153 lab=t076}
N 3300 1160 3300 1185 {}
C {lab_pin.sym} 3300 1185 0 0 {name=l154 lab=t077}
C {sg13g2_pr/rppd.sym} 3550 1130 0 0 {name=RU78 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 1100 3550 1075 {}
C {lab_pin.sym} 3550 1075 2 0 {name=l155 lab=t077}
N 3550 1160 3550 1185 {}
C {lab_pin.sym} 3550 1185 0 0 {name=l156 lab=t078}
C {sg13g2_pr/rppd.sym} 3800 1130 0 0 {name=RU79 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 1100 3800 1075 {}
C {lab_pin.sym} 3800 1075 2 0 {name=l157 lab=t078}
N 3800 1160 3800 1185 {}
C {lab_pin.sym} 3800 1185 0 0 {name=l158 lab=t079}
C {sg13g2_pr/rppd.sym} 4050 1130 0 0 {name=RU80 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 1100 4050 1075 {}
C {lab_pin.sym} 4050 1075 2 0 {name=l159 lab=t079}
N 4050 1160 4050 1185 {}
C {lab_pin.sym} 4050 1185 0 0 {name=l160 lab=t080}
C {sg13g2_pr/rppd.sym} 300 1350 0 0 {name=RU81 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 1320 300 1295 {}
C {lab_pin.sym} 300 1295 2 0 {name=l161 lab=t080}
N 300 1380 300 1405 {}
C {lab_pin.sym} 300 1405 0 0 {name=l162 lab=t081}
C {sg13g2_pr/rppd.sym} 550 1350 0 0 {name=RU82 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 1320 550 1295 {}
C {lab_pin.sym} 550 1295 2 0 {name=l163 lab=t081}
N 550 1380 550 1405 {}
C {lab_pin.sym} 550 1405 0 0 {name=l164 lab=t082}
C {sg13g2_pr/rppd.sym} 800 1350 0 0 {name=RU83 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 1320 800 1295 {}
C {lab_pin.sym} 800 1295 2 0 {name=l165 lab=t082}
N 800 1380 800 1405 {}
C {lab_pin.sym} 800 1405 0 0 {name=l166 lab=t083}
C {sg13g2_pr/rppd.sym} 1050 1350 0 0 {name=RU84 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 1320 1050 1295 {}
C {lab_pin.sym} 1050 1295 2 0 {name=l167 lab=t083}
N 1050 1380 1050 1405 {}
C {lab_pin.sym} 1050 1405 0 0 {name=l168 lab=t084}
C {sg13g2_pr/rppd.sym} 1300 1350 0 0 {name=RU85 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 1320 1300 1295 {}
C {lab_pin.sym} 1300 1295 2 0 {name=l169 lab=t084}
N 1300 1380 1300 1405 {}
C {lab_pin.sym} 1300 1405 0 0 {name=l170 lab=t085}
C {sg13g2_pr/rppd.sym} 1550 1350 0 0 {name=RU86 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 1320 1550 1295 {}
C {lab_pin.sym} 1550 1295 2 0 {name=l171 lab=t085}
N 1550 1380 1550 1405 {}
C {lab_pin.sym} 1550 1405 0 0 {name=l172 lab=t086}
C {sg13g2_pr/rppd.sym} 1800 1350 0 0 {name=RU87 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 1320 1800 1295 {}
C {lab_pin.sym} 1800 1295 2 0 {name=l173 lab=t086}
N 1800 1380 1800 1405 {}
C {lab_pin.sym} 1800 1405 0 0 {name=l174 lab=t087}
C {sg13g2_pr/rppd.sym} 2050 1350 0 0 {name=RU88 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 1320 2050 1295 {}
C {lab_pin.sym} 2050 1295 2 0 {name=l175 lab=t087}
N 2050 1380 2050 1405 {}
C {lab_pin.sym} 2050 1405 0 0 {name=l176 lab=t088}
C {sg13g2_pr/rppd.sym} 2300 1350 0 0 {name=RU89 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 1320 2300 1295 {}
C {lab_pin.sym} 2300 1295 2 0 {name=l177 lab=t088}
N 2300 1380 2300 1405 {}
C {lab_pin.sym} 2300 1405 0 0 {name=l178 lab=t089}
C {sg13g2_pr/rppd.sym} 2550 1350 0 0 {name=RU90 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 1320 2550 1295 {}
C {lab_pin.sym} 2550 1295 2 0 {name=l179 lab=t089}
N 2550 1380 2550 1405 {}
C {lab_pin.sym} 2550 1405 0 0 {name=l180 lab=t090}
C {sg13g2_pr/rppd.sym} 2800 1350 0 0 {name=RU91 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 1320 2800 1295 {}
C {lab_pin.sym} 2800 1295 2 0 {name=l181 lab=t090}
N 2800 1380 2800 1405 {}
C {lab_pin.sym} 2800 1405 0 0 {name=l182 lab=t091}
C {sg13g2_pr/rppd.sym} 3050 1350 0 0 {name=RU92 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 1320 3050 1295 {}
C {lab_pin.sym} 3050 1295 2 0 {name=l183 lab=t091}
N 3050 1380 3050 1405 {}
C {lab_pin.sym} 3050 1405 0 0 {name=l184 lab=t092}
C {sg13g2_pr/rppd.sym} 3300 1350 0 0 {name=RU93 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 1320 3300 1295 {}
C {lab_pin.sym} 3300 1295 2 0 {name=l185 lab=t092}
N 3300 1380 3300 1405 {}
C {lab_pin.sym} 3300 1405 0 0 {name=l186 lab=t093}
C {sg13g2_pr/rppd.sym} 3550 1350 0 0 {name=RU94 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 1320 3550 1295 {}
C {lab_pin.sym} 3550 1295 2 0 {name=l187 lab=t093}
N 3550 1380 3550 1405 {}
C {lab_pin.sym} 3550 1405 0 0 {name=l188 lab=t094}
C {sg13g2_pr/rppd.sym} 3800 1350 0 0 {name=RU95 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 1320 3800 1295 {}
C {lab_pin.sym} 3800 1295 2 0 {name=l189 lab=t094}
N 3800 1380 3800 1405 {}
C {lab_pin.sym} 3800 1405 0 0 {name=l190 lab=t095}
C {sg13g2_pr/rppd.sym} 4050 1350 0 0 {name=RU96 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 1320 4050 1295 {}
C {lab_pin.sym} 4050 1295 2 0 {name=l191 lab=t095}
N 4050 1380 4050 1405 {}
C {lab_pin.sym} 4050 1405 0 0 {name=l192 lab=t096}
C {sg13g2_pr/rppd.sym} 300 1570 0 0 {name=RU97 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 1540 300 1515 {}
C {lab_pin.sym} 300 1515 2 0 {name=l193 lab=t096}
N 300 1600 300 1625 {}
C {lab_pin.sym} 300 1625 0 0 {name=l194 lab=t097}
C {sg13g2_pr/rppd.sym} 550 1570 0 0 {name=RU98 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 1540 550 1515 {}
C {lab_pin.sym} 550 1515 2 0 {name=l195 lab=t097}
N 550 1600 550 1625 {}
C {lab_pin.sym} 550 1625 0 0 {name=l196 lab=t098}
C {sg13g2_pr/rppd.sym} 800 1570 0 0 {name=RU99 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 1540 800 1515 {}
C {lab_pin.sym} 800 1515 2 0 {name=l197 lab=t098}
N 800 1600 800 1625 {}
C {lab_pin.sym} 800 1625 0 0 {name=l198 lab=t099}
C {sg13g2_pr/rppd.sym} 1050 1570 0 0 {name=RU100 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 1540 1050 1515 {}
C {lab_pin.sym} 1050 1515 2 0 {name=l199 lab=t099}
N 1050 1600 1050 1625 {}
C {lab_pin.sym} 1050 1625 0 0 {name=l200 lab=t100}
C {sg13g2_pr/rppd.sym} 1300 1570 0 0 {name=RU101 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 1540 1300 1515 {}
C {lab_pin.sym} 1300 1515 2 0 {name=l201 lab=t100}
N 1300 1600 1300 1625 {}
C {lab_pin.sym} 1300 1625 0 0 {name=l202 lab=t101}
C {sg13g2_pr/rppd.sym} 1550 1570 0 0 {name=RU102 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 1540 1550 1515 {}
C {lab_pin.sym} 1550 1515 2 0 {name=l203 lab=t101}
N 1550 1600 1550 1625 {}
C {lab_pin.sym} 1550 1625 0 0 {name=l204 lab=t102}
C {sg13g2_pr/rppd.sym} 1800 1570 0 0 {name=RU103 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 1540 1800 1515 {}
C {lab_pin.sym} 1800 1515 2 0 {name=l205 lab=t102}
N 1800 1600 1800 1625 {}
C {lab_pin.sym} 1800 1625 0 0 {name=l206 lab=t103}
C {sg13g2_pr/rppd.sym} 2050 1570 0 0 {name=RU104 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 1540 2050 1515 {}
C {lab_pin.sym} 2050 1515 2 0 {name=l207 lab=t103}
N 2050 1600 2050 1625 {}
C {lab_pin.sym} 2050 1625 0 0 {name=l208 lab=t104}
C {sg13g2_pr/rppd.sym} 2300 1570 0 0 {name=RU105 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 1540 2300 1515 {}
C {lab_pin.sym} 2300 1515 2 0 {name=l209 lab=t104}
N 2300 1600 2300 1625 {}
C {lab_pin.sym} 2300 1625 0 0 {name=l210 lab=t105}
C {sg13g2_pr/rppd.sym} 2550 1570 0 0 {name=RU106 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 1540 2550 1515 {}
C {lab_pin.sym} 2550 1515 2 0 {name=l211 lab=t105}
N 2550 1600 2550 1625 {}
C {lab_pin.sym} 2550 1625 0 0 {name=l212 lab=t106}
C {sg13g2_pr/rppd.sym} 2800 1570 0 0 {name=RU107 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 1540 2800 1515 {}
C {lab_pin.sym} 2800 1515 2 0 {name=l213 lab=t106}
N 2800 1600 2800 1625 {}
C {lab_pin.sym} 2800 1625 0 0 {name=l214 lab=t107}
C {sg13g2_pr/rppd.sym} 3050 1570 0 0 {name=RU108 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 1540 3050 1515 {}
C {lab_pin.sym} 3050 1515 2 0 {name=l215 lab=t107}
N 3050 1600 3050 1625 {}
C {lab_pin.sym} 3050 1625 0 0 {name=l216 lab=t108}
C {sg13g2_pr/rppd.sym} 3300 1570 0 0 {name=RU109 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 1540 3300 1515 {}
C {lab_pin.sym} 3300 1515 2 0 {name=l217 lab=t108}
N 3300 1600 3300 1625 {}
C {lab_pin.sym} 3300 1625 0 0 {name=l218 lab=t109}
C {sg13g2_pr/rppd.sym} 3550 1570 0 0 {name=RU110 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 1540 3550 1515 {}
C {lab_pin.sym} 3550 1515 2 0 {name=l219 lab=t109}
N 3550 1600 3550 1625 {}
C {lab_pin.sym} 3550 1625 0 0 {name=l220 lab=t110}
C {sg13g2_pr/rppd.sym} 3800 1570 0 0 {name=RU111 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 1540 3800 1515 {}
C {lab_pin.sym} 3800 1515 2 0 {name=l221 lab=t110}
N 3800 1600 3800 1625 {}
C {lab_pin.sym} 3800 1625 0 0 {name=l222 lab=t111}
C {sg13g2_pr/rppd.sym} 4050 1570 0 0 {name=RU112 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 1540 4050 1515 {}
C {lab_pin.sym} 4050 1515 2 0 {name=l223 lab=t111}
N 4050 1600 4050 1625 {}
C {lab_pin.sym} 4050 1625 0 0 {name=l224 lab=t112}
C {sg13g2_pr/rppd.sym} 300 1790 0 0 {name=RU113 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 1760 300 1735 {}
C {lab_pin.sym} 300 1735 2 0 {name=l225 lab=t112}
N 300 1820 300 1845 {}
C {lab_pin.sym} 300 1845 0 0 {name=l226 lab=t113}
C {sg13g2_pr/rppd.sym} 550 1790 0 0 {name=RU114 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 1760 550 1735 {}
C {lab_pin.sym} 550 1735 2 0 {name=l227 lab=t113}
N 550 1820 550 1845 {}
C {lab_pin.sym} 550 1845 0 0 {name=l228 lab=t114}
C {sg13g2_pr/rppd.sym} 800 1790 0 0 {name=RU115 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 1760 800 1735 {}
C {lab_pin.sym} 800 1735 2 0 {name=l229 lab=t114}
N 800 1820 800 1845 {}
C {lab_pin.sym} 800 1845 0 0 {name=l230 lab=t115}
C {sg13g2_pr/rppd.sym} 1050 1790 0 0 {name=RU116 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 1760 1050 1735 {}
C {lab_pin.sym} 1050 1735 2 0 {name=l231 lab=t115}
N 1050 1820 1050 1845 {}
C {lab_pin.sym} 1050 1845 0 0 {name=l232 lab=t116}
C {sg13g2_pr/rppd.sym} 1300 1790 0 0 {name=RU117 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 1760 1300 1735 {}
C {lab_pin.sym} 1300 1735 2 0 {name=l233 lab=t116}
N 1300 1820 1300 1845 {}
C {lab_pin.sym} 1300 1845 0 0 {name=l234 lab=t117}
C {sg13g2_pr/rppd.sym} 1550 1790 0 0 {name=RU118 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 1760 1550 1735 {}
C {lab_pin.sym} 1550 1735 2 0 {name=l235 lab=t117}
N 1550 1820 1550 1845 {}
C {lab_pin.sym} 1550 1845 0 0 {name=l236 lab=t118}
C {sg13g2_pr/rppd.sym} 1800 1790 0 0 {name=RU119 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 1760 1800 1735 {}
C {lab_pin.sym} 1800 1735 2 0 {name=l237 lab=t118}
N 1800 1820 1800 1845 {}
C {lab_pin.sym} 1800 1845 0 0 {name=l238 lab=t119}
C {sg13g2_pr/rppd.sym} 2050 1790 0 0 {name=RU120 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 1760 2050 1735 {}
C {lab_pin.sym} 2050 1735 2 0 {name=l239 lab=t119}
N 2050 1820 2050 1845 {}
C {lab_pin.sym} 2050 1845 0 0 {name=l240 lab=t120}
C {sg13g2_pr/rppd.sym} 2300 1790 0 0 {name=RU121 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 1760 2300 1735 {}
C {lab_pin.sym} 2300 1735 2 0 {name=l241 lab=t120}
N 2300 1820 2300 1845 {}
C {lab_pin.sym} 2300 1845 0 0 {name=l242 lab=t121}
C {sg13g2_pr/rppd.sym} 2550 1790 0 0 {name=RU122 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 1760 2550 1735 {}
C {lab_pin.sym} 2550 1735 2 0 {name=l243 lab=t121}
N 2550 1820 2550 1845 {}
C {lab_pin.sym} 2550 1845 0 0 {name=l244 lab=t122}
C {sg13g2_pr/rppd.sym} 2800 1790 0 0 {name=RU123 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 1760 2800 1735 {}
C {lab_pin.sym} 2800 1735 2 0 {name=l245 lab=t122}
N 2800 1820 2800 1845 {}
C {lab_pin.sym} 2800 1845 0 0 {name=l246 lab=t123}
C {sg13g2_pr/rppd.sym} 3050 1790 0 0 {name=RU124 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 1760 3050 1735 {}
C {lab_pin.sym} 3050 1735 2 0 {name=l247 lab=t123}
N 3050 1820 3050 1845 {}
C {lab_pin.sym} 3050 1845 0 0 {name=l248 lab=t124}
C {sg13g2_pr/rppd.sym} 3300 1790 0 0 {name=RU125 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 1760 3300 1735 {}
C {lab_pin.sym} 3300 1735 2 0 {name=l249 lab=t124}
N 3300 1820 3300 1845 {}
C {lab_pin.sym} 3300 1845 0 0 {name=l250 lab=t125}
C {sg13g2_pr/rppd.sym} 3550 1790 0 0 {name=RU126 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 1760 3550 1735 {}
C {lab_pin.sym} 3550 1735 2 0 {name=l251 lab=t125}
N 3550 1820 3550 1845 {}
C {lab_pin.sym} 3550 1845 0 0 {name=l252 lab=t126}
C {sg13g2_pr/rppd.sym} 3800 1790 0 0 {name=RU127 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 1760 3800 1735 {}
C {lab_pin.sym} 3800 1735 2 0 {name=l253 lab=t126}
N 3800 1820 3800 1845 {}
C {lab_pin.sym} 3800 1845 0 0 {name=l254 lab=t127}
C {sg13g2_pr/rppd.sym} 4050 1790 0 0 {name=RU128 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 1760 4050 1735 {}
C {lab_pin.sym} 4050 1735 2 0 {name=l255 lab=t127}
N 4050 1820 4050 1845 {}
C {lab_pin.sym} 4050 1845 0 0 {name=l256 lab=t128}
C {sg13g2_pr/rppd.sym} 300 2010 0 0 {name=RU129 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 1980 300 1955 {}
C {lab_pin.sym} 300 1955 2 0 {name=l257 lab=t128}
N 300 2040 300 2065 {}
C {lab_pin.sym} 300 2065 0 0 {name=l258 lab=t129}
C {sg13g2_pr/rppd.sym} 550 2010 0 0 {name=RU130 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 1980 550 1955 {}
C {lab_pin.sym} 550 1955 2 0 {name=l259 lab=t129}
N 550 2040 550 2065 {}
C {lab_pin.sym} 550 2065 0 0 {name=l260 lab=t130}
C {sg13g2_pr/rppd.sym} 800 2010 0 0 {name=RU131 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 1980 800 1955 {}
C {lab_pin.sym} 800 1955 2 0 {name=l261 lab=t130}
N 800 2040 800 2065 {}
C {lab_pin.sym} 800 2065 0 0 {name=l262 lab=t131}
C {sg13g2_pr/rppd.sym} 1050 2010 0 0 {name=RU132 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 1980 1050 1955 {}
C {lab_pin.sym} 1050 1955 2 0 {name=l263 lab=t131}
N 1050 2040 1050 2065 {}
C {lab_pin.sym} 1050 2065 0 0 {name=l264 lab=t132}
C {sg13g2_pr/rppd.sym} 1300 2010 0 0 {name=RU133 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 1980 1300 1955 {}
C {lab_pin.sym} 1300 1955 2 0 {name=l265 lab=t132}
N 1300 2040 1300 2065 {}
C {lab_pin.sym} 1300 2065 0 0 {name=l266 lab=t133}
C {sg13g2_pr/rppd.sym} 1550 2010 0 0 {name=RU134 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 1980 1550 1955 {}
C {lab_pin.sym} 1550 1955 2 0 {name=l267 lab=t133}
N 1550 2040 1550 2065 {}
C {lab_pin.sym} 1550 2065 0 0 {name=l268 lab=t134}
C {sg13g2_pr/rppd.sym} 1800 2010 0 0 {name=RU135 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 1980 1800 1955 {}
C {lab_pin.sym} 1800 1955 2 0 {name=l269 lab=t134}
N 1800 2040 1800 2065 {}
C {lab_pin.sym} 1800 2065 0 0 {name=l270 lab=t135}
C {sg13g2_pr/rppd.sym} 2050 2010 0 0 {name=RU136 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 1980 2050 1955 {}
C {lab_pin.sym} 2050 1955 2 0 {name=l271 lab=t135}
N 2050 2040 2050 2065 {}
C {lab_pin.sym} 2050 2065 0 0 {name=l272 lab=t136}
C {sg13g2_pr/rppd.sym} 2300 2010 0 0 {name=RU137 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 1980 2300 1955 {}
C {lab_pin.sym} 2300 1955 2 0 {name=l273 lab=t136}
N 2300 2040 2300 2065 {}
C {lab_pin.sym} 2300 2065 0 0 {name=l274 lab=t137}
C {sg13g2_pr/rppd.sym} 2550 2010 0 0 {name=RU138 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 1980 2550 1955 {}
C {lab_pin.sym} 2550 1955 2 0 {name=l275 lab=t137}
N 2550 2040 2550 2065 {}
C {lab_pin.sym} 2550 2065 0 0 {name=l276 lab=t138}
C {sg13g2_pr/rppd.sym} 2800 2010 0 0 {name=RU139 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 1980 2800 1955 {}
C {lab_pin.sym} 2800 1955 2 0 {name=l277 lab=t138}
N 2800 2040 2800 2065 {}
C {lab_pin.sym} 2800 2065 0 0 {name=l278 lab=t139}
C {sg13g2_pr/rppd.sym} 3050 2010 0 0 {name=RU140 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 1980 3050 1955 {}
C {lab_pin.sym} 3050 1955 2 0 {name=l279 lab=t139}
N 3050 2040 3050 2065 {}
C {lab_pin.sym} 3050 2065 0 0 {name=l280 lab=t140}
C {sg13g2_pr/rppd.sym} 3300 2010 0 0 {name=RU141 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 1980 3300 1955 {}
C {lab_pin.sym} 3300 1955 2 0 {name=l281 lab=t140}
N 3300 2040 3300 2065 {}
C {lab_pin.sym} 3300 2065 0 0 {name=l282 lab=t141}
C {sg13g2_pr/rppd.sym} 3550 2010 0 0 {name=RU142 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 1980 3550 1955 {}
C {lab_pin.sym} 3550 1955 2 0 {name=l283 lab=t141}
N 3550 2040 3550 2065 {}
C {lab_pin.sym} 3550 2065 0 0 {name=l284 lab=t142}
C {sg13g2_pr/rppd.sym} 3800 2010 0 0 {name=RU143 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 1980 3800 1955 {}
C {lab_pin.sym} 3800 1955 2 0 {name=l285 lab=t142}
N 3800 2040 3800 2065 {}
C {lab_pin.sym} 3800 2065 0 0 {name=l286 lab=t143}
C {sg13g2_pr/rppd.sym} 4050 2010 0 0 {name=RU144 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 1980 4050 1955 {}
C {lab_pin.sym} 4050 1955 2 0 {name=l287 lab=t143}
N 4050 2040 4050 2065 {}
C {lab_pin.sym} 4050 2065 0 0 {name=l288 lab=t144}
C {sg13g2_pr/rppd.sym} 300 2230 0 0 {name=RU145 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 2200 300 2175 {}
C {lab_pin.sym} 300 2175 2 0 {name=l289 lab=t144}
N 300 2260 300 2285 {}
C {lab_pin.sym} 300 2285 0 0 {name=l290 lab=t145}
C {sg13g2_pr/rppd.sym} 550 2230 0 0 {name=RU146 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 2200 550 2175 {}
C {lab_pin.sym} 550 2175 2 0 {name=l291 lab=t145}
N 550 2260 550 2285 {}
C {lab_pin.sym} 550 2285 0 0 {name=l292 lab=t146}
C {sg13g2_pr/rppd.sym} 800 2230 0 0 {name=RU147 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 2200 800 2175 {}
C {lab_pin.sym} 800 2175 2 0 {name=l293 lab=t146}
N 800 2260 800 2285 {}
C {lab_pin.sym} 800 2285 0 0 {name=l294 lab=t147}
C {sg13g2_pr/rppd.sym} 1050 2230 0 0 {name=RU148 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 2200 1050 2175 {}
C {lab_pin.sym} 1050 2175 2 0 {name=l295 lab=t147}
N 1050 2260 1050 2285 {}
C {lab_pin.sym} 1050 2285 0 0 {name=l296 lab=t148}
C {sg13g2_pr/rppd.sym} 1300 2230 0 0 {name=RU149 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 2200 1300 2175 {}
C {lab_pin.sym} 1300 2175 2 0 {name=l297 lab=t148}
N 1300 2260 1300 2285 {}
C {lab_pin.sym} 1300 2285 0 0 {name=l298 lab=t149}
C {sg13g2_pr/rppd.sym} 1550 2230 0 0 {name=RU150 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 2200 1550 2175 {}
C {lab_pin.sym} 1550 2175 2 0 {name=l299 lab=t149}
N 1550 2260 1550 2285 {}
C {lab_pin.sym} 1550 2285 0 0 {name=l300 lab=t150}
C {sg13g2_pr/rppd.sym} 1800 2230 0 0 {name=RU151 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 2200 1800 2175 {}
C {lab_pin.sym} 1800 2175 2 0 {name=l301 lab=t150}
N 1800 2260 1800 2285 {}
C {lab_pin.sym} 1800 2285 0 0 {name=l302 lab=t151}
C {sg13g2_pr/rppd.sym} 2050 2230 0 0 {name=RU152 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 2200 2050 2175 {}
C {lab_pin.sym} 2050 2175 2 0 {name=l303 lab=t151}
N 2050 2260 2050 2285 {}
C {lab_pin.sym} 2050 2285 0 0 {name=l304 lab=t152}
C {sg13g2_pr/rppd.sym} 2300 2230 0 0 {name=RU153 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 2200 2300 2175 {}
C {lab_pin.sym} 2300 2175 2 0 {name=l305 lab=t152}
N 2300 2260 2300 2285 {}
C {lab_pin.sym} 2300 2285 0 0 {name=l306 lab=t153}
C {sg13g2_pr/rppd.sym} 2550 2230 0 0 {name=RU154 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 2200 2550 2175 {}
C {lab_pin.sym} 2550 2175 2 0 {name=l307 lab=t153}
N 2550 2260 2550 2285 {}
C {lab_pin.sym} 2550 2285 0 0 {name=l308 lab=t154}
C {sg13g2_pr/rppd.sym} 2800 2230 0 0 {name=RU155 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 2200 2800 2175 {}
C {lab_pin.sym} 2800 2175 2 0 {name=l309 lab=t154}
N 2800 2260 2800 2285 {}
C {lab_pin.sym} 2800 2285 0 0 {name=l310 lab=t155}
C {sg13g2_pr/rppd.sym} 3050 2230 0 0 {name=RU156 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 2200 3050 2175 {}
C {lab_pin.sym} 3050 2175 2 0 {name=l311 lab=t155}
N 3050 2260 3050 2285 {}
C {lab_pin.sym} 3050 2285 0 0 {name=l312 lab=t156}
C {sg13g2_pr/rppd.sym} 3300 2230 0 0 {name=RU157 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 2200 3300 2175 {}
C {lab_pin.sym} 3300 2175 2 0 {name=l313 lab=t156}
N 3300 2260 3300 2285 {}
C {lab_pin.sym} 3300 2285 0 0 {name=l314 lab=t157}
C {sg13g2_pr/rppd.sym} 3550 2230 0 0 {name=RU158 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 2200 3550 2175 {}
C {lab_pin.sym} 3550 2175 2 0 {name=l315 lab=t157}
N 3550 2260 3550 2285 {}
C {lab_pin.sym} 3550 2285 0 0 {name=l316 lab=t158}
C {sg13g2_pr/rppd.sym} 3800 2230 0 0 {name=RU159 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 2200 3800 2175 {}
C {lab_pin.sym} 3800 2175 2 0 {name=l317 lab=t158}
N 3800 2260 3800 2285 {}
C {lab_pin.sym} 3800 2285 0 0 {name=l318 lab=t159}
C {sg13g2_pr/rppd.sym} 4050 2230 0 0 {name=RU160 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 2200 4050 2175 {}
C {lab_pin.sym} 4050 2175 2 0 {name=l319 lab=t159}
N 4050 2260 4050 2285 {}
C {lab_pin.sym} 4050 2285 0 0 {name=l320 lab=t160}
C {sg13g2_pr/rppd.sym} 300 2450 0 0 {name=RU161 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 2420 300 2395 {}
C {lab_pin.sym} 300 2395 2 0 {name=l321 lab=t160}
N 300 2480 300 2505 {}
C {lab_pin.sym} 300 2505 0 0 {name=l322 lab=t161}
C {sg13g2_pr/rppd.sym} 550 2450 0 0 {name=RU162 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 2420 550 2395 {}
C {lab_pin.sym} 550 2395 2 0 {name=l323 lab=t161}
N 550 2480 550 2505 {}
C {lab_pin.sym} 550 2505 0 0 {name=l324 lab=t162}
C {sg13g2_pr/rppd.sym} 800 2450 0 0 {name=RU163 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 2420 800 2395 {}
C {lab_pin.sym} 800 2395 2 0 {name=l325 lab=t162}
N 800 2480 800 2505 {}
C {lab_pin.sym} 800 2505 0 0 {name=l326 lab=t163}
C {sg13g2_pr/rppd.sym} 1050 2450 0 0 {name=RU164 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 2420 1050 2395 {}
C {lab_pin.sym} 1050 2395 2 0 {name=l327 lab=t163}
N 1050 2480 1050 2505 {}
C {lab_pin.sym} 1050 2505 0 0 {name=l328 lab=t164}
C {sg13g2_pr/rppd.sym} 1300 2450 0 0 {name=RU165 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 2420 1300 2395 {}
C {lab_pin.sym} 1300 2395 2 0 {name=l329 lab=t164}
N 1300 2480 1300 2505 {}
C {lab_pin.sym} 1300 2505 0 0 {name=l330 lab=t165}
C {sg13g2_pr/rppd.sym} 1550 2450 0 0 {name=RU166 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 2420 1550 2395 {}
C {lab_pin.sym} 1550 2395 2 0 {name=l331 lab=t165}
N 1550 2480 1550 2505 {}
C {lab_pin.sym} 1550 2505 0 0 {name=l332 lab=t166}
C {sg13g2_pr/rppd.sym} 1800 2450 0 0 {name=RU167 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 2420 1800 2395 {}
C {lab_pin.sym} 1800 2395 2 0 {name=l333 lab=t166}
N 1800 2480 1800 2505 {}
C {lab_pin.sym} 1800 2505 0 0 {name=l334 lab=t167}
C {sg13g2_pr/rppd.sym} 2050 2450 0 0 {name=RU168 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 2420 2050 2395 {}
C {lab_pin.sym} 2050 2395 2 0 {name=l335 lab=t167}
N 2050 2480 2050 2505 {}
C {lab_pin.sym} 2050 2505 0 0 {name=l336 lab=t168}
C {sg13g2_pr/rppd.sym} 2300 2450 0 0 {name=RU169 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 2420 2300 2395 {}
C {lab_pin.sym} 2300 2395 2 0 {name=l337 lab=t168}
N 2300 2480 2300 2505 {}
C {lab_pin.sym} 2300 2505 0 0 {name=l338 lab=t169}
C {sg13g2_pr/rppd.sym} 2550 2450 0 0 {name=RU170 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 2420 2550 2395 {}
C {lab_pin.sym} 2550 2395 2 0 {name=l339 lab=t169}
N 2550 2480 2550 2505 {}
C {lab_pin.sym} 2550 2505 0 0 {name=l340 lab=t170}
C {sg13g2_pr/rppd.sym} 2800 2450 0 0 {name=RU171 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 2420 2800 2395 {}
C {lab_pin.sym} 2800 2395 2 0 {name=l341 lab=t170}
N 2800 2480 2800 2505 {}
C {lab_pin.sym} 2800 2505 0 0 {name=l342 lab=t171}
C {sg13g2_pr/rppd.sym} 3050 2450 0 0 {name=RU172 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 2420 3050 2395 {}
C {lab_pin.sym} 3050 2395 2 0 {name=l343 lab=t171}
N 3050 2480 3050 2505 {}
C {lab_pin.sym} 3050 2505 0 0 {name=l344 lab=t172}
C {sg13g2_pr/rppd.sym} 3300 2450 0 0 {name=RU173 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 2420 3300 2395 {}
C {lab_pin.sym} 3300 2395 2 0 {name=l345 lab=t172}
N 3300 2480 3300 2505 {}
C {lab_pin.sym} 3300 2505 0 0 {name=l346 lab=t173}
C {sg13g2_pr/rppd.sym} 3550 2450 0 0 {name=RU174 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 2420 3550 2395 {}
C {lab_pin.sym} 3550 2395 2 0 {name=l347 lab=t173}
N 3550 2480 3550 2505 {}
C {lab_pin.sym} 3550 2505 0 0 {name=l348 lab=t174}
C {sg13g2_pr/rppd.sym} 3800 2450 0 0 {name=RU175 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 2420 3800 2395 {}
C {lab_pin.sym} 3800 2395 2 0 {name=l349 lab=t174}
N 3800 2480 3800 2505 {}
C {lab_pin.sym} 3800 2505 0 0 {name=l350 lab=t175}
C {sg13g2_pr/rppd.sym} 4050 2450 0 0 {name=RU176 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 2420 4050 2395 {}
C {lab_pin.sym} 4050 2395 2 0 {name=l351 lab=t175}
N 4050 2480 4050 2505 {}
C {lab_pin.sym} 4050 2505 0 0 {name=l352 lab=t176}
C {sg13g2_pr/rppd.sym} 300 2670 0 0 {name=RU177 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 2640 300 2615 {}
C {lab_pin.sym} 300 2615 2 0 {name=l353 lab=t176}
N 300 2700 300 2725 {}
C {lab_pin.sym} 300 2725 0 0 {name=l354 lab=t177}
C {sg13g2_pr/rppd.sym} 550 2670 0 0 {name=RU178 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 2640 550 2615 {}
C {lab_pin.sym} 550 2615 2 0 {name=l355 lab=t177}
N 550 2700 550 2725 {}
C {lab_pin.sym} 550 2725 0 0 {name=l356 lab=t178}
C {sg13g2_pr/rppd.sym} 800 2670 0 0 {name=RU179 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 2640 800 2615 {}
C {lab_pin.sym} 800 2615 2 0 {name=l357 lab=t178}
N 800 2700 800 2725 {}
C {lab_pin.sym} 800 2725 0 0 {name=l358 lab=t179}
C {sg13g2_pr/rppd.sym} 1050 2670 0 0 {name=RU180 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 2640 1050 2615 {}
C {lab_pin.sym} 1050 2615 2 0 {name=l359 lab=t179}
N 1050 2700 1050 2725 {}
C {lab_pin.sym} 1050 2725 0 0 {name=l360 lab=t180}
C {sg13g2_pr/rppd.sym} 1300 2670 0 0 {name=RU181 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 2640 1300 2615 {}
C {lab_pin.sym} 1300 2615 2 0 {name=l361 lab=t180}
N 1300 2700 1300 2725 {}
C {lab_pin.sym} 1300 2725 0 0 {name=l362 lab=t181}
C {sg13g2_pr/rppd.sym} 1550 2670 0 0 {name=RU182 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 2640 1550 2615 {}
C {lab_pin.sym} 1550 2615 2 0 {name=l363 lab=t181}
N 1550 2700 1550 2725 {}
C {lab_pin.sym} 1550 2725 0 0 {name=l364 lab=t182}
C {sg13g2_pr/rppd.sym} 1800 2670 0 0 {name=RU183 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 2640 1800 2615 {}
C {lab_pin.sym} 1800 2615 2 0 {name=l365 lab=t182}
N 1800 2700 1800 2725 {}
C {lab_pin.sym} 1800 2725 0 0 {name=l366 lab=t183}
C {sg13g2_pr/rppd.sym} 2050 2670 0 0 {name=RU184 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 2640 2050 2615 {}
C {lab_pin.sym} 2050 2615 2 0 {name=l367 lab=t183}
N 2050 2700 2050 2725 {}
C {lab_pin.sym} 2050 2725 0 0 {name=l368 lab=t184}
C {sg13g2_pr/rppd.sym} 2300 2670 0 0 {name=RU185 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 2640 2300 2615 {}
C {lab_pin.sym} 2300 2615 2 0 {name=l369 lab=t184}
N 2300 2700 2300 2725 {}
C {lab_pin.sym} 2300 2725 0 0 {name=l370 lab=t185}
C {sg13g2_pr/rppd.sym} 2550 2670 0 0 {name=RU186 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 2640 2550 2615 {}
C {lab_pin.sym} 2550 2615 2 0 {name=l371 lab=t185}
N 2550 2700 2550 2725 {}
C {lab_pin.sym} 2550 2725 0 0 {name=l372 lab=t186}
C {sg13g2_pr/rppd.sym} 2800 2670 0 0 {name=RU187 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 2640 2800 2615 {}
C {lab_pin.sym} 2800 2615 2 0 {name=l373 lab=t186}
N 2800 2700 2800 2725 {}
C {lab_pin.sym} 2800 2725 0 0 {name=l374 lab=t187}
C {sg13g2_pr/rppd.sym} 3050 2670 0 0 {name=RU188 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 2640 3050 2615 {}
C {lab_pin.sym} 3050 2615 2 0 {name=l375 lab=t187}
N 3050 2700 3050 2725 {}
C {lab_pin.sym} 3050 2725 0 0 {name=l376 lab=t188}
C {sg13g2_pr/rppd.sym} 3300 2670 0 0 {name=RU189 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 2640 3300 2615 {}
C {lab_pin.sym} 3300 2615 2 0 {name=l377 lab=t188}
N 3300 2700 3300 2725 {}
C {lab_pin.sym} 3300 2725 0 0 {name=l378 lab=t189}
C {sg13g2_pr/rppd.sym} 3550 2670 0 0 {name=RU190 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 2640 3550 2615 {}
C {lab_pin.sym} 3550 2615 2 0 {name=l379 lab=t189}
N 3550 2700 3550 2725 {}
C {lab_pin.sym} 3550 2725 0 0 {name=l380 lab=t190}
C {sg13g2_pr/rppd.sym} 3800 2670 0 0 {name=RU191 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 2640 3800 2615 {}
C {lab_pin.sym} 3800 2615 2 0 {name=l381 lab=t190}
N 3800 2700 3800 2725 {}
C {lab_pin.sym} 3800 2725 0 0 {name=l382 lab=t191}
C {sg13g2_pr/rppd.sym} 4050 2670 0 0 {name=RU192 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 2640 4050 2615 {}
C {lab_pin.sym} 4050 2615 2 0 {name=l383 lab=t191}
N 4050 2700 4050 2725 {}
C {lab_pin.sym} 4050 2725 0 0 {name=l384 lab=t192}
C {sg13g2_pr/rppd.sym} 300 2890 0 0 {name=RU193 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 2860 300 2835 {}
C {lab_pin.sym} 300 2835 2 0 {name=l385 lab=t192}
N 300 2920 300 2945 {}
C {lab_pin.sym} 300 2945 0 0 {name=l386 lab=t193}
C {sg13g2_pr/rppd.sym} 550 2890 0 0 {name=RU194 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 2860 550 2835 {}
C {lab_pin.sym} 550 2835 2 0 {name=l387 lab=t193}
N 550 2920 550 2945 {}
C {lab_pin.sym} 550 2945 0 0 {name=l388 lab=t194}
C {sg13g2_pr/rppd.sym} 800 2890 0 0 {name=RU195 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 2860 800 2835 {}
C {lab_pin.sym} 800 2835 2 0 {name=l389 lab=t194}
N 800 2920 800 2945 {}
C {lab_pin.sym} 800 2945 0 0 {name=l390 lab=t195}
C {sg13g2_pr/rppd.sym} 1050 2890 0 0 {name=RU196 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 2860 1050 2835 {}
C {lab_pin.sym} 1050 2835 2 0 {name=l391 lab=t195}
N 1050 2920 1050 2945 {}
C {lab_pin.sym} 1050 2945 0 0 {name=l392 lab=t196}
C {sg13g2_pr/rppd.sym} 1300 2890 0 0 {name=RU197 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 2860 1300 2835 {}
C {lab_pin.sym} 1300 2835 2 0 {name=l393 lab=t196}
N 1300 2920 1300 2945 {}
C {lab_pin.sym} 1300 2945 0 0 {name=l394 lab=t197}
C {sg13g2_pr/rppd.sym} 1550 2890 0 0 {name=RU198 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 2860 1550 2835 {}
C {lab_pin.sym} 1550 2835 2 0 {name=l395 lab=t197}
N 1550 2920 1550 2945 {}
C {lab_pin.sym} 1550 2945 0 0 {name=l396 lab=t198}
C {sg13g2_pr/rppd.sym} 1800 2890 0 0 {name=RU199 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 2860 1800 2835 {}
C {lab_pin.sym} 1800 2835 2 0 {name=l397 lab=t198}
N 1800 2920 1800 2945 {}
C {lab_pin.sym} 1800 2945 0 0 {name=l398 lab=t199}
C {sg13g2_pr/rppd.sym} 2050 2890 0 0 {name=RU200 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 2860 2050 2835 {}
C {lab_pin.sym} 2050 2835 2 0 {name=l399 lab=t199}
N 2050 2920 2050 2945 {}
C {lab_pin.sym} 2050 2945 0 0 {name=l400 lab=t200}
C {sg13g2_pr/rppd.sym} 2300 2890 0 0 {name=RU201 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 2860 2300 2835 {}
C {lab_pin.sym} 2300 2835 2 0 {name=l401 lab=t200}
N 2300 2920 2300 2945 {}
C {lab_pin.sym} 2300 2945 0 0 {name=l402 lab=t201}
C {sg13g2_pr/rppd.sym} 2550 2890 0 0 {name=RU202 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 2860 2550 2835 {}
C {lab_pin.sym} 2550 2835 2 0 {name=l403 lab=t201}
N 2550 2920 2550 2945 {}
C {lab_pin.sym} 2550 2945 0 0 {name=l404 lab=t202}
C {sg13g2_pr/rppd.sym} 2800 2890 0 0 {name=RU203 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 2860 2800 2835 {}
C {lab_pin.sym} 2800 2835 2 0 {name=l405 lab=t202}
N 2800 2920 2800 2945 {}
C {lab_pin.sym} 2800 2945 0 0 {name=l406 lab=t203}
C {sg13g2_pr/rppd.sym} 3050 2890 0 0 {name=RU204 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 2860 3050 2835 {}
C {lab_pin.sym} 3050 2835 2 0 {name=l407 lab=t203}
N 3050 2920 3050 2945 {}
C {lab_pin.sym} 3050 2945 0 0 {name=l408 lab=t204}
C {sg13g2_pr/rppd.sym} 3300 2890 0 0 {name=RU205 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 2860 3300 2835 {}
C {lab_pin.sym} 3300 2835 2 0 {name=l409 lab=t204}
N 3300 2920 3300 2945 {}
C {lab_pin.sym} 3300 2945 0 0 {name=l410 lab=t205}
C {sg13g2_pr/rppd.sym} 3550 2890 0 0 {name=RU206 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 2860 3550 2835 {}
C {lab_pin.sym} 3550 2835 2 0 {name=l411 lab=t205}
N 3550 2920 3550 2945 {}
C {lab_pin.sym} 3550 2945 0 0 {name=l412 lab=t206}
C {sg13g2_pr/rppd.sym} 3800 2890 0 0 {name=RU207 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 2860 3800 2835 {}
C {lab_pin.sym} 3800 2835 2 0 {name=l413 lab=t206}
N 3800 2920 3800 2945 {}
C {lab_pin.sym} 3800 2945 0 0 {name=l414 lab=t207}
C {sg13g2_pr/rppd.sym} 4050 2890 0 0 {name=RU208 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 2860 4050 2835 {}
C {lab_pin.sym} 4050 2835 2 0 {name=l415 lab=t207}
N 4050 2920 4050 2945 {}
C {lab_pin.sym} 4050 2945 0 0 {name=l416 lab=t208}
C {sg13g2_pr/rppd.sym} 300 3110 0 0 {name=RU209 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 3080 300 3055 {}
C {lab_pin.sym} 300 3055 2 0 {name=l417 lab=t208}
N 300 3140 300 3165 {}
C {lab_pin.sym} 300 3165 0 0 {name=l418 lab=t209}
C {sg13g2_pr/rppd.sym} 550 3110 0 0 {name=RU210 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 3080 550 3055 {}
C {lab_pin.sym} 550 3055 2 0 {name=l419 lab=t209}
N 550 3140 550 3165 {}
C {lab_pin.sym} 550 3165 0 0 {name=l420 lab=t210}
C {sg13g2_pr/rppd.sym} 800 3110 0 0 {name=RU211 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 3080 800 3055 {}
C {lab_pin.sym} 800 3055 2 0 {name=l421 lab=t210}
N 800 3140 800 3165 {}
C {lab_pin.sym} 800 3165 0 0 {name=l422 lab=t211}
C {sg13g2_pr/rppd.sym} 1050 3110 0 0 {name=RU212 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 3080 1050 3055 {}
C {lab_pin.sym} 1050 3055 2 0 {name=l423 lab=t211}
N 1050 3140 1050 3165 {}
C {lab_pin.sym} 1050 3165 0 0 {name=l424 lab=t212}
C {sg13g2_pr/rppd.sym} 1300 3110 0 0 {name=RU213 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 3080 1300 3055 {}
C {lab_pin.sym} 1300 3055 2 0 {name=l425 lab=t212}
N 1300 3140 1300 3165 {}
C {lab_pin.sym} 1300 3165 0 0 {name=l426 lab=t213}
C {sg13g2_pr/rppd.sym} 1550 3110 0 0 {name=RU214 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 3080 1550 3055 {}
C {lab_pin.sym} 1550 3055 2 0 {name=l427 lab=t213}
N 1550 3140 1550 3165 {}
C {lab_pin.sym} 1550 3165 0 0 {name=l428 lab=t214}
C {sg13g2_pr/rppd.sym} 1800 3110 0 0 {name=RU215 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 3080 1800 3055 {}
C {lab_pin.sym} 1800 3055 2 0 {name=l429 lab=t214}
N 1800 3140 1800 3165 {}
C {lab_pin.sym} 1800 3165 0 0 {name=l430 lab=t215}
C {sg13g2_pr/rppd.sym} 2050 3110 0 0 {name=RU216 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 3080 2050 3055 {}
C {lab_pin.sym} 2050 3055 2 0 {name=l431 lab=t215}
N 2050 3140 2050 3165 {}
C {lab_pin.sym} 2050 3165 0 0 {name=l432 lab=t216}
C {sg13g2_pr/rppd.sym} 2300 3110 0 0 {name=RU217 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 3080 2300 3055 {}
C {lab_pin.sym} 2300 3055 2 0 {name=l433 lab=t216}
N 2300 3140 2300 3165 {}
C {lab_pin.sym} 2300 3165 0 0 {name=l434 lab=t217}
C {sg13g2_pr/rppd.sym} 2550 3110 0 0 {name=RU218 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 3080 2550 3055 {}
C {lab_pin.sym} 2550 3055 2 0 {name=l435 lab=t217}
N 2550 3140 2550 3165 {}
C {lab_pin.sym} 2550 3165 0 0 {name=l436 lab=t218}
C {sg13g2_pr/rppd.sym} 2800 3110 0 0 {name=RU219 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 3080 2800 3055 {}
C {lab_pin.sym} 2800 3055 2 0 {name=l437 lab=t218}
N 2800 3140 2800 3165 {}
C {lab_pin.sym} 2800 3165 0 0 {name=l438 lab=t219}
C {sg13g2_pr/rppd.sym} 3050 3110 0 0 {name=RU220 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 3080 3050 3055 {}
C {lab_pin.sym} 3050 3055 2 0 {name=l439 lab=t219}
N 3050 3140 3050 3165 {}
C {lab_pin.sym} 3050 3165 0 0 {name=l440 lab=t220}
C {sg13g2_pr/rppd.sym} 3300 3110 0 0 {name=RU221 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 3080 3300 3055 {}
C {lab_pin.sym} 3300 3055 2 0 {name=l441 lab=t220}
N 3300 3140 3300 3165 {}
C {lab_pin.sym} 3300 3165 0 0 {name=l442 lab=t221}
C {sg13g2_pr/rppd.sym} 3550 3110 0 0 {name=RU222 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 3080 3550 3055 {}
C {lab_pin.sym} 3550 3055 2 0 {name=l443 lab=t221}
N 3550 3140 3550 3165 {}
C {lab_pin.sym} 3550 3165 0 0 {name=l444 lab=t222}
C {sg13g2_pr/rppd.sym} 3800 3110 0 0 {name=RU223 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 3080 3800 3055 {}
C {lab_pin.sym} 3800 3055 2 0 {name=l445 lab=t222}
N 3800 3140 3800 3165 {}
C {lab_pin.sym} 3800 3165 0 0 {name=l446 lab=t223}
C {sg13g2_pr/rppd.sym} 4050 3110 0 0 {name=RU224 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 3080 4050 3055 {}
C {lab_pin.sym} 4050 3055 2 0 {name=l447 lab=t223}
N 4050 3140 4050 3165 {}
C {lab_pin.sym} 4050 3165 0 0 {name=l448 lab=t224}
C {sg13g2_pr/rppd.sym} 300 3330 0 0 {name=RU225 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 3300 300 3275 {}
C {lab_pin.sym} 300 3275 2 0 {name=l449 lab=t224}
N 300 3360 300 3385 {}
C {lab_pin.sym} 300 3385 0 0 {name=l450 lab=t225}
C {sg13g2_pr/rppd.sym} 550 3330 0 0 {name=RU226 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 3300 550 3275 {}
C {lab_pin.sym} 550 3275 2 0 {name=l451 lab=t225}
N 550 3360 550 3385 {}
C {lab_pin.sym} 550 3385 0 0 {name=l452 lab=t226}
C {sg13g2_pr/rppd.sym} 800 3330 0 0 {name=RU227 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 3300 800 3275 {}
C {lab_pin.sym} 800 3275 2 0 {name=l453 lab=t226}
N 800 3360 800 3385 {}
C {lab_pin.sym} 800 3385 0 0 {name=l454 lab=t227}
C {sg13g2_pr/rppd.sym} 1050 3330 0 0 {name=RU228 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 3300 1050 3275 {}
C {lab_pin.sym} 1050 3275 2 0 {name=l455 lab=t227}
N 1050 3360 1050 3385 {}
C {lab_pin.sym} 1050 3385 0 0 {name=l456 lab=t228}
C {sg13g2_pr/rppd.sym} 1300 3330 0 0 {name=RU229 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 3300 1300 3275 {}
C {lab_pin.sym} 1300 3275 2 0 {name=l457 lab=t228}
N 1300 3360 1300 3385 {}
C {lab_pin.sym} 1300 3385 0 0 {name=l458 lab=t229}
C {sg13g2_pr/rppd.sym} 1550 3330 0 0 {name=RU230 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 3300 1550 3275 {}
C {lab_pin.sym} 1550 3275 2 0 {name=l459 lab=t229}
N 1550 3360 1550 3385 {}
C {lab_pin.sym} 1550 3385 0 0 {name=l460 lab=t230}
C {sg13g2_pr/rppd.sym} 1800 3330 0 0 {name=RU231 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 3300 1800 3275 {}
C {lab_pin.sym} 1800 3275 2 0 {name=l461 lab=t230}
N 1800 3360 1800 3385 {}
C {lab_pin.sym} 1800 3385 0 0 {name=l462 lab=t231}
C {sg13g2_pr/rppd.sym} 2050 3330 0 0 {name=RU232 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 3300 2050 3275 {}
C {lab_pin.sym} 2050 3275 2 0 {name=l463 lab=t231}
N 2050 3360 2050 3385 {}
C {lab_pin.sym} 2050 3385 0 0 {name=l464 lab=t232}
C {sg13g2_pr/rppd.sym} 2300 3330 0 0 {name=RU233 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 3300 2300 3275 {}
C {lab_pin.sym} 2300 3275 2 0 {name=l465 lab=t232}
N 2300 3360 2300 3385 {}
C {lab_pin.sym} 2300 3385 0 0 {name=l466 lab=t233}
C {sg13g2_pr/rppd.sym} 2550 3330 0 0 {name=RU234 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 3300 2550 3275 {}
C {lab_pin.sym} 2550 3275 2 0 {name=l467 lab=t233}
N 2550 3360 2550 3385 {}
C {lab_pin.sym} 2550 3385 0 0 {name=l468 lab=t234}
C {sg13g2_pr/rppd.sym} 2800 3330 0 0 {name=RU235 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 3300 2800 3275 {}
C {lab_pin.sym} 2800 3275 2 0 {name=l469 lab=t234}
N 2800 3360 2800 3385 {}
C {lab_pin.sym} 2800 3385 0 0 {name=l470 lab=t235}
C {sg13g2_pr/rppd.sym} 3050 3330 0 0 {name=RU236 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 3300 3050 3275 {}
C {lab_pin.sym} 3050 3275 2 0 {name=l471 lab=t235}
N 3050 3360 3050 3385 {}
C {lab_pin.sym} 3050 3385 0 0 {name=l472 lab=t236}
C {sg13g2_pr/rppd.sym} 3300 3330 0 0 {name=RU237 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 3300 3300 3275 {}
C {lab_pin.sym} 3300 3275 2 0 {name=l473 lab=t236}
N 3300 3360 3300 3385 {}
C {lab_pin.sym} 3300 3385 0 0 {name=l474 lab=t237}
C {sg13g2_pr/rppd.sym} 3550 3330 0 0 {name=RU238 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 3300 3550 3275 {}
C {lab_pin.sym} 3550 3275 2 0 {name=l475 lab=t237}
N 3550 3360 3550 3385 {}
C {lab_pin.sym} 3550 3385 0 0 {name=l476 lab=t238}
C {sg13g2_pr/rppd.sym} 3800 3330 0 0 {name=RU239 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 3300 3800 3275 {}
C {lab_pin.sym} 3800 3275 2 0 {name=l477 lab=t238}
N 3800 3360 3800 3385 {}
C {lab_pin.sym} 3800 3385 0 0 {name=l478 lab=t239}
C {sg13g2_pr/rppd.sym} 4050 3330 0 0 {name=RU240 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 4050 3300 4050 3275 {}
C {lab_pin.sym} 4050 3275 2 0 {name=l479 lab=t239}
N 4050 3360 4050 3385 {}
C {lab_pin.sym} 4050 3385 0 0 {name=l480 lab=t240}
C {sg13g2_pr/rppd.sym} 300 3550 0 0 {name=RU241 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 300 3520 300 3495 {}
C {lab_pin.sym} 300 3495 2 0 {name=l481 lab=t240}
N 300 3580 300 3605 {}
C {lab_pin.sym} 300 3605 0 0 {name=l482 lab=t241}
C {sg13g2_pr/rppd.sym} 550 3550 0 0 {name=RU242 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 550 3520 550 3495 {}
C {lab_pin.sym} 550 3495 2 0 {name=l483 lab=t241}
N 550 3580 550 3605 {}
C {lab_pin.sym} 550 3605 0 0 {name=l484 lab=t242}
C {sg13g2_pr/rppd.sym} 800 3550 0 0 {name=RU243 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 800 3520 800 3495 {}
C {lab_pin.sym} 800 3495 2 0 {name=l485 lab=t242}
N 800 3580 800 3605 {}
C {lab_pin.sym} 800 3605 0 0 {name=l486 lab=t243}
C {sg13g2_pr/rppd.sym} 1050 3550 0 0 {name=RU244 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1050 3520 1050 3495 {}
C {lab_pin.sym} 1050 3495 2 0 {name=l487 lab=t243}
N 1050 3580 1050 3605 {}
C {lab_pin.sym} 1050 3605 0 0 {name=l488 lab=t244}
C {sg13g2_pr/rppd.sym} 1300 3550 0 0 {name=RU245 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1300 3520 1300 3495 {}
C {lab_pin.sym} 1300 3495 2 0 {name=l489 lab=t244}
N 1300 3580 1300 3605 {}
C {lab_pin.sym} 1300 3605 0 0 {name=l490 lab=t245}
C {sg13g2_pr/rppd.sym} 1550 3550 0 0 {name=RU246 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1550 3520 1550 3495 {}
C {lab_pin.sym} 1550 3495 2 0 {name=l491 lab=t245}
N 1550 3580 1550 3605 {}
C {lab_pin.sym} 1550 3605 0 0 {name=l492 lab=t246}
C {sg13g2_pr/rppd.sym} 1800 3550 0 0 {name=RU247 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 1800 3520 1800 3495 {}
C {lab_pin.sym} 1800 3495 2 0 {name=l493 lab=t246}
N 1800 3580 1800 3605 {}
C {lab_pin.sym} 1800 3605 0 0 {name=l494 lab=t247}
C {sg13g2_pr/rppd.sym} 2050 3550 0 0 {name=RU248 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2050 3520 2050 3495 {}
C {lab_pin.sym} 2050 3495 2 0 {name=l495 lab=t247}
N 2050 3580 2050 3605 {}
C {lab_pin.sym} 2050 3605 0 0 {name=l496 lab=t248}
C {sg13g2_pr/rppd.sym} 2300 3550 0 0 {name=RU249 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2300 3520 2300 3495 {}
C {lab_pin.sym} 2300 3495 2 0 {name=l497 lab=t248}
N 2300 3580 2300 3605 {}
C {lab_pin.sym} 2300 3605 0 0 {name=l498 lab=t249}
C {sg13g2_pr/rppd.sym} 2550 3550 0 0 {name=RU250 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2550 3520 2550 3495 {}
C {lab_pin.sym} 2550 3495 2 0 {name=l499 lab=t249}
N 2550 3580 2550 3605 {}
C {lab_pin.sym} 2550 3605 0 0 {name=l500 lab=t250}
C {sg13g2_pr/rppd.sym} 2800 3550 0 0 {name=RU251 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 2800 3520 2800 3495 {}
C {lab_pin.sym} 2800 3495 2 0 {name=l501 lab=t250}
N 2800 3580 2800 3605 {}
C {lab_pin.sym} 2800 3605 0 0 {name=l502 lab=t251}
C {sg13g2_pr/rppd.sym} 3050 3550 0 0 {name=RU252 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3050 3520 3050 3495 {}
C {lab_pin.sym} 3050 3495 2 0 {name=l503 lab=t251}
N 3050 3580 3050 3605 {}
C {lab_pin.sym} 3050 3605 0 0 {name=l504 lab=t252}
C {sg13g2_pr/rppd.sym} 3300 3550 0 0 {name=RU253 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3300 3520 3300 3495 {}
C {lab_pin.sym} 3300 3495 2 0 {name=l505 lab=t252}
N 3300 3580 3300 3605 {}
C {lab_pin.sym} 3300 3605 0 0 {name=l506 lab=t253}
C {sg13g2_pr/rppd.sym} 3550 3550 0 0 {name=RU254 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3550 3520 3550 3495 {}
C {lab_pin.sym} 3550 3495 2 0 {name=l507 lab=t253}
N 3550 3580 3550 3605 {}
C {lab_pin.sym} 3550 3605 0 0 {name=l508 lab=t254}
C {sg13g2_pr/rppd.sym} 3800 3550 0 0 {name=RU255 model=rppd body=sub spiceprefix=X w=2u l=3.43u b=0 m=1}
N 3800 3520 3800 3495 {}
C {lab_pin.sym} 3800 3495 2 0 {name=l509 lab=t254}
N 3800 3580 3800 3605 {}
C {lab_pin.sym} 3800 3605 0 0 {name=l510 lab=out}
C {devices/res.sym} 4600 250 0 0 {name=RS0 value="{1e-3 + 1e12*(floor(trim_code/1)-2*floor(trim_code/2))\}" m=1}
N 4600 220 4600 195 {}
C {lab_pin.sym} 4600 195 2 0 {name=l511 lab=in}
N 4600 280 4600 305 {}
C {lab_pin.sym} 4600 305 0 0 {name=l512 lab=t001}
C {devices/res.sym} 4880 250 0 0 {name=RS1 value="{1e-3 + 1e12*(floor(trim_code/2)-2*floor(trim_code/4))\}" m=1}
N 4880 220 4880 195 {}
C {lab_pin.sym} 4880 195 2 0 {name=l513 lab=t001}
N 4880 280 4880 305 {}
C {lab_pin.sym} 4880 305 0 0 {name=l514 lab=t003}
C {devices/res.sym} 5160 250 0 0 {name=RS2 value="{1e-3 + 1e12*(floor(trim_code/4)-2*floor(trim_code/8))\}" m=1}
N 5160 220 5160 195 {}
C {lab_pin.sym} 5160 195 2 0 {name=l515 lab=t003}
N 5160 280 5160 305 {}
C {lab_pin.sym} 5160 305 0 0 {name=l516 lab=t007}
C {devices/res.sym} 5440 250 0 0 {name=RS3 value="{1e-3 + 1e12*(floor(trim_code/8)-2*floor(trim_code/16))\}" m=1}
N 5440 220 5440 195 {}
C {lab_pin.sym} 5440 195 2 0 {name=l517 lab=t007}
N 5440 280 5440 305 {}
C {lab_pin.sym} 5440 305 0 0 {name=l518 lab=t015}
C {devices/res.sym} 5720 250 0 0 {name=RS4 value="{1e-3 + 1e12*(floor(trim_code/16)-2*floor(trim_code/32))\}" m=1}
N 5720 220 5720 195 {}
C {lab_pin.sym} 5720 195 2 0 {name=l519 lab=t015}
N 5720 280 5720 305 {}
C {lab_pin.sym} 5720 305 0 0 {name=l520 lab=t031}
C {devices/res.sym} 6000 250 0 0 {name=RS5 value="{1e-3 + 1e12*(floor(trim_code/32)-2*floor(trim_code/64))\}" m=1}
N 6000 220 6000 195 {}
C {lab_pin.sym} 6000 195 2 0 {name=l521 lab=t031}
N 6000 280 6000 305 {}
C {lab_pin.sym} 6000 305 0 0 {name=l522 lab=t063}
C {devices/res.sym} 6280 250 0 0 {name=RS6 value="{1e-3 + 1e12*(floor(trim_code/64)-2*floor(trim_code/128))\}" m=1}
N 6280 220 6280 195 {}
C {lab_pin.sym} 6280 195 2 0 {name=l523 lab=t063}
N 6280 280 6280 305 {}
C {lab_pin.sym} 6280 305 0 0 {name=l524 lab=t127}
C {devices/res.sym} 6560 250 0 0 {name=RS7 value="{1e-3 + 1e12*(floor(trim_code/128)-2*floor(trim_code/256))\}" m=1}
N 6560 220 6560 195 {}
C {lab_pin.sym} 6560 195 2 0 {name=l525 lab=t127}
N 6560 280 6560 305 {}
C {lab_pin.sym} 6560 305 0 0 {name=l526 lab=out}
C {devices/code.sym} 200 30 0 0 {name=TRIMCODE only_toplevel=false place=header value=".param trim_code=128"}
C {iopin.sym} 200 -80 0 0 {name=p1 lab=in}
C {iopin.sym} 300 -80 0 0 {name=p2 lab=out}
C {iopin.sym} 400 -80 0 0 {name=p3 lab=sub}
