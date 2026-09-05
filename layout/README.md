# layout — bandgap core + startup GDS (issue #11)

Physical layout for the two schematics landed in #9 (`design/bandgap_core.sch`,
`design/bandgap_startup.sch`). This directory is no longer a placeholder:

> **Two PDKs share this directory.** Everything from here down to the
> `SG13CMOS5L port (issue #66)` heading at the end describes the **SG13G2**
> block (`common.py`, `bandgap_core/`, `bandgap_startup/`, `bandgap_amp/`,
> `bandgap_top/`). The SG13CMOS5L port (`common_sg13cmos5l.py`,
> `sg13cmos5l-bandgap_core/`) has its own layer table, its own primitives
> and its own DRC/LVS verdicts — jump straight to that section rather than
> reading anything below across.

```
layout/
  README.md                  this file
  common.py                  shared klayout.db drawing primitives (layer
                              table, Builder, draw_npn13g2/draw_hv_mos/
                              draw_poly_res, plus issue #20's routing
                              primitives: route_h/route_v/via1_tap/
                              draw_gate_tab) both generate.py scripts import
  lvs_reference.py            converts design/netlist/*.spice to the
                              plain-element form klt lvs requires (issue #12)
  bandgap_core/
    generate.py               draws + routes bandgap_core.gds
    bandgap_core.gds          committed, deterministic layout
    lvs_request.json          klt lvs request (issue #12)
    lvs_reference.spice       generated reference netlist (issue #12)
    drc_report.json           committed klt drc report
    lvs_report.json           committed klt lvs report
    bandgap_core.pex.spice    klt extract --parasitics output (issue #14)
    pex_extract_report.json   committed klt extract --format json report
  bandgap_startup/
    generate.py               draws + routes bandgap_startup.gds
    bandgap_startup.gds       committed, deterministic layout
    lvs_request.json          klt lvs request (issue #12)
    lvs_reference.spice       generated reference netlist (issue #12)
    drc_report.json           committed klt drc report
    lvs_report.json           committed klt lvs report
    bandgap_startup.pex.spice klt extract --parasitics output (issue #14)
    pex_extract_report.json   committed klt extract --format json report
  bandgap_amp/
    generate.py               draws + routes bandgap_amp.gds (issue #169)
    bandgap_amp.gds           committed, deterministic layout
    lvs_request.json          klt lvs request (issue #169)
    lvs_reference.spice       generated reference netlist (issue #169)
    drc_report.json           committed klt drc report
    lvs_report.json           committed klt lvs report
  bandgap_top/
    generate.py               instances + routes bandgap_top.gds (issue #169)
    bandgap_top.gds           committed, deterministic layout
    lvs_request.json          klt lvs request (issue #169)
    lvs_reference.spice       generated (flattened) reference netlist (issue #169)
    drc_report.json           committed klt drc report
    lvs_report.json           committed klt lvs report
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
- **Is routed** (issue #20). Every schematic net now carries real
  `Metal1`/`Metal2`/`Via1`/`GatPoly` shapes physically connecting each
  device's labeled terminals to every other device sharing that net — not
  just an isolated shape group per device with a matching label, as #11
  originally built it (see "DRC/LVS verification" below, cause 2 of #12's
  original two-cause finding, now closed). Each net is also labeled a
  second time on `Metal1.text`/`Metal2.text` (`(8, 25)`/`(10, 25)`), the
  layer `klt`'s curated `sg13g2` extraction deck's
  `EXTRACTION_DECK.metal_labels` actually reads for net naming — the
  original `Metal1.label`/`Metal2.label` convention (`(8, 1)`/`(10, 1)`)
  is purely informational to this deck's own extraction pass (confirmed
  directly: those layers show up in `klt extract`'s own `ignored_layers`).
  See `layout/common.py`'s `route_h`/`route_v`/`via1_tap`/`draw_gate_tab`
  and each cell's own `generate.py` `_route()` for the routing itself.
- **Is DRC-clean** (issue #12, still clean after #20's routing — see
  "DRC/LVS verification" below). The informational run this issue
  originally recorded here (`klt drc layout/bandgap_core/bandgap_core.gds
  --deck sg13g2`) found `status: "violations"`, 26 `cont.width.1`
  violations: the simplified `Cont` pads this layout drew were 0.15 µm on
  their narrow axis, 0.01 µm under the curated deck's real 0.16 µm
  minimum-Cont-width floor. #12 treated this as a genuine (if small)
  geometry defect rather than an inherent simplification artifact —
  `layout/common.py`'s `draw_npn13g2`/`draw_hv_mos` now draw that axis at
  0.18 µm, comfortably clear of the floor and still fully inside each
  device's own `Activ`/`Metal1` margins (see `layout/common.py`'s own
  inline comments at each callsite). Both `bandgap_core.gds` and
  `bandgap_startup.gds` still report `status: "clean"`, `violation_count:
  0` after #20's routing shapes were added — see the committed reports.
- **Is LVS-`match` on `bandgap_startup`, still `mismatch` on
  `bandgap_core`** — see "DRC/LVS verification" below for the full, itemized
  finding. The three independent causes this bullet used to list (the
  curated deck's bipolar *and* resistor recognition gap, its lack of any
  well/substrate-tap modelling, and `bandgap_core`'s `M1`/`M2`/`M3`
  device-symmetry ambiguity) have since been reduced to **one**: resistor
  recognition landed upstream and the marker-layer fix landed here (#20's
  rescope / #45, then #149/#161); the well/substrate-tap gap was fixed
  upstream (`klayout-tools`#1278) and drawn here (#155/#157/#158); and the
  `M1`/`M2`/`M3` automorphism was broken by unit-device decomposition
  (#154). What remains on `bandgap_core` is 3 `device.unmatched` errors on
  `Q1`/`Q2`/`Q3` (`NPN13G2`) plus their class-level `topology` entry — SiGe
  HBT recognition was investigated and **permanently declined** upstream
  (`klayout-tools`#1242), so this one is not fixable from either side.
- **Is not** a re-implementation of each device's real PCell. `Q1`/`Q2`/`Q3`
  (`draw_npn13g2` in `layout/common.py`) faithfully replicate the one
  geometric fact this issue's tooling-friction check turned on (the real,
  per-stripe `Nx` multiplicity — see below) but omit the real PCell's base
  poly, STI, `nSD` block polygon, and thermal pseudo-layer detail. `M1`–
  `M3`/`MSENSE`/`MKFB` (`draw_hv_mos`) are a generic single-finger MOS
  footprint, not read from `pmosHV_code.py`/`nmosHV_code.py` (out of this
  issue's scope — those two PyCells are not what the issue's tooling-
  friction checks are about). `R1`/`R2`/`RPU` (`draw_poly_res`) are
  drawn as **serpentines** at the schematics' literal `w`/`l` — see
  "Folded (serpentine) resistors (issue #173)" below.

  *(Superseded, kept for the record: through issue #172 these were drawn as
  straight, unfolded bars, which for `R1` (`l=511u`) and `RPU`
  (`l=1411.3u`) made for a very long, thin body — sub-mm to ~1.4 mm. That
  was an honest rendering of the netlist's own sizing, and explicitly "not a
  claim about how the resistor would actually be folded for a compact final
  layout". `measurements/2026-09-layout-area/` then measured what it cost:
  77.5% of the assembled footprint was aspect-ratio whitespace. Issue #173
  folded them.)*

## Folded (serpentine) resistors (issue #173)

Every long poly resistor in this repo -- `R1`/`R2` in both variants'
`bandgap_core`, `RPU` in both variants' `bandgap_startup` -- is drawn as a
serpentine rather than a single straight bar. This section is the SG13G2
account; the CMOS5L side draws the identical geometry through
`common_sg13cmos5l.py`'s `draw_rppd`/`draw_rhigh` (same arithmetic, its own
layer stack), and its own section below records its own floorplan
consequences.

**Why.** `measurements/2026-09-layout-area/` measured the cost of the
straight bars directly: `sg13cmos5l_bandgap_top`, the only assembled
top-level GDS at the time, occupied 0.3211 mm2 at density 0.092 -- 4.45x the
sum of its own three leaf cells' footprints, i.e. **77.5% of the assembled
footprint lay outside every leaf's own bounding box**, with inter-cell
routing accounting for only 8,866 um2 of it. The cause was aspect ratio:
`sg13cmos5l_bandgap_startup` was a **145:1** bar (1424.9 x 9.8 um) whose
`RPU` alone set its bounding box, and the three leaves were placed in
disjoint x-ranges so the assembly's width was the sum of three widths.

**Geometry.** `legs` vertical bars of the schematic's own `w`, on a
horizontal pitch of `w + gap`, joined end-to-end by `w`-thick links that
alternate top/bottom. `(x0, y0)` is the marked core's **lower-left corner**
(it was a bar centreline before the fold -- every call site was updated).
For an even `legs` both free ends come out on the block's bottom row, which
is what let each cell keep its existing escape topology; an odd `legs` leaves
end B on top. Each free end carries the same wider un-marked `GatPoly`
"dog-bone" head, `Cont` and `Metal1` pad the straight bar already used.

**The fold conserves the drawn conductor length exactly.**
`layout/_klayout_builder_base.py::fold_plan` is shared by both variants and
derives the leg height and inter-leg gap **in whole nanometres** such that
`legs*leg_len + (legs-1)*gap == l` exactly. It does that by searching the gap
upward from the DRC-driven floor (`RES_FOLD_GAP_UM`, 0.4 um, against
`gatpoly.space.1`'s 0.18 um) for the first value that divides evenly:
incrementing the gap by 1 nm changes the numerator by `-(legs-1)` nm, i.e. by
`+1` modulo `legs`, so a solution always exists within `legs` nanometres of
the floor and the drawn gap is never *below* it. The docstring carries the
full derivation, including why the marked core's drawn **area** (`l * w`) and
**perimeter** (`2*(l + w)`) are also unchanged by the fold.

That matters for more than tidiness. `klt`'s curated `sg13g2` deck extracts
these as real `rppd`/`rhigh` devices and derives `R` from the marked core's
own drawn geometry, so exact length conservation is what keeps the
*extracted* value identical -- confirmed directly, not assumed:

| device | cell | before | after |
| --- | --- | --- | --- |
| `R2` (`rppd`) | `bandgap_core` | `10751` | `10751` |
| `R1` (`rppd`) | `bandgap_core` | `66430` | `66430` |
| `RPU` (`rhigh`) | `bandgap_startup` | `1919368` | `1919368` |

**One device, not a series chain.** The marker layers
(`PolyRes`/`EXTBlock`/`pSD`/`SalBlock`, plus `nSD` for `rhigh`) are drawn on
*exactly* the same box set as the `GatPoly` core, corners included, so the
recognised segment is the whole serpentine and the only un-marked `GatPoly`
left is the two end heads. `kdb.DeviceExtractorResistor` requires exactly two
contact polygons per marked shape, and gets exactly two. Had the fold instead
left the corners un-marked, each leg would have recognised as its own device
and the layout would have carried `legs` resistors against the reference
netlist's one -- a new `device.unmatched` class on a cell
(`bandgap_startup`) that currently reaches `status: "match"`.

**What the fold does change** is the device's parasitics and its matching --
and both move in the favourable direction. A folded block sees a far smaller
across-die process/temperature gradient than a 1.4 mm bar, so `R1`/`R2`
matching improves rather than degrades; and the extracted *wire* parasitics
fall sharply, because the routing that used to reach the far end of a
millimetre-long bar no longer has to (`bandgap_startup`'s `det` trunk went
from a ~1.4 mm horizontal run to a 4.5 um riser). The substrate-coupling term
the PEX flow charges to the resistor body itself is unchanged, since the
fold conserves the core's area and perimeter.

**Fold counts** are chosen per call site, in each cell's own `generate.py`,
not derived inside `draw_poly_res` -- a resistor's fold count is a floorplan
decision. Each is picked to make its own block roughly square
(`legs = sqrt(l / pitch)`) and rounded to an even number:

| device | `w` / `l` | legs | block (um) | aspect |
| --- | --- | --- | --- | --- |
| `R2` (`bandgap_core`) | 2 / 82.7 | 6 | 14.0 x 13.45 | 1.04 |
| `R1` (`bandgap_core`) | 2 / 511 | 14 | 33.278 x 36.123 | 1.09 |
| `RPU` (`bandgap_startup`) | 1 / 1411.3 | 32 | 44.772 x 43.704 | 1.02 |
| `R2` (`sg13cmos5l_bandgap_core`) | 2 / 85.1 | 6 | 14.0 x 13.85 | 1.01 |
| `R1` (`sg13cmos5l_bandgap_core`) | 2 / 647 | 16 | 38.12 x 40.055 | 1.05 |
| `RPU` (`sg13cmos5l_bandgap_startup`) | 1 / 1411.3 | 32 | 44.772 x 43.704 | 1.02 |

A folded block's *footprint* is ~`l * pitch` for **any** leg count, so the
count trades aspect ratio only -- the area the fold costs over the bare
conductor is the inter-leg gap, which DRC requires. Both variants draw `RPU`
at the same count and therefore the same geometry: it is the same device.

**Result** (full before/after, all eight committed cells, in
`measurements/2026-09-resistor-fold/`):

| cell | before | after | aspect before -> after |
| --- | --- | --- | --- |
| `bandgap_core` | 516.9 x 64.5 | 142.9 x 73.7 | 8.0:1 -> 1.9:1 |
| `bandgap_startup` | 1416.9 x 22.2 | 50.1 x 50.5 | 63.7:1 -> 1.0:1 |
| `bandgap_top` | 2228.3 x 93.3 | 482.5 x 97.3 | 23.9:1 -> 5.0:1 |
| `sg13cmos5l_bandgap_core` | 840.5 x 64.9 | 230.1 x 64.9 | 12.9:1 -> 3.5:1 |
| `sg13cmos5l_bandgap_startup` | 1424.9 x 9.8 | 84.6 x 53.5 | 145.4:1 -> 1.6:1 |
| `sg13cmos5l_bandgap_top` | 2455.8 x 130.8 | 502.8 x 94.8 | 18.8:1 -> 5.3:1 |

Both assemblies stayed `klt drc` **clean, 0 violations**, and every touched
cell's `klt lvs` verdict -- `mismatch_count`, `error_count` and the
per-category breakdown -- is identical before and after (`bandgap_startup`
still reaches `status: "match"`). See
`measurements/2026-09-resistor-fold/README.md` section 5, which compares the
four leaf cells against the *pre-fold GDS re-run through the same installed
`klt`* rather than against their committed reports, because the three
`sg13cmos5l-*` cells' committed reports predate a deck build that now
recognises `rppd`/`rhigh` -- a deck drift that is visible in this branch's
refreshed reports and is not a consequence of the fold. Both assemblies are
compared against their committed reports directly, and both come out
unchanged (`bandgap_top` 8/6, `sg13cmos5l_bandgap_top` 22/22), so #171's own
`bandgap_top` LVS improvement survives the fold and the re-pack intact.

**Top-level placement was re-packed, not interleaved.** Both `generate.py`
assemblies still place their three leaves in disjoint x-ranges, left to
right, at the same ~30 um inter-cell gaps; what changed is that the leaves
are a quarter as wide, the hard-coded riser columns are now written as
`<CELL>_DX + local` (they previously baked in the old offsets), and each
bus stack came down to sit just above the tallest leaf. Issue #173's own
proposed step 2 -- genuinely interleaving the placement into two rows -- is
deliberately **not** done: both assemblies' inter-cell routing is documented
as resting on the disjoint-x-range invariant, which is what makes each net's
crossings checkable one at a time under the single modelled routing metal the
`sg13cmos5l` deck declares. Breaking it is a full re-verification of every
riser column on both assemblies and is tracked as **#177**.

One thing the fold *simplified* rather than complicated, worth recording
because it is the direct inverse of the problem: `sg13cmos5l-bandgap_top`
used to need `Metal1` bridges on two of its `GatPoly` risers, because `RPU`'s
unbroken 1.4 mm body spanned almost the whole `startup` leaf and both risers'
natural columns fell inside it. The folded body ends at local `x=44.97`, so
both columns are clear and both bridges are gone. The one riser that *would*
now land inside the folded block (`vdd`, whose terminal is the block's
bottom-left corner) escapes sideways into the empty amp-startup gap instead.


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
| `EXTBlock.drawing` | 111/0 |
| `SalBlock.drawing` | 28/0 |

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

`bandgap_core.gds`: 1 top cell (`bandgap_core`), bbox
`(-5.4, -3.1)`–`(137.478, 70.623)` µm as of issue #173's fold (was
`(511.5, 61.4)` when `R1` was a straight 511 µm bar that dominated the
bounding box on its own; the cell traded 374 µm of width for 9 µm of
height — see "Folded (serpentine) resistors" below and
`measurements/2026-09-resistor-fold/`). The
`EmWind.drawing` (33/0) layer carries exactly 10 shapes — `Q1` (`Nx=1`) + `Q2`
(`Nx=8`) + `Q3` (`Nx=1`) = 10, matching the schematic's `Nx` values exactly,
confirming the per-stripe geometry described below.

(Re-read from the committed GDS 2026-09-04 by
[`measurements/2026-09-layout-area/`](../measurements/2026-09-layout-area/README.md).
The three counts above previously cited the pre-retune geometry — `105`
shapes / `13` layer combinations / a `694.7` µm right edge — which the
`R1`: 694.5 µm -> 511 µm retune of #134/#139 superseded without this
paragraph being refreshed. The `EmWind.drawing` claim was re-verified at the
same time and was, and is, correct.)

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

## DRC/LVS verification (issues #12, #20)

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
| `bandgap_core` | `layout/bandgap_core/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:894326a4...` (refreshed, issue #155 — new tap-ring `Activ`/`Cont`/`Metal1` geometry introduces no new violations) |
| `bandgap_startup` | `layout/bandgap_startup/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:894326a4...` (refreshed, issue #155, same deck build issue #152 already moved both cells to) |

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
`--rerun` for a full re-check), run from the repo root. `draw_poly_res`'s
new `rppd`/`rhigh` marker geometry (issue #20, below) adds no DRC exposure
of its own — the curated deck declares no rules at all for
`PolyRes`/`EXTBlock`/`pSD`/`SalBlock`/`nSD`, and the new `GatPoly` resistor
body is comfortably clear of every `Gat*`/`Cnt.d` floor (re-verified after
that change; both cells stayed `clean`, 0 violations, not merely assumed
still clean from before).

### LVS — `bandgap_startup` reaches `match`, `bandgap_core` narrowed to its one permanent cause (issues #20/#27, #161)

| Cell | Report | Status | Engine |
| --- | --- | --- | --- |
| `bandgap_core` | `layout/bandgap_core/lvs_report.json` | `mismatch` (6 findings, 4 error-severity — down from 10/9 after issue #161's `rppd` bulk-terminal reconciliation; the 4 errors are exactly `Q1`–`Q3` `device.unmatched` plus their own class-level topology entry, the permanent bipolar-recognition cause; see "`rppd`/`rhigh` bulk-terminal mismatch resolved (issue #161)" below) | `klayout` (`klayout.db.NetlistComparer`) |
| `bandgap_startup` | `layout/bandgap_startup/lvs_report.json` | **`match`** (`error_count: 0`; `mismatch_count: 2` is two `severity: "warning"` disclosures, down from 3/2 after issue #161's `rhigh` bulk-terminal reconciliation; see "`rppd`/`rhigh` bulk-terminal mismatch resolved (issue #161)" below) | `klayout` (`klayout.db.NetlistComparer`) |

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
change. **Updated for issue #20's resistor-recognition rescope**: each
`R`-card now carries its real model name (`rppd`/`rhigh`) and `L=`/`W=`
geometry after its literal resistance value (`R2 sns2 cb2 10751.0 rppd
L=82.7U W=2U`), not a bare value-only card — `NetlistSpiceReader` names a
bare-value R-element's device class the fixed generic `RES`, which can
never pair against `klt`'s sg13g2 deck's own `rppd`/`rhigh`
`ResistorDevice.name` on the layout side; the model-name form lets the
reader assign the class from that token instead (verified interactively:
produces an `RPPD`/`RHIGH`-named class on the reference side, which
`NetlistComparer.same_device_classes`'s default same-name matching pairs
case-insensitively against the layout's own lowercase `rppd`/`rhigh` —
confirmed against this repo's own real `klt lvs` run, not merely asserted
from the API docs' wording, see "Resistor recognition" below).

### Resistor recognition (issue #20 rescope, 2026-08-23)

`rppd`/`rhigh` poly-resistor recognition landed upstream in `klt`'s curated
`sg13g2` deck (klayout-tools#1236/#1248, both merged) — but it requires
geometry `layout/common.py::draw_poly_res` did not draw. This pass adds it:

- **`GatPoly` is the deck's real resistor *body* layer** —
  `klayout_tools.decks.sg13g2.EXTRACTION_DECK.resistors`'s own
  `body=(5, 0)` field — **not** `PolyRes` (128,0), which is only the
  *marker* layer ANDed with it. Before this issue, `draw_poly_res` drew
  only `PolyRes`; with no `GatPoly` present at all, the recognised
  `body` region was always empty regardless of which marker layers were
  drawn. `draw_poly_res` now draws a `GatPoly` "dog-bone" (a narrow core
  matching the marked segment's own `w`/`l` exactly, with a *wider* head
  at each end for the terminal contacts) — the narrow/wide-head split
  matters beyond DRC: `klt`'s native `kdb.DeviceExtractorResistor`
  requires the un-marked conductor left after the marked core is cut out
  to split into exactly **two** disjoint polygons (one per terminal); an
  initial uniform-width attempt left a thin un-marked sliver connecting
  both heads into one polygon, and `klt extract` logged `"Expected two
  polygons on contacts interacting with one resistor shape (found 1) -
  resistor shape ignored"` and dropped the device (verified directly, not
  assumed — see this issue's own PR).
