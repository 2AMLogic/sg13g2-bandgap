# 0006: Target-spec table ratification (`README.md`), with an honest evidence status per row

- **Status**: ratified
- **Date**: 2026-08-27
- **Decided by**: Builder agent, issue #125
- **Related**: #13 (original ratification issue, closed `NOT_PLANNED` —
  operator ruling quoted in #125 removes the block that issue's open status
  previously represented), #125 (this ratification), #9 (trim-network
  explicit scope cut), `spec/porting-plan.md` §6 (the draft target-rationale
  table these values were carried over from unchanged), `0001-bipolar-device-selection.md`,
  `0002-supply-voltage-scope.md` (the two prior decision records already
  feeding this table)

## Context

`spec/porting-plan.md` §6 drafted a starting target-spec table for this
block, carried over largely unchanged from `gf180-bandgap`/`sky130-bandgap`'s
own ratified tables, explicitly flagged at the time as "not yet
SG13G2-verified" for every row except Supply (already grounded via
`0002-supply-voltage-scope.md`). `README.md` republished that same table
under a `DRAFT — engineering to ratify, see issue #13` heading, and
`spec/README.md` states the ratified table "will live in the top-level
`README.md`" once ratification happens.

Issue #13 (the original ratification-tracking issue) closed `NOT_PLANNED`;
issue #125's body carries an operator ruling that cutting this ratification
PR is now ordinary agent work, not blocked on further discussion. Since
issue #13 closed, substantial SG13G2-specific closed-loop evidence has
landed that did not exist when §6 was drafted: full-PVT (45-point)
closed-loop testbenches for `vref`/TC
(`sim/closed-loop-vref-pvt/records/20260826-103022-014570b.md`), PSRR
(`sim/closed-loop-psrr/records/20260826-114500-874c585.md`), and Iq
(`sim/closed-loop-iq/records/20260826-152134-9b7a6de.md`), plus startup/
loop-closure evidence from `sim/closed-loop-startup/`. This record ratifies
the table against that evidence, rather than against the draft's original
"not yet SG13G2-verified" caveat.

## Decision

**The target-spec table in `README.md`'s "Target specification" section is
ratified as this block's official spec**, effective this record. The
heading changes from `DRAFT — engineering to ratify, see issue #13` to
`RATIFIED`. No target *number* in the table changes from the draft
`spec/porting-plan.md` §6 values — per `CLAUDE.md` and `spec/README.md`,
this repo does not relax a spec (draft or ratified) to make results pass,
and none of the gaps found below are treated as grounds to renumber a row.

Ratifying the table is a statement that these are the block's locked-in
target numbers going forward, evaluated honestly against real SG13G2
evidence — **it is explicitly not a claim that every row is currently
met.** The evidence status, as of this record:

- **Output reference** (~1.2 V ±1% untrimmed): **short of target.**
  `sim/closed-loop-vref-pvt/records/20260826-103022-014570b.md` measures
  `vref` at 27 °C settling to 1.162–1.173 V — 2.3–3.1% below the 1.2 V
  nominal, outside the ±1% untrimmed band. Only 12/45 PVT points land
  inside [1.188 V, 1.212 V] at all, concentrated at the 125 °C corners
  where untrimmed TC drift happens to carry `vref` back up near 1.2 V — not
  because the design is accurate at its nominal operating condition. Same
  root cause as the TC row below (no trim network).
- **Temp coefficient** (< 50 ppm/°C target, < 20 ppm/°C stretch): **short
  of target, with a known, documented, not-yet-closed cause.** The same
  record's informal endpoint-method TC computation reads ~349–376 ppm/°C
  across the 15 corner/supply groups this run covers — 7x+ over target.
  `design/README.md`'s "Explicitly out of scope" section (issue #9) already
  documents that no trim network exists in this design's first pass, and
  that an untrimmed `VBE`-based bandgap's TC is normally in the
  hundreds-of-ppm/°C range without one. This is a known gap against the
  ratified target, tracked as open follow-on work (a future trim-network
  issue), not a target change.
