# closed-loop-zout-pex

Independent confirmation testbench for issue #191:
[`sim/closed-loop-psrr-pex/`](../closed-loop-psrr-pex/README.md) measured
**negative worst-case PSRR at all 45 PVT points** — a `27.1–31.6 MHz`
narrow-band supply-ripple *gain* of `0.8–2.1 dB`, where the schematic-level
bench still rejected at that frequency. That issue's own "why it is probably
not an artifact" case is circumstantial (uniform sign/magnitude, direction
and frequency tracking the extracted wire capacitance, proximity to
[`sim/loop-gain-phase-margin`](../loop-gain-phase-margin/README.md)'s own
41.6–53.4 MHz unity-gain crossover) — this experiment is the independent
measurement issue #191 explicitly requires before accepting that case.

## What this measures, and why it is independent of the PSRR bench

Same co-simulated `bandgap_core` + `bandgap_amp` + `bandgap_startup`
closed-loop topology as `sim/closed-loop-psrr-pex`, same 45-point PVT grid,
same layout-extracted device/parasitic block
(`layout/bandgap_top/bandgap_top.pex.spice`, byte-for-byte identical device
cards and wire-parasitic network — see that experiment's own README for the
full account of what the extraction does and does not model, and why
`vsubs` is tied to `vss` rather than through the transient PEX benches' 1 TΩ
DC-only tie; both apply here unchanged) — but the loop is stimulated at a
**completely different port**:

- `sim/closed-loop-psrr-pex` injects a 1 V∠0° AC perturbation on `vdd` and
  reads `v(vref)`: `PSRR(f) = -dB(v(vref))`.
- `sim/closed-loop-zout-pex` (this experiment) leaves `vdd` as a plain,
  unperturbed DC source and instead injects a 1 A∠0° AC test current
  directly at `vref`, reading the resulting `v(vref)` — the closed-loop
  small-signal **output impedance** `Zout(f) = v(vref)/i(Itest)`, numerically
  equal to `v(vref)` in ohms since the stimulus magnitude is exactly 1 A.

### Why an output-impedance probe answers the confirmation question

PSRR and closed-loop output impedance are different transfer functions, but
for a single-loop negative-feedback system they share the same denominator:
both are proportional to `1/(1 + T(jω))`, where `T(jω)` is the loop
transmission (the same quantity `sim/loop-gain-phase-margin` measures
directly by breaking the loop). Wherever the loop's own return difference
`1 + T(jω)` gets small — a genuine loop resonance, e.g. the amplifier's
non-dominant pole/zero pair `sim/loop-gain-phase-margin/README.md`'s
"Multiple 0 dB crossings" section already documents at the schematic level
— **every** closed-loop transfer function referred to that node peaks or
dips together, regardless of which port is stimulated. That is the
discriminator this bench exists to apply:

- If `Zout(f)` **also** peaks near 27–31 MHz on this same PEX netlist, that
  is independent evidence (a completely different stimulus port, never
  touching the extracted `vdd` wire network at all) that the mechanism is
  the closed loop's own resonance, consistent with `sim/closed-loop-psrr-pex`'s
  circumstantial case.
- If `Zout(f)` instead stays flat/monotonic through that band while
  `sim/closed-loop-psrr-pex`'s dip is still there, that would point at
  something specific to the `vdd` injection path (e.g. a resonance internal
  to the extracted `vdd` wire network itself, upstream of the rest of the
  loop) rather than a property of the loop as a whole.

