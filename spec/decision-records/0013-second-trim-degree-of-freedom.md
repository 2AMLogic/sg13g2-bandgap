# 0013: Second trim degree of freedom — do not build one under the ratified 1-point Trim row; the CTAT knob is identified and sized for whenever a 2-point row is proposed

- **Status**: proposed (this record changes no target number and sets no
  stretch number — see "What this record does not do")
- **Date**: 2026-10-02
- **Decided by**: Loom Builder agent, issue #267 (every number below
  re-derived from committed CSVs by `sim/tools/project_trim_strategies.py`,
  not copied from the issue)

Numbering note: `0011` is the highest number on `main` as of this record.
`0012` is **taken by an open PR** — PR #270 (`loom:pr`,
`loom:operator-only`/`loom:operator-decision`, OPEN and unmerged as of
2026-10-02) carries `0012-trimmed-line-disposition.md`. Per `TEMPLATE.md`'s
numbering rule ("re-check if another record may have landed concurrently, to
avoid a collision"), this record takes **`0013`** rather than the next number
free on `main`, which would collide with #270 the way #262 had to fix after
the fact. If PR #270 is withdrawn, `0012` stays unused; a gap is cheaper than
a duplicate, which the #228 CI check fails on.

## Context

`0011` ratified the Trim row — *"1-point at 27 °C; range ≥ ±15%; resolution
≤ 0.25%/step; magnitude only"* — and #229 built it: a 255-unit
binary-weighted `rppd` ladder in series with R1. The Trim row's own numbers
are met. The **trimmed line** behind it is not, and the first trim-domain MC
([`sim/closed-loop-vref-trim-mc/`](../../sim/closed-loop-vref-trim-mc/README.md),
N=300/point) found why: the one knob sets both the output level and the PTAT
gain, so nulling a die's 27 °C level deliberately mis-sets its gain. Measured,
a trimmed die's post-trim 27→125 °C drift regresses on its own `code*` at
**+0.0577 %/code** (r = +0.842, residual sd 0.752%), which is **74%** of the
**+0.0775 %/code** deterministic detuning slope — i.e. a trimmed die behaves
mostly like a *detuned nominal die*, and real dies land at codes **90…229**,
not 127…129. #267 is the tracker asking whether a second knob should be built
to break that coupling; PR #270's `0012` left its stretch column `—`
explicitly so this work would have somewhere evidence-backed to land.

Two artifacts were produced to answer it, and this record rests on them:

- **[`sim/trim-knob-jacobian/`](../../sim/trim-knob-jacobian/README.md)** —
  a new deterministic bench measuring each candidate knob's **column** in the
  `(level, drift)` plane on the real trim-bearing closed loop, 405/405 points
  PASS across `{typ,bcs,wcs,sf,fs}` × `{2.97,3.30,3.63} V` ×
  `{−40,27,125} °C` × 9 knob points, 0/15 corner/supply groups failing its
  gates.
- **[`design/bandgap_trim_second_knob.md`](../../design/bandgap_trim_second_knob.md)**
  — the evaluation: the column algebra, the three candidates measured, what
  each strategy would deliver, and what each would cost.

### The one measurement that decides most of the question

A trim knob is a **column**: the `(Δlevel, Δdrift)` pair it produces per unit
of authority. Two knobs are two degrees of freedom only if their columns are
not parallel; area, bit count, decode style and placement are irrelevant to
that test. Measured, per corner/supply group:

| knob | what it is | `ratio = Δdrift/Δlevel` (15 groups) | independent of the as-built ladder? |
|---|---|---|---|
| **A** | the as-built R1-side ladder | +0.3311 … +0.3348 | — (reference) |
| **B** | an `rppd` element in series with R2 ("a second ladder on R2") | +0.3247 … +0.3291 | **no** — within **1.9%** of A at every group |
| **C** | a VBE/R CTAT current injected into the output branch | −0.1584 … −0.1507 | **yes** — opposite in sign |
| **D** | a trim applied as a *scaling* of the whole reference | +0.0074 … +0.0112 | yes, and essentially drift-free |

Knob A's ratio is the first-principles `ΔT/T = +0.3265` to within 1.4–2.5%,
and knob C's is the measured `ΔVBE/VBE` (−0.1693…−0.1630) to within 6.4–7.6%.
So a knob's ratio is set by the **temperature shape** of the volts it adds,
not by its construction — which is why **every "obvious" knob on this
topology is collinear with the one already built**: a second R2 ladder, a
joint R1/R2 code, a ΔVBE-ratio trim, a Q3 current-density trim. All of them
scale a `VT`-proportional term, and a `VT`-proportional term carries its own
PTAT slope of exactly `level/T`. The exchange rate the as-built knob fights
is **3.07:1** (removing `d` of drift costs `3.07·d` of 27 °C level error).

### What each strategy would deliver, and what it would cost

Projected by `sim/tools/project_trim_strategies.py` from the three committed
records (`max_T |vref(T) − 1.050|/1.050` over {−40, 27, 125} °C, N≈300/point).
**These are projections, not measurements** — each knob's measured column is
superposed onto every committed MC die's own three-temperature state. S0
reproduces the committed digest's 3σ to the digit, which is their sanity
check.

| strategy | new silicon | sort insertions | 3σ (typ/bcs/wcs) | within ±0.5% |
|---|---|---|---|---|
| **S0** as built: knob A, 27 °C null | none | 1 | 2.60 / 2.52 / 2.59% | 28.5–31.7% |
| **S2** knob A + a code-offset rule read off `code*` | none | 1 | 2.08 / 2.02 / 2.10% | 26.9–29.4% |
| **S1** knob A, minimax aim | none | ≥2 | 2.07 / 1.98 / 2.05% | 35.5–36.1% |
| **S5** level-only knob (D), no R1 trim | scaling knob | 1 | 1.55 / 1.54 / 1.47% | 36.4–36.8% |
| **S4** knobs A+C set from 27 °C observables | CTAT knob | 1 | 1.35 / 1.31 / 1.35% | 40.9–42.1% |
| **S3** knobs A+C, minimax aim | CTAT knob | ≥2 | **0.056 / 0.055 / 0.056%** | **100%** |

Cost of the CTAT knob (knob C), from the evaluation's §5: ≈ 2,000–4,000 µm²
(roughly a second trim ladder, 6–12% of the 271.47 × 126.59 µm top assembly),
a **current-mode** ~7-bit DAC plus a VBE/R generator, ≈ 240 kΩ of `rppd` for
the reference resistor, and **+1 µA nominal / up to +3 µA at full scale** of
quiescent current — against only **8.2 µA** of headroom between the worst
committed Iq (41.78 µA, `bcs`/125 °C/3.63 V) and the ratified `< 50 µA`. It
also doubles the mask-option decode, and with it the LVS "a layout is one
code" problem already filed upstream as klayout-tools#2653.

## Decision

**Do not build a second trim knob.** Specifically, under the Trim row `0011`
ratifies — **1-point at 27 °C, magnitude only** — no second knob earns its
cost, and this record declines to build one. Three findings, each measured or
projected above, decide it:

1. **The whole "second ladder" family is ruled out by measurement, not by
   cost.** Knob B's column is within 1.9% of knob A's at all 15
   corner/supply groups. A second ladder on R2, a joint R1/R2 decode, a
   ΔVBE-ratio trim and a Q3 current-density trim are all the *same* degree of
   freedom the block already has — a singular 2×2, pure cost, zero benefit.
   This disposition is permanent and does not depend on the Trim row: it is
   topology, not economics.
2. **The knob #267's own framing asks for — a level-only knob — is
   insufficient even though it works.** Knob D is measured as a real,
   independent, nearly drift-free column (`|ratio_D| ≤ 0.0112`), and a trim
   built purely on it still projects 3σ **1.47–1.55%**. Because `code*`
   explains only ~71% of the post-trim drift variance, eliminating the
   trim-induced component leaves the population's **intrinsic** TC scatter
   (residual sd 0.72–0.75%), which no level knob of any kind reaches. The
   correction to #267's premise is therefore: *the problem is not that the
   trim adds TC, it is that nothing in the block trims TC.*
3. **The only knob worth building (the CTAT knob) does not pay for itself
   under a 1-point row.** With a single 27 °C insertion its best honest rule
   projects 3σ **1.35%** — against **2.08%** available from a population
   code-offset rule that costs *no silicon and no extra test time at all*,
   and against 2.60% as built. Spending a second ladder's area and 3 µA of
   an 8.2 µA Iq headroom — ~37%, or ~60% if the generator mirror is not
   ratioed and the reference current is paid for twice — to move from 2.08%
   to 1.35%, still ~2.7× outside
   `0011`'s ±0.5%, is not a trade this record makes. It pays for itself only
   at **two** insertions (S3: 3σ 0.056%, 100% of dies inside ±0.5%), and a
   second insertion is not something this record may grant — the Trim row
   says 1-point.

### What is recorded *for* the CTAT knob, so the decline is reversible

The decline is "not under this row", not "never". The evaluation leaves the
knob fully specified, and this record ratifies that specification as the
design of record should a 2-point Trim row ever be proposed:

- **Topology**: a VBE/R CTAT current `I_c = VBE(Q3)/R_c` injected into the
  output branch, adding `(R1_eff/R_c)·VBE` to `vref`. Its control voltage is
  a real HBT junction on a dedicated node (`cb3`) — **BiCMOS is what makes it
  cheap here**, where the CMOS sibling blocks would have to synthesize it.
- **DAC**: current-mode, ~7 bits, ≈ 2.95 µA full scale with ≈ 0.95 µA
  nominal; the as-built ladder's default code drops ≈ 27 LSBs to absorb the
  nominal CTAT term. A resistive conductance DAC is impossible (its smallest
  branch would be ~30 MΩ).
- **`R_c` in `rppd`**, the same material class as R1, so the `R1/R_c` ratio
  the CTAT term depends on tracks the res corner.
- **Two aim constants** — bow-centred targets at 27 and 125 °C rather than
  exact nulls — worth ~0.24% of systematic residual for free.
- **A worst-corner Iq gate**: `Iq < 50 µA` must still hold at
  `bcs`/125 °C/3.63 V with the knob at full scale; ratio the generator mirror
  rather than paying for the reference current twice.
- **Authority**: ±~145 mV two-sided about a non-zero nominal; the existing
  8-bit ladder needs no re-range (the joint solve pulls codes to 101…184,
  0.0% railed).
- **The claim gate**: none of the above is a measurement until a trim-domain
  MC runs with the knob in the netlist, N ≥ 300/point on the same `_mismatch`
  sections and seed discipline as `sim/closed-loop-vref-trim-mc/`, including
  the DAC's and the generator's own mismatch.

### What this record does not do

- **It does not change any target number**, so the relax-after-measured-FAIL
  rule and the two-key ratification gate do not bind it. `README.md`'s
  target-spec table is untouched.
- **It does not set a stretch number.** `0012` (PR #270) leaves the
  Output-reference row's stretch column `—` and says a future record sets one
  "when #267 produces evidence for one". The evidence-backed answer this
  record supplies is an **architecture** answer, not a number: ±0.5% is
  reachable on this block only with a second knob **and** a second
  temperature (S3), the two together are worth a factor of ~37 over the
  better of the two halves alone, and neither is available under the ratified
  1-point row. Projections are not a line. A stretch number still requires
  the trim-domain MC named above.
- **It does not re-decide the trimmed line.** That is `0011`/`0012`'s row.
- **It does not change the Trim row.** Moving from 1-point to 2-point is a
  Trim-row change with real wafer-sort cost, and belongs to a superseding
  record of `0011`, not to this one. Filed as **#285** so the finding is not
  lost.

## Alternatives considered

- **Build the CTAT knob now anyway, on the strength of S4 (3σ 1.35% from a
  single 27 °C insertion).** Rejected on the arithmetic in Decision 3: it
  costs ~2,000–4,000 µm² and up to 3 µA of an 8.2 µA headroom to beat a
  free alternative (S2, 2.08%) by 0.7 percentage points, while landing
  ~2.7× outside the line that motivated the work. A knob that cannot reach
  the target but consumes most of the remaining current budget is the worst
  of both branches.
- **Build a second ladder on R2, or a joint R1/R2 decode** — #267's first
  named candidate. Rejected by direct measurement: `b_minus_a` is
  −0.0064…−0.0057 across all 15 groups, i.e. the column is parallel to the
  one already built. Nothing about area, resolution or decode changes that;
  it is the `ΔT/T` shape of any `VT`-proportional knob.
- **Build the level-only knob** — the literal request in #267 ("null a die's
  level *without* moving its PTAT gain"). Rejected on Decision 2: measured as
  a genuine independent column and still 3σ 1.47–1.55%, because ~29% of the
  post-trim drift variance is intrinsic TC scatter no level knob touches.
- **Adopt the free S2 code-offset rule** (`m = round(+8.00 − 0.0600·code*)`,
  fitted on typ, out-of-sample on bcs/wcs; 3σ 2.02–2.10% for no silicon and
  no extra insertion). Not adopted *by this record*, on two grounds: it is a
  projection rather than a measurement, and it buys 3σ by **trading 27 °C
  accuracy** — the fraction of dies inside ±0.5% falls slightly (26.9–29.4%
  vs 28.5–31.7%). It is a sort-program rule, not a design change, and
  adopting it would be a trimmed-line move this record's scope forbids. It is
  recorded here because it is the baseline any second knob must beat, and it
  is the reason S4 fails to clear that bar.
- **Reduce the ladder's own contribution to the systematic bow instead.**
  Not an alternative, and recorded so it is not mistaken for one: #269
  measures the trim-bearing core at 32.8–38.6 ppm/°C box TC against the
  pre-trim core's 10.2–18.5 ppm/°C (with the convergence aids worth only
  3.8–5.4% of that gap), so the ladder does dominate the *deterministic*
  residual. But that residual is **systematic** — identical for every die —
  and so cannot move the per-die 3σ table above at all. It is additive with a
  second knob, not a substitute for one.
- **Defer the whole question until the trimmed line is ratified** (wait for
  PR #270). Rejected: `0012` explicitly leaves its stretch column empty *for*
  this work, and nothing in the column measurements or the cost accounting
  depends on where the trimmed line is drawn. Deferring would leave both
  records pointing at each other.
- **Route the decision to the operator as a test-cost call.** Rejected as
  incomplete analysis. There is no open test-cost question under the row in
  force: `0011` ratified a 1-point trim, and under a 1-point trim the answer
  is determined (Decision 3). The operator question — "may this block spend a
  second wafer-sort insertion?" — only arises if someone proposes changing
  the Trim row, which is where it is now filed.

## Consequences

- **The `0011` Trim row stands unchanged**, and with it the 1-point, 27 °C,
  magnitude-only trim. No `README.md` row moves.
- **`0012`'s stretch column stays `—`.** This record is the evidence-backed
  answer #267 owed it, and the answer is "no tighter line yet, and here is
  exactly what would set one and what it would cost" — not a number. A
  reader of `0012` who follows the pointer to #267 now lands on measured
  columns and a sized knob instead of an open question.
- **The second-ladder family is closed permanently.** Any future proposal for
  a trim on R2, a joint R1/R2 code, a ΔVBE-ratio trim or a Q3
  current-density trim must first explain why
  `sim/trim-knob-jacobian/`'s measured `ratio_B ≈ ratio_A` does not apply to
  it. This is the cheapest consequence of the work and the most durable.
- **`design/bandgap_trim_network.md`'s §2–§3 TC-null premise is superseded**
  (stated in that document's own header, which now points here): its sizing
  remains correct — it is about coverage, and the MC confirms it with zero
  railed dies — but its claim that a 1-point R1 trim restores each die's own
  null is falsified by measurement. `sim/closed-loop-vref-boxtc-trim/`'s
  ±1-code claim gate rests on that same premise; re-deciding it is #268's AC
  4, not this record's — and because this record builds no knob, #268's AC 4
  is a renumbering question after all, with no new knob to reconsider it
  against.
- **The bad consequence, stated plainly**: the block ships with no path to
  `0011`'s ±0.5% trimmed line. This record does not create one — it
  establishes that none exists under the ratified Trim row, and that the one
  that *would* exist (CTAT knob + 2-point trim, projected 3σ 0.056% plus a
  0.11–0.35% systematic bow, so ~0.27–0.5% in total against ~4.2% as built
  on the same accounting) costs a second wafer-sort insertion this record has
  no authority to grant. That is a worse answer than "we built the knob", and
  it is the answer the measurements support.
- **No `sim/` record is reinterpreted or re-run.** `sim/trim-knob-jacobian/`
  is new, append-only evidence; every other record keeps the verdict it
  earned against the gate in force when it ran.
- **Follow-on work this record names rather than performs**: the Trim-row
  question (1-point → 2-point, with the CTAT knob) is tracked as **#285**,
  filed with this record's PR; the trim-domain MC that would convert any of
  the projections above into a claim is that issue's acceptance criterion,
  not this one's.
