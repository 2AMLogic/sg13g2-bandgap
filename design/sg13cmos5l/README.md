# design/sg13cmos5l — SG13CMOS5L port schematics (issue #64, phase 1/4 of #63)

**Placement decision**: SG13CMOS5L schematics live under this
PDK-named subdirectory, `design/sg13cmos5l/`, parallel to (not mixed
into) `../*.sch` (the existing SG13G2 schematics, which are all directly
under `design/`). This repo had no existing multi-PDK schematic
convention to follow (per issue #64's own note), so the choice made here
is: **the original SG13G2 schematics keep their historical flat
location** (`design/bandgap_core.sch` etc. — not moved, to avoid an
unnecessary path-breaking churn across every existing `sim/` testbench
and `design/README.md` reference that already points at them), and
**every other PDK variant gets its own `design/<pdk-variant>/`
subdirectory**, matching `sim/`'s own per-PDK-pin convention
(`sim/pdk.json` today, a future `sim/pdk-sg13cmos5l.json` per issue #65's
own Implementation Guidance) applied one level up, to schematics instead
of evidence records. `design/xschemrc` needed **no changes** for this —
it already resolves the PDK generically from `PDK_ROOT`/`PDK`
(issue #64's own Implementation Guidance confirmed this before any code
was written), and symbol-library resolution is path-search-based, not
schematic-location-based, so a schematic in this subdirectory resolves
`sg13cmos5l_pr/*.sym` exactly the same way a `design/*.sch` file resolves
`sg13g2_pr/*.sym`.

```
design/sg13cmos5l/
  README.md            this file
  bandgap_core.sch      the bandgap core (issue #64) -- see its own header
                         for the full topology/sizing derivation
  netlist/              xschem-generated .spice netlist (committed, same
                         fleet convention design/README.md documents)
```

## What's here (issue #64)

**Device-topology decision**: see
[`spec/decision-records/0004-cmos5l-bipolar-device-selection.md`](../../spec/decision-records/0004-cmos5l-bipolar-device-selection.md)
(DR-0004). Summary: SG13CMOS5L has no `npn13G2`-equivalent HBT — only
`pnpMPA`, the same low-gain (`bf ≈ 1.10`) parasitic-style PNP DR-0001
evaluated and rejected as SG13G2's primary bipolar device. With no HBT
available here, `bandgap_core.sch` follows gf180-bandgap's/sky130-bandgap's
grounded-collector parasitic-PNP-pair Brokaw shape instead of
re-parameterizing `../bandgap_core.sch` (SG13G2's grounded-*emitter* NPN
core) — **this is a genuinely new schematic, not a copy of either.**

**`bandgap_core.sch`** — three `pnpMPA` legs (Q1 unit `w=1u l=2u`, Q2 at
`w=8u l=2u` for the 8:1-area PTAT delta-VEB, Q3 unit output device), each
diode-connected (base tied to collector) with the shared node tied to
`vss` — grounded-collector, emitter driven from a matched `sg13_hv_pmos`
mirror leg gated by an external `fb` node (DR-0002's 3.3V HV supply
flavor, inherited unchanged). `R2` sets the PTAT current once an external
amplifier forces `sns1 = sns2`; `R1` sums the CTAT `VEB(Q3)` with the
PTAT `I*R1` term at `vref`. `rppd` (mild-TC precision resistor, same
flavor this repo's SG13G2 core and both sibling repos favor) is used for
both resistors. No cascode, trim, compensation cap, error amplifier, or
startup circuit — `bandgap_core` only, matching the acceptance criteria's
"at minimum `bandgap_core`" bar. Full topology rationale and the
provisional sizing derivation are in the schematic's own header comment.

### Explicitly out of scope for this issue (follow-up filed)

- **The error amplifier, startup circuit, and top-level integration**
  (`bandgap_amp`/`bandgap_startup`/`bandgap_top` equivalents for
  SG13CMOS5L) — not attempted this phase, per the parent issue's own
  allowance ("if time allows, else file as follow-up"). Filed as a
  separate follow-up issue (see this PR's description for the link)
  rather than expanding this phase's scope.
- **A cascode / PSRR output stage, a trim network, PVT-swept sizing.**
  Same reasons `../bandgap_core.sch`'s own first pass (issue #9) deferred
  these — #65 (phase 2, PVT-cornered testbenches) is the issue that grounds
  this core's numbers in real `sim/` evidence.
- **Loop-compensation or filter capacitors.** No amplifier exists yet to
  compensate. DR-0004 names this explicitly as forward guidance for
  whichever future phase adds one: this PDK has **no MIM cap** — only MoM
  (`cap_cmomf`/`cap_cmomi`) and MOS caps (`moscap_n`/`moscap_p`) — and per
  the parent issue, MoM caps carry no corner/mismatch spread in their
  models, so any future comp-cap sizing needs a dedicated sensitivity
  sweep rather than a PVT-corner claim.

## Running xschem / regenerating the netlist

```bash
export PDK_ROOT=/path/to/parent-dir-containing-ihp-sg13cmos5l
export PDK=ihp-sg13cmos5l
cd design && xschem --rcfile ./xschemrc sg13cmos5l/bandgap_core.sch   # interactive
```

To regenerate the committed netlist headlessly (no X server needed):

```bash
export PDK_ROOT=/path/to/parent-dir-containing-ihp-sg13cmos5l
export PDK=ihp-sg13cmos5l
cd design/sg13cmos5l
xschem -n -x -q -r --rcfile ../xschemrc -o ./netlist ./bandgap_core.sch
```

Same `xschem -n -x -q -r` convention `design/README.md` documents for the
SG13G2 schematics (netlist, headless X, quiet, regenerate-existing).

**A resolvable SG13CMOS5L PDK install is required.** Unlike SG13G2 (whose
`design/xschemrc` resolution this repo already documents), SG13CMOS5L's
own device symbols (`libs.tech/xschem/sg13cmos5l_pr/*.sym`, for every
device except the two real MoM-cap symbols) are **symlinks into a sibling
`ihp-sg13g2` checkout** (`../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/*.sym`)
— confirmed by reading them directly. This PDK's own `README.md`
documents the intended install shape as a combined checkout,
`IHP-Open-PDK/{ihp-sg13g2,ihp-sg13cmos5l}` side by side; an
`ihp-sg13cmos5l`-only install (e.g. a bare `git clone
https://github.com/IHP-GmbH/ihp-sg13cmos5l.git`) leaves those symlinks
dangling. See "Tooling/PDK friction encountered" below for how this was
resolved in this environment and the upstream issue filed for it.

## What has and has not been verified in this environment (issue #64, honest account)

Per `CLAUDE.md`'s "no claim without a testbench": this issue lands a
schematic source, not a `sim/`-quality verified design — that is #65's
job. What follows is an honest, specific account of what schematic-entry-
time checking this issue's Builder actually ran.

- **Netlisting**: `bandgap_core.sch` was netlisted headlessly
  (`xschem -n -x -q -r`, command above) with zero errors or warnings
  against a real, resolved SG13CMOS5L PDK install (once the sibling-checkout
  friction below was worked around), against the real `sg13cmos5l_pr`
  symbol library. The resulting netlist
  (`design/sg13cmos5l/netlist/bandgap_core.spice`, committed) was checked
  against the schematic's intended wiring, e.g.
  `XQ1 vss vss sns1 pnpMPA a={ 1u * 2u } p={ ( 1u + 2u ) * 2 } m=1` —
  base/collector tied to `vss`, emitter tied to `sns1`, exactly the
  grounded-collector, diode-connected wiring the header comment describes.
- **Real-device DC operating-point sanity check (informal, NOT `sim/`
  evidence)**: unlike `../bandgap_core.sch`'s own first-pass check (issue
  #9), which had to substitute ideal current sources and ideal resistors
  for the SG13G2 MOS/resistor devices (no `.osdi` models were buildable in
  that environment at the time), **this environment's SG13CMOS5L install
  ships prebuilt `.osdi` binaries already**
  (`libs.tech/ngspice/osdi/{psp103,psp103_nqs,r3_cmc,mosvar,cap_cmomf,cap_cmomi}.osdi`
  — no `sim/tools/build-osdi.sh`-equivalent build step was needed here).
  So this check ran the schematic's actual generated netlist verbatim
  (real `sg13_hv_pmos` PSP103 mirror legs, real `rppd` r3_cmc resistors,
  real `pnpMPA` Gummel-Poon devices — no substitutions at all), open-loop
  with `fb` set by a diode-connected reference mirror carrying 5µA (same
  fixture pattern `sim/core-open-loop-bias/testbench/tb_core_open_loop_bias.spice.tmpl`
  uses for the SG13G2 core), at the `typ` process corner, 27°C, `vdd=3.3V`:

  | Node/quantity | Result |
  |---|---|
  | `vref` | 1.2049 V |
  | `sns1` / `sns2` | 0.7810 V / 0.7818 V (0.8 mV apart, open-loop — no amp yet to force equality) |
  | Branch currents (`i(vm1)`/`i(vm2)`/`i(vm3)`) | 5.087 µA / 5.087 µA / 5.069 µA |
  | Mirror `Vsg` (`vdd - fb`) | 0.805 V |
  | Mirror `Vsd` headroom (`vdd - sns1`) | 2.519 V |

  `vref` lands within 0.4% of the 1.2V target using the schematic's own
  hand-derived `R1`/`R2` (see the schematic header for the derivation),
  branch currents track the intended 5µA design current closely even
  though real PSP103 mirror devices (not ideal current sources) are doing
  the mirroring, and the PMOS legs sit well inside SG13CMOS5L's 3.3V HV
  rating with ample `Vsd` headroom. This is a single nominal data point
  with no PVT sweep and no closed loop (no amplifier exists yet to force
  `sns1 = sns2`) — reported here as "the topology and hand-sizing are in
  the right ballpark," matching the same evidentiary weight
  `design/README.md`'s own "issue #9" section gives its analogous check,
  not a verified spec claim. #65 is the issue that produces real `sim/`
  evidence.
- **Not attempted**: PVT corner sweep, closed-loop behavior (no amplifier
  yet), startup-circuit behavior, DRC/LVS, layout, mismatch/Monte Carlo.
  All explicitly out of this issue's scope.

## Tooling/PDK friction encountered

**A real, upstream-worthy gap, filed per `CLAUDE.md`'s friction
protocol**: this PDK's `libs.tech/xschem/sg13cmos5l_pr/*.sym` device
symbols (every device except the two MoM-cap symbols) are relative
symlinks into a *sibling* `ihp-sg13g2` checkout
(`../../../../ihp-sg13g2/libs.tech/xschem/sg13g2_pr/*.sym`) that does not
exist in an `ihp-sg13cmos5l`-only install — confirmed by reading the
symlinks directly and by this PDK's own `README.md`, which documents the
intended install as a combined `IHP-Open-PDK/{ihp-sg13g2,
ihp-sg13cmos5l}` checkout. Filed generically (tool/deck gap, no
design-specific detail) at `2AMLogic/klayout-tools` — see this PR's
description for the issue link. Worked around **locally, in this
environment only** (not a repo change) by placing a sibling `ihp-sg13g2`
checkout next to the existing `ihp-sg13cmos5l` install under the shared
`PDK_ROOT` this repo's tooling already searches (`~/share/pdk`), so the
relative symlinks resolve — no `design/xschemrc`/`sim/env.sh` change was
needed or made, since both files already resolve `PDK_ROOT`/`PDK`
generically from the environment.

Once that install-shape gap was worked around, no further friction was
encountered: every symbol this schematic instantiates
(`sg13_hv_pmos.sym`, `pnpMPA.sym`, `rppd.sym`) resolved with pinouts and
`template=`/`format=` netlist parameters exactly matching what
`spec/decision-records/0004-cmos5l-bipolar-device-selection.md` derived
from reading the model cards directly, and the PDK's prebuilt `.osdi`
binaries loaded with no build step. The MoM-cap-only constraint (no MIM
cap symbol/model anywhere in this PDK) was also confirmed directly and
did not block this phase, since `bandgap_core` alone needs no capacitor
— see DR-0004 for why this is flagged as forward guidance rather than
resolved here.
