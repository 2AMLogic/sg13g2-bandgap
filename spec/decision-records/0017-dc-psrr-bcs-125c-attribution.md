# 0017: DC PSRR at `bcs`/125 °C/3.63 V — attribute the miss, carry the fix as a bench-local candidate (wider amp input pair), do not touch the committed design yet

- **Status**: proposed
- **Date**: 2026-11-21
- **Decided by**: Loom Builder agent, issue #631

## Context

The T1 item-5 PSRR-@-DC row (> 60 dB) misses at exactly one of 45 PVT
points: `bcs`/125 °C/3.63 V reads 59.685 dB in the schematic record of
reference ([`sim/closed-loop-psrr/records/20261113-085406-9d568b91.csv](../sim/closed-loop-psrr/records/20261113-085406-9d568b91.csv)),
and the row has been marginal on the layout side too (post-layout worst
60.001 dB, then 59.997 dB on PR #383's extraction, per #387). Issue #631
asked for (a) a measured attribution of what sets the limit, (b) a bounded
fix proposal carried **without** editing `design/` — PR #435 has demonstrated
the stuck shape a premature netlist change produces (red hygiene since
2026-10-30 on the PEX-generator self-test, waiting on the #436 re-layout) —
and (c) a fleet grid proving the candidate. The attribution
([`sim/closed-loop-psrr/attribution/`](../sim/closed-loop-psrr/attribution/))
found the limit is not a leak but a **near-cancellation**: at the binding
corners the vdd→vref transfer is a ~1 µV/V residue of opposing tens-of-µV/V
terms — the amp output-mirror feedthrough (XMP3/XMP4, ≈ −73 µV/V) against
the loop-mediated terms (XMP3/4's tail, pair and core-mirror counterparts,
+18 to +53 µV/V each), with the startup branch contributing nothing and a
93 dB floor once all MOS supply coupling is ablated. The candidate screen
then measured that **every single-term scaling fails**: core-mirror or tail
lengthening moves the wrong corners (−1.6 to −3.0 dB at `bcs`), and ANY
length scaling of XMP3/XMP4 — the term that dominates — collapses the pn
pole into the loop's 40–50 MHz crossover (PM −16.5° at ×2, −41° at ×4; the
same solve-quality-gated probe that reproduces the committed loop-gain
record's margins to 0.3°). The one bounded knob that helps every binding
corner without destabilizing the loop is **more input-pair gm at unchanged
length**: XMP1/XMP2 20u/1u → 40u/1u (`p12-w2`), +2.7 dB loop gain, no
corner regressed across twelve probed PVT points, PM 51–55°, Iq +0.07 µA,
op-level TC spans improved 2–3 ppm/°C.

## Decision

1. The DC-PSRR row's limit at `bcs`/125 °C/3.63 V is **recorded as the
   cancellation residue measured in
   [`sim/closed-loop-psrr/attribution/README.md`](../sim/closed-loop-psrr/attribution/README.md)**,
   with the fix screen and the two structural findings (stability budget
   spent; single-term scaling cannot fix the row). No spec row or bound
   changes.
2. The bounded fix proposal is **XMP1/XMP2 widened 20u/1u → 40u/1u**,
   carried as the bench-local variant
   [`sim/closed-loop-psrr/variants/p12-w2.body.spice.tmpl`](../sim/closed-loop-psrr/variants/p12-w2.body.spice.tmpl)
   — a proposal, not the as-built DUT — grid-verified by the variant fleet
   record named in §3 below (`run_klt_sim.sh` with `PSRR_VARIANT=p12-w2`,
   the mechanism this record adds). `design/` and `design/netlist/` stay
   untouched; the change reaches the committed design only through the
   follow-up issue, sequenced after #436's re-layout lands and jointly with
   #435 (whose XMN1-4 resize moves this row −7 dB at `bcs` and +18 dB at
   `fs`/2.97 V, and whose own loop stability at `wcs`/125 °C/2.97 V measured
   unsolved-quality here).
3. Applying the candidate to `design/` is **gated on the apply-time
   re-verification matrix** filed as
   [#638](https://github.com/2AMLogic/sg13g2-bandgap/issues/638): the full
   boxTC/vref-PVT, startup transient, loop-gain grid and Iq re-runs on the
   changed core (probe-level checks here: TC spans improve, PM 51–55° with
   solve-quality OK, startup released at every probed op, Iq 41.85 µA worst),
   then the re-layout and post-layout PSRR re-run.

## Alternatives considered

- **Lengthen XMP3/XMP4 (×2 or ×4)** — numerically fixes `bcs` (+4.8 to
  +8.3 dB) but measured unstable (PM −16.5°/−41°, solve-quality OK solves);
  rejected on the stability evidence, not on PSRR.
- **Lengthen the core PMOS mirror or the amp tail** — measured wrong-direction
  at the miss corner (−1.6 to −3.0 dB) while helping 2.97 V corners; rejected.
- **Scale every supply PMOS together (`allpmos-l2`)** — same corner
  opposition as the tail alone; rejected.
- **PR #435's XMN1-4 resize as the vehicle** — out of scope here by the
  issue's own instruction, and measured to deepen the `bcs` miss to 52.7 dB;
  any joint disposition belongs to the follow-up.
- **Widen the input pair further (×3, ×4) or lengthen it (40u/2u)** — all
  fail the #289 solve-quality gate on the d1/d2 nodes; rejected.
- **A cascode on the output mirror** — the headroom study in the attribution
  record shows ~0.2 V slack at 2.97 V and it needs a new bias branch; kept as
  the named alternative if the row's post-layout margin demands more than
  `p12-w2`'s +1.3 dB at `bcs`, not chosen for a first bounded step.

## Consequences

- The > 60 dB row keeps its bound; the schematic grid of record for the
  candidate is variant fleet record
  [`sim/closed-loop-psrr/records/20261121-095519-80e1511e.md`](../sim/closed-loop-psrr/records/20261121-095519-80e1511e.md):
  45/45 points above 60 dB, worst corner `bcs`/125 °C/3.63 V at 60.9884 dB —
  a +0.988 dB margin (0.012 dB short of a literal 1.000 dB; the probes
  matched the fleet to 0.0004 dB).
- The amp's phase margin budget is the binding constraint this record adds
  to the design's common knowledge: future PSRR or gain work must budget
  against the 40–50 MHz crossover, and any XMN1-4 / XMP3-4 change must
  re-run the loop-gain grid, not assume it.
- Hygiene is unchanged: the variant is bench-local, records stay
  append-only, and the freshness checker's as-built line for this bench is
  untouched (the variant record names the variant template as its DUT).
