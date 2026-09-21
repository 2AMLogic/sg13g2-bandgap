# closed-loop-vref-pvt-pex-boxtc

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
[`spec/decision-records/0009-box-method-tc-evidence.md`](../../spec/decision-records/0009-box-method-tc-evidence.md).

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
[`spec/decision-records/0009-box-method-tc-evidence.md`](../../spec/decision-records/0009-box-method-tc-evidence.md)
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
