# Chipalooza Challenge #2 — sign-off proposal: SG13CMOS5L bandgap voltage reference

**Status: layout + post-layout PVT sim landed; not a finished sign-off.**
This document covers phases 1/4-3/4 of the SG13CMOS5L port (issue #63):
device-topology decision + schematic capture (#64/#68), PVT-cornered
pre-layout simulation (#65), and layout + post-layout PVT simulation
(#81/#84). The Challenge #2 brief's full bar (schematic + pre-layout sim ->
layout + post-layout sim over PVT -> DRC/LVS-clean GDS,
open-source-EDA-verifiable) is **not yet fully met** — DRC is clean, but
LVS reports a fully-attributed `mismatch` against `klayout-tools`' curated
SG13CMOS5L deck's known starter-scope gaps, not a real circuit defect — see
"Sign-off status against the brief" below for the complete, per-stage
breakdown. This document proposes the block and reports what has been
verified so far, honestly bounded by what has not.

Block-only document: no personal or institutional detail below, per the
epic's (2AMLogic/2am#542) Tier 1 disclosure scope.

## 1. Block type and positioning

**This is a reference block offered as a better-or-independent bandgap
option, not a slot-filling novelty.** The Challenge #2 harness already
supplies its own 1.2V bandgap and bias currents, so this block's job is
not to fill an otherwise-empty slot — it is a second, independently
verified analog voltage reference built around a real bipolar-junction
core (a grounded-collector parasitic-PNP Brokaw pair, not a resistor
divider or a purely digital trimmed reference), suitable for on-die
cross-check, redundancy, or direct substitution for the harness-default
reference if a design elects to use it instead.

The core, error amplifier, and startup circuit are each independently
PVT-cornered (temperature x supply x process, 45-point grids) with
**45/45 points passing** in every one of the three testbenches landed for
this phase (see section 4). That is offered as the block's positioning
argument: a small, closed-loop, self-starting analog macro with real
verification evidence behind it, not just a schematic.

## 2. I/O mapped to the Challenge #2 slot budget

The assembled block (`design/sg13cmos5l/bandgap_top.sch`) exposes exactly
three pins today:

| Pin | Direction | Role |
|---|---|---|
| `vdd` | power | 3.3V HV-flavor analog supply (see section 3 and section 5 for why 3.3V, not 1.2V) |
| `vss` | power | ground |
| `vref` | analog output | the bandgap reference voltage |

Mapped against the brief's slot budget (≤24 digital control inputs, ≤12
digital test outputs, ≤4 shared analog lines, 0-4 dedicated pads,
template wrapper cell):

| Budget category | Used | Notes |
|---|---|---|
| Digital control inputs | **0 / 24** | No enable, trim, or mode pin exists in the current schematic — the block is unconditional and self-starting once `vdd` is applied (see section 4's startup evidence). Adding a trim or enable input is a candidate future increment, not assumed here. |
| Digital test outputs | **0 / 12** | No digital status/flag signal exists. |
| Dedicated pads (preferred) | **1 / 4** | `vref` is the block's only analog signal requiring external access. A dedicated pad is the preferred routing for it, since a shared analog mux bus adds switch leakage/loading on what is otherwise a low-current, high-impedance reference node (`i_leg3` ~5 uA per the core's own bias current, section 4) — that loading is not characterized against this block's output impedance. |
| Shared analog lines (fallback) | **1 / 4** | If dedicated pads are oversubscribed by other Challenge #2 participants, `vref` degrades gracefully to 1 of the 4 shared analog lines instead of a dedicated pad. |

`vdd`/`vss` are assumed supplied from the harness's shared global analog
rails (3.3V/ground) rather than counted against either digital or analog
per-block slot budgets, consistent with the brief's framing that the
harness already carries shared bias/supply infrastructure for its own
default bandgap. **This is an assumption, not a fact confirmed against the
brief text**, which does not detail per-block power delivery; it is
flagged here as an open question for harness integration rather than
asserted as settled.

Total slot-budget usage proposed: **0 digital control inputs, 0 digital
test outputs, 1 shared analog line or 1 dedicated pad** — well inside
every ceiling the brief sets.

## 3. Functional description

`design/sg13cmos5l/bandgap_top.sch` wires three sub-blocks
(`design/sg13cmos5l/README.md` has the full account; summarized here):

- **`bandgap_core.sch`** (issue #64, `spec/decision-records/0004-cmos5l-bipolar-device-selection.md`)
  — three `pnpMPA` legs (a parasitic-style PNP, the only bipolar device
  SG13CMOS5L offers — see decision record DR-0004), each diode-connected
  with base and collector tied to `vss` (grounded-collector), emitter
  driven from a matched `sg13_hv_pmos` current-mirror leg. An 8:1
  emitter-area ratio between the PTAT leg and the unit legs produces a
  PTAT delta-VEB across `rppd` precision resistor `R2`; `R1` sums that
  PTAT term with the CTAT `VEB` of the third leg at the `vref` node — the
  same Brokaw-cell summing structure this repo's SG13G2 core and both
  sibling repos (`gf180-bandgap`, `sky130-bandgap`) use.
- **`bandgap_amp.sch`** (issue #68) — an error amplifier that forces the
  core's two sense nodes (`sns1`, `sns2`) equal, closing the loop that the
  core alone leaves open (`core.sns1 -> amp.in_n`, `core.sns2 ->
  amp.in_p`, `amp.out -> core.fb`).
- **`bandgap_startup.sch`** (issue #68, ported unchanged from this repo's
  own SG13G2 startup circuit — no bipolar device, so the port needed only
  a symbol-library path change) — a current-sensing kick circuit that
  pulls the mirror on at cold start and self-disengages once the core is
  running, sharing `sns1` and `fb` with the core.

No cascode, trim network, compensation capacitor, or digital control
exists at this phase. The PDK offers no MIM capacitor (only MoM
`cap_cmomf`/`cap_cmomi` and MOS caps) — any future compensation or filter
cap must be a MoM device, whose SPICE models carry no corner or mismatch
spread (`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`);
that is flagged there as forward guidance for whichever future phase adds
one, not resolved in this phase.

## 4. Spec table

**No ratified SG13CMOS5L accuracy target exists yet**
(`spec/porting-plan-sg13cmos5l.md`, "Status: engineering input, not a
ratified decision"). Rows below are re-derived directly from issue #65's
three PVT-cornered `sim/` records (all dated 2026-08-25, commit
`8361d0d`, all 45/45 points **PASS**) — none are copied from this repo's
own SG13G2 target table (`README.md`) without independent re-derivation
against this evidence, and any row this evidence does not support is
marked `insufficient-evidence`/`unmet` rather than omitted or silently
relaxed, per this repo's evidence discipline (`CLAUDE.md`).

Both brief rails are addressed explicitly: this block is an **analog-only
block instantiating no device against the harness's 1.2V digital rail** —
it uses only the 3.3V HV-flavor analog rail (`sg13_hv_pmos`, DR-0002's
choice, inherited unchanged by DR-0004; confirmed directly in
`sim/sg13cmos5l-core-open-loop-bias/README.md`). The 1.2V row below is
marked `N/A` for that reason, not `unmet` or omitted.

| Parameter | Min | Typ | Max | Status | Evidence |
|---|---|---|---|---|---|
| Output reference voltage, `vref` @ vdd=3.3V, full temp x process grid | 1.18974 V (wcs, 125 C) | 1.19687 V (typ, 27 C) | 1.19961 V (bcs, -40 C) | Falls inside this repo's own SG13G2 *draft, unratified* +-1% envelope around 1.2V (1.188-1.212 V) across every one of the 15 points swept at vdd=3.3V — informal comparison only, since no CMOS5L target itself is ratified | `sim/sg13cmos5l-closed-loop-startup/records/20260825-203907-8361d0d.csv` (45/45 PASS); full 5-corner x 3-temp x 3-vdd grid, `vref_final_v` column |
| Supply operating range, 3.3V analog rail | 2.97 V | 3.30 V | 3.63 V | **Met** — self-starts and reaches closed-loop equilibrium at all 3 swept supply points, every temperature/process corner (45/45 PASS) | Same record as above |
| Supply operating range, 1.2V digital rail | -- | -- | -- | **N/A** — analog-only block, instantiates no device against the LV digital rail (confirmed, `sim/sg13cmos5l-core-open-loop-bias/README.md`) | n/a |
| Self-start | -- | -- | -- | **Met** (self-starts): startup circuit releases (`v(det) <= 0.2*vdd`, `\|i(XMKFB)\| <= 50 nA`) and the loop closes (`\|sns1-sns2\| <= 20 mV`) within the 2 ms transient window, all 45 PVT points. **Insufficient-evidence** for a specific settling-time bound (e.g. "< 1 ms"): the testbench checks end-state at a fixed 2 ms sample, it does not record the crossing time, so no settling-time number can be reported without inventing one | `sim/sg13cmos5l-closed-loop-startup/` (as above) |
| Temperature coefficient (-40..125 C) | -- | -- | -- | **Insufficient-evidence** — no dedicated TC testbench exists (issue #65's three testbenches measure startup/loop-closure/open-loop-bias endpoints, not TC). See note below for informal, non-spec context computed from the same raw data. | none dedicated |
| PSRR @ DC | -- | -- | -- | **Insufficient-evidence** — no AC/PSRR testbench exists; `bandgap_amp.sch` has no compensation capacitor yet, so a loop-stability/PSRR measurement is not yet meaningful (`design/sg13cmos5l/README.md`, "Not attempted") | none |
| Line regulation | -- | -- | -- | **Insufficient-evidence** — no dedicated line-regulation testbench (DC operating-point sweep across supply, not a regulation-bandwidth measurement). See note below for informal context. | none dedicated |
| Load regulation | -- | -- | -- | **Insufficient-evidence** — no testbench sweeps an external load on `vref` at all | none |
| Quiescent current, `Iq` | -- | -- | -- | **Insufficient-evidence** — the only current data landed (`sim/sg13cmos5l-core-open-loop-bias/`) measures branch currents in an *open-loop* fixture with an externally forced 5 uA reference leg, not the assembled block's real self-biased supply current; not a valid `Iq` measurement | none valid |

**Informal, non-spec context (explicitly not a qualified measurement, no
row above claims these numbers as a spec result):**

- Computed directly from `sim/sg13cmos5l-closed-loop-startup`'s own raw
  `vref_final_v` values at the `typ`/`mos_tt`/`res_typ` corner, vdd=3.30V:
  -40 C = 1.19745 V, 27 C = 1.19687 V, 125 C = 1.19093 V. A box-method
  calculation over this single process corner gives roughly
  `(1.19745 - 1.19093) / (1.19687 * 165) ~= 33 ppm/°C`. This is *not* a
  qualified TC measurement — no dedicated TC testbench exists, the
  underlying testbench was built to check startup/loop-closure endpoints,
  and this number mixes whatever convergence-aid artifacts
  (`rshunt=1e9`, `gmin=1e-9`) that testbench's own README documents as
  needed for numerical stability at the ramp instant. Reported only for
  order-of-magnitude orientation.
- Similarly, at `typ`/27 C across the swept vdd grid: 2.97V = 1.19644 V,
  3.30V = 1.19687 V, 3.63V = 1.19712 V, giving a rough line sensitivity of
  `~1.0 mV/V` (`~0.09 %/V`) at this single corner/temperature — again
  informal context only, not a line-regulation spec claim (that requires
  a dedicated small-signal or fast-sweep testbench this phase does not
  have).

## 5. Sign-off status against the brief

| Brief stage | Status |
|---|---|
| Schematic + pre-layout sim | **Done.** `design/sg13cmos5l/bandgap_top.sch` (+ `bandgap_core`/`bandgap_amp`/`bandgap_startup`) captured (issues #64, #68); three PVT-cornered pre-layout testbenches landed with 45/45 PASS each (issue #65, section 4 above). |
| Layout + post-layout sim over PVT | **Done, with a disclosed gap.** `layout/sg13cmos5l-bandgap_top/` assembled from the three leaf cells (issue #81); post-layout (PEX) re-simulation of all 14 MOS devices' real drawn geometry across the same 45-point PVT grid lands 45/45 PASS (issue #84, `sim/sg13cmos5l-closed-loop-startup-pex/`). No wire (metal) parasitics are modelled — `klt extract --deck sg13cmos5l --parasitics` fails outright on a `klayout-tools` deck-registry bug found and filed this pass ([klayout-tools#1440](https://github.com/2AMLogic/klayout-tools/issues/1440)) — so this is device-geometry PEX evidence, not the wire-RC-inclusive claim the SG13G2 side carries (issue #37). See `sim/sg13cmos5l-closed-loop-startup-pex/README.md` for the full disclosure. |
| DRC/LVS-clean GDS, in-repo, open-source-EDA-verifiable | **DRC clean; LVS is not literally clean.** `layout/sg13cmos5l-bandgap_top/drc_report.json` reports `clean`, 0 violations. `lvs_report.json` reports `status: "mismatch"` (51 findings), but every finding is fully attributed to four documented starter-deck limitations (no bipolar/resistor device recognition, no HV MOS flavour, no well/substrate tap — each independently filed against `klayout-tools`), not a real connectivity defect in this layout — see `layout/README.md`'s "SG13CMOS5L: LVS" section for the full attribution. The brief's bar as literally worded ("LVS-clean") is therefore not fully met; the gap is a young open-source deck's coverage limit, disclosed and tracked upstream, not a circuit or layout error. |

The brief's full sign-off bar requires all three stages. Schematic + pre-layout
sim (stage 1) and layout + post-layout PVT sim (stage 2) are both landed;
stage 3 (a literally LVS-clean GDS) remains open pending the `klayout-tools`
deck-coverage gaps named above — this document should still be read as
reporting real, PVT-cornered verification evidence with every caveat
disclosed, not as a completed, unconditional Challenge #2 submission.

## 6. Bench test plan (for measured silicon, if/when it returns)

None of the rows below exist yet — this is a plan for what a bring-up
bench would need to run, not a report of results:

1. **DC output voltage vs. temperature** — thermal chamber or thermal
   stream, precision digital multimeter (>=6.5 digit) on `vref`, swept
   across the full qualification temperature range at fixed `vdd`. Repeat
   across multiple packaged units to separate process spread from
   per-unit TC.
2. **Temperature coefficient** — derive from (1) using the standard
   box-method or least-squares-fit TC extraction across measured units;
   compare against whatever accuracy target is ratified by the time
   silicon returns (none exists today — see section 4).
3. **Line regulation** — sweep `vdd` across the qualified 3.3V +-10% range
   (2.97-3.63V) at fixed temperature and load, measure `vref` with the
   same precision multimeter; repeat at temperature extremes.
4. **Load regulation** — if the harness exposes `vref` to an external
   load (electronic load or resistive divider), sweep load current and
   measure `vref` droop; requires knowing the harness's actual output
   buffering/loading path, which this document does not assume.
5. **PSRR** — inject a calibrated AC ripple on the 3.3V analog rail (network
   or spectrum analyzer, or a dedicated ripple-injection fixture) and
   measure `vref`'s AC response across frequency, once a compensation
   capacitor exists in a future `bandgap_amp.sch` revision — the current
   schematic has no compensation cap, so an on-die PSRR measurement
   without one would not represent a stability-qualified design.
6. **Quiescent current** — measure total DC current drawn from the 3.3V
   supply at each temperature/supply corner with the block otherwise
   idle, using a precision current-sense path (shunt + multimeter, or a
   supply with built-in current metering) — this is the missing
   measurement section 4 flags as `insufficient-evidence` even in
   simulation.
7. **Startup / settling time** — oscilloscope on `vref` (and, if
   accessible, the startup circuit's internal `det`/`fb` nodes) during a
   `vdd` power-up ramp, to capture an actual settling-time number — the
   simulated evidence in section 4 only confirms end-state pass/fail at a
   fixed 2 ms sample, not a measured settling time.
8. **Unit-to-unit (process/mismatch) spread** — across a reasonable
   sample size of packaged/measured units, report `vref` mean and sigma
   at a fixed temperature/supply condition; no Monte Carlo simulation
   exists yet for this block (see `design/sg13cmos5l/README.md`, "Not
   attempted"), so measured silicon would be the first mismatch data
   point of any kind for this design.

## References

- `design/sg13cmos5l/README.md` — schematic capture account (issues
  #64/#68), including the informal single-nominal-corner check that
  preceded the formal PVT sweep.
- `spec/decision-records/0004-cmos5l-bipolar-device-selection.md` (DR-0004)
  — device/topology decision.
- `spec/porting-plan-sg13cmos5l.md` — porting plan, explicitly not a
  ratified spec.
- `sim/sg13cmos5l-closed-loop-startup/`, `sim/sg13cmos5l-core-open-loop-bias/`,
  `sim/sg13cmos5l-startup-trip-point/` — the three PVT-cornered testbenches
  this document's spec table draws from (issue #65).
- Issue #63 (parent, tracks all four phases), #64, #65, #66, #68.
