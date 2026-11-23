# closed-loop-vref-mc

Closed-loop untrimmed `vref` **device-mismatch Monte Carlo** campaign
(issue #215) — the T1 gap-to-tracker (#4) checklist item 6 evidence
("Statistical claims carry Monte Carlo evidence — recorded seed, sample
count, deterministic negative control, combined with (not instead of)
process corners") that `sim/closed-loop-offset/` explicitly deferred and
`design/README.md` still listed as "not attempted". This is also the
untrimmed-spread evidence issue #150 records PR #128's ratification review
is waiting on for the "accuracy-band relax + Trim spec row" argument — see
"What this evidence does and does not claim" below.

## What this testbench claims, and what it does not

**It is a real statistical mismatch study**, unlike
[`../closed-loop-offset/`](../closed-loop-offset/README.md)'s deterministic
±5 mV offset *sensitivity* probe. This campaign draws N (≥300) independent
samples of `vref`'s closed-loop DC operating point against SG13G2's own
`agauss()`-based per-device statistical mismatch models
(`hbt_typ_mismatch`, `mos_tt_mismatch`, `res_typ_mismatch`, and their
`bcs`/`wcs` siblings) — real device-to-device variation, not a hand-picked
probe value.

**It does not claim conformance to any ratified spec row.**
`spec/porting-plan.md` §6's `Output reference ~1.2 V ±1 % untrimmed / ±0.5 %
with trim` row is still unratified (#125, escalated in #150/#128) — the
per-point `within +/-1%` / `within +/-0.5%` fractions this record reports
are computed **against that point's own sample mean**, not against
`spec/porting-plan.md`'s `1.2 V` figure, and are stated explicitly as
**evidence for**, not a ruling on, that still-open ratification. No target
row in `spec/porting-plan.md` is edited by this issue.

**It does not design a trim network.** The `within +/-0.5%` fraction is
reported as "the trim range a future trim DAC would need to cover" purely
as a descriptive frame for the same data column — sizing an actual trim
network is out of scope (see the issue's own "Out of scope" section).

**It is pre-layout.** Like every other `sim/closed-loop-*` experiment in
this tree, the DUT is the schematic-derived `design/netlist/bandgap_core.spice`
(`R1 = 511 µm`) — the closed-loop netlist #150 says the ratification
evidence must describe. A post-layout PEX mismatch twin (the `-pex` slugs
the corner sweeps already have) is explicit "Out of scope" here.

## Method: two ingredients per draw

1. **`.options rndseed=<N>` at SPICE-netlist level, before any `.lib`
   include or device is parsed** — verified by direct experiment, not
   assumed: SG13G2's mismatch models express per-device variation as
   `.param`-level `agauss(...)` expressions (e.g.
   `sg13g2_hbt_mod_mismatch.lib`'s `qarea='agauss(1, 0.1, ...)'`), evaluated
   **once, at netlist-parse time**. A `set rndseed=N` issued later from
   inside `.control` (the ngspice idiom that looks like the obvious way to
   seed Monte Carlo) has **no effect** on these expressions — confirmed
   directly: two separate `.control`-only-seeded runs of the identical
   netlist produced *different* device draws each time, while
   `.options rndseed=N` at the netlist's top level, read before parsing,
   reproduces bit-for-bit across separate `ngspice` invocations with the
   same seed and produces a different (but still deterministic) draw for
   each different seed value. See the testbench template's own header for
   this rationale restated next to the code it governs.
2. **The `_mismatch` corner-lib sections** (`hbt_typ_mismatch`,
   `mos_tt_mismatch`, `res_typ_mismatch`, and their `bcs`/`wcs` siblings)
   instead of the plain (`hbt_typ`, `mos_tt`, `res_typ`, ...) deterministic
   sections every PVT-sweep testbench in this tree uses. The negative
   control below uses the identical seed sequence against the **plain**
   sections instead.

Each draw is a single `.nodeset`-seeded `.op` (the same DC-bias technique
`../closed-loop-offset/`, `../loop-gain-phase-margin/` and
`../closed-loop-psrr/` all use — seeded from `../closed-loop-startup/`'s own
committed converged transient endpoint at the matching corner/temp/vdd, a
Newton-Raphson initial-guess hint only, not an acceptance criterion), **not**
a full startup-ramp transient. This is what makes an N≥300-per-point
campaign tractable: measured directly, one `.op` draw against an
already-`pre_osdi`-loaded circuit runs in well under a second of wall
time, vs. tens of seconds of `ngspice` CPU time for
`../closed-loop-vref-pvt/`'s own full 3 ms startup-ramp transient at the
same corner — the difference between an O(minutes) campaign and an
O(hours) one at this sample count.

## Scope: nominal + 4 corners + a negative control, not the full PVT grid

Six points, each run at N draws:

| point | PDK corner sections | temp | vdd | purpose |
|---|---|---|---|---|
| `nominal` | `*_mismatch` (typ) | 27°C | 3.30V | headline untrimmed-spread evidence |
| `negctrl` | plain (typ, non-mismatch) | 27°C | 3.30V | **negative control** — same seeds, must show exactly zero spread |
| `bcs_n40` | `*_mismatch` (bcs) | -40°C | 3.30V | mismatch combined with a process corner |
| `bcs_125` | `*_mismatch` (bcs) | 125°C | 3.30V | mismatch combined with a process corner |
| `wcs_n40` | `*_mismatch` (wcs) | -40°C | 3.30V | mismatch combined with a process corner |
| `wcs_125` | `*_mismatch` (wcs) | 125°C | 3.30V | mismatch combined with a process corner |

This satisfies the issue's own bar ("at least bcs/wcs at -40°C and 125°C,
3.30V") without also sweeping the full `{2.97, 3.30, 3.63}` supply axis:
`../closed-loop-vref-pvt/` and `../closed-loop-iq/` already cover that axis
deterministically and independently, and multiplying N≥300 mismatch draws
by 3 supply points for no incremental evidence value this issue asks for
would triple this campaign's own runtime. Per-mismatch-family decomposition
(HBT-only / MOS-only / resistor-only draws) is explicitly optional per the
issue's own Test Plan and is not run here — a natural, cheap follow-up
using this same driver and template if the aggregate spread ever needs
attributing to one device family over another.

## Evidence volume (#26): what is committed, and what is not

Committing all `6 x N` (≥1800 at N=300) raw per-draw netlists and `ngspice`
logs would violate this issue's own "not N raw ngspice logs" instruction
and dwarf every other experiment's evidence footprint. This experiment
instead commits, per `<record-id>`:

- **`records/<record-id>.csv`** — the corner-id-matched **digest** CSV
  `sim/README.md`'s evidence-format checker cross-references against
  `netlist-snapshots/<record-id>/*.spice` and `corners/<record-id>/*.log`
  (the same contract every other `sim/` experiment satisfies): **one row
  per point** (6 rows), each carrying that point's own N/n_pass/mean/sigma/
  3sigma-over-mean%/min/max/`within +/-1%`/`within +/-0.5%` summary
  statistics.
- **`netlist-snapshots/<record-id>/<corner-id>.spice`** and
  **`corners/<record-id>/<corner-id>.log`** — the **representative draw 0**
  netlist and raw log for each of the 6 points (6 files each, not
  `6 x N`) — enough for `sim/README.md`'s DUT-freshness check (device
  models/params, not node names) and for a human to see exactly what one
  draw's netlist looks like, without paying for `6 x N` near-identical
  copies that differ only in `.options rndseed=<N>`.
- **`records/<record-id>-draws.csv`** — the actual **per-draw summary CSV**
  this issue's Acceptance Criteria ask for: all `6 x N` rows (one per draw,
  every point), the raw data the digest CSV's statistics above are computed
  from. This file is a plain sibling in `records/`, not named
  `<record-id>.csv` — `check_evidence_formats.py`'s corner-id cross-check
  only inspects the file that exactly matches the record's own `.md` stem
  (see its own docstring, "the `.csv` sibling"), so this second CSV is free
  to carry `6 x N` rows without being required to have `6 x N` matching
  netlist/log files of its own.

No per-draw `ngspice` log or per-draw netlist is committed anywhere; the
scratch working directory the removed `run_mc.sh` generated them in is deleted on exit
(`mktemp -d` + `trap ... EXIT`), whether the run succeeds or fails.

## Negative control (hard gate, not just reported)

The removed `run_mc.sh` computed the negative control's `vref` min/max **before**
writing the record, and `exit 1`s with a loud, explicit error — rather than
writing a record — if that spread is not *exactly* zero (bit-identical
across every draw). The same rndseed sequence that produces a real,
different draw against the `_mismatch` sections must produce the *same*
`vref` every time against the plain (non-statistical) sections; any
observed spread there would mean a mismatch section leaked into the
control, or `.options rndseed=` is not actually reaching `ngspice` before
parse — a driver bug, not sampling noise (the same "any nonzero spread here
is disqualifying" discipline `sky130-sar-adc/sim/mc-smoke/` uses for its
own negative control).

## Pass/fail criteria (per draw, and per point)

A **draw** `PASS`es when: `.op` converges (`ngspice` exit 0, no model-load
error) AND every one of `v(fb)`/`v(sns1)`/`v(sns2)`/`v(vref)`/`v(det)`/
`i(Vmkfb)` parses AND the loop is genuinely closed and not railed —
`sim/lib/pvt_verdict_common.sh`'s shared `pvt_closed_loop_verdict()` (the
same `DVSNS_CLOSE_V`/`FB_RAIL_MARGIN_V`/`DET_RELEASE_FRAC`/
`I_MKFB_RELEASE_A` tolerances and formula every closed-loop PVT experiment
in this tree uses), without its optional settledness argument (a single
`.op` has no time axis to settle across).

A **point** (one digest-CSV row) `PASS`es only when **all** `N` of its
draws individually `PASS`. This is a convergence/loop-closure gate, **not**
a pass/fail against any accuracy target — a point with, say, 297/300 PASS
draws is reported `FAIL` here even though its 297 converged draws are
perfectly valid statistical evidence; the record's own prose states the
`n_pass`/`n_draws` fraction either way, so nothing is hidden by this
strict convention.

## Running

The legacy `run_mc.sh` (a hand-launched `ngspice -b` loop) was removed after 1e3baf2f; see git history. The campaign runs
through `klt sim`; see the next section.

## Running on the `klt sim` fleet (issue #403, Part of #273)

The legacy `run_mc.sh` was removed after 1e3baf2f; see git history. The campaign runs as

```bash
sim/closed-loop-vref-mc/run_klt_sim.sh --sanity   # seed-parity probe (3 decks, never a grid)
sim/closed-loop-vref-mc/run_klt_sim.sh --batch    # 6 points x 300 draws = 1800 decks, on the fleet
KLT_SIM_WORK=<batch dir> sim/closed-loop-vref-mc/run_klt_sim.sh --record
```

### Seed parity: how per-draw seeding maps to `klt sim`

`run_mc.sh` seeded draw *i* as `.options rndseed = SEED + i` (line 140), written
at netlist level so it is read before any `agauss()` is evaluated. The mapping
chosen here is the `decks` transport: each draw is the template rendered
exactly as `run_mc.sh` rendered it, with that line included, and klt ships it
byte-for-byte (`sim/harness/vref_mc_klt.py prepare`, requests of 100 draws).
The seeding rule is therefore reproduced by construction, not re-derived:

- Rendering is byte-identical to the removed `run_mc.sh`'s sed pipeline (checked for draws
  0 and 2 of the nominal point; `.options rndseed=20260909` / `20260911`).
- `monte_carlo` alone could not express this: it derived each sample's seed by
  a SHA-256 construction (upstream gap 2AMLogic/klayout-tools#4173, now
  closed). A `monte_carlo.seed_mode: "sequential"` request (`seed + sample_index`)
  now exists, but would also need the SG13G2 corner bundle
  (`sim/harness/klt_corner_bundle.py`) to map the six `_mismatch` sections and
  the per-point `.nodeset` seeds; the decks transport needs neither and matches
  the sibling `closed-loop-vref-trim-mc` conversion.
- Fleet probe (nominal draws 0-2, seeds 20260909-20260911, submitted twice):
  both submissions returned identical `vref` (1.031189 / 1.087442 /
  1.039954 V), so the seed pins the draw on the fleet.

**Live verification NOT performed: draw-for-draw equality with the committed
pre-trim record.** The probe's values differ from that record's draws 0-2
(1.051133 / 1.020032 / 1.084036 V). The two are not like-for-like: that record
ran the pre-trim core, whereas the template now carries the 255-unit trim
ladder, which adds devices to the netlist and so changes which mismatch values
the same seed assigns to which device; and a same-deck local `ngspice` run is
impossible on this dispatch host (its ngspice rejects the v0.4 OSDI models).
So the refresh is a statistically equivalent re-draw, not a replay of the old
draws; equality of the seed rule, not of the values, is what is established.

### Trim-bearing DUT refresh (issue #403)

**DUT.** Same as the #264 refresh: the template's core is the trim-bearing
`design/netlist/bandgap_core.spice` with the ladder pinned at code **128**
(no trim-code axis; the code-swept bench is
[`../closed-loop-vref-trim-mc/`](../closed-loop-vref-trim-mc/README.md)).

**Result** (record `records/20261104-201955-2a0f04d7.md`, 18 fleet jobs
listed in the run's `environment.remote`, 6 points x 300 = 1800/1800 draws PASS):

| point | mean vref (V) | 3sigma/mean (%) | within +/-1% | within +/-0.5% |
|---|---|---|---|---|
| typ mismatch, 27 C | 1.054644 | 13.54 | 0.153 | 0.070 |
| typ negative control, 27 C | 1.047278 | 0.00 | 1.000 | 1.000 |
| bcs mismatch, -40 C | 1.053879 | 12.77 | 0.183 | 0.080 |
| bcs mismatch, 125 C | 1.048679 | 15.08 | 0.147 | 0.087 |
| wcs mismatch, -40 C | 1.056207 | 12.54 | 0.177 | 0.090 |
| wcs mismatch, 125 C | 1.054700 | 14.80 | 0.143 | 0.077 |

The negative control is still exactly zero-spread (`vref` identical at all
300 draws). The nominal 3-sigma is 13.54%, against the superseded record's
13.04%: close, as expected for the same summing resistor at code 128, and
reported as measured, not tuned. No ratified spec row is edited; the
untrimmed/trimmed line dispositions are #265's. The `#273` freshness waiver for
the 2026-09-09 record is deleted.

### N=1200 follow-up campaign (issue #635, T1 item 6)

The N=300 run above left one question open: its `klt yield` report's
sigma-to-spec **lower bounds** at the 125 °C corners (2.8845 `bcs_125`,
2.8632 `wcs_125`, at two-sided 95 % confidence) missed the ratified 3σ
gate while the point estimates (3.16, 3.14) sat above it — a
confidence-bound shortfall, not an observed spread violation. #635 sized
the follow-up (break-even N ≈ 881 / 1,182 at the observed half-widths;
a projected WCS lower bound of 3.0011 at N=1,200) and ran it as one fixed
campaign of **N=1200 draws per point** — 7,200 decks, 72 `decks` requests
of 100, `--max-in-flight 4`, `batch.capacity_wait_s=600`, seed rule
unchanged (`20260909 + draw_index`).

**Result** (record `records/20261121-194338-b03b10b7.md`, 72 fleet jobs in
its `environment.remote`, 6 points x 1200 = 7200/7200 draws PASS):

| point | mean vref (V) | 3sigma/mean (%) | within +/-1% | within +/-0.5% | outside 0.882-1.218 V |
|---|---|---|---|---|---|
| typ mismatch, 27 C | 1.050042 | 13.01 | 0.190 | 0.095 | 1 |
| typ negative control, 27 C | 1.047278 | 0.00 | 1.000 | 1.000 | 0 |
| bcs mismatch, -40 C | 1.049321 | 12.31 | 0.198 | 0.100 | 1 |
| bcs mismatch, 125 C | 1.044015 | 14.46 | 0.177 | 0.086 | 1 |
| wcs mismatch, -40 C | 1.051733 | 12.07 | 0.196 | 0.100 | 1 |
| wcs mismatch, 125 C | 1.050103 | 14.17 | 0.179 | 0.092 | 2 |

The negative control is still exactly zero-spread (one distinct `vref`,
1.047278 V, across all 1200 draws — the value `sim/trim-coverage`'s
code-128 point has always read). Six of the 6,000 mismatch draws fall
outside the ±16 % bounds (one per point except `wcs_125`'s two, max
1.264654 V); every one of the 7,200 draws converged with the loop closed,
so no convergence/exclusion distinction is needed this time.

**Superset status: verified draw-for-draw.** The startup CSV the harness
seeds `.nodeset` initial guesses from changed revision between the two
campaigns (2026-10-01 vs 2026-11-18); all nodeset voltages the deck reads
are numerically identical, so the decks differ at most in number
formatting. Joining the first 300 draw indices per point against the
committed `20261104-201955-2a0f04d7-draws.csv` (1,800 rows): every status
matches, and 1,797 of 1,800 `vref` values are byte-identical at the
recorded 7-significant-digit precision — the three exceptions (`bcs_125`
225/273, `wcs_n40` 13) differ by 1 in the last recorded digit
(|Δ| ≤ 1e-6 V, ≤ 1e-6 relative), the fleet runner's floating-point noise
across instance generations, not a different draw. Indices 300-1199 are
fresh draws under the same rule. The N=1200 population is therefore a
superset of the N=300 one for every statistical purpose.

**The gate clears.** The re-minted `klt yield` report (below) reads
sigma-to-spec lower bounds of **3.0782** (`bcs_125`) and **3.2389**
(`wcs_125`) — both above 3, with all five points `met` and every
sample-size verdict `sufficient`. The N=300 shortfall was what it looked
like: bound-width, not spread. The point estimates moved modestly
(`bcs_125` 3.16 → 3.22, `wcs_125` 3.14 → 3.39) and the half-widths halved
as 1/√N, exactly the scaling the sizing used.

## Results (this repo's own committed record)

See `records/<record-id>.md` for the full per-point table (mean/sigma/
3sigma-over-mean%/min/max/`within +/-1%`/`within +/-0.5%`) and the
negative-control confirmation. Read together with
[`../closed-loop-offset/README.md`](../closed-loop-offset/README.md)'s
`dVref/dVos ≈ 8.8 V/V` deterministic sensitivity figure, this record turns
that sensitivity into an actual predicted spread from real device
mismatch — the missing ingredient tracker #4 item 6 and issue #150 were
waiting on.

See `sim/README.md` for the append-only `records/`/`corners/`/
`netlist-snapshots/` convention every experiment in this tree follows —
this experiment follows the same shape, with the one addition
(`records/<record-id>-draws.csv`) "Evidence volume" above explains.

## `klt yield` envelope (issues #630 and #635, T1 item 6)

The statistical evidence `klt signoff` grades for T1 item 6 is a
[`klt yield`](https://github.com/2AMLogic/klayout-tools) JSON report. The
**current** mint is a re-analysis of the committed N=1200 campaign
`20261121-194338-b03b10b7` (issue #635); the N=300 mint of #630
(`20261120-231009-73ef81b4-*`, a re-analysis of `20261104-201955-2a0f04d7`
that failed the hot-corner gate and sized this follow-up) stays beside it
as history. Three files per mint, beside the run's records (producer
`klayout-tools[yield]==0.9.2`; graded under the repo's CI pin
`klayout-tools==0.8.0` — see `manifests/README.md`'s item 6 entry):

- `records/20261121-195500-b03b10b7-yield-samples.json` — the sample set,
  derived by `klt yield-csv` from `20261121-194338-b03b10b7-draws.csv`
  (`--group-by point --value vref_v --status-col status --pass-value PASS
  --draw-col draw_index --unit V`); its `derivation` block pins that CSV's
  sha256 (`73338af2…`) and the column mapping. Six groups of 1,200, zero
  errored draws; the seed rule (`20260909 + draw_index`, N=1,200 per
  population) is readable from the draws' own `seed` column — `klt
  yield-csv` 0.9.2 cannot emit a `provenance` block, so the report's
  `source.provenance` is null (klayout-tools#6974, re-checked at mint
  time: still open, no released producer attaches a control or provenance
  to a CSV-derived sample set).
- `records/20261121-195500-b03b10b7-yield-limits.json` — the spec-limits
  file: 0.882–1.218 V (±16 % of 1.050 V, DR-0011) on the five mismatch
  points only (`nominal`, `bcs_n40`, `bcs_125`, `wcs_n40`, `wcs_125`;
  the zero-spread `negctrl` group is kept out — it is this harness's own
  determinism check, not klt's negative control), each with
  `target_sigma: 3` (the ratified 3σ claim in the form `klt yield` grades:
  sigma-to-spec lower bound at two-sided 95 % confidence) and
  `min_converged_samples: 1200` (the campaign's N, all of which converged),
  `spec_row: output-reference-untrimmed`.
- `records/20261121-195500-b03b10b7-yield-report.json` — the report
  (`klt yield … --measurement nominal,bcs_n40,bcs_125,wcs_n40,wcs_125`,
  6,000 samples; exit 0, `status: "pass"`), cited unpinned by
  `manifests/sg13g2-bandgap.json` under item 6 with the trimmed ±0.5 %
  line declared as a `spec_rows` gap (#303).

**Reported as graded, not curated.** All five sample-size verdicts are
`sufficient` (±1-point yield-interval half-width) and all five
sigma-to-spec lower bounds clear the 3σ gate — 3.5307 (`nominal`), 3.7195
(`bcs_n40`), **3.0782** (`bcs_125`), 3.7613 (`wcs_n40`), **3.2389**
(`wcs_125`) against point estimates 3.6889 / 3.8849 / 3.2189 / 3.9284 /
3.3857 — so the report passes and the `output-reference-untrimmed` citation row
grades `met` (item 6 itself stays `unmet`/`partial_coverage`: the trimmed
±0.5 % line is a declared gap, #303). Six of 6,000 draws
fall outside the bounds (empirical yield 0.99917 at four points,
0.99833 at `wcs_125`, each with its Clopper-Pearson interval). The ±16 %
line and the 3σ claim are not edited; the passing verdict is the measured
outcome #635 was sized to determine, not a relaxation. The **klt negative
control is not declared** (`negative_control: null` + the report's own
warning): no released CLI path attaches a control to a CSV-derived sample
set (klayout-tools#6974 — re-checked at re-mint, still unlanded), and the
campaign's zero-spread `negctrl` point stays what it always was — the
harness's own determinism check, not klt's negative control. When #6974
lands a released CSV-control producer, the next re-mint should declare the
seeded known-bad trim population #630 sketched.

**The N=300 mint stays as history.** `records/20261120-231009-73ef81b4-*`
(min_converged_samples 300, 1,500 samples, exit 3 `status: "fail"`,
hot-corner lower bounds 2.8845 / 2.8632) documented the confidence-bound
shortfall that sized this campaign; it is superseded, not edited.
