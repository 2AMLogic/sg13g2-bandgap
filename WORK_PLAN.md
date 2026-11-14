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
- **#469**: sim: get the box-TC 100 C corner to solve inside the batch job limit (unblocks #402)

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#469**: sim: get the box-TC 100 C corner to solve inside the batch job limit (unblocks #402)
- **#472**: Dedupe the PEX vref DUT wrapper: closed_loop_vref_pvt_pex_boxtc.body.spice.tmpl is byte-identical to its sibling, and the harness already has the BODY_TEMPLATE override
- **#473**: Drop the last hand-rolled MSENSE-width parse and fix sim/lib/msense_width.sh's stale caller list
- **#477**: Dedupe .github/scripts: the two dependency checkers each carry the same manifest-to-envelope citation resolver
- **#478**: layout/README.md: consolidate the three colliding "Reproducing" sections — neither SG13G2 recipe regenerates all four cells
- **#481**: Hoist the duplicated klt-sim runner preamble shared by pex_runner.sh and cmos5l_runner.sh

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#463**: Dedupe the Monte Carlo klt-sim harnesses: PDK corner-section maps, sections(), make_ctx() and load_seeds() re-typed instead of imported
- **#468**: sim: add a klt sim wrapper for startup-time-to-release (Startup row)
- **#475**: Dedupe .github/scripts: check_artifact_manifests.py re-grows _ci_common's Report, resolve_root and ls-files reader

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#476**: refactor: give the MC harness family one copy of its corner-section mapping
- **#479**: refactor(ci): fold two checkers into _ci_common's shared scaffolding

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#482**: feat(sim): klt sim wrapper for startup-time-to-release, with a ladder enricher mode

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
- **#467**: sim: add a klt sim wrapper for closed-loop-vref-pvt (Output-reference nominal row) *(curated)*
- **#468**: sim: add a klt sim wrapper for startup-time-to-release (Startup row) *(curated)*
- **#469**: sim: get the box-TC 100 C corner to solve inside the batch job limit (unblocks #402) *(curated)*

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
| Ready (`loom:issue`) | 7 |
| In Progress (`loom:building`) | 4 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 1 |
| Curated | 13 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
