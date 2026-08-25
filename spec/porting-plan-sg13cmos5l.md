# Porting plan — IHP SG13CMOS5L (from this repo's own SG13G2 design + the sibling repos' precedent)

**Status: engineering input, not a ratified decision.** Sibling document to
[`porting-plan.md`](porting-plan.md) (the original SG13G2 plan, from
gf180-bandgap/sky130-bandgap), covering the second PDK variant this repo
now targets: IHP SG13CMOS5L (`~/share/pdk/ihp-sg13cmos5l`), tracked by
issue #63 ("Chipalooza" port, four phases) and started by issue #64 (phase
1/4, this document's origin). It does not ratify a target spec for the
CMOS5L variant — that remains future work — but it does record the one
decision phase 1 was scoped to make (see
[`decision-records/0004-cmos5l-bipolar-device-selection.md`](decision-records/0004-cmos5l-bipolar-device-selection.md),
DR-0004).

**Sources checked**: `~/share/pdk/ihp-sg13cmos5l` (`main` branch, commit
`607e18d`, 2026-08-25) — read directly, `libs.tech/ngspice/models/`,
`libs.tech/xschem/sg13cmos5l_pr/`, `libs.doc/doc/`, `README.md`,
`versions.txt`; this repo's own `design/bandgap_core.sch` and
`spec/decision-records/0001-0003` (SG13G2's own port, the *closer*
precedent for this variant than either CMOS-only sibling, since the
front-end MOS/resistor/PNP devices are literally shared between SG13G2 and
SG13CMOS5L); `2AMLogic/gf180-bandgap`/`2AMLogic/sky130-bandgap` (the
grounded-collector parasitic-PNP-pair core precedent DR-0004 adopts, since
SG13CMOS5L — unlike SG13G2 — has no HBT).

## 1. What SG13CMOS5L is, relative to SG13G2

SG13CMOS5L is IHP's reduced-metal-stack (per that PDK's own `README.md`,
"M1-M4-TM1 stack") CMOS-only sibling process to SG13G2, not an unrelated
third PDK. Confirmed directly from the installed checkout:

- **Front-end devices are shared.** `sg13cmos5l_pr`'s MOS symbols
  (`sg13_lv_nmos`/`pmos`, `sg13_hv_nmos`/`pmos`, RF variants), `pnpMPA`,
  and the resistor symbols (`rppd`/`rhigh`/`rsil`) are *symlinks* into a
  sibling `ihp-sg13g2` checkout's own `sg13g2_pr` symbol library — same
  models, same `.sym` files, byte for byte. The ngspice model `.lib` files
  for these devices under `ihp-sg13cmos5l/libs.tech/ngspice/models/` are
  likewise symlinks to `ihp-sg13g2`'s copies (`sg13g2_moshv_mod.lib`,
  `sg13g2_moslv_mod.lib`, `resistors_mod.lib`, etc. — the literal
  filenames still say `sg13g2_*`).
- **The HBT (`npn13G2`) is NOT shared.** No HBT symbol, model, or
  reference anywhere in `ihp-sg13cmos5l`'s tree. SG13CMOS5L is CMOS +
  parasitic-PNP only — see DR-0004.
- **No MIM cap.** Only MoM (`cap_cmomf`/`cap_cmomi`, real files, not
  symlinks — these have their own SG13CMOS5L-specific Verilog-A models,
  `libs.tech/verilog-a/cap_cmomf/`, `cap_cmomi/`) and MOS cap
  (`moscap_n`/`moscap_p`, symlinked from `ihp-sg13g2`).
