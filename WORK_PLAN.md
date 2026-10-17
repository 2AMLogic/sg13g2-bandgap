# Work Plan

Current repository work state, generated from GitHub labels by the Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

_None._

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#352**: layout: close T1 items 4 and 11 with a klayout-runset LVS report (PDK runset recognizes NPN13G2)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#353**: feat(lvs): grade bandgap_top with the PDK LVS runset for T1 items 4 and 11

## Proposed

Issues carrying `loom:curated`.

- **#4**: Track the gap to T1 sim-validated / bronze (klayout-tools design-evidence tiers) *(curated)*
- **#273**: Finish the #264 refresh: closed-loop-vref-mc (1800 draws) and closed-loop-vref-pvt-boxtc (120 transient points) *(curated)*
- **#278**: Re-run the five PEX experiments through the klt sim harness (the remaining half of #275) *(curated)*
- **#299**: signoff: bind T1 items 9 and 10 (and re-bind item 1) to audited artifacts (klayout-tools#2718 landed) *(curated)*
- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6) *(curated)*
- **#322**: Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326) *(curated)*
- **#335**: sim: provision SG13CMOS5L pin on the permitted batch backend (Part of #322) *(curated)*
- **#352**: layout: close T1 items 4 and 11 with a klayout-runset LVS report (PDK runset recognizes NPN13G2) *(curated)*

## Proposed (Architect / Hermit)

- **#310**: signoff: execute the deferred cold-start testbench audit for T1 item 9 *(architect)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 0 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 8 |
| Architect / Hermit proposals | 1 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
