# closed-loop-vref-pvt

Closed-loop **DC / `vref` characterization** (issue #86, follow-on to #58).
Co-simulates `design/bandgap_core.sch` + `design/bandgap_amp.sch` +
`design/bandgap_startup.sch` (`design/netlist/bandgap_core.spice` +
`design/netlist/bandgap_amp.spice` + `design/netlist/bandgap_startup.spice`)
in **one netlist**, wired exactly as `design/bandgap_top.sch` specifies —
the identical co-simulated topology
[`../closed-loop-startup/`](../closed-loop-startup/README.md) built for
issue #58. That experiment's own claim is "does the assembled block start
and close the loop" (45/45 PASS, no ideal feedback fixture anywhere). This
experiment's claim is different: **what DC value does `vref` actually
settle to, across the full PVT grid, and how does that value move with
temperature** — the two questions `design/README.md`'s issue #58 "Not
attempted" list named as open (`design/README.md`'s "What has and has not
been verified" section, updated by this issue).

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x
HBT/MOS/resistor-process-corner PVT grid, through the real closed loop
(no ideal current-source/fixture standing in for the amplifier or the
mirror bias — the same "no fixture stands in for the servo loop" property
`../closed-loop-startup/README.md` established), `vref` settles to a real,
steady DC value: confirmed by measuring it at two separated time points
(`t=2ms` and `t=3ms`) and requiring `|vref(3ms)-vref(2ms)| <= 1 mV` before
trusting the reading — a genuine DC operating point, not a still-slewing
transient snapshot. It additionally computes an **informal** temperature
coefficient (TC) per process-corner/supply group via the endpoint method:

```
TC_ppm_per_C = 1e6 * (vref(125C) - vref(-40C)) / (165 * vref(27C))
```

(165 = 125 − (−40), the temperature span; `vref(27C)` is the reference used
to convert an absolute V/°C slope into the relative ppm/°C figure
`spec/porting-plan.md` §6's own draft target row uses.)

**It does not claim conformance to any ratified spec row.**
`spec/porting-plan.md` §6 is still a **draft, unratified** table (#13) — per
`klayout-tools`' `docs/design-evidence-tiers.md` T1 checklist (referenced
from issue #4), no checklist item on #4 closes from this record alone, and
this README does not compare
its own numbers against that draft table's `< 50 ppm/°C` TC target as a
pass/fail bar. It reports what the endpoint-method computation finds
(**~349-376 ppm/°C** across this run's 15 corner/supply groups — see
`records/<record-id>-tc.csv` for the full table) as **evidence**, not a
verdict. That number is not a surprise given `design/README.md`'s own
explicit scope cut: **no trim network exists in this design yet**
("Neither sibling repo's first-pass core had one either" —
`design/README.md`'s "Explicitly out of scope" section for issue #9), and
an untrimmed VBE-based bandgap reference's TC is expected to be in the
hundreds-of-ppm/°C range without one. This experiment is the capability to
re-check that number the moment a trim network and a ratified spec row both
exist — it is not, by itself, a claim that the design meets or misses any
target.

It also does not claim anything about loop stability/phase margin (see
[`../loop-gain-phase-margin/`](../loop-gain-phase-margin/README.md) for
that) or offset/mismatch (still deferred — see `design/README.md`'s updated
"Not attempted" list).

## Why the same topology as `closed-loop-startup`, and what's different

Reusing `closed-loop-startup`'s proven co-simulated netlist (rather than
inventing a different bring-up path) is deliberate: that experiment already
found and fixed the numerical convergence problem this topology's vdd ramp
hits at a handful of PVT corners (see its own README "A real numerical
finding" section), and reusing its exact `rshunt=1e9 gmin=1e-9` aids here
means this experiment inherits that fix rather than rediscovering it. Three
differences from `closed-loop-startup`'s own template:

1. **The vdd ramp holds to 3 ms instead of 2 ms** — one extra millisecond so
   `vref` can be measured at two separated points (`t=2ms` and `t=3ms`).
2. **`vref` is measured at both points**, and `run_pvt_sweep.sh` requires
   `|vref(3ms)-vref(2ms)| <= 1 mV` as an explicit "settled" pass criterion —
   `closed-loop-startup` never needed this, since its own claim was about
   loop closure and startup release, not the precision of a single
   accuracy number.
3. **This experiment additionally computes the TC summary** described
   above, which `closed-loop-startup`'s own record does not.

Every other convention (device-for-device netlist copy, corner-label
vocabulary, `rshunt`/`gmin` convergence aids, evidence-record shape) is
unchanged from `closed-loop-startup` — see that experiment's README for the
full account of anything not repeated here.

## Pass/fail criteria

A point is `PASS` only if, at the end of the transient (`t=3ms`):

1. **Startup released**: `v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA` — the
   same criteria `../closed-loop-startup/README.md` uses (re-evaluated here
   at `t=3ms` instead of `2ms`).
2. **Loop closed**: `|sns1 - sns2| <= 20 mV` — same tolerance and rationale
   as `../closed-loop-startup/README.md`.
3. **Not railed**: `fb` sits strictly inside `(vss, vdd)`, at least 0.05 V
   from either rail — same criterion as `../closed-loop-startup/README.md`.
4. **Settled** (new to this experiment): `|vref(3ms) - vref(2ms)| <= 1 mV`
   — confirms the reported `vref` is a genuine DC value, not a still-moving
   transient snapshot.

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

45/45 points PASS. Across all 45 points, `vref` ranges **1.134-1.215 V**
(closely matching `closed-loop-startup`'s own independently-measured
`vref` band at `t=2ms`, 1.134-1.215 V — expected, since both experiments
drive the identical topology through the identical ramp). Every point
settled exactly (`vref_settle_delta_v` reads `0` at ngspice's own six
significant figures for every corner in this run — the vdd ramp is fully
held flat from `200us` to `3ms`, so nothing is still slewing by `2ms`
already). The informal TC table (`records/<record-id>-tc.csv`, reproduced
in the record's own `.md`) reads 349-376 ppm/°C across the 15
corner/supply groups — see "What this testbench claims" above for why that
number is expected, not a target miss.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-vref-pvt/run_pvt_sweep.sh
```

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
