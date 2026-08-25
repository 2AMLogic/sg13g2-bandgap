# closed-loop-startup

The first genuinely **closed-loop** testbench in this tree. Co-simulates
`design/bandgap_core.sch` + `design/bandgap_amp.sch` + `design/bandgap_startup.sch`
(`design/netlist/bandgap_core.spice` + `design/netlist/bandgap_amp.spice` +
`design/netlist/bandgap_startup.spice`) in **one netlist**, wired exactly as
`design/bandgap_top.sch` specifies, under a **transient** `vdd` ramp — the
same fixture shape [`../startup-core-handover/`](../startup-core-handover/README.md)
uses, but with the real error amplifier (issue #58) closing the loop instead
of an ideal current-source fixture standing in for it. Built for issue #58;
see [`design/README.md`](../../design/README.md) § "What's here (issue #58)"
for the schematic-side account this testbench validates.

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x HBT/MOS/resistor-process-
corner PVT grid, with `vdd` ramped from 0 V to the corner's supply over
200 µs and held to 2 ms, the assembled three-block circuit —

1. **self-starts** — `bandgap_startup`'s `XMKFB` fully releases the shared
   `fb` node once the core+amp have ramped up (`v(det) <= 0.2*vdd` and
   `|i(XMKFB)| <= 50 nA`, the same release criteria
   [`../startup-core-handover/`](../startup-core-handover/README.md) uses),
   and
2. **settles to a real closed-loop operating point** — the amplifier
   actually forces `sns1 ≈ sns2` (`|sns1 - sns2| <= 20 mV`, a loop-closure
   tolerance, not a spec claim — see "Pass/fail criteria" below), with `fb`
   landing at an interior equilibrium rather than railing to either supply.

It does **not** claim conformance to any ratified spec row — `spec/porting-plan.md`
§6 is still a draft table, and ratification is tracked separately (#13).
It is, in the same sense every experiment in this tree is, closed-loop
**infrastructure and plumbing evidence**: proof the assembled block actually
starts and settles, not a measurement of untrimmed accuracy, PSRR, Iq, or
temperature coefficient against any target. It also does **not** claim
anything about loop stability/phase margin (this testbench is transient-only,
not an AC small-signal sweep — no compensation capacitor exists yet in
`bandgap_amp.sch`'s first pass either, see that schematic's header) or about
offset/mismatch (no Monte Carlo here).

## What is different from every prior testbench in this tree

Every PVT-swept testbench that predates this one —
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md),
[`../startup-trip-point/`](../startup-trip-point/README.md),
[`../startup-core-handover/`](../startup-core-handover/README.md), and their
`-pex` variants — substitutes an **ideal diode-connected-replica current
fixture** (`XM0`/`Ibias`, a 5 µA reference) for the mirror bias, because no
error amplifier existed in this repo yet (`design/README.md`, issue #9's
scope cut). That fixture is a very high output impedance load at `fb`; a
real amplifier is normally a *low* output impedance driver of `fb` — the
qualitative difference `../startup-core-handover/README.md`'s own "important
caveat" section already anticipated. This testbench removes that fixture
entirely: `bandgap_amp`'s own real `sg13_hv_pmos`/`sg13_hv_nmos` devices now
hold `fb` at whatever level makes `sns1 = sns2`, dynamically, through the
same stiff startup transient every prior testbench's ideal fixture could not
model.

## Fixtures (not device substitutions)

- **`Vvdd`** — the identical `PWL(0 0 200u <VDD> 2m <VDD>)` transient ramp
  `../startup-core-handover/` uses.
- **`Vmkfb`** — a 0 V ammeter in series with `XMKFB`'s drain, so the startup
  circuit's own residual contribution to the shared `fb` node can be
  measured directly rather than inferred from voltage alone. A 0 V source
  is a DC/transient short and does not move the operating point.
- **`Vsub`** — ties the global substrate net `sub!` to `vss`, the same
  convention every testbench in this tree uses.
- **`rshunt`/`gmin` (`.options`)** — convergence aids only, not physical
  fixtures; see "A real numerical finding" below.

**No fixture stands in for the servo loop.** This is the point of the
experiment.

## A real numerical finding, not a design defect

A handful of PVT corners would not converge with ngspice's default solver
settings: `doAnalyses: TRAN: Timestep too small ... trouble with
xq3:npn13g2_nx_vbic-instance`, always at `t ≈ 30-40 µs` into the 200 µs
ramp — the instant `vdd` is still well under 1 V and `bandgap_core`'s
diode-connected `npn13G2` legs sit at a genuinely near-singular, near-zero-
bias operating point, before any real current has been established anywhere
in the loop. Dev-time debugging for issue #58 found this a whack-a-mole
problem with either convergence aid alone at a single value: `rshunt=1e12`
left 4 of 45 corners failing (`typ_27c_3.30v`, `wcs_27c_3.63v`,
`sf_-40c_2.97v`, `fs_27c_2.97v`); strengthening to `rshunt=1e9` alone fixed
those four but newly failed a fifth (`wcs_27c_3.30v`). The combination in
`testbench/tb_closed_loop_startup.spice.tmpl`'s `.options` line
(`rshunt=1e9 gmin=1e-9`) cleared all 45 corners. Both aids are many orders
of magnitude below any current this testbench measures (`rshunt=1e9` sinks
≤1 nA at 1 V; `gmin=1e-9` is the same class of aid ngspice's own dynamic
gmin-stepping already applies internally, just present from the start) —
neither relaxes any pass/fail criterion, they only help the solver step
through a numerically stiff instant it would otherwise stall on.

This is the first time this repo's `sim/` tree has needed a convergence aid
at all: every prior PVT sweep drove `fb` from an ideal, always-well-defined
current source. This testbench is the first where `fb` is dynamically
co-determined by a real, high-impedance-at-cutoff amplifier stage during the
exact instant the whole circuit is at its most degenerate — a genuinely
harder numerical problem, not a symptom of a wiring bug (every one of the
originally-failing corners converges cleanly, with results consistent with
its neighbors, once given the aid).

`run_pvt_sweep.sh`'s own measurement-extraction step is also hardened
against this failure mode (`|| true` on each `grep`, since `set -euo pipefail`
would otherwise abort the *entire* 45-point sweep — losing every other
point's evidence — the first time a single corner's `.measure` lines fail to
print because the transient itself aborted; see the script's own comment).

## Pass/fail criteria

A point is `PASS` only if, at the end of the transient (`t=2ms`, fully
ramped and settled):

1. **Startup released**: `v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA` — the
   same criteria `../startup-core-handover/README.md` uses.
2. **Loop closed**: `|sns1 - sns2| <= 20 mV`. The amplifier's whole job is
   forcing these two nodes equal; a finite-gain single-stage OTA cannot make
   them exactly equal, so this is a loop-closure tolerance, not a spec
   claim. 20 mV is a generous bound relative to the ~55 mV `dVBE(Q1,Q2)`
   design swing (`design/bandgap_core.sch`'s own header) — roughly 40x the
   worst measured residual (0.51 mV) in this run, loose enough to tolerate
   real PVT-driven loop-gain variation, tight enough that a genuinely
   unclosed loop (e.g. a polarity bug making this positive feedback instead
   of negative — see `design/bandgap_amp.sch`'s header "polarity" section)
   would fail it outright rather than merely look imprecise.
3. **Not railed**: `fb` sits strictly inside `(vss, vdd)`, at least 0.05 V
   from either rail — confirms the amplifier found a real interior
   equilibrium (a working negative-feedback servo) rather than saturating
   to one supply (what a positive-feedback/polarity-bug loop would do
   instead).

`ngspice` exiting non-zero, a model-load error, or any of the six final
measurements coming back empty (a `.measure` that could not find its
target — see "A real numerical finding" above) also fails the point, same
convention as every other testbench in this tree.

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md) and
[`../startup-core-handover/`](../startup-core-handover/README.md) (the HBT
axis is included, since the core's three real `npn13G2` legs are DUT
devices here too):

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

x temperature `{-40, 27, 125} °C` x supply `{2.97, 3.30, 3.63} V` = 45
points.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-startup/run_pvt_sweep.sh
```

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
