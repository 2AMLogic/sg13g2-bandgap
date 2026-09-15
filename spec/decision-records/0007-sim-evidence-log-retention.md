# 0007: sim/ evidence-log retention — keep the full `.op` dump, uncompressed

- **Status**: proposed
- **Date**: 2026-09-15
- **Decided by**: Loom Builder (agent), issue #26

## Context

`sim/`'s evidence convention is append-only: every sweep mints a new
`corners/<record-id>/` tree of raw ngspice logs that is never edited or
deleted (`sim/README.md` → "Append-only rule", enforced by
`.github/scripts/check_evidence_formats.py`). Issue #26 asked whether those
logs are too *verbose* to keep at full fidelity, after PR #25 converted
`core-open-loop-bias` from ideal primitives to real compact models (PSP103VA
MOS + `r3_cmc` resistors, loaded via OSDI) and the per-record size jumped
from 540 KB to 6.4 MB.

Three testbench templates carry a `.op` card in addition to the `op` inside
their `.control` block, and that card is what emits the bulk of each log
(re-verified at `0442b89`, 2026-09-15):

```
$ git grep -n '^\.op$' -- 'sim/*/testbench/*.tmpl'
sim/core-open-loop-bias/testbench/tb_core_open_loop_bias.spice.tmpl:83
sim/core-open-loop-bias-pex/testbench/tb_core_open_loop_bias_pex.spice.tmpl:288
sim/sg13cmos5l-core-open-loop-bias/testbench/tb_sg13cmos5l_core_open_loop_bias.spice.tmpl:79
```

What the run scripts actually consume is tiny. In
`sim/core-open-loop-bias/corners/20260830-132212-d83f7c4/typ_27c_3.30v.log`
(3,668 lines, 224 KB), `run_pvt_sweep.sh` parses exactly **9** lines — the
`v(vref)`/`v(fb)`/`v(sns1)`/`v(sns2)`/`v(cb2)`/`v(cb3)`/`i(vm1)`/`i(vm2)`/
`i(vm3)` prints at lines 14-22, emitted by the `.control` block's own `op`.
Everything from line 23 to 3,658 is the `.op` card's output: an
internal-node dump (94 node rows), then ~2,570 lines of **model-card**
parameter tables (three `PSP103VA models` blocks plus one `r3_cmc models`
block) and ~810 lines of per-device instance dumps. PR #25 measured that dropping the `.op`
card shrinks a log ~70x while preserving every value the run script parses
and every value quoted in the record `.md`; on the larger present-day logs
the ratio is closer to 120x (3,668 lines → ~30).

Working-tree weight has grown accordingly (`du -sh`, same commit; `sim/` now
holds 22 experiment directories):

| dir | working tree |
|---|---|
| `sim/core-open-loop-bias-pex/corners` | 70M |
| `sim/core-open-loop-bias/corners` | 23M |
| `sim/sg13cmos5l-core-open-loop-bias/corners` | 18M |
| all 17 other experiments' `corners/` combined | ~46M |
| **`sim/` total** | **157M** |

The three `.op`-card experiments are ~111M of that 157M (~71%), which is the
number issue #26, the Hermit's 2026-08-23 pass (20M of 25M) and the Curator's
2026-09-15 pass (114M of 158M) all reported, and which motivated deciding
now: git history cannot be pruned later without a rewrite.

**The `du` figures are the wrong cost, and that is what settles this.** These
logs are near-identical repetitive text, so git's zlib + cross-blob delta
compression is extraordinarily effective on them. Measured on the same
commit with `git rev-list --disk-usage --objects HEAD -- <path>`:

| object set | working tree | permanent cost in git |
|---|---|---|
| whole repo at HEAD | — | **15.7 MiB** |
| `sim/` at HEAD | 157M | 7.0 MiB (44% of the repo) |
| the three `.op`-card `corners/` trees | ~111M | **3.2 MiB** (21% of the repo) |
| one 45-point record (`core-open-loop-bias/corners/20260830-132212-d83f7c4`) | 9.9M | 191 KiB (~53x) |

