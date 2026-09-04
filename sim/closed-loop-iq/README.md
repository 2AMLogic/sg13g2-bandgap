# closed-loop-iq

Closed-loop **quiescent supply current (Iq)** characterization (issue #95,
follow-on to #58/#86/#88). Co-simulates `design/bandgap_core.sch` +
`design/bandgap_amp.sch` + `design/bandgap_startup.sch`
(`design/netlist/bandgap_core.spice` + `design/netlist/bandgap_amp.spice`
+ `design/netlist/bandgap_startup.spice`) in **one netlist**, wired exactly
as `design/bandgap_top.sch` specifies — the identical co-simulated topology
[`../closed-loop-startup/`](../closed-loop-startup/README.md) and
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md) already use.
Those experiments' own claims are "does the assembled block start and close
the loop" (`closed-loop-startup`, 45/45 PASS) and "what DC value does `vref`
settle to" (`closed-loop-vref-pvt`, 45/45 PASS). This experiment's claim is
different again: **how much total current does the assembled block draw
from `vdd`, once settled, across the full PVT grid** — the last of the two
`spec/porting-plan.md` §6 draft-table rows (`vref`/TC, PSRR, supply, Iq,
startup — area is the only remaining gap, and is a layout-geometry metric,
out of `sim/`-testbench scope) with no `sim/` testbench coverage at all.

(That area gap is now covered outside `sim/`, exactly where this paragraph
says it belongs: see
[`measurements/2026-09-layout-area/`](../../measurements/2026-09-layout-area/README.md),
a reproducible `klt stats` measurement of every committed
`layout/<cell>/<cell>.gds`. It remains out of `sim/`-testbench scope — this
sentence is unchanged in substance, only cross-referenced.)

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x
HBT/MOS/resistor-process-corner PVT grid, through the real closed loop (no
ideal current-source/fixture standing in for the amplifier or the mirror
bias — the same "no fixture stands in for the servo loop" property
`../closed-loop-startup/README.md` established), the assembled block draws a
real, steady total current from `vdd`: confirmed by measuring `i(Vvdd)` at
two separated time points (`t=2ms` and `t=3ms`) and requiring
`|i(Vvdd)(3ms)-i(Vvdd)(2ms)| <= 100 nA` before trusting the reading — a
genuine settled quiescent current, not a still-slewing transient snapshot.
It also reports the average of `i(Vvdd)` over the same `[2ms, 3ms]` window
(`iq_avg_a` in the CSV) as this experiment's headline number, which for a
point that has already settled exactly (as every point in this run's own
committed record does) equals the two endpoint readings.

`Vvdd` is not an added fixture — it is the same transient supply-ramp source
`../closed-loop-startup/` and `../closed-loop-vref-pvt/` already drive the
circuit with; this experiment simply reads the current it already carries
(`i(Vvdd)`), the same way `../closed-loop-startup/`'s own `Vmkfb` ammeter
reads a current without adding a new device to the circuit under test.

