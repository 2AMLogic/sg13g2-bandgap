# closed-loop-vref-trim-mc

Trim-domain **device-mismatch Monte Carlo with a modeled 1-point 27 °C
trim** (issue #229) — the trimmed-line evidence DR-0011's re-cast
Output-reference row obligates: *"a trim-domain mismatch Monte Carlo
demonstrating the ±0.5% trimmed line over −40…125 °C after a modeled
1-point 27 °C trim"*. It is
[`../closed-loop-vref-mc/`](../closed-loop-vref-mc/README.md)'s (issue #215's)
trim-domain twin: the same `_mismatch` corner-lib sections, the same
`.options rndseed` parse-time discipline (verified there by direct
experiment — the mismatch expressions evaluate once, at netlist-parse
time, so the seed must be read before any `.lib`), the same
`.nodeset`-seeded single-`.op`-per-netlist technique, and the same
negative-control hard gate.

## Which spec row this backs

This bench is the **trimmed-line Monte Carlo** evidence for the **Trim** row
(DR-0011's Output-reference obligation; the row is kept as ratified by
[DR-0014](../../spec/decision-records/0014-trim-row-keep-1-point.md), which cites
this bench for the trimmed +/-0.5% line). Its deterministic counterpart,
the ladder's range/resolution, is [`../trim-coverage/`](../trim-coverage/README.md).
`run_trim_mc.sh` loops `ngspice -b` and must not be run as a grid on a dispatch
host; it is kept as the point-definition reference. The campaign runs through
[`run_klt_sim.sh`](run_klt_sim.sh) (issue #423, below).

## What this testbench claims, and what it does not

**It claims**: after a per-die 1-point trim at 27 °C (the die's own
corner, targeting DR-0011's 1.050 V TC-null point — never 1.2 V), the
closed-loop `vref` of N ≥ 300 seeded device-mismatch draws stays inside
**±0.5% of 1.050 V over −40…125 °C** at the 3σ level — the
trimmed-line counterpart of the untrimmed ±16% (3σ) line the #215 MC
established. Per-die data: the chosen trim code `code*`, its
distribution (mean/σ/min/max, railed count), the measured per-die trim
unit (mV/LSB) and the fit's linearity residual — all in
`records/<record-id>-draws.csv`.

**The modeled trim is a real ladder measurement, not an ideal voltage
knob.** Each draw runs six netlists through the actual 255-unit ladder:

1. **Fit** (27 °C, codes `{0, 1, 255}`): `vref(code) = a + unit·code`
   from the **{0, 255} chord** (`unit = (vref(255)−vref(0))/255`) — not
   the `{0,1}` tangent, because the ladder has a measured ~−1.4 LSB
   full-scale concavity (M3 finite-`ro` sublinearity,
   `sim/trim-coverage/`) whose chord-interpolation error is ~4× smaller
   than the tangent's; the code-1 row is the per-die low-code sanity
   check. `code* = clip(round((1.050 − a)/unit), 0, 255)` — the code a
   wafer-sort 1-point trim would pick for this die.
2. **Verify** (`code*`, temps `{−40, 27, 125}` °C): the trimmed die's
   `vref`; the trimmed line is `max_T |vref(T) − 1.050|/1.050`.

**Die identity is preserved across a draw's six netlists**: the device
draw is a pure function of (`.options rndseed`, the device instance
list), and every netlist of one draw shares both — only
`.param trim_code` and `.options temp` differ, neither of which touches
the draw. The fit at 27 °C and the verification at −40/125 °C are
therefore the SAME die.

**The ladder's own mismatch is part of the evidence**: all 255 unit
segments and the R1 base are inside the `res_*_mismatch` draw, so the
trim-domain spread includes the trim network's contribution, not just
the core's.

**It does not claim the trim covers every die.** A draw whose `code*`
rails at 0/255 is disclosed (`railed=1` in the draws CSV, `n_railed` in
the digest) — the ladder is sized so the correlated-coverage analysis in
`design/bandgap_trim_network.md` puts the rail beyond ±3.5σ of the
mismatch distribution, and this campaign measures where the population
actually lands. It also does not re-run the supply axis (held at 3.30 V
for the same stated reason as #215) and is pre-layout (like every
`closed-loop-*` experiment here).

## Points

| point | sections | trim at | verify at |
|---|---|---|---|
| `nominal` | `*_typ_mismatch` | 27 °C, typ | −40/27/125 °C |
| `negctrl` | plain (typ) | 27 °C, typ | −40/27/125 °C |
| `bcs` | `*_bcs_mismatch` | 27 °C, bcs | −40/27/125 °C |
| `wcs` | `*_wcs_mismatch` | 27 °C, wcs | −40/27/125 °C |

Negative control (hard gate): the same seeds against the plain sections
must trim to **exactly zero spread** at every draw and every verify
temperature — any spread is a driver bug (a mismatch section leaked in,
or a seed not reaching parse), and the run aborts without writing a
record, exactly as #215's does.

## Pass/fail criteria

Per draw: all six `.op`s converge (each invocation is bounded at 300 s —
a small tail of 125 °C mismatch draws grinds through ngspice's stepping
retries after the r3_cmc electro-thermal network feeds Newton a NaN;
bounded draws are recorded FAIL and disclosed, the same
non-converged-point discipline every PVT bench here carries) with the
loop genuinely closed and not railed (`pvt_closed_loop_verdict`, same
shared thresholds). Per point:
`n_pass == n_draws`, the negative control is exactly zero-spread, and —
the claim gate — **3σ of the per-draw max-temperature deviation ≤ 0.5%**
at every mismatch point. The fraction of draws inside ±0.5%
(`frac_within_0p5_pct`) is reported alongside (the 3σ gate is the
binding one, matching how the untrimmed line is a 3σ line).

## Evidence volume

Same discipline as #215: per-draw netlists and logs are NOT committed
(24 × N ≈ 7200 of them at N=300); the committed evidence is the digest
CSV (one row per point), the per-draw summary CSV
(`<record-id>-draws.csv`, one row per draw — the raw data the digest
summarizes), and ONE representative netlist+log per point (draw 0's
27 °C verify stage). The scratch directory is deleted on exit.

## Running it: `klt sim` decks (`run_klt_sim.sh`)

```bash
sim/closed-loop-vref-trim-mc/run_klt_sim.sh --sanity   # 2 local decks vs the committed record
sim/closed-loop-vref-trim-mc/run_klt_sim.sh --batch    # fit stage, code*, verify stage, assemble (fleet)
KLT_SIM_WORK=<batch dir> sim/closed-loop-vref-trim-mc/run_klt_sim.sh --record
```

`KLT_SIM_N` (default 300) and `KLT_SIM_SEED` (default 20260930) size the
campaign; `KLT_SIM_WORK` names the work directory (re-run with the same one to
resume). The decks are the template above, rendered by
[`sim/harness/trim_mc_klt.py`](../harness/trim_mc_klt.py) with the substitutions
`run_trim_mc.sh` made, and shipped byte-for-byte by klt's pre-composed `decks`
requests (`corners` + `monte_carlo` cannot express this: `corners.params`
cannot vary the code per sample, and the die identity comes from the
parse-time `.options rndseed` in each deck). Because the verify decks need each
die's `code*`, it is two fleet stages with a host-side step between:

1. **fit** — per (point, draw) the codes-0/1/255 decks at 27 C;
2. **`code*`** — computed from the fit logs by the script's own formula
   (`clip(round((1.050 − a)/unit), 0, 255)`, `unit` the {0,255} chord);
3. **verify** — per (point, draw) the `code*` decks at −40/27/125 C;
4. **assemble** — `records/<id>-draws.csv` (header unchanged), the digest, the
   negative-control gate, and the record via `klt_sim_evidence.py`.

Per-deck timeout stays 300 s. A failed or timed-out deck is a verify-FAIL row
(disclosed in `n_pass < n_draws`); a unit that never came back from the fleet
refuses the whole record — a partial draw set is never recorded. The digest port
is checked against the committed #229 record: fed its `-draws.csv`, it
reproduces its digest CSV exactly (`sim/harness/test_trim_mc_klt.py`).

A deck-list request refuses `--wait-for-capacity`, so the capacity wait rides
the request (`batch.capacity_wait_s`, `KLT_SIM_CAPACITY_WAIT_S`). A refused or
failed submit stops the run with the error; there is no local fallback. This
path does not use `monte_carlo`, so it does not depend on #403. The fleet
runner images ship the `decks` transport; the request names the image's baked
PDK root (`models.pdk_root`, `KLT_SIM_BATCH_PDK_ROOT`, default `/opt/pdk`) so
klt ships the decks' absolute `.lib` paths verbatim.

**Sanity gate.** Two draw-0, code-0, 27 C decks run first (local backend by
default; `KLT_SIM_SANITY_BACKEND=batch` for a host whose ngspice cannot load the
OSDI models). The **negative control** must land on the committed record's
`fit0_vref_v` (7.336808e-01; same engine, PDK, OSDI and renderer give the same
number to every printed digit) — that is the gate. The nominal mismatch draw is
printed against its committed value (7.140489e-01) but does **not** gate: a
mismatch draw comes from the host's RNG, and the committed record was produced
on another platform. The same deck, run on a Linux host (locally and on the
fleet alike), gives 7.318626e-01. Consequence: a fresh fleet record would sample a
different — equally valid — 300-draw population than #229's committed one, so
its per-draw rows differ draw for draw while the statistics are comparable;
the negative control and its trimmed values are identical.

## Cold start (legacy loop, reference only)

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent of ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time
sim/closed-loop-vref-trim-mc/run_trim_mc.sh --seed 20260930 --n 300   # NOT on a dispatch host
```

Requires at least one committed `sim/closed-loop-startup/records/*.csv`
(per-corner `.nodeset` seeds). Writes append-only evidence under
`netlist-snapshots/<record-id>/`, `corners/<record-id>/` and
`records/<record-id>.{md,csv,-draws.csv}` — see
[`../README.md`](../README.md).
