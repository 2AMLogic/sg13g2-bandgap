# sg13cmos5l-closed-loop-startup

PVT-cornered testbench co-simulating `design/sg13cmos5l/bandgap_core.sch` +
`bandgap_amp.sch` + `bandgap_startup.sch` (issue #65, phase 2/4 of the
SG13CMOS5L port, issue #63). This is the SG13CMOS5L analogue of
[`sim/closed-loop-startup/`](../closed-loop-startup/README.md) (the SG13G2
precedent) and the formal, PVT-cornered counterpart to
`design/sg13cmos5l/README.md`'s own single-nominal-corner informal
closed-loop check (issue #68).

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
                                         # AND a sibling ihp-sg13g2/ -- see
                                         # sim/pdk-sg13cmos5l.json
                                         # "sibling_checkout_requirement"
export PDK=ihp-sg13cmos5l
sim/sg13cmos5l-closed-loop-startup/run_pvt_sweep.sh
```

Requires ngspice on `PATH`. This PDK ships its OSDI device models prebuilt --
see `sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`.

## What this claims

Wired exactly as `design/sg13cmos5l/bandgap_top.sch` specifies (`core.fb <-
amp.out`, `core.sns1 -> amp.in_n`, `core.sns2 -> amp.in_p`, `startup` shares
`sns1` and `fb` with the core), with `vdd` itself ramped `0 -> VDD` over
200 us and held to 2 ms, the assembled block **self-starts and settles to a
closed-loop operating point** across the full temperature x supply x
pnpMPA/MOS/resistor-process-corner PVT grid:

1. **Startup released**: `v(det) <= 0.2*vdd` and `|i(XMKFB)| <= 50 nA`.
2. **Loop closed**: `|sns1 - sns2| <= 20 mV` -- the amplifier's whole job is
   forcing these two nodes equal.
3. **Not railed**: `fb` sits strictly inside `(vss, vdd)`, at least 50 mV from
   either rail -- confirms a real negative-feedback equilibrium rather than a
   polarity-bug saturation to one supply.

This is closed-loop infrastructure/plumbing evidence for issue #65, **not** a
claim against any ratified spec row (no ratified SG13CMOS5L accuracy target
exists yet -- `spec/porting-plan-sg13cmos5l.md`).

## What's different from the SG13G2 precedent

- **Core topology is reversed** -- grounded-collector `pnpMPA` legs instead
  of grounded-emitter `npn13G2` legs. See
  `sim/sg13cmos5l-core-open-loop-bias/README.md` for the full account; the
  wiring into the amplifier and startup circuit is unaffected, since both of
  those consume `sns1`/`sns2`/`fb` as plain node voltages regardless of which
  terminal of the bipolar device they come from.
- **`cornerPNP.lib` replaces `cornerHBT.lib`** in the `.lib` section list,
  same `PNP_SECTION_OF` map (and `sf`/`fs` -> `typ` fallback) as
  `sim/sg13cmos5l-core-open-loop-bias`.
- **No OSDI compile step**: this PDK ships `.osdi` models prebuilt (see
  `sim/pdk-sg13cmos5l.json` `"osdi_toolchain"`).
- **Supply grid is unchanged** (`{2.97, 3.30, 3.63}` V) -- see
  `sim/pdk-sg13cmos5l.json` `"supply_rails"`.
- Everything else -- the `rshunt=1e9 gmin=1e-9` convergence aids, the `vdd`
  PWL ramp shape, the three pass criteria and their thresholds, the
  `|| true`-guarded `.measure` parsing for non-convergent marginal corners --
  is identical to `sim/closed-loop-startup`, reused verbatim because none of
  it is PDK-specific.

## Cross-check against the informal single-corner result (issue #68)

`design/sg13cmos5l/README.md`'s own informal check at `typ`/`mos_tt`/`res_typ`,
27 degC, `vdd=3.3V` reported `|sns1-sns2| = 0.233 mV`, `fb = 2.49710 V`,
`det = 4.18836 mV`, `i(XMKFB) = 2.497 nA` -- this experiment's own `typ`
corner at the same temperature/supply point reproduces those results (see the
record's own CSV row for the exact re-run values), confirming this formal
testbench's fixture matches the informal check's fixture rather than
introducing a new discrepancy.

## Not attempted

Mismatch/Monte Carlo, AC/loop-stability (phase margin -- no compensation
capacitor exists in `bandgap_amp.sch` yet), DRC/LVS, layout. No MoM-cap-
dependent measurement exists in this testbench (none of the three DUTs
instantiate a capacitor) -- when a future phase adds a compensation/filter
cap, its spec row must be marked `insufficient-evidence` per issue #65's own
acceptance criteria, since MoM caps carry no corner/mismatch spread in this
PDK's models (`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`).

## `klt sim` harness (issue #337, Part of #322)

The legacy `run_pvt_sweep.sh` loop above stays the generator of every
committed record. This experiment can now also be expressed as a `klt sim`
request so a multi-corner run goes to the batch fleet (host rules: no
hand-launched grids on dispatch hosts):

```bash
sim/sg13cmos5l-closed-loop-startup/run_klt_sim.sh --sanity   # one local corner vs the legacy anchor (the gate)
sim/sg13cmos5l-closed-loop-startup/run_klt_sim.sh --batch    # 45-point grid on the fleet (needs a CMOS5L image)
sim/sg13cmos5l-closed-loop-startup/run_klt_sim.sh --record   # KLT_SIM_WORK=<batch work dir>; mint evidence
```

| file | role |
|---|---|
| `testbench/sg13cmos5l_closed_loop_startup.body.spice.tmpl` | bench body: devices and fixtures carried over from the legacy template (a test asserts the device lines match) |
| `testbench/sg13cmos5l_closed_loop_startup.request.json.tmpl` | the full 45-point grid and the measurements |
| `testbench/sg13cmos5l_closed_loop_startup.record-spec.json` | the adapter's narrative + `pass_requires` + corner-section columns |
| `run_klt_sim.sh` | thin declaration over [`sim/harness/cmos5l_runner.sh`](../harness/cmos5l_runner.sh) |

**Sharding.** One request per (process, supply) = 15, 3 temperatures each.
The rail is a PWL ramp whose target is baked into the body, and `alter`
would clobber it, so the request has no supply axis; `enrich` injects the
baked ramp target from each corner's deck (shared with the SG13G2 PWL
benches via `enrich_pvt_report.inject_baked_supply`, for failed corners too,
so the adapter's corner-id grammar always sees a supply).

**Measurements**: `det_early_v`, `fb_early_v` (20 us), `fb_final_v`,
`sns1_final_v`, `sns2_final_v`, `vref_final_v`, `det_final_v`,
`i_mkfb_final_a` (2 ms, the transient end), plus `dvsns_final_v` derived by
`enrich` (|sns1-sns2|, a difference of two reported values, as the legacy
awk did). PASS = the legacy three criteria -- startup released
(`det <= 0.2 vdd` and `|i(XMKFB)| <= 50 nA`), loop closed
(`dvsns <= 20 mV`), `fb` inside `[0.05 V, vdd - 0.05 V]` -- applied per point
by `cmos5l_klt.py enrich --kind closed-loop` (same constants as
`sim/lib/pvt_verdict_common.sh`; a test pins them), no settledness term.
`rshunt=1e9 gmin=1e-9` are carried over in the body, unchanged.
XMSENSE's width is read from the live
`design/sg13cmos5l/netlist/bandgap_startup.spice` by the runner (as the legacy
script does), substituted into the body, and recorded in an `msense_w` CSV
column through a per-run copy of the record spec.

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
