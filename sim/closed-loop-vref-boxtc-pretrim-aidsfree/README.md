# closed-loop-vref-boxtc-pretrim-aidsfree

A focused A/B (issue #269), not a full PVT grid: does removing the
`rshunt=1e9`/`gmin=1e-9` convergence aids, **by itself, on the pre-trim
core**, explain the box-method TC jump #229 measured on the trim-bearing
core (19.8/20.1 ppm/°C aided → 38.6/45.7 ppm/°C aids-free), or does the
255-unit trim ladder?

## Why this experiment exists

`sim/closed-loop-vref-boxtc-trim/` (#229) measures the **trim-bearing**
core without the aids and finds box TC 20.2–45.7 ppm/°C across the near-band
grid — 2× the ratified `< 20 ppm/°C` stretch at four of five corners. Two
changes happened at once between that record and the pre-trim, **aided**
`sim/closed-loop-vref-pvt-boxtc/` record (`20260921-194249-77820fc`,
19.8/20.1 ppm/°C): the aids were dropped, *and* the monolithic R1 became a
255-unit ladder (#264's trim-bearing DUT refresh re-pointed
`closed-loop-vref-pvt-boxtc/`'s own template at the ladder with the aids
already dropped, so that bench's *current* template can no longer serve as
the "pre-trim, aided" baseline a fresh run would need — see "Why a
historical DUT" below). Issue #269 exists to separate those two confounded
causes. `closed-loop-vref-boxtc-trim/README.md`'s own "Solver options"
section already measured one anecdotal data point for the aids' effect on
the pre-trim circuit (2.2 mV at 125 °C) but never turned it into a
box-method TC delta across a temperature grid — this experiment does that.

## Why a historical DUT

`sim/closed-loop-vref-pvt-boxtc/testbench/tb_closed_loop_vref_boxtc.spice.tmpl`
on `main` today is **already** the trim-bearing, aids-free template (issue
#264 re-pointed it, alongside ten other schematic-DUT benches, at the
trim-bearing core with the aids dropped — its own committed `records/`
directory is simply stale relative to that template change, tracked by
#273). So there is no live template left in this tree that is "pre-trim,
aided" — the only committed description of that DUT is the git history
behind `20260921-194249-77820fc`'s own "Netlist provenance" field (core
`design/netlist/bandgap_core.spice` at git blob `d83f7c4`) plus the
historical template git blob `ebd0c02`. This experiment's own
`testbench/tb_closed_loop_vref_boxtc_pretrim_ab.spice.tmpl` reconstructs
that exact historical DUT verbatim (monolithic `XR1 vref cb3 sub! rppd
w=2u l=511u`, no `XXTRIM`), with the convergence aids made a template axis
(`@@AIDS_OPTIONS@@`) rather than hardcoded, so one template drives both
legs of the A/B.

Because this DUT deliberately does **not** match this worktree's current
(trim-bearing) `design/netlist/bandgap_core.spice`, this experiment's own
records intentionally avoid citing that live path as their provenance (see
each record's own "Netlist provenance" field) — `check_evidence_formats.py`'s
D2 freshness check looks for a committed `design/**/*.spice` path named in a
record's own text and compares device sets against it; a record that names
none is reported as "DUT freshness not checked" (a note), which is the
correct, honest outcome here: this is deliberately historical evidence, not
a claim about today's DUT.

## Why not `klt sim`, and why not a `run_pvt_sweep.sh` grid

This dispatch host's own rules forbid hand-looping `ngspice -b` over a
corner grid and direct multi-corner work to `klt sim`'s batch backend
instead. Both alternatives were checked and rejected for this specific A/B,
not assumed away:

1. **`klt sim --backend batch` cannot run this PDK's grids at all today.**
   The batch fleet's AMI bakes only `sky130A`/`gf180mcuD`, with no
   `ihp-sg13g2` and no OSDI compile step — documented already in
   `sim/harness/README.md` ("What still blocks the grids") and tracked as
   issue #277 (`loom:operator-only`, infra) / #278 (the grid re-runs that
   depend on it). This is a pre-existing, independently-confirmed blocker,
   not something this issue's own work triggered.
2. **Separately, `klt sim`'s per-corner supply override cannot drive this
   testbench's ramp fixture correctly even on a backend that could reach
   this PDK.** `klayout_tools.sim._write_corner_deck` overrides a supply
   with a plain `alter <name>=<value>` card. Verified directly against
   ngspice 46 during this issue's own investigation (a two-line scratch
   deck, no PDK involved): `alter`-ing a source declared with an explicit
   `PWL(...)` waveform has **no effect** on the transient the source
   actually drives — the source keeps tracking its original PWL target
   regardless of the altered value. This testbench's `Vvdd` is exactly such
   a source (`PWL(0 0 200u @@VDD@@ 3m @@VDD@@)`, needed to reproduce the
   same startup-release/loop-closure/settledness protocol every
   `closed-loop-*` bench in this tree uses), so a `klt sim` corner sweep
   over `corners.supply_v` would silently simulate every requested voltage
   at the *template's own* literal PWL value instead — wrong, not merely
   imprecise. This is a capability gap distinct from the three already
   filed in `sim/harness/README.md`'s "Upstream friction" table; filed
   generically as a fourth, per this repo's friction protocol:
   [klayout-tools#2706](https://github.com/2AMLogic/klayout-tools/issues/2706).

So the sanctioned path for *this* A/B, on *this* host, today, is the
explicit standing exception both of those same rules carry: "a single
corner — a debug probe, one operating point — may run locally." This
experiment's own `run_one_point.sh` runs exactly one (corner, temperature,
supply, aids-state) point per invocation and is invoked by hand, once per
point — nothing in this tree loops over a grid. The points actually run
(19, listed in the committed record below) are a deliberately narrow,
hand-picked set: the full 8-temperature grid at 3.63 V, aids removed, for
the two corners (`bcs`, `typ`) issue #269's own per-corner table shows
degrading most under the trim ladder, plus three aids-present points that
reproduce the committed aided pre-trim record
(`sim/closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc-boxtc.csv`)
as a correctness check on this experiment's own script before trusting its
aids-free numbers.

## What the committed record shows

[`records/20261002-125922-d770c09.md`](records/20261002-125922-d770c09.md),
[`...csv`](records/20261002-125922-d770c09.csv),
[`...-boxtc.csv`](records/20261002-125922-d770c09-boxtc.csv) — 19/19 points
PASS.

**Validation (3 points, aids present)**: `bcs`/3.63 V/125 °C = 1.04335 V,
`bcs`/3.63 V/0 °C = 1.04643 V, `typ`/3.63 V/125 °C = 1.04801 V — all agree
with the committed `20260921-194249-77820fc-boxtc.csv` vmin/vmax values to
the last printed digit. This experiment's template and script reproduce the
record they are being compared against.

**The A/B (16 points, full 8-temperature grid, aids removed)**:

| corner / vdd | aided (committed, `77820fc`) | aids-free (this record) | Δ | trim-bearing aids-free (#229, code 128) |
|---|---|---|---|---|
| `bcs`/3.63 V | 17.839 ppm/°C | **18.515 ppm/°C** | +0.676 (+3.8%) | 38.610 ppm/°C (+116% over aided) |
| `typ`/3.63 V | 10.161 ppm/°C | **10.705 ppm/°C** | +0.544 (+5.4%) | 32.8 ppm/°C (+223% over aided) |

Removing the convergence aids alone, on the pre-trim core, moves box TC by
single-digit percent at both checked corners — the same small-signal
sensitivity `closed-loop-vref-boxtc-trim/README.md`'s own anecdotal 2.2 mV
(125 °C) finding implied, now quantified as a box-TC delta across the full
grid. It is nowhere near the 2–3× jump the trim-bearing core shows
aids-free at these same two (corner, vdd) groups. **The trim ladder, not
the convergence aids, is the dominant cause of the box-TC degradation #229
measured.**

## Disposition (issue #269 AC2)

No superseding decision record. The `< 20 ppm/°C` stretch *number* does not
need to move — `0010-box-method-tc-evidence.md` already characterizes the
pre-trim core honestly ("at the boundary," 19.8/20.1 ppm/°C), and this
record confirms that characterization is unaffected by the aids (18.5/10.7
ppm/°C aids-free vs 17.8/10.2 ppm/°C aided at the two corners checked — both
readings are consistent with "at the boundary," not with a methodology
artifact). What changed is which core is real: the trim-bearing core is the
as-built design, and #229's own committed record
(`sim/closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv`,
38.610/45.695 ppm/°C) already is the disposition that the stretch is not
met on it — this experiment's job was only to confirm that finding is not
an aids-removal artifact, which it does. `README.md`'s TC-row status prose
is updated to state the trim-bearing reality (confirmed real, not an aids
artifact) alongside the pre-trim boundary finding `0010` already recorded,
rather than citing only the superseded aided pre-trim numbers.

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh   # one-time: build the OSDI models

# One point per invocation -- see "Why not klt sim..." above for why this
# experiment does not ship a run_pvt_sweep.sh-shaped grid loop.
sim/closed-loop-vref-boxtc-pretrim-aidsfree/run_one_point.sh \
    <RECORD_ID> <corner: typ|bcs|wcs|sf|fs> <temp_c> <vdd> <aided|aidsfree>
```

Each call appends one row's worth of netlist/log/row data under
`netlist-snapshots/<RECORD_ID>/`, `corners/<RECORD_ID>/` and
`.rows/<RECORD_ID>/` (the last a scratch dir, not committed — assemble
`records/<RECORD_ID>.csv` from it by concatenating the `.row` files with
the header this directory's own committed CSV uses). Extending this
record's own grid (more corners, more supplies) to further corroborate the
disposition above is welcome follow-on work once issue #277/#278 land and
a full `klt sim` batch grid becomes possible on this PDK; it is not required
to act on the disposition already reached.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
