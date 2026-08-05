# 0001: Bipolar device selection — real HBT (`npn13G2`) over parasitic-style PNP (`pnpMPA`)

- **Status**: proposed (input to a future spec-ratification issue; this
  block has no ratified spec yet, unlike gf180/sky130 at the time their
  analogous topology records were written)
- **Date**: 2026-08-05
- **Decided by**: Builder agent, issue #2
- **Related**: #1 (`klt` PDK resolver — blocks any work that would validate
  this decision in schematic/layout), `2AMLogic/gf180-bandgap`
  `spec/decision-records/0001-bandgap-topology-selection.md` (topology
  precedent for a parasitic-PNP-only process), `2AMLogic/sky130-bandgap`
  `spec/topology-survey.md` (topology precedent for a fixed-geometry
  parasitic-PNP process)

## Context

`CLAUDE.md` and `README.md` both flag SG13G2 being BiCMOS — offering real
bipolar devices rather than the parasitic PNPs gf180-bandgap and
sky130-bandgap rely on — as a genuine, expected difference from those ports,
and ask that the choice be made deliberately rather than defaulted into.
Reading SG13G2's actual SPICE model decks
(`ihp-sg13g2/libs.tech/ngspice/models/sg13g2_hbt_mod.lib`, IHP-Open-PDK
`main` commit `22f2a25`, 2026-08-05) and the process specification
(`SG13G2_os_process_spec.pdf` Rev. 1.2, §3 "Bipolar Parameters") shows this
process actually ships **two** bipolar device families, not one:

