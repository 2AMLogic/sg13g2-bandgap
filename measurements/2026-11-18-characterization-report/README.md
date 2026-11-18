# Aggregated characterization report, November 2026 (18 Nov) (T1 item 8, the `Characterization report` row)

Audited commit: **`11a18b96`** (the `feature/issue-557` head that re-mints
the layout evidence and both audited PEX DUT inputs; this report is
committed on the same branch, issue #557). Supersedes
[`../2026-11-16-characterization-report/`](../2026-11-16-characterization-report/README.md)
(audited at `00acddae`; left untouched as history), which superseded
[`../2026-11-13-characterization-report/`](../2026-11-13-characterization-report/README.md)
(audited at `9d568b91`), which superseded
[`../2026-11-04-characterization-report/`](../2026-11-04-characterization-report/README.md)
(audited at `2a0f04d7`), which superseded
`../2026-11-characterization-report/` (`03e62489`),
`../2026-10-characterization-report/` and `../2026-09-characterization-report/`.
The only evidence that moved since the 16 Nov report is the layout re-mint
of the #557 Via1 containment fix (see "What moved since the 16 Nov report"
below); no `sim/` record moved. Like the 16 Nov rotation this one is **not**
provenance-only: the DUT behind the three post-layout benches' newest
records changed (the layout they were extracted from was re-extracted), so
the PSRR @ DC row's verdict moves with it — met with caveats becomes **not
met on current evidence** — while every quoted number is unchanged, no
simulation was run, and the schematic DUT netlists, the spec table and
every selected record are unchanged.

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
- **It does not claim every row passes.** Two lines fail on the current
  evidence and are reported as such: the trimmed line (measured, UNMET) and
  PSRR @ DC (whose only passing record predates the current extraction);
  several more are caveated-met. A `met` on T1 item 8 means
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

## What moved since the 16 Nov report

