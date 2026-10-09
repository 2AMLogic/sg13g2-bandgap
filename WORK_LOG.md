# Work Log

Chronological record of completed work in this repository, maintained by the Guide role.

Entries are grouped by date, newest first. Each entry references a merged PR or closed issue.

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->

### 2026-10-09

- **PR #316**: ci: detect dependency drift in the active characterization report (#315)
- **Issue #315** (closed): ci: detect dependency drift in the active characterization summary
- **PR #314**: design: opt-in netlist drift check (#312)
- **Issue #312** (closed): design: add a netlist-vs-schematic drift check and fix the regen docs (trim missing, author paths embedded)
- **PR #311**: sim: bind PEX simulation records to their consumed extraction hashes
- **Issue #309** (closed): sim: bind PEX simulation records to their consumed extraction hashes

### 2026-10-08

- **PR #307**: measurements: October characterization report bound to T1 item 8 (#300)
- **Issue #300** (closed): measurements: refresh the aggregated characterization report against the current spec and trim-bearing core, and wrap it for T1 item 8

- **PR #306**: signoff: bind T1 items 1 and 10 to audited artifacts, bump klt pin to 3a75c3ae (#299)
- **PR #305**: docs(readme): Trim-row disposition now tracked in #303
- **PR #301**: ci: run solve-quality and harness-transformer self-tests in hygiene
- **PR #296**: chore: pin tracker-state-comment helper as repo-owned (#295)
- **Issue #265** (closed): Trimmed-line disposition: DR-0011's +/-0.5% does not hold on #229's aids-free trim-domain MC evidence
- **Issue #297** (closed): Run the loop-gain solve-quality test in hygiene CI and add harness self-tests
- **Issue #295** (closed): Orphan helper .loom/scripts/tracker-state-comment.sh: upstream it or pin it

### 2026-10-04

- **PR #293**: sim(pex): re-run three of the five PEX grids through the klt-sim batch bridge (part of #278)

### 2026-10-03

- **PR #288**: spec(0014): keep the 1-point 27 °C Trim row explicitly (no hot insertion, no CTAT knob)
- **PR #290**: sim(loop-gain): trim-code axis of phase margin; 36.3 deg is a corrupted AC solve, accept and disclose (#271)
- **PR #291**: sim(loop-gain): solve-quality gate and guarded 45-point record (#289)
- **PR #292**: sim(tools): PEX netlist-body generator for bandgap_core (part of #278)
- **Issue #289** (closed): loop-gain bench: a single AC sweep can return a numerically corrupted solve that PASSes (36.3 deg / 43.9 deg were artifacts); add a solve-quality guard
- **Issue #285** (closed): Trim row: should the ratified 1-point 27 °C trim become 2-point (room+hot) with the CTAT knob? It is the only measured path to ±0.5%
- **Issue #271** (closed): Trim ladder costs real loop phase margin at wcs/125C/2.97V (36.3 deg vs 88.5 deg pre-trim)

### 2026-10-02

- **PR #281**: docs(sim/harness): disclose the .meas 6-s.f. precision ceiling and accept it
- **PR #283**: docs: attribute the ±0.5% trimmed budget to DR-0011 in boxtc-trim README
- **PR #284**: sim(269): aids-free pre-trim box-TC A/B — the ladder, not the aids, drives the <20 ppm/°C stretch miss
- **PR #286**: sim(267)+spec(0013): measure every candidate second-trim knob's column, and decline the knob under the ratified 1-point Trim row
- **PR #287**: feat: run the klt sim probe on the batch fleet (--batch)
- **Issue #282** (closed): sim/closed-loop-vref-boxtc-trim/README.md attributes the ±0.5% budget to DR-0010 in one line and DR-0011 in another
- **Issue #280** (closed): sim/harness: the klt sim path records one fewer significant figure than run_pvt_sweep.sh, undisclosed
- **Issue #277** (closed): Infra: the EDA batch fleet image carries no ihp-sg13g2 PDK (and no OSDI build step), so klt sim cannot run this repo's corner grids
- **Issue #269** (closed): TC row: the trim-bearing, aids-free core reads 20.2-45.7 ppm/C box TC - target still met, <20 ppm/C stretch is not
- **Issue #267** (closed): Second trim degree of freedom: the 1-point R1 trim converts offset into TC at a measured 0.058%/code, which is what sets the trimmed line

### 2026-10-01

- **PR #266**: feat: trim network for the core's R1/R2 divider (DR-0011 Trim row) + evidence
- **PR #274**: test(sim): refresh 9 schematic-DUT experiments against the trim-bearing core
- **PR #276**: layout: re-draw the summing resistor as #229's trim ladder, re-run DRC/LVS/PEX
- **PR #279**: sim: settle the corner-grid harness (klt sim) and the D2 mask-option disposition (#275)
- **Issue #275** (closed): Re-run the five PEX experiments against the trim-bearing extraction (#272's scope item 3/4) — needs a corner-grid harness this host may run
- **Issue #272** (closed): Re-layout and re-extract the block against the trim-bearing core, then refresh the 5 PEX experiments
- **Issue #264** (closed): Refresh sim/ evidence against the trim-bearing core netlist (post-#229)
- **Issue #229** (closed): Design the trim network obligated by the re-cast Output-reference row (DR-0009: range >= +/-15%, <= 0.25%/step, 1-point @ 27C)

### 2026-09-30

- **PR #230**: ratification: re-cast the Output-reference row (DR-0010)
- **PR #263**: spec: renumber duplicate decision record 0010 -> 0011
- **Issue #262** (closed): spec: duplicate decision-record number 0010 on main (hygiene CI failing since PR #230 merge)
- **Issue #231** (closed): Apply the two ratification keys to PR #230 (DR-0009, Output-reference re-cast) — non-author
- **Issue #221** (closed): Output-reference row: decide its disposition (re-target vs. defend ±1% untrimmed) — both ratification keys escalated it

### 2026-09-29

- **PR #259**: chore: resync installed Loom surfaces (--force past obsolete local edits)
- **PR #261**: Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers
- **Issue #260** (closed): Remove duplicated Report/sha256_file scaffolding across .github/scripts CI checkers

### 2026-09-27

- **PR #251**: docs(layout): condense SG13CMOS5L resolved-issue narrative in README to pointers
- **PR #254**: docs(layout): re-derive the #174 LVS section from the current 14-finding report
- **PR #256**: docs: fix false "no underpass needed" claim for bandgap_startup
- **PR #257**: docs(layout): re-derive SG13CMOS5L cause-4 pfet/well half and net_count from committed evidence
- **Issue #255** (closed): docs(layout): SG13CMOS5L cause-4 item still says PMOS bodies are unbiased; committed reports say vdd (plus stale net_count)
- **Issue #253** (closed): docs(layout): two stale "no underpass needed" claims for sg13cmos5l-bandgap_startup
- **Issue #252** (closed): docs(layout): #174 LVS section quotes 22 findings; committed sg13cmos5l-bandgap_top report says 14
- **Issue #250** (closed): docs: condense SG13CMOS5L half of layout/README.md — closed-issue narrative duplicated in generate.py docstrings, with stale LVS counts (follow-up to #189)

### 2026-09-26

- **PR #249**: Add pinned-comment convention for tracker issues at the addComment cap
- **Issue #248** (closed): Issue #4 hit GitHub's 2500-comment hard cap: addComment now permanently disabled

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
