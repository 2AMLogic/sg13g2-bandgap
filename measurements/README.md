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
