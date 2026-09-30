# closed-loop-vref-boxtc-trim

Post-trim **box-method temperature-coefficient bench** (issue #229) — the
post-trim TC re-measurement DR-0011's ±0.5% trimmed budget obligates:
*"a post-trim TC re-measurement bounding the trim-induced TC degradation
(DR-0010's ±0.5% budget carries ~0.17% headroom for it — an estimate to
verify, not a measurement)"*.

It is [`../closed-loop-vref-pvt-boxtc/`](../closed-loop-vref-pvt-boxtc/README.md)
(issue #222) re-pointed at the trim-bearing core with a trim-code axis:
the **same** transient fixture (200 µs supply ramp, 3 ms hold), the same
settledness convention (|vref(3ms) − vref(2ms)| ≤ 1 mV plus the
startup-release / loop-closure / not-railed prerequisites) and every
`.measure` — only the DUT differs (R1 base `l=37.2u` + the 255-unit
ladder, subcircuit copied device-for-device from
`design/netlist/bandgap_trim.spice`) and the code is swept per point via
the subcircuit-local `.param trim_code`.

### Solver options (one deliberate deviation from the #222 bench)

`rshunt=1e9` / `gmin=1e-9` — the pre-trim bench's convergence aids — are
**dropped** here (`reltol=5e-3` + `tran 50n`, the #149 timestep-stiffness
pair, are kept). The aids assume a circuit with a handful of
high-impedance nodes; the ladder adds 254 interior series nodes, and at
1 GΩ ‖ 1 nS each they leak a measured ~0.55 µA out of the output branch:
at code 128 / typ / 27 °C the settled transient reads 1.01206 V **with**
the aids vs 1.04728 V without — a 37 mV artifact (and the pre-trim
circuit itself reads 2.2 mV high at 125 °C with them, A/B-tested by
stripping the aids from the committed #222 snapshot netlist). Without the
aids, this bench's settled transient agrees with a plain `.op` of the
same netlist to 5 significant figures (verified at typ/27 °C and
typ/125 °C) — that tran↔op equivalence is the bench's own internal
cross-check, and its code-128 rows are what `sim/trim-coverage/`'s `.op`
rows reproduce at the shared points.

## Why a code axis — and why the gated band is ±1 code, not ±64

The core's one knob sets both the output level and the TC (the R1/R2
ratio is the PTAT gain): moving a die off **its own** TC-null adds TC.
The key physics (see
[`../../design/bandgap_trim_network.md`](../../design/bandgap_trim_network.md)
§3): the mismatch population's errors are PTAT-shaped (loop-current
scaling, R1/R2 ratio, ΔVBE), so correcting a die's level with R1 restores
**its own** null ratio — a correctly-trimmed die sits at its own null
whatever `code*` it lands on. The trim-induced TC that remains comes from
the **sub-code mis-aim**: ±½ LSB of quantization plus the chord-fit aim
error (bounded <~0.4 LSB by `sim/trim-coverage/`'s measured full-scale
curvature) — i.e. ≤ ~1 code off null.

| code | grid | role |
|---|---|---|
| 127, 128, 129 | full corner × supply × 8 temps | the ±1-code mis-aim band real trims land in — **the claim gate** |
| 0, 64, 192, 255 | `{typ, bcs, wcs}` × 3.30 V × 8 temps | the TC-vs-code sensitivity slope and its saturation — reported, ungated (a correctly-trimmed die never sits there; a mis-trimmed one is bounded by them) |

**Claim gate**: the worst ±1-code box-TC delta vs the code-128 baseline,
over the full corner/supply grid, × the 98 °C span from the 27 °C trim
point, must stay inside the ~0.175% headroom DR-0011's budget table
carries for trim-induced TC drift (0.5% − 0.20% TC drift − 0.125%
quantization) — i.e. a delta cap of ~18.75 ppm/°C.
`records/<record-id>-trimdtc.csv` carries each group's delta and gate
status.

## Grid

Codes {127, 128, 129} × `{typ, bcs, wcs, sf, fs}` × 8 temperatures ×
`{2.97, 3.30, 3.63} V` (360 points) + codes {0, 64, 192, 255} ×
`{typ, bcs, wcs}` × 3.30 V × 8 temperatures (96 points) — 456 transient
points (3.8× the pre-trim boxtc bench's 120; the code axis is the
multiplier).

## What this testbench claims, and what it does not

**It claims**: `vref`'s box-method TC
(`1e6·(vmax − vmin)/(165·vref(27 °C))` over the 8-point grid's sampled
extrema) per (corner, code, supply) group, through the real closed loop
with the real ladder at each code, and the trim-induced TC delta vs the
code-128 baseline. NOT a claim against a different target — the ratified
TC row (< 50 ppm/°C target) is unchanged by this record.

**It does not** run mismatch draws (deterministic sections only — the
per-die trimmed spread is the trim-MC's claim) and is pre-layout, like
every `closed-loop-*` experiment here.

## Pass/fail criteria

Identical to `../closed-loop-vref-pvt-boxtc/`'s four criteria (startup
released, loop closed, not railed, settled) — a point that is not a
genuine settled closed-loop operating point contributes no `vref` to its
group's box, disclosed as `n_pass < n_grid` in
`records/<record-id>-boxtc.csv` and justified from this record's own
committed flanking points, never a scratch re-run.

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent of ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time
JOBS=8 sim/closed-loop-vref-boxtc-trim/run_pvt_sweep.sh
```

Requires ngspice plus the OSDI models, and at least one committed
`sim/closed-loop-startup/records/*.csv` is NOT needed by this bench (no
`.nodeset` seeding — the transient ramps from 0 V like every `*-boxtc`
point). Writes append-only evidence under `corners/<record-id>/`,
`netlist-snapshots/<record-id>/` and
`records/<record-id>.{md,csv,-boxtc.csv,-trimdtc.csv}` — see
[`../README.md`](../README.md).
