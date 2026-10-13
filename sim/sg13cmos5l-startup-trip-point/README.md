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

## `klt sim` harness (issue #337, Part of #322)

The legacy `run_pvt_sweep.sh` loop above stays the generator of every
committed record. This experiment can now also be expressed as a `klt sim`
request so a multi-corner run goes to the batch fleet (host rules: no
hand-launched grids on dispatch hosts):

```bash
sim/sg13cmos5l-startup-trip-point/run_klt_sim.sh --sanity   # one local corner vs the legacy anchor (the gate)
sim/sg13cmos5l-startup-trip-point/run_klt_sim.sh --batch    # 45-point grid on the fleet (needs a CMOS5L image)
sim/sg13cmos5l-startup-trip-point/run_klt_sim.sh --record   # KLT_SIM_WORK=<batch work dir>; mint evidence
```

| file | role |
|---|---|
| `testbench/sg13cmos5l_startup_trip_point.body.spice.tmpl` | bench body: devices and fixtures carried over from the legacy template (a test asserts the device lines match) |
| `testbench/sg13cmos5l_startup_trip_point.request.json.tmpl` | the full 45-point grid and the measurements |
| `testbench/sg13cmos5l_startup_trip_point.record-spec.json` | the adapter's narrative + `pass_requires` + corner-section columns |
| `run_klt_sim.sh` | thin declaration over [`sim/harness/cmos5l_runner.sh`](../harness/cmos5l_runner.sh) |

**Sharding.** One request per (process, supply) = 15, 3 temperatures each:
the dc sweep stop and two measurement levels scale with the supply
(`Vsns1 0 VDD 0.005`, trip level `VDD/2`, "core up" level `VDD-0.05`, both
`%.4f` as the legacy awk formats them). This bench instantiates no bipolar
device, so only the MOS-hv/resistor families are involved: `cornerMOShv.lib`
rides `models`/`corners.process` and `cornerRES.lib` is the body-level card.

**Measurements**: `det_on_v`, `fb_on_v`, `vtrip_v`, `det_off_v`,
`fb_off_v` (the legacy columns). The legacy cold-start `op` is the first
point of the dc sweep, so `det_on_v`/`fb_on_v` are `.meas dc ... at=0`.
**Unverified:** whether ngspice accepts `.meas dc ... at=` at the exact sweep
*start* (the legacy script documents that it refuses the exact *end*); the
`--sanity` gate hits it before any grid. PASS = the legacy six criteria
(`det_on >= 0.8 vdd`, `fb_on <= 0.1`, `0 < vtrip < vdd`, `det_off <= 0.2 vdd`,
`fb_off >= 0.8 vdd`), applied per point by `cmos5l_klt.py enrich --kind
trip-point` with the same formula as `pvt_trip_point_verdict`; a missing
operand FAILs the point, never passes it. No threshold changed.

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
