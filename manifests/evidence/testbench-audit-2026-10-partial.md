# Testbench cold-start audit — PARTIAL (issue #310)

Status: **item 9 stays uncited.** This is a progress record, not an attestation.
It is deliberately *not* bound by `manifests/sg13g2-bandgap.json` and has no
envelope. DUT revision audited: repo commit `b60f8a0c` (`design/netlist/` and
`layout/*/*.pex.spice` as committed there). Not repeated for #303 sizing.

Audit method: scratch copy of the tree (`git archive HEAD`, outside the repo),
PDK fetched fresh with `fetch-ihp-sg13g2.sh` (tarball sha256 verified against
`sim/pdk.json`), OSDI models built with `sim/tools/build-osdi.sh` (`--check`
OK), batch identity `batch-runner-submit`, klt `0.7.1.dev2517+g6bb7cf233677`.
No `ngspice -b` grid was run on the dispatch host; only the single-corner local
sanity gate and probe ran locally.

## Executed

| Spec row | Command (from scratch tree) | Outcome |
|---|---|---|
| (harness) | `sim/harness/probe/run_probe.sh --batch` | PASS (after two retries; first two submits refused by the fleet cap, below) |
| Output reference / TC / Supply, post-layout | `sim/closed-loop-vref-pvt-pex/run_klt_sim.sh --sanity`, `--batch`, `--record` | sanity PASS (vref_3ms 1.04615 V vs anchor 1.04728 V); 15 fleet jobs; **45/45 points pass** the closed-loop verdict; `vref_3ms_v` spans 1.03894–1.0495 V over the 45 points. This is a simulation outcome, not a claim that the ±0.5 % trimmed or <50 ppm/°C bounds are met — the trimmed bound is judged elsewhere (see the item-8 report). |

## Not executed — blockers, by spec row

- **Trim, Iq, Startup, PSRR (schematic), MC:** no `klt sim` wrapper exists for
  `closed-loop-iq`, `closed-loop-startup`, `closed-loop-psrr`,
  `closed-loop-vref-pvt`, `closed-loop-vref-boxtc-trim`, `closed-loop-vref-mc`,
  `closed-loop-vref-trim-mc`, `trim-coverage`, `startup-time-to-release`; each
  is a local `ngspice -b` loop the dispatch host forbids. Wrappers must be
  written first (the existing PEX wrappers cover post-layout only).
- **TC (box method), PSRR, Zout, core bias (post-layout):** wrappers exist
  (`closed-loop-vref-pvt-pex-boxtc`, `closed-loop-psrr-pex`,
  `closed-loop-zout-pex`, `core-open-loop-bias-pex`) but were not run: one grid
  took ~1.5 h of wall time here, and the 120-point box-TC grid is larger.
- **Fleet capacity:** `batch_concurrency_cap` — "N instance(s) already running
  + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8" — refused most of the
  first 15-shard submission, and the probe twice. The runner is resumable
  (submission identity, #332), so refused shards were resubmitted, not run
  locally.

## Cold-start defects found and fixed in this change

1. `--record` of every PEX wrapper refused: `klt_sim_evidence.py` needs
   `--extraction-sources`, but no runner generated or passed it.
2. `fixup_batch_report.py` rewrote only quoted `"/opt/pdk/…"` paths; klt 0.7
   writes the deck's `.lib` card unquoted, so the record step could not
   resolve the includes.
3. Unfixed: the audit record id is `…-unknown` when the scratch tree is not a
   git checkout (use a real `git clone`/worktree for the scratch tree).
