# 0006: Post-layout ~30 MHz PSRR dip — mechanism, design response, spec row

- **Status**: proposed
- **Date**: 2026-09-06
- **Decided by**: Loom Builder (agent), issue #191

## Context

`sim/closed-loop-psrr-pex/` (issue #192, record `20260905-233826-f6f3efc`,
`dd45eaf`) measured negative worst-case PSRR at all 45 PVT points
post-layout: the supply-rejection curve dips to a genuine local **minimum**
of `−2.15 … −0.84 dB` near `27.1–31.6 MHz` and then *recovers* (rises back
through 0 dB a few MHz higher, then keeps climbing) — i.e. the assembled
block slightly *amplifies* supply ripple in a narrow band, where the
pre-layout schematic-level bench still rejected it by `+2.52 … +4.26 dB` at
that same frequency. That experiment's own README built a circumstantial
case for a genuine loop-resonance mechanism (uniform sign/magnitude across
all 45 points, direction/frequency tracking the extracted wire capacitance,
proximity to `sim/loop-gain-phase-margin`'s independently measured
41.6–53.4 MHz unity-gain crossover and issue #146's thin gain-margin
finding), but explicitly deferred confirmation to this issue rather than
asserting it.

Issue #191 asked for three things: (1) an independent confirmation
testbench, distinct from the supply-injection measurement, to isolate
whether the dip is the loop's own resonance vs. an artifact specific to the
`vdd` injection path; (2) a design-response decision once the mechanism is
known; (3) a decision on whether `spec/porting-plan.md` §6's draft
`PSRR @ DC > 60 dB` row should gain an away-from-DC bound now.

## Confirmation testbench and result

`sim/closed-loop-zout-pex/` (new, this issue) measures the SAME closed-loop
topology on the SAME layout-extracted device/parasitic block
(`layout/bandgap_top/bandgap_top.pex.spice`, byte-for-byte identical device
cards and wire-parasitic network to `sim/closed-loop-psrr-pex`'s own
template), but stimulated at a completely different port: instead of a
1 V∠0° AC perturbation on `vdd` (PSRR's own injection), a 1 A∠0° AC test
current is injected directly at `vref` (`vdd` left as a plain DC source),
and the closed-loop small-signal output impedance
`Zout(f) = v(vref)/i(Itest)` is read. PSRR and Zout are different transfer
functions referred to the *same* node (`vref`), so they share the *same*
poles (the same linearized network, the same `1/(1+T(jω))` return-
difference denominator — the injection port only changes the numerator/
zeros, not the poles). A genuine loop resonance — a real, lightly-damped
dip in `1+T(jω)` — would therefore be expected to produce at least some
peaking in **both** transfer functions, not only the one stimulated
through `vdd`.

**Result (record `20260906-003654-dd45eaf`, 45/45 points PASS)**: at
**every single one of the 45 PVT points**, `Zout(f)` is strictly
monotonically decreasing across the ENTIRE 1 Hz–1 GHz sweep — the peak
`|Zout|` is always the DC value (`zout_peak_freq_hz = 1 Hz` at all 45
points; `zout_peak_db` never differs from `zout_dc_db`), and a direct scan
of every point's raw `.ac.txt` curve (not just the summary's DC/1 kHz/
100 kHz/1 MHz columns) finds **zero** local bumps anywhere in the
20–40 MHz band where `sim/closed-loop-psrr-pex`'s own dip sits — including
the 8 "near-cancellation" `27°C`/`3.63V`-family points that experiment's
own README flags as behaving differently at DC. Full per-point
cross-comparison against `psrr_min_freq_hz`/`psrr_min_db`:
`sim/closed-loop-zout-pex/records/20260906-003654-dd45eaf-vs-psrr-pex.csv`.

