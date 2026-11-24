# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

### 2026-09-23

- **PR #244**: fix: draw the CMOS5L well taps (2 floating MOS wells fixed, 10 pnpMPA base rings nSD-marked; ERC 12 -> 10)
- **PR #245**: fix(sg13cmos5l-bandgap_core): extend Q2 emitter trunk to reach R2's e2 drop
- **PR #247**: feat(loom): sticky-blocked registry with atomic settle and drift repair for issue #4
- **Issue #246** (closed): loom:blocked silently lost on issue #4 across claim/settle cycles
- **Issue #243** (closed): sg13cmos5l-bandgap_core: R2's e2 drop (x=58) lands in free field, disjoint from the Q2 emitter trunk (x=123.6..165.9) — the e2 net is split as drawn
- **Issue #240** (closed): Zero out the 12 erc.missing_tie findings on sg13cmos5l-bandgap_top (2 floating MOS wells + 10 marker-less pnpMPA base rings)

### 2026-09-22

- **PR #238**: chore: add reuse.lock.json in_tree entry for bandgap_amp (evaluate)
- **PR #239**: feat: register T1 item 11 compound ERC+LVS citation in the signoff manifest
- **PR #241**: feat: declare checked nwell tie in erc-supply-spec under upgraded klt
- **Issue #235** (closed): 2am: reuse rule 9 — in-tree bandgap amplifier duplicates sibling canary sg13g2-opamp — add reuse.lock.json in_tree entry (evaluate), then adopt or record
- **Issue #233** (closed): Declare a checked klt erc tie on an upgraded klt (completes item 11's missing_tie half, follows up #225)

### 2026-09-21

- **PR #227**: docs: add aggregated per-spec-row characterization report under measurements/
- **PR #228**: spec: renumber duplicate 0007 to 0009, resolve DR-0001/0002 statuses, add CI duplicate-number check
- **PR #232**: feat: grade T1 state mechanically via klt signoff block manifest
- **PR #234**: feat: add ERC supply spec + report for sg13cmos5l-bandgap_top
- **PR #236**: feat: add committed box-method TC testbenches (schematic + PEX) on the 8-point grid
- **Issue #226** (closed): Commit a klt signoff block manifest so this block's T1 state is graded, not hand-read
- **Issue #225** (closed): T1 item 11 (power delivery, structural): no klt erc supply spec or report in this repo
- **Issue #223** (closed): spec: duplicate decision-record number 0007 on main, and DR-0001/DR-0002 left 'proposed' after the table they feed was ratified
- **Issue #222** (closed): sim: commit a box-method TC testbench (endpoint method understates TC post-retune; box worst corner ~20.2 ppm/°C vs the < 20 stretch)
- **Issue #15** (closed): Publish an aggregated characterization report under measurements/

### 2026-09-19

- **PR #224**: ratification: run the two-key review of the target-spec table and record its outcome
- **Issue #125** (closed): Cut the spec-ratification PR now that #13 is resolved (two-key mechanism)

### 2026-09-15

- **PR #219**: docs(spec): DR-0007 — keep sim/ evidence logs verbatim and uncompressed
- **PR #220**: ratification: ratify target-spec table with current R1=511um/N=300-MC evidence (supersedes #128)
- **Issue #150** (closed): PR #128's ratification evidence is stale relative to main's R1=511um TC retune (#139's fix didn't touch it)
- **Issue #118** (closed): Recurring redispatch-race churn on #4 (loom-daemon, cf. rjwalters/loom#6685)
- **Issue #26** (closed): Decide evidence-log verbosity policy for sim/ records (6.4 MB per sweep after OSDI conversion)

### 2026-09-12

- **PR #218**: fix: normalize GraphQL/REST merge-state shapes in dep-recheck-fingerprint.sh
- **Issue #217** (closed): dep-recheck-fingerprint.sh produces non-deterministic CONCLUSION_HASH for an unchanged blocked PR (spam on #125)

### 2026-09-10

- **Issue #167** (closed): Champion: Merge-Risk Hold Digest

### 2026-09-09

- **PR #216**: sim: add closed-loop-vref-mc device-mismatch Monte Carlo campaign
- **Issue #215** (closed): sim: untrimmed `vref` mismatch Monte Carlo (`hbt_typ_mismatch` + `mos_tt_mismatch` + `res_typ_mismatch`, seeded, N≥300, negative control) — T1 item 6 evidence for the ±1 % untrimmed Output-reference row

### 2026-09-08

- **PR #203**: refactor(sim): dedupe trip-point verdict awk block into sim/lib/pvt_verdict_common.sh
- **PR #205**: refactor(sim): extend abs_diff() to 10 remaining inline call sites
- **PR #208**: refactor(sim): use abs_diff() helper in run_offset_check.sh (#206)
- **PR #209**: refactor: dedupe _shift/_assert_column_pitch into _klayout_builder_base
- **PR #212**: refactor(layout): dedupe poly-resistor core geometry into _klayout_builder_base
- **PR #213**: refactor(sim): derive startup-time-to-release checkpoint ladder from template
- **Issue #211** (closed): Dedupe poly-resistor leg/bbox geometry: identical arithmetic in common.py and common_sg13cmos5l.py
- **Issue #210** (closed): Dedupe startup-time-to-release checkpoint ladder: hardcoded in both run_pvt_sweep.sh and its .spice.tmpl
- **Issue #207** (closed): Dedupe _shift() / _assert_column_pitch() across the two bandgap_top generate.py modules
- **Issue #206** (closed): Extend abs_diff() to the one remaining inline call site in sim/closed-loop-offset/run_offset_check.sh
- **Issue #204** (closed): Extend abs_diff() to 10 remaining inline call sites in run_pvt_sweep.sh
- **Issue #202** (closed): Dedupe trip-point verdict awk block into sim/lib/pvt_verdict_common.sh

### 2026-09-07

- **PR #197**: refactor(sim): dedupe .measure grep/awk extraction idiom into sim/lib
- **PR #199**: refactor(sim): dedupe .op voltage-extraction idiom into sim/lib
- **PR #201**: refactor(sim): dedupe cross-bench comparison idioms in *-pex run_pvt_sweep.sh into sim/lib
- **Issue #200** (closed): Consolidate duplicated cross-bench comparison idioms in *-pex run_pvt_sweep.sh scripts
- **Issue #198** (closed): sim: dedupe .op voltage-extraction idiom across 3 run_pvt_sweep.sh scripts
- **Issue #196** (closed): sim: dedupe .measure grep/awk extraction idiom across run_pvt_sweep.sh into sim/lib
- **Issue #55** (closed): Champion: Merge-Risk Hold Digest
