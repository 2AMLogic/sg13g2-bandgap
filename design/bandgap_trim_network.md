# Trim network: sizing and coverage (issue #229)

This document is the sizing rationale for the trim network
DR-0011 ([`spec/decision-records/0011-output-reference-row-disposition.md`](../spec/decision-records/0011-output-reference-row-disposition.md))
obligates and `README.md`'s ratified Trim row states: *"1-point at 27 °C;
range ≥ ±15%; resolution ≤ 0.25%/step; magnitude only"*. It ties that row
to `design/bandgap_trim.sch` / `bandgap_core.sch` (the implementation),
[`sim/trim-coverage/`](../sim/trim-coverage/README.md) (the measured
range/resolution/linearity evidence),
[`sim/closed-loop-vref-trim-mc/`](../sim/closed-loop-vref-trim-mc/README.md)
(the trimmed ±0.5% line) and
[`sim/closed-loop-vref-boxtc-trim/`](../sim/closed-loop-vref-boxtc-trim/README.md)
(the post-trim TC). It follows `gf180-bandgap`'s
`design/bandgap_trim_network.md` (issue #14) in structure — this design
is that ladder re-derived for a core whose mismatch scatter is an order
of magnitude wider and whose PTAT term is a smaller share of the output.

## 1. Topology: a series binary-weighted ladder on the output branch

The trim inserts **in series with R1**, on the Q3 side of the summing
resistor: `bandgap_core.sch`'s R1 no longer runs to `cb3`, it runs to a
new node `tn0` (`l = 37.2u` base), and `XTRIM`
(`bandgap_trim.sch`) continues `tn0 → cb3`. The PTAT branch current is
set entirely by the R2/Q1/Q2 loop (`I = VT·ln(8)/R2`), independent of
what sits in the output branch, so

```
vref = VBE(Q3) + I·(R1_base + Rtrim(code))     — magnitude only,
```

linear in `trim_code` to first order (`sim/trim-coverage/` measures the
linearity residual rather than assuming it). Placing the ladder on the
`cb3` side (vs gf180's `vref` side) keeps the ladder's well parasitics
off the output node — `cb3` is Q3's diode-connected base, a
low-impedance node; this is a placement choice only, electrically the
same series element.

`bandgap_trim` is **255 identical `rppd` unit segments** (`w=2u`,
`l=3.43u`, `b=0`, `m=1`) in one series string, tapped after
1/3/7/15/31/63/127 units into eight binary-weighted groups
(weights 2⁰…2⁷ = 1/2/4/8/16/32/64/128). Each group is shunted by one
strap `RS0…RS7` — not a fabricated device, a behavioral resistor
modeling a metal-option / probe-pad link (`1e-3 Ω` = link drawn, group
shorted out; `1e12 Ω` = link cut, group in circuit), decoded from the
subcircuit-local parameter `trim_code` (0…255):

```
bit_b  = floor(trim_code/2^b) − 2·floor(trim_code/2^(b+1))
Rtrim(trim_code) = trim_code · R_unit        — monotonic, exact-binary
```

**Why identical unit segments and not eight differently-sized
resistors**: the same measured lesson gf180's design doc records —
differently-sized single resistors do not hold `2^b` ratios across PVT
because the per-instance header/contact fraction differs by bit (on this
PDK the `rppd` per-instance offset is ~35 Ω of a 478 Ω unit — 7.3%, and
it skews differently from the body over corners). Integer counts of the
identical physical device are exact by construction at every corner;
`sim/trim-coverage/`'s per-group weight gate verifies this on SG13G2's
own corners.

**Why `w=2u`**: matches R1/R2 exactly (the process spec's
precision-resistor width, per `spec/porting-plan.md` §2), so the
ladder-to-R2 ratio the trim step depends on tracks over res corners with
the same device geometry class.

## 2. The sizing constraint is correlated coverage, not the voltage window

DR-0011 derives the Trim row's ±15% floor from the typ/27 °C MC point:
worst 3σ die 13.31% below / 12.68% above 1.050 V, plus the ±0.65% PVT
mean envelope, rounded out. Read naively as an adjustable-voltage window
(`±15% of 1.050 V = ±157.5 mV each side`), a 6-bit ladder at the 0.25%
step cap would cover it (63 × 2.625 mV = 165 mV). **That reading
under-sizes the ladder**, because the trim step is not a constant
voltage: it is `I·R_unit`, and the dies that need the MOST correction
are the ones whose own `I` is farthest off.

The #215 MC's scatter is current-error dominated (measured σ = 45.5 mV
on a 0.3386 V PTAT term ⇒ σ_f ≈ 13.4% on the branch current, from
mirror + ΔVBE + R2 mismatch). A die with current error `f` has

```
untrimmed offset  = 0.3386·f                    (needs |0.3386·f| of correction)
its own trim step = step_nom·(1 + f)            (scales WITH the error)
```

so the coverable condition at the trim point is
`0.3386·|f| ≤ S·step_nom·(1+f)` for `S` available steps in that
direction. With the nominal 3σ current error (|f| = 0.40) that demands
**≥ 227.7 mV of up-range at nominal step** (2.33× the high-side
requirement, because a low-current die needs up-correction while its
step shrank), against only ~98 mV needed down-range — the correlation
is asymmetric. A ±15%-window 6-bit ladder covers only |f| ≤ 0.32 ≈ 2.4σ
on the low side — the trimmed line would be a ~2.4σ claim under a row
derived for 3σ.

**This design therefore sizes to correlated coverage**: an 8-bit ladder
(255 units) whose nominal step is chosen so that, simultaneously:

| constraint | binding value | this design |
|---|---|---|
| resolution ≤ 0.25%/step (2.625 mV at 1.050 V) | cap | step = 2.443 mV = 0.2327% (measured, typ/27 °C/3.30 V) |
| quantization ±½ step ≤ 0.125% of budget | cap | ±1.222 mV = 0.1164% |
| up-range ≥ 227.7 mV (correlated 3σ coverage) | floor | 127 × 2.443 = 310.3 mV (f_cover = 0.478 ≈ 3.57σ) |
| down-range ≥ ~98 mV (correlated 3σ) | floor | 128 × 2.443 = 312.7 mV (f_cover = 0.480) |
| range ≥ ±15% of 1.050 V each direction (the ratified floor, both readings satisfied) | floor | +29.6% / −29.8% |

Coverage in σ units uses the measured σ_f = 45.486 mV / 338.6 mV ≈ 0.134
(the #215 record's typ point): the rails sit at ±3.6σ, outside the ±3σ
population the untrimmed ±16% line covers — and
`sim/closed-loop-vref-trim-mc/` measures where the population actually
rails (`n_railed`), closing the argument with data rather than the
Gaussian assumption.

**Why 8 bits and not 7**: a 7-bit ladder (127 codes) needs step ≥
2.56 mV to meet the correlated up-range floor (89 codes × step ≥
227.7 mV with an asymmetric default code) while the resolution cap is
2.625 mV — a 2.5%-wide window with zero margin on either constraint at
every corner. 8 bits restores a ≥ 45%-wide step window (any step in
[1.79, 2.625] mV meets both constraints); the cost is ladder area
(§5) — accepted, because the ±0.5% trimmed line is the buyer-facing row.

## 3. Unit geometry derivation (typ res corner, 27 °C)

Measured against the PDK's own `r3_cmc` model (the numbers the netlist
will simulate, not the display formula on `rppd.sym`):

```
R(l) ≈ 129.25 Ω/µm · l + 35.0 Ω        (w = 2 µm, res_typ, 27 °C)
R2   = R(82.7 µm)  = 10722.2 Ω          (unchanged, sets I)
R1_nom = R(511 µm) = 66069.4 Ω          (the pre-#229 summing resistor)
```

- **Unit segment**: `R_unit = R(3.43 µm) = 478.3 Ω`, chosen so the
  ideal-loop step `VT(27 °C)·ln(8)·R_unit/R2 ≈ 2.40 mV` lands mid-window
  under both constraints; the **measured** closed-loop step at
  typ/27 °C/3.30 V is `vref(129) − vref(128) = 2.443 mV`
  (`sim/trim-coverage/`), 6.9% under the resolution cap — the
  loop-current/mirror effects the ideal formula omits are absorbed by
  that margin, and the measured number is the one the table above
  quotes.
- **Default code 128**: `R1_base = R(37.2 µm) = 4843.1 Ω`, so
  `R1_eff(128) = 4843.1 + 128·478.3 = 66066.5 Ω` vs `R1_nom =
  66069.4 Ω` — within 3 Ω (0.005%). Measured: `vref(128) = 1.047278 V`
  vs the pre-trim single-instance core's 1.047338 V at the same point
  (−0.06 mV). Every pre-#229 record therefore stays electrically valid
  against the schematic default — the same continuity convention
  gf180's default code 32 established.
- The trim targets **1.050 V** — each die's ratio corrected back toward
  the TC-null operating point, never toward 1.2 V (DR-0011's
  Alternatives: trimming to 1.2 V is a ratio move back toward the
  measured 349–376 ppm/°C pre-retune core). Because the mismatch
  population's errors are PTAT-shaped (current scaling, ratio error,
  ΔVBE — all land on `I·R1`), correcting the level with R1 also restores
  the die's TC-null ratio to first order; the residual trim-induced TC
  is what `sim/closed-loop-vref-boxtc-trim/` bounds.

