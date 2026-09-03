# startup-core-handover

Co-simulates `design/bandgap_core.sch` + `design/bandgap_startup.sch`
(`design/netlist/bandgap_core.spice` + `design/netlist/bandgap_startup.spice`)
in **one netlist**, with a **transient** `vdd` ramp, so the assembled
block's cold-start -> running-core hand-over is what ngspice actually
solves for -- not inferred by comparing two separate open-loop DC benches
(`sim/core-open-loop-bias/` and `sim/startup-trip-point/`), the way
`sim/startup-trip-point/README.md`'s "Cross-bench observation" originally
did. Built for issue #24; see
[`spec/decision-records/0003-startup-sense-nmos-resize.md`](../../spec/decision-records/0003-startup-sense-nmos-resize.md)
for the design decision this experiment's evidence drove.

## What this testbench claims, and what it does not

`bandgap_core`'s `sns1` and `fb` pins are wired directly to
`bandgap_startup`'s own `sns1` and `fb` pins -- the two nodes the assembled
block actually shares. No external source sweeps or forces either one
(unlike `sim/startup-trip-point`'s `Vsns1`, which sweeps `sns1` externally
to trace out a trip point in isolation). Instead, `vdd` itself ramps from
0 V to the corner's supply over 200 µs and holds to 2 ms, and the whole
circuit -- both DUTs plus the same open-loop mirror-bias fixture
`sim/core-open-loop-bias` uses -- is solved as one coupled transient. This
checks directly: does `XMKFB` (the startup kick's pull-down on the shared
mirror gate `fb`) fully release once the core has ramped up and settled,
at every PVT point?

