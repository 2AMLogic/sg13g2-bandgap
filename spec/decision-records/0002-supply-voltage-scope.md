# 0002: Supply voltage scope — 3.3 V (HV flavor) primary, no native 1.8 V flavor exists

- **Status**: proposed (input to a future spec-ratification issue)
- **Date**: 2026-08-05
- **Decided by**: Builder agent, issue #2
- **Related**: #1 (`klt` PDK resolver), `0001-bipolar-device-selection.md`
  (this record's supply choice interacts with that record's `BVCEO`
  headroom constraint), `2AMLogic/gf180-bandgap`
  `spec/decision-records/0002-supply-voltage-scope.md` (identical question,
  resolved 3.3V-only for gf180), `2AMLogic/sky130-bandgap`
  `spec/decision-records/DR-001-supply-flavor-scope.md` (identical question,
  resolved 3.3V-primary / 1.8V-stretch-deferred for sky130)

## Context

This repo's `README.md` "Target specification" table currently states the
Supply row as `1.8 V / 3.3 V — confirm against SG13G2 flavors`. That value
was carried over as an unconfirmed placeholder — it does not name a value
either sibling repo's spec ratified, and it does not match either of
SG13G2's actual device flavors.

Reading the SG13G2 process specification directly
(`SG13G2_os_process_spec.pdf` Rev. 1.2, §§2.1–2.6, and the ngspice model
files `sg13g2_moslv_mod.lib` / `sg13g2_moshv_mod.lib`, IHP-Open-PDK `main`
commit `22f2a25`, 2026-08-05) shows this PDK ships exactly two MOS voltage
flavors:

- **LV (`sg13_lv_nmos`/`sg13_lv_pmos`)**: 1.2 V core devices, `V_GS ≤ 1.65 V`
  at 125 °C per the process-spec pass/fail table.
- **HV (`sg13_hv_nmos`/`sg13_hv_pmos`)**: 3.3 V I/O devices, `V_GS ≤ 3.3 V`
  (Maximum) per the process-spec pass/fail table.

**No 1.8V-rated device family exists in this PDK's menu.** The README
draft's "1.8 V" half of the placeholder does not correspond to any real
SG13G2 device flavor — unlike sky130, whose 1.8V core devices
(`nfet_01v8`/`pfet_01v8`) are real and drove that repo's now-deferred 1.8V
Stretch column (`sky130-bandgap` DR-001).

## Decision

**3.3 V ±10% (HV device flavor) is the wave-1 primary Target**, matching
gf180-bandgap's identical resolution of this same question
(`gf180-bandgap` DR-0002: 3.3V-only for wave 1) and consistent with
sky130-bandgap's precedent of scoping wave 1 to a single flavor
(`sky130-bandgap` DR-001: 3.3V primary, alternate flavor deferred).

The 1.2 V LV core is named as this repo's analog of a future "Stretch"
flavor — **explicitly not 1.8 V**, correcting the README draft's placeholder
rather than merely re-wording it. No 1.2V-flavor work is undertaken in wave
1; this record does not schedule or scope that future work beyond naming it
as the real (rather than invented) alternate flavor this PDK offers.

This record updates `README.md`'s Target-specification table Supply row
from `1.8 V / 3.3 V — confirm against SG13G2 flavors` to `3.3 V ±10% (HV
flavor)` under Target, with `1.2 V (LV flavor)` noted under Stretch — see
the corresponding `README.md` edit in the same PR that lands this record.

## Alternatives considered

- **1.8 V primary or dual 1.8V/3.3V.** Rejected outright. No SG13G2 device
  flavor is rated at 1.8 V — adopting it would mean either inventing a
  voltage domain this PDK does not offer, or silently substituting the LV
  (1.2 V) flavor under a mislabeled "1.8 V" name. Either is worse than
  correcting the placeholder.
- **1.2 V (LV flavor) primary.** Rejected as primary. `0001-bipolar-device-selection.md`
  already names `npn13G2`'s low `BVCEO` (≈1.6 V target) as a first-order
  headroom constraint; stacking that against a 1.2 V primary supply leaves
  even less margin than the 3.3 V choice, working against the same-wave
  device-selection decision rather than complementing it. A 1.2 V primary
  is not rejected as *never* viable — only as the wrong choice to pair with
  wave 1's bipolar-device decision.
- **Dual 3.3V/1.2V flavor from wave 1.** Rejected, for the same reason both
  sibling repos rejected their own dual-flavor options: it roughly doubles
  wave-1 device-selection, testbench, and layout scope for a block whose
  purpose (per `README.md`) is proving out the SG13G2 design-to-silicon
  flow as fast as tooling allows, not maximizing flavor coverage on the
  first pass.
- **3.3 V (HV flavor) primary, 1.2 V (LV flavor) named as a future Stretch
  flavor (this decision).** Accepted. Matches both siblings' single-flavor
  wave-1 precedent, and — unlike simply leaving the README placeholder
  unresolved — names the *real* alternate flavor this PDK offers instead of
  the unconfirmed 1.8 V guess.

## Consequences

- **Unlocks a concrete Supply-row edit to `README.md`**, replacing an
  unconfirmed placeholder with a value grounded in the process spec's own
  device tables, landed in the same PR as this record.
- **Interacts with `0001-bipolar-device-selection.md`**: if `npn13G2` (the
  real HBT, `BVCEO` target 1.6 V) is the chosen bandgap-core device, the
  3.3 V primary rail's headroom advantage over the 1.2 V alternative is
  *not* automatically comfortable the way gf180's parasitic-PNP-on-3.3V
  choice was — any output-stage/cascode design must still respect the
  `BVCEO` ceiling regardless of which supply flavor is ultimately used. This
  record fixes the supply flavor; it does not resolve that headroom budget,
  which remains schematic-entry work for a future issue.
- **A future 1.2V-flavor variant remains a possible stretch goal**, to be
  scoped as its own separate issue and decision record if pursued — this
  record does not commit to it, schedule it, or imply timing, matching both
  siblings' treatment of their own deferred alternate-flavor columns.
- **Formal spec ratification remains a separate, later step.** As in both
  sibling repos, this record narrows flavor scope; it does not itself
  ratify the target-spec table's numeric values, which remains the
  responsibility of a future spec-ratification issue once schematic-level
  design work is far enough along to ground those numbers in SG13G2
  simulation.