**It does not claim conformance to any ratified spec row.**
`spec/porting-plan.md` §6 is still a **draft, unratified** table (#125) —
per `klayout-tools`' `docs/design-evidence-tiers.md` T1 checklist
(referenced from issue #4), no checklist item on #4 closes from this record
alone, and this README does not compare its own numbers against that draft
table's `< 50 µA` Iq target as a pass/fail bar. It reports what this run
measured (**19.98-42.37 µA** across this run's 45 PVT points — see
`records/<record-id>.csv` for the full per-point table) as **evidence**, not
a verdict. This experiment is the capability to re-check that number the
moment a ratified spec row exists — it is not, by itself, a claim that the
design meets or misses any target. (For context only, since this is not a
pass/fail claim: every point in this run's own record happens to measure
below the draft `< 50 µA` target — see "Results summary" below.)

It also does not claim anything about loop stability/phase margin (see
[`../loop-gain-phase-margin/`](../loop-gain-phase-margin/README.md)),
PSRR (see [`../closed-loop-psrr/`](../closed-loop-psrr/README.md)),
`vref`/TC (see [`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md)),
or offset/mismatch (see
[`../closed-loop-offset/`](../closed-loop-offset/README.md)).

## Why the same topology as `closed-loop-startup`/`closed-loop-vref-pvt`, and what's different

Reusing the proven co-simulated netlist (rather than inventing a different
bring-up path) is deliberate: `../closed-loop-startup/` already found and
fixed the numerical convergence problem this topology's `vdd` ramp hits at a
handful of PVT corners (see its own README "A real numerical finding"
section), and reusing its exact `rshunt=1e9 gmin=1e-9` aids here means this
experiment inherits that fix rather than rediscovering it. The only
differences from `../closed-loop-vref-pvt/`'s own template:

1. **The headline measurement is `i(Vvdd)`, not `v(vref)`** — this
   experiment adds `i_vdd_2ms`/`i_vdd_3ms`/`i_vdd_avg` measurements and
   drops the `v_vref_2ms`/`v_vref_3ms` ones (already covered by
   `../closed-loop-vref-pvt/`, out of this experiment's own scope).
2. **The settledness tolerance is expressed in amps, not volts**
   (`SETTLE_TOL_A = 100 nA` vs. `../closed-loop-vref-pvt/`'s
   `SETTLE_TOL_V = 1 mV`) — same discipline, different unit, chosen relative
   to this design's own measured Iq scale (tens of µA — 100 nA is well under
   1% of the smallest measured point).
3. **Iq is reported as a magnitude.** `Vvdd` is an independent voltage
   source, so ngspice's passive sign convention reports `i(Vvdd)` negative
   while it delivers (rather than absorbs) current to the circuit —
   `run_pvt_sweep.sh` takes the absolute value before writing the CSV, the
   same sign-handling convention this template's own `i(Vmkfb)` measurement
   already needs.

Every other convention (device-for-device netlist copy, corner-label
vocabulary, `rshunt`/`gmin` convergence aids, `vdd` ramp shape, evidence-
record shape) is unchanged from `../closed-loop-vref-pvt/` — see that
experiment's and `../closed-loop-startup/`'s READMEs for the full account of
anything not repeated here.

## Pass/fail criteria

A point is `PASS` only if, at the end of the transient (`t=3ms`):

1. **Startup released**: `v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA` — the
   same criteria `../closed-loop-startup/README.md` and
   `../closed-loop-vref-pvt/README.md` use (re-evaluated here at `t=3ms`).
2. **Loop closed**: `|sns1 - sns2| <= 20 mV` — same tolerance and rationale
   as `../closed-loop-startup/README.md`.
3. **Not railed**: `fb` sits strictly inside `(vss, vdd)`, at least 0.05 V
   from either rail — same criterion as `../closed-loop-startup/README.md`.
4. **Settled** (new to this experiment): `|i(Vvdd)(3ms) - i(Vvdd)(2ms)| <=
   100 nA` — confirms the reported Iq is a genuine settled quiescent value,
   not a still-slewing transient snapshot.

`ngspice` exiting non-zero, a model-load error, or any `.measure` coming
back empty also fails the point, same convention as every other testbench
in this tree.

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md) and
[`../closed-loop-startup/`](../closed-loop-startup/README.md):

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

x temperature `{-40, 27, 125} °C` x supply `{2.97, 3.30, 3.63} V` = 45
points.

## Results summary (this repo's own committed record)

45/45 points PASS. Across all 45 points, the settled quiescent Iq
(`iq_avg_a`) ranges **19.98-42.37 µA**, rising with temperature (as expected
for a `VBE`-referenced bias network: the core's diode-connected `npn13G2`
legs draw more current as `VBE` and device characteristics shift with
temperature) and with supply (as expected for any resistively/mirror-set
bias current with finite output impedance). Every point settled exactly
(`iq_settle_delta_a` reads `0` at ngspice's own six significant figures for
every corner in this run — the `vdd` ramp is fully held flat from `200us` to
`3ms`, so nothing is still slewing by `2ms` already, matching
`../closed-loop-vref-pvt/`'s own independent finding for `vref`). As noted
above, this range happens to sit below `spec/porting-plan.md` §6's draft
`< 50 µA` target at every point in this run — offered as context, not as a
pass/fail claim (see "What this testbench claims" above).

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-iq/run_pvt_sweep.sh
```

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
