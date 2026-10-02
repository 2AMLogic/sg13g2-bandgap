# trim-knob-jacobian

Deterministic **second-trim-knob Jacobian bench** (issue #267): the measured
`(level, drift)` column of each candidate second trim knob, on the real
trim-bearing closed loop, at the 27 °C trim point.

The 1-point R1 trim this block carries converts a die's 27 °C level error
into post-trim temperature drift — **+0.0775 %/code** deterministically
([`../closed-loop-vref-boxtc-trim/`](../closed-loop-vref-boxtc-trim/README.md))
and **+0.0577 %/code** across the mismatch population
([`../closed-loop-vref-trim-mc/`](../closed-loop-vref-trim-mc/README.md)).
#267 asks whether a *second* knob can break that coupling. That question is
not about area or decode: it is about each candidate knob's **column** in the
`(level, drift)` plane. Two knobs whose columns are parallel span **one**
degree of freedom between them no matter how much silicon the second one
costs, and the 2×2 solve for (level, drift) is singular. This bench measures
that column per candidate, so the evaluation in
[`../../design/bandgap_trim_second_knob.md`](../../design/bandgap_trim_second_knob.md)
rests on a measurement rather than on an argument.

## What this testbench claims, and what it does not

**It measures, per corner/supply group**, with
`L(k) = vref(k, 27 °C)`, `Dh(k) = vref(k, 125 °C) − vref(k, 27 °C)` and
`Dc(k) = vref(k, −40 °C) − vref(k, 27 °C)`, each knob `k`'s secant against
this run's own baseline point (`base`: code 128, no R2-branch element,
`gctat = ggain = 0` — the as-built core):

```
dlevel(k) = L(k)  − L(base)          ddrift(k) = Dh(k) − Dh(base)
ratio(k)  = ddrift(k) / dlevel(k)    <- the offset-to-drift conversion rate
```

| knob | what moves | what it stands for |
|---|---|---|
| **A** `trim_code` | the as-built 255-unit R1-side ladder's own decoded straps | the reference column — the knob #267's coupling is measured on |
| **B** R2-branch series `rppd` | an `rppd` segment of R1/R2's own `w=2u` class added in series with R2 (R2's card is never re-sized) | "a second ladder on R2 (or a joint R1/R2 code)" |
| **C** `gctat` | a behavioral VCCS `I = gctat·v(cb3)` from `vdd` into `vref`, i.e. a VBE/R CTAT current in the output branch, adding `(R1_eff/R_c)·VBE` to `vref` | "a VBE-offset / curvature trim" |
| **D** `ggain` | a behavioral VCCS `I = ggain·v(vref)`, which solves to `vref = (VBE + I·R1_eff)/(1 − ggain·R1_eff)` | a trim applied as a **scaling** of the whole reference (an output gain stage / VBE multiplier) — the "null the level without moving the PTAT gain" knob |

**It claims the columns, and the two first-principles predictions they
confirm**, against which each gate is set:

- `ratio_ptat = T(125 °C)/T(27 °C) − 1 = +0.326503`. Any knob that moves
  `vref` by rescaling a **VT-proportional** term must add drift equal to
  `level · ΔT/T`, because the volts it adds are themselves PTAT. Knobs A and
  B are both of that kind.
- `ratio_ctat = (VBE(125 °C) − VBE(27 °C))/VBE(27 °C)`, measured per group
  from this run's own `vbeq3` column (−0.1630…−0.1693). A knob that moves
  `vref` by adding a **VBE-proportional** term adds drift in the opposite
  direction — which is what makes it a second degree of freedom.

**It does NOT claim an implementation.** Knobs C and D are deliberately
**behavioral** — the same convention the ladder's own `1e-3`/`1e12` strap
cards already use to model a metal-option link rather than a drawn device.
They measure what a knob of that temperature *shape* does to the real loop,
which is what an architecture choice turns on; they do not model the branch
that would generate the current. That branch's area, quiescent current,
mismatch and PSRR cost are evaluation inputs in
[`../../design/bandgap_trim_second_knob.md`](../../design/bandgap_trim_second_knob.md),
not claims of this record. Knobs A and B move real PDK devices.

**It does not run mismatch draws** (deterministic corner sections only — the
per-die behaviour of any knob is a trim-domain MC's claim, as it is for the
as-built ladder) and is pre-layout, like every `closed-loop-*` and
`trim-*` experiment here.

## Why the knob settings are what they are

