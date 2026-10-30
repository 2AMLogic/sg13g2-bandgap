# 0016: Resize the amplifier's NMOS mirror against measured mismatch and re-aim the one-point trim — trimmed 3σ is 0.89–0.94 %, not ±0.5 %

- **Status**: proposed
- **Date**: 2026-10-30
- **Decided by**: Loom Builder agent, issue #303 (numbers below are from the committed
  records named in "Evidence", not copied from the issue or the PR #270 reviews)

Numbering note: `0015` is the highest number on `main` as of this record, so this
record takes `0016`.

## Context

The operator ruling of 2026-10-08 declined the ±4.5 % (3σ) relaxation of
[`0012`](0012-trimmed-line-disposition.md) (now marked declined, analysis kept) and asked
for a harder try at the design inside [`0014`](0014-trim-row-keep-1-point.md)'s ruling:
one-point trim, no CTAT knob, no second insertion. This record reports that try. It does
**not** edit any `spec/` row and does not revisit `0014`.

## Evidence

All on the klt batch fleet, seed 20260930, N = 300 draws per point, committed append-only
under `sim/closed-loop-vref-trim-mc/records/`:

| record | what | core |
|---|---|---|
| `20261030-124725-b5e4f8b4-attrib.{md,csv}` | untrimmed 27 °C contribution breakdown | as-built |
| `20261030-132227-19b1416e-attrib.{md,csv}` | same breakdown | resized |
| `20261030-070305-03e62489.{md,csv}` | trim campaign, DR-0011 code rule | as-built |
| `20261030-140458-19b1416e.{md,csv}` | trim campaign, DR-0011 code rule | resized |
| `20261030-162252-3158d1b9.{md,csv}` | trim campaign, **re-aimed** code rule | resized |

Method and gates are in `sim/closed-loop-vref-trim-mc/README.md` ("Mismatch attribution,
resizing and the re-aimed trim"). Every attribution run passes its hard gates (plain-section
negative control and all-groups-off control each exactly zero spread) and each trim run keeps
the plain-section negative control at exactly zero spread.

## Decision

The decision is items 1–5 below: the sizing, the re-aimed code rule, and the resulting
trimmed-3σ statement (0.89–0.94 %), each with its measured basis.

### 1. Mismatch contribution (item 1)

Untrimmed vref at 27 °C, code 128, 3.30 V, typ. Shares are over the sum of the single-group
variances, which reconciles with the all-mismatch variance (ratio 1.026 as-built, 1.004
resized). The leave-one-out column is not additive and is not relied on.

| group | as-built share | as-built σ alone (mV) | resized share | resized σ alone (mV) |
|---|---:|---:|---:|---:|
| amp NMOS mirror (XMN1–4) | **57.6 %** | 36.97 | 7.0 % | 8.72 |
| bipolars (XQ1–3) | 27.9 % | 25.74 | **61.0 %** | 25.81 |
| amp tail + PMOS load | 5.3 % | 11.24 | 12.0 % | 11.43 |
| amp input pair | 4.7 % | 10.57 | 10.3 % | 10.60 |
| core PMOS mirror | 4.5 % | 10.32 | 9.8 % | 10.35 |
| R1/R2, trim ladder, startup | 0.0 % | ≤ 0.47 | 0.0 % | ≤ 0.47 |

All-mismatch σ: 4.588 % → 3.141 % of vref (3σ 13.76 % → 9.42 %). Input-referred offset σ:
5.82 mV → 2.69 mV, where the NMOS mirror was 85.2 % of the offset.

Against the review's claims:

- **Confirmed**: the offset term is large and one group dominates it. The amp NMOS mirror is
  the single dominant contributor (57.6 % of vref variance, 85.2 % of offset), in
  10 µm × 1 µm devices.
