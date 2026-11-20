# Work Plan

Current repository work state, generated from GitHub labels by the Guide role.

<!-- guide:plan-body:start -->
_Generated: 2026-11-20T21:23:08Z (snapshot; compare against live labels)_
## Operator Attention: Merge-Risk-Hold Pileup

Judge-approved PRs under a hold (`loom:blocked` or `loom:operator`) — only a human merge decision is missing.

_None._

## Very Important

`loom:very-important` (one counts per workspace); every stage takes these first.

- **#628**: Rebase PR #383 (runset recognition layers, #380 + #387) onto current main: resolve 38 conflicts, regenerate layout, re-mint evidence, re-run the three PEX benches

## Important

`loom:important`; taken before unlabelled work.

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#414**: sim: add klt sim wrappers for closed-loop-iq and closed-loop-startup (Part of #412) *(held)*
- **#436**: Re-layout and re-extract bandgap_top after NMOS mirror resize (PR #435); PEX generator self-test fails *(held)*
- **#629**: T1 item 5 (corner verification): cite the klt sim corner-matrix envelopes per spec row and declare the row set, so the item grades on evidence instead of no_evidence

## Ready

Human-approved issues (`loom:issue`) ready for implementation — excluding held (`loom:blocked`/`loom:operator`/`loom:frozen`), `loom:building`, and issues closed by an open `loom:pr` PR (listed under Approved).

- **#303**: design: resize the core against mismatch and re-aim the trim; ±4.5 % is declined (operator ruling 2026-10-08, T1 items 5 and 6)
- **#629**: T1 item 5 (corner verification): cite the klt sim corner-matrix envelopes per spec row and declare the row set, so the item grades on evidence instead of no_evidence
- **#631**: design: PSRR @ DC misses the > 60 dB row at bcs/125 C/3.63 V (59.685 dB schematic); attribute the limit and propose a bounded fix

## In Progress

Issues currently being built (`loom:building`).

- **#380**: layout: make draw_hv_mos / draw_npn13g2 recognizable by the IHP PDK LVS runset (single-device runset-LVS fixtures)
- **#628**: Rebase PR #383 (runset recognition layers, #380 + #387) onto current main: resolve 38 conflicts, regenerate layout, re-mint evidence, re-run the three PEX benches
- **#630**: T1 item 6 (Monte Carlo): produce and cite a klt yield report for the untrimmed Output-reference line, with a real negative control and the statistical row set declared

## PRs Awaiting Review

PRs waiting on Judge (`loom:review-requested`).

_None._

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
- **#628**: Rebase PR #383 (runset recognition layers, #380 + #387) onto current main: resolve 38 conflicts, regenerate layout, re-mint evidence, re-run the three PEX benches *(curated)*
- **#629**: T1 item 5 (corner verification): cite the klt sim corner-matrix envelopes per spec row and declare the row set, so the item grades on evidence instead of no_evidence *(curated)*
- **#630**: T1 item 6 (Monte Carlo): produce and cite a klt yield report for the untrimmed Output-reference line, with a real negative control and the statistical row set declared *(curated)*
- **#631**: design: PSRR @ DC misses the > 60 dB row at bcs/125 C/3.63 V (59.685 dB schematic); attribute the limit and propose a bounded fix *(curated)*
- **#633**: sg13cmos5l-bandgap_top: pnpMPA base rings carry zero contacts (draw_pnpmpa cont_array underflow at w=1u l=2u) — the base tie does not exist as drawn *(curated)*

## Proposed (Architect / Hermit)

- **#460**: Remove two logic-free awk wrappers (zout_summary.awk, psrr_summary.awk) left behind by the klt sim conversion *(hermit)* *(held)*
- **#480**: Collapse the sg13cmos5l-bandgap_top duplicate extraction pair: extract_report.json and pex_extract_report.json differ only in one string *(hermit)* *(held)*

## Epics

_None._

## Backlog Balance

| Bucket | Count |
|------|-------|
| Operator merge-risk holds | 0 |
| Very important | 1 |
| Important | 4 |
| Ready (`loom:issue`, net of holds/building/merge-pending) | 3 |
| In Progress (`loom:building`) | 3 |
| PRs awaiting review | 0 |
| Approved PRs awaiting merge | 0 |
| Curated | 14 |
| Architect / Hermit proposals | 2 |
| Active epics | 0 |
<!-- guide:plan-body:end -->
