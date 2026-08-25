# sg13cmos5l-startup-trip-point

PVT-cornered testbench for `design/sg13cmos5l/bandgap_startup.sch`'s
engage/disengage behavior (issue #65, phase 2/4 of the SG13CMOS5L port,
issue #63). This is the SG13CMOS5L analogue of
[`sim/startup-trip-point/`](../startup-trip-point/README.md) (the SG13G2
precedent).

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
                                         # AND a sibling ihp-sg13g2/ -- see
                                         # sim/pdk-sg13cmos5l.json
                                         # "sibling_checkout_requirement"
export PDK=ihp-sg13cmos5l
sim/sg13cmos5l-startup-trip-point/run_pvt_sweep.sh
```

Requires ngspice on `PATH`. This PDK ships its OSDI device models prebuilt --
see `sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`.

## What this claims

The startup circuit engages at cold start (core sense node `sns1` at 0 V =>
`det` pulled to >= 80% of `vdd`, `fb` held below 100 mV so the PMOS mirror is
forced on) and disengages once the core is running (`sns1` near `vdd` =>
`det` below 20% of `vdd` and `fb` released above 80% of `vdd`), with a
well-defined trip point strictly inside `(0, vdd)`, across the full
temperature x supply x MOS/resistor-process-corner grid.

This is infrastructure/plumbing evidence for issue #65, **not** a claim
against any ratified spec row.

## What's different from the SG13G2 precedent

Almost nothing. `design/sg13cmos5l/bandgap_startup.sch` (issue #68) is a
direct port of SG13G2's own `design/bandgap_startup.sch` with **only the
symbol-library path changed** -- same device sizes (`XRPU w=1u l=1411.3u`,
`XMSENSE w=10u l=0.5u`, `XMKFB w=2u l=0.5u`), same topology, no bipolar
device at all in either variant. `design/sg13cmos5l/README.md`'s "issue #68"
section already re-verified (not assumed) that `bandgap_core.sch`'s `sns1`
node sits at the same ~0.7-0.8V one-VEB/VBE swing this circuit's `XMSENSE`
gate was built for, and that `fb`'s polarity is identical in both cores --
this testbench's own PVT sweep is the formal, corner-swept confirmation of
that informal claim.

The only real differences from `sim/startup-trip-point`:

- Reads `design/sg13cmos5l/netlist/bandgap_startup.spice` as its DUT
  (`design/netlist/bandgap_startup.spice` unchanged, still SG13G2's own).
- No `sim/tools/build-osdi.sh` compile step needed: this PDK ships its OSDI
  models prebuilt (`sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`).
- Supply grid is unchanged (`{2.97, 3.30, 3.63}` V, the 3.3V HV-flavor analog
  rail) -- see `sim/pdk-sg13cmos5l.json` `"supply_rails"`.

## Not attempted

PVT sweep of `bandgap_core.sch`/`bandgap_amp.sch` in isolation (see
`sim/sg13cmos5l-core-open-loop-bias`), closed-loop behavior (see
`sim/sg13cmos5l-closed-loop-startup`), mismatch/Monte Carlo, DRC/LVS,
layout. This testbench has no MoM-cap-dependent measurement (the startup
circuit has no capacitor).
