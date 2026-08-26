# loop-gain-phase-margin

Closed-loop **small-signal AC loop-gain / phase-margin** testbench (issue
#86, follow-on to #58) — the stability measurement `design/README.md`'s
issue #58 "Not attempted" list named as open ("loop-gain/phase-margin/
stability measurement (no small-signal AC testbench yet — this issue's
testbench is transient-only)"). Co-simulates `design/bandgap_core.sch` +
`design/bandgap_amp.sch` + `design/bandgap_startup.sch` — the same three
DUTs, wired exactly as `design/bandgap_top.sch` specifies, that
[`../closed-loop-startup/`](../closed-loop-startup/README.md) and
[`../closed-loop-vref-pvt/`](../closed-loop-vref-pvt/README.md) use — but
breaks the loop at the shared `fb` node and runs an `.ac` analysis around a
`.nodeset`-seeded DC operating point instead of a transient bring-up.

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x
HBT/MOS/resistor-process-corner PVT grid, at the real closed-loop DC
operating point (verified per point, not assumed — see "op landed near its
seed" below), the loop's small-signal gain crosses 0 dB with **positive**
phase margin everywhere — i.e. the loop is unconditionally stable at every
corner this repo's PVT grid covers, by a wide margin (this run: **85-119°**
phase margin, DC loop gain **45.1-47.5 dB**, unity-gain crossover
**41.5-53.3 MHz** — see `records/<record-id>.csv` for the full 45-point
table).

**It does not claim conformance to any ratified spec row** — `spec/`
carries no ratified loop-stability target for this design (#13 tracks
ratification generally; no draft phase-margin number exists in
`spec/porting-plan.md` §6 to compare against in the first place). It does
not measure PSRR or offset/mismatch (both explicitly deferred — see
`design/README.md`'s updated "Not attempted" list and #88, the follow-up
issue this issue files for them). It does not claim the amplifier is
well-compensated in any classical sense (no explicit compensation
capacitor exists in `design/bandgap_amp.sch`'s first pass — see that
schematic's own header) — the wide margins measured here are a property of
this specific lightly-loaded, low-current topology having its dominant
pole naturally far out (tens of MHz), not evidence that a design with
different loading or higher bandwidth requirements would be similarly
stable without adding compensation.

## Loop-break method

The three DUTs are copied verbatim, identical to
`../closed-loop-startup/`'s own device-for-device copy, **except** the
single shared `fb` node is split into two nodes for this testbench only:

- **`fb_src`** — `bandgap_amp`'s own output (`MP4`/`MN3` drains — what
  `design/bandgap_amp.sch`'s header calls `out`).
- **`fb_load`** — everything `fb_src` normally drives directly:
  `bandgap_core`'s three PMOS mirror gates (`M1`/`M2`/`M3`) and
  `bandgap_startup`'s `XMKFB` drain (via the same `Vmkfb` 0 V ammeter
  fixture `../closed-loop-startup/` uses).

A large inductor (`Lbreak`, 1e9 H) connects `fb_src` to `fb_load`: at DC an
ideal inductor is a short circuit **regardless of its inductance**, so this
preserves the closed-loop DC operating point exactly (`fb_src = fb_load`,
the same constraint the real single `fb` node enforces) while presenting a
huge (> 1e17 Ω at the lowest swept frequency) AC impedance — breaking the
loop for the `.ac` analysis without touching its DC bias. A small-signal AC
voltage source (`Vtest`, 1 V∠0°, DC = 0 V) is injected in series with
`Lbreak` between `fb_src` and `fb_load` — Middlebrook's classic single
voltage-injection loop-gain probe.

This specific break point is deliberately chosen, not arbitrary: single
voltage injection is most accurate when the injection point sees a
**low** impedance looking back into the driving side (`fb_src`, a real
amplifier output) and a **high** impedance looking forward into the loaded
side (`fb_load`, whose only other connections are MOS gates — near-infinite
DC/AC impedance — plus `XMKFB`'s drain through a 0 V ammeter, which is off
at this operating point). That is exactly the impedance asymmetry this
node presents, so single injection (rather than the more elaborate
double-injection/two-probe methods needed when neither side is clearly
low-impedance) is well justified here.

### Why not just reuse `closed-loop-startup`'s own vdd-ramp transient?

Tried first, and it does not work: splitting `fb` into `fb_src`/`fb_load`
from the *start* of a vdd-ramp transient starves `fb_load`'s dynamics — its
only fast current path to the rest of the circuit is through `Lbreak`
itself, whose `L/R` time constant against `fb_load`'s otherwise
near-infinite-impedance loads (MOS gates) is enormous relative to the
200 µs-3 ms ramp/settle window. Confirmed empirically during this issue's
own dev-time prototyping: every `Lbreak` value tried (1 H through 1e9 H)
either failed the transient outright (`Timestep too small`) or settled far
from `../closed-loop-startup/`'s own known-correct endpoint (e.g. `sns2`
railed near `vdd` instead of the real ~0.7-0.8 V, `L=1e6` case). This is
why this testbench uses a fixed-`vdd` `.op`/`.ac` pair instead of a
transient, seeded by `.nodeset` (below) rather than by its own bring-up.