No simulation was run and no `sim/` record moved. What moved is the layout
evidence: issue #557 (this branch) completed the #556 Via1 containment fix
across the remaining cells — `bandgap_core` and `bandgap_top` now draw
0.19 um Via1 cuts and cap every via-bearing Metal2 route end, driving the
deck's `metal2.enclosing.via1.1` and `via1.width.1` classes to **0 on every
cell** (core 9 + 17 markers before, top's own shapes 30 + 31 before;
`bandgap_startup` draws no Via1 at all and its layout is byte-identical;
`bandgap_amp` was fixed by #556). The GDS, the per-cell DRC/LVS/PEX
reports, top's curated + runset LVS, ERC and the new `drc_waivers.json`
(assembled top verdict `clean` with 33 waived cell-scoped markers →
#571/#572/#573) were re-minted per the `layout/README.md` recipe under
`klt 0.9.3.dev663` / klayout 0.30.12 — the build whose deck carries the
containment rules.

The two extracted DUT inputs this report audits moved with it:
`layout/bandgap_top/bandgap_top.pex.spice` (a real geometry change — the
Via1 end caps and the 0.19 um cuts are in the extracted metal stack) and
`layout/bandgap_startup/bandgap_startup.pex.spice` (layout byte-identical;
the re-mint under the current deck emits `rhigh` as a subcircuit with
explicit L/W and adds a `.GLOBAL vsubs` substrate tie).
`layout/bandgap_core/bandgap_core.pex.spice` was re-minted too but is not
a `dut[]` entry of this inventory. The one-point core PEX probe
(`layout/README.md` "Trim ladder layout"; explicitly not a committed
`sim/` record) was re-run on the refreshed core extraction and reproduces
its recorded point exactly (`vref` 1.052999 V, ladder/base ratio 12.630) —
the answer-preserving evidence that the re-mint did not move the core's
DC operating point.

No PEX grid was re-run. The three post-layout benches whose DUT is the old
extraction — `sim/closed-loop-psrr-pex` and `sim/closed-loop-zout-pex`
(top extraction) and `sim/startup-trip-point-pex` (startup extraction) —
are therefore disclosed below as **stale**: their records are history, not
current claims. The consequence for the verdict table is spelled out at
the PSRR row: the only record that cleared the 60 dB bound (post-layout,
45/45, margin 0.0013 dB) predates the current extraction, and the current
schematic grid reads 59.685 dB at its worst corner, below the bound. No
bound is relaxed and no number is re-cooked; the schematic half of every
one of those benches' DUT sets is unchanged (`design/netlist/` is
untouched by this branch).

## What moved since the 13 Nov report

One record was minted on the Spot batch fleet (`klt sim`, issue #402):
`sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c`, the
schematic box-method TC grid, now on the **trim-bearing** core at code 128.
The 13 Nov report cited the experiment's pre-trim 2026-09-21 record
(`20260921-194249-77820fc`, waived under #273); the new record runs the same
120-point PVT grid (5 corners x 8 temperatures x 3 supplies) through the
co-simulated closed-loop schematic with the trim-bearing core, aids-free
(`rshunt`/`gmin` dropped) plus the bench's measured answer-preserving KLU
direct linear solver (#469). The DUT swap is exactly the one every #264
refresh adopted; the testbench is unchanged.

**What changed is the DUT, and the TC numbers move with it — read as the
trim-bearing aids-free DUT's own numbers, with the disposition attached
elsewhere.** The pre-trim record stays as history (append-only `sim/`
evidence); its #273 waiver is deleted from
[`sim/evidence-freshness-waivers.json`](../../sim/evidence-freshness-waivers.json)
because the refresh that waiver existed for is now delivered.

| closed-loop-vref-pvt-boxtc | pre-trim (`20260921-194249-77820fc`) | trim-bearing, code 128, aids-free + KLU (`20261116-024010-dc056b4c`) |
|---|---|---|
| `vref_3ms_v` @ `typ`/27 °C/3.30 V | 1.04947 V | **1.04728 V** (−2.19 mV, −0.21%) |
| Box TC, worst group | `wcs`/3.30 V = 19.77 ppm/°C | **`bcs`/3.63 V = 38.62 ppm/°C** |
| Box TC, 15-group range | 8.90–19.77 ppm/°C | 20.20–38.62 ppm/°C |
| Endpoint TC, 15-group range | −14.4 … +18.1 ppm/°C | **−37.3 … −14.1 ppm/°C** |
| Box extrema positions | `vmin` @ 125 °C in 14/15 groups (`wcs` at −40 °C), `vmax` @ 0–75 °C | `vmin` @ 125 °C in all 15 groups; `vmax` @ 0 °C (`typ`/`sf`/`fs`), −20 °C (`bcs`), 27 °C (`wcs`) |
| Points PASS | 120/120 | 120/120 |

The −2.19 mV nominal move is the same delta, to the digit, that the #264
twin measured on the identical DUT swap, and the new grid's `vref` range
endpoints (1.04060 to 1.05052 V) and nominal (1.04728 V) agree with the
`sim/closed-loop-vref-pvt` trim-bearing grid to all five quoted decimals.
The endpoint range −37.3 … −14.1 ppm/°C is that twin's endpoint range
repeated — two separately-written benches agreeing — and the 20.20–38.62
ppm/°C box range sits inside
[`sim/closed-loop-vref-boxtc-trim`](../../sim/closed-loop-vref-boxtc-trim/README.md)'s
independent 20.2–45.7 ppm/°C ±1-code box-method band for the same core. The
ratified `< 20 ppm/°C` stretch is not met by the box method on this DUT
(0 of 15 groups below 20); that disposition is **#269's** — the ratified
box-TC row's evidence lives in `sim/closed-loop-vref-boxtc-trim` — and
nothing in `spec/` is edited. The **Temp coefficient verdict below is
unchanged**: target met, stretch not met, exactly as the 13 Nov report read
it from the trim evidence.

The run was dispatched to the AWS Spot batch fleet as one
`klt sim --batch-set` (the committed concurrent submit path, in-flight 2 x 3
shard jobs), which ran **120 spot fleet jobs** (`provider: aws-batch-fleet`,
c7i/m7i/m6i.4xlarge, all `state: done`, `exit_code: 0`) to completion in a
62-minute wall clock, individual jobs 79–120 s — including every 100 °C
point, the corner that sank the pre-KLU attempt at 3643 s. The submitting
client was `klt 0.9.3.dev16+gdcf18e2e0c03` and the runners `klt 0.9.0`, with
`runner_compatibility: match` and the corner model library matched by
content hash (`models_lib_comparison: match`); the job ids are in the
record's `environment.remote`. The runner's ngspice is 47, compiled with the
KLU direct linear solver, and the run's disclosed evidence for solver
engagement is that all **120/120** harvested corner logs carry ngspice's
`Using KLU as Direct Linear Solver` line (a strictly stronger check on this
question than the runner's `--fail-fast-probe`, which is a `local`/
`local-parallel`-only flag and does not run for a batch dispatch — hence it
is disclosed rather than claimed). **No live re-verification of the fleet
run was performed for this report** — as with every earlier batch-minted
record, the fleet evidence is read from the committed record.

## What moved between the 4 Nov and the 13 Nov report

One record was re-minted on the Spot batch fleet (`klt sim`, issue #415):
`sim/closed-loop-psrr/records/20261113-085406-9d568b91`, the schematic
PSRR @ DC grid. The 4 Nov report cited
`20261001-085737-e5507b2`, produced by the experiment's legacy local
`run_pvt_sweep.sh` shell loop; the new record runs the same 45-point PVT grid
(5 corners x 3 temperatures x 3 supplies) through the `klt sim` corner matrix
dispatched off-host, which is what issue #415 set out to deliver. The DUT, the
testbench and the spec row are untouched.

**What changed is provenance, not results.** The new grid reproduces the
record it replaces figure-for-figure: same 45/45 PASS, same
59.685..100.400 dB range, same worst point 59.6849 dB at bcs / 125 C /
3.63 V, agreeing to within 6e-6 relative on every PSRR column
(`psrr_dc_db`, `psrr_1khz_db`, `psrr_100khz_db`, `psrr_1mhz_db`,
`psrr_min_db`). Accordingly the PSRR @ DC verdict, its bound, its binding
corner and every number quoted for it below are **unchanged**.

The run was dispatched to the AWS Spot batch fleet as 15 `klt sim` jobs
(`provider: aws-batch-fleet`, 3 grid points each, all `state: done`,
`exit_code: 0`); the job ids are in the record's `environment.remote`.
**No live re-verification of the fleet run was performed for this
report.**

## What moved between the earlier November and the 4 Nov report

One record was re-minted on the Spot batch fleet (`klt sim`, issue #403):
`sim/closed-loop-vref-mc/records/20261104-201955-2a0f04d7`, the untrimmed
±16% line's mismatch MC, now on the trim-bearing core at code 128 instead of
the pre-trim core. Its waiver (#273, the untrimmed-MC half) is deleted from
`sim/evidence-freshness-waivers.json`.

| Untrimmed MC point (N=300) | Earlier (pre-trim, 2026-09-09) 3 sigma/mean | Now (trim-bearing, 2026-11-04) 3 sigma/mean |
|---|---|---|
| typ mismatch, 27 C | 13.04% | 13.54% |
| bcs, -40 C / 125 C | 12.20% / 14.60% | 12.77% / 15.08% |
| wcs, -40 C / 125 C | 12.09% / 14.34% | 12.54% / 14.80% |
| Worst-case total vs 1.050 V (3 sigma + mean offset) | 15.32% (bcs/125 C) | 15.31% (wcs/125 C) |

The line is still inside ±16% by a margin of 0.69 points. The binding corner
moved from bcs/125 C to wcs/125 C because the trim-bearing core's mean shifted
up (wcs/125 C mean 1.054700 V). **Draw-for-draw parity with the earlier record
is not established**: the fleet decks reuse the same seeds
(`20260909 + draw_index`) but the DUT and runner differ, so the two
populations are comparable, not identical. The negative control (no mismatch)
reads 1.047278 V at all 300 draws, equal to `sim/trim-coverage`'s code-128
point. The fleet job ids are in the record's `environment.remote`; no live
re-verification of the fleet run was performed for this report.

## What moved between October and the earlier November report

Two records were re-minted on the Spot batch fleet (`klt sim`, `klt 0.8.0`,
fleet job ids in each record's `environment.remote`; issue #427, following
#422/#425) and are the only evidence that changed:

| Line | October (`b89f4c5f`) | November (`03e62489`) |
|---|---|---|
| Trim range / resolution (`sim/trim-coverage`) | 169/169 PASS; +29.22 / -29.63% worst; 0.2347%/step | **Unchanged**: 169/169 PASS, identical figures (deterministic sweep) |
| Trimmed ±0.5%, typ 3 sigma / inside ±0.5% | 2.601% / 29.8% | 2.399% / 24.7% |
| Trimmed ±0.5%, bcs 3 sigma / inside | 2.523% / 28.5% (58 excluded) | 2.413% / 25.0% (0 excluded) |
| Trimmed ±0.5%, wcs 3 sigma / inside | 2.592% / 31.7% (7 excluded) | 2.390% / 27.0% (0 excluded) |

The trim-MC mismatch draw comes from the host's RNG, so the fleet nominal
population is different from, but comparable to, October's (the negative
control, which has no mismatch, is identical). The trimmed line is still
**UNMET**: the verdict wording is unchanged, no spec row was touched, and the
lower 3 sigma does not bring it near the 0.5% claim.

## The design under test and how freshness was established

The current committed DUT is the **trim-bearing** core: `design/netlist/
bandgap_core.spice` and `bandgap_trim.spice` at `9530863` (2026-09-30, the
255-unit R1 trim ladder, #229), `bandgap_amp.spice` at `397fe2d`,
`bandgap_startup.spice` at `66ac99d`; `git log -- design/netlist` shows
nothing newer. The post-layout DUT is the re-extraction minted by this branch (issue
#557, `klt 0.9.3.dev663`): `layout/bandgap_top/bandgap_top.pex.spice` and
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

This rotation adds a second, **unwaived** staleness class of its own: the
three post-layout benches taken on the pre-#557 extraction, disclosed in
the table below rather than waived — a disclosure is this report's own
honest mark, and no tracker waiver exists for them:

| Stale record (pre-#557 extraction) | Bench |
|---|---|
| `sim/closed-loop-psrr-pex/records/20261004-030337-5553d523.md` (45-point PSRR grid) | the post-layout PSRR grid predates the current extraction |
| `sim/closed-loop-zout-pex/records/20261004-030338-5553d523.md` | the post-layout Zout record predates the current extraction |
| `sim/startup-trip-point-pex/records/20260905-033740-fe97115.md` | the startup trip-point PEX record predates the current extraction |

Wherever a row below leans on a stale record, it says **"evidence predates
the current netlist"** (the waived class) or names the pre-#557 extraction
(this rotation's class) and does not quote the number as current.

Other disclosures that apply to several rows:

- **Schematic vs post-layout (PEX).** The trim-bearing schematic grids
  cover vref, TC (endpoint and both box-method grids), Iq and startup
  (2026-10-01 and 2026-11-16) plus PSRR (2026-11-13, re-minted on the batch
  fleet by #415; the 2026-10-01 local sweep it replaces reproduces
  figure-for-figure). The trim-bearing **PEX** evidence is narrower and,
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
commit — for post-layout rows, on the extraction minted by this branch
(the #557 re-extraction).

| Row (bound; governing record) | Verdict | Binding corner | Statistical? | Newest committed record(s) behind it | Fresh? |
|---|---|---|---|---|---|
| **Output reference, nominal**: 1.050 V (`0011`, proposed) | **Met with caveats**: 1.04060 to 1.05052 V over the 45-point grid; nominal 1.04728 V (-0.26%); schematic only. The 120-point box-TC grid (2026-11-16) reads the same range endpoints and the same nominal, a second bench agreeing | bcs/125 C/2.97 V (low), wcs/27 C/3.63 V (high) | No, corner-swept | `sim/closed-loop-vref-pvt/records/20261001-085908-e5507b2.csv` (2026-10-01); corroborated by `sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c.csv` (2026-11-16) | **Current** (schematic). PEX history only: the PEX vref grid predates the current netlist, and the PSRR-PEX record's DC-op `vref_op` (1.03894 to 1.04950 V) predates the current extraction |
| **Output reference, untrimmed line**: ±16% (3 sigma, mismatch MC + PVT) (`0011`) | **Met with caveats**: worst-case 3 sigma total 15.31% against the 16% line (0.69 points of margin) | wcs/125 C (3 sigma/mean 14.80%, mean 1.054700 V) | **Yes**: N=300, seeded | `sim/closed-loop-vref-mc/records/20261104-201955-2a0f04d7.{md,csv}` + `-draws.csv` (2026-11-04) | **Current** (schematic, trim-bearing core at code 128). Draw-for-draw parity with the 2026-09-09 pre-trim record is unestablished. No PEX mismatch MC |
| **Output reference, trimmed line**: ±0.5% trimmed, 1-point @ 27 C (`0011`) | **UNMET (measured)**: 3 sigma of worst-case deviation over -40 to 125 C is **2.40%** (nominal point); only 24.7% of dies inside ±0.5%. The disposition (redesign, #303) is **unsettled**; the bound is not relaxed | no single corner: 2.40 / 2.41 / 2.39% (typ / bcs / wcs, all at 3.30 V) | **Yes**: N=300 per point, seeded, with negative control | `sim/closed-loop-vref-trim-mc/records/20261030-070305-03e62489.{md,csv}` + `-draws.csv` (2026-10-30) | **Current** (schematic, trim-bearing). No PEX trim-domain MC |
| **Trim**: 1-point @ 27 C only, no hot insertion, no CTAT knob (`0014`, proposed); range >= ±15%; resolution <= 0.25%/step; magnitude only | **Met** (range, resolution); 1-point-only holds by construction (no second knob, `0013`/`0014`) | Range worst: +29.22 / -29.63% (both wcs / 2.97 V); resolution worst 0.2347%/step (bcs 3.30/3.63 V) | No: 15 corner/supply groups, deterministic | `sim/trim-coverage/records/20261030-061206-03e62489.{md,csv}` + `-analysis.csv` (2026-10-30) | **Current** (schematic). No PEX trim sweep. `0014` is `proposed` and #303 may change the DUT |
| **Temp coefficient** (-40 to 125 C): < 50 ppm/C; stretch < 20 | **Target met; stretch not met.** Box method, default code 128: two independent trim-bearing grids agree — `closed-loop-vref-boxtc-trim` 20.2 to 38.6 ppm/C and the 120-point grid 20.20 to 38.62 ppm/C (0 of 15 groups below 20, worst `bcs`/3.63 V in both); ±1-code band worst **45.7 ppm/C** (inside 50 by 8.6%). Endpoint method: -37.3 to -14.1 ppm/C | bcs / 3.63 V (box, both grids; code 127: 45.7); endpoint worst bcs / 3.63 V | No, corner-swept | `sim/closed-loop-vref-boxtc-trim/records/20261001-043806-729d889-boxtc.csv` (box, ratified row); `sim/closed-loop-vref-pvt-boxtc/records/20261116-024010-dc056b4c-boxtc.csv` (box, 120-point); `sim/closed-loop-vref-pvt/records/20261001-085908-e5507b2-tc.csv` (endpoint) | **Current** (schematic: all three trim-bearing). The PEX and pre-trim box-method records (20.1 / 19.8 ppm/C worst) **predate the current netlist** |
| **PSRR @ DC**: > 60 dB; stretch > 70 | **Not met on current evidence; stretch not met.** The only current record is schematic: 59.685 to 100.400 dB, **44/45 above 60 dB** — the worst corner reads 59.685 dB, below the bound. The post-layout grid that met it (60.001 to 99.507 dB, 45/45, margin 0.0013 dB; 10/45 above 70) predates the current extraction and is history, not a current claim | bcs / 125 C / 3.63 V | No, corner-swept | `sim/closed-loop-psrr/records/20261113-085406-9d568b91.csv` (current); `sim/closed-loop-psrr-pex/records/20261004-030337-5553d523.csv` (history) | **Current** (schematic). The post-layout PSRR grid predates the current extraction |
| **Supply**: 3.3 V ±10% (HV); stretch 1.2 V (LV) | **Met by construction** (rating argument, `0002` ratified); every current record sweeps 2.97/3.30/3.63 V. The 1.2 V stretch is a flavor statement, not measured | n/a | No | `spec/decision-records/0002-supply-voltage-scope.md` + `vdd_v` column of the records above | Current (grid); the argument itself is not simulated |
| **Iq**: < 50 uA; stretch < 20 | **Met with caveats; stretch not met.** 19.58 to 41.78 uA, 45/45 under 50 (margin 16.4%); 2/45 under 20 uA. Pre-layout only | bcs / 125 C / 3.63 V | No, corner-swept | `sim/closed-loop-iq/records/20261001-092257-4fe07ea.csv` | **Current** (schematic). No PEX Iq bench exists |
| **Startup**: self-starting, < 1 ms | **Met**: 45/45 self-start; every point released by the first 100 us checkpoint (~10x inside 1 ms; resolution 100 us). Post-layout: startup-cell trip point 45/45 | all points identical at the checkpoint resolution | No: pass counts | `sim/closed-loop-startup/records/20261001-083332-e5507b2.csv`; `sim/startup-time-to-release/records/20261001-085905-e5507b2.csv`; `sim/startup-trip-point-pex/records/20260905-033740-fe97115.csv` | **Current** (schematic). The startup trip-point PEX record predates the current extraction: the `bandgap_startup` layout it names is byte-identical, but the re-minted extraction (subcircuit `rhigh`, substrate tie) is the DUT now committed. No PEX time-to-release |

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

**Untrimmed ±16% line.** `0011` derives the line as the worst MC corner's
3 sigma/mean plus its mean offset (14.60% + 0.85% = about 15.3%, rounded up,
from the earlier pre-trim record). The spot check recomputes that sum from the
current record's own digest as 15.31% (wcs/125 C: 14.80% scaled to 1.050 V plus
a 0.45% mean offset). The MC: seed `20260909 + draw_index`, N=300 per point, nominal point plus
bcs/wcs at -40 and 125 C (3.30 V), 6 points, all 300 draws converged at every
point, deterministic negative control with exactly zero spread (1.047278 V at
all 300 draws). All 300 nominal draws sit inside 1.050 V ±16%. **This record
was re-minted on the trim-bearing core (issue #403, `klt sim` on the batch
fleet, 1800 draws in 18 jobs) and is current**; it replaces the pre-trim
2026-09-09 record, which is kept as history. The margin to the line is thin
(0.69 points), the evidence is schematic only, and draw-for-draw parity with
the earlier record is not established (see "What moved between the earlier
November and the 4 Nov report" above).

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
grid (2026-11-13): 59.685 to 100.400 dB, 44/45 above 60 dB, worst 59.685 dB
at bcs/125 C/3.63 V — below the bound. The record that met the row was the
post-layout, trim-bearing grid (2026-10-04): 45/45 points above 60 dB at
**60.001 dB for the worst point** (0.0013 dB margin; next-worst 60.336 dB),
10/45 above the 70 dB stretch. The post-layout PSRR grid predates the
current extraction — it was extracted from the pre-#557 layout, whose
Via1 landings this branch has since re-drawn and re-extracted — so its
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
stretch is touched only at 2 points. No post-layout Iq bench exists; Iq is a
DC bias quantity, but that is a judgment, not evidence.

### Startup

Self-start 45/45 and time-to-release at the first 100 us checkpoint on all 45
points, schematic, current. The post-layout evidence is the startup cell's
trip point (45/45, 2026-09-05), which exercises the extracted
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
- The three post-layout benches newly disclosed as stale (PSRR-PEX,
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
python3 -I measurements/2026-11-18-characterization-report/spotcheck.py
```

It reads only the committed CSVs under `sim/` and prints one line per quoted
figure. No `sim/` CSV moved since the 16 Nov report, so the output is
byte-identical to that report's block. Output at the audited commit
`11a18b96`:

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
untrimmed MC digest typ_mismatch: 27C n_pass 300/300, mean 1.054644 V, 3sigma/mean 13.54%, within 1%: 15.3%, within 0.5%: 7.0%
untrimmed MC digest typ_negctrl: 27C n_pass 300/300, mean 1.047278 V, 3sigma/mean 0.00%, within 1%: 100.0%, within 0.5%: 100.0%
untrimmed MC digest bcs_mismatch: -40C n_pass 300/300, mean 1.053879 V, 3sigma/mean 12.77%, within 1%: 18.3%, within 0.5%: 8.0%
untrimmed MC digest bcs_mismatch: 125C n_pass 300/300, mean 1.048679 V, 3sigma/mean 15.08%, within 1%: 14.7%, within 0.5%: 8.7%
untrimmed MC digest wcs_mismatch: -40C n_pass 300/300, mean 1.056207 V, 3sigma/mean 12.54%, within 1%: 17.7%, within 0.5%: 9.0%
untrimmed MC digest wcs_mismatch: 125C n_pass 300/300, mean 1.054700 V, 3sigma/mean 14.80%, within 1%: 14.3%, within 0.5%: 7.7%
untrimmed MC nominal recomputed from draws: N=300 mean 1.054644 sigma 0.047611 3sigma/mean 13.54%
untrimmed worst-case 3sigma total vs 1.050 V (DR-0011's 15.3% sum, recomputed): 15.31% vs the +/-16% line
untrimmed MC +/-16% band around 1.050 V: draws inside [0.882, 1.218] V: 300/300
PEX pre-trim vref grid (STALE): 45 PASS; 1.04309..1.05667 V; nominal 1.05048 V
loop-gain (supplementary, not a spec row): 45/45 PASS, 45 quality=ok rows
loop-gain phase margin: 45 rows with a crossover; min 83.5 deg
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
