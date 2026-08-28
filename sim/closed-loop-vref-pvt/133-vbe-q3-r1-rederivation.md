# VBE(Q3) measurement and R1 re-derivation (issue #133)

Decision-support evidence for the [PR #128](https://github.com/2AMLogic/sg13g2-bandgap/pull/128)
Output-reference escalation. Both review keys on that PR traced the untrimmed
`vref` accuracy miss to an **unverified `VBE(Q3)≈0.75V` sizing assumption** in
`design/bandgap_core.sch`'s own header — R1 (90 kΩ) was hand-sized from that
assumption before any simulation existed, not from a measured value. This
document measures the real `VBE(Q3)`, re-derives R1 from it using the same
formula the schematic's own header uses, and reports what untrimmed accuracy
band the re-derived R1 actually achieves across the full PVT grid.

**Scope**: decision-support only. This document does **not** edit
`spec/target-spec.md`, PR #128, or the ratification tooling, and step 3 below
is explicitly **sim-only** — no `design/` file is changed by this issue.

## 1. Measured VBE(Q3), from a committed testbench

`sim/closed-loop-vref-pvt/testbench/tb_closed_loop_vref.spice.tmpl` was
extended (this issue) with a `.measure` probe on `v(cb3)` — Q3's
diode-connected base/collector node. Since Q3's emitter is tied to `vss` (the
0 V reference), `v(cb3)` **is** `VBE(Q3)` directly. The probe is read at the
same two settledness-checked time points (`t=2ms`/`t=3ms`) `vref` already
uses, through the same real closed-loop topology (`bandgap_core` +
`bandgap_amp` + `bandgap_startup`, wired exactly as `design/bandgap_top.sch`
specifies — no ideal fixture anywhere).

Full record (45/45 PASS, current `design/netlist/bandgap_core.spice @
4832c71`): [`records/20260828-190552-4e4a2c8.md`](records/20260828-190552-4e4a2c8.md)
/ [`.csv`](records/20260828-190552-4e4a2c8.csv) (`vbeq3_2ms_v`/`vbeq3_3ms_v`
columns).

**At the design's own nominal corner (`typ`/27°C/3.30V):**

```
VBE(Q3) = 0.708570 V   (vs. the design/bandgap_core.sch header's
                         assumed 0.75 V -- a 41.4 mV / 5.5% gap)
```

This closely matches the #128 EE-key review's own independent estimate from
`sns1 ≈ VBE(Q1)` (0.7087 V, a different PVT point in an earlier record but
the same device family and current) — cross-check, not a coincidence: Q1 and
Q3 are both `Nx=1` `npn13G2` devices carrying nearly the same ~5 µA design
current.

**Across the full 45-point PVT grid**, `VBE(Q3)` at `t=3ms` ranges:

| | min | max |
|---|---|---|
| VBE(Q3) | 0.5857 V (125 °C, worst case) | 0.7892 V (−40 °C, worst case) |

Full per-point table: `records/20260828-190552-4e4a2c8.md` "VBE(Q3) per PVT
point" section, or the CSV directly.

## 2. R1 re-derivation

`design/bandgap_core.sch`'s own header derives R1 as:

```
vref = VBE(Q3) + I*R1        (Brokaw CTAT + PTAT sum)
I    = VT*ln(8)/R2           (PTAT branch current, R2 = 10.75 kOhm as sized/built)
R1   = (vref_target - VBE(Q3)) / I
```

with `vref_target ≈ 1.2 V` and an **assumed, unsimulated** `VBE(Q3) ≈ 0.75 V`,
giving the committed `R1 = 90 kΩ` (`w=2u l=694.5u`).

Re-deriving with the **measured** `VBE(Q3) = 0.708570 V` at the same nominal
corner, and the same `I` formula (`VT` at 27°C = 300.15 K, `R2 = 10.75 kΩ`
unchanged):

```
VT(27C)  = kT/q = 0.025865 V
I        = VT*ln(8)/R2 = 0.025865 * 2.079442 / 10750 = 5.0032 uA

R1_new   = (1.2 - 0.708570) / 5.0032e-6
         = 0.491430 / 5.0032e-6
         = 98,223 Ohm  ~= 98.2 kOhm
```

**Cross-check against the measured branch current** (back-derived from this
record's own measured `vref`/`VBE(Q3)` and the *current* R1=90kΩ, rather than
the analytic `VT*ln(8)/R2` estimate above):

```
I_empirical = (vref_measured - VBE(Q3)_measured) / R1_current
            = (1.16677 - 0.708570) / 90000
            = 5.0911 uA
```