## 4. Strap decode

`RS<b> = {1e-3 + 1e12·(floor(trim_code/2^b) − 2·floor(trim_code/2^(b+1)))}`
— 1 mΩ when bit b is 0 (strap closed, group shorted out), 1 TΩ when 1
(group in circuit). The straps are verification-time models of a
metal-option / probe-pad link, exactly gf180's convention; the physical
realization (metal-option mask select vs laser/e-fuse) is a layout/test
follow-on like gf180's #16, and does not change this sizing. Code
selection at test is the wafer-probe 1-point trim
(`sim/closed-loop-vref-trim-mc/` models it per-die); the schematic
default stays 128.

## 5. Layout area budget

Unit cell: `rppd w=2u l=3.43u` ≈ **6.9 µm²** drawn per segment
(2 µm × 3.43 µm). At 255 segments the ladder's drawn resistor area is
≈ **1750 µm²**; adding the eight strap shunt links, the segment-to-segment
series links and tap contacts at the same M1/poly conventions the core's
existing resistors use, plus dummies-for-matching at the array edges
(same discipline the R1/R2 pair gets), a **≈ 2200–2600 µm²** budget
covers the ladder as a routed array. For scale: the pre-trim core's R1
alone (511 µm × 2 µm) is ≈ 1022 µm² and R2 ≈ 165 µm² — the trim ladder
roughly doubles the core's precision-resistor area. Re-layout of
`layout/bandgap_core` (still sized for the pre-#134 694.5 µm R1) carries
this budget; that re-layout remains the separate follow-on it already
was, not part of this issue's schematic-level design.

## 6. Evidence map

| claim | evidence |
|---|---|
| range ≥ ±15%, resolution ≤ 0.25%/step, exact binary weights, monotonic, linear | `sim/trim-coverage/records/` (`-analysis.csv` per corner/supply group at 27 °C) — **met** |
| default code ≡ pre-trim core (records continuity) | `sim/trim-coverage/` headline (vref(128) vs 1.047338 V) — **met** (−0.06 mV) |
| correlated coverage (no railed dies) | `sim/closed-loop-vref-trim-mc/records/` (`n_railed = 0` at every point) — **met** |
| ±0.5% trimmed line over −40…125 °C after a 1-point 27 °C trim | `sim/closed-loop-vref-trim-mc/records/` — **measured NOT met**: 3σ ≈ ±2.6%, ≈30% of dies inside ±0.5% (the 27 °C trim itself centers every die to quantization-class; the miss is the population's drift — the nominal die's ~0.43% alone exceeds DR-0011's 0.20% drift input, and a code*-correlated pivot ~0.04%/code remains). Disposition tracked in #265 |
| trim-induced TC degradation inside the ~0.175% headroom | `sim/closed-loop-vref-boxtc-trim/records/` (`-trimdtc.csv` ±1-code gate, rails bounded) |
| untrimmed ±16% (3σ) line (context the trim improves on) | `sim/closed-loop-vref-mc/records/` (issue #215, unchanged; the trim MC reproduces its typ/27 σ to 3%) |
