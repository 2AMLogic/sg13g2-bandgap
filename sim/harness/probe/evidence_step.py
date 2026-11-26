#!/usr/bin/env python3
"""The evidence step of the `klt sim` harness self-test (issue #728).

    python3 sim/harness/probe/evidence_step.py --report R --spec S \
        --experiment <scratch root>/sim/<name> --checkout C --record-id I

`run_probe.sh` calls this once per mode, after `klt sim` has written its
report. It is the probe's assertion 5: the adapter
(`sim/harness/klt_sim_evidence.py`) publishes that report as a stored record,
the production record checker accepts it, and the snapshot the record's
manifest names inlines the DUT.

The record is scratch, and the step keeps it that way:

* Nothing reaches the fleet. The adapter takes its store as an argument, so
  the step hands it :class:`ProbeStore`: it keeps the bytes it is handed and
  makes no `klt artifact` call, with `KLT_ARTIFACT_BROKER` unset or set.
* Nothing lands in the checkout. The adapter installs the manifest under the
  repository root it is given, and the checker looks for it under
  `experiment.parents[1]`. The step derives that root from the experiment, so
  the two are the same directory -- a scratch root under the probe's work
  directory -- and the record is manifest-backed the way every DR-0015
  record is, without a real `manifests/artifacts/` being touched.

The real checkout (`--checkout`, the one `run_probe.sh` runs from) supplies
what must not be faked: the checker itself,
`.github/scripts/check_evidence_formats.py`, and the reference DUT,
`design/netlist/bandgap_core.spice`.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import evidence_store as es  # noqa: E402
import klt_sim_evidence as kse  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402

PROBE = "run_probe.sh"
CHECKER = Path(".github") / "scripts" / "check_evidence_formats.py"
DUT_NETLIST = Path("design") / "netlist" / "bandgap_core.spice"
PRODUCER = {"tool": PROBE, "version": None, "loom.repo": None, "commit": None}


class ProbeStore(es.Store):
    """The adapter's store, standing in for `klt artifact put` beside the probe.

    `put` is handed each staged file under the manifest name `klt` would have
    minted. It returns the manifest `klt` would have written, so the production
    record checker exercises its stored-record branch on a faithful shape, and
    keeps the bytes in :attr:`objects` for the step to read back. It runs no
    `klt` and opens no connection. As in :func:`evidence_store.put_files`, a
    zero-byte file is listed rather than stored. An entry says what it is: the
    probe as producer, a `probe/` key namespace -- nothing was put by `klt`,
    and nothing is in the fleet store.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def preflight(self, repo_root: Path) -> None:
        """There is nothing to reach, so there is nothing to find unavailable."""

    def put(self, files: list[tuple[Path, str]], repo_root: Path) -> tuple[dict, list[str]]:
        names = [name for _, name in files]
        if len(set(names)) != len(names):
            raise es.StoreError("two staged files map to the same evidence name")
        kept = {name: Path(path).read_bytes() for path, name in files}
        if not any(kept.values()):
            raise es.StoreError("nothing to store: every staged file is empty")
        entries = []
        empty = []
        for name, data in kept.items():
            if not data:
                empty.append(name)
                continue
            sha = hashlib.sha256(data).hexdigest()
            self.objects[name] = data
            entries.append({
                "sha256": sha, "size": len(data), "kind": "evidence", "producer": PRODUCER,
                "uri": f"artifact:probe/{sha[:2]}/{sha}", "name": name,
            })
        manifest = {"schema_version": 1, "entries": sorted(entries, key=lambda e: e["name"])}
        return manifest, sorted(empty)


def load_checker(checkout: Path):
    """Import the production record checker, unmodified, from the real checkout."""
    scripts = str(checkout / CHECKER.parent)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from _ci_common import Report

    loader = importlib.util.spec_from_file_location("check_evidence_formats", checkout / CHECKER)
    checker = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(checker)
    return checker, Report


def check_record(checker, Report, experiment: Path, rid: str) -> None:
    """Fail unless the production record checker accepts the scratch record."""
    report = Report()
    checker.check_record(experiment / "records" / f"{rid}.md", experiment, report)
    for problem in report.problems:
        print("  record-format FAIL:", problem)
    if report.problems:
        raise SystemExit(f"{PROBE}: the adapter's record does not satisfy check_record()")
    print("  check_record() on the adapter's output: ok")


def verify_snapshots(checker, checkout: Path, experiment: Path, rid: str,
                      store: ProbeStore) -> None:
    """Fail unless every snapshot the manifest names inlines the DUT, host-path-free."""
    manifest_path = es.manifest_path(experiment.parents[1], experiment.name, rid)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prefix = f"sim/{experiment.name}/{checker.SNAPSHOT_DIR}/{rid}/"
    snapshots = [e["name"] for e in manifest["entries"]
                 if e["name"].startswith(prefix) and e["name"].endswith(".spice")]
    if not snapshots:
        raise SystemExit(f"{PROBE}: the manifest names no netlist snapshot under {prefix}")
    dut = checker.spice_instances((checkout / DUT_NETLIST).read_text(encoding="utf-8"))
    for name in snapshots:
        snapshot = store.objects[name].decode("utf-8")
        devices = checker.spice_instances(snapshot)
        absent = [instance for instance in dut if instance not in devices]
        print(f"  snapshot inlines {len(devices)} instances; "
              f"{len(absent)} of the DUT's are absent")
        if absent:
            raise SystemExit(
                f"{PROBE}: the snapshot does not inline the DUT's own devices, so the D2 "
                f"freshness rule cannot see them (first missing: {absent[:5]})"
            )
        if kse.PDK_ROOT_PLACEHOLDER not in snapshot:
            raise SystemExit(
                f"{PROBE}: snapshot carries no ${{PDK_ROOT}}-relative model-library card"
            )
    print("  snapshot is self-contained and host-path-free: ok")


def run(report_path: Path, spec_path: Path, experiment: Path, checkout: Path, rid: str,
        *, store: ProbeStore | None = None) -> ProbeStore:
    """Publish `report_path` as scratch record `rid`, then assert 5 on it.

    `experiment` is `<scratch root>/sim/<name>` under the probe's work
    directory; `checkout` is the real checkout. Returns the store holding the
    run's bytes.
    """
    report = json.loads(report_path.read_text(encoding="utf-8"))
    mbs.refresh_rollup(report)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    experiment = experiment.resolve()
    store = store or ProbeStore()

    passed, total = kse.emit(report, spec, experiment, experiment.parents[1], rid,
                             store=store, report_path=report_path)
    print(f"klt_sim_evidence.py: {passed}/{total} PASS -> {experiment.name}/records/{rid}.md")
    if passed != total:
        raise SystemExit(f"{PROBE}: the adapter graded the run {passed}/{total} PASS")

    checker, Report = load_checker(checkout)
    check_record(checker, Report, experiment, rid)
    verify_snapshots(checker, checkout, experiment, rid, store)
    return store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", required=True, help="the `klt sim` JSON report")
    parser.add_argument("--spec", required=True, help="the probe's record spec JSON")
    parser.add_argument("--experiment", required=True, help="<scratch root>/sim/<name>")
    parser.add_argument("--checkout", required=True, help="the real checkout")
    parser.add_argument("--record-id", required=True)
    args = parser.parse_args(argv)
    run(Path(args.report), Path(args.spec), Path(args.experiment), Path(args.checkout),
        args.record_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
