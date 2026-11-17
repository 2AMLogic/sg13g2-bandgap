# 0016: the evidence standard for layout/signoff evidence is the PyPI `klayout-tools==0.8.0` pin, not a host dev build

- **Status**: proposed
- **Date**: 2026-11-17
- **Decided by**: Loom Builder (agent), issue #558

## Context

The committed top-level evidence was minted under scattered klt builds:
`layout/bandgap_top/lvs_report.json` carries provenance
`0.6.0+geb7e7c6ace30` (KLayout 0.30.12), while
`manifests/sg13g2-bandgap.signoff.json` records `build.version` 0.8.0 and
CI (`.github/workflows/hygiene.yml`, "Install pinned klt") pins
`klayout-tools==0.8.0` from PyPI. The dev hosts now carry a git build
(`0.9.3.dev517+gc6ecffcb8e56`), and grading under it flips the committed
`bandgap_top` LVS verdict from 10 findings / 4 error-severity (devices
275/275, nets 257/261) to 1023 / 1019 (devices 17/275, nets 5/261) and
makes `check_signoff_manifest.py` report ROTTED at `$.build.git_commit`.
Until this record the repo had no written statement of which klt build is
its evidence standard (issue #558).

Measured comparison (one local `klt lvs` per version on the committed
`bandgap_top.gds` + `lvs_request.json`, all else byte-identical;
2026-11-17):

| klt (PyPI unless noted) | klayout | deck `sg13g2` hash | findings / error-sev | devices matched | nets matched |
| --- | --- | --- | --- | --- | --- |
| 0.6.0 git build (minted the committed report) | 0.30.12 | `f9771af8…` | 10 / 4 | 275/275 | 257/261 |
| 0.8.0 (CI pin) | 0.30.13 | `1c95db40…` | 1023 / 1019 | 17/275 | 5/261 |
| 0.9.2 (latest PyPI) | 0.30.13 | `cf6dfead…` | 1023 / 1019 | 17/275 | 5/261 |

Two traced facts narrow the decision:

1. **The signoff rot is a host-vs-pin artifact, not real drift.** Re-running
   `check_signoff_manifest.py` with the CI pin (exact PyPI 0.8.0) on the
   unmodified tree exits 0 — verdict of record current, all 6 pinned
   citations fresh. The ROTTED verdict only appears under a host dev build,
   whose `build.git_commit`/`grading_ruleset_id` differ from the pinned
   release. A git build also cannot satisfy an exact pin at all
   (klayout-tools#2823).
2. **The LVS explosion is deck-generation drift, not a 0.9-only regression.**
   The CI pin itself already grades 1023/1019 — the committed 10/4 report is
   not reproducible under *any* PyPI-installable pin. The signature is the
   sg13g2 deck's resistor pairing: at 0.8.0+ every MOS device matches but
   zero resistors do (layout-side class `rppd` vs reference-side `RPPD` no
   longer pair), cascading into ~500 `net.unmatched`. Filed upstream as
   [klayout-tools#6313](https://github.com/2AMLogic/klayout-tools/issues/6313)
   (sibling-deck analogue: klayout-tools#4424).

## Decision

**The evidence standard for every layout verdict and signoff grade in this
repo is the exact PyPI release `klayout-tools==0.8.0` — the same release
CI's `klayout-tools==` pin installs.** Concretely:

1. Evidence is minted and verified under that pin, via a throwaway
   environment (`uvx --from "klayout-tools==0.8.0" klt …`), never under the
   host's dev build. Dev builds do not satisfy an exact pin
   (klayout-tools#2823) and grade a different `build`/ruleset identity, so
   ROTTED/STALE verdicts they produce against committed evidence are
   host-vs-pin artifacts, not evidence rot — re-check under the pin before
   believing one.
2. `layout/bandgap_top/lvs_report.json` is re-minted under the pin (done in
   this PR: 1023 findings / 1019 error-severity, devices 17/275, nets
   5/261, deck `1c95db40…`). The committed request document is unchanged.
   The old 10/4 report is retired as unreproducible under the standard, not
   silently overwritten: the delta and its cause are this record and
   klayout-tools#6313.
3. `manifests/sg13g2-bandgap.signoff.json` already records build 0.8.0 and
   grades current under the pin; it stays. CI's pin stays 0.8.0.
4. **Bump procedure unchanged:** raising the pin (this standard, CI's
   `klayout-tools==`, or both together) re-runs `klt signoff --manifest`
   and re-mints every affected report **in the same PR** (hygiene.yml's
   existing rule), with the measured before/after counts recorded here or
   in the bumping PR.

## Alternatives considered

- **Pin 0.9.2 (latest PyPI)** — grades this GDS byte-identically to 0.8.0
  (1023/1019; same categories, same counts; only provenance/deck-hash
  strings differ). Choosing it would force a CI pin bump plus a signoff
  re-grade for zero verdict difference, against the fewest-evidence-change
  rule. Rejected; revisit when the upstream gap (#6313) is fixed — that fix
  is the natural bump point, via the bump procedure above.
- **Pin the host dev build (0.9.3.dev517+g…)** — not installable from PyPI,
  so CI could never reproduce a grade minted under it (and klayout-tools#2823
  makes an exact pin impossible for a git build). Rejected.
- **Keep the 0.6.0-minted LVS report** — unreproducible under any
  installable pin; keeping it would leave the verdict table claiming
  275/275 device match under a deck that no release ships. Rejected.

## Consequences

- `bandgap_top`'s verdict row now reads 1023 findings / 1019
  error-severity, devices 17/275, nets 5/261, until the upstream deck gap
  (#6313) is fixed and the bump procedure re-mints the evidence. The
  "permanent bipolar-recognition cause" narrative (3 `NPN13G2` reference
  devices) remains true but is no longer the *dominant* finding count.
- The `bandgap_core` row and the sg13cmos5l-* cells still cite 0.6.0-era
  mints; refreshing them under the standard is a follow-up (tracked via the
  #6313 fix landing, not this record).
- DRC re-verification under the standard is #556's scope, deliberately not
  done here.
- Grades are host-reproducible again: any agent on any host can re-derive
  every committed verdict with one `uvx` pin, and CI (exact pin) agrees
  with what is committed.
