# 0009: Box-method TC on committed testbenches — the stretch column's honest boundary

- **Status**: proposed (this record changes no target number — see "What
  this record does not do")
- **Date**: 2026-09-21
- **Decided by**: Loom Builder (agent), issue #222

## Context

The two-key ratification review of `0007` (PR #220, EE key
`request-changes`) found the TC row's `< 50 ppm/°C` target sound but its
`< 20 ppm/°C` **stretch** claim unsupported by the evidence then on
record: the committed 3-temperature-point sweeps compute the **endpoint
method**, and this repo's own analysis
(`measurements/2026-08-tc-retune/README.md` §4b) showed the endpoint method
understates TC once the `R1=511 µm` retune nulls the first-order slope and
`vref(T)` bows through an interior maximum — §4b's 8-point scratch-harness
scan put the worst **box-method** corner at ~20.2 ppm/°C (`wcs`, 3.30 V,
pre-layout, one grid point not converged). `0008` carried that caveat into
`README.md`'s row status. Issue #222 existed to close the evidence gap:
make the box method a first-class committed measurement (schematic and
PEX), resolve the §4b non-convergence, and state the box-method worst
corner explicitly, whichever side of 20 ppm/°C it lands on.

## Measurement

Two new committed experiments (each 120 points: corner {typ, bcs, wcs, sf,
fs} × temperature {-40, -20, 0, 27, 50, 75, 100, 125} °C × supply
{2.97, 3.30, 3.63} V, 8-point grid = §4b's grid; per-point netlists
byte-identical from the `.lib` line down to the official endpoint-method
benches, so the two methods read from the same testbench):

- `sim/closed-loop-vref-pvt-boxtc/` (record `20260921-194249-77820fc`):
  120/120 PASS. Box TC 8.90-19.77 ppm/°C across the 15 groups; worst
  corner **`wcs`/3.30 V = 19.765 ppm/°C** (vmax @ 75 °C, vmin @ −40 °C).
  Parabolic-vertex bound through the bracketing 50/75/100 °C points:
  true peak ≈ +20 µV above the sampled max (≈ 84.7 °C), vertex-corrected
  box ≈ 19.88 ppm/°C — still inside 20.
- `sim/closed-loop-vref-pvt-pex-boxtc/` (record `20260921-195122-77820fc`):
  120/120 PASS. Box TC 10.56-20.14 ppm/°C; worst corner
  **`bcs`/3.63 V = 20.137 ppm/°C** (vmax @ 0 °C, vmin @ 125 °C; the
  sampled max sits ~2 °C from its own parabolic vertex, so the overshoot
  is not a sampling artifact — vertex-corrected ≈ 20.14). Post-layout the
  worst corner **moves** from `wcs` (which improves by −1.7…−2.0) to `bcs`
  (which degrades by +2.3…+2.5 along with typ/sf/fs) — the wire-parasitic
  series-R shift `sim/closed-loop-vref-pvt-pex` already documents moves
  each corner's `vref(T)` series slightly and differently, and at the
  boundary those shifts flip which corner binds.

**The §4b non-convergence resolved by convergence**: `wcs/0 °C` — the one
grid point the §4b scratch harness could not converge — converged under
both new official-harness benches at both levels; every group reads
`n_pass == n_grid == 8`. No bounding argument is needed; §4b's is retired.

**§4b cross-check** (issue #222's test plan, 3.30 V, schematic): typ
9.067 vs 8.574, bcs 16.454 vs 15.640, wcs 19.765 vs ~20.2, sf 9.122 vs
8.514, fs 9.069 vs 8.459 ppm/°C — every |Δ| < 1 ppm/°C (the materiality
bar the experiment README sets, well above observed solver noise).
Consistent; no finding. The scratch scan's `~20.2` and the committed
`19.765` agree within that bar; the scratch number's extra ~0.4 ppm/°C is
consistent with its missing 0 °C point and hand-transcribed setup.

## Decision

The ratified TC row's numbers are unchanged. Its status prose, from this
record on, states the box-method worst corner explicitly at both levels:

- **Target `< 50 ppm/°C`: met** at both levels by both methods — the worst
  number anywhere is the post-layout box 20.1 ppm/°C, >2.4× inside.
- **Stretch `< 20 ppm/°C`: at the boundary, and level-dependent.** Met by
  the endpoint method at both levels (worst |TC| 18.1 pre-layout / 17.6
  post-layout). By the box method: **pre-layout worst 19.8 ppm/°C** —
  just inside (~1% margin, ~0.6% after the vertex bound) — and
  **post-layout worst 20.1 ppm/°C** — just outside (~0.7%). Honest
  summary: the design sits *on* the 20 ppm/°C stretch line; whether a
  given box-method measurement reads inside or outside depends on layout
  state and corner, not on a comfortable margin either way.

The box method is the appropriate assessment metric for this row's
stretch claim going forward (the endpoint method's near-zero readings
post-retune are an endpoint-averaging artifact, quantified per-group in
the new records), and `README.md`'s TC-row status cites the committed
records rather than §4b's scratch scan.

## Alternatives considered

- **Keep assessing the stretch by the endpoint method** — rejected: the
  repo's own §4b analysis (now confirmed by committed records at all 15
  groups × 2 levels) shows the endpoint method systematically understates
  TC here; a stretch claim resting on it would be the exact unsupported
  claim the EE key flagged.
- **Treat 19.8/20.1 as "met" outright (or "failed" outright)** — rejected:
  the margin on both sides is ~1%, inside any honest engineering margin
  for an untrimmed bandgap; the boundary is the finding, and the
  level-dependence (wcs→bcs flip) is real information for any future
  trim/curvature work.
- **Re-open the stretch number itself** — out of scope: issue #222's AC
  forbids target changes, and no evidence here motivates one; a future
  trim network (tracked separately) would change the measured numbers,
  not the row.

## Consequences

- The stretch column is honestly bounded: any future claim that it is
  "met" must cite the box method at the level being claimed, and must
  survive the ~1% boundary (a trim network or curvature correction would
  be the design responses; neither is warranted by this record alone).
- TC-row evidence refreshes after design changes now need the 8-point
  grid (120 points/level) rather than only the 45-point endpoint sweep —
  the two new experiments carry that cost, deliberately kept out of the
  official benches (see `sim/closed-loop-vref-pvt-boxtc/README.md`'s
  "Why a sibling experiment" section).
- The worst-corner flip (`wcs` pre-layout → `bcs` post-layout) means
  layout-level evidence is the binding one for this row: pre-layout-only
  refreshes can under- or over-state the boundary by ~2 ppm/°C at the
  corners that move.
- §4b's scratch scan is superseded as evidence by the committed records;
  `measurements/2026-08-tc-retune/README.md` stays as the historical
  analysis that predicted exactly this shape (and is now cross-checked
  consistent with the committed numbers).

## What this record does not do

No target or stretch number changes; no spec-row disposition flips; no
re-ratification is triggered (the two-key review of `0007`/`0008` already
put the stretch caveat on the record — this record replaces the scratch
citation with committed measurements, per issue #222's charter).
