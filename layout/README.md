# layout — bandgap core + startup GDS (issue #11)

Physical layout for the two schematics landed in #9 (`design/bandgap_core.sch`,
`design/bandgap_startup.sch`). This directory is no longer a placeholder:

```
layout/
  README.md                  this file
  common.py                  shared klayout.db drawing primitives (layer
                              table, Builder, draw_npn13g2/draw_hv_mos/
                              draw_poly_res) both generate.py scripts import
  bandgap_core/
    generate.py               draws bandgap_core.gds
    bandgap_core.gds          committed, deterministic layout
  bandgap_startup/
    generate.py               draws bandgap_startup.gds
    bandgap_startup.gds       committed, deterministic layout
```

## Provenance

**Manually constructed** with the `klayout.db` (`pya`-compatible) Python API
directly, via `layout/common.py` + each cell's own `generate.py` — the same
construction pattern `gf180-bandgap/layout/bandgap_top/generate.py` and
`gf180-bandgap/layout/common/klayout_builder.py` already established for the
fleet's most mature block (`klayout.db`/`pya` is the "tool/flow", per this
issue's acceptance criteria; the pip `klayout` package, version `0.30.10` in
this environment).

**Not** a PDK-native PCell run. SG13G2 does ship its own native PyCell
library (`ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/`, covering
`npn13G2`, `pnpMPA`, `sg13_hv_nmos`/`pmos`, `rppd`/`rhigh`/`rsil`, etc.) and
that library's own `README.md` documents that it is designed to run inside
KLayout directly (an `#ifdef KLAYOUT` / `#else` conditional-compilation
convention selects the KLayout-vs-Cadence code path at import time — this is
not Cadence-only code). Two concrete things blocked using it for this issue,
both checked concretely rather than assumed:

1. **`klt gen` — the fleet's own headless PCell harness — has no generator
   family that resolves SG13G2 at all.** Checked directly: every analog-
   primitive generator in `klt gen --list` (`bjt_array`, `mos_array`,
   `res_array`, `cap_array`, `diff_pair`, `guard_ring`, `esd_device`,
   `bond_pad`) returns `PDK variant 'ihp-sg13g2' is not supported by this
   generator -- supported families: gf180mcu, sky130` against a `klt
   pdk find`-resolvable SG13G2 install. Only `resistor_strip` (the
   PDK-agnostic phase-1 reference generator, which has no PDK-role-layer
   lookup) works. **Filed generically**, per `CLAUDE.md`'s friction
   protocol, as
   [klayout-tools#1266](https://github.com/2AMLogic/klayout-tools/issues/1266)
   — not SG13G2-specific in that filing; the same hard two-family allowlist
   would block any third PDK family's generator-driven layout work.
2. **The native PyCell library's own companion compatibility shim
   (`pycell4klayout-api`) was not present in this environment's PDK
   checkout.** `ihp-sg13g2/libs.tech/klayout/python/pycell4klayout-api/` is
   an empty directory in the tarball fetch this issue used (it is a
   separate git submodule the plain-tarball extraction did not pull in) —
   without it, the native PyCells' `from cni.dlo import *` (the Cadence-DLO
   compatibility layer the KLayout code path also depends on) cannot
   resolve. This is a checkout/fetch-method gap, not itself filed against
   `klayout-tools` (it is about how this repo's sandbox obtained the PDK,
   not a `klt` capability), but recorded here as the second concrete reason
   the native-PCell path was not exercised for this issue.

Given both, this issue instead **reads the native PyCell library's own
source directly** as the authoritative geometry/pinout reference (see
"Tooling-friction findings" below) and reconstructs a simplified,
schematic-accurate footprint by hand — not a re-implementation of every
layer the real PCells draw, but faithful on the two specific facts this
issue's acceptance criteria asked to check (the `Nx` multi-stripe geometry,
and `pnpMPA`'s pin count/naming).

## What this layout is / is not

