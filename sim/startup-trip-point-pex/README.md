# startup-trip-point-pex

Post-layout (PEX) counterpart to
[`sim/startup-trip-point/`](../startup-trip-point/README.md), issue #14.
Same claim, same PVT grid, same `sns1`-stimulus/`fb`-pull-up fixtures — the
difference is where `XMSENSE`/`XMKFB`'s geometry comes from: the
schematic-level testbench copies `design/netlist/bandgap_startup.spice`'s
own `w`/`l` verbatim; this one re-encodes them from
`klt extract --deck sg13g2 --parasitics layout/bandgap_startup/bandgap_startup.gds`
(committed as `layout/bandgap_startup/bandgap_startup.pex.spice` +
`pex_extract_report.json`). Read this file before trusting a record here —
it is **not** a pure layout extraction re-simulated as-is, and its headline
45/45 PASS number needs the "Cross-bench observation" section below to be
read correctly.

## Dependency on layout/README.md

`layout/bandgap_startup/lvs_report.json` reads `status: "mismatch"` as of
this writing (issue #20, still open, blocked on `klayout-tools`#1273). Same
caveated-but-not-clean extraction-input situation as
`core-open-loop-bias-pex/README.md` describes — see that file and
`layout/README.md`'s "DRC/LVS verification" section for the full account.

## What this does and does not model

**Modelled, from the real routed layout:**

- `XMSENSE`/`XMKFB` (`sg13_hv_nmos`) — real drawn junction geometry
  (`as=0.8p ad=0.8p ps=4.8u pd=4.8u`) from
  `layout/bandgap_startup/pex_extract_report.json`'s `devices[]` block.
  Their D/G/S node roles match the schematic's own convention exactly (no
  swap, unlike `core-open-loop-bias-pex`'s PMOS legs) — confirm directly:
  `M$1 det \$4 vss vsubs` (extracted) vs. `XMSENSE det sns1 vss vss`
  (schematic) line up terminal-for-terminal once `\$4` is read as the
  extraction's anonymous label for `sns1`.

**NOT modelled, or modelled differently than the current schematic
(disclosed, not silently omitted):**

- **XMSENSE's extracted width is `w=2u`, not the schematic's current
  `w=10u`.** `layout/bandgap_startup/generate.py` (issue #11/PR #19) drew
  this device before
  [decision record 0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md)
  (issue #24/PR #29) widened `XMSENSE` from `w=2u` to `w=10u` in
  `design/netlist/bandgap_startup.spice` to fix a real 125 °C
  startup-release margin bug — the layout has never been regenerated to
  match. This testbench is deliberately **as-drawn** (`w=2u`): PEX evidence
  should show what the committed GDS actually is, not what the current
  schematic says.
  **[Issue #32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32) tracks
  regenerating the layout** (see "Follow-up filed" below) — this
  experiment does not attempt to fix it, only to surface it accurately.
- **Resistor devices are not extracted at all.** Same `klt`/`sg13g2` deck
  gap as `core-open-loop-bias-pex` — `XRPU` (`rhigh`) is spliced in
  verbatim from `design/netlist/bandgap_startup.spice`, wired to the
  extraction's own real, physically-routed `vdd`/`det` net names.
- **Zero wire resistance and capacitance.** Same deck-content gap as
  `core-open-loop-bias-pex` — `pex_extract_report.json`'s `parasitics`
  block reports `r_count: 0, c_count: 0` here too.
- **Body terminal substituted, not extracted as-is.** Both extracted
  devices' body terminals land on the deck's own synthesized global
  fallback net (`vsubs` in `bandgap_startup.pex.spice`), not the
  schematic's real body-tied-to-`vss` (`layout/README.md`'s LVS cause 2).
  This testbench ties body to `vss` directly instead, mirroring the
  schematic's real intent.

## Cold-start invocation

Same prerequisites as `sim/startup-trip-point/` (ngspice, a resolvable
SG13G2 PDK install, OSDI models via `sim/tools/build-osdi.sh`). Does **not**
require `klt` to run this script — regenerate the extraction input with:

```bash
cd layout/bandgap_startup
klt extract --deck sg13g2 --parasitics bandgap_startup.gds \
  -o bandgap_startup.pex.spice --format json > pex_extract_report.json
```

Then:

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/startup-trip-point-pex/run_pvt_sweep.sh
```

Same 45-point grid, same four pass criteria, same output layout as
`sim/startup-trip-point/` — see that experiment's README and
`sim/README.md` for the full conventions.

## Cross-bench observation: reproduces decision record 0003's margin bug

**The direct 45-point sweep alone reads 45/45 PASS**, even at `w=2u` — this
testbench drives `sns1` across the full `0 -> vdd` range, and the circuit
always finishes releasing by the time `sns1` reaches `vdd`. This is the same
limitation `sim/startup-trip-point`'s own records already flagged for the
schematic-level testbench: a full-range sweep does not, by itself, reproduce
decision record 0003's margin bug — only a comparison against the core's
*real* `sns1` operating point (or a true co-simulation, like
`sim/startup-core-handover/`) does.

Comparing this record's `vtrip_v` against
[`core-open-loop-bias-pex`](../core-open-loop-bias-pex/README.md)'s own real
`sns1` (`vbe_q1_v` column) at matching `(corner, temp, vdd)` points:

| corner | temp | vdd | core `sns1` (V) | `vtrip` (V) | margin (mV) |
|---|---|---|---|---|---|
| `sf`  | 125 | 3.63 | 0.5804 | 0.5832 | **-2.75** |
| `wcs` | 125 | 2.97 | 0.5909 | 0.5951 | **-4.17** |
| `wcs` | 125 | 3.30 | 0.5910 | 0.5984 | **-7.41** |
| `wcs` | 125 | 3.63 | 0.5911 | 0.6012 | **-10.16** |

(margin = core `sns1` - `vtrip`; negative means the core's real operating
point has not yet reached the trip threshold, i.e. the startup circuit
would still read "engaged" once the core is actually running there.)

Every other one of the 45 points has a positive margin (>20 mV, most well
above 50 mV). **These are the exact same 4 points**
`wcs_125c_{2.97,3.30,3.63}v` and `sf_125c_3.63v` — decision record 0003's
own cross-bench comparison flagged before it built the true co-simulation
(`sim/startup-core-handover/`) that confirmed and fixed the bug at the
schematic level, and the margins here (2-10 mV) match that record's own
figure almost exactly.

**What this means**: decision record 0003 widened `XMSENSE` to `w=10u` in
`design/netlist/bandgap_startup.spice` only. `layout/bandgap_startup.gds`
still draws `XMSENSE` at the original, buggy `w=2u`. This PEX evidence shows
the **as-fabricated layout would carry the same margin bug decision record
0003 fixed at the schematic level** into silicon — not a new PEX-specific
defect, but real evidence that the layout has drifted out of sync with the
schematic it was drawn from.

**Not attempted here**: a true co-simulation (`sim/startup-core-handover/`
style, sharing real `sns1`/`fb` nodes under a transient ramp) against the
PEX-extracted devices, which would confirm this cross-bench margin
comparison the same rigorous way issue #24 confirmed the original schematic-
level finding. Left as follow-on scope — see "Follow-up filed" below ([issue #32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32)).

## Follow-up filed

Regenerating `layout/bandgap_startup.gds` with `XMSENSE` at `w=10u` (and
re-running DRC/LVS/PEX against the corrected layout) is tracked in
[issue #32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32) — see
that issue for the exact scope.
