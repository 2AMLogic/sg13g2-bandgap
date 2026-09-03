# closed-loop-psrr

Closed-loop **small-signal AC power-supply-rejection (PSRR)** testbench
(issue #88, follow-on to #86/#58) — the measurement `design/README.md`'s
issue #58 "Still not attempted" list named as open, alongside offset/
mismatch (see [`../closed-loop-offset/`](../closed-loop-offset/README.md)
for that one). Co-simulates `design/bandgap_core.sch` +
`design/bandgap_amp.sch` + `design/bandgap_startup.sch` — the same three
DUTs, wired exactly as `design/bandgap_top.sch` specifies, that
[`../closed-loop-startup/`](../closed-loop-startup/README.md),
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md) and
[`../loop-gain-phase-margin/`](../loop-gain-phase-margin/README.md) all
use — but, unlike `loop-gain-phase-margin`, does **not** break the `fb`
loop. PSRR is inherently a closed-loop measurement (how well the
already-closed loop rejects a disturbance injected on its own supply
rail), so this testbench injects an AC perturbation directly on `vdd`
instead, around a `.nodeset`-seeded DC operating point.

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x
HBT/MOS/resistor-process-corner PVT grid, at the real closed-loop DC
operating point (verified per point — see "op landed near its seed"
below), the closed loop attenuates a small-signal `vdd` perturbation at
`vref` by **57.1-105.2 dB at DC**, degrading to a worst case of
**3.2-4.8 dB** (per-corner minimum across the full 1 Hz-1 GHz sweep) near
**31-40 MHz** — see `records/<record-id>.csv` for the full 45-point table
(columns `psrr_dc_db`, `psrr_min_db`/`psrr_min_freq_hz`, and three spot
values `psrr_1khz_db`/`psrr_100khz_db`/`psrr_1mhz_db`). PSRR never goes
negative anywhere in the swept range at any corner (i.e. `vref` ripple is
never larger than the injected `vdd` ripple) — see "Sign convention" for
why that is the expected, physically sane result for this convention, not
an assumption.

