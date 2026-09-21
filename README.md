# sg13g2-bandgap

A bandgap voltage reference on
[IHP SG13G2](https://github.com/IHP-GmbH/IHP-Open-PDK), a 130 nm SiGe BiCMOS
open PDK — designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the
open-source xschem + ngspice flow.

**Status: schematic captured and simulated across PVT; layout DRC-clean;
LVS `match` on `bandgap_startup`, still `mismatch` on `bandgap_core`.** The
`klt` resolver gap that once blocked this repo closed on 2026-08-05
([klayout-tools#522](https://github.com/2AMLogic/klayout-tools/issues/522)),
and a curated SG13G2 DRC/LVS starter deck now ships with klayout-tools
([#905](https://github.com/2AMLogic/klayout-tools/issues/905) /
[#911](https://github.com/2AMLogic/klayout-tools/pull/911)); design work has
proceeded since. `spec/`, `design/`, `sim/`, and `layout/` are all populated,
including pre- and post-layout (PEX) PVT sweeps and committed `klt drc` /
`klt lvs` reports. The current open blockers are `bandgap_core`'s three
`NPN13G2` devices, which the curated extraction deck cannot recognise at all
because SiGe HBT recognition was investigated and permanently declined
upstream
([klayout-tools#1242](https://github.com/2AMLogic/klayout-tools/pull/1242)),
and the trim network obligated by the re-cast Output-reference row (issue
#229) — design work, not further tooling work. The earlier
"not-yet-routed floorplan" cause (#20) was
retired by PR #27 and #20 is closed; the earlier ratification gate (#13) is
closed and the target-spec table below is ratified against
currently-committed evidence — see
[`spec/decision-records/0007-target-spec-ratification.md`](spec/decision-records/0007-target-spec-ratification.md),
and
[`0008-two-key-ratification-review-outcome.md`](spec/decision-records/0008-two-key-ratification-review-outcome.md)
for what the two-key review of that ratification found (issue #125).

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

## Target specification (RATIFIED; Output-reference row re-cast by the two-key-gated decision record 0010 — see below)

| Parameter | Target | Stretch |
|---|---|---|
| Output reference | 1.050 V — ±16% untrimmed (3σ, mismatch MC + PVT); ±0.5% trimmed (1-point @ 27 °C) | — |
| Trim | 1-point @ 27 °C; range ≥ ±15%; resolution ≤ 0.25%/step; magnitude only | — |
| Temp coefficient (−40…125 °C) | < 50 ppm/°C | < 20 ppm/°C |
| PSRR @ DC | > 60 dB | > 70 dB |
| Supply | 3.3 V ±10% (HV flavor) | 1.2 V (LV flavor) |
| Iq | < 50 µA | < 20 µA |
| Startup | self-starting, < 1 ms | — |

Ratified in
[`spec/decision-records/0007-target-spec-ratification.md`](spec/decision-records/0007-target-spec-ratification.md)
against the currently-committed `R1=511µm` retune (issue #134) and an N=300
device-mismatch Monte Carlo (issue #215); that record supersedes the earlier
`feature/issue-125` ratification draft (PR #128), whose cited evidence
predated both. The Output-reference row is re-cast (nominal, untrimmed and
trimmed lines, plus a Trim row) by
[`spec/decision-records/0010-output-reference-row-disposition.md`](spec/decision-records/0010-output-reference-row-disposition.md)
(issue #221, two-key-gated). Ratifying the table locks in these target
*numbers*, not a claim that every row is currently met — per
`CLAUDE.md`/`spec/README.md` this repo does not relax a spec to make
results pass.

**The two-key ratification review of that record ran on 2026-09-19** (EE key
`request-changes`, market key `escalate`, `ratify-key.sh release` →
NOT-ELIGIBLE; verdict links and full findings in
[`0008-two-key-ratification-review-outcome.md`](spec/decision-records/0008-two-key-ratification-review-outcome.md)),
so the honest per-row status is:

- **Temp coefficient, Supply, Iq, Startup, PSRR @ DC** — target met on
  currently-committed evidence, and found technically sound (EE key) and
  `competitive`/`adequate-for-catalog` (market key). Two caveats the review
  put on the record: the TC row meets its `< 50 ppm/°C` **target** by both the
  endpoint and box methods, but the `< 20 ppm/°C` **stretch** is met only by
  the endpoint method — `measurements/2026-08-tc-retune/README.md` §4b's
  box-method scan reaches ~20.2 ppm/°C at the `wcs` corner (issue #222); and
  the PSRR row's post-layout margin at its binding corner (`bcs`/125 °C/
  3.63 V) is 0.20 dB, on a corner that reads 59.68 dB pre-layout.
- **Output reference — re-cast by decision record
  [`0010`](spec/decision-records/0010-output-reference-row-disposition.md)
  (issue #221).** The row both keys declined is disposed by re-cast, not
  defence: the nominal is re-targeted from ~1.2 V to **1.050 V**, this
  core's own TC-null operating point (the one R1/R2 knob that closed the TC
  row in #134 sets both the output level and the PTAT gain; at the TC-null
  ratio the measured post-layout output is 1.04309–1.05667 V across the
  45-point PVT grid, nominal point 1.05048 V — holding 1.2 V instead is the
  measured 349–376 ppm/°C pre-retune core). The untrimmed line is set to
  what the block's own mismatch evidence supports: **±16% (3σ)**, derived
  from the N=300 mismatch Monte Carlo (3σ/mean 13.04% at typ/27 °C,
  12.09–14.60% across corner points) plus the corner-mean offset — an
  order of magnitude wider than the gf180/sky130 ±2% lines because this
  PDK's mismatch scatter is an order of magnitude larger than theirs. The
  buyer-facing accuracy is the **±0.5% trimmed** line (1-point trim at
  27 °C), backed by the new **Trim row** (range ≥ ±15%, resolution
  ≤ 0.25%/step) — the row shape the market key asked for, and the same
  re-cast shape both siblings ratified on their own numbers. The trim
  network behind the trimmed line does not exist yet and is tracked by
  **#229** (replacing the closed issue #9 as the tracker); until it lands,
  the committed evidence demonstrates the untrimmed ±16% line and supports
  ±0.5% as a budgeted target.

See `0007` for full per-row evidence and the Output-reference-vs-TC trade-off,
`0008` for what the two-key review changed about the status above, and `0010`
for the Output-reference disposition and its derivations.

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
seat → measured silicon. **Current position: tooling resolved; spec
ratified (see decision records above), five of six rows two-key reviewed
clean and the Output-reference row re-cast by the two-key-gated record 0010
(#221) rather than blocking the other five; schematic simulated across PVT,
pre- and post-layout (PEX);
layout DRC-clean, with LVS `match` on `bandgap_startup` and `mismatch` on
`bandgap_core` (three unrecognised `NPN13G2` devices, klayout-tools#1242,
permanent).**

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