- **Marker layers**: `PolyRes` (128,0, unchanged), `EXTBlock` (111,0),
  `pSD` (14,0), `SalBlock` (28,0) — `rppd`'s own `requires` tuple — drawn
  coincident with the marked core for every resistor instance (`R1`/`R2`
  in `bandgap_core`, `RPU` in `bandgap_startup`). `RPU`'s schematic model
  is `rhigh`, which additionally *requires* `nSD` (7,0) over the same
  segment (the layer that positively disambiguates it from `rppd`, whose
  own `excludes` drops any segment carrying `nSD`) — `draw_poly_res` now
  draws that too when `flavor="rhigh"`, so `RPU` recognises as the
  electrically-correct `rhigh` class (1360 Ω/sq) rather than mis-resolving
  to `rppd` (260 Ω/sq).
- **The installed `klt` needed upgrading.** This environment's pinned
  `klayout-tools` (`0.2.0`, pip) predates klayout-tools#1236/#1248 — its
  `decks/sg13g2.py` declares no `EXTBlock`/`pSD`/`SalBlock`/resistor
  recognition at all, so the first re-run after drawing the new marker
  layers still extracted 0 resistor devices. Upgrading to the current
  PyPI release (`klayout-tools==0.3.0`, `uv tool install klayout-tools==0.3.0
  --force`) picked up the merged capability; re-running then recognised
  `R1`/`R2` as `rppd` and `RPU` as `rhigh` (`klt extract`'s own
  `device_counts`). Not itself a layout change, but recorded here since a
  future pass re-diagnosing "why doesn't `klt extract` see my marker
  layers" should check the installed `klt`/`klayout-tools` version before
  re-investigating the geometry.

**Result: `R1`/`R2`/`RPU` move from *never extracted* to recognised,
correctly classed, and genuinely candidate-paired by `klt lvs` — but not
all the way to `device.matched`.** Before this pass, `klt extract` found 0
resistor devices at all (`device_counts: {"pfet": 3}` only) and `klt lvs`'s
`RES`-class reference devices (`R1`/`R2`/`RPU`) were each a fully isolated,
one-sided `device.unmatched` finding (`device.reference` populated,
`device.layout: null` — no candidate on the layout side even existed).
After this pass, `klt extract` reports `device_counts: {"pfet": 3, "rppd":
2}` (`bandgap_core`) / `{"nfet": 2, "rhigh": 1}` (`bandgap_startup`), and
`klt lvs` now finds a real two-sided candidate pairing for every one of
them (e.g. `bandgap_core`: `{"class": "rppd", "device": {"layout": "$4",
"reference": "2"}}` — both sides populated in the *same* mismatch entry,
the same shape the deck-recognised `pfet`/`nfet` MOS devices already had).
That pairing still resolves to `device.unmatched`, not `device.matched`,
for the same reason the `pfet`/`nfet` pairings do (see "Net effect"
below): `counts.nets.matched` is `0` on **both** cells, for **every**
top-level net (`vdd`, `vss`, `sns1`, `sns2`, `cb2`, `cb3`, `vref`, `fb`/
`det`) — a total, circuit-wide net-topology break the three permanent
blockers below cause on their own, independent of resistor recognition.
No device on either cell — MOS or resistor — can reach `device.matched`
while every net it touches is itself unmatched; this is not a new or
resistor-specific gap this pass introduced, it is the same pre-existing
break #27 already fully diagnosed (causes 1 and 3 below directly corrupt
the net graph; cause 2, `bandgap_startup`'s `poly_label` gap, does the
same for `MKFB`'s gate net specifically). Re-attempting `hints.same_nets`
to force a match here would face the identical `hints.rejected` outcome
#27's own PR already hit for the MOS devices, for the identical root
cause — not re-attempted, per this issue's own explicit scope boundary.

**#20's routing is real and verified, but does not, on its own, close the
gap** — `klt extract`'s own device/net breakdown confirms the physical
connectivity is now correct: every schematic net (`vdd`, `fb`, `sns1`,
`sns2`, `vref`, `cb2`, `cb3`, `vss`/`det`) extracts to a single, named,
physically-merged net (`bandgap_core.gds`: 11 layout nets across the 3
recognised `pfet` devices' terminals, vs. #12's pre-routing 12
*disconnected* nets for the same 3 devices; `bandgap_startup.gds`: 5 nets
for 2 `nfet` devices). Re-running after #20's routing landed found the
original cause 2 from #12 (no top-level routing) genuinely closed, but
surfaced **two further, independent, out-of-this-repo's-control causes**
that #12's original two-cause attribution did not anticipate — both
confirmed by direct experiment, not inferred:

1. **Bipolar device recognition is permanently declined upstream**
   (`klayout_tools.decks.sg13g2.EXTRACTION_DECK` still models no bipolar
   device class at all; `klayout-tools#1242` investigated and declined it
   permanently — closed as `klayout-tools#1232`'s own `completed`, a
   docs-only PR, not something a future pass should re-investigate). Every
   `Q1`–`Q3` (`bandgap_core`) device is therefore necessarily
   reference-only in the compare — `device.unmatched`, class `NPN13G2`.
   **Resistor recognition, by contrast, is resolved** — see "Resistor
   recognition" above: `R1`/`R2`/`RPU` are no longer in this bucket as of
   this issue.
