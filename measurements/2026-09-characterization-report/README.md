# Aggregated characterization report (T1 item 8 — the `Characterization report` gap)

The single, current, aggregated per-spec-row characterization artifact for
this block. Issue #5's closing verdict table (2026-08-16) marked item 8
**FAIL** — "`measurements/README.md`@d9cebd5: placeholder. No aggregated
characterization artifact exists." This directory is that artifact: one
verdict per ratified spec row, each verdict citing the specific committed
evidence record behind it.

It lives in `measurements/` (not `sim/`) because it is exactly what
[`measurements/README.md`](../README.md) scopes this directory to: a
multi-run comparison synthesizing across `sim/`'s per-experiment append-only
records, not a new experiment. Every number below is drawn from
already-committed evidence — nothing was re-simulated for this report.

## What this claims, and what it does not

**It claims**: for each of the six rows of the ratified target-spec table,
an honest verdict — met / met-with-caveats / unmet — against the currently
committed evidence, with the evidence record, corner, and date named for
every verdict. Every citation below was re-verified against `main` at
`77820fc` (2026-09-21): all nine cited records exist, and no record
committed after the ratification (`9fd1519`, 2026-09-15) supersedes any of
them — each citation is still the most current record for its testbench.

**It does not claim a clean two-key ratification release.** The two-key
review of the ratification ran post-hoc on PR #220
([`0008-two-key-ratification-review-outcome.md`](../../spec/decision-records/0008-two-key-ratification-review-outcome.md),
2026-09-19): the EE key returned `request-changes` and the market key
`escalate`, both converging on the same single row (Output reference), and
`ratify-key.sh release` returned **NOT-ELIGIBLE**. `0008` says explicitly
that this report "should read this record and #221 before claiming" a clean
release — this report does accordingly: five of six rows carry a
two-key-reviewed status they did not have before that review; the
Output-reference row's disposition is **re-opened, tracked as #221** (open
as of this writing), and is reported here as unmet-and-unsettled, not as
any kind of pass.

**It does not re-derive spec-conformance verdicts.** The per-row verdicts
below synthesize [`0007-target-spec-ratification.md`](../../spec/decision-records/0007-target-spec-ratification.md)
(ratified 2026-09-15), the corrections and two-key outcome in `0008`, and
the current `README.md` § "Target specification" — the sources of truth for
per-row dispositions. Where a number is quoted it was spot-checked against
the cited record's committed CSV and matched (see per-row notes); `0008`'s
own re-derivation of every cited number from the CSVs (matching except the
two corrections it records) is the broader audit behind that.

## Verdict table

Against `README.md` § "Target specification" (ratified via `0007`; status
annotations qualified by `0008`). "Statistical?" records whether the row's
verdict rests on a distribution claim — per the Monte Carlo evidence rule,
any such row must cite seeded-MC-with-negative-control evidence, and any
row that is a single corner-swept number says so.

