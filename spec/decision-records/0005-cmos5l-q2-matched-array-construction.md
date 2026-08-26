# 0005: SG13CMOS5L `bandgap_core.sch` Q2 construction — 8 parallel unit `pnpMPA` devices (`m=8`), not one `w=8u` wide emitter

- **Status**: proposed (same status band as DR-0004 — input to the
  SG13CMOS5L port's own future spec-ratification step, not yet a ratified
  spec row)
- **Date**: 2026-08-26
- **Decided by**: Builder agent, issue #73 (found during the SG13CMOS5L
  layout phase, issue #66)
- **Related**: `0004-cmos5l-bipolar-device-selection.md` (DR-0004, this
  record amends its "Emitter-area ratio realized via the symbol's own
  `w`/`l` parameters" claim about Q2's construction, without changing its
  device/topology-class decision), `design/sg13cmos5l/bandgap_core.sch`
  (issue #64, the schematic this record's decision applies to),
  `layout/sg13cmos5l-bandgap_core/generate.py` (issue #66, where the
  unbuildable single-wide-emitter construction was first flagged), issue
  #73 (this record's own tracker)

## Context

`design/sg13cmos5l/bandgap_core.sch` (issue #64, landed under DR-0004)
captured Q2 — the 8x-area PTAT leg — as a single `pnpMPA` instance with
`w=8u l=2u m=1` (netlist: `a={ 8u * 2u } p={ ( 8u + 2u ) * 2 } m=1`). The
SG13CMOS5L layout phase (issue #66) found this construction cannot be
built:

1. **It exceeds the PCell's own parameter range.** SG13CMOS5L's
   `sg13cmos5l_pycell_lib/sg13cmos5l_tech.json` declares
   `pnpMPA_minW = 300.0n`, `pnpMPA_maxW = 2.0u` — confirmed directly against
   the installed PDK. `pnpMPA_code.py`'s `genLayout()` draws the emitter
   window directly from `w`/`l` with no internal arraying (`setupParams`
   reads only `self.l`/`self.w`; the PCell's own `m` "Multiplier" param spec
   exists but is never read by `genLayout()` at all), so a single `w=8u`
   instance cannot be PCell-generated regardless of `m`.
   `layout/sg13cmos5l-bandgap_core/generate.py` (issue #66) worked around
   this by hand-drawing the emitter geometry to match the netlist's `a`/`p`
   exactly — an honest rendering of a non-buildable device, flagged in
   `layout/README.md` and cross-referencing this issue.
2. **A single wide emitter is not the standard way to build a matched 8x
   device anyway** — the standard construction is N unit devices in
   parallel (ideally common-centroid around the 1x unit `Q1`/`Q3`).

## Decision

**Rebuild Q2 as 8 parallel unit `pnpMPA` devices (`w=1u l=2u`, matching
`Q1`/`Q3`'s own unit geometry) via the SPICE `m=8` subcircuit multiplier**,
concretely: `XQ2 vss vss e2 pnpMPA a={ 1u * 2u } p={ ( 1u + 2u ) * 2 } m=8`
(was `a={ 8u * 2u } p={ ( 8u + 2u ) * 2 } m=1`). In the schematic, this is a
one-attribute change (`w=8u l=2u m=1` -> `w=1u l=2u m=8` on the `Q2`
instance) — no new symbols, no new nodes, no wiring change. In the layout
(issue #66's follow-on, this same PR), Q2's hand-drawn single-device
footprint is replaced by 8 real PCell-generated unit `pnpMPA` instances
(`w=1u l=2u`, each individually within `pnpMPA_maxW`), wired in parallel to
`e2` and `vss`.

**This is electrically identical to the construction it replaces — not an
approximation.** Two independent checks, both run in this environment
against the installed PDK:

1. **Direct read of `sg13cmos5l_pnpMPA_mod.lib`'s `.subckt pnpMPA c b e`**:
   the block computes both `dev_a=a*1e12` and `dev_p=p*1e6`, but **only
   `dev_a` is ever used** — via `QpnpMPA c b e pnpMPA_mod area=dev_a`, the
   standard SPICE BJT `AREA` instance parameter, which scales `is`/`ise`/
   `isc`/`ikf` proportionally and `rb`/`rc`/`re` inversely. `dev_p` is
   computed and then never referenced by any `.model` equation in the file.
   So this device's electrical behavior — including the `VEB` term this
   core's whole PTAT/CTAT math is built on — is a pure function of `a`
   (area); `p` (perimeter) is cosmetic in this specific (`level=1`
   Gummel-Poon) compact model. The issue's original premise — that
   `pnpMPA`'s model card "scales with both `a` (area) and `p` (perimeter)",
   so changing the array's drawn perimeter would move `VEB` — does not hold
   for this device; it was a reasonable a priori concern (perimeter-
   dependent leakage terms are common in real compact BJT models) that this
   record closes by reading the actual model code rather than assuming it.
2. **Direct ngspice cross-check** (`.model` params scaled to 1.0, 5uA
   forced-current bias, `typ` corner, 27C — the same standalone op-point
   fixture `design/sg13cmos5l/README.md`'s own issue-#64 account used):
   `XQwide` (`a={8u*2u} p={(8u+2u)*2} m=1`) and `XQarray`
   (`a={1u*2u} p={(1u+2u)*2} m=8`) both settle to **exactly** the same
   node voltage (0.7251882 V at 27C typ, matched to every printed digit).
   This is the expected consequence of (1): SPICE's `m=` subcircuit
   multiplier (ngspice replicates the subcircuit `m` times, sharing
   terminals) is mathematically equivalent, for a model whose only
   area-dependence is a linear `is`/`ikf`/`isc` scale-up and an inverse
   `rb`/`rc`/`re` scale-down, to a single instance at `m=1` with `a` scaled
   up by the same factor — both give the model the same *total* effective
   area (`8 x (1u*2u) = 8u*2u = 16 um^2`), and neither depends on `p` at
   all. The two constructions are not merely close; they are the same
   circuit as far as `ngspice`/the compact model is concerned.

Because of this, `bandgap_core.sch`'s existing sizing (`R1`, `R2`, the
provisional `vref` target — all derived from the pre-DR-0005 `VEB`
measurements in the schematic's own header) is **not invalidated** by this
change and needed no re-derivation. What the acceptance criteria's PVT
re-run (`sim/sg13cmos5l-core-open-loop-bias`,
`sim/sg13cmos5l-closed-loop-startup`) grounds is that this equivalence holds
across the full corner grid, not just the single nominal point checked
above — see those experiments' own `records/` for the re-run evidence this
record's PR carries.

## Alternatives considered

- **Keep the single `w=8u` wide emitter, with a documented justification
  against `pnpMPA_maxW`.** Rejected outright — there is no justification
  that survives "the PCell generator cannot draw this device at all"; this
  is not a case of an aggressive-but-buildable geometry, it is a parameter
  value outside the PCell's declared range. The issue's own curator comment
  flagged this as "the option most likely to survive review while still
  being wrong," which matches this analysis.
- **An explicit 8-instance array** (8 separate `X` lines, each
  `pnpMPA a={1u*2u} p={(1u+2u)*2} m=1`, wired in parallel at the SPICE
  level) instead of one `X` line with `m=8`. Electrically identical to the
  chosen construction (SPICE's `m=` multiplier IS this — an internal
  parallel replication of the same subcircuit call), so this is a
  notational choice, not a different electrical decision. Rejected only for
  schematic-capture ergonomics: one `pnpMPA` symbol with `m=8` is a single
  edit and matches how `sky130-bandgap`'s own `bandgap_core.sch` already
  expresses its own PNP array multiplicity (`m='n_pnp_ptat'` on a single
  `X` line, confirmed by reading that repo's schematic directly) — this
  repo's fleet precedent already favors the `m=` idiom over hand-multiplied
  instances. The **layout**, unlike the netlist, still draws 8 separate
  physical PCell instances (the PCell itself has no internal `m`-driven
  array-generation — `pnpMPA_code.py`'s `genLayout()` never reads `m` — so
  "8 parallel devices" is achieved at the layout level by placement, not by
  a PCell array feature), which is the real, physical form of "an explicit
  8-instance array" this alternative names; the netlist-level notational
  choice above does not change that.
- **Full common-centroid placement of the 8 unit devices around `Q1`/`Q3`**
  (e.g. an ABBA-style interleaved layout) in this same pass. Deferred, not
  rejected: it is the layout-quality ideal this record's own "Decision"
  section names, but achieving it against this deck's single-metal,
  no-via, no-bipolar-recognition constraint (see
  `layout/sg13cmos5l-bandgap_core/generate.py`'s own docstring) is a
  materially larger floorplan rework than this issue's scope, and this
  deck cannot LVS-verify device matching for `pnpMPA` at all yet (no
  bipolar device class recognized — a documented, upstream-filed deck
  gap), so a common-centroid layout would currently buy no verifiable
  matching benefit over a simpler linear placement. `layout/README.md`
  names this as a follow-up for whichever future phase gets bipolar LVS
  coverage from the deck.

## Consequences

- **`design/sg13cmos5l/bandgap_core.sch`'s `Q2` instance changes from
  `w=8u l=2u m=1` to `w=1u l=2u m=8`** — a one-attribute schematic edit,
  header comment updated to describe the new construction and cross-
  reference this record.
- **`design/sg13cmos5l/netlist/bandgap_core.spice` and the embedded core
  body in `design/sg13cmos5l/netlist/bandgap_top.spice`** both regenerate
  with `XQ2 ... a={ 1u * 2u } p={ ( 1u + 2u ) * 2 } m=8`.
- **No sizing values change** (see "Decision" above) — `R1`/`R2`/the
  provisional `vref` target are unaffected.
- **`sim/sg13cmos5l-core-open-loop-bias` and
  `sim/sg13cmos5l-closed-loop-startup` re-run against the updated netlist**
  as new, append-only evidence records (not a rewrite of the prior
  records) — see those experiments' `records/` directories for the new
  timestamped entries this PR adds, and their `README.md`s if a result
  differs materially from the prior (pre-DR-0005) record in a way this
  record's electrical-equivalence claim does not predict.
- **`layout/sg13cmos5l-bandgap_core/generate.py` (issue #66) is
  regenerated**: Q2's single hand-drawn `w=8u` footprint (previously
  flagged in `layout/README.md` as an honest rendering of a non-buildable
  device) is replaced by 8 real PCell-buildable unit `pnpMPA` instances
  wired in parallel, and the cell's DRC/LVS/extract reports are refreshed
  against the new GDS hash. The `layout/README.md` note this record
  supersedes is updated to point here instead of describing the gap as
  still-open.
- **This record does not change DR-0004's device/topology-class decision**
  (still `pnpMPA`, still grounded-collector, still the gf180/sky130-style
  Brokaw shape) — it corrects DR-0004's narrower claim about *how* the 8x
  ratio is realized, and additionally corrects DR-0004's implicit
  assumption (inherited from the issue that opened this record, not from
  DR-0004's own text) that `pnpMPA`'s perimeter parameter is
  electrically load-bearing; it is not, for this model.