- **Refuted in size**: the measured input-referred offset is σ = 5.8 mV (review: "about
  8 mV"), and the untrimmed σ is 4.59 % (review: 4.3–4.5 %). The input pair the review
  singles out is only 4.7 % of the variance; the resistors contribute nothing.
- **Not tested here**: "74 % of the level error is flat in temperature" and "that converted
  term is 84–85 % of post-trim drift spread". The attribution is of the *untrimmed 27 °C*
  level only. A trimmed-domain attribution (which group drives the post-trim drift) was not
  run; see Consequences.
- **A finding the review did not have**: the PDK's `npn13G2` mismatch subcircuit draws a
  10 % one-sigma emitter-area error per device, independent of `Nx`
  (`sg13g2_hbt_mod_mismatch.lib`). It is 27.9 % of the as-built variance and 61.0 % of the
  resized variance, and **sizing cannot reduce it** in this model. That is a property of
  the model, not necessarily of silicon.

### 2. Sizing (item 2)

**Decision**: the four amplifier NMOS mirror devices go from W/L = 10 µm/1 µm to
**40 µm/4 µm** (`design/bandgap_amp.sch`, regenerated `design/netlist/bandgap_amp.spice` and
`bandgap_top.spice`). Nothing else is resized: after this the next contributors are each
≤ 12 % and bipolars are model-limited, so further area buys little offset.

**Area delta**: NMOS mirror gate area 4 × 10 µm² = 40 µm² → 4 × 160 µm² = 640 µm², i.e.
**+600 µm² of gate area (16×)**. Layout footprint was not measured (pre-layout); this is the
gate-area figure only.

Resized offset σ 5.82 → 2.69 mV and untrimmed vref σ 4.59 → 3.14 %; trimmed 3σ in section 4.

### 3. Re-aimed code rule (item 3)

`0014`'s S2 rule: final code = `code* + round(k0 + k1·code*)`, clipped to 0..255, no extra
hardware and no second insertion. `0014` projected `k0 = 8.0, k1 = −0.06` on the as-built
core. Refitted on the **resized** core, on the typ-mismatch point of
`20261030-140458-19b1416e` only (298 converged dies; same grid and criterion as
`sim/tools/project_trim_strategies.py`):

**`k0 = +3.25, k1 = −0.02`** (`20261030-162252-3158d1b9-reaim-rule.json`).

bcs and wcs are out of sample. Projected typ 3σ 0.886 % vs measured 0.890 %.

### 4. Result: the trimmed line (item 4)

Max |vref(T) − vref(27 °C)| over −40/27/125 °C after the 27 °C trim, 3σ in % of vref:

| point | as-built, DR-0011 rule | resized, DR-0011 rule | **resized, re-aimed** | re-aimed, failed draws filled at worst | re-aimed, share of dies inside ±0.5 % |
|---|---:|---:|---:|---:|---:|
| typ | 2.399 | 1.144 | **0.890** | 0.890 | 49.3 % |
| bcs | 2.413 | 1.151 | **0.942** | 1.005 | 50.8 % |
| wcs | 2.390 | 1.110 | **0.911** | 0.933 | 51.5 % |

Re-aimed mean + 3σ is 1.46 / 1.51 / 1.48 %; worst single draw 1.65 / 1.77 / 1.76 %.
Zero dies hit a code rail. The plain-section negative control has exactly zero spread and a
worst deviation of 0.354 %, which is the deterministic floor of the trim (code 130, no
mismatch): about 71 % of the ±0.5 % line is used by a perfect die.

**How close to ±0.5 %**: not close. The measured 3σ is **1.8–1.9× the line**, and only about
half the population lands inside it. Resizing took the 3σ from about 2.4 % to about 1.14 %
(−52 %); re-aiming took a further 0.25 percentage points to about 0.9 %. Neither is a
mechanism that can close the remaining gap: the largest remaining untrimmed contributor is
the bipolar area draw, which sizing cannot touch, and the deterministic floor alone takes
0.354 % of the 0.5 %.

**Conclusion**: with resizing and re-aiming exhausted inside `0014`'s boundary, the one-point
trim does not reach ±0.5 % on this evidence. This is the evidence for revisiting `0014`'s trim
ruling (for example a second degree of freedom per `0013`); this record does not do that and
does not relax any gate.

### 5. Evidence quality (item 5 of the issue's scope)

- **Axes covered**: supply 3.30 V only; trim at 27 °C, verify at −40/27/125 °C only; process
  typ / bcs / wcs mismatch plus a typ negative control; pre-layout, no parasitics, no
  lifetime drift. Supply and interior temperatures are not covered, so the result is an
  *optimistic* bound on the line, not a worst case.
- **Draws**: seed 20260930, N = 300 per point, 1,200 rows in the draws CSV. No draw is
  dropped; each failed one is a `FAIL` row.
- **Non-converging draws, explained**: the 4 failed draws in the re-aimed run (bcs 55, 161,
  265; wcs 184; `…-failed-draws.csv`) each lost exactly one verify deck, the 125 °C one, to a
  **fleet-side deck timeout, not a simulator non-convergence**. The plain run of the same
  dies lost a different set (typ 55, 73; bcs 265; wcs 184), so the timeout is not tied to the
  die or the code. The population statistics are over converged draws; the table above also
  gives the bound with every failed draw filled at its point's worst passing deviation, which
  moves a 3σ by at most 0.063 points. The timeout itself has not been root-caused here.
- **The old "58 of 300 non-converged" draws** from the review were not reproduced on this
  core and were not investigated further.

## Alternatives considered

- **Size every contributor up** — the shares say only the NMOS mirror was worth 16× area;
  the rest is ≤ 12 % each and the bipolar term does not respond to area.
- **Keep the `0014` S2 constants (8.0, −0.06)** — they were fit on the as-built core, which
  no longer exists; refitting on the resized core is required for the rule to centre.
- **Declare ±0.5 % met on the typ point's projection** — the projection (0.886 %) is itself
  above the line.

## Consequences

- The ±0.5 % trimmed line is **measured not met** with a one-point trim, on the best
  design reachable inside `0014`. `0014`'s ruling is the thing that needs revisiting; this
  record leaves it standing. #268 stays blocked on that outcome.
- Costs +600 µm² of amplifier gate area (pre-layout figure) and a rewired netlist/schematic;
  any downstream result that used the as-built amp (PEX, startup, loop stability, box-TC)
  predates the resize and must be re-run before it is cited against this core.
- **Layout and signoff artifacts are stale against the resized schematic.** This record
  changes `design/` only. The committed `layout/bandgap_amp/` and `layout/bandgap_top/`
  GDS, LVS references, DRC/LVS reports and `*.pex.spice` extractions still describe the
  old `w=10u l=1u` mirror (XMN1–4), so layout and schematic disagree until the mirror is
  re-laid-out and re-extracted. The PEX netlist-body generator self-test
  (`sim/tools/test_gen_pex_netlist_body.py`) correctly fails on that disagreement and is
  not relaxed. The re-layout, re-extraction and refresh of artifacts bound to the old
  extraction are tracked in #436; the footprint of the 40u/4u mirror is not known until
  that layout exists.
- The attribution is of the untrimmed 27 °C level. Which group drives the post-trim *drift*
  is not measured; that is the natural next experiment and is not claimed here.
- The bipolar 10 % area draw is a PDK-model fact that dominates the floor; whether silicon
  shows it is outside what this repo can measure.
