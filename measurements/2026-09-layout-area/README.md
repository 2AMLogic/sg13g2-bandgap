# Layout-area measurement (T1 item 5 — the `Area` spec row)

> **Update (issue #173, 2026-09-05) — the numbers in this file's own tables
> are the *pre-fold* geometry, and `area_record.json` next to it is not.**
> This analysis's conclusion (aspect ratio from unfolded resistor bars, not
> device count, accounts for 77.5% of the assembled footprint) was acted on
> in issue #173: every long poly-resistor bar in `layout/` is now drawn as a
> serpentine, and both assemblies were re-packed. `area_record.json` is a
> *derived* artifact — `measure_area.py --check` re-derives it from whatever
> GDS is committed and fails on drift — so it was refreshed to today's
> geometry rather than left contradicting the tree. **The prose tables below
> were not rewritten**: they are this analysis's own findings and stand as
> the recorded "before". The before/after comparison, and the mechanism
> analysis for the residual whitespace, live in
> [`../2026-09-resistor-fold/README.md`](../2026-09-resistor-fold/README.md).
> Headline: `sg13cmos5l_bandgap_top` 0.3211 mm² -> 0.0476 mm² (6.74x),
> `bandgap_startup` 63.7:1 -> 1.0:1, `sg13cmos5l_bandgap_startup`
> 145.4:1 -> 1.6:1, with no resistor's extracted value and no cell's
> DRC/LVS verdict changed.

First evidence of any kind for the one row of `spec/porting-plan.md` §6 that
had **none**: `Area | < 0.05 mm²`. Every other row of that seven-row draft
table already has a committed `sim/` testbench and an append-only evidence
record — `vref`/TC (`sim/closed-loop-vref-pvt`), PSRR
(`sim/closed-loop-psrr`), supply (all of them, swept), Iq
(`sim/closed-loop-iq`), startup (`sim/closed-loop-startup`,
`sim/startup-trip-point`, `sim/startup-time-to-release`). Area was the
outstanding gap, and `sim/closed-loop-iq/README.md` says so in as many words:

> the last of the two `spec/porting-plan.md` §6 draft-table rows (…) with no
> `sim/` testbench coverage at all — **area is the only remaining gap, and is
> a layout-geometry metric, out of `sim/`-testbench scope**

It is out of `sim/` scope because it is not a PVT-cornered simulation: it is
a geometry measurement of committed GDS. That is what this record is, and it
lives in `measurements/` for exactly the reason `measurements/README.md`
gives — "supplementary quantitative analysis that doesn't fit `sim/`'s
per-experiment append-only evidence convention".

## What this claims, and what it does not

**It claims**: the layouts committed on `main` today occupy the bounding-box
footprints, and contain the drawn-polygon areas, tabulated below —
re-derivable from the committed GDS files by anyone with `klt` on `PATH`, in
seconds, with no PDK and no simulator (`measure_area.py --check`).

