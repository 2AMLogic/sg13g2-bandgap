# Work Log Archive — 2026-09

Sections moved byte-for-byte from [WORK_LOG.md](../WORK_LOG.md) by `loom-daemon work-docs archive`.

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
