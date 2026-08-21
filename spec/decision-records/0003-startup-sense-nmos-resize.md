# 0003: bandgap_startup XMSENSE resize (w=2u -> w=10u)

- **Status**: proposed
- **Date**: 2026-08-21
- **Decided by**: Loom Builder (agent), issue #24

## Context

`design/bandgap_startup.sch` (issue #9) senses `bandgap_core`'s own `sns1`
node to decide when to release the startup kick it applies to the shared
mirror gate `fb`. Its first-pass sizing (`XMSENSE`, the `sg13_hv_nmos` sense
device, at `w=2u l=0.5u`, opposite `XRPU`'s ~2 MΩ `rhigh` pull-up) was
hand-derived, not simulation-checked (`design/README.md`'s explicit scope
note).

Issue #22 built the OSDI device models and the first PVT-cornered
testbenches for both `design/netlist/bandgap_core.spice` and
`design/netlist/bandgap_startup.spice`
(`sim/core-open-loop-bias/`, `sim/startup-trip-point/`). Comparing those two
experiments' records at matching `(corner, temperature, supply)` points
(`sim/startup-trip-point/README.md`, "Cross-bench observation") found the
sense stage's trip point sitting **above** the core's own `sns1` operating
voltage at four 125 °C points (`wcs_125c_{2.97,3.30,3.63}v`,
`sf_125c_3.63v`), by 2-10 mV — meaning the startup kick's pull-down
(`XMKFB`) would not fully release once the core is actually running there.
That comparison was explicitly caveated as two separate open-loop DC
benches, not a co-simulation, so issue #24 was filed to settle it directly.

## Decision

Issue #24 built `sim/startup-core-handover/`, a true co-simulation of
`bandgap_core` + `bandgap_startup` sharing their real `sns1`/`fb` nodes
under a **transient** `vdd` ramp (0 -> `VDD` over 200 µs, held to 2 ms),
biasing the mirror open-loop via the same diode-connected-replica fixture
`sim/core-open-loop-bias` uses (5 µA reference — no error amplifier exists
yet, issue #9's scope cut). Run against the original design (`XMSENSE`
`w=2u`), this confirmed — and substantially widened — the margin problem:
**12 of 45 points** fail full hand-over at 125 °C (v(det) stays well above
`vdd/2`, `XMKFB` keeps sinking up to ~17.4 µA at the worst point,
`wcs_125c_3.63v`), spanning every process corner at that temperature, not
just the four the cross-bench comparison flagged. The mechanism: `XMKFB`'s
residual pull-down current is not a passive leakage term against this
fixture — it forces extra current through the shared mirror, which drives
`sns1` higher via `VBE = Vt*ln(I/Is)`, which keeps the sense stage only
partially tripped, a stable partial-release equilibrium (checked out to
10 ms of settled transient time, not a slow transient artifact).

**Decision: widen `XMSENSE` from `w=2u` to `w=10u` (5x), `l=0.5u`
unchanged.** `XRPU` and `XMKFB` are unchanged. Re-running the same
co-simulation against the resized design: **45/45 points** now fully
release — `XMKFB`'s residual current drops to sub-nA (worst point:
3.7e-10 A, down from 1.74e-05 A) and `sns1` recovers to within 0.1 mV of
the core-only (no startup circuit) operating point at every previously-
failing corner. `sim/startup-trip-point`'s own testbench (updated to match)
now shows the trip point sitting 64-77 mV below the core's `sns1` at the
four originally-flagged points, comfortably clear of the original 2-10 mV
deficit.

## Alternatives considered

- **Shrink `XRPU`'s `rhigh` pull-up instead of widening `XMSENSE`.** Would
  lower the trip point the same way (weaker pull-up needs less pull-down to
  overcome), but also raises `XRPU`'s own steady-state current once
  `XMSENSE` clamps `det` low (the schematic header's own Iq accounting for
  `RPU`), an itemized quiescent-current cost `XMSENSE`'s resize does not
  carry. Not pursued since a single-parameter fix already clears the
  problem with a wide margin (see Decision).
- **Add hysteresis to the sense stage** (e.g. weak positive feedback from
  `det`/`fb` back into the sense path), which issue #24's acceptance
  criteria explicitly allowed. A resize alone was sufficient once verified
  by co-simulation, so the added circuit complexity, area, and (for a
  first-pass, sim-only-verified block) unverified stability risk of a
  hysteretic sense stage were not taken on. Worth revisiting only if a
  future PVT point (e.g. mismatch/Monte Carlo) reopens the margin.
- **Leave `XMSENSE` at `w=2u` and treat the 12-point 125 °C failure as
  acceptable**, on the theory that the real assembled circuit's future
  error amplifier (low output impedance at `fb`) would suppress the
  residual-current feedback this co-simulation's high-impedance
  current-source fixture amplifies (see the co-simulation testbench's own
  "IMPORTANT CAVEAT"). Rejected: the amplifier does not exist yet, this
  circuit needs to hand over correctly on its own terms today, and a 5x
  sense-device widen is a small, well-understood-consequence fix with no
  reason to defer it pending unbuilt follow-on work.

## Consequences

- `design/bandgap_startup.sch` and `design/netlist/bandgap_startup.spice`
  now specify `XMSENSE` at `w=10u l=0.5u` (was `w=2u l=0.5u`). `XRPU`
  (`rhigh` pull-up) and `XMKFB` are unchanged.
- `sim/startup-trip-point/testbench/tb_startup_trip_point.spice.tmpl`
  (a static, verbatim-copy-of-the-DUT testbench, unlike
  `sim/startup-core-handover`'s live read of the design netlist) needed a
  matching manual update and re-run to keep mirroring the real design —
  noted here since it is easy for a future resize to miss a testbench that
  copies device lines by hand rather than reading them from
  `design/netlist/` at generation time.
  `sim/startup-core-handover/run_pvt_sweep.sh` avoids that class of drift
  going forward by parsing `XMSENSE`'s `w=` directly out of
  `design/netlist/bandgap_startup.spice` at run time.
- `XMSENSE`'s larger W increases its own gate capacitance and (very
  slightly) `bandgap_startup`'s area; neither is claimed to matter at this
  design stage (no layout-area or CV budget exists yet for this block to
  compare against).
- This does **not** touch any ratified spec row: nothing under
  `spec/porting-plan.md` §6 is ratified yet (#13), and this decision only
  concerns `design/bandgap_startup.sch`'s own device sizing, not the core's
  topology or target `vref`.
- Still open, out of scope for this decision: the co-simulation's own
  caveat that its open-loop current-source fixture is a pessimistic bound
  relative to the eventual closed loop with a real error amplifier (not yet
  built). Once that amplifier lands, the hand-over should be re-verified
  against the real closed loop rather than this fixture — tracked
  informally here, not yet filed as its own issue.
