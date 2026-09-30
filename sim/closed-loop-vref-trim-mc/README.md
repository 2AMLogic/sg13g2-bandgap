# closed-loop-vref-trim-mc

Trim-domain **device-mismatch Monte Carlo with a modeled 1-point 27 °C
trim** (issue #229) — the trimmed-line evidence DR-0011's re-cast
Output-reference row obligates: *"a trim-domain mismatch Monte Carlo
demonstrating the ±0.5% trimmed line over −40…125 °C after a modeled
1-point 27 °C trim"*. It is
[`../closed-loop-vref-mc/`](../closed-loop-vref-mc/README.md)'s (issue #215's)
trim-domain twin: the same `_mismatch` corner-lib sections, the same
`.options rndseed` parse-time discipline (verified there by direct
experiment — the mismatch expressions evaluate once, at netlist-parse
time, so the seed must be read before any `.lib`), the same
`.nodeset`-seeded single-`.op`-per-netlist technique, and the same
negative-control hard gate.

## What this testbench claims, and what it does not

**It claims**: after a per-die 1-point trim at 27 °C (the die's own
corner, targeting DR-0011's 1.050 V TC-null point — never 1.2 V), the
closed-loop `vref` of N ≥ 300 seeded device-mismatch draws stays inside
**±0.5% of 1.050 V over −40…125 °C** at the 3σ level — the
trimmed-line counterpart of the untrimmed ±16% (3σ) line the #215 MC
established. Per-die data: the chosen trim code `code*`, its
distribution (mean/σ/min/max, railed count), the measured per-die trim
unit (mV/LSB) and the fit's linearity residual — all in
`records/<record-id>-draws.csv`.

**The modeled trim is a real ladder measurement, not an ideal voltage
knob.** Each draw runs six netlists through the actual 255-unit ladder:

1. **Fit** (27 °C, codes `{0, 1, 255}`): `vref(code) = a + unit·code`
   from codes 0/1; code 255 measures the linearity residual rather than
   assuming it. `code* = clip(round((1.050 − a)/unit), 0, 255)` — the
   code a wafer-sort 1-point trim would pick for this die.
2. **Verify** (`code*`, temps `{−40, 27, 125}` °C): the trimmed die's
   `vref`; the trimmed line is `max_T |vref(T) − 1.050|/1.050`.

**Die identity is preserved across a draw's six netlists**: the device
draw is a pure function of (`.options rndseed`, the device instance
list), and every netlist of one draw shares both — only
`.param trim_code` and `.options temp` differ, neither of which touches
the draw. The fit at 27 °C and the verification at −40/125 °C are
therefore the SAME die.

**The ladder's own mismatch is part of the evidence**: all 255 unit
segments and the R1 base are inside the `res_*_mismatch` draw, so the
trim-domain spread includes the trim network's contribution, not just
the core's.

**It does not claim the trim covers every die.** A draw whose `code*`
rails at 0/255 is disclosed (`railed=1` in the draws CSV, `n_railed` in
the digest) — the ladder is sized so the correlated-coverage analysis in
`design/bandgap_trim_network.md` puts the rail beyond ±3.5σ of the
mismatch distribution, and this campaign measures where the population
actually lands. It also does not re-run the supply axis (held at 3.30 V
for the same stated reason as #215) and is pre-layout (like every
`closed-loop-*` experiment here).

## Points

| point | sections | trim at | verify at |
|---|---|---|---|
| `nominal` | `*_typ_mismatch` | 27 °C, typ | −40/27/125 °C |
| `negctrl` | plain (typ) | 27 °C, typ | −40/27/125 °C |
| `bcs` | `*_bcs_mismatch` | 27 °C, bcs | −40/27/125 °C |
| `wcs` | `*_wcs_mismatch` | 27 °C, wcs | −40/27/125 °C |

Negative control (hard gate): the same seeds against the plain sections
must trim to **exactly zero spread** at every draw and every verify
temperature — any spread is a driver bug (a mismatch section leaked in,
or a seed not reaching parse), and the run aborts without writing a
record, exactly as #215's does.

## Pass/fail criteria

Per draw: all six `.op`s converge with the loop genuinely closed and not
railed (`pvt_closed_loop_verdict`, same shared thresholds). Per point:
`n_pass == n_draws`, the negative control is exactly zero-spread, and —
the claim gate — **3σ of the per-draw max-temperature deviation ≤ 0.5%**
at every mismatch point. The fraction of draws inside ±0.5%
(`frac_within_0p5_pct`) is reported alongside (the 3σ gate is the
binding one, matching how the untrimmed line is a 3σ line).

## Evidence volume

Same discipline as #215: per-draw netlists and logs are NOT committed
(24 × N ≈ 7200 of them at N=300); the committed evidence is the digest
CSV (one row per point), the per-draw summary CSV
(`<record-id>-draws.csv`, one row per draw — the raw data the digest
summarizes), and ONE representative netlist+log per point (draw 0's
27 °C verify stage). The scratch directory is deleted on exit.

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent of ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time
sim/closed-loop-vref-trim-mc/run_trim_mc.sh --seed 20260930 --n 300
```

Requires at least one committed `sim/closed-loop-startup/records/*.csv`
(per-corner `.nodeset` seeds). Writes append-only evidence under
`netlist-snapshots/<record-id>/`, `corners/<record-id>/` and
`records/<record-id>.{md,csv,-draws.csv}` — see
[`../README.md`](../README.md).
