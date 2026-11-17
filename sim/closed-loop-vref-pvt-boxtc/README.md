# closed-loop-vref-pvt-boxtc

Closed-loop **box-method temperature-coefficient characterization** (issue
#222, follow-on to #86/#134). Co-simulates the exact same
`bandgap_core` + `bandgap_amp` + `bandgap_startup` closed-loop topology
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md) uses — the
per-point netlist is **byte-identical from the `.lib` line down** (device
set, fixture, every `.measure`) except the direct linear solver: this bench
pins `klu`, a deliberate, measured answer-preserving departure (issue #469,
[Hot-corner solve time](#hot-corner-solve-time-issue-469-measured-2026-11-14)).
This experiment's other difference is the **temperature grid** its driver
sweeps.

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

## Trim-bearing DUT refresh (issue #402)

**DUT.** The core netlist this bench inlines device-for-device is
#229's trim-bearing `design/netlist/bandgap_core.spice`, ladder pinned at
code **128** — the same DUT every #264 refresh adopted (see
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md)'s refresh
section for the ladder's device-for-device description). The template has
carried that core since the #273 `klt sim` conversion (PR #398); what this
bench was missing was the **record** — until now, the newest committed
record below was still the pre-trim 2026-09-21 run, held by the standing
#273 evidence-freshness waiver.

**Solver options.** Aids-free (`rshunt`/`gmin` dropped, `reltol=5e-3` +
`tran 50n` kept) like every #264 bench, plus this bench's own `klu` direct
linear solver — #469's measured answer-preserving departure, 17× on the hot
corner (see [Hot-corner solve time](#hot-corner-solve-time-issue-469-measured-2026-11-14)
below).

**Result** (record
[`records/20261116-024010-dc056b4c.md`](records/20261116-024010-dc056b4c.md),
120/120 points PASS, 120 fleet jobs listed in the run's
`environment.remote`):

| quantity | pre-trim (`20260921-194249-77820fc`) | trim-bearing, code 128, aids-free + KLU (`20261116-024010-dc056b4c`) |
|---|---|---|
| `vref_3ms_v` @ `typ`/27 °C/3.30 V | 1.04947 V | **1.04728 V** (−2.19 mV, −0.21%) |
| box TC, worst group | `wcs`/3.30 V = 19.77 ppm/°C | **`bcs`/3.63 V = 38.62 ppm/°C** |
| box TC, 15-group range | 8.90–19.77 ppm/°C | 20.20–38.62 ppm/°C |
| endpoint TC, 15-group range | −14.4 … +18.1 ppm/°C | **−37.3 … −14.1 ppm/°C** |
| box extrema positions | `vmin` @ 125 °C in 14/15 groups (`wcs` at −40 °C), `vmax` @ 0–75 °C | `vmin` @ 125 °C in all 15 groups; `vmax` @ 0 °C (`typ`/`sf`/`fs`), −20 °C (`bcs`), 27 °C (`wcs`) |
| points PASS | 120/120 | 120/120 |

The −2.19 mV nominal move is the same delta, to the digit, that the #264
twin measured on the identical DUT swap. The TC rows move by more, and that
is expected, not a regression: **read them as the trim-bearing aids-free
DUT's own numbers, with the disposition attached elsewhere.** The endpoint
range −37.3 … −14.1 ppm/°C is the twin refresh's endpoint range repeated —
two separately-written benches agreeing — and the 20.20–38.62 ppm/°C box
range sits inside
[`../closed-loop-vref-boxtc-trim/`](../closed-loop-vref-boxtc-trim/README.md)'s
independent 20.2–45.7 ppm/°C box-method band for the same core. The
ratified `< 20 ppm/°C` stretch is not met by the box method on this DUT;
that disposition is **#269's** (the ratified box-TC row's evidence lives in
`../closed-loop-vref-boxtc-trim/`), and nothing in `spec/` is edited here.
The "Results summary" and "§4b cross-check" sections below read the
superseded pre-trim record and are left standing as that record's reading
(`sim/` evidence is append-only); their §4b agreement statements apply to
the pre-trim DUT the §4b scratch scan also ran.

**Batch path used** (disclosure): `run_klt_sim.sh --batch` handed all 15
per-(corner, supply) requests to **one** `klt sim --batch-set` (in-flight
2, 3 shard jobs per request, `--wait-for-capacity 600` — the committed
defaults), which ran **120 spot fleet jobs** (c7i/m7i/m6i.4xlarge,
`runner_compatibility: match`, runner klt 0.9.0 vs client 0.9.3.dev16) to
completion in a **62-minute** wall clock, individual jobs 79–120 s — every
100 °C point completed inside a fleet job whose `elapsed_seconds` is in the
committed 79–120 s set (all 120 jobs `exit_code: 0`; the fleet entries carry
no corner label, so no finer per-point timing is reconstructible from the
record), against the 3643 s the pre-KLU hot corner needed. The fleet
runner's ngspice is KLU-capable and **engaged
KLU on every corner**: all **120/120** harvested corner logs carry ngspice's
`Using KLU as Direct Linear Solver` line, and the runner environment
capture reads `ngspice-47 … Compiled with KLU Direct Linear Solver`. The
`#273` freshness waiver for the 2026-09-21 record is deleted.

## Why the 2026-11-13 refresh attempt topped out (superseded history)

The refresh above landed; this section is the measured history of the one
attempt that did not, kept because the "Hot-corner solve time" section
below quotes its row 0. On 2026-11-13, with the concurrent submission in
place but before #469's KLU adoption, all three `typ` requests came back
7/8 with their 100 °C corner graded `error`/`timeout` at the request's
`options.timeout_s` of 1800 s — reproducibly, the same point every time. A
single-corner local debug probe of `typ`/100 °C/2.97 V **passed** and
settled in **3643 s** (`vref_3ms = 1.04385 V`, settle delta 0): ngspice
logs `singular matrix` on the 255 interior ladder nodes and recovers
through dynamic gmin stepping — slow, not wrong. But 3643 s does not fit a
fleet job (`BATCH_MAX_JOB_SECONDS=3600`, so the largest legal one-corner
`timeout_s` is 3480 s), and the axis was already sharded as far as it goes
(`remote.hosts: 8` = one fleet job per temperature), so the grid topped out
around 105/120 with exactly the hot end missing. That was **not** recorded:
`vmax` sits at 50–75 °C in most groups of the pre-trim record, so a box
computed without the 100 °C point is a lower bound on the box, not the box
— a weaker claim than the waiver it would have replaced.

The same session also measured the campaign's own fleet overrun: at 3
requests in flight the 24 simultaneous shard launches took the shared fleet
to 384 vCPU against `BATCH_MAX_VCPU=224` and lost about half its shards to
exhausted capacity waits; the committed defaults (2 requests × 3 shard
jobs) lost none — see [Running](#running) below. #469's KLU adoption (17×
on the hot corner) is what made the refresh above possible. Nothing here is
a reason to re-add the convergence aids: #264 dropped them for a measured
37 mV settled-`vref` error on this ladder, which is a wrong answer rather
than a slow one.

## Hot-corner solve time (issue #469, measured 2026-11-14)

The 100 °C point is slow, not non-convergent, and the cost is wall clock in
the transient — so the fix attempted here was on the solver-options side
only. All probes below are one-corner local runs of typ / 100 °C / 2.97 V
through the committed templates (scratch `klt sim` request, `--timeout-s
5400` override, `/usr/bin/time -v` wall clock), on a dispatch host with
ngspice 47 (compiled with KLU) and klt 0.9.2.dev1029; row 0 is the 2026-11-13
probe recorded above, re-quoted for comparison. No convergence aid
(`rshunt`/`gmin`) was touched and `reltol` stayed at `5e-3` throughout.

**Where the time goes (split probe).** Re-running the same corner with the
transient truncated to the supply ramp (`50n 200u`, row 1) took **325 s** of
the 3643 s total: roughly 91% of the wall clock sits in the post-ramp
settled transient (200 µs → 3 ms), and the cost scales with simulated time
rather than being concentrated in one stiff event. That rules out the
operating-point/`.nodeset` family up front (the t=0 solve is the all-zero
rails solution the PWL ramp intends, and the ramp itself is cheap), and
points every candidate at the per-timestep solve.

| # | setting | tran window | wall (s) | `vref_3ms` (V) | settle Δ (V) | verdict |
|---|---------|-------------|---------:|----------------|--------------|---------|
| 0 | baseline — ngspice default solver (SPARSE 1.3), 2026-11-13 probe | `50n 3m` | 3643 | 1.04385 | 0 | incumbent: exceeds the 3480 s largest legal one-corner `timeout_s` |
| 1 | split probe — same options, truncated window | `50n 200u` | 325 | n/a | n/a | timing probe only (klt grades it `error` because the `at=2m/3m` measurements fall outside the truncated window — expected, see above) |
| 2 | `.options … klu` — KLU direct linear solver | `50n 3m` | **211** | 1.04385 | 0 | **adopted**: 17× vs baseline, answer identical at 6 significant figures |

**Why KLU is the adopted candidate.** It is answer-preserving by
construction — same equations, same tolerances, a different direct
factorization of the same matrix (ngspice 47 ships compiled with KLU; the
default is SPARSE 1.3, which is what every committed log of this bench
shows). The measurement confirms it: `vref_3ms` is identical to the
baseline to the reported precision (1.04385 V), `vref_settle_delta = 0`,
and the corner grades `pass`. The remaining candidates from the issue's
ranked list were not spent: they are accuracy knobs (`trtol`, `method=gear`) or a weaker
version of the same lever (`tran` initial step / `tmax`), and none can beat
a 17× answer-preserving win for the purpose #402 needs. The
`singular matrix` recovery this corner is known for still occurs under KLU
(check node `xxtrim.t251`) and recovers as before; under klt 0.9.2 grading
it is recorded as a `warning`-severity diagnostic and the corner still
grades `pass`.

**What landed.** `.options … klu` on both decks —
`testbench/closed_loop_vref_pvt_boxtc.body.spice.tmpl` (the `klt sim`
bench) and `testbench/tb_closed_loop_vref_boxtc.spice.tmpl` (the
point-definition reference, kept in step) — plus a measured-timing note in
the request template's `_comment` block. Both acceptance bands were
checked on the edited templates:

- hot corner (row 2): `vref_3ms = 1.04385 V`, within 0.0005 V of the
  committed SPARSE answer, settle delta 0, 211 s < 3480 s;
- reference corner (`run_klt_sim.sh --sanity`, typ / 27 °C / 3.30 V):
  `sanity vref_3ms_v = 1.04728 (anchor 1.04728, delta 0) ok` — sanity gate
  PASS, 161 s.

`timeout_s: 1800` in the request template now covers the whole grid
including the 100 °C points (211 s ≪ 1800 s), so #402 needs **no**
`timeout_s` raise to complete the refresh — only the re-run itself. One
precondition for that re-run: the fleet runner's ngspice must also be
KLU-capable (the measurement above pins only this host's ngspice 47; the
committed 2026-09-21 logs show SPARSE 1.3 but no version banner). If it is
not, the option is ignored and the 100 °C points time out exactly as
before — `klt sim --fail-fast-probe` (already recommended above) surfaces
that on the first corner instead of after a shard campaign.

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
overshooting it loses shards rather than finishing sooner (see the
superseded-history section above). The runner defaults them to the pair
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
