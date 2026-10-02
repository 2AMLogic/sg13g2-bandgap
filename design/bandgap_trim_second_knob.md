# A second trim degree of freedom: evaluation (issue #267)

This document evaluates whether this block should carry a **second trim
knob**, and which one. It is the sibling of
[`bandgap_trim_network.md`](bandgap_trim_network.md) (which sizes the
as-built 1-point R1 ladder) and it exists because that ladder's one knob
converts a die's 27 °C level error into post-trim temperature drift at a
*measured* rate — the finding #267 was filed on.

Its evidence is three committed records plus one new bench:

| what | where |
|---|---|
| each candidate knob's measured `(level, drift)` column on the real loop | [`../sim/trim-knob-jacobian/`](../sim/trim-knob-jacobian/README.md) — **new, issue #267** |
| the as-built knob's deterministic code sensitivity and the 8-temperature curves | [`../sim/closed-loop-vref-boxtc-trim/`](../sim/closed-loop-vref-boxtc-trim/README.md) (#229) |
| the trim-domain mismatch population (N=300/point, per-die `code*` and post-trim `vref`) | [`../sim/closed-loop-vref-trim-mc/`](../sim/closed-loop-vref-trim-mc/README.md) (#229) |
| ladder range/resolution/linearity and the per-die trim unit | [`../sim/trim-coverage/`](../sim/trim-coverage/README.md) (#229) |
| quiescent current, the budget a new branch spends | [`../sim/closed-loop-iq/`](../sim/closed-loop-iq/README.md) |

**Scope boundary.** This document decides whether a second knob is worth
building and which one. It does **not** set the ratified trimmed line. The
ratified line today is still DR-0011's **±0.5%**, measured **NOT met**
(`sim/closed-loop-vref-trim-mc/`: 3σ 2.52–2.60%, worst draw 6.79%, 28.5–31.7%
of dies inside ±0.5%). A re-cast to **±4.5% (3σ)** is *proposed* in #265 /
PR #270, which was still **OPEN and unmerged as of 2026-10-02** (Judge-approved
`loom:pr`, held by `loom:operator-only` + `loom:operator-decision` for the
two-key ratification release) — `spec/decision-records/0012-trimmed-line-disposition.md`
does not exist on `main`. Re-check its state before treating ±4.5% as
settled. If a second knob is built and measured, a *superseding* record sets
a tighter line; never this document.

## 1. The offset-to-drift coupling is thermodynamic, not a defect of the ladder

The as-built ladder's measured sensitivity is **+0.0775 %/code** of signed
27 °C → 125 °C drift (`sim/closed-loop-vref-boxtc-trim/`, typ/3.30 V, linear
over codes 0…255), against a measured trim step of **2.443 mV/code**
(`sim/trim-coverage/`). Those two numbers are not independent:

```
Δdrift   ΔT      398.15 − 300.15
────── = ──  =   ───────────────  = 0.3265        (27 °C → 125 °C)
Δlevel    T          300.15

2.443 mV × 0.3265 / 1.050 V = 0.0760 %/code      predicted
                              0.0775 %/code      measured  (+2.0%)
```

The reason is structural. The core is `vref = VBE(Q3) + (R1/R2)·VT·ln 8`: the
only thing the R1 ladder can move is the **VT-proportional** term, and volts
that are proportional to `VT` carry their own PTAT slope of exactly
`level/T`. So a knob of that kind cannot move the level without moving the
drift by `ΔT/T` times as much — whatever its construction, resolution, or
area. The trim-knob-jacobian bench measures `ratio_A = Δdrift/Δlevel =
+0.3311…+0.3348` across all 15 corner/supply groups, i.e. the `ΔT/T`
prediction to within **1.4–2.5%**, and `−0.2262…−0.2245` on the cold side
against a prediction of `−0.2232`.

Two consequences follow immediately, and they frame everything below:

- **The exchange rate is 3.07:1 against you.** Removing `d` of drift with the
  R1 knob alone costs `d/0.3265 = 3.07·d` of 27 °C level error. That is why
  re-aiming the existing knob (§3.2) can only ever trade, never win.
- **"It is the ladder's fault" is falsified.** A differently built,
  differently sized, or finer ladder on the same branch has the same column.

## 2. What a second knob has to be: the column test

A trim knob is a **column** in the `(level, drift)` plane: the pair
`(Δlevel, Δdrift)` it produces per unit of authority. Two knobs are a genuine
*two* degrees of freedom only if their columns are not parallel — i.e. only
if the 2×2

```
| 1          1        | | x_A |   | level error |
| ratio_A    ratio_K  | | x_K | = | drift error |
```

is non-singular, which needs `ratio_K ≠ ratio_A`. **Area, bit count, decode
style and placement are all irrelevant to this test.** That is the whole
question #267 asks, so it is the question the new bench measures, and it is
answerable before any transistor is drawn.

The physics that decides it: a knob's `ratio` is set entirely by the
**temperature shape** of the volts it adds. A knob that scales a
`VT`-proportional term has `ratio = +ΔT/T`. A knob that adds a
`VBE`-proportional term has `ratio = ΔVBE/VBE`, which is **negative** on this
PDK's HBT (`−0.1630…−0.1693`, measured per group from the bench's own
`vbeq3` column). A knob that scales the *whole* reference has `ratio ≈ 0`.