- **Is**: a floorplan-level layout that instantiates one shape group per
  schematic device (`M1`/`M2`/`M3`, `Q1`/`Q2`/`Q3`, `R1`/`R2` in
  `bandgap_core`; `RPU`/`MSENSE`/`MKFB` in `bandgap_startup`), on real
  SG13G2 GDS layer numbers (read off `ihp-sg13g2/libs.tech/klayout/tech/
  sg13g2.lyp`'s own `<source>` entries — see "Layer numbers" below), sized
  to the schematics' own committed `w`/`l`/`Nx` parameters, with `TEXT` and
  `Metal1.label`/`Metal2.label`/`GatPoly.label`/`PolyRes.label` labels
  naming each device and the schematic net it connects to (`vdd`, `vss`,
  `fb`, `sns1`, `sns2`, `vref`, `cb2`, `cb3`, `det`) — enough for a layout
  viewer to confirm device-for-device correspondence against
  `design/bandgap_core.sch`/`design/bandgap_startup.sch`, per this issue's
  own test plan.
- **Is DRC-clean** (updated by issue #12 — see "DRC/LVS verification" below).
  The informational run this issue originally recorded here (`klt drc
  layout/bandgap_core/bandgap_core.gds --deck sg13g2`) found `status:
  "violations"`, 26 `cont.width.1` violations: the simplified `Cont` pads
  this layout drew were 0.15 µm on their narrow axis, 0.01 µm under the
  curated deck's real 0.16 µm minimum-Cont-width floor. #12 treated this as
  a genuine (if small) geometry defect rather than an inherent
  simplification artifact — `layout/common.py`'s `draw_npn13g2`/
  `draw_hv_mos` now draw that axis at 0.18 µm, comfortably clear of the
  floor and still fully inside each device's own `Activ`/`Metal1` margins
  (see `layout/common.py`'s own inline comments at each callsite). Both
  `bandgap_core.gds` and `bandgap_startup.gds` now report `status: "clean"`,
  `violation_count: 0` — see the committed reports.
- **Is not** LVS-clean yet (#12 also ran this fresh — see "DRC/LVS
  verification" below for the full, itemized finding: a real
  `status: "mismatch"` on both cells, attributable to the curated deck's
  documented bipolar/resistor-recognition gap plus this layout's own
  floorplan-only routing, not a fixable circuit defect).
- **Is not** a re-implementation of each device's real PCell. `Q1`/`Q2`/`Q3`
  (`draw_npn13g2` in `layout/common.py`) faithfully replicate the one
  geometric fact this issue's tooling-friction check turned on (the real,
  per-stripe `Nx` multiplicity — see below) but omit the real PCell's base
  poly, STI, `nSD` block polygon, and thermal pseudo-layer detail. `M1`–
  `M3`/`MSENSE`/`MKFB` (`draw_hv_mos`) are a generic single-finger MOS
  footprint, not read from `pmosHV_code.py`/`nmosHV_code.py` (out of this
  issue's scope — those two PyCells are not what the issue's tooling-
  friction checks are about). `R1`/`R2`/`RPU` (`draw_poly_res`) are drawn
  as straight, unfolded bars at the schematics' literal `w`/`l` — for `R1`
  (`l=694.5u`) and `RPU` (`l=1411.3u`) this makes for a very long, thin
  body (sub-mm to ~1.4 mm), an honest rendering of the netlist's own
  provisional (not yet simulation-verified — see each schematic's header)
  sizing, not a claim about how the resistor would actually be folded for
  a compact final layout.

## Layer numbers

Read directly from `ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp`'s own
`<name>`/`<source>` entries (IHP-Open-PDK `main` @ `22f2a25`, 2026-08-05 —
the same checkout `spec/porting-plan.md` cites), not invented:

| Layer | GDS (layer/datatype) |
|---|---|
| `Activ.drawing` | 1/0 |
| `GatPoly.drawing` | 5/0 |
| `nSD.drawing` | 7/0 |
| `Cont.drawing` | 6/0 |
| `Metal1.drawing` | 8/0 |
| `pSD.drawing` | 14/0 |
| `Via1.drawing` | 19/0 |
| `Metal2.drawing` | 10/0 |
| `NWell.drawing` | 31/0 |
| `nBuLay.drawing` | 32/0 |
| `EmWind.drawing` | 33/0 |
| `PolyRes.drawing` | 128/0 |
| `TEXT.drawing` | 63/0 |

## Reproducing

```bash
cd layout
python3 bandgap_core/generate.py
python3 bandgap_startup/generate.py
```

(`uv run --with klayout python3 ...` if `klayout` is not already on the
active interpreter's path — matching `gf180-bandgap`'s convention.) Output
is byte-for-byte deterministic (`SaveLayoutOptions.gds2_write_timestamps =
False`), so re-running leaves `git diff` empty — verified for this issue.

```bash
klt cells layout/bandgap_core/bandgap_core.gds --format json
klt stats layout/bandgap_core/bandgap_core.gds --format json
klt layers layout/bandgap_core/bandgap_core.gds --format json
```

`bandgap_core.gds`: 1 top cell (`bandgap_core`), 105 shapes/labels across 13
layer/datatype/purpose combinations, bbox `(-5.4, -3.1)`–`(694.7, 61.4)` µm
(the `R1` long-bar resistor dominates the bounding box — see above). The
`EmWind.drawing` (33/0) layer carries exactly 10 shapes — `Q1` (`Nx=1`) + `Q2`
(`Nx=8`) + `Q3` (`Nx=1`) = 10, matching the schematic's `Nx` values exactly,
confirming the per-stripe geometry described below.

## Tooling-friction findings (`spec/porting-plan.md` §7, items 2 and 3)

Both checked concretely against SG13G2's own native PyCell source
(`ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/ihp/`), per this
issue's acceptance criteria — not simulated, not assumed.

### 1. `npn13G2`'s `Nx` parameter: a real, independently-drawn multi-stripe layout — confirmed

Reading `npn13G2_code.py`'s `genLayout()`: the PCell's outer loop is
`for pcIndexX in range(int(math.floor(Nx)))`, and **inside** that loop it
draws a separate `Via1` pair, `EmWind` window, `Cont` pair, and `Activ`/
`nSD` detail **per index**, each offset by `stepX * pcIndexX` (`stepX =
1.85` µm — the emitter-stripe pitch). Only the collector/base metal rails
and the outer `TRANS`/`pSD`/`Activ` boundary polygons are drawn once,
spanning the full `stretchX = stepX*(Nx-1)`-wide row. This is unambiguously
**Nx real, independently-placed emitter stripes on a fixed pitch, not a
single shape whose parameters merely scale a SPICE model** — confirming
`spec/porting-plan.md` §2/§5's "closer to gf180's directly-sizable device"
framing at the *layout* level, not just the SPICE-subckt level.

`layout/common.py`'s `draw_npn13g2()` replicates exactly this fact (using
the PCell's own `stepX = 1.85 µm` pitch and its default `le`/`we` emitter-
window size), and `bandgap_core.gds`'s `Q2` instance (`Nx=8`) draws 8
separate `EmWind` windows at that pitch — visible in the committed GDS
itself, not just asserted in this README (see "Reproducing" above: `klt
layers` reports exactly 10 `EmWind` shapes across `Q1`+`Q2`+`Q3`).

**One caveat, not glossed over**: "independently-placeable" needs a second
qualifier. Within **one** PCell instantiation, the Nx stripes are real,
separate geometry — but they are placed automatically, at a fixed pitch, in
a single row, by that one PCell call. The PCell itself does not expose a
way to interleave a single instance's own stripes into an external
common-centroid pattern (e.g. splitting Q2's 8 stripes across two
physically-separated locations) — that would require decomposing into
multiple smaller-`Nx` PCell calls placed by the caller, the same way
`klt gen`'s `mos_array`/`bjt_array` families let a caller choose
`topology='common_centroid'` externally. Whether this repo's eventual
common-centroid matching plan needs that decomposition is downstream
floorplan work (out of this issue's scope), not answered here — this
finding only settles the narrower question `spec/porting-plan.md` §7 item 3
asked: real per-stripe geometry, not a SPICE-only trick.

### 2. `pnpMPA`'s layout-pcell pinout vs. its 3-terminal schematic symbol — mismatch confirmed

`pnpMPA.sym` (the xschem schematic symbol, `ihp-sg13g2/libs.tech/xschem/
sg13g2_pr/pnpMPA.sym`) declares three named pins: `collector` (pin 1),
`base` (pin 2), `emitter` (pin 3) — a standard 3-terminal bipolar symbol,
exactly as `spec/porting-plan.md` §7 item 2 described it.

Reading `pnpMPA_code.py`'s `genLayout()`, the **layout** PCell creates
exactly three named pins via `dbCreatePin()`: **`PLUS`**, **`MINUS`**, and
**`TIE`** — a diode-style 2-terminal-plus-substrate-tie layout (`PLUS`/
`MINUS` are drawn as the two `Activ`/`Metal1` islands the model's own
header comment's `DUT: diode_pp=pnpMPA` name already hinted at; `TIE` is
the surrounding `pSD` guard-ring contact). **There is no layout pin named,
or corresponding one-to-one to, `collector`/`base`/`emitter`** — the
layout PCell's own pin *count* (3) coincidentally matches the schematic
symbol's pin count, but the *names* and the underlying *terminal topology*
do not: a diode-connected 2-terminal device with a tie ring is not the
same electrical structure as an independently-contactable 3-terminal
bipolar transistor layout.

This confirms `spec/porting-plan.md` §7 item 2's suspicion and strengthens
`spec/decision-records/0001-bipolar-device-selection.md`'s decision to keep
`pnpMPA` a documented *fallback* rather than a primary device: were
`pnpMPA` ever promoted to primary, someone would first need to resolve
this pin-mapping mismatch (at minimum, confirm which of `PLUS`/`MINUS`
corresponds to which of `collector`/`base`/`emitter` in the underlying
device physics, and how — or whether — the third schematic terminal maps
onto the `TIE` ring at all) before layout capture could proceed the way it
did for `npn13G2` in this issue. **Not filed against `klayout-tools`** —
this is a property of the IHP-authored PDK PyCell library's own content,
not a `klt`/`klayout-tools` tool capability gap, so it does not meet the
friction protocol's "generic tool gap" bar (`CLAUDE.md`). Recorded here,
in this issue's closing comment, and cross-referenced from DR-0001 as
the appropriate record per this issue's own acceptance criteria.

### 3. New finding (not anticipated in `spec/porting-plan.md` §7): `klt gen` has no SG13G2 support at all

Not one of the two specific checks this issue asked for, but discovered
while attempting the pcell-generated provenance path (see "Provenance"
above) — every `klt gen` analog-primitive generator hard-rejects the
SG13G2 PDK family. This **is** a generic `klt`/`klayout-tools` tool gap
(not a PDK-content fact), so it **was** filed:
[klayout-tools#1266](https://github.com/2AMLogic/klayout-tools/issues/1266).

## DRC/LVS verification (issue #12)

Fresh, committed `klt drc`/`klt lvs` reports for both cells — the first
time either tool has been run against a real SG13G2 layout in this repo.
No SG13G2 PDK install (IHP-Open-PDK checkout) was needed for either: `klt
drc`'s default `--engine curated` and `klt lvs`'s default `"klayout"`
engine both run against `klt`'s own pip-installed, declarative
`decks/sg13g2.py` deck (klayout-tools#905/#911) — a real, `git`-pinned
IHP-Open-PDK v0.3.0 checkout is that deck's own build-time provenance
source, not a runtime dependency of running it.

### DRC — clean

| Cell | Report | Status | Deck (content hash) |
| --- | --- | --- | --- |
| `bandgap_core` | `layout/bandgap_core/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:a64d3a7b...` |
| `bandgap_startup` | `layout/bandgap_startup/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:a64d3a7b...` |

The 26 `cont.width.1` violations this issue's own informational run
originally found (see "What this layout is / is not" above) were fixed by
widening the narrow axis of every simplified `Cont` pad in
`draw_npn13g2`/`draw_hv_mos` (`layout/common.py`) from 0.15 µm to 0.18 µm —
0.02 µm clear of the curated deck's real 0.16 µm `Cnt.a` minimum-width
floor, verified against `ihp-sg13g2/libs.tech/klayout/tech/drc/rule_decks/
feol/5_14_cont.drc`'s own cited rule. This was judged a genuine (if small)
layout defect, not an inherent artifact of this layout's simplification —
the fix only grows each `Cont` box further into its own device's already-
generous `Activ`/`Metal1` margin (verified: re-running finds 0 new
violations of any kind, not just a disappeared `cont.width.1` count).
Reproduce: `klt drc --check layout/bandgap_core/drc_report.json` (or
`--rerun` for a full re-check), run from the repo root.

### LVS — mismatch, fully attributed (not yet a fixable circuit defect)

| Cell | Report | Status | Engine |
| --- | --- | --- | --- |
| `bandgap_core` | `layout/bandgap_core/lvs_report.json` | `mismatch` (32 findings, 30 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |
| `bandgap_startup` | `layout/bandgap_startup/lvs_report.json` | `mismatch` (18 findings, 16 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |

Reproduce: `klt lvs layout/bandgap_core/lvs_request.json` (run from
`layout/bandgap_core/`, since the request's relative paths resolve against
its own directory — see `docs/cli/lvs.md` in `klayout-tools`); `klt lvs
--check layout/bandgap_core/lvs_report.json` (same directory) verifies the
committed report against the current inputs without re-running the compare.

**Reference-netlist conversion.** `design/netlist/bandgap_core.spice`/
`bandgap_startup.spice` (landed by #9) are written in the subckt-call form
xschem/ngspice always emit (`XM1 d g s b sg13_hv_pmos w=10u l=1u ...`), but
`klt lvs` requires the plain-element form and its own automatic converter
(`reference.form: "subckt-call"`) turned out to be MOS-only — it hard-fails
on this circuit's 3-terminal `rppd`/`rhigh` resistor calls (misdetected as
malformed 4-terminal MOS calls, since they also carry `l`/`w`) and silently
mishandles its parameter-only `npn13G2` bipolar calls (no `l`/`w`, so they
pass through as unresolved subcircuits instead of converting, corrupting
the whole reference into an auto-synthesized-subcircuit hierarchy that
cannot structurally match the layout side's flat netlist at all). Confirmed
by running both the unconverted and `subckt-call`-converted reference
directly (see this issue's own PR for the exact commands/output). **Filed
generically against `klayout-tools`**, per `CLAUDE.md`'s friction protocol:
[klayout-tools#1269](https://github.com/2AMLogic/klayout-tools/issues/1269).
Worked around here with `layout/lvs_reference.py`, a small, repo-local,
deterministic script that reads `design/netlist/*.spice` and emits the
`layout/*/*.lvs_reference.spice` plain-element files the committed
`lvs_request.json`s actually reference — regenerate with
`python3 layout/lvs_reference.py` after any `design/netlist/*.spice`
change.

**Two independent, fully-attributed causes for the mismatch itself** (per
`klt lvs`'s own `mismatches[]` categorisation in each committed report —
neither is a routing/connectivity bug this issue introduced, and neither is
fixable within this issue's own scope):

1. **`klt`'s curated `sg13g2` extraction deck does not recognise bipolar or
   resistor devices at all** (`klayout_tools.decks.sg13g2.EXTRACTION_DECK`
   only models thin-oxide MOS — see this deck's own module docstring, and
   this repo's `CLAUDE.md`: "resistor/capacitor/bipolar/diode device
   recognition... explicitly out of scope"). Every `Q1`–`Q3`/`R1`/`R2`
   (`bandgap_core`) and `RPU` (`bandgap_startup`) device is therefore
   necessarily reference-only in the compare — `device.unmatched`, class
   `NPN13G2`/`RES`, 5 of `bandgap_core`'s 8 `device.unmatched` findings and
   1 of `bandgap_startup`'s 3. Not a new gap (already documented) and not
   actionable from this repo's side.
2. **This layout has no top-level routing between device instances** — a
   real, new finding, but not a defect: `layout/common.py`'s drawing
   primitives (`draw_hv_mos`/`draw_npn13g2`/`draw_poly_res`) each draw one
   isolated shape group per device, with no `Metal1`/`Metal2`/`Via1` wiring
   *between* instances. `klt extract` confirms this directly:
   `bandgap_core.gds` extracts to **12 disconnected nets** for its 3 `pfet`
   devices' worth of terminals (one net per terminal, no merging across
   instances) against the schematic's 8 named nets, several of which
   (`vdd`, `fb`, `vss`) are shared across multiple devices in the netlist
   but never physically joined in the drawn geometry. This is exactly what
   issue #11 documented building — a labeled floorplan/device-placement
   layout, not a routed one (see "What this layout is / is not" above,
   and #11's own acceptance criteria) — so it is a real, pre-existing,
   already-disclosed limitation of the layout this issue verifies against,
   not something #12 introduced or should silently paper over. Filed as a
   design-specific follow-up in *this* repo (not `klayout-tools` — this is
   about wiring up the layout, not a tool gap):
   [#20](https://github.com/2AMLogic/sg13g2-bandgap/issues/20).

Net effect: even the 3 MOS devices the deck *does* recognise on both sides
(`pfet` `M1`/`M2`/`M3` in `bandgap_core`; `nfet` `MSENSE`/`MKFB` in
`bandgap_startup`) show as `device.unmatched` too — not because the device
recognition itself is wrong (same class, same L/W on both sides), but
because `NetlistComparer`'s topology match has no surrounding net structure
to anchor a pairing on, given cause 2 above. `status: "mismatch"` is
reported honestly rather than claimed clean or silently downgraded to
warnings — per `CLAUDE.md`, "Verification is the product": this repo's DRC
result is a genuine pass; its LVS result is a genuine, fully-explained
fail, not fabricated evidence either way.
