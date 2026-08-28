# TC-row retune analysis (issue #134)

Closes the TC gap the EE key's review of ratification PR #128 flagged: the
drafted `< 50 ppm/C` temperature-coefficient row in
`spec/porting-plan.md` Sec 6 was contradicted by 100% of the committed
`sim/closed-loop-vref-pvt` PVT evidence (baseline record
`20260826-103022-014570b`, 349.0-376.3 ppm/C measured across all 15
process-corner/supply groups). This file is the required write-up for
steps 1-3 of #134's "What to build" — the per-corner gap table, the
dominant-error-regime analysis, and the resistor-ratio retune that closed
it. **This is not a spec change** — `spec/porting-plan.md` is untouched, per
the issue's own AC; that row stays a draft target pending #128's own
ratification mechanism.

Outcome: a resistor-ratio-only retune (`R1`: 694.5um -> 511um, `R2`
unchanged) closes the gap. No second-order curvature-correction circuitry
was needed. See "Side effects" below for what this retune trades away.

## 1. Per-corner gap: drafted row vs. committed evidence (baseline, before this fix)

From `sim/closed-loop-vref-pvt/records/20260826-103022-014570b-tc.csv`
(design/netlist/bandgap_core.spice @ `4832c71`, R1=694.5um, R2=82.7um,
both `rppd`), TC computed by the endpoint method (`1e6*(vref(125C) -
vref(-40C))/(165*vref(27C))` — equivalent to the box method here because
every one of these 15 series is monotonic in T, confirmed by direct
inspection of the per-corner curves, see Sec 2 below):

| corner | vdd (V) | vref(-40C) | vref(27C) | vref(125C) | TC (ppm/C) | vs. `< 50 ppm/C` |
|---|---|---|---|---|---|---|
| typ | 2.97 | 1.13709 | 1.16631 | 1.20656 | 360.993 | 7.2x over |
| typ | 3.30 | 1.13754 | 1.16677 | 1.20700 | 360.799 | 7.2x over |
| typ | 3.63 | 1.13787 | 1.16702 | 1.20702 | 359.112 | 7.2x over |
| bcs | 2.97 | 1.13411 | 1.16248 | 1.20148 | 351.234 | 7.0x over |
| bcs | 3.30 | 1.13454 | 1.16292 | 1.20188 | 350.945 | 7.0x over |
| bcs | 3.63 | 1.13486 | 1.16314 | 1.20184 | 349.003 | 7.0x over |
| wcs | 2.97 | 1.14161 | 1.17215 | 1.21438 | 376.258 | 7.5x over |
| wcs | 3.30 | 1.14208 | 1.17264 | 1.21486 | 376.152 | 7.5x over |
| wcs | 3.63 | 1.14243 | 1.17293 | 1.21494 | 374.664 | 7.5x over |
| sf | 2.97 | 1.13714 | 1.16637 | 1.20664 | 361.131 | 7.2x over |
| sf | 3.30 | 1.13757 | 1.16682 | 1.20705 | 360.888 | 7.2x over |
| sf | 3.63 | 1.13789 | 1.16705 | 1.20704 | 359.103 | 7.2x over |
| fs | 2.97 | 1.13703 | 1.16623 | 1.20648 | 360.914 | 7.2x over |
| fs | 3.30 | 1.13750 | 1.16672 | 1.20695 | 360.763 | 7.2x over |
| fs | 3.63 | 1.13784 | 1.16699 | 1.20699 | 359.121 | 7.2x over |

Every one of the 15 groups misses the drafted row by 7.0-7.5x — matching
the EE key's "contradicted by 100%" characterization exactly.

## 2. Dominant-error regime: first-order slope, not curvature

The topology (`design/bandgap_core.sch`) is a classic Brokaw-style
CTAT+PTAT sum: `vref = VBE(Q3) + I*R1`, `I = VT*ln(8)/R2` (Q1 unit device,
Q2 8x, PTAT current forced by the amplifier servoing sns1=sns2 across
R2). At the baseline sizing, `R1/R2 = 694.5/82.7 = 8.40`, giving an implied
PTAT gain of `(R1/R2)*ln(8) = 17.47` — close to the ~17-20x rule-of-thumb
silicon-BJT literature value, which is why this looked like a reasonable
first-pass sizing (`design/bandgap_core.sch`'s original header comment,
predating this issue).

