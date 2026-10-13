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

## `klt sim` harness (issue #337, Part of #322)

The legacy `run_pvt_sweep.sh` loop above stays the generator of every
committed record. This experiment can now also be expressed as a `klt sim`
request so a multi-corner run goes to the batch fleet (host rules: no
hand-launched grids on dispatch hosts):

```bash
sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --sanity   # one local corner vs the legacy anchor (the gate)
sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --batch    # 45-point grid on the fleet (needs a CMOS5L image)
sim/sg13cmos5l-core-open-loop-bias/run_klt_sim.sh --record   # KLT_SIM_WORK=<batch work dir>; mint evidence
```

| file | role |
|---|---|
| `testbench/sg13cmos5l_core_open_loop_bias.body.spice.tmpl` | bench body: devices and fixtures carried over from the legacy template (a test asserts the device lines match) |
| `testbench/sg13cmos5l_core_open_loop_bias.request.json.tmpl` | the full 45-point grid and the measurements |
| `testbench/sg13cmos5l_core_open_loop_bias.record-spec.json` | the adapter's narrative + `pass_requires` + corner-section columns |
| `run_klt_sim.sh` | thin declaration over [`sim/harness/cmos5l_runner.sh`](../harness/cmos5l_runner.sh) |

**Sharding.** One request per process corner (5), each sweeping 3
temperatures x 3 supplies natively (`corners.supply_v` on the plain DC
`Vvdd`). The runner image's single-`models.lib` request cannot vary the
process within one request (klayout-tools#2668), so the first family
(`cornerPNP.lib`) rides `models`/`corners.process` and the MOS/resistor
sections are body-level `.lib` cards against the image's baked PDK root.

**Measurements** (same columns as the legacy CSV): `vref_v`, `vfb_v`,
`veb_q1_v`, `veb_q2_v`, `veb_q3_v`, `dveb_ptat_v`, `i_leg1_a`, `i_leg2_a`,
`i_leg3_a`, `r1_ohm`, `r2_ohm`. The legacy `.op` becomes a 50 ns transient
read at 40 ns (ngspice has no `.MEASURE OP`; all sources are DC), and the
derived columns are single `.meas ... find par(...)` cards instead of awk
post-processing. PASS = `klt sim` pass and `vref_v`, `veb_q1_v`, `veb_q2_v`,
`i_leg{1,2,3}_a` present -- the legacy rule. Difference from legacy: a
corner where the r1/r2 quotient itself cannot be evaluated (leg current
exactly 0) would presumably be graded failed by klt (a failed `.meas`), where the
legacy loop wrote an empty cell and still PASSed -- not exercised here; with
no leg current that is a failure anyway.

### SG13CMOS5L corner mapping (derived, not borrowed)

SG13G2's `klt_corner_bundle.CORNER_SECTIONS` pairs an *HBT* section
(`cornerHBT.lib`) with the MOS/resistor ones, and SG13CMOS5L has no HBT, so
that table is not evidence here. The triple for this PDK is
`CORNER_SECTIONS` in [`sim/harness/cmos5l_klt.py`](../harness/cmos5l_klt.py):

| label | pnpMPA (`cornerPNP.lib`) | MOS-hv (`cornerMOShv.lib`) | resistor (`cornerRES.lib`) |
|---|---|---|---|
| typ | `typ` | `mos_tt` | `res_typ` |
| bcs | `bcs` | `mos_ff` | `res_bcs` |
| wcs | `wcs` | `mos_ss` | `res_wcs` |
| sf | `typ` | `mos_sf` | `res_typ` |
| fs | `typ` | `mos_fs` | `res_typ` |

`cornerPNP.lib` is a real file in the CMOS5L tree whose sections are `typ`,
`stat`, `bcs`, `wcs` -- no skewed section, hence the sf/fs fallback to `typ`.
`cornerMOShv.lib`/`cornerRES.lib` are symlinks into the sibling `ihp-sg13g2/`
checkout, so those two columns are SG13G2's. The map is cross-checked, by
`run_klt_sim.sh` on every invocation and by CI, against the `PNP_SECTION_OF`
maps of the legacy scripts that generated every committed record and against
the section names in the installed `*.lib` files
(`cmos5l_klt.py check-mapping`).

### Status -- read before trusting any of this

* **Nothing here has been run.** Issue #337 is a conversion with no
  simulation and no evidence: the request/body/spec files were checked only
  by fixture tests (`python3 sim/harness/test_cmos5l_harness.py`), which
  need no ngspice or PDK. No record, corner log or snapshot was added, and
  the legacy records above are untouched.
* **`--sanity` is the gate and has not been exercised.** It runs one local
  corner and compares against the newest legacy record's typ/27C/3.30V row
  (anchors in `run_klt_sim.sh`; tolerances absorb the klt-vs-legacy
  measurement path, not a design change).
* **`--batch` cannot dispatch today.** The batch runner image bakes
  `ihp-sg13g2` only (`sim/pdk-sg13cmos5l.json`
  `deferred_requirements.provisioning`, a sibling issue); the runner refuses
  unless `KLT_SIM_CMOS5L_BATCH_READY=1` and has no local-grid fallback. The
  target PDK pin is likewise unverified at runtime
  (`sim/pdk-sg13cmos5l.json` `target_pin_status`).
* A record minted from this harness is a *new* record on the target pin; it
  neither replaces nor edits the legacy ones, and a regression against them
  authorises no retune or spec change.
