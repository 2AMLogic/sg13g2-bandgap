# Work Plan

Current repository work state, generated from GitHub labels by the Guide role.

<!-- guide:plan-body:start -->
_Generated: 2026-11-27T14:17:39Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#752**: test(sim): move the TC companion tests into their own module
- **#757**: chore: resync installed Loom surfaces

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)

## Important

`loom:important`; taken before unlabelled work.

- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412)
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails
- **#653**: Re-run closed-loop-iq for a re-derivable item-5 citation and update the record spec's magnitude Claim (post-#648)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#751**: Move the temperature-coefficient companion tests out of the harness transformer suite
- **#755**: Refresh the dispatch checkout’s Loom resolver so large defaults no longer break issue filing

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#752**: test(sim): move the TC companion tests into their own module
- **#757**: chore: resync installed Loom surfaces

## Proposed

Issues carrying `loom:curated`.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6) *(curated)*
- **#322**: Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326) *(curated)*
- **#335**: sim: provision SG13CMOS5L pin on the permitted batch backend (Part of #322) *(curated)*
- **#379**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)*
- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures) *(curated)*
- **#387**: Re-audit characterization report after PR #383 changed the layout PEX netlists *(curated)*
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(curated)*
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails *(curated)*
- **#440**: Confirm seed-parity of closed-loop-vref-mc fleet draws against a local ngspice run *(curated)*
- **#653**: Re-run closed-loop-iq for a re-derivable item-5 citation and update the record spec's magnitude Claim (post-#648) *(curated)*
- **#698**: Re-run sim/sg13cmos5l-closed-loop-startup-pex against the parasitic-bearing sg13cmos5l-bandgap_top.pex.spice (post-#480) *(curated)*
- **#755**: Refresh the dispatch checkout’s Loom resolver so large defaults no longer break issue filing *(curated)*

## Proposed (Architect / Hermit)

- **#708**: Remove the unusable dpkg-deb recovery recipe from the Linux OSDI bootstrap *(hermit)*
- **#718**: Simplify the Python verdict-constant guard with ast.Store *(hermit)*
- **#738**: Retire scheduled sticky-label checks for closed tracker #4 *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 2 |
| Very important | 1 |
| Important | 3 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 2 |
| Curated | 12 |
| Architect / Hermit proposals | 3 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
