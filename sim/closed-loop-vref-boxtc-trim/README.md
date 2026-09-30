# closed-loop-vref-boxtc-trim

Post-trim **box-method temperature-coefficient bench** (issue #229) — the
post-trim TC re-measurement DR-0011's ±0.5% trimmed budget obligates:
*"a post-trim TC re-measurement bounding the trim-induced TC degradation
(DR-0010's ±0.5% budget carries ~0.17% headroom for it — an estimate to
verify, not a measurement)"*.

It is [`../closed-loop-vref-pvt-boxtc/`](../closed-loop-vref-pvt-boxtc/README.md)
(issue #222) re-pointed at the trim-bearing core with a trim-code axis:
the **same** transient fixture (200 µs supply ramp, 3 ms hold), the same
solver options, the same settledness convention
(|vref(3ms) − vref(2ms)| ≤ 1 mV plus the startup-release / loop-closure /
not-railed prerequisites) and every `.measure` — only the DUT differs
(R1 base `l=37.2u` + the 255-unit ladder, subcircuit copied
device-for-device from `design/netlist/bandgap_trim.spice`) and the code
is swept per point via the subcircuit-local `.param trim_code`.

## Why a code axis

The core's one knob sets both the output level and the TC (the R1/R2
ratio is the PTAT gain): moving off the code-128 TC-null by design
*adds* TC. The trim's job (per DR-0011) is to correct each die **toward**
the TC-null point, so a correctly-trimed die sits near the null — but a
die trimmed many codes away sits measurably off it. This bench bounds
that trim-induced TC degradation:

| code | role |
|---|---|
| 128 | the schematic default — total R1_eff ≈ the pre-trim 511 µm single instance; the TC-null baseline, expected to reproduce the committed pre-trim box-TC evidence |
| 64, 192 | the ±64-code band around default that the trim-domain MC's `code*` population actually lands in ([`../closed-loop-vref-trim-mc/`](../closed-loop-vref-trim-mc/README.md)) |
| 0, 255 | the rails — the worst trim-induced TC the ladder can produce at all, bounding the sensitivity even for dies outside the covered population |

**Claim gate**: over the ±64 band (the codes real dies use), the
worst-case trim-induced box-TC delta × the 98 °C span from the 27 °C trim
point to either rail must stay inside the ~0.175% headroom DR-0011's
budget table carries for trim-induced TC drift (0.5% − 0.20% TC drift −
0.125% quantization). `records/<record-id>-trimdtc.csv` carries each
corner/supply group's deltas and gate status.

## Grid

Process corner `{typ, bcs, wcs, sf, fs}` × trim code `{128, 64, 192,
0, 255}` × temperature `{−40, −20, 0, 27, 50, 75, 100, 125} °C` × supply
`{2.97, 3.30, 3.63} V` — 600 transient points (5× the pre-trim boxtc
bench's 120; the code axis is the multiplier). `TRIM_CODES="128 192"` can
scope a re-run to a code subset — the record mints a new `<record-id>`
either way.

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
