# trim-coverage

Deterministic **trim-ladder coverage bench** (issue #229): the AC1
evidence that the committed trim network realizes DR-0011's ratified Trim
row — *"1-point at 27 °C; range ≥ ±15%; resolution ≤ 0.25%/step; magnitude
only"* — through the real closed loop, before any statistical claim is
made about what the trim does for mismatched dies (that is
[`../closed-loop-vref-trim-mc/`](../closed-loop-vref-trim-mc/)'s job).

## What this testbench claims, and what it does not

**It measures the real ladder.** The DUT is the trim-bearing
`bandgap_core` (R1 base `l=37.2u` to node `tn0` + `XXTRIM`), with the
255-unit binary-weighted ladder subcircuit copied device-for-device from
`design/netlist/bandgap_trim.spice` — its subcircuit-local
`.param trim_code` is the ONLY per-point difference between netlists. The
strap resistors decode `trim_code` into closed/open links (see
`design/bandgap_trim.sch`), so every code is measured through the ladder
the layout will carry, never through a synthetic trim source.

**It claims, per corner/supply group at the 27 °C trim temperature:**

- **Resolution**: the direct step `vref(129) − vref(128)` is ≤ 0.25% of
  the 1.050 V target (the row binds at 27 °C per DR-0011's derivation).
- **Range**: `vref(255) − vref(128)` (up) and `vref(128) − vref(0)` (down)
  are each ≥ 15% of 1.050 V.
- **Exact binary weights**: each single-bit code's measured step above
  code 0 equals `2^b` LSB-units within 0.5% (integer counts of the
  identical physical device hold `2^b` ratios at every corner by
  construction — gf180's measured lesson that differently-sized single
  resistors do not; this gate verifies it on this PDK's own corners).
- **Linearity**: the code-255 residual against `vref(0) + 255·unit` is
  within a quarter LSB (the loop's `vref = VBE(Q3) + I·(R1 + Rtrim)` with
  `I` set entirely by the R2/Q1/Q2 loop is linear in code to first order;
  this MEASURES the residual instead of assuming it).
- **Monotonicity**: `vref` strictly increases over the visited codes.

**It also verifies the default-code continuity claim** (the sizing
decision documented in `design/bandgap_trim_network.md`): at
typ/27 °C/3.30 V, the default code 128's `vref` reproduces the pre-trim
R1=511 µm single-instance core's committed operating point (1.047338 V)
— every pre-#229 record stays electrically valid at the schematic
default — and it measures the trim step's temperature dependence at
typ/3.30 V (−40/125 °C), where the step tracks the PTAT loop current
(`I = VT·ln(8)/R2`), i.e. scales with `T`.

**It does not claim anything about mismatched dies.** No statistical
sections are selected; the corner sections are the plain deterministic
ones every PVT sweep in this tree uses. Coverage of the mismatch
population is the trim-domain MC's claim, not this bench's.

## Grid

15 corner/supply groups (`{typ, bcs, wcs, sf, fs}` × `{2.97, 3.30, 3.63}`
V) at 27 °C × 11 codes (`{0, 1, 2, 4, 8, 16, 32, 64, 128, 129, 255}`),
plus the step-temperature probe (typ/3.30 V at −40/125 °C, codes
128+129) — 171 fast single-`.op` points. One `.op` per netlist; the driver
renders one netlist per point via `sed` (the repo's per-point-netlist
convention — no `alterparam` mid-run code changes, whose `reset`
semantics this tree does not rely on).

## Pass/fail criteria

Per point: `.op` converges, no model-load error, every printed node
parses, and `sim/lib/pvt_verdict_common.sh`'s shared
`pvt_closed_loop_verdict()` confirms the loop is genuinely closed and not
railed. Per group: the five ladder gates above
(`records/<record-id>-analysis.csv` carries each group's numbers and
status; the record's headline quotes the worst resolution/spans).

## Cold start

```bash
export PDK_ROOT=/path/to/ihp-open-pdk   # parent of ihp-sg13g2/
export PDK=ihp-sg13g2
sim/tools/build-osdi.sh                 # one-time
sim/trim-coverage/run_trim_coverage.sh             # sequential
JOBS=8 sim/trim-coverage/run_trim_coverage.sh      # bounded parallel
```

Requires at least one committed `sim/closed-loop-startup/records/*.csv`
(per-corner `.nodeset` DC-bias seeds). Writes append-only evidence under
`netlist-snapshots/<record-id>/`, `corners/<record-id>/` and
`records/<record-id>.{md,csv,-analysis.csv}` — see
[`../README.md`](../README.md).
