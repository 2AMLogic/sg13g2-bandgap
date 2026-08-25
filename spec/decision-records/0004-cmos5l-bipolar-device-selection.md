# 0004: SG13CMOS5L bipolar device selection — `pnpMPA`, grounded-collector core (mirrors gf180/sky130, not this repo's own SG13G2 core)

- **Status**: proposed (input to the SG13CMOS5L port's own future spec-ratification
  step; parallels how 0001/0002 are "proposed" pending this repo's own
  spec-ratification issue)
- **Date**: 2026-08-25
- **Decided by**: Builder agent, issue #64 (phase 1/4 of the SG13CMOS5L port,
  split from #63)
- **Related**: `0001-bipolar-device-selection.md` (the analogous SG13G2
  question this record extends/contrasts with — read first),
  `0002-supply-voltage-scope.md` (this record inherits its 3.3V HV-flavor
  supply choice unchanged), `spec/porting-plan.md` (the original SG13G2
  porting plan this record's sibling, `spec/porting-plan-sg13cmos5l.md`,
  extends for the CMOS5L branch), `2AMLogic/gf180-bandgap`
  `spec/decision-records/0001-bandgap-topology-selection.md` (the
  grounded-collector parasitic-PNP-pair precedent this record adopts),
  `2AMLogic/sky130-bandgap` `spec/topology-survey.md` (same precedent, same
  device class), issue #63 (parent, tracks all four phases), #65 (phase 2,
  depends on this record's device choice), #66 (phase 3, blocked on
  upstream `klt` SG13CMOS5L deck coverage, independent of this decision)

## Context

