# layout — bandgap core + startup GDS (issue #11)

Physical layout for the two schematics landed in #9 (`design/bandgap_core.sch`,
`design/bandgap_startup.sch`). This directory is no longer a placeholder:

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
- **Is not** LVS-clean, still (#20 re-ran this fresh after routing — see
  "DRC/LVS verification" below for the full, itemized finding: a real
  `status: "mismatch"` persists on both cells, now attributed to *three*
  independent, fully-diagnosed causes, none fixable from this repo's own
  side: the curated deck's documented bipolar/resistor-recognition gap
  (unchanged from #12), a newly-discovered lack of any well/substrate-tap
  modelling in the same deck, and (`bandgap_core` only) a genuine
  structural device-symmetry ambiguity the missing bipolar/resistor
  devices expose).
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
| `bandgap_core` | `layout/bandgap_core/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:72c12aad...` |
| `bandgap_startup` | `layout/bandgap_startup/drc_report.json` | `clean`, 0 violations | `sg13g2`, `sha256:72c12aad...` |

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

### LVS — still `mismatch`, resistor recognition now resolved (issues #20/#27)

| Cell | Report | Status | Engine |
| --- | --- | --- | --- |
| `bandgap_core` | `layout/bandgap_core/lvs_report.json` | `mismatch` (30 findings, 29 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |
| `bandgap_startup` | `layout/bandgap_startup/lvs_report.json` | `mismatch` (16 findings, 14 error-severity) | `klayout` (`klayout.db.NetlistComparer`) |

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
   **Not independently re-tested under issue #20's resistor recognition**:
   `R1`/`R2` are no longer invisible to the layout-side extraction (unlike
   when this experiment ran), and `R1`/`R2` differ in length (`l=694.5u`
   vs `l=82.7u`) — in principle this *could* now distinguish `M2`
   (`→R2→Q2`) from `M3` (`→R1→Q3`) structurally, narrowing the automorphism
   to a smaller ambiguity (or none). Re-running the same `hints.same_nets`
   experiment to check is exactly the automorphism-resolution work this
   issue's own scope explicitly excludes ("do not attempt... via routing or
   LVS hints") — left untested here deliberately, not because the outcome
   is assumed unchanged.

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

### Permanent blockers (issue #20 rescope, 2026-08-23)

Three causes are now understood, from this issue's and #27's own recorded
evidence, to be **permanently unreachable through routing, marker-layer
geometry, or `klt lvs` hints alone** — a future pass should not
re-investigate any of these from scratch without a new upstream capability
or a schematic-level circuit change:

1. **Bipolar (SiGe HBT) device recognition is permanently declined
   upstream** (`klayout-tools#1242`, closed; `klayout-tools#1232`'s own
   `completed` docs-only PR, no code change to wait on). Every
   `Q1`–`Q3` (`bandgap_core`) instance stays `device.unmatched`,
   class `NPN13G2`, indefinitely.
2. **`bandgap_core`'s `M1`/`M2`/`M3` were a genuine graph automorphism**
   at the recognised-device level when bipolar *and* resistor devices were
   both excluded from the comparison (cause 3 above, PR #27's own
   experiment, before issue #20's resistor recognition) — confirmed by
   direct experiment at the time: explicit `hints.same_nets` pairings were
   rejected by the comparer, with conflicting `net.merged`/`net.split`
   findings as evidence a different, equally-valid correspondence exists
   under the layout's own more symmetric graph structure. **Not
   independently re-tested since resistor recognition landed** (see cause
   3 above's own caveat) — `R1`/`R2` now genuinely differ in length and
   are no longer invisible to the layout side, which could in principle
   narrow or resolve this specific ambiguity; re-running the hints
   experiment to check is itself the automorphism-resolution work this
   issue's scope explicitly excludes. Listed here as a blocker this issue
   did not resolve, not as a settled-permanent fact independent of #20.
3. **`bandgap_startup`'s `MSENSE.gate` net extracts as an anonymous net**,
   independent of resistor recognition, because the curated deck declares
   no `poly_label` layer at all (`EXTRACTION_DECK.poly_label=None`) — GDS
   text placed on a `GatPoly`-adjacent label layer is simply not a signal
   this deck's net-naming pass reads for a gate terminal (unlike
   `Metal1.text`/`Metal2.text`, see this file's own module-level comment on
   `L_METAL1_TEXT`/`L_METAL2_TEXT` in `layout/common.py`). Re-verified
   directly for this issue: `klt extract` reports `MSENSE`'s gate net as
   `$4` (`MSENSE`'s own schematic net is `sns1`), never `sns1` by name —
   a structural, permanent deck limitation (no drawn or derivable poly-label
   geometry can produce a name from a layer the deck's connectivity graph
   never reads at all), not a routing or layout-marker gap.

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
