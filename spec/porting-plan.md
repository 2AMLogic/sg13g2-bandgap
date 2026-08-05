# Porting plan — what carries over from gf180-bandgap and sky130-bandgap

**Status: engineering input, not a ratified decision.** This document is the
required reading for anyone starting design work on this block once the
`klt` PDK resolver (#1) unblocks tooling. It does not ratify the target spec
— that remains a future spec-ratification issue, as in both sibling repos —
but it does record two decisions this issue was scoped to make (see
[`decision-records/0001-bipolar-device-selection.md`](decision-records/0001-bipolar-device-selection.md)
and
[`decision-records/0002-supply-voltage-scope.md`](decision-records/0002-supply-voltage-scope.md)).

**Sources checked** (read first, per the issue body, rather than starting
from a blank page):

- `2AMLogic/gf180-bandgap` `spec/decision-records/0001-bandgap-topology-selection.md`,
  `0002-supply-voltage-scope.md`, `0003-target-spec-ratification.md`,
  `0004-par-r-mismatch-coefficient-risk.md` — the most mature block in the
  fleet, DRC/LVS-clean.
- `2AMLogic/sky130-bandgap` `spec/topology-survey.md`,
  `spec/decision-records/DR-001-supply-flavor-scope.md`,
  `DR-002-trim-network-scoping.md` — the existing CMOS-PDK port, and
  therefore the best evidence of what porting a bandgap actually costs.
- `IHP-GmbH/IHP-Open-PDK`, `main` branch, commit `22f2a25` (2026-08-05) —
  read directly for this issue, since neither sibling repo's device menu
  is SG13G2's: `ihp-sg13g2/libs.doc/doc/SG13G2_os_process_spec.pdf` (Rev.
  1.2), `ihp-sg13g2/libs.tech/ngspice/models/sg13g2_hbt_mod.lib`,
  `.../sg13g2_moslv_mod.lib`, `.../sg13g2_moshv_mod.lib`, and the
  `ihp-sg13g2/libs.tech/xschem/sg13g2_pr/` symbol directory. All device
  numbers below are static SPICE model-card / process-spec table values
  read from this checkout, not simulation output — consistent with
  CLAUDE.md's "no claim without a testbench" for anything presented as
  measured/simulated data. **Re-verify against the PDK checkout actually
  resolved by `klt` once #1 clears** — a public-repo `main` read today is
  not guaranteed to be byte-identical to whatever revision the tooling
  eventually pins.

## 1. What carries over unchanged

The port is deliberately conservative: change the devices, not the design
philosophy. What both sibling repos establish, and what this repo inherits
directly:

- **The verification discipline.** PVT-cornered testbenches
  (−40/27/125 °C × supply × process corner), append-only `sim/` records, no
  claim without a testbench (`CLAUDE.md`, `sim/README.md` conventions in
  both siblings). Nothing about SG13G2 changes this.
- **The decision-record process itself.** One decision per record, numbered
  sequentially, never rewritten once ratified — superseded instead. This
  repo adopts gf180's `NNNN-<slug>.md` numbering (rather than sky130's
  `DR-NNN-<slug>.md`) purely because it is the elder of the two conventions
  cited in the issue; nothing about the choice is load-bearing, and either
  reads identically once files exist. See
  [`decision-records/TEMPLATE.md`](decision-records/TEMPLATE.md).
- **The friction protocol.** Tool gaps get filed generically against
  `klayout-tools`, design specifics stay out of that tracker — unchanged by
  which PDK triggered the gap.
- **The general shape of a bandgap-core spec.** Output reference (~1.2 V),
  temperature coefficient, PSRR, supply, quiescent current, area, startup —
  the same seven-row target-spec shape both siblings use survives the port;
  only the numeric values and the device-flavor framing under "Supply" need
  reconsidering (§4, §6).
- **The resistor-flavor pattern, structurally.** Both gf180 (`rpolyh` etc.)
  and sky130 (`res_high_po` mild-TC vs. `res_xhigh_po` strong-opposite-sign-TC,
  higher-sheet-resistance) ship more than one poly-resistor flavor with a
  deliberate TC-vs-density tradeoff, and both survey documents conclude the
  milder-TC flavor is the right default for ratio-critical PTAT/CTAT legs.
  SG13G2 has the same *shape* of tradeoff — see §2.
