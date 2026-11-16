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

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412)
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails
- **#470**: docs: bring the README status and maturity-ladder lines in line with the signoff verdict

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#468**: sim: add a klt sim wrapper for startup-time-to-release (Startup row)
- **#470**: docs: bring the README status and maturity-ladder lines in line with the signoff verdict
- **#473**: Drop the last hand-rolled MSENSE-width parse and fix sim/lib/msense_width.sh's stale caller list
- **#474**: A third box-method TC implementation survives #465: closed-loop-vref-boxtc-trim's awk copy
- **#481**: Hoist the duplicated klt-sim runner preamble shared by pex_runner.sh and cmos5l_runner.sh
- **#484**: Deduplicate the characterization reports' spotcheck.py: 186 of 201 lines are identical in all four copies
- **#486**: Hoist the triplicated nodeset-seed loader and SEED_FIELDS token map into one harness module
- **#489**: Consider the KLU direct solver on the sibling klt sim benches that share the boxtc DUT
- **#493**: _ci_common.cited_envelopes() batches its diagnostics ahead of each caller's tail, reordering multi-problem failure output

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#501**: docs: record measured KLU-vs-SPARSE solve times for closed-loop-iq and closed-loop-startup
- **#504**: test: tripwire the trim bench's awk box-TC copy to boxtc_companion

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#482**: feat(sim): klt sim wrapper for startup-time-to-release, with a ladder enricher mode
- **#490**: refactor: drop last hand-rolled MSENSE parse; de-enumerate sim/lib caller headers
- **#497**: docs: align README status, maturity ladder and measurements/ line with committed evidence
- **#498**: refactor(sim): hoist SEED_FIELDS and load_seeds into one shared seed_deck module
- **#499**: fix: yield cited_envelopes() lazily so walk diagnostics interleave with each caller's tail
- **#505**: refactor: extract shared spotcheck bodies into measurements/lib/spotcheck_common.py
- **#506**: test: pin the shared PEX body-template contract in SetDispatchWiringTests

## Proposed

Issues carrying `loom:curated`.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6) *(curated)*
- **#322**: Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326) *(curated)*
- **#335**: sim: provision SG13CMOS5L pin on the permitted batch backend (Part of #322) *(curated)*
- **#379**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)*
- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures) *(curated)*
- **#387**: Re-audit characterization report after PR #383 changed the layout PEX netlists *(curated)*
- **#402**: sim: refresh closed-loop-vref-pvt-boxtc (120 points) via concurrent klt sim shard submission (Part of #273) *(curated)*
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(curated)*
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails *(curated)*
- **#440**: Confirm seed-parity of closed-loop-vref-mc fleet draws against a local ngspice run *(curated)*
- **#468**: sim: add a klt sim wrapper for startup-time-to-release (Startup row) *(curated)*
- **#470**: docs: bring the README status and maturity-ladder lines in line with the signoff verdict *(curated)*
- **#474**: A third box-method TC implementation survives #465: closed-loop-vref-boxtc-trim's awk copy *(curated)*
- **#489**: Consider the KLU direct solver on the sibling klt sim benches that share the boxtc DUT *(curated)*
- **#493**: _ci_common.cited_envelopes() batches its diagnostics ahead of each caller's tail, reordering multi-problem failure output *(curated)*
- **#502**: Harness tests do not pin the shared PEX body-template contract (#472 / PR #495) *(curated)*

## Proposed (Architect / Hermit)

- **#460**: Remove two logic-free awk wrappers (zout_summary.awk, psrr_summary.awk) left behind by the klt sim conversion *(hermit)*
- **#480**: Collapse the sg13cmos5l-bandgap_top duplicate extraction pair: extract_report.json and pex_extract_report.json differ only in one string *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 4 |
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 10 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 7 |
| Curated | 16 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