`git rev-list --disk-usage --objects --all -- sim` returns 7,311,506 bytes
against HEAD's 7,309,889 — i.e. **every superseded record in the entire
history of `sim/` adds ~1.6 KB** over the current checkout, because each
re-run deltas almost perfectly against the previous one. The growth curve the
issue was worried about is, in history terms, nearly flat.

The "continuous growth" branch of the concern has also closed on its own:
#16 landed as `.github/workflows/hygiene.yml`, which is checker-only — its
own header states it "never runs klt, ngspice or the PDK", and
`sim/README.md` now ratifies the rule that "CI checks the shape of evidence;
it never produces evidence." No CI path mints `corners/` records, so new
records arrive only when a human or agent deliberately re-runs a sweep.

## Decision

**Raw per-point simulator output under `sim/*/corners/<record-id>/` is
retained in full, verbatim, and uncompressed — one plain-text `*.log` per PVT
point, exactly as ngspice emitted it, including the complete `.op`
operating-point and model-parameter dump.** This ratifies the current
behaviour as policy; no testbench template, run script, or existing record
changes.

Specifically, and binding on future experiments:

1. **Do not remove the `.op` card** from a testbench to shrink its logs. An
   experiment on real compact models *should* dump its resolved model and
   device parameters. New testbenches using OSDI compact models are expected
   to carry it.
2. **Do not compress logs in the tree** (no `.log.gz`, no tarred
   `corners/<record-id>.tar.gz`). See "Alternatives considered" — it costs
   more history bytes than it saves, and it breaks both `grep` and the
   `corners_dir.glob("*.log")` contract in
   `.github/scripts/check_evidence_formats.py`.
3. **Do not trim selectively** (full dump for the typical corner, short logs
   elsewhere). A corner-dependent evidence format is exactly the asymmetry
   that hides a deck bug at a skewed corner.
4. **CI must not mint records.** The existing "CI checks the shape of
   evidence; it never produces evidence" rule in `sim/README.md` is part of
   this decision's basis; a future proposal to have CI commit `corners/` must
   supersede this record rather than proceed under it.
