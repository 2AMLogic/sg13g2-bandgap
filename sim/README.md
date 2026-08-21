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
  core (three real `npn13G2` legs + the real `sg13_hv_pmos` mirror + both
  real `rppd` resistors), with the mirror biased open-loop from a
  diode-connected replica leg because no amplifier exists yet, swept across
  the full temperature x supply x HBT/MOS/resistor-process-corner PVT grid
  (45 points). First testbench to land (issue #10, as an ideal-primitive
  approximation); converted to real compact models by issue #22.
- **[`startup-trip-point/`](startup-trip-point/README.md)** — the startup
  circuit (`design/netlist/bandgap_startup.spice`): does it engage at cold
  start and release once the core is running, across the same PVT grid
  (45 points). Every device in that netlist is OSDI-gated, so this
  experiment could not exist at all before issue #22 — which makes it the
  end-to-end proof that the OSDI toolchain below works. Its records
  originally surfaced a real 125 °C worst-case margin observation (a
  cross-bench comparison against `core-open-loop-bias`'s own records); see
  its README.
- **[`startup-core-handover/`](startup-core-handover/README.md)** — the
  direct follow-on to that margin observation (issue #24): co-simulates
  `bandgap_core` + `bandgap_startup` in one netlist, sharing their real
  `sns1`/`fb` nodes, under a **transient** `vdd` ramp — settling what the
  cross-bench comparison above could only suggest. Confirmed (and
  substantially widened) the margin problem pre-fix, then confirmed the fix
  (widening `bandgap_startup`'s `XMSENSE`,
  [decision record 0003](../spec/decision-records/0003-startup-sense-nmos-resize.md))
  post-fix, across the same 45-point PVT grid.
- **[`core-open-loop-bias-pex/`](core-open-loop-bias-pex/README.md)** and
  **[`startup-trip-point-pex/`](startup-trip-point-pex/README.md)** — issue
  #14's post-layout (PEX) counterparts to the first two experiments above:
  same claims, same 45-point PVT grids, but the MOS devices' geometry comes
  from `klt extract --deck sg13g2 --parasitics` against the routed
  `layout/bandgap_core/bandgap_core.gds` /
  `layout/bandgap_startup/bandgap_startup.gds`, not the schematic. Both
  read the pre-layout (schematic-only) records above unchanged — this is
  new, additional evidence, not a replacement. Each README states in full
  what the extraction does and does not model (bipolar/resistor devices
  are not recognised by the sg13g2 deck and are schematic-sourced;
  wire parasitics are zero — the deck's own R/C coefficient tables are
  empty for this layout's metal levels). `startup-trip-point-pex`'s own
  cross-bench comparison against `core-open-loop-bias-pex` originally
  found that `layout/bandgap_startup.gds` still drew `XMSENSE` at the
  pre-decision-record-0003 `w=2u` (the schematic was widened to `w=10u`,
  the layout not yet regenerated to match) — reproducing decision record
  0003's exact same 4-point, 125 °C margin bug at the layout level. Issue
  #32 regenerated the layout with `XMSENSE` at the matching `w=10u`; the
  same cross-bench comparison against the corrected layout now clears at
  all 45 points — see that experiment's README for the full before/after
  writeup.

## OSDI device models: required setup, and how they are built here (issue #22)

SG13G2's PSP103.6 HV/LV-MOS models and its `r3_cmc`-based resistor models
(`rppd`, `rsil`, `rhigh`) are Verilog-A compact models. ngspice can only
instantiate them through OSDI-compiled shared libraries, and
`IHP-Open-PDK` `v0.3.0` (the release [`pdk.json`](pdk.json) pins) ships the
Verilog-A **sources** but no prebuilt `.osdi` binaries. A freshly-unpacked
PDK therefore has no `libs.tech/ngspice/osdi/` directory at all, and every
MOS and every resistor in `design/netlist/*.spice` fails to simulate. Only
the HBT family (`npn13G2`, a native VBIC level=9 model card) works without
this step.

**Cold-start setup — one command:**

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # fetch pinned compiler, build models
sim/tools/build-osdi.sh --check         # verify only (models present + loadable)
```

`build-osdi.sh` is idempotent: it exits early if the models already build
and load, re-downloads nothing it has cached under
`~/.cache/sg13g2-bandgap` (override with `SG13G2_TOOLS_CACHE`), and writes
its output to `$PDK_ROOT/$PDK/libs.tech/ngspice/osdi/` — the location the
PDK's own `.spiceinit` and `install.py` use. Nothing it produces is
committed to this repo: `.osdi` files are platform-specific native shared
libraries, so they are *built*, never *vendored*, here. `sim/env.sh`
exports `SG13G2_OSDI_DIR` and warns when the models are missing, and each
`run_*.sh` preflights with `build-osdi.sh --check` before claiming a
result.

### The approach, and why the alternatives were rejected

**Chosen: compile the PDK's own Verilog-A sources with a checksum-pinned
prebuilt OpenVAF-Reloaded (`openvaf-r` `v24.0.1mob`).**

- The compact-model *code* that reaches the simulator is the PDK's own,
  byte for byte, from the tarball already `sha256`-pinned in `pdk.json`.
  The only third-party binary in the chain is the **compiler**, pinned by
  `sha256` against GitHub's own published release digest and re-verified on
  every run (`build-osdi.sh` deletes the download and exits non-zero on a
  mismatch, rather than compiling with an unverified toolchain).
- `openvaf-r` is not an arbitrary third-party pick: the PDK's own
  `libs.tech/verilog-a/openvaf-compile-va.sh` and
  `libs.tech/ngspice/install.py` both look for `openvaf-r` **first** and
  fall back to `openvaf` only if it is absent. This build uses the same
  flags (`-D__NGSPICE__`) and the same four-model list those scripts use,
  so what lands in `osdi/` is what the PDK intends ngspice to load.

**Rejected — build upstream OpenVAF 23.5.0 from source** (the version the
PDK's `versions.txt` names). That release ships zero binary assets
(re-verified 2026-08-21 via the GitHub releases API) and its last upstream
push was 2024-08; building it requires a patched LLVM of a specific major
version, which is a much larger and far less reproducible cold-start
dependency than a checksummed 60 MB compiler archive — and it would still
produce the *same* models from the *same* PDK sources. The reproducibility
this repo needs is "a cold-start agent gets identical `.osdi` behavior from
one documented command", which the pinned-compiler path satisfies with
strictly fewer moving parts.

**Rejected — vendor prebuilt `.osdi` binaries** (from a third party, or by
committing this machine's build). This is the supply-chain-worst option and
the one this repo should never take: a `.osdi` is an opaque native shared
library that ngspice `dlopen`s, so a subtly-wrong or hostile model would
pass every testbench here *looking* correct, and the evidence records would
silently inherit it. They are also per-OS/per-arch, so a committed binary
would be dead weight for most contributors. Building from the PDK's
auditable Verilog-A source keeps the model text reviewable.

### Verified, not asserted

The build is **deterministic**, checked by wiping both the compiler cache
and the output directory and rebuilding cold: the four `.osdi` files came
back byte-for-byte identical. On `macos-aarch64` with
`openvaf-r v24.0.1mob` against IHP-Open-PDK `v0.3.0` (2026-08-21) the
`sha256` sums were:

```
e91a2addddaf967874049d6e9c118be0da1c84e3ec88da669d78c1f84bc2df31  psp103.osdi
aee0280b0de1cb6dbb06b183f5868931a86b5278b5b88f70dd5d3da4e966f2f5  psp103_nqs.osdi
8e78a6d4af23fa978df660a40fe585bc1caf38fd36e6b25aea55795c5a4535dd  r3_cmc.osdi
ac2b43d50c720a1b060f5d4b11de0f00ff539fa433ca481fe9ec61c8bd0667d4  mosvar.osdi
```

Those sums are a convenience for confirming you built the same thing on the
same platform — they are **not** a portability claim: a different OS/arch
(or a different compiler pin) will legitimately produce different bytes,
which is exactly why the binaries are rebuilt rather than committed.

`sim/tools/build-osdi.sh --check` runs a real `ngspice -b` batch that
instantiates `sg13_hv_pmos`, `sg13_hv_nmos` and `rppd` against the PDK's
own `cornerMOShv.lib`/`cornerRES.lib` sections and fails loudly on
`Unable to find definition of model`, `Unknown model type`, or a missing
operating point. Both testbenches below run real OSDI-backed MOS and
resistor devices across the full PVT grid — see their records for the
evidence.

### Platform note (macOS, arm64)

The published OpenVAF-Reloaded macOS bundles carry a code signature that no
longer matches their own bytes (`codesign -v lib/libLLVM.dylib` →
`invalid signature (code or signature have been modified)`), so macOS
`SIGKILL`s `openvaf-r` the instant `dyld` maps the library — observed as a
silent exit `137` with no output whatsoever, which is easy to misread as
"the binary is broken". `build-osdi.sh` re-signs the bundled dylibs ad-hoc
(`codesign --force --sign -`) after the `sha256` check passes, which is
what makes the compiler runnable. This is a note for the next agent who
hits exit 137, not a security exception: the bytes are verified *before*
they are re-sealed.

This whole area is a genuine PDK-tooling gap, not a `klt`/`klayout-tools`
gap — `klt` resolves PDK *paths*; it does not compile or vendor simulator
device models. Per `CLAUDE.md`'s friction protocol, that means it belongs
here (issue #22), not on the `klayout-tools` tracker, which is exactly
where `design/README.md` already placed it.

### Platform note (linux, x86_64)

Verified working for the first time in issue #14, with a similar but
distinct fix needed: the pinned `openvaf-r-v24.0.1mob-linux-x86_64` release
ships `lib/libLLVM.so.21.1` as a **dangling symlink** to
`../../x86_64-linux-gnu/libLLVM.so.21.1` — unlike the macOS bundle (which
ships the real `dylib`), the Linux release assumes the *host* provides a
system-installed LLVM 21, which no current Ubuntu LTS ships as a package
(24.04/noble tops out at `libllvm20`).

As of [issue #31](https://github.com/2AMLogic/sg13g2-bandgap/issues/31),
`build-osdi.sh` handles this automatically — no manual pre-step required.
On `Linux/x86_64` it fetches and sha256-verifies the real
`libLLVM.so.21.1` from the official LLVM apt repository's `libllvm21`
package for `noble` (the same fetch-and-verify pattern already used for the
`openvaf-r` compiler tarball), unpacks it unprivileged with `dpkg-deb -x`
(no root or system install needed), and points `LD_LIBRARY_PATH` at it for
its own `openvaf-r` invocations only. The pin (package URL, sha256,
release codename) lives in `sim/pdk.json`'s
`osdi_toolchain.libllvm21_deb`, alongside the `openvaf-r` asset pins. If
`dpkg-deb` is not on `PATH`, `build-osdi.sh` falls back to printing the
exact copy-pasteable manual workaround rather than failing silently.