## 3. The three candidates, measured

All four columns below are from one record,
`sim/trim-knob-jacobian/records/20261002-131827-d770c09a-jacobian.csv`
(405/405 points PASS, 0/15 groups FAIL its gates), measured about the
as-built code-128 / 27 °C baseline at ±~20 mV of authority, with each knob's
2× point confirming linearity.

| knob | what it is | `ratio` (15 groups) | independent of A? |
|---|---|---|---|
| **A** | the as-built R1-side ladder | +0.3311 … +0.3348 | — (reference) |
| **B** | an `rppd` trim element in series with R2 ("second ladder on R2") | +0.3247 … +0.3291 | **no** — `ratio_B − ratio_A` = −0.0064…−0.0057 |
| **C** | a VBE/R CTAT current injected into the output branch | −0.1584 … −0.1507 | **yes** — `ratio_C − ratio_A` = −0.4904…−0.4847 |
| **D** | a trim applied as a *scaling* of the whole reference | +0.0074 … +0.0112 | **yes** — but see §3.4 |

### 3.1 A second ladder on R2 (or a joint R1/R2 code) — ruled out, by measurement

**It is the same degree of freedom as the knob already built.** Measured:
`ratio_B` sits within **1.9%** of `ratio_A` at every corner and supply —
parallel columns, a singular 2×2, no new freedom bought for whatever the
second ladder costs.

The algebra says why, and says it is exact rather than incidental. With
`I = VT·ln8/R2` set by the R2/Q1/Q2 loop,

```
∂vref/∂(ln R2) = −(R1/R2)·VT·ln8 − VT = −(0.3386 + 0.0259) V = −0.3645 V
```

and **both** terms are proportional to `VT`: the PTAT term directly, and the
`VBE(Q3)` term because changing `R2` changes the branch current and
`δVBE = VT·δ(ln I)`. A knob whose entire response is PTAT has `ratio = ΔT/T`
by §1 — the same column as R1. A *joint* R1/R2 code is a linear combination
of two parallel columns and is therefore also parallel.

The same argument disposes of two knobs not named in #267 but worth closing
out: trimming the ΔVBE generator's ratio `N` (it scales `VT·ln N`, PTAT) and
trimming Q3's current density (it moves `VBE` by `VT·ln k`, also PTAT). **On
this topology every "obvious" knob is collinear with the one already built.**

### 3.2 A 2-point (room + hot) trim — necessary, but not sufficient on its own

A second temperature does not add a knob; it adds *information*. With the
single existing knob and perfect per-die knowledge of all three verify
temperatures, the best achievable aim (minimax rather than a 27 °C null) is
3σ **2.07%** against the as-built **2.60%** — a 20% improvement for the cost
of a second insertion, because of §1's 3.07:1 exchange rate. One knob cannot
null two conditions.

