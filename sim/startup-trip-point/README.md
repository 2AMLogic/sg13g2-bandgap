# startup-trip-point

The first PVT-cornered testbench for `design/bandgap_startup.sch` /
`design/netlist/bandgap_startup.spice` (issue #9's schematic), landed by
issue #22.

## Why this testbench exists

Every device in `bandgap_startup.spice` is OSDI-gated: two `sg13_hv_nmos`
switches (PSP103.6, `psp103.osdi`) and one `rhigh` pull-up (`r3_cmc`,
`r3_cmc.osdi`). Before issue #22 built those models, this netlist could not
be simulated **at all** in this environment — not approximately, not with
substitutions, since there was no device left to substitute *around*. It is
therefore the cleanest end-to-end demonstration that the OSDI toolchain
documented in `sim/README.md` § "OSDI device models" actually works: if the
models are missing or wrong, this experiment produces nothing.

## What this testbench claims, and what it does not

The startup circuit's job is: while the core is dead, force the mirror gate
`fb` low so current starts flowing; once the core is running, get out of the
way. This bench checks exactly that shape, at every PVT point:

1. **Engages at cold start** — with the core sense node `sns1` at 0 V,
   `XMSENSE` is off, so `XRPU` pulls `det` to ≥ 80 % of `vdd`…
2. **…and drives the mirror** — which turns `XMKFB` on and holds `fb`
   below 100 mV (recorded values are sub-millivolt).
3. **Has a well-defined trip point** — sweeping `sns1` from 0 to `vdd`,
   `v(det)` crosses `vdd/2` at some `0 < vtrip < vdd`.
4. **Disengages when the core is up** — near `sns1 = vdd`, `det` is below
   20 % of `vdd` and `fb` is released above 80 % of `vdd`.

All four are checked per point by `run_pvt_sweep.sh`; a point is only
`PASS` if all four hold *and* ngspice exits 0 with no model-load error. A
clean exit alone is not treated as a pass.

This is **infrastructure/plumbing evidence**, not a claim against any
ratified spec row (none is ratified — see #125). In particular it does **not**
claim the assembled bandgap starts: that needs the core and the startup
circuit co-simulated with a transient supply ramp, and an error amplifier
that does not exist yet (issue #9's scope cut).

### Cross-bench observation: a margin problem at 125 °C, worst-case corner

For the startup circuit to release cleanly, its trip point must sit *below*
the core's own `sns1` operating voltage. Comparing this experiment's
`vtrip_v` against `sim/core-open-loop-bias`'s `vbe_q1_v` at the matching
`(corner, temperature, supply)` point — the two experiments share a corner
label vocabulary precisely so this comparison is possible — the ordering
holds at 41 of 45 points, and **fails at four**:

| point | core `sns1` | startup `vtrip` |
|---|---|---|
| `wcs_125c_2.97v` | 0.5909 V | 0.5951 V |
| `wcs_125c_3.30v` | 0.5910 V | 0.5984 V |
| `wcs_125c_3.63v` | 0.5911 V | 0.6012 V |
| `sf_125c_3.63v`  | 0.5804 V | 0.5832 V |

At those points the detector would still be (partly) engaged with the core
running: a device-sizing margin issue in `bandgap_startup.sch`, exposed by
the first simulation this circuit has ever had. It is **not** an OSDI or
model problem, and it is out of scope for issue #22 (which built the
models); it is filed as its own design issue, #24. The comparison is also
cross-bench, not co-simulated — two separate open-loop DC benches — so
treat it as a strong indication to investigate rather than a verdict.

**Update (issue #24): investigated, confirmed (and widened), and fixed.**
`sim/startup-core-handover/` co-simulates `bandgap_core` + `bandgap_startup`
directly (sharing the real `sns1`/`fb` nodes, transient `vdd` ramp) rather
than comparing two separate DC benches. Against the original sizing above,
it confirmed the margin problem and found it substantially larger than this
cross-bench comparison suggested: 12 of 45 points fail full hand-over at
125 °C (every process corner at that temperature), not just these four,
because the residual pull-down current self-reinforces through the core's
own mirror rather than staying a small, static offset. Widening
`bandgap_startup`'s `XMSENSE` from `w=2u` to `w=10u` (see
[decision record 0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md))
fixed it: the `vtrip_v`/`wcs`/`sf` numbers in the table above are from the
pre-fix sizing and are kept here as the historical finding that motivated
#24 — the current design's trip point at those same four points now sits
64-77 mV *below* the core's `sns1` (see this experiment's latest
`records/*.csv`), and `sim/startup-core-handover`'s own records show 45/45
points fully releasing post-fix.

## Fixtures (not device substitutions)

The three DUT devices are copied verbatim from
`design/netlist/bandgap_startup.spice`. Two fixtures are added:

- **`Vsns1`** drives the core sense node, which in the assembled block is
  `bandgap_core.spice`'s `XQ1` collector/base. Sweeping it is how the
  engage/disengage transition is exercised in a single DC analysis.
- **`Rfbpu`**, a 10 MΩ pull-up from `vdd` to `fb`. `fb` is the PMOS mirror
  gate; nothing drives it high yet, so once `XMKFB` turns off it would be a
  floating node. The pull-up stands in for whatever eventually holds `fb`
  high (the amplifier output stage) and is weak enough (≤ 0.4 µA) not to
  contest `XMKFB`'s pull-down — the recorded `fb_on` column, sub-millivolt
  at every point, is the evidence for that.

`Vsub` ties the design's global `sub!` substrate net to `vss` through a 0 V
source, the same convention `sim/core-open-loop-bias` uses.

## Corner coverage

Same corner-label vocabulary as `sim/core-open-loop-bias`, minus the HBT
axis (no bipolar device here):

| label | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-------------------|-----------------|
| `typ` | `mos_tt`          | `res_typ`       |
| `bcs` | `mos_ff`          | `res_bcs`       |
| `wcs` | `mos_ss`          | `res_wcs`       |
| `sf`  | `mos_sf`          | `res_typ`       |
| `fs`  | `mos_fs`          | `res_typ`       |

× temperature `{-40, 27, 125}` °C × supply `{2.97, 3.30, 3.63}` V
(3.3 V ±10 %, per `spec/porting-plan.md` §4/DR-0002) = 45 points.

## Cold-start invocation

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time; idempotent
sim/startup-trip-point/run_pvt_sweep.sh
```

Requires `ngspice` on `PATH` plus the OSDI models; does not require
`xschem` or `klt`. The run writes a new, timestamped, append-only evidence
record — never overwriting a prior run — under `netlist-snapshots/`,
`corners/` and `records/`, per `sim/README.md`'s convention, and exits
non-zero if any point fails so a future CI wiring (#16) can gate on it.

## ngspice note: `meas ... at=` and the sweep end point

`meas dc <name> find v(x) at=<vdd>` fails with
`measure ... find(AT) : out of interval` when `<vdd>` is exactly the last
point of the `dc` sweep. The "core fully up" measurements are therefore
taken at `vdd − 0.05 V`, one grid point short of the end. This is an
ngspice behavior, not a circuit property — recorded here so the next agent
does not re-derive it from a confusing failure.