To tell slope from curvature, `vref(T)` was sampled at 8 points
(-40,-20,0,27,50,75,100,125 C) rather than the official testbench's 3
(-40,27,125), at the nominal (typ) and a representative worst (wcs)
corner, both at Vdd=3.30V, using a scratch harness built from the same
device set/topology as
`sim/closed-loop-vref-pvt/testbench/tb_closed_loop_vref.spice.tmpl`. (No
`sim/` plotting tool exists in this repo as of 2026-08-28 — flagged by
Curator triage on this issue — so the "plot" below is a literal ASCII
rendering of the tabulated data; the underlying values are in the tables
throughout this file.)

```
BASELINE (R1=694.5um), typ corner, 3.30V   (V range: 1.13754 - 1.20700)
  -40C  1.13754  |*
  -20C  1.14643  |      *
    0C  1.15517  |             *
   27C  1.16677  |                     *
   50C  1.17646  |                            *
   75C  1.18682  |                                   *
  100C  1.19700  |                                           *
  125C  1.20700  |                                                  *

BASELINE (R1=694.5um), wcs corner, 3.30V   (V range: 1.14208 - 1.21486)
  -40C  1.14208  |*
  -20C  1.15137  |      *
    0C  1.16051  |             *
   27C  1.17264  |                     *
   50C  1.18280  |                            *
   75C  1.19366  |                                   *
  100C  1.20434  |                                           *
  125C  1.21486  |                                                  *
```

Both curves are visibly straight lines, not bowed — per-20K-step slope at
the typ corner ranges 0.40-0.44 mV/K across the whole -40..125C span (a
~10% spread, not the multi-fold spread curvature would produce), and the
wcs corner is the same shape (0.42-0.46 mV/K). **The baseline error is
first-order-slope-dominated**: the PTAT term's positive slope is too large
relative to `VBE(Q3)`'s negative slope for `npn13G2` at this branch
current (curvature effects are present but small next to the ~360 ppm/C
overshoot). This is a real numeric difference from typical silicon-BJT
rule-of-thumb sizing, not a topology error — `npn13G2` at ~5uA/branch
needs measurably less PTAT gain than ~17.5x to null the first-order term,
consistent with CLAUDE.md's own framing that "BiCMOS is a real
difference" here.

**Per the issue's playbook** ("evaluate the standard fixes in increasing
invasiveness order: resistor-ratio retune first, then only if needed,
second-order curvature correction, stop at the first that meets the
row"): since the error is slope-dominated, the resistor-ratio retune is
evaluated first below, and (see Sec 4) it is sufficient — the more
invasive curvature-correction fallback was not needed.

## 3. Fix evaluated: R1/R2 ratio retune

`I` (the branch current) is set entirely by `R2` (`I = VT*ln(8)/R2`);
`R1` only sets `vref`'s DC level and its PTAT contribution. So retuning
`R1` alone (holding `R2` fixed) changes `vref` and its TC without moving
the design current — a pure-resistor-ratio retune, the least invasive fix
on the issue's own escalation ladder, with no amplifier/topology impact.

`R1`'s length was swept (typ corner, Vdd=3.30V, endpoint-method TC over
-40/27/125C) to find the zero-TC crossing:

| R1 length (um) | R1/R2 | PTAT gain (R1/R2\*ln8) | vref(27C) | TC (ppm/C, endpoint) |
|---|---|---|---|---|
| 694.5 (baseline) | 8.40 | 17.47 | 1.16677 | 360.799 |
| 600 | 7.26 | 15.09 | 1.10468 | 184.998 |
| 500 | 6.05 | 12.57 | 1.03891 | -24.268 |
| 505 | 6.11 | 12.70 | 1.04220 | -13.201 |
| 510 | 6.17 | 12.82 | 1.04549 | -2.145 |
| **511** | **6.18** | **12.85** | **1.04615** | **0.058** |
| 515 | 6.23 | 12.95 | 1.04878 | 8.784 |
| 550 | 6.65 | 13.83 | 1.07181 | 83.631 |
| 400 | 4.84 | 10.06 | 0.97305 | -262.305 |
| 300 | 3.63 | 7.54 | 0.90712 | -535.342 |

The endpoint-method zero crossing sits between R1=510 and R1=511um;
**R1=511um** (nearest length to the crossing, keeping the same `rppd`
flavor/width as R2, `w=2u`) was selected as the retuned value.

