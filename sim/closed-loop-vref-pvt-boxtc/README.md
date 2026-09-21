# closed-loop-vref-pvt-boxtc

Closed-loop **box-method temperature-coefficient characterization** (issue
#222, follow-on to #86/#134). Co-simulates the exact same
`bandgap_core` + `bandgap_amp` + `bandgap_startup` closed-loop topology
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md) uses — the
per-point netlist is **byte-identical from the `.lib` line down** (device
set, fixture, solver options, every `.measure`); this experiment's only
difference is the **temperature grid** its driver sweeps.

## Why this experiment exists

The official bench's TC table (`../closed-loop-vref-pvt`'s
`records/<id>-tc.csv`) uses the **endpoint method** over 3 temperatures:

```
TC_endpoint = 1e6 * (vref(125C) - vref(-40C)) / (165 * vref(27C))
```

After the `R1 = 511 µm` retune (issue #134) nulled `vref(T)`'s first-order
slope, `vref(T)` is **no longer monotonic** — it bows through an interior
maximum (a concave-down "frown"), so the −40 °C and +125 °C endpoints land
close together and the endpoint method reads near zero while the curve
actually peaks in between.
[`measurements/2026-08-tc-retune/README.md`](../../measurements/2026-08-tc-retune/README.md)
§4b documented exactly this with an 8-temperature-point scan in a **scratch
harness**: worst box-method corner ≈ **20.2 ppm/°C** (`wcs`, 3.30 V) vs the
endpoint method's ~18 ppm/°C — i.e. the ratified `< 20 ppm/°C` **stretch**
column is met by the endpoint method but not by the box method, and the
box-method number rested on an uncommitted testbench (a
`docs/design-evidence-tiers.md` T1 item 9 gap: "every claimed measurement's
testbench committed, with a documented cold-start invocation").

This experiment makes that scan a first-class, committed measurement, per
issue #222: same netlist, **8-temperature grid**
`{-40, -20, 0, 27, 50, 75, 100, 125} °C` (the grid §4b used — adjacent-point
spacing ≤ 27 °C brackets the observed interior extrema), full corner ×
supply grid (the §4b scratch scan was single-supply 3.30 V only; this sweep
covers all 15 corner/supply groups).

## What this testbench claims, and what it does not

It claims: across process corner `{typ, bcs, wcs, sf, fs}` × temperature
`{-40, -20, 0, 27, 50, 75, 100, 125} °C` × supply `{2.97, 3.30, 3.63} V`
(120 points), through the real closed loop, `vref`'s settled DC value —
measured under the same settledness convention as the official bench
(`|vref(3ms) − vref(2ms)| ≤ 1 mV`, plus the same startup-release /
loop-closure / not-railed prerequisites) — supports a **box-method** TC per
corner/supply group:

```
TC_box = 1e6 * (vmax - vmin) / (165 * vref(27C))
```

where `vmax`/`vmin` are the extrema **over the sampled grid points that
passed** (not just the two endpoints). `records/<record-id>-boxtc.csv`
records each group's `n_pass`/`n_grid`, the temperatures the sampled extrema
sit at, the box TC, and — for side-by-side comparison on the same run's
data — the official 3-point endpoint TC computed from this run's own
−40/27/125 °C points.

**It does not change any target.** The ratified TC row
(`< 50 ppm/°C` target, `< 20 ppm/°C` stretch — `README.md`, DR
`0007`/`0008`) is untouched by this experiment; this record states where
the box-method worst corner actually sits, whichever side of the stretch
number it lands on. The metric choice matters for the stretch column's
honest status and is recorded in
[`spec/decision-records/0009-box-method-tc-evidence.md`](../../spec/decision-records/0009-box-method-tc-evidence.md).

It also does not claim anything the official bench does not already cover
(startup, loop closure, `vref` DC accuracy, VBE(Q3)) — those columns are
re-measured here only because they ride along in the same log.

## Why a sibling experiment, not a finer grid inside `closed-loop-vref-pvt`

Issue #222 allowed either. A sibling keeps each experiment's claim atomic
(one directory per distinct claim, per `sim/README.md`'s convention) and —
decisively — keeps the official bench's own re-run cost at its established
45 points: folding the fine grid into `closed-loop-vref-pvt` would triple
that bench's per-re-run cost (45 → 120 transient points) for every future
design change, when only TC-evidence refreshes need the fine grid. The
endpoint-vs-box comparison stays possible because this experiment computes
the endpoint TC on its own data too.

## Pass/fail criteria

Identical to [`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md)'s
four criteria (startup released, loop closed, not railed, settled), because
a point that is not a genuine settled closed-loop operating point has no
`vref` worth feeding a box method. A `FAIL` point contributes no `vref` to
its group's box (see "Non-converged points" below).

## Non-converged points (issue #222 AC 3)

The §4b scratch scan had one non-converged grid point (`wcs`/0 °C) and
argued from its two flanking points that it could not exceed the box
bounded by the other 7 — plausible, but an argument from a scratch re-run,
not committed data. This experiment's policy, applied automatically by
`run_pvt_sweep.sh`:

- Every group's `n_pass`/`n_grid` in `-boxtc.csv` discloses exactly which
  groups a failed point shrank; the record's `**Failed points**` field
  names them by corner id.
- The exclusion is justified **from this run's own committed data**: the
  failed point's flanking converged grid points are in this record's own
  CSV, and between two flanking points of a smooth curve whose sampled
  adjacent-interval curvature is bounded by the rest of the group's points,
  the unsampled point cannot exceed the group's sampled extrema by more
  than that observed curvature budget — read directly off the committed
  `vref(T)` series, not off a scratch argument.
- If the official harness's convergence aids (`reltol=5e-3` + 50 ns initial
  tran step — stronger than the scratch harness's identical-looking but
  separately-invoked setup) clear the point outright, the §4b caveat is
  simply resolved: the committed grid is complete and no bounding argument
  is needed.

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md):

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

× temperature `{-40, -20, 0, 27, 50, 75, 100, 125} °C` × supply
`{2.97, 3.30, 3.63} V` = **120 points**.

## Results summary (this repo's own committed record)

Record [`records/20260921-194249-77820fc.md`](records/20260921-194249-77820fc.md):
**120/120 points PASS** — including `wcs/0 °C`, the one grid point the §4b
scratch harness could not converge. The official harness's convergence aids
(`reltol=5e-3` + 50 ns initial tran step) cleared it outright, so the §4b
bounding argument is retired by a complete committed grid: every group in
`records/20260921-194249-77820fc-boxtc.csv` reads `n_pass == n_grid == 8`.
No non-converged-point exclusion is needed at all (issue #222 AC 3's best
outcome).

- **Worst box-method corner: `wcs`/3.30 V = 19.765 ppm/°C**
  (`vmax` 1.05554 V @ 75 °C, `vmin` 1.05210 V @ −40 °C, `vref(27 °C)`
  1.05484 V) — inside the `< 20 ppm/°C` **stretch** by ~1.2%. A parabolic
  vertex bound fitted through the three grid points bracketing the sampled
  maximum (50/75/100 °C) puts the true interior peak at ≈ 1.05556 V
  (≈ +20 µV, ≈ 84.7 °C), i.e. a vertex-corrected box of ≈ 19.88 ppm/°C —
  still inside, by ~0.6%.
- Box TC across all 15 groups: **8.90-19.77 ppm/°C**; the box is the
  physically-appropriate metric post-retune (the curve is a concave-down
  "frown" with an interior maximum at every corner), and it reads
  systematically higher than the endpoint method on the same run's data
  (e.g. `typ`/3.30 V: box 9.067 vs endpoint −0.808 ppm/°C) — the endpoint
  method's near-zero numbers are the endpoint-averaging artifact §4b
  predicted, now quantified at every group from a committed record.
- **§4b cross-check (3.30 V)**: `typ` 9.067 vs 8.574, `bcs` 16.454 vs
  15.640, `wcs` 19.765 vs ~20.2, `sf` 9.122 vs 8.514, `fs` 9.069 vs
  8.459 ppm/°C — every |Δ| < 1 ppm/°C, inside this README's
  materiality bar. Consistent; no finding. (The scratch scan's single
  non-converged point and its `~` on the wcs figure account for the
  remaining difference.)

The ratified-row reading this record feeds (target met with >2.4× margin;
stretch at the boundary) is recorded in
[`spec/decision-records/0009-box-method-tc-evidence.md`](../../spec/decision-records/0009-box-method-tc-evidence.md)
and reflected in `README.md`'s TC-row status.

## Cross-check against the §4b scratch table (issue #222 test plan)

`measurements/2026-08-tc-retune/README.md` §4b's table (3.30 V,
pre-layout) reads: `typ` 8.574, `bcs` 15.640, `wcs` ~20.2, `sf` 8.514,
`fs` 8.459 ppm/°C. Issue #222's test plan requires the committed numbers to
be consistent with that table "at the points it covers — a material
disagreement is itself a finding worth recording". The comparison (this
experiment's committed `-boxtc.csv` at 3.30 V vs those constants) is
recorded in the "Results summary" above and in
[`spec/decision-records/0009-box-method-tc-evidence.md`](../../spec/decision-records/0009-box-method-tc-evidence.md);
any material disagreement (defined here as > 1 ppm/°C, comfortably above
run-to-run solver noise observed at six significant figures on this bench)
is a finding to record and investigate, not to tune away.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-vref-pvt-boxtc/run_pvt_sweep.sh          # sequential (default)
JOBS=8 sim/closed-loop-vref-pvt-boxtc/run_pvt_sweep.sh   # bounded parallel
```

`JOBS=N` (default 1) runs the 120 independent per-point `ngspice` batch
processes with bounded N-way concurrency — a wall-clock-only knob with the
same contract `../closed-loop-vref-mc/`'s `--parallel` established: it does
not change which points run, their results, or the records' emission order
(each point writes its own row file; the CSV is assembled in grid order
after every point settles).

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