There is also a **free** version of the same idea, worth recording because it
costs nothing: the measured population regression
(`drift ≈ 0.0577·code* − 7.80 %`, r = +0.842) means a die's drift is partly
predictable from the `code*` a 27 °C-only insertion already produces, so a
deterministic code offset `m = round(+8.00 − 0.0600·code*)` can be applied at
sort with no extra measurement and no silicon. Projected (rule fitted on typ,
applied out-of-sample to bcs/wcs): 3σ **2.02–2.10%**, i.e. most of S1's
benefit for none of its cost — but the fraction of dies inside ±0.5% drops
slightly (26.9–29.4% vs 28.5–31.7%), because the rule buys 3σ by trading
27 °C accuracy. It is an improvement in the 3σ line and a small regression in
the median die; it is not a path to ±0.5% either way.

### 3.3 A VBE-offset / CTAT trim — the only independent column on this topology

Measured `ratio_C = −0.1507…−0.1584` against the `ΔVBE/VBE` prediction
(−0.1630…−0.1693) to within 6.4–7.6%, linear to ≤0.5% over 2× authority, and
**opposite in sign to knob A**. Paired with A it gives a well-conditioned 2×2
whose level-neutral TC gain the bench reports directly:

```
tc_gain_level_neutral = ratio_A − ratio_C = +0.4847 … +0.4904
```

— i.e. combining A and C so the 27 °C level does not move buys 0.49 V of
drift per volt of knob-A authority. **This is the knob to build**, and §4
quantifies what it is worth, §5 what it costs.

What it is, physically: a current `I_c = VBE/R_c` injected into the output
branch, which adds `(R1_eff/R_c)·VBE` — a CTAT term — to `vref`. The bench
models it behaviorally (a VCCS controlled by `v(cb3)`); the implementing
circuit is a VBE/R generator plus a current DAC (§5). **BiCMOS matters here**:
`VBE(Q3)` is a real HBT junction on a dedicated node (`cb3`), already brought
out as a measured quantity by every bench in this tree, and not the
substrate-PNP the CMOS siblings must work around — the control voltage this
knob needs is simply available. Neither `gf180-bandgap` nor `sky130-bandgap`
has explored any second knob (both carry a 1-point magnitude-only ladder and
no second-knob design doc or decision record), so there is nothing to port;
this is the canary block leading rather than following.

### 3.4 The knob #267's framing implies — a level-only knob — is measured, and is not enough

#267 asks for "a second trim knob that can null a die's level **without**
moving its PTAT gain". Knob D is exactly that knob: a scaling of the whole
reference multiplies level and drift alike, so it converts essentially no
offset into drift (`|ratio_D| ≤ 0.0112`, measured).

**And it still does not reach ±0.5%.** Projected with no R1 trim at all and
the level corrected purely by scaling: 3σ **1.47–1.55%**, worst draw 2.76%,
36.4–36.8% of dies inside ±0.5% (§4). The reason is visible in the same
regression that motivated #267: `code*` explains ~71% of the post-trim drift
variance, so eliminating the trim-induced component leaves the other ~29% —
the population's **intrinsic** TC scatter, residual sd 0.72–0.75%, which no
level knob of any kind can touch.

So the finding is a correction to the issue's own premise, not a
confirmation: **the problem is not that the trim adds TC, it is that nothing
in the block trims TC.** A second knob is worth building only if it is aimed
at the die's *slope*, which §4 shows requires the second temperature as well.

## 4. What each strategy would deliver

Reproduce with `sim/tools/project_trim_strategies.py` (reads the three
committed records named above). **These are projections, not measurements**:
each knob's measured column is superposed onto every committed MC die's own
three-temperature state. The three assumptions that makes — linearity
extrapolated ~7× beyond the measured ±20 mV, die-independence of the
columns, and only three temperatures — are exactly what the follow-on
trim-domain MC must confirm. S0 reproduces the committed digest's 3σ to the
digit (2.601/2.523/2.592%), which is the projection's own sanity check.

`max_T |vref(T) − 1.050| / 1.050` over {−40, 27, 125} °C, N≈300 per point:

