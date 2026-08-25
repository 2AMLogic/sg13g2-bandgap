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

**Update (issue #32, `records/20260821-224608-837323a.{md,csv}`):**
`layout/bandgap_startup/generate.py` has been regenerated with `XMSENSE` at
`w=10u`, matching `design/netlist/bandgap_startup.spice`'s current value —
see "Cross-bench observation" below for the current (passing) numbers. The
original bug-reproducing record from before the fix
(`records/20260821-160458-42d8348.{md,csv}`, `w=2u` extraction) is preserved
below and on disk, per this directory's append-only convention — it is
historical evidence of the bug this issue fixed, not a live caveat.

**Update (issue #37, `records/20260821-231306-9ea33c1.{md,csv}`):**
re-extracted against the *same* corrected `w=10u` geometry, but with the
`sg13g2` deck's now-populated parasitics tables, so this was the first
record here to carry real Metal1/Metal2 **wire R/C** (see "Wire resistance
and capacitance" below). It did **not** change the issue #32 conclusion:
45/45 PASS, and the cross-bench margin bug decision record 0003 describes
stayed **resolved** — every one of the 45 points kept a positive margin,
minimum `+63.59 mV`. Wire parasitics moved `vtrip` by at most `17 µV`
(median `9 µV`) relative to issue #32's own wire-RC-free record.

**Update (issue #56, `records/20260825-132535-eeea775.{md,csv}` — the
current record):** the committed PEX evidence had gone stale relative to
`layout/bandgap_startup/bandgap_startup.gds` — PR #45 added resistor
marker layers to the layout, but only the DRC/LVS reports were regenerated
against it at the time, not the PEX leg. Re-extracting and re-running this
sweep against the current GDS: **max `|Δvtrip|` across all 45 points vs.
the immediately-preceding record is `3 µV`** — noise at the CSV's own
printed precision. The cross-bench margin-bug comparison against
`core-open-loop-bias-pex`'s own refreshed record (issue #56) stays
resolved: all 45 points positive, minimum margin `+63.5956 mV` at
`wcs_125c_3.63v` (was `+63.5946 mV` at the same point, pre-#56 — a ~1 µV
shift, consistent with the near-zero `vref`/`vtrip` deltas above, not a
regression). As with
`core-open-loop-bias-pex`, PR #45's marker layers also made the `sg13g2`
deck's `rhigh` recognizer match `XRPU` for the first time here
(`device_counts` went from `{"nfet": 2}` to `{"nfet": 2, "rhigh": 1}`) —
see "NOT modelled" below; this testbench's architecture is otherwise
unchanged, and consuming the newly-recognised resistor is tracked as a
follow-on, [issue #59](https://github.com/2AMLogic/sg13g2-bandgap/issues/59).

## Dependency on layout/README.md

`layout/bandgap_startup/lvs_report.json` reads `status: "mismatch"` as of
this writing (issue #20, still open, blocked on `klayout-tools`#1273). Same
caveated-but-not-clean extraction-input situation as
`core-open-loop-bias-pex/README.md` describes — see that file and
`layout/README.md`'s "DRC/LVS verification" section for the full account.
This mismatch reason is unchanged by issue #32's width fix (re-confirmed:
same 16 findings / 14 error-severity, same category breakdown, before and
after regenerating the layout).

## What this does and does not model

**Modelled, from the real routed layout:**

- `XMSENSE`/`XMKFB` (`sg13_hv_nmos`) — real drawn junction geometry
  (`XMSENSE`: `as=4p ad=4p ps=20.8u pd=20.8u`, at the corrected `w=10u`;
  `XMKFB`: `as=0.8p ad=0.8p ps=4.8u pd=4.8u`, unchanged at `w=2u`) from
  `layout/bandgap_startup/pex_extract_report.json`'s `devices[]` block.
  Their D/G/S node roles match the schematic's own convention exactly (no
  swap, unlike `core-open-loop-bias-pex`'s PMOS legs) — confirm directly:
  `M$1 det \$4 vss vsubs` (extracted) vs. `XMSENSE det sns1 vss vss`
  (schematic) line up terminal-for-terminal once `\$4` is read as the
  extraction's anonymous label for `sns1`.
- **Wire resistance and capacitance (issue #37, updated 2026-08-21).**
  [klayout-tools#1277](https://github.com/2AMLogic/klayout-tools/issues/1277)
  closed via [klayout-tools#1280](https://github.com/2AMLogic/klayout-tools/pull/1280),
  which populated the `sg13g2` deck's `PARASITICS.metals`/`metal_overlaps`
  coefficient tables. Re-extracting against the current deck now reports
  `r_count: 5, c_count: 3, cc_count: 0` (`total_resistance_ohm: 544.07`,
  `total_capacitance_ff: 132.50`) in `pex_extract_report.json`'s
  `parasitics` block — `metals_without_coefficient` is now empty. Every
  `R`/`C` card the re-extraction wrote is spliced into
  `testbench/tb_startup_trip_point_pex.spice.tmpl` verbatim, through the
  same per-terminal hub node names (`det__t0`/`__t1`, `fb__t0`,
  `vss__t0`/`__t1`) the extraction itself uses. Effect on the recorded
  sweep is small but real: max `|Δvtrip|` across all 45 points vs. the
  pre-#1280 baseline (`records/20260821-160458-42d8348.csv`) is `17 µV`.
  `XMSENSE`'s gate net (`\$4`, the schematic's `sns1`) gets no wire model
  either way — it is a single-terminal, deck-disconnected net in this
  isolated cell's own extraction, unaffected by the deck fix; the
  testbench's own `Vsns1` drive is a fixture bridging that separate gap,
  unchanged by this pass.

**NOT modelled, or modelled differently than the current schematic
(disclosed, not silently omitted):**

- **XMSENSE's extracted width is now `w=10u`, matching the schematic
  (issue #32 — resolved).** `layout/bandgap_startup/generate.py` (issue
  #11/PR #19) originally drew this device at `w=2u`, before
  [decision record 0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md)
  (issue #24/PR #29) widened `XMSENSE` from `w=2u` to `w=10u` in
  `design/netlist/bandgap_startup.spice` to fix a real 125 °C
  startup-release margin bug — the layout was not regenerated to match
  until [issue #32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32).
  This testbench is **as-drawn** (now `w=10u`): PEX evidence reflects what
  the committed GDS actually is. See "Cross-bench observation" below for
  the before/after margin numbers, and `records/20260821-160458-42d8348.md`
  (preserved) for the original `w=2u` bug-reproducing record.
- **The resistor device is now recognised (issue #56), but still not
  consumed by this testbench.** `rhigh` (this experiment's `XRPU`) already
  had a recognizer in `EXTRACTION_DECK.resistors`
  (`klayout_tools.decks.sg13g2`, issue #1235) before PR #45, but
  `layout/common.py`'s shared `draw_poly_res` (used by both cells' poly
  resistors) only drew the `PolyRes` body and a `Metal1` end pad, never the
  `pSD`/`SalBlock`/`EXTBlock` marker layers `rhigh`/`rppd` recognition
  additionally requires — a layout-drawing gap in this repo, not a
  `klayout-tools` one. **PR #45 added those marker layers to the GDS**, and
  re-extracting against the current layout (issue #56) confirms
  recognition now succeeds: `device_counts` reads `{"nfet": 2, "rhigh":
  1}` (up from `{"nfet": 2}`), with a real `rhigh` device card (`R$3`,
  drawn resistance `1919368 ohm` from the layout's own geometry) in the
  re-extracted `bandgap_startup.pex.spice`. **This testbench does not yet
  consume that** — `XRPU` (`rhigh`) is still spliced in verbatim from
  `design/netlist/bandgap_startup.spice`, wired to the extraction's own
  real, physically-routed `vdd`/`det` net names; the newly-extracted `R$3`
  device card and its isolated two-node net (`\$5`/`\$5__t0`) are
  deliberately omitted from
  `testbench/tb_startup_trip_point_pex.spice.tmpl` rather than
  double-counted alongside the schematic splice. Incorporating it is
  tracked as a follow-on:
  [issue #59](https://github.com/2AMLogic/sg13g2-bandgap/issues/59).
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

Same deck-version caveat as `core-open-loop-bias-pex/README.md`'s "Cold-start
invocation" section: the committed extraction here was produced from
`klt 0.3.0+g71cbae53b7e6.dirty` (`provenance.klt_version` in the JSON,
issue #56), not the (currently stale,
[klayout-tools#1249](https://github.com/2AMLogic/klayout-tools/issues/1249))
`pip`-installed `klayout-tools==0.2.0`. Confirm `pex_extract_report.json`'s
`parasitics.r_count`/`c_count` are non-zero before trusting a re-run, and
regenerate `testbench/tb_startup_trip_point_pex.spice.tmpl`'s "Wire
parasitics" block from a freshly regenerated `bandgap_startup.pex.spice` if
they no longer match.

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

## Cross-bench observation: decision record 0003's margin bug — before/after issue #32

**The direct 45-point sweep alone reads 45/45 PASS**, both before and after
issue #32's width fix — this testbench drives `sns1` across the full
`0 -> vdd` range, and the circuit always finishes releasing by the time
`sns1` reaches `vdd`. This is the same limitation `sim/startup-trip-point`'s
own records already flagged for the schematic-level testbench: a full-range
sweep does not, by itself, reproduce (or clear) decision record 0003's
margin bug — only a comparison against the core's *real* `sns1` operating
point (or a true co-simulation, like `sim/startup-core-handover/`) does.

Comparing this record's `vtrip_v` against
[`core-open-loop-bias-pex`](../core-open-loop-bias-pex/README.md)'s own real
`sns1` (`vbe_q1_v` column) at matching `(corner, temp, vdd)` points:

**Before the fix** (`records/20260821-160458-42d8348.csv`, `XMSENSE` extracted
at the stale `w=2u`):

| corner | temp | vdd | core `sns1` (V) | `vtrip` (V) | margin (mV) |
|---|---|---|---|---|---|
| `sf`  | 125 | 3.63 | 0.5804 | 0.5832 | **-2.80** |
| `wcs` | 125 | 2.97 | 0.5909 | 0.5951 | **-4.22** |
| `wcs` | 125 | 3.30 | 0.5910 | 0.5984 | **-7.45** |
| `wcs` | 125 | 3.63 | 0.5910 | 0.6013 | **-10.21** |

(margin = core `sns1` - `vtrip`; negative means the core's real operating
point had not yet reached the trip threshold, i.e. the startup circuit
would still read "engaged" once the core was actually running there.) These
were **the exact same 4 points** `wcs_125c_{2.97,3.30,3.63}v` and
`sf_125c_3.63v` — decision record 0003's own cross-bench comparison flagged
before it built the true co-simulation (`sim/startup-core-handover/`) that
confirmed and fixed the bug at the schematic level, and the margins there
(2-10 mV) matched that record's own figure almost exactly. Every other one
of the 45 points already had a positive margin (>20 mV, most well above
50 mV).

**After the fix** (`records/20260821-224608-837323a.csv`, `XMSENSE` extracted
at the corrected `w=10u`, matching the schematic):

| corner | temp | vdd | core `sns1` (V) | `vtrip` (V) | margin (mV) |
|---|---|---|---|---|---|
| `sf`  | 125 | 3.63 | 0.5804 | 0.5076 | **+72.84** |
| `wcs` | 125 | 2.97 | 0.5909 | 0.5229 | **+68.03** |
| `wcs` | 125 | 3.30 | 0.5910 | 0.5254 | **+65.58** |
| `wcs` | 125 | 3.63 | 0.5911 | 0.5274 | **+63.64** |

All **45/45** points now show a positive margin (the previously-failing 4
points now clear by 63-73 mV; every other point clears by 63-229 mV — see
the full record CSV for every point).

**After issue #56's re-extraction** (`records/20260825-132535-eeea775.csv`
against `records/20260825-132531-eeea775.csv` — current, post-PR-#45-marker-
layer evidence): the same 4 points read `sf_125c_3.63v` `+72.80`,
`wcs_125c_2.97v` `+67.99`, `wcs_125c_3.30v` `+65.53`, `wcs_125c_3.63v`
`+63.60` (mV) — each within `0.05 mV` of the issue #32/#37 figures directly
above, i.e. unchanged within this pair of experiments' own few-µV noise
floor (see the "Update (issue #56)" note at the top of this file). All
45/45 points stay positive; the margin-bug fix these two experiments
cross-confirm is unaffected by PR #45's resistor-recognition marker
layers.

**What this means**: decision record 0003 widened `XMSENSE` to `w=10u` in
`design/netlist/bandgap_startup.spice` at the schematic level (issue #24/PR
#29); issue #32 brought the layout into sync by regenerating
`layout/bandgap_startup.gds` with the same `w=10u`. This PEX evidence
confirms the corrected, as-fabricated layout **no longer carries the 125 °C
startup-release margin bug** decision record 0003 originally fixed only at
the schematic level — the layout and schematic are now in agreement, and
the cross-bench comparison that previously exposed the drift now clears at
every PVT point.

**Not attempted here**: a true co-simulation (`sim/startup-core-handover/`
style, sharing real `sns1`/`fb` nodes under a transient ramp) against the
PEX-extracted, corrected-width devices, which would confirm this
cross-bench margin comparison the same rigorous way issue #24 confirmed the
original schematic-level finding. Left as follow-on scope, not required to
close issue #32 (which was scoped to the layout/GDS drift specifically, not
a new co-simulation methodology).

## Follow-up — resolved

Regenerating `layout/bandgap_startup.gds` with `XMSENSE` at `w=10u` (and
re-running DRC/LVS/PEX against the corrected layout) was tracked in
[issue #32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32) and is now
done — see the "Update" note at the top of this file and "Cross-bench
observation" above for the resulting evidence.