- **The device-mismatch-first methodology**, not the numbers. Both DR-0004
  (gf180, resistor mismatch coefficient risk) and DR-002 (sky130, MC-driven
  trim scoping) show the fleet's practice of grounding accuracy claims in
  measured/simulated mismatch data rather than asserted specs. SG13G2 ships
  its own device-family mismatch decks (`sg13g2_hbt_mod_mismatch.lib`,
  `sg13g2_moslv_mod_mismatch.lib`, `sg13g2_moshv_mod_mismatch.lib`,
  `resistors_mod_mismatch.lib`) and the process spec documents a
  `σ(dVBE) = k·A^-0.5` HBT matching-coefficient measurement (condition
  `A.al`, at `VBE=0.7V, VCB=0V`) directly analogous to what DR-0004 needed
  for gf180's resistors — the *method* transfers; the coefficient `k` does
  not appear in the process-spec table itself and must be pulled from the
  mismatch model card once device-characterization work starts.

## 2. What changes, and why

| Aspect | gf180 / sky130 | SG13G2 | Why it changes |
|---|---|---|---|
| Bipolar device | Parasitic vertical/substrate PNP (gf180's only bipolar device; sky130's `pnp_05v5`, BF ≈ 16.6–19.4, grounded-collector, only two fixed unit geometries) | Real SiGe:C HBT NPN (`npn13G2`, VBIC Rev. 1.15, BF target 650, min 300 — see §3) **plus** a separate, much lower-gain PNP (`pnpMPA`, Level-1 Gummel-Poon, BF ≈ 1.10) | This is the process's headline difference (`CLAUDE.md`, README) — see [DR-0001](decision-records/0001-bipolar-device-selection.md). |
| MOS voltage flavors | gf180: 3.3V-primary only (DR-0002). sky130: 1.8V core / 3.3V I/O (thick-oxide), DR-001 scoped to 3.3V-primary for wave 1 | 1.2V core (`sg13_lv_nmos/pmos`, `V_GS ≤ 1.65V @125°C`) / 3.3V I/O (`sg13_hv_nmos/pmos`, `V_GS ≤ 3.3V Maximum`) — **no 1.8V-rated device family exists in this PDK** | The README's draft "1.8 V / 3.3 V" Supply row inherited a number that does not match any SG13G2 device flavor — see [DR-0002](decision-records/0002-supply-voltage-scope.md). |
| Poly resistor flavors | gf180: `rpolyh` (+ alternatives, DR-0004). sky130: `res_high_po` (TC1 ≈ +514 ppm/°C, ~330 Ω/sq) vs. `res_xhigh_po` (TC1 ≈ −1470 ppm/°C, ~2000 Ω/sq, ~6× denser) | Three flavors: `Rsil` (salicided, TC1 ≈ +3100 ppm/°C, ~7 Ω/sq — low-R, strong positive TC), `Rppd` (unsalicided p+ poly, TC1 ≈ +170 ppm/°C, ~260 Ω/sq — the mild-TC precision candidate, PDK explicitly recommends ≥2 µm line width "for realizing precision resistors"), `Rhigh` (unsalicided, partially compensated, TC1 ≈ −2300 ppm/°C, ~1360 Ω/sq — high-density, strong opposite-sign TC) | Same *shape* of tradeoff as sky130's two-flavor menu (mild-TC/precision vs. dense/strong-TC), but a third flavor and different numeric TCs/sheet resistances — device sizing cannot be copied numerically, only the flavor-selection *reasoning* (mild-TC flavor for ratio-critical legs) transfers. `Rppd` is this repo's analog to sky130's `res_high_po` / gf180's `rpolyh`; `Rsil`'s very strong positive TC (~10× `Rppd`'s) makes it a poor ratio-leg candidate despite its low resistance. |
| Emitter-area ratio realization | sky130: **no continuously-sized PNP** — only two fixed unit geometries; any N:1 ratio must be built as a unit-device array. gf180: single vertical PNP, sized directly. | `npn13G2` is natively parametrized by an emitter-multiplicity factor `Nx` (1–10, `m=1` instancing) in its own SPICE subckt — closer to gf180's directly-sizable device than sky130's fixed-array constraint. `pnpMPA`, if used instead (§3), has fixed default area/perimeter parameters (`a`, `p`) with no equivalent multiplier — an N:1 ratio on `pnpMPA` would need sky130-style external unit-device paralleling. | Whether the fixed-array layout constraint applies at all depends on the bipolar-device decision (§3) — it is not a fixed fact of this PDK the way it is for sky130. |
| MOS naming/class split | gf180: single 3.3V flavor. sky130: `nfet_01v8`/`pfet_01v8` (1.8V core) vs. `nfet_g5v0d10v5`/`pfet_g5v0d10v5` (5V gate / 10.5V drain, used at 3.3V) | `sg13_lv_nmos`/`sg13_lv_pmos` (1.2V core, PSP 103.6 model) vs. `sg13_hv_nmos`/`sg13_hv_pmos` (3.3V I/O) | Same two-oxide pattern as both siblings (every PDK in the fleet ships a core/IO split); only the cell names and voltage numbers differ — low-friction to port. |

