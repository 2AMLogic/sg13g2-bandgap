# startup-time-to-release

A direct follow-up to [`../closed-loop-startup/`](../closed-loop-startup/README.md),
filed against issue #4's T1 checklist item 5 ("Full PVT corner simulation vs
a ratified spec"). PR #128's EE-key review (the still-open spec-ratification
PR, #125) found that while `closed-loop-startup`, `closed-loop-vref-pvt` and
`closed-loop-iq` all prove the assembled block self-starts and settles across
the full PVT grid, **no committed testbench in this tree reports an explicit
time-to-release figure** to compare directly against the draft
"Startup: self-starting, < 1 ms" spec row (`spec/porting-plan.md` §6, still
unratified — #125) — every prior testbench only checks the release criteria
at one or two fixed checkpoints (`t=20us`/`t=2ms`), never asks "how fast".
This experiment is that missing measurement.

## What this testbench claims, and what it does not

It claims: co-simulating `design/bandgap_core.sch` + `design/bandgap_amp.sch`
+ `design/bandgap_startup.sch` in one netlist (the identical DUT/fixture set
[`../closed-loop-startup/`](../closed-loop-startup/README.md) uses — see that
README for the full device inventory, not repeated here), sampled at a fixed
100us-resolution checkpoint ladder from `t=100us` to `t=1ms` (plus a coarser
`t=2ms` cross-check point), the earliest time at which the full closed-loop
release criteria (see "Pass/fail criteria" below) hold *and keep holding*
through the end of the simulated window, across the full temperature x
supply x HBT/MOS/resistor-process-corner PVT grid.

It does **not** claim conformance to the draft `< 1 ms` spec row — that row
is not ratified (#125), and per `CLAUDE.md`/`spec/README.md` this repo does
not compare evidence against an unratified number as if it were a pass/fail
gate. It reports the measured `release_time_us` per corner as data; anyone
evaluating it against the draft target (or the eventual ratified one) does
so downstream of this record, not inside it. It also inherits every scope
limit `closed-loop-startup` already documents (no AC/stability claim, no
Monte Carlo/mismatch claim, no PSRR/accuracy/Iq claim).

## Why fixed-time checkpoints, not a `WHEN`/crossing-search `.measure`

The obvious first design was a single `meas tran t_release WHEN v(det)=<thresh>
FALL=1` (find the time `det` falls through the release threshold). **Tried
first, and rejected — confirmed by direct test, not assumed**: at several PVT
corners, most visibly the design's own `typ`/27C/3.30V nominal point, `det`
and `i(XMKFB)` never rise above their release thresholds *at all* during the
`vdd` ramp (`det` peaks at ~0.48 V against the 0.66 V threshold at that
corner; `i(XMKFB)` peaks at ~4.3 nA against the 50 nA threshold — both well
inside the "already released" region for the entire simulated window). A
`FALL=1` search finds no crossing to report and fails with `measure ...
when(WHEN) : out of interval`; under `set -euo pipefail`-hardened error
handling that is recoverable per-point, but it means "released essentially
immediately" and "the testbench is broken" are indistinguishable from a bare
crossing-search failure alone. Fixed-time `AT=` sampling (`meas tran x find
v(y) at=<t>`, the same form every other testbench in this tree already uses
for its early/final checkpoints) has no such failure mode — it always
succeeds unless the transient itself did not converge that far — so this
testbench's `.control` block samples a ladder of `AT=` points instead. See
`testbench/tb_startup_time_to_release.spice.tmpl`'s own header for the same
account.

**Practical consequence**: resolution is bucketed to the ladder's own 100us
step below 1ms, not an exact crossing instant. A reported `release_time_us`
of e.g. `100` means "already released by the first checkpoint, and stayed
released" — it does not mean release happened at exactly `t=100us`; it could
have been anywhere in `[0, 100us]` (or earlier still, during the `vdd` ramp
itself, which runs `0->200us`). This is a real, disclosed resolution limit,
not a hidden one — every citation of this experiment's numbers should carry
this caveat.

## `release_time_us` definition — a suffix-of-PASS rule, not "first PASS anywhere"

Each checkpoint (`100u, 200u, ..., 1000u, 2000u`) gets its own
`pvt_closed_loop_verdict()` evaluation (the same three-criteria check
`../closed-loop-startup/` uses, from `sim/lib/pvt_verdict_common.sh`) —
startup released, loop closed, not railed. `release_time_us` is the
**earliest checkpoint such that it and every later checkpoint through
`2000u` all PASS** — not merely the first checkpoint that happens to PASS.
This guards against misreporting a corner that transiently satisfies the
release criteria (e.g. a brief overshoot through the threshold band during
loop settling) and then regresses before genuinely settling. A corner whose
release criteria never reach that stable suffix within the 2ms simulated
window reports `NOT_RELEASED` and fails the point outright — same
`ngspice` non-convergence / model-load-error / missing-measurement failure
modes every other testbench in this tree uses, plus this one.

## Pass/fail criteria

A point is `PASS` only if `release_time_us` is found (a real value on the
checkpoint ladder, per the suffix-of-PASS rule above) within the 2ms
simulated window. The per-checkpoint release criteria are identical to
[`../closed-loop-startup/README.md`](../closed-loop-startup/README.md)'s own
"Pass/fail criteria" section (`v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA`;
`|sns1-sns2| <= 20 mV`; `fb` at least `0.05 V` from either rail) — not
repeated here.

## Corner coverage

Identical grid to every other closed-loop experiment in this tree: process
corner `{typ, bcs, wcs, sf, fs}` (HBT x MOS-hv x resistor sections) x
temperature `{-40, 27, 125} °C` x supply `{2.97, 3.30, 3.63} V` = 45 points.
See [`../closed-loop-startup/README.md`](../closed-loop-startup/README.md)'s
own corner-label table for the section pairing, not repeated here.

## CSV columns

`records/<record-id>.csv` adds two columns beyond the usual
corner/PDK-section/temp/vdd/status set: `release_time_us` (this experiment's
own headline number, or `NOT_RELEASED`) and `checkpoint_verdicts` (a
semicolon-joined `<time>u:<PASS|FAIL|MISSING>` list across the full ladder,
so a reader can see the full trajectory, not just the final answer — e.g.
confirm a `PASS` point genuinely holds from its reported `release_time_us`
onward, or see exactly where a `NOT_RELEASED` point's criteria keep failing).
`det_2000u_v`/`i_mkfb_2000u_a`/`fb_2000u_v`/`dvsns_2000u_v` restate the final
(`t=2ms`) checkpoint's raw values, for direct cross-validation against
[`../closed-loop-startup/`](../closed-loop-startup/README.md)'s own
independently-committed `t=2ms` record (same DUT, same fixture, same
corner — the two experiments should agree to solver-noise precision; a
divergence would mean one of the two testbenches has a bug worth chasing).

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/startup-time-to-release/run_pvt_sweep.sh
```

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
