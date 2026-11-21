# closed-loop-psrr — DC-PSRR attribution at `bcs`/125 °C/3.63 V (issue #631)

Local, single-corner `.op`/`.ac` probes that attribute the DC-PSRR row's one
miss (`bcs`/125 °C/3.63 V, 59.685 dB in record
[`../records/20261113-085406-9d568b91.csv`](../records/20261113-085406-9d568b91.csv),
0.315 dB under the > 60 dB row) and screen bounded fixes for it. This is
deliberately **not** a grid: dispatch hosts allow one local corner at a time,
so every number below is ONE `ngspice -b` run on the committed bench body,
seeds from [`../../closed-loop-startup/records/`](../../closed-loop-startup/records/)'s
newest committed record (per-corner rows). The full-grid verification of the
surviving candidate is a separate `klt sim` fleet record minted by
[`run_probe.sh`]'s sibling path — see
[`../records/`](../records/)'s newest variant record and
[`../variants/`](../variants/).

## How to reproduce

```sh
source sim/env.sh                       # PDK_ROOT + OSDI models
cd "$(mktemp -d)"
sim/closed-loop-psrr/attribution/run_probe.sh bcs 125 3.63 asbuilt
# RESULT corner=bcs temp=125 vdd=3.63 variant=asbuilt psrr_dc_db=5.968490e+01 ...
sim/closed-loop-psrr/attribution/run_probe.sh wcs 125 2.97 p12-w2 --loop-gain
# RESULT ... lg_quality=OK ... lg_phase_margin_deg=5.104870e+01 ...
```

- [`gen_probe_deck.py`](gen_probe_deck.py) instantiates the committed bench
  body ([`../testbench/closed_loop_psrr.body.spice.tmpl`](../testbench/closed_loop_psrr.body.spice.tmpl))
  exactly as `run_klt_sim.sh` does (same `@@` token set, same seed lookup,
  same XMSENSE width read), adds only probe prints (`show`, the complex 1 Hz
  response, `i(Vvdd)`), and optionally applies a **variant** rewrite.
- **Ablation variants** (`quiet-*`) move one device group's supply
  terminals to a second source `Vvddq` at the same DC potential but `AC 0` —
  removing exactly that group's direct small-signal vdd coupling without
  moving the operating point. `quiet-all` is the null control.
- **Fix-candidate variants** are single bounded device resizes.
- **`--loop-gain`** re-topologizes the same instantiated body into the
  Middlebrook loop break [`../../loop-gain-phase-margin/`](../../loop-gain-phase-margin/)
  uses (`T = v(fb_src)/v(fb_load)`, same Lbreak/Vtest fixture), and
  post-processes with that bench's own `find_crossover.awk` and
  `solve_quality.py` gate — no re-derived stability math.
- Decks: [`decks/`](decks/) (token-path form, one per row quoted below);
  all rows: [`results/probe-results.tsv`](results/probe-results.tsv).
- Environment: ngspice 47 (KLU), PDK pin per [`../../pdk.json`](../../pdk.json),
  sessions 2026-11-21 (see the TSV header).

The probe reproduces the committed record's own points to the third decimal
(59.685 dB at `bcs`/125 °C/3.63 V; 60.760 at `fs`/125 °C/2.97 V) and the
loop-gain probe reproduces the committed loop-gain record's phase margins
(96.00° vs 95.76° at `wcs`/125 °C/2.97 V; 103.86° vs 104.18° at
`bcs`/125 °C/3.63 V) — the two differential oracles that make the numbers
below trustworthy.

## 1. What sets DC PSRR at the binding corners: a cancellation, not a leak

Ablations at the worst corner (`bcs`/125 °C/3.63 V; PSRR = −dB of the vdd→vref
transfer, higher is better):

| variant | psrr_dc_db | reading |
|---|---:|---|
| asbuilt | 59.685 | the committed record's number |
| quiet-startup | 59.664 | startup branch contributes **nothing** (XRPU's coupling is ~0) |
| quiet-all (null control) | 93.369 | with every MOS supply terminal quiet, rejection is near-perfect; the residual path (bipolars, resistors) is 93 dB |
| quiet-core (XM1/XM2A/B/XM3A/B/C) | 34.360 | removing the core mirror's coupling makes it 25× WORSE |
| quiet-amp (XMTAIL+XMP1-4) | 34.853 | same for the amplifier — worse, not better |
| quiet-tail (XMTAIL only) | 25.269 | the single largest ablation effect |
| quiet-p34 (XMP3/XMP4 only) | 22.906 | …exceeded only by the output mirror |

Every "remove the suspect" experiment makes rejection **worse**. Converted to
complex vdd→vref gains at 1 Hz (µV per V of ripple, from the measured
magnitudes and phases), the as-built total is a −1.04 µV/V residue of
opposing terms of tens of µV/V each: the output-mirror feedthrough
(XMP3/XMP4, ≈ −73 µV/V) against the loop-mediated terms (XMTAIL ≈ +53,
XMP1/XMP2 bulk ≈ +36, core mirror ≈ +18 µV/V). DC PSRR at this corner is
therefore **a near-cancellation the loop's finite gain leaves behind**, not a
single leaking path — which the fix screen below confirms mechanically:
scaling any ONE term up or down moves the residue the "wrong" way at some
corner. The same structure holds at `fs`/125 °C/2.97 V (quiet-p34 → 24.1 dB,
quiet-tail → 27.2 dB): the 2.97 V corners are the same cancellation with less
loop gain holding it together. The measured refutations: supply ripple
injected by the startup branch (≈0), and "one rogue device dominates"
(every ablation worsens the row).

## 2. Coordination with PR #435 (the unmerged XMN1-4 resize)

`xmn435` = PR #435's resize verbatim (XMN1-4 10u/1u → 40u/4u, confirmed
against `feature/issue-303` tip `50c460f`):

