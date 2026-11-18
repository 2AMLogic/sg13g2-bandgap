# 2026-11 KLU re-time: closed-loop-iq and closed-loop-startup (issue #518)

PR #501 (issue #489) left the KLU-vs-SPARSE wall-clock question for this
repo's two supply benches undetermined: its tabled timings were taken on a
contended dispatch host and both bench READMEs disclaimed every wall clock
in them. This entry is the re-time the issue asked for, on the host class
the 2026-11-17 operator ruling approved: **one `repo-script` batch job on
one batch-fleet instance**, all cells serial inside the job, nothing else
running on the instance (the fleet launches one JobId-tagged instance per
job and powers it off at the end).

## Method

- **Job**: group `rs-20261118T043815Z-17be3498-s00` (see `job/`), sim image
  profile, Spot `m7i.4xlarge` (16 vCPU, 8 physical cores), AMI
  `ami-09c14f55df4958cbd`, job wall 3176 s, source commit `17be3498`
  (tarball sha256 `d35b2677…`, recorded in `job/run.json`). Driver:
  `retimer.py`, entry `retime_job.sh` (submitted as
  `infra/aws/repo-script-submit.py --image-profile sim --timeout 3600
  --wait-for-capacity 600`).
- **Image check first** (issue #518 acceptance criterion 1): the job asserts
  the image's ngspice banner reports `Compiled with KLU Direct Linear
  Solver` before running anything. It did: ngspice-47.
- **Cells**: exactly the four (bench, corner) rows PR #501 reported —
  per bench the sanity corner (typ/27 °C/3.30 V) and the hot corner
  (typ/125 °C/2.97 V). *"2 benches × 4 corners = 48 runs" in the issue's
  arithmetic double-counts: #501 timed two corners per bench, so the grid
  is 4 cells × 2 solvers × ≥3 repeats; the driver ran 5–6 repeats per cell
  while its job budget allowed (41 timed runs total).* The issue body's own
  scope note ("re-time only the cells someone wants to attribute to the
  solver") fixes this cell set.
- **Decks**: each bench's committed body/request templates, instantiated
  the way `run_klt_sim.sh` instantiates them (OSDI dir from the image's
  baked PDK at `/opt/pdk`, `@@VDD@@` per corner, `@@MSENSE_W@@` = 10u read
  from `design/netlist/bandgap_startup.spice`, corner bundle from
  `sim/harness/klt_corner_bundle.py`). The KLU variant differs from the
  SPARSE variant by **exactly the `klu` token** on the
  `.options reltol=5e-3` line — asserted in-code (unified diff of the two
  bodies is that one line, nothing else; body sha256s in `out/meta.json`).
- **Per run**: a one-corner local `klt sim` invocation (the scratch-request
  method the boxtc README documents), engine wall = the report corner's
  `runtime_s` (the engine-wall source #501's table used), process wall
  around the whole `klt` invocation, peak RSS, and the
  `Using … as Direct Linear Solver` line grepped from **that run's own
  ngspice log** — which must match the intended solver. Every run's
  answers were also compared with the #501/committed-CSV values at 6
  significant figures. Fleet klt on the image: `klt 0.9.0`.
- **Ordering**: pass-major (pass 1 for all 8 cell/solver combos, then
  pass 2, …), serially, one ngspice at a time; a budget guard stopped
  optional passes past the job cap.

## Result (engine wall, s; min / median / max of 5–6 serial repeats)

| cell | SPARSE 1.3 | KLU | Δ(min) | ratio (min) | verdict |
|---|---|---|---:|---:|---|
| iq / typ/27 °C/3.30 V (sanity) | 79.0 / 86.2 / 95.6 | 76.0 / 88.8 / 90.0 | 3.0 | 1.04× | **not resolved** (spread 16.6 / 14.0 > Δ) |
| iq / typ/125 °C/2.97 V (hot) | 107.2 / 116.2 / 119.7 | 74.6 / 86.6 / 87.4 | 32.6 | **1.44×** | **resolved: KLU wins** |
| startup / typ/27 °C/3.30 V (sanity) | 53.1 / 61.9 / 63.7 | 50.3 / 51.8 / 60.2 | 2.8 | 1.06× | **not resolved** (spread 10.6 / 9.9 > Δ) |
| startup / typ/125 °C/2.97 V (hot) | 69.0 / 79.7 / 82.2 | 50.8 / 51.9 / 58.1 | 18.2 | **1.36×** | **resolved: KLU wins** |

Medians agree with the mins on the resolved cells (iq/hot 1.34×,
startup/hot 1.54×). A cell whose spread exceeds its SPARSE↔KLU delta is
reported "not resolved", per the issue's own rule — never as a win or a
loss.

**Answer preservation**: all 41 runs graded `pass`, landed exactly on the
committed anchors at 6 significant figures (`fb_v` 2.49682 / 2.22558,
`|iq_avg_a|` 2.80682e-05 / 3.62959e-05, `vref_final_v` 1.04728 / 1.04201),
and the `singular matrix` recovery diagnostic the hot corners are known
for occurred under both solvers on the hot cells (recovered; corner grades
`pass`), on different internal trim nodes — SPARSE flags `xxtrim.t231`
and `xxtrim.t240`, KLU flags `xxtrim.t252` — and under KLU only the
27 °C sanity corner of both benches also emits one such warning per run
(`xxtrim.t254`, 10/10 runs, recovered; SPARSE: none there).
`out/results.csv` carries every run; `out/meta.json` the summary,
the per-run bodies' sha256 and the host facts.

## Verdict: adopted on both benches

KLU cuts **26–30 % off each bench's slowest corner** (the 125 °C cells —
resolved, delta ≫ spread) and shows no resolved difference on the 27 °C
sanity corners (point estimates favor KLU slightly there too). Both benches
therefore adopt `klu`: `.options reltol=5e-3 klu` on both body templates,
the request `_comment` timing notes, and #488's "except that body's klu
direct-solver pin" carve-out reverted — all three closed-loop supply
benches now pin KLU. The 45-point grids were re-run through each bench's
`run_klt_sim.sh --batch` on the adopted templates (new records in each
bench's `records/`: iq `20261118-072122-3e600d97`, startup
`20261118-082945-3e600d97`, both 45/45 PASS, identical to the pre-adoption
records at 6 significant figures on every verdict-bearing column — on each
grid the one wiggling column is the femtoamp/picoamp `i_mkfb*` noise-floor
current (Iq `i_mkfb_a`, 33/45 points, max ~1.6% relative; startup
`i_mkfb_final_a`, 32/45 points, max ~1.3% relative); see the bench READMEs).
`timeout_s` stays 1800: no corner was anywhere near it under either solver.

## Caveats, stated plainly

- **Run-to-run spread on the "dedicated" instance was ~10–20 %**
  (e.g. iq/sanity SPARSE 79.0–95.6 s), larger than a truly single-threaded
  idle box should show. The job-end load average read exactly 8.00 on the
  16-vCPU instance (start: 0.36), i.e. ~8 threads were runnable on average
  — consistent with the engine (or the klt local runner's worker pool,
  sized to the harness's `EDA_JOB_CONCURRENCY=8`) using more than one
  thread. This is the same image and the same execution environment every
  fleet `klt sim` job gets, and it applied identically to both solvers on
  interleaved passes, so the paired comparison and the ratio are sound;
  but the absolute seconds are fleet-environment seconds, not
  single-thread ideal-processor seconds (the same cell measured 42 s on
  this repo's dispatch worker under klt 0.9.3.dev with no
  `EDA_JOB_CONCURRENCY` exported). The verdict rests on deltas that exceed
  the measured spread, never on the absolute values.
- One instance type (m7i.4xlarge), one job, one pass ordering — no
  cross-instance hardware variance inside the measurement.
- `out/work/` keeps every run's `report.json` and `request.json` plus the
  committed `body.spice` decks; it does **not** keep the raw per-run
  `ngspice.log` files. `.gitignore`'s blanket `*.log` rule (then without any
  `measurements/**` negation) silently dropped all 41 of them at `git add`,
  and the job's Spot instance is gone, so they are not recoverable. The
  solver assignment those logs attested survives three other ways:
  `out/results.csv`'s `solver_line`/`solver_line_ok` columns (41/41
  `True`), `retimer.py`'s in-code assertion plus `out/meta.json`'s
  `problems: []`, and the committed `out/work/*/body.spice` decks, whose
  KLU and SPARSE variants differ by exactly the `klu` token on the
  `.options reltol=5e-3` line. The assembled corner decks (`corner.cir`)
  were pruned per run (regenerable from the committed templates +
  `out/meta.json`'s substitutions and sha256s).

## Contents

- `retimer.py` / `retime_job.sh` — the driver (also the T1 cold-start
  invocation: submit `retime_job.sh` as a `repo-script` job, or run
  `retimer.py --out <dir>` on any host with the PDK resolved).
- `out/` — everything the job produced that is committed (`results.csv`,
  `meta.json`, per-run reports/requests under `out/work/`); the raw
  per-run `ngspice.log` files were dropped by `.gitignore`'s `*.log` rule
  and are not recoverable (see Caveats).
- `job/` — the collected job envelope (`run.json`, `status.json`,
  `group.json`).
