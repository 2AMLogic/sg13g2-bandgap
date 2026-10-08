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
  As of the commit that last regenerated it (#300): **tier: none — 5/11 T1
  items met** (items 1, 2, 3, 8, 10; read the count from the report's
  `t1_met_count`, not from this sentence). That is the honest state; an
  all-`unmet` manifest is a correct result, and nothing here inflates it.
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
- **Item 2 (Layout) — cited: `layout/bandgap_top/drc_report.json`**: proves
  the committed GDS exists and was DRC-checkable at the pinned content hash;
  the generator (`layout/bandgap_top/generate.py`) is committed and
  deterministic.
- **Item 3 (DRC clean) — cited: `layout/bandgap_top/drc_report.json`**:
  `status: clean`, input hash pinned to the current committed GDS. **DRC
  coverage disclosure (claimant-enforced, quoted from the citation's
  `coverage` block):** the curated starter deck checks 16 chapters
  (`deck_scope`: Act, Cnt, Gat, M1–M5, TM1, TM2, TV1, TV2, V1–V4); this run
  skipped 27 carried rules (`rules_skipped`, all metal3+ / topmetal / topvia
  width-space-enclosure rules — the block routes on M1/M2 only) and drew 14
  layers the deck has no rule for (`layers_in_stream_without_rules`: 5/1,
  7/0, 8/1, 8/25, 10/1, 10/25, 14/0, 28/0, 31/0, 33/0, 63/0, 111/0, 128/0,
  128/1 — marker/label/implant layers, including the EXTBlock/pSD/SalBlock
  resistor-recognition markers). A `met` here means "clean inside that
  scope", not "no DRC-expressible defect exists".
- **Item 4 (LVS clean) — cited unpinned: `layout/bandgap_top/lvs_report.json`**:
  grades `check_failed` — `status: mismatch`, honestly. Sole remaining cause
  on the SG13G2 cells: `bandgap_core`/`bandgap_top`'s three `NPN13G2`
  devices, whose recognition the curated deck permanently declines upstream
  (klayout-tools#1242); see tracker #4 and `layout/README.md`. The citation
  carries no `content_hash` pin because `klt lvs` envelopes record no
  `provenance.input` block (upstream JSON contract) — its freshness is
  enforced by `check_evidence_formats.py`'s layout-report staleness gate
  instead, which re-derives every committed report's input hashes.
- **Item 11 (Power delivery, structural) — cited as the compound pair
  `layout/sg13cmos5l-bandgap_top/erc_report.json` (pinned) +
  `layout/bandgap_top/lvs_report.json` (item 4's own, unpinned):** grades
  `check_failed`, honestly — the first item-11 citation any fleet block has
  registered (#234 closed #225; #239 registered the citation). Since #233
  declared the spec's `ties[]` entry and regenerated the report under the
  commit-pinned `klt 0.5.0+g32f69f811682`, the ERC half is **checked
  evidence with findings on record**, not a passing envelope:
  `erc_status: "violations"` with **12 `erc.missing_tie` findings** (one
  per physically distinct `NWell` island — no nSD-covered `Activ` is drawn
  inside any well; 2 floating MOS wells + 10 marker-less pnpMPA base
  rings, filed as #240 and kept, not tuned away), while the supply-island
  half stays clean (each declared supply resolves to exactly one island,
  and `gates[]`/`nets[]` findings are byte-identical to the pre-tie
  report — klayout-tools#2186's tie isolation). Both halves keep the item
  unmet: (a) the ERC half's `erc.missing_tie` count is nonzero until #240
  clears; (b) the LVS half — every declared supply paired in the cited
  report's `net_correspondence` — is not met: that report pairs only
  `d1`/`d2` (the standing NPN13G2 decline item 4 documents,
  klayout-tools#1242). `t1_met_count` is unchanged at 3. The citation's
  pin binds the ERC envelope's **input** hash (the committed GDS — the
  same convention every pinned citation uses), so it is unchanged by a
  report regeneration that does not touch the GDS; the report's own
  spec/GDS freshness anchors are what `check_evidence_formats.py`
  re-derives.

- **Item 8 (Characterization report) — cited: `measurements/2026-10-characterization-report/envelope.json`**
  (#300; `generic` envelope, `t1_item: 8`, `provenance.input.path` =
  `README.md` beside it, pinned to that report's sha256). The report is
  [`measurements/2026-10-characterization-report/README.md`](../measurements/2026-10-characterization-report/README.md),
  stamped at the audited commit `b89f4c5f`: one entry per row of the
  `README.md` target-spec table (the Output-reference row as its nominal,
  untrimmed and trimmed lines), each with bound, verdict, binding corner,
  whether the verdict is statistical, the newest committed `sim/` record
  behind it, and a current-or-"predates the current netlist" mark; every
  quoted number is re-derived from its CSV by the report's `spotcheck.py`.
  **What an item 8 `met` means here — and what it does not.** It means the
  report exists, is current at the stamped commit and cites its evidence. It
  is **not** a statement that every spec row passes: the report itself
  records the trimmed ±0.5% line as measured unmet (3σ ≈ 2.6%), the PSRR
  row as met by 0.0013 dB, and four records as stale against the
  trim-bearing netlist (`sim/evidence-freshness-waivers.json`). Whether the
  block conforms to its spec is item 5's question, and item 5 stays unmet.
  **The pin binds the report, not the envelope**: the grader re-hashes the
  report file, so editing the report without regenerating the envelope and
  this manifest's pin fails `check_signoff_manifest.py` (the exact-bytes
  freshness is tested, not assumed). Like items 1 and 10, "current" is
  attested at the stamped commit, not tracked transitively: a later change
  to `design/` or a new `sim/` record does not by itself stale the pin, so
  whoever changes the DUT must revisit the report (the report's "Gaps"
  section names #303 as the change that would force it). The September
  report (`2026-09-characterization-report/`) is superseded and kept as
  history.

Items deliberately left **uncited** (they render `unmet` / `no_evidence`,
which is the honest machine-readable gap — repo evidence exists for several
of them, but no `klt` envelope grades it yet):

- **5 (PVT corners):** the ratified spec exists
  (`spec/decision-records/0007`) and `sim/closed-loop-vref-pvt/` holds
  append-only CSV/MD corner records — joined since #236 by the box-method
  TC grid on the same 8-point corner set
  (`sim/closed-loop-vref-pvt-boxtc/`, schematic + PEX) — but no `klt sim`
  corner-matrix envelope has ever been produced.
- **6 (Monte Carlo):** `sim/closed-loop-vref-mc/` holds an N=300 seeded
  mismatch MC with negative control (issue #215) — but no `klt yield`
  envelope.
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

### The pin

The verdict is graded against the exact upstream `klt` build recorded in the
workflow's `pip install` line (a pinned git rev of
`2AMLogic/klayout-tools`, currently `3a75c3ae` — the merge of
klayout-tools#2718, artifact-anchored `generic` evidence for items 1, 2, 9
and 10; PyPI releases up to 0.5.0 predate T1 item 11, which the ladder added
2026-09-17 in klayout-tools#2025, so a PyPI pin would silently grade a
10-item checklist). The report embeds the governing checklist's own
`source_doc_content_hash`; when the pin is bumped to a rev whose checklist
differs, the committed report stops matching and CI fails until the report
is regenerated and committed — the same "checklist moved, re-read
everything" discipline the 2026-09-17 item-11 incident made necessary
fleet-wide.

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
