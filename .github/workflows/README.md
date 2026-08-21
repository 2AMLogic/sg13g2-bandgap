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
  placeholder README (the current state of `sim/`, `layout/`, and
  `measurements/`) passes.

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
- Testbench or PVT-corner result formats in `sim/` — there is no `sim/`
  evidence format yet to check.
- DRC/LVS/PEX report formats or pass/fail status in `layout/` — no
  DRC/LVS/PEX artifacts exist yet.
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

As #9 (schematic), #10 (testbenches), #11 (layout), #12 (DRC/LVS), #14
(PEX), and #15 (characterization) land real artifacts, this workflow is
the natural place to add format/freshness validation for each of them
(e.g. "DRC/LVS JSON reports parse and assert `status: clean`/`status:
match`") — see issue #16 for the original scoping discussion. Extending
those checks is follow-on work, not something this workflow claims to do
yet.
