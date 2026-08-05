# sg13g2-bandgap — agent instructions

Open-source canary block: a bandgap voltage reference on IHP SG13G2, a 130 nm
SiGe BiCMOS open PDK, designed and verified by AI agents.

- **PDK**: IHP SG13G2 (open PDK, IHP-GmbH/IHP-Open-PDK). Open-source flow:
  xschem + ngspice for design/sim, klayout-tools (`klt`) for layout work.
- **BLOCKED: `klt` cannot resolve this PDK yet.** `klt pdk` handles only the
  open_pdks layout, and lambdapdk's `ihp130` tree is not SG13G2. Resolver
  support is the blocking prerequisite. Until it lands, work here is limited
  to specification and porting-plan documents.
  **Do not hand-wire paths around the resolver.** That gap is precisely the
  friction this repo exists to surface; file it and fix it upstream rather
  than routing past it, because routing past it destroys the reason the repo
  was opened.
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