- **PSRR @ DC** (> 60 dB target, > 70 dB stretch): **does not uniformly
  meet target across PVT.** `sim/closed-loop-psrr/records/20260826-114500-874c585.md`
  measures DC PSRR of 57.1–105.2 dB across the 45-point grid: 20/45 points
  fall below the 60 dB target (worst case 57.1 dB), 37/45 fall below the
  70 dB stretch, and only 8/45 clear 70 dB. That testbench's own README
  attributes the small cluster of high (80–105 dB) readings to a
  bias-point-specific near-cancellation at 27 °C/3.63 V (a genuine sign
  change in the net `vdd`-to-`vref` transfer function in that narrow supply
  window), not typical behavior — most corners/supplies read 57–70 dB.
  Needs further corner-by-corner design work (e.g. a cascode/PSRR-
  improvement output stage, already named as out-of-scope-for-now in
  `design/README.md`), not just more simulation.
- **Supply** (3.3 V ±10% HV / 1.2 V LV stretch): **met by construction.**
  Grounded directly in the SG13G2 device menu's `V_GS` ratings, not a
  simulated result (`0002-supply-voltage-scope.md`); every closed-loop PVT
  record above sweeps exactly the 2.97/3.30/3.63 V grid this row specifies.
- **Iq** (< 50 µA target, < 20 µA stretch): **meets target.**
  `sim/closed-loop-iq/records/20260826-152134-9b7a6de.md` measures settled
  Iq of 19.98–42.37 µA across the 45-point grid — under 50 µA at every
  corner, and touches the 20 µA stretch only at the coldest/lightest-load
  corner.
- **Startup** (self-starting, < 1 ms): **plumbing verified across PVT; the
  precise time-to-release number is not yet reported.**
  `sim/closed-loop-startup/`, `sim/closed-loop-vref-pvt/`, and
  `sim/closed-loop-iq/` all show 45/45 PASS on self-start/loop-closure by
  their measured checkpoints (fully released and settled by `t=2ms`/`t=3ms`
  in each testbench's own transient). No committed testbench yet reports an
  explicit measured time-to-release figure to compare directly against the
  < 1 ms target — a real remaining evidence gap on this row, distinct from
  the TC/PSRR gaps above (this one is a missing measurement, not a known
  design shortfall).

## Alternatives considered

- **Leave the table in DRAFT status until every row's evidence gap closes.**
  Rejected — `spec/README.md` and issue #13's disposition both treat
  ratification as locking in the *target numbers* so downstream work (spec-
  gated testbenches, epic #4's checklist, issue #15) can proceed against a
  stable reference, not as a certification that the design already meets
  every row. Blocking ratification on closing TC/PSRR/output-reference gaps
  would conflate "the spec is decided" with "the design is done" — two
  different milestones this repo's own maturity ladder already
  distinguishes.
- **Relax the TC, output-reference, or PSRR targets to match measured
  results.** Rejected outright per `CLAUDE.md`/`spec/README.md`: this repo
  does not relax a spec, draft or ratified, to make results pass. The gaps
  above are recorded as follow-on design work, not renumbered away.
- **Silently drop the "Evidence status" detail and just flip the
  heading.** Rejected — `README.md`'s own maturity-ladder language and this
  block's "verification is the product" premise (`CLAUDE.md`) both require
  that a ratified table be read alongside what current evidence actually
  says about it, not presented as if every row were already met.

## Consequences

- **`README.md`'s target-spec table is now the block's ratified spec** —
  future testbenches and decision records can cite it directly as "the
  ratified target" rather than as a draft pending ratification, and epic #4
  / issue #15 (both gated on this issue per its own acceptance criteria)
  can proceed.
- **Three follow-on gaps remain open, tracked here rather than resolved
  here**: (1) a trim network to close the TC and output-reference gaps
  (issue #9's explicit scope cut, now with a ratified target to close
  against), (2) a PSRR-improvement output stage or equivalent design work
  to bring the worst-case corners above 60 dB uniformly, and (3) an
  explicit startup time-to-release measurement to compare against the
  < 1 ms target. None of these are scheduled or resolved by this record —
  it documents status, consistent with `spec/README.md`'s instruction that
  decision records record decisions, not fixes.
- **No `sim/` evidence or testbench is invalidated.** Every cited record's
  own README already disclaimed spec-conformance before this ratification;
  this record does not change any of those records' own claims, only
  formalizes which numbers they are now implicitly evaluated against.