Separately, a direct look at the raw PSRR curve itself
(`sim/closed-loop-psrr-pex/corners/20260905-233826-f6f3efc/typ_27c_3.30v.ac.txt`,
representative of all 45 points) confirms PSRR does not merely cross 0 dB
and keep falling: it dips to a local minimum (`−1.62 dB` at `2.93e7 Hz` for
this point) and then recovers, rising back through 0 dB by `~3.7e7 Hz` and
continuing to climb through the rest of the sweep — the signature of a
**transmission zero** (a notch) in the `vdd`→`vref` path's own numerator,
not a pole shared by the whole closed-loop network (a pole would show up
in every transfer function referred to that node, including Zout).

## Decision

### Mechanism: NOT a confirmed loop resonance — a `vdd`→`vref` transmission-zero / feedthrough effect

This independent probe does **not** corroborate "the loop's own resonance
interacting with extracted wire parasitics" as the mechanism. The complete
absence of any peaking in Zout, at any of the 45 points, while the exact
same closed-loop network's PSRR shows a clear notch at the same frequency,
is strong evidence against a shared-pole (loop-resonance) explanation and
is instead consistent with a **transmission-zero / feedthrough effect
specific to the `vdd`→`vref` path** — most plausibly the extracted
`vdd`-adjacent wire coupling (`ccc_vdd_vref`, `cvdd`, and the `rvdd_t*`
network feeding the `M3A/B/C` mirror legs that drive `vref`) creating a
high-frequency feedforward term that partially cancels the regulated
path's own rolloff at one frequency (the notch minimum) and then dominates
on either side (the recovery). This is real, physically-grounded
post-layout evidence — not a measurement artifact in the sense of "an
incorrect or invalid measurement" — but it is a **different** mechanism
than the loop-instability/resonance story the original circumstantial case
raised as its leading hypothesis. `sim/closed-loop-psrr-pex/README.md` is
corrected below to reflect this rather than repeat the unconfirmed
resonance framing.

This also resolves why the effect's sign/magnitude is uniform across all
45 PVT points and tracks the extracted wire capacitance directly (as the
original README observed): a passive feedthrough network's own
frequency-dependent coupling is exactly the kind of effect that scales
with parasitic capacitance and is comparatively insensitive to the
process/temperature/supply corner that mostly perturbs device
transconductances and thus loop gain — consistent with what was measured,
and better explained by a passive numerator effect than by an active-loop
resonance (which would be expected to show more corner-to-corner spread,
tracking gain-margin variation the way `sim/loop-gain-phase-margin`'s own
notch does).

### Design response: accept as-is for this block's current intended use; no compensation capacitor warranted

No loop-stability risk was found (Zout shows no evidence of a lightly
damped resonance or thin gain margin anywhere in this measurement), so a
stability-motivated design response (an explicit compensation capacitor)
is **not warranted** by this evidence. The effect itself is narrow-band
(`27.1–31.6 MHz`), small in magnitude (`0.8–2.1 dB` of ripple gain, i.e.
under 1.3x in linear terms), and sits decades above the frequency range a
voltage reference's supply-rejection is typically specified against in
practice (switching-regulator ripple in the hundreds of kHz to low-MHz
range; PSRR at 1 MHz remains a healthy `34.3–56.3 dB` post-layout per
`sim/closed-loop-psrr-pex`'s own record, unaffected by this narrow notch).

**Decision: accept the `0.8–2.1 dB` narrowband ripple gain near 30 MHz
as-is for this block's intended use.** No design change (compensation
capacitor, routing rework) is made under this issue. If a future
application for this block needs guaranteed PSRR into the tens-of-MHz
range, the mechanism finding above points at a concrete, comparatively
low-risk fix path — reducing the extracted `vdd`-to-`vref`/mirror-leg
coupling by routing changes in `layout/bandgap_top/` — rather than a
schematic-level compensation capacitor; that is flagged as a candidate
follow-up, not undertaken here (out of this issue's decide-and-record
scope, and not motivated by any currently known requirement).

### Spec-row question: defer to the eventual ratification pass (#125); do not add an away-from-DC bound now

`spec/porting-plan.md` §6's draft `PSRR @ DC > 60 dB` row is **not**
amended by this record. Reasoning:

