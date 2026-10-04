# closed-loop-psrr-pex

> ## Two decisions taken by issue #275, before this experiment's re-run
>
> This experiment is one of the five whose PEX evidence is still waived against
> the **pre-trim** geometry in `sim/evidence-freshness-waivers.json`. #272
> delivered the trim-bearing re-layout and re-extraction; #275 settled the two
> questions that had to be answered before the AC PSRR grid could be
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

Post-layout (PEX) counterpart to
[`sim/closed-loop-psrr/`](../closed-loop-psrr/README.md), for T1 tracker #4
item 7 (post-layout simulation). Same claim, same co-simulated
`bandgap_core` + `bandgap_amp` + `bandgap_startup` closed-loop topology, same
45-point PVT grid, same AC injection and PSRR sign convention — the
difference is where every MOS/resistor device's geometry, and every wire's
parasitic R/C, comes from: the schematic-level testbench copies
`design/netlist/bandgap_core.spice` / `bandgap_amp.spice` /
`bandgap_startup.spice` verbatim; this one re-encodes 17 MOS + 3 resistor
devices, plus the whole block's wire-parasitic network, from
`klt extract --deck sg13g2 --parasitics layout/bandgap_top/bandgap_top.gds`
(committed as `layout/bandgap_top/bandgap_top.pex.spice` +
`pex_extract_report.json`). Read this file before trusting a record here — it
is **not** a pure layout extraction re-simulated as-is.