| corner | as-built | xmn435 | Δ |
|---|---:|---:|---:|
| `bcs`/125 °C/3.63 V (the row's miss) | 59.685 | **52.655** | **−7.0 dB** |
| `fs`/125 °C/2.97 V | 60.760 | 78.794 | +18.0 dB |

The resize moves this row strongly in **both directions**: it would fix the
2.97 V corners outright and deepen the `bcs` miss to 7 dB. Additionally, its
loop-gain solve at `wcs`/125 °C/2.97 V was **rejected** by the #289
solve-quality gate (ripple 12.7 dB in the 10–200 MHz band; nominal reading
11.2° PM) — the same corruption signature that bench's own history records,
so #435's stability at that corner is **unverified either way** here. Any
PSRR disposition must be settled jointly with #435, not after it.

## 3. Bounded-fix screen (PSRR at the binding corners + stability)

PSRR dB at the as-built record's worst corners (all 125 °C unless noted);
PM from the `--loop-gain` probe at the corners where the loop-gain record
binds:

| candidate | `bcs` 3.63 | `sf` 3.63 | `typ` 3.63 | `fs` 2.97 | `wcs` 2.97 | PM | verdict |
|---|---:|---:|---:|---:|---:|---|---|
| as-built | 59.685 | 60.040 | 60.465 | 60.760 | 60.867 | 96–104° | — |
| corepmos-l2 / -l4 | 58.213 / 57.649 | — | — | — | — | not reached | ✗ wrong direction at the miss corner |
| tail-l2 | 56.725 | — | — | 61.550 | — | 83.7° | ✗ −3.0 dB at `bcs` |
| tail-l4 (with xmp34-l4) | 59.741 | 60.025 | 60.367 | 61.679 | 61.760 | — | ✗ 3.63 V corners unchanged |
| xmp34-l2 | 64.464 | 64.260 | 64.429 | 60.693 | 60.868 | **−16.5°** | ✗ unstable |
| xmp34-l4 | 67.949 | 67.218 | 67.232 | 60.610 | 60.810 | (−41° with tail-l2) | ✗ unstable |
| xmp34-w2 | 49.132 | — | — | 65.867 | — | 57.7° | ✗ destroys the cancellation |
| allpmos-l2 | 58.045 | 58.409 | 58.818 | 62.573 | 62.270 | marginal-notch shape | ✗ 3.63 V corners worse |
| p12-l2 (40u/2u) | 60.760 | — | — | — | — | REJECT (3.7 dB) | ✗ |
| p12-w3 (60u/1u) | 62.250 | 62.065 | — | — | — | REJECT (4.0 dB) | ✗ |
| p12-w4 (80u/1u) | 62.250 | 62.065 | — | — | — | REJECT (25.6 dB) | ✗ |
| **p12-w2 (40u/1u)** | **60.988** | **61.291** | **61.705** | **61.544** | **61.622** | **51.0–54.8°, quality OK** | ✓ carried forward |

Two structural findings fall out of the screen:

- **The amp's stability budget is spent.** The unity crossover sits at
  40–50 MHz with the internal poles (pn, d1/d2) just above it; ANY length
  scaling of XMP3/XMP4 collapses the pn pole (×4 length ⇒ PM −41°; ×2 ⇒
  −16.5°) and the ×2/×4 input-pair scalings fail the solve-quality gate the
  same way. The only resize family that keeps the loop healthy is a WIDER
  input pair at unchanged length, which buys loop gain (+2.7 dB at
  `wcs`/125 °C/2.97 V) without adding length-capacitance to d1/d2.
- **Single-term scaling cannot fix this row.** Every candidate that scales
  one cancellation term improves some corners and degrades others
  (`tail-*`: +0.8 at 2.97 V, −3 at `bcs`; `allpmos-l2`: +1.3 at 2.97 V,
  −1.6 at `bcs`). The one knob that helps everywhere is more loop gain
  through the input pair's gm.

## 4. The carried candidate: `p12-w2` (XMP1/XMP2 20u/1u → 40u/1u)

Probe results across every as-built marginal corner (worst ten of the
committed record plus the −40 °C extremes; full table in
[`results/probe-results.tsv`](results/probe-results.tsv)):

| corner | as-built (record) | p12-w2 (probe) | Δ |
|---|---:|---:|---:|
| `bcs`/125 °C/3.63 V | 59.685 | **60.988** | **+1.30** |
| `sf`/125 °C/3.63 V | 60.040 | 61.291 | +1.25 |
| `typ`/125 °C/3.63 V | 60.465 | 61.705 | +1.24 |
| `fs`/125 °C/2.97 V | 60.760 | 61.544 | +0.78 |
| `fs`/27 °C/2.97 V | 60.904 | 61.959 | +1.05 |
| `fs`/125 °C/3.63 V | 60.986 | 62.208 | +1.22 |
| `wcs`/125 °C/2.97 V | 60.867 | 61.622 | +0.76 |
| `wcs`/27 °C/2.97 V | 61.109 | 62.123 | +1.01 |
| `typ`/125 °C/2.97 V | 61.293 | 62.022 | +0.73 |
| `bcs`/−40 °C/3.63 V | 69.293 | 70.986 | +1.69 |
| `wcs`/−40 °C/2.97 V | 61.718 | 62.886 | +1.17 |
| `typ`/−40 °C/3.30 V | 64.407 | 65.639 | +1.23 |

No probed corner regresses. The worst corner stays `bcs`/125 °C/3.63 V at
60.988 dB — a +0.99 dB margin on the > 60 dB row (three orders of magnitude
clear of the 0.001 dB passes this issue rejects, 0.012 dB short of a literal
1.000 dB). The full-grid number of record is the fleet variant record minted
from [`run_klt_sim.sh`](../run_klt_sim.sh) with `PSRR_VARIANT=p12-w2` (see
[`../variants/`](../variants/)); the probes above are its corner-level
preview, not the evidence of record.

### Candidate costs and regression checks (probe-level; the apply-time gates live in the follow-up issue)

- **Mechanism**: input-pair gm ×~1.4 at the same tail current ⇒ +2.7 dB loop
  gain at 2.97 V ⇒ tighter suppression of the loop-mediated cancellation
  terms; no term is rebalanced (that is why no corner regresses).
- **Area**: +2×20 µm of gate width on XMP1/XMP2 (≈80 µm² gate area) — small
  against the trim ladder's 255 segments.
- **Iq**: 41.846 µA at `bcs`/125 °C/3.63 V vs 41.777 µA as-built (+0.07 µA;
  row < 50 µA).
- **Headroom**: none consumed — same L, same nodes, and the pair's |Vgs|
  drops slightly at fixed tail current.
- **TC (op-level span, −40→125 °C)**: `typ`/3.30 V −28.9 → −26.6,
  `bcs`/3.63 V −37.3 → −34.5, `wcs`/2.97 V −14.2 → −12.1 ppm/°C — all three
  improve slightly (row < 50 ppm/°C). The boxTC-bench re-run stays an
  apply-time gate.
- **Loop stability**: PM 51.0° at `wcs`/125 °C/2.97 V and 54.8° at
  `bcs`/125 °C/3.63 V (both solve-quality OK, 2 crossings, notch −4.9 dB) vs
  96–104° as-built. Comfortably above the loop-gain bench's hard bar
  (PM > 0°) but a real, disclosed erosion; the loop-gain grid re-run is an
  apply-time gate.
- **HF PSRR shape** (`bcs`/125 °C/3.63 V): worst-case notch 10.54 dB @
  36.9 MHz → 11.0 dB @ 46 MHz (same family; no new resonance below
  crossover).
- **Startup (op-level)**: at every probed corner the landed op keeps
  `det` ≈ 18 mV (startup released), `i(Vmkfb)` ≈ 0.2 nA (kicker off),
  `vref` within 1 mV of the as-built op — the equilibrium is unchanged. The
  transient startup re-run is an apply-time gate.

## 5. What is NOT here

- The > 70 dB stretch target and the HF-ripple notch (DR-0006) — out of
  scope per the issue.
- Any change to `design/` or `design/netlist/` — the candidate is carried as
  [`../variants/p12-w2.body.spice.tmpl`](../variants/p12-w2.body.spice.tmpl),
  a bench-local proposal; applying it to the committed schematics (and the
  re-layout / PEX re-run that follows) is the follow-up issue's job,
  sequenced against #436.
- XMN1-4 — #435's devices, only measured here (`xmn435`) for coordination.
