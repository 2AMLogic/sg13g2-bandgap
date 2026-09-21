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
  As of the commit that added it: **tier: none — 3/11 T1 items met**. That is
  the honest state; an all-`unmet` manifest is a correct result, and nothing
  here inflates it.

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

- **Item 1 (Design sources) — cited: `layout/bandgap_top/pex_extract_report.json`**
  (`extract` envelope, `status: extracted`, input hash pinned to the
  committed `bandgap_top.gds`). `klt signoff`'s own gate binding documents
  `klt extract` as the *netlist regeneration* gate; this citation proves the
  netlist regenerates from the committed, generator-produced GDS. It does
  **not** prove the xschem-schematic→SPICE export step (`design/*.sch` →
  `design/netlist/*.spice`), for which no `klt` verb exists — that link is
  enforced instead by `check_evidence_formats.py`'s sim-DUT freshness check
  against the committed netlists.
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

Items deliberately left **uncited** (they render `unmet` / `no_evidence`,
which is the honest machine-readable gap — repo evidence exists for several
of them, but no `klt` envelope grades it yet):

- **5 (PVT corners):** the ratified spec exists
  (`spec/decision-records/0007`) and `sim/closed-loop-vref-pvt/` holds
  append-only CSV/MD corner records — but no `klt sim` corner-matrix
  envelope has ever been produced.
- **6 (Monte Carlo):** `sim/closed-loop-vref-mc/` holds an N=300 seeded
  mismatch MC with negative control (issue #215) — but no `klt yield`
  envelope.
- **7 (Post-layout):** PEX netlists and post-layout PEX sim records exist
  (`layout/*/*.pex.spice`, `sim/closed-loop-*-pex/`) — but no `klt pex`
  delta report; item 7 rejects every other evidence kind by construction.
- **8 (Characterization report):** no single aggregated per-spec-row
  characterization artifact exists yet.
- **9 (Testbenches) / 10 (Repo hygiene):** the testbenches, cold-start docs,
  README, LICENSE and CI all exist — but no `klt` envelope can attest to
  them, and a token citation would be exactly the dishonest row the ladder
  forbids.
- **11 (Power delivery, structural):** no `klt erc` supply-spec run exists;
  tracked by #225.

## Freshness and CI

Every pinned citation's `content_hash` must match both the cited envelope's
recorded `provenance.input.content_hash` **and** the sha256 of the committed
artifact that envelope names (the GDS) — a manifest citing an artifact that
has since changed fails rather than rotting. The `signoff-manifest` job in
`.github/workflows/hygiene.yml` enforces all of this:
`.github/scripts/check_signoff_manifest.py` re-runs the grade and requires
the committed `*.signoff.json` to be structurally identical to the fresh
output, and `.github/scripts/test_check_signoff_manifest.py` self-tests the
checker (a checker that cannot fail is indistinguishable from no checker).

### The pin

The verdict is graded against the exact upstream `klt` build recorded in the
workflow's `pip install` line (a pinned git rev of
`2AMLogic/klayout-tools`, currently `2b1e55e5` — PyPI releases up to 0.5.0
predate T1 item 11, which the ladder added 2026-09-17 in klayout-tools#2025,
so a PyPI pin would silently grade a 10-item checklist). The report embeds
the governing checklist's own `source_doc_content_hash`; when the pin is
bumped to a rev whose checklist differs, the committed report stops matching
and CI fails until the report is regenerated and committed — the same
"checklist moved, re-read everything" discipline the 2026-09-17 item-11
incident made necessary fleet-wide.
