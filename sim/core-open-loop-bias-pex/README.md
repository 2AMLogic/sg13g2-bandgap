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

**NOT modelled (disclosed, not silently omitted):**

- **Bipolar and resistor devices are not extracted at all.** `klt`'s curated
  `sg13g2` deck recognises only `nfet`/`pfet` (see
  `pex_extract_report.json`'s `device_classes`) — `XQ1`/`XQ2`/`XQ3`
  (`npn13G2`) and `XR1`/`XR2` (`rppd`) are spliced in **verbatim** from
  `design/netlist/bandgap_core.spice`, wired to the extraction's own real,
  physically-routed net names (`sns1`, `sns2`, `cb2`, `cb3`, `vref`, `vss` —
  all real pins in `pex_extract_report.json`, not invented nodes). This is
  the same deck gap `layout/README.md`'s LVS section documents (cause 1),
  filed generically against `klayout-tools` ([klayout-tools#1277](https://github.com/2AMLogic/klayout-tools/issues/1277)).
- **Zero wire resistance and capacitance.** `pex_extract_report.json`'s own
  `warnings` state it plainly: *"'sg13g2' deck's PARASITICS.metals has no
  R/C coefficient for Metal1, Metal2 -- --parasitics reports zero resistance
  and capacitance for that metal level on every net"*. `--parasitics` ran
  without error (`status: "extracted"`), but the deck's own coefficient
  table is empty for both metal levels this layout uses, so `r_count` /
  `c_count` in `pex_extract_report.json`'s `parasitics` block are both `0`.
  This netlist carries real drawn **device** geometry but no real **wire**
  parasitics whatsoever — a materially weaker "PEX" than the name usually
  implies elsewhere in the fleet. **Filed generically against
  `klayout-tools`** ([klayout-tools#1277](https://github.com/2AMLogic/klayout-tools/issues/1277)),
  a deck-content gap, not a design-specific one.
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
