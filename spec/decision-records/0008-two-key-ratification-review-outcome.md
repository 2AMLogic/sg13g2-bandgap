# 0008: Outcome of the two-key ratification review of the target-spec table (run post-hoc on PR #220)

- **Status**: proposed (this record changes no target number — see "What this
  record does not do")
- **Date**: 2026-09-18
- **Decided by**: Loom Builder agent, issue #125, recording the verdicts of the
  two non-author ratification keys

## Context

`0007-target-spec-ratification.md` (PR #220, merged 2026-09-15T11:50:47Z) flipped
`README.md`'s target-spec table from DRAFT to ratified. That record's own
"Consequences" section states: *"The two-key review mechanism
(`ratification/ee-key`, `ratification/market-key`) still gates the actual merge
decision for this record's PR — this record does not pre-empt or substitute for
that review."*

**That gate did not run before the merge.** `gh api
repos/2AMLogic/sg13g2-bandgap/pulls/220/reviews` returned an empty list, and
#220's only issue-comments were the ordinary Judge approval and its
verdict-anchor marker — no `RATIFY-KEY` verdict of the kind PR #128 (closed,
superseded) carried. Issue #125 recorded this gap; the operator ruled on
2026-09-18 that ratification is un-parked into the two-key path, that the keys
are applied with `./scripts/ratify-key.sh check` → `apply --key ee|market` →
`release`, and that whether the review runs against already-merged #220 or a
fresh PR is an implementation choice, not an operator question.

The review was run against #220, because #220 is the diff that actually made the
ratification claim, and because the Builder working #125 is not #220's author or
`0007`'s author — reviewing #220 keeps the keys genuinely non-author, where
authoring a fresh ratification PR and then reviewing it would not.

## Decision

**Record the two-key review's outcome as part of the spec's own history, and
qualify the Output-reference row's ratified status accordingly.**

Verdicts (both posted by forge-authenticated, per-key GitHub App identities —
neither is in #220's author set, and they are two distinct holders, so
`ratify-key.sh`'s non-author and distinct-holder gates both passed before
anything was written):

| Key | Holder | Verdict | Review |
|---|---|---|---|
| EE (technical soundness) | `@2am-ee-key[bot]` | `request-changes` | [pullrequestreview-5254712564](https://github.com/2AMLogic/sg13g2-bandgap/pull/220#pullrequestreview-5254712564) |
| Market (competitiveness) | `@2am-market-key[bot]` | `escalate` | [pullrequestreview-5254720800](https://github.com/2AMLogic/sg13g2-bandgap/pull/220#pullrequestreview-5254720800) |

`./scripts/ratify-key.sh release --repo 2AMLogic/sg13g2-bandgap --pr 220`
returned **`NOT-ELIGIBLE`** (exit 1) with *relax-after-measured-FAIL detected:
yes*, and wrote nothing — no `loom:auto-merge-ok`, no `loom:operator`. The
release rule (`2am` `ratification/protocol.md` §3) checks the EE verdict before
the relax-after-FAIL branch, so an EE `request-changes` short-circuits to
NOT-ELIGIBLE and the market key's `escalate` never reaches the branch that would
have applied `loom:operator`. **The escalation is therefore carried by this
record and by issues #221/#222/#223 rather than by a label** — noted explicitly
because a reader looking for the escalation label on #220 will not find one.

### What both keys agree on

Five of six rows' **target numbers** stand:

| Row | EE (soundness) | Market (competitiveness of the target) |
|---|---|---|
| Temp coefficient < 50 ppm/°C | sound (target) | `competitive` |
| PSRR @ DC > 60 dB | sound | `adequate-for-catalog` |
| Supply 3.3 V ±10% | sound | `competitive` |
| Iq < 50 µA | sound | `competitive` |
| Startup self-starting < 1 ms | sound | `adequate-for-catalog` |
| **Output reference ~1.2 V ±1% untrimmed** | **unsound** | **Step-5 gate not satisfied → `escalate`** |

Both keys independently converge on the same single row, from different angles:

- **EE:** the committed N=300 mismatch Monte Carlo
  (`sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md`) gives
  σ(vref) = 45.5 mV ⇒ 3σ/mean = 13.0% at the nominal point (12.1–14.6% at the
  bcs/wcs × −40/125 °C points). A ±1% band at 1.2 V is ±12 mV, so untrimmed ±1%
  is unreachable for this core *independently* of the ~11.9–13.1% systematic
  offset — and unreachable by the kind of resistor-ratio retune that closed the
  TC row, because mismatch scatter is not set by R1/R2. Both sibling bandgaps
  (`gf180-bandgap` `0003`, `sky130-bandgap` `DR-005`) met the numerically
  identical situation and re-cast the row (±2% untrimmed / ±0.5% trimmed) while
  adding a ratified **Trim** row; `0007` does not acknowledge that precedent,
  repeating an unreconciled finding PR #128's EE review already raised.
- **Market:** no public comp in this class publishes an *untrimmed* accuracy line
  at all — LM4040 (SLOS456Q) states its wafer-sort trim outright, REF3033-Q1
  (SBVS131) is ±0.2% post-trim, REF2030 ±0.05%, TL431 grade-binned — so the row
  as written has no public bar to be found competitive against; and measured
  against the loosest trimmed comp (LM4040 D grade, 1.0% max initial) the
  block's own evidence is ~12–13× short of the class's functional floor.

### Two evidence statements in `0007`/`README.md` that the EE key found overstated

Corrected in `README.md` by this record's PR. `0007` itself is ratified and is
**not** rewritten (`spec/README.md`'s append-only rule) — this record is where
the corrections live:

1. **Output-reference miss range.** `0007` and `README.md` state "~12.5–13.1%
   below the 1.2 V nominal across the entire 45-point PVT grid". Re-derived from
   `sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.csv`
   (`vref_3ms_v`, 45 rows): the grid is **1.04309–1.05667 V**, i.e.
   **11.94–13.08%** low, with **0/45** inside `[1.188 V, 1.212 V]`. The 0/45
   count and the upper bound are exact; the lower bound is 11.9%, not 12.5%
   (12.5% is the *nominal* point, 1.05048 V). Direction is conservative, but a
   ratification record's cited range should match its CSV.
2. **TC stretch.** `0007` states the TC row "now meets target AND stretch". The
   target (< 50 ppm/°C) is met by every method available, pre- and post-layout.
   The stretch (< 20 ppm/°C) is met only by the endpoint method
   (−14.4…18.1 ppm/°C schematic, −17.6…15.5 ppm/°C PEX — both re-derived exactly
   from the committed `-tc.csv` files), and this repo's own
   `measurements/2026-08-tc-retune/README.md` §4b is titled "*the official
   3-point grid understates the true box TC here*": post-retune `vref(T)` is
   non-monotonic, and §4b's 8-point box-method scan gives worst case **wcs
   ≈ 20.2 ppm/°C**, outside the stretch. That box scan is also pre-layout only,
   3.30 V-only, run in a scratch harness (so T1 item 9 is unmet for the box
   number), and missing one non-converged point. Tracked as #222.

### Consequent status of the table

The table's six **target numbers are unchanged** by this record, and nothing here
relaxes a spec to make a result pass. What changes is the honesty of the status
annotation: the Output-reference row's ratified value **and** its
"ratify-with-row-flagged-unmet" disposition did not clear either key, so that row
is recorded as **re-opened pending the disposition decision in #221**, while the
other five rows carry a two-key-reviewed status they did not have before.

## What this record does not do

- **It does not re-target any row.** Choosing between a sibling-parity re-cast
  (re-derived untrimmed line + trimmed line + a ratified Trim row) and a physical
  defence of ±1% untrimmed is a spec decision that needs its own record, its own
  evidence, and its own two-key review. That is #221, and this record
  deliberately does not pre-empt it — the market key's own review names the
  shape that would clear its gate, and neither key gets to write this repo's
  spec.
- **It does not revert `README.md`'s ratified heading.** Five rows survived both
  keys; reverting the whole table to DRAFT would discard that and would itself be
  an unreviewed spec-status change.
- **It does not rewrite `0007`.** Ratified records are superseded, never edited
  (`spec/README.md`). If #221's outcome changes a target number, that record
  supersedes `0007`'s Output-reference row explicitly.
- **It does not claim the two-key gate was satisfied.** It was run and it did not
  release. Anything downstream that needs "ratified with a clean two-key
  release" — e.g. epic #4's T1 checklist items 5/7/8, or #15's aggregated
  characterization report — should read this record and #221 before claiming it.

## Alternatives considered

- **Open a fresh ratification PR and run the keys on that instead.** Rejected on
  two grounds. (a) Provenance: #220 is the diff that made the claim and is
  already on `main`; a ceremony PR re-asserting an edit that is already merged
  would put the review trail on the wrong artifact. (b) Incentive separation: the
  Builder working #125 would have been that PR's author, and the whole point of
  the two-key mechanism is that the author's own agent does not also drive the
  review. Reviewing #220 — authored by a different agent invocation, with `0007`
  written by that invocation — keeps the separation real rather than merely
  structural.
- **Run the keys as `dry-runs/` documents instead of live reviews.** Both
  `SKILL.md` files allow that shape "for a dry run against a closed/still-open
  historical case with no live PR review to post into". Rejected because #220
  *can* take a review (both were posted successfully, `CHANGES_REQUESTED`), the
  operator ruling asks for the real `apply` path, and a dry-run document is
  explicitly not an attestation.
- **Treat the merge of #220 as having settled the question, and close #125.**
  Rejected: #220's own decision record names the two-key gate as still owing, and
  the gap between "a ratification merged" and "the gate that authorizes
  ratification ran" is exactly the kind of thing this repo exists to notice.
- **Revert #220 (return the table to DRAFT) pending #221.** Rejected: it would
  throw away five rows that both keys accepted, and would relitigate a merge the
  operator ruling did not ask to undo. Qualifying one row is the narrower,
  honest action.
- **Apply `loom:operator` to #220 by hand to represent the escalation.**
  Rejected: `release` is the only sanctioned writer of those labels, and it
  deliberately wrote nothing in this ordering. Hand-applying the label a release
  path declined to apply would forge the appearance of a mechanism's output.

## Consequences

- **The Output-reference row is the block's one open spec question**, tracked as
  **#221** (disposition: re-target vs. defend ±1% untrimmed), which must itself
  land through a two-key-reviewed ratification PR. Until then, no downstream
  document should describe that row as settled.
- **The trim-network remediation now has a real tracker.** `README.md` and `0007`
  both attribute the Output-reference gap to "open follow-on trim-network work
  (issue #9)", but #9 is *closed* ("Create bandgap schematic design sources") —
  the trim network appears only in `design/README.md`'s "Explicitly out of scope
  for this issue" list, which belongs to that closed issue. `README.md` now cites
  #221 instead.
- **#222** carries the TC box-method evidence gap; **#223** carries two
  decision-record bookkeeping defects the EE key found (the duplicate `0007`
  number on `main`, and `0001`/`0002` still `proposed` after the table they feed
  was ratified).
- **Two disclosed evidence gaps from `0007` remain open and are unchanged by this
  record**: no `closed-loop-iq-pex` experiment exists (T1 item 7 for the Iq row —
  tracked by epic #4's item 7), and `startup-time-to-release` has no PEX-level
  counterpart. Both keys accepted the rows anyway, and said why.
- **The PSRR row's margin is thin and now on the record**: post-layout worst
  corner is 60.1978 dB (`bcs`/125 °C/3.63 V) against a 60 dB row — 0.20 dB — and
  the same corner reads 59.677 dB pre-layout (2/45 points below 60 dB), i.e. the
  row passes because extraction helped it. Not a finding against the target
  (both keys accepted it), but not something to describe as comfortable either.
- **No `sim/` evidence or testbench is invalidated.** Every number cited here was
  re-derived from the committed CSVs and matched, except where noted in "Two
  evidence statements … overstated" above; provenance was checked fresh (the PEX
  netlist postdates the last GDS-changing commit, and both
  `evidence-freshness-waivers.json` files are empty).