SG13CMOS5L (`~/share/pdk/ihp-sg13cmos5l`, IHP-GmbH's reduced-metal-stack
CMOS-only sibling process to SG13G2 — see that PDK's own `README.md`, "M1-
M4-TM1 stack") is the target for the Chipalooza port tracked by #63. This
repo's *existing* bandgap core (`design/bandgap_core.sch`, landed by issue
#9) is built around `npn13G2`, a real SiGe:C HBT — DR-0001's deliberate,
reasoned choice, made specifically because SG13G2 offers that device
"instead of the parasitic-PNP topology gf180-bandgap/sky130-bandgap use."

**SG13CMOS5L does not offer that device.** Verified directly against the
installed PDK checkout (2026-08-25):

- `libs.tech/ngspice/models/`: `sg13cmos5l_pnpMPA_mod.lib` /
  `sg13cmos5l_pnpMPA_stat.lib` — a PNP, `.model pnpMPA_mod pnp level=1`
  (Gummel-Poon), `bf = 1.10*sgp_mpa_bf` (i.e. current gain near unity,
  `sgp_mpa_bf` corner-scaled around 1.0 in `cornerPNP.lib`'s `typ`
  section) — model-card-identical in structure to the `pnpMPA` device
  DR-0001 read in SG13G2's own model deck and explicitly *rejected* as
  primary (kept only as "documented fallback"). There is no `npn13G2`
  device, model, or symbol anywhere in this PDK's tree.
- `libs.tech/xschem/sg13cmos5l_pr/`: no HBT symbol. The MOS symbols
  (`sg13_lv_nmos`/`pmos`, `sg13_hv_nmos`/`pmos`, plus test/RF variants) and
  `pnpMPA.sym` are present — as *symlinks* into a sibling `ihp-sg13g2`
  checkout (`../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/*.sym`),
  confirming these front-end devices are literally shared between the two
  processes at the SPICE/symbol level, differing only in back-end-of-line
  metal stack. This symlink structure is broken by default in an
  `ihp-sg13cmos5l`-only install (this PDK's own `README.md` documents it
  as needing to sit inside a combined `IHP-Open-PDK/{ihp-sg13g2,
  ihp-sg13cmos5l}` checkout) — see "Tooling/PDK friction" in
  `design/sg13cmos5l/README.md` for how this was worked around locally and
  the upstream `klayout-tools` issue filed for it. This is an environment/
  install-shape gap, not a device-availability fact — once resolved, the
  device menu is exactly what's described here.
- Caps: only `cap_cmomf.sym`/`cap_cmomi.sym` (MoM, real files — not
  symlinks) and `moscap_n.sym`/`moscap_p.sym` (MOS cap, symlinked from the
  same sibling). **No MIM cap symbol or model exists** in this PDK's tree.

So the device-topology question DR-0001 answered for SG13G2 (real HBT vs.
parasitic PNP) is not available to re-decide the same way here — the
"real HBT" branch of that choice does not exist in this process. What
*is* available is functionally the same low-gain `pnpMPA` device DR-0001
evaluated and rejected as SG13G2's primary bipolar device, now the *only*
bipolar device SG13CMOS5L offers.

## Decision

**Adopt `pnpMPA` as the bandgap-core bipolar device, wired
grounded-collector (base and collector tied together, that shared node
tied to `vss`; emitter driven from the PMOS mirror) — i.e. the same device
class and core topology shape gf180-bandgap's and sky130-bandgap's cores
use, not a re-parameterized copy of this repo's own `design/bandgap_core.sch`
(SG13G2's grounded-*emitter* NPN core).**

This is the mirror image of DR-0001's SG13G2 decision, and deliberately
so: DR-0001 chose `npn13G2` over `pnpMPA` specifically *because* SG13G2
offered a real HBT that neither sibling repo had access to. That reasoning
does not transfer to SG13CMOS5L, which has no HBT at all — the "different,
and different is part of the value here" framing DR-0001 used to justify
picking the unusual device does not apply to a process whose only bipolar
device is the same class of device both sibling repos already use. Given
that, following the siblings' well-precedented grounded-collector
parasitic-PNP-pair Brokaw-core shape is the right default: it is
mature, well-understood (both sibling repos' DR-0001-equivalent records
survey it in depth), and does not invent a novel topology to compensate
for a device class this process simply does not have.

**Topology, concretely** (see `design/sg13cmos5l/bandgap_core.sch` for the
full derivation in the schematic's own header — this record fixes the
device/topology *class* choice, not the final sizing):

- Three `pnpMPA` legs, each diode-connected (base tied to collector, tied
  to `vss` — the process's own model-card header, `DUT: diode_pp=pnpMPA`,
  suggests this device is characterized in exactly this configuration),
  emitter driven from a matched `sg13_hv_pmos` mirror leg (DR-0002: 3.3V HV
  flavor, unchanged by this record).
- Emitter-area ratio realized via the symbol's own `w`/`l` parameters
  (the model's `area = (w*l)*1e12` scaling is a standard SPICE BJT area
  multiplier, confirmed by reading `sg13cmos5l_pnpMPA_mod.lib`'s
  `.subckt pnpMPA c b e` directly — not the fixed-parameter case
  DR-0001 described for SG13G2's own `pnpMPA` reading, which was reading
  the *device's* fixed default, not its parametrization route). An 8:1
  ratio (`w=8u` on the PTAT leg vs. `w=1u` on the unit legs, `l=2u` fixed)
  is used, matching this repo's own SG13G2 core's `Nx=8` choice for
  continuity of the `VT*ln(8)` PTAT math between the two cores — not a
  claim that 8:1 is independently optimal for `pnpMPA`'s own error budget,
  which is unexamined at this phase.
- `rppd` (mild-TC precision resistor, same flavor DR-0001-era SG13G2 work
  and both sibling repos favor for ratio-critical legs) sums the PTAT
  `I*R1` term with the CTAT `VEB(Q3)` at `vref`, the same Brokaw sum every
  core in this fleet uses.

**No cascode, no trim, no compensation cap, no startup circuit, no error
amplifier in this phase** — `bandgap_core` only, matching the acceptance
criteria's "at minimum `bandgap_core`" bar and this repo's own SG13G2
`design/bandgap_core.sch` (issue #9) precedent of landing the core alone
first, loop-closing devices as later, separate work.

## MoM-cap-only constraint — flagged for phase 2, not resolved here

No MIM cap exists in this PDK (`cap_cmomf`/`cap_cmomi`, both MoM, are the
only fixed-value cap primitives; `moscap_n`/`moscap_p` are MOS caps). This
phase's `bandgap_core` schematic uses no capacitor at all — the open-loop
core has nothing to compensate yet. **This is named here as forward
guidance, not deferred silently**: when a future phase adds an error
amplifier (loop compensation) or an output filter, any cap sized there
must be a MoM device, and per the parent issue's own note, "MoM caps carry
no corner/mismatch spread in their models" in this PDK's deck — so any
such sizing should be flagged for a dedicated sensitivity sweep (a phase-2
task, tracked implicitly by #65's "any MoM-cap-dependent spec row ...
explicitly marked `insufficient-evidence`" acceptance criterion) rather
than trusted as a clean PVT-swept result the way `rppd`/`sg13_hv_pmos`
corners currently are.

## Alternatives considered

- **A grounded-emitter NPN core, re-parameterized from this repo's own
  `design/bandgap_core.sch`.** Not available — SG13CMOS5L has no NPN HBT
  or any other NPN device to redraw that topology around. Not a real
  alternative, listed only to be explicit about why the "port the existing
  SG13G2 schematic" default does not apply here the way it might for a
  device-menu superset process.
- **A Banba-style or other sub-1V current-summing topology.** Rejected for
  the same reason gf180-bandgap's DR-0001 rejected it: this process's HV
  flavor gives ample 3.3V headroom (DR-0002), so sub-1V operation buys
  nothing and only adds current-mirror matching-group risk, which is
  exactly the wrong tradeoff for `pnpMPA`'s already-low, poorly-matched
  gain (`bf ≈ 1.1`).
- **Deferring the device-topology call to phase 2 (sim) or phase 3
  (layout).** Rejected — the parent issue (#63) and this phase's own
  acceptance criteria ask for this decision now, before #65's PVT
  testbenches and #66's layout work have anything concrete to build
  against, mirroring DR-0001's own "decide deliberately, ahead of the next
  phase" framing for SG13G2.

## Consequences

- **`design/sg13cmos5l/bandgap_core.sch` is a genuinely new schematic, not
  a re-parameterized copy of either `design/bandgap_core.sch` (this repo's
  own SG13G2 core) or a byte-for-byte port of a sibling repo's core** — it
  follows the sibling repos' topology *shape* (grounded-collector PNP
  pair) using this PDK's own device parametrization (`w`/`l`-scaled area,
  not sky130's fixed-geometry array or gf180's vertical-PNP substrate-tie
  convention).
- **`pnpMPA`'s low gain (`bf ≈ 1.1`) is inherited as a first-order
  base-current error term**, the same DR-0001 already named for SG13G2's
  own fallback-only reading of this device — this is now the *primary*
  device for SG13CMOS5L, not a fallback, so that error term is load-bearing
  here in a way it never became for SG13G2 (which used the real HBT
  instead). Untrimmed-accuracy budgeting against this is out of this
  phase's scope (no `sim/`-grade PVT sweep yet — that is #65).
- **The MoM-cap-only constraint does not bind on this phase's schematic**
  (no cap used), but is now a named, forward-tracked constraint for
  whichever future phase adds loop compensation — see the section above
  and #65's acceptance criteria.
- **This record does not change DR-0001 or DR-0002.** DR-0001 remains the
  correct, ratified-status record for SG13G2's own core; DR-0002's 3.3V HV
  supply-flavor scoping is inherited unchanged by this SG13CMOS5L branch
  (see `spec/porting-plan-sg13cmos5l.md` §1).
- **This decision is unverified against a full PVT sweep.** Only an
  informal, single-nominal-point DC check has been run in this
  environment (documented in `design/sg13cmos5l/README.md`, matching the
  "informal, NOT `sim/` evidence" discipline this repo's `design/README.md`
  already established for SG13G2's own first-pass core) — #65 is the
  issue that grounds this in real `sim/`-evidence PVT-corner results.
