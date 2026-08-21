# core-open-loop-bias

The first PVT-cornered testbench for `design/bandgap_core.sch` /
`design/netlist/bandgap_core.spice` (issue #9's schematic, issue #10's
testbench infrastructure).

## What this testbench claims, and what it does not

It exercises the bandgap core's three real bipolar legs (`XQ1`/`XQ2`/`XQ3`,
`npn13G2`, exact geometries copied from `design/netlist/bandgap_core.spice`)
across the full temperature x supply x process-corner PVT grid, and confirms
the PTAT delta-VBE / CTAT VBE / summed vref behavior moves the way a bandgap
core is supposed to. It is **infrastructure and plumbing evidence** — proof
the corner-sweep mechanism actually runs, cold-start, against a real PDK —
**not** a claim against any ratified spec row: no spec row is ratified yet
(`spec/porting-plan.md` §6 is still a draft table; ratification is tracked
separately, see #13). Do not cite this record's `vref` number as "the
bandgap's output voltage" in any spec/README claim without first checking
whether the closed-loop, mirror-biased circuit (still unbuilt — see below)
reproduces it.

## Known simulation gap: OSDI-gated device models

The real `bandgap_core.spice` netlist has two device types this testbench
**cannot** instantiate in this environment, both traced independently
(not merely asserted) by attempting to load them and reading the failure:

1. **`XM1`/`XM2`/`XM3` (`sg13_hv_pmos` current-mirror legs).** SG13G2's
   HV-MOS compact model is PSP103.6, instantiated in ngspice only through
   an OSDI-compiled Verilog-A shared library
   (`libs.tech/ngspice/osdi/psp103.osdi`, loaded by the PDK's own
   `.spiceinit`). IHP-Open-PDK's `v0.3.0` release tarball does not ship a
   prebuilt `.osdi` for this model, and this PDK release's own
   `versions.txt` names `openvaf 23.5.0` as the tool required to build one
   — no OpenVAF build (no prebuilt binary release exists upstream; no
   `brew`/`pip`/`conda` package found either) was available in the sandbox
   this testbench was authored and run in. Separately, and independent of
   the OSDI gap: no error amplifier exists yet to force `sns1 = sns2` and
   close the mirror's own feedback loop (`design/README.md`, issue #9's
   explicit scope cut) — so even a working PSP103 model could not be
   correctly biased by this testbench alone.
2. **`XR1`/`XR2` (`rppd` resistors).** This is a **new finding**, not
   previously documented: `rppd`'s own compact model (`r3_cmc`, in
   `resistors_mod.lib`) is *also* only instantiable via the same
   OSDI-shared-library mechanism (`libs.tech/ngspice/osdi/r3_cmc.osdi`,
   also unbuilt here) — confirmed by the same `Unable to find definition
   of model xr2:res_rppd` failure this testbench's author hit before
   substituting the workaround below. `design/README.md`'s account of
   issue #9's informal check mentions using "ideal R primitives" but does
   not explain that `rppd` itself needs OSDI, not just the MOS devices —
   this testbench's investigation independently re-derived and confirms
   that reason.

**Substitutions made, and why they are not arbitrary:**

- `XM1`/`XM2`/`XM3` -> ideal `I` current sources, 5 µA/leg — the same
  nominal current issue #9's own informal single-point check used
  (`design/README.md`), so this testbench's nominal-corner result is
  directly comparable to that earlier check (and does closely reproduce
  it: `dVBE(Q1,Q2) ≈ 55.2 mV` at 27 °C nominal here vs. `55.2 mV` reported
  there).
- `XR1`/`XR2` -> ideal `R` devices, value computed *inside the generated
  netlist* as `{rsh_rppd * (drawn_L / drawn_effective_W)}`, where
  `rsh_rppd` is loaded from the **real** `cornerRES.lib` `.LIB res_<corner>`
  section for whichever process corner is being run — i.e. the per-corner
  sheet-resistance number is pulled from the PDK's own corner deck, not
  hand-transcribed or held constant across corners. What is **not**
  modeled: `r3_cmc`'s TC nonlinearity beyond the linear `rsh` term,
  parasitic cap/self-heating terms, and any mismatch. See the template's
  own header comment for the exact formula.

**Net effect on corner coverage**: the process-corner axis this testbench
actually sweeps is the **HBT+resistor-sheet-resistance** axis
(`{typ, bcs, wcs}`, pairing `cornerHBT.lib`'s and `cornerRES.lib`'s own
matching corner labels — not a mapping this testbench invented). It does
**not** sweep `cornerMOShv.lib`'s MOS process corners (`mos_tt/ss/ff/sf/fs`)
at all, since no MOS device is instantiated. A future testbench that
exercises the real mirror (once OSDI models are built/vendored — see the
follow-up issue this PR files) will need to add that axis.

**Supply (`VDD`) coverage**: this open-loop bench sweeps `VDD` at
`{2.97, 3.30, 3.63}` V (3.3 V ±10 %, per `spec/porting-plan.md` §4/DR-0002)
because the required PVT grid's supply axis must be exercised structurally
even before a mirror/amp exists to make the result supply-*sensitive*.
Ideal current sources have no supply dependence by construction, so — as
the recorded evidence itself shows — `vref` is exactly flat across the
`VDD` axis in every record this testbench produces. That flatness is the
correct, honest result for *this* testbench, not a bug: real supply
sensitivity (line regulation) is a property of the mirror + closed loop,
neither of which exists yet.

## Cold-start invocation

Requires only `ngspice` on `PATH` and a resolvable SG13G2 PDK install (see
`sim/pdk.json` for the pinned release — `IHP-GmbH/IHP-Open-PDK` tag
`v0.3.0`, fetchable via `klayout-tools`' `scripts/fetch-ihp-sg13g2.sh`, the
same fetch `design/README.md` documents for schematic work). Does **not**
require `xschem` or `klt`.

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/core-open-loop-bias/run_pvt_sweep.sh
```

(`PDK_ROOT`/`PDK` may be left unset if the PDK is installed under one of the
prefixes `sim/env.sh` checks automatically — `/usr/share/pdk`,
`/usr/local/share/pdk`, `~/share/pdk`, `~/.ciel`, `~/.volare`.)

This generates one netlist per `(process corner, temperature, supply)`
point (27 points: 3 x 3 x 3) from `testbench/tb_core_open_loop_bias.spice.tmpl`,
runs each through `ngspice -b`, and writes a new, timestamped, append-only
evidence record — never overwriting a prior run — under:

- `netlist-snapshots/<record-id>/<corner-id>.spice` — the exact generated
  netlist for each point
- `corners/<record-id>/<corner-id>.log` — the raw ngspice batch output
- `records/<record-id>.md` — the human-readable summary
- `records/<record-id>.csv` — the parsed, machine-readable data

Exits non-zero (after writing whatever it did produce) if any point fails,
so a future CI wiring (#16) can gate on it.

## Regenerating the netlist substitution values by hand (sanity check)

If auditing the `R1`/`R2` substitution above without re-running ngspice:
`R2 = rsh_rppd(corner) * 82.7 / 2.006`, `R1 = rsh_rppd(corner) * 694.5 / 2.006`
(2.006 = drawn `w=2u` + `rppd`'s own `weff = w + 0.006u` correction, `b=0`
so `leff = l`). At the `typ` corner (`rsh_rppd = 260.0`): `R2 ≈ 10.72 kΩ`,
`R1 ≈ 90.0 kΩ` — matching the recorded evidence.
