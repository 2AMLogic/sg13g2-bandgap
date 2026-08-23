# sg13g2-bandgap

A bandgap voltage reference on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), a 130 nm SiGe BiCMOS
open PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: schematic captured and simulated across PVT; layout DRC-clean, LVS
not yet matched.** The `klt` resolver gap that once blocked this repo closed
on 2026-08-05
([klayout-tools#522](https://github.com/2AMLogic/klayout-tools/issues/522)),
and a curated SG13G2 DRC/LVS starter deck now ships with klayout-tools
([#905](https://github.com/2AMLogic/klayout-tools/issues/905) /
[#911](https://github.com/2AMLogic/klayout-tools/pull/911)); design work has
proceeded since. `spec/`, `design/`, `sim/`, and `layout/` are all populated,
including pre- and post-layout (PEX) PVT sweeps and committed `klt drc` /
`klt lvs` reports. The current open blockers are the not-yet-routed floorplan
that keeps LVS from a device-level match (#20) and ratification of the draft
target-spec table below (#13) — not the tooling.

**Built agent-native.** Every specification, decision record, testbench, and
line of documentation here is produced by AI agents working from a ratified
spec and an append-only evidence trail — not human-authored work that agents
merely assisted with. Verification is the product: every claim traces to a
recorded result under PVT corners. Where the agents hit friction with the
open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction is
filed as a public issue against the tool itself, so the fix benefits everyone
using SG13G2, not just this repo.

## Why this block, on this PDK

The sibling canaries all sit on gf180mcu or sky130. SG13G2 is a third PDK
with its own rule deck, device models, and tech file, and none of it has met
these tools.

The block is deliberately the *least* novel thing available: a bandgap
reference, which is the most mature design in the fleet
([gf180-bandgap](https://github.com/2AMLogic/gf180-bandgap),
[sky130-bandgap](https://github.com/2AMLogic/sky130-bandgap)). That is the
whole experimental design. If the design is the one we understand best, then
anything that breaks here is the PDK or the tools — not the circuit. A novel
block on a novel PDK would confound the two.

SG13G2 being a **BiCMOS** process is a genuine bonus: it offers real bipolar
devices rather than the parasitic PNPs the CMOS ports rely on, which is a
different device class for extraction and LVS to handle.

## Target specification (DRAFT — engineering to ratify, see issue #13)

| Parameter | Target | Stretch |
|---|---|---|
| Output reference | ~1.2 V ±1% untrimmed | ±0.5% with trim |
| Temp coefficient (−40…125 °C) | < 50 ppm/°C | < 20 ppm/°C |
| PSRR @ DC | > 60 dB | > 70 dB |
| Supply | 3.3 V ±10% (HV flavor) | 1.2 V (LV flavor) |
| Iq | < 50 µA | < 20 µA |
| Startup | self-starting, < 1 ms | — |

Supply row confirmed against SG13G2's actual device menu (1.2 V LV core /
3.3 V HV I/O — no 1.8 V-rated flavor exists in this PDK) — see
[`spec/decision-records/0002-supply-voltage-scope.md`](spec/decision-records/0002-supply-voltage-scope.md).
The bipolar-versus-parasitic device call for the core itself is recorded in
[`spec/decision-records/0001-bipolar-device-selection.md`](spec/decision-records/0001-bipolar-device-selection.md);
full porting analysis in [`spec/porting-plan.md`](spec/porting-plan.md).

Port parity note: the spec deliberately mirrors the gf180 and sky130
bandgaps — same block, three PDKs. Where SG13G2's devices make a target
inappropriate rather than merely harder, change it and record why.

Maturity ladder: tooling resolved → spec ratified → schematic simulated
across PVT → layout DRC/LVS-clean → post-layout re-verification → shuttle
seat → measured silicon. **Current position: tooling resolved; schematic
simulated across PVT, pre- and post-layout (PEX); layout DRC-clean but LVS
not yet device-matched (#20). Spec ratification is still open (#13), so the
ladder's second rung is climbed out of order — the draft table above is what
the sims are measured against.**

## Repo layout

```
spec/          ratified spec + decision records
design/        schematics / netlists (xschem)
sim/           testbenches + PVT corner results (ngspice)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
```

## Continuous integration

A `hygiene` workflow (`.github/workflows/hygiene.yml`) runs on every push and
pull request. It checks that decision records in `spec/decision-records/`
follow `TEMPLATE.md`'s required sections, and that `design/`, `sim/`,
`layout/`, and `measurements/` follow this repo's `README.md` convention.
It does not (yet) validate the DRC/LVS/PEX report formats now committed
under `layout/`, nor characterization artifacts (there is no silicon yet).
Full scope and known gaps:
[`.github/workflows/README.md`](.github/workflows/README.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
