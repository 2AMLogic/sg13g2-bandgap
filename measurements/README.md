# measurements

Supplementary quantitative analysis that doesn't fit `sim/`'s per-experiment
append-only evidence convention (multi-run comparisons, design-space
searches, dominant-error-regime writeups) — see the repo README for scope.

- `lib/` — shared helper code for the dated reports, the `measurements`
  analogue of `sim/lib/` (#484). Currently `spotcheck_common.py`: the
  re-derivation bodies (CSV readers plus one printing function per spec
  area) that each characterization report's `spotcheck.py` used to carry
  as a ~201-line copy. A report's script pins its own record paths and
  calls into the module, so a rotation changes two paths instead of
  copying 201 lines; like `spotcheck.py` itself it is a companion script,
  not one of the hashed report artifacts.
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
- `2026-09-characterization-report/` — **superseded by `2026-10-characterization-report/`**, itself superseded by `2026-11-characterization-report/` (below; kept untouched as history). Issue #15 (T1 checklist item 8): the
  aggregated per-spec-row characterization report #5's verdict table marked
  missing. One honest verdict per ratified spec row (Output reference
  unmet-and-unsettled per the two-key outcome, re-opened as #221; TC, PSRR
  @ DC, Supply, Iq, Startup met with their caveats carried), each citing
  its specific committed `sim/` evidence record — all nine citations
  re-verified most-current at `main`@`77820fc` — with headline numbers
  re-derived from the records' own CSVs.
- `2026-10-characterization-report/` — **superseded by `2026-11-characterization-report/`** (below; kept untouched as history). Issue #300 (T1 checklist item 8): the
  aggregated characterization report, replacing the September one.
  One entry per row of the spec table as it stands at the audited commit
  `b89f4c5f` (seven rows; Output reference reported as its nominal,
  untrimmed and trimmed lines), each with bound, verdict, binding corner,
  statistical or not, the newest committed `sim/` record behind it, and
  whether that record was taken on the trim-bearing netlist or "predates the
  current netlist" (four waived records, #273/#275). Every quoted number is
  re-derived from its CSV by `spotcheck.py`, with no new simulation. The
  trimmed +/-0.5% line is reported as measured unmet and its redesign
  (#303) as unsettled. `envelope.json` is the `generic` evidence envelope
  `manifests/sg13g2-bandgap.json` cites for item 8, pinned to the report's
  sha256. `dependencies.json` (#315) is the report's audited dependency
  inventory (DUT netlist hashes, spec-table row digests, decision-record
  statuses, selected records and stale-evidence disclosures); CI's
  `check_report_dependencies.py` fails when any of them moves, and the
  remedy is a new dated report, not an edit to this one. See
  `manifests/README.md` → "Item-8 dependency drift".

- `2026-11-characterization-report/` — **superseded by `2026-11-04-characterization-report/`** (below; kept untouched as history). Issue #427 (T1 checklist item 8): the
  aggregated characterization report, replacing the October one. The
  October report was superseded when the `klt sim` re-mints of
  `sim/trim-coverage` (`20261030-061206-03e62489`) and
  `sim/closed-loop-vref-trim-mc` (`20261030-070305-03e62489`, fleet-run,
  `klt 0.8.0`) became each experiment's newest record (#422/#425 deferred the
  re-mint to this report). Stamped at audited commit `03e62489`; the trim
  range/resolution figures are unchanged and the trimmed +/-0.5% line is
  still measured unmet (3 sigma about 2.4% vs 2.6% in October). Same shape as
  the October report: `README.md`, `spotcheck.py`, `envelope.json`
  (cited by `manifests/sg13g2-bandgap.json` for item 8) and
  `dependencies.json` (#315).

- `2026-11-04-characterization-report/` — **superseded by
  `2026-11-13-characterization-report/`** (below; kept untouched as history).
  Issue #403 (T1 checklist item 8): replaced the earlier November
  one. It was superseded when the `klt sim` re-mint of
  `sim/closed-loop-vref-mc` (`20261104-201955-2a0f04d7`, trim-bearing core at
  code 128) became that experiment's newest record and the #273 waiver for the
  pre-trim record was deleted. Stamped at audited commit `2a0f04d7`; the
  untrimmed +/-16% line is still met (worst-case total 15.31%, binding corner
  now wcs/125 C). Same shape as the earlier reports: `README.md`,
  `spotcheck.py`, `envelope.json` (cited by `manifests/sg13g2-bandgap.json` for
  item 8) and `dependencies.json` (#315).

- `2026-11-13-characterization-report/` — **superseded by
  `2026-11-16-characterization-report/`** (below; kept untouched as history).
  Issue #415 (T1 checklist item 8): replaced the 4 Nov one. It
  rotated because the `klt sim` batch re-mint of the schematic PSRR grid
  (`sim/closed-loop-psrr/records/20261113-085406-9d568b91`, 45 points in 15
  fleet jobs) became that experiment's newest record. Stamped at audited
  commit `9d568b91`. **No verdict or quoted number changed**: the new grid
  reproduces the 2026-10-01 local sweep it replaces figure-for-figure (same
  45/45 PASS, same 59.685..100.400 dB range, same worst point 59.6849 dB at
  bcs/125 C/3.63 V, agreeing to within 6e-6 relative on every PSRR column), so
  `spotcheck.py`'s output is byte-identical to the 4 Nov report's. Same shape
  as the earlier reports: `README.md`, `spotcheck.py`, `envelope.json` (cited
  by `manifests/sg13g2-bandgap.json` for item 8) and `dependencies.json`
  (#315).

- `2026-11-16-characterization-report/` — **superseded by
  `2026-11-18-characterization-report/`** (below; kept untouched as history).
  Issue #402 (T1 checklist item 8): replaced the 13 Nov one. It
  rotated because the trim-bearing 120-point box-method TC grid
  (`sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c`, one
  `klt sim --batch-set`, 120 fleet jobs, 62 min) became that experiment's
  newest record and its pre-trim #273 waiver was deleted. Stamped at audited
  commit `00acddae`. **Unlike the previous two rotations this one is not
  provenance-only**: the DUT behind the moved record changed (pre-trim core →
  trim-bearing at code 128, aids-free + KLU), so the bench's quoted TC
  numbers move (box 8.90–19.77 → 20.20–38.62 ppm/°C; endpoint
  −14.4…+18.1 → −37.3…−14.1 ppm/°C) while the Temp coefficient verdict does
  not (target met, stretch not met; disposition stays with #269's
  `sim/closed-loop-vref-boxtc-trim`). Same shape as the earlier reports:
  `README.md`, `spotcheck.py`, `envelope.json` (cited by
  `manifests/sg13g2-bandgap.json` for item 8) and `dependencies.json`
  (#315).

- `2026-11-18-characterization-report/` — **superseded by
  `2026-11-18-klu-retime-characterization-report/`** (below; kept untouched
  as history). Issue #557 (T1 checklist item 8): replaced the 16 Nov one.
  It rotated because that branch's Via1 containment fix re-minted the
  layout evidence (GDS, DRC/LVS/PEX under `klt 0.9.3.dev663`), moving both
  audited PEX DUT inputs (`bandgap_top.pex.spice`,
  `bandgap_startup.pex.spice`). Stamped at audited commit `11a18b96`. **No
  `sim/` record moved and no simulation was run**: the three post-layout
  benches (PSRR-PEX, Zout-PEX, startup trip-point) are disclosed as
  predating the current extraction, and the PSRR @ DC row's verdict moves
  with them — met with caveats becomes **not met on current evidence** (the
  only record that cleared 60 dB, post-layout 45/45 at 0.0013 dB margin,
  predates the re-extraction; the current schematic grid reads 59.685 dB at
  its worst corner). The re-run one-point core PEX probe reproduces its
  recorded point exactly (vref 1.052999 V, ratio 12.630). Same shape as the
  earlier reports: `README.md`, `spotcheck.py`, `envelope.json` (cited by
  `manifests/sg13g2-bandgap.json` for item 8) and `dependencies.json`
  (#315).

- `2026-11-18-klu-retime-characterization-report/` — issue #518 (T1
  checklist item 8): the current aggregated characterization report,
  replacing the 18 Nov one. The name carries a `klu-retime` suffix because
  the same-day `2026-11-18-` slot is taken by the #557 report it supersedes
  (byte-identical history). It rotated because issue #518's KLU
  direct-solver adoption on the two supply benches re-minted their 45-point
  grids (`sim/closed-loop-iq/records/20261118-072122-3e600d97`,
  `sim/closed-loop-startup/records/20261118-082945-3e600d97`), making them
  those experiments' newest records. Stamped at audited commit `73c420a2`.
  **Provenance-only, like the 13 Nov rotation**: the Iq grid reproduces its
  predecessor figure-for-figure (recomputed from both CSVs, maximum
  shared-column relative delta 0) and the startup grid's claims are
  unchanged (45/45 self-start; node round-off within the `reltol=5e-3`
  solver swap), so no verdict and no quoted number move and the spot-check
  block is byte-identical to the 18 Nov report's. Same shape as the earlier
  reports: `README.md`, `spotcheck.py`, `envelope.json` (cited by
  `manifests/sg13g2-bandgap.json` for item 8) and `dependencies.json`
  (#315).
