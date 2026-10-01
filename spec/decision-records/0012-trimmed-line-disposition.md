# 0012: Trimmed-line disposition — re-cast to ±4.5% (3σ) on the aids-free trim-domain evidence, because no 1-point trim of this core reaches ±0.5%

- **Status**: proposed — ratified by operation of the two-key release gating this
  record's PR (see Consequences); not ratified by this author's assertion
- **Date**: 2026-10-01
- **Decided by**: Loom Builder agent, issue #265 (numbers re-derived from the
  committed CSVs, not copied from the issue)

Numbering note: `0011` is the highest number on `main` as of this record
(`0011-output-reference-row-disposition.md`), so this record takes `0012`.
Re-checked against `main` immediately before the PR, per `TEMPLATE.md`'s
numbering rule and the duplicate-number CI check added by #228.

## Context

[`0011`](0011-output-reference-row-disposition.md) re-cast the
Output-reference row and set its buyer-facing **trimmed** line at **±0.5%**
(1-point trim, 27 °C) from a three-term budget — TC drift from the trim point
≈ 0.20%, trim quantization 0.125%, leaving ≈ 0.17% headroom for trim-induced
TC degradation — and said so in its own words: *"an estimate to be verified,
not a measurement"*, obligating a trim network plus *"a trim-domain mismatch
MC and a post-trim TC re-measurement"*, and committing that *"if future
evidence (trim-domain MC, post-trim TC) shows a term was under-budgeted, the
row is fixed by a superseding record, never by silent re-relaxation."*

#229 built the network (255-unit binary-weighted `rppd` ladder in series with
R1, strap-decoded, default code 128) and ran both benches. The Trim row's own
numbers are met on that evidence (`sim/trim-coverage/`: step 2.443 mV =
0.2327%/step ≤ 0.25%; range +29.6%/−29.8% ≥ ±15%; exact binary weights;
monotonic; zero railed dies in the MC). **The ±0.5% trimmed line is measured
not met**, and this record is the superseding record `0011` promised.

Three committed-evidence facts force the disposition. All three are
re-derived here from the CSVs, not quoted.

### 1. A perfect die, perfectly trimmed, already misses ±0.5%

`sim/closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv`
runs the trim-bearing core with **no mismatch** on an 8-temperature grid
across `{typ, bcs, wcs, sf, fs}` × `{2.97, 3.30, 3.63} V`. Taking the
quantity the trimmed line is actually about — `max_T |vref(T) − vref(27 °C)|`
as a percentage of 1.050 V — at the default code 128:

| corner | 2.97 V | 3.30 V | 3.63 V |
|---|---|---|---|
| typ | 0.486% | 0.486% | 0.505% |
| bcs | 0.552% | 0.552% | **0.581%** |
| wcs | 0.333% | 0.333% | 0.352% |
| sf | 0.476% | 0.486% | 0.505% |
| fs | 0.486% | 0.486% | 0.505% |

Zero mismatch, zero quantization, the die sitting exactly on its code: **three
of five corners are already outside ±0.5%**, and the ±1-code band the same
bench gates on reaches 0.657% (bcs/3.63 V/code 127). No per-die trim can
remove this term — it is the deterministic residual TC of the trim-bearing
core, the same for every die. **±0.5% is therefore unreachable by any 1-point
trim of this core, independently of mismatch, quantization, or ladder
linearity.**

### 2. `0011`'s 0.20% drift input was understated two ways, both measurable

- **Unit error.** `0011` took the box-method worst corner (~20.2 ppm/°C) and
  multiplied by the 98 °C span from the trim point. But box TC is defined as
  `1e6·(vmax − vmin)/(165·vref(27 °C))` over the **165 °C** grid, and this
  core's `vref(T)` is non-monotonic (the very reason `0010` adopted the box
  method). The quantity the budget needs is `max_T |vref(T) − vref(27 °C)|`,
  which the committed #222 CSVs give directly: **0.295%** pre-layout
  (`bcs`/3.63 V) and **0.324%** post-layout — already ~1.5× the 0.20% input,
  on `0011`'s own source evidence.