**It does not claim conformance to any ratified spec row.**
`spec/porting-plan.md` §6 is still a **draft, unratified** table (#125,
PR #128). Following the same discipline `sim/closed-loop-iq/README.md`
established, the committed `area_record.json` carries `"verdict": null`: it
reports what was measured as *evidence*, not as a pass/fail verdict against a
target nobody has ratified. The `< 0.05 mm²` figure appears below only as the
drafted number these measurements are evidence *for*, so a reader never has to
guess which row a number relates to.

**It does not claim these are manufacturable-quality layouts.** Every cell
here is the labeled floorplan/device-placement layout `layout/README.md`
documents, not a finished physical implementation. The area of a floorplan is
a real, checkable number about the artifact this repo actually ships — it is
not a prediction of the area of a layout nobody has drawn yet.

**It does not measure the assembled SG13G2 block**, because no such GDS exists
on `main`. See "The SG13G2 gap" below.

## Results

Measured 2026-09-04 by `measure_area.py --write` against every committed
`layout/<cell>/<cell>.gds`; per-cell GDS `sha256` and the `klt` version are
recorded in [`area_record.json`](area_record.json).

`footprint` is the top cell's bounding-box area (`width × height`) — the
number the drafted spec row is about. `drawn` is the total area of drawn
polygons; it is a strict lower bound on any re-floorplanned version of the
same devices, i.e. the part of the footprint a placement change cannot
remove. `density` is `drawn / footprint`.

| cell | bbox (µm) | footprint (µm²) | footprint (mm²) | drawn (µm²) | density | aspect |
|---|---|---|---|---|---|---|
| `bandgap_core` | 516.90 × 64.50 | 33,340.1 | 0.0333 | 7,011.8 | 0.210 | 8.0:1 |
| `bandgap_startup` | 1416.90 × 22.24 | 31,511.9 | 0.0315 | 8,967.0 | 0.285 | 63.7:1 |
| `sg13cmos5l_bandgap_amp` | 84.00 × 42.94 | 3,607.0 | 0.0036 | 2,590.2 | 0.718 | 2.0:1 |
| `sg13cmos5l_bandgap_core` | 840.50 × 64.91 | 54,556.9 | 0.0546 | 9,658.4 | 0.177 | 12.9:1 |
| `sg13cmos5l_bandgap_startup` | 1424.90 × 9.80 | 13,964.0 | 0.0140 | 8,553.3 | 0.613 | 145.4:1 |
| `sg13cmos5l_bandgap_top` | 2455.75 × 130.75 | 321,089.3 | 0.3211 | 29,667.5 | 0.092 | 18.8:1 |

## The SG13G2 gap: what can and cannot be concluded

`spec/porting-plan.md` §6's `Area` row is **SG13G2-only** —
`spec/porting-plan-sg13cmos5l.md` states no area target at all (checked: it
contains no area row). So the row's subject is the assembled SG13G2 block, and
on `main` today the SG13G2 variant has GDS for only two of its four cells
(`bandgap_core`, `bandgap_startup`); `bandgap_amp` and `bandgap_top` have
none. That is issue **#169** / PR **#170**, open at the time of writing. The
assembled SG13G2 footprint therefore **cannot** be measured yet, and this
record does not pretend to.

Two things *can* be concluded rigorously from the numbers above, and are worth
recording now because neither depends on #170 landing:

1. **A hard floor of 33,340 µm² (0.0333 mm², 67% of the drafted 50,000 µm²
   budget) is already committed, from `bandgap_core` alone.** Any assembly
   containing an instance of `bandgap_core` has a bounding box at least as
   large as that instance's own — rotation preserves area, so this holds for
   any placement. `bandgap_startup` (31,511.9 µm²) and `bandgap_amp` (not yet
   drawn) are still to be added on top of it.
2. **The floor is an aspect-ratio/placement problem, not a device-count
   problem.** The two SG13G2 cells' *drawn* geometry totals 15,978.7 µm² —
   32.0% of the budget, and a strict lower bound no re-floorplanning can
   remove. The other 68% of the budget is not consumed by devices; it is
   consumed by whitespace, at densities of 0.210 and 0.285.

## Where the whitespace comes from (sibling-variant evidence)

The SG13CMOS5L variant is the only one in this repo with a committed,
hierarchically assembled top-level GDS, built by the same generators and in
the same unfolded-bar style, so it is the best available evidence for what an
SG13G2 assembly will cost. It is a **proxy, not a spec comparison** — as noted
above, the CMOS5L porting plan drafts no area row.

- `sg13cmos5l_bandgap_top` occupies **321,089.3 µm² (0.3211 mm²)** — 6.4× the
  SG13G2 draft table's 0.05 mm², at a density of **0.092**.
- Its three leaf cells' own footprints total 72,127.9 µm². The assembly is
  **4.45×** that: **77.5% of the assembled footprint lies outside every leaf's
  own bounding box.** The dominant area cost is inter-cell whitespace, not the
  cells.
- Inter-cell routing itself is not the culprit either: the top's drawn area
  (29,667.5 µm²) exceeds the sum of its leaves' drawn areas (20,801.9 µm²) by
  only 8,865.6 µm².
- The mechanism is visible in the `aspect` column. `sg13cmos5l_bandgap_startup`
  is a **145:1** bar (1424.9 × 9.8 µm) — `layout/README.md` already documents
  that its `R1` resistor "is a ~1.4 mm bar which single-handedly sets the
  cell's bounding box". `layout/sg13cmos5l-bandgap_top/generate.py` places the
  three leaves **side by side in disjoint x-ranges** (documented in
  `layout/README.md`), so the assembly's width is the sum of three widths while
  its height is set by the tallest cell — a box whose height the 9.8 µm-tall
  startup bar occupies 7% of, across 58% of its width.

The same 63.7:1 unfolded `R1` bar is present in SG13G2's own
`bandgap_startup`, so the same mechanism should be expected to dominate the
SG13G2 assembly once #169/PR #170's `bandgap_top` lands and this measurement
is re-run.

**Dominant-error-regime conclusion**: folding the long resistor bars
(serpentine/multi-segment) and interleaving the placement, rather than
reducing devices, is where an area reduction would come from. This mirrors
`measurements/2026-08-tc-retune/`'s finding for the TC row — identify the
dominant regime first, then fix that, rather than adding circuitry.

## Reproducing

```bash
python3 measurements/2026-09-layout-area/measure_area.py            # print the table
python3 measurements/2026-09-layout-area/measure_area.py --check    # verify the record
python3 measurements/2026-09-layout-area/measure_area.py --write    # re-mint the record
```

Requires only `klt` on `PATH` (klayout-tools) — no PDK, no ngspice, no
`klayout` python module. `--check` re-derives every geometry number from the
committed GDS and exits non-zero on any drift; it deliberately ignores the
provenance block (`klt` version, timestamp), because the reproducibility claim
is "the same GDS yields the same areas", not "the same machine".

`measure_area.py` discovers cells by the same `layout/<cell>/<cell>.gds`
convention `.github/scripts/check_evidence_formats.py`'s `check_layout()`
enforces, so a cell that gains a layout later (e.g. `bandgap_top` via #170) is
picked up with no edit to the script — only a `--write` and a new record.

## Incidental finding: a stale bbox citation in `layout/README.md`

Running this measurement surfaced that `layout/README.md`'s `bandgap_core`
paragraph still cited the **pre-retune** geometry: bbox
`(-5.4, -3.1)`–`(694.7, 61.4)` µm, "105 shapes/labels across 13
layer/datatype/purpose combinations". The committed GDS measures bbox
`(-5.4, -3.1)`–`(511.5, 61.4)` µm, 241 shapes, 20 layer/datatype
combinations. The `694.7` right edge is the `R1 = 694.5 µm` bar that
`measurements/2026-08-tc-retune/` retuned to `511 µm` (#134/#139) — the
citation was never refreshed when the retune landed. Corrected in the same PR
as this record; the `EmWind.drawing` (33/0) claim of exactly 10 shapes in that
same paragraph re-verified and is still correct.

## Relation to issue #4 (T1 checklist)

This is a *part of* T1 item 5, not a closure of it. Item 5 requires every spec
row at its bound corners against a **ratified** table; §6 is not ratified
(#125/PR #128), and one row's evidence does not make a table. What changes is
that the `Area` row moves from "no artifact at all" to "measured, recorded,
reproducible, with the dominant cost regime identified" — the same increment
PR #168 made for the startup row.