| strategy | new silicon | sort insertions | 3σ (typ/bcs/wcs) | mean+3σ | worst | within ±0.5% |
|---|---|---|---|---|---|---|
| **S0** as built: knob A, 27 °C null | none | 1 | 2.60 / 2.52 / 2.59% | 3.69% | 6.79% | 28.5–31.7% |
| **S2** knob A + code-offset rule from `code*` | none | 1 | 2.08 / 2.02 / 2.10% | 3.08% | 5.67% | 26.9–29.4% |
| **S1** knob A, minimax aim | none | ≥2 | 2.07 / 1.98 / 2.05% | 2.95% | 5.47% | 35.5–36.1% |
| **S5** level-only knob (D), no R1 trim | scaling knob | 1 | 1.55 / 1.54 / 1.47% | 2.35% | 3.03% | 36.4–36.8% |
| **S4** knobs A+C set from 27 °C observables | CTAT knob | 1 | 1.35 / 1.31 / 1.35% | 2.05% | 3.36% | 40.9–42.1% |
| **S3** knobs A+C, minimax aim | CTAT knob | ≥2 | **0.056 / 0.055 / 0.056%** | 0.16% | 0.14% | **100%** |

S4's rule is a linear predictor in observables the fit stage **already
measures per die** — `vref(code 0)` (≈ `VBE(Q3)`), the die's own trim unit,
and `vref(27 °C)` at `code*` — fitted on typ and applied out-of-sample to
bcs/wcs. It is the honest ceiling of a single-insertion two-knob trim: a
27 °C measurement cannot separate a PTAT-shaped `VBE` error (Is mismatch)
from a CTAT-shaped one (bandgap/ideality mismatch), so the second knob can
only be set from a population correlation, and **half the benefit is lost**.

**The two findings that decide the issue:**

1. **Neither the second knob nor the second temperature is sufficient
   alone.** At 3σ: one knob with two temperatures (S1) is 2.07%, two knobs
   with one temperature (S4) is 1.35% — against 2.60% as built. **Together
   (S3) they are 0.056%**, a factor of 37 better than the better of the two
   halves. The second knob is what makes the second insertion pay for
   itself, and vice versa.
2. **S3's 0.056% is the three-temperature metric and is not the whole
   error.** Section B of the same projection measures what the MC's three
   verify temperatures cannot see — the residual bow on the deterministic
   8-temperature grid, which is systematic and adds to S3:

   | aim | residual over 8 temperatures, 15 groups |
   |---|---|
   | 1 knob, 27 °C null (**as built**) | 0.339 … 0.474% |
   | 1 knob, minimax | 0.146 … 0.206% |
   | 2 knobs, null at 27 and 125 °C | 0.323 … 0.353% |
   | 2 knobs, minimax over the grid | 0.099 … 0.108% |

   Adding S3's own per-die figure to it: a two-knob trim aimed naively (null
   at 27 and 125 °C) lands at roughly **0.16% (mean+3σ) + 0.35% ≈ 0.5%** —
   at the edge of DR-0011's line — while the same two knobs aimed at
   bow-centred targets instead of exact nulls land at roughly
   **0.16% + 0.11% ≈ 0.27%**, comfortably inside it. For scale, the as-built
   line on the same accounting is 3.69% + 0.47% ≈ 4.2%. **The aim points are
   free and worth ~0.24%**: they are two design constants, not extra test
   time. Any implementation of this knob must specify them.

   **That bow is mostly the ladder's own, and reducing it is a different
   job from this one.** [`../sim/closed-loop-vref-boxtc-pretrim-aidsfree/`](../sim/closed-loop-vref-boxtc-pretrim-aidsfree/README.md)
   (#269, landed 2026-10-02) separates the two changes that happened at once
   between the pre-trim and trim-bearing box-TC records: dropping the
   convergence aids is worth +3.8%/+5.4% of box TC on the pre-trim core,
   while the trim-bearing core reads 32.8–38.6 ppm/°C against the pre-trim
   10.2–18.5 ppm/°C at the same two groups. So the 255-unit ladder — at
   code 128, where it is *nominally* the resistance it replaced — is itself
   the dominant cause of the deterministic residual the table above
   measures. **This does not make a ladder fix an alternative to a second
   knob**, and the distinction matters: the bow is a *systematic* term, the
   same for every die, so it cannot touch §4A's per-die 3σ (2.60% as built,
   1.35% with S4) at all. It is additive with a second knob and tracked
   where it belongs, with #269's own disposition; a two-knob trim would
   simply have less systematic residual to aim around if it were reduced.

### Authority the joint solve needs (a sizing input, not a claim)

From the exact (A, C) solve that nulls level and hot drift on every committed
MC die:

