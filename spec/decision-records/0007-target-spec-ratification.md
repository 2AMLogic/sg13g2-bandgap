# 0007: Target-spec table ratification (`README.md`), refreshed for the R1=511µm retune and N=300 Monte Carlo

- **Status**: ratified
- **Date**: 2026-09-15
- **Decided by**: Loom Builder agent, issue #150 (supersedes the
  `feature/issue-125` draft ratification, PR #128)

## Context

`spec/porting-plan.md` §6 drafted a starting target-spec table for this
block, carried over largely unchanged from `gf180-bandgap`/`sky130-bandgap`'s
own ratified tables. `README.md` republished that table under a
`DRAFT — engineering to ratify` heading pending issue #125.

PR #128 (branch `feature/issue-125`) attempted this ratification on
2026-08-27, citing `sim/closed-loop-vref-pvt/records/20260826-103022-014570b.md`
(Output reference, TC), `sim/closed-loop-psrr/records/20260826-114500-874c585.md`
(PSRR), and `sim/closed-loop-iq/records/20260826-152134-9b7a6de.md` (Iq). That
evidence predates two committed changes that materially move the numbers it
argues from:

1. **Issue #134 / PR #136 / PR #138** (2026-08-28): retuned the `R1`/`R2`
   resistor ratio (`R1: 694.5µm → 511µm`, `design/bandgap_core.sch`, verified
   live at `l=511u` on `main` as of this record) specifically to close the
   Temp-coefficient row's gap. This traded away Output-reference accuracy —
   `vref` moved from ~1.16–1.17 V (PR #128's cited numbers) to ~1.04–1.06 V
   across PVT.
2. **Issue #215 / PR #216** (2026-09-09): added `sim/closed-loop-vref-mc/`, a
   seeded N=300 device-mismatch Monte Carlo of the closed-loop untrimmed
   `vref` operating point at the current `R1=511µm` sizing — a statistical
   dimension to the Output-reference row that did not exist when PR #128 was
   drafted.

Issue #150 tracks this staleness (itself a re-finding of issue #139, whose
own fix, PR #140, added only a sim-side note rather than updating PR #128's
committed content). The operator ruled (issue #150, 2026-09-15, "Revision
2026-09-14 (operator lane)") that a spec ratification is not an operator
task (standing ruling `2AMLogic/2am#357`) and that PR #128's branch should
not be rebased — instead, this record and its accompanying `README.md` edit
are drafted fresh from current `main` to supersede PR #128, with every row
citing currently-committed evidence. PR #128 should be closed once this
record's PR merges.

Numbering note: `0006` is already taken on `main`
(`0006-post-layout-psrr-hf-resonance.md`, issue #191, 2026-09-06) — this
record is `0007` per `TEMPLATE.md`'s numbering rule (next unused number),
not `0006` as PR #128's stale draft used.

## Decision

**The target-spec table in `README.md`'s "Target specification" section is
ratified as this block's official spec**, effective this record. The
heading changes from `DRAFT — engineering to ratify, see issue #125` to
`RATIFIED, with one row explicitly unmet`. No target *number* in the table
changes from the draft `spec/porting-plan.md` §6 values — per `CLAUDE.md`
and `spec/README.md`, this repo does not relax a spec to make results pass.

Ratifying the table locks in these target numbers, evaluated honestly
against the currently-committed evidence below — **it is not a claim that
every row is currently met.** Per-row evidence status, recommendation (one
of: ratify as-is / ratify with row explicitly flagged unmet / re-target),
and the evidence it is based on:

- **Output reference** (~1.2 V ±1% untrimmed): **ratify with this row
  explicitly flagged unmet — the block's most significant known gap.**
  Post-retune closed-loop evidence, both pre-layout
  (`sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md`, nominal
  27°C/3.30V: `vref` = 1.04947 V) and post-layout PEX
  (`sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md`,
  nominal: `vref` = 1.05048 V, max |Δ vs. schematic| = 0.00167 V across all
  45 points), puts untrimmed `vref` at **~12.5–13.1% below the 1.2 V
  nominal across the entire 45-point PVT grid** — worse than PR #128's cited
  pre-retune ~2.3–3.1% miss, and **0/45 points now land inside the ±1%
  band** `[1.188 V, 1.212 V]` (PEX record), down from PR #128's own 12/45 —
  because the retune flattened TC across PVT rather than concentrating
  `vref` near 1.2 V at the hot corners the way the pre-retune, TC-dominated
  design happened to. This is a real, understood trade-off (see
  "Output-reference-vs-TC trade-off" below), not a regression from a design
  error.
  The N=300 device-mismatch Monte Carlo
  (`sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md`) adds a
  statistical dimension PR #128 never had: at the nominal point, untrimmed
  `vref` mean = 1.046711 V with 3σ/mean ≈ 13.0% — only 20.7% of draws land
  within ±1% of *that draw population's own mean* (not of the 1.2 V
  target), 10.3% within ±0.5%. Process corners (bcs/wcs × −40/125°C) show
  comparable 12.1–14.6% 3σ/mean spread. This means even a perfectly-trimmed
  nominal-mean design would still see real, uncorrected device-mismatch
  scatter of this magnitude — a second data point (distinct from the
  systematic miss above) that a future trim network must also budget for,
  not just cancel a fixed offset.
  `design/README.md`'s "Explicitly out of scope" section (issue #9) already
  documents no trim network exists in this design's first pass; this
  remains open follow-on work, not a target change.
- **Temp coefficient** (< 50 ppm/°C target, < 20 ppm/°C stretch): **ratify
  as-is — now meets target AND stretch.** This is the row the R1=511µm
  retune (issue #134) was built to fix. Pre-layout
  (`sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md`): informal
  endpoint-method TC across the 15 corner/supply groups ranges
  **−14.4…18.1 ppm/°C**. Post-layout PEX
  (`sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md`):
  **−17.6…15.5 ppm/°C**. Both are inside the 20 ppm/°C stretch target, a
  large improvement from PR #128's cited pre-retune ~349–376 ppm/°C (7x+
  over the 50 ppm/°C target).
- **PSRR @ DC** (> 60 dB target, > 70 dB stretch): **ratify as-is — meets
  target on the most current (post-layout) evidence; stretch not met.**
  Post-layout PEX
  (`sim/closed-loop-psrr-pex/records/20260905-233826-f6f3efc.md`): DC PSRR
  ranges **60.20–105.71 dB across all 45 points — 45/45 clear the 60 dB
  target** (worst case 60.20 dB, `bcs_125c_3.63v`); 35/45 fall short of the
  70 dB stretch. Pre-layout, post-retune
  (`sim/closed-loop-psrr/records/20260830-133912-d83f7c4.md`): DC PSRR
  ranges 59.68–100.40 dB, with 2/45 points (both within 0.4 dB of the line)
  marginally short of 60 dB — the PEX extraction's added parasitics are
  what push those two points over the line, which is why the post-layout
  number is treated as the more trustworthy evidence for this
  recommendation. This is a substantial improvement over PR #128's cited
  pre-retune 57.1–105.2 dB / 20-of-45-below-60dB.
  Separately,
  [`spec/decision-records/0006-post-layout-psrr-hf-resonance.md`](0006-post-layout-psrr-hf-resonance.md)
  documents a narrowband (27.1–31.6 MHz) transmission-zero effect where
  post-layout PSRR dips to a local minimum of −2.15…−0.84 dB (i.e. slight
  ripple amplification) before recovering — a real, accepted-as-is,
  away-from-DC finding that does not affect this DC-scoped row (that record
  already decided not to add an away-from-DC spec bound, deferring to this
  ratification pass, which likewise does not add one: no requirement in
  this repo's draft spec currently anticipates bounding PSRR above DC).
- **Supply** (3.3 V ±10% HV / 1.2 V LV stretch): **ratify as-is — met by
  construction, unchanged from the original ratification argument.**
  Grounded directly in the SG13G2 device menu's voltage ratings, not a
  simulated result
  ([`0002-supply-voltage-scope.md`](0002-supply-voltage-scope.md)); every
  closed-loop PVT record cited in this document sweeps exactly the
  2.97/3.30/3.63 V grid this row specifies.
- **Iq** (< 50 µA target, < 20 µA stretch): **ratify as-is — meets target
  with margin; pre-layout evidence only (real, disclosed gap).**
  `sim/closed-loop-iq/records/20260830-133900-d83f7c4.md` (current,
  post-retune): settled Iq ranges **19.88–42.16 µA** across the 45-point
  grid — under the 50 µA target at every corner (~16% margin at the
  worst-case corner), touching the 20 µA stretch only at the
  coldest/lightest-load corner. No `closed-loop-iq-pex` (post-layout)
  testbench exists yet in `sim/` — a genuine gap this record discloses
  rather than papers over. Judgment call (not mechanically resolvable from
  existing evidence): Iq is a DC bias-current quantity set primarily by
  `R2` and device sizing rather than by wire parasitics, and the retune did
  not touch `R2` or any current-mirror device, so the schematic-level
  margin is judged likely to survive extraction — but this is a
  recommendation for the two-key reviewers to weigh, not a substitute for
  running the PEX experiment.
- **Startup** (self-starting, < 1 ms): **ratify as-is — meets target with
  ~10x margin, corroborated at both schematic and post-layout levels.**
  `sim/closed-loop-startup/records/20260830-132425-d83f7c4.md` (current,
  post-retune schematic): 45/45 PASS on self-start/loop-closure.
  `sim/startup-time-to-release/records/20260904-184431-6fa83b4.md` (issue
  #4 T1-checklist follow-up, filed directly in response to PR #128's own
  EE-key finding that no testbench reported an explicit time-to-release
  number): 45/45 PASS, with **every PVT point releasing by the very first
  100 µs checkpoint** — comfortably inside the < 1 ms target at ~10x
  margin, closing the exact evidence gap PR #128's decision record left
  open.
  `sim/startup-trip-point-pex/records/20260905-033740-fe97115.md`
  (post-layout, issue #14/#32): 45/45 PASS confirming the startup circuit's
  own release behavior survives layout extraction, though the specific
  time-to-release figure above has not been separately re-measured at the
  PEX level. Judgment call: given the ~10x schematic-level margin and
  PEX-confirmed release behavior, this residual gap is judged non-blocking
  for ratification, but is disclosed here rather than silently assumed
  away.

### Output-reference-vs-TC trade-off

The R1=511µm retune is a genuine trade, not a free improvement: it moves
this design from "TC fails badly, Output-reference nearly meets target" to
"TC passes with margin, Output-reference misses badly." Both cannot be
satisfied simultaneously by this resistor-ratio-only retune (the same
constraint `design/bandgap_core.sch`'s own comments document, issue #134).
Closing the Output-reference gap without reopening the TC gap requires a
trim network (issue #9's scope cut) or a different core topology change —
neither of which this record proposes; both are recommended as open
follow-on design work for whoever picks up the Output-reference gap next.
The two-key reviewers may instead prefer a **re-target** of the
Output-reference row (e.g. loosening the untrimmed accuracy target, or
retargeting the nominal `vref` value itself to something nearer the
retuned design's natural operating point) as an alternative to "flagged
unmet + trim network" — that is explicitly not decided here; per
`CLAUDE.md`/`spec/README.md` this repo does not relax a spec unilaterally to
make results pass, so any re-target must be its own deliberate, reviewed
decision, not a byproduct of this ratification pass.

## Alternatives considered

- **Rebase or push directly to `feature/issue-125` / PR #128.** Rejected per
  the operator's explicit ruling on issue #150 (2026-09-15): open a fresh PR
  from current `main` that supersedes PR #128 instead of touching its
  branch.
- **Leave the table in DRAFT status until the Output-reference gap
  closes.** Rejected for the same reason PR #128's own (superseded) record
  rejected it: `spec/README.md` treats ratification as locking in the
  *target numbers* so downstream work can proceed against a stable
  reference, not as a certification that every row is already met — this
  block's own maturity ladder already distinguishes "spec ratified" from
  "design done."
- **Relax the Output-reference, TC, or PSRR targets to match measured
  results.** Rejected outright per `CLAUDE.md`/`spec/README.md`: this repo
  does not relax a spec, draft or ratified, to make results pass. A
  re-target is named above as an option for the two-key reviewers to
  consider explicitly, not something this record does unilaterally.
- **Wait for a `closed-loop-iq-pex` / PEX-level startup-time-to-release
  experiment before ratifying.** Rejected as out of scope for this
  record — both are judgment calls disclosed explicitly above (not
  mechanically resolvable from existing evidence), and per the operator's
  build plan this record's job is to make the ratification's inputs current
  and honest, not to run new simulations. Recommended as candidate future
  follow-on work.

## Consequences

- **`README.md`'s target-spec table is now the block's ratified spec**,
  with every row's evidence status current as of 2026-09-15 (`R1=511µm`,
  post-#134-retune, post-#215 Monte Carlo, post-#191 PEX PSRR/Zout).
  Future testbenches and decision records can cite it directly as "the
  ratified target."
- **PR #128 (`feature/issue-125`) is superseded** by this record and its
  accompanying PR — its cited evidence predates the R1 retune and the N=300
  Monte Carlo and should not be used for the ratification decision going
  forward. It should be closed once this record's PR merges (not done by
  this record itself — a human/Champion action per the PR body).
- **Two follow-on gaps remain open, tracked here rather than resolved
  here**: (1) a trim network to close the Output-reference gap (issue #9's
  explicit scope cut, now re-quantified against both a systematic ~12.5–13%
  miss and a ~13% 3σ/mean mismatch-driven scatter), and (2) two disclosed,
  non-blocking pre-layout-only/PEX-level evidence gaps (`closed-loop-iq-pex`
  does not exist; `startup-time-to-release` has no PEX-level counterpart).
  None of these are scheduled or resolved by this record.
- **No `sim/` evidence or testbench is invalidated.** Every cited record's
  own README already disclaimed spec-conformance before this ratification;
  this record does not change any of those records' own claims, only
  formalizes which numbers they are now implicitly evaluated against.
- **The two-key review mechanism (`ratification/ee-key`,
  `ratification/market-key`) still gates the actual merge decision** for
  this record's PR — this record does not pre-empt or substitute for that
  review, including on the Output-reference re-target option raised above.
