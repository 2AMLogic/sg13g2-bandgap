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

- **#415**: sim: add klt sim wrapper for schematic closed-loop-psrr (Part of #412)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

_None._

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#416**: sim: add klt sim wrappers for the Trim benches (trim-mc, trim-coverage) (Part of #412)
- **#423**: sim: add klt sim decks wrapper for closed-loop-vref-trim-mc (split from #416)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#299**: signoff: bind T1 items 9 and 10 (and re-bind item 1) to audited artifacts (klayout-tools#2718 landed) *(curated)*
- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6) *(curated)*
- **#322**: Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326) *(curated)*
- **#335**: sim: provision SG13CMOS5L pin on the permitted batch backend (Part of #322) *(curated)*
- **#371**: Live --batch run of the shared PEX runner driver (sim/harness/pex_runner.sh) *(curated)*
- **#379**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)*
- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures) *(curated)*
- **#387**: Re-audit characterization report after PR #383 changed the layout PEX netlists *(curated)*
- **#402**: sim: refresh closed-loop-vref-pvt-boxtc (120 points) via concurrent klt sim shard submission (Part of #273) *(curated)*
- **#403**: sim: closed-loop-vref-mc klt sim monte_carlo seeding design and 1800-draw refresh (Part of #273) *(curated)*
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(curated)*
- **#415**: sim: add klt sim wrapper for schematic closed-loop-psrr (Part of #412) *(curated)*
- **#416**: sim: add klt sim wrappers for the Trim benches (trim-mc, trim-coverage) (Part of #412) *(curated)*
- **#423**: sim: add klt sim decks wrapper for closed-loop-vref-trim-mc (split from #416) *(curated)*

## Proposed (Architect / Hermit)

_None._

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 1 |
| Ready (`loom:issue`) | 0 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 14 |
| Architect / Hermit proposals | 0 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