## Nodeset provenance

`.op` on the loop-broken topology has no transient bring-up to guide it
into the correct basin (see above) — and this circuit genuinely has more
than one DC equilibrium, the same degenerate all-off state
`design/bandgap_startup.sch` exists to kick the *unbroken* circuit out of.
Left to its own default initial guess, a bare `.op` has no guaranteed way
to land in the intended equilibrium.

The fix: `run_pvt_sweep.sh` reads `fb_final_v`/`sns1_final_v`/
`sns2_final_v`/`vref_final_v` for the matching `corner_label`/`temp_c`/
`vdd_v` row out of **`../closed-loop-startup/`'s own most recent committed
record CSV** (looked up by column name, not position, at generation time —
see that script's `lookup_seed()`), and substitutes them into this
testbench's `.nodeset` line. `.nodeset` is an initial-guess *hint* for
`.op`'s Newton-Raphson iteration (unlike `.ic`, it is not an enforced
constraint) — since the seed values ARE (very nearly) the real closed-loop
answer for that exact corner, `.op` converges back to them directly rather
than searching. This was confirmed empirically across 6 spot-checked
corners during dev-time prototyping (typ/27°C/3.30V, wcs/-40°C/2.97V,
bcs/125°C/3.63V, sf/125°C/3.63V, fs/-40°C/3.63V, typ/125°C/2.97V) to
reproduce `../closed-loop-startup/`'s own `fb`/`sns1`/`sns2`/`vref` values
to 3-4 significant figures, despite only 5 of this circuit's ~13
non-trivial nodes (`fb_load`, `fb_src`, `sns1`, `sns2`, `vref`) being
seeded — the other internal nodes (`tail`, `d1`, `d2`, `pn`, `cb2`, `cb3`,
`det`) are left for the solver, and consistently land in the right basin
anyway once the sense/feedback nodes are anchored.

This is a genuine **cross-experiment dependency**: this experiment cannot
produce a meaningful result without a committed `../closed-loop-startup/`
record to read seeds from. `run_pvt_sweep.sh` fails loudly (exit 3, before
running any simulation) if no `../closed-loop-startup/records/*.csv`
exists at all. It does not require a *fresh* `../closed-loop-startup/` run
first — the committed record already in this repo is sufficient, and is
what this experiment's own committed record was generated against (see
"Nodeset seed provenance" in `records/<record-id>.md`).

### "op landed near its seed" — verified per point, not just trusted

The dev-time spot check above covered 6 of 45 points. `run_pvt_sweep.sh`
itself re-verifies the same property for **every** point in the actual
sweep: after `.op` converges, it compares the resulting `v(fb_load)`
against its own `.nodeset` seed and fails the point outright
(`|fb_op - fb_seed| > 0.05 V`) rather than silently reporting a loop-gain
number computed around the wrong equilibrium. All 45 points in this run's
own committed record pass this check with `fb_op` within a few mV of
`fb_seed` (see `records/<record-id>.csv`'s `fb_seed_v`/`fb_op_v` columns).

## Sign convention

Define `T(s) = V(fb_src)/V(fb_load)` from the AC sweep. Empirically (this
run, every corner): `T(j·2π·1Hz)` has phase ≈ +180° and magnitude ≈ 45-48 dB
— a large negative real number at DC. This is the expected signature of a
correctly-wired negative-feedback loop measured this way: increasing
`fb_load` (holding `fb_src` fixed) lowers each core mirror leg's current
(higher gate voltage → less PMOS overdrive), which lowers
`e = sns2 - sns1 ≈ I·R2 - VT·ln(8)`, which — per
`design/bandgap_amp.sch`'s own "polarity" derivation (`sns2` = non-inverting,
`sns1` = inverting) — lowers `out` (`fb_src`). So `d(fb_src)/d(fb_load) < 0`
at DC: a negative real transfer function, i.e. phase 180°, exactly what was
measured. (Had the amplifier's polarity been wired backwards — the
single most safety-critical wiring decision `design/bandgap_amp.sch`'s own
header calls out — this sign would flip to phase 0°/positive real, a
positive-feedback loop; this testbench would have caught that immediately
as a DC-phase sign flip, independent of anything downstream.)

