# measurements

Supplementary quantitative analysis that doesn't fit `sim/`'s per-experiment
append-only evidence convention (multi-run comparisons, design-space
searches, dominant-error-regime writeups) — see the repo README for scope.

- `2026-08-tc-retune/` — issue #134: the TC-row gap analysis (per-corner
  measured-vs-drafted table), the slope-vs-curvature dominant-error-regime
  analysis, and the resistor-ratio retune (`R1`: 694.5um -> 511um) that
  closed it, cross-referenced against the `sim/closed-loop-vref-pvt`
  evidence this analysis is built on.
- `2026-09-layout-area/` — issue #4 (T1 checklist item 5): the first evidence
  for `spec/porting-plan.md` §6's `Area` row, the one row of that table with
  no artifact of any kind. A reproducible `klt stats`-based measurement of
  every committed `layout/<cell>/<cell>.gds` (footprint, drawn area, density,
  aspect ratio) plus the dominant-cost-regime analysis — whitespace from
  unfolded resistor bars, not device count.
- `2026-09-resistor-fold/` — issue #173: the before/after for acting on that
  analysis. Every long poly-resistor bar is now drawn as a serpentine and
  both top-level assemblies were re-packed; this entry records the resulting
  footprint/aspect-ratio move on all eight committed cells, the exact
  conservation of every resistor's extracted value across the fold, the
  unchanged DRC/LVS verdicts, and a named account of the whitespace that
  remains (inter-cell routing channel + single-row placement).
- `2026-09-two-row-placement/` — issue #177: acting on *that* account. Both
  top-level assemblies were re-placed from one left-to-right row into two
  rows around a shared routing channel, which required replacing the
  disjoint-x-range invariant their inter-cell routing rested on. This entry
  records the resulting footprint move (`bandgap_top` 1.66×,
  `sg13cmos5l_bandgap_top` 1.42×; whitespace 56.6% → 28.1% and 51.6% →
  31.4%), a band-by-band identity for the whitespace that remains, the
  re-derived invariant and how it is machine-checked, the unchanged
  DRC/LVS/extraction evidence — including the byte-identical net sets that
  are the direct proof no riser merged into a neighbour — and the one
  four-net short an intermediate draft produced that `klt drc` called clean.
