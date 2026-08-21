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

## Devices: all real compact models since issue #22

Every device in this testbench is now the PDK's own compact model, with the
geometry `design/netlist/bandgap_core.spice` draws:

- `XQ1`/`XQ2`/`XQ3` — `npn13G2`, the PDK's native VBIC level=9 model card
  (never needed OSDI).
- `XM1`/`XM2`/`XM3` — `sg13_hv_pmos`, PSP103.6, loaded from `psp103.osdi`.
- `XR1`/`XR2` — `rppd`, `r3_cmc`, loaded from `r3_cmc.osdi`.

The OSDI models are built by `sim/tools/build-osdi.sh` from the PDK's own
Verilog-A sources; `sim/README.md` § "OSDI device models" documents that
build, its provenance pins, and why the alternatives were rejected.
`run_pvt_sweep.sh` preflights with `build-osdi.sh --check` and refuses to
produce a record if the models are missing or unloadable.

**Historical note (append-only tree, so the old records still stand).**
Records in `records/` dated before issue #22 (`20260821-115433-5f66bd5`)
were produced by a different version of this testbench: it substituted
ideal 5 µA current sources for `XM1`/`XM2`/`XM3` and ideal `R` devices
(valued `rsh_rppd × squares` from the per-corner `cornerRES.lib` section)
for `XR1`/`XR2`, because no OSDI models existed in that environment. Those
records are still valid evidence *of what they measured*; they are just not
comparable, device-for-device, with post-#22 records. The two agree closely
where they should: `dVBE(Q1,Q2) ≈ 55.2 mV` at the 27 °C nominal point in
both, and the real `r3_cmc` `R1` measures `89.78 kΩ` (typ, 27 °C) against
the ideal substitution's `89.46 kΩ` — a ~0.4 % head/end-resistance term the
ideal `rsh × squares` formula cannot represent.

## Open-loop bias: what is a fixture and what is the DUT

No error amplifier exists yet (`design/README.md`, issue #9's explicit
scope cut), so nothing in the design drives the mirror gate `fb`. This
testbench supplies two fixtures, neither of which replaces a DUT device:

1. **Mirror bias** — a diode-connected replica `XM0` (same `sg13_hv_pmos`,
   same `w=10u l=1u`) carrying a 5 µA reference sets `fb`. The three DUT
   legs are therefore real PSP103 mirrors of a real PSP103 device: leg
   current now moves with temperature, supply and the MOS process corner
   the way silicon would, instead of being pinned at exactly 5 µA by an
   ideal source. 5 µA/leg matches issue #9's own informal nominal check.
2. **Ammeters** — each mirror drain reaches its DUT node through a 0 V
   source, so per-leg current is measurable. A 0 V source is a DC short and
   does not move the operating point.

This is still **open loop**: nothing forces `sns1 = sns2`. It happens that
they land within ~1 mV of each other at the nominal point, which is a
property of the leg design, not a loop.

**Corner coverage**: the process-corner axis is now
`{typ, bcs, wcs, sf, fs}`, covering **all five** of `cornerMOShv.lib`'s
process sections:

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

`typ`/`bcs`/`wcs` reuse the corner label the PDK itself assigns in
`cornerHBT.lib` and `cornerRES.lib`, paired with the MOS section of
matching intent (`ff` = best case, `ss` = worst case). `sf`/`fs` are the
two skewed MOS corners; `cornerHBT.lib` and `cornerRES.lib` have no
counterpart section for them, so those two points run typical HBT and
resistor sections and vary only the MOS axis. That is stated here rather
than buried in the script because it is a testbench convention, not a PDK
one.

**Supply (`VDD`) coverage**: `{2.97, 3.30, 3.63}` V (3.3 V ±10 %, per
`spec/porting-plan.md` §4/DR-0002). Unlike the pre-#22 ideal-source
version — where `vref` was exactly flat across this axis by construction —
the real mirror gives a genuine, if small, supply dependence (`vref` moves
about 1.4 mV per 0.33 V of supply at the typical corner, from the mirror's
finite output resistance). Full line-regulation claims still require the
closed loop and the amplifier, neither of which exists yet; this is the
mirror's open-loop supply sensitivity only.

## Cold-start invocation

Requires `ngspice` on `PATH`, a resolvable SG13G2 PDK install (see
`sim/pdk.json` for the pinned release — `IHP-GmbH/IHP-Open-PDK` tag
`v0.3.0`, fetchable via `klayout-tools`' `scripts/fetch-ihp-sg13g2.sh`, the
same fetch `design/README.md` documents for schematic work), and the OSDI
device models built once by `sim/tools/build-osdi.sh`. Does **not** require
`xschem` or `klt`.

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time; idempotent
sim/core-open-loop-bias/run_pvt_sweep.sh
```

(`PDK_ROOT`/`PDK` may be left unset if the PDK is installed under one of the
prefixes `sim/env.sh` checks automatically — `/usr/share/pdk`,
`/usr/local/share/pdk`, `~/share/pdk`, `~/.ciel`, `~/.volare`.)

This generates one netlist per `(process corner, temperature, supply)`
point (45 points: 5 x 3 x 3) from `testbench/tb_core_open_loop_bias.spice.tmpl`,
runs each through `ngspice -b`, and writes a new, timestamped, append-only
evidence record — never overwriting a prior run — under:

- `netlist-snapshots/<record-id>/<corner-id>.spice` — the exact generated
  netlist for each point
- `corners/<record-id>/<corner-id>.log` — the raw ngspice batch output
- `records/<record-id>.md` — the human-readable summary
- `records/<record-id>.csv` — the parsed, machine-readable data

Exits non-zero (after writing whatever it did produce) if any point fails,
so a future CI wiring (#16) can gate on it.

## Hand-checking the recorded resistor values (sanity check)

The `r1_ohm`/`r2_ohm` columns are not model parameters — they are computed
from the recorded DC drop over the recorded leg current
(`(v(vref) - v(cb3)) / i(vm3)` and `(v(sns2) - v(cb2)) / i(vm2)`), i.e. what
the real `r3_cmc` device actually presented at that operating point.

To audit them without re-running ngspice, the first-order value is
`rsh_rppd(corner) × L / weff`, with `weff = 2u + 0.006u` (`rppd`'s own
formula at `b=0`, so `leff = l`): at the `typ` corner (`rsh_rppd = 260.0`)
that is `R2 ≈ 10.72 kΩ`, `R1 ≈ 90.0 kΩ`. The recorded values sit slightly
below (`10.72 kΩ` / `89.78 kΩ` at 27 °C typ) because `r3_cmc` also models
head/end resistance and a temperature coefficient the sheet-resistance
formula alone does not. A recorded value more than a few percent off that
first-order number is worth investigating; an exact match would mean the
compact model is not actually being used.
