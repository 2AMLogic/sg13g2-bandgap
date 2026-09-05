# core-open-loop-bias-pex

> **Update (issue #173, 2026-09-05) — this experiment's spliced wire
> parasitics are stale, and no new record has been minted yet.** #173 folded
> the long poly-resistor bars in `layout/` into serpentines. No device moved:
> every recognised resistor extracts to the same ohms before and after, and no
> MOS/bipolar `w`/`l`/count changed
> (`measurements/2026-09-resistor-fold/README.md` §4). But the routing got
> much shorter, so the extracted **wire parasitics** in this testbench's own
> input netlist fell substantially — and the template below carries a
> hand-merged *copy* of that block rather than reading the file at run time,
> so it still describes the pre-fold layout. The records here remain valid
> evidence for the layout they were taken against; they are not evidence for
> the layout on `main`. Refreshing the block and re-running is tracked in
> **#176** (which also explains why #173 did not simply do it: the merge rule
> the template uses is not written down anywhere, and the committed block
> already did not reproduce from the committed `.pex.spice` before #173).

Post-layout (PEX) counterpart to [`sim/core-open-loop-bias/`](../core-open-loop-bias/README.md),
issue #14. Same claim, same PVT grid, same open-loop bias/ammeter fixtures —
the difference is where `XM1`/`XM2`/`XM3`'s geometry comes from: the
schematic-level testbench copies `design/netlist/bandgap_core.spice`'s own
`w`/`l` verbatim; this one re-encodes them from
`klt extract --deck sg13g2 --parasitics layout/bandgap_core/bandgap_core.gds`
(committed as `layout/bandgap_core/bandgap_core.pex.spice` +
`pex_extract_report.json`). Read this file before trusting a record here —
it is **not** a pure layout extraction re-simulated as-is.

**Update (issue #59, follow-up correction,
`records/20260825-145023-2ff6265.{md,csv}` — the current record):** the
record minted immediately below (`20260825-143531-648b320`) contradicts
itself: this experiment's `run_pvt_sweep.sh` still echoed the pre-#59
boilerplate "(bipolar/resistor devices are schematic-sourced, not
extracted; …)" into the generated record's **Claim** paragraph, two lines
above the **Devices** paragraph that correctly reports `XR1`/`XR2` as
extracted. The script's boilerplate is fixed and the sweep re-run to mint
a corrected record. Records are append-only, so
`20260825-143531-648b320` stays on disk with its stale sentence — read
`20260825-145023-2ff6265` instead; its `.csv` is **byte-identical** to
`20260825-143531-648b320.csv` (45/45 PASS, every measured value
unchanged), because the fix was prose-only and touched no simulated
quantity. The same stale phrasing was also corrected in both PEX sweep
scripts' own file-header comments (`core-open-loop-bias-pex` and
`startup-trip-point-pex`); `startup-trip-point-pex`'s record boilerplate
never carried it, so its `records/20260825-143537-648b320.{md,csv}`
remains the current startup record.

**Update (issue #59, `records/20260825-143531-648b320.{md,csv}` —
superseded for prose by `20260825-145023-2ff6265` above, identical
numbers):** `XR1`/`XR2` (`rppd`) are now instantiated from the
extracted `R$5`/`R$4` devices instead of spliced verbatim from
`design/netlist/bandgap_core.spice` — see the "NOT modelled" section
below for the full account, including an important correction: the
extraction's own native `R$4 sns2__t0 cb2__t0 vsubs 10751 rppd` card is
**not** literal simulatable ngspice syntax (confirmed by direct testing,
not assumed) — `XR1`/`XR2` below are X-subckt calls to the real `rppd`
PDK subckt, the same re-encoding the PMOS mirror legs already needed.
**Max `|Δvref|` across all 45 points vs. the immediately-preceding
(schematic-resistor) record (`records/20260825-132531-eeea775.csv`) is
`0.951 mV`** (at `bcs_125c_3.63v`) — a real, measured move, not noise;
the resistor bulk terminal moving from the schematic fixture's `sub!`
(shorted to `vss`) to the extraction's real `vsubs` (a ~1 TΩ tie to
ground) changes the bias `rppd`'s body sees, which measurably shifts its
resistance via the `r3_cmc` model's own bias dependence. All 45 points
stay physically sensible (no singular-matrix or dangling-node failures);
the cross-bench margin comparison against `startup-trip-point-pex`
(below) stays resolved at every point.

**Update (issue #56, `records/20260825-132531-eeea775.{md,csv}`):** the
committed PEX evidence had gone stale relative to
`layout/bandgap_core/bandgap_core.gds` — PR #45 added resistor marker
layers (`GatPoly` dog-bone bodies plus `EXTBlock`/`pSD`/`SalBlock`/`nSD`
markers) to the layout, but only the DRC/LVS reports were regenerated
against it at the time, not the PEX leg. Re-extracting and re-running this
sweep against the current GDS: **max `|Δvref|` across all 45 points vs.
the immediately-preceding record (`records/20260821-225609-837323a.csv`)
is `1 µV`** — noise at the CSV's own printed precision, not a real move.
One thing *did* change beyond "small-to-none," though, and is worth
stating plainly rather than folding into a rounding error: PR #45's marker
layers made the `sg13g2` deck's `rppd` recognizer actually match both poly
resistors in this layout for the first time (`device_counts` went from
`{"pfet": 3}` to `{"pfet": 3, "rppd": 2}`) — see the "NOT modelled"
section below for what that does and does not change here. This
testbench's own architecture (which devices are extracted vs.
schematic-spliced) was unchanged by this pass; incorporating the
newly-recognised resistors was tracked as issue #59, now resolved above.

## Dependency on layout/README.md