| | typ | bcs | wcs |
|---|---|---|---|
| knob A authority | −144.3 … +65.2 mV | −145.0 … +67.1 mV | −145.6 … +63.6 mV |
| knob C authority | −65.5 … +144.2 mV | −66.9 … +144.7 mV | −64.1 … +144.9 mV |
| total A code | 103 … 183 | 103 … 184 | 101 … 179 |
| railed | **0.0%** | **0.0%** | **0.0%** |

Two useful facts fall out. **The existing 8-bit ladder already has the
headroom**: the joint solve pulls codes to 101…184, well inside 0…255, so
knob A needs no re-range (it does consume ~±60 codes of what the
correlated-coverage sizing in `bandgap_trim_network.md` §2 left as margin —
which that sizing has, by measurement). And knob C needs a **two-sided**
±~145 mV of authority about a non-zero nominal: at the bench's measured
14.08 nA/mV (≈295 nA bought 20.96 mV at typ/3.30 V), that is a span of
≈ 2.95 µA with a nominal injection of ≈ 0.95 µA, so the core's default code
drops by ≈ 27 LSBs to absorb the nominal CTAT term.

## 5. What it costs

| cost | estimate | basis |
|---|---|---|
| **Quiescent current** | +1 µA nominal, **up to +3 µA** at full scale for the injected copy, plus the generator's own copy of it (≈ 2× unless the mirror is ratioed) | worst committed Iq is **41.78 µA** (`bcs`/125 °C/3.63 V, `sim/closed-loop-iq/`) against the ratified **< 50 µA** target — only **8.2 µA** of headroom, so a naive 2× implementation spends ~60% of it. **This, not area, is the binding budget.** |
| **Reference resistor `R_c`** | ≈ 240 kΩ at full scale. Must be the **same material class as R1** (`rppd`) so the `R1/R_c` ratio the CTAT term depends on tracks the res corner; at `w=2u` that is 1,857 µm of length (≈ 3,700 µm² drawn, i.e. a second ladder's worth), at `w=0.5u` about 464 µm (≈ 230 µm² of body) at the cost of width-dependent matching | `rppd` 129.25 Ω/µm at `w=2u` (`bandgap_trim_network.md` §3); `VBE/R_c` with `VBE = 0.709 V` |
| **The DAC** | ~7 bits (a 1.6 mV step keeps C's quantization at the existing ±½-LSB level-quantization class). A *resistive* conductance DAC is impossible here — its smallest branch would be ~30 MΩ, metres of `rppd` — so it must be **current-mode**: one VBE/R reference current plus a binary-weighted PMOS steering array. First-order area 1,500–2,500 µm² including decode | compare the as-built ladder's **measured** 3,179 µm² / 12.5 µm² per unit (`layout/README.md`, issue #272) |
| **Area, total** | ≈ 2,000–4,000 µm², i.e. roughly a second trim ladder, ~6–12% of the 271.47 × 126.59 µm top assembly | ibid. |
| **Mask option / decode** | a second 7–8-bit option doubles the decode and, with it, the LVS mask-option problem: *a layout is one code*, so `layout/lvs_reference.py::convert_with_metal_options` must resolve two independent options instead of one (the missing tool capability is already filed — [klayout-tools#2653](https://github.com/2AMLogic/klayout-tools/issues/2653); this needs no new tool issue, it needs that one to land) | `bandgap_trim_network.md` §4 |
| **Wafer sort** | **a second, hot insertion** — the cost that decides the question (§6) | §4's S3-vs-S4 split |
| **New error terms** | the DAC's own mismatch and the generator amp's offset/PSRR land directly on `vref` and are **not** in any number above (a 1% error on a 2 µA injection is ≈ 1.4 mV ≈ 0.13% of target) | must be measured by the follow-on trim-domain MC |

## 6. Recommendation

**Of the three candidates, only the CTAT (VBE/R) knob is worth building at
all — and only if the trim flow can afford a second, hot insertion.** The
hinge is sharp and is the one input simulation cannot supply:

- **With a second insertion** (S3): projected 3σ ≈ 0.056% over the verify
  temperatures (mean+3σ 0.16%) plus a 0.11–0.35% systematic bow depending on
  the aim constants, so ~0.27–0.5% in total against ~4.2% as built on the
  same accounting — **roughly an order of magnitude**, and the only path
  found to DR-0011's ratified ±0.5%. Worth ~2,000–4,000 µm² and ~3 µA.
- **With a single 27 °C insertion** (S4): projected 3σ ≈ 1.35% against
  2.60% as built — a 1.9× improvement for the same silicon and quiescent
  current. For comparison, **S2 buys 3σ 2.08% for nothing at all**. Spending
  a second ladder's area and 60% of the Iq headroom to go from 2.08% to
  1.35% — still ~2.7× outside the ratified line — is not a trade this
  document recommends.

Rejected, with the measurement that rejects each:

- **A second ladder on R2 / a joint R1/R2 code** — `ratio_B` is within 1.9%
  of `ratio_A` at all 15 corner/supply groups. Collinear; no degree of
  freedom bought; pure cost. Likewise a ΔVBE-ratio or current-density trim
  (§3.1).
- **A level-only knob** (the literal request in #267) — measured as a real,
  independent, nearly drift-free column, and still only 3σ 1.47–1.55%,
  because ~29% of the post-trim drift variance is intrinsic TC scatter that
  no level knob reaches (§3.4).
- **A 2-point trim with the existing knob alone** — 3σ 2.07%; §1's 3.07:1
  exchange rate caps it (§3.2).

### The disposition, and where the hinge was settled

DR-0011's **ratified** Trim row is *"1-point at 27 °C … magnitude only"*, so
the second-insertion branch is not available to be chosen here: under the row
in force, the answer is the S4 branch above, and S4 does not pay for itself.
[`spec/decision-records/0013-second-trim-degree-of-freedom.md`](../spec/decision-records/0013-second-trim-degree-of-freedom.md)
is that disposition — **no second knob is built**, the second-ladder family
is closed permanently on the measurement in §3.1, and the CTAT knob's
specification below is ratified as the design of record for whenever a
2-point Trim row is proposed. The Trim-row question itself (1-point →
2-point) is filed as **#285** alongside that record; it is a wafer-sort cost
decision and a `0011` supersession, neither of which belongs to this
document.

Implementation requirements that follow-on must carry, each of which this
evaluation has already made falsifiable:

1. **Current-mode DAC**, ~7 bits, ≈ 2.95 µA full scale, ≈ 0.95 µA nominal,
   with the as-built ladder's default code dropped ≈ 27 LSBs to absorb it.
2. **`R_c` in `rppd`** so `R1/R_c` tracks the res corner; settle the
   `w=2u`-vs-narrower area/matching trade explicitly.
3. **A worst-corner Iq gate**: total `Iq` < 50 µA must still hold at
   `bcs`/125 °C/3.63 V with the knob at full scale (8.2 µA of headroom
   today) — ratio the generator mirror rather than paying for the reference
   current twice.
4. **Two aim constants** (the bow-centred targets at 27 °C and 125 °C, not
   exact nulls) — worth ~0.24% for free, per §4.
5. **A trim-domain MC with the knob in the netlist**, N ≥ 300 per point on
   the same `_mismatch` sections and seed discipline as
   `sim/closed-loop-vref-trim-mc/`, including the DAC's and the generator's
   own mismatch — the only thing that converts §4's projections into a
   claim, and the only basis on which a *superseding* spec record could
   tighten the trimmed line.

## 7. What this document does not decide

- **The trimmed line.** DR-0011's ±0.5% stands as ratified-and-not-met; the
  ±4.5% re-cast is #265 / PR #270's to make (OPEN and unmerged at the time of
  writing). A tighter line requires requirement 5 above, landed and measured,
  and then a superseding decision record.
- **Whether the trim flow gets a second insertion.** That is a test-cost
  decision and a change to DR-0011's ratified Trim row, not a simulation
  result. §6 states the answer under either branch so the decision can be
  made without re-opening this analysis; `0013` declines the knob under the
  row as ratified and files the row question separately.
- **The bench gate constants** in `sim/closed-loop-vref-trim-mc/` and
  `sim/closed-loop-vref-boxtc-trim/` — #268 re-points those at whatever line
  `0012` ratifies, and if this knob lands it is #268's AC 4 that revisits
  them, not this document.
