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
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(held)*
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails *(held)*

## Ready

Human-approved issues ready for implementation (`loom:issue`).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#572**: layout: metal1.enclosing.cont.1 x18 in bandgap_core under the require_containment sg13g2 deck
- **#573**: layout: cont.ongrid.1 x4 in bandgap_startup under the current sg13g2 deck

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#557**: layout: remaining via1 end-cap/size defects in bandgap_core, bandgap_startup, bandgap_top under the current sg13g2 deck
- **#571**: layout: nwell.enclosing.nactiv.1 (amp 5, core 6, top 11) under the require_containment sg13g2 deck

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#574**: fix(layout): enclose core/top Via1 landings in Metal2 at the deck's fixed 0.19 um

## Approved (Awaiting Merge)

PRs that passed review and are queued for Champion auto-merge (`loom:pr`).

_None._

## Proposed

Issues carrying `loom:curated`.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6) *(curated)*
- **#322**: Re-stamp SG13CMOS5L PDK pin from klayout-tools (IHP-Open-PDK dev f7bca326) *(curated)* *(held)*
- **#335**: sim: provision SG13CMOS5L pin on the permitted batch backend (Part of #322) *(curated)* *(held)*
- **#379**: Adopt the common artifact store for sim evidence (manifests in git, bytes via klt artifact) *(curated)* *(held)*
- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures) *(curated)*
- **#387**: Re-audit characterization report after PR #383 changed the layout PEX netlists *(curated)* *(held)*
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(curated)* *(held)*
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails *(curated)* *(held)*
- **#440**: Confirm seed-parity of closed-loop-vref-mc fleet draws against a local ngspice run *(curated)* *(held)*
- **#557**: layout: remaining via1 end-cap/size defects in bandgap_core, bandgap_startup, bandgap_top under the current sg13g2 deck *(curated)*
- **#561**: Evidence backlog: 20 committed layout reports predate the DR-0016 evidence standard (klt 0.8.0) *(curated)*
- **#571**: layout: nwell.enclosing.nactiv.1 (amp 5, core 6, top 11) under the require_containment sg13g2 deck *(curated)*
- **#572**: layout: metal1.enclosing.cont.1 x18 in bandgap_core under the require_containment sg13g2 deck *(curated)*
- **#573**: layout: cont.ongrid.1 x4 in bandgap_startup under the current sg13g2 deck *(curated)*

## Proposed (Architect / Hermit)

- **#460**: Remove two logic-free awk wrappers (zout_summary.awk, psrr_summary.awk) left behind by the klt sim conversion *(hermit)* *(held)*
- **#480**: Collapse the sg13cmos5l-bandgap_top duplicate extraction pair: extract_report.json and pex_extract_report.json differ only in one string *(hermit)* *(held)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 0 |
| Important | 3 |
| Ready (`loom:issue`) | 3 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 1 |
| Approved PRs awaiting merge | 0 |
| Curated | 14 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
