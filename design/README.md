# design — schematics and netlists

Schematic capture is [xschem](http://xschem.sourceforge.net/); simulation is
[ngspice](https://ngspice.sourceforge.io/) via the PVT corner runner in
[`../sim/`](../sim/README.md) (issue #10 — landed as
`sim/core-open-loop-bias/`; see "What has and has not been verified" below
for what this issue's own, informal, non-`sim/`-evidence checks did and did
not confirm, and `sim/core-open-loop-bias/README.md` for the first real
`sim/`-evidence testbench built on top of it).

**Multi-PDK note (issue #64)**: everything below is the original IHP SG13G2
port. A second PDK variant, IHP SG13CMOS5L, is being ported starting with
[`sg13cmos5l/`](sg13cmos5l/README.md) (issue #64, phase 1/4 of #63) — a
separate, PDK-named subdirectory rather than a modification of the
schematics below (see that directory's README for the placement rationale
and why SG13CMOS5L needed a different bipolar-device topology,
[`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`](../spec/decision-records/0004-cmos5l-bipolar-device-selection.md)).

```
design/
  xschemrc        repo xschem config: resolves the SG13G2 PDK, adds repo
                   symbol libraries (fleet convention — modeled on
                   gf180-bandgap/design/xschemrc and sky130-bandgap's
                   equivalent)
  bandgap_core.sch    the bandgap core (issue #9)
  bandgap_core.sym    hierarchical-instantiation symbol for the above
                      (issue #58 — #9 landed the schematic without one, since
                      no top-level wiring existed yet to need it)
  bandgap_startup.sch the startup circuit (issue #9)
  bandgap_startup.sym hierarchical-instantiation symbol for the above
                      (issue #58, same reason as bandgap_core.sym)
  bandgap_amp.sch     the error amplifier closing the loop (issue #58)
  bandgap_amp.sym     hierarchical-instantiation symbol for the above
                      (issue #58)
  bandgap_top.sch     top-level integration: core + amp + startup wired
                      together, the first closed-loop schematic (issue #58)
  netlist/        xschem-generated .spice netlists (committed — see fleet
                   convention note below)
```

## What's here (issue #9)

Two xschem schematics, built around `npn13G2` (SG13G2's real SiGe:C HBT) in
a **grounded-emitter** topology, per
[`spec/decision-records/0001-bipolar-device-selection.md`](../spec/decision-records/0001-bipolar-device-selection.md)
(DR-0001) and targeting the 3.3V HV supply flavor per
[`spec/decision-records/0002-supply-voltage-scope.md`](../spec/decision-records/0002-supply-voltage-scope.md)
(DR-0002):

- **`bandgap_core.sch`** — three `npn13G2` legs (Q1 unit, Q2 at `Nx=8` for
  the PTAT delta-VBE, Q3 unit output device), each diode-connected
  (base tied to collector) with the **emitter grounded** — the mirror image
  of gf180-bandgap's and sky130-bandgap's grounded-*collector* PNP-pair
  cores, not a re-parameterized copy of either
  (`spec/porting-plan.md` §5). Each leg is fed from a matched `sg13_hv_pmos`
  mirror device gated by an external `fb` node. `R2` (leg 2) sets the PTAT
  current once an external error amplifier forces `sns1 = sns2`; `R1`
  (output leg) sums the CTAT `VBE(Q3)` with the PTAT `I*R1` term at `vref`
  — the same Brokaw-style sum both sibling cores use, adapted to an NPN
  device. No cascode and no external amplifier/startup wiring are included
  in this first pass — see "Explicitly out of scope" below. `Rppd` (mild
  TC, the porting plan's precision-resistor candidate) is used for both
  resistors. Full topology rationale, the BVCEO/BVEBO safety argument for
  why no cascode is needed on these three diode-connected devices, and the
  provisional sizing derivation are in the schematic's own header comment
  (open `bandgap_core.sch` in a text editor or xschem to read it).
- **`bandgap_startup.sch`** — a current-sensing, self-disabling startup kick
  (three devices: `Rhigh` pull-up, two `sg13_hv_nmos` switches), modeled on
  gf180-bandgap's `bandgap_startup.sch` pattern but sensing `bandgap_core`'s
  own `sns1` node directly (this core's first pass has no internal bias-
  mirror leg to sense, unlike gf180's `ibias` node — see the schematic's
  header for the adaptation). Deliberately uses **no bipolar device**, so
  DR-0001's Consequences-section BVCEO/BVEBO constraint on any bipolar
  device in the startup path does not bind here by construction (noted
  explicitly in the header, not silently true).

Both schematics' pin lists and the reasoning behind them are documented in
full inside each `.sch` file's own header comment — read those first; this
README summarizes, it does not duplicate the full derivation.

### Explicitly out of scope for this issue (follow-on work)

- ~~**The error amplifier** that drives `fb` and senses `sns1`/`sns2`~~ —
  **landed by issue #58**, see "What's here (issue #58)" below.
- ~~**Top-level integration** wiring `bandgap_core` + the future amp +
  `bandgap_startup` together~~ — **landed by issue #58**, see below.
- **A cascode / PSRR-improvement output stage.** `bandgap_core.sch`'s header
  explains why the three core HBTs themselves need no cascode for BVCEO
  safety (diode-connected, `Vce = Vbe`, far below the ~1.4-1.6V BVCEO
  floor) — a future PSRR pass could still add one to the mirror, and would
  need to keep any *bipolar* device it adds within the same BVCEO/BVEBO
  ceiling per DR-0001.
- **A trim network.** Neither sibling repo's first-pass core had one either.
- **Simulation-grounded sizing.** All resistor/device sizes here are a
  first-pass, hand-derived estimate (see each schematic's header) — #10
  (PVT testbenches) is what will re-derive them against real corner-swept
  simulation data, the way gf180-bandgap's own core sizing was repeatedly
  revised (issues #55/#61/#96/#147 in that repo) after its first landing.

## What's here (issue #58)

Closes the loop for the first time: an error amplifier, a top-level
integration schematic wiring it to `bandgap_core` + `bandgap_startup`, and
(in [`../sim/closed-loop-startup/`](../sim/closed-loop-startup/README.md))
the first genuinely closed-loop `sim/` testbench.

- **`bandgap_amp.sch`** — a single-stage, current-mirror-folded OTA, all
  real `sg13_hv_pmos`/`sg13_hv_nmos` devices (no bipolar device at all, so
  DR-0001's BVCEO/BVEBO constraint does not bind here by construction —
  the same "noted explicitly, not silently true" discipline
  `bandgap_startup.sch` already applies). Topology mirrors sky130-bandgap's
  *original* placeholder amplifier (that repo's issue #8): a PMOS input
  pair for this core's low (~0.7-0.8V, one VBE) sense-node common mode,
  folded through an NMOS-then-PMOS mirror chain so the output can swing
  close enough to `vdd` to fully turn off `bandgap_core`'s PMOS mirror legs
  — not gf180-bandgap's placeholder, which is an NMOS-input design built
  for that core's opposite (near-`vdd`) sense-node polarity. Rather than
  add a bias-generation pin to the already-landed `bandgap_core.sch` (out
  of scope here), this amplifier senses `fb` directly (a non-loading tap,
  the same way `bandgap_core`'s own M1-M3 gates already do) to mirror the
  core's own per-branch current into its own tail — see the schematic's
  header "polarity" and topology sections for the full derivation,
  including the single most safety-critical design decision here: which
  sense node (`sns1` vs `sns2`) is the inverting vs. non-inverting input.
  Getting that backwards makes the loop positive feedback instead of
  negative.
- **`bandgap_top.sch`** — instantiates `bandgap_core` + `bandgap_amp` +
  `bandgap_startup` and wires them at the nodes they share (`core.fb` <-
  `amp.out`, `core.sns1` -> `amp.in_n`, `core.sns2` -> `amp.in_p`,
  `startup.sns1` <- `core.sns1`, `startup.fb` -> `core.fb`), matching
  gf180-bandgap's and sky130-bandgap's own `bandgap_top.sch` pattern
  (`spec/porting-plan.md` §5). Exposes only `vdd`, `vss`, `vref` at the top
  level, the same minimal pin set both sibling repos use.
- **`bandgap_core.sym`, `bandgap_startup.sym`, `bandgap_amp.sym`** —
  hierarchical-instantiation symbols so the three schematics can be
  instantiated in `bandgap_top.sch` (issue #9 landed `bandgap_core.sch`/
  `bandgap_startup.sch` without symbols, since no top-level wiring existed
  yet to need one). Pin lists match each schematic's own `iopin` list
  exactly.
- **Closed-loop validation**: see
  [`sim/closed-loop-startup/README.md`](../sim/closed-loop-startup/README.md)
  for the first `sim/`-evidence testbench co-simulating all three blocks —
  a transient `vdd` ramp, checking the assembled block self-starts (the
  startup circuit fully releases) and settles to a real closed-loop
  operating point (the amplifier actually forces `sns1 ≈ sns2`, and `fb`
  lands at an interior equilibrium rather than railing) across the full
  PVT grid.

## Running xschem / regenerating the netlist

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
cd design && xschem --rcfile ./xschemrc bandgap_core.sch   # interactive
```

`design/xschemrc` resolves the SG13G2 PDK the same way `klt pdk find`
does (`PDK_ROOT`/`PDK` env vars, falling back to the usual open_pdks install
prefixes), sources the PDK's own xschemrc so the `sg13g2_pr` device symbols
are on the library path, and adds `design/`, `design/symbols/` (once it
exists) and every `sim/<experiment-slug>/testbench/` (once any exist) to the
library path.

To regenerate the committed netlists headlessly (no X server needed):

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
cd design
xschem -n -x -q -r --rcfile ./xschemrc -o ./netlist ./bandgap_core.sch
xschem -n -x -q -r --rcfile ./xschemrc -o ./netlist ./bandgap_startup.sch
xschem -n -x -q -r --rcfile ./xschemrc -o ./netlist ./bandgap_amp.sch
xschem -n -x -q -r --rcfile ./xschemrc -o ./netlist ./bandgap_top.sch
```

This is the same fleet convention gf180-bandgap's `design/README.md` and
`sim/smoke_test/run_smoke_test.sh` use (`xschem -n -x -q -r`: netlist,
headless X, quiet, regenerate-existing). Netlists land in `design/netlist/`
and are committed (reviewable in git), matching gf180-bandgap's
`design/netlist/*.spice` convention — not `.gitignore`d.

**A resolvable SG13G2 PDK install is required** (`PDK_ROOT`/`PDK` pointing
at an `ihp-sg13g2/` open_pdks-shaped directory, i.e. what `klt pdk find`
resolves — see `CLAUDE.md`; klayout-tools' own
`scripts/fetch-ihp-sg13g2.sh` fetches a pinned IHP-Open-PDK release into
that shape). This repo does not vendor the PDK itself.

## What has and has not been verified in this environment (issue #9, honest account)

Per `CLAUDE.md`'s "no claim without a testbench": this issue lands schematic
sources, not a `sim/`-quality verified design. What follows is an honest,
specific account of what schematic-entry-time checking this issue's Builder
actually ran, in the sandbox it ran in — not a substitute for #10.

- **Netlisting**: both schematics were netlisted headlessly with a real,
  fetched SG13G2 PDK install (`xschem -n -x -q -r`, command above) with zero
  `l_s_d(): Symbol not found` or other xschem errors, and the resulting
  `.spice` output (`design/netlist/*.spice`, committed) was manually
  checked against each schematic's intended pin mapping (e.g.
  `XQ1 sns1 sns1 vss vss npn13G2 Nx=1` — collector/base tied to `sns1`,
  emitter and substrate tied to `vss`, exactly the diode-connected,
  grounded-emitter wiring the header comment describes). This confirms the
  schematics are syntactically valid and structurally wired as designed
  against the real `sg13g2_pr` symbol library — not merely "should work."
- **HBT device-model sanity (informal, NOT `sim/` evidence)**: the three
  `npn13G2` legs (with ideal current sources and ideal `R` primitives
  standing in for the PMOS mirror and `rppd` resistors — see next bullet)
  were run through ngspice's real VBIC `npn13G2` model card
  (`cornerHBT.lib`, `hbt_typ` corner) at a single nominal op-point (27°C,
  5µA/branch). Result: `dVBE(Q1,Q2) = 55.2 mV`, closely matching the
  `VT*ln(8) = 53.75 mV` hand estimate the schematic's sizing comment uses,
  and a provisional `vref = 1.158 V` — within ~3.5% of the ~1.2V target
  using the schematic's own hand-picked `R1`/`R2` values. This is a single
  nominal data point with two of three device types replaced by ideal
  components, not a corner sweep or a mismatch/PVT-grounded result — it is
  reported here as "the topology and hand-sizing are in the right
  ballpark," not as a verified spec claim.
- **What could NOT be run in this environment**: a full mixed-device
  op-point (real `sg13_hv_pmos` mirror + real `rppd`/`rhigh` resistors +
  real `npn13G2`) was attempted and failed — the installed `ngspice-46`
  build has no `PSP103`/`r3_cmc` compact-model support compiled in, and
  SG13G2's PSP-MOS and `r3_cmc`-resistor compact models are shipped as
  Verilog-A sources (`libs.tech/verilog-a/`) that need to be compiled to
  `.osdi` shared libraries (via OpenVAF) before ngspice can load them
  (`libs.tech/ngspice/.spiceinit`'s `osdi '...psp103.osdi'` etc. lines) —
  the IHP-Open-PDK release tarball does not ship prebuilt `.osdi` files, and
  neither OpenVAF nor a prebuilt `.osdi` set was available in this sandbox.
  This is **not** a `klayout-tools`/`klt` gap (out of that tool's scope —
  `klt` resolves PDK *paths*, it does not compile simulator device models),
  so it was not filed under the friction protocol; it is noted here as an
  honest environment limitation for whoever picks up #10, which will need a
  machine (or a documented OpenVAF build step) with working `.osdi` models
  to run any MOS- or resistor-containing testbench at all.
  **Resolved by issue #22**: `sim/tools/build-osdi.sh` now builds the
  PSP103 and `r3_cmc` models from the PDK's own Verilog-A sources with a
  checksum-pinned OpenVAF-Reloaded compiler, so real `sg13_hv_pmos` /
  `sg13_hv_nmos` / `rppd` / `rhigh` devices simulate here. See
  `sim/README.md` § "OSDI device models" for the build, and
  `sim/core-open-loop-bias/` + `sim/startup-trip-point/` for the
  full-PVT-grid evidence produced with them. The paragraph above is kept
  as the historical account of what issue #9's environment could do.
- **Not attempted**: DRC/LVS, layout, PVT corner sweeps, mismatch/Monte
  Carlo, startup-circuit transient behavior, and anything requiring the
  amplifier this issue deliberately does not build. All out of this
  issue's scope per the acceptance criteria (structural: schematics
  committed, DR-0001/DR-0002 reflected — not simulation-verified).

## What has and has not been verified in this environment (issue #58, honest account)

- **Netlisting**: `bandgap_amp.sch` and `bandgap_top.sch` both netlist
  headlessly (`xschem -n -x -q -r`, command above) with zero errors or
  warnings, against the same real, fetched SG13G2 PDK install `bandgap_core.sch`/
  `bandgap_startup.sch` already used — including `bandgap_top.sch`'s
  hierarchical expansion of all three sub-schematics via their new `.sym`
  files, which resolves to exactly the wiring the "What's here" section
  above describes (checked directly against the generated
  `design/netlist/bandgap_top.spice`).
- **Standalone amplifier op-point/DC-sweep sanity (informal, NOT `sim/`
  evidence)**: before wiring the amplifier into the full loop, its
  standalone netlist was driven with fixed `in_p`/`in_n` sources and swept
  `in_p` across the input common-mode range at a fixed `in_n`. Result: a
  monotonic, sharply single-ended output transition centered near
  `in_p = in_n` (as a differential servo amplifier should show), rising
  with `in_p` — confirming the polarity derivation in the schematic's own
  header before it was ever exposed to the real closed loop.
- **Closed-loop `sim/` evidence — the actual claim**: see
  [`sim/closed-loop-startup/README.md`](../sim/closed-loop-startup/README.md).
  45/45 PVT points (the same corner x temperature x supply grid every
  other testbench in this tree uses) show the assembled block self-starting
  (the startup circuit's `MKFB` fully releases) and settling to a real
  closed-loop equilibrium (`|sns1 - sns2|` within 0.51 mV of zero at its
  worst corner, well inside the 20 mV loop-closure tolerance; `vref` lands
  in a 1.134-1.215 V band across the full grid, `fb` never rails to either
  supply). This is genuinely closed-loop evidence, not an informal check —
  the first in this repository.
- **A real numerical finding, not a design defect**: a handful of PVT
  corners would not converge with ngspice's default solver settings during
  the transient's very early (sub-1 V), near-singular startup instant —
  resolved with `rshunt`/`gmin` convergence aids (documented in the
  testbench template itself, both many orders of magnitude below any
  measured current in this circuit, so neither relaxes any pass/fail
  criterion). Worth naming here because it is the first time this repo's
  `sim/` tree has needed a convergence aid at all — every prior PVT sweep
  used an idealized fixture at exactly the node this amplifier's own real
  devices now drive dynamically through a genuinely stiff instant.
- **Not attempted**: loop-gain/phase-margin/stability measurement (no
  small-signal AC testbench yet — this issue's testbench is transient-only),
  PSRR, offset/mismatch, and any claim against `spec/porting-plan.md` §6's
  draft target table (not ratified — #13). All explicitly out of this
  issue's scope; see `sim/closed-loop-startup/README.md`'s own "what this
  testbench claims, and what it does not" section.

## Tooling/PDK friction encountered

None rising to the friction protocol's bar (`CLAUDE.md`: file generic
`klayout-tools` gaps upstream). `klt pdk find --pdk-root ... --pdk
ihp-sg13g2` correctly resolved a manually-fetched SG13G2 install in this
sandbox with no resolver issues, and every device symbol named in
`spec/porting-plan.md`'s device survey (`npn13G2.sym`, `rppd.sym`,
`rhigh.sym`, `rsil.sym`, `sg13_hv_nmos.sym`, `sg13_hv_pmos.sym`) existed
exactly where the porting plan said it would, with pinouts and `template=`
netlist parameters that matched what was used here with no surprises. The
missing prebuilt `.osdi` models (see above) is an `ngspice`/PDK-simulation-
model-build gap, not a `klt`/`klayout-tools` one.