- **Convergence aids.** The #222 benches carry `rshunt=1e9` / `gmin=1e-9`.
  #229's benches drop them, with the A/B recorded in
  `sim/closed-loop-vref-boxtc-trim/README.md`: on the ladder-bearing netlist
  the aids are worth 37 mV at code 128/typ/27 °C (254 interior series nodes
  at 1 GΩ ‖ 1 nS leak ~0.55 µA out of the output branch), and on the
  **pre-trim** #222 netlist itself they still lift the settled 125 °C value
  by 2.2 mV. Aids-free, the same measurement reads **0.486%** at typ/3.30 V
  (fact 1) — ~2.4× the budgeted 0.20%.

The aids-free bench cross-validates itself: its settled transient agrees with
a plain `.op` of the same netlist to five significant figures, and its
`*_tranval_*` rows re-demonstrate that per corner inside the committed
evidence.

### 3. The per-die spread is a measured code-correlated drift pivot

`sim/closed-loop-vref-trim-mc/records/20260930-232155-affdefe-draws.csv`
(N=300/point, seed 20260930, 1-point 27 °C trim through the real ladder).
Regressing each die's own `(vref(125 °C) − vref(27 °C))/1.050` on the trim
code that die's wafer-sort trim picked:

| point | slope | r | residual σ | usable draws |
|---|---|---|---|---|
| typ mismatch | +0.0577 %/code | +0.842 | 0.752% | 299/300 |
| bcs mismatch | +0.0590 %/code | +0.845 | 0.720% | 242/300 |
| wcs mismatch | +0.0575 %/code | +0.842 | 0.743% | 293/300 |

~71% of the post-trim drift variance is explained by `code*` alone. The
**deterministic** sensitivity from the box-TC bench is **+0.0775 %/code**
(signed 27 °C → 125 °C drift at typ/3.30 V, essentially linear across the
whole ladder: −10.45% at code 0, −0.486% at code 128, +9.32% at code 255).
The population slope is **74% of that deterministic detuning slope**, and the
population lands at codes **90…229** (σ ≈ 20 LSB), not 127…129.

Physically: the one knob sets both the output level and the PTAT gain. The
part of a die's 27 °C level error that is *not* PTAT-shaped (HBT VBE offset,
ΔVBE-generator error) can only be nulled at 27 °C by deliberately mis-setting
the PTAT gain — so a 1-point trim **converts offset into TC**, at the rate
measured above. Only ~26% of the population's level error is null-preserving.

