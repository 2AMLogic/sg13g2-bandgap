# closed-loop-vref-pvt-pex

> ## Two decisions taken by issue #275, before this experiment's re-run
>
> This experiment is one of the five whose PEX evidence is still waived against
> the **pre-trim** geometry in `sim/evidence-freshness-waivers.json`. #272
> delivered the trim-bearing re-layout and re-extraction; #275 settled the two
> questions that had to be answered before the 45-point post-layout `vref` grid DR-0011's nominal derives from could be
> re-run against it, and this section records both — the re-run itself is
> **#278**, blocked on **#277**. Neither decision changes any number in the
> records already committed here; they change how the next record is produced
> and how CI judges it. Disclosed here rather than silently reconciled, per this
> repo's convention.
>
> **1. The harness is `klt sim`, not `run_pvt_sweep.sh`** (option 1 of the two
> #275 offered). The dispatch hosts this repo's agents run on forbid
> hand-looping `ngspice -b` over a corner grid and direct multi-corner work to
> `klt sim`'s batch backend. The next record here will therefore be minted by
> `sim/harness/klt_sim_evidence.py` from a `klt sim` report rather than by this
> directory's `run_pvt_sweep.sh`, and its `- **Harness**:` field will say so.
> `run_pvt_sweep.sh` stays on disk and stays correct — it is how every record
> currently in `records/` was produced, and it remains the right entry point on
> a workstation. Read [`sim/harness/README.md`](../harness/README.md) for the
> decision, the three pieces of the harness, the one-corner anchor that proves
> it (3 µV against a committed record), and precisely what still blocks the
> grids: the batch fleet's runner image carries no `ihp-sg13g2` PDK and no
> compiled-OSDI step (#277).
>
> **2. A mask-option PEX DUT has no `trim_code`, and D2 now knows that**
> (disposition (b) of the three #275 sketched). The layout realises **one** trim
> code (128) in metal, so a faithful post-layout netlist of it has no
> `trim_code` parameter, no `XXTRIM` instance and no `RS0`-`RS7` cards: the
> closed straps are real metal (wire resistance, worth ~0.3 mV here — about an
> eighth of the 2.443 mV trim step) and the open strap is simply absent.
> Compared against `design/netlist/bandgap_core.spice`'s *unresolved* instance
> set, such a snapshot would read as `<absent>` on 264 instances and fail the
> D2 freshness rule — even though the design did not change, only its
> representation did.
>
> `.github/scripts/check_evidence_formats.py` now **resolves** the mask option
> before comparing: the behavioural `RS<bit>` strap cards and the `XXTRIM`
> subcircuit call are excluded from the DUT signature, while the ladder's own
> 255 `rppd` units stay in it and must still match device-for-device. That is
> the same convention `layout/lvs_reference.py`'s `convert_with_metal_options`
> already applies to the LVS reference, so both sides of the compare agree on
> what a mask-option netlist is. The code-fixed PEX template this experiment
> will use must therefore name its ladder units `XRU1`-`XRU255`, the schematic's
> own names, because that is what D2 keys on.
>
> The honest cost, stated rather than left implicit: with the strap cards out of
> the expected set, **D2 no longer notices which code a snapshot realises** —
> the 255 units are geometrically identical and D2 compares no node names. That
> axis is guarded by LVS instead, where it belongs: `convert_with_metal_options`
> reads the realised code from the same `.param trim_code` default the layout's
> own `TRIM_CODE` must agree with, so a code mismatch surfaces as an LVS
> failure. Rejected alternative (#275's disposition (a)): keeping a
> `.subckt bandgap_trim` shell with the behavioural straps inside the PEX
> template would have satisfied D2 unchanged, but it would make this bench model
> a code the layout does not realise whenever `trim_code != 128` — a trap set
> for the next reader.

Post-layout (PEX) counterpart to [`sim/closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md),
issue #186 (a direct follow-on to issue #187, which committed the extracted
`layout/bandgap_top/bandgap_top.pex.spice` this experiment reads). Same
claim, same co-simulated `bandgap_core` + `bandgap_amp` + `bandgap_startup`
closed-loop topology, same 45-point PVT grid — the difference is where
every MOS/resistor device's geometry (and every wire's parasitic R/C) comes
from: the schematic-level testbench copies `design/netlist/bandgap_core.spice`
/ `bandgap_amp.spice` / `bandgap_startup.spice` verbatim; this one re-encodes
17 MOS + 3 resistor devices from
`klt extract --deck sg13g2 --parasitics layout/bandgap_top/bandgap_top.gds`
(committed as `layout/bandgap_top/bandgap_top.pex.spice` +
`pex_extract_report.json`). Read this file before trusting a record here —
it is **not** a pure layout extraction re-simulated as-is.

**This is the first closed-loop PEX experiment in this tree.**
`sim/core-open-loop-bias-pex/` and `sim/startup-trip-point-pex/` (issue #14)
are both leaf-cell, open-loop benches — `sim/README.md`'s own "Testbenches
landed so far" entry for that pair states plainly that they say nothing
about the assembled, closed-loop block. This experiment is what closes that
gap, now that `layout/bandgap_top/` and `layout/bandgap_amp/` carry their
own committed extractions (issue #187).

## Dependency on layout/README.md

`layout/bandgap_top/lvs_report.json` reads `status: "mismatch"`, narrowed to
a single permanent cause: three `device.unmatched` errors on `Q1`/`Q2`/`Q3`
(`class: "NPN13G2"`) plus their class-level `topology` entry, because SiGe
HBT recognition is **permanently declined upstream** (`klayout-tools`#1242)
— the curated extraction deck cannot see bipolar devices at all. Every MOS
and resistor device matches (`counts.devices.matched: 20`, of `23`
reference). `layout/README.md`'s "DRC/LVS verification" section is the
authoritative, fuller account; this README restates only what matters for
simulation.

## What this does and does not model

**Modelled, from the real routed, ASSEMBLED layout:**

- All 17 MOS devices (`XM1`/`XM2A`/`XM2B`/`XM3A`/`XM3B`/`XM3C` — the core
  mirror; `XMTAIL`/`XMP1`-`XMP4`/`XMN1`-`XMN4` — the amplifier;
  `XMSENSE`/`XMKFB` — the startup circuit) and both resistors
  (`XR1`/`XR2` — the core's `rppd` legs) plus the startup pull-up
  (`XRPU` — `rhigh`), all with real drawn `w`/`l`/`as`/`ad`/`ps`/`pd`
  (MOS) or `w`/`l` (resistors) taken directly from
  `pex_extract_report.json`'s `devices[]` block. Same PSP103.6/r3_cmc
  compact models the schematic-level testbench uses — real drawn geometry
  through the real compact model, not an ideal-primitive substitution.
  Instance names match `design/netlist/bandgap_core.spice` /
  `bandgap_amp.spice` / `bandgap_startup.spice` one-for-one, confirmed by
  reading `bandgap_top.pex.spice`'s own `M$1`-`M$17`/`R$18`-`R$20` cards
  and matching each one's drawn geometry against the schematic device it
  replaces (not assumed from card order) — this is also what lets
  `.github/scripts/check_evidence_formats.py`'s DUT-freshness check compare
  this bench's snapshots against all three `design/netlist/*.spice` files
  directly (see `sim/README.md` "DUT freshness"; that script's
  `dut_signature()` docstring explains why the extraction's *extra*
  `as`/`ad`/`ps`/`pd` params don't count as a mismatch).
- **Real body/well ties, not a testbench fixture** — unlike
  `sim/core-open-loop-bias-pex` (whose leaf-cell layout left PMOS bodies on
  an anonymous single-terminal net at extraction time), every device here
  reports a genuine, distinct body terminal on the real, multi-terminal
  `VDD` (PMOS) or `VSS` (NMOS) net, each through its own wire-parasitic hub
  leg — instantiated exactly as extracted, no override needed.
- **Real wire resistance and capacitance for the whole assembled block.**
  `pex_extract_report.json`'s `parasitics` block reports `r_count: 77,
  c_count: 13, cc_count: 22` (`total_resistance_ohm: 869.74`,
  `total_capacitance_ff: 261.13`) — the largest wire-parasitic set of any
  experiment in this tree, being the whole block rather than one leaf cell.
  Every card is spliced into
  `testbench/tb_closed_loop_vref_pex.spice.tmpl` verbatim (after the
  merged-net-label rename below), wired through the same per-terminal hub
  node names the extraction itself uses.
- **Merged-net labels, named explicitly.** `pex_extract_report.json` reports
  three top-level pins as merged labels — `FB|OUT` (10 device terminals),
  `IN_N|SNS1` (3), `IN_P|SNS2` (4) — because `design/bandgap_top.sch` ties
  `bandgap_amp`'s `out`/`in_n`/`in_p` pins directly onto
  `bandgap_core`/`bandgap_startup`'s `fb`/`sns1`/`sns2`
  (`design/netlist/bandgap_top.spice`'s own
  `Xx2 sns2 sns1 vss fb vdd bandgap_amp` instance line) — intended top-level
  ties, not shorts. This experiment names them `fb`, `sns1`, `sns2`
  (matching every schematic-level closed-loop testbench's own net names)
  rather than embedding the extraction's escaped `FB\x7cOUT` /
  `IN_N\x7cSNS1` / `IN_P\x7cSNS2` forms, per issue #186's own guidance.
  `sim/tools/dump_pex_wire_parasitics.py`'s raw output still uses the
  escaped forms — the template's header documents the rename mapping so a
  future refresh does not have to re-derive it.

**NOT modelled (disclosed, not silently omitted):**

- **Bipolar devices are still not extracted.** `XQ1`/`XQ2`/`XQ3`
  (`npn13G2`) are spliced in verbatim from
  `design/netlist/bandgap_core.spice`, wired to the extraction's own real,
  physically-routed net names (`sns1`, `cb2`, `cb3`, `vss`) — not invented
  nodes. Same permanent upstream gap `sim/core-open-loop-bias-pex`'s README
  documents (`klayout-tools`#1242).
- **D/S terminal roles may be swapped relative to the schematic, harmlessly**
  for the same reason `sim/core-open-loop-bias-pex`'s README gives: every
  device's `as_um2 == ad_um2` and `ps_um == pd_um` (symmetric drawn
  geometry), so PSP103's terminal formulation is symmetric under the
  exchange.
- **Self-heating thermal pseudo-nodes** — not applicable here either way,
  same as every other testbench in this tree (no `dtemp`/`trise` sweep, no
  thermal network wired).

## `klt sim` harness migration (issue #278)

This experiment's grid now runs through the `klt sim` batch harness
(`sim/harness/README.md`, the #275 decision) instead of the
`run_pvt_sweep.sh` shell loop; the loop script itself remains for history
and cold-start reference but is no longer the evidence-producing path on
the dispatch hosts (their operating rules direct multi-corner work to
`klt sim`'s batch backend).

```bash
sim/closed-loop-vref-pvt-pex/run_klt_sim.sh --sanity   # one local corner, vs the sanity anchor
sim/closed-loop-vref-pvt-pex/run_klt_sim.sh --batch    # the PVT grid, on the fleet (resumable)
sim/closed-loop-vref-pvt-pex/run_klt_sim.sh --record   # mint the record from the merged report
```

What changed about how this experiment's evidence is minted:

- **The DUT half is generated, not transcribed.**
  `sim/tools/gen_pex_netlist_body.py --cell top` regenerates the whole
  device + wire-parasitic body from the committed extraction and design
  netlists on every run (hub tags read off each device card, the merged
  tap net renamed to `tn0`, the 255 ladder units under their `XRU<n>`
  names for D2, the three subckts are flattened through the design netlist's own instance lines, and the `FB|OUT`/`IN_N|SNS1`/`IN_P|SNS2` merged label nets are renamed to their schematic names `fb`/`sns1`/`sns2`). The hand-transcribed
  `testbench/*.spice.tmpl` files remain for history; the bench body
  (`testbench/*.body.spice.tmpl`) now carries only fixtures and includes
  the generated DUT.
- **The grid runs as per-process x supply `klt sim --backend batch` requests**
  (one fleet job each), merged deterministically
  (`sim/harness/merge_batch_shards.py`) before the adapter mints one
  record: the runner image's klt 0.5.0 carries one model library and
  SG13G2's corner set spans three per-device-family files
  (klayout-tools#2668), so the process axis cannot vary within one
  request. the ramp source that is this bench's convergence path cannot survive `alter`, so the PWL target is baked into per-supply body variants -- 15 requests of 3 temperatures each.
- **Reported precision is 6 significant figures** (`.meas`'s fixed print
  format; `sim/harness/README.md` "Reported precision" owns the
  disposition and its arithmetic against every live claim).
  The resident-vector `.save` card the 3 ms transient requires (issue #278 work item 3) disables `par()` in `.meas find` (verified on ngspice 46), so the two derived columns (`dvsns_v`, `vref_settle_delta_v`) are formed by the enrichment pass from the reported operands -- the same practice this experiment's committed records already used for their derived columns.
- **The per-point verdict is applied by the enrichment pass**
  (`sim/harness/enrich_pvt_report.py`) over the merged report, not by the loop script's inline
  checks: startup released (det <= 0.2*vdd, |i_mkfb| <= 50 nA), loop closed (|dvsns| <= 20 mV), fb not railed, settled (|vref(3ms)-vref(2ms)| <= 1 mV) -- the same four criteria and constants `sim/lib/pvt_verdict_common.sh`'s `pvt_closed_loop_verdict` encodes.
- The record quadruple layout (`records/<id>.{{md,csv}}` +
  `corners/<id>/*.log` + `netlist-snapshots/<id>/*.spice`) is unchanged --
  `sim/harness/klt_sim_evidence.py` mints it from the report, and the
  netlist snapshots now inline the generated DUT through the same include
  splicing the adapter always did.

## Cold-start invocation

Same prerequisites as `sim/closed-loop-vref-pvt/` (ngspice, a resolvable
SG13G2 PDK install, OSDI models via `sim/tools/build-osdi.sh`). Does **not**
require `klt` to run this script — `klt` was used once, offline (issue
#187), to produce the committed `layout/bandgap_top/bandgap_top.pex.spice`
this testbench re-encodes the extracted devices from and still splices the
bipolar devices into. Regenerate that input with:

```bash
cd layout/bandgap_top
klt extract --deck sg13g2 --parasitics bandgap_top.gds \
  -o bandgap_top.pex.spice --format json > pex_extract_report.json
```

If re-running, confirm `pex_extract_report.json`'s `provenance.klt_version`
and `parasitics.r_count`/`c_count`/`cc_count` still match the values quoted
above before trusting a refreshed template — same staleness caveat every
other PEX experiment's README in this tree carries. If the extraction
changes, regenerate this template's device cards and wire-parasitics block
from the new file with:

```bash
python3 sim/tools/dump_pex_wire_parasitics.py --devices-only layout/bandgap_top/bandgap_top.pex.spice
python3 sim/tools/dump_pex_wire_parasitics.py --wires-only layout/bandgap_top/bandgap_top.pex.spice
```

then reapply the `FB|OUT`/`IN_N|SNS1`/`IN_P|SNS2` -> `fb`/`sns1`/`sns2`
rename and the per-device `ng=1`/`m=1`/`b=0` restoration the template's own
header documents (both hand steps — the dump tool intentionally does not
try to infer testbench-specific re-encoding decisions, see its own module
docstring).

Then:

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh
sim/closed-loop-vref-pvt-pex/run_pvt_sweep.sh
```

Same 45-point grid, same output layout (`netlist-snapshots/`, `corners/`,
`records/`) as `sim/closed-loop-vref-pvt/` — see that experiment's README
and `sim/README.md` for the full conventions. This script additionally
writes a `records/<id>-vs-schematic.csv` cross-bench delta against
`sim/closed-loop-vref-pvt/`'s own newest record.

## Cross-bench comparison against sim/closed-loop-vref-pvt (schematic-level)

The current record (`records/20260905-114438-8abe2aa.md`) compares against
`sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.csv`: **max
`|Δvref|` across all 45 points is `1.67 mV`** (at `wcs_-40c_3.63v`), out of
a ~1.05 V `vref` — well under 0.2%. Checked at all 45 points, not just the
max: every single point's `vref` moves in the SAME direction (up, PEX >
schematic — see `records/20260905-114438-8abe2aa-vs-schematic.csv`), the
same sign the leaf-level `core-open-loop-bias-pex` wire-parasitics finding
reports (series-R IR drops at these currents, not a regression). No point
moved the other way; no exception to call out. `startup-release`/
`loop-closure`/`not-railed`/settledness verdicts agree at all 45 points
(PASS/PASS throughout).

The informal endpoint-method TC (`records/20260905-114438-8abe2aa-tc.csv`)
keeps the SAME SIGN as `sim/closed-loop-vref-pvt`'s own current TC record
at every one of the 15 corner/supply groups (negative for `typ`/`bcs`/`sf`/
`fs`, positive for `wcs`) — but the magnitude moves, sometimes
substantially in relative terms: e.g. `typ`/2.97V goes from `-0.636` to
`-3.753` ppm/°C, `bcs`/3.63V from `-14.422` to `-17.591`, `wcs`/2.97V from
`18.107` to `15.333`. This is an artifact of the endpoint method applied to
an already near-flat TC curve (this design has no trim network yet, so a
few ppm/°C is well within the sub-mV `vref` shifts these PEX wire
parasitics themselves introduce — see the per-point `Δvref` above), not a
new finding about the circuit's physics. Neither this nor the `vref` shift
above is a claim against `spec/porting-plan.md` §6's still-unratified
vref/TC target row (#125).
