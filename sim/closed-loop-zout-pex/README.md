# closed-loop-zout-pex

> ## Two decisions taken by issue #275, before this experiment's re-run
>
> This experiment is one of the five whose PEX evidence is still waived against
> the **pre-trim** geometry in `sim/evidence-freshness-waivers.json`. #272
> delivered the trim-bearing re-layout and re-extraction; #275 settled the two
> questions that had to be answered before the output-impedance grid could be
> re-run against it, and this section records both — the re-run itself is
> **#278**, blocked on **#277**. Neither decision changes any number in the
> records already committed here; they change how the next record is produced
> and how CI judges it. Disclosed here rather than silently reconciled, per this
> repo's convention.
>
> **1. The harness is `klt sim`, not `run_pvt_sweep.sh`** (option 1 of the two
> #275 offered). The dispatch hosts this repo's agents run on forbid
> hand-looping `ngspice -b` over a corner grid and direct multi-corner work to
> `klt sim`'s batch backend. The next record here will therefore be minted by
> `sim/harness/klt_sim_evidence.py` from a `klt sim` report rather than by this
> directory's `run_pvt_sweep.sh`, and its `- **Harness**:` field will say so.
> `run_pvt_sweep.sh` stays on disk and stays correct — it is how every record
> currently in `records/` was produced, and it remains the right entry point on
> a workstation. Read [`sim/harness/README.md`](../harness/README.md) for the
> decision, the three pieces of the harness, the one-corner anchor that proves
> it (3 µV against a committed record), and precisely what still blocks the
> grids: the batch fleet's runner image carries no `ihp-sg13g2` PDK and no
> compiled-OSDI step (#277).
>
> **2. A mask-option PEX DUT has no `trim_code`, and D2 now knows that**
> (disposition (b) of the three #275 sketched). The layout realises **one** trim
> code (128) in metal, so a faithful post-layout netlist of it has no
> `trim_code` parameter, no `XXTRIM` instance and no `RS0`-`RS7` cards: the
> closed straps are real metal (wire resistance, worth ~0.3 mV here — about an
> eighth of the 2.443 mV trim step) and the open strap is simply absent.
> Compared against `design/netlist/bandgap_core.spice`'s *unresolved* instance
> set, such a snapshot would read as `<absent>` on 264 instances and fail the
> D2 freshness rule — even though the design did not change, only its
> representation did.
>
> `.github/scripts/check_evidence_formats.py` now **resolves** the mask option
> before comparing: the behavioural `RS<bit>` strap cards and the `XXTRIM`
> subcircuit call are excluded from the DUT signature, while the ladder's own
> 255 `rppd` units stay in it and must still match device-for-device. That is
> the same convention `layout/lvs_reference.py`'s `convert_with_metal_options`
> already applies to the LVS reference, so both sides of the compare agree on
> what a mask-option netlist is. The code-fixed PEX template this experiment
> will use must therefore name its ladder units `XRU1`-`XRU255`, the schematic's
> own names, because that is what D2 keys on.
>
> The honest cost, stated rather than left implicit: with the strap cards out of
> the expected set, **D2 no longer notices which code a snapshot realises** —
> the 255 units are geometrically identical and D2 compares no node names. That
> axis is guarded by LVS instead, where it belongs: `convert_with_metal_options`
> reads the realised code from the same `.param trim_code` default the layout's
> own `TRIM_CODE` must agree with, so a code mismatch surfaces as an LVS
> failure. Rejected alternative (#275's disposition (a)): keeping a
> `.subckt bandgap_trim` shell with the behavioural straps inside the PEX
> template would have satisfied D2 unchanged, but it would make this bench model
> a code the layout does not realise whenever `trim_code != 128` — a trap set
> for the next reader.

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

## `klt sim` harness migration (issue #278)

This experiment's grid now runs through the `klt sim` batch harness
(`sim/harness/README.md`, the #275 decision) instead of the
`run_pvt_sweep.sh` shell loop; the loop script itself remains for history
and cold-start reference but is no longer the evidence-producing path on
the dispatch hosts (their operating rules direct multi-corner work to
`klt sim`'s batch backend).

```bash
sim/closed-loop-zout-pex/run_klt_sim.sh --sanity   # one local corner, vs the sanity anchor
sim/closed-loop-zout-pex/run_klt_sim.sh --batch    # the PVT grid, on the fleet (resumable)
sim/closed-loop-zout-pex/run_klt_sim.sh --record   # mint the record from the merged report
```

What changed about how this experiment's evidence is minted:

- **The DUT half is generated, not transcribed.**
  `sim/tools/gen_pex_netlist_body.py --cell top` regenerates the whole
  device + wire-parasitic body from the committed extraction and design
  netlists on every run (hub tags read off each device card, the merged
  tap net renamed to `tn0`, the 255 ladder units under their `XRU<n>`
  names for D2, the three subckts are flattened and the merged label nets renamed as in the vref bench). The hand-transcribed
  `testbench/*.spice.tmpl` files remain for history; the bench body
  (`testbench/*.body.spice.tmpl`) now carries only fixtures and includes
  the generated DUT.
- **The grid runs as per-process x supply `klt sim --backend batch` requests**
  (one fleet job each), merged deterministically
  (`sim/harness/merge_batch_shards.py`) before the adapter mints one
  record: the runner image's klt 0.5.0 carries one model library and
  SG13G2's corner set spans three per-device-family files
  (klayout-tools#2668), so the process axis cannot vary within one
  request. same fixture shape as the psrr bench (the `Itest` injection and the seed set are both per-supply) -- 15 requests of 3 temperatures each.
- **Reported precision is 6 significant figures** (`.meas`'s fixed print
  format; `sim/harness/README.md` "Reported precision" owns the
  disposition and its arithmetic against every live claim).
  Same log-side enrichment shape as the psrr bench, with the +dB sign (`Zout = db(v(vref))` for the 1 A stimulus).
- **The per-point verdict is applied by the enrichment pass**
  (`sim/harness/enrich_ac_report.py --kind zout`) over the merged report, not by the loop script's inline
  checks: same verdict shape as the psrr bench.
- The record quadruple layout (`records/<id>.{{md,csv}}` +
  `corners/<id>/*.log` + `netlist-snapshots/<id>/*.spice`) is unchanged --
  `sim/harness/klt_sim_evidence.py` mints it from the report, and the
  netlist snapshots now inline the generated DUT through the same include
  splicing the adapter always did.

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
