# sim/harness — the corner-grid harness decision (issue #275)

Every one of this repo's 23 experiments runs its PVT grid through a
`run_pvt_sweep.sh` shell loop that invokes `ngspice -b` once per point: 45
points for the `.op`/AC benches, 120 for the box-TC transients at up to 600 s
each. **The dispatch hosts this repo's agents run on forbid that** — their
operating rules direct multi-corner work to `klt sim`'s batch backend
(`KLT_SIM_BACKEND=batch` is exported there) and single corners only to the
local engine. So the five PEX re-runs #275 asks for could not be started
until the harness question was answered, and the answer is shared by every
other sim issue on those hosts.

This directory is that answer, as working code rather than a plan.

<!-- toc -->
- [Decision: `klt sim` (option 1), with an adapter](#decision-klt-sim-option-1-with-an-adapter)
- [What is proven, and how to re-prove it](#what-is-proven-and-how-to-re-prove-it)
- [Reported precision: 6 s.f. through `.meas`, 7 through an `.op` print](#reported-precision-6-sf-through-meas-7-through-an-op-print)
- [What still blocks the grids](#what-still-blocks-the-grids)
- [Upstream friction](#upstream-friction)
- [D2 and the mask option](#d2-and-the-mask-option)
- [Writing a new `klt sim` experiment](#writing-a-new-klt-sim-experiment)
<!-- /toc -->

## Decision: `klt sim` (option 1), with an adapter

#275 offered two options and a preference order. **Option 1 is adopted**: each
grid is expressed as a `klt sim` request (`corners`/`monte_carlo`), dispatched
by `klt sim` to whichever backend the host allows, and the returned JSON
report is translated into this repo's append-only evidence layout by a single
shared adapter. Option 2 (an operator-sanctioned run host for the existing
shell loops) is **not** adopted: it would buy one grid and leave the next
issue in the same position, and it is the opposite of where the hosts' own
rules point.

Three pieces, all in this directory:

| File | Role |
|---|---|
| `klt_corner_bundle.py` | Generates the single-file ngspice corner bundle `klt sim`'s one-`models.lib` request shape requires, from SG13G2's three per-device-family corner libraries. Also `--check-preflight`, which asserts the corner→section table has not drifted from `sim/lib/pvt_preflight.sh`'s own maps. |
| `klt_sim_evidence.py` | The adapter. `klt sim` report + a per-experiment record spec → `records/<id>.{md,csv}` + `corners/<id>/*.log` + `netlist-snapshots/<id>/*.spice`. Generic over experiments; all 23 can use it. |
| `probe/run_probe.sh` | The standing self-test: one corner end-to-end, plus five assertions (below). |

`sim/harness/` deliberately holds no `records/` directory, which is what keeps
`.github/scripts/check_evidence_formats.py` from treating it as an
experiment. Nothing here is evidence.

### Why the adapter is not optional

`klt sim`'s report is a *response document*. Three things it does not give you
that this repo's evidence format requires, each of which the adapter does and
each of which CI would otherwise catch as a format failure:

1. **The corner id.** `klt sim` names a point `typ/3.300V/27C`; this repo's
   grammar is `<process>_<temp>c_<supply>v` (`typ_27c_3.30v`), and that
   spelling has to agree with the CSV's own `temp_c`/`vdd_v` cells or check C
   fails on a set difference.
2. **A self-contained netlist snapshot.** The deck `klt sim` generates only
   `.include`s the netlist body, so copying it verbatim would commit a
   snapshot holding *no device instances at all* — and D2 parses the
   snapshot's own text for the DUT's devices. It would not fail loudly; it
   would silently downgrade a hard freshness check to "snapshots inline none
   of its instances". The adapter splices every local `.include`/`.lib` in.
3. **No absolute host paths.** The same pass rewrites surviving PDK paths to
   `${PDK_ROOT}`-relative form, so a record does not pin one machine's
   directory layout. (`klt sim` applies the same discipline to its own
   `environment.models_lib` field — klayout-tools #1261/#1274.)

Everything *narrative* in a record — Claim, provenance, the corner-matrix
sentence — comes from a per-experiment spec JSON, never from the shared
adapter. The adapter owns the mechanics and the parts CI checks; each
experiment keeps its own argument.

## What is proven, and how to re-prove it

```bash
sim/harness/probe/run_probe.sh        # ~15 s, one corner, local
```

It runs one corner (typ / 27 °C / 3.30 V) of `sim/core-open-loop-bias`'s own
committed claim through `klt sim` and asserts, in order:

1. `klt_corner_bundle.py`'s corner→section table still matches
   `sim/lib/pvt_preflight.sh`.
2. ngspice honours a `pre_osdi` card in a `.control` block reached through
   `.include` — the one deviation from `klt sim`'s netlist-body contract an
   OSDI PDK forces (see below).
3. A nested corner-bundle `.lib` resolves.
4. The measured point reproduces `sim/core-open-loop-bias`'s committed
   `records/20261001-082455-f748685.csv` row to within 2 × 10⁻⁵ V. Measured
   when this landed: `vref` 1.05271 V against the record's 1.052707 V
   (**3 µV**), `r1_ohm` 66057.1 Ω against 66057.04 Ω (**0.06 Ω**). The
   harness moves no number.
5. `klt_sim_evidence.py`'s output satisfies `check_evidence_formats.py`'s own
   `check_record()`, and its snapshot inlines **all** of
   `design/netlist/bandgap_core.spice`'s instances (285 instances inlined, 0
   of the DUT's absent) with no absolute host path.

Point 4 is worth stating plainly because it is the only thing that makes the
harness swap safe: the `.op` claim is measured as a short transient plus
`.meas tran … at=40n` (ngspice implements no `.MEASURE OP` — there is no
sweep variable for a measurement to search over, and `klt sim` rejects a
`.meas op` card before it reaches the engine). That substitution is
numerically free here to five digits, which is the evidence for it. A bench
with real settling dynamics must re-establish that for itself rather than
inherit this result.

**Five digits is where the agreement was *checked*, not where either number
runs out.** The committed record carries seven significant figures and the
`klt sim` path reports six, so the comparison in point 4 cannot be tightened
past the coarser of the two no matter how well the two agree physically. That
one-digit difference is a property of the `.meas` print format, not of the
transient-for-`.op` substitution and not of the circuit — it would be there on
a bench with no settling dynamics at all. The two limits are separate and the
next section states the precision one on its own terms, because conflating
them would read the format ceiling as physics.

## Reported precision: 6 s.f. through `.meas`, 7 through an `.op` print

**Disposition: 6 significant figures is accepted for `klt sim` records.**
Recorded here *before* #278 mints its first grid through the adapter, so that
the first committed record is not where the question gets asked. The rest of
this section is the disclosure and the arithmetic behind that disposition.

### The delta

Both paths, same host, same corner (typ / 27 °C / 3.30 V), same engine
(ngspice 46):

| quantity | `run_pvt_sweep.sh` (`.op` print) | `klt sim` (`.meas`) | resolution lost |
|---|---|---|---|
| `vref_v` | `1.052707e+00` | `1.05271e+00` | 10 µV |
| `r1_ohm` | `6.605704e+04` | `6.60571e+04` | 0.1 Ω |

The two agree to every digit the coarser one reports. **This is a
report-format ceiling, not a physics limit, and not an error** — the solver
resolved the seventh figure in both runs; only one of the two extraction paths
can print it.

### Where the digit goes

ngspice prints `.meas` results at a **fixed 6 significant figures**, and
`.options numdgt=N` does not widen them. That is reproducible in eleven lines
with no PDK and no models at all:

```
.options numdgt=10
V1 in 0 1
R1 in out 1k
R2 out 0 2.0001k
C1 out 0 1f
.control
tran 1n 10n
meas tran vout find v(out) at=5n     $ -> vout = 6.66678e-01   (6 s.f.)
print v(out)                         $ -> 6.666778e-01         (7 s.f.)
quit
.endc
```

The exact value is `2.0001/3.0001 = 0.666677777…`. So:

- It is **not** `klt_sim_evidence.py`. The adapter formats `.6e` and is
  faithful to its input.
- It is **not** `klt sim`'s JSON report, which carries exactly what `.meas`
  printed.
- It **is** the `.meas` card, which is the only measurement form `klt sim`'s
  request schema can express — there is no `print`/`wrdata`/rawfile extraction
  form. `run_pvt_sweep.sh` gets seven figures because it scrapes the `.op`
  print block (`grep -E '^v\(vref\)' | awk '{print $3}'`), and its derived
  columns are recomputed in `awk` at `%.6e` from those.

**The ceiling is invisible in the record's own formatting**, which is the part
worth stating loudly. The adapter's `.6e` emits a seven-digit field whose last
digit is a padding artifact of the print format: the probe's own output is
`1.052710e+00`, a trailing zero where the `.op` path had a `7`. Nothing about
the file announces that its last digit carries no information. That is exactly
why this is written down rather than left to be re-derived by whoever next
diffs a `klt sim` record against a `run_pvt_sweep.sh` one.

### Why 6 s.f. is accepted

Worst case the quantization is ±5 µV per endpoint on a volt-scale node, ±10 µV
on a difference of two. Against every live claim:

| Claim | Its own scale | 10 µV is |
|---|---|---|
| `vref` PVT spread vs DR-0011's **±0.5 %** trimmed budget | ±5.25 mV on a 1.05 V reference | 0.2 % of the budget |
| Box-method TC (`*-boxtc`, DR-0010, against the ratified < 50 ppm/°C row) | measured box drift **1.5–3.5 mV** over the 165 °C span (`closed-loop-vref-pvt-boxtc` 2026-09-21: 8.90 ppm/°C typ, 19.77 ppm/°C worst at wcs) | ≤ 0.06 ppm/°C of an 8.9–19.8 ppm/°C result, i.e. ≤ 0.7 % |
| The ±1-code box-TC **delta cap**, ~18.75 ppm/°C (DR-0011's ~0.175 % budget headroom, via `closed-loop-vref-boxtc-trim`) | a difference of two box TCs | ≤ 0.12 ppm/°C, 0.6 % of the cap |
| Untrimmed core TC, 349–376 ppm/°C (DR-0011) | — | three orders of magnitude below |
| PSRR / Zout in dB | `psrr_dc_db` 61.3862, `zout_dc_db` 96.9533 | **already 6 s.f. in the committed records** — no change at all |

Two notes on that table, because they are the reason the disposition is safe
rather than merely convenient:

- **Derived quantities are computed before they are rounded, on both paths.**
  `closed-loop-vref-pvt-boxtc/run_pvt_sweep.sh` forms `box_tc` from the
  full-precision per-point `vref`, then prints `vmin`/`vmax` at `%.5g` and
  `box_tc` at `%.3f` — so that bench's committed `-boxtc.csv` endpoints are
  **already** reported at five figures, coarser than the `.meas` ceiling under
  discussion. The 6-s.f. input is not the binding constraint on that claim.
- **The quantization is not below the noise of the printed claim**, and this
  section does not pretend otherwise: ≤ 0.06 ppm/°C would land in `box_tc`'s
  third printed decimal. It is immaterial relative to the *claim gates*
  (≤ 0.7 % of the smallest measured TC, 0.6 % of the ±1-code delta cap), not
  relative to the last digit of the printout.

### What the disposition does not cover

- **A claim whose margin is within ~100× of 10 µV.** None exists today. If one
  is ever written, it must establish its own precision floor rather than
  inherit this disposition — the same rule point 4 above applies to the
  transient-for-`.op` substitution.
- **A measurement formed as a difference of two large, separately-`.meas`-ed
  numbers.** Relative precision there is set by what survives the subtraction,
  not by the 6 s.f. of each operand, and can be several digits worse. Prefer a
  derived `.meas … find par('…')` evaluated inside the engine, or recompute
  from a `.op`-style column, over subtracting two reported values.
- **Re-measuring an existing record and comparing at 7 s.f.** A
  `klt sim` re-run can only ever be checked against a `run_pvt_sweep.sh`
  record to six figures; `probe/run_probe.sh`'s 2 × 10⁻⁵ V anchor tolerance is
  set with that in mind and must not be tightened below the ceiling.

Filed upstream as **klayout-tools#2681** (see Upstream friction below), which
asks for an extraction path not bounded by `.meas`'s print format — rawfile or
`print`-block extraction — and, failing that, for the ceiling to be stated in
the `measurements` contract and surfaced as a report field so a consumer can
pin it as provenance instead of discovering it by diff. If that lands, these
records can be re-minted at full solver precision with no change to any
request.

## What still blocks the grids

**The five grids are not re-run by this PR, and the five waivers in
`sim/evidence-freshness-waivers.json` are deliberately left in place.** The
reason is specific and verifiable, and it is not a `klt sim` problem:

> `klt sim --backend batch` can only run on a PDK already baked into the
> batch fleet's AMI, and the SG13G2 PDK is not one of them.

Checked against the live fleet rather than inferred (2026-10-01, `klt`
0.6.0+gf0615edf6037):

| What | State |
|---|---|
| Job bucket, launch template, security group, submit identity | **present** — `aws sts get-caller-identity --profile batch-runner-submit` resolves, the bucket lists, and it already holds prior `klt-sim-*` job trees. The fleet is real and has run `klt sim` before. |
| Pinned AMI | **present** — `eda-batch-runner-20260921-…` (`Component=eda-batch-runner`), 2026-09-21. |
| PDKs on that AMI | **`sky130A` + `gf180mcuD` only** — `2am`'s `infra/aws/batch-image-pins.env` pins `PDK_VARIANTS="sky130A gf180mcuD"` under `BAKED_PDK_ROOT=/opt/pdk`; `batch-image.md` describes the image's "open-PDK working set" as exactly those two. No `ihp-sg13g2`. |
| OSDI models on that AMI | **no bake step exists** — and SG13G2 needs one: IHP-Open-PDK v0.3.0 ships the PSP103/r3_cmc/mosvar Verilog-A *sources*, not compiled `.osdi` binaries. `sim/tools/build-osdi.sh` is this repo's own compile step and has no counterpart in the image bake. |
| Shipping the PDK as a job input instead | **not expressible** — `klayout_tools.sim_batch._build_batch_job_spec` ships exactly two inputs, the netlist and the request document; `models.pdk`/`models.pdk_root` are passed as *names* for the instance to resolve locally. There is no extra-inputs field. |

So the chain is: harness built and proven ✅ → batch backend reachable ✅ →
batch image cannot simulate SG13G2 ❌. The remedy is a change to the fleet
image spec (add `ihp-sg13g2` to `PDK_VARIANTS` and an OSDI compile step to
the bake), which is an operator/infra action in `2AMLogic/2am`, tracked here as
**#277** (`loom:operator-only`) — not something a Builder can do from a dispatch
host — and per those hosts' own rules, "if a
tool is genuinely missing or wrong, say so in your PR/issue; the fix is a
change to the worker spec, not to this host."

One sizing note for whoever picks that up: the fleet's
`BATCH_MAX_JOB_SECONDS` is 3600 s. The 45-point `.op`/AC grids fit easily
(the probe's corner runs in well under a second). The 120-point box-TC
transient grid at up to 600 s per point does **not** fit one job serially; it
needs either `klt sim --hosts`-style sharding on the batch backend or a
raised per-job ceiling, and that should be settled before that grid is
submitted rather than discovered by a timeout.

The five grid re-runs themselves are **#278**, which depends on #277 and
carries the remaining template work (a PEX netlist-body *generator*, the hub-tag
renumbering, the illegal merged-tap-net name, `XRU<n>` naming for D2, the
transient `save` card, and #272's one-point sanity anchor).

**What must not happen in the meantime:** nobody should "just run the grids"
by looping `ngspice -b` on a dispatch host, or by widening
`probe/run_probe.sh`'s one corner. That is the rule this whole directory
exists to respect.

One note for a future reader re-checking the fleet state above: a plain
`batch-fleet-provision.sh plan` run from a dispatch host reports the bucket,
launch template and AMI as **absent**, because it defaults to
`BATCH_ADMIN_PROFILE=2am-admin`, which has no credentials there. That is a false
negative — re-check with `--profile batch-runner-submit` before concluding the
fleet does not exist.

## Upstream friction

Per this repo's friction protocol (`CLAUDE.md`), each place `klt` was awkward
or missing a capability for this work is filed generically at
`2AMLogic/klayout-tools` rather than worked around silently:

| Gap | Worked around here by | Filed |
|---|---|---|
| No request field for an **engine preload command**. A PDK whose compact models are OSDI/Verilog-A must execute `pre_osdi` *before* the netlist is parsed; `klt sim`'s generated `.control` block emits only `alter`, the analysis, `write`, `quit`, with no extension point. | A `.control pre_osdi …` block in the netlist **body** — which the netlist-body contract documents as unsupported. Verified to work on ngspice 46; `run_probe.sh` asserts it keeps working. | klayout-tools#2666 |
| `models.lib` is a **single file**. A PDK that splits corner definitions across several per-device-family `.lib` files cannot be expressed; `corners.process[].sections` multiplexes sections *within* one file. | `klt_corner_bundle.py` synthesizes a bundle `.lib` whose sections are this repo's corner labels. | klayout-tools#2667 |
| The **batch backend ships only** the netlist and the request, so a grid can only run against a PDK pre-baked into the fleet image — there is no way to declare the model library (or preloadable model binaries) as job inputs. | Nothing. This is the standing blocker above. | klayout-tools#2668 |
| **Measurements are expressible only as `.meas` cards**, and ngspice prints `.meas` results at a fixed 6 significant figures that `.options numdgt=N` does not widen. There is no `print`/`wrdata`/rawfile extraction form, so reported precision is capped one digit below what the `.op`-print path this harness replaces achieves. | Nothing — the digit is unrecoverable through the request schema. Disclosed and dispositioned above ([Reported precision](#reported-precision-6-sf-through-meas-7-through-an-op-print)): 6 s.f. accepted, immaterial to every live claim. | klayout-tools#2681 |

A smaller one, noted but not filed because the body absorbs it cleanly: the
request `options` object is the *runner's* (timeout, artifacts, workers) and
has no SPICE-`.options` passthrough, so a solver setting like `reltol` is a
property of the netlist body rather than of the request.

## D2 and the mask option

The other decision #275 required. The layout realises **one** trim code (128)
by metal option, so a faithful post-layout netlist of it has no `trim_code`
parameter, no `XXTRIM` instance and no `RS0`-`RS7` cards: the closed straps
are real metal (wire resistance) and the open one is simply absent. Compared
against the unresolved schematic instance set, such a snapshot reads as
`<absent>` on 264 instances — even though the design did not change, only its
representation did.

**Disposition (b) is adopted**: `check_evidence_formats.py`'s D2 rule now
*resolves* the mask option before comparing, excluding the behavioural
`RS<bit>` strap cards and the subcircuit call from the DUT signature while
keeping the ladder's own 255 units in it. This is the same convention
`layout/lvs_reference.py`'s `convert_with_metal_options` already applies to
the LVS reference, so the two sides of the compare agree on what a
mask-option netlist *is*.

Disposition (a) — keeping a `.subckt bandgap_trim` shell with the behavioural
straps inside a PEX template — was rejected for the reason #275 itself names:
it would make the bench model a code the layout does not realise whenever
`trim_code != 128`, which is a trap set for the next reader.

What this deliberately stops checking, stated rather than left implicit: with
the strap cards out of the expected set, D2 no longer notices *which* code a
snapshot realises — the 255 units are geometrically identical and D2 compares
no node names. That axis is guarded by LVS instead, which is where it belongs:
`convert_with_metal_options` reads the realised code from the same
`.param trim_code` default the layout's own `TRIM_CODE` must agree with, so a
code mismatch surfaces as an LVS failure. D2's question is "is this the same
design?", not "is this the same mask option?".

Three self-test cases in `.github/scripts/test_check_evidence_formats.py`
hold that line: a code-fixed snapshot passes, a resized ladder unit is still
stale, and a subcircuit needs *both* signatures (`RS<bit>` cards **and** a
`.param trim_code=` default) before it is treated as a mask option, so an
ordinary subcircuit that happens to name a resistor `RS1` is not swallowed.

## Writing a new `klt sim` experiment

Four files, three of which are the experiment's own:

1. **Netlist body** (`sim/<exp>/testbench/*.body.spice`) — a circuit body: no
   `.lib`, no `.temp`/`.options temp=`, no analysis card, no `.end`. It *does*
   carry the `.control pre_osdi …` block (see Upstream friction) and any
   `.options` the bench needs, and every rail source it wants swept must be a
   named, alterable element.
2. **Request** (`sim/<exp>/testbench/*.request.json[.tmpl]`) — `corners`
   (`process` from `klt_corner_bundle.py`'s labels, `supply_v`,
   `temperature_c`), `analysis`, `measurements` (one `.meas` card per CSV
   column, including derived ones via `find par('…')`), and
   `options.keep_artifacts: true` — the adapter needs the per-corner log and
   deck, and will refuse to mint a record without them. Every column so
   measured arrives at **6 significant figures**, not more — read
   [Reported precision](#reported-precision-6-sf-through-meas-7-through-an-op-print)
   before setting a `pass_requires` threshold or a tolerance against one, and
   prefer a derived `.meas` over subtracting two reported values.
3. **Record spec** (`sim/<exp>/testbench/*.record-spec.json`) — the
   experiment's own narrative plus `pass_requires` (the measurements whose
   absence makes a point FAIL even when the solve converged) and
   `extra_columns`.
4. **Runner** (`sim/<exp>/run_klt_sim.sh`) — generates the bundle, substitutes
   the body/request paths, calls `klt sim`, calls the adapter. `probe/run_probe.sh`
   is the worked example.

`sim/harness/probe/` holds a complete instance of all four.
