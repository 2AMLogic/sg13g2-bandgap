# design/sg13cmos5l — SG13CMOS5L port schematics (issues #64/#68, phases 1-2/4 of #63)

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
  README.md               this file
  bandgap_core.sch        the bandgap core (issue #64) -- see its own header
                          for the full topology/sizing derivation
  bandgap_core.sym        hierarchical-instantiation symbol (issue #68)
  bandgap_startup.sch      startup circuit (issue #68)
  bandgap_startup.sym      hierarchical-instantiation symbol (issue #68)
  bandgap_amp.sch          error amplifier (issue #68)
  bandgap_amp.sym          hierarchical-instantiation symbol (issue #68)
  bandgap_top.sch          top-level integration: core + amp + startup
                           (issue #68)
  netlist/                xschem-generated .spice netlists (committed, same
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
`w=1u l=2u m=8` — 8 parallel unit devices for the 8:1-area PTAT delta-VEB,
Q3 unit output device), each diode-connected (base tied to collector) with
the shared node tied to `vss` — grounded-collector, emitter driven from a
matched `sg13_hv_pmos` mirror leg gated by an external `fb` node (DR-0002's
3.3V HV supply flavor, inherited unchanged). `R2` sets the PTAT current once
an external amplifier forces `sns1 = sns2`; `R1` sums the CTAT `VEB(Q3)`
with the PTAT `I*R1` term at `vref`. `rppd` (mild-TC precision resistor,
same flavor this repo's SG13G2 core and both sibling repos favor) is used
for both resistors. No cascode, trim, compensation cap, error amplifier, or
startup circuit at THIS phase — `bandgap_core` only, matching issue #64's
acceptance criteria's "at minimum `bandgap_core`" bar. Full topology
rationale and the provisional sizing derivation are in the schematic's own
header comment.

**Q2's matched-array construction (issue #73, DR-0005)**: Q2 was originally
captured as a single `pnpMPA` instance with `w=8u l=2u` — an 8x-area device
built as one wide emitter. The SG13CMOS5L layout phase (issue #66) found
that construction unbuildable (`w=8u` exceeds this PCell's own
`pnpMPA_maxW` of 2.0µm — `pnpMPA_code.py`'s PCell generator cannot draw it
at all) and not how a matched 8x array is built anyway (the standard is N
unit devices in parallel). Issue #73 / DR-0005 changed Q2 to 8 parallel
`w=1u l=2u` unit devices via the SPICE `m=8` multiplier — each unit device
is well inside `pnpMPA_maxW`, and DR-0005 shows (direct model-card read,
confirmed by an ngspice cross-check) that this is electrically **identical**
to the old single-device construction: `pnpMPA`'s `.model` equations use
only the `a` (area) parameter, never `p` (perimeter, computed but unused),
and SPICE's `m=` subcircuit multiplier is mathematically equivalent to an
`area` multiplier for this model's linear/inverse-linear area dependence.
The re-run `sim/sg13cmos5l-*` PVT evidence (see those experiments' own
`records/`) confirms the numbers are unchanged. See
`spec/decision-records/0005-cmos5l-q2-matched-array-construction.md` for
the full account.

## What's here (issue #68 -- startup, amplifier, top-level integration)

Phase 2/4 of the SG13CMOS5L port (issue #68), the SG13CMOS5L analogue of
this repo's own SG13G2 `#9` → `#58` split. Lands the three schematics
`bandgap_core.sch` (issue #64, above) deliberately deferred, plus the
`.sym` files `bandgap_top.sch` needs to instantiate all three
hierarchically:

- **`bandgap_startup.sch`** — current-sensing, self-disabling startup kick.
  Ported from `../bandgap_startup.sch` (SG13G2, issue #9/#22/#24) with
  **only the symbol-library path changed** (`sg13g2_pr/` →
  `sg13cmos5l_pr/`) — that schematic's own header already noted it uses no
  bipolar device, and this port explicitly re-verified (not assumed) that
  `bandgap_core.sch`'s `sns1` node sits at the same ~0.7–0.8V one-VEB/VBE
  swing `../bandgap_startup.sch`'s `MSENSE` gate was built for, and that
  `fb`'s polarity (pulling it low turns the PMOS mirror ON) is identical
  in both cores. `sg13cmos5l_pr/rhigh.sym` and `sg13cmos5l_pr/sg13_hv_nmos.sym`
  are confirmed (by reading the installed PDK) to be the same devices as
  SG13G2's own — see "Tooling/PDK friction encountered" below — so sizing
  transfers unchanged from `../bandgap_startup.sch`'s current (post-#24-fix)
  values, not independently re-swept against pnpMPA's own PVT grid (#65).
- **`bandgap_amp.sch`** — error amplifier forcing `sns1 = sns2`. Ported
  from `../bandgap_amp.sch` (SG13G2, issue #58) with only the symbol-library
  path changed, after re-deriving (not assuming) both the polarity and the
  input common-mode range against this core's own topology and measured
  op-point: `bandgap_core.sch`'s legs give the identical
  `e := sns2 - sns1` monotonicity `../bandgap_amp.sch`'s header derives
  (only VBE relabeled VEB), so `sns2` is again the non-inverting input and
  `sns1` the inverting input; and the measured op-point (`sns1=0.7810V`,
  `sns2=0.7818V`, issue #64's own account below) sits in the same
  ~0.7–0.8V low-common-mode band `../bandgap_amp.sch`'s PMOS input pair was
  built for, so no input-pair polarity flip or level-shift was needed. See
  `bandgap_amp.sch`'s own header for the full re-derivation.
- **`bandgap_top.sch`** — top-level integration wiring core + amp + startup,
  exposing only `vdd`/`vss`/`vref`, matching `../bandgap_top.sch`'s pattern
  exactly (same internal wiring: `core.fb <- amp.out`, `core.sns1 ->
  amp.in_n`, `core.sns2 -> amp.in_p`, `startup.sns1 <- core.sns1`,
  `startup.fb -> core.fb`).
- **`bandgap_core.sym`/`bandgap_startup.sym`/`bandgap_amp.sym`** —
  hierarchical-instantiation symbols, following `../bandgap_core.sym` /
  `../bandgap_startup.sym` / `../bandgap_amp.sym`'s (SG13G2, issue #58)
  pattern; pin lists match each schematic's own iopin list exactly.

### Explicitly out of scope for this issue (follow-up filed)

- **A cascode / PSRR output stage, a trim network, PVT-swept sizing.**
  Same reasons `../bandgap_core.sch`'s own first pass (issue #9) deferred
  these — #65 (phase 3, PVT-cornered testbenches) is the issue that grounds
  this core's numbers in real `sim/` evidence.
- **Loop-compensation or filter capacitors.** DR-0004 names this explicitly
  as forward guidance for whichever future phase adds one: this PDK has
  **no MIM cap** — only MoM (`cap_cmomf`/`cap_cmomi`) and MOS caps
  (`moscap_n`/`moscap_p`) — and per the parent issue, MoM caps carry no
  corner/mismatch spread in their models, so any future comp-cap sizing
  needs a dedicated sensitivity sweep rather than a PVT-corner claim. No
  compensation capacitor exists in `bandgap_amp.sch`'s first pass either
  (matching `../bandgap_amp.sch`'s own deferral) — loop stability
  (phase margin) is not measured by this issue's transient-only informal
  check below.
- **A real PVT-swept closed-loop testbench under `sim/`.** This issue's own
  closed-loop check (below) is a single nominal-corner, informal,
  non-`sim/`-evidence check — a `sim/closed-loop-startup`-equivalent
  full-PVT-grid testbench for SG13CMOS5L is #65's scope, mirroring how
  SG13G2's own `sim/closed-loop-startup/` (issue #58) followed the
  schematic-capture phase.

## Running xschem / regenerating the netlist

```bash
export PDK_ROOT=/path/to/parent-dir-containing-ihp-sg13cmos5l
export PDK=ihp-sg13cmos5l
cd design/sg13cmos5l && xschem --rcfile ../xschemrc bandgap_top.sch   # interactive
```

(Invoke from `design/sg13cmos5l/` itself, not `design/` — `design/xschemrc`
resolves hierarchical-instantiation symbols like `bandgap_core.sym` by
searching the invoking schematic's own directory first, precisely so a
same-named symbol/schematic in `../` (SG13G2's own `bandgap_core.sym`, for
example) cannot silently shadow this directory's SG13CMOS5L one — see
"Tooling/PDK friction encountered" below for the bug this fixed.)

To regenerate the committed netlist headlessly (no X server needed):

```bash
export PDK_ROOT=/path/to/parent-dir-containing-ihp-sg13cmos5l
export PDK=ihp-sg13cmos5l
cd design/sg13cmos5l
xschem -n -x -q -r --rcfile ../xschemrc -o ./netlist ./bandgap_core.sch
xschem -n -x -q -r --rcfile ../xschemrc -o ./netlist ./bandgap_startup.sch
xschem -n -x -q -r --rcfile ../xschemrc -o ./netlist ./bandgap_amp.sch
xschem -n -x -q -r --rcfile ../xschemrc -o ./netlist ./bandgap_top.sch
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

*(See "issue #68" below for the startup/amp/top verification account —
kept separate since it was run in a different, later pass.)*

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

## What has and has not been verified in this environment (issue #68, honest account)

Per `CLAUDE.md`'s "no claim without a testbench": this issue lands schematic
sources plus an **informal** sanity check, not `sim/`-quality PVT-cornered
evidence — that remains #65's job. What follows is an honest, specific
account of what this issue's Builder actually ran.

- **Netlisting**: `bandgap_startup.sch`, `bandgap_amp.sch`, and
  `bandgap_top.sch` all netlist headlessly (`xschem -n -x -q -r`, command
  above) with **zero errors or warnings** against a real, resolved
  SG13CMOS5L PDK install. `bandgap_top.spice`'s hierarchical expansion was
  checked directly against its own header's wiring table (`core.fb <-
  amp.out`, `core.sns1 -> amp.in_n`, `core.sns2 -> amp.in_p`, `startup.sns1
  <- core.sns1`, `startup.fb -> core.fb`) and confirmed to expand
  `bandgap_core.sym`/`bandgap_amp.sym`/`bandgap_startup.sym` into the
  correct **SG13CMOS5L** (`pnpMPA`-based) subcircuit bodies, not SG13G2's —
  see "Tooling/PDK friction encountered" below for a real symbol-resolution
  bug this surfaced and fixed.
  **Regression check** (this issue's own acceptance criterion): both
  `PDK=ihp-sg13g2` (default) and `design/sg13cmos5l/bandgap_core.sch` were
  re-netlisted after the `design/xschemrc` fix below and confirmed
  unaffected — SG13G2's `bandgap_top.sch` still expands to its own
  `npn13G2`-based subcircuits with zero errors, and SG13CMOS5L's
  `bandgap_core.sch` (issue #64) still netlists standalone with zero
  errors.
- **Informal closed-loop sanity check (NOT `sim/` evidence)**: a single
  nominal-corner (`typ`/`mos_tt`/`res_typ`, 27°C, `vdd=3.3V`) transient,
  modeling `sim/closed-loop-startup/testbench/tb_closed_loop_startup.spice.tmpl`'s
  fixture shape (a `vdd` ramp `PWL(0 0 200u 3.3 2m 3.3)`, the same
  `rshunt=1e9 gmin=1e-9` convergence aids that testbench's own header
  documents as needed for the numerically stiff early-ramp instant) but
  hand-run in this environment rather than landed as a `sim/`
  testbench/script (that remains #65's scope) — co-simulating all three
  new netlists (`bandgap_core.spice` + `bandgap_amp.spice` +
  `bandgap_startup.spice`, wired exactly as `bandgap_top.sch` specifies) in
  one ngspice run, with real `pnpMPA`/PSP103/`r3_cmc` devices throughout
  (no substitutions), reusing this environment's prebuilt `.osdi` binaries.
  Result at `t=2ms` (fully ramped and settled):

  | Node/quantity | Result | `sim/closed-loop-startup/README.md`'s pass/fail bar (reused informally) |
  |---|---|---|
  | `sns1` / `sns2` | 0.780514 V / 0.780281 V | `\|sns1-sns2\| <= 20 mV` -> **0.233 mV, PASS** |
  | `fb` | 2.49710 V | interior, >=0.05V from either rail (`vss=0`, `vdd=3.3`) -> **0.80V from vdd, 2.50V from vss, PASS** |
  | `vref` | 1.19687 V | (informational — within 0.3% of the 1.2V target using `bandgap_core.sch`'s own hand-derived `R1`/`R2`) |
  | `det` | 4.18836 mV | `<= 0.2*vdd` (0.66V) -> **PASS, startup released** |
  | `i(XMKFB)` | 2.497 nA | `<= 50 nA` -> **PASS, startup released** |

  All three of `sim/closed-loop-startup/README.md`'s reused pass/fail
  criteria (startup released, loop closed, not railed) pass at this single
  nominal corner: the assembled block **self-starts and settles to a real
  closed-loop operating point**, confirming the amplifier's polarity
  derivation in `bandgap_amp.sch`'s header is correct (a polarity bug would
  instead rail `fb` to a supply, per that header's own warning) and that
  the ported startup circuit correctly releases once the core is running.
  This is a **single nominal data point**, not a PVT sweep, no mismatch/
  Monte Carlo, and no AC/phase-margin check (transient-only, no
  compensation capacitor exists yet) — reported here with the same
  evidentiary weight `design/README.md`'s own "issue #58" section gives its
  analogous first closed-loop check, not a verified spec claim. #65 is the
  issue that produces real PVT-cornered `sim/` evidence for this assembled
  block.
- **Not attempted**: PVT corner sweep, mismatch/Monte Carlo, AC/loop-
  stability (phase margin) analysis, DRC/LVS, layout. All explicitly out
  of this issue's scope (#65/#66).

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

### `design/xschemrc` symbol-resolution bug (issue #68, this repo's own config — not a klayout-tools gap)

`bandgap_top.sch` is the first schematic in either PDK variant's directory
to hierarchically instantiate repo-local symbols
(`bandgap_core.sym`/`bandgap_amp.sym`/`bandgap_startup.sym`) from
**inside** `design/sg13cmos5l/` — issue #64's `bandgap_core.sch` was a
single leaf schematic with no symbol placement, so it never exercised this
path. Netlisting `bandgap_top.sch` initially failed with
`l_s_d(): Symbol not found: sg13g2_pr/npn13G2.sym` — a symbol that
`bandgap_top.sch` never references directly. Root cause, confirmed by
inspecting the generated netlist's `sym_path`/`sch_path` comments: xschem
resolved the placed `bandgap_core.sym` (and `bandgap_amp.sym`) to
**`design/bandgap_core.sym`/`.sch` — the SG13G2 originals**, not this
directory's SG13CMOS5L ones, because `design/xschemrc`'s
`XSCHEM_LIBRARY_PATH` explicitly listed `design/` (added for the flat
SG13G2 schematics) but never listed `design/sg13cmos5l/` at all — so a
same-base-filename collision between the two directories silently resolved
to whichever directory `XSCHEM_LIBRARY_PATH` happened to list, **not** to
the schematic's own directory. This is not an SG13G2/SG13CMOS5L PDK gap —
it is this repo's own `design/xschemrc` search-path configuration not
having anticipated the per-PDK-variant subdirectory convention issue #64
introduced, once a schematic in that subdirectory actually needed
hierarchical symbol resolution. **Not filed at `klayout-tools`** (out of
that tracker's scope — it is this repo's own Tcl config file, not a PDK
resolver or deck gap).

**Fixed** in `design/xschemrc`: the invoking schematic's own working
directory (`[pwd]`, matching this repo's own documented per-PDK-variant
invocation convention — `cd design && xschem ...` for SG13G2,
`cd design/sg13cmos5l && xschem ...` for SG13CMOS5L, see "Running xschem"
above) is now searched **before** the flat `design/` directory. Verified
both directions after the fix: `design/sg13cmos5l/bandgap_top.sch` now
expands to the correct `pnpMPA`-based subcircuits (confirmed via the
generated netlist's `sym_path`/`sch_path` comments), and SG13G2's own
`design/bandgap_top.sch` still expands to its own `npn13G2`-based
subcircuits unchanged (the required regression check, above).
