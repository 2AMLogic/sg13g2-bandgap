# manifests — the block's `klt signoff` manifest and verdict of record

This directory holds this block's machine-readable gap-to-T1 state (issue
#226). The hand-maintained checkbox list in tracker issue #4 is retired: the
**verdict of record** is the committed signoff report next to the manifest
that produced it.

- `sg13g2-bandgap.json` — the **block manifest** consumed by
  `klt signoff --manifest`. Declares the block id (`sg13g2-bandgap`, the row
  key the fleet roll-up at 2AMLogic/2am#956 consumes) and `kind: analog`
  (confirmed against the block: a bandgap voltage reference with no digital
  partition), plus one evidence citation per T1 item this repo can currently
  back with a committed `klt` envelope.
- `sg13g2-bandgap.signoff.json` — the committed **verdict of record**: the
  exact output of `klt signoff --manifest manifests/sg13g2-bandgap.json
  --format json`.
  The pinned grader reports **tier none, 5/11 T1 items met** (1, 2, 3, 8
  and 10). In item 6, the N=1,200 yield report passes the untrimmed row.
  The trimmed row remains a declared gap (#303), so the item grades
  `unmet`/`partial_coverage`. Item 5 grades `unmet`/`check_failed`.
  Its PSRR grid measures 59.685 dB against the > 60 dB bound at
  bcs/125 °C/3.63 V.
- `artifacts/` — **stored-run manifests** (issue #379, DR-0015): one
  `<bench>-<run-id>.manifest.json` per new `klt sim` run, naming the run's raw
  logs and netlist snapshots in the fleet artifact store by sha256. See
  [`artifacts/README.md`](artifacts/README.md). Unrelated to the signoff
  manifest above and to the `klt` pin: the artifact client needs klayout-tools
  `7e3561f` or later, installed separately.
- `evidence/` — the **audited inventories** (`*.txt`) and their
  artifact-anchored `generic` envelopes (`*.json`) that items 1 and 10 cite
  (see below).

## Re-running

From the repo root, with the pinned `klt` build installed (see "The pin"
below):

```sh
klt signoff --manifest manifests/sg13g2-bandgap.json --format json
```

Exit `0` means tier `T1`; exit `3` means graded and not-T1 (with the full
report on stdout) — **exit 3 is a valid, successful grade**, not an error.
Only a crash / exit 1 / exit 4 (`refused`) means the grading itself failed.

## What each citation does and does not prove

The grader cannot check topical relevance for items it grades on "some
passing envelope was cited" — citing honestly is this repo's responsibility
(`docs/design-evidence-tiers.md` → "Not every item has a tool behind it").
The binding used here:

- **Item 1 (Design sources) — cited: `evidence/design-sources.json`** (#299;
  artifact-anchored `generic` envelope, `t1_item: 1`, bound to
  `evidence/design-sources.txt`). Before #299 this item borrowed the
  `extract` envelope `layout/bandgap_top/pex_extract_report.json`, which
  graded `met` but proved nothing about the schematic-to-netlist step (and
  carries no `artifact_binding`; the new grader prints "topic: not bound"
  for such a citation). The inventory lists every `design/*.sch`, its
  symbols and the derived `design/netlist/*.spice` with sha256s, the export
  command, and the outcome of a **one-off audit**: the five exports were
  re-run in a scratch copy against the pinned IHP-Open-PDK v0.3.0
  (tarball sha256 matched `sim/pdk.json`) and reproduced every committed
  netlist (0 differing lines once the author-path `**` comments and blank
  lines are ignored). The SG13CMOS5L variant under `design/sg13cmos5l/`
  did **not** reproduce cleanly (a brace-formatting difference in two
  netlists) and is excluded from the attestation.
  **What the binding does and does not prove.** `klt signoff` re-hashes the
  inventory file only. A later edit to a listed schematic or netlist does
  not make the row stale by itself — the inventory is an audited record, not
  a transitive hash tree, and nothing here claims otherwise. Netlist drift
  against the sims is caught by `check_evidence_formats.py`'s sim-DUT
  freshness check; the `.sch` to `.spice` export is **not** re-checked in
  CI. Whoever changes `design/` must re-audit and regenerate the inventory,
  envelope, pin and verdict.
  **Stale-input detection (#324).** `evidence/design-sources.inventory.json`
  (beside the attestation, *not* bound by the envelope or manifest pin) is the
  machine-readable form of the audit's inputs: the 14 in-scope
  `design/*.sch`, `design/*.sym` and `design/netlist/*.spice` hashes, the
  export rcfile `design/xschemrc`, and the scope globs (SG13CMOS5L under
  `design/sg13cmos5l` explicitly excluded). `.github/scripts/check_design_source_dependencies.py`
  (hygiene job; self-test alongside) fails, naming the path, when an audited
  input changed or vanished, when an in-scope cell was added that the audit
  never saw, or when the inventory disagrees with the attestation's own hash
  lines. Unrelated edits and SG13CMOS5L changes pass. A pass means only
  "the audited inputs are unchanged" -- it is not a new export-equivalence
  proof, and CI never refreshes anything. On failure: do a fresh explicit
  export audit, then write a new attestation, inventory, envelope, pin and
  verdict (a superseded audit's inventory stays as history and is not checked).
  The attestation text's sentence that nothing re-validates the listed hashes
  predates this check and is left byte-identical so the envelope pin holds.
- **Item 2 (Layout) — cited: `layout/bandgap_top/drc_report.json`**: proves
  the committed GDS exists and was DRC-checkable at the pinned content hash;
  the generator (`layout/bandgap_top/generate.py`) is committed and
  deterministic. The #579 rebase regenerated the GDS with #571's tap-margin
  fix composed onto #574's Via1 Metal2-landing enclosures, and #572 composed
  its Metal1 base-contact landing onto that; the item is
  `met` again (it had regressed to `check_failed` on the pre-#574 branch,
  whose assembled GDS still carried the Via1 classes).
- **Item 3 (DRC clean) — cited: `layout/bandgap_top/drc_report.json`**:
  `status: clean`, input hash pinned to the current committed GDS, with
  **4 markers waived** cell-scoped (`drc_waivers.json`, each naming its
  tracking issue: 4 `cont.ongrid.1` →
  #573 — every waived marker instance-attributed to a leaf cell, none in
  top's own geometry). The 11 `nwell.enclosing.nactiv.1` markers #574's
  waiver carried are gone at the source: #571's tap-margin fix closed the
  class, and per `drc_waivers.json`'s own rule the two entries naming it
  were deleted in the #579 rebase; the 18 `metal1.enclosing.cont.1`
  markers are gone the same way — #572's landing strips closed the class
  inside `bandgap_core`, and the entry naming it is deleted in this PR
  (waived set 22 → 4). Every Via1 class is **0** (#574's landings
  fix, composed into this GDS).
  **DRC coverage disclosure (claimant-enforced, quoted from the report's
  `coverage` block):** the curated deck now checks 25 chapters
  (`deck_scope`: Act, Cnt, Gat, M1–M5, MIM, NW, Offgrid, TM1, TM2, TV1,
  TV2, V1–V4, pSD, plus the curated Cont/Via1–Via4 upper-landing
  containment chapters); this run skipped 32 carried rules
  (`rules_skipped`, all Via2+/metal3+/topmetal/topvia
  width-space-enclosure rules — the block routes on M1/M2 with Cont/Via1
  only) and drew 10 layers the deck has no rule for
  (`layers_in_stream_without_rules`: 5/1, 8/1, 8/25, 10/1, 10/25, 28/0,
  33/0, 111/0, 128/0, 128/1 — label/pin-purpose variants and marker
  layers, including the EXTBlock/SalBlock/PolyRes resistor-recognition
  markers and EmWind). A `met` here means "clean inside that scope",
  not "no DRC-expressible defect exists".
- **Item 4 (LVS clean) — cited unpinned: `layout/bandgap_top/lvs_report.json`**:
  grades `check_failed` — `status: mismatch`, honestly. Sole remaining cause
  on the SG13G2 cells: `bandgap_core`/`bandgap_top`'s three `NPN13G2`
  devices, whose recognition the curated deck permanently declines upstream
  (klayout-tools#1242); see tracker #4 and `layout/README.md`. The citation
  carries no `content_hash` pin because `klt lvs` envelopes record no
  `provenance.input` block (upstream JSON contract) — its freshness is
  enforced by `check_evidence_formats.py`'s layout-report staleness gate
  instead, which re-derives every committed report's input hashes.
- **Item 5 (PVT corners) — cited as four `klt sim` grid envelopes, one per
  expressible spec row** (issue #629): the committed run reports
  `records/<id>-report.json` of `sim/closed-loop-vref-pvt`
  (`20261122-181757-c5b84561`), `sim/closed-loop-psrr`
  (`20261122-182058-1d0308ad`), `sim/closed-loop-iq`
  (`20261127-000000-b092b294`) and `sim/startup-time-to-release`
  (`20261122-183926-90e8e4dd`), each carrying its row's ratified bound as a
  request-level `limits` on the measurement that measures it (with a
  `spec_row` tag), so the run's own report grades the row — the envelope's
  `measurements[]` rollup records status, limits and the binding
  `worst_case` corner, and `spec_rows["5"]` declares the full row set.
  Grades `unmet` / `check_failed`, honestly: the PSRR envelope **fails** at
  its binding corner — `psrr_dc_lin` 0.00103694 V (59.685 dB) against
  `max` 1e-3 (> 60 dB) at bcs / 125 °C / 3.63 V, matching the 2026-11-13
  grid to the digit; the failing row names design issue **#631**. The other
  three rows pass with machine-**derived** coverage (`row_sources`):
  `output-reference-nominal` (settled `vref_3ms_v` ∈ [0.882, 1.218] V at
  every corner — the ±16 % window of the 1.050 V nominal, DR-0011's
  *deterministic PVT-extent half*; the 3σ mismatch half is item 6's), `iq`
  (`iq_avg_a ≥ −50 µA` on the signed average: the binding value is
  −41.7771 µA at bcs/125 °C/3.63 V and its margin 8.2229 µA is that value
  minus `limits.min`, so the envelope's value, limit and margin re-derive
  each other — the 27 November re-run on the #648 generator, #653; the
  superseded `20261122-181711-c5b84561` envelope paired the same margin with
  a +41.7771 µA magnitude) and `startup`
  (`i_mkfb_1000u_a` within ±50 nA at the spec's own 1 ms checkpoint, worst
  0.183 nA; the ladder bench — not `closed-loop-startup` — is the Startup
  citation precisely because its request can carry the 1 ms bound, and its
  enrichment records the full per-checkpoint release-criteria verdicts).
  Four rows are **declared gaps** in `spec_rows["5"]`: the box-method
  temp-coefficient and the trim range/resolution are deterministic figures
  derived *across* corners of one swept axis, which `klt sim` cannot grade
  (klayout-tools#7184) — their committed measurements (20.20–38.62 ppm/°C;
  +29.22/−29.63 %; 0.2347 %/step) are quoted in the gap reasons but are
  not envelope-graded — and the Supply row is a rating argument
  (DR-0002), not a simulation: every cited envelope sweeps 2.97/3.30/3.63 V.
  The citations carry no `content_hash` pin (a `klt sim` report's
  `provenance.input` names the run's scratch netlist, which is not
  committed) — the same unpinned-citation convention as items 4 and 6;
  freshness is enforced by the append-only rule on `sim/*/records/`
  (`check_evidence_formats.py::check_append_only`, the gate that actually
  blocks an edit to an unpinned citation — `check_signoff_manifest.py`'s
  re-grade reads the envelope's own `status` fields and does not re-check
  measurement values against their limits, so a value-only edit changes no
  verdict; measured in issue #646), and by the artifact manifests' sha256s
  over the run's raw logs and netlist snapshots. One more upstream
  limitation is disclosed here: the #2668 one-model-library-per-request
  split means each grid runs as 15 requests whose reports this repo's
  merger re-assembles, re-deriving the request-declared `measurements[]`
  rollup over the concatenated corners by klt's own aggregation rule
  (`sim/harness/merge_batch_shards.py`; klayout-tools#7225 asks for a
  supported form). What a `met` here
  would mean: every cited envelope passing and every declared row covered —
  nothing here relaxes the PSRR miss to get there.
- **Item 6 (Statistical claims carry Monte Carlo evidence) — cited unpinned:
  `sim/closed-loop-vref-mc/records/20261121-195500-b03b10b7-yield-report.json`**:
  a `klt yield` JSON report minted (producer `klayout-tools[yield]==0.9.2`,
  graded under the CI pin `0.8.0` — both versions re-pinned in #635) from the
  **committed N=1200 campaign** `20261121-194338-b03b10b7-draws.csv` (the
  #635 follow-up: 6 points x 1,200 draws, 7,200/7,200 PASS on the batch
  fleet, 72 job ids in the run record's `environment.remote`; its first 300
  draw indices reproduce the 2026-11-04 N=300 record draw-for-draw at
  recorded precision — 1,797/1,800 `vref` byte-identical, 3 draws differing
  by 1 in the last digit, 0 status mismatches) via `klt yield-csv` (same CSV
  sha256 in the sample set's `derivation` block). Five measurements (the
  mismatch points `nominal`, `bcs_n40`, `bcs_125`, `wcs_n40`, `wcs_125`,
  N=1,200 each, seed rule `20260909 + draw_index` readable from the draws'
  own seed column; the zero-spread `negctrl` rows are excluded — 1,200
  draws, one distinct `vref`) carry the ±16 % bounds 0.882–1.218 V,
  `target_sigma: 3`, `min_converged_samples: 1200`,
  `spec_row: output-reference-untrimmed`; `spec_rows["6"]` declares that
  row covered and the trimmed ±0.5 % line as a **gap** (#303, PR #435
  pending — re-campaign and re-mint when it lands).
  **What the citation does and does not prove.** It proves the statistical
  machinery ran on real seeded draws and that the ratified 3σ claim, in the
  form `klt yield` grades it (sigma-to-spec lower bound at two-sided 95 %
  confidence), now **holds at every point**: lower bounds 3.5307 /
  3.7195 / **3.0782** / 3.7613 / **3.2389** (nominal / bcs_n40 / bcs_125 /
  wcs_n40 / wcs_125) against point estimates 3.6889 / 3.8849 / 3.2189 /
  3.9284 / 3.3857 — the N=300 mint's hot-corner misses (2.8845 / 2.8632)
  were confidence-bound width, not observed spread, exactly what #635's
  1/√N sizing projected. Every sample-size verdict is `sufficient`
  (±1-point half-width), all 6,000 requested mismatch draws converged, and
  6 of 6,000 draws fall outside the bounds (empirical yield 0.99917 at
  four points, 0.99833 at `wcs_125`, each with its Clopper-Pearson
  interval). It does **not** settle item 6: the trimmed ±0.5 % line stays
  a declared gap, so the item grades `unmet`/`partial_coverage` with the
  untrimmed row `met` — reported as graded. The **negative control is not
  declared** (`not_declared`): the report carries klt's own null + warning
  because `klt yield-csv` 0.9.2 cannot attach a control (klayout-tools#6974,
  re-checked at re-mint: still no released CSV-control producer); the
  campaign's zero-spread `negctrl` point stays the harness's own
  determinism check, not klt's negative control. The citation carries no
  `content_hash` pin because `klt yield` envelopes record no
  `provenance.input` block (upstream JSON contract, like `klt lvs`); its
  freshness is three separate checks, none of which hashes the sample
  set into the verdict: (1) `klt signoff` re-grades the report, and
  `check_signoff_manifest.py` fails if the resulting grade differs from the
  committed `sg13g2-bandgap.signoff.json`; (2) the append-only check
  (`APPEND_ONLY_RE` in `check_evidence_formats.py`, covering
  `sim/*/records/`) protects the committed N=1,200 samples document and
  report once they are on `main`; (3) regenerating the samples and report
  (`klt yield-csv`, `klt yield`) from the committed
  `20261121-194338-b03b10b7-draws.csv` and comparing byte for byte
  verifies their contents against the source CSV and limits. An edit to
  the samples or report that leaves the grade unchanged is **not** caught
  by (1) — it was measured under the pinned grader: perturbing a sample
  value, or editing the report's `distribution.mean` / `sigma_to_spec`
  without flipping a verdict, leaves the fresh grade byte-identical.
  The superseded N=300 mint (`20261120-231009-73ef81b4-*`, exit 3, hot
  lower bounds 2.8845 / 2.8632) stays committed as the history that sized
  this campaign.
- **Item 11 (Power delivery, structural) — cited as the compound pair
  `layout/bandgap_top/erc_report.json` (pinned to the `bandgap_top.gds`
  hash) + `layout/bandgap_top/lvs_report.runset.json` (item 4's LVS
  report, unpinned):** grades `unmet` / `lvs_did_not_pass` (#411). The ERC
  half is complete and clean: `layout/bandgap_top/erc-supply-spec.json`
  (SG13G2 stackup GatPoly/Metal1/Metal2, `Cont` + `Via1`, `VDD`/`VSS` as
  supplies, one n-well `ties[]` entry) re-minted under the containment-deck
  build (`klt 0.9.3.dev1023`, klayout 0.30.13 — the same build as the cell's
  DRC mint in #572) against the #572 regenerated GDS
  reports `erc_status: "clean"` with zero findings — each supply resolves to
  exactly one island, and all 7 gates and the n-well tie were *checked*
  (`erc_coverage.checked`). The envelope's top-level `status` reads
  `not_checked` (exit 4) only because no `--pdk` antenna table is supplied;
  gate on `erc_status`. Net names are upper-case because the builders
  upper-case every drawn label (`layout/common.py`). No substrate tie is
  declared (no drawn p-well layer for `ties[]` to name). The remaining
  reason is the LVS half: the cited report's `lvs_status` is `mismatch`
  (the standing NPN13G2 decline, klayout-tools#1242; re-citation tracked in
  #381). Before #411 this item cited the **SG13CMOS5L port's** ERC report,
  which is a different PDK and layout and was never this block's evidence.
  **Re-run the ERC after any regeneration of the GDS** and re-pin both
  this citation and the report.
- **SG13CMOS5L port ERC (not cited anywhere).**
  `layout/sg13cmos5l-bandgap_top/erc_report.json` still reads
  `erc_status: "violations"` with **10 `erc.missing_tie` findings** even
  though #240 ("Zero out the 12 erc.missing_tie findings") closed on
  2026-09-23. The remaining ten are the pnpMPA wells whose correct tie is
  `vss` (needs klayout-tools#2354). That residue is *not* resolved by #240's
  closure; either reopen that work or fix it when the port is next touched.

- **Item 8 (Characterization report) — cited: `measurements/2026-11-27-characterization-report/envelope.json`**
  (#300; `generic` envelope, `t1_item: 8`, `provenance.input.path` =
  `README.md` beside it, pinned to that report's sha256). The report is
  [`measurements/2026-11-27-characterization-report/README.md`](../measurements/2026-11-27-characterization-report/README.md),
  stamped at audited commit `a1a3a3ef`. It uses the N=1,200 untrimmed
  campaign (#635) and the four limit-graded corner grids (#629), with
  one entry per row of
  the `README.md` target-spec table (the Output-reference row as its
  nominal, untrimmed and trimmed lines), each with bound, verdict, binding
  corner, whether the verdict is statistical, the newest committed `sim/`
  record behind it, and a current-or-stale mark; every quoted number is
  re-derived from its CSV by the report's `spotcheck.py`.
  **What an item 8 `met` means here — and what it does not.** It means the
  report exists, is current at the stamped commit and cites its evidence. It
  is **not** a statement that every spec row passes: the report itself
  records the trimmed ±0.5% line as measured unmet (3σ ≈ 2.4%), the PSRR
  row as not met on current evidence — and, since #629, machine-graded: the
  schematic grid's own report reads 44/45 PASS, its bcs/125 °C/3.63 V
  corner at 59.685 dB below the > 60 dB bound (design issue #631), while
  the post-layout grid that cleared it by 0.0013 dB predates the current
  extraction — and six stale records: two pre-trim-DUT PEX records waived
  under #275 in `sim/evidence-freshness-waivers.json`, three post-layout
  benches disclosed against the pre-#557 extraction (the PSRR-PEX and
  Zout-PEX grids, the startup trip-point sweep), and the pre-trim
  solver-aids A/B record, disclosed as run on the pre-trim core (2
  corners). Whether the block conforms to its spec is item 5's question,
  and item 5 stays unmet.
  **The pin binds the report, not the envelope**: the grader re-hashes the
  report file, so editing the report without regenerating the envelope and
  this manifest's pin fails `check_signoff_manifest.py` (the exact-bytes
  freshness is tested, not assumed). The pin alone would not notice the
  report's *dependencies* moving while its bytes stay put, so since #315 the
  report also carries a machine-readable dependency inventory,
  [`dependencies.json`](../measurements/2026-11-27-characterization-report/dependencies.json),
  checked by `.github/scripts/check_report_dependencies.py` (see "Item-8
  dependency drift" below): a change to an audited DUT netlist, a spec-table
  bound, a quoted decision-record status, or a newer record in a summarized
  experiment now fails CI even though the pin still matches (#303 is the
  change expected to trigger it). The nine earlier reports
  (`2026-09-characterization-report/`, `2026-10-characterization-report/`,
  `2026-11-characterization-report/`, `2026-11-04-characterization-report/`,
  `2026-11-13-characterization-report/`,
  `2026-11-16-characterization-report/`,
  `2026-11-18-characterization-report/`,
  `2026-11-18-klu-retime-characterization-report/`,
  `2026-11-22-item5-limits-characterization-report/`,
  `2026-11-23-characterization-report/`)
  are superseded and kept as history; none is required to track newer
  inputs. The list is self-maintaining by rule — every
  `measurements/*characterization-report/` directory except the one
  `evidence["8"]` pins is superseded history — so a rotation moves the
  links, the audited commit and the narrative to the incoming report and
  adds the outgoing one to the list;
  `check_report_dependencies.py` fails CI when the item-8 bullet links any
  report but the actively pinned one, or stops naming its `envelope.json`.

Items deliberately left **uncited** (they render `unmet` / `no_evidence`,
which is the honest machine-readable gap — repo evidence exists for several
of them, but no `klt` envelope grades it yet):

- **7 (Post-layout):** PEX netlists and post-layout PEX sim records exist
  (`layout/*/*.pex.spice`, `sim/closed-loop-*-pex/`) — but no `klt pex`
  delta report; item 7 rejects every other evidence kind by construction.
- **9 (Testbenches) — left uncited after the #299 audit.** The upstream
  contract now allows an artifact-anchored attestation, but the checklist
  asks for "a documented cold-start invocation **a third party can run**"
  for every claimed measurement, and this audit could not honestly attest
  that. Statically: every one of the 27 experiment directories under `sim/`
  has a `run_*.sh`, 26 open with a cold-start header, and the ratified
  spec's seven rows (Output reference, Trim, Temp coefficient, PSRR @ DC,
  Supply, Iq, Startup) each map to committed benches. Dynamically: none of
  those cold-start invocations was executed, because they are 45-point
  local `ngspice -b` grids (or N=300 Monte Carlo runs) that the dispatch
  hosts forbid hand-launching, only some experiments have a `klt sim`
  wrapper, no SG13G2 PDK or built OSDI models exist on that host, and each
  run would mint new append-only `sim/` records. A pass inferred from
  "the files exist" would be exactly the dishonest row the ladder forbids,
  so the row stays `unmet` / `no_evidence`. To close it: run each row's
  cold-start in an isolated checkout on a host with the PDK and OSDI models
  (the multi-corner ones through `klt sim`), record the outcomes in a
  `testbenches.txt` inventory, add the envelope, and bind it.
- **10 (Repo hygiene) — cited: `evidence/hygiene.json`** (#299;
  artifact-anchored `generic` envelope, `t1_item: 10`, bound to
  `evidence/hygiene.txt`). The audit found a real gap, fixed in the same
  change: the top-level `README.md` had what-the-block-is and the spec
  table but no statement of how to reproduce the results, so #299 added a
  "Reproducing the results" section (pointers to the netlist-export,
  per-experiment cold-start, layout and signoff instructions — audited for
  presence and accuracy of the pointers, **not** by re-running them). The
  inventory records the examined files with sha256s, `LICENSE` (Apache-2.0)
  and the `hygiene.yml` jobs. As with item 1, only the inventory file is
  re-hashed by the grader; edits to the listed files are not transitively
  tracked.

## Freshness and CI

Every pinned citation's `content_hash` must match both the cited envelope's
recorded `provenance.input.content_hash` **and** the sha256 of the committed
artifact that envelope names (the GDS, or for an artifact-anchored `generic`
envelope the file named by its `provenance.input.path` — a string resolves
beside the envelope, a `{path, scope: "repo"}` object against the repository
root) — a manifest citing an artifact that has since changed fails rather
than rotting. A `generic` citation for one of the artifact-anchored items
(1, 2, 9, 10 — upstream's `_ITEMS_REQUIRING_ANCHORED_GENERIC_EVIDENCE` at the
pin) must also declare the `t1_item` it is cited for, name a
`provenance.input.path`, and be pinned. A `generic` citation for item 8 may
omit `t1_item`, as upstream accepts; if it declares one, it must equal 8
(`wrong_item` otherwise), and if it is pinned and names a path, that artifact
is re-hashed the same way. Absolute or repository-escaping paths are
rejected. Native and compound (item 11) citations are checked as before. The `signoff-manifest` job in
`.github/workflows/hygiene.yml` enforces all of this:
`.github/scripts/check_signoff_manifest.py` re-runs the grade and requires
the committed `*.signoff.json` to be structurally identical to the fresh
output, and `.github/scripts/test_check_signoff_manifest.py` self-tests the
checker (a checker that cannot fail is indistinguishable from no checker).

### Item-8 dependency drift

`check_report_dependencies.py` (stdlib only, run by the PDK-free `hygiene`
job, self-tested by `test_check_report_dependencies.py`) follows
`evidence["8"]` to the cited envelope and requires a `dependencies.json`
beside it. That inventory is hand-audited, never regenerated by CI, and
records:

- `report` / `report_sha256` — the report bytes it describes (must still
  match, and match the envelope's recorded hash);
- `dut[]` — the audited DUT inputs with sha256s: the schematic netlists
  under `design/netlist/` and the extracted `*.pex.spice` the post-layout
  rows lean on. Other files under `design/` (READMEs, scripts) are not DUT
  inputs;
- `spec.table` — a **per-row normalised digest** of the `README.md`
  "Target specification" table (cells stripped, whitespace collapsed), so
  prose elsewhere in `README.md`, or re-flowing the table, does not stale
  the report while any changed bound, added or removed row does;
  `spec.decision_records[]` — the `Status:` word of each decision record the
  report quotes; `spec.absent[]` — globs the report states match nothing
  (record `0012`);
- `experiments[]` — each summarized `sim/<slug>`, its `selected_record`,
  the record files read, the spec rows it backs, and `freshness`. The
  selected record must still be the experiment's newest
  (`sorted(records/*.md)`, the ordering `check_evidence_formats.py` uses).
  `current` may not name a record `sim/evidence-freshness-waivers.json`
  waives as run on a superseded DUT; `stale` is an **honest disclosure** and
  passes, provided its `disclosure` phrase appears in the report and its
  `waiver_issue` (if any) matches a live waiver. Experiments not listed are
  not looked at.

The checker also follows the pin into **this README's own item-8 bullet**
(#647, the rotation the 2026-11-22 report exposed): the bullet must name
the actively cited `envelope.json` path, every markdown link into
`measurements/` inside it must resolve inside the actively cited report's
directory (superseded reports stay backticked names, never links), and it
must link the active report's `README.md` and `dependencies.json` — so the
next rotation cannot move the manifest pin while the heading, the links or
both keep describing the superseded report.

Every path must be repository-relative and stay inside the repository;
missing, malformed or changed inputs fail with the row or experiment they
affect. Only the actively cited report is checked; an inventory beside a
superseded report is noted, not checked. **When it fails, nothing is
regenerated automatically**: the remedy is a new dated report (the old one
is left untouched as history), a new `dependencies.json`, envelope and
manifest pin, and a regenerated `*.signoff.json`. The new report may report
stale or failing evidence as such — a completed audit is not a
circuit-performance pass, and no bound is relaxed to make it green.

### The pin

The verdict is graded against the exact upstream `klt` release recorded in
the workflow's `pip install` line (PyPI `klayout-tools==0.8.0`, tag `v0.8.0`,
commit `c572046b`). The report embeds the governing checklist's own
`source_doc_content_hash` and the build's `grading_ruleset_id`; when the pin
is bumped to a release whose checklist or ruleset differs, the committed
report stops matching and CI fails until the report is regenerated and
committed — the same "checklist moved, re-read everything" discipline the
2026-09-17 item-11 incident made necessary fleet-wide.

**Bump to 0.8.0 (from the git rev `7ee09483`, 0.7.1.dev1743)**: grading this
unchanged manifest at both gives an identical verdict — `t1_met_count` 5, items
1/2/3/8/10 `met`, 4/5/6/7/9/11 `unmet`, same `source_doc_content_hash`. Only
the `build` block changed (release version, tag, commit, `is_release: true`,
new `grading_ruleset_id`).

**What changed between the old pin (`2b1e55e5`) and `3a75c3ae`** (compared by
grading this unchanged manifest at both): the checklist is still 11 items
and every verdict is unchanged; the checklist prose of items 6 (campaign
discipline: `undersized_sample`, `negative_control_not_detected`), 8 (bare
`generic` envelopes only for item 8; anchored form for 1/2/9/10) and 11
(island/tie/roles/disclosure rules) was extended, so
`source_doc_content_hash` changed; the report gained `build`,
`build_t1_item_count`, per-item `graded_by_build` and, on pinned citations,
`input_verified`; and items 1, 2, 9, 10 can now carry an `artifact_binding`.
Native citations of those items still grade `met` but are reported as "not
bound".