**This is the second closed-loop PEX experiment in this tree, and the first
frequency-domain one.** `sim/closed-loop-vref-pvt-pex/` (issue #186) covers
the same assembled layout in the time/DC domain; `sim/core-open-loop-bias-pex/`
and `sim/startup-trip-point-pex/` (issue #14) are leaf-cell, open-loop, and
also DC/transient. Until this experiment, **no** post-layout evidence in this
repo said anything about the block's small-signal behaviour — the frequency
range is exactly where wire capacitance is expected to matter most, so it is
the part of the pre-layout evidence a PEX re-run was least entitled to be
assumed to reproduce. (It does not: see "What the layout changes" below.)

## Composition: two existing testbenches, three deltas

The testbench template is deliberately the *device/parasitic half* of
`sim/closed-loop-vref-pvt-pex/testbench/tb_closed_loop_vref_pex.spice.tmpl`
(same extraction, same instance names, same wire-parasitic block, copied
verbatim) driven by the *measurement half* of
`sim/closed-loop-psrr/testbench/tb_closed_loop_psrr.spice.tmpl` (AC injection
on `vdd`, `.nodeset`-seeded `.op`, `PSRR(f) = -db(v(vref))`). Everything each
of those files documents applies here unchanged and is not restated:

- **What the extraction does and does not model** (bipolar devices are still
  not extracted and are spliced in from the schematic; D/S terminal roles may
  be swapped harmlessly; body/well ties are real, not a fixture; the three
  merged-net labels `FB|OUT` / `IN_N|SNS1` / `IN_P|SNS2` are intended
  top-level ties, not shorts) →
  [`sim/closed-loop-vref-pvt-pex/README.md`](../closed-loop-vref-pvt-pex/README.md).
- **Why PSRR is measured with the loop closed, the sign convention, and the
  nodeset provenance** → [`sim/closed-loop-psrr/README.md`](../closed-loop-psrr/README.md).

Only three things are new here:

1. **`vsubs` is tied to `vss`**, not through the 1 TΩ DC tie the transient PEX
   benches use — see below; the size of that choice is measured in
   [`vsubs-tie-sensitivity.md`](vsubs-tie-sensitivity.md).
2. The transient `vdd` ramp is replaced by a DC supply carrying the 1 V / 0°
   AC stimulus (so this bench needs no `rshunt`/`gmin`/`reltol` convergence
   aids — there is no near-singular ramp instant to get through).
3. `run_pvt_sweep.sh` uses the **sibling experiment's own**
   `../closed-loop-psrr/tools/psrr_summary.awk` rather than a copy, so the
   two benches' DC/worst-case/interpolated numbers cannot drift apart and
   quietly invalidate the cross-bench comparison below.

## The vsubs tie matters here

Every extracted ground capacitance returns to the node `vsubs`. The DC and
transient PEX benches tie it to `0` through 1 TΩ; a frequency-domain bench
cannot, because at AC that leaves `vsubs` floating and each net's ground cap
couples net-to-net instead of to ground. The substrate is tied to `vss` in
this block, so this bench shorts `vsubs` to `vss` through a 0 V source.

Measured, not asserted ([`vsubs-tie-sensitivity.md`](vsubs-tie-sensitivity.md),
three PVT points): the two ties agree to ≤ 0.1 mdB **at DC**, and the 1 TΩ
float reports PSRR **4.0–5.2 dB better at 100 kHz and 5.9–6.0 dB better at
1 MHz** with a ~1.0 dB shallower worst-case dip. Inheriting the DC fixture
unexamined would therefore have made this experiment's headline
high-frequency numbers optimistic by ~5–6 dB.

## Dependency on layout/README.md

`layout/bandgap_top/lvs_report.json` reads `status: "mismatch"`, narrowed to
a single permanent cause: three `device.unmatched` errors on `Q1`/`Q2`/`Q3`
(`class: "NPN13G2"`) plus their class-level `topology` entry, because SiGe
HBT recognition is **permanently declined upstream**
([`klayout-tools#1242`](https://github.com/2AMLogic/klayout-tools/issues/1242)).
Every MOS and resistor device matches (`counts.devices.matched: 20`, of `23`
reference). `layout/README.md`'s "DRC/LVS verification" section is the
authoritative account.

## Pass/fail criteria

Identical to `sim/closed-loop-psrr`, and identically limited:

1. `.op` converged within 0.05 V of its own `.nodeset` seed — i.e. the DC bias
   this AC analysis linearizes around is the intended closed-loop equilibrium,
   not the degenerate all-off one `design/bandgap_startup.sch` exists to
   avoid. Verified per point, not assumed.
2. The `.ac` sweep produced a curve to summarise.

**A PASS here does not mean "PSRR met a bar."** No spec row is ratified
(#125), so nothing gates on the PSRR value itself; a PASS means a trustworthy
measurement was produced at a verified operating point.

## `klt sim` harness migration (issue #278)

This experiment's grid now runs through the `klt sim` batch harness
(`sim/harness/README.md`, the #275 decision) instead of the
`run_pvt_sweep.sh` shell loop; the loop script itself remains for history
and cold-start reference but is no longer the evidence-producing path on
the dispatch hosts (their operating rules direct multi-corner work to
`klt sim`'s batch backend).

```bash
sim/closed-loop-psrr-pex/run_klt_sim.sh --sanity   # one local corner, vs the sanity anchor
sim/closed-loop-psrr-pex/run_klt_sim.sh --batch    # the PVT grid, on the fleet (resumable)
sim/closed-loop-psrr-pex/run_klt_sim.sh --record   # mint the record from the merged report
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
  request. an `alter`-driven supply axis would clobber the 1 V AC stimulus (verified on ngspice 46), and the nodeset seed set is per-supply -- 15 requests of 3 temperatures each.
- **Reported precision is 6 significant figures** (`.meas`'s fixed print
  format; `sim/harness/README.md` "Reported precision" owns the
  disposition and its arithmetic against every live claim).
  The request's four measurements are linear magnitudes (`find v(vref) at=<f>`); the dB conversions and the op-point / worst-case / worst-case-frequency columns are formed by the enrichment pass from single reported values and the per-corner log's printed AC sweep (the runner image's klt 0.5.0 predates `measurements[].expr`, and curve argmin has no `.meas` form at all).
- **The per-point verdict is applied by the enrichment pass**
  (`sim/harness/enrich_ac_report.py --kind psrr`) over the merged report, not by the loop script's inline
  checks: op landed near its `.nodeset` seed (50 mV, the hand-transcribed bench's own check), startup released, loop closed, fb not railed. The bench stays nodeset-seeded rather than ramp-settled because ngspice re-solves the DC operating point for an `ac` analysis from the sources' DC values -- a ramp-settled PWL supply linearises around a collapsed point (verified on ngspice 46 with a nonlinear circuit; a linear one cannot distinguish the two).
- The record quadruple layout (`records/<id>.{{md,csv}}` +
  `corners/<id>/*.log` + `netlist-snapshots/<id>/*.spice`) is unchanged --
  `sim/harness/klt_sim_evidence.py` mints it from the report, and the
  netlist snapshots now inline the generated DUT through the same include
  splicing the adapter always did.

## Cold-start invocation

Same prerequisites as `sim/closed-loop-psrr` (ngspice, a resolvable SG13G2
PDK install, OSDI models via `sim/tools/build-osdi.sh`, and at least one
committed `sim/closed-loop-startup/records/*.csv` for the per-corner nodeset
seeds). Does **not** require `klt`: `klt` was used once, offline (issue #187),
to produce the committed `layout/bandgap_top/bandgap_top.pex.spice` this
testbench re-encodes. Regenerate that input with:

```bash
cd layout/bandgap_top
klt extract --deck sg13g2 --parasitics bandgap_top.gds \
  -o bandgap_top.pex.spice --format json > pex_extract_report.json
```

If it changes, regenerate this template's device cards and wire-parasitics
block from the new file the same way
[`sim/closed-loop-vref-pvt-pex/README.md`](../closed-loop-vref-pvt-pex/README.md)
documents (`sim/tools/dump_pex_wire_parasitics.py`, then the
`FB|OUT`/`IN_N|SNS1`/`IN_P|SNS2` → `fb`/`sns1`/`sns2` rename) — both templates
carry the same device/parasitic block on purpose.

Then:

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/closed-loop-psrr-pex/run_pvt_sweep.sh
```

Same output layout (`netlist-snapshots/`, `corners/`, `records/`) as every
other experiment — see `sim/README.md`. This script additionally writes a
`records/<id>-vs-schematic.csv` cross-bench delta against
`sim/closed-loop-psrr/`'s own newest record.

## What the layout changes (record `20260905-233826-f6f3efc`)

45/45 PVT points PASS. Compared point-by-point against
`sim/closed-loop-psrr/records/20260830-133912-d83f7c4.csv` (that experiment's
own current record) in `records/20260905-233826-f6f3efc-vs-schematic.csv`.
Three findings, each read off the committed per-point data rather than
inferred from the headline maximum:

**1. At DC, the layout costs very little — under 2 dB.** At the 37 of 45
points whose schematic-level DC PSRR sits in the ordinary 59.7–77 dB band,
`ΔPSRR(DC)` spans just `−1.94 … +0.54 dB`, and the post-layout DC PSRR band
is `60.20–72.00 dB`. Every one of the 45 points stays above 60 dB at DC
post-layout (worst: 60.20 dB at `wcs`/125 °C/2.97 V). That is *not* a claim
against `spec/porting-plan.md` §6's still-unratified `PSRR @ DC > 60 dB`
draft row (#125) — it is the measured band, recorded so a future ratification
pass has post-layout evidence to reason from instead of pre-layout only.

**2. The remaining 8 points are the near-cancellation peaks, and they move a
lot in both directions — expected, not a regression.** `sim/closed-loop-psrr`'s
own README already documents that this design shows a bias-point-specific
near-cancellation at some corners, where DC PSRR peaks (up to 100.4 dB
schematic). Those 8 points (every `27 °C`/`3.63 V` group, plus three
`125 °C`/`3.30 V` ones) carry `ΔPSRR(DC)` from `−12.70` to `+18.77 dB` — the
whole reported range of this record's headline maximum. A peak that exists
because two contributions nearly cancel has a height set by the residual, so
any perturbation (here: ~870 Ω of wire resistance and 261 fF of wire
capacitance) moves it by a lot in whichever direction it happens to push the
residual. All 8 remain ≥ 74.4 dB post-layout, i.e. still better than the
ordinary points — the peaks shift, they do not become holes.

**3. Above ~10 kHz the layout costs real rejection, and the worst-case dip
crosses below 0 dB — this is the finding.** Interpolated at fixed
frequencies, post-layout minus schematic: **`−5.1 … −18.9 dB` at 100 kHz** and
**`−15.8 … −19.2 dB` at 1 MHz** (post-layout bands `53.4–56.3 dB` and
`34.3–36.5 dB`, versus `59.5–74.7` and `50.6–54.9` schematic). The worst-case
dip degrades uniformly by `−4.66 … −5.15 dB` at every one of the 45 points
and moves **down** in frequency, from `31.6–39.8 MHz` (schematic,
`+2.52 … +4.26 dB`) to `27.1–31.6 MHz` (post-layout, `−2.15 … −0.84 dB`).

  Read plainly: **at all 45 PVT points, the post-layout block slightly
  *amplifies* supply ripple (by 0.8–2.1 dB) in a narrow band near 30 MHz,
  where the pre-layout netlist still rejected it by 2.5–4.3 dB.** The
  direction and the frequency both track the added wire capacitance, and the
  band sits in the same decade as `sim/loop-gain-phase-margin`'s
  independently-measured 41.6–53.4 MHz unity-gain crossover (read from that
  experiment's own current record, `20260830-133911-d83f7c4.csv`, 44 of 45
  points reporting a crossing) and the thin
  gain-margin story issue #146 records for that experiment — a circumstantial
  case (three separately-built testbenches pointing at the same region) this
  README originally read as suggesting a shared loop-resonance mechanism.
  No spec row addresses PSRR away from DC, so this violates nothing; it is
  recorded because it is a real post-layout behaviour change that
  pre-layout evidence alone would have missed.

  **Update (issue #191, corrected):** the loop-resonance hypothesis above
  was explicitly flagged as circumstantial and unconfirmed, and issue #191's
  independent confirmation testbench,
  [`sim/closed-loop-zout-pex/`](../closed-loop-zout-pex/README.md), **does
  not corroborate it.** That experiment probes the same closed-loop network
  on the same PEX netlist from a different port (a current injected
  directly at `vref` rather than a voltage on `vdd`) and finds `Zout(f)`
  strictly monotonically decreasing across the *entire* 1 Hz–1 GHz sweep at
  all 45 points — no peaking anywhere near 27–31 MHz, or anywhere at all.
  Since PSRR and Zout share the same closed-loop poles (differing only in
  which port is stimulated), a genuine loop resonance would be expected to
  show up in both; its total absence in Zout, combined with PSRR's own
  curve showing a local minimum that *recovers* a few MHz higher rather
  than a monotonic crossing, points instead at a **transmission zero /
  feedthrough effect specific to the `vdd`→`vref` path** (most plausibly
  the extracted `vdd`-adjacent wire coupling into the `M3A/B/C` mirror legs
  that drive `vref`), not a shared-pole loop resonance. See
  `spec/decision-records/0006-post-layout-psrr-hf-resonance.md` for the
  full mechanism finding, the resulting design-response decision (accept
  as-is; no compensation capacitor warranted, since no instability was
  found), and the spec-row decision (deferred to the eventual ratification
  pass, #125).

## What this experiment does not do

- **It is not a spec-conformance claim.** No row of `spec/porting-plan.md` §6
  is ratified (#125), and item 7 of tracker #4 asks for a *spec-suite* re-run
  against a ratified spec. This lands one more spec-row-shaped measurement of
  that eventual suite in post-layout form; it does not check any box on its
  own.
- **It is not a statistical claim.** Deterministic corners only — no Monte
  Carlo (tracker #4 item 6, N/A per #5).
- **It does not re-derive the extraction.** The extraction is
  `layout/bandgap_top/bandgap_top.pex.spice` @ its committed git sha, stamped
  in every record; its own freshness is `layout/`'s hash-checked concern
  (`.github/scripts/check_evidence_formats.py`).