**It does not claim conformance to any ratified spec row.**
`spec/porting-plan.md` §6 carries a **draft, unratified** `PSRR @ DC | > 60
dB` target row (#125 tracks ratification generally; that number has never
been checked against real evidence before this testbench). This record's
own DC-PSRR range (57.1-105.2 dB) straddles that draft number at some
corners and clears it by a wide margin at others — **this is stated as
context only, not a pass/fail verdict**: per `klayout-tools`'
`docs/design-evidence-tiers.md` T1 checklist (referenced from issue #4),
producing the capability to run this comparison is not the same as running
it as a ratified check, and no checklist item on #4 is closed by this
record. It does not claim the design meets any offset/mismatch target
either (see `../closed-loop-offset/README.md` for that separate,
explicitly-informal characterization).

## Injection method

### Why inject on `vdd` directly, not a loop-break probe

`../loop-gain-phase-margin/` breaks the shared `fb` node with a
Middlebrook single-voltage-injection probe because *loop gain* is, by
definition, a property of the open-loop transfer function around the
loop — it has no meaning without first opening the loop somewhere. PSRR
is different: it is explicitly a **closed-loop** figure of merit — "how
much of the supply's own ripple survives, in this design's real operating
condition, feedback and all, at the output node". Breaking the loop to
measure it would answer a different, less useful question (open-loop
supply sensitivity, which says nothing about how the assembled,
self-regulating circuit behaves). So this testbench keeps `fb` a single,
unbroken node — exactly `../closed-loop-startup/`'s and
`../closed-loop-vref-pvt/`'s own topology — and instead injects the
disturbance at its true physical source: `Vvdd`'s own AC term
(`Vvdd vdd 0 dc @@VDD@@ ac 1 0`). `Vvss` (the ground/reference every node,
including `vref`, is ultimately measured against) stays at a separate,
unperturbed `dc 0` source — exactly the textbook PSRR setup: perturb the
rail under test, hold the reference rail still, read the ripple that
reaches the node of interest.

### DC bias: `.nodeset`, for the same reason `loop-gain-phase-margin` needs it

This circuit has (at least) two DC equilibria — the intended closed-loop
operating point and the degenerate all-off state
`design/bandgap_startup.sch` exists to kick the circuit out of (see
`../closed-loop-startup/README.md`). A bare `.op` with no bring-up and no
bias hint has no guaranteed way to land in the intended basin. Unlike
`loop-gain-phase-margin`, this testbench's own topology does not disrupt
`fb`'s fast dynamics (the loop is never split), so in principle a
transient bring-up analogous to `closed-loop-startup`'s vdd-ramp could
work here too — but `.nodeset`-seeding from `../closed-loop-startup/`'s
own most recent committed record is simpler, already proven, and
sufficient: it is (very nearly) the true answer for this exact corner, so
`.op`'s Newton-Raphson converges to it directly. `run_pvt_sweep.sh` reads
`fb_final_v`/`sns1_final_v`/`sns2_final_v`/`vref_final_v` for the matching
`corner_label`/`temp_c`/`vdd_v` row out of that experiment's own most
recent committed record CSV (looked up by column name, exactly as
`../loop-gain-phase-margin/run_pvt_sweep.sh` does), and fails loudly (exit
3) if no such record exists.

### "op landed near its seed" — verified per point, not just trusted

`run_pvt_sweep.sh` compares the resulting `v(fb)` against its own
`.nodeset` seed after `.op` converges and fails the point outright
(`|fb_op - fb_seed| > 0.05 V`) rather than silently reporting a PSRR curve
computed around the wrong equilibrium — the same tolerance and rationale
`../loop-gain-phase-margin/` uses for the identical check. All 45 points in
this run's own committed record pass this check (see
`records/<record-id>.csv`'s `fb_seed_v`/`fb_op_v` columns).

## Sign convention

**Derived, not assumed.** The testbench's `Vvdd` carries a 1 V∠0°
small-signal AC stimulus (`ac 1 0`) superimposed on its DC bias. Because
`0 dB = 20·log10(1)`, that stimulus magnitude is itself exactly 0 dB, so
the standard closed-loop PSRR definition —

```
PSRR(f) [dB] = 20*log10( |Δvdd(f)| / |Δvref(f)| )
```

— reduces, for this specific 1 V-magnitude stimulus, to
`PSRR(f) = -20*log10(|v(vref,f)|) = -db(v(vref))` directly (`ngspice`'s
`db()` operator is already `20*log10(|.|)` of its complex argument). This
is exactly what the testbench computes
(`let psrr_db = -db(v(vref))`). Under this convention, **a larger
`PSRR_dB` is better rejection** (less of the injected `vdd` ripple reaches
`vref`) — the conventional PSRR sense, and the same sense
`spec/porting-plan.md` §6's draft target (`> 60 dB`) uses, which is why no
extra sign flip or unit conversion is applied anywhere downstream of this
`.control` block.

**Verified empirically, not just derived analytically**: `vref` is a
linear combination of several supply-coupled paths in this circuit (the
three PMOS mirror legs' own drain-source modulation by `vdd`, the
amplifier's own supply-referred bias currents, and the closed-loop
correction those disturbances themselves induce through `fb`) — too many
interacting paths for a clean hand-derived closed-form sign proof the way
`../loop-gain-phase-margin/README.md`'s single-loop-break polarity
argument manages. Instead this convention is validated against two
independent, physically-motivated sanity checks, both of which hold at
every one of the 45 committed points:

1. **PSRR is never negative anywhere in the swept range.** A negative
   value under this convention would mean `vref`'s ripple is *larger* than
   the injected `vdd` ripple — net amplification of supply noise, which
   would be a red flag (either a real circuit problem or a sign error in
   this testbench). The worst point in this run's entire 45-corner x
   1 Hz-1 GHz sweep is `+3.2 dB` (`psrr_min_db`, wcs/-40°C/3.63V) — always
   attenuation, never amplification.
2. **PSRR degrades sharply near the loop's own independently-measured
   unity-gain crossover.** `../loop-gain-phase-margin/`'s own record
   (issue #86) measured this design's loop-gain unity-gain crossover at
   **41.5-53.3 MHz** across the same 45-point grid. This testbench's own
   worst-case (minimum) PSRR in every corner falls at **31-40 MHz**
   (`psrr_min_freq_hz` column) — the same decade, from a wholly
   independent AC analysis with a different injection point and a
   different `.control` block. This is exactly the expected physical
   picture: negative feedback is what suppresses a `vdd` disturbance's
   effect on `vref` at low frequency, and that suppression can only be as
   good as the loop's own gain, which collapses toward the same
   frequency band `loop-gain-phase-margin` already found the loop's own
   gain crosses 0 dB. Two independently-built testbenches agreeing on
   *where* this design's regulation runs out of headroom is strong
   corroboration that both are measuring the same real effect, under a
   sign convention that produces physically sane numbers.

## A real feature at 27°C/3.63V, not a bug: anomalously high DC PSRR at one bias point

Every process corner in this run shows an unusually high DC PSRR
specifically at **27°C, 3.63V** (e.g. `typ`: 84.8 dB vs. 57-68 dB at its
other two supply points; `fs`: 105.2 dB, the single highest value in the
whole grid). Inspecting the raw AC data explains why: at that one bias
point, `v(vref)`'s DC phase is close to **-180°**, vs. close to **0°** at
the same corner's 2.97V/3.30V points (see
`corners/<record-id>/*_27c_3.63v.ac.txt` vs. `*_27c_3.30v.ac.txt`). This
is the signature of a genuine sign change in the net `vdd`-to-`vref`
transfer function as `vdd` is swept from 3.30V to 3.63V at this one
temperature — i.e. a real zero of that transfer function sits somewhere
in that 0.33V window, where the multiple supply-coupled feedthrough paths
described in "Sign convention" above pass through a near-exact
cancellation. This produces an anomalously *good*, but fragile and
bias-point-specific, PSRR reading — not evidence that this design
achieves 80-105 dB PSRR generally (it plainly does not — the same
process corner reads 57-68 dB at its other two supply points). The
**worst-case per-corner DC value (57.1 dB)** and the **worst-case
across the full swept range (3.2 dB, near the loop crossover)** are the
figures that characterize this design's real PSRR; the 27°C/3.63V spike
is called out here so a future reader does not mistake it for the
design's typical behavior.

## Pass/fail criteria

A point is `PASS` only if:

1. **`.op` landed near its seed**: `|v(fb) - fb_seed| <= 0.05 V` — see
   "op landed near its seed" above.
2. **The `.ac` sweep produced data** — a PSRR curve to measure.

`ngspice` exiting non-zero or a model-load error also fails the point,
same convention as every other testbench in this tree. **This testbench
does not gate PASS/FAIL on the PSRR value itself** — no ratified spec
target exists to compare against (see "What this testbench claims, and
what it does not"), so `PASS` here means "a trustworthy PSRR measurement
was produced at the real closed-loop operating point", not "PSRR met some
bar".

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../loop-gain-phase-margin/`](../loop-gain-phase-margin/README.md) and
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md):

| label | `cornerHBT.lib` | `cornerMOShv.lib` | `cornerRES.lib` |
|-------|-----------------|-------------------|-----------------|
| `typ` | `hbt_typ`       | `mos_tt`          | `res_typ`       |
| `bcs` | `hbt_bcs`       | `mos_ff`          | `res_bcs`       |
| `wcs` | `hbt_wcs`       | `mos_ss`          | `res_wcs`       |
| `sf`  | `hbt_typ`       | `mos_sf`          | `res_typ`       |
| `fs`  | `hbt_typ`       | `mos_fs`          | `res_typ`       |

x temperature `{-40, 27, 125} °C` x supply `{2.97, 3.30, 3.63} V` = 45
points.

## Results summary (this repo's own committed record)

45/45 points PASS. DC PSRR **57.1-105.2 dB** across the grid (see "A real
feature at 27°C/3.63V" above for why the top of that range is a
bias-point-specific near-cancellation rather than typical behavior — most
corners/supplies read 57-70 dB). Worst-case PSRR anywhere in the full
1 Hz-1 GHz sweep, any corner: **3.2-4.8 dB**, always near **31-40 MHz** —
the same decade `../loop-gain-phase-margin/`'s independently-measured
41.5-53.3 MHz unity-gain crossover falls in (see "Sign convention" for why
that agreement matters). Spot values at 1 kHz/100 kHz/1 MHz (
`psrr_1khz_db`/`psrr_100khz_db`/`psrr_1mhz_db` columns) show the expected
monotonic-ish rolloff from the DC value toward the crossover-band minimum.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/closed-loop-psrr/run_pvt_sweep.sh
```

Requires a committed `../closed-loop-startup/records/*.csv` to exist (see
"DC bias: `.nodeset`" above) — already true in this repo; no separate
`closed-loop-startup` run is required first.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