## 3. Bipolar-versus-parasitic call

**Recorded in
[`decision-records/0001-bipolar-device-selection.md`](decision-records/0001-bipolar-device-selection.md).**
Summary: SG13G2's NPN (`npn13G2`) is a genuine, high-performance SiGe:C HBT
(VBIC Rev. 1.15 model, current-gain target `BF = 650`, min 300, max 1200,
per the process spec's Bipolar Parameters table) — categorically different
from a "parasitic" device, and categorically better-characterized than
either sibling's parasitic PNP. But it is **NPN-only, with a low
emitter-collector breakdown voltage** (`BVCEO` target 1.6 V, min 1.4 V, for
the standard flavor) — well below the 3.3 V primary rail this repo is
adopting (§4). Using it means redrawing the bandgap core around a
grounded-emitter NPN rather than the grounded-collector PNP pair both
sibling repos' Brokaw/Kuijk-style cores use — a genuine topology change, not
a device swap into the existing schematic shape.

SG13G2 also ships `pnpMPA`, a PNP built on a Level-1 Gummel-Poon model with
`BF ≈ 1.10` — an order of magnitude *worse* current gain than either
sibling's parasitic PNP (sky130's `pnp_05v5`: BF ≈ 16.6–19.4). It would let
the port be more literal (same grounded-collector PNP-pair core shape as
gf180/sky130), at the cost of a base-current error term worse than either
CMOS port's baseline.