## 4. Retuned design: per-corner verification

### 4a. Official testbench evidence (3-temperature-point endpoint method, matches existing sim/ convention)

`design/bandgap_core.sch` / `design/netlist/bandgap_core.spice`: `R1`
`rppd w=2u l=694.5u` -> `rppd w=2u l=511u` (R2 unchanged).
`sim/closed-loop-vref-pvt/testbench/tb_closed_loop_vref.spice.tmpl`'s
embedded DUT copy updated to match (see "Testbench-DUT sync debt" below —
this template hand-copies the core netlist rather than including the live
file, same as 7 other `sim/*/testbench/*.tmpl` files).

Re-run: `sim/closed-loop-vref-pvt/records/20260828-191918-4e4a2c8*`
(design/netlist/bandgap_core.spice @ `4832c71` — see the git-sha caveat
in that record's own provenance section; this PR's commit is the first to
actually carry the new `l=511u` value, so the record's `%h` stamp reflects
`HEAD` at generation time, one commit behind, per this repo's established
run-then-commit convention). **45/45 points PASS** (same startup-release /
loop-closure / not-railed / settledness criteria as the baseline record).

| corner | vdd | vref(-40C) | vref(27C) | vref(125C) | TC (ppm/C) |
|---|---|---|---|---|---|
| typ | 2.97 | 1.04437 | 1.04582 | 1.04442 | 0.290 |
| typ | 3.30 | 1.04469 | 1.04615 | 1.04470 | 0.058 |
| typ | 3.63 | 1.04494 | 1.04633 | 1.04469 | -1.448 |
| bcs | 2.97 | 1.04149 | 1.04211 | 1.03948 | -11.690 |
| bcs | 3.30 | 1.04180 | 1.04242 | 1.03974 | -11.977 |
| bcs | 3.63 | 1.04203 | 1.04258 | 1.03968 | -13.661 |
| wcs | 2.97 | 1.04881 | 1.05157 | 1.05211 | 19.019 |
| wcs | 3.30 | 1.04915 | 1.05191 | 1.05243 | 18.898 |
| wcs | 3.63 | 1.04941 | 1.05211 | 1.05246 | 17.569 |
| sf | 2.97 | 1.04441 | 1.04587 | 1.04448 | 0.406 |
| sf | 3.30 | 1.04472 | 1.04619 | 1.04474 | 0.116 |
| sf | 3.63 | 1.04496 | 1.04635 | 1.04471 | -1.448 |
| fs | 2.97 | 1.04433 | 1.04576 | 1.04435 | 0.116 |
| fs | 3.30 | 1.04466 | 1.04610 | 1.04466 | 0.000 |
| fs | 3.63 | 1.04492 | 1.04630 | 1.04466 | -1.506 |

All 15 groups are within `[-13.7, +19.0] ppm/C` — inside the drafted
`< 50 ppm/C` row by a wide margin, using the same endpoint-method
convention the repo's own testbench script already implements.

### 4b. Curvature caveat: the official 3-point grid understates the true box TC here

Near the first-order-cancellation point, `vref(T)` is **no longer
monotonic** — the near-zero endpoint-method numbers above (e.g. typ:
0.058 ppm/C) are an artifact of the -40C and 125C endpoints landing close
together while the curve actually bows through an interior extremum. The
issue explicitly asks for the **box method** (`(vmax-vmin)/(vref(27C)*165)`
over the true sampled extrema, not just the two endpoints), so the same
8-temperature-point scan from Sec 2 was re-run post-retune, at Vdd=3.30V
(representative — the official 45-point sweep above shows <2 ppm/C
spread across Vdd within any one corner, so Vdd was not re-scanned at
fine grain):

```
RETUNED (R1=511um), typ corner, 3.30V   (V range: 1.04469 - 1.04617)
  -40C  1.04469  |*
  -20C  1.04535  |                      *
    0C  1.04582  |                                      *
   27C  1.04615  |                                                 *
   50C  1.04617  |                                                  *
   75C  1.04594  |                                          *
  100C  1.04544  |                         *
  125C  1.04470  |*

RETUNED (R1=511um), wcs corner, 3.30V   (V range: 1.04915 - 1.05266)
  -40C  1.04915  |*
  -20C  1.05020  |               *
    0C  (did not converge -- see note below)
   27C  1.05191  |                                       *
   50C  1.05239  |                                              *
   75C  1.05266  |                                                  *
  100C  1.05266  |                                                  *
  125C  1.05243  |                                               *
```