- **`npn13G2`** (and voltage/current variants `npn13G2l`, `npn13G2v`): a
  real SiGe:C HBT, VBIC Rev. 1.15 model. Process-spec target current gain
  `BF = 650` (min 300, max 1200) at `AE = 0.07×0.9 µm²`, `f_T` target
  300–350 GHz, `f_max` target 400–450 GHz. This is categorically not a
  parasitic device — it is the process's headline product (SG13S/SG13G2 are
  marketed on this HBT's performance, per the process spec's General
  Information section) — and its current gain is roughly an order of
  magnitude better-characterized than either sibling's parasitic PNP
  (sky130's `pnp_05v5`: BF ≈ 16.6–19.4, per `spec/topology-survey.md`).
  However, its breakdown voltages are low by bandgap-core standards:
  `BVCEO` target 1.6 V (min 1.4 V), `BVCBO` target 4.8 V (min 3.8 V),
  `BVEBO` target 1.6 V (min 1.0 V) — all for the standard flavor, all
  well inside a 3.3 V ±10% supply rail (§4 of this repo's porting plan).
- **`pnpMPA`**: a PNP, but modeled as a Level-1 Gummel-Poon device with a
  fixed forward current gain `bf = 1.10 * sgp_mpa_bf` in the model card —
  i.e. current gain near unity, an order of magnitude *worse* than either
  sibling's parasitic PNP. The model's own header comment (`DUT:
  diode_pp=pnpMPA`) suggests it derives from a diode-connected
  characterization structure rather than a device engineered for
  transistor-mode gain. Its subckt uses fixed default area/perimeter
  parameters (`a`, `p`) rather than an emitter-multiplicity parameter.

Both device families have existing xschem schematic symbols
(`npn13G2.sym` and variants, `pnpMPA.sym` in
`ihp-sg13g2/libs.tech/xschem/sg13g2_pr/`), so this decision is not gated on
symbol availability — only on the `klt` resolver (#1) for anything beyond
schematic entry.

## Decision

**Adopt `npn13G2` (the real SiGe:C HBT) as the primary bandgap-core bipolar
device.** This is "different, and different is part of the value here," per
the issue body: it is a genuinely better-characterized, higher-gain device
than either sibling repo's parasitic PNP, and using it is consistent with
this repo's premise that SG13G2's BiCMOS bipolar devices are a real
engineering opportunity, not just a PDK curiosity to note and route around.

This has a direct topology consequence, named here rather than left
implicit: `npn13G2` is an NPN device, so a core built on it is a
**grounded-emitter** topology, not the grounded-collector PNP-pair topology
both gf180's Brokaw-cell core and sky130's Kuijk-style core use. **This is
not a device swap into the existing sibling schematics — the core has to be
redrawn.** NPN-based bandgap cores are well precedented in the literature
(and arguably more natural in a BiCMOS process, where the NPN is usually the
higher-performance device), but the specific circuit topology remains
schematic-entry work for a future issue, gated on #1.

`npn13G2`'s low breakdown voltage (`BVCEO` target 1.6 V) is adopted as a
**named, first-order design constraint**, not glossed over: any cascode or
output-buffer stage built around this core must treat the `BVCEO` ceiling
as load-bearing for device survival on a 3.3 V ±10% rail (see this repo's
`spec/porting-plan.md` §5 for why this differs from gf180 DR-0001's framing
of cascoding as a PSRR-only nicety), not merely a PSRR enhancement.

**`pnpMPA` is retained as a documented fallback**, not rejected outright.
If, once schematic entry starts, the NPN-topology redesign or the
`BVCEO` headroom constraint proves harder to close than expected, `pnpMPA`
lets the topology follow gf180/sky130's grounded-collector PNP-pair core
more literally — at the cost of a base-current error term roughly 10–15×
worse than either sibling's parasitic PNP (`BF ≈ 1.10` vs. `BF ≈ 16.6–19.4`),
which would need to dominate the untrimmed-accuracy budget in a way neither
sibling repo's error budget had to plan for.

## Alternatives considered

- **`pnpMPA`-based, literal PNP-pair port of the gf180/sky130 core shape.**
  Rejected as primary. It would minimize topology-porting risk (same
  grounded-collector core shape as both siblings) but forfeits the actual
  engineering opportunity this repo's premise is built on (a real bipolar
  device, per CLAUDE.md/README), and its BF ≈ 1.10 gain is worse than even
  the "parasitic" devices it would be imitating — trading one risk (topology
  redesign) for a strictly worse one (a low-gain base-current error term
  with no upside). Kept as documented fallback rather than discarded, since
  the NPN-topology risk is currently unverified (gated on #1).
- **`npn13G2`-based NPN-topology core (this decision).** Accepted. Uses the
  process's actual headline device, matches CLAUDE.md's framing of real
  bipolar devices as a genuine opportunity, and is honest about the cost
  (topology redesign, `BVCEO` headroom constraint) rather than assuming it
  away.
- **Dual-device core (using both `npn13G2` and `pnpMPA` together in one
  topology, e.g. an NPN core plus a PNP-based auxiliary/startup branch).**
  Rejected for wave 1 as unnecessary scope expansion — neither sibling
  repo's wave-1 core needed more than one bipolar device family, and
  introducing a second here before the first is even schematic-verified
  would compound two unverified topology choices (device count and device
  class) at once. Nothing forecloses a mixed approach at the design-entry
  stage if the schematic work in a future issue finds a concrete reason to
  add one; this record does not commit to or against that.
- **Deferring the call entirely until schematic entry.** Rejected — the
  issue explicitly asks for this decision to be made now, deliberately,
  ahead of tooling access, so schematic entry is not blocked on it once #1
  clears.

## Consequences

- **The bandgap core cannot be a literal port of either sibling's
  schematic.** `design/bandgap_core.sch`-equivalent work for this repo
  starts from an NPN-topology reference design, not a re-parameterized copy
  of gf180's Brokaw cell or sky130's Kuijk-style core. This is a real,
  larger-than-usual first-schematic-entry task relative to a same-topology
  port, and should be scoped accordingly when that issue is curated.
- **The `BVCEO ≈ 1.6 V` ceiling is now a stated constraint** any future
  output-stage/cascode design must close against, on top of the ordinary
  PSRR target — see `spec/porting-plan.md` §5 for the specific way this
  changes gf180 DR-0001's cascode reasoning.
- **sky130's fixed-geometry-PNP-array layout constraint does not
  automatically apply.** `npn13G2` has a native `Nx` emitter-multiplicity
  SPICE parameter (unlike sky130's fixed two-geometry PNP menu), which
  suggests area-ratio realization may be closer to gf180's directly-sizable
  device than to sky130's forced-array pattern — but this is a SPICE-model
  fact, not yet a confirmed layout-pcell fact (see `spec/porting-plan.md`
  §7, tooling-friction item 3). If `pnpMPA` is used instead (as fallback),
  the sky130-style array constraint re-applies, since `pnpMPA`'s fixed
  area/perimeter parameters offer no equivalent multiplier.
- **The HBT matching coefficient needed for an untrimmed-accuracy budget
  (`σ(dVBE) = k·A^-0.5`, process-spec condition `A.al`) is not published in
  the process-spec table itself** and must be pulled from
  `sg13g2_hbt_mod_mismatch.lib` once device-characterization work begins —
  analogous to what gf180's DR-0004 needed to do for its resistor mismatch
  coefficient, but for the bipolar device instead.
- **This decision is unverified in simulation.** No schematic, testbench,
  or `sim/` record exists yet for either device — this record fixes the
  device-selection call so that work is not repeatedly re-litigated once
  #1 clears, not a claim that the choice has been validated in sim. If
  schematic-level analysis later finds the NPN-topology redesign or the
  `BVCEO` constraint materially harder to close than expected, that finding
  should produce a superseding record, not a silent switch to `pnpMPA`.