This bench does **not** break the loop anywhere (unlike
`sim/loop-gain-phase-margin`'s Middlebrook probe) — `fb` remains the single
node the extraction itself models as one hub, and the DC operating point is
seeded and re-verified exactly as `sim/closed-loop-psrr-pex` does (see
below). It is therefore a strictly smaller change from that experiment's own
template than a loop-gain probe on the PEX netlist would have been (which
would additionally have needed a documented, defensible way to split the
extracted `fb` hub's lumped ground/coupling capacitance between the two
loop-broken halves) — the output-impedance probe reuses the closed,
untouched extraction exactly as-is, changing only the stimulus/measurement
FIXTURE.

## Pass/fail criteria

Identical to `sim/closed-loop-psrr-pex`, and identically limited:

1. `.op` converged within 0.05 V of its own `.nodeset` seed — i.e. the DC
   bias this AC analysis linearizes around is the intended closed-loop
   equilibrium, not the degenerate all-off one `design/bandgap_startup.sch`
   exists to avoid. Verified per point, not assumed.
2. The `.ac` sweep produced a curve to summarise.

**A PASS here does not mean "Zout met a bar."** No spec row addresses
closed-loop output impedance at all — this is a confirmation probe for
issue #191, not a spec-conformance claim.

## Cold-start invocation

Same prerequisites as `sim/closed-loop-psrr-pex` (ngspice, a resolvable
SG13G2 PDK install, OSDI models via `sim/tools/build-osdi.sh`, and at least
one committed `sim/closed-loop-startup/records/*.csv` for the per-corner
nodeset seeds). Does **not** require `klt`.

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/closed-loop-zout-pex/run_pvt_sweep.sh
```

Same output layout (`netlist-snapshots/`, `corners/`, `records/`) as every
other experiment — see `sim/README.md`. This script additionally writes a
`records/<id>-vs-psrr-pex.csv` cross-bench comparison of
`zout_peak_freq_hz` against `sim/closed-loop-psrr-pex`'s own
`psrr_min_freq_hz`, per PVT point, against that experiment's own newest
record.

## Result (record `20260906-003654-dd45eaf`)

**45/45 PVT points PASS. At every single point, `Zout(f)` is strictly
monotonically decreasing across the ENTIRE 1 Hz–1 GHz sweep** — the peak
`|Zout|` is always the DC value (`zout_peak_freq_hz = 1 Hz` at all 45
points, i.e. the summary's own "peak" column never differs from its "DC"
column), and no point's raw `.ac.txt` curve contains so much as a local
bump anywhere in the 20–40 MHz band where `sim/closed-loop-psrr-pex`'s own
dip sits (checked directly against each point's full swept curve, not only
the DC/1 kHz/100 kHz/1 MHz summary columns). DC `|Zout|` spans
`96.04–98.04 dB-ohm` (`~63–80 kΩ`) across the grid — a real, if large,
closed-loop output impedance, physically expected for this topology: unlike
`sns1`/`sns2` (which the amplifier directly senses and forces equal),
`vref` is a mirrored replica leg (`M3A/B/C` sharing the same `fb` gate
signal as `M1`/`M2`) that the feedback loop does not directly regulate —
its own small-signal impedance is set by that leg's own output resistance,
not by the loop's full gain.

**This is a clean, unambiguous null result for the loop-resonance
hypothesis.** Full per-point cross-comparison against
`sim/closed-loop-psrr-pex`'s own `psrr_min_freq_hz`/`psrr_min_db`:
[`records/20260906-003654-dd45eaf-vs-psrr-pex.csv`](records/20260906-003654-dd45eaf-vs-psrr-pex.csv).
Read alongside a direct look at the raw PSRR curve
(`sim/closed-loop-psrr-pex/corners/20260905-233826-f6f3efc/*.ac.txt`): PSRR
does not merely cross 0 dB and keep falling — it dips to a genuine local
**minimum** near 27–32 MHz and then *recovers* (rises back through 0 dB a
few MHz higher, then keeps climbing) — the signature of a **transmission
zero** in the `vdd`→`vref` path's own numerator (a notch), not a pole
shared by the whole closed-loop network. Since PSRR and Zout are two
different closed-loop transfer functions referred to the *same* node
(`vref`) and therefore share the *same* poles (the same linearized
network, the same `1/(1+T(jω))` denominator — injection port only changes
the numerator/zeros), a genuine loop resonance (a real, lightly-damped dip
in `1+T(jω)`) would be expected to produce at least some peaking in
*every* closed-loop transfer function referred to that node, not only the
one stimulated through `vdd`. Zout shows literally none, at any of the 45
PVT points, including the 8 "near-cancellation" `27°C`/`3.63V`-family
points `sim/closed-loop-psrr-pex/README.md` flags as behaving differently
at DC.

**Reading**: this independent probe does **not** corroborate "the loop's
own resonance interacting with extracted wire parasitics" as the
mechanism. It is far more consistent with a **transmission-zero /
feedthrough effect specific to the `vdd`→`vref` path** — most plausibly
the extracted `vdd`-adjacent wire coupling capacitance (`ccc_vdd_vref`,
`cvdd`, and the `rvdd_t*` network feeding the `M3A/B/C` mirror legs that
drive `vref`) creating a high-frequency feedforward term that partially
cancels the regulated path's own rolloff at one frequency (producing the
notch's minimum) and then dominates on either side (producing the
recovery). This is real, physically-grounded post-layout evidence — not a
measurement artifact in the sense of "wrong" — but it changes the
recommended framing from "the loop itself is marginally stable and
resonating" (which would be a stability concern, potentially needing
compensation) to "a passive, layout-specific feedthrough path becomes
significant at high frequency" (a routing/parasitic concern, not a
stability one). See
`spec/decision-records/0006-post-layout-psrr-hf-resonance.md` for the full
decision this confirmation feeds: the mechanism finding, the design-response
call, and the spec-row question.
