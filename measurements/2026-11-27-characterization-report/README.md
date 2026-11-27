# Aggregated characterization report, 27 November 2026 (T1 item 8)

At audited commit **`a1a3a3ef`**, the 1,200-draw mismatch campaign passes the
untrimmed reference's 3σ gate at all five measured points. The lowest 95%
confidence bound is **3.0782** at bcs/125 °C. The trimmed reference still
misses its ±0.5% line, and the schematic PSRR grid misses 60 dB at one corner.
The verdict table covers all seven target-specification rows. The Iq grid was
re-run, so its envelope's value, limit and margin now re-derive each other.

This report supersedes the [23 November report](../2026-11-23-characterization-report/README.md).
It rotated because the Iq grid was re-minted on 27 November
(`sim/closed-loop-iq/records/20261127-000000-b092b294`) with the signed
average the run graded (#648), which made it that experiment's newest
record. No verdict and no magnitude move. The Iq envelope's cited value
changes sign, from +41.7771 uA to -41.7771 uA, and now reproduces its stored
margin. Four limit-graded grids supply the nominal output, PSRR, Iq and
startup results for item 5. The untrimmed row uses the November 21 campaign
and yield report for item 6. Earlier reports document the measurement history.

## Untrimmed mismatch campaign

The fleet ran 72 batches of 100 decks at trim code 128. All 7,200 draws
converged, including 1,200 deterministic controls at 1.047278 V.
Each point uses seeds `20260909 + draw_index` for indices 0 through 1199.
Joining the first 300 indices per point to the November 4 campaign gives
1,800 matching statuses and 1,797 identical recorded voltages. Three
values differ by one unit in the last printed digit (at most 1 µV):
bcs/125 °C draws 225 and 273, and wcs/−40 °C draw 13. The run record lists
the batch jobs. [Campaign record](../../sim/closed-loop-vref-mc/records/20261121-194338-b03b10b7.md)

The yield producer (`klayout-tools[yield]==0.9.2`) evaluated 6,000
mismatch draws against 0.882–1.218 V. Six draws fell outside the limits,
including two at wcs/125 °C. The empirical yield estimates carry
Clopper–Pearson intervals. The 3σ gate separately tests the lower bound of
the two-sided 95% interval on the distance to the nearer limit, in standard
deviations. The deterministic control checks the harness. The yield producer
records its own negative control as `not_declared`.
[Yield report](../../sim/closed-loop-vref-mc/records/20261121-195500-b03b10b7-yield-report.json)

| Mismatch point | Sigma-to-spec | 95% lower bound | 3σ gate |
|---|---:|---:|---|
| nominal | 3.6889 | 3.5307 | Pass |
| bcs, −40 °C | 3.8849 | 3.7195 | Pass |
| bcs, 125 °C | 3.2189 | 3.0782 | Pass |
| wcs, −40 °C | 3.9284 | 3.7613 | Pass |
| wcs, 125 °C | 3.3857 | 3.2389 | Pass |

Under the pinned `klayout-tools==0.8.0` grader, the untrimmed citation
grades **met**. Item 6 grades **unmet / partial_coverage** because the
trimmed line is a declared gap (#303). Item 5 grades **unmet / check_failed**
on the as-built PSRR grid. Item 8 grades **met** for the characterization
report. [Signoff verdict](../../manifests/sg13g2-bandgap.signoff.json)

## The design under test and how freshness was established

The current committed DUT is the **trim-bearing** core: `design/netlist/
bandgap_core.spice` and `bandgap_trim.spice` at `9530863` (2026-09-30, the
255-unit R1 trim ladder, #229), `bandgap_amp.spice` at `397fe2d`,
`bandgap_startup.spice` at `66ac99d`; `git log -- design/netlist` shows
nothing newer. The post-layout DUT is the re-extraction from issue #557 (`klt 0.9.3.dev663`): `layout/bandgap_top/bandgap_top.pex.spice` and
`layout/bandgap_startup/bandgap_startup.pex.spice`, both pinned by sha256
in [`dependencies.json`](dependencies.json) (`bandgap_core.pex.spice` was
re-minted in the same pass but is not a `dut[]` input of this report).

Freshness is taken from record metadata and netlist snapshots, not dates.
Each record's "Netlist provenance" block names the netlist commits it
simulated, and `python3 .github/scripts/check_evidence_formats.py` compares
every experiment's newest record's committed per-point netlist snapshots to
the current `design/` netlist. At the audited commit that check passes, and
reports exactly two records as stale-but-waived in
[`sim/evidence-freshness-waivers.json`](../../sim/evidence-freshness-waivers.json)
(both ran on the pre-trim core, `R1 = 511 um`, no trim ladder):

| Stale record (pre-trim DUT) | Waiver issue |
|---|---|
| `sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md` (PEX 45-point vref grid) | #275 |
| `sim/closed-loop-vref-pvt-pex-boxtc/records/20260921-195122-77820fc.md` | #275 |

Both #273 waivers are gone (the untrimmed-MC half was delivered by #403,
the schematic box-TC half by #402's `20261116-024010-dc056b4c` record); the
pre-trim records they covered stay in `sim/` as history. The two remaining
#275 records: their issue is closed, but the re-runs do not exist and the
waivers stand, so this report treats them as stale too. The waiver file
also still carries `extraction-sources` entries (#309) for legacy PEX
records whose parasitic freshness is unchecked — a different waiver kind,
noted by the gate, not DUT staleness.

Three further post-layout benches used the pre-#557 extraction.

| Stale record (pre-#557 extraction) | Bench |
|---|---|
| `sim/closed-loop-psrr-pex/records/20261004-030337-5553d523.md` (45-point PSRR grid) | the post-layout PSRR grid predates the current extraction |
| `sim/closed-loop-zout-pex/records/20261004-030338-5553d523.md` | the post-layout Zout record predates the current extraction |
| `sim/startup-trip-point-pex/records/20260905-033740-fe97115.md` | the startup trip-point PEX record predates the current extraction |

Wherever a row below leans on a stale record, it says **"evidence predates
the current netlist"** (the waived class) or names the pre-#557 extraction
(the three post-layout benches) and does not quote the number as current.

Other disclosures that apply to several rows:

- **Schematic vs post-layout (PEX).** The trim-bearing schematic grids
  cover vref, TC (endpoint and both box-method grids), Iq, startup and
  PSRR. Three limit-graded grids date from 22 November and the Iq grid
  from 27 November. The trim-bearing **PEX** evidence is narrower and,
  since the #557 re-extraction, all of it predates the current extraction:
  the closed-loop PSRR and Zout grids (2026-10-04, `klt sim`, #278) and the
  startup trip-point sweep (2026-09-05). There is no post-layout record on
  the current extraction at all — the re-run one-point core probe is not a
  committed `sim/` record — and no trim-bearing PEX vref/TC/Iq/trim record
  ever existed.
- **Solver aids.** The 2026-10-01 schematic grids and the trim-domain records
  are the real DUT. The remaining pre-trim box-TC record was taken with
  convergence aids (`rshunt`/`gmin`); the aids-free A/B is
  [`sim/closed-loop-vref-boxtc-pretrim-aidsfree/`](../../sim/closed-loop-vref-boxtc-pretrim-aidsfree/README.md)
  (pre-trim core, 2 corners). The 2026-11-16 grid is aids-free like every
  #264 refresh, with the #469 KLU solver.
- **Convergence exclusions** are named per row; a group with `n_pass <
  n_grid` lost points and its extreme may be understated. The 2026-11-16
  120-point grid has none: every group is complete at 8/8.
- **Decision-record status as it stands** (`Status:` field of each file):
  `0007` ratified (2026-09-15); `0008`, `0010`, `0011`, `0013`, `0014` are
  `proposed` (`0011` and `0014` record that ratification comes only through
  the two-key release gate, not by flipping the field); `0012` does not exist
  on `main`. Where a bound below cites one, the status quoted is that one.

## Verdict table

"Current" below means: taken on the trim-bearing DUT at the audited
commit — for post-layout rows, on the extraction from #557.

| Row (bound; governing record) | Verdict | Binding corner | Statistical? | Newest committed record(s) behind it | Fresh? |
|---|---|---|---|---|---|
| **Output reference, nominal**: 1.050 V (`0011`, proposed) | **Met with caveats**: 1.04060 to 1.05052 V over the 45-point grid; nominal 1.04728 V (-0.26%); schematic only. The 120-point box-TC grid (2026-11-16) reads the same range endpoints and the same nominal, a second bench agreeing | bcs/125 C/2.97 V (low), wcs/27 C/3.63 V (high) | No, corner-swept | `sim/closed-loop-vref-pvt/records/20261122-181757-c5b84561.csv` (2026-11-22, limit-graded); corroborated by `sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c.csv` (2026-11-16) | **Current** (schematic). PEX history only: the PEX vref grid predates the current netlist, and the PSRR-PEX record's DC-op `vref_op` (1.03894 to 1.04950 V) predates the current extraction |
| **Output reference, untrimmed line**: ±16% (3 sigma, mismatch MC + PVT) (`0011`) | **Met with caveats**: worst-case 3 sigma total 14.95% against the 16% line (1.05 points of margin); the `klt yield` 3 sigma **lower-bound gate passes at N=1200** (hot-corner bounds 3.0782 / 3.2389 vs 3) | bcs/125 C (3 sigma/mean 14.46%, mean 1.044015 V) | **Yes**: N=1200, seeded | `sim/closed-loop-vref-mc/records/20261121-194338-b03b10b7.{md,csv}` + `-draws.csv` (2026-11-21) + the yield set `20261121-195500-b03b10b7-yield-{samples,limits,report}.json` | **Current** (schematic, trim-bearing core at code 128). The first-300 comparison is quantified above. No PEX mismatch MC |
| **Output reference, trimmed line**: ±0.5% trimmed, 1-point @ 27 C (`0011`) | **UNMET (measured)**: 3 sigma of worst-case deviation over -40 to 125 C is **2.40%** (nominal point); only 24.7% of dies inside ±0.5%. The disposition (redesign, #303) is **unsettled**; the bound is not relaxed | no single corner: 2.40 / 2.41 / 2.39% (typ / bcs / wcs, all at 3.30 V) | **Yes**: N=300 per point, seeded, with negative control | `sim/closed-loop-vref-trim-mc/records/20261030-070305-03e62489.{md,csv}` + `-draws.csv` (2026-10-30) | **Current** (schematic, trim-bearing). No PEX trim-domain MC |
| **Trim**: 1-point @ 27 C only, no hot insertion, no CTAT knob (`0014`, proposed); range >= ±15%; resolution <= 0.25%/step; magnitude only | **Met** (range, resolution); 1-point-only holds by construction (no second knob, `0013`/`0014`) | Range worst: +29.22 / -29.63% (both wcs / 2.97 V); resolution worst 0.2347%/step (bcs 3.30/3.63 V) | No: 15 corner/supply groups, deterministic | `sim/trim-coverage/records/20261030-061206-03e62489.{md,csv}` + `-analysis.csv` (2026-10-30) | **Current** (schematic). No PEX trim sweep. `0014` is `proposed` and #303 may change the DUT |
| **Temp coefficient** (-40 to 125 C): < 50 ppm/C; stretch < 20 | **Target met; stretch not met.** Box method, default code 128: two independent trim-bearing grids agree — `closed-loop-vref-boxtc-trim` 20.2 to 38.6 ppm/C and the 120-point grid 20.20 to 38.62 ppm/C (0 of 15 groups below 20, worst `bcs`/3.63 V in both); ±1-code band worst **45.7 ppm/C** (inside 50 by 8.6%). Endpoint method: -37.3 to -14.1 ppm/C | bcs / 3.63 V (box, both grids; code 127: 45.7); endpoint worst bcs / 3.63 V | No, corner-swept | `sim/closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv` (box, ratified row); `sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c-boxtc.csv` (box, 120-point); `sim/closed-loop-vref-pvt/records/20261122-181757-c5b84561-tc.csv` (endpoint) | **Current** (schematic: all three trim-bearing). The PEX and pre-trim box-method records (20.1 / 19.8 ppm/C worst) **predate the current netlist** |
| **PSRR @ DC**: > 60 dB; stretch > 70 | **UNMET (measured, now machine-graded)**; stretch not met. The only current record is schematic: 59.685 to 100.400 dB, **44/45 above 60 dB** — the worst corner reads 59.68493 dB, below the bound, and since issue #629 the run's own report grades it (44/45 PASS; the failing envelope is the block manifest's cited item-5 citation). The post-layout grid that met it (60.001 to 99.507 dB, 45/45, margin 0.0013 dB; 10/45 above 70) predates the current extraction and is history, not a current claim | bcs / 125 C / 3.63 V | No, corner-swept | `sim/closed-loop-psrr/records/20261122-182058-1d0308ad.csv` (current, limit-graded); `sim/closed-loop-psrr-pex/records/20261004-030337-5553d523.csv` (history) | **Current** (schematic). The post-layout PSRR grid predates the current extraction |
| **Supply**: 3.3 V ±10% (HV); stretch 1.2 V (LV) | **Met by construction** (rating argument, `0002` ratified); every current record sweeps 2.97/3.30/3.63 V. The 1.2 V stretch is a flavor statement, not measured | n/a | No | `spec/decision-records/0002-supply-voltage-scope.md` + `vdd_v` column of the records above | Current (grid); the argument itself is not simulated |
| **Iq**: < 50 uA; stretch < 20 | **Met with caveats; stretch not met.** 19.58 to 41.78 uA, 45/45 under 50 (margin 16.4%); 2/45 under 20 uA. Pre-layout only. The envelope's grade re-derives from its signed average at all 45 corners | bcs / 125 C / 3.63 V (signed average -41.7771 uA; margin 8.2229 uA) | No, corner-swept | `sim/closed-loop-iq/records/20261127-000000-b092b294.csv` (2026-11-27, limit-graded on the signed average; identical to `20261122-181711-c5b84561` in every cell except the sign of `iq_avg_a`) | **Current** (schematic). No PEX Iq bench exists |
| **Startup**: self-starting, < 1 ms | **Met**: 45/45 self-start; every point released by the first 100 us checkpoint (~10x inside 1 ms; resolution 100 us). Post-layout: startup-cell trip point 45/45 | all points identical at the checkpoint resolution | No: pass counts | `sim/closed-loop-startup/records/20261118-082945-3e600d97.csv` (2026-11-18, KLU re-time; claims unchanged from `20261001-083332-e5507b2`); `sim/startup-time-to-release/records/20261122-183926-90e8e4dd.csv` (2026-11-22, limit-graded); `sim/startup-trip-point-pex/records/20260905-033740-fe97115.csv` | **Current** (schematic). The startup trip-point PEX record predates the current extraction: the `bandgap_startup` layout it names is byte-identical, but the re-minted extraction (subcircuit `rhigh`, substrate tie) is the DUT now committed. No PEX time-to-release |

## Per-row notes

### Output reference

Three lines, kept separate because they have different evidence and
different status.

**Nominal 1.050 V.** On the current DUT (schematic, code 128), `vref` over the
45-point grid is 1.04060 to 1.05052 V, i.e. -0.90% to +0.05% around 1.050 V,
all 45 points settled (`|vref(3ms)-vref(2ms)| = 0`). Typ/27 C/3.30 V reads
1.04728 V. The default code reproduces the pre-trim operating point to 0.06 mV
(1.047278 V against 1.047338 V, from `sim/trim-coverage`'s own record). The
120-point box-TC grid minted 2026-11-16 (#402) is an independent second bench
on the same corner set and reads the same range endpoints and the same
nominal to all five decimals (max settle delta 1e-05 V). The stale PEX grid
(1.04309 to 1.05667 V, nominal 1.05048 V) is **not quoted as current**;
neither is the PSRR-PEX bench's DC operating-point column (1.03894 to
1.04950 V), which predates the current extraction — no post-layout `vref`
exists on the current extraction (the re-run core probe is not a committed
record).

**Untrimmed ±16% line.** The largest sum of the 3σ spread and the mean
offset, both relative to 1.050 V, is **14.95%** at bcs/125 °C
(mean 1.044015 V). This leaves 1.05 percentage points to the bound.
The earlier N=300 record gave 15.31% at wcs/125 °C. The table above
reports the separate confidence-bound test. Both results apply to the
seeded trim-bearing schematic at code 128 and 3.30 V. Post-layout
mismatch remains unmeasured.

**Trimmed ±0.5% line.** Measured **not met**. The trim-domain MC
(`sim/closed-loop-vref-trim-mc`) models a 1-point trim at 27 C (per-die code
chosen from a 3-code fit) on the trim-bearing DUT, with the ladder's own
mismatch inside the draw, and reads vref at -40, 27 and 125 C. Per point
(seed `20260930 + draw_index`, N=300; re-minted 2026-10-30 on the fleet, record `20261030-070305-03e62489`):

| Point | Converged / N | Inside ±0.5% over -40 to 125 C | 3 sigma of worst-case deviation | Worst draw |
|---|---|---|---|---|
| typ mismatch (27 C reference) | 299 / 300 (1 excluded) | 24.7% | 2.399% | 4.44% |
| bcs mismatch | 300 / 300 | 25.0% | 2.413% | 4.33% |
| wcs mismatch | 300 / 300 | 27.0% | 2.390% | 4.41% |
| typ negative control | 300 / 300 | 100% | 0.000% | 0.43% |

Statistics are over the converged draws only; the exclusions are
draws whose verification failed (no reading recorded), not outliers dropped on value. Only the typ point
lost a draw (1 of 300); bcs and wcs converged in full this time, so all three
points now rest on essentially the whole population. At the 27 C trim point
itself all 299 converged nominal draws land within 0.284% (the trim works
there); the failure is the temperature
drift, which the 1-point trim cannot remove. The mismatch-free negative
control still drifts 0.43% over temperature, above the 0.20% budget input
`0011` used. The campaign covers the schematic only and the three-corner
(typ/bcs/wcs) mismatch set at 3.30 V; the sf/fs corners and the 2.97/3.63 V
supplies are not covered, and no PEX trim-domain MC exists. The record's own
status is `FAIL` at the 3 sigma gate for these three points, and that is what
it shows. Whether the bound is met by a redesign (#303) is not decided here.

### Trim

Range and resolution measured on the current DUT across all 15
corner/supply groups at 27 C (169/169 points converged): range at worst
+29.22% / -29.63% (bound ±15%), resolution 0.2309 to 0.2347% of target per
step (bound 0.25%), worst deviation from exact binary weights 0.2937%, monotonic
in 15/15. "1-point @ 27 C only, magnitude only" is a structural statement,
and nothing in the design adds a second knob (`0013`, `0014`: both `proposed`).
It is not a measured quantity. The row is on the current netlist but, like the
trimmed line, schematic-only.

### Temp coefficient

Target met on the current DUT by both methods; the stretch is not met, and
that disposition is #269's. Box method (the method the two-key review asked
for), default code 128 — now on **two independent trim-bearing grids that
agree**: the ratified-row evidence `sim/closed-loop-vref-boxtc-trim`
(15 groups, 20.2 to 38.6 ppm/C, worst bcs/3.63 V) and the 120-point grid
minted 2026-11-16 (#402, record `20261116-024010-dc056b4c`): 15 groups, all
complete at 8/8, 20.20 to 38.62 ppm/°C, worst bcs/3.63 V at 38.62 ppm/°C;
**0 of 15 groups below the 20 ppm/°C stretch** in both. The ±1-code band the
real trim lands in (codes 127 to 129, `closed-loop-vref-boxtc-trim`, 45
groups): 15.5 to 45.7 ppm/C, 45/45 under 50 and 3/45 under 20 (all three are
code 129 at wcs, which is not the default). Endpoint method: -37.3 to -14.1
ppm/C, worst bcs/3.63 V — the 2026-11-16 grid's endpoint column repeats the
`closed-loop-vref-pvt` twin's range exactly, two separately-written benches
agreeing. The box extrema sit at the hot end (`vmin` at 125 °C in all 15
groups of the new grid; `vmax` at 0 °C for typ/sf/fs, −20 °C for bcs, 27 °C
for wcs), which is what makes the box a real full-grid claim this time: the
superseded 2026-11-13 attempt topped out around 105/120 with exactly the hot
end missing, and was correctly not recorded as a refresh. Disclosure: the
PEX and pre-trim box-method records (20.1 / 19.8 ppm/C worst) predate the
current netlist and are history, not current numbers; their #273 waiver is
gone (both halves of the refresh it covered are delivered — #403's MC
re-mint and this grid) and the remaining pre-trim waivers are the two #275
PEX rows above.

### PSRR @ DC

**Not met on current evidence.** The only current record is the schematic
as-built limit-graded grid (2026-11-22): 59.685 to 100.400 dB, 44/45 above 60 dB, worst 59.685 dB
at bcs/125 C/3.63 V — below the bound. The record that met the row was the
post-layout, trim-bearing grid (2026-10-04): 45/45 points above 60 dB at
**60.001 dB for the worst point** (0.0013 dB margin; next-worst 60.336 dB),
10/45 above the 70 dB stretch. The post-layout PSRR grid predates the
current extraction — it was extracted from the pre-#557 layout, whose
Via1 landings changed in #557 — so its
45/45 is history, not a current claim, and the row is reported as not met
rather than resting a marginal pass on superseded parasitics. The stretch
(> 70 dB) is not met either way. `0006` documents the narrowband above-DC
transmission zero; no above-DC bound exists in the spec (the PEX record's
`psrr_min_db` is 5.69 to 6.59 dB at the HF notch, outside this row). A
re-run of the PEX grid on the current extraction is the missing
current-evidence half of this row.

### Supply

Not a simulated quantity. The record argument is `0002`; the current records
sweep exactly the 2.97/3.30/3.63 V grid the row specifies.

### Iq

Schematic only, current. 19.58 to 41.78 uA across 45 points; the 20 uA
stretch is touched only at 2 points. The record is the 27 November re-run
(`sim/closed-loop-iq/records/20261127-000000-b092b294`), the first minted
with the #648 report generator. It is identical to the 22 November record
it supersedes in every cell except the sign of `iq_avg_a` (recomputed from
both CSVs, 45 rows x 17 columns). All 45 of its stored netlist snapshots,
read from the artifact store, carry the committed DUT: the core's 275
device lines verbatim, the amplifier's and startup cell's devices
differing only by the flattened port nets and the `Vmkfb` ammeter fixture.
That column now keeps the sign `klt sim`
graded: negative while the supply delivers current. The row's grade
therefore re-derives from the envelope itself at every corner. The rollup
carries `limits.min` -5e-05 A. The binding corner, bcs/125 C/3.63 V, reads
-4.17771e-05 A with a stored margin of 8.2229e-06 A, the signed value minus
the lower limit. In the superseded envelope that corner read +4.17771e-05 A
beside the same margin, which the published value did not give by that
subtraction (9.17771e-05 A). `iq_2ms_a` and `iq_3ms_a` remain magnitudes
and equal `|iq_avg_a|` at six significant figures. The 2026-11-18 KLU
re-time record reproduced its predecessor on every verdict-bearing column
(recomputed from both CSVs, the one moving shared column is `i_mkfb_a`, a
~1e-15…1e-13 A noise-floor current moving ≤ ~1.6% relative on 33/45
points), so the switch of the direct solver moves the bench's provenance,
not its numbers. No post-layout Iq bench exists; Iq is a DC bias quantity,
but that is a judgment, not evidence.

### Startup

Self-start 45/45 and time-to-release at the first 100 us checkpoint on all 45
points, schematic, current (the self-start grid is the 2026-11-18 KLU
re-time record; its claims are unchanged from the 2026-10-01 record it
replaces — the one moving stored column is `i_mkfb_final_a`, a ~1e-15…1e-13
A noise-floor current (32/45 points, max ~1.3% relative), every stored
node voltage is identical, and no verdict reads it). The post-layout
evidence is the startup cell's trip point (45/45, 2026-09-05), which exercises the extracted
`bandgap_startup` layout; the startup trip-point PEX record predates the
current extraction (the layout is byte-identical, the extraction is
re-minted), it was never run against the trim-bearing assembly, and there
is no post-layout time-to-release.

## Supplementary current evidence not tied to a spec row

- Loop stability on the current DUT: `sim/loop-gain-phase-margin/records/
  20261003-180919-2addad0.csv`, the solve-quality-guarded grid from #289 (45/45
  `quality=ok`; minimum phase margin 83.5 deg across the 45 rows). Not a spec
  row.
- Output impedance, post-layout: `sim/closed-loop-zout-pex/records/
  20261004-030338-5553d523.csv`. The post-layout Zout record predates the
  current extraction. Not a spec row; not quoted further here.

## Gaps this report does not close

- #303 (open): redesign against mismatch and re-aim of the trim for the
  trimmed line; one-point trim only.
- #273's two evidence halves are delivered (#403's untrimmed-MC re-mint;
  #402's schematic box-TC grid, 2026-11-16) and both its waivers are
  deleted; whether the issue itself closes is the tracker's call.
- The two PEX re-runs still waived under #275 have no open tracker.
- The three post-layout benches disclosed as stale (PSRR-PEX,
  Zout-PEX, startup trip-point) need re-runs on the current #557 extraction;
  the `extraction-sources` waivers they carry (#309) still mark their
  parasitic freshness unchecked, and this report's disclosure replaces, not
  creates, a tracker.
- No post-layout Iq, trim-domain or trim-coverage evidence; no post-layout
  time-to-release; no post-layout record at all on the current extraction.
- If #303 changes the DUT before this report is merged or later, every row
  marked "Current" must be rechecked; the netlist-snapshot check will flag the
  ones that go stale.

## Reproducing the spot-check

```sh
python3 -I measurements/2026-11-27-characterization-report/spotcheck.py
```

The script reads the committed CSVs, the item 5 corner envelopes and the
item 6 yield report, and re-derives the Iq row's signed grade from its
envelope. Its output for the audited inputs follows.

```text
vref-pvt sch trim-bearing: 45/45 PASS; vref 1.04060..1.05052 V; vs 1.050 V: -0.90%..+0.05%; nominal typ/27C/3.30V 1.04728 V (-0.259%); max settle delta 0 V
vref-pvt sch trim-bearing endpoint TC: 15 groups; -37.3..-14.1 ppm/C; max |TC| 37.3; groups < 50: 15; groups < 20: 3
psrr-pex vref_op (PEX trim-bearing, 27C/DC op only): 45/45 PASS; vref_op 1.03894..1.04950 V
PSRR@DC PEX trim-bearing: 60.001..99.507 dB; >60 dB: 45/45; >70 dB: 10/45; worst 60.0013 dB at bcs/125C/3.63V
PSRR@DC PEX trim-bearing, 2nd/3rd worst: 60.336, 60.502 dB
PSRR above-DC min (PEX trim-bearing): psrr_min_db 5.69..6.59 dB (HF notch, not the DC row)
PSRR@DC sch trim-bearing: 59.685..100.400 dB; >60 dB: 44/45; >70 dB: 10/45; worst at bcs/125C/3.63V
Supply grid actually swept by the current records: ['2.97', '3.30', '3.63']
Iq sch trim-bearing: 45/45 PASS; 19.58..41.78 uA; <50 uA: 45/45; <20 uA: 2/45; worst bcs/125C/3.63V; margin to 50 uA 16.4%; max settle delta 0 A
Iq signed grade: 45/45 corners re-derived (avg < 0, samples >= 0, margin = avg - limits.min); limits.min -5e-05 A; binding bcs/3.63V/125C: avg -4.17771e-05 A, margin 8.2229e-06 A, pass; rollup names a smallest-margin corner
startup sch trim-bearing: 45/45 PASS
startup time-to-release sch trim-bearing: 45/45 PASS; release_time_us values ['1.000000e+02']; max 100 us (ladder step 100 us)
startup trip point PEX (2026-09-05): 45/45 PASS
trim-coverage: 15/15 groups PASS; range up +29.22..+29.72%, down -29.63..-30.12% (worst-case +29.22/-29.63); LSB 0.2309..0.2347 %/step; worst binary-weight deviation 0.2937%; monotonic in 15/15
trim-coverage points: 169/169 PASS
trim-MC nominal: N=300 draws, 299 converged (1 excluded); within +/-0.5% over -40..125C: 24.7%; 3*sigma(max_dev) 2.399%; worst draw 4.44%; seeds 20260930..20261229
trim-MC bcs: N=300 draws, 300 converged (0 excluded); within +/-0.5% over -40..125C: 25.0%; 3*sigma(max_dev) 2.413%; worst draw 4.33%; seeds 20260930..20261229
trim-MC wcs: N=300 draws, 300 converged (0 excluded); within +/-0.5% over -40..125C: 27.0%; 3*sigma(max_dev) 2.390%; worst draw 4.41%; seeds 20260930..20261229
trim-MC negctrl: N=300 draws, 300 converged (0 excluded); within +/-0.5% over -40..125C: 100.0%; 3*sigma(max_dev) 0.000%; worst draw 0.43%; seeds 20260930..20261229
trim-MC digest typ_mismatch: status FAIL, n_pass 299/300, frac_within_0p5 24.75%, 3sigma 2.399%
trim-MC digest typ_negctrl: status PASS, n_pass 300/300, frac_within_0p5 100.00%, 3sigma 0.000%
trim-MC digest bcs_mismatch: status FAIL, n_pass 300/300, frac_within_0p5 25.00%, 3sigma 2.413%
trim-MC digest wcs_mismatch: status FAIL, n_pass 300/300, frac_within_0p5 27.00%, 3sigma 2.390%
trim-MC nominal at the 27C trim point: max |dev_27c| 0.284%; draws with |dev_27c|<=0.5%: 299/299
box TC trim-bearing, code 128: 15 groups; 20.2..38.6 ppm/C; < 20: 0; < 50: 15
box TC trim-bearing, code 128 worst: bcs_code128/3.63V 38.610
box TC trim-bearing, codes 127..129: 45 groups; 15.5..45.7 ppm/C; < 50: 45/45; < 20: 3/45
box TC trim-bearing worst near-band: bcs_code127/3.63V 45.695 (n_pass 8/8)
box TC groups with excluded points: 20 of 45 near-band groups have n_pass<n_grid (fs_code127/2.97V:7/8, fs_code127/3.30V:6/8, fs_code127/3.63V:7/8, fs_code128/2.97V:7/8, fs_code128/3.30V:7/8, fs_code129/2.97V:7/8, fs_code129/3.30V:7/8, fs_code129/3.63V:7/8, sf_code127/2.97V:7/8, sf_code127/3.30V:7/8, sf_code128/2.97V:7/8, sf_code128/3.30V:7/8, sf_code128/3.63V:7/8, sf_code129/2.97V:7/8, sf_code129/3.63V:7/8, typ_code128/2.97V:7/8, typ_code128/3.30V:7/8, typ_code128/3.63V:7/8, typ_code129/2.97V:7/8, typ_code129/3.30V:7/8)
box TC complete groups only: 25 groups; max 45.695
box-TC grid sch trim-bearing: 120/120 PASS; vref 1.04060..1.05052 V; vs 1.050 V: -0.90%..+0.05%; nominal typ/27C/3.30V 1.04728 V (-0.259%); max settle delta 1e-05 V
box TC trim-bearing 120-point grid, code 128: 15 groups, complete: 15/15; 20.20..38.62 ppm/C; < 20: 0; < 50: 15; worst 38.62 at bcs/3.63V
box TC trim-bearing 120-point grid endpoint TC: 15 groups; -37.3..-14.1 ppm/C; max |TC| 37.3
box TC trim-bearing 120-point grid extrema: vmin at 125 C in 15/15 groups; vmax at -20 C (bcs), 0 C (fs/sf/typ), 27 C (wcs)
PEX pre-trim endpoint TC (STALE): -17.6..15.5 ppm/C over 15 groups
sch pre-trim box TC (STALE): 15 groups; max 19.8 ppm/C at wcs/3.30V (n_pass 8/8)
PEX pre-trim box TC (STALE): 15 groups; max 20.1 ppm/C at bcs/3.63V (n_pass 8/8)
pre-trim aids-free A/B: 4 groups; header ['corner_label', 'vdd_v', 'n_pass', 'n_grid', 'vmin_v', 'vmin_temp_c']
    {'corner_label': 'bcs_aided', 'vdd_v': '3.63', 'n_pass': '2', 'n_grid': '2', 'vmin_v': '1.0433', 'vmin_temp_c': '125', 'vmax_v': '1.0464', 'vmax_temp_c': '0', 'vref_27c_v': '', 'box_tc_ppm_per_c': ''}
    {'corner_label': 'bcs_aidsfree', 'vdd_v': '3.63', 'n_pass': '8', 'n_grid': '8', 'vmin_v': '1.0411', 'vmin_temp_c': '125', 'vmax_v': '1.0443', 'vmax_temp_c': '0', 'vref_27c_v': '1.0442', 'box_tc_ppm_per_c': '18.515'}
    {'corner_label': 'typ_aided', 'vdd_v': '3.63', 'n_pass': '1', 'n_grid': '1', 'vmin_v': '1.048', 'vmin_temp_c': '125', 'vmax_v': '1.048', 'vmax_temp_c': '125', 'vref_27c_v': '', 'box_tc_ppm_per_c': ''}
    {'corner_label': 'typ_aidsfree', 'vdd_v': '3.63', 'n_pass': '8', 'n_grid': '8', 'vmin_v': '1.0456', 'vmin_temp_c': '125', 'vmax_v': '1.0474', 'vmax_temp_c': '27', 'vref_27c_v': '1.0474', 'box_tc_ppm_per_c': '10.705'}
untrimmed MC digest typ_mismatch: 27C n_pass 1200/1200, mean 1.050042 V, 3sigma/mean 13.01%, within 1%: 19.0%, within 0.5%: 9.5%
untrimmed MC digest typ_negctrl: 27C n_pass 1200/1200, mean 1.047278 V, 3sigma/mean 0.00%, within 1%: 100.0%, within 0.5%: 100.0%
untrimmed MC digest bcs_mismatch: -40C n_pass 1200/1200, mean 1.049321 V, 3sigma/mean 12.31%, within 1%: 19.8%, within 0.5%: 10.0%
untrimmed MC digest bcs_mismatch: 125C n_pass 1200/1200, mean 1.044015 V, 3sigma/mean 14.46%, within 1%: 17.7%, within 0.5%: 8.6%
untrimmed MC digest wcs_mismatch: -40C n_pass 1200/1200, mean 1.051733 V, 3sigma/mean 12.07%, within 1%: 19.6%, within 0.5%: 10.0%
untrimmed MC digest wcs_mismatch: 125C n_pass 1200/1200, mean 1.050103 V, 3sigma/mean 14.17%, within 1%: 17.9%, within 0.5%: 9.2%
untrimmed MC nominal recomputed from draws: N=1200 mean 1.050042 sigma 0.045531 3sigma/mean 13.01%
untrimmed worst-case 3sigma total vs 1.050 V (DR-0011's 15.3% sum, recomputed): 14.95% vs the +/-16% line
untrimmed MC +/-16% band around 1.050 V: draws inside [0.882, 1.218] V: 1199/1200
PEX pre-trim vref grid (STALE): 45 PASS; 1.04309..1.05667 V; nominal 1.05048 V
loop-gain (supplementary, not a spec row): 45/45 PASS, 45 quality=ok rows
loop-gain phase margin: 45 rows with a crossover; min 83.5 deg
item-6 nominal: 1200/1200 converged; 95% lower bound 3.5307; target 3 met=True
item-6 bcs_n40: 1200/1200 converged; 95% lower bound 3.7195; target 3 met=True
item-6 bcs_125: 1200/1200 converged; 95% lower bound 3.0782; target 3 met=True
item-6 wcs_n40: 1200/1200 converged; 95% lower bound 3.7613; target 3 met=True
item-6 wcs_125: 1200/1200 converged; 95% lower bound 3.2389; target 3 met=True
first 300 draws per point: 1800/1800 matching statuses; 1797/1800 identical Vref strings
deterministic control: 1200 converged; distinct Vref (V) ['1.047278e+00']
item-5 envelope output-reference-nominal: pass; limits {'min': 0.882, 'max': 1.218}; worst 1.0406 at bcs/2.97V/125C (margin 0.1586); corners 45/45 pass
item-5 envelope psrr-dc: fail; limits {'max': 0.001}; worst 0.00103694 at bcs/3.63V/125C (margin -3.694e-05); corners 44/45 pass
item-5 envelope iq: pass; limits {'min': -5e-05}; worst -4.17771e-05 at bcs/3.63V/125C (margin 8.2229e-06); corners 45/45 pass
item-5 envelope startup: pass; limits {'min': -5e-08, 'max': 5e-08}; worst 1.83124e-10 at bcs/3.63V/125C (margin 4.98169e-08); corners 45/45 pass
```

Two conventions to read the output by: "3 sigma of worst-case deviation" is
`3 * stdev` of each converged draw's `max_dev_pct` (the maximum absolute
deviation from 1.050 V over -40/27/125 C), the same definition the record's own
digest uses (reproduced exactly: 2.399440 for the nominal point); and the
box-method TC is `(vmax-vmin)/(vref(27C) * 165 C)`, taken from the record's
`box_tc_ppm_per_c` column.

## Binding

[`envelope.json`](envelope.json) is a `generic` envelope for T1 item 8. It
pins the sha256 of **this file** (not of the envelope) in its
`provenance.input`, and `manifests/sg13g2-bandgap.json` pins the same hash.
Editing this file without regenerating both makes
`.github/scripts/check_signoff_manifest.py` fail. Companion files
(`spotcheck.py`) are not hashed.
