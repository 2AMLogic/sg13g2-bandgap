# sg13g2-bandgap — agent instructions

Open-source canary block: a bandgap voltage reference on IHP SG13G2, a 130 nm
SiGe BiCMOS open PDK, designed and verified by AI agents.

- **PDK**: IHP SG13G2 (open PDK, IHP-GmbH/IHP-Open-PDK). Open-source flow:
  xschem + ngspice for design/sim, klayout-tools (`klt`) for layout work.
- **The deck is new — starter-grade.** `klt` resolves this PDK (the resolver
  gap, klayout-tools #522, is closed) and a curated SG13G2 DRC/LVS starter
  deck ships with klayout-tools (klayout-tools #905/#911) — but that deck is
  young and has met almost no real blocks. Expect deck gaps as normal
  friction: a rule it cannot check yet, an LVS device it does not extract, a
  waiver it lacks. File each one upstream per the friction protocol below
  rather than routing around it — working around a deck gap silently destroys
  the reason this repo was opened. **Design work here is no longer gated on
  the resolver**: the porting plan (#3) proceeds to actual schematics and sim.
- **The PDK is the variable, not the design.** This block is a port of the
  fleet's most mature design (`gf180-bandgap`, `sky130-bandgap`) *on purpose*.
  Anything that breaks should be assumed to be the PDK, the deck, or the
  tools before it is assumed to be the circuit. Start from the sibling
  repos' schematics and decision records rather than from a blank page.
- **BiCMOS is a real difference.** SG13G2 offers actual bipolar devices rather
  than the parasitic PNPs the CMOS ports rely on. That changes the circuit's
  options and gives extraction and LVS a device class they have not handled
  here. Expect friction there specifically.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue at
  `2AMLogic/klayout-tools` describing the tool gap generically — that tracker
  is scoped to the tool, so keep design-specific detail out of it and describe
  the gap, not the design.
- **Verification is the product**: no claim without a testbench. PVT corners
  on every recorded result; `sim/` results are append-only evidence.
- Spec changes go through `spec/` with a decision record; agents do not relax
  the ratified spec to make results pass.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->

<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.10.0 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
