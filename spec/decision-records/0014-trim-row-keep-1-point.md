# 0014: Trim row — keep the 1-point 27 °C trim, explicitly: no second (hot) sort insertion and no CTAT knob, accepting the measured ~2.6% (3σ) trimmed spread

- **Status**: proposed — ratified only by the two-key release run through
  `2am` `scripts/ratify-key.sh` (operator ruling on #285, per 2am#1056), not
  by a direct status flip and not by this author's assertion
- **Date**: 2026-10-03
- **Decided by**: operator ruling (rjwalters, #285, 2026-10-02); recorded by
  the Loom Builder agent, issue #285. Every number below is re-derived from
  committed records by `sim/tools/project_trim_strategies.py` (re-run
  2026-10-03, output identical to `0013`'s tables), not copied from the issue.

Numbering note: `0013` is the highest number on `main`. `0012` is reserved by
the open, unmerged PR #270 (`0012-trimmed-line-disposition.md`), so this
record takes **`0014`**, following `0013`'s own precedent of not reusing a
number held by an in-flight PR.

## Context

`0011` ratified the Trim row — *"1-point at 27 °C; range ≥ ±15%; resolution
≤ 0.25%/step; magnitude only"*. #229 built it, and the Trim row's own numbers
are met (`sim/trim-coverage/`). The trimmed line behind it is not: the
trim-domain MC (`sim/closed-loop-vref-trim-mc/`, N=300/point) found the one
knob converts offset into TC. `0013` (#267) then measured every candidate
second knob's column (`sim/trim-knob-jacobian/`) and found that **±0.5% is
reachable on this block only with a second, CTAT knob and a second, hot sort
insertion together**. It declined the knob under the 1-point row and filed
the Trim-row question as #285. That is this record's question: does the Trim
row move to 2-point (room + hot)?

The evidence, with what is measured kept apart from what is projected
(`max_T |vref(T) − 1.050|/1.050` over {−40, 27, 125} °C, N≈300/point,
typ/bcs/wcs):

| strategy | new silicon | sort insertions | 3σ | within ±0.5% | kind |
|---|---|---|---|---|---|
| S0 as built: R1 ladder, 27 °C null | none | 1 | 2.60 / 2.52 / 2.59% | 28.5–31.7% | **measured**: the trim-domain MC; the script reproduces its digest to the digit |
| S2 S0 + code-offset rule read off `code*` | none | 1 | 2.08 / 2.02 / 2.10% | 26.9–29.4% | projection |
| S1 R1 ladder, minimax aim | none | ≥2 | 2.07 / 1.98 / 2.05% | 35.5–36.1% | projection |
| S4 R1 ladder + CTAT knob, 27 °C observables | CTAT knob | 1 | 1.35 / 1.31 / 1.35% | 40.9–42.1% | projection |
| S3 R1 ladder + CTAT knob, minimax aim | CTAT knob | ≥2 | 0.056 / 0.055 / 0.056% | 100% | projection |

Each projection superposes a knob's **measured** column onto each committed
MC die's own three-temperature state. That assumes linearity ~7× beyond the
measured ±20 mV, die-independent columns, and three temperatures only. It
also leaves out the CTAT DAC's and its generator's own mismatch. Adding the
systematic 8-temperature bow (also deterministic and measured) gives S3 a
projected **~0.27–0.5%** in total, against **~4.2%** as built on the same
accounting.

The cost side has three measured or estimated parts and one part nobody has
supplied (`design/bandgap_trim_second_knob.md` §5):

- **Silicon** (estimate): ≈ 2,000–4,000 µm², about a second trim ladder, or
  6–12% of the 271.47 × 126.59 µm top assembly.
- **Quiescent current** (estimate against measured headroom): +1 µA nominal,
  up to +3 µA at full scale. The headroom is 8.2 µA: the worst committed Iq
  is 41.78 µA at `bcs`/125 °C/3.63 V against the ratified `< 50 µA`.
- **Decode / LVS**: a second mask option. It needs klayout-tools#2653 landed.
- **Test cost: a second, hot wafer-sort insertion. There is no figure for
  it.** No sort program is committed to this repo, and so are no per-insertion
  cost, hot-chuck throughput or test-time budget. No simulation can supply
  one.

## Decision

**Keep the Trim row 1-point at 27 °C, and say so explicitly.** The Trim row
in `README.md`'s target-spec table is amended from `0011`'s wording to:

> **Trim: 1-point @ 27 °C only — no second (hot) sort insertion and no
> second (CTAT/TC) trim knob; range ≥ ±15%; resolution ≤ 0.25%/step;
> magnitude only**

Range, resolution and temperature are unchanged. The amendment turns what
`0011` left implicit into a ratified scope statement. The block's trim flow is
one insertion at 27 °C with one magnitude knob. The CTAT knob specified in
`0013` is **not built**.

**The accepted consequence, stated plainly**: the block ships with the
measured trimmed spread of a 1-point trim. That is **3σ ≈ 2.6%** over
−40…125 °C (S0: 2.52–2.60%, mean+3σ 3.60–3.69%, 28.5–31.7% of dies inside
±0.5%). The ±0.5% that 0011 budgeted is not met, and this record knowingly
creates no path to it.

### The test-cost reasoning, stated rather than assumed

The decision rests on an **absent** input, and it says so:

1. **The cost of a hot insertion cannot be priced, because no sort program
   exists.** The question "can we afford a second insertion?" has no number
   behind it in this repo. This record neither assumes the cost is small
   enough to pay nor invents a figure.
2. **Absent a price, the default is the insertion the block already has.** A
   second insertion is a recurring per-die cost on every unit forever. The
   CTAT knob is a fixed silicon cost of 6–12% area and up to ~37% of the
   remaining Iq headroom. Either one is committed the moment the row moves.
   Its benefit is a **projection** (S3) that no testbench has confirmed yet.
   `0013`'s claim gate is a trim-domain MC with the knob and its DAC mismatch
   in the netlist. The operator ruled that unpriced recurring cost plus
   unmeasured benefit does not justify moving the row.
3. **Neither half alone is worth buying**, so no cheaper partial move exists:
   - a 2-point trim on the existing knob (S1) projects 2.07%;
   - the CTAT knob at one insertion (S4) projects 1.35% and was already
     rejected by `0013` against the free S2 rule at 2.08%;
   - only both together (S3) reach ±0.5%.

   So the choice is binary, between the as-built 1-point flow and the full
   2-point + CTAT flow.
4. **What would change the answer** (the revisit triggers named in the
   ruling): (a) a sort program appears and states a per-insertion cost or
   test-time budget, against which S3's benefit can be weighed; or (b) a
   customer requirement for ±0.5% (or anything tighter than ~±2.6% 3σ)
   arrives. Either one reopens this row through a superseding record. That
   record then inherits `0013`'s CTAT specification and claim gate unchanged.

### What this record does not do

- **It changes no target number.** Range, resolution, temperature and
  magnitude-only are `0011`'s values. The text amendment narrows the row's
  scope and relaxes nothing. It is still a change to a ratified row's
  wording, so it goes through the two-key gate (see Consequences).
- **It does not re-decide the trimmed line.** The Output-reference row's
  trimmed line belongs to `0011` / `0012` (PR #270, which re-casts it on
  measured evidence). Accepting the ~2.6% (3σ) spread here records what a
  1-point trim *delivers*. It does not move any line to make that number
  pass.
- **It does not set a stretch number.** `0012`'s stretch column stays `—`.
- **It does not reverse `0013`.** The CTAT knob's specification stays the
  design of record for a future 2-point proposal, and the second-ladder
  family stays closed on measurement.

## Alternatives considered

- **Supersede the Trim row to 2-point (room + hot) and build the CTAT knob to
  `0013`'s specification** (S3, projected ~0.27–0.5% total). This is the only
  path found to ±0.5%. It was not chosen because the deciding input, the cost
  of a hot insertion, does not exist in this repo, and because its benefit is
  still a projection. Choosing it would commit recurring test cost and
  6–12% area with no price on the first and no testbench under the second.
  It is reserved for the revisit triggers above.
- **2-point trim with the existing knob only** (S1, 2.07%). Rejected: it pays
  the unpriced insertion for a 0.5-point gain that the free S2 rule nearly
  matches (2.08%). `0013`'s measured 3.07:1 exchange rate caps it.
- **Build the CTAT knob at a single insertion** (S4, 1.35%). Already rejected
  by `0013` (area and Iq cost to beat a free rule by 0.7 points, still ~2.7×
  outside ±0.5%). Nothing here changes that arithmetic.
- **Adopt the S2 code-offset rule now** (2.02–2.10%, no silicon, no extra
  insertion). Not adopted. It is a sort-program rule and there is no sort
  program to carry it. It is also a projection that trades away some
  27 °C accuracy (26.9–29.4% inside ±0.5% vs 28.5–31.7%). It stays the
  free option to price first if a sort program appears.
- **Defer: leave the row unrecorded and #285 open.** Rejected by the operator
  ruling. `0013` and #285 would keep pointing at each other, and "1-point" would
  stay an unexamined default instead of a decided scope.

## Consequences

- **`README.md`'s Trim row carries the amended wording above.** `0011` is not
  edited, because ratified records are superseded, never rewritten. This
  record supersedes **only the wording** of `0011`'s Trim row. Every `0011`
  number stands.
- **#285's 2-point branch is not triggered.** No CTAT knob schematic and no
  CTAT trim-domain MC are built, so #285's acceptance criteria 2 and 3
  (knob + N ≥ 300 MC, then a tighter-line record) do not apply under this
  outcome. They stay the exact obligations of any future 2-point proposal.
  `sim/trim-knob-jacobian/` and the projection script stay as committed
  evidence. No `sim/` record is re-run or reinterpreted.
- **#268's AC 4** (reconsidering the boxtc-trim ±1-code gate) stays a
  renumbering question. No new knob exists to reconsider it against.
- **klayout-tools#2653** is not needed for a *second* mask option on this
  block. Its status upstream is unaffected.
- **The bad consequence**: the block has no path to ±0.5%. Its trimmed
  accuracy is what one 27 °C insertion on one coupled knob delivers. That is
  measured at 3σ ≈ 2.6% and gets no better without new silicon and new test
  time. A buyer-facing line tighter than the measured 1-point spread cannot
  be claimed while this row stands.
- **Two-key gate**: this record changes a ratified row's text, so it is
  ratified by the two-key release in `2am` (`ratify-key.sh check` →
  `apply --key ee` → `apply --key market` → `release`), run by non-author key
  holders before merge, per the operator ruling and 2am#1056. It must not be
  ratified by editing its Status line. On any non-clean verdict the PR is held
  and the finding is escalated.
- **Revisit**: a sort program with a stated insertion cost, or a ±0.5%
  customer requirement, reopens this row through a superseding record. Its
  starting point is `0013`'s CTAT specification and claim gate, and the S2
  rule as the free baseline to price first.