- **Prebuilt OSDI models ship with this PDK.** Unlike SG13G2's v0.3.0
  release tarball (which needed `sim/tools/build-osdi.sh` to compile
  PSP103/`r3_cmc` from source — issue #22), this SG13CMOS5L checkout
  already has `libs.tech/ngspice/osdi/{psp103,psp103_nqs,r3_cmc,mosvar,
  cap_cmomf,cap_cmomi}.osdi` built — no build step was needed for this
  phase's DC sanity check. Whether this holds for whatever release phase
  2 (#65) actually pins is unconfirmed; re-check before assuming.

## 2. What carries over from this repo's own SG13G2 port

Because the front-end devices are literally shared, more carries over here
than either CMOS-only sibling could offer:

- **The verification discipline, decision-record process, and friction
  protocol** — unchanged, same as `porting-plan.md` §1 already established
  for SG13G2; nothing about a second PDK variant changes these.
- **The 3.3V HV-flavor supply choice (DR-0002).** SG13CMOS5L ships the
  identical `sg13_hv_nmos`/`sg13_hv_pmos` devices at the identical 3.3V
  rating (same model files). DR-0004 inherits this unchanged rather than
  re-litigating it. (Note: #65, the sim phase, frames its own target as
  "1.2V digital / 3.3V analog," which is this same HV-flavor choice for
  the analog core — the 1.2V figure there is the *digital* rail this
  bandgap-only block does not itself use.)
- **The `rppd` mild-TC precision-resistor choice.** Same device, same
  model, same process-spec-recommended `≥2µm` line width this repo's own
  SG13G2 core already uses for its ratio-critical legs — ported directly,
  not re-derived.
- **The `pnpMPA` device's own characterization**, already read once for
  DR-0001 (SG13G2's fallback-device evaluation) and re-read for DR-0004 —
  the model card is identical between the two PDKs (same `bf ≈ 1.10`,
  same `.subckt pnpMPA c b e` structure), so no new model-reading work was
  needed here beyond confirming the file is the same.

## 3. What does not carry over: the core topology itself

Per DR-0004: with no HBT, `design/sg13cmos5l/bandgap_core.sch` cannot be a
re-parameterized copy of `design/bandgap_core.sch` (SG13G2's grounded-
emitter NPN core). It instead follows gf180-bandgap's/sky130-bandgap's
grounded-collector parasitic-PNP-pair shape — the *reverse* of
`porting-plan.md`'s own §3 conclusion, which chose the NPN topology
specifically because SG13G2 had a real HBT neither sibling repo did. See
DR-0004 for the full reasoning and the schematic's own header for the
sizing derivation.

## 4. Open questions / flagged risk (for phase 2/#65 and beyond)

1. **`pnpMPA`'s low gain (`bf ≈ 1.10`) is now load-bearing**, not a
   documented-but-unused fallback the way it is for SG13G2 (DR-0001). Any
   future untrimmed-accuracy budget for this core needs to treat base-
   current error as a first-order term.
2. **MoM-cap-only compensation/filter sizing has no corner/mismatch
   spread in this PDK's models** (per the parent issue #63/#64's own
   finding). Flagged in DR-0004 as forward guidance; #65's acceptance
   criteria already track marking any such spec row
   `insufficient-evidence` rather than a clean pass.
3. **The sibling-checkout install-shape gap** (§1's "front-end devices are
   shared" symlinks are dangling in an `ihp-sg13cmos5l`-only install) is a
   real environment-setup trap for whoever next resolves this PDK fresh —
   filed generically upstream at `2AMLogic/klayout-tools` per the friction
   protocol (see `design/sg13cmos5l/README.md` "Tooling/PDK friction
   encountered" for the full account and the issue link).
4. **`klt drc`/`klt lvs` do not support SG13CMOS5L today** — already
   identified and tracked by #66 (phase 3), with its own upstream
   `klayout-tools` epic (#1398) and phase issues (#1399-#1401). Not
   re-litigated here; noted for completeness of this plan's "what's
   blocked and where" picture.
5. **Whether the prebuilt `.osdi` binaries this checkout ships remain
   present in whatever SG13CMOS5L release phase 2 (#65) actually pins.**
   This phase's install happens to have them; not yet confirmed as a
   stable property of the PDK's release process the way SG13G2's
   need-to-build-from-source property was confirmed stable across
   multiple issues (#22, #31).

## 5. Next steps

DR-0004 and this plan are inputs to phase 2 (#65, PVT-cornered
testbenches) and phase 3 (#66, layout — currently blocked on upstream
`klt` deck coverage). Startup-circuit/amplifier/top-level-integration
schematic capture for SG13CMOS5L (this repo's `bandgap_startup`/
`bandgap_amp`/`bandgap_top` equivalents) was explicitly deferred by phase
1 per the parent issue's own allowance and filed as a separate follow-up
issue rather than expanding this phase's scope.
