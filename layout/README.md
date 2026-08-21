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
- **Is not** DRC-clean or LVS-verified. Ran informationally against the
  curated deck (`klt drc layout/bandgap_core/bandgap_core.gds --deck
  sg13g2`): `status: "violations"`, 26 `cont.width.1` violations (the
  simplified `Cont` pads this layout draws are undersized against the real
  minimum-contact-width rule — expected, since this issue's device
  footprints are hand-simplified, not the real PCells' exact stackup). This
  is explicitly **not** this issue's acceptance bar — DRC/LVS verification
  is tracked separately in #12, which this issue's own "What to build"
  section says not to block on.
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
