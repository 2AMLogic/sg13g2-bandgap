# sg13cmos5l-core-open-loop-bias

PVT-cornered testbench for `design/sg13cmos5l/bandgap_core.sch`'s open-loop
behavior (issue #65, phase 2/4 of the SG13CMOS5L port, issue #63). This is
the SG13CMOS5L analogue of [`sim/core-open-loop-bias/`](../core-open-loop-bias/README.md)
(the SG13G2 precedent), adapted for a core with a fundamentally different
bipolar topology -- see "What's different from the SG13G2 precedent" below.

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
                                         # AND a sibling ihp-sg13g2/ -- see
                                         # sim/pdk-sg13cmos5l.json
                                         # "sibling_checkout_requirement"
export PDK=ihp-sg13cmos5l
sim/sg13cmos5l-core-open-loop-bias/run_pvt_sweep.sh
```

Requires ngspice on `PATH`. Unlike SG13G2, this PDK ships its OSDI device
models **prebuilt** -- no `sim/tools/build-osdi.sh` compile step is needed
(that script's `--check` mode still runs as an unconditional preflight via
`sim/lib/pvt_preflight.sh`, and passes with zero code changes since it
resolves `PDK_ROOT`/`PDK` generically -- see `sim/pdk-sg13cmos5l.json`
`"osdi_toolchain"`).

## What this claims

`bandgap_core.sch`'s three real `pnpMPA` legs (Q1 unit, Q2 8x-area, Q3 unit
output) produce a PTAT delta-VEB and a summed CTAT+PTAT `vref`, biased by the
real `sg13_hv_pmos` PSP103 mirror (not an ideal current source), across the
full temperature x supply x pnpMPA/MOS/resistor-process-corner grid, when the
mirror's `fb` gate is driven open-loop from a diode-connected replica leg
carrying 5 uA -- the exact same fixture pattern and current
`sim/core-open-loop-bias` uses for the SG13G2 core.

This is infrastructure/plumbing evidence for issue #65, **not** a claim
against any ratified spec row: this repo's `spec/` tracks no ratified
SG13CMOS5L accuracy target yet (see `spec/porting-plan-sg13cmos5l.md`,
"Status: engineering input, not a ratified decision").

## What's different from the SG13G2 precedent

- **Topology is reversed.** SG13G2's own `bandgap_core.sch` uses a
  grounded-*emitter* `npn13G2` core (`XQ1 sns1 sns1 vss vss npn13G2 ...` --
  base and collector tied together at `sns1`, emitter at `vss`). SG13CMOS5L
  has no HBT (`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`,
  DR-0004), so `bandgap_core.sch` uses the gf180-bandgap/sky130-bandgap
  grounded-*collector* `pnpMPA` shape instead: `XQ1 vss vss sns1 pnpMPA ...`
  -- base **and collector** tied together at `vss`, emitter at `sns1`. The
  measured quantity is still each device's V(E)-V(B) ("VEB", the PNP
  equivalent of an NPN's VBE), but because the base sits at `vss` = 0 V,
  VEB(Q1) is simply `v(sns1)` directly -- same numeric role SG13G2's
  `v(sns1)` = VBE(Q1) plays, just from the opposite terminal convention. See
  the testbench template's own header for the full account.
- **An amplifier already exists for this core** (`design/sg13cmos5l/bandgap_amp.sch`,
  issue #68) -- unlike SG13G2's own `core-open-loop-bias`, which was written
  *before* `design/bandgap_amp.sch` existed (issue #9's scope cut) and so had
  no alternative to an open-loop fixture. This experiment deliberately keeps
  the same open-loop fixture anyway, on purpose: it isolates the core's own
  PTAT/CTAT generation from the amplifier's loop dynamics, the same
  diagnostic value SG13G2's precedent has. `sim/sg13cmos5l-closed-loop-startup`
  is the companion experiment that removes this fixture entirely and lets the
  real amplifier close the loop.
- **`cornerPNP.lib` replaces `cornerHBT.lib`.** `pnpMPA`'s process-corner
  sections are `typ`/`bcs`/`wcs` (no `hbt_` prefix, and -- like `cornerHBT.lib`
  -- no skewed `sf`/`fs`-equivalent section, so this experiment's own
  `PNP_SECTION_OF` map in `run_pvt_sweep.sh` falls `sf`/`fs` back to `typ`,
  the same fallback `sim/lib/pvt_preflight.sh`'s shared `HBT_SECTION_OF` map
  already uses for SG13G2's HBT). See `sim/pdk-sg13cmos5l.json`
  `"bipolar_device_note"`.
- **Supply grid is unchanged**: `{2.97, 3.30, 3.63}` V, the same 3.3V
  HV-flavor analog rail (`sg13_hv_pmos`, DR-0002's choice, inherited
  unchanged by DR-0004) every SG13G2 testbench in this tree sweeps. The
  parent epic's "1.2V digital / 3.3V analog" framing names SG13CMOS5L's LV
  digital rail, which this bandgap-only, analog-only block never
  instantiates a device against -- see `sim/pdk-sg13cmos5l.json`
  `"supply_rails"` and `spec/porting-plan-sg13cmos5l.md` section 2 for the
  same clarification made at design-capture time.

## Not attempted

PVT sweep of `bandgap_amp.sch`/`bandgap_startup.sch` in isolation, closed-loop
behavior (see `sim/sg13cmos5l-closed-loop-startup`), startup-circuit behavior
in isolation (see `sim/sg13cmos5l-startup-trip-point`), mismatch/Monte Carlo,
DRC/LVS, layout. No MoM-cap-dependent measurement exists in this testbench --
`bandgap_core.sch` has no capacitor at all (no compensation/filter cap in any
landed SG13CMOS5L schematic yet) -- so issue #65's "mark MoM-cap-dependent
spec rows `insufficient-evidence`" acceptance criterion has no row to apply
to here; noted for whichever future phase adds one (see
`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`'s own
forward-guidance flag: MoM caps carry no corner/mismatch spread in this
PDK's models).
