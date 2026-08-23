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

Both checks are plain bash scripts under `.github/scripts/`, runnable
locally the same way CI runs them:

```bash
.github/scripts/check-decision-records.sh
.github/scripts/check-repo-structure.sh
```

### What it does NOT check (known gaps)

This workflow validates hygiene of the artifacts that exist *today*. It
does **not** yet validate:

- Schematic/netlist content in `design/` (e.g. that `.sch` files netlist
  cleanly, or that symbols resolve against the SG13G2 PDK).
- Testbench or PVT-corner result formats in `sim/` — `sim/README.md`
  documents a real evidence-record convention (record IDs, corner-id
  grammar, append-only rule) as of #10, and one testbench
  (`sim/core-open-loop-bias/`) already produces records against it, but
  this workflow does not yet parse or enforce that convention (e.g. no
  append-only check comparable to gf180-bandgap's `sim/check_records.py`
  lint step).
- DRC/LVS/PEX report formats or pass/fail status in `layout/` — clean
  `drc_report.json`, `lvs_report.json`, `pex_extract_report.json`, and
  `*.pex.spice` are now committed under `layout/bandgap_core/` and
  `layout/bandgap_startup/` (as of #11/#12/#14), but this workflow does not
  yet parse or validate their content.
- Characterization/measurement data formats in `measurements/` — empty
  until tape-out.
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
(PEX) have all landed real artifacts; only #15 (characterization report
under `measurements/`) is still open. For each of the landed artifact
classes, this workflow is the natural place to add format/freshness
validation (e.g. "DRC/LVS JSON reports parse and assert `status:
clean`/`status: match`") — see issue #16 for the original scoping
discussion. Extending those checks, and adding the equivalent validation
once #15 lands, is follow-on work, not something this workflow claims to
do yet.
