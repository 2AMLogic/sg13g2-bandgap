# 0009: Output-reference row disposition — re-cast to the core's TC-null operating point (1.050 V) with evidence-derived untrimmed/trimmed lines and a Trim row

- **Status**: proposed — ratified by operation of the two-key release gating this
  record's PR (see Consequences); not ratified by this author's assertion
- **Date**: 2026-09-21
- **Decided by**: Loom Builder agent, issue #221 (disposition A, numbers
  derived, not copied)

Numbering note: this record is `0009` per `TEMPLATE.md`'s numbering rule —
`0007` is currently used **twice** on `main` (`0007-sim-evidence-log-retention.md`
and `0007-target-spec-ratification.md`, tracked by #223) and `0008` is taken
(`0008-two-key-ratification-review-outcome.md`, PR #224).

## Context

Both ratification keys declined the Output-reference row as ratified by
`0007-target-spec-ratification.md` (EE `request-changes`, market `escalate`,
`ratify-key.sh release` → NOT-ELIGIBLE with relax-after-measured-FAIL detected;
verdicts and findings in
[`0008-two-key-ratification-review-outcome.md`](0008-two-key-ratification-review-outcome.md)).
Issue #221 is the tracker for the deliberate disposition both keys asked for.
Three committed-evidence facts force it:

1. **±1% untrimmed is unreachable for this core, independent of any systematic
   offset.** The seeded N=300 device-mismatch Monte Carlo
   ([`sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md`](../sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md),
   negative control exactly zero-spread) puts untrimmed 3σ/mean at
   **13.04%** at typ/27 °C (σ = 45.486 mV, mean 1.046711 V) and
   **12.09–14.60%** across the bcs/wcs × −40/125 °C corner points. A ±1% band
   at 1.2 V is ±12 mV; the mismatch scatter alone is ~13× that.
2. **The systematic miss is 11.94–13.08% low across the 45-point post-layout
   PVT grid, with 0/45 inside `[1.188, 1.212]` V.** Re-derived here from the
   committed
   [`sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.csv`](../sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.csv)
   (`vref_3ms_v`, 45 rows: 1.04309–1.05667 V, mean 1.04980 V; nominal
   typ/27 °C/3.30 V point 1.05048 V). This is the single-degree-of-freedom
   consequence of the R1=511 µm TC retune (#134), not a design error.
3. **Both sibling bandgaps met the numerically identical situation and
   re-cast the row** — `gf180-bandgap` `0003` (±2% untrimmed + a ratified
   Trim row: range ≥ ±5%, resolution ≤ 0.25%/step, at 27 °C) and
   `sky130-bandgap` `DR-005` (±2% untrimmed / ±0.5% trimmed + a Trim row,
   derived from a measured offset budget). Their **numbers** cannot be copied
   here: their untrimmed 3σ mismatch is ~1.4–1.5% of output; this PDK's is
   ~13%. The **method** — set the untrimmed line to what the block's own
   mismatch evidence supports, and make a trimmed line the buyer-facing
   accuracy backed by a Trim row — is exactly what this record adopts.

The physics that sets the nominal: this core is a Brokaw NPN sum
(`design/bandgap_core.sch`), `vref = VBE(Q3) + I·R1` with
`I = VT·ln(8)/R2`, so the R1/R2 ratio sets **both** the output level and the
PTAT gain that nulls TC — one knob. At the measured TC-null ratio
(R1/R2·ln(8) ≈ 12.85, post-#134) the nominal post-layout operating point is
VBE(Q3) = 0.70890 V + I·R1 = 0.34158 V = **1.05048 V** (PEX CSV, nominal
point). The original ~1.2 V nominal was a provisional sizing assumption
(VBE ≈ 0.75 V assumed, R1/R2·ln(8) ≈ 17.5) whose measured TC was
349–376 ppm/°C — 7× over the ratified < 50 ppm/°C row — which is why #134
retuned it away. npn13g2's HBT VBE and its TC-null PTAT gain simply do not
sum to 1.2 V: **on this PDK, 1.2 V and a nulled TC are mutually exclusive at
this core's one knob.**

## Decision

**Disposition A — sibling-parity re-cast, with SG13G2-derived numbers.** The
Output-reference row in `README.md`'s target-spec table is re-cast as:

> **Output reference: 1.050 V — ±16% untrimmed (3σ, N=300 mismatch MC +
> process/temp/supply corners, −40…125 °C); ±0.5% trimmed (1-point trim,
> 27 °C)**

and a new row is added:

> **Trim: 1-point at 27 °C; range ≥ ±15%; resolution ≤ 0.25%/step;
> magnitude only**

### The nominal: 1.2 V → 1.050 V

1.050 V is the TC-null operating point itself: the PEX grid mid is 1.04988 V
and the nominal point is 1.05048 V, so the re-targeted nominal sits at the
center of the block's own measured PVT envelope. Holding the nominal at
~1.2 V would make every accuracy number a restatement of the #134 trade
(until a second design knob exists, none does — see Alternatives). This is
the deliberate, reviewed way `0007` itself contemplated ("retargeting the
nominal `vref` value itself to something nearer the retuned design's natural
operating point") but did not decide.

### The untrimmed line: ±16% (3σ) — derived, not copied

Worst-case 3σ deviation of an untrimmed die from the 1.050 V nominal, from
the committed records:

| Term | Value | Source |
|---|---|---|
| Worst MC corner mean offset vs 1.050 V | 0.85% (bcs/125 °C mean 1.041041 V) | MC record |
| Worst MC corner 3σ/mean | 14.60% (bcs/125 °C; 13.04% at typ/27 °C) | MC record |
| 3σ expressed vs 1.050 V nominal | 14.47% | derived |
| **Worst-case 3σ total** | **≈ 15.3%** | derived (sum, conservative) |

The PVT mean envelope (±0.65% around grid mid, PEX CSV) is already inside
the corner-mean offset term above; the sum is linear (worst-case), not RSS.
The line is set at **±16%** — 15.3% rounded up, so the ratified line covers
the derivation rather than trimming it. Empirical sanity: the worst single
draw across all six N=300 MC points is 0.8647 V (a ≈3.5σ tail event at
bcs/125 °C) — outside any 3σ line by construction, which is what "3σ" means.

### The trimmed line: ±0.5% (1-point, 27 °C)

A 1-point trim at 27 °C corrects each die's offset at the trim temperature
(the trimmable set: R1/R2 ratio mismatch + mirror and ΔVBE mismatch — the
entire 13%-class scatter of fact 1). What remains across −40…125 °C:

| Term | Worst case | Source |
|---|---|---|
| TC drift from the 27 °C trim point (ΔT = 98 °C, box-method worst corner ~20.2 ppm/°C, #222) | ≈ 0.20% | derived |
| Trim quantization (±½ step at 0.25%/step) | 0.125% | derived |
| **Worst-case residual** | **≈ 0.33% < 0.5%** | derived |

leaving ~0.17% headroom for trim-induced TC degradation, which is real and
must be re-measured once a trim network exists (obligated below). The
±0.5%-with-trim figure already sits in today's table as the stretch column
with no Trim row and no trim network behind it; this record promotes it to
the buyer-facing trimmed line **backed by** the Trim row, per the market
key's stated exit criterion ("a trimmed line a buyer can compare … backed
by a ratified Trim row (range, resolution, temperature at which it is
performed) — with the untrimmed line set to whatever the block's own
mismatch evidence supports"). For comparison shape only: ±0.5% initial
accuracy is the LM4040 C-grade line (SLOS456Q); this row's ±0.5% additionally
includes full-range temperature drift, which the comp convention specs
separately. The competitiveness ruling itself belongs to the market key, not
this record.

### The Trim row: range ≥ ±15%, resolution ≤ 0.25%/step, 1-point at 27 °C

- **Range**: must cover the worst per-die offset at the trim temperature.
  From the typ/27 °C MC point: worst 3σ die sits 13.31% below / 12.68%
  above the 1.050 V target (mean 1.046711 V, 3σ = 0.136458 V); add the
  ±0.65% PVT mean envelope and round out → **≥ ±15%**. The trim targets
  1.050 V — each die's ratio corrected **back toward the TC-null point** —
  never toward 1.2 V (see Alternatives).
- **Resolution**: ≤ 0.25%/step keeps quantization (±0.125%) inside the
  ±0.5% trimmed budget above with the drift term; same value both siblings
  ratified, reached here from the budget rather than copied.
- **Temperature**: 27 °C, matching both siblings' 1-point wafer-sort-style
  convention.

### Sibling divergence, addressed explicitly

- **Adopted from the siblings**: the re-cast itself (the method of setting
  the untrimmed line from the block's own measured mismatch evidence and
  adding a ratified Trim row behind a trimmed line), the Trim row's shape
  (1-point, 27 °C, magnitude-only, ≤ 0.25%/step), and sky130's "the spec
  moves deliberately, not silently" framing.
- **SG13G2 departs on the numbers, derived by the same method**: ±16%
  untrimmed vs their ±2%, because this PDK's measured mismatch scatter
  (12.1–14.6% 3σ/mean) is an order of magnitude worse than sky130's
  1.39–1.54%.
- **SG13G2 departs on the nominal**: 1.050 V vs their 1.20 V, because their
  CMOS parasitic-PNP cores reach TC-null near 1.2 V while this PDK's npn13g2
  HBT (VBE(Q3) = 0.709 V measured PEX, TC-null gain R1/R2·ln(8) ≈ 12.85)
  sums to ~1.05 V at null. A 1.2 V nominal on this PDK is a 349–376 ppm/°C
  core (measured, pre-#134) — it would sacrifice the ratified TC row to
  cosmetically hold the old nominal.

### This is a re-target, not a relaxation to make results pass

Said in this record's own words: the previous ±1% untrimmed line was a
ported assumption inherited from sibling specs whose measured mismatch
(1.4–1.5% 3σ) happens to fit under a ±2% line; this PDK's own committed
mismatch and PVT evidence shows the equivalent derivation lands at ±16%
untrimmed, and that the ~1.2 V nominal was never this core's TC-null
operating point — it was a provisional sizing input corrected by #134. The
numbers above are derived from measured records committed before this
decision (MC 2026-09-09, PEX 2026-09-05, retune 2026-08) and re-derived
here from their CSVs; none of them was chosen to make a failing measured
result pass. No `sim/` record is reinterpreted: every previously-committed
record already disclaimed spec conformance for this row. What was
`unmet` under the old line is `met-by-construction-3σ` under the derived
one — and the derived line is wide enough that the committed evidence
demonstrates it rather than merely aspiring to it. If future evidence
(trim-domain MC, post-trim TC) shows a term was under-budgeted, the row is
fixed by a superseding record, never by silent re-relaxation.

## Alternatives considered

- **Disposition B — defend ±1% untrimmed on physical merits.** Rejected: no
  evidence exists that any second knob (topology change, curvature
  correction, per-die trim moving the untrimmed line) reaches ±1% untrimmed
  on this PDK, and the mismatch scatter that forbids it is set by device
  physics, not by the R1/R2 ratio that closed the TC row. #221 allows B
  only with evidence; there is none to cite, and this record will not
  speculate one into existence.
- **Trim the output back to 1.2 V (keep the old nominal, trim closes the
  12–13% gap).** Rejected on the core's own one-knob physics: trimming
  vref from 1.05 V to 1.2 V is a ratio move back toward the pre-#134
  operating point whose measured TC was 349–376 ppm/°C — it would re-open
  the ratified TC row to cosmetically preserve a nominal this PDK's devices
  do not support. The trim defined here corrects each die toward the
  TC-null point instead, which restores both vref and TC.
- **Copy the siblings' ±2% untrimmed verbatim.** Rejected: parity is on the
  *method* (derive from the block's own mismatch evidence), not the number;
  this block's scatter is ~10× theirs. A ±2% line here would be violated by
  the committed MC evidence itself.
- **Keep the ~1.2 V nominal and widen only the accuracy band (±26%-class
  untrimmed).** Rejected: an accuracy band that wide is a restatement of the
  systematic miss, not a specification; no buyer or testbench can use it,
  and it would leave the table implying the block is a 1.2 V reference that
  it measurably is not.
- **Leave the row "ratified but unmet" with a trim-network tracker (0007's
  original disposition).** Rejected: both keys explicitly declined it (EE:
  physics and unacknowledged sibling precedent; market: no public bar
  exists for an untrimmed ±1% line at all), and #221 exists because that
  disposition did not clear the gate.

## Consequences

- **`README.md`'s target-spec table** carries the re-cast Output-reference
  row and the new Trim row from this record; the status prose stops citing
  the closed issue #9 as the trim-network tracker and cites the new open
  trim-network design issue instead. `0007` is not rewritten (ratified
  records are superseded, never edited): this record supersedes `0007`'s
  Output-reference row and its "re-target is explicitly not decided here"
  deferral. `0007`'s Consequences pointer at this issue — the trim-network
  loop it opens — is closed by this record naming the obligated work and
  its tracker.
- **The ±0.5%-with-trim stretch is consumed**: it becomes the trimmed
  target line, so the Output-reference row's stretch column becomes `—`
  until a future record has evidence for a tighter one.
- **Design work this row now obligates** (none of it exists today —
  `design/README.md`'s first-pass scope cut stands): a trim network on the
  core's R1/R2 divider realizing range ≥ ±15% at ≤ 0.25%/step (binary-weighted
  segments, sibling-style); its device selection and segment sizing; layout
  area for it; **and its own evidence** — a trim-domain mismatch MC and a
  post-trim TC re-measurement (the ±0.5% budget's 0.17% headroom for
  trim-induced TC degradation is an estimate to be verified, not a
  measurement). Tracked as
  [#229](https://github.com/2AMLogic/sg13g2-bandgap/issues/229) (filed with
  this PR, replacing the closed issue #9 as the tracker); the row is
  the obligation, the issue is the schedule.
- **Verification burden shifts, honestly**: until the trim network exists,
  the committed evidence demonstrates the **untrimmed ±16% (3σ)** line
  (MC + PEX records above are exactly that demonstration) and supports the
  ±0.5% line only as a budgeted target. A future characterization pass
  verifies the untrimmed line over full PVT and, once trim exists, the
  trimmed line; a miss is handled by fix-or-superseding-record, never
  silent relaxation.
- **Two-key gate**: this record changes target numbers, so the
  relax-after-measured-FAIL rule applies to its own PR — the review must
  run (`ratify-key.sh check` → `apply --key ee` → `--key market` →
  `release`) **before** merge, by non-author key holders. It is ratified by
  the operation of that release (ee `approve` + market `competitive`
  applying `loom:auto-merge-ok`); on any non-clean verdict the PR is held
  or withdrawn and the finding escalated, never force-merged — the exact
  inversion of the #220 sequence this record exists to complete.
- **#223 unblocks**: its DR-0001/DR-0002 `proposed`→`ratified` flip was
  gated on this disposition; that flip remains #223's own change, not this
  record's.
