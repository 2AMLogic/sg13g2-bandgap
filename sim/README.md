# sim/ — PVT-cornered testbenches and evidence records

This directory holds ngspice testbenches and their results for the SG13G2
bandgap. It follows the same evidence-record convention the fleet's more
mature ports (`gf180-bandgap`, `sky130-bandgap`) established, adapted where
SG13G2's own tooling forces a difference (noted explicitly below, not
silently). Per `CLAUDE.md`: **verification is the product, no claim without
a testbench**, and results here are **append-only evidence** — a re-run
mints a new, timestamped record; nothing under `records/`,
`netlist-snapshots/` or `corners/` is ever edited or deleted after it lands.

## PDK pin

Every record in this tree is generated against the SG13G2 PDK revision
pinned in [`pdk.json`](pdk.json) (currently `IHP-Open-PDK` tag `v0.3.0`,
fetchable via `klayout-tools`' `scripts/fetch-ihp-sg13g2.sh` — the same
fetch `design/README.md` documents for schematic-entry work). A record's own
`## PDK` field additionally states the exact `PDK_ROOT`/`ngspice -v` the run
used, so a later reader can tell whether their own environment matches
without re-deriving it from `pdk.json` alone.

`source env.sh` resolves `PDK_ROOT`/`PDK` the same way `design/xschemrc`
does (env vars first, then the usual open_pdks install prefixes) — every
testbench's `run_*.sh` sources it, and an interactive `ngspice` session can
too, so nothing here can silently drift onto a different install than what a
script used.

## Directory / naming convention

```
sim/
  README.md            this file — the authoritative convention
  pdk.json              pinned PDK revision (see "PDK pin" above)
  env.sh                 PDK_ROOT/PDK resolution, sourced by every testbench
  <experiment-slug>/     one directory per distinct claim under test
    README.md            testbench rationale, cold-start invocation, PDK pin,
                          and any device/model substitutions + why (required)
    testbench/
      tb_<name>.spice[.tmpl]   the testbench netlist or generation template
    run_*.sh              the cold-start entry point for this experiment
    netlist-snapshots/
      <record-id>/
        <corner-id>.spice    the exact generated netlist for that PVT point
    corners/
      <record-id>/
        <corner-id>.log      raw ngspice batch output for that PVT point
    records/
      <record-id>.md         append-only human-readable summary
      <record-id>.csv         append-only parsed/machine-readable data
```

- **`<experiment-slug>`** — short, kebab-case, one directory per distinct
  claim being tested (e.g. `core-open-loop-bias`), not per run.
- **`<record-id>`** — `<YYYYMMDD>-<HHMMSS>-<short-git-sha>` (UTC), e.g.
  `20260821-115433-5f66bd5`. A re-run mints a new `<record-id>`; nothing
  under an existing one is ever edited.
- **`<corner-id>`** — `<process>_<temp>c_<supply>v`, e.g. `typ_-40c_2.97v`,
  `bcs_27c_3.30v`, `wcs_125c_3.63v`. `<process>` names whichever PDK corner
  section(s) that testbench actually selected (see each testbench's own
  `README.md` — SG13G2 ships per-device-family corner files, `cornerHBT.lib`
  / `cornerMOShv.lib` / `cornerMOSlv.lib` / `cornerRES.lib` / `cornerCAP.lib`
  / `cornerDIO.lib`, each with its own section vocabulary — `hbt_typ`,
  `mos_ff`, `res_wcs`, ... — so which families and sections a given
  `<process>` label covers is testbench-specific, not fixed fleet-wide).

### Deliberate deviation from the gf180-bandgap/sky130-bandgap layout: per-corner-point netlist snapshots

Those two sibling repos' harnesses snapshot **one** netlist per
`<record-id>` (corner selection happens at simulate time via their harness,
external to the netlist file). That is not available here: ngspice's `.lib
"<file>" <section>` directive takes a literal section name, not a
parameter-substitutable expression — confirmed by direct test, not assumed
(`.lib "..." {my_param}` fails with `section definition {my_param} not
found`). So a testbench here that sweeps SG13G2's per-device-family corner
files generates **one netlist per PVT point** and snapshots all of them
under `netlist-snapshots/<record-id>/<corner-id>.spice`, a subdirectory
rather than a single file. Everything else (the `<record-id>` grammar, the
append-only rule, the `corners/`/`records/` layout) is unchanged.

## Summary record format

Each `records/<record-id>.md` states: the experiment/claim under test, the
netlist provenance (schematic vs. extracted, and the exact `design/`
git sha), the PDK revision + ngspice version actually used, the full list of
corner-matrix points run, the pass/fail result per point (and overall),
links to the testbench/snapshots/logs, and a timestamp/author. See
`core-open-loop-bias/records/*.md` for a real example, or
`core-open-loop-bias/run_pvt_sweep.sh` for how one is generated.

## Append-only rule

`records/*.md`, `records/*.csv`, `netlist-snapshots/**` and `corners/**`
files are **never** edited or deleted after creation. A correction or a
re-run always mints a new `<record-id>`; nothing is enforced mechanically
for this yet (unlike gf180-bandgap's `sim/check_records.py` lint step — that
is fleet-pattern infrastructure this repo has not built; a future CI pass,
tracked under #16, is the natural place to add it once more than one
experiment exists here). Until then this is enforced by convention and PR
review, the same way `spec/decision-records/`'s append-only rule is.

## Testbenches landed so far

- **[`core-open-loop-bias/`](core-open-loop-bias/README.md)** — the bandgap
  core's three real bipolar legs, current-biased directly (no mirror, no
  amplifier — neither exists yet), swept across the full
  temperature x supply x HBT/resistor-process-corner PVT grid. This is the
  first testbench to land (issue #10) and satisfies that issue's "at
  minimum one full PVT sweep is runnable" acceptance criterion. Read its own
  `README.md` for exactly what it does and does not claim, and for a real
  tooling gap this landing surfaced (below).

## Known environment limitation: SG13G2's MOS and resistor compact models need OSDI

SG13G2's PSP103 HV/LV-MOS model and its `r3_cmc`-based resistor models
(`rppd`, and presumably its sibling flavors `rsil`/`rhigh`, not yet checked)
are Verilog-A models only instantiable in ngspice via OSDI-compiled shared
libraries. `IHP-Open-PDK`'s `v0.3.0` release tarball does not ship prebuilt
`.osdi` binaries, and that release's own `versions.txt` names `openvaf
23.5.0` as the tool needed to build them — no prebuilt OpenVAF binary
release exists upstream (checked directly against the GitHub releases API)
and no `brew`/`pip`/`conda` package was found either, in the sandbox this
was authored in. Only the HBT device family (`npn13G2`, a native VBIC
level=9 model card — no OSDI needed) is currently simulatable here.

This is a genuine tooling gap, not a design or `klt` issue —
`design/README.md` already reasoned (correctly) that it is out of
`klayout-tools`' scope, since `klt` resolves PDK *paths*, not simulator
device-model builds. It blocks any testbench that needs the real PMOS
mirror or the real `rppd`/`rsil`/`rhigh` resistor compact models — i.e.
every testbench beyond `core-open-loop-bias`'s open-loop, ideal-bias
approximation. Tracked as a follow-up issue (filed alongside this PR); until
it lands, every testbench here that needs a MOS or resistor device will
need the same ideal-primitive substitution `core-open-loop-bias` uses, with
the same explicit disclosure.
