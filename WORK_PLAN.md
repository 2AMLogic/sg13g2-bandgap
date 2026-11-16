# Work Plan

Current repository work state, generated from GitHub labels by the Guide role.

<!-- guide:plan-body:start -->
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

- **#513**: chore(loom): resync installed Loom to v0.19.1302

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

_None._

## Important

`loom:important`; taken before unlabelled work.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412)
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#487**: render_deck() in the two MC harnesses carries 11 more byte-identical lines, and the 3-line half already has a factored helper in trim_coverage_klt
- **#510**: sim/harness: a TC companion that derives zero rows should be loud, not a header-only CSV
- **#515**: closed-loop-vref-pvt-boxtc README quotes a per-100 °C-point timing range the committed record cannot source
- **#516**: No gate re-derives the characterization reports' committed "Spot-check output" blocks
- **#519**: Remove closed-loop-vref-pvt run_pvt_sweep.sh: superseded by the new run_klt_sim.sh twin
- **#520**: Remove startup-time-to-release run_pvt_sweep.sh: superseded by its run_klt_sim.sh twin
- **#524**: Docs nit: name the generic KLT_SIM_BATCH_PDK_ROOT in run_klt_trim_axis.sh's Environment header; re-wrap sim/harness/README.md:634
- **#530**: The trim bench's array-valued constants (NEAR_CODES, FAR_CODES, FAR_CORNERS, FAR_VDDS, TEMPS count) are still restated as record prose

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

- **#513**: chore(loom): resync installed Loom to v0.19.1302

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
- **#487**: render_deck() in the two MC harnesses carries 11 more byte-identical lines, and the 3-line half already has a factored helper in trim_coverage_klt *(curated)*
- **#510**: sim/harness: a TC companion that derives zero rows should be loud, not a header-only CSV *(curated)*
- **#515**: closed-loop-vref-pvt-boxtc README quotes a per-100 °C-point timing range the committed record cannot source *(curated)*
- **#516**: No gate re-derives the characterization reports' committed "Spot-check output" blocks *(curated)*
- **#524**: Docs nit: name the generic KLT_SIM_BATCH_PDK_ROOT in run_klt_trim_axis.sh's Environment header; re-wrap sim/harness/README.md:634 *(curated)*
- **#530**: The trim bench's array-valued constants (NEAR_CODES, FAR_CODES, FAR_CORNERS, FAR_VDDS, TEMPS count) are still restated as record prose *(curated)*

## Proposed (Architect / Hermit)

- **#460**: Remove two logic-free awk wrappers (zout_summary.awk, psrr_summary.awk) left behind by the klt sim conversion *(hermit)*
- **#480**: Collapse the sg13cmos5l-bandgap_top duplicate extraction pair: extract_report.json and pex_extract_report.json differ only in one string *(hermit)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 1 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 9 |
| In Progress (`loom:building`) | 1 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 1 |
| Curated | 15 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
