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

## Trim-bearing DUT refresh (issue #264)

**DUT.** The core netlist this bench inlines device-for-device is now
#229's trim-bearing `design/netlist/bandgap_core.spice`: `XR1` is segmented
to its `l=37.2u` base into node `tn0`, and the 255-unit binary-weighted
`bandgap_trim` ladder continues `tn0 -> cb3` (see
[`../../design/bandgap_trim_network.md`](../../design/bandgap_trim_network.md)).
The ladder subcircuit is copied into the template device-for-device with its
subcircuit-local `.param trim_code` pinned to the schematic default **128**;
there is no trim-code axis here — the code-swept benches are
[`../trim-coverage/`](../trim-coverage/README.md),
[`../closed-loop-vref-trim-mc/`](../closed-loop-vref-trim-mc/README.md) and
[`../closed-loop-vref-boxtc-trim/`](../closed-loop-vref-boxtc-trim/README.md).
At code 128 the ladder reproduces the pre-trim 511 µm summing resistor to
within 12 Ω of its measured 66.06 kΩ (0.018%, measured in
[`../core-open-loop-bias/`](../core-open-loop-bias/README.md)'s own refresh).

**Solver options.** Unchanged — this bench never carried the `rshunt=1e9` /
`gmin=1e-9` convergence aids the transient benches needed, so the ~0.55 µA
ladder-leak artifact that forced those benches to drop them (see
[`../closed-loop-vref-boxtc-trim/README.md`](../closed-loop-vref-boxtc-trim/README.md)
§"Solver options") never applied here. The `.nodeset` seeds this bench reads
from `../closed-loop-startup`'s newest record are this refresh's own
aids-free startup record, so the seeded operating point and the DUT agree.

**What moved** — record `20261001-085806-e5507b2` (trim-bearing) vs the
superseded `20260830-133911-d83f7c4` (pre-trim), 45/45 PASS both:

| quantity | pre-trim | trim-bearing, code 128 |
|---|---|---|
| DC loop gain | 45.1–47.6 dB | 45.1–47.6 dB (bit-identical) |
| unity-gain crossover | 41.6–53.4 MHz | 30.2–49.9 MHz |
| phase margin (points with a crossing) | 88.5–119.3° (44/45) | **36.3–112.1°** (45/45) |
| notch minimum | −1.12 … +0.11 dB | −21.59 … −0.17 dB |
| `notch_margin_flag` = `marginal` | 43/45 | 36/45 |
| `vref_op_v` @ `typ`/27 °C/3.30 V | 1.047339 V | 1.047278 V (−60 µV) |

**This is the one refreshed experiment where the trim network measurably
changes the circuit's own behavior, not just the number's last digits — read
it as a real finding, not as noise.** 255 `rppd` segments carry 255
segment-to-substrate junction capacitances on the `vref`→`cb3` branch, so the
ladder loads the output node: the crossover drops (mean 46.2 → 44.2 MHz, and
the worst corner from 41.6 to 30.2 MHz) and the resonance that sets this
design's gain margin is damped — the notch deepens everywhere (the
`notch_margin_flag` count falls from 43 to 36 `marginal`, and this run finds a
real crossing at all 45 points, so the §"Pass/fail criteria" guard band is
not load-bearing for any point here).