Every setting is sized to move the 27 °C level by about ±20 mV — roughly
8 LSBs of the as-built ladder: far above any solver noise, and small enough
to stay in the knob's linear regime. The run **verifies** that rather than
assuming it: knob A is two-sided (`a_lo`/`a_hi`, whose ratios must agree)
and knobs B/C/D carry a second point at twice the magnitude
(`*_ratio_2x`), because each of those three can only move the level in one
direction from a baseline that has no such element at all.

**R2 itself is never re-sized.** A drawn ladder on the R2 branch *adds*
series resistance, which is what knob B models, and keeping the committed
`XR2` card byte-identical at every point is also what keeps every netlist
snapshot's DUT signature identical — the invariant
`.github/scripts/check_evidence_formats.py`'s D2 freshness check enforces.

## Grid

`{typ, bcs, wcs, sf, fs}` × `{2.97, 3.30, 3.63} V` ×
`{−40, 27, 125} °C` × 9 knob points = **405 `.op` points**. The level leg of
every column is read at 27 °C (the 1-point trim temperature DR-0011
ratifies); the drift legs need the two end temperatures, so every knob point
runs at all three.

Method: one `.nodeset`-seeded `.op` per netlist — the
[`../trim-coverage/`](../trim-coverage/README.md) technique, with the seeds
read from [`../closed-loop-startup/`](../closed-loop-startup/README.md)'s own
most recent record (per-corner/temperature/supply `PASS` rows). The
`base`-point `.op` at typ/3.30 V reproduces
[`../closed-loop-vref-boxtc-trim/`](../closed-loop-vref-boxtc-trim/README.md)'s
settled **transient** code-128 values to 6 significant figures at both 27 °C
(1.047278 V) and 125 °C (1.042182 V), which is this bench's own
cross-check against committed evidence.

## Pass/fail criteria

Per point: the four shared criteria every PVT bench here applies (startup
released, loop closed, not railed, converged — `pvt_closed_loop_verdict`).

Per corner/supply group, all of:

| gate | threshold | what it establishes |
|---|---|---|
| `n_pass == n_grid` | — | no point of the group is missing |
| `\|a_dev_vs_pred_pct\|` | ≤ 5% | knob A's column IS the `ΔT/T` prediction — the coupling is a property of the knob's temperature shape, not of the ladder |
| `\|b_minus_a\|` | ≤ 0.02 | the R2-branch knob's column is **parallel** to knob A's ⇒ no second degree of freedom |
| `\|c_minus_a\|` | ≥ 0.30 | the CTAT knob's column is **independent** of knob A's ⇒ a real second degree of freedom |
| `c_ratio` | < 0 | and of the opposite sign, so the 2×2 is well conditioned |
| `\|c_lin_dev_pct\|` | ≤ 10% | the CTAT column is linear over 2× its magnitude |
| `\|d_ratio\|` | ≤ 0.05 | the scaling knob is **level-only**: it converts (almost) no offset into drift |

`records/<record-id>-jacobian.csv` carries every group's columns, both
predictions, the cold-side ratios, and the gate status.

### Measured (record `20261002-131827-d770c09a`, 405/405 PASS, 0/15 groups FAIL)

| knob | `ratio` (15 groups) | prediction | verdict |
|---|---|---|---|
| A — R1 ladder | +0.3311 … +0.3348 | `ΔT/T` = +0.3265 (within 1.4…2.5%) | the reference column |
| B — R2-branch ladder | +0.3247 … +0.3291 | same `ΔT/T` | **parallel to A** (`b_minus_a` −0.0064…−0.0057, i.e. ≤ 1.9% of A's own ratio) — **no new degree of freedom** |
| C — VBE/R CTAT injection | −0.1584 … −0.1507 | `ΔVBE/VBE` = −0.1693…−0.1630 (within 6.4…7.6%) | **independent** (`c_minus_a` −0.4904…−0.4847) |
| D — reference scaling | +0.0074 … +0.0112 | ≈ 0 (a scaling multiplies level and drift alike) | **level-only** |

Derived and reported in the same CSV: `tc_gain_level_neutral =
ratio_A − ratio_C` = **+0.4847…+0.4904** — the drift a level-neutral
combination of knobs A and C buys per volt of knob-A authority, which is the
sizing input a real second knob needs.

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent of ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time
JOBS=8 sim/trim-knob-jacobian/run_knob_jacobian.sh
```

Requires ngspice plus the OSDI models, and at least one committed
`sim/closed-loop-startup/records/*.csv` (the `.nodeset` seeds). Writes
append-only evidence under `netlist-snapshots/<record-id>/`,
`corners/<record-id>/` and
`records/<record-id>.{md,csv,-jacobian.csv}` — see
[`../README.md`](../README.md).
