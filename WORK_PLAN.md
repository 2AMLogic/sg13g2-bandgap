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

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#556**: layout: bandgap_amp has 12 Via1 shapes half outside Metal2 (metal2.enclosing.via1.1)
- **#558**: tool drift: top-level LVS findings explode 10/4 -> 1023/1019 under klt 0.9.3 deck; signoff manifest ROTTED on main

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

- **#559**: fix(layout): enclose bandgap_amp Via1 landings in Metal2 at the deck's fixed 0.19 um
- **#560**: evidence: re-mint bandgap_top LVS under pinned klt 0.8.0; add DR-0016 evidence standard

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
- **#556**: layout: bandgap_amp has 12 Via1 shapes half outside Metal2 (metal2.enclosing.via1.1) *(curated)*
- **#558**: tool drift: top-level LVS findings explode 10/4 -> 1023/1019 under klt 0.9.3 deck; signoff manifest ROTTED on main *(curated)*

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
| Ready (`loom:issue`) | 1 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 2 |
| Approved PRs awaiting merge | 0 |
| Curated | 11 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
