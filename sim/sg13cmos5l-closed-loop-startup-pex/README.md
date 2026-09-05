# sg13cmos5l-closed-loop-startup-pex

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

Post-layout (PEX) counterpart to
[`sim/sg13cmos5l-closed-loop-startup/`](../sg13cmos5l-closed-loop-startup/README.md),
issue #84 (the SG13CMOS5L port's own post-layout PVT gap, the last item
against parent issue #63's Acceptance Criteria after #81 landed the
assembled `layout/sg13cmos5l-bandgap_top/` GDS). Same claim, same PVT grid,
same closed-loop-startup pass criteria — the difference is where every MOS
device's `w`/`l` and junction `as`/`ad`/`ps`/`pd` come from: the
schematic-level testbench copies `design/sg13cmos5l/netlist/*.spice`'s own
values verbatim (with junction geometry defaulted to zero); this one
re-encodes them from
`klt extract --deck sg13cmos5l layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.gds`
(committed as
`layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.pex.spice` +
`pex_extract_report.json`). **Read this file before trusting a record
here** — it is not a pure layout extraction re-simulated as-is, and unlike
the SG13G2 PEX precedent, **no wire (metal) parasitics are modelled at
all** — see "What this does and does not model" below.

**Scoping choice (per issue #84's Implementation Guidance, option 2 —
top-level PEX):** the already-assembled `layout/sg13cmos5l-bandgap_top/`
GDS is extracted once, and the result feeds one
`sg13cmos5l-closed-loop-startup-pex` testbench, reusing
`sg13cmos5l-closed-loop-startup`'s existing PVT grid and pass/fail criteria
(startup released, loop closed, not railed) — rather than three separate
per-leaf-cell PEX testbenches (option 1, the `core-open-loop-bias-pex`/
`startup-trip-point-pex` shape). This mirrors the layout side's own choice
in issue #81 (one assembled GDS, not three separately-extracted leaf
netlists re-stitched at sim time).

## Dependency on layout/README.md

