# Aggregated characterization report, October 2026 (T1 item 8, the `Characterization report` row)

Audited commit: **`b89f4c5f`** (`main` on 2026-10-08, merge of PR #306).
Supersedes [`../2026-09-characterization-report/`](../2026-09-characterization-report/README.md)
(written 2026-09-21 against `77820fc`; left untouched as history).

This is the one aggregated, current artifact giving per-spec-row performance
across conditions, with the committed evidence record each verdict rests on.
**No simulation was run for it.** Every number is read from a record already
committed under `sim/`, and every quoted figure is reproduced by
[`spotcheck.py`](spotcheck.py) (output at the end of this file).

## What this report claims, and what it does not

- **It claims** completeness and honest citation: one entry per row of the
  `README.md` "Target specification" table as it stands at the audited commit
  (seven rows; the Output-reference row is reported as its three lines:
  nominal, untrimmed, trimmed), each with its bound, verdict, binding corner,
  whether the verdict is statistical, the newest committed record behind it,
  and whether that record was taken on the current (trim-bearing) design.
- **It does not claim every row passes.** Two lines fail or are only
  caveated-met, and they are reported as such. A `met` on T1 item 8 means
  "this report exists, is current and cites its evidence"; whether the block
  conforms to its spec is T1 item 5's question, and the report's passing
  `envelope.json` attests nothing else.
- **It does not change the spec.** No spec row, decision record, sim record
  or netlist is edited. Bounds are copied from the spec table as it stands;
  nothing here relaxes one. The `±4.5%` re-cast of the trimmed line (PR #270,
  would-be record `0012`) was **declined** by operator ruling on 2026-10-08;
  it is not approved, no `0012` exists on `main`, and the redesign is tracked
  in **#303** (open). Where this report says "unsettled" it means that
  redesign outcome, not the measured failure.

## The design under test and how freshness was established

The current committed DUT is the **trim-bearing** core: `design/netlist/
bandgap_core.spice` and `bandgap_trim.spice` at `9530863` (2026-09-30, the
255-unit R1 trim ladder, #229), `bandgap_amp.spice` at `397fe2d`,
`bandgap_startup.spice` at `66ac99d`; `git log -- design/netlist` shows
nothing newer. The post-layout DUT is `layout/bandgap_top/bandgap_top.pex.spice`
re-extracted at `8a44ec19` (2026-10-01, #272); no commit since touches it.

Freshness is taken from record metadata and netlist snapshots, not dates.
Each record's "Netlist provenance" block names the netlist commits it
simulated, and `python3 .github/scripts/check_evidence_formats.py` compares
every experiment's newest record's committed per-point netlist snapshots to
the current `design/` netlist. At the audited commit that check passes, and
reports exactly four records as stale-but-waived in
[`sim/evidence-freshness-waivers.json`](../../sim/evidence-freshness-waivers.json)
(each ran on the pre-trim core, `R1 = 511 um`, no trim ladder):

| Stale record (pre-trim DUT) | Waiver issue |
|---|---|
| `sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md` (untrimmed MC) | #273 (open) |
| `sim/closed-loop-vref-pvt-boxtc/records/20260921-194249-77820fc.md` | #273 (open) |
| `sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md` (PEX 45-point vref grid) | #275 |
| `sim/closed-loop-vref-pvt-pex-boxtc/records/20260921-195122-77820fc.md` | #275 |

Issue #273 is the owed refresh of the first two (the two grids this report is
asked to flag). The same waiver file also carries two further pre-trim PEX
records under #275; that issue is closed, but the re-runs for those two
records do not exist and their waivers stand, so this report treats them as
stale too. Wherever a row below leans on one of these four, it says
**"evidence predates the current netlist"** and does not quote the number as
current.

Other disclosures that apply to several rows:

- **Schematic vs post-layout (PEX).** The trim-bearing schematic grids
  (2026-10-01) cover vref, TC (endpoint), Iq, PSRR and startup. The
  trim-bearing **PEX** evidence is narrower: the closed-loop PSRR and Zout
  grids (2026-10-04, `klt sim`, #278) and nothing else. There is no
  trim-bearing PEX vref/TC/Iq/trim record.
- **Solver aids.** The 2026-10-01 schematic grids and the trim-domain records
  are the real DUT. The pre-trim box-TC records used convergence aids
  (`rshunt`/`gmin`); the aids-free A/B is
  [`sim/closed-loop-vref-boxtc-pretrim-aidsfree/`](../../sim/closed-loop-vref-boxtc-pretrim-aidsfree/README.md)
  (pre-trim core, 2 corners).
- **Convergence exclusions** are named per row; a group with `n_pass <
  n_grid` lost points and its extreme may be understated.
- **Decision-record status as it stands** (`Status:` field of each file):
  `0007` ratified (2026-09-15); `0008`, `0010`, `0011`, `0013`, `0014` are
  `proposed` (`0011` and `0014` record that ratification comes only through
  the two-key release gate, not by flipping the field); `0012` does not exist
  on `main`. Where a bound below cites one, the status quoted is that one.

## Verdict table

"Current" below means: taken on the trim-bearing DUT at the audited commit.

| Row (bound; governing record) | Verdict | Binding corner | Statistical? | Newest committed record(s) behind it | Fresh? |
|---|---|---|---|---|---|
| **Output reference, nominal**: 1.050 V (`0011`, proposed) | **Met with caveats**: 1.04060 to 1.05052 V over the 45-point grid; nominal 1.04728 V (-0.26%); schematic only | bcs/125 C/2.97 V (low), wcs/27 C/3.63 V (high) | No, corner-swept | `sim/closed-loop-vref-pvt/records/20261001-085908-e5507b2.csv` (2026-10-01) | **Current** (schematic). PEX: only a DC-op `vref_op` of 1.03894 to 1.04950 V in the PSRR-PEX record; the PEX vref grid predates the current netlist |
| **Output reference, untrimmed line**: +/-16% (3 sigma, mismatch MC + PVT) (`0011`) | **Met with caveats, statistical evidence predates the current netlist**: worst-case 3 sigma total 15.32% against the 16% line | bcs/125 C (3 sigma/mean 14.60%, mean 1.041041 V) | **Yes**: N=300, seeded | `sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.{md,csv}` + `-draws.csv` (2026-09-09) | **Predates the current netlist** (waived, #273). The current-DUT 45-point grid (row above) supports only the systematic part |
| **Output reference, trimmed line**: +/-0.5% trimmed, 1-point @ 27 C (`0011`) | **UNMET (measured)**: 3 sigma of worst-case deviation over -40 to 125 C is **2.60%** (nominal point); only 29.8% of dies inside +/-0.5%. The disposition (redesign, #303) is **unsettled**; the bound is not relaxed | no single corner: 2.60 / 2.52 / 2.59% (typ / bcs / wcs, all at 3.30 V) | **Yes**: N=300 per point, seeded, with negative control | `sim/closed-loop-vref-trim-mc/records/20260930-232155-affdefe.{md,csv}` + `-draws.csv` (2026-09-30) | **Current** (schematic, trim-bearing). No PEX trim-domain MC |
| **Trim**: 1-point @ 27 C only, no hot insertion, no CTAT knob (`0014`, proposed); range >= +/-15%; resolution <= 0.25%/step; magnitude only | **Met** (range, resolution); 1-point-only holds by construction (no second knob, `0013`/`0014`) | Range worst: +29.22 / -29.63% (both wcs / 2.97 V); resolution worst 0.2347%/step (bcs 3.30/3.63 V) | No: 15 corner/supply groups, deterministic | `sim/trim-coverage/records/20260930-195507-9530863.{md,csv}` + `-analysis.csv` (2026-09-30) | **Current** (schematic). No PEX trim sweep. `0014` is `proposed` and #303 may change the DUT |
| **Temp coefficient** (-40 to 125 C): < 50 ppm/C; stretch < 20 | **Target met; stretch not met.** Box method, default code 128: 20.2 to 38.6 ppm/C (0 of 15 groups below 20); +/-1-code band worst **45.7 ppm/C** (inside 50 by 8.6%). Endpoint method: -37.3 to -14.1 ppm/C | bcs / 3.63 V (code 128: 38.6; code 127: 45.7); endpoint worst bcs / 3.63 V | No, corner-swept | `sim/closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv` (box); `sim/closed-loop-vref-pvt/records/20261001-085908-e5507b2-tc.csv` (endpoint) | **Current** (schematic). The PEX and pre-trim box-method records (20.1 / 19.8 ppm/C worst) **predate the current netlist** |
| **PSRR @ DC**: > 60 dB; stretch > 70 | **Met with caveats (marginal); stretch not met.** Post-layout, trim-bearing: 60.001 to 99.507 dB, 45/45 above 60 dB, **margin 0.0013 dB**; 10/45 above 70 dB. Schematic reads 44/45 above 60, with the same corner at 59.685 dB | bcs / 125 C / 3.63 V | No, corner-swept | `sim/closed-loop-psrr-pex/records/20261004-030337-5553d523.csv` (primary); `sim/closed-loop-psrr/records/20261001-085737-e5507b2.csv` | **Current** (both) |
| **Supply**: 3.3 V +/-10% (HV); stretch 1.2 V (LV) | **Met by construction** (rating argument, `0002` ratified); every current record sweeps 2.97/3.30/3.63 V. The 1.2 V stretch is a flavor statement, not measured | n/a | No | `spec/decision-records/0002-supply-voltage-scope.md` + `vdd_v` column of the records above | Current (grid); the argument itself is not simulated |
| **Iq**: < 50 uA; stretch < 20 | **Met with caveats; stretch not met.** 19.58 to 41.78 uA, 45/45 under 50 (margin 16.4%); 2/45 under 20 uA. Pre-layout only | bcs / 125 C / 3.63 V | No, corner-swept | `sim/closed-loop-iq/records/20261001-092257-4fe07ea.csv` | **Current** (schematic). No PEX Iq bench exists |
| **Startup**: self-starting, < 1 ms | **Met**: 45/45 self-start; every point released by the first 100 us checkpoint (~10x inside 1 ms; resolution 100 us). Post-layout: startup-cell trip point 45/45 | all points identical at the checkpoint resolution | No: pass counts | `sim/closed-loop-startup/records/20261001-083332-e5507b2.csv`; `sim/startup-time-to-release/records/20261001-085905-e5507b2.csv`; `sim/startup-trip-point-pex/records/20260905-033740-fe97115.csv` | **Current** (schematic). The PEX record is startup-cell-only: it names no `design/` netlist, so the checker does not test it, but the extracted layout it names (`bandgap_startup` at `7b4d0e1`) is unchanged since. No PEX time-to-release |

## Per-row notes

### Output reference

Three lines, kept separate because they have different evidence and
different status.

**Nominal 1.050 V.** On the current DUT (schematic, code 128), `vref` over the
45-point grid is 1.04060 to 1.05052 V, i.e. -0.90% to +0.05% around 1.050 V,
all 45 points settled (`|vref(3ms)-vref(2ms)| = 0`). Typ/27 C/3.30 V reads
1.04728 V. The default code reproduces the pre-trim operating point to 0.06 mV
(1.047278 V against 1.047338 V, from `sim/trim-coverage`'s own record). The
stale PEX grid (1.04309 to 1.05667 V, nominal 1.05048 V) is **not quoted as
current**; the only current post-layout `vref` is the DC operating-point
column of the PSRR-PEX bench.

**Untrimmed +/-16% line.** `0011` derives the line as the worst MC corner's
3 sigma/mean plus its mean offset (14.60% + 0.85% = about 15.3%, rounded up).
The spot check recomputes that sum from the record's own digest as 15.32%. The
MC: seed `20260909 + draw_index`, N=300 per point, nominal point plus
bcs/wcs at -40 and 125 C (3.30 V), 6 points, all 300 draws converged at every
point, deterministic negative control with exactly zero spread (1.047339 V at
all 300 draws). All 300 nominal draws sit inside 1.050 V +/-16%. **This record
ran on the pre-trim core and is waived as stale (#273); the 1800-draw refresh
is owed.** It is quoted as the newest evidence for the line, not as evidence on
the current netlist. Only the corner-swept part is re-measured on the current
DUT, and only on the schematic.

**Trimmed +/-0.5% line.** Measured **not met**. The trim-domain MC
(`sim/closed-loop-vref-trim-mc`) models a 1-point trim at 27 C (per-die code
chosen from a 3-code fit) on the trim-bearing DUT, with the ladder's own
mismatch inside the draw, and reads vref at -40, 27 and 125 C. Per point
(seed `20260930 + draw_index`, N=300):

| Point | Converged / N | Inside +/-0.5% over -40 to 125 C | 3 sigma of worst-case deviation | Worst draw |
|---|---|---|---|---|
| typ mismatch (27 C reference) | 299 / 300 (1 excluded) | 29.8% | 2.601% | 6.72% |
| bcs mismatch | 242 / 300 (58 excluded) | 28.5% | 2.523% | 6.79% |
| wcs mismatch | 293 / 300 (7 excluded) | 31.7% | 2.592% | 6.79% |
| typ negative control | 300 / 300 | 100% | 0.000% | 0.43% |

Statistics are over the converged draws only; the exclusions are
draws whose verification failed (no reading recorded), not outliers dropped on value. The bcs point lost 58 of
300 draws, so its percentages describe a subset and are weaker evidence than
the other two. At the 27 C trim point itself all 299 converged nominal draws
land within 0.246% (the trim works there); the failure is the temperature
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
+29.22% / -29.63% (bound +/-15%), resolution 0.2309 to 0.2347% of target per
step (bound 0.25%), worst deviation from exact binary weights 0.2937%, monotonic
in 15/15. "1-point @ 27 C only, magnitude only" is a structural statement,
and nothing in the design adds a second knob (`0013`, `0014`: both `proposed`).
It is not a measured quantity. The row is on the current netlist but, like the
trimmed line, schematic-only.

### Temp coefficient

Target met on the current DUT by both methods. Box method (the method the
two-key review asked for), 8-temperature grid, code 128: 15 groups, 20.2 to
38.6 ppm/C, worst bcs/3.63 V; the +/-1-code band the real trim lands in
(codes 127 to 129, 45 groups): 15.5 to 45.7 ppm/C, 45/45 under 50 and 3/45
under 20 (all three are code 129 at wcs, which is not the default). **The
stretch (< 20 ppm/C) is not met on the trim-bearing core**: at the default
code 0 of 15 groups clear it. Disclosure: 20 of the 45 near-band groups lost
one or two grid points (mostly the 100 C point) to non-convergence, and the worst
number, 45.7 ppm/C (bcs/3.63 V, code 127), is a complete 8/8 group. The
pre-trim records (box 19.8 ppm/C schematic and 20.1 ppm/C PEX worst; endpoint
-17.6 to 15.5 ppm/C PEX) and the aids-free A/B belong to the superseded core
and are history, not current numbers.

### PSRR @ DC

On the post-layout, trim-bearing DUT 45/45 points clear 60 dB, at **60.001 dB
for the worst point** (0.0013 dB margin; next-worst 60.336 dB). It is a
corner-swept row; the margin is a small fraction of any plausible model
error, and the schematic is below 60 dB at the same corner (59.685 dB). It should not be
read as comfortable. The stretch (> 70 dB) is not met (10/45 above 70 dB).
`0006` documents the narrowband above-DC transmission zero; no above-DC bound
exists in the spec (the PEX record's `psrr_min_db` is 5.69 to 6.59 dB at the
HF notch, outside this row).

### Supply

Not a simulated quantity. The record argument is `0002`; the current records
sweep exactly the 2.97/3.30/3.63 V grid the row specifies.

### Iq

Schematic only, current. 19.58 to 41.78 uA across 45 points; the 20 uA
stretch is touched only at 2 points. No post-layout Iq bench exists; Iq is a
DC bias quantity, but that is a judgment, not evidence.

### Startup

Self-start 45/45 and time-to-release at the first 100 us checkpoint on all 45
points, schematic, current. The post-layout evidence is the startup cell's
trip point (45/45, 2026-09-05), which exercises the extracted
`bandgap_startup` layout; it has not been re-run against the trim-bearing
assembly, and there is no post-layout time-to-release.

## Supplementary current evidence not tied to a spec row

- Loop stability on the current DUT: `sim/loop-gain-phase-margin/records/
  20261003-180919-2addad0.csv`, the solve-quality-guarded grid from #289 (45/45
  `quality=ok`; minimum phase margin 83.5 deg across the 45 rows). Not a spec
  row.
- Output impedance, post-layout: `sim/closed-loop-zout-pex/records/
  20261004-030338-5553d523.csv`. Not a spec row; not quoted further here.

## Gaps this report does not close

- #303 (open): redesign against mismatch and re-aim of the trim for the
  trimmed line; one-point trim only.
- #273 (open): the untrimmed MC and the schematic box-TC grid re-runs on the
  trim-bearing core. The two PEX re-runs still waived under #275 have no
  open tracker.
- No post-layout Iq, trim-domain or trim-coverage evidence; no post-layout
  time-to-release.
- If #303 changes the DUT before this report is merged or later, every row
  marked "Current" must be rechecked; the netlist-snapshot check will flag the
  ones that go stale.

## Reproducing the spot-check

```sh
python3 -I measurements/2026-10-characterization-report/spotcheck.py
```

It reads only the committed CSVs under `sim/` and prints one line per quoted
figure. Output at the audited commit `b89f4c5f`:

```text
vref-pvt sch trim-bearing: 45/45 PASS; vref 1.04060..1.05052 V; vs 1.050 V: -0.90%..+0.05%; nominal typ/27C/3.30V 1.04728 V (-0.259%); max settle delta 0 V
vref-pvt sch trim-bearing endpoint TC: 15 groups; -37.3..-14.1 ppm/C; max |TC| 37.3; groups < 50: 15; groups < 20: 3
psrr-pex vref_op (PEX trim-bearing, 27C/DC op only): 45/45 PASS; vref_op 1.03894..1.04950 V
PSRR@DC PEX trim-bearing: 60.001..99.507 dB; >60 dB: 45/45; >70 dB: 10/45; worst 60.0013 dB at bcs/125C/3.63V
PSRR@DC PEX trim-bearing, 2nd/3rd worst: 60.336, 60.502 dB
PSRR above-DC min (PEX trim-bearing): psrr_min_db 5.69..6.59 dB (HF notch, not the DC row)
PSRR@DC sch trim-bearing: 59.685..100.400 dB; >60 dB: 44/45; >70 dB: 10/45; worst 59.6849 dB at bcs/125C/3.63V
Supply grid actually swept by the current records: ['2.97', '3.30', '3.63']
Iq sch trim-bearing: 45/45 PASS; 19.58..41.78 uA; <50 uA: 45/45; <20 uA: 2/45; worst bcs/125C/3.63V; margin to 50 uA 16.4%; max settle delta 0 A
startup sch trim-bearing: 45/45 PASS
startup time-to-release sch trim-bearing: 45/45 PASS; release_time_us values ['100']; max 100 us (ladder step 100 us)
startup trip point PEX (2026-09-05): 45/45 PASS
trim-coverage: 15/15 groups PASS; range up +29.22..+29.72%, down -29.63..-30.12% (worst-case +29.22/-29.63); LSB 0.2309..0.2347 %/step; worst binary-weight deviation 0.2937%; monotonic in 15/15
trim-coverage points: 169/169 PASS
trim-MC nominal: N=300 draws, 299 converged (1 excluded); within +/-0.5% over -40..125C: 29.8%; 3*sigma(max_dev) 2.601%; worst draw 6.72%; seeds 20260930..20261229
trim-MC bcs: N=300 draws, 242 converged (58 excluded); within +/-0.5% over -40..125C: 28.5%; 3*sigma(max_dev) 2.523%; worst draw 6.79%; seeds 20260930..20261229
trim-MC wcs: N=300 draws, 293 converged (7 excluded); within +/-0.5% over -40..125C: 31.7%; 3*sigma(max_dev) 2.592%; worst draw 6.79%; seeds 20260930..20261229
trim-MC negctrl: N=300 draws, 300 converged (0 excluded); within +/-0.5% over -40..125C: 100.0%; 3*sigma(max_dev) 0.000%; worst draw 0.43%; seeds 20260930..20261229
trim-MC digest typ_mismatch: status FAIL, n_pass 299/300, frac_within_0p5 29.77%, 3sigma 2.601%
trim-MC digest typ_negctrl: status PASS, n_pass 300/300, frac_within_0p5 100.00%, 3sigma 0.000%
trim-MC digest bcs_mismatch: status FAIL, n_pass 242/300, frac_within_0p5 28.51%, 3sigma 2.523%
trim-MC digest wcs_mismatch: status FAIL, n_pass 293/300, frac_within_0p5 31.74%, 3sigma 2.592%
trim-MC nominal at the 27C trim point: max |dev_27c| 0.246%; draws with |dev_27c|<=0.5%: 299/299
box TC trim-bearing, code 128: 15 groups; 20.2..38.6 ppm/C; < 20: 0; < 50: 15
box TC trim-bearing, code 128 worst: bcs_code128/3.63V 38.610
box TC trim-bearing, codes 127..129: 45 groups; 15.5..45.7 ppm/C; < 50: 45/45; < 20: 3/45
box TC trim-bearing worst near-band: bcs_code127/3.63V 45.695 (n_pass 8/8)
box TC groups with excluded points: 20 of 45 near-band groups have n_pass<n_grid (fs_code127/2.97V:7/8, fs_code127/3.30V:6/8, fs_code127/3.63V:7/8, fs_code128/2.97V:7/8, fs_code128/3.30V:7/8, fs_code129/2.97V:7/8, fs_code129/3.30V:7/8, fs_code129/3.63V:7/8, sf_code127/2.97V:7/8, sf_code127/3.30V:7/8, sf_code128/2.97V:7/8, sf_code128/3.30V:7/8, sf_code128/3.63V:7/8, sf_code129/2.97V:7/8, sf_code129/3.63V:7/8, typ_code128/2.97V:7/8, typ_code128/3.30V:7/8, typ_code128/3.63V:7/8, typ_code129/2.97V:7/8, typ_code129/3.30V:7/8)
box TC complete groups only: 25 groups; max 45.695
PEX pre-trim endpoint TC (STALE): -17.6..15.5 ppm/C over 15 groups
sch pre-trim box TC (STALE): 15 groups; max 19.8 ppm/C at wcs/3.30V (n_pass 8/8)
PEX pre-trim box TC (STALE): 15 groups; max 20.1 ppm/C at bcs/3.63V (n_pass 8/8)
pre-trim aids-free A/B: 4 groups; header ['corner_label', 'vdd_v', 'n_pass', 'n_grid', 'vmin_v', 'vmin_temp_c']
    {'corner_label': 'bcs_aided', 'vdd_v': '3.63', 'n_pass': '2', 'n_grid': '2', 'vmin_v': '1.0433', 'vmin_temp_c': '125', 'vmax_v': '1.0464', 'vmax_temp_c': '0', 'vref_27c_v': '', 'box_tc_ppm_per_c': ''}
    {'corner_label': 'bcs_aidsfree', 'vdd_v': '3.63', 'n_pass': '8', 'n_grid': '8', 'vmin_v': '1.0411', 'vmin_temp_c': '125', 'vmax_v': '1.0443', 'vmax_temp_c': '0', 'vref_27c_v': '1.0442', 'box_tc_ppm_per_c': '18.515'}
    {'corner_label': 'typ_aided', 'vdd_v': '3.63', 'n_pass': '1', 'n_grid': '1', 'vmin_v': '1.048', 'vmin_temp_c': '125', 'vmax_v': '1.048', 'vmax_temp_c': '125', 'vref_27c_v': '', 'box_tc_ppm_per_c': ''}
    {'corner_label': 'typ_aidsfree', 'vdd_v': '3.63', 'n_pass': '8', 'n_grid': '8', 'vmin_v': '1.0456', 'vmin_temp_c': '125', 'vmax_v': '1.0474', 'vmax_temp_c': '27', 'vref_27c_v': '1.0474', 'box_tc_ppm_per_c': '10.705'}
untrimmed MC digest typ_mismatch (STALE): 27C n_pass 300/300, mean 1.046711 V, 3sigma/mean 13.04%, within 1%: 20.7%, within 0.5%: 10.3%
untrimmed MC digest typ_negctrl (STALE): 27C n_pass 300/300, mean 1.047339 V, 3sigma/mean 0.00%, within 1%: 100.0%, within 0.5%: 100.0%
untrimmed MC digest bcs_mismatch (STALE): -40C n_pass 300/300, mean 1.042605 V, 3sigma/mean 12.20%, within 1%: 21.0%, within 0.5%: 10.3%
untrimmed MC digest bcs_mismatch (STALE): 125C n_pass 300/300, mean 1.041041 V, 3sigma/mean 14.60%, within 1%: 17.7%, within 0.5%: 9.7%
untrimmed MC digest wcs_mismatch (STALE): -40C n_pass 300/300, mean 1.048912 V, 3sigma/mean 12.09%, within 1%: 20.0%, within 0.5%: 11.0%
untrimmed MC digest wcs_mismatch (STALE): 125C n_pass 300/300, mean 1.052766 V, 3sigma/mean 14.34%, within 1%: 17.3%, within 0.5%: 10.0%
untrimmed MC nominal recomputed from draws (STALE): N=300 mean 1.046711 sigma 0.045486 3sigma/mean 13.04%
untrimmed worst-case 3sigma total vs 1.050 V (STALE; DR-0011's 15.3% sum): 15.32% vs the +/-16% line
untrimmed MC +/-16% band around 1.050 V (STALE): draws inside [0.882, 1.218] V: 300/300
PEX pre-trim vref grid (STALE): 45 PASS; 1.04309..1.05667 V; nominal 1.05048 V
loop-gain (supplementary, not a spec row): 45/45 PASS, 45 quality=ok rows
loop-gain phase margin: 45 rows with a crossover; min 83.5 deg
```

Two conventions to read the output by: "3 sigma of worst-case deviation" is
`3 * stdev` of each converged draw's `max_dev_pct` (the maximum absolute
deviation from 1.050 V over -40/27/125 C), the same definition the record's own
digest uses (reproduced exactly: 2.601233 for the nominal point); and the
box-method TC is `(vmax-vmin)/(vref(27C) * 165 C)`, taken from the record's
`box_tc_ppm_per_c` column.

## Binding

[`envelope.json`](envelope.json) is a `generic` envelope for T1 item 8. It
pins the sha256 of **this file** (not of the envelope) in its
`provenance.input`, and `manifests/sg13g2-bandgap.json` pins the same hash.
Editing this file without regenerating both makes
`.github/scripts/check_signoff_manifest.py` fail. Companion files
(`spotcheck.py`) are not hashed.