This contradicts, with data, the premise stated in
`design/bandgap_trim_network.md` §2–§3 and in
`sim/closed-loop-vref-boxtc-trim/README.md` ("a correctly-trimmed die sits at
its own null whatever `code*` it lands on"), which is what that bench's
±1-code claim gate rests on. The mechanism, and whether to build a second
knob that separates level from gain, is tracked as **#267** — a design
question, not this record's.

## Decision

**Re-cast the trimmed line of `README.md`'s Output-reference row to what the
block's own trim-domain evidence supports.** The row becomes:

> **Output reference: 1.050 V — ±16% untrimmed (3σ, N=300 mismatch MC +
> process/temp/supply corners, −40…125 °C); ±4.5% trimmed (3σ, 1-point trim
> at 27 °C, −40…125 °C)** — stretch `—`

Everything else in `0011` stands: the 1.050 V nominal, the ±16% untrimmed
line, and the Trim row (1-point at 27 °C; range ≥ ±15%; resolution
≤ 0.25%/step; magnitude only), which is **met** on committed evidence. This
record supersedes exactly one sentence of `0011`: its ±0.5% trimmed line and
the three-term budget behind it.

### The trimmed line: ±4.5% (3σ) — derived by `0011`'s own method

`0011` set the untrimmed line as (worst corner-mean offset) + (worst 3σ),
summed linearly and rounded up. Same method here, on the trimmed population's
worst verified temperature (125 °C), deviations taken from 1.050 V:

| point | mean | σ | \|mean\| + 3σ |
|---|---|---|---|
| typ mismatch | −0.140% | 1.382% | 4.29% |
| bcs mismatch | −0.283% | 1.336% | 4.29% |
| wcs mismatch | −0.103% | 1.370% | 4.21% |

| Term | Worst | Source |
|---|---|---|
| Trimmed-die deviation at the worst verified temperature, \|mean\| + 3σ | 4.29% | trim-MC draws CSV, re-derived |
| Non-converged draws re-included (`bcs` 58/300 skew +7.5 LSB in `code*`; imputed via the fact-3 regression) | +0.01% | derived |
| 8-temperature extremum the MC's 3 verify temperatures do not sample (box bench 0.486% vs MC negative control 0.434%, same die) | +0.05% | boxtc-trim vs trim-MC |
| Supply axis (MC runs 3.30 V only; deterministic drift spread 2.97→3.63 V) | +0.03% | boxtc-trim |
| Post-layout: worst committed PEX-vs-schematic box-TC delta (2.482 ppm/°C × 165 °C) | +0.04% | `closed-loop-vref-pvt-pex-boxtc` |
| **Worst-case 3σ total** | **≈ 4.42%** | derived (linear sum, conservative) |

The line is set at **±4.5%** — rounded up so the ratified line covers the
derivation rather than trimming it, exactly as `0011` rounded 15.3% → ±16%.
Empirical check on the committed draws: **99.59–99.67%** of converged draws
fall inside ±4.5% (a 3σ Gaussian line would cover 99.73%), against
94.65–95.90% inside ±2.6%. The worst single draw anywhere is 6.79% — a tail
event outside any 3σ line by construction, as with the untrimmed line.

### Why not ±2.6%, the number the trim-MC digest reports

`three_sigma_max_dev_pct` in the digest CSV (2.52–2.60%) is `3 × σ` of
`max_dev_pct`, a **folded magnitude** statistic with its mean dropped — the
bench's own internal gate, not a two-sided accuracy line. Measured coverage
inside ±2.6% is 94.65% (typ) / 95.45% (bcs) / 95.90% (wcs): a ~2σ band.
Ratifying it as a "3σ" line would mislabel the coverage by an order of
magnitude in escape rate, and would break method parity with the untrimmed
±16% line, which is `|mean| + 3σ` of the distribution itself.

### The stretch column stays `—`

`0011` consumed the old ±0.5%-with-trim stretch; this record does not put a
number back. The evidence that would set one does not exist: with the
`code*`-correlated term removed by regression, the residual 3σ is still
2.16–2.26%, and what a **second** trim degree of freedom (or a 2-temperature
trim) would actually achieve is unmeasured. Naming ±0.5% as a stretch when
fact 1 shows the present architecture cannot reach it even with a perfect die
would be an aspiration, not a specification. A future record sets a tighter
line when #267 produces evidence for one.

### This is a re-target on measured evidence, not a relaxation to pass

Said plainly: a target widened **after** a measured FAIL is exactly the move
this repo's relax-after-measured-FAIL rule exists to catch, so the burden is
on this record to show the widening follows the measurement rather than the
measurement following the widening. What it shows is that `0011`'s ±0.5% was
never a measurement: it was a budget whose drift term was derived in the
wrong units from convergence-aided evidence, and whose central physical
assumption — that a 1-point level trim preserves each die's TC null — is
falsified by the first trim-domain MC ever run on this block. The new number
is derived from records committed **before** this decision (trim MC
2026-09-30, post-trim box TC 2026-10-01, both landed by #229 and merged by
PR #266), by the same arithmetic `0011` used for the untrimmed line, and no
committed `sim/` record is reinterpreted or re-run: every one of them keeps
the verdict it earned against the gate in force when it ran. The honest
consequence is recorded too, in Consequences below: **±4.5% trimmed is not a
competitive line**, and this record does not claim it is.

## Alternatives considered

- **Keep ±0.5% and mark the row "ratified but unmet" pending a design fix.**
  Rejected twice over: both ratification keys explicitly declined that
  disposition for this same row (`0008`), and fact 1 makes it worse than it
  was then — the line is now known to be unreachable by the ratified Trim
  row's own architecture, so the table would carry a number no amount of
  trimming effort can meet.
- **Re-cast the line at ±2.6%** (issue #265's own first candidate, the
  digest's headline statistic). Rejected on the coverage arithmetic above: it
  is a ~2σ band that would be published as 3σ, and it is method-inconsistent
  with the untrimmed line in the same row.
- **Defer the disposition until a re-laid-out PEX core is measured** (#265's
  third candidate). Rejected on magnitude: the committed PEX-vs-schematic
  box-TC delta is ≤ 2.482 ppm/°C (0.04% of span) and the PEX level offset at
  typ/27 °C (~3 mV) is trimmed out by construction — PEX moves this number in
  the third decimal place, not from 0.5% to 4.3%. Deferring would leave the
  row carrying a measured-FAIL line for the duration, which is the state
  `0008` already rejected.
- **Build the second trim knob first, then dispose the row** (#265's second
  candidate). Rejected *as a disposition*: a design change is not a spec
  decision, its schedule is unknown, and the row would carry a measured-FAIL
  line until it lands. Adopted instead as the path to a future tighter line,
  tracked as **#267**, with this record's stretch column left empty so that
  work has somewhere evidence-backed to land.
- **Drop the trimmed line from the row entirely and publish only the
  untrimmed ±16%.** Rejected: the market key's stated exit criterion asks for
  "a trimmed line a buyer can compare … backed by a ratified Trim row", and
  the Trim row is met. A measured trimmed line, even an uncompetitive one, is
  the comparable artifact; silence is not.
- **Widen the line to the worst observed draw (±6.8%) instead of a 3σ line.**
  Rejected: the untrimmed row is a 3σ line, the Trim row's coverage argument
  is a 3σ argument, and a worst-of-N line is an artifact of N rather than a
  specification.

## Consequences

- **`README.md`'s target-spec table** carries the re-cast trimmed line and
  the status prose that goes with it. `0011` is **not** rewritten (committed
  records are superseded, never edited): this record supersedes `0011`'s
  ±0.5% trimmed line and its three-term budget table, and nothing else in it.
- **`0011` itself is still `proposed`, and this record does not change
  that.** `gh api repos/2AMLogic/sg13g2-bandgap/pulls/230/reviews` returns an
  empty list: PR #230 merged on 2026-09-30 carrying
  `loom:operator-only`/`loom:operator-decision` with **no** ratification
  review posted, so the ±0.5% line this record supersedes never cleared a
  two-key release either — the same gap `0008` recorded against #220. Stated
  here because a reader could otherwise take "supersedes a ratified line" as
  given, and because this record's own PR must not repeat that path.
- **The row's buyer-facing accuracy is not competitive, and this record says
  so.** Against the comps `0008`'s market key cited — LM4040 D grade ±1%
  initial (SLOS456Q), REF3033-Q1 ±0.2% (SBVS131), REF2030 ±0.05% — a ±4.5%
  trimmed line is ~4.5× outside the loosest catalogue floor. The block's
  measured 1-point trim buys a 3.6× improvement (±16% → ±4.5%), not a
  catalogue-grade one. Whether that is acceptable for this block's purpose is
  the market key's ruling, not this record's; what this record owes is the
  honest number and the named path to a better one (#267).
- **The committed benches' gate constants are deliberately left alone by this
  record's PR.** `run_trim_mc.sh` still carries `TRIM_BUDGET_PCT="0.5"` and
  the boxtc-trim bench still carries its ~17.86 ppm/°C ±1-code cap derived
  from `0011`'s budget. Changing them while this record is `proposed` would
  convert a committed, honest FAIL into a PASS under an unratified record —
  the precise move `CLAUDE.md` forbids. Re-pointing them **after** a clean
  two-key release is tracked as **#268**.
- **The boxtc-trim bench's ±1-code claim gate does not bound a real
  population.** Its `OK` rows are correct for what they measure (±1 code),
  but fact 3 shows real dies land 90…229, so those rows must not be read as
  bounding trim-induced TC in the field. The bench README is annotated
  accordingly by this PR; re-designing the gate is part of #268.
- **An out-of-scope measurement is recorded and tracked, not disposed here**:
  the trim-bearing, aids-free core reads 20.2–38.6 ppm/°C box TC at the
  default code (45.7 ppm/°C across the ±1-code band) against #222's aided
  19.8/20.1 ppm/°C. The ratified TC **target** (< 50 ppm/°C) still holds
  everywhere; the **stretch** (< 20 ppm/°C) does not, and the aids-vs-ladder
  split is unmeasured. The TC row is a different ratified row with its own
  two-key history — disposing it here would put two decisions in one record.
  Tracked as **#269**.
- **#264's refreshed benches, when they land, are additional inputs to this
  line, not a re-opening of it.** If a refreshed trim-domain MC moves the
  number materially, a superseding record re-casts it — the same
  fix-or-supersede discipline `0011` committed to and this record is an
  instance of.
- **Two-key gate**: this record widens a ratified target number after a
  measured FAIL, so the relax-after-measured-FAIL rule applies to its own PR
  — the review must run (`ratify-key.sh check` → `apply --key ee` →
  `--key market` → `release`) **before** merge, by non-author key holders.
  It is ratified by the operation of that release; on any non-clean verdict
  the PR is held or withdrawn and the finding escalated, never force-merged.
  Until then the record's Status stays `proposed` and `README.md` labels the
  line as such.