`layout/bandgap_core/lvs_report.json` still reads `status: "mismatch"`, but
the reason has narrowed to a single permanent cause: three `device.unmatched`
errors on `Q1`/`Q2`/`Q3` (`class: "NPN13G2"`) plus their class-level
`topology` entry, because SiGe HBT recognition was investigated and
**permanently declined upstream** (`klayout-tools`#1242) — the curated
extraction deck cannot see bipolar devices at all. Every MOS and resistor
device now matches (`counts.devices.matched: 8`, was `0`). Per issue #14's
own scope text and its Curator Enhancement, a caveated-but-not-clean layout
is an allowed extraction input — but every caveat that LVS mismatch carries
also applies to the PEX evidence built from the same layout. This README
restates the parts that matter for simulation; `layout/README.md`'s
"DRC/LVS verification" section is the authoritative, fuller account.

Earlier revisions of this file attributed the mismatch to issue #20 "still
open, blocked on `klayout-tools`#1273". Both are now closed —
`klayout-tools`#1273 (well/substrate-tap modelling) was fixed by
`klayout-tools`#1278, and #20 was closed `not planned` once its routing
scope was exhausted — so neither is the live cause any more.

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

**Modelled, from the real routed layout (continued) — resistors (issue #59):**

- **`XR1`/`XR2` (`rppd`) are now instantiated from the extracted `R$5`/
  `R$4` devices**, using real drawn geometry from `pex_extract_report.json`
  (`w_um`/`l_um` — numerically identical to the schematic's own nominal
  `w`/`l` for both resistors: these are fixed-geometry poly resistors, so
  this pass buys no *geometry* correction on its own). **Important
  correction, found by direct testing while implementing issue #59, not
  assumed from `bandgap_core.pex.spice`'s own text:** that file's native
  `R$4 sns2__t0 cb2__t0 vsubs 10751 rppd` card is **not** literal
  simulatable ngspice syntax — a 2-terminal `R` element cannot take a 3rd
  node before its value (ngspice errors `unknown parameter (vsubs)`);
  `rppd` is a PDK subckt (`.subckt rppd 1 2 bn`, in
  `resistors_mod.lib`), the same situation the `pfet`/`nfet` M-cards
  already needed X-subckt re-encoding for (see above). `XR1`/`XR2` are
  therefore X-subckt calls to the real `rppd` subckt, bulk on `vsubs`
  (the extraction's real reported bulk net) instead of the schematic
  fixture's `sub!`. Separately: `pex_extract_report.json`'s own `r_ohm`
  field (`10751`/`66430`, current post-#134-retune extraction — issue
  #141) is klt's own first-order `rsh * l_um / w_um`
  sheet-resistance estimate (confirmed exactly: `260 * 82.7 / 2 = 10751`,
  `260 * 511 / 2 = 66430`) — not the full `r3_cmc` compact-model
  resistance. Simulating the X-subckt form at the same drawn geometry
  computes `~10761 Ω` / `~66257 Ω` (`res_typ`, 27 °C, measured from
  `records/20260829-103823-1d98d88.csv`), within `~0.3%` of
  `r_ohm` — small, and in the expected direction (the compact model adds
  contact/end-effect terms the sheet-resistance formula omits). Disclosed
  here rather than silently reconciled.

**NOT modelled (disclosed, not silently omitted):**

- **Bipolar devices are still not extracted here.** `npn13G2`/`npn13G2l`/
  `npn13G2v` (SiGe HBTs) are not simply unrecognised yet —
  `klayout_tools.decks.sg13g2`'s own module docstring documents this as a
  materially harder gap than a missing device-class entry (multi-terminal
  marker-layer disambiguation this engine's device model doesn't yet
  express) — the same deck gap `layout/README.md`'s LVS section documents
  (cause 1). `XQ1`/`XQ2`/`XQ3` are still spliced in **verbatim** from
  `design/netlist/bandgap_core.spice`, wired to the extraction's own real,
  physically-routed net names (`sns1`, `sns2`, `cb2`, `cb3`, `vref`,
  `vss` — all real pins in `pex_extract_report.json`, not invented
  nodes).
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
the committed `layout/bandgap_core/bandgap_core.pex.spice` this testbench
re-encodes the extracted PMOS/resistor devices from (issue #59) and still
splices the bipolar devices into. Regenerate that input with:

```bash
cd layout/bandgap_core
klt extract --deck sg13g2 --parasitics bandgap_core.gds \
  -o bandgap_core.pex.spice --format json > pex_extract_report.json
```

**Re-verify the deck version before regenerating.** The committed
`pex_extract_report.json`/`bandgap_core.pex.spice` (issue #56, 2026-08-25)
record `provenance.klt_version: "0.3.0"` — that is the only `klt` version
string the JSON persists, and it is what a re-run should be compared
against. (The producing environment's own `klt --version` banner printed the
fuller `klt 0.3.0+g71cbae53b7e6.dirty`, but the extractor does not write that
build suffix into the report, so it is *not* checkable from the committed
evidence — do not treat it as recorded provenance.) Separately, the same JSON
records `provenance.deck.released: true`, the first record here from a
tagged/released **deck** build rather than a pre-release dev commit; that is
a property of the DRC/LVS deck, not of the `klt` binary.
`pip install klayout-tools` (`klayout-tools==0.2.0` as of this writing) is
[known-stale relative to `main`](https://github.com/2AMLogic/klayout-tools/issues/1249)
and does not yet carry the Metal1/Metal2 PARASITICS fix
([klayout-tools#1280](https://github.com/2AMLogic/klayout-tools/pull/1280))
nor the resistor-recognition marker layers PR #45 added the layout side of.
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
