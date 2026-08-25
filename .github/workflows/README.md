# CI workflows

## `hygiene.yml`

Runs on every push to `main` and on every pull request. It validates repo
structure/hygiene that already exists in this repo today — nothing more.

### What it checks

- **`.github/scripts/check-decision-records.sh`** — every file in
  `spec/decision-records/*.md` (other than `TEMPLATE.md` itself) has the
  structure `TEMPLATE.md` requires: a `# NNNN: <title>` heading, the
  `- **Status**:` / `- **Date**:` / `- **Decided by**:` metadata bullets,
  and the `## Context`, `## Decision`, `## Alternatives considered`,
  `## Consequences` section headers. A record missing any of these fails
  the job with the specific field/header that's missing.
- **`.github/scripts/check-repo-structure.sh`** — `design/`, `sim/`,
  `layout/`, and `measurements/` each exist and each contain a non-empty
  `README.md` starting with a `# ` heading, per this repo's directory
  convention. It does not check the *content* of those READMEs beyond that
  — an intentionally sparse "empty until the first work lands here"
  placeholder README (the current state of `layout/` and `measurements/`;
  `sim/README.md` now documents a real evidence-record convention as of
  #10, though nothing in this workflow enforces it yet — see below) passes.

- **`.github/scripts/test_check_evidence_formats.py`** — the evidence
  checker's own self-test. It builds synthetic evidence trees in a temp
  directory, injects one defect per case (an overclaiming `Result`
  headline, a dropped per-point log, a stale report hash, a waiver with no
  tracking issue, an edited committed record, …) and asserts the checker
  rejects each one, plus that an undamaged tree passes. Runs **before** the
  checker itself: a format checker that cannot fail is indistinguishable
  from no checker at all.
- **`.github/scripts/check_evidence_formats.py`** — the evidence-format and
  freshness gate. Three things, all headless and PDK-free:
  1. **`sim/` record format** — every `sim/<slug>/records/<record-id>.md`
     against the convention `sim/README.md` documents: record-id grammar,
     required fields, the `.csv` sibling, the corner-id grammar, and the
     agreement between the record's headline (`N/M points PASS`), its parsed
     CSV, its per-point netlist snapshots and its raw logs. A record cannot
     claim a PVT point it has no log for, and cannot claim a pass count its
     own data contradicts.
  2. **Append-only evidence** — nothing under `sim/*/records/`,
     `sim/*/netlist-snapshots/` or `sim/*/corners/` may be modified or
     deleted relative to the merge base. This is why the checkout uses
     `fetch-depth: 0`.
  3. **`layout/` report format and freshness** — each `*_report.json`
     parses, names its engine and its deck by content hash, is internally
     consistent (a `clean` DRC has zero violations; a `match` LVS has zero
     mismatches), enumerates its DRC coverage gaps, and — the "staleness is
     failure" rule — records input hashes that still match the committed
     GDS / reference netlist / extracted netlist. Known-stale reports are
     waived by name, with a tracking issue, in
     `layout/evidence-freshness-waivers.json`; see `layout/README.md`.

  It deliberately does **not** demand a particular DRC/LVS *verdict*. This
  repo's LVS legitimately reads `mismatch` today for reasons documented in
  `layout/README.md`; the job here is to keep that verdict honest and fresh,
  not to demand one the deck cannot yet produce. It also never *mints*
  evidence — `sim/` results are produced deliberately on a machine with the
  PDK, never by a CI robot.

All four checks are plain bash/python3 scripts under `.github/scripts/`
(stdlib only, no venv), runnable locally the same way CI runs them:

```bash
.github/scripts/check-decision-records.sh
.github/scripts/check-repo-structure.sh
python3 .github/scripts/test_check_evidence_formats.py
python3 .github/scripts/check_evidence_formats.py
```

### What it does NOT check (known gaps)

This workflow validates hygiene of the artifacts that exist *today*. It
does **not** yet validate:

- Schematic/netlist content in `design/` (e.g. that `.sch` files netlist
  cleanly, or that symbols resolve against the SG13G2 PDK), nor that a
  committed netlist is fresh relative to its `.sch` source — the netlists
  carry no provenance hash of the schematic they came from, so the
  sha256-based freshness check used for `layout/` has nothing to compare
  against here.
- That a `sim/` record is fresh relative to the netlist it simulated. A
  record names its source git sha in prose (`- **Netlist provenance**`),
  which is not machine-comparable the way `layout/`'s recorded sha256
  hashes are. Adding a provenance hash to the record format would close
  this and is the natural next step.
- Characterization/measurement data formats in `measurements/` — empty
  until tape-out (#15).
- Markdown style/lint (line length, table formatting, etc.) on `README.md`
  or `spec/`. This was considered (via `markdownlint-cli2`) but the
  default ruleset flags dozens of pre-existing, non-broken issues across
  this repo's prose docs (long lines in decision records, compact table
  formatting, code fences without a language tag) — adding it as-is would
  make the workflow fail on content nobody considers broken, and tuning a
  bespoke ruleset was judged out of scope for this pass. A future issue
  can add markdown linting with a repo-tuned config once someone wants to
  enforce a specific style.

#9 (schematic), #10 (testbenches), #11 (layout), #12 (DRC/LVS), and #14
(PEX) have all landed real artifacts, and evidence-format + freshness
validation for the `sim/` and `layout/` classes landed as part of #4's
checklist item 10 (see issue #16 for the original scoping discussion). Only
#15 (characterization report under `measurements/`) is still open; adding
the equivalent validation once it lands is follow-on work, not something
this workflow claims to do yet.

The first run of the freshness check against `main` found a real defect
rather than passing vacuously: both cells' `pex_extract_report.json` were
produced against a GDS superseded by PR #45. That is filed as **#56** and
waived by name in `layout/evidence-freshness-waivers.json` until the
re-extraction and PEX PVT re-run land.