`layout/sg13cmos5l-bandgap_top/lvs_report.json` reads `status: "mismatch"`
(51 findings, 49 error-severity) as of this writing — fully attributed to
four already-documented, already-filed deck gaps (no bipolar class, no
resistor class with a body-shorting side effect, no HV MOS flavour, no
well/substrate tap), not an unexplained residue. Per issue #84's own
dependency text (issue #81, closed) and the same precedent
`sim/core-open-loop-bias-pex/README.md` established for the SG13G2 side, a
caveated-but-fully-attributed layout is an allowed extraction input — every
caveat `layout/README.md`'s "SG13CMOS5L: LVS" section documents also applies
to the PEX evidence built from the same layout. This README restates the
parts that matter for simulation; `layout/README.md`'s own section is the
authoritative, fuller account.

## What this does and does not model

**Modelled, from the real routed layout:**

- All 14 MOS devices (`XM1`/`XM2`/`XM3` in the core, `XMTAIL`/`XMP1`-`XMP4`/
  `XMN1`-`XMN4` in the amp, `XMSENSE`/`XMKFB` in the startup circuit) — real
  drawn `w`/`l`, **plus** real drawn junction geometry
  (`as`/`ad`/`ps`/`pd`), taken directly from `pex_extract_report.json`'s
  `devices[]` block, matching `device_counts: {"nfet": 6, "pfet": 8}`
  exactly (the sum of each leaf's own MOS devices — same accounting
  `layout/README.md`'s "Cell: `sg13cmos5l-bandgap_top`" section already
  verified for the assembly). Every device's `w`/`l` is numerically
  identical to the schematic's own nominal value (confirmed device-by-device
  in the testbench template's own inline comments) — the real, new
  information this pass adds is the junction area/perimeter, which the
  schematic-level testbench omits entirely (`sg13_hv_pmos`/`sg13_hv_nmos`'s
  own subckt default is `as=ad=ps=pd=0` — see
  `libs.tech/ngspice/models/sg13g2_moshv_mod.lib`). Same PSP103 compact
  model as the schematic-level testbench — real drawn geometry through the
  real compact model, not an ideal-primitive substitution, same as the
  SG13G2 precedent's own claim.
- Every extracted device's `as_um2 == ad_um2` and `ps_um == pd_um`
  (confirmed directly in `pex_extract_report.json` — symmetric drawn
  source/drain geometry throughout this layout), so the extraction's own
  drain/source terminal-order divergence from the schematic (KLayout's
  `M...pfet`/`M...nfet` cards order terminals by its own connectivity walk,
  not the schematic's `d`/`g`/`s` convention) is electrically
  inconsequential here — disclosed, not silently assumed, mirroring the
  SG13G2 precedent's own equivalent finding.

**NOT modelled (disclosed, not silently omitted):**

- **No wire (metal) parasitics anywhere in this netlist.** This is the one
  material way this experiment is *weaker* than its SG13G2 counterpart
  (`sim/core-open-loop-bias-pex`, which does wire in real Metal1/Metal2
  R/C as of issue #37). Not a scope choice made here — `klt extract --deck
  sg13cmos5l --parasitics <file>.gds` fails outright:

  ```
  {"schema_version": 1, "error": {"command": "extract", "message":
  "unknown deck 'sg13cmos5l' (available: gf180mcu, sg13g2, sky130)"}}
  ```

  Root cause, found and filed this pass:
  `klayout_tools.decks.__init__._parasitics_registry()` hardcodes its
  deck import/dict to three decks (`sky130`, `gf180mcu`, `sg13g2`) and
  never imports `sg13cmos5l` — every *other* per-deck lookup table in that
  same file (extraction deck, layer names, unmodelled-voltage-marker list,
  nominal DBU) already includes `sg13cmos5l`; only this one function's
  import list was never updated when the `sg13cmos5l` deck module was
  added. This contradicts `decks/sg13cmos5l.py`'s own module comment
  directly above its `PARASITICS = ParasiticsDeck()` declaration, which
  documents that `--parasitics` against this deck is *supposed* to succeed
  today and just report zero R/C for every net (the same graceful
  degradation every other deck with no curated sheet-resistance table
  already gets) — not fail outright. Filed generically as
  [klayout-tools#1440](https://github.com/2AMLogic/klayout-tools/issues/1440),
  per `CLAUDE.md`'s friction protocol, rather than worked around by
  fabricating R/C values this repo cannot back with a real extraction.
  Even once that registry gap is fixed, the module's own comment says the
  best case is *still* zero R/C for every net (no curated
  sheet-resistance/parallel-plate-capacitance table exists yet for this
  MOS-only starter deck) — so this repo used the one extraction mode that
  does work (`klt extract --deck sg13cmos5l`, no `--parasitics`, which
  reports the real device geometry this experiment's own MOS devices use)
  rather than block on the registry fix. Every net in this testbench is
  therefore the same idealized zero-impedance node the schematic-level
  `sim/sg13cmos5l-closed-loop-startup` testbench already uses — no IR-drop
  or coupling-capacitance claim is made anywhere here.
- **Bipolar and resistor devices are still not extracted here** — the
  `sg13cmos5l` deck's `device_classes` still reads `["nfet", "pfet"]` only
  (`klt deck info --deck sg13cmos5l`), unchanged since issue #81. `XQ1`/
  `XQ2`/`XQ3` (`pnpMPA`) and `XR1`/`XR2` (`rppd`, core) are spliced in
  **verbatim** from `design/sg13cmos5l/netlist/bandgap_core.spice`; `XRPU`
  (`rhigh`, startup) is spliced in verbatim from
  `design/sg13cmos5l/netlist/bandgap_startup.spice` — all wired to the
  extraction's own real, physically-routed net names (`sns1`, `sns2`,
  `vref`, `vdd`, `vss`, `fb`, `det` — all real pins in
  `pex_extract_report.json`, not invented nodes). Already-filed, unchanged
  by this pass: [klayout-tools#1242](https://github.com/2AMLogic/klayout-tools/issues/1242)
  (bipolar) and [klayout-tools#1415](https://github.com/2AMLogic/klayout-tools/issues/1415)
  (resistor).
- **PMOS body is a testbench fixture, not an extracted tie.** The
  extraction's own `unbiased_pmos_body_nets` warns all 8 PMOS bodies land
  on an anonymous, single-terminal net with no DC path (no drawn
  well/substrate-tap layer at all —
  [klayout-tools#1414](https://github.com/2AMLogic/klayout-tools/issues/1414),
  already filed, unchanged). This testbench ties each one to `vdd`
  directly, mirroring the schematic's own real body-tied-to-vdd intent —
  disclosed as a fixture bridging a known gap, not a claim about the real
  layout's body connectivity.
- **No HV/LV MOS-flavour distinction.** The deck extracts every MOS device
  (regardless of the `ThickGateOx` marker every device here actually
  carries) as a generic `nfet`/`pfet` class — this testbench still
  re-encodes each one as the real `sg13_hv_pmos`/`sg13_hv_nmos` compact
  model per schematic knowledge (the extraction's own native class name is
  a placeholder, not a real PDK subckt reference), so this is a testbench
  choice informed by the schematic, not something the extraction itself
  confirms. Already-filed:
  [klayout-tools#1416](https://github.com/2AMLogic/klayout-tools/issues/1416).
- **XMSENSE's `w=10u` is the layout's own drawn value**, not read live from
  `design/sg13cmos5l/netlist/bandgap_startup.spice` the way the pre-layout
  `sg13cmos5l-closed-loop-startup` testbench does — a post-layout claim
  must reflect the physical GDS. It happens to equal the schematic's
  current value (post decision record 0003 / issue #32's SG13G2
  regeneration and issue #74's matching CMOS5L layout draw), but if a
  future schematic-only resize diverges from this without a layout
  regeneration, this PEX record would silently go stale exactly the way
  issue #37/#56 describe for the SG13G2 side — the fix is to re-run "Cold-start
  invocation" below against the regenerated GDS, not to hand-edit the
  template's hardcoded value.
- **Self-heating thermal pseudo-nodes** — not applicable here either way:
  neither the schematic-level nor this PEX testbench enables any
  thermal-network wiring, so this run says nothing about whether extraction
  handles it. Left for a future thermal testbench, not silently claimed
  either way (same disclosure the SG13G2 precedent carries).

## Cold-start invocation

Same prerequisites as `sim/sg13cmos5l-closed-loop-startup/` (ngspice, a
resolvable `PDK_ROOT` containing both `ihp-sg13cmos5l/` and a sibling
`ihp-sg13g2/` — see `sim/pdk-sg13cmos5l.json`
`"sibling_checkout_requirement"`). Does **not** require `klt` to run this
script — `klt` was used once, offline, to produce the committed
`layout/sg13cmos5l-bandgap_top/sg13cmos5l-bandgap_top.pex.spice` this
splices schematic devices into. Regenerate that input with:

```bash
cd layout/sg13cmos5l-bandgap_top
klt extract --deck sg13cmos5l sg13cmos5l-bandgap_top.gds \
  -o sg13cmos5l-bandgap_top.pex.spice --format json > pex_extract_report.json
```

(No `--parasitics` — see "What this does and does not model" above for
why; a re-attempt is worth trying first, in case
[klayout-tools#1440](https://github.com/2AMLogic/klayout-tools/issues/1440)
has since been fixed upstream — if `--parasitics` starts succeeding with a
non-`unknown deck` result, re-derive whether it reports non-zero R/C before
assuming this experiment should be extended to model wire parasitics.)

**Re-verify the deck version before regenerating.** The committed
`pex_extract_report.json`/`sg13cmos5l-bandgap_top.pex.spice` (issue #84,
2026-08-26) were produced from a `klt` build at content hash
`sha256:9a4e18f2fd7a0d39d02abc220141dd5c300158e2540cd19f2f2ea9151f965b80`
(`provenance.deck.content_hash` in the JSON — `klt deck info --deck
sg13cmos5l`), `klt` version `0.3.0` (`klt --version` reported
`0.3.0+g3f98b441bf2f` in this environment). If device geometry in a freshly
regenerated `sg13cmos5l-bandgap_top.pex.spice` no longer matches the
testbench template's hand-transcribed `w`/`l`/`as`/`ad`/`ps`/`pd` values
(see the template's own inline "Extraction provenance" comments naming
which `pex_extract_report.json` device each schematic instance name maps
to), update the template from the new file — same manual-transcription
convention `core-open-loop-bias-pex`'s own README documents.

Then:

```bash
export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
                                         # AND a sibling ihp-sg13g2/
export PDK=ihp-sg13cmos5l
sim/sg13cmos5l-closed-loop-startup-pex/run_pvt_sweep.sh
```

Same 45-point grid, same output layout (`netlist-snapshots/`, `corners/`,
`records/`) as `sim/sg13cmos5l-closed-loop-startup/` — see that
experiment's README and `sim/README.md` for the full conventions.

## Cross-check against the pre-layout precedent

Since every MOS device's `w`/`l` is numerically unchanged from the
schematic (only junction geometry is added, and this testbench adds no
wire parasitics), this record's per-point results are expected to closely
track `sim/sg13cmos5l-closed-loop-startup`'s own pre-layout results at
matching `(corner, temp, vdd)` points — confirmed directly, not merely
assumed: at `typ`/27 °C/3.30 V, this experiment's own record reports
`fb=2.49710 V`, `det=4.18834 mV`, `i(XMKFB)=2.49705 nA`, matching the
pre-layout record's `fb=2.49710 V`, `det=4.18836 mV`,
`i(XMKFB)=2.49707 nA` to 5-6 significant figures — the small residual is
consistent with the added junction capacitance's negligible effect on a
transient that has fully settled by the `t=2ms` measurement point, not a
splicing error. This is the expected outcome given what changed (junction
geometry only, no wire RC) and confirms the device mapping in the
testbench template is correct.