The decision record adopts `npn13G2` as the primary bandgap-core device —
"different, and different is part of the value here," per the issue body —
with `pnpMPA` kept as a documented fallback. See the record for the full
reasoning, alternatives considered, and consequences (notably: the
`BVCEO ≈ 1.6 V` ceiling becomes a first-order constraint on any cascoded
output stage, not merely a PSRR nice-to-have as in gf180's DR-0001).

## 4. Supply target

**Recorded in
[`decision-records/0002-supply-voltage-scope.md`](decision-records/0002-supply-voltage-scope.md).**
Summary: the README's draft Supply row ("1.8 V / 3.3 V — confirm against
SG13G2 flavors") inherited a number that matches neither of this PDK's two
actual device flavors (1.2 V LV core, 3.3 V HV I/O — confirmed against the
process spec's HV-NMOS/HV-PMOS tables, `V_GS ≤ 3.3V Maximum`, and the LV
tables, `V_GS ≤ 1.65V @125°C`). The decision record adopts **3.3 V (HV
flavor) as the wave-1 primary target**, matching gf180's precedent and
giving the topology headroom that neither of the two SG13G2 bipolar options
(§3) can be assumed to use comfortably without cascoding. The 1.2 V LV core
is named as the analog of sky130's "Stretch" column for a possible future
wave — explicitly **not** 1.8 V, since no 1.8V-rated device family exists in
this PDK's menu.

## 5. What does not transfer, and why

- **The literal Brokaw/Kuijk core schematic (both siblings).** Both cores
  are built around a matched, grounded-collector PNP pair. If DR-0001's
  `npn13G2` choice is carried into schematic entry, the core is a
  grounded-*emitter* NPN topology — a different circuit, not a
  re-parameterized copy of either sibling's `design/bandgap_core.sch`.
- **sky130's fixed-geometry-PNP-array layout constraint.** This drove a
  real layout/mismatch decision in sky130 (`spec/topology-survey.md`:
  "any emitter-area ratio... must be built by paralleling multiple unit
  devices"). It does not automatically apply here: `npn13G2` has a native
  `Nx` emitter-multiplicity parameter, closer to gf180's directly-sizable
  device. It would re-apply only if the fallback `pnpMPA` device is chosen
  instead (§2 table) — worth re-checking once schematic entry starts,
  since the SPICE-level `Nx` parameter says nothing about whether the
  layout pcell for `npn13G2` actually draws N independently placeable,
  common-centroid-able emitter stripes for `Nx > 1`, or merely scales a
  single device's model parameters (see §7, tooling-friction item 3).
- **gf180 DR-0001's "cascode for PSRR, not survival" framing.** gf180's
  topology record treats a cascoded current-mode output stage as a
  strictly additive PSRR improvement, affordable because gf180's parasitic
  PNP has ample headroom on the 3.3V rail. That framing does not transfer
  if `npn13G2` is the core device: with `BVCEO ≈ 1.6 V`, a cascode (or
  equivalent breakdown-protection structure) becomes load-bearing for
  device survival on a 3.3 V ±10% rail, not merely a PSRR bonus. Whoever
  designs the output stage needs to re-derive this budget from SG13G2's
  numbers, not inherit gf180's conclusion that headroom is "not scarce."
- **sky130 DR-001's 1.8 V-stretch-flavor framing.** sky130 defers a
  structurally distinct 1.8 V Banba-style core as future stretch work.
  SG13G2 has no 1.8V-rated device family at all (§4), so there is no
  equivalent "sub-1V on the low-voltage core" stretch goal to defer in the
  same shape — if a future SG13G2 stretch flavor is pursued, it would sit
  on the 1.2 V LV core, a different voltage point with different headroom
  characteristics than sky130's 1.8V stretch, and would need its own
  topology survey rather than inheriting sky130's Banba recommendation.
- **Every sibling repo's numeric mismatch/trim evidence.** gf180 DR-0004's
  `par_r = 0.021` resistor-mismatch risk bound and sky130 DR-002's
  downward-only trim-range finding (`n_r2_trim` collapsing the `ff`/2.97V
  operating point) are measured results specific to those processes'
  device decks. Nothing about either numeric conclusion transfers to
  SG13G2 — only the practice of measuring rather than assuming a
  mismatch/trim budget transfers. SG13G2's own mismatch decks
  (`sg13g2_hbt_mod_mismatch.lib`, `sg13g2_moslv_mod_mismatch.lib`,
  `sg13g2_moshv_mod_mismatch.lib`, `resistors_mod_mismatch.lib`) and the
  process spec's `A.al` HBT matching-coefficient condition are the inputs
  a future device-characterization issue would use to redo this work from
  scratch.
- **gf180's single-bipolar-device simplicity.** gf180 has exactly one
  bipolar device, so "which bipolar device" was never a design question
  there. SG13G2's two-bipolar-device menu (§3) is a genuinely new decision
  axis neither sibling repo's process forced — the porting-plan process
  itself had to grow a step (DR-0001) that neither predecessor needed.

## 6. Draft spec targets against SG13G2's real devices

| Parameter | Target (SG13G2, draft) | Basis |
|---|---|---|
| Output reference | ~1.2 V ±1% untrimmed | Carried over unchanged from both siblings as a starting target — SG13G2-specific offset/mismatch analysis (needs `npn13G2`'s VBE at the chosen operating current, plus the `A.al` matching coefficient once pulled from the mismatch deck) has not been done; this number is not yet grounded in SG13G2 simulation the way the siblings' ratified tables are. |
| Temp coefficient (−40…125 °C) | < 50 ppm/°C | Carried over unchanged; not yet SG13G2-verified. |
| PSRR @ DC | > 60 dB | Carried over unchanged; note from §3/§5 that whatever cascode/output stage is needed to hit this must simultaneously respect `npn13G2`'s `BVCEO ≈ 1.6 V` ceiling if that device is used — a joint constraint the sibling repos did not have to solve. |
| Supply | **3.3 V ±10% (HV flavor)** — see §4, DR-0002 | Confirmed against the process spec's HV-NMOS/HV-PMOS tables (`V_GS ≤ 3.3V Maximum`); corrects the README draft's "1.8 V / 3.3 V" placeholder, which matched no real SG13G2 flavor. |
| Iq | < 50 µA | Carried over unchanged; not yet SG13G2-verified. Note `npn13G2`'s minimum-geometry device has a documented `IC07` (collector current at `VBE=0.7V, VCB=0V`) target of 3.8 µA, min 2.6 µA, max 5.2 µA (`AE = 0.07×0.9 µm²`) — a real anchor point for core-branch current sizing once schematic entry starts, unlike the siblings' devices, which have no equivalently-documented single-device current spec at a fixed VBE. |
| Area | < 0.05 mm² | Carried over unchanged; not yet SG13G2-verified, and not yet comparable to either sibling given the topology is not a literal port (§5). |
| Startup | self-starting, < 1 ms | Carried over unchanged; not yet SG13G2-verified. If `npn13G2` is used, note the startup circuit's own devices must also respect `BVCEO`/`BVEBO` (1.0–1.6 V target range) if any bipolar device appears in the startup path. |

None of these SG13G2-specific rows should be read as ratified — this table
states starting targets for the eventual spec-ratification issue (as in
both siblings, ratification is a separate, later step), grounded in real
device numbers where the process spec provides them, and explicitly flagged
as unverified where it does not.

## 7. Tooling friction anticipated in advance (check against reality once #1 clears)

Per the issue's fourth acceptance-criteria bullet, these are risks read
from the PDK's model decks and directory layout — not yet checked against
actual `klt` behavior, since the resolver (#1) blocks that check today.

1. **VBIC self-heating/thermal pseudo-nodes in the HBT SPICE subckt.**
   `npn13G2`'s subckt exposes an internal thermal network (`Rt t 0 = 1e9`,
   `cth`/`rth` self-heating parameters; the `_5t` variant makes the thermal
   node `t` an explicit 5th terminal). LVS extraction has to correctly
   recognize this as a non-electrical pseudo-node and not attempt to match
   it against anything in a layout-extracted netlist, or every HBT instance
   risks a spurious LVS mismatch. Worth checking concretely once tooling
   access lands, and filing generically against `klayout-tools` if it is
   not already handled — this is exactly the kind of "different device
   class for extraction and LVS to handle" CLAUDE.md already anticipates,
   named here concretely rather than generically.
2. **`pnpMPA`'s layout-pcell pinout may not match its 3-terminal schematic
   symbol.** The model's own header comment reads `DUT: diode_pp=pnpMPA`,
   suggesting the device may have originally been characterized as a
   diode-connected test structure. The `sg13g2_pr/gds` directory was not
   inspected at the pcell level for this issue (out of scope without layout
   tooling access) — worth confirming the layout generator actually
   produces independent collector/base/emitter terminals matching
   `pnpMPA.sym`'s 3-pin schematic symbol before committing to this device
   as DR-0001's fallback.
3. **Whether `npn13G2`'s `Nx` emitter-multiplicity parameter is a real,
   independently-placeable multi-stripe layout, or a SPICE-only model
   scaling trick.** This directly gates whether §2's "closer to gf180's
   directly-sizable device" framing holds at the layout level or whether
   sky130-style external unit-device paralleling is still needed for
   common-centroid matching. Needs a layout-pcell check once tooling
   access lands.
4. **Two bipolar device families sharing one mismatch-methodology surface
   area.** Unlike either sibling (one bipolar device each), a
   characterization pass here has two bipolar mismatch decks to reconcile
   (`sg13g2_hbt_mod_mismatch.lib` for `npn13G2`, and whatever mismatch
   support — if any — `pnpMPA` has, not yet checked). Confirm `pnpMPA` has
   equivalent mismatch-model support before relying on it as anything more
   than a documented fallback.
5. **Not a new risk, positive finding**: SG13G2's corner-file layout
   (separate `cornerHBT.lib`, `cornerMOShv.lib`, `cornerMOSlv.lib`,
   `cornerRES.lib`, `cornerCAP.lib`, `cornerDIO.lib` files) is already
   split per device family, matching the fleet's per-family PVT-corner
   testbench pattern — no anticipated friction porting the corner-sweep
   methodology itself.
6. **Not a new risk, positive finding**: xschem schematic symbols already
   exist for every device named in this plan (`npn13G2.sym` and variants,
   `pnpMPA.sym`, `rsil.sym`/`rppd.sym`/`rhigh.sym`) in
   `ihp-sg13g2/libs.tech/xschem/sg13g2_pr/`, and a netgen LVS setup
   (`ihp-sg13g2_setup.tcl`) exists in `ihp-sg13g2/libs.tech/netgen/`. The
   blocking gap is specifically `klt`'s PDK-resolver step (#1), not an
   absence of schematic-capture or LVS-setup support in the upstream PDK
   itself.
7. **The upstream resolver tracking issue itself shows closed as of this
   writing.** `klayout-tools#522` ("klt pdk cannot resolve IHP-Open-PDK
   (SG13G2) — blocks any SG13G2 work") is **closed** as of 2026-08-05, the
   same day this plan was written. This repo's own tracking issue (#1) was
   still open and labeled `loom:blocked` at the time of this check. This
   plan does not itself act on that discrepancy — updating #1's status or
   `CLAUDE.md`'s "BLOCKED" language is out of scope for issue #2 — but it is
   recorded here so whoever next works #1 checks `klt pdk find`/`list`/`env`
   against a real IHP-Open-PDK fetch before assuming the resolver blocker is
   still live, rather than rediscovering the closure independently.

## 8. Next steps

This plan and its two decision records are inputs to a future
spec-ratification issue (as in both siblings, ratification is a distinct,
later step this issue does not itself perform) and to schematic entry,
both gated on #1 (`klt` PDK resolver support). Nothing in this document
authorizes layout or simulation work ahead of that resolver landing.
