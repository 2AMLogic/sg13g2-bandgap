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
`klt lvs` reports. The target-spec table below is now ratified (#125); the
current open blocker is the not-yet-routed floorplan that keeps LVS from a
device-level match (#20) — not the tooling.

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

## Target specification (RATIFIED)

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
Ratification of this table itself — the event, plus the honest evidence
status behind each row — is recorded in
[`spec/decision-records/0006-target-spec-ratification.md`](spec/decision-records/0006-target-spec-ratification.md).

Port parity note: the spec deliberately mirrors the gf180 and sky130
bandgaps — same block, three PDKs. Where SG13G2's devices make a target
inappropriate rather than merely harder, change it and record why.

### Evidence status per row

Ratifying this table locks in the *target numbers*, not a claim that every
row is currently met — SG13G2 closed-loop PVT evidence now exists for every
row below (see the cited `sim/` records; each testbench's own README is
explicit that a `N/M PASS` headline is a plumbing/measurement-trustworthiness
result, not a spec-conformance verdict, and none of these records claims
conformance to this table):

- **Output reference** — [`sim/closed-loop-vref-pvt/records/20260826-103022-014570b.md`](sim/closed-loop-vref-pvt/records/20260826-103022-014570b.md)
  measures `vref` settled across all 45 PVT points at 1.134–1.215 V. At
  27 °C specifically (the temperature the ±1% figure is naturally read
  against — TC is tracked separately below), the settled value is
  **1.162–1.173 V**, i.e. ~2.3–3.1% *below* the 1.2 V nominal — outside the
  ±1% untrimmed band, not merely spread within it. Only 12/45 points across
  the full grid land inside [1.188 V, 1.212 V], and those are concentrated
  at the 125 °C corners where untrimmed TC drift happens to carry `vref`
  back up near 1.2 V, not because the design is independently accurate at
  its nominal condition. **Currently short of target**, for the same
  underlying reason as the TC row below (no trim network yet).
- **Temp coefficient** — the same record's informal endpoint-method TC
  computation reads **~349–376 ppm/°C** across the 15 corner/supply groups,
  well above the < 50 ppm/°C target (and the < 20 ppm/°C stretch). This is
  expected and documented, not a surprise: `design/README.md`'s "Explicitly
  out of scope" section (issue #9) records that no trim network exists in
  this design yet, and an untrimmed `VBE`-based bandgap's TC is normally in
  the hundreds-of-ppm/°C range without one. **Currently short of target,
  with a known, documented cause (no trim network) — not yet closed.**
- **PSRR @ DC** — [`sim/closed-loop-psrr/records/20260826-114500-874c585.md`](sim/closed-loop-psrr/records/20260826-114500-874c585.md)
  measures DC PSRR of **57.1–105.2 dB** across the 45-point grid: 20/45
  points fall below the 60 dB target (worst case 57.1 dB), 37/45 fall below
  the 70 dB stretch, and only 8/45 clear 70 dB — and that testbench's own
  README attributes the small cluster of high (80–105 dB) readings to a
  bias-point-specific near-cancellation at 27 °C/3.63 V, not typical
  behavior. **Does not uniformly meet the 60 dB target across PVT** — needs
  further corner-by-corner characterization/design work, not just more
  simulation.
- **Supply** — grounded directly in the SG13G2 device menu (HV-NMOS/HV-PMOS
  `V_GS ≤ 3.3 V` tables), not a simulated result; see
  [`spec/decision-records/0002-supply-voltage-scope.md`](spec/decision-records/0002-supply-voltage-scope.md).
  **Met by construction** — every PVT record above sweeps exactly the
  2.97/3.30/3.63 V (±10% of 3.3 V) grid this row specifies.
- **Iq** — [`sim/closed-loop-iq/records/20260826-152134-9b7a6de.md`](sim/closed-loop-iq/records/20260826-152134-9b7a6de.md)
  measures settled quiescent current of **19.98–42.37 µA** across the same
  45-point grid. **Meets the < 50 µA target at every corner**, and touches
  the < 20 µA stretch only at the coldest/lightest-load corner.
- **Startup** — [`sim/closed-loop-startup/`](sim/closed-loop-startup/README.md)
  and `closed-loop-vref-pvt`/`closed-loop-iq` all show 45/45 PASS on
  self-starting and loop-closure by their measured checkpoints (`t=2ms`,
  re-confirmed settled at `t=3ms`): the startup circuit's `MKFB` fully
  releases, the loop closes (`|sns1-sns2|` within 0.51 mV of zero at its
  worst corner), and `fb` never rails. **The loop-closure/self-start
  plumbing is verified across full PVT; no testbench yet reports an
  explicit measured time-to-release number to compare against the < 1 ms
  figure itself** — a real remaining gap in this row's evidence, not a
  target miss.

### Maturity ladder

Tooling resolved → spec ratified → schematic simulated across PVT → layout
DRC/LVS-clean → post-layout re-verification → shuttle seat → measured
silicon. **Current position: tooling resolved; spec ratified (#125);
schematic simulated across PVT, pre- and post-layout (PEX); layout
DRC-clean but LVS not yet device-matched (#20).** As the evidence-status
notes above make explicit, "spec ratified" here means the target *numbers*
are locked in as the block's official spec, evaluated honestly against real
SG13G2 PVT evidence — it does not mean every row is currently met; the TC,
output-reference, and PSRR gaps above remain open follow-on work.

## Chipalooza

This repo also carries a second port of the same bandgap design onto IHP
SG13CMOS5L (a CMOS-only sibling process to SG13G2), targeting the
Chipalooza Challenge #2 brief. Schematic capture, PVT-cornered pre-layout
simulation, layout, and post-layout (PEX) PVT simulation are all done
(45/45 points PASS in every testbench, including the post-layout pass);
the assembled GDS is DRC-clean, and LVS reports a fully-attributed
`mismatch` against `klayout-tools`' curated SG13CMOS5L deck's documented
starter-scope gaps, not a real circuit defect. See
[`docs/chipalooza/challenge-2-proposal.md`](docs/chipalooza/challenge-2-proposal.md)
for the full proposal: positioning, I/O budget, functional description, a
spec table re-derived from the SG13CMOS5L `sim/` evidence, a bench test
plan for measured silicon, and the complete per-stage sign-off breakdown.
Tracked by issue #63 (parent) and its phase/follow-on issues
(#64-#67, #73, #74, #76, #81, #84).

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
follow `TEMPLATE.md`'s required sections, that `design/`, `sim/`, `layout/`,
and `measurements/` follow this repo's `README.md` convention, and that the
committed **evidence** is well-formed, self-consistent, append-only and fresh:

```bash
python3 .github/scripts/check_evidence_formats.py       # what CI runs
python3 .github/scripts/test_check_evidence_formats.py  # the checker's self-test
```

Every `sim/` record is checked against the convention in
[`sim/README.md`](sim/README.md) — including that its `N/M points PASS`
headline agrees with its own parsed CSV and its own raw per-point logs — and
every `layout/` DRC/LVS/PEX report is checked against the sha256 of the input
it says it consumed, because *staleness is failure*. It does not yet validate
characterization artifacts (there is no silicon yet). Full scope, known gaps
and the waiver mechanism for known-stale reports:
[`.github/workflows/README.md`](.github/workflows/README.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
