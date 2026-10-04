# closed-loop-vref-pvt-pex-boxtc

> ## Two decisions taken by issue #275, before this experiment's re-run
>
> This experiment is one of the five whose PEX evidence is still waived against
> the **pre-trim** geometry in `sim/evidence-freshness-waivers.json`. #272
> delivered the trim-bearing re-layout and re-extraction; #275 settled the two
> questions that had to be answered before the 120-point box-method TC transient grid could be
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

Closed-loop **post-layout (PEX) box-method temperature-coefficient
characterization** (issue #222, follow-on to #186). Co-simulates the exact
same layout-extracted closed-loop topology
[`../closed-loop-vref-pvt-pex/`](../closed-loop-vref-pvt-pex/README.md)
uses — every MOS/resistor device's geometry and the whole block's wire
parasitics from `klt extract --deck sg13g2 --parasitics` against the
routed, assembled `layout/bandgap_top/bandgap_top.gds`, bipolar devices
spliced from the schematic — with a **byte-identical per-point netlist from
the `.lib` line down**. This experiment's only difference from that bench
is the **temperature grid** its driver sweeps.

## Why this experiment exists

Issue #222's second build item: the only box-method TC numbers in the repo
before this experiment were **pre-layout and scratch-harness**
(`measurements/2026-08-tc-retune/README.md` §4b), while the ratified TC row
is claimed at **both** levels (its endpoint-method evidence exists at both:
`../closed-loop-vref-pvt/` and `../closed-loop-vref-pvt-pex/`). This bench
closes the PEX half of that gap: the box method
(`(vmax − vmin)/(vref(27 °C) · 165 °C)` over
`{-40, −20, 0, 27, 50, 75, 100, 125} °C`) on the same assembled-GDS
extraction the official post-layout vref bench uses, across the full
corner × supply grid.

## What this testbench claims, and what it does not

It claims: across process corner `{typ, bcs, wcs, sf, fs}` × temperature
`{-40, -20, 0, 27, 50, 75, 100, 125} °C` × supply `{2.97, 3.30, 3.63} V`
(120 points), the settled post-layout `vref` series supports a
**box-method TC per corner/supply group**, under the same four pass
criteria as the official post-layout bench (startup released, loop closed,
not railed, `|vref(3ms) − vref(2ms)| ≤ 1 mV`). `records/<record-id>-boxtc.csv`
records each group's extrema, their temperatures, `n_pass`/`n_grid`, the
box TC and the endpoint TC on the same run's data;
`records/<record-id>-vs-schematic-boxtc.csv` additionally diffs every
group's box TC against
[`../closed-loop-vref-pvt-boxtc/`](../closed-loop-vref-pvt-boxtc/README.md)'s
own current (newest) record — the post-layout delta of the metric this
experiment measures, from committed records only.

**It does not change any target** — same disclaimer as the schematic
sibling; see that README and
[`spec/decision-records/0010-box-method-tc-evidence.md`](../../spec/decision-records/0010-box-method-tc-evidence.md).

What the extraction does and does not model (bipolar devices
schematic-sourced, the three merged-net-label pins, the `vsubs` far-plate
convention) is unchanged from
[`../closed-loop-vref-pvt-pex/`](../closed-loop-vref-pvt-pex/README.md)'s
own account — this bench re-encodes that experiment's device set
verbatim.

## Pass/fail criteria

Identical to [`../closed-loop-vref-pvt-pex/`](../closed-loop-vref-pvt-pex/README.md)'s
(startup released, loop closed, not railed, settled) — a point that is not
a genuine settled closed-loop operating point has no `vref` worth feeding
a box method. A `FAIL` point contributes no `vref` to its group's box.

## Non-converged points (issue #222 AC 3)

Same policy as the schematic sibling's README documents (disclose via
`n_pass < n_grid`, justify from this run's own committed flanking points,
prefer outright convergence via the official harness's aids). The §4b
scratch scan's single non-convergence was pre-layout (`wcs`/0 °C); this
bench applies the same machinery because a post-layout grid point can fail
the same way, for the same solver reasons the official post-layout bench's
own header documents.

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../closed-loop-vref-pvt-pex/`](../closed-loop-vref-pvt-pex/README.md)
(`typ`/`bcs`/`wcs`/`sf`/`fs` → `hbt_*` × `mos_*` × `res_*` sections,
identical to the schematic-side table) × temperature
`{-40, -20, 0, 27, 50, 75, 100, 125} °C` × supply `{2.97, 3.30, 3.63} V`
= **120 points**.

## Results summary (this repo's own committed record)

Record [`records/20260921-195122-77820fc.md`](records/20260921-195122-77820fc.md):
**120/120 points PASS** — every group in
`records/20260921-195122-77820fc-boxtc.csv` reads `n_pass == n_grid == 8`
(no non-converged points, same as the schematic sibling — the official
harness's convergence aids cleared the grid the §4b scratch harness could
not).

- **Worst box-method corner: `bcs`/3.63 V = 20.137 ppm/°C**
  (`vmax` 1.04750 V @ 0 °C, `vmin` 1.04402 V @ 125 °C, `vref(27 °C)`
  1.04735 V) — **outside the `< 20 ppm/°C` stretch by ~0.7%**. The sampled
  maximum at 0 °C sits within the 0/27 °C bracket of its own near-vertex
  (parabolic vertex bound: ≈ 1.04750 V @ ≈ 2.2 °C, vertex-corrected box
  ≈ 20.14 ppm/°C) — the overshoot is not a sampling artifact.
- **The worst corner moves post-layout**: pre-layout the worst box group is
  `wcs` (19.765 @ 3.30 V); post-layout `wcs` *improves* by −1.7…−2.0
  ppm/°C while `typ`/`bcs`/`sf`/`fs` *degrade* by +1.4…+2.5, putting
  `bcs`/3.63 V on top — per-group deltas in
  `records/20260921-195122-77820fc-vs-schematic-boxtc.csv`. The wire-parasitic
  series-R shift `../closed-loop-vref-pvt-pex/` already documents moves
  each corner's `vref(T)` series slightly and differently; at the stretch
  boundary those small shifts flip which corner binds.
- Box TC across all 15 groups: **10.56-20.14 ppm/°C**; endpoint method on
  the same run's data: |TC| ≤ 17.59 ppm/°C — the same endpoint-understates
  pattern as the schematic sibling, at every group.

The ratified-row reading this record feeds (target met with >2.4× margin
at both levels; stretch met by endpoint method at both levels, box method
at the boundary — pre-layout just inside, post-layout just outside) is
recorded in
[`spec/decision-records/0010-box-method-tc-evidence.md`](../../spec/decision-records/0010-box-method-tc-evidence.md)
and reflected in `README.md`'s TC-row status.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-vref-pvt-pex-boxtc/run_pvt_sweep.sh          # sequential (default)
JOBS=8 sim/closed-loop-vref-pvt-pex-boxtc/run_pvt_sweep.sh   # bounded parallel
```

`JOBS=N` (default 1) has the same wall-clock-only contract the schematic
sibling's README documents (established by `../closed-loop-vref-mc/`'s
`--parallel`): same points, same results, same emission order.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows, and
`../closed-loop-vref-pvt-pex/README.md` for how to regenerate the committed
`layout/bandgap_top/bandgap_top.pex.spice` input this bench re-encodes
(`klt`, offline, once — not needed to re-run this sweep).

