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
[`spec/decision-records/0010-box-method-tc-evidence.md`](../../spec/decision-records/0010-box-method-tc-evidence.md).

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
`run_pvt_sweep.sh` (removed in #438):

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

## Why the refresh is still outstanding (issue #402, measured 2026-11-13)

The newest committed record below is still the **pre-trim** 2026-09-21 run,
held by the standing #273 evidence-freshness waiver. #402 set out to
discharge it by re-running all 120 points on the batch fleet, with the 15
per-(corner, supply) requests submitted concurrently rather than one
blocking `klt sim` after another (which projected to 7+ h). The concurrent
submission now exists and works — `sim/harness/submission_identity.sh`'s
`si_set_*` helpers hand the whole campaign to one `klt sim --batch-set` —
but the grid still does not complete, for a reason that is **not**
submission serialization:

- **The 100 °C point exceeds the fleet's per-job wall-clock ceiling.** All
  three `typ` requests (2.97 / 3.30 / 3.63 V) came back 7/8, each with its
  100 °C corner graded `error` / `timeout` at the request's
  `options.timeout_s` of 1800 s. Reproducible, same point every time.
- **The point is not non-convergent — it is just slow.** A single-corner
  local debug probe of `typ`/100 °C/2.97 V (one corner is the one thing the
  dispatch hosts may run locally) **passed**, settled, in **3643 s**:
  `vref_3ms = 1.04385 V`, `vref_settle_delta = 0`. ngspice logs
  `singular matrix: check nodes xxtrim.t155 and xxtrim.t241` and recovers
  through dynamic gmin stepping — the 255 interior ladder nodes the #264
  aids-free trim-bearing DUT adds, with `rshunt`/`gmin` deliberately
  dropped. The cost is wall clock, not correctness.
- **3643 s does not fit.** 2am's sim fleet caps a job at
  `BATCH_MAX_JOB_SECONDS=3600`, and `klt sim` requires
  `timeout_s x units + 120 s` to stay under it, so the largest `timeout_s`
  this bench can legally request for a one-corner shard is **3480 s**. The
  axis is already sharded as far as it goes (`remote.hosts: 8` = one fleet
  job per temperature), so the template's usual advice — "raise the shard
  count, not the ceiling" — has no remaining shard to add.

So the grid currently tops out around 105/120, with the missing points
exactly the hot end. That is **not** recorded as a refresh: `vmax` in the
box `(vmax - vmin) / (165 * v27)` sits at 50–75 °C in most groups of the
superseded record, so a box computed without the 100 °C point is a lower
bound on the box, not the box, and would be a weaker claim than the waiver
it replaced. Nothing here is a reason to re-add the convergence aids: #264
dropped them because they cost a measured 37 mV of settled `vref` on this
ladder, which is a wrong answer rather than a slow one.

A separate, smaller finding from the same session, already handled in the
runner's defaults: at 3 requests in flight the campaign's own 24 simultaneous
shard launches ran the shared fleet to 384 vCPU against `BATCH_MAX_VCPU=224`
and lost about half its shards to exhausted capacity waits. 2 requests × 3
shard jobs each (`PEX_BATCH_MAX_IN_FLIGHT` / `KLT_SIM_MAX_CONCURRENT_JOBS`,
now the committed defaults) lost none. Worth knowing before anyone retries
this grid with a bigger number.

Two things would unblock it, neither of them a change to this repo: a
higher per-job ceiling on the sim fleet (a 2am `infra/aws/` change), or a
materially faster hot-corner solve. Until one lands, the #273 waiver stays.
A future attempt should pass `klt sim --fail-fast-probe`, which calibrates
on the first corner and aborts up front, rather than discovering this after
a 1800 s timeout per shard.

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
[`spec/decision-records/0010-box-method-tc-evidence.md`](../../spec/decision-records/0010-box-method-tc-evidence.md)
and reflected in `README.md`'s TC-row status.

## Cross-check against the §4b scratch table (issue #222 test plan)

`measurements/2026-08-tc-retune/README.md` §4b's table (3.30 V,
pre-layout) reads: `typ` 8.574, `bcs` 15.640, `wcs` ~20.2, `sf` 8.514,
`fs` 8.459 ppm/°C. Issue #222's test plan requires the committed numbers to
be consistent with that table "at the points it covers — a material
disagreement is itself a finding worth recording". The comparison (this
experiment's committed `-boxtc.csv` at 3.30 V vs those constants) is
recorded in the "Results summary" above and in
[`spec/decision-records/0010-box-method-tc-evidence.md`](../../spec/decision-records/0010-box-method-tc-evidence.md);
any material disagreement (defined here as > 1 ppm/°C, comfortably above
run-to-run solver noise observed at six significant figures on this bench)
is a finding to record and investigate, not to tune away.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                                      # one-time: build the OSDI models
sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --sanity       # one local corner, vs the sanity anchor
sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --batch        # the 120-point grid, on the fleet (resumable)
sim/closed-loop-vref-pvt-boxtc/run_klt_sim.sh --record       # mint the record from the merged report
```

The grid runs through the `klt sim` batch harness (`sim/harness/README.md`,
the #275 decision), not the `run_pvt_sweep.sh` shell loop that minted the
2026-09-21 record — that script was removed in #438 and is recoverable from
git history only. Its `JOBS=N` wall-clock knob went with it: the 120 points
are no longer `ngspice` processes on the invoking host at all, so there is
nothing local to fan out. The fleet-side equivalents are the request's
`remote.hosts` (8 — one fleet job per temperature point) and
`PEX_BATCH_MAX_IN_FLIGHT` / `KLT_SIM_MAX_CONCURRENT_JOBS` (how many of the
15 requests, and how many of each request's 8 shard jobs, are in flight at
once). Like `JOBS`, none of them changes which points run or what they
measure — they trade wall clock against the fleet's shared vCPU budget, and
overshooting it loses shards rather than finishing sooner (see "Why the
refresh is still outstanding" above). The runner defaults them to the pair
measured to lose no shards, **2** requests × **3** shard jobs; both are
overridable, but the fleet is shared and 3 × 8 = 24 simultaneous jobs
already overran it.

`--batch` is resumable in two independent senses: a shard whose committed
submission identity still matches its inputs is not re-submitted
(`sim/harness/submission_identity.py`, #332), and `KLT_SIM_SET_RESUME=1`
re-attaches each in-flight request to the fleet jobs its previous run
recorded instead of relaunching them. Point `KLT_SIM_WORK` at the same
directory to pick a campaign back up.

See `sim/README.md` for the append-only `records/` convention every
experiment in this tree follows; since #379 (DR-0015) a new run's raw logs
and per-point netlist snapshots live in the fleet artifact store under a
committed `manifests/artifacts/` manifest rather than in committed
`corners/` / `netlist-snapshots/` directories.
