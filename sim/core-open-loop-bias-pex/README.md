# core-open-loop-bias-pex

Post-layout (PEX) counterpart to [`sim/core-open-loop-bias/`](../core-open-loop-bias/README.md),
issue #14. Same claim, same PVT grid, same open-loop bias/ammeter fixtures —
the difference is where `XM1`/`XM2`/`XM3`'s geometry comes from: the
schematic-level testbench copies `design/netlist/bandgap_core.spice`'s own
`w`/`l` verbatim; this one re-encodes them from
`klt extract --deck sg13g2 --parasitics layout/bandgap_core/bandgap_core.gds`
(committed as `layout/bandgap_core/bandgap_core.pex.spice` +
`pex_extract_report.json`). Read this file before trusting a record here —
it is **not** a pure layout extraction re-simulated as-is.

## Dependency on layout/README.md

`layout/bandgap_core/lvs_report.json` reads `status: "mismatch"` as of this
writing (issue #20, still open, blocked on `klayout-tools`#1273). Per issue
#14's own scope text and its Curator Enhancement, a caveated-but-not-clean
layout is an allowed extraction input — but every caveat that LVS mismatch
carries also applies to the PEX evidence built from the same layout. This
README restates the parts that matter for simulation; `layout/README.md`'s
"DRC/LVS verification" section is the authoritative, fuller account.

## What this does and does not model

**Modelled, from the real routed layout:**

- `XM1`/`XM2`/`XM3` (`sg13_hv_pmos`) — real drawn `w=10u l=1u`, plus real
  drawn junction geometry `as=4p ad=4p ps=20.8u pd=20.8u`, taken directly
  from `pex_extract_report.json`'s `devices[]` block. Same PSP103.6 compact
  model as the schematic-level testbench (`psp103.osdi`) — this is real
  drawn geometry through the real compact model, not an ideal-primitive
  substitution.
- **Wire resistance and capacitance for Metal1/Metal2 (issue #37, updated
  2026-08-21).** [klayout-tools#1277](https://github.com/2AMLogic/klayout-tools/issues/1277)
  (filed against PR #33's original extraction, whose `r_count`/`c_count`
  were both `0`) closed via
  [klayout-tools#1280](https://github.com/2AMLogic/klayout-tools/pull/1280),
  which populated the `sg13g2` deck's `PARASITICS.metals`/`metal_overlaps`
  coefficient tables. Re-extracting against the current deck now reports
  `r_count: 9, c_count: 7, cc_count: 8` (`total_resistance_ohm: 316.67`,
  `total_capacitance_ff: 104.78`) in `pex_extract_report.json`'s
  `parasitics` block, and `metals_without_coefficient`/
  `overlap_pairs_without_coefficient` are both now empty — the deck's own
  zero-RC warning is gone, and no *other* metal level newly reports zero
  RC. Every `R`/`C` card the re-extraction wrote is spliced into
  `testbench/tb_core_open_loop_bias_pex.spice.tmpl` verbatim, wired through
  the same per-terminal hub node names (`vdd__t0`/`__t1`/`__t2`,
  `sns1__t0`/`sns2__t0`/`vref__t0`, `cb2__par`/`cb3__par`/`vss__par`) the
  extraction itself uses — this is genuinely simulated, not just committed
  as an unused artifact. Effect on the recorded PVT sweep is small but
  real: max `|Δvref|` across all 45 points vs. the pre-#1280 baseline
  (`records/20260821-160423-42d8348.csv`) is `0.78 mV` — series-R IR drops
  at these currents (tens of µA through tens/hundreds of Ω), not a
  regression; ground/coupling capacitance has zero effect at this `.op`-only
  analysis point (open circuit at DC), included anyway for completeness. See
  "Cold-start invocation" below for the exact regeneration command.

**NOT modelled (disclosed, not silently omitted):**

- **Bipolar and resistor devices are still not extracted here** — but the
  underlying deck capability picture changed since PR #33's original
  README text, so re-verify rather than trust the old claim verbatim:
  `pex_extract_report.json`'s `device_classes` now lists `["nfet", "pfet",
  "resistor", "dantenna", "dpantenna"]` (grown from `["nfet", "pfet"]`),
  and `device_counts` still reads `{"pfet": 3}` — zero resistor/diode
  instances recognised in *this* layout. Two independent, non-conflated
  reasons: **(1) `npn13G2`/`npn13G2l`/`npn13G2v`** (SiGe HBTs) are not
  simply unrecognised yet — `klayout_tools.decks.sg13g2`'s own module
  docstring documents this as a materially harder gap than a missing
  device-class entry (multi-terminal marker-layer disambiguation this
  engine's device model doesn't yet express) — unaffected by this pass,
  still the same deck gap `layout/README.md`'s LVS section documents
  (cause 1). **(2) `rppd`** (the poly resistor flavour `R1`/`R2` use) *does*
  now have a recognizer in `EXTRACTION_DECK.resistors` — but this specific
  layout's `draw_poly_res` (`layout/common.py`) only draws the `PolyRes`
  body and a `Metal1` end pad, never the `pSD`/`SalBlock`/`EXTBlock` marker
  layers `rppd` recognition additionally requires — confirmed directly:
  layer `128/0` (`PolyRes.drawing`) dropped out of both
  `pex_extract_report.json`'s `ignored_layers` entirely in this
  re-extraction (it is no longer outside the deck's connectivity graph),
  yet still contributes zero recognised resistor devices. This is a
  layout-drawing gap in this repo, not a `klayout-tools` gap — not filed
  upstream, and not fixed in this pass (out of scope for issue #37; noted
  for a future layout-regeneration issue). `XQ1`/`XQ2`/`XQ3` (`npn13G2`)
  and `XR1`/`XR2` (`rppd`) are therefore still spliced in **verbatim** from
  `design/netlist/bandgap_core.spice`, wired to the extraction's own real,
  physically-routed net names (`sns1`, `sns2`, `cb2`, `cb3`, `vref`, `vss` —
  all real pins in `pex_extract_report.json`, not invented nodes).
- **PMOS body is a testbench fixture, not an extracted tie.** The
  extraction's own `unbiased_pmos_body_nets` warns all three PMOS bodies
  land on an anonymous, single-terminal net with no DC path (same root
  cause as `layout/README.md`'s LVS cause 2 — the deck declares no
  well/substrate-tap layer at all). This testbench ties each one to `vdd`
  directly, mirroring the schematic's own real body-tied-to-vdd intent —
  disclosed as a fixture bridging a known gap, not a claim about the real
  layout's body connectivity.
- **D/S terminal roles are swapped relative to the schematic, harmlessly.**
  The extraction's native `M` cards read `nd=vdd ng=$9 ns=<leg>`
  (`pex_extract_report.json`'s `devices[].nets`), opposite the schematic's
  `d=<leg> g=fb s=vdd`. Confirmed inconsequential here: every leg's
  `as_um2 == ad_um2` and `ps_um == pd_um` (symmetric drawn geometry), so
  PSP103's terminal formulation is symmetric under this exchange. Stated
  explicitly rather than silently assumed.
- **Self-heating thermal pseudo-nodes** (`spec/porting-plan.md` §7 item 1's
  flagged extraction risk) — not applicable here either way: neither the
  schematic-level nor this PEX testbench enables VBIC self-heating (no
  `dtemp`/`trise` sweep, no thermal network wired), so this run says
  nothing about whether extraction handles it. Left for a future thermal
  testbench, not silently claimed either way.

## Cold-start invocation

Same prerequisites as `sim/core-open-loop-bias/` (ngspice, a resolvable
SG13G2 PDK install, OSDI models via `sim/tools/build-osdi.sh`). Does **not**
require `klt` to run this script — `klt` was used once, offline, to produce
the committed `layout/bandgap_core/bandgap_core.pex.spice` this splices
schematic devices into. Regenerate that input with:

```bash
cd layout/bandgap_core
klt extract --deck sg13g2 --parasitics bandgap_core.gds \
  -o bandgap_core.pex.spice --format json > pex_extract_report.json
```

**Re-verify the deck version before regenerating.** The committed
`pex_extract_report.json`/`bandgap_core.pex.spice` (issue #37, 2026-08-21)
were produced from a `klt` build at `klayout-tools` commit `dab6e5b`
(`provenance.deck.content_hash` in the JSON), not a tagged PyPI release —
`pip install klayout-tools` (`klayout-tools==0.2.0` as of this writing) is
[known-stale relative to `main`](https://github.com/2AMLogic/klayout-tools/issues/1249)
and does not yet carry the Metal1/Metal2 PARASITICS fix
([klayout-tools#1280](https://github.com/2AMLogic/klayout-tools/pull/1280)).
If re-running with a `pip`-installed `klt`, confirm `pex_extract_report.json`'s
`parasitics.r_count`/`c_count` are non-zero before trusting the result — a
stale install will silently reproduce the old zero-RC behavior with
`status: "extracted"` and no error. If the testbench template's hand-spliced
`R`/`C` cards (see `testbench/tb_core_open_loop_bias_pex.spice.tmpl`'s "Wire
parasitics" block) no longer match a freshly regenerated
`bandgap_core.pex.spice`, update that block from the new file's own
non-`M`-card lines — same manual-transcription convention the `w`/`l`/`as`/
`ad`/`ps`/`pd` device geometry above it already uses.

Then:

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/core-open-loop-bias-pex/run_pvt_sweep.sh
```

Same 45-point grid, same output layout (`netlist-snapshots/`, `corners/`,
`records/`) as `sim/core-open-loop-bias/` — see that experiment's README
and `sim/README.md` for the full conventions.

## Cross-bench observation: decision record 0003's margin bug — before/after issue #32

Comparing this experiment's `sns1` (`vbe_q1_v` column) against
[`startup-trip-point-pex`](../startup-trip-point-pex/README.md)'s `vtrip_v`
at matching `(corner, temp, vdd)` points originally reproduced
[decision record 0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md)'s
exact same 4 flagged points — `wcs_125c_{2.97,3.30,3.63}v` and
`sf_125c_3.63v` — with closely matching margins (2-10 mV here vs. the
decision record's own "2-10 mV" figure), while the **layout** was still
drawn at `XMSENSE w=2u` (decision record 0003 only widened the schematic to
`w=10u` — the layout had not yet been regenerated). [Issue
#32](https://github.com/2AMLogic/sg13g2-bandgap/issues/32) has since
regenerated `layout/bandgap_startup.gds` with `XMSENSE` at the matching
`w=10u`; re-running this same cross-bench comparison against the corrected
layout now clears at all 45 points. See
`startup-trip-point-pex/README.md`'s own "Cross-bench observation" section
(updated for issue #32) for the full before/after comparison.