Both are now a "frown" (concave-down, interior maximum) rather than a
straight ramp — the expected shape once the first-order slope is
nulled and curvature is what remains. Box-method TC computed from every
converged fine-grid point (Vdd=3.30V):

| corner | vmin (T) | vmax (T) | TC_box (ppm/C) |
|---|---|---|---|
| typ | 1.04469 (-40C) | 1.04617 (50C) | 8.574 |
| bcs | 1.03974 (125C) | 1.04242 (0C) | 15.640 |
| wcs | 1.04915 (-40C) | 1.05266 (75/100C) | ~20.2 |
| sf  | 1.04472 (-40C) | 1.04619 (27C) | 8.514 |
| fs  | 1.04466 (-40/125C) | 1.04610 (50C) | 8.459 |

Worst case is **wcs at ~20.2 ppm/C** — still less than half the drafted
`< 50 ppm/C` budget. (One fine-grid point, wcs/T=0C, did not converge in
the scratch harness — the same kind of isolated single-point transient
non-convergence the official testbench's own header documents as expected
at marginal PVT corners near the startup ramp's near-singular early
instant; the same non-convergence pattern reproduces at the *baseline*
R1 value too, e.g. typ/3.63V/T=0C in an identical scratch re-run, so it
is pre-existing testbench brittleness, not something this retune
introduced. The missing point sits between two converged neighbors
(-20C: 1.05020, 27C: 1.05191) and cannot plausibly exceed the box already
bounded by the other 7 points.)

**Conclusion: the resistor-ratio retune alone (R1: 694.5um -> 511um)
meets the drafted `< 50 ppm/C` TC row across all evaluated corners, by
both the official testbench's endpoint method and a curvature-inclusive
box-method check. The more invasive second-order curvature-correction
fallback was not needed** — per the issue's own instruction to "stop at
the first fix that meets the row."

## 5. Side effects and follow-ups (explicitly out of scope for this issue)

- **Output-reference row moves further from its own draft target.**
  `vref` drops from ~1.166V (typ/27C/3.30V, baseline) to ~1.046V (same
  point, retuned) — this retune trades TC-row conformance for a bigger
  miss on the separately-tracked `~1.2V` Output-reference row (issue
  #133, EE key's other PR #128 finding). This is a known, real tradeoff
  inherent to a 2-BJT Brokaw core's single degree of freedom (`R1/R2`
  sets both `vref`'s level and its first-order TC simultaneously) — not
  something this issue's scope (TC only) can or should resolve. No
  `spec/` edit was made for either row, per this issue's AC.
- **Layout desync.** `layout/bandgap_core`'s committed GDS/DRC/LVS/PEX
  artifacts were drawn for `R1` at `l=694.5um` (see `layout/README.md`).
  This schematic-level fix does not regenerate that layout — a follow-up
  klayout-tools-side issue is needed to re-draw/re-extract
  `layout/bandgap_core` against the new `R1` length before any layout-level
  (PEX) PVT evidence can be trusted again.
- **Testbench-DUT sync debt.** `tb_closed_loop_vref.spice.tmpl` (this
  issue's testbench) hand-embeds a "verbatim" copy of
  `design/netlist/bandgap_core.spice` rather than including the live file,
  and was updated in this PR to match. Seven other
  `sim/*/testbench/*.tmpl` files do the same thing and were **not**
  touched here (out of scope for a TC-only fix) — they now embed a stale
  `R1=694.5u` copy of the core DUT relative to the current schematic. This
  is a structural gap (each new experiment re-copies the DUT by hand, with
  nothing that flags drift when the schematic changes) worth its own
  follow-up issue.

## Reproduction

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/closed-loop-vref-pvt/run_pvt_sweep.sh
```

The fine-grid (8-temperature-point) box-method scan in Sec 2/4b was a
one-off scratch harness (same device set/topology/options as
`tb_closed_loop_vref.spice.tmpl`, extra temperature points only) — not
committed as new `sim/` infrastructure, since the official 3-point
testbench already gives the endpoint-method table this repo's other PVT
experiments use, and generalizing the fine-grid scan into shared `sim/`
infra is better scoped as its own follow-up than folded into this fix.