- The away-from-DC effect this record investigates is narrow-band,
  layout-parasitic-specific, and sits far above any frequency the draft
  table (or either sibling repo's own ratified spec) currently anticipates
  needing to bound — committing to a specific away-from-DC number now
  would require knowing the eventual target application's actual ripple
  spectrum, which is not yet defined anywhere in this repo's draft spec.
- The mechanism finding above means this specific numeric notch is a
  property of the *current* layout's routing, not an intrinsic limit of
  the topology — a routing change could plausibly move or shrink it
  without touching the circuit at all, so binding a number to it now risks
  over-constraining a layout detail that has not been optimized for this
  property.
- `spec/porting-plan.md` already states plainly that its §6 table is a set
  of draft starting targets, not yet ratified, with ratification treated
  as a deliberate, later, separate step (#125). This record's evidence
  (both `sim/closed-loop-psrr-pex`'s and `sim/closed-loop-zout-pex`'s
  committed records) is available for that pass to reason from when it
  happens — recording it now, without prematurely picking a number, is
  consistent with how every other still-open row in that table is already
  being handled.

## Alternatives considered

- **Loop-gain/loop-transmission probe on the PEX netlist** (a Middlebrook
  break at the extraction's own `fb` hub node, mirroring
  `sim/loop-gain-phase-margin`'s schematic-level method) — not built.
  Breaking the extracted `fb` hub node would have required a documented,
  defensible way to split its lumped ground capacitance (`cfb`, to `vsubs`)
  and cross-coupling capacitances (`ccc_fb_sns1`, `ccc_fb_pn`,
  `ccc_fb_vdd`, `ccc_fb_vss`) between the two loop-broken halves (`fb_src`/
  `fb_load`) — a new modelling choice with no obviously "correct" answer,
  unlike the output-impedance probe, which reuses the closed, untouched
  extraction exactly as committed. The output-impedance probe was judged
  sufficient to answer the confirmation question issue #191 asks for
  (and, as it turned out, gave a clean, unambiguous null result) without
  introducing that extra, harder-to-defend choice. A loop-gain-on-PEX probe
  remains a reasonable future follow-up if a direct post-layout gain-margin
  number (comparable to `sim/loop-gain-phase-margin`'s schematic-level one)
  is ever needed, but is not required to answer this issue's question.
- **Accepting the circumstantial case in `sim/closed-loop-psrr-pex`'s own
  README without an independent measurement** — rejected because issue
  #191 explicitly asks for confirmation, and, as the result above shows,
  the circumstantial evidence (while suggestive) pointed at the wrong
  leading hypothesis: an independent measurement was necessary to catch
  that.
- **Adding a compensation capacitor now, on the strength of the
  circumstantial case alone** — rejected as premature and, per the
  confirmation result, likely the wrong fix even if pursued: no loop
  resonance was found to compensate, so a compensation cap would not
  address the actual (transmission-zero) mechanism.

## Consequences

- `sim/closed-loop-psrr-pex/README.md`'s "What the layout changes" finding
  3 is corrected (not deleted — this is append-only evidence, so the
  underlying `.csv`/`.md` records are untouched) to no longer lead with the
  loop-resonance hypothesis as the likely explanation, and to point at this
  record and `sim/closed-loop-zout-pex/` for the confirmation result.
- `spec/porting-plan.md` §6 is unchanged. A future ratification pass (#125)
  inherits three data points instead of one: `sim/closed-loop-psrr-pex`'s
  own dip, `sim/closed-loop-zout-pex`'s null result, and this record's
  reasoning for why an away-from-DC bound was deferred rather than decided.
- No design/layout work is invalidated or required by this record. The
  routing-change follow-up noted under "Design response" above is
  explicitly not filed as a new issue by this record — it is a documented
  option, not a commitment, since no current requirement motivates it.
- Issue #4's T1 tracker item 7 (post-layout simulation) gains one more
  closed-loop PEX experiment (`sim/closed-loop-zout-pex/`) beyond what item
  7 itself required, specifically because #191 asked for it.