## `klt sim` harness migration (issue #278)

This experiment's grid now runs through the `klt sim` batch harness
(`sim/harness/README.md`, the #275 decision) instead of the
`run_pvt_sweep.sh` shell loop; the loop script itself remains for history
and cold-start reference but is no longer the evidence-producing path on
the dispatch hosts (their operating rules direct multi-corner work to
`klt sim`'s batch backend).

```bash
sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --sanity   # one local corner, vs the sanity anchor
sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --batch    # the PVT grid, on the fleet (resumable)
sim/closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh --record   # mint the record from the merged report
```

What changed about how this experiment's evidence is minted:

- **The DUT half is generated, not transcribed.**
  `sim/tools/gen_pex_netlist_body.py --cell top` regenerates the whole
  device + wire-parasitic body from the committed extraction and design
  netlists on every run (hub tags read off each device card, the merged
  tap net renamed to `tn0`, the 255 ladder units under their `XRU<n>`
  names for D2, the three subckts are flattened through the design netlist's own instance lines, and the `FB|OUT`/`IN_N|SNS1`/`IN_P|SNS2` merged label nets are renamed to their schematic names `fb`/`sns1`/`sns2`). The hand-transcribed
  `testbench/*.spice.tmpl` files remain for history; the bench body
  (`testbench/*.body.spice.tmpl`) now carries only fixtures and includes
  the generated DUT.
- **The grid runs as per-process x supply `klt sim --backend batch` requests**
  (one fleet job each), merged deterministically
  (`sim/harness/merge_batch_shards.py`) before the adapter mints one
  record: the runner image's klt 0.5.0 carries one model library and
  SG13G2's corner set spans three per-device-family files
  (klayout-tools#2668), so the process axis cannot vary within one
  request. same fixture shape as the vref bench -- 15 requests of 8 temperatures each (120 points), the most harness-bound grid of the five.
- **Reported precision is 6 significant figures** (`.meas`'s fixed print
  format; `sim/harness/README.md` "Reported precision" owns the
  disposition and its arithmetic against every live claim).
  Same `.save`/`par()` constraint and same derived-column handling as the vref bench.
- **The per-point verdict is applied by the enrichment pass**
  (`sim/harness/enrich_pvt_report.py`) over the merged report, not by the loop script's inline
  checks: same four criteria as the vref bench.
- The record quadruple layout (`records/<id>.{{md,csv}}` +
  `corners/<id>/*.log` + `netlist-snapshots/<id>/*.spice`) is unchanged --
  `sim/harness/klt_sim_evidence.py` mints it from the report, and the
  netlist snapshots now inline the generated DUT through the same include
  splicing the adapter always did.