The phase-margin cost lands almost entirely on one corner:
`wcs`/125 °C/2.97 V, whose notch goes from −0.39 dB to −21.59 dB and whose
phase margin reads **36.3°** (that corner is also the one point the pre-trim
run could not resolve a crossing for — the comparison is honest but not
like-for-like at that single point). The other 44 points stay in 83.9–112.1°.
Every point still clears this bench's hard stability bar (phase margin
> 0° at a found crossing), and no ratified spec row carries a phase-margin
number for this to violate — `spec/porting-plan.md` §6's draft table has none
and ratification of it is still open (#125). But "the ladder costs real phase
margin at the worst corner" is a design-level consequence of #229 that this
bench is the first to see, and it is tracked separately rather than buried
here — see **#271**, which also carries the corroborating PSRR-side
observation and the candidate dispositions.
A margin number read off the §"Results summary" section below is a pre-trim
number.

> **Re-read 2026-10-03 (issue #271):** the worst-corner figures above —
> phase margin **36.3°**, crossover **30.2 MHz**, notch **−21.59 dB**, all at
> `wcs`/125 °C/2.97 V — come from a **numerically corrupted AC solve**, not
> from the circuit. See §"Trim-code axis (issue #271)" directly below. The
> other 44 points of that record are clean solves and stand as written.

## Trim-code axis (issue #271)

**Question.** Is the 36.3° that `20261001-085806-e5507b2` reads at
`wcs`/125 °C/2.97 V a floor, or one sample of a phase margin that keeps
falling as more ladder segments come into the `vref`→`cb3` branch (higher
trim code)? **Answer: neither. 36.3° is one draw from a corrupted solve. The
genuine phase margin is bounded at ≥ 81.9° across codes 0–255 at every
point measured, and it rises with code. Disposition: accept and disclose.**
No compensation is owed. The bench defect that let a corrupted solve PASS
is tracked in **#289**.

**Record.** `records/20261003-151849-bc6b7ce.{md,csv}`: 93/93 PASS
under this bench's own criteria. It was run through `klt sim` on 2am's
batch fleet: 11 jobs, ids and instances in
`records/20261003-151849-bc6b7ce.jobs.json`, ngspice 46. The grid:

- **Trim codes** 0, 32, 64, 96, 128, 160, 192, 224 and 255.
- **PVT points (7):** the anchor; its supply neighbours `wcs`/125 °C/3.30 V
  and /3.63 V; and the four next-lowest margins in the 45-point record
  (`wcs`/−40 °C/3.63 V, `wcs`/27 °C/3.63 V, `wcs`/−40 °C/3.30 V,
  `fs`/−40 °C/3.63 V).
- **AC grids:** the bench's `dec 30`, plus a 10× finer `dec 300` (rows
  `_fine`) at the anchor (all codes) and at `wcs`/125 °C/3.30 V (codes 0,
  128, 255).
- **Deck variants** (CSV `deck`), described below.

**Harness** (`run_klt_trim_axis.sh` → `tools/klt_trim_axis.py`). Each body
is rendered from this bench's own `testbench/tb_loop_gain.spice.tmpl`, so
the DUT, the `.nodeset` seeds and the Lbreak/Vtest loop break are
unchanged. Three fixture-only adaptations:

1. **The code axis.** It rides `corners.supply_v` as eight `alter` keys,
   one per binary strap (`r.xxtrim.rs0`…`rs7`), swept together by index.
   `klt sim` has no parameter axis (klayout-tools#2725).
2. **T, crossover and margin are computed from the returned complex
   rawfile** with this bench's own `tools/find_crossover.awk`. No `.meas`
   card can express a ratio of two complex node voltages
   (klayout-tools#2724).
3. **The `.op`-near-seed check is carried through the AC run** by an
   isolated **op-probe** fixture. Each B-source outputs
   `V(node)*V(acs)`, where `acs` has 1 V AC / 0 V DC, so its AC response
   equals the node's DC bias. A `klt sim` request runs one analysis per
   corner, and `.MEASURE` has no `op` type.

The harness moves no number. `run_klt_trim_axis.sh --anchor` (one unit,
local) and the fleet's `np` code-128 row both reproduce the committed
anchor exactly: **36.3046°, 3.016466e+07 Hz, 20 crossings, −21.5902 dB
notch, 46.3857 dB DC gain**. At the other six points, the code-128 `probe`
rows match `20261001-085806-e5507b2` to within **0.7896°**, with
bit-identical DC gain.

### Finding 1: 36.3° is a corrupted solve, not a floor and not a trend

- **An electrically inert change flips it.** The `probe` deck adds four
  B-sources that only *sense* their nodes. Same circuit, same operating
  point: DC gain is 46.3857 dB in both decks, and `fb_op_v` is 2.18312 V
  against a 2.18312 V seed. Yet code 128 reads **95.7613°** (2 crossings,
  notch −0.6781 dB) where the bench deck (`np`, the control) reads
  **36.3046°**.
- **Corrupted solves are unmistakable.** CSV `ripple_db` is the largest
  single-point departure of |T| from its 3-point median over 10–200 MHz.
  Across all 93 rows it splits with nothing in between: ≤ 0.6643 dB on
  77 clean rows, ≥ 4.0985 dB on 16 corrupted rows. All 16 corrupted rows
  are at `wcs`/125 °C/2.97 V. They carry 14–228 zero-dB crossings, and
  their phase margins scatter over **22.0971–102.1069°** with no relation
  to code.
- **The matrix decides which codes corrupt; the grid does not.** In the
  `probe` deck, codes {0, 96, 160, 192, 224} corrupt; in the `np` deck,
  codes {32, 64, 128}. The sets are identical on both grids, and no code
  corrupts in both decks. The behaviour is deterministic: the same deck
  gives the same corrupted numbers locally and on the fleet.
- **The finer grid does not converge a corrupted solve.** It finds more
  spurious crossings (203–228) and finds them earlier, at 27.3–28.1 MHz
  with 23.3866–29.1802° margin. So `dec 300` cannot rescue the bench grid's
  36.3°. Clean `dec 300` solves agree with the clean `dec 30` ones.
- **The defect predates the trim ladder.**
  `tools/klt_trim_axis.py ripple-scan corners/<record-id>` over the
  committed records finds the same signature at `fs`/125 °C/3.63 V in
  `20260829-103017-1d98d88` and `20260829-115938-6fa92b5` (ripple 6.6123 dB,
  20 crossings). Those are the **43.9155°** and **−16.2597 dB** figures that
  §"Results summary" below quotes. In `20261001-085806-e5507b2`, only the
  anchor exceeds 1 dB (15.0336 dB; next highest 0.4238 dB).
  `20260826-103412-014570b` and `20260830-133911-d83f7c4` have none.

The root cause is not established. This deck combines 1 mΩ / 1 TΩ
behavioural straps with a 1e9 H break inductor, so the AC matrix spans an
extreme conductance range. Pivot ordering is a plausible suspect, given
that an added element flips the result, but that is a hypothesis.

### Finding 2: the clean phase margin is bounded, and rises with code

Clean solves only (`ripple_db` ≤ 1 dB), `probe` deck, `dec 30` grid:

| PVT point | code 0 | code 128 | code 255 | range over 9 codes |
|---|---|---|---|---|
| `wcs`/125 °C/3.30 V | 90.1714° | 92.9551° | 98.8470° | 90.1714–98.8470° |
| `wcs`/125 °C/3.63 V | 87.0315° | 89.4528° | 98.1967° | 87.0315–98.1967° |
| `wcs`/−40 °C/3.63 V | **81.9360°** | 83.4876° | 87.9727° | 81.9360–87.9727° |
| `wcs`/27 °C/3.63 V | 85.0660° | 86.4597° | 90.3718° | 85.0660–90.3718° |
| `wcs`/−40 °C/3.30 V | 85.3518° | 86.9201° | 92.1430° | 85.3518–92.1430° |
| `fs`/−40 °C/3.63 V | 85.3492° | 86.9225° | 92.3156° | 85.3492–92.3156° |

- **Lowest margin anywhere: 81.9360°**, at `wcs`/−40 °C/3.63 V, code 0.
- At each of these six points, margin is **lowest at code 0** (the ladder
  fully strapped out) **and highest at code 255** (every segment in
  circuit). The rise from code 0 to 255 is 5.3058–11.1652°. The trend is
  not strictly monotonic in between. It runs **opposite** to the "more
  segments, less margin" hypothesis #271 was opened to test.
- **At the anchor itself**, each code has at least two clean solves across
  decks and grids. All 20 clean solves lie in **92.9544–102.0614°**.
  Different clean solves of the same code spread by up to 3.6647° (code
  255). That spread is this measurement's numerical resolution at this
  corner. It is about 4% of the smallest clean margin (3.6647° against
  92.9544°, a ratio of about 25), so more than an order of magnitude
  below it.
- Crossover at the six clean points (`dec 30`): 39.70–44.70 MHz. Notch
  minima (`dec 30`): −1.4355 … −0.5184 dB. On the `dec 300` grid, one row
  at these points falls just outside that range: `wcs_code128_fine` at
  125 °C/3.30 V reads −1.4709 dB. All of these are still within or near the
  §"Pass/fail criteria" guard band. Gain margin, not phase margin, remains
  this design's thin margin (§"Results summary"); the code axis does not
  change that.

### Disposition and scope

**Accept and disclose.** Phase margin is bounded at ≥ 81.9° over the full
code range at all seven points, including the four worst neighbours of the
45-point grid. It does not fall with code, and nothing points at
`bandgap_amp` compensation. No follow-up for compensation is filed.

What this does **not** cover:

- The other 38 PVT points are measured at code 128 only, in
  `20261001-085806-e5507b2`; all of them are clean solves there.
- No ratified spec row carries a phase-margin bar. The ratified table in
  the top-level `README.md` has no such row, and `spec/porting-plan.md` §6
  still states that none of its draft rows is ratified. Its ratification
  issue, #125, is closed.
- Two units carry a recovered `singular_matrix` diagnostic from `klt sim`
  (`Warning: singular matrix:  check node q.xq1.qnpn13g2#emitter` in the
  log). Both are `probe`-deck, code 64 at the anchor: `wcs_code64`
  (`dec 30`, `ripple_db` 0.2101 dB) and `wcs_code64_fine` (`dec 300`,
  `ripple_db` 0.3670 dB). Both are clean solves and are reported as such.

The bench defect is that the single-sweep pass bar (PM > 0° at the first
falling crossing) cannot tell a corrupted solve from a real one. Two
distinct corrupted points have now PASSed into committed records, as three
CSV rows. Adding a
solve-quality guard is **#289** (implemented there: see "Solve-quality
gate"). #271 itself did not change `run_pvt_sweep.sh`.

## What this testbench claims, and what it does not

It claims: across the full temperature x supply x
HBT/MOS/resistor-process-corner PVT grid, at the real closed-loop DC
operating point (verified per point, not assumed — see "op landed near its
seed" below), the loop's small-signal gain crosses 0 dB with **positive**
phase margin at every corner where a single AC sweep resolves a crossing at
all, and — at the one corner where it does not (see "Pass/fail criteria"
below) — the sweep's own resonant gain notch (see "Multiple 0 dB crossings")
never robustly clears 0 dB in either direction, so the loop is never shown
unstable there either. **Phase margin is comfortable everywhere it is
measured (this run: 43.9-117.1°; 43.9° is a corrupted solve, see the
2026-10-03 note under "Results summary"); gain margin is a separate, much thinner story**
— see "Pass/fail criteria" below for why nearly every corner's own notch
minimum sits within about a dB of 0 dB, not just the one corner that
occasionally fails to resolve a crossing at all (DC loop gain **45.1-47.5 dB**,
unity-gain crossover **41.7-52.9 MHz** — see `records/<record-id>.csv` for the
full 45-point table).

**It does not claim conformance to any ratified spec row** — `spec/`
carries no ratified loop-stability target for this design (#125 tracks
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
first crossing before recovering back above it — i.e. **at least two** 0 dB
crossings close together, not one clean monotonic rolloff (most points in
`records/<record-id>.csv` report `n_crossings=2`; a few corners near the
edge of the notch region report more, e.g. `fs`/125°C/3.63V's `n_crossings=20`
— extra ripple in the same already-thin notch, not a different
phenomenon). Confirmed to be a genuine feature of the amplifier's own
internal dynamics, not an artifact of the `Lbreak` injection technique: the
peak/crossing frequencies are identical whether `Lbreak` is 1e6 H or 1e9 H
(tested during dev-time prototyping — an injection-technique artifact
would move with `Lbreak`; a real circuit pole/zero pair would not, and does
not, here). This is plausibly the folded-cascode-like `MN4`/`MP3`/`MP4`
output stage's own non-dominant pole/zero pair (`design/bandgap_amp.sch`'s
header describes this fold explicitly) becoming underdamped at this
current/loading level — consistent with "no explicit compensation
capacitor" being a real, if here relatively benign, first-pass gap that
schematic's own header already flags. `tools/find_crossover.awk` reports
the **first** (lower-frequency) falling crossing as the phase-margin
point — the conservative, standard convention — and records `n_crossings`
in the CSV for transparency; every point in this run's phase margin
(43.9-117.1°, see "Results summary" below, including its 2026-10-03 note
on the 43.9° point) is measured well clear of the
brief post-crossing dip, so the choice of first-vs-any crossing does not
change this run's qualitative conclusion (every corner where a crossing is
found is comfortably stable in phase). The notch's OWN minimum magnitude —
a separate, much thinner gain-margin story than the phase-margin numbers
above — is the subject of "Pass/fail criteria" below.

## Pass/fail criteria

A point is `PASS` only if:

0. **The AC response passes the solve-quality gate** (issue #289, methodology
   change, evaluated first — see "Solve-quality gate" below): finite, spans
   1 Hz–~1 GHz, at least 5 samples in 10–200 MHz, and `ripple_db <= 1.0 dB`.
   A point that fails is `FAIL` with `quality=inconclusive` and a
   `reject_reason` in the CSV; its `crossover_hz` and `phase_margin_deg`
   are **blank** (it publishes no margin), criteria 2 and 3 are not
   consulted — in particular the guard band in #2 cannot rescue it — and
   its raw `*.ac.txt` and log stay as evidence. Its `dc_gain_db`,
   `n_crossings` and `notch_*` columns remain as diagnostics only.
1. **`.op` landed near its seed**: `|v(fb_load) - fb_seed| <= 0.05 V` — see
   "op landed near its seed" above.
2. **Either** a falling 0 dB crossing exists in the 1 Hz-1 GHz sweep (the AC
   analysis actually found a crossover to measure phase margin at), **or**
   no crossing was found but the sweep's own resonant notch minimum
   (`tools/find_crossover.awk`'s `notch_min_db` — the lowest magnitude
   sampled anywhere in the sweep, reported unconditionally) sits within
   `NOTCH_GUARD_DB` (currently **1.0 dB**) of 0 dB.
3. **If a crossing WAS found**, phase margin at that crossing is `> 0°` —
   the hard stability bar; `PM<=0` would mean the loop is not
   unconditionally stable at that corner. This bar is untouched by the
   guard band in #2, which only ever turns a would-be `NONE`-crossing
   `FAIL` into a `PASS`, never rescues a real crossing with bad phase
   margin.

`ngspice` exiting non-zero, a model-load error, or the AC sweep producing
no data also fails the point, same convention as every other testbench in
this tree.

### Solve-quality gate (issue #289)

**Why.** Issue #271 showed that this deck's AC matrix (1 mΩ / 1 TΩ trim
straps, a 1e9 H loop-break inductor: a very wide conductance range) can
yield a numerically corrupted loop-gain response, deterministically per
matrix, and that the pre-#289 bar (PM > 0° at the first falling crossing)
passes it and publishes its margin. The guard changes what the bench
*publishes*; it does not change the DUT or any spec.

**Metric.** `ripple_db` = max over 10–200 MHz of
`|mag_db[n] − median(mag_db[n−1], mag_db[n], mag_db[n+1])|`
(`tools/solve_quality.py`). One module is used by both paths:
`run_pvt_sweep.sh` calls `solve_quality.py check <ac.txt>` on its own
`wrdata` file, and `tools/klt_trim_axis.py` imports it. CSV columns
`ripple_db`, `quality` (`ok`/`inconclusive`) and `reject_reason` are in
both paths' records.

**Threshold: 1.0 dB.** Calibration over every committed loop-gain
`*.ac.txt` (dec 30 and dec 300): clean solves read ≤ 0.6643 dB
(worst: `wcs_code0_np_fine_125c_2.97v`), corrupted solves ≥ 4.0985 dB
(`wcs_code32_np_125c_2.97v`); no committed unit lies in between
(`tools/test_solve_quality.py` asserts that). 1.0 dB sits in
that gap, 0.34 dB above the highest clean reading and 3.1 dB below the lowest
corrupted one.
Reasons reported: `ripple_exceeds_threshold`, `no_data`, `non_finite`,
`truncated_sweep` (the sweep must start ≤ 1.5 Hz and reach ≥ 0.9 GHz),
`insufficient_band_points`. Every failure mode rejects (fail closed).

**Limits — read before trusting it.** The gate detects the observed
signature: isolated multi-dB point-to-point jumps of |T| inside 10–200 MHz.
It does not claim to detect every possible solver corruption: a corrupted
response whose damage lies outside that band, or one that is smooth but
wrong, passes. The threshold is calibrated on this deck's committed
records, not derived. The `temperature limiting function received NaN`
ngspice message is **not** a criterion: it appears in about half the clean
solves as well (e.g. `wcs_code128_125c_2.97v` in
`20261003-151849-bc6b7ce` carries it and is clean). The crossing count is
diagnostic only; legitimate responses can have several crossings.

**No retry.** A rejected unit is reported inconclusive and stays so.
Re-solving with a perturbed equivalent matrix (as #271's control deck did)
was not implemented: a retry that can swap in a favourable answer needs both
attempts retained and a rule that never picks the larger margin, and the
fail-closed form already meets the goal.

**Probe vs control twin.** In the `klt sim` records the `probe` deck carries
the OP PROBE fixture, which is what lets `klt sim` read the bias for the
"op landed near its seed" check. The `np` control deck has no probe; its op
check is that its DC loop gain equals its probe twin's. Under the gate a
`np` row only gets that evidence from a twin that is itself a clean solve
*and* passed its own op check, so a corrupted twin cannot vouch for a
control row. Adding the probe changes the matrix, hence which solves
corrupt: at `wcs`/125 °C/2.97 V, code 128, the bench's matrix (`np`,
`ripple_db` 15.0336 / 20.5376 on dec 30 / dec 300) is corrupted while the
`probe` matrix is clean (0.1261 / 0.3599). A clean `probe` row therefore
means *that matrix's* solve is clean, not that the bench's own matrix is.

**Reproduction vs acceptance.** `run_klt_trim_axis.sh --anchor` reproduces the
committed 36.3046° at that point and now prints
`solve quality REJECT (ripple_exceeds_threshold)`: it reproduces an
*artifact*, and the number is not an accepted margin.

**Modes.** `run_klt_trim_axis.sh --batch` is the unchanged #271
characterization (a code × corner grid, not a PVT grid).
`run_klt_trim_axis.sh --pvt` is the full 45-point PVT grid at code 128 on
the fleet (one `klt sim --backend batch` request per PVT point, because the
`.nodeset` seed is per point).

### Why criterion #2 has a guard band (issue #146)

This design's resonant gain notch (see "Multiple 0 dB crossings" above)
sits close enough to 0 dB, at nearly every corner in this grid, that a
bare "did the sweep find a falling crossing" test is not robust: two
independent re-runs of the exact same `bcs`/125°C/2.97V netlist (bit-
identical `dc_gain_db` both times — this is solver-level numerical
sensitivity, gmin stepping / OSDI Newton-iteration path, not a circuit
change) put that corner's notch minimum at `-0.0506 dB` and `+0.0620 dB`
respectively — opposite sides of 0 dB, which without a guard band flips
the point from `PASS` to `FAIL` on a re-run with nothing else changed.
`NOTCH_GUARD_DB=1.0` is roughly an order of magnitude more headroom than
that observed noise floor: a notch that clears the guard band in either
direction (e.g. this run's `fs`/125°C/3.63V, whose notch bottoms out at a
comfortable `-16.26 dB` (a corrupted solve, see the 2026-10-03 note under
"Results summary"), or `wcs`/-40°C/3.63V at `-1.29 dB`) is treated as
a robust, unambiguous result either way. A notch that rises **clearly and
robustly above 0 dB by more than the guard band** — a genuine several-dB
regression, not solver noise — still fails outright; the guard band only
ever softens the razor's-edge case this issue exists to fix, never masks a
real loss of margin.

**This run's own evidence shows the guard band is not academic**: 41 of
this run's 45 points have a notch minimum within `+-1.0 dB` of 0 dB (see
`records/<record-id>.csv`'s `notch_min_db` column) — i.e. **gain margin is
a genuinely thin, near-universal property of this corner grid**, distinct
from the comfortable phase margin (43.9-117.1°; see the 2026-10-03 note
under "Results summary" on the 43.9° point) reported above. Only one
of those 41 (`bcs`/125°C/2.97V, this run) actually failed to resolve a
crossing at all and needed the guard band to avoid a `FAIL`; the CSV's
`notch_margin_flag` column (`marginal`/`clear`) flags all of them for
transparency regardless of which side of 0 dB they landed on. This is a
disclosed property of this specific lightly-loaded, uncompensated
topology (see "What this testbench claims" above), not a testbench
artifact — a future revision adding real compensation would be expected to
open this margin up considerably.

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

### Newest record: solve-quality-gated, `20261003-180919-2addad0` (issue #289)

The newest record is `records/20261003-180919-2addad0.{md,csv}`: all 45 PVT
points at code 128 (5 process × 3 temperature × 3 supply), through
`run_klt_trim_axis.sh --pvt` (`klt sim --backend batch`, one fleet job per
point; 45 distinct job ids, all `done`/exit 0, in
`records/20261003-180919-2addad0.jobs.json`), every unit checked by the
solve-quality gate (see "Pass/fail criteria"). Result: **45/45 quality `ok`,
45/45 PASS, no unit rejected, no retry**. Highest `ripple_db` 0.4463 dB
(`typ`/125 °C/3.63 V), under the 1.0 dB threshold and far below the lowest corrupted
reading (4.0985 dB). Phase margin **83.49–115.16°** (lowest: `wcs`/−40 °C/3.63 V, then
`wcs`/27 °C/3.63 V at 86.46°), DC loop gain 45.13–47.60 dB, crossover
40.2–51.1 MHz; 36 of 45 notch minima are within ±1.0 dB of 0 dB. Nine units'
logs carry a recovered `singular matrix` warning and are clean solves.

**This record supersedes the numbers below.** The 36.3° at `wcs`/125 °C/
2.97 V (`20261001-085806-e5507b2`) and the 43.9° / −16.26 dB at `fs`/125 °C/
3.63 V (`20260829-103017-1d98d88`, `20260829-115938-6fa92b5`) are
**artifacts of corrupted solves**, not margins (issue #271): in the new
record those points read 95.76° and 95.39°.

**What the new record does and does not show.** It is a `klt sim` record,
whose `probe` deck adds the OP PROBE fixture (see "Probe vs control twin"):
that is a different matrix from `run_pvt_sweep.sh`'s, and at `wcs`/125 °C/
2.97 V the bench's own matrix is the corrupted one. So the new record shows
that the gate passes 45 clean `probe` solves; it does not show that
`run_pvt_sweep.sh`'s matrix is clean at all 45 points. `run_pvt_sweep.sh`
carries the same gate now, and would mark the `wcs`/125 °C/2.97 V row
inconclusive rather than publish 36.3°; this change did not re-run that
local shell grid (dispatch hosts do not run local grids), so that
behaviour is covered by the replay tests in `tools/test_solve_quality.py`
and not by a live shell run. The older records are append-only and keep
their original rows; read them with the artifact notes in this README.

### Earlier record (pre-#289; its low-end values are artifacts)

45/45 points PASS. Across the 44 points where a crossing was found: DC loop
gain **45.1-47.5 dB** (~180-750 V/V), unity-gain crossover
**41.7-52.9 MHz**, phase margin **43.9-117.1°** — every one of those points
is unconditionally stable in the classical phase-margin sense (see "What
this testbench claims" above for why the wide phase margin should be read
as a property of this specific lightly-loaded topology's naturally-far-out
dominant pole, not as evidence that no future revision of this amplifier
will ever need compensation). The remaining point (`bcs`/125°C/2.97V) found
no crossing in this run but PASSes via the notch guard band described in
"Pass/fail criteria" above.

> **2026-10-03 (issue #271):** the low end of that range, **43.9°** at
> `fs`/125 °C/3.63 V, and that point's **−16.26 dB** notch quoted below
> come from a numerically corrupted solve (ripple 6.6123 dB, 20 crossings).
> See §"Trim-code axis (issue #271)" above. Excluding that point, the
> margins in that record start at 87.1658°.

**Gain margin, not phase margin, is this design's real limiting factor**:
41/45 points have a notch minimum within `+-1.0 dB` of 0 dB (see
`records/<record-id>.csv`'s `notch_min_db`/`notch_margin_flag` columns) —
this is a genuinely thin margin at nearly every corner in this grid, not
an artifact isolated to one PVT combination. Only 4 corners
(`fs`/125°C/3.63V at a comfortable `-16.26 dB`, a corrupted solve per the
2026-10-03 note above, and three `wcs` points at
`-1.0` to `-1.3 dB`) clear the guard band with room to spare.

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

Solve-quality regression tests (read-only replay of committed responses):

```bash
python3 sim/loop-gain-phase-margin/tools/test_solve_quality.py
```

Trim-code axis (issue #271) and full-PVT (issue #289), through `klt sim`:

```bash
sim/loop-gain-phase-margin/run_klt_trim_axis.sh --anchor   # 1 unit, local: the 36.3046 deg sanity anchor
sim/loop-gain-phase-margin/run_klt_trim_axis.sh --batch    # full plan on 2am's batch fleet -> new record
sim/loop-gain-phase-margin/run_klt_trim_axis.sh --pvt      # 45-point PVT grid at code 128 on the fleet, gated (#289)
python3 sim/loop-gain-phase-margin/tools/klt_trim_axis.py ripple-scan \
  sim/loop-gain-phase-margin/corners/<record-id>          # solve-quality scan of any record
```

`--batch` needs a `klt` carrying the batch backend (0.6.0+) and 2am's
`batch-fleet-provision.sh`. It submits at most `KLT_TRIM_AXIS_CONCURRENCY`
(default 3) jobs at a time, because the fleet refuses rather than queues
past its shared instance cap. On a dispatch host, never widen `--anchor`
into a local grid.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows.
