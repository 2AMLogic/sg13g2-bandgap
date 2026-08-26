# closed-loop-offset

Closed-loop **deterministic input-referred-offset sensitivity** check
(issue #88, follow-on to #86/#58) — an informal characterization of
offset/mismatch, the other item `design/README.md`'s issue #58 "Still not
attempted" list named alongside PSRR (see
[`../closed-loop-psrr/`](../closed-loop-psrr/README.md) for that one).

## What this testbench claims, and what it does not

**It is explicitly NOT a Monte Carlo / statistical mismatch study.** Monte
Carlo mismatch infrastructure does not exist in this repo and is tracked
separately (issue #4 checklist item 6, currently N/A per #5) — this
experiment does not build it, invoke it, or produce any statistical
(sigma/yield) claim. What it claims instead, following the escape hatch
this issue's own Acceptance Criteria offers ("a sensitivity or
single-point mismatch check"): a **deterministic** DC voltage source
(`Vos`) is inserted in series with `bandgap_amp`'s inverting input
(`in_n`/`XMP2`'s gate only), modeling a generic amplifier
input-referred-offset voltage. Sweeping `Vos` to `{0, +5mV, -5mV}` at
three representative PVT points (not the full 45-point grid — see
"Scope" below) and comparing the resulting `vref` measures this design's
own **vref sensitivity to an amplifier input offset**
(`dVref/dVos`, dimensionless V/V) — a property of the *topology*, useful
regardless of what this specific amplifier's *actual* offset happens to
be (which is unknown without real mismatch data).

**It does not claim to predict this design's actual offset or mismatch
magnitude.** `±5 mV` is an arbitrarily chosen, round probe value — not
derived from `npn13G2`/PSP103 Pelgrom mismatch coefficients or any
layout-specific matching data, none of which this repo has without Monte
Carlo infrastructure. A future Monte Carlo pass (once that infrastructure
exists) is what would answer "what IS this design's actual offset/yield" —
this experiment answers the narrower, still-useful question "if there
were an offset of a given size, how much would it move `vref`", which the
Monte Carlo pass could then combine with a real mismatch distribution.

**It does not claim conformance to any ratified spec row** —
`spec/porting-plan.md` has no offset/mismatch target row at all (§6's
seven-row table covers TC, PSRR, supply, Iq, area, startup — no offset
line item), so there is nothing to compare against even informally.

## Scope: three points, not a PVT sweep

Unlike every other closed-loop experiment in this tree, this check runs
**3 PVT points x 3 `Vos` values = 9 runs**, not the full 45-point grid:
`typ`/27°C/3.30V (nominal), `wcs`/-40°C/2.97V (coldest, lowest supply —
`sim/closed-loop-startup/README.md`'s own worst-margin corner) and
`bcs`/125°C/3.63V (hottest, highest supply). This is a deliberate choice,
not a shortcut taken under time pressure: the issue's own Acceptance
Criteria explicitly describes this scope as "a sensitivity or
**single-point** mismatch check" — a handful of representative points is
enough to show the sensitivity coefficient is stable across PVT (it is —
see "Results" below), and a full 45-point x 3-`Vos` = 135-run sweep would
not change that qualitative conclusion, only cost 15x the runtime for
information this check does not claim to need (this is not a PVT-graded
pass/fail bar the way PSRR's own dB figures are).

## Offset probe method

`design/bandgap_amp.sch`'s own topology has a single differential input
pair (`MP1`/`MP2`, tail node `tail`, PMOS gates `in_p`/`in_n`) — the
standard place to model an op-amp-style input-referred offset is in
series with one of the two inputs. This testbench splits the shared
`sns1` node into `sns1` (unchanged — everything else this co-simulation
uses, including `bandgap_startup`'s own `XMSENSE` gate, stays on the real
`sns1`) and `sns1_amp` (the amp-only copy `XMP2`'s gate connects to
instead), bridged by `Vos sns1_amp sns1 dc @@VOS@@`. A `Vos = 0V` probe
reduces this to a plain wire, exactly reproducing
`../closed-loop-vref-pvt/`'s own unmodified topology — confirmed in this
run's own data (the `Vos=0` row at each PVT point matches that
experiment's already-committed `vref` value within ~0.1-0.2%: `typ`
1.1654 V here vs. 1.16677 V there, `wcs` 1.1403 V vs. 1.14161 V, `bcs`
1.2004 V vs. 1.20184 V — the small residual is expected, not a bug: this
check's `.op` is a `.nodeset`-seeded fixed-point solve, while
`../closed-loop-vref-pvt/` measures a full `vdd`-ramp transient at
`t=2ms`/`t=3ms`, so the two are independent numerical paths to (very
nearly) the same answer, not the same computation repeated; see
`records/<record-id>.csv`'s `vos_tag=0` rows against
`../closed-loop-vref-pvt/records/*.csv`).

`XMSENSE` (the startup circuit's sense device) is deliberately left on
the real `sns1`, not `sns1_amp` — `bandgap_startup` is not part of "the
amplifier" the offset probe models, and `design/bandgap_top.sch` itself
only wires the amplifier's own inputs to the sense nodes; sensing the
amp-internal offset-shifted copy of `sns1` for a device outside the
amplifier would not represent any real signal in this circuit.

## DC bias

Same `.nodeset`-seeding technique
[`../loop-gain-phase-margin/`](../loop-gain-phase-margin/README.md) and
[`../closed-loop-psrr/`](../closed-loop-psrr/README.md) both use, seeded
from `../closed-loop-startup/`'s own committed per-corner converged
transient endpoint for the **real** (`Vos=0`) circuit — a useful
Newton-Raphson initial-guess hint even for the `Vos != 0` runs, which are
*expected* to converge to a nearby but genuinely different equilibrium
(that shift is the effect under test).

## Pass/fail criteria

Deliberately **not** "`.op` landed near its `Vos=0` seed" — an offset
probe is supposed to move the operating point away from that seed, so
reusing `../closed-loop-psrr/`'s exact check would fail every non-zero
`Vos` point by design and prove nothing. Instead, a point is `PASS` only
if:

1. **`.op` converges** (`ngspice` exit 0, no model-load error).
2. **The loop is still genuinely closed around its own (possibly
   `Vos`-shifted) equilibrium**: `|v(sns2) - v(sns1_amp)| <= 0.02 V` —
   confirms the amplifier's own high gain is still forcing its two real
   inputs together despite the injected offset (i.e. this is a real
   closed-loop DC operating point, not a railed or divergent one). All 9
   points in this run land far inside this bound (worst case 0.68 mV,
   `loop_err_v` column) — more than an order of magnitude tighter than
   the 20 mV tolerance, consistent with the ~45-47 dB DC loop gain
   `../loop-gain-phase-margin/` independently measured for this design.
3. **`vref` lands in a plausible in-range band** (`0.3 V <= vref <= vdd`)
   — not railed to a supply or to 0 V.

## Results (this repo's own committed record)

9/9 points PASS. `vref` sensitivity to the amplifier's own input-referred
offset is essentially flat across the three PVT points swept:

| corner (typ 27°C/3.30V etc.) | `dVref/dVos` (V/V) |
|-------------------------------|---------------------|
| `typ` / 27°C / 3.30V           | 8.79 |
| `wcs` / -40°C / 2.97V          | 8.80 |
| `bcs` / 125°C / 3.63V          | 8.78 |

**Cross-checked against a hand-derived physical estimate, not just
reported as-is.** This design's core (`design/bandgap_core.sch`) mirrors
the same current through `R2` (`XR2`, `l=82.7u`) and `R1` (`XR1`,
`l=694.5u`) via three identically-sized PMOS legs. To first order, the
loop forces `sns2 ≈ sns1 + Vos` (the amplifier's own effective input
error nulled around whatever offset is injected), so the mirrored current
shifts by approximately `Vos/R2`, and `vref` (which sits across `R1` from
the same mirrored current) shifts by approximately
`Vos * (R1/R2) = Vos * (694.5/82.7) = Vos * 8.40`. The measured
`dVref/dVos ≈ 8.78-8.80` is within ~5% of that estimate — close enough to
confirm the simulated sensitivity is a real, explicable circuit property
(the resistor ratio that also sets this design's PTAT gain), not a
testbench artifact, while the small residual (higher than the pure `R1/R2`
first-order estimate) is expected from the second-order paths the
back-of-envelope estimate ignores (the mirror legs' own finite output
impedance, `Q3`'s own `Vbe` shift, and the amplifier's own finite — not
infinite — DC gain).

**What this means in plain terms**: a 5 mV amplifier input offset would
move this design's `vref` by roughly 44 mV (`5mV * 8.79`) — a real, sizable
shift relative to `vref`'s own ~1.13-1.22 V nominal range (`sim/closed-loop-vref-pvt`'s
own committed band), underscoring why an untrimmed reference like this one
(no trim network — issue #9's explicit scope cut) is offset-sensitive, and
why a future Monte Carlo pass (once that infrastructure exists) is the
right way to learn whether this specific amplifier's *real* offset,
combined with this now-measured 8.8x sensitivity, is small enough to
matter for this design's eventual application.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-offset/run_offset_check.sh
```

Requires a committed `../closed-loop-startup/records/*.csv` to exist (see
"DC bias" above) — already true in this repo; no separate
`closed-loop-startup` run is required first.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows —
this experiment follows the same shape, just with a smaller (9-point, not
45-point) corner matrix (see "Scope" above for why that is deliberate).
