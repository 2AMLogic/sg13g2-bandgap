# 0015: sim/ evidence of new runs goes to the artifact store; git keeps a manifest

- **Status**: proposed
- **Date**: 2026-10-23
- **Decided by**: Loom Builder (agent), issue #379 (parent 2AMLogic/2am#5553)

## Context

`sim/` evidence is append-only, and `0009-sim-evidence-log-retention.md` made
the raw per-point ngspice logs under `sim/*/corners/<record-id>/` part of it:
kept verbatim and uncompressed **in git**. Its item 4 says any proposal that
changes how records are committed "must supersede this record". The working
tree now carries about 266 MB of run output (`sim/core-open-loop-bias/` 79 MB,
`sim/core-open-loop-bias-pex/` 78 MB, `sim/sg13cmos5l-core-open-loop-bias/`
19 MB, `sim/loop-gain-phase-margin/` 17 MB, `sim/closed-loop-vref-boxtc-trim/`
9 MB).

The fleet now has a common artifact store (2AMLogic/2am#5553, operator
decision 1.1, 2026-10-22): evidence bytes are **private**, manifests are
**public**, so a manifest is safe to commit to this public repo. `klt artifact
put` stores the bytes through a broker and writes a manifest that names each
object by sha256; the `uri` is the logical `artifact:<key>` only the broker
resolves (klayout-tools `docs/cli/artifact.md`, needs `7e3561f` or later).
`sg13g2-comparator` landed the reference implementation (#319, #321).

0009's revisit trigger has **not** fired. Re-measured at `b60f8a0c` on
2026-10-23: `git rev-list --disk-usage --objects HEAD -- sim` is 13.8 MiB
against the 50 MiB threshold, and `sim/` is about 27% of the 51.2 MiB
all-history figure against the 75% threshold. This record is therefore a
deliberate policy change, not the trigger firing.

## Decision

**For runs minted after this record, the raw outputs are stored in the fleet
artifact store and git keeps only a manifest and the run's summary.** 0009 is
superseded for new runs only.

1. `sim/harness/klt_sim_evidence.py` (the writer behind every
   `sim/*/run_klt_sim.sh`) stores a run's per-point logs and netlist
   snapshots with `klt artifact put` and commits
   `manifests/artifacts/<bench>-<run-id>.manifest.json`, the CSV and the
   Markdown record. The record gains a **Stored evidence** field listing
   each object's name, size and sha256. Each manifest `name` is the path the
   file would have had (`sim/<bench>/corners/<run-id>/<pt>.log`,
   `sim/<bench>/netlist-snapshots/<run-id>/<pt>.spice`).
2. **Fail closed.** With `$KLT_ARTIFACT_BROKER` unset, no `klt artifact put`
   (or a `klt` older than `7e3561f`), or an unreachable broker, the writer
   exits nonzero and writes nothing under `sim/` or `manifests/`. A put that
   fails part-way leaves no manifest. There is **no option or fallback that
   commits the bytes instead**.
3. **Manifest-forward only.** History is not rewritten. Records minted before
   this one keep their committed `corners/` and `netlist-snapshots/` trees and
   remain valid; their append-only rule is unchanged. A record is stored
   **xor** legacy: committed bytes beside a manifest are a CI failure.
4. CI checks the contract: `check_artifact_manifests.py` validates each
   manifest's schema, accepts only `artifact:` uris, and fails if a stored
   object's bytes (or the git-ignored `.evidence-scratch/` staging tree) are
   tracked; `check_evidence_formats.py` accepts a manifest-only record and
   still requires `corners/` and `netlist-snapshots/` for legacy ones. CI
   cannot hash-verify the bytes (no broker access): that is `klt artifact
   verify <manifest>` from a fleet worker.
5. Nothing in the repo names a storage bucket, account id, `s3://` uri or
   broker URL.

Items 1-4 of 0009 are otherwise untouched for legacy records. Its reasoning
about the `.op` dump still applies to what is *stored*: the full log is
uploaded, not trimmed or compressed. Its item 5 (size thresholds) does not
apply to stored runs, because their bytes are no longer in the repo, and no
size budget replaces it (manifests and summaries are small).

## Alternatives considered

- **Gzip or trim logs in git** — contradicts 0009 and does not remove the
  bytes from history.
- **Fall back to committing bytes when the broker is down** — forbidden by the
  fleet decision; it would make "evidence is stored" depend on network luck
  and silently reintroduce the problem.
- **Move existing evidence out of git** — would rewrite history or break the
  append-only rule; the legacy records stay where they are.
- **A repo-local size budget** — this repo has none and does not need one once
  new bytes stay out of git.

## Consequences

- New records are small (a manifest, a CSV, a Markdown file); the working-tree
  growth 0009 accepted stops for `run_klt_sim.sh` runs.
- Raw logs of new runs are **private**: a reader without broker access sees
  the manifest and the summary but cannot fetch the `.op` dump. The sha256
  and size in the record still pin what was run. This is a real loss of
  open reviewability for the new runs, accepted by the fleet decision.
- The D2 DUT-freshness check reads netlist snapshots from the tree; for a
  stored newest record it cannot, and reports a note ("netlist snapshots are
  in the artifact store") instead of a verdict. Freshness for such records
  is now a `klt artifact get` away, not a CI check.
- Running the writer needs `klt` at klayout-tools `7e3561f` or later and
  `$KLT_ARTIFACT_BROKER` (set for agent sessions on fleet workers); a laptop
  without it cannot mint a record.
- The older `run_pvt_sweep.sh` shell writers still commit bytes. They are
  legacy; this record does not convert them, and new evidence should use the
  `klt sim` harness.
- Not touched: the target spec, any circuit, and `manifests/klt-pin.json`
  (the signoff/layout pin is a separate build from the artifact client).