Given `T(s)` starts at +180° and (per the standard loop-gain Bode
narrative) rotates toward 0° as frequency increases through the loop's
poles, the danger condition (Barkhausen/Nyquist for this convention) is
`T(jω) = 1∠0°` — magnitude 1 (0 dB) **and** phase 0° simultaneously.
**Phase margin is therefore `PM = phase(T(jω_c))` directly** (no extra
180° subtraction), evaluated continuously (unwrapped) from the +180°
starting reference, at the frequency `ω_c` where `|T(jω_c)| = 1`. This is
implemented in `tools/find_crossover.awk`.

## Multiple 0 dB crossings — a real feature, not a bug

Every corner in this run's magnitude response shows a resonant peak
(gain rising several dB above its DC value) around 3-5 MHz before rolling
off steeply, then a brief dip a few dB below 0 dB immediately after the
first crossing before recovering back above it — i.e. **two** 0 dB
crossings close together (`n_crossings=2` for all 45 points in
`records/<record-id>.csv`), not one clean monotonic rolloff. Confirmed to
be a genuine feature of the amplifier's own internal dynamics, not an
artifact of the `Lbreak` injection technique: the peak/crossing frequencies
are identical whether `Lbreak` is 1e6 H or 1e9 H (tested during dev-time
prototyping — an injection-technique artifact would move with `Lbreak`;
a real circuit pole/zero pair would not, and does not, here). This is
plausibly the folded-cascode-like `MN4`/`MP3`/`MP4` output stage's own
non-dominant pole/zero pair (`design/bandgap_amp.sch`'s header describes
this fold explicitly) becoming underdamped at this current/loading level —
consistent with "no explicit compensation capacitor" being a real, if
here relatively benign, first-pass gap that schematic's own header already
flags. `tools/find_crossover.awk` reports the **first** (lower-frequency)
falling crossing as the phase-margin point — the conservative, standard
convention — and records `n_crossings` in the CSV for transparency; every
point in this run's phase margin (85-119°) is measured well clear of the
brief post-crossing dip, so the choice of first-vs-any crossing does not
change this run's qualitative conclusion (all corners comfortably stable).

## Pass/fail criteria

A point is `PASS` only if:

1. **`.op` landed near its seed**: `|v(fb_load) - fb_seed| <= 0.05 V` — see
   "op landed near its seed" above.
2. **A falling 0 dB crossing exists** in the 1 Hz-1 GHz sweep (the AC
   analysis actually found a crossover to measure phase margin at).
3. **Phase margin > 0°** at that crossing — the hard stability bar; `PM<=0`
   would mean the loop is not unconditionally stable at that corner.

`ngspice` exiting non-zero, a model-load error, or the AC sweep producing
no data also fails the point, same convention as every other testbench in
this tree. (A secondary, non-failing observation: every point in this run
clears a much higher, more conventional "adequate margin" bar too — the
worst corner's 85° is still well above the ~45-60° a typical amplifier
design target would use — so no corner in this run is only marginally
passing the hard bar above.)

## Corner coverage

Same corner-label vocabulary and section pairing as
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md) and
[`../closed-loop-startup/`](../closed-loop-startup/README.md):

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

45/45 points PASS. Across all 45 points: DC loop gain **45.1-47.5 dB**
(~180-750 V/V), unity-gain crossover **41.5-53.3 MHz**, phase margin
**85-119°**. The design is unconditionally stable at every PVT corner this
repo's grid covers, by a wide margin — see "What this testbench claims"
above for why that should be read as a property of this specific
lightly-loaded topology's naturally-far-out dominant pole, not as evidence
that no future revision of this amplifier will ever need compensation.

## Running

```bash
export PDK_ROOT=/path/to/ihp-open-pdk
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh              # one-time: build the OSDI models
sim/loop-gain-phase-margin/run_pvt_sweep.sh
```

Requires a committed `../closed-loop-startup/records/*.csv` to exist (see
"Nodeset provenance" above) — already true in this repo; no separate
`closed-loop-startup` run is required first.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