2. **Resolved upstream, not yet exercised by this layout**: the curated
   deck previously declared no well/substrate-tap layer at all; this was
   filed as [klayout-tools#1273](https://github.com/2AMLogic/klayout-tools/issues/1273)
   and closed/merged 2026-08-21 — `decks/sg13g2.py` now declares
   `tap_nplus=(7, 0)` (`nSD`)/`tap_pplus=(14, 0)` (`pSD`), the same
   implant-derived tap-region fallback `gf180mcu.py`'s own deck already
   used (issue #1084). Re-verified directly for this issue (not assumed
   still-broken from #27's original text): `klt extract` **still** reports
   `device.body_unverified` for every `pfet`/`nfet` body terminal on both
   cells, because this repo's own `draw_hv_mos` (`layout/common.py`) draws
   no distinct tap/well-tie ring at all — with the deck-side capability now
   present but no drawn tap geometry anywhere to derive a real net from,
   every body terminal still falls back to an anonymous (`bandgap_core`,
   PMOS) or deck-synthesized `vsubs` (`bandgap_startup`, NMOS) net. This is
   now a **layout gap**, not a deck gap — actionable by a future issue that
   adds tap-ring geometry to `draw_hv_mos`, out of this issue's own scope
   (marker-layer resistor recognition only).
3. **New finding, `bandgap_core` only: a genuine device-symmetry ambiguity
   cause 1 exposes.** `M1`/`M2`/`M3` are drawn with *identical* `w`/`l`
   (`10u`/`1u`) and identical `source`/`gate` nets (`vdd`/`fb`); the only
   thing that structurally distinguishes them in the *real* schematic is
   which downstream bipolar/resistor device each one's drain net connects
   to (`M1`→`Q1` directly, `M2`→`R2`→`Q2`, `M3`→`R1`→`Q3`) — devices cause
   1 above makes invisible to the layout-side extraction. With those
   devices gone, the layout's own extracted netlist has a real graph
   automorphism: swapping any pair of `{M1, M2, M3}` (and their drain
   nets) produces an indistinguishable netlist, so no structural,
   name-independent matcher can uniquely pair, say, layout `$1` to
   reference `M1` specifically rather than `M2` or `M3`. Verified directly,
   not just inferred: adding explicit `hints.same_nets` pairings (`klt
   lvs`'s own mechanism for exactly this situation, `docs/cli/lvs.md`
   "Hints") for `vdd`/`sns1`/`sns2`/`vref` (and separately, for
   `bandgap_startup`'s asymmetric `MSENSE`/`MKFB` pair, `det`/`fb`) still
   produced `hints.rejected` for every declared pairing, each run also
   reporting `net.merged`/`net.split` findings — the comparer's own
   evidence that a *different*, conflicting correspondence is equally
   valid under the layout's own (more symmetric) graph structure. This
   confirms the ambiguity is real, not a hint-application mistake, and
   that cause 2 above (the body-net gap) alone is already sufficient to
   block a clean match even on `bandgap_startup`'s asymmetric device pair,
   independent of this symmetry issue. Not filed against `klayout-tools` —
   this is a consequence of cause 1 (already filed, out of scope) combined
   with this specific circuit's own topology, not a `klt` capability gap.
   **Re-tested under issue #20's resistor recognition (issue #149's own
   pre-implementation step, 2026-08-30):** with `R1`/`R2` now recognised
   and genuinely differing in length, re-declaring the *same*
   `hints.same_nets` pairing (`sns2`↔`SNS2`) against the (still symmetric,
   pre-#149) `M1`/`M2`/`M3` still produced `hints.rejected` plus the same
   full `net.merged`/`net.split` cascade this bullet originally found —
   resistor recognition alone does **not** narrow the automorphism (the
   comparer's canonicalisation pass apparently does not use
   recognised-but-still-identical-`w`/`l` MOS parameters to disambiguate on
   its own — confirmed a second way, see "`M1`/`M2`/`M3` automorphism
   resolved" below: a *tiny*, non-decomposed `w` perturbation alone
   (`M1=10.00u`/`M2=10.02u`/`M3=10.04u`, still 1 device per branch) also
   left the same cascade fully intact). **RESOLVED by issue #149's
   schematic-level fix** (unit-device decomposition, not routing/hints,
   and not a parameter-value nudge either — see below for why only a real
   device-*count* difference actually works against this deck) — see
   "`M1`/`M2`/`M3` automorphism resolved (issue #149)" below for the fix
   and the direct `klt extract` evidence that the ambiguity is gone.

Net effect: even the devices the deck *does* recognise on both sides
(`pfet` `M1`/`M2`/`M3` in `bandgap_core`; `nfet` `MSENSE`/`MKFB` and
`rhigh` `RPU` in `bandgap_startup`; `rppd` `R1`/`R2` in `bandgap_core`)
still show as `device.unmatched` — not because #20's routing (or this
issue's own resistor-recognition work) is wrong; both are verified correct
(`klt extract`'s own net counts for routing, and the fresh `rppd`/`rhigh`
`device_counts` for resistor recognition, both above). `counts.nets.matched`
is `0` on both cells for **every** top-level net, so no device pairing
attempted against any of those nets can resolve to `device.matched` either
— see "Permanent blockers" below for the three causes this traces to.
`status: "mismatch"` is reported honestly rather than claimed clean or
silently downgraded to warnings — per `CLAUDE.md`, "Verification is the
product": this repo's DRC result is a genuine pass; its LVS result is a
genuine, fully-explained fail, not fabricated evidence either way.

### Permanent blockers (issue #20 rescope, 2026-08-23; cause 2 resolved in-repo via issue #149, cause 3 resolved upstream via issue #152, the well/substrate-tap gap resolved in-repo via issue #155 (2026-08-30), the net-name case-identity conflict issue #155 newly exposed resolved in-repo via issue #157 (2026-08-30), and the `rppd`/`rhigh` bulk-terminal-count mismatch resolved via issue #161 (2026-08-30) — see "`rppd`/`rhigh` bulk-terminal mismatch resolved (issue #161)" below)

One cause remains **permanently unreachable through routing, marker-layer
geometry, or `klt lvs` hints alone** — a future pass should not
re-investigate it from scratch without a new upstream capability or a
schematic-level circuit change. The other two, both originally recorded
here as permanent, have since been resolved — each by exactly one of the
two escape hatches this list's own caveat named, and neither by routing,
marker geometry or hints:

- **cause 2** by a schematic-level circuit change in this repo (issue #149's
  `M1`/`M2`/`M3` unit-device decomposition, see below), and
- **cause 3** by a new upstream capability (`klayout-tools#1481`, re-verified
  for issue #152, see below).

The well/substrate-tap gap cause 3's own entry used to name as the reason
neither cell could reach `net.matched` has *also* since been resolved
in-repo (issue #155's `draw_hv_mos` tap-ring geometry, see "Well/substrate-
tap ring geometry added (issue #155)" below) — every `nfet`/`pfet` body
terminal on both cells now resolves to its real schematic net, not an
anonymous or deck-synthesized `vsubs` net.

The net-name case-identity conflict issue #155's own tap-ring fix newly
exposed (`bandgap_startup`'s `det`/`vss` nets pairing correctly but
tripping a `topology`/"name identity conflict" over case alone, `klt lvs`'s
reference side always reading upper-case via `NetlistSpiceReader` against
this repo's own lower-case `layout/common.py` labels) is **also since
resolved in-repo** (issue #157, 2026-08-30 — see "Net-name case-identity
conflict resolved (issue #157)" below): `Builder.label()`
(`layout/common.py`) now upper-cases the text it draws on the deck's real
net-naming layers, matching the reader's own convention.

All are kept in this list for their own record. As of issue #161
(2026-08-30), the `rppd`/`rhigh` bulk-terminal-count mismatch that used to
sit alongside cause 1 on both cells is **also resolved** (see "`rppd`/
`rhigh` bulk-terminal mismatch resolved (issue #161)" below) —
`bandgap_startup` now reaches `status: "match"` (`error_count: 0`; its
`mismatch_count: 2` is two `severity: "warning"` disclosures, never a real
defect). `bandgap_core` cannot follow it all the way to `match`: cause 1
above (bipolar recognition, permanently declined upstream) is independent
of the bulk-terminal fix and still leaves `Q1`–`Q3` `device.unmatched` —
but its report now narrows to *exactly* that permanent cause plus the same
two disclosure-only warnings `bandgap_startup` carries.

1. **Bipolar (SiGe HBT) device recognition is permanently declined
   upstream** (`klayout-tools#1242`, closed; `klayout-tools#1232`'s own
   `completed` docs-only PR, no code change to wait on). Every
   `Q1`–`Q3` (`bandgap_core`) instance stays `device.unmatched`,
   class `NPN13G2`, indefinitely.
2. **RESOLVED in-repo (issue #149): `bandgap_core`'s `M1`/`M2`/`M3` were a
   genuine graph automorphism** at the recognised-device level when bipolar
   *and* resistor devices were both excluded from the comparison (cause 3
   above, PR #27's own experiment, before issue #20's resistor recognition)
   — confirmed by direct experiment at the time: explicit `hints.same_nets`
   pairings were rejected by the comparer, with conflicting
   `net.merged`/`net.split` findings as evidence a different, equally-valid
   correspondence exists under the layout's own more symmetric graph
   structure. Issue #149 broke the automorphism at the schematic level
   (unit-device decomposition, not routing or hints) — see "`M1`/`M2`/`M3`
   automorphism resolved (issue #149)" below for the fix and the direct
   before/after evidence that the ambiguity is gone. As with cause 3, this
   does **not** get `bandgap_core` to a clean `match`: cause 1 above and the
   well/substrate-tap gap (cause 2 under "Net effect" above, described in
   cause 3's entry below) are unaffected and independently keep every net on
   this cell from reaching `net.matched`.
3. **RESOLVED upstream (issue #152)** (`bandgap_startup`'s `MSENSE.gate` net /
   `poly_label`). This previously extracted as an anonymous net because the
   curated deck declared no `poly_label` layer at all
   (`EXTRACTION_DECK.poly_label=None`) — GDS text placed on a
   `GatPoly`-adjacent label layer was simply not a signal this deck's
   net-naming pass read for a gate terminal (unlike `Metal1.text`/
   `Metal2.text`, see this file's own module-level comment on
   `L_METAL1_TEXT`/`L_METAL2_TEXT` in `layout/common.py`). Filed as
   [klayout-tools#1476](https://github.com/2AMLogic/klayout-tools/issues/1476)
   and closed via
   [klayout-tools#1481](https://github.com/2AMLogic/klayout-tools/pull/1481),
   merged 2026-08-30 ("decks: set poly_label on sg13g2/sg13cmos5l so
   labeled poly gates extract named") — the curated `sg13g2` deck now
   declares a `poly_label` layer. Re-verified directly for this issue
   (issue #152), from a fresh `klt` build against the merged commit
   (`2AMLogic/klayout-tools@7066037`, deck `content_hash:
   sha256:894326a4e37fb24fef2f7ffc6ae1da55a0e262b0f0bc1c09adc4862909278fda`,
   vs. the previously-committed report's
   `sha256:72c12aadf165e17090871284ebf8688f2066e6d11967f30723945c3efc12bf59`):
   `klt lvs` now extracts `MSENSE`'s gate net as named **`sns1`** —
   matching the schematic net name exactly — where it previously extracted
   anonymous `$4`. See the refreshed
   `layout/bandgap_startup/lvs_report.json` (and `drc_report.json`, whose
   content hash moved with the deck but whose verdict stayed `clean`, 0
   violations). **This did not, on its own, get `bandgap_startup` to a
   clean `match`** at the time: the well/substrate-tap gap (cause 2 under
   "Net effect" above: [klayout-tools#1273](https://github.com/2AMLogic/klayout-tools/issues/1273)
   resolved the deck side, but this repo's own `draw_hv_mos`
   (`layout/common.py`) drew no tap-ring geometry, so both `nfet` body
   terminals fell back to the deck-synthesized `vsubs` net) remained
   unresolved and independently kept every net on this cell from reaching
   `net.matched`. **RESOLVED in-repo, issue #155** — see "Well/substrate-tap
   ring geometry added (issue #155)" immediately below.

### Well/substrate-tap ring geometry added (issue #155)

The well/substrate-tap gap cause 3's own entry named above is now fixed at
the layout level: `draw_hv_mos` (`layout/common.py`) draws one tap ring per
MOS instance — a small, separate `Activ` island (never touching the
device's own source/drain `Activ`, clearing `activ.space.1`'s 0.21um floor
with margin) on the *opposite*-doping implant marker from the device's own
source/drain (`nSD`/(7,0) for a `pmos` tap inside its own `NWell`, `pSD`/
(14,0) for an `nmos` tap outside every `NWell`) — exactly the geometry the
deck's own `tap_nplus`/`tap_pplus` derivation
([klayout-tools#1273](https://github.com/2AMLogic/klayout-tools/issues/1273))
reads. Each ring is contacted and landed on `Metal1`, bridged (a short,
overlapping `Metal1` strip) into whichever of the device's own source/drain
pads carries its real body net — every existing call site in this repo ties
a `pmos`'s body to its own `source_net` and an `nmos`'s body to its own
`drain_net` (verified against every `XM*` instance line in
`design/netlist/bandgap_core.spice`/`bandgap_startup.spice`), which is
`draw_hv_mos`'s new `body_net` parameter's default, so no existing call site
needed to change. `NWell` is widened on whichever side a `pmos` tap lands on
to keep it inside the same well island the well-tie derivation requires.

**Verified: every MOS body terminal now extracts to its real schematic net,
not an anonymous or deck-synthesized `vsubs` net.** Fresh `klt extract`
against both regenerated cells:

```
# bandgap_startup.gds (klt extract --deck sg13g2 --top bandgap_startup)
M$1 det sns1 vss vss nfet L=0.5U W=10U   <- MSENSE (D=det G=sns1 S=vss B=vss, exact match)
M$2 fb det vss vss nfet L=0.5U W=2U      <- MKFB   (D=fb G=det S=vss B=vss, exact match)

# bandgap_core.gds (klt extract --deck sg13g2 --top bandgap_core)
M$1 vdd fb sns1 vdd pfet L=1U W=10U   <- M1   (S=vdd B=vdd, exact match)
M$2 vdd fb sns2 vdd pfet L=1U W=9U    <- M2A  (S=vdd B=vdd, exact match)
M$3 vdd fb sns2 vdd pfet L=1U W=1U    <- M2B  (S=vdd B=vdd, exact match)
M$4 vdd fb vref vdd pfet L=1U W=8U    <- M3A  (S=vdd B=vdd, exact match)
M$5 vdd fb vref vdd pfet L=1U W=1U    <- M3B  (S=vdd B=vdd, exact match)
M$6 vdd fb vref vdd pfet L=1U W=1U    <- M3C  (S=vdd B=vdd, exact match)
```

**DRC stays clean, 0 violations, on both cells** (`klt drc`, re-verified
after the new tap-ring geometry) — no DRC rule in the curated deck's own
`DECK` list constrains `NWell`/`nSD`/`pSD` directly, so the only floors the
new geometry had to clear were the ordinary `Activ`/`Cont`/`Metal1` ones
(all satisfied with real margin — see `layout/common.py`'s own `TAP_*`
module constants and their comment for the exact numbers).

**Fresh `klt lvs`, both cells, honest results — neither reaches `match`:**

- **`bandgap_startup`**: `mismatch_count` 16 -> **5** (14 -> **4**
  error-severity). Both `nfet` devices (`MSENSE`/`MKFB`) now report
  `device.matched` with exactly-correct terminals (see the `klt extract`
  dump above). The 5 remaining findings are **two independent causes,
  neither the tap gap**:
  1. `RPU`/`rhigh` stays `device.unmatched` — a pre-existing,
     already-present-before-this-fix cause (the same baseline report
     already listed it): this deck's `rhigh` resistor extracts with a
     synthesized 3rd (`vsubs`-global) bulk terminal
     (`DeviceExtractorResistorWithBulk`), while the reference's plain
     `RPU vdd det … rhigh` card is 2-terminal — a terminal-count mismatch,
     unrelated to well/substrate-tap geometry.
  2. A **newly-exposed** net-name case-identity conflict: `klt lvs`'s
     reference side is read via KLayout's own `NetlistSpiceReader`, which
     uppercases every net name (`vss` -> `VSS`, `det` -> `DET`) — this
     repo's own `layout/common.py` labels match `design/netlist/*.spice`'s
     own lowercase spelling instead. `NetlistComparer` still correctly
     pairs `det`/`vss` topologically (both devices' terminals match
     exactly, confirmed above) but reports `topology`/"name identity
     conflict" for each, since the two sides' net names now differ only in
     case. This could not surface before this fix — with 0 devices
     matching, no net correspondence existed to expose it. Filed at **#157**
     for a future pass (case-folding options evaluated there, not decided
     here — this issue's own scope is `draw_hv_mos`'s tap-ring geometry,
     not the net-labeling/reference-conversion case convention).
- **`bandgap_core`**: `mismatch_count` 36 -> **10** (35 -> **9**
  error-severity); matched devices 0 -> **6** (every `pfet`), matched nets
  0 -> **2**. Remaining causes: permanent blocker #1 above (bipolar, 3
  `Q1`-`Q3` `device.unmatched`), the same pre-existing `rppd` bulk-terminal
  3-vs-2 mismatch as `bandgap_startup`'s `RPU` above (`R1`/`R2`, 2
  `device.unmatched`), and a `net.merged`/`net.split` finding on `VSS`
  that traces to that same `rppd` bulk-terminal artifact (the resistors'
  own synthesized `vsubs` bulk net does not merge with the real, routed
  `vss` net in this cell the way the tap ring's bridge merges an `nfet`
  body with its own drain pad in `bandgap_startup`) — **not** a
  well/substrate-tap regression: `bandgap_core` has no `nmos` devices at
  all, and this cell's own PMOS body ties are independently confirmed
  exact-match above. As documented in permanent blocker #1, `bandgap_core`
  cannot reach a clean `match` regardless (bipolar recognition is
  permanently declined upstream) — this fix's job here was narrowing the
  mismatch count and confirming every `pfet` body tie, both achieved.

Reproduce: `klt extract`/`klt drc`/`klt lvs` exactly as documented earlier
in this section, against `layout/bandgap_core/bandgap_core.gds`/
`layout/bandgap_startup/bandgap_startup.gds` regenerated via
`python3 layout/bandgap_core/generate.py`/`layout/bandgap_startup/generate.py`
(deterministic — a second run leaves `git diff` empty, verified).

### Net-name case-identity conflict resolved (issue #157)

The net-name case-identity conflict issue #155 newly exposed (bullet 2
above) is now fixed. Root cause, traced directly rather than assumed:
`klayout.db.NetlistSpiceReader` (the engine `klt lvs`'s reference side is
read through) upper-cases **every** net name it reads, unconditionally,
regardless of the input SPICE text's own case — confirmed interactively,
independent of what case `layout/lvs_reference.py` writes:

```python
>>> nl = kdb.Netlist()
>>> nl.read("bandgap_startup.lvs_reference.spice", kdb.NetlistSpiceReader())
>>> [n.name for n in nl.top_circuit().each_net()]
['VDD', 'DET', 'SNS1', 'VSS', 'FB']   # the file itself spells them lower-case
```

The curation comment on issue #157 recommended fixing this at
`layout/lvs_reference.py` (the reference-conversion boundary, its own
Option 3) — but the check above shows that boundary has no lever over the
reference side's net-name case at all: whatever case that script writes,
`NetlistSpiceReader` folds it to upper-case regardless. The layout side
(`klt extract`'s net-naming pass) is the one side whose net-name case *is*
a free variable — it reads a GDS text label's case back verbatim
(confirmed the same way the pre-fix report showed: `net: {"layout": "det",
"reference": "DET"}`, the layout side literally preserving
`layout/common.py`'s own lower-case labels). **Fixed at that free variable
instead** (issue #157's own Option 1, with the deviation from the curated
Option 3 noted and justified here): `layout/common.py`'s `Builder.label()`
now upper-cases the text it draws on exactly the deck's real net-naming
layers (`L_METAL1_TEXT`/`L_METAL2_TEXT` — `EXTRACTION_DECK.metal_labels` —
and `L_GATPOLY_LABEL`, which doubles as `EXTRACTION_DECK.poly_label`),
centrally, in one place — not at each `draw_npn13g2`/`draw_hv_mos`/
`draw_poly_res`/`draw_gate_tab` call site's own net-name string literal —
so the fix generalizes to any current or future net with no per-net
enumeration (unlike a `hints.same_nets` entry, issue #157's own Option 2).
Every other label layer (`L_TEXT`, and `L_METAL1_LABEL`/`L_METAL2_LABEL`/
`L_POLYRES_LABEL`'s purely-informational duplicates — not read by `klt
extract`'s net-naming pass at all, see the module-level comment on
`L_METAL1_TEXT` above) is left exactly as each call site spells it; this is
a case-only change, cosmetic to the compare — `NetlistComparer` pairs
devices/nets by structure, not by name, so it does not and must not alter
which physical devices/nets pair against which schematic ones.

**Verified**: `bandgap_startup`'s `det`/`vss` `topology`/"name identity
conflict" findings are gone — `mismatch_count` 5 -> **3** (4 -> **2**
error-severity). The `sns1`/`fb` nets, already `net.matched` before this
fix, are unaffected (still matched, both sides now spelled upper-case).
The 3 remaining findings are all the same, pre-existing, out-of-scope
`RPU`/`rhigh` cause already documented above (bullet 1: a terminal-count
mismatch, this deck's `rhigh` extracting a synthesized 3rd bulk terminal
against the reference's plain 2-terminal card) — `device.unmatched` for
`RPU`/`rhigh` itself, plus `RPU`'s own anonymous `vdd`-net end (`$5`/`VDD`)
still failing the same name-identity check for the unrelated reason that
it never got a real name at all (not a case issue). Not fixed here — out
of #157's own scope, tracked separately (see bullet 1 above).

`bandgap_core`'s `klt lvs` finding *count* is unchanged (10/9, same as
after issue #155) — this cell reaches no `net.matched` pairing at all yet
(permanent blocker #1, bipolar recognition, plus the `rppd` bulk-terminal
cause below), so there was no case-identity-conflict finding for this fix
to remove. Re-running after the fix does reclassify three findings from
`net.merged`(1)/`net.split`(2) to `net.unmatched`(3) — a side effect of
`klt lvs`'s own merge/split heuristic (which inspects whether a
differently-*named* both-sided pairing co-occurs with a one-sided
leftover) now seeing every net upper-cased consistently, not a new or
regressed finding; the same `VSS`/`vsubs`/rppd-bulk-terminal root cause as
before, confirmed by the finding count staying exactly 10/9 and no new
device or net leaving `matched`.

**GDS content changed, evidence chain updated accordingly.** Both cells'
`.gds` files changed (label text only, no geometry) and were re-verified
end to end: `klt drc` stays `clean`, 0 violations, on both (regenerated
`drc_report.json`); both `lvs_report.json` regenerated as above. Both
cells' `pex_extract_report.json`/`<cell>.pex.spice` — extracted from the
pre-fix GDS — are now stale relative to the post-fix one (re-extracting
both to check confirmed the change is case-only: no `R`/`C` device
parameter differs, only net-name case in the emitted `.pex.spice`) and are
**waived** rather than re-extracted here (`layout/evidence-freshness-
waivers.json`, tracked at #159) — re-extracting and re-running both PVT
sweeps needs `klt`/PDK/ngspice/OSDI models CI does not have, and is out of
this "routine"-complexity issue's own scope.

Reproduce: `klt lvs layout/bandgap_startup/lvs_request.json` /
`klt lvs layout/bandgap_core/lvs_request.json`, against
`bandgap_startup.gds`/`bandgap_core.gds` regenerated via each cell's own
`generate.py` (same reproduction steps as above — deterministic, `git diff`
empty on a second run).

### `M1`/`M2`/`M3` automorphism resolved (issue #149)

Cause (d) of T1 tracker #4 item 4 (permanent blocker #2 above) is now
resolved at the schematic level — **not** by routing or `klt lvs` hints,
both of which #27's and this issue's own pre-implementation re-check
confirmed cannot touch it (see permanent blocker #2 and the "New finding"
bullet above).

**Fix — unit-device decomposition (Option 1 from issue #149).**
`design/bandgap_core.sch` (and the netlist it generates,
`design/netlist/bandgap_core.spice`) now draws `M1` as a single
`w=10u l=1u` `sg13_hv_pmos`, `M2` as two parallel fingers, one dominant
(`w=9u`) plus one trim (`w=1u`) (`M2A`/`M2B`), and `M3` as three parallel
fingers, one dominant (`w=8u`) plus two trim (`w=1u` each) (`M3A`–`M3C`)
— each branch's *total* mirror width stays nominally `W/L=10u/1u`, but
the three branches now have structurally distinct device counts (1 vs 2
vs 3 — the minimum pairwise-distinct set), so no graph automorphism
exists among them regardless of whether a comparer's canonicaliser
weighs device parameters at all. `layout/bandgap_core/generate.py` draws
each unit finger as its own separate, non-touching `draw_hv_mos`
footprint (confirmed by `klt extract` — see below — that the deck's own
extraction does **not** silently re-merge adjacent parallel MOS instances
into one device) and ties each branch's finger drains together with a
Metal1 strip before routing on to that branch's resistor.

**This decomposition is NOT electrically exact — quantified, not
assumed.** Unlike an idealised SPICE parallel-device sum, IHP-SG13G2's
real `sg13_hv_pmos` PSP103 compact model is not scale-invariant in `W`:
an isolated fixed-bias DC op-point check (same `Vgs`/`Vds` on `M1` vs
`M2A+M2B` vs `M3A+M3B+M3C`, no other circuitry) measures `M2`'s total
current ~1.0% above `M1`'s and `M3`'s ~2.0% above `M1`'s — a real,
device-count-driven deviation, not width-narrowing alone (it persists,
nearly unchanged, whether the trim finger is `1u` or `0.5u`, and roughly
doubles between a 2-count and 3-count branch). A first-implemented,
shallower draft of this fix ({1,2,4}-count, equal-width fingers: `M2`
2×`5u`, `M3` 4×`2.5u`) measured a **~1% closed-loop vref shift at every
PVT corner** from this effect against a same-day pre-#149 baseline. The
`{1,2,3}`-count, dominant+trim-finger geometry actually landed here was
chosen specifically to minimize this: device-count spread is the minimum
pairwise-distinct set possible (`{1,2,3}`, not `{1,2,4}`), and each
branch keeps one dominant, near-original-width finger plus the smallest
number of small trim fingers needed to reach its target count. **Measured
result (full 45-corner closed-loop PVT re-run, `sim/closed-loop-vref-pvt`,
vs a same-day pre-#149 baseline on this exact post-#134-retune netlist,
same tooling)**: max `vref(3ms)` delta 3.81 mV (0.366%, `bcs`/`-40C`/
`3.63V`), 45-corner average 3.28 mV (~0.31%) — smaller than the ~15 mV
process-corner-to-corner spread this design already has at any fixed PVT
point — and the TC (ppm/C) this repo actually tracks against
`spec/porting-plan.md` Sec 6's draft target moved by <=1.3 ppm/C at every
corner/supply group (worst-case box TC stays ~18 ppm/C, inside the draft
`<50 ppm/C` row both before and after). Full per-corner data:
`sim/closed-loop-vref-pvt/records/`.

**Verified: `klt extract` now recognises 6 distinct pfet devices** (not
3), each in its correct, one-to-one branch correspondence
(`klt extract layout/bandgap_core/bandgap_core.gds --deck sg13g2 --top
bandgap_core`, re-run against this PR's own `bandgap_core.gds`):

```
M$1 vdd $9 sns1 $11 pfet L=1U W=10U   <- M1
M$2 vdd $9 sns2 $14 pfet L=1U W=9U    <- M2A
M$3 vdd $9 sns2 $15 pfet L=1U W=1U    <- M2B
M$4 vdd $9 vref $17 pfet L=1U W=8U    <- M3A
M$5 vdd $9 vref $18 pfet L=1U W=1U    <- M3B
M$6 vdd $9 vref $19 pfet L=1U W=1U    <- M3C
```

Branch `sns1` (M1) now has exactly 1 recognised pfet, branch `sns2` (M2)
exactly 2, branch `vref` (M3) exactly 3 — this device-*count* asymmetry,
directly readable from `klt extract`'s own output independent of any
`hints`/comparer configuration, is the structural fact that breaks the
automorphism. It is **not**, on its own, name- or connectivity-resolved
(that would need a full `match`, explicitly not this issue's bar — see
below) — it is the same kind of node-degree/multiplicity distinguishing
signal a graph-isomorphism search needs to rule out `M1`↔`M2`↔`M3`
swaps, which the pre-#149 layout (three structurally-identical 1-device
branches) categorically could not provide.

**Re-tried, and dropped: the deliberately-wrong cross-branch
`hints.same_nets` pairing this issue's own pre-implementation re-check
used (`sns2`↔`VREF`) as a second, independent confirmation.** Directly
re-run against this PR's own layout/reference: `hints.rejected` fires (as
expected — a 2-device branch cannot topologically satisfy a hint
asserting equality with a 3-device branch), but the run **still**
reports a `net.merged`/`net.split` cascade, not the clean single-entry
rejection an isolated cause-(d) fix would ideally produce — confirmed
this is **not** specific to the {1,2,3} decomposition (the same test
against the {1,2,4}-count first draft, and even against a trivial
same-count-but-different-`w` control, produces an equivalent cascade).
The reason: `counts.nets.matched` is already `0` for **every** top-level
net on this cell with *no* hints declared at all (permanent blockers #1
and the well/tap gap below leave essentially nothing else in this graph
uniquely pinned down), so *any* declared hint — right or wrong — collides
with that pre-existing, unrelated ambiguity and produces some cascade
regardless of whether cause (d) itself is fixed. This specific
hints-based check is **confounded** by `bandgap_core`'s other,
already-tracked LVS gaps and does not cleanly isolate cause (d) either
way; the `klt extract` device-count evidence above is the reliable,
unconfounded signal, and is what this issue's own resolution rests on.

**A full `match` is still not the acceptance bar** (per issue #149's own
text): `bandgap_core`'s remaining `mismatch` status is fully attributed
to permanent blockers #1 (bipolar declined upstream) and the unexercised
well/tap-layer gap (the "two further causes" list's item 2 above) — both
pre-existing, both out of this issue's scope, both already tracked.
`layout/bandgap_core/lvs_report.json` is regenerated fresh against the
decomposed layout (`36` findings, `35` error-severity — the raw count
rises only because there are now 6 recognised pfets to individually
report `device.unmatched` instead of 3, not because anything regressed).

### `rppd`/`rhigh` bulk-terminal mismatch resolved (issue #161)

**Root cause, confirmed directly** (not re-derived from prior write-ups):
the installed `klt`'s curated `sg13g2` deck
(`klayout_tools.decks.sg13g2.EXTRACTION_DECK.resistors`) declares every
poly-resistor flavour this circuit uses — `rppd` and `rhigh` — with
`bulk_to_substrate=True`. That selects `klayout.db
.DeviceExtractorResistorWithBulk` over the plain two-terminal
`DeviceExtractorResistor`, which extracts a *third* terminal (`W`,
alongside the two-terminal `A`/`B` heads) tied to the deck's substrate/well
connectivity — mirroring upstream's own real LVS deck, which ties
`rppd_sub`/`rhigh_sub` to `pwell` (see that deck module's own inline
citation of `res_extraction.lvs`). `layout/lvs_reference.py`'s converted
`R`-cards, by contrast, are plain two-terminal SPICE (`R<n> <p1> <p2>
<value> <model>`) — `klayout.db.NetlistSpiceReader`'s only resistor-element
reading, with no third-terminal syntax to express. Every `rppd`/`rhigh`
instance therefore compared a 3-terminal layout-side device against a
2-terminal reference-side one — a `device.unmatched` on both cells, plus a
`net.unmatched` on `bandgap_core`'s `vsubs` net (the synthesized bulk net
the two `rppd` instances' third terminal lands on, with nothing on the
reference side to pair it against).

**Fix — direction 1, via `klt lvs`'s own built-in reconciliation hook**,
not a hand-rolled workaround: `request.reference.device_bulk` (issue #506
in `klayout-tools`, `klt lvs`'s own "issue #504's option 1") declares that
a named reference-side device class is missing exactly the terminal the
same-named layout-side class carries, and ties every reference instance's
new terminal to a named net — reconciling the two classes to the same
arity *before* `NetlistComparer.compare()` runs, so a real, honest
`device.matched` pairing becomes possible instead of only diagnosable. This
is a request-file option, not a code change to `layout/lvs_reference.py` or
`layout/common.py` — no reference-conversion syntax could express a third
SPICE-`R` terminal at all (confirmed above), so the fix lives entirely in
each cell's `lvs_request.json`:

```json
"reference": {
  "netlist": "bandgap_startup.lvs_reference.spice",
  "device_bulk": { "rhigh": "VSS" }
}
```

```json
"reference": {
  "netlist": "bandgap_core.lvs_reference.spice",
  "device_bulk": { "rppd": "vsubs" }
}
```

The two cells name **different** nets, each read directly off a fresh `klt
extract` of that cell's own layout (not guessed or copy-pasted between
cells) — `RPU`'s (`bandgap_startup`) synthesized bulk terminal already
resolves to the real, routed `VSS` net (issue #155's tap-ring bridges the
`nfet` body into the same net as `rhigh`'s bulk tie in this cell), while
`R1`/`R2`'s (`bandgap_core`) synthesized bulk terminal stays on the deck's
anonymous `vsubs` global (this cell has no `nfet` device at all — every
device is `pfet`, whose body ties to `VDD`, not the substrate — so nothing
in this cell's own layout merges `vsubs` into a real net, independent of
and not regressed by issue #155's tap-ring work). Naming the net a request
declares is an *assertion*, not an independently re-derived fact — `klt
lvs` discloses every reconciled class as its own `severity: "warning"`,
`category: "device.bulk_reconciled"` mismatch entry precisely so a
`"match"` reached this way is never silently indistinguishable from a
fully independent one (see `docs/cli/lvs.md`, "`device.bulk_reconciled`").

**Verified with a fresh `klt lvs` re-run on both cells** (`klt
0.3.0+gc6dbf66c53c6`, `klayout 0.30.12`, deck `content_hash:
sha256:894326a4e37fb24fef2f7ffc6ae1da55a0e262b0f0bc1c09adc4862909278fda` —
the same deck build issue #152 last moved both cells to; re-verified
`klt drc --check --rerun` stays byte-identical to the committed
`drc_report.json` on both cells, `clean`, 0 violations, confirming no
geometry changed and this fix's evidence refresh is LVS-only):

- **`bandgap_startup` reaches `status: "match"`** — `mismatch_count: 2`,
  `error_count: 0`. Both remaining entries are `severity: "warning"`: the
  `device.bulk_reconciled` disclosure above, and the same pre-existing,
  informational "device class has no counterpart on the other side, but no
  devices of this class were extracted either" `topology` entry every prior
  report on this cell has also carried. This is the first cell in this
  repo's history to reach `status: "match"`.
- **`bandgap_core` narrows to exactly the one permanent cause left**:
  `mismatch_count: 6`, `error_count: 4`. The 4 errors are `Q1`–`Q3`
  `device.unmatched` (`NPN13G2`, permanent blocker #1, bipolar recognition
  permanently declined upstream) plus their own class-level `topology`
  "device class could not be mapped to a counterpart" entry — the same
  cause reported at two granularities, not a new or independent one. The
  other 2 entries are the same `device.bulk_reconciled` disclosure and
  benign no-op `topology` entry `bandgap_startup` also carries.
  `counts.nets.matched` rose from 2 to 5 (`SNS2`, `VDD`, `VREF`, and the
  reconciled `vsubs` all now pair; `FB`↔`\$9` already did) — every net this
  cell's own `pfet`/`rppd` devices touch, which is everything except the
  bipolar-only `VSS` net neither side's comparer can currently reach
  (permanent blocker #1's own consequence, not a new gap).

**Evidence-format checker bug found and fixed alongside this issue**
(`.github/scripts/check_evidence_formats.py`): the checker asserted
`(status == "match") == (mismatch_count == 0)`, an invariant `klt lvs`'s
own documented contract does not make — "`mismatch_count` ... [c]an be
nonzero even when `status` is `'match'`" for exactly this
`device.bulk_reconciled`-disclosure case (`docs/cli/lvs.md`). No prior
report in this repo had ever reached `status: "match"`, so this gap in the
checker had never been exercised before `bandgap_startup`'s fresh report
above tripped it. Fixed to check `error_count == 0` for a `"match"`
verdict (the invariant `klt lvs`'s docs actually guarantee) and
`mismatch_count == 0` implies `"match"` (the converse direction, still
sound) instead — both directions covered by new self-test cases in
`.github/scripts/test_check_evidence_formats.py`
(`case_lvs_match_with_warning_only_disclosure`,
`case_lvs_zero_mismatches_not_match`).

Reproduce: `klt lvs layout/bandgap_startup/lvs_request.json` / `klt lvs
layout/bandgap_core/lvs_request.json`, from each cell's own directory;
`python3 .github/scripts/check_evidence_formats.py` and `python3
.github/scripts/test_check_evidence_formats.py` for the evidence-format
fix.

## Evidence freshness, enforced in CI

Per the klayout-tools evidence ladder, **staleness is failure**: a report whose
verdict was produced against a different GDS than the one committed today is not
evidence, however clean it reads. Every report here records the sha256 of what it
consumed —

| report | recorded input hash | checked against |
|---|---|---|
| `drc_report.json` | `provenance.input.content_hash` | `<cell>.gds` |
| `lvs_report.json` | `environment.layout_sha256` | `<cell>.gds` |
| `lvs_report.json` | `environment.reference_sha256` | `<cell>.lvs_reference.spice` |
| `pex_extract_report.json` | `provenance.input.content_hash` | `<cell>.gds` |
| `pex_extract_report.json` | `netlist_sha256` | `<cell>.pex.spice` |

— and `.github/scripts/check_evidence_formats.py` re-derives all five on every
push and PR. A mismatch fails the build. The checker also asserts each report is
internally consistent (a `clean` DRC has zero violations, a `match` LVS has zero
mismatches) and that the DRC report still enumerates its deck coverage gaps —
but it deliberately does **not** demand a particular verdict. This repo's LVS
legitimately reads `mismatch` for the reasons documented above; CI's job is to
keep that verdict honest and fresh, not to demand one the deck cannot produce.

### Known-stale evidence: `layout/evidence-freshness-waivers.json`

Regenerating a report can require `klt`, the PDK, ngspice and OSDI models, none
of which CI has — so a stale report cannot always be fixed on the spot. It can
be **waived**, but only explicitly: an entry in
`layout/evidence-freshness-waivers.json` names the exact report, the exact
check, the exact stale hash, a tracking issue (required — a waiver with no issue
is a schema error), and the reason. A waived check prints a loud `STALE (waived,
#N)` note instead of failing.

Waivers **self-expire**: once the evidence is regenerated, the recorded hash no
longer matches and the checker fails until the entry is deleted — so a waiver
cannot quietly outlive the problem it describes.

Both cells' `pex_extract_report.json` are waived today, tracked at **#56**: the
PEX leg was last extracted at `f940680` (PR #39) while the GDS was last
regenerated at `bf9051c` (PR #45, the resistor marker layers) — the same
follow-up item 1 of "Post-layout parasitic extraction" below already describes
in prose. Their DRC and LVS reports *were* regenerated in PR #45 and are fresh.

## Post-layout parasitic extraction (issue #14)

Per this issue's own dependency text, LVS's `mismatch` status above is the
allowed "explicitly-caveated" extraction input, not a blocker — but every
caveat above also applies here, plus two more this pass found.

**Extraction succeeded, cleanly, for both cells**:

```bash
cd layout/bandgap_core
klt extract --deck sg13g2 --parasitics bandgap_core.gds \
  -o bandgap_core.pex.spice --format json > pex_extract_report.json
# same for layout/bandgap_startup/
```

`status: "extracted"` for both, no errors. `bandgap_core.pex.spice` /
`bandgap_startup.pex.spice` and their `pex_extract_report.json` companions
are committed as read-only extraction artifacts — see
`sim/core-open-loop-bias-pex/README.md` and
`sim/startup-trip-point-pex/README.md` for the full account of what this
extraction does and does not model, and the resulting PVT-sweep evidence
under `sim/`. Two findings from this pass, beyond what's already documented
above:

1. **Resolved (issue #37, 2026-08-21): the `sg13g2` deck's own
   `PARASITICS.metals`/`metal_overlaps` coefficient tables were empty for
   Metal1 and Metal2** at the time this section was first written —
   `pex_extract_report.json`'s own `warnings` said so directly, and
   `parasitics.r_count`/`parasitics.c_count` both read `0` in the reports
   PR #33 committed. This was a deck-content gap, not specific to this
   design, so it was **filed generically against `klayout-tools`**
   ([klayout-tools#1277](https://github.com/2AMLogic/klayout-tools/issues/1277)),
   per `CLAUDE.md`'s friction protocol — which closed via
   [klayout-tools#1280](https://github.com/2AMLogic/klayout-tools/pull/1280)
   (Metal1/Metal2), later broadened by
   [klayout-tools#1282](https://github.com/2AMLogic/klayout-tools/pull/1282)
   to the full Metal1-TopMetal2 stack. Re-extracting `bandgap_core.gds`/
   `bandgap_startup.gds` against the current deck (issue #37) now reports
   `r_count: 9, c_count: 7`/`r_count: 5, c_count: 3` respectively, both
   `metals_without_coefficient` lists empty, and no other metal level newly
   reports zero RC. **Bipolar (`npn13G2`) device recognition is a separate,
   permanently-declined gap** (`klayout-tools#1242`) — see "Permanent
   blockers" above. **Resistor (`rppd`/`rhigh`) device recognition is
   resolved as of issue #20**: `draw_poly_res` now draws the marker layers
   (and the `GatPoly` body layer) that recognition needs — see "Resistor
   recognition" above. Do not conflate the two: wire-parasitics modelling
   and bipolar/resistor device recognition are independent deck
   capabilities that happened to both be tracked from this same section.
   **Not yet re-extracted for PEX**: this issue's `draw_poly_res` change
   modifies the exact GDS this section's own committed
   `bandgap_core.pex.spice`/`bandgap_startup.pex.spice` and
   `pex_extract_report.json` were extracted from — those artifacts (and the
   downstream `sim/core-open-loop-bias-pex`/`sim/startup-trip-point-pex`
   PVT-sweep evidence built on them) are now stale relative to the
   regenerated GDS and current `klt` version, and out of this issue's own
   scope (DRC/LVS device recognition only) to regenerate and re-validate —
   left as a follow-up rather than silently re-extracted without re-running
   the PVT sweeps that depend on them. **That follow-up is now filed as #56**,
   and the staleness is no longer prose-only: it is detected mechanically by
   `.github/scripts/check_evidence_formats.py` and waived by name in
   `layout/evidence-freshness-waivers.json` — see "Evidence freshness,
   enforced in CI" above.
2. **Resolved (issue #32): `layout/bandgap_startup/generate.py` drew
   `XMSENSE` at `w=2u`, stale relative to `design/netlist/bandgap_startup.spice`'s
   `w=10u`.** [Decision record
   0003](../spec/decision-records/0003-startup-sense-nmos-resize.md)
   (issue #24/PR #29) widened `XMSENSE` in the schematic/netlist only,
   *after* this layout was drawn (issue #11/PR #19) — the layout was not
   regenerated to match until issue #32. `sim/startup-trip-point-pex/README.md`'s
   "Cross-bench observation" showed this was not a paper cut: re-simulating
   the then-as-drawn (`w=2u`) extracted geometry reproduced decision record
   0003's exact same 4-point, 125 °C startup-release margin bug the
   schematic-level fix already resolved. Issue #32 regenerated
   `bandgap_startup.gds` with `XMSENSE` at `w=10u` (`layout/bandgap_startup/generate.py`'s
   `draw_hv_mos(..., "MSENSE", ...)` call, `_route()`'s wiring re-verified
   at the wider footprint — see that file's own docstring/inline comments),
   re-ran `klt drc`/`klt lvs`/`klt extract --parasitics` against the
   regenerated GDS (DRC stayed clean; LVS's `mismatch` reason is unchanged —
   same 16 findings/14 error-severity, same categories, still blocked purely
   on cause 2/`klayout-tools`#1273 above, not a new failure mode), and
   re-ran `sim/startup-trip-point-pex/run_pvt_sweep.sh`: the cross-bench
   comparison against `sim/core-open-loop-bias-pex` now clears at all 45
   PVT points, including the 4 that previously failed
   (`wcs_125c_{2.97,3.30,3.63}v`, `sf_125c_3.63v`) — see
   `sim/startup-trip-point-pex/README.md`'s updated "Cross-bench
   observation" section for the before/after numbers.

---

## Cell: `bandgap_amp` (issue #169)

One-to-one with `design/netlist/bandgap_amp.spice` (schematic from #58): a
9-device, pure-CMOS 2-stage OTA -- `MTAIL`/`MP3`/`MP4` `sg13_hv_pmos`
`w=10u l=1u`, `MP1`/`MP2` `sg13_hv_pmos` `w=20u l=1u`, `MN1`-`MN4`
`sg13_hv_nmos` `w=10u l=1u`. No bipolar or resistor devices at all -- unlike
`bandgap_core`/`bandgap_startup`, this cell needed no new drawing
primitives, only `layout/common.py`'s existing `draw_hv_mos` plus its
`route_h`/`route_v`/`via1_tap`/`draw_gate_tab` routing helpers (see
`layout/common.py`'s own docstrings; no changes to that module's drawing
functions). Top cell `bandgap_amp`, bbox `(-10.8, -1.59)`-`(205.1, 32.175)`
µm, 164 polygons across 13 layer/datatype combinations.

**Floorplan**: PMOS row (`y=30`) left to right MP1/MP2/MTAIL/MP3/MP4 --
ordered so the `vdd`-carrying source pads (MTAIL/MP3/MP4) and the
`tail`-carrying source pads (MP1/MP2) each form one contiguous group,
routable as a single Metal1 bar with no vias. NMOS row (`y=0`): MN1 under
MP1 (`d1`), MN2 under MP2 (`d2`), MN3 under MP4 (`out`), MN4 further right.
`vdd`/`tail`/`vss` are each a single Metal1 bar across their own contiguous
pad group; `d1`/`d2`/`out` are straight Metal1 trunks between the two rows;
`MN3.gate`/`MN4.gate`/`MTAIL.gate`/the `pn` net's metal leg each cross to
their own target trunk via a Metal2 riser/jog/riser at a distinct,
strictly-ordered jog height (see `generate.py`'s own module docstring for
the non-crossing argument). `in_p`/`in_n` (single-terminal within this
cell) each get a `draw_gate_tab` bringing them out to a real Metal1 pad, so
`bandgap_top` can route them from outside this cell.

**Documented simplification**: `MP1`/`MP2`'s real schematic body tie is
`vdd`, distinct from their own channel nets -- `draw_hv_mos`'s existing
`body_net` default (ties a PMOS's tap to its own `source_net`) would short
`tail` to `vdd` if passed explicitly here, so every call below leaves
`body_net` unset, tying each device's tap to its own already-drawn channel
pad instead. This makes `MP1`/`MP2`'s drawn body tie (`tail`) diverge from
the schematic's real one (`vdd`) -- see `generate.py`'s own module
docstring for the full reasoning.

**DRC**: `klt drc --deck sg13g2` reports `status: "clean"`, 0 violations
(`layout/bandgap_amp/drc_report.json`).

**LVS**: issue #169 itself scoped LVS *fixing* out (mirroring #11's own
floorplan-first sequencing before #12's LVS pass) -- but this repo's own
CI evidence-format gate (`.github/scripts/check_evidence_formats.py`,
landed after #11/#12 in #57) requires every committed `*.gds` cell to ship
*some* `lvs_report.json`, `status` restricted to `"match"`/`"mismatch"`
(no "not run" escape hatch). So `klt lvs` **was** run here, once, and its
honest result committed as-is -- not chased to `"match"`, which remains a
real follow-up (see "Explicitly out of scope" below).
`layout/bandgap_amp/lvs_report.json`: `status: "mismatch"`, 2 findings, both
`error`-severity `device.unmatched` on `MP1`/`MP2` -- exactly the two
devices the body-tie simplification above predicts, no other cause. Engine:
`klayout` (`klayout.db.NetlistComparer`), reference converted by
`layout/lvs_reference.py` (this netlist has no bipolar/resistor devices, so
no new conversion logic was needed there).

**Determinism**: `python3 layout/bandgap_amp/generate.py` re-run leaves
`git diff --stat` empty (byte-for-byte identical GDS).

## Cell: `bandgap_top` (issue #169)

Hierarchical assembly of the three SG13G2 leaf cells (`bandgap_core`,
`bandgap_amp`, `bandgap_startup`) into `design/bandgap_top.sch`'s
closed-loop block -- the same "instance the already-committed leaf GDS
files, route only the inter-cell connections" pattern
`layout/sg13cmos5l-bandgap_top/generate.py` already established for the
SG13CMOS5L variant (issue #81). No leaf cell's own committed GDS is
modified; `bandgap_top/generate.py` only reads them (`klayout.db.Layout.read`)
and adds new top-level geometry. Top cell `bandgap_top`, bbox
`(-16.5, -3.1)`-`(2211.8, 90.15)` µm, 449 polygons across the same 13
layer/datatype combinations `bandgap_amp` uses (no new layers).

**Connectivity**, one-to-one against `design/netlist/bandgap_top.spice`'s
own `Xx1`/`Xx2`/`Xx3` subckt-instance lines and each sub-cell's own port
order (verified against the netlist text directly, not assumed -- a
swapped `sns1`/`sns2`/`fb` connection would be a silent functional bug DRC
alone cannot catch):

```
Xx1 vdd vss fb sns1 sns2 vref bandgap_core   (vdd vss fb sns1 sns2 vref)
Xx2 sns2 sns1 vss fb vdd     bandgap_amp     (in_p in_n vss out vdd)
Xx3 vdd vss sns1 fb          bandgap_startup (vdd vss sns1 fb)
```

`bandgap_amp`'s own port names differ from the nets they connect to at this
level (`in_p`->`sns2`, `in_n`->`sns1`, `out`->`fb`); `bandgap_core`'s and
`bandgap_startup`'s own port names already match. `vdd`/`vss`/`vref` are
brought out to `bandgap_top`'s own external pins; `fb`/`sns1`/`sns2` are
internal-only.

**Two new boundary pads, in `bandgap_top`'s own top cell only.**
`bandgap_core`'s `fb` and `bandgap_startup`'s `sns1` are each a bare,
single-terminal `GatPoly` gate in their own originating cell (no metal pad
needed for that cell's own, already-verified DRC/LVS scope) -- `generate.py`
draws one extra `draw_gate_tab` each, positioned against that leaf's own
known (placement-adjusted) gate edge, rather than editing either leaf's own
committed GDS. `bandgap_amp`'s own `in_p`/`in_n` needed the same treatment,
but that tab was added directly in `bandgap_amp/generate.py` itself (a new
cell with no prior committed geometry to disturb).

**Routing**: every inter-cell bus is Metal1, every riser is Metal2
(transitioning via `via1_tap`), so this module's own buses/risers never
cross each other regardless of height order. A separate, real hazard this
issue's own `klt extract` re-run found and fixed: each leaf cell's own
*internal* routing (unmodified, already committed before this issue) also
uses Metal2 in places (`bandgap_core`'s own `sns2`/`vref` jogs,
`bandgap_amp`'s own `tail`/`pn` jogs), and a new top-level riser can
physically merge with one of those if its column falls inside that leaf's
own internal Metal2 footprint -- `klt drc` cannot catch this class of bug
(the result is one clean merged polygon, not two shapes placed too close
together). See `bandgap_top/generate.py`'s own `_riser_up` docstring and
its `LANDING_UM` module comment for the full, itemized account of every
crossing found and how each was fixed (routing around the leaf's own busy
Y-band entirely, bridging through it on Metal1, or riding an
already-same-net Metal1 conductor past it).

**Verified with `klt extract` (device-free net extraction -- not a
reference-comparison LVS run, still out of this issue's own LVS scope)**:
after the fix above, `klt extract --deck sg13g2 bandgap_top.gds` reports
exactly 13 nets -- one per `bandgap_top`'s own six external/internal-shared
pins (`vdd`, `vss`, `fb`\|`out`, `sns1`\|`in_n`, `sns2`\|`in_p`, `vref`) plus
seven genuinely-internal-to-one-leaf nets (`cb2`, `cb3`, `d1`, `d2`, `det`,
`pn`, `tail`) -- matching the design's real topology, with no unexpected
merges. This is a connectivity sanity check, not LVS (no reference netlist
comparison is performed).

**DRC**: `klt drc --deck sg13g2` reports `status: "clean"`, 0 violations
(`layout/bandgap_top/drc_report.json`).

**LVS**: run for the same CI-evidence-format-gate reason `bandgap_amp`'s own
"LVS" section above explains -- committed as-is, not chased to `"match"`.
`layout/bandgap_top/lvs_report.json`: `status: "mismatch"`, **8 findings**
(2 `device.bulk_reconciled` warnings, 5 `device.unmatched` errors, 1
`topology` error) -- down from the 17 findings issue #169 originally
committed, after issue #171 resolved both of that report's two
composed-level-specific causes (rows 3 and 4 of the table that issue itself
recounted). Reference netlist flattened by `layout/lvs_reference.py`'s
`flatten()` (the same subckt-instantiation flattening
`sg13cmos5l-bandgap_top`'s own reference already uses), engine `klayout`.

**Cause A (issue #171) -- resistor `device_bulk` propagation, resolved.**
`layout/bandgap_top/lvs_request.json` now carries
`"reference.device_bulk": {"rppd": "VSS", "rhigh": "VSS"}`. The naive fix
issue #171 itself recorded as tried-and-failed (copying `bandgap_core`'s own
leaf-level `{"rppd": "vsubs"}` verbatim into the composed request) really
does fail exactly as documented: it clears the `rhigh` finding but not
`rppd`, and creates a new `net.merged`/`net.split` pair, because a
`device_bulk`-created net is scoped **per reconciled circuit**, and this
composed reference has exactly one (flat, no subckt boundaries) -- so a
single created `vsubs` net gets shared by *both* `rppd` instances (`X1_R1`
and `X1_R2`) at once, and the layout side has no `vsubs`-named net at all to
pair it against (confirmed by direct experiment, not just re-asserted).
**The actual fix is `"VSS"`, not `"vsubs"`, for both classes** -- verified
directly against `klt extract`'s own output for `bandgap_top.gds`
(`layout/bandgap_top/bandgap_top.lvs_reference.spice`'s device lines aside,
a raw `klt extract --deck sg13g2 bandgap_top.gds` run shows every resistor's
own third terminal already resolving to the real, existing `VSS` net --
`R$18 IN_P|SNS2 CB2 VSS ...`, not an isolated/anonymous one). This is a real
difference from each leaf's own *standalone* extraction (where `bandgap_core`
alone has no nearby substrate tap reaching an actual `VSS`-labelled pin, so
the deck synthesizes a private `vsubs` placeholder for it) -- once composed,
the whole layout's substrate is one physically-continuous node that some
*other* leaf's own tap (e.g. `bandgap_startup`'s, whose own leaf-level
request already points `rhigh` at a real `VSS`) ties to the real rail, so
`klt extract` resolves every resistor's own bulk terminal to that same real
`VSS` net at this composed level. Pointing `device_bulk` at the net the
layout side *actually* reports (rather than a name copied from a different
cell's own, differently-connected standalone extraction) is what makes this
reconciliation land without any `vsubs` collision -- both entries reconcile
against an *existing* reference net (`reference_net_created: false` in the
report's own `device.bulk_reconciled` disclosures), never a freshly-created
one, so there is nothing left to collide. All three previously-`device.
unmatched` resistors (`X1_R1`, `X1_R2`, `X3_RPU`) now pair cleanly; the two
`severity: "warning"` `device.bulk_reconciled` entries disclose that the
match rests on this caller-supplied reconciliation, per `klt lvs`'s own
convention (see `docs/cli/lvs.md` in `klayout-tools`).

**Cause B (issue #171) -- reference-flatten hierarchy-prefix net-identity
conflicts, resolved.** `layout/lvs_reference.py`'s `flatten()` now
canonicalises node names through two reconciliation passes instead of
unconditionally prefixing every child-internal net with `<instance>.`:

- A child's own purely-internal net (`bandgap_core`'s `cb2`/`cb3`,
  `bandgap_amp`'s `tail`/`d1`/`d2`/`pn`, `bandgap_startup`'s `det`) is now
  emitted **bare** -- matching `bandgap_top.gds`'s own genuinely flat
  physical net names (`CB2`, not `X1.CB2`) -- unless two or more instances'
  own internal nets actually share a raw name, in which case the original
  `<instance>.`-prefixed disambiguation still applies (a real safety margin
  this design has never needed, kept for a design that might).
- A top-level connecting net reached through **more than one distinct local
  port name** across the children that use it (`bandgap_top.spice`'s `fb`,
  reached as `bandgap_core`'s and `bandgap_startup`'s own `fb` port *and*
  `bandgap_amp`'s own `out` port) is now aliased to the sorted, comma-joined
  union of those local names -- `"FB,OUT"` -- reproducing `klt extract`'s own
  merged-pin-alias spelling for the *same* physical net (`FB|OUT` in every
  user-facing string) **from the schematic netlist alone**, no GDS/layout
  data involved. Verified against all three real merged nets this
  composition produces: `fb`/`out` -> `FB,OUT`, `sns1`/`in_n` -> `IN_N,SNS1`,
  `sns2`/`in_p` -> `IN_P,SNS2` -- each matching `klt extract`'s own
  `merged_net_labels[]` exactly.

Both reconciliations are driven entirely by `bandgap_top.spice`'s own
hierarchy (subckt port lists + the top-level connection line) -- neither
needed a GDS-derived alias map or a request-side `hints.same_nets` entry (see
below for why that hook does not actually apply here). All 8 of the original
report's `topology`/"name-identity conflict" findings (`CB2`, `CB3`, `D1`,
`D2`, `DET`, `TAIL`, `IN_N|SNS1`, `IN_P|SNS2`) are gone. **Confirmed
pdk-agnostic and shared-code-safe**: `flatten()` serves both PDK ports, and
`sg13cmos5l-bandgap_top`'s own `lvs_report.json` was re-run and re-committed
alongside this fix (see its own "LVS" section below for what changed there
and why).

**`hints.same_nets` was investigated for Cause B and does not work here --
not a design gap, a real `klt` interaction worth knowing about.** Before
settling on the reconciliation above, `request.hints.same_nets` (which
`docs/cli/lvs.md` explicitly recommends pairing with `device_bulk`, and
which a comparer log more generally can resolve *ambiguous* net pairings
through) was tried directly against the un-fixed reference for the two
merged-alias findings (`IN_N|SNS1`/`SNS1`, `IN_P|SNS2`/`SNS2`). It does not
help: `NetlistComparer` had *already* paired those two nets on its own
(structurally, despite the differing names) before the hint is even
declared, and a `hints.same_nets` pairing is only tracked as "confirmed" via
the comparer's own `match_nets`/`match_ambiguous_nets` events -- not via the
`net_mismatch` event that already-paired-but-differently-named nets go
through. The result of declaring the hint anyway was strictly *worse*: the
original `topology` finding stayed, **and** a new `hints.rejected` finding
appeared alongside it (the comparer's own record shows the pairing was never
confirmed through the hint's own tracked path, even though the pairing is,
in fact, correct). This is a real, generic `klt` interaction gap -- filed
upstream per `CLAUDE.md`'s friction protocol, no design-specific detail:
[`klayout-tools#1484`](https://github.com/2AMLogic/klayout-tools/issues/1484).

**What's left, and why it is out of scope here.** `layout/bandgap_top/
lvs_report.json` still reports `status: "mismatch"`, 8 findings -- issue
#171 was scoped to Causes A and B only, not to `bandgap_top` reaching
`"match"`:

| # | Findings | Cause | Status |
|---|---|---|---|
| 1 | 3 `device.unmatched`, class `NPN13G2` (`X1_Q1`/`X1_Q2`/`X1_Q3`) | `bandgap_core`'s permanently-declined `npn13G2` recognition gap (see "Permanent blockers" above) | already known, permanent |
| 2 | 2 `device.unmatched`, class `pfet` (`X2_MP1`/`X2_MP2`) | `bandgap_amp`'s `MP1`/`MP2` body-tie simplification (see `bandgap_amp`'s own "LVS" section above) | already known, documented |
| 3 | 1 `topology`, "device class could not be mapped to a counterpart" | The report does not name the class, so this one is **inferred, not verified**: `bandgap_core`'s own leaf report shows the identical finding alongside its `NPN13G2` gap and nothing else unmapped, so cause 1 is the most plausible attribution here too | inferred |
| -- | 2 `device.bulk_reconciled` (`severity: "warning"`, never affects `status`) | Cause A's own disclosure that the `rppd`/`rhigh` match rests on this request's `device_bulk` reconciliation (see above) | disclosure, not a defect |

Consistent with the rest of this file, none of the above is a reason to treat
the `mismatch` as benign: `bandgap_top` is **not** LVS-clean. Its remaining
`mismatch` verdict now rests entirely on the two permanently-declined,
already-documented leaf-level causes (plus one inferred instance of the
first) -- exactly what issue #169's own LVS run should have been able to say
from the start, before issue #171 corrected it.

**Determinism**: `python3 layout/bandgap_top/generate.py` re-run leaves
`git diff --stat` empty, as long as the three leaf GDS files it reads are
themselves unchanged.

**Explicitly out of scope for issue #169** (mirrors `bandgap_core`'s/
`bandgap_startup`'s own #11 -> #12/#14 sequencing): *fixing* either cell's
`mismatch` LVS verdict toward `"match"`, and post-layout PEX simulation of
the closed loop -- both left as separate follow-ups once this floorplan-level
layout lands (see tracking issue #4, item 7). Running `klt lvs` itself, once,
to produce the committed reports above was **not** optional (see "LVS"
sections above) -- only the multi-issue effort of resolving what it finds
is deferred, the same way #12's own findings took #20/#45/#149/#154/#161/#163
to work through for `bandgap_core`/`bandgap_startup`. The two causes issue
#169's own LVS run newly surfaced (the un-propagated resistor `device_bulk`
and the reference-flatten hierarchy-prefix net-identity conflicts) were
resolved by issue #171 (above); the two permanently-declined leaf-level
causes remain deferred, same as ever.

---

# SG13CMOS5L port (issues #66, #74, #76)

Everything above this line is the **SG13G2** block. This section covers the
**SG13CMOS5L** port's own layout, which shares this directory (and this
repo's evidence conventions) but almost none of its code.

All three leaf cell directories below carry the boundary-port-pad convention
issue #76 added (each cell's own `Metal1` pad per schematic port, on the
cell's own edge, returned from `generate.py`'s `build()` as a `{net:
pad_box}` map) — `sg13cmos5l-bandgap_top/` (issue #81) is the hierarchical
assembly of those three; see "Cell: `sg13cmos5l-bandgap_top`" below.

```
layout/
  common_sg13cmos5l.py             CMOS5L drawing primitives — a deliberate
                                    fork of common.py (different layer table,
                                    different net-label layer, different
                                    device set; see that module's docstring)
  sg13cmos5l-bandgap_core/         issue #66
  sg13cmos5l-bandgap_amp/          issue #74
  sg13cmos5l-bandgap_startup/      issue #74
  sg13cmos5l-bandgap_top/          issue #81 — hierarchical assembly of the
                                    three cells above, not a leaf cell of its
                                    own (its own generate.py instances the
                                    three leaves' already-committed GDS files
                                    rather than drawing devices)
```

Every leaf cell directory (and `sg13cmos5l-bandgap_top/`) carries the same
seven files:

```
  sg13cmos5l-bandgap_<cell>/
    generate.py                     draws + routes the cell
    sg13cmos5l-bandgap_<cell>.gds   committed, deterministic layout
    sg13cmos5l-bandgap_<cell>.lvs_reference.spice   generated reference netlist
    sg13cmos5l-bandgap_<cell>.extracted.spice       klt extract output
    lvs_request.json                klt lvs request
    drc_report.json                 committed klt drc report
    lvs_report.json                 committed klt lvs report
    extract_report.json             committed klt extract report (the
                                     machine-readable evidence for the
                                     deck-coverage gaps documented below)
```

**`sg13cmos5l-bandgap_top/` carries two additional files as of issue #84**
(the top-level PEX scoping choice — see "SG13CMOS5L: Post-layout parasitic
extraction" below; the three leaf cells do not carry these, since this
port's post-layout evidence is extracted once against the assembled top
cell, not per leaf):

```
    sg13cmos5l-bandgap_top.pex.spice   klt extract output (no --parasitics
                                        -- see below for why), consumed by
                                        sim/sg13cmos5l-closed-loop-startup-pex/
    pex_extract_report.json            committed klt extract --format json
                                        report for the file above
```

**Directory naming.** `layout/sg13cmos5l-<cell>/`, mirroring `sim/`'s own
per-PDK prefix convention (`sim/sg13cmos5l-core-open-loop-bias/`, …) rather
than a nested `layout/sg13cmos5l/<cell>/`. Nesting would have put the cell
one level below where `.github/scripts/check_evidence_formats.py` looks for
cells (`layout/*/` holding a `<dirname>.gds`), silently exempting every new
report from the format/freshness checks — the opposite of what committing
them is for.

## Reproducing

```bash
for cell in core amp startup; do
  uv run --with klayout python3 "layout/sg13cmos5l-bandgap_$cell/generate.py"
done
# bandgap_top (issue #81) reads the three leaf GDS files above as cell
# instances, so it must run after them, not in the same loop:
uv run --with klayout python3 layout/sg13cmos5l-bandgap_top/generate.py

python3 layout/lvs_reference.py            # regenerates every reference netlist

cd layout/sg13cmos5l-bandgap_core          # or -bandgap_amp / -bandgap_startup / -bandgap_top
klt drc --deck sg13cmos5l sg13cmos5l-bandgap_core.gds --format json > drc_report.json
klt lvs lvs_request.json --format json > lvs_report.json
klt extract --deck sg13cmos5l sg13cmos5l-bandgap_core.gds \
  -o sg13cmos5l-bandgap_core.extracted.spice --format json > extract_report.json
```

Output is byte-for-byte deterministic (`SaveLayoutOptions.gds2_write_timestamps
= False`), so re-running `generate.py` leaves `git diff` empty — verified.

`klt` versions used for the reports in this section: **`0.3.0+gc27f7eccf49c`**
and **`0.3.0+g07b1f04f29f2`** (both KLayout `0.30.11`), split by which cell's
reports they minted:

- **`0.3.0+gc27f7eccf49c`** produced `bandgap_amp`'s and `bandgap_startup`'s
  reports (issue #74) *and* `bandgap_core`'s original ones (issue #66) —
  deliberately one build for all three, so the already-committed `bandgap_core`
  reports did not have to be re-minted against a newer deck merely to add two
  neighbours.
- **`0.3.0+g07b1f04f29f2`** produced the `bandgap_core` reports committed here,
  regenerated for issue #73's Q2 rebuild (DR-0005, see "Q2: 8 parallel unit
  devices" below). That build was reinstalled from a local `klayout-tools`
  checkout for that regeneration.

The two builds carry the **same `sg13cmos5l` deck content hash**
(`sha256:9a4e18f2fd7a…`) — verified identical deck, only the surrounding `klt`
build differs — so every report below still cites one and the same deck and the
three cells' verdicts remain comparable across the build boundary. `klt`'s own
`provenance.klt_version` field records the release (`0.3.0`) rather than the
`+g…` build suffix, so the reports themselves cannot distinguish the two; the
deck `content_hash` they *do* record is the field that matters, and it matches
across all three cells.

`sg13cmos5l-bandgap_top`'s own reports (issue #81) were minted with
**`0.3.0+g3f98b441bf2f`** (KLayout `0.30.11`) — a later build still, but
carrying the identical deck `content_hash` (`sha256:9a4e18f2fd7a…`) as the
three builds above, so its verdicts remain directly comparable to the leaf
cells' own.

The `sg13cmos5l` deck did not exist in the `klt` build this host carried when
issue #66 was filed (`0.3.0+g3c14ac2f8903`, whose `decks` registry returned
only `['gf180mcu', 'sg13g2', 'sky130']`); it landed upstream in
klayout-tools#1408 and this host's `klt` was reinstalled from that source
before any report below was produced. `--deck sg13cmos5l` is the
real, working flag spelling — confirmed by running it, **not** by reading
`--help`, whose `--deck` list still names only `sky130, gf180mcu, sg13g2`
(filed upstream, see "Tooling friction filed upstream" below).

## Cell: `sg13cmos5l-bandgap_core`

One-to-one with `design/sg13cmos5l/netlist/bandgap_core.spice` (schematic
from #64): `M1`/`M2`/`M3` `sg13_hv_pmos` `w=10u l=1u`, `R2` `rppd`
`w=2u l=85.1u`, `R1` `rppd` `w=2u l=647.0u`, `Q1`/`Q3` `pnpMPA` `w=1u l=2u`,
`Q2` 8x parallel `pnpMPA` `w=1u l=2u` unit instances (issue #73, DR-0005 --
see "Q2: 8 parallel unit devices" below; **not** the single `w=8u l=2u`
device this cell originally drew, which exceeded the PCell's own `maxW`).
Top cell `sg13cmos5l_bandgap_core`, bbox `(-10.0, -3.21)`–`(830.5, 61.7)` µm
(widened from `(-8.48, -3.21)`–`(830.2, 61.7)`: three new boundary port pads
for `sns1`/`sns2`/`vref`, issue #76 -- see "Boundary ports" below; before
that, widened from `(800.2, 61.7)` for `X_M3`/`R1`/`Q3` shifting right,
150 -> 180, to make room for Q2's 8-unit row), 1188 polygons across 12
layer/datatype combinations.

**Issue #173 folded `R1`/`R2`**, and the bbox is now
`(-10.0, -3.21)`–`(220.07, 61.7)` µm: `R1`'s straight 647 µm bar used to set
this cell's 840.5 µm width on its own, exactly as `bandgap_core`'s 511 µm
bar did on the SG13G2 side. Folded, `R1` is a 38.12 x 40.055 µm block and
`R2` a 14.0 x 13.85 µm one, both placed above their own mirror leg, and this
cell's height is unchanged. Two floorplan constants moved with them and are
worth naming because neither is arbitrary: `Y_R2` dropped 45 -> 44 so the
folded block's top clears the mirror row's own NWell/ThickGateOx bottom edge
(a resistor body inside the mirror's n-well would be physically wrong), and
`Y_SNS2_PORT` rose 50 -> 57 because `sns2`'s `poly_underpass` crossing of
`vref`'s trunk used to sit in field that `R1`'s folded body now occupies —
left at 50 it would have merged into `R1`'s own conductor and shorted `sns2`
to `vref`. See `measurements/2026-09-resistor-fold/`.

### Boundary ports for `bandgap_top` assembly (issue #76)

`fb` (a tap pad left of `M1`) and `vdd` (the merged source rail along the
top) were already flush with this cell's own bounding box -- reachable from
outside the cell without crossing anything. `sns1`, `sns2` and `vref` were
not: each is a plain interior column (`sns1` at `x=0` from `Q1`'s emitter up
to `M1`'s drain; `sns2` at `x=45` from `R2`'s own pad up to `M2`'s drain;
`vref` at `x=180` from `R1`'s own pad up to `M3`'s drain), unreachable from
outside the cell's own footprint without threading a corridor the cell never
reserved -- concretely, `Q1`'s own base/collector rings close on three of
their four sides, so a straight drop through the ring from outside would
short `sns1` to `vss` rather than connect to it (exactly the "plausible but
not correct" failure issue #76's own analysis warns against).

Each of the three now gets a dedicated `common_sg13cmos5l.boundary_port()`
pad -- a `Metal1` pad flush with one edge of the cell, labelled with the net
it carries, returned (alongside `vdd`/`vss`/`fb`'s own already-flush
geometry) as a `{net: pad_box}` map from `generate.py`'s own `build()` for a
parent assembly to route against:

- **`sns1`** branches left off its own vertical trunk at `y=50` (clear of
  `Q1`'s ring, whose top is at `y=33.01`, and of `M1`'s drain pad, whose
  bottom is at `y=59.1`), straight out to the left edge.
- **`sns2`** branches right off its own trunk at `y=50`, straight across --
  **except** `vref`'s own trunk occupies the entire column `x=179.75` from
  `y=16.1` to `y=59.1` (the whole span between its own two pads), so any
  rightward path at any height in that band crosses it. Resolved with one
  `poly_underpass()` at `x=176..184.5`, the same single-metal crossing
  technique `bandgap_amp` already uses for its own `out` net.
- **`vref`** branches right off its own trunk at `y=40` (a different height
  from `sns2`'s crossing, so the two new stubs never share a row), straight
  to the right edge -- clear because neither the `vss` aisle (`x=87`, which
  only exists for `y` in `[0, 30]`) nor the Q2 emitter bus (`y=34`, which
  only spans `x=123.75..165.75`) reaches `y=40`.

**Re-verified, not just re-drawn**: `klt drc` stays `clean` (0 violations)
and `klt extract`'s device/net list is **byte-identical** to the
pre-#76 committed one (verified: the regenerated
`sg13cmos5l-bandgap_core.extracted.spice` diffs empty against the previously
committed file) -- the three new pads add reachability, not topology, since
every one of `sns1`/`sns2`/`vref`'s labels already existed inside the cell
before this issue. `klt lvs`'s finding counts are consequently unchanged
(27 findings, 25 error-severity, identical `category_counts`). The one new
thing `extract_report.json` records is a third `unmodelled_poly` entry (the
`sns2` crossing's own poly strip) -- the same already-filed
klayout-tools#1425 gap (an intentional poly underpass reads as an
unmodelled resistor body), not a new one.

### Q2: 8 parallel unit devices (issue #73, DR-0005)

The SG13CMOS5L layout phase (this section, issue #66) originally found that
the schematic's `Q2` (a single `pnpMPA` `w=8u l=2u`) could not be
PCell-generated: CMOS5L's `pnpMPA_maxW` is 2.0 µm
(`sg13cmos5l_pycell_lib/sg13cmos5l_tech.json`), so `generate.py` drew that
instance's emitter geometry by hand to match the netlist's `a`/`p` exactly
-- an honest rendering of a non-buildable device, not a real PCell
instantiation. Issue #73 / DR-0005 resolved this at the design level: `Q2`
is now `pnpMPA a={1u*2u} p={(1u+2u)*2} m=8` -- 8 parallel copies of the same
unit device `Q1`/`Q3` already use, electrically identical to the
single-wide-emitter construction it replaces (DR-0005 shows the compact
model depends only on `a`, never `p`, and SPICE's `m=` multiplier is
mathematically equivalent to an area multiplier for this model). This
layout now draws 8 real, individually-PCell-buildable `pnpMPA` unit
instances (`w=1u l=2u`, each well inside `pnpMPA_maxW`) in a row, all wired
in parallel -- see `generate.py`'s own module docstring for the exact
routing (a shared Metal1 emitter trunk plus a chained vss strap, both
direct extensions of the patterns every other device in this cell already
uses) and floorplan-shift rationale (`X_M3` 150 -> 180).

**Re-verified, not just re-drawn**: `klt drc` stays `clean` (0 violations,
same as before), and `klt lvs`'s `mismatch` finding counts are **exactly
unchanged** (27 findings, 25 error-severity, identical `category_counts`)
-- because `klt lvs`'s reference-side device count treats a `pnpMPA` call's
`m=` as a property of one logical device, not a physical expansion, and the
curated deck's `bipolars=()` gap (unchanged, see below) makes every
`pnpMPA` instance invisible to layout-side extraction regardless of how
many physical copies are drawn. `layout/lvs_reference.py`'s `pnpMPA`
conversion is updated to carry `m=` through as the reference `Q` line's
`M=` parameter (previously dropped entirely -- inconsequential while every
`m=` in this cell's netlist was `1`, newly load-bearing now that `Q2`'s is
not), so the reference netlist honestly says what the schematic built even
though the deck cannot yet compare it.

**Single-metal, planar by necessity.** The curated `sg13cmos5l` deck's
extraction stack is `metals=((8, 0),)` with `vias=()` — one routing metal, no
via — where the `sg13g2` deck declares seven metals and six vias. A `Metal2`
jumper would be invisible to `klt extract` and would split the net it
carries, so this cell is routed entirely on `Metal1` plus a `GatPoly` bar for
the gate-to-gate `fb` net, with a floorplan arranged so no two nets ever need
to cross (see `generate.py`'s own floorplan table).

**HV flavour: drawn, not modelled.** The schematic's transistors are the
thick-gate-oxide `sg13_hv_pmos`, so `draw_hv_pmos` draws the real
`ThickGateOx` (44/0) marker. The curated deck's `mos_flavours` is empty, so
it binds them to the plain `pfet` class anyway — but drawing the marker makes
`klt` say so itself rather than leaving an HV device disguised as clean LV
geometry: both `drc_report.json` (`coverage.voltage_domain_warnings`) and
`extract_report.json` (`warnings`, `voltage_domain_warnings`) carry a
`44/0` entry naming the gap.

## Cell: `sg13cmos5l-bandgap_amp` (issue #74)

One-to-one with `design/sg13cmos5l/netlist/bandgap_amp.spice` (schematic from
#70): `MTAIL`/`MP3`/`MP4` `sg13_hv_pmos` `w=10u l=1u`, `MP1`/`MP2`
`sg13_hv_pmos` `w=20u l=1u`, `MN1`–`MN4` `sg13_hv_nmos` `w=10u l=1u`. Top
cell `sg13cmos5l_bandgap_amp`, bbox `(-7.0, -1.24)`–`(77.0, 41.7)` µm
(widened from `(-5.27, -1.24)`–`(75.62, 41.7)`: two new boundary port pads
for `in_p`/`in_n`, issue #76 -- see "Boundary ports" below), 759 polygons
across 9 layer/datatype combinations. **The first CMOS5L cell in this repo
whose bounding box is set by its own devices** rather than by a straight,
unfolded resistor bar — it has no resistor.

**The NMOS primitive landed here.** `bandgap_core` is all-PMOS, so
`common_sg13cmos5l.py` had no NMOS footprint before this issue.
`draw_hv_nmos` is transcribed from CMOS5L's own `nmosHV_code.py`, which
declares only `Activ`/`GatPoly`/`Cont`/`Metal1`/`ThickGateOx` — **no implant
marker and no well**. That is not an omission in the transcription: in SG13's
layer scheme `pSD` (14/0) is the only drawn implant mask and n+ is its
complement, and the curated deck models exactly that split ("NMOS = active
outside nwell, PMOS = active inside nwell"). Source and drain are mirrored
relative to `draw_hv_pmos` (source at the bottom), so a shared `vss` rail sits
directly under the NMOS row.

**Not planar — one poly underpass, deliberately.** Unlike `bandgap_core`,
this circuit has *no* planar single-metal solution, and the obstruction is
structural rather than a placement accident: `out` has members in all three
device rows, `MTAIL`'s drain must cross the same band between the top PMOS row
and the input pair, and `out`'s bottom member sits outside the span
`MTAIL`'s drop has to land in. Swapping columns moves the crossing; it does
not remove it. So `out`'s lane dips onto `GatPoly` for 8 µm (x=16..24 at
y=36) and passes *under* `MTAIL`'s Metal1 drop — a real crossing, since
`GatPoly` and `Metal1` are separate conductors in the deck's connectivity
graph, joined only through `Cont` (6/0). Verified rather than asserted:
`extract_report.json` reports `out` and `tail` as two distinct whole nets and
`merged_net_labels` is empty. The underpass crosses field only (a poly strip
over `Activ` would be a parasitic transistor, not a wire).

**Column order is the circuit's own net-adjacency order.** `MN3 -d1- MN1` and
`MN2 -d2- MN4` each become one continuous `GatPoly` gate bar over field, with
the input pair sitting directly above its own diode-connected load so
`d1`/`d2` are straight vertical drops; the top row follows the circuit's path
`MP3 -pn- MP4 -out- MTAIL`, which puts the mirror pair adjacent (one shared
gate bar again). See `generate.py`'s own floorplan sketch.

### Boundary ports for `bandgap_top` assembly (issue #76)

`vdd` (top rail), `vss` (bottom rail) and `out` (`MN3`'s own drain pad,
whose device width happens to reach the cell's left edge) were already
flush with this cell's own bounding box. `in_p`/`in_n` were not — each is a
poly gate tap in the interior (`X_IN_P_TAB=7`, `X_IN_N_TAB=58`), the same
gap issue #76 found in `bandgap_core`. Both now get a dedicated
`boundary_port()`, reached by extending each tap's own gate-link sideways:

- **`in_p`** escapes left at the input pair's own row (`y=20`) — crossing
  `out`'s own vertical stub at `x=0` (which spans the entire `y=0.64..36`
  band between `MN3`'s drain and the underpass lane) on a second
  `poly_underpass()`, distinct from the one this cell already uses for
  `out` itself.
- **`in_n`** escapes right at the same `y=20` — crossing `pn`'s own
  vertical stub at `x=65` (`MN4`'s drain up to the `Y_OUT_LANE` turn) on a
  third poly underpass.

**Re-verified, not just re-drawn**: `klt drc` stays `clean` and
`klt extract`'s device/net list is byte-identical to the pre-#76 committed
one, so `klt lvs`'s finding counts are unchanged (25 findings, 23
error-severity). Two new `unmodelled_poly` entries appear in
`extract_report.json` (the two new underpasses' own poly strips) — the same
already-filed klayout-tools#1425 gap this cell's own pre-existing underpass
already triggers, not a new one.

## Cell: `sg13cmos5l-bandgap_startup` (issue #74)

One-to-one with `design/sg13cmos5l/netlist/bandgap_startup.spice` (schematic
from #70): `RPU` `rhigh` `w=1u l=1411.3u`, `MSENSE` `sg13_hv_nmos`
`w=10u l=0.5u`, `MKFB` `sg13_hv_nmos` `w=2u l=0.5u`. Top cell
`sg13cmos5l_bandgap_startup`, bbox `(-0.2, -1.2)`–`(84.4, 52.304)` µm as of
issue #173's fold.

This cell was the repo's most extreme rectangle: `RPU`'s straight 1411 µm
bar set its `(-0.5, -1.2)`–`(1424.4, 8.6)` bbox single-handedly — a
**145.4:1** aspect ratio, and the specific cell
`measurements/2026-09-layout-area/` named as the direct cause of the
assembled top's 77.5% whitespace. Folded into 32 serpentine legs, `RPU` is a
44.772 x 43.704 µm block and the cell is 1.6:1. The `MSENSE`/`MKFB` cluster
moved 1340 µm left with it, keeping every one of its own internal clearances
unchanged (it used to sit under the bar's far end; it now sits just past the
folded block's right edge, the same relative topology). See
`measurements/2026-09-resistor-fold/`.

**The `rhigh` flavour landed here.** `draw_rhigh` shares its construction with
`draw_rppd` (CMOS5L's two poly resistors share one PCell base class,
`res_base_code.ResistorBase`) and differs by exactly one layer, read from
`rhigh_code.py`'s own layer block: `nSD` (7/0) over the marked body, which
`rppd_code.py` does not declare at all. `layout/lvs_reference.py` gained the
matching `rhigh` value formula from that PDK's own `rhigh.sym` — note it is
*not* the `rppd` formula with different constants: the width correction is
negative (`rhigh_lwd = -0.04u` against `rppd`'s `+6 nm`), and the sheet value
the symbol uses is `rhighG2_rspec` (1360.0), not the bare `rhigh_rspec`
(1300.0).

**Planar, single-metal, no underpass needed.** This cell's net graph is a
path, so it fits the one-metal/no-via stack directly. Both transistors sit at
the far right end under `RPU`'s `det` head, so `det` — the only net here with
more than two members — never travels the bar's length; `MSENSE`'s gate
escapes left and `MKFB`'s escapes right, so the two gate nets never share a
poly corridor. `vdd`, `sns1` and `fb` are ports whose only in-cell member is
the terminal they name.

### Boundary ports for `bandgap_top` assembly (issue #76)

`vdd` (`RPU`'s own left head) already sits flush against this cell's own
left+top edges; `vss` (the merged NMOS source rail) already sits flush
against the bottom edge. `sns1`/`fb` did not — each is an interior gate tab
(`X_SNS1_TAB=1388`, `MKFB`'s own drain pad at `x=1419..1421`). Both now get
a dedicated `boundary_port()`:

- **`sns1`** drops straight down from its own tap to the bottom edge — the
  tap sits 2 µm clear of the `vss` rail's own left edge (`x=1390`), so no
  crossing is needed.
- **`fb`** — `MKFB`'s own drain pad sits directly above the `vss` rail
  (whose x-span, `1390..1421`, includes the pad's own x-position) *and*
  `det`'s own horizontal lane at `y=3` spans the entire `x=1395..1423.5`
  run (crossing `fb`'s own column at `x=1420` too), so a straight escape in
  any direction hits one net or the other. Resolved with a **vertical**
  poly underpass across `det`'s lane (`y=2.0..4.0`, built from the same
  `poly_tab()`/`route_v(L_GATPOLY, ...)` primitives `poly_underpass()`
  itself composes, oriented across a horizontal metal lane instead of a
  vertical one), then a jog up and right to the cell's own right edge.
  **One iteration needed fixing**: the underpass's first landing pads (at
  `y=2.5`/`3.5`, only 0.10 µm from `det`'s own Metal1 lane) DRC-failed
  `metal1.space.1` three times; widening to `y=2.0`/`4.0` (2.0 µm clearance)
  cleared all three.

**Re-verified, not just re-drawn**: `klt drc` stays `clean` and
`klt extract`'s device/net list is byte-identical to the pre-#76 committed
one (`fb` and `det|vdd` remain two separate nets — the first attempt's `fb`
route crossed `det`'s own lane on plain Metal1 and merged the two, caught by
re-running `klt extract` and comparing net counts before committing
anything). `klt lvs`'s finding counts are unchanged (16 findings, 14
error-severity). One new `unmodelled_poly` entry appears in
`extract_report.json` (the vertical underpass's own poly strip) — the same
already-filed klayout-tools#1425 gap, not a new one.

## Cell: `sg13cmos5l-bandgap_top` (issue #81)

The hierarchical assembly of the three leaf cells above, one-to-one against
`design/sg13cmos5l/netlist/bandgap_top.spice`'s own `.subckt bandgap_top vdd
vss vref` line (`Xx1 vdd vss fb sns1 sns2 vref bandgap_core`, `Xx2 sns2 sns1
vss fb vdd bandgap_amp`, `Xx3 vdd vss sns1 fb bandgap_startup`). Unlike every
other `generate.py` in this repo, this one does **not** draw device geometry:
`layout/sg13cmos5l-bandgap_top/generate.py` reads the three already-committed
leaf GDS files as `klayout.db` cell instances (`kdb.CellInstArray`) into one
new layout, then draws only the inter-cell routing between each leaf's own
`boundary_port()` pad (issue #76) — no leaf cell's own internal geometry is
touched. Top cell `sg13cmos5l_bandgap_top`, bbox `(-50.25, -10.25)`–`(2405.5,
120.5)` µm, assembled from `sg13cmos5l-bandgap_core.gds` (~840 µm),
`sg13cmos5l-bandgap_amp.gds` (~84 µm) and `sg13cmos5l-bandgap_startup.gds`
(~1425 µm).

**Floorplan.** The three cells sit side by side, left to right (core, amp,
startup), separated by 30 µm gaps that are empty at *every* height — no
cell's own bounding box reaches into a neighbour's gap at any `y`, since the
three occupy disjoint x-ranges (`core (-10, -3.21)-(830.5, 61.7)`, `amp
(860.5, -1.24)-(944.5, 41.7)`, `startup (974.5, -1.2)-(2399.4, 8.6)`). No
mirroring: every inter-cell connection is routed via a dedicated bus/column
rather than relying on adjacent edges lining up.

**Routing: buses + poly risers.** `vdd`, `vss`, `fb` and `sns1` each need all
three cells — a four-nets-deep channel-routing problem at this assembly's own
single modelled metal (`metals=((8, 0),)`, `vias=()`, klayout-tools#1417,
the same constraint every leaf cell's own floorplan already works within).
Four full-span nets cannot all avoid crossing each other purely by placement
(a bus reaching three widely-separated cells necessarily spans the x-range
any *other* bus's riser must cross to reach a taller one), so this follows
the same answer the leaf cells already established for their own internal
crossings: cross on `GatPoly` instead. Each net gets one straight horizontal
`Metal1` bus (`vdd`@75 µm, `vss`@90 µm, `fb`@105 µm, `sns1`@120 µm — all
comfortably above every leaf cell's own bounding-box top, `core`'s 61.7 µm
being the tallest) plus one `GatPoly` riser per contributing cell, each at
its own dedicated column, transitioning `Metal1`↔`GatPoly` via `poly_tab()`
at both ends — the same primitive every leaf cell's own `poly_underpass()`
already uses. `sns2` (core+amp only) and `vref` (core + this assembly's own
external port) are routed directly, entirely on `Metal1`, through a column
chosen to clear every other net's own path.

**One real short found and fixed, not glossed over.** `bandgap_startup`'s own
`RPU` (a deck-unrecognised `rhigh` resistor) draws its conductor body as one
unbroken `GatPoly` bar spanning almost that cell's entire width (local
`x=0..1411.3`, `y=7.5..8.5`) — both `sns1`'s and `vss`'s own natural riser
columns (chosen to reuse each cell's own existing tap/pad locations) fall
within that span. The first attempt routed straight through on `GatPoly`,
which physically merged `sns1` and `vss` into `RPU`'s own already-documented
`vdd|det` short (caught immediately by `klt extract`: `s`/`d` of `bandgap_top`'s
own M1 both read `det|in_n|sns1|vdd|vss` — a five-way merge, not the intended
`in_n|sns1` pair). Fixed by bridging *over* the resistor body on `Metal1`
instead (the reverse of the usual crossing: `GatPoly` below and above the
body, `Metal1` across it) — but the first bridge attempt (0.2 µm clearance
past the body's own `7.5..8.5`) *still* merged, because `poly_tab()`'s own
`GatPoly` landing pad is itself 0.70 µm tall (0.35 µm each side of the
transition point) and so its own pad overlapped the body even though the
riser's long run did not. Widening the bridge to `(6.8, 9.2)` (clearing the
pad's own half-height plus margin) resolved it — re-verified via `klt
extract` at each step, isolating `_route_sns1`/`_route_vss` alone before
re-testing the full assembly, not merely re-run once and assumed fixed.

**Re-verified, not just laid out**: `klt extract`'s own net list confirms
each of the six shared nets merges into exactly one physically-connected net
across all of its contributing cells (`vdd`→`det|vdd` — see below, `vss`
alone, `fb|out`, `in_n|sns1`, `e2|in_p|sns2`, `e3|vref`), with no other
accidental short. `device_counts`: `{"nfet": 6, "pfet": 8}` — the sum of each
leaf's own MOS devices (core 3 pfet; amp 5 pfet + 4 nfet; startup 2 nfet),
confirming no device was dropped or duplicated by the assembly.

### DRC — clean

| Cell | Report | Status | Deck (content hash) |
| --- | --- | --- | --- |
| `sg13cmos5l-bandgap_top` | `layout/sg13cmos5l-bandgap_top/drc_report.json` | `clean`, 0 violations | `sg13cmos5l`, `sha256:9a4e18f2fd7a…` (same content hash as the three leaf cells) |

Reproduce: `klt drc --check layout/sg13cmos5l-bandgap_top/drc_report.json`
(or `--rerun` for a full re-check).

### LVS — `mismatch`, same four causes, re-verified for this cell

| Report | Status | Engine | nets | devices | pins |
| --- | --- | --- | --- | --- | --- |
| `layout/sg13cmos5l-bandgap_top/lvs_report.json` | `mismatch` (22 findings, all error-severity) | `klayout` | layout=15, reference=13, matched=2 | layout=17, reference=20, matched=8 | layout=13, reference=0, matched=13 |

Reproduce: `klt lvs lvs_request.json` from `layout/sg13cmos5l-bandgap_top/`
(run against `lvs_reference.flatten()`'s own output — `python3
layout/lvs_reference.py` regenerates
`sg13cmos5l-bandgap_top.lvs_reference.spice` from
`design/sg13cmos5l/netlist/bandgap_top.spice` directly, without needing an
assembled GDS); `klt lvs --check lvs_report.json` verifies the committed
report against the current inputs without re-running the compare.

**Re-run and re-committed by issue #171, numbers changed for two separate
reasons -- neither is a regression, but the itemised four-cause list right
below this paragraph is now stale and due for its own re-audit.** Issue
#171 fixed `layout/lvs_reference.py`'s `flatten()` (shared by this cell and
the SG13G2 `bandgap_top` above -- see that cell's own "LVS" section for the
fix itself), which regenerated this cell's `.lvs_reference.spice` too and,
per this repo's own evidence-freshness gate, requires this report to be
re-run and re-committed alongside it (`environment.reference_sha256` must
match the file that now exists). Comparing the *old* reference file's own
`.spice` text against the version of `klt`/the `sg13cmos5l` deck installed
while fixing #171 (before applying any of that issue's own code changes)
already shows drift from what is committed above (`51` findings recorded ->
`52` findings reproduced, with `device.body_unverified` no longer appearing
at all) -- i.e. **some** of the count/category change between the numbers
above and what is itemised below traces to an upstream `klayout-tools`
deck/engine version bump (`provenance.deck.content_hash` and
`klayout_version` both differ from what the previously-committed report
recorded), entirely independent of issue #171's own `flatten()` fix, and the
rest traces to that fix itself (the same net-naming reconciliation that
removed the SG13G2 `bandgap_top`'s own 8 `topology` name-conflict findings
lets more of this cell's own nets and devices pair too). Disentangling
which finding below comes from which of those two causes -- and refreshing
the itemised list to match -- needs its own dedicated pass; issue #171's own
scope was the SG13G2 `bandgap_top` causes, and it is not stretched here to
also re-audit this cell's four-cause narrative. Filed as **issue #174**
(see that issue for the fresher itemisation) rather than silently
left stale or expanded into out-of-scope work in the same PR.

The same four causes each leaf cell already hits, as re-verified against
this assembly's own report **before** issue #171 (numbers below predate
both the `flatten()` fix and the upstream deck/engine bump described above
-- see the paragraph immediately above for why they no longer match the
freshly-committed report's own top-line numbers):

1. **No bipolar device class** (`klayout-tools#1242`, permanently declined) —
   all 10 `pnpMPA` instances inside `bandgap_core` (`Q1`, 8×`Q2` unit, `Q3`)
   are reference-only `device.unmatched`, class `PNPMPA`.
2. **No resistor recognition, and the unmodelled body shorts its own
   terminals** (`klayout-tools#1415`) — `R1`/`R2` (`bandgap_core`) and `RPU`
   (`bandgap_startup`) are reference-only `device.unmatched`, class
   `RPPD`/`RHIGH`; their own unmodelled `GatPoly` bodies short `sns2`↔`e2`
   and `vref`↔`e3` (`bandgap_core`) and `vdd`↔`det` (`bandgap_startup`) —
   confirmed in `extract_report.json`'s own `merged_net_labels`
   (`det|vdd`, `e2|in_p|sns2`, `e3|vref`), the *same* three merges each leaf
   cell's own report already recorded, now additionally carrying the
   assembly's own intentional cross-cell merges (`in_p`/`in_n` are amp's own
   names for `sns2`/`sns1`, `out` is amp's own name for `fb`).
3. **No HV MOS flavour** (`mos_flavours=()`) — every `sg13_hv_pmos`/
   `sg13_hv_nmos` instance across all three leaf cells binds to the plain
   `pfet`/`nfet` class regardless; `extract_report.json`'s own
   `voltage_domain_warnings` names the gap against the `44/0` `ThickGateOx`
   marker every device still carries.
4. **No well/substrate tap** (`tap`/`tap_nplus`/`tap_pplus` all `None`) —
   `device.body_unverified` (2 warning-severity findings: one covering all 6
   `nfet` bodies against the deck-synthesized `vsubs` global, one covering
   all 8 `pfet` bodies against an anonymous well net) and
   `unbiased_pmos_body_nets` (8 entries) both confirm no drawn tap geometry
   resolves any MOS body terminal to a real schematic net — the same gap
   each leaf cell's own report already carries, unchanged by the assembly.

With every device's net-graph correspondence broken by causes 3–4 above
(`counts.nets.matched: 0` for all 13 nets), no MOS device pairing can reach
`device.matched` either — the same "net topology break blocks every
downstream device match" mechanism already documented for each leaf cell,
not a new finding at the assembly level. `status: "mismatch"` is reported
honestly, per `CLAUDE.md`'s "Verification is the product" — no reference
device was dropped and no net was renamed to manufacture a `match`.

**New `unmodelled_poly` entries, same already-filed gap.** This assembly's
own poly risers (21 `unmodelled_poly` entries in `extract_report.json`) read
exactly like every leaf cell's own `poly_underpass()`/gate-tap poly already
does — an intentional poly wire with no resistor-marker geometry reads as an
unmodelled resistor body to this deck. Same already-filed
[klayout-tools#1425](https://github.com/2AMLogic/klayout-tools/issues/1425),
not a new gap.

## SG13CMOS5L layer numbers

Read directly from `ihp-sg13cmos5l/libs.tech/klayout/tech/sg13cmos5l.lyp`'s
own `<name>`/`<source>` entries (IHP release v0.2.0, the install
`klt pdk list` resolves at `~/share/pdk/ihp-sg13cmos5l`) — **not** copied
from the SG13G2 table above and not assumed identical to it:

| Layer | GDS (layer/datatype) | Used for |
|---|---|---|
| `Activ.drawing` | 1/0 | MOS diffusion, PNP emitter/base/collector |
| `GatPoly.drawing` | 5/0 | MOS gate, `fb` routing bar, `rppd` conductor |
| `Cont.drawing` | 6/0 | every contact |
| `nSD.drawing` | 7/0 | (declared, unused by this cell) |
| `Metal1.drawing` | 8/0 | all routing |
| `Metal1.pin` | 8/2 | **net names** (`EXTRACTION_DECK.metal_labels`) |
| `pSD.drawing` | 14/0 | p+ implant (PMOS S/D, PNP emitter + collector ring, `rppd` body) |
| `SalBlock.drawing` | 28/0 | `rppd` silicide block |
| `NWell.drawing` | 31/0 | PMOS well, PNP base |
| `NWell.pin` | 31/2 | well names (`EXTRACTION_DECK.well_label`) |
| `ThickGateOx.drawing` | 44/0 | HV (thick-oxide) marker |
| `TEXT.drawing` | 63/0 | human-readable annotation only |
| `EXTBlock.drawing` | 111/0 | `rppd` extraction marker |
| `PolyRes.drawing` | 128/0 | `rppd` body marker |

The **net-label layer is the one difference most likely to bite a future
port**: this deck reads net names from `Metal1.pin` (8/2) and well names from
`NWell.pin` (31/2), where the `sg13g2` deck reads `Metal1.text`/`Metal2.text`
(8/25, 10/25) and declares no well label at all. Labelling the SG13G2 layers
here would leave every net anonymous — the same class of mistake issue #20
already made once in the other direction.

Device geometry is likewise read from CMOS5L's **own** PyCell sources
(`libs.tech/klayout/python/sg13cmos5l_pycell_lib/ihp/{pmosHV,nmosHV,pnpMPA,rppd,rhigh}_code.py`)
and its own `sg13cmos5l_tech.json` `techParams` table, cited per constant in
`layout/common_sg13cmos5l.py`.

## SG13CMOS5L: DRC — clean

| Cell | Report | Status | Deck (content hash) |
| --- | --- | --- | --- |
| `sg13cmos5l-bandgap_core` | `layout/sg13cmos5l-bandgap_core/drc_report.json` | `clean`, 0 violations | `sg13cmos5l`, `sha256:9a4e18f2fd7a…` |
| `sg13cmos5l-bandgap_amp` | `layout/sg13cmos5l-bandgap_amp/drc_report.json` | `clean`, 0 violations | `sg13cmos5l`, `sha256:9a4e18f2fd7a…` |
| `sg13cmos5l-bandgap_startup` | `layout/sg13cmos5l-bandgap_startup/drc_report.json` | `clean`, 0 violations | `sg13cmos5l`, `sha256:9a4e18f2fd7a…` |

Reproduce: `klt drc --check layout/sg13cmos5l-bandgap_<cell>/drc_report.json`
(or `--rerun` for a full re-check). All three cells were checked against the
same deck content hash, so the three verdicts are directly comparable.

The deck is a six-rule MOS-only starter (`activ.width.1`/`activ.space.1`,
`gatpoly.width.1`/`gatpoly.space.1`, `metal1.width.1`/`metal1.space.1`) —
`coverage.layers_in_stream_without_rules` lists the drawn layers it has no
rule for at all (nine for `bandgap_core` and `bandgap_startup`: `Cont`,
`Metal1.pin`, `nSD`, `pSD`, `SalBlock`, `ThickGateOx`, `TEXT`, `EXTBlock`,
`PolyRes`; six for `bandgap_amp`, which draws no resistor markers but does
draw `NWell`). **A clean verdict here is a much weaker statement than a clean
SG13G2 run**, and this section is where that qualification travels with it —
in particular, nothing in this deck checks the two things #74's cells added
(a contact's enclosure by the poly it lands on, and any implant rule at all).

Two real defects were found and fixed by `bandgap_core`'s first two DRC runs,
not waved through:

1. **`metal1.space.1` × 4** — each PNP's ring straps stopped at the `Activ`
   ring outline instead of the `Metal1` ring drawn 0.02 µm inside it (the
   PCell's own inset), leaving a 0.02 µm gap the deck correctly read as a
   notch rather than a connection. `draw_pnpmpa` now returns
   `base_ring_m1`/`collector_ring_m1` and the routing straps against those.
2. **`metal1.width.1` × 2** — the `sns2`/`vref` drops landed on their
   resistor end-pads *off-centre*, so the drop overhung the pad edge and the
   join was a step rather than a T. Landing a 0.30 µm stem wholly inside the
   0.50 µm pad measures 0.212 µm across the T's own diagonal, clear of the
   0.16 µm floor.

Both of `bandgap_amp` and `bandgap_startup` came back `clean` on their **first**
DRC run — because finding 2 above was generalised into the primitives rather
than fixed in place. Every Metal1 trunk that lands on a poly tap lands on a
0.50 µm square `TAB_PAD_UM` pad (wider than the 0.30 µm trunk in *both* axes,
so the join is always a T and never a step), and `_gate_link` draws a
gate-to-gate poly bar at the devices' own channel length so the link and the
two gate rectangles merge into one plain rectangle with no junction at all.

## SG13CMOS5L: LVS — `mismatch`, fully attributed

| Cell | Report | Status | Engine |
| --- | --- | --- | --- |
| `sg13cmos5l-bandgap_core` | `layout/sg13cmos5l-bandgap_core/lvs_report.json` | `mismatch` (27 findings, 25 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |
| `sg13cmos5l-bandgap_amp` | `layout/sg13cmos5l-bandgap_amp/lvs_report.json` | `mismatch` (25 findings, 23 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |
| `sg13cmos5l-bandgap_startup` | `layout/sg13cmos5l-bandgap_startup/lvs_report.json` | `mismatch` (16 findings, 14 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |

```
bandgap_core     nets: layout=7   reference=8  matched=0
                 devices: layout=3   reference=8  matched=0
                 device.body_unverified 1, device.unmatched 8,
                 net.unmatched 15, topology 3

bandgap_amp      nets: layout=11  reference=9  matched=2
                 devices: layout=9   reference=9  matched=0
                 device.body_unverified 2, device.unmatched 9,
                 net.merged 6, net.split 8

bandgap_startup  nets: layout=5   reference=5  matched=0
                 devices: layout=2   reference=3  matched=0
                 device.body_unverified 1, device.unmatched 3,
                 net.unmatched 10, topology 2
```

Reproduce: `klt lvs lvs_request.json` from
`layout/sg13cmos5l-bandgap_<cell>/` (the request's relative paths resolve
against its own directory), or `klt lvs --check lvs_report.json` to verify
the committed report against the current inputs without re-running.

**This is reported as `mismatch` deliberately.** Four independent causes are
each attributed below, every one of them a property of the curated deck's
present coverage rather than of these layouts, and every one filed upstream.
No reference netlist was trimmed, no net was renamed and no device was
dropped to manufacture a `match` — the same honest-reporting posture #20 and
#4 (item 4) established for the SG13G2 side, and the same one the CI checker
enforces (it asserts a `match` has zero mismatches; it deliberately does not
demand a verdict).

**Which cause bites which cell** (#74 re-derived this per cell rather than
inheriting #66's list — the causes are the same four, but they do not all
apply everywhere, and cause 4 turns out to be far more damaging than
`bandgap_core` alone showed):

| Cause | `bandgap_core` | `bandgap_amp` | `bandgap_startup` |
| --- | --- | --- | --- |
| 1. no bipolar class | yes (`Q1`–`Q3`) | n/a — no bipolar | n/a — no bipolar |
| 2. no resistor class, body shorts its terminals | yes (`R1`/`R2`) | n/a — no resistor | yes (`RPU`; `vdd` merges into `det`) |
| 3. no HV MOS flavour | yes | yes | yes |
| 4. no well/substrate tap | yes | yes — **and it alone accounts for the whole verdict** | yes |

1. **No bipolar device class** — `EXTRACTION_DECK.bipolars == ()`, so `Q1`,
   `Q2` and `Q3` have no layout counterpart (3 × `device.unmatched`). This
   one is **not** expected to close: `ihp-sg13cmos5l`'s own
   `lvs/rule_decks/bjt_extraction.lvs` and `custom_bjt_extractor.lvs` are
   relative symlinks into the sibling `ihp-sg13g2` checkout its
   `.github/ihp-sg13g2.ref` pins (both resolve on this host, which *does*
   carry that sibling at `~/share/pdk/ihp-sg13g2`), and extract `pnpMPA`
   through the very `CustomBJTExtractor` klayout-tools#1232/#1242 already
   investigated and declined for SG13G2 — including the specific finding that
   `pnpMPA`'s base/collector terminals are restricted per-instance to the
   region interacting with its own computed emitter extents, which
   `BipolarDevice`'s static `requires`/`excludes` model cannot express. The
   CMOS5L bipolar gap is the same permanent blocker as the SG13G2 one, on
   literally the same source file. Nothing in a future layout pass will move
   it.
2. **No resistor recognition, and the unmodelled body *shorts* its own
   terminals** — `EXTRACTION_DECK.resistors == ()`, so `R1`/`R2` are
   unmatched (2 × `device.unmatched`); worse, their `GatPoly` bodies are
   contacted at both ends, so `klt extract` absorbs them into ordinary
   interconnect and merges `sns2` with `e2` and `vref` with `e3`
   (`extract_report.json`'s `unmodelled_poly` and `merged_net_labels`
   sections record both, in `klt`'s own words). That collapse is why *zero*
   devices match rather than three: with two nets merged and five of eight
   devices invisible, the surviving three PFETs are a perfectly symmetric
   sub-graph with no distinguishing structure left — the same automorphism
   trap the SG13G2 cell hit, arrived at by a different route. Filed as
   klayout-tools#1415.

   `bandgap_startup` reproduces this exactly, on a different device flavour:
   `RPU` is unmatched and its `GatPoly` body shorts its own two terminals, so
   the extracted netlist's supply pin reads `det|vdd` — `klt extract`'s own
   `merged_net_labels` names both. Re-verified rather than restated: see the
   two-step isolation below.
3. **No HV MOS flavour** — `mos_flavours == ()`, so `M1`/`M2`/`M3` bind to
   the LV `pfet` class regardless of the drawn `ThickGateOx`; the reference
   netlist maps `sg13_hv_pmos` to `pfet` to match, and the drawn marker makes
   the substitution visible in both reports rather than silent. Filed as
   klayout-tools#1416. Both #74 cells hit the same substitution on the NMOS
   side too (`sg13_hv_nmos` -> `nfet`), and both `extract_report.json`s carry
   the `44/0` `voltage_domain_warnings` entry naming it.
4. **No well/substrate tap** — `tap`/`tap_nplus`/`tap_pplus` are all `None`
   (the only curated deck for which that is true), so no drawn geometry can
   join a well net to a supply rail and all three PMOS bodies compare against
   an anonymous well net (`device.body_unverified`). Filed as
   klayout-tools#1414. **Tried and rejected**: labelling the shared n-well
   `vdd` on `NWell.pin`. It names the isolated net but cannot connect it —
   the netlist simply grows a second, disjoint `vdd$1` net, `klt lvs`'s
   finding count is unchanged at 27, and the only real effect is to suppress
   `klt extract`'s own "PMOS devices tie their body to an anonymous net with
   no DC bias path" warning. Suppressing the most direct evidence of the gap
   to gain a misleading net name is the wrong trade; the wells are left
   unlabelled and the warning stands in `extract_report.json`.

   **#74 found this cause is much worse than `bandgap_core` alone showed.**
   The CMOS5L cells with NMOS hit it from the substrate side as well — the
   NMOS body terminal falls back to the deck's synthesized `vsubs` global,
   which no drawn substrate tie can resolve to `vss` — and on a cell where
   *every* body ties to a rail, that stops the **rails themselves** from
   corresponding: the reference's `vdd` carries three source terminals plus
   five bodies, while the layout's `vdd` carries only the sources. Losing
   both supply nets costs `NetlistComparer` its usual traversal anchors, and
   every other finding in the report becomes an artifact of that.

### Isolating cause 4: the `bandgap_amp` layout is topologically correct

`bandgap_amp` reads `mismatch` with 0/9 devices matched, which looks like a
routing bug. It is not. Re-run the identical, committed GDS against a
reference netlist whose **only** edit is detaching the body terminals — each
MOS's 4th node changed from the rail it belongs on to a dangling node; no
device removed, no other net renamed, no parameter touched:

```bash
cd layout/sg13cmos5l-bandgap_amp
sed -e 's/ vdd pfet / wellnet pfet /' -e 's/ vss nfet / vsubs nfet /' \
  sg13cmos5l-bandgap_amp.lvs_reference.spice > /tmp/amp-bodies-detached.spice
# ...then point a copy of lvs_request.json at that file and re-run `klt lvs`.
```

```
status: match          mismatches: 2   errors: 0
nets:    layout=11  reference=11  matched=11
devices: layout=9   reference=9   matched=9
category_counts: device.body_unverified 2
```

0/9 -> **9/9 devices** and 2/11 -> **11/11 nets**, with the tap gap as the
sole independent variable. Every net in `bandgap_amp` — including `out`,
which is the one that crosses on a poly underpass — is topologically
identical to the schematic.

The same two-step isolation on `bandgap_startup` separates its two causes
cleanly: detaching bodies alone takes it to 2/2 transistors and 4/6 nets
matched (the residue being `RPU` and the shorted `vdd`/`det` pair);
additionally collapsing `RPU` into a `vdd`–`det` short — i.e. modelling what
cause 2 does to the layout — takes it to a full `match`, 5/5 nets and 2/2
devices.

**This diagnostic is deliberately not committed as evidence.** The reference
netlists under `layout/` are generated from the schematics and tie every body
to the rail the schematic ties it to, because that is what the circuit is.
The detached-body netlist is a *probe* for attributing a known deck gap, not
an alternative truth — committing it would be exactly the "trim the reference
until it matches" move this section's opening paragraph rules out. The
command above is short enough to re-run.

This finding is recorded upstream on klayout-tools#1414, since it materially
changes that gap's impact statement.

### `bandgap_amp`'s poly underpass reads as an unmodelled resistor body

One further finding from #74, benign but worth recording so a future reader
does not chase it: `bandgap_amp`'s `extract_report.json` carries an
`unmodelled_poly` entry (`bbox_um` 15.65–24.35 × 35.65–36.35, `reason:
"unmarked"`) and the matching "...absorbed into ordinary interconnect as an
unintended short" warning. That is the deliberate poly underpass, and the
absorption is precisely what it is for.

`klt extract`'s heuristic fires on any poly shape that is not a recognised
gate, touches `contact` at two or more points, and carries no resistor
marker — which a poly underpass matches exactly — and there is no CLI flag,
deck field or marker convention to say "this strip is intentional
interconnect". Filed generically as
[klayout-tools#1425](https://github.com/2AMLogic/klayout-tools/issues/1425).
Until it closes, a non-empty `unmodelled_poly[]` on this cell is expected;
the check that it is *only* the underpass is that `merged_net_labels` is
empty and `klt lvs` finds no `net.merged` between two schematic nets.

## SG13CMOS5L: Post-layout parasitic extraction (issue #84)

Per issue #84's own dependency text, LVS's `mismatch` status above (fully
attributed to the same four causes every leaf cell already carries) is the
allowed extraction input, same convention issue #14 established for the
SG13G2 side. **Device-level extraction succeeded, cleanly, against the
assembled top cell**:

```bash
cd layout/sg13cmos5l-bandgap_top
klt extract --deck sg13cmos5l sg13cmos5l-bandgap_top.gds \
  -o sg13cmos5l-bandgap_top.pex.spice --format json > pex_extract_report.json
```

`status: "extracted"`, no errors, `device_count: 14` (`device_counts:
{"nfet": 6, "pfet": 8}`, matching "Cell: `sg13cmos5l-bandgap_top`"'s own
device-count accounting above). `sg13cmos5l-bandgap_top.pex.spice` and its
`pex_extract_report.json` companion are committed as read-only extraction
artifacts — see
`sim/sg13cmos5l-closed-loop-startup-pex/README.md` for the full account of
what this extraction does and does not model, and the resulting PVT-sweep
evidence under `sim/`.

**`--parasitics` does not work for this deck — found and filed this
pass, not silently worked around.** The obvious next command,

```bash
klt extract --deck sg13cmos5l --parasitics sg13cmos5l-bandgap_top.gds \
  -o sg13cmos5l-bandgap_top.pex.spice --format json
```

fails outright: `{"error": {"message": "unknown deck 'sg13cmos5l'
(available: gf180mcu, sg13g2, sky130)"}}`, exit 1 — even though `klt deck
info --deck sg13cmos5l` reports the deck installed and `klt extract --deck
sg13cmos5l` (no `--parasitics`) succeeds normally, as above. Root cause,
traced directly in the installed package source:
`klayout_tools.decks.__init__._parasitics_registry()` hardcodes its deck
import/dict to three decks (`sky130`, `gf180mcu`, `sg13g2`) and never
imports `sg13cmos5l` — every *other* per-deck lookup table in that same
file (the extraction-deck registry, the layer-name table, the
unmodelled-voltage-marker list, the nominal-DBU table) already includes
`sg13cmos5l`; only this one function's import list was never updated when
`decks/sg13cmos5l.py` was added. This directly contradicts that module's
own comment above its `PARASITICS = ParasiticsDeck()` declaration, which
documents `--parasitics` against `sg13cmos5l` as intended to succeed today
(reporting zero R/C for every net, the same graceful degradation any deck
with no curated sheet-resistance table gets) — not fail outright. Filed
generically, per `CLAUDE.md`'s friction protocol, as
[klayout-tools#1440](https://github.com/2AMLogic/klayout-tools/issues/1440)
— distinct from (and found on top of) the already-filed device-class gaps
below, since even a fixed registry would still report zero R/C for this
starter deck (no coefficient table exists yet), so this pass used the
plain (working) extraction mode above rather than block on the registry
fix. Consequence: `sim/sg13cmos5l-closed-loop-startup-pex/` (issue #84)
extracts real device geometry (`w`/`l`/`as`/`ad`/`ps`/`pd`) but models zero
wire (metal) parasitics — a materially weaker claim than the SG13G2 PEX
pair's own wire-RC-inclusive evidence (issue #37). See that experiment's
README for the full disclosure.

## Reference netlist

`layout/lvs_reference.py` gained a `pdk="sg13cmos5l"` mode (issue #66) that
converts `design/sg13cmos5l/netlist/bandgap_core.spice` into the plain-element
form `klt lvs` requires. Two things it does that the SG13G2 path did not need:

- **`pnpMPA` is a 3-terminal `Q` element** (`Q1 vss vss sns1 pnpmpa AE=2P
  PE=6U`), where SG13G2's `npn13G2` is 4-terminal. Its size parameters are
  emitter area/perimeter, not `w`/`l`, and xschem emits them as *expressions*
  (`a={ 1u * 2u }`) — so the line parser is now brace-aware and a small
  suffix-aware evaluator resolves them.
- **`rppd`'s value uses CMOS5L's own symbol formula**
  (`libs.tech/xschem/sg13cmos5l_pr/rppd.sym`'s `value=` expression: a
  `70 µΩ·m` end term plus 260 Ω/sq over the width-corrected `w + 6 nm`),
  rather than the flat sheet approximation the SG13G2 path uses. Worth
  keeping separate: CMOS5L's `techParams` carries **two** sheet values
  (`rppd_rspec = 250.0`, `rppdG2_rspec = 260.0`) and it is the symbol, not
  the bare `rspec`, that says which one the schematic's own annotated value
  uses.

Issue #74 extended it to `bandgap_amp` and `bandgap_startup`. `sg13_hv_nmos`
already mapped to `nfet` in the shared `_MOS_CLASS` table, so the amp needed
no new conversion at all; `bandgap_startup`'s `RPU` needed the `rhigh` value
formula, read from `rhigh.sym` the same way. That formula is **not** the
`rppd` one with different constants — its width correction is negative
(`rhigh_lwd = -0.04u` against `rppd`'s `+6 nm`) and the sheet value the symbol
uses is `rhighG2_rspec` (1360.0), not the bare `rhigh_rspec` (1300.0), the
same two-sheet-values trap `rppd` has. `RPU` at `w=1u l=1411.3u` comes out at
`1999501.7` Ω.

`bandgap_top` needed a **different** entry point, not an extension of
`convert()`: it is a hierarchical netlist (three subckt calls, no device
lines of its own), which `convert()`'s per-device-line grammar cannot
express. `lvs_reference.py` gained `flatten()` for this (issue #76):
it parses the hierarchical deck's own top-level calls and each called
subckt's own body (`_parse_subckt_blocks()` — `bandgap_top.spice` carries
all three children's full definitions inline, the normal xschem/ngspice
netlisting shape, not yet flattened into one plain-element netlist),
substitutes each child's own port names through its call's own connection
map, scopes every other (non-port) net and every device's own instance name
to that instance (`x1.e2`, `Mx1_M1`, …, so two children's internal nets or
instance names can never collide even though none in this design actually
do), and hands each renamed device line to the same `_convert_device_line()`
dispatch `convert()` itself uses — so a flattened and a flat netlist convert
identically device-line-by-device-line. Verified directly against
`design/sg13cmos5l/netlist/bandgap_top.spice` (no assembled GDS needed to
check this): the output parses cleanly via
`klayout.db.NetlistSpiceReader` into one `.TOP` circuit, 20 devices (8 from
`bandgap_core`, 9 from `bandgap_amp`, 3 from `bandgap_startup`) and 13 nets
(6 shared — `fb`/`sns1`/`sns2`/`vdd`/`vref`/`vss` — plus 7 correctly-scoped
internal ones). Run through `klt lvs` against the assembled
`sg13cmos5l-bandgap_top.gds` in issue #81 — see "Cell:
`sg13cmos5l-bandgap_top`" above.

The SG13G2 pair's generated netlists are **byte-identical** after this change
(verified: `git diff` empty). The new `* PDK:` provenance header is emitted
only for a non-default PDK, precisely so the two still-fresh SG13G2
`lvs_report.json`s — which pin those files' exact bytes in
`environment.reference_sha256` — are not marked stale by a cosmetic edit.

## Tooling friction filed upstream

Per `CLAUDE.md`'s friction protocol, every gap this phase hit is filed
generically against the tool, not worked around in this repo:

| Gap | Upstream issue |
|---|---|
| No well/substrate tap layers in the `sg13cmos5l` deck | [klayout-tools#1414](https://github.com/2AMLogic/klayout-tools/issues/1414) |
| No poly-resistor recognition; unmodelled body shorts its terminals | [klayout-tools#1415](https://github.com/2AMLogic/klayout-tools/issues/1415) |
| No HV (`ThickGateOx`) MOS flavour | [klayout-tools#1416](https://github.com/2AMLogic/klayout-tools/issues/1416) |
| Only `Metal1` modelled, no via — forces planar single-metal layout | [klayout-tools#1417](https://github.com/2AMLogic/klayout-tools/issues/1417) |
| `sg13cmos5l` missing from `--deck` help text and from `drc.md`/`lvs.md`/`pdk.md` | [klayout-tools#1418](https://github.com/2AMLogic/klayout-tools/issues/1418) |
| An intentional poly underpass is reported as an unmodelled resistor body, with no way to annotate it | [klayout-tools#1425](https://github.com/2AMLogic/klayout-tools/issues/1425) (issue #74) |
| `--parasitics` fails outright for `sg13cmos5l` (`_parasitics_registry()` never registers this deck) | [klayout-tools#1440](https://github.com/2AMLogic/klayout-tools/issues/1440) (issue #84) |

Bipolar (`pnpMPA`) recognition is deliberately **not** re-filed: see cause 1
above — it is the same source file, and the same finding, klayout-tools#1242
already closed as investigated-and-declined for SG13G2.

Nor is the NMOS/substrate side of cause 4 re-filed as its own issue: it is
the same missing `tap_nplus`/`tap_pplus` pair klayout-tools#1414 already asks
for, seen from the other body type. What #74 *did* add there is a comment
recording the isolation result above — that on a cell where every body ties
to a rail, the gap takes an otherwise-perfect compare from 9/9 devices to
0/9 rather than merely raising `device.body_unverified`.

## What this layout is / is not

Everything the SG13G2 section's "What this layout is / is not" says applies
here too (simplified representative footprints, not PCell-exact stacks;
no guard rings, fill or seal ring;
no analog matching structures — no common-centroid mirror interdigitation, no
dummy devices). Two CMOS5L-specific additions:

- **`Q2` is now drawn as 8 parallel unit devices, not one wide emitter**
  (issue #73, DR-0005 — resolved; see "Q2: 8 parallel unit devices" above for
  the full account). It was originally drawn as one `w=8u` emitter matching
  the netlist's then-`a={ 8u * 2u }` / `p={ (8u + 2u) * 2 }` exactly, flagged
  here as *not* how a real matched 8× PNP would be built and, worse, not even
  PCell-buildable (`pnpMPA_maxW` is `2.0u` in `sg13cmos5l_tech.json`). The
  design-side fix (issue #73) and this layout's own regeneration landed
  together in the same change. `bandgap_core` only — `bandgap_amp` and
  `bandgap_startup` (#74) draw no bipolars at all.
- **The n-well is shared across each cell's PMOS** (rather than one well per
  device) so their body terminals resolve to a single well net, matching the
  schematic's common `vdd` body tie — the only part of the body connection
  the deck can express at all (cause 4 above). In `bandgap_amp` that is one
  well spanning **both** PMOS rows, not one per row, for the same reason.
- **`bandgap_amp` uses a poly underpass** where `bandgap_core` is strictly
  planar. That is a real, standard single-metal technique rather than a
  compromise, but it is worth naming as a difference from the SG13G2 cells,
  which never need one because that deck models seven metals and six vias.
  Its resistance is not modelled by anything here; the deck's parasitics
  surface is out of scope for these cells, as it is for `bandgap_core`.

## Cells not laid out

None, as of issue #81. `bandgap_top` (schematic landed in #70) was the last
one — it is not a fourth leaf cell but an **assembly** of the three others
(`Xx1 vdd vss fb sns1 sns2 vref bandgap_core`, `Xx2 sns2 sns1 vss fb vdd
bandgap_amp`, `Xx3 vdd vss sns1 fb bandgap_startup`,
`design/sg13cmos5l/netlist/bandgap_top.spice`'s own top-level netlist), and
its own layout — `layout/sg13cmos5l-bandgap_top/` — is now assembled,
routed, and DRC/LVS/extract-verified. See "Cell:
`sg13cmos5l-bandgap_top` (issue #81)" above for the full account
(floorplan, routing, the short found and fixed, and the LVS attribution).

This section's own history, briefly: issue #76 closed the blocker that had
kept the assembly out of scope — **none of the three leaf cells had a
boundary port** (every net name used to be a `Metal1.pin` label on whatever
*internal* device pad happened to carry the net, sufficient for a
standalone leaf-cell LVS but leaving several ports physically unreachable
from outside the cell's own footprint), and added the
`common_sg13cmos5l.boundary_port()` convention plus `lvs_reference.py`'s
`flatten()` mode. Issue #81 (this section) did the assembly itself.