5. **Revisit trigger (this decision is bounded, not permanent).** Supersede
   this record with a new one if either threshold is crossed:
   `git rev-list --disk-usage --objects HEAD -- sim` exceeds **50 MiB** (7x
   today's 7.0 MiB), or `sim/`'s share of the repo's HEAD object cost exceeds
   **75%** (44% today). Both are one-command checks; neither is a judgement
   call.

The reason to keep rather than trim is this repo's stated purpose, not
inertia. Per `CLAUDE.md`, the SG13G2 deck is "starter-grade" and "the PDK is
the variable, not the design" — the `.op` dump is the only artifact that
records *which resolved model parameters were actually in force* at a given
corner, after corner-section selection, binning and temperature scaling. That
is precisely the class of fact a canary block exists to catch being wrong, and
it cannot be recovered from the netlist snapshot alone (the snapshot names a
`.lib` file and section; it does not contain the values that section resolved
to). For the SG13CMOS5L variant it is not recoverable at all in the general
case: `sim/pdk-sg13cmos5l.json` pins a **live `main`-branch commit** of a
repository whose own README calls itself "temporary storage during the
development of the build/compile migration script", and that pin file
explicitly instructs readers to "re-verify commit reachability … rather than
assuming immutability the way a tagged tarball would guarantee." Evidence
whose reproduction depends on a mutable upstream pin must be self-contained.

Against that, the entire measured upside of trimming is bounded by the
**3.2 MiB** of packed history the three `.op`-card trees occupy. Discarding
the repo's only record of the deck's resolved device physics to reclaim ~3 MiB
is not a trade this repo should make.

## Alternatives considered

- **Drop the `.op` card, keep `op` in the `.control` block** (PR #25's ~70x
  measurement; the strongest alternative). Preserves every value
  `run_pvt_sweep.sh` parses and every value quoted in a record `.md`, and
  would shrink future logs ~120x. Rejected on cost/benefit *and* on principle:
  the saving is capped at ~3.2 MiB of permanent history (the `du` figure of
  ~111M overstates it ~34x), and what it discards is the resolved
  model-parameter evidence described above — irrecoverable for
  `sim/sg13cmos5l-*` records given their mutable PDK pin. The "recoverable on
  demand, since the parsed CSV plus the committed netlist snapshot make each
  point exactly reproducible" argument in #26 holds only while the pinned PDK
  install can be reconstituted bit-for-bit, which SG13CMOS5L's own pin file
  disclaims.
- **Gzip the per-point logs in place** (`*.log.gz`). Measurably *worse* than
  doing nothing. The 9.9M record dir above costs 191 KiB in git as plain
  text; the same directory as `tar -czf -9` is 1,102,398 bytes (~1.05 MiB,
  5.6x larger), and per-file gzip is worse still (45 × ~26 KB ≈ 1.17 MB, no
  cross-file sharing) — because pre-compressed blobs defeat the delta
  compression that is doing the real work here, and every re-run would then
  add a fresh ~1 MiB instead of deltaing to near-zero. It would also break
  `git grep` over the evidence and the `*.log` glob the evidence-format
  checker requires, for negative benefit.
- **Keep the full dump for the typical corner only, trim the rest.** Cheap to
  implement and preserves a sample of the model dump. Rejected: a skewed
  corner (`wcs_125c_3.63v`, `sf_*`) is where a young deck is most likely to
  resolve a parameter wrongly, so trimming exactly there inverts the
  evidence's value. It would also make `corners/` heterogeneous, which a
  future reader cannot distinguish from an incomplete run.
- **Keep full logs but exclude `corners/` from CI-committed runs.** Moot as
  written: #16 landed checker-only, no CI path produces evidence, and
  `sim/README.md` already states that rule. Folded into this decision as
  item 4 rather than kept as a separate option.
- **Cap retention (keep only the N newest records per experiment).** Directly
  contradicts the append-only rule and the mechanical check that enforces it,
  and would require the history rewrite this decision exists to avoid. Not
  pursued; the delta-compression measurement shows old records are nearly
  free anyway (~1.6 KB for all of `sim/`'s superseded history).

## Consequences

- **No existing record is affected.** Nothing under `sim/*/corners/`,
  `sim/*/netlist-snapshots/` or `sim/*/records/` is edited, deleted,
  recompressed or re-run by this decision, and no git history is rewritten.
  The append-only rule already forbade all of that; this record restates it
  so the intent is not ambiguous.
- **No testbench changes.** The three `.op`-card templates keep their card;
  the other 19 experiments' templates, which never carried one, are not
  required to add one retroactively (their records are already landed and
  append-only). Item 1 above applies to testbenches written from here on.
- **Future `run_pvt_sweep.sh` output is unchanged**, so a 45-point sweep of
  `core-open-loop-bias-pex` continues to add ~10-20M to the working tree and
  a few hundred KiB to history per re-run.
- **The working-tree cost is real and is accepted.** A fresh checkout of this
  repo carries 157M of `sim/` today and will keep growing; only the *history*
  cost is nearly flat. Anyone doing shallow/sparse work can
  `git clone --filter=blob:none` or sparse-checkout `sim/*/corners`, but the
  default clone is not optimised and this decision does not promise it will
  be.
- **This constrains #16's successors, not #16 itself.** Any future proposal to
  run sweeps in CI and commit their records must supersede this record
  (item 4), because CI-minted records are the one mechanism that would turn
  occasional growth into continuous growth — the scenario the delta-
  compression argument above does *not* cover.
- **The decision is falsifiable and self-expiring** via item 5's two
  thresholds. If `sim/` outgrows them, the right response is a superseding
  record, not a silent trim.
- **Not touched by this record**: nothing under `spec/porting-plan.md` §6
  (ratification is tracked by #125 / PR #128, and no row is ratified). This
  is an evidence-retention convention, not a circuit or target-spec change.