It does **not** claim anything about the assembled block's actual
closed-loop startup time or transient shape once the (not yet built) error
amplifier exists -- see "Important caveat" below for why this fixture is a
pessimistic bound, not a tight prediction, of that future behavior. It is
also still, in the same sense every experiment in this tree is,
infrastructure/plumbing evidence rather than a claim against a ratified
spec row: nothing under `spec/porting-plan.md` §6 is ratified yet (#125).

## Fixtures (not device substitutions)

- **`Vvdd`** -- a `PWL(0 0 200u <VDD> 2m <VDD>)` transient ramp, the piece
  neither `sim/core-open-loop-bias` nor `sim/startup-trip-point` has (both
  use a plain `dc` source for `vdd`). 200 µs is comfortably above the
  ~2 µs RC set by `XRPU`'s ~1.9-2 MΩ `rhigh` against MOSFET gate
  capacitance (see `design/bandgap_startup.sch`'s header for `XRPU`'s R
  derivation), so the ramp itself does not artificially slow-walk the
  circuit's own response.
- **`XM0`/`Ibias`** -- the identical open-loop mirror-bias fixture
  `sim/core-open-loop-bias` uses: a diode-connected replica of the mirror
  device (`sg13_hv_pmos`, `w=10u l=1u`) carrying a 5 µA reference, standing
  in for the error amplifier's eventual job of holding `fb` at whatever
  level gives the design current (no amplifier exists yet -- issue #9's
  scope cut). This is a testbench fixture, not a DUT substitution.
- **`Vmkfb`** -- a 0 V ammeter in series with `XMKFB`'s drain, connecting it
  to the shared `fb` node through its own `fbx` node. A 0 V source is a
  DC/transient short and does not move the operating point; it exists so
  the startup circuit's own current contribution to `fb` can be measured
  directly (`i_mkfb_v` in the records) instead of inferred from voltage
  alone.
- **`Vsub`** -- ties the global substrate net `sub!` to `vss` through a
  0 V source, the same convention every other testbench in this tree uses.

## IMPORTANT CAVEAT: this fixture is a pessimistic bound, not a tight prediction

An ideal current source (`Ibias`) is a very high output impedance load at
`fb`. A real error amplifier is normally a *low* output impedance driver of
`fb` -- that is what "amplifier" means here. Any residual current `XMKFB`
pulls out of `fb` while incompletely released therefore moves `fb` (and so
the mirror current, and so `sns1`, through the same self-reinforcing loop
this experiment's own data exhibits -- see "What the first co-simulation
run found" below) far more against this fixture's near-infinite source
impedance than it would against a real amplifier's low output impedance.

This does not make the finding wrong: the fixture is the same one
`sim/core-open-loop-bias`'s own claims already rest on, and it is a
physically real circuit, not an approximation of one -- ngspice solves the
real coupled dynamics of exactly the devices present. What it means is:
read this experiment's specific current/voltage numbers (e.g. "17.4 µA of
residual `XMKFB` current at the worst pre-fix point") as a worst-case bound
on how bad an incomplete release could look, not as a prediction of what
the assembled block with its future amplifier will actually show. The
qualitative direction -- does `XMKFB` release or not -- is exactly what
this experiment settles; the quantitative severity of a *failing* point is
likely overstated relative to the real closed loop.

## What the first co-simulation run found (pre-fix, `XMSENSE w=2u`)

Run against the original `design/bandgap_startup.sch` sizing (before
issue #24's fix), record `20260821-144158-6cc16d3`: **12 of 45 points**
fail full hand-over at 125 °C, spanning every process corner at that
temperature (`typ`, `bcs`, `wcs`, `sf`, `fs` -- not just the four points
`sim/startup-trip-point`'s cross-bench comparison originally flagged). At
the worst point (`wcs_125c_3.63v`), `v(det)` settles at 0.887 V (vs. a
`vdd/2` release threshold of 1.815 V -- nowhere close) and `XMKFB` still
sinks 17.4 µA at `t=2ms`, checked stable out to `t=10ms` (not a slow
transient still settling). `sns1` itself settles at 0.645 V, well above
the core-only (no startup circuit) value of 0.591 V at that corner
(`sim/core-open-loop-bias`'s own record) -- direct confirmation of the
self-reinforcing mechanism described in the caveat above: `XMKFB`'s
residual pull-down forces extra mirror current, which raises `sns1` via
`VBE = Vt*ln(I/Is)`, which is not enough excess drive to fully trip the
sense stage, so the loop settles at a stable partial-release point rather
than either extreme.

This is a **stronger** finding than the cross-bench comparison suggested
(2-10 mV of margin deficit at four points), not a weaker one: co-simulating
the real feedback path the two-separate-DC-benches comparison could not see
shows the practical consequence is much larger than the raw voltage gap
implied, because the deficit is self-reinforcing once the loop is closed.

## What the second co-simulation run found (post-fix, `XMSENSE w=10u`)

Run against the resized `design/bandgap_startup.sch` (see
[decision record 0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md)),
record `20260821-144329-60f50a7`: **45 of 45 points** PASS. At the same
previously-worst point (`wcs_125c_3.63v`), `XMKFB`'s residual current drops
to 3.7e-10 A (from 1.74e-05 A) and `sns1` recovers to 0.591085 V, within
0.1 mV of the core-only value. Every other previously-failing point shows
the same pattern: `XMKFB` current at or below the low-nA range, `sns1`
matching its core-only counterpart closely.

## Pass/fail criteria

A point is `PASS` only if, at the end of the transient (`t=2ms`, fully
ramped and settled):

1. `v(det) <= 0.2*vdd` -- the same "released" threshold
   `sim/startup-trip-point` uses.
2. `|i(XMKFB)| <= 50 nA` -- 1% of the 5 µA/leg open-loop design current.
   This is the more load-bearing of the two criteria: `v(det)` alone can
   look superficially released while `XMKFB` is still contributing a
   current large enough to meaningfully perturb the shared mirror. See the
   pre-fix `bcs_125c_3.63v` point in record `20260821-144158-6cc16d3`'s
   CSV: `det_final_v = 0.411 V` is already below the `0.2*vdd = 0.726 V`
   release threshold criterion 1 alone would accept, but
   `i_mkfb_final_a = 4.28e-7` is 8.6x the 50 nA threshold -- correctly
   marked `FAIL`. The two criteria do not always agree, which is exactly
   why both are checked rather than either alone.

`ngspice` exiting non-zero, a model-load error, or either measurement
coming back empty (a `.measure` that could not find its target) also fails
the point, same convention as every other testbench in this tree.

## Corner coverage

Same corner-label vocabulary and section pairing as `sim/core-open-loop-bias`
(the HBT axis is included, unlike `sim/startup-trip-point`, since the
core's three real `npn13G2` legs are DUT devices in this co-simulation
too):

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

× temperature `{-40, 27, 125}` °C × supply `{2.97, 3.30, 3.63}` V
(3.3 V ±10 %, per `spec/porting-plan.md` §4/DR-0002) = 45 points.

## `XMSENSE`'s width is read live from `design/netlist/bandgap_startup.spice`

Unlike `sim/startup-trip-point`'s testbench (which hardcodes each DUT
device's geometry as static text, copied by hand from the design netlist),
`run_pvt_sweep.sh` here `grep`/`sed`-extracts `XMSENSE`'s `w=` directly out
of `design/netlist/bandgap_startup.spice` at run time and substitutes it
into the template's `@@MSENSE_W@@` placeholder. This was a direct lesson
from issue #24's own resize: re-running `sim/startup-trip-point` after
widening `XMSENSE` initially reproduced the *old*, pre-resize trip point,
because its static template had not been hand-updated to match -- caught
before that stale record was committed, but exactly the class of drift a
live read avoids going forward. `XRPU` and `XMKFB`'s geometry (unchanged by
this issue) are still copied statically, matching every other testbench's
convention; only `XMSENSE` gets the dynamic treatment, since it is the one
device this issue's evidence showed is the design's tunable knob.

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time; idempotent
sim/startup-core-handover/run_pvt_sweep.sh
```

Requires `ngspice` on `PATH` plus the OSDI models; does not require
`xschem` or `klt`. Writes a new, timestamped, append-only evidence record
-- never overwriting a prior run -- under `netlist-snapshots/`, `corners/`
and `records/`, per `sim/README.md`'s convention, and exits non-zero if any
point fails so a future CI wiring (#16) can gate on it.