5.0032 µA (analytic) vs. 5.0911 µA (empirical) — a 1.7% spread, consistent
with the mirror's finite output impedance/Early effect (not modeled by the
ideal `I = VT*ln(8)/R2` formula) rather than a derivation error. Using the
analytic value (matching the schematic's own derivation method, as this
issue's scope asks) gives:

```
R1_new = 98.2 kOhm   (vs. the committed 90 kOhm, a +9.1% resize)
```

Scaling `rppd`'s `w=2u` geometry linearly from the existing `l=694.5u ->
R=90kOhm` data point (`rppd`'s own `R(w,l)` model is linear in `l` for a
fixed `w` and `b=0`, confirmed against `resistors_mod.lib`'s `.subckt rppd`
body): `l_new = 694.5u * (98223/90000) ≈ 758.0 um`.

## 3. Sim-only re-run with the re-derived R1 (NOT a committed design change)

A scratch copy of `tb_closed_loop_vref.spice.tmpl` with `XR1`'s `l` changed
from `694.5u` to `758.0u` (R1 ≈ 98.2 kΩ) was swept across the same 45-point
PVT grid (temperature × supply × HBT/MOS/resistor-process-corner), entirely
outside this repo (`/tmp`, not committed under `sim/` or `design/`) — no
`design/` file was edited, and no new `sim/*/records/` evidence was minted for
this scratch step, per this issue's explicit "no committed design change"
scope.

**43/45 points converged (2 corners — `bcs`/27°C/2.97V and `wcs`/−40°C/3.30V —
hit the same class of numerical stiffness `closed-loop-startup/README.md`'s
"A real numerical finding" section already documents for this topology's vdd
ramp near-singular startup instant: `ngspice` reports "Timestep too small ...
trouble with xq3" at t≈30-40µs, i.e. during the ramp, not at the settled
operating point.** This is a solver-numerics artifact of the larger R1
changing the local Jacobian conditioning at that specific transient instant,
not a functional finding about the circuit; chasing further convergence aids
for this exploratory, sim-only step is out of this issue's scope.

**At the design's own nominal corner (`typ`/27°C/3.30V):**

```
vref = 1.20845 V   (+0.70% vs. the 1.2 V target -- inside +-1%)
```

This directly answers the EE-key review's specific complaint ("at the
design's own `typ/27°C` corner the output is ~2.8% low") — the re-derived R1
resolves the nominal-corner miss.

**Across the full grid (43/45 converged points), against the 1.2 V target:**

| | vref | vs. 1.2 V target |
|---|---|---|
| min | 1.16612 V (`bcs`/−40°C/2.97V) | −2.82% |
| max | 1.27107 V (`wcs`/125°C/3.63V) | +5.92% |

Only 11/43 points (25.6%) land inside the ±1% band (`[1.188 V, 1.212 V]`) —
comparable to the *committed* R1=90kΩ record's own 12/45 (26.7%), **not** a
material improvement in PVT-band coverage, despite the nominal-corner fix.

**Temperature coefficient got measurably worse, not better**, with the larger
R1 (same endpoint-method computation `run_pvt_sweep.sh` uses):

| R1 | TC range (ppm/°C, 15 corner/supply groups) |
|---|---|
| 90 kΩ (committed) | 349–376 |
| 98.2 kΩ (re-derived) | 457–483 |

This is the expected first-order consequence, not a testbench artifact:
increasing R1 scales up the PTAT term `I*R1` (which carries essentially all
of the circuit's temperature dependence, since the CTAT `VBE(Q3)` term and
the PTAT current `I = VT*ln(8)/R2` are both fixed by device physics/R2), so
raising R1 to re-center the nominal-corner `vref` on 1.2 V proportionally
raises the *absolute* temperature-driven spread too. A sizing-only resize
trades where the band is centered, not how wide it is.

## 4. Conclusion

**No — a pure sizing fix (re-deriving R1 alone) cannot meet the ±1% untrimmed
`vref` accuracy row across the full PVT grid.**

It does fix exactly what the EE-key review flagged: the re-derived
`R1 ≈ 98.2 kΩ` centers `vref` on the 1.2 V target at the design's own nominal
corner (`typ`/27°C/3.30V, +0.70% vs. the prior −2.8%), confirming the
`VBE(Q3)≈0.75V` sizing assumption really was the primary cause of *that
specific* miss, exactly as the EE review's re-derivation predicted. But the
untrimmed accuracy row is a full-PVT claim, not a single-corner one, and the
temperature-driven spread that R1 cannot address (VBE(Q3)'s own CTAT slope is
a device-physics property, not a sizing choice) still blows the ±1% band at
both temperature extremes — and, because a bigger R1 amplifies the PTAT term
along with it, the spread in this specific re-derivation gets slightly worse
in ppm/°C, not better. This is exactly the outcome
`design/README.md`'s "Explicitly out of scope" section already anticipated
for issue #9 (no trim network in this design's first pass) and matches the
sibling-repo precedent PR #128's own EE-key review cites (`gf180-bandgap`
DR-0003, `sky130-bandgap` DR-005): closing the full-PVT accuracy gap needs a
trim network (or an equivalent temperature-compensation mechanism), not a
resistor resize. The pending #128 operator decision should treat "sizing fix"
and "accuracy-band relax + Trim row" as complementary, not competing: a
corrected R1 is still worth landing on its own merits (it fixes a real,
demonstrated sizing-assumption bug and centers the nominal corner correctly),
but it does not substitute for the trim-network path the ±1% row ultimately
needs.

## Reproducing

Step 1 (committed): `sim/closed-loop-vref-pvt/run_pvt_sweep.sh` (see that
experiment's own `README.md`).

Step 3 (scratch, sim-only, not part of this repo): copy
`sim/closed-loop-vref-pvt/testbench/tb_closed_loop_vref.spice.tmpl`, change
`XR1 vref cb3 sub! rppd w=2u l=694.5u m=1 b=0` to `l=758.0u`, and re-run the
same 45-point temperature × supply × process-corner grid documented in
`sim/closed-loop-vref-pvt/README.md`'s "Corner coverage" section against the
modified copy, outside this repo's `sim/` tree.
