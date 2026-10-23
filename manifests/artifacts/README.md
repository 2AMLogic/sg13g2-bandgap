# `manifests/artifacts/` — stored-evidence manifests

One file per stored run: `<bench>-<run-id>.manifest.json`, written by
`sim/harness/klt_sim_evidence.py` (issue #379, `spec/decision-records/0015-sim-evidence-artifact-store.md`).
Each entry names one object in the fleet artifact store by its sha256, with
`size`, `kind` (`evidence`), `producer` (`tool`, `version`, `loom.repo`,
`commit`), `uri`, and `name`, the path the bytes would have had under `sim/`.
The format is klayout-tools' `docs/cli/artifact.md`.

Evidence bytes are **private**; these manifests are **public**. A `uri` is the
logical `artifact:<key>` that only the artifact broker resolves, so a manifest
names no bucket or account. The broker URL comes from `$KLT_ARTIFACT_BROKER`
and is never written into the repo. The run's Markdown summary and CSV are
committed under `sim/<bench>/records/`.

Manifests are append-only evidence: never edit or delete one. CI runs
`python3 .github/scripts/check_artifact_manifests.py`, which checks the schema,
that every `uri` is `artifact:`, that every `name` belongs to the manifest's own
run, and that no stored object's bytes (nor the `.evidence-scratch/` staging
tree) are also tracked. It cannot reach the broker, so schema-valid is not
hash-verified: from a fleet worker, run `klt artifact verify <manifest>` (exit
`0` = every object present and matching). Requires klayout-tools `7e3561f` or
later. Records minted before DR-0015 have no manifest and keep their committed
`corners/` and `netlist-snapshots/` trees. See `sim/README.md`, "Stored
evidence".
