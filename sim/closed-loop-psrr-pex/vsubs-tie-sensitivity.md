# `vsubs` tie sensitivity — measured, not asserted

This experiment makes exactly one modelling choice that is not inherited
verbatim from an existing testbench in this tree: it returns every extracted
ground capacitance to `vss` (`Vvsubs vsubs vss dc 0`) instead of to the 1 TΩ
DC tie (`Rvsubs_dctie vsubs 0 1e12`) that `sim/core-open-loop-bias-pex` and
`sim/closed-loop-vref-pvt-pex` use. Because that choice is the only place this
bench could quietly flatter itself, it is measured here rather than argued.

**Why the choice exists.** `layout/bandgap_top/bandgap_top.pex.spice` reports
each net's ground capacitance against the node `vsubs` (the extractor's
substrate/far-plate convention). A DC or transient bench needs only *a* DC
path from that node, so 1 TΩ is fine there and guarantees zero DC influence.
A frequency-domain bench is different: at AC, a 1 TΩ return leaves `vsubs`
effectively floating, so each net's "ground" capacitance stops behaving as a
capacitance to ground and instead couples net-to-net in series with the other
nets' ground caps. In this block the far plate is the substrate, and the
substrate is tied to `vss` — the same tie `design/bandgap_core.sch`'s `sub!`
net carries, and the net every extracted device bulk terminal lands on
(`layout/bandgap_top/pex_extract_report.json`). So `vsubs` is shorted to `vss`
through a 0 V source (a DC and AC short that injects nothing).

**How this was measured.** `tools/vsubs_tie_sensitivity.sh` re-runs committed
per-point netlist snapshots both ways — as committed, and with that single
line swapped back to the 1 TΩ form — and summarises each AC curve with the
same `sim/closed-loop-psrr/tools/psrr_summary.awk` the sweep itself uses. It
writes nothing into the append-only evidence tree; reproduce with:

```bash
sim/closed-loop-psrr-pex/tools/vsubs_tie_sensitivity.sh 20260905-233826-f6f3efc
```

**Result** (record `20260905-233826-f6f3efc`, three representative PVT points —
nominal, slow/hot/low-supply, fast/cold/high-supply):

| point | tie | PSRR DC (dB) | worst PSRR (dB) | at (Hz) | 1 kHz (dB) | 100 kHz (dB) | 1 MHz (dB) |
|---|---|---|---|---|---|---|---|
| `typ_27c_3.30v` | `vss` short (committed) | 65.2635 | −1.6229 | 2.929e+07 | 65.2594 | 55.0511 | 35.4592 |
| `typ_27c_3.30v` | 1 TΩ float | 65.2634 | −0.5888 | 2.929e+07 | 65.2624 | 59.9836 | 41.4181 |
| `wcs_125c_2.97v` | `vss` short (committed) | 60.3095 | −1.7722 | 2.712e+07 | 60.3078 | 53.3611 | 34.3015 |
| `wcs_125c_2.97v` | 1 TΩ float | 60.3095 | −0.7740 | 2.712e+07 | 60.3090 | 57.3724 | 40.3150 |
| `bcs_-40c_3.63v` | `vss` short (committed) | 68.1254 | −1.2267 | 3.162e+07 | 68.1191 | 56.1989 | 36.4657 |
| `bcs_-40c_3.63v` | 1 TΩ float | 68.1254 | −0.2384 | 3.162e+07 | 68.1237 | 61.3623 | 42.3186 |

**What it says**, read off the table rather than assumed:

- **At DC the choice does not matter at all** — the two ties agree to
  ≤ 0.1 mdB at all three points, and to 4 decimal places at two of them. That
  is the expected result (a capacitor is an open circuit at DC) and is a
  useful sanity check that the swap changed nothing it should not have.
- **Above ~10 kHz it matters, and always in the same direction**: the 1 TΩ
  float reports PSRR **4.0–5.2 dB better at 100 kHz and 5.9–6.0 dB better at
  1 MHz**, and a worst-case dip ~1.0 dB shallower, at every point checked. The
  floating return partially decouples the extracted ground capacitance, so it
  systematically *understates* the parasitic loading this experiment exists to
  measure.
- Which is the load-bearing consequence: had this bench inherited the 1 TΩ
  fixture unexamined, its headline high-frequency numbers would have been
  optimistic by ~5–6 dB, and its worst-case-PSRR finding (see `README.md`)
  would have been softer than the layout supports. The frequency of the
  worst-case dip is unaffected (identical to the printed precision at all
  three points) — the tie changes how much ripple gets through, not where the
  resonance sits.

**Scope.** Three PVT points, not the full 45-point grid: the effect under test
is a property of the passive return network, not of the bias point, and the
three points span the corner grid's extremes. That is a deliberate
"sensitivity check" scope, the same one `sim/closed-loop-offset` uses for its
own three-point sweep — not an evidence record, which is why this lives here
rather than under `records/`.