| Row | Target (stretch) | Verdict | Statistical? | Primary evidence |
|---|---|---|---|---|
| Output reference | ~1.2 V ±1% untrimmed (±0.5% w/ trim) | **UNMET — disposition re-opened (#221)** | **Yes** — systematic sweep + N=300 MC | `vref-pvt` 2026-08-30, `vref-pvt-pex` 2026-09-05, `vref-mc` 2026-09-09 (below) |
| Temp coefficient | < 50 ppm/°C (< 20 stretch) | **MET (target); stretch endpoint-method only (#222)** | No — single corner-swept numbers | `vref-pvt` 2026-08-30, `vref-pvt-pex` 2026-09-05 |
| PSRR @ DC | > 60 dB (> 70 stretch) | **MET (target, 0.20 dB worst-case margin); stretch not met** | No — single corner-swept numbers | `psrr-pex` 2026-09-05 (primary), `psrr` 2026-08-30 |
| Supply | 3.3 V ±10% HV (1.2 V LV stretch) | **MET by construction** | No — not a simulated quantity | `0002` decision record + every cited PVT sweep |
| Iq | < 50 µA (< 20 stretch) | **MET (~16% worst-case margin); pre-layout only — disclosed gap** | No — single corner-swept numbers | `closed-loop-iq` 2026-08-30 |
| Startup | self-starting, < 1 ms | **MET (~10× margin)** | No — go/no-go + checkpoint pass counts | `closed-loop-startup` 2026-08-30, `startup-time-to-release` 2026-09-04, `startup-trip-point-pex` 2026-09-05 |

## Per-row verdicts and citations

### Output reference — UNMET, disposition re-opened (#221)

This is the row both ratification keys declined, and the block's most
significant known gap. It is the **only statistical row** in the table: the
verdict combines a systematic 45-point PVT corner sweep with a seeded
device-mismatch Monte Carlo, per the rule that a statistical claim carries
MC evidence (recorded seed, sample count, deterministic negative control,
combined with — not instead of — process corners — `vref-mc`'s campaign
satisfies all four: `.options rndseed=20260909+draw_index`, N=300
draws/point, a deterministic negative-control campaign, and MC points at
the nominal plus `bcs`/`wcs` × −40/125 °C corners).

Two independent failure mechanisms, both cited from committed evidence:

1. **Systematic offset (corner-swept, not statistical):** post-layout PEX
   across the full 45-point PVT grid
   ([`sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md`](../../sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md),
   2026-09-05): untrimmed `vref` spans **1.04309–1.05667 V** —
   **11.94–13.08% below the 1.2 V nominal, 0/45 points inside the ±1%
   band** `[1.188 V, 1.212 V]` (re-derived from the record's CSV for this
   report; matches `0008` § "Two evidence statements" exactly, which
   corrected `0007`'s "12.5–13.1%" phrasing — 12.5% is the *nominal*
   point, 1.05048 V). Pre-layout counterpart
   ([`sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md`](../../sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md),
   2026-08-30): nominal 27 °C/3.30 V `vref` = 1.04947 V; PEX-vs-schematic
   max |Δ| = 0.00167 V across all 45 points — layout extraction moves the
   number negligibly; the miss is systematic, set by the `R1`=511 µm
   TC-vs-`vref` retune (issue #134, see `0007` §
   "Output-reference-vs-TC trade-off").
2. **Device-mismatch scatter (statistical):** N=300 seeded Monte Carlo
   ([`sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md`](../../sim/closed-loop-vref-mc/records/20260909-232418-c9b83ab.md),
   2026-09-09): at the nominal point untrimmed `vref` mean = 1.046711 V,
   σ = 45.5 mV ⇒ **3σ/mean ≈ 13.0%** (corner points 12.1–14.6%); only
   20.7% of draws land within ±1% of the draw population's *own* mean,
   10.3% within ±0.5%. A ±1% band at 1.2 V is ±12 mV — unreachable for
   this core even with the systematic offset fully removed, and not fixable
   by the resistor-ratio retune class that closed the TC row.

**Disposition — re-opened, not settled.** Both keys declined to ratify the
row as written (EE `request-changes` on physics and the gf180/sky130
precedent of re-casting the row with a Trim row; market `escalate` because
no public part in this class publishes an untrimmed accuracy line at all —
see `0008` for both reviews verbatim-linked). Choosing between re-targeting
the row and defending ±1% untrimmed is **issue #221** (open as of
2026-09-21), which needs its own decision record and two-key review. The
trim network that would close the trimmed line remains out of scope
(`design/README.md`). Nothing in this report should be read as predicting
that decision's outcome.

### Temp coefficient — MET (target); stretch endpoint-method only (#222)

Target < 50 ppm/°C is met **by every method available, pre- and
post-layout**; the < 20 ppm/°C stretch is met **only by the endpoint
method** — this caveat is on the record from the two-key review (`0008`),
tracked as #222. Single corner-swept numbers, not distributions.

- Pre-layout
  ([`sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md`](../../sim/closed-loop-vref-pvt/records/20260830-114117-931c0e2.md)
  + its `-tc.csv`, 2026-08-30): informal endpoint-method TC across the 15
  corner/supply groups ranges **−14.4…18.1 ppm/°C**.
- Post-layout PEX
  ([`sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md`](../../sim/closed-loop-vref-pvt-pex/records/20260905-114438-8abe2aa.md)
  + its `-tc.csv`, 2026-09-05): **−17.6…15.5 ppm/°C** — both inside the
  20 ppm/°C stretch by the endpoint method, vs. ~349–376 ppm/°C
  pre-retune (`0007`'s history).
- The caveat: post-retune `vref(T)` is non-monotonic, and
  [`measurements/2026-08-tc-retune/README.md`](../2026-08-tc-retune/README.md)
  §4b's 8-point box-method scan — the method its own title says the
  3-point grid understates — gives worst case **wcs ≈ 20.2 ppm/°C**,
  outside the stretch. That scan is pre-layout only, 3.30 V-only, run in a
  scratch harness, and missing one non-converged point (`0008`, #222). The
  **target** (< 50 ppm/°C) clears even the box-method number.

### PSRR @ DC — MET (target, thin worst-case margin); stretch not met

Post-layout PEX
([`sim/closed-loop-psrr-pex/records/20260905-233826-f6f3efc.md`](../../sim/closed-loop-psrr-pex/records/20260905-233826-f6f3efc.md),
2026-09-05): DC PSRR ranges **60.20–105.71 dB across all 45 points —
45/45 clear the 60 dB target** (re-derived from the record's CSV for this
report; worst case 60.1978 dB at `bcs`/125 °C/3.63 V, matching `0008`).
35/45 fall short of the 70 dB stretch, so the stretch is **not met**. Single
corner-swept numbers, not distributions.

Two honesty notes carried from `0007`/`0008`:

- **The margin is 0.20 dB at the binding corner**, and the same corner
  reads 59.677 dB pre-layout
  ([`sim/closed-loop-psrr/records/20260830-133912-d83f7c4.md`](../../sim/closed-loop-psrr/records/20260830-133912-d83f7c4.md),
  2026-08-30, 2/45 points marginally short there) — the row passes because
  extraction *helped* it. Both keys accepted the row anyway; it should not
  be described as comfortable.
- **Away from DC**, [`0006-post-layout-psrr-hf-resonance.md`](../../spec/decision-records/0006-post-layout-psrr-hf-resonance.md)
  documents a narrowband (27.1–31.6 MHz) transmission-zero dip to
  −2.15…−0.84 dB (re-confirmed in the PEX CSV's `psrr_min_db` column) — a
  real, accepted-as-is finding that does not affect this DC-scoped row; no
  above-DC PSRR bound exists in the ratified spec.

### Supply — MET by construction

Target 3.3 V ±10% (HV flavor) is grounded in the SG13G2 device menu's
voltage ratings
([`0002-supply-voltage-scope.md`](../../spec/decision-records/0002-supply-voltage-scope.md)),
not in a simulated result: every closed-loop PVT record cited in this
report sweeps exactly the 2.97/3.30/3.63 V grid the row specifies (visible
in each record's `vdd_v` column). The 1.2 V LV stretch is a flavor
statement, not a measured quantity of this block. Not a statistical claim
and not a single-corner sweep — a by-construction rating argument.

### Iq — MET (~16% worst-case margin); pre-layout only (disclosed gap)

[`sim/closed-loop-iq/records/20260830-133900-d83f7c4.md`](../../sim/closed-loop-iq/records/20260830-133900-d83f7c4.md)
(2026-08-30, post-retune): settled Iq ranges **19.88–42.16 µA** across the
45-point grid (re-derived from the record's CSV for this report) — under
the 50 µA target at every corner, ~16% margin at the worst case; the 20 µA
stretch is touched only at the coldest/lightest-load corner. Single
corner-swept numbers, not distributions.

**Disclosed gap:** no `closed-loop-iq-pex` testbench exists — this row's
evidence is pre-layout only. `0007` records the judgment call (Iq is a DC
bias quantity set by `R2` and device sizing, untouched by the retune, so
schematic margin is judged likely to survive extraction) and both keys
accepted the row with the gap stated. It remains open follow-on work
(epic #4's item 7).

### Startup — MET (~10× margin)

Three records, two levels, all pass/fail per PVT point — pass counts, not
distributions:

- Schematic self-start/loop-closure
  ([`sim/closed-loop-startup/records/20260830-132425-d83f7c4.md`](../../sim/closed-loop-startup/records/20260830-132425-d83f7c4.md),
  2026-08-30): **45/45 PASS**.
- Time-to-release
  ([`sim/startup-time-to-release/records/20260904-184431-6fa83b4.md`](../../sim/startup-time-to-release/records/20260904-184431-6fa83b4.md),
  2026-09-04): **45/45 PASS, every PVT point releasing by the first
  100 µs checkpoint** — ~10× inside the < 1 ms target.
- Post-layout trip point
  ([`sim/startup-trip-point-pex/records/20260905-033740-fe97115.md`](../../sim/startup-trip-point-pex/records/20260905-033740-fe97115.md),
  2026-09-05): **45/45 PASS** — release behavior survives layout
  extraction. Disclosed gap: the specific time-to-release figure has no
  PEX-level re-measurement (`0007` records the ~10×-margin judgment call;
  both keys accepted).

## Gaps this report does not close

This report aggregates; it does not resolve. Still open against the rows
above, all tracked elsewhere:

- **#221** (open) — Output-reference row disposition: re-target vs. defend
  ±1% untrimmed. Needs its own decision record and two-key review.
- **#222** (open) — TC stretch box-method evidence gap: no committed,
  PVT-cornered, non-scratch box-method testbench behind the ~20.2 ppm/°C
  number.
- **#223** (open) — decision-record bookkeeping defects found by the EE
  key (duplicate `0007` numbering on `main`; `0001`/`0002` still
  `proposed`).
- No `closed-loop-iq-pex` experiment; no PEX-level time-to-release.

## Provenance

- Written 2026-09-21 against `main`@`77820fc` (worktree branched from
  `origin/main` at that commit). All nine cited `sim/` records verified to
  exist at that commit, and verified most-current: no record under
  `sim/*/records/` was committed after the ratification commit
  `9fd1519` (2026-09-15).
- Per-row verdicts and dispositions synthesize
  [`0007`](../../spec/decision-records/0007-target-spec-ratification.md)
  (ratified 2026-09-15) and
  [`0008`](../../spec/decision-records/0008-two-key-ratification-review-outcome.md)
  (two-key review outcome, 2026-09-19) — the authoritative per-row
  dispositions — plus `README.md` § "Target specification" as it stands
  after `0008`'s PR.
- Quoted headline numbers (PEX `vref` grid and in-band count, PEX DC PSRR
  range and worst corner, Iq range) re-derived from the cited records'
  committed CSVs for this report and matched `0007`/`0008` (with `0008`'s
  two corrections taken as current).
