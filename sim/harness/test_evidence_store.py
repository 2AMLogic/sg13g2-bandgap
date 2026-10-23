#!/usr/bin/env python3
"""Self-test for `evidence_store.py` and the fail-closed writer (issue #379).

    python3 sim/harness/test_evidence_store.py

No broker, no network and no real `klt`: the store client is faked. The cases
prove the contract the artifact-store adoption rests on -- each of the three
preflight failures (no broker, no `klt artifact put`, unreachable broker) and a
put that fails part-way leave nothing under `sim/` or `manifests/`, and the
writer has no way to commit the bytes instead.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_store as es  # noqa: E402
import klt_sim_evidence as kse  # noqa: E402

SPEC = {"Experiment": "e", "Claim": "c", "PDK": "p", "request": "r",
        "Corner matrix run": "m", "pass_requires": ["vref"]}


class FakeStore(es.Store):
    """Stores nothing; mints the manifest `klt artifact put` would."""

    def __init__(self, *, preflight_error: str | None = None, fail_after: int | None = None):
        self.preflight_error = preflight_error
        self.fail_after = fail_after
        self.preflighted = 0
        self.put_names: list[str] = []

    def preflight(self, repo_root: Path) -> None:
        self.preflighted += 1
        if self.preflight_error:
            raise es.StoreError(self.preflight_error)

    def put(self, files, repo_root):
        entries = []
        for i, (path, name) in enumerate(files):
            if self.fail_after is not None and i >= self.fail_after:
                raise es.StoreError(f"klt artifact put {name} failed (exit 1): broker_down")
            sha, size = es.sha256_file(path)
            self.put_names.append(name)
            entries.append({
                "sha256": sha, "size": size, "kind": "evidence",
                "producer": {"tool": "klt", "version": "0", "loom.repo": "o/r", "commit": None},
                "uri": f"artifact:evidence/o__r/{sha[:2]}/{sha}", "name": name,
            })
        return {"schema_version": 1, "entries": sorted(entries, key=lambda e: e["name"])}, []


def tree(root: Path, *sub: str) -> dict[str, bytes]:
    out = {}
    for s in sub:
        base = root / s
        if base.exists():
            out.update({str(p.relative_to(root)): p.read_bytes()
                        for p in sorted(base.rglob("*")) if p.is_file()})
    return out


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class PreflightTests(TempDirCase):
    """Each way the store can be unavailable refuses before any work."""

    @staticmethod
    def run_ok(argv, **_kw):
        return subprocess.CompletedProcess(argv, 0, "", "")

    def test_unset_broker_refuses(self) -> None:
        with self.assertRaises(es.StoreError) as ctx:
            es.preflight(self.tmp, env={}, which=lambda _n: "/bin/klt", run=self.run_ok,
                         probe=lambda *_a: None)
        self.assertIn("KLT_ARTIFACT_BROKER", str(ctx.exception))

    def test_missing_artifact_put_refuses(self) -> None:
        env = {es.ENV_BROKER: "http://broker.invalid", es.ENV_REPO: "o/r"}
        with self.assertRaises(es.StoreError) as ctx:  # klt not installed
            es.preflight(self.tmp, env=env, which=lambda _n: None, run=self.run_ok,
                         probe=lambda *_a: None)
        self.assertIn("not on PATH", str(ctx.exception))

        def no_verb(argv, **_kw):  # an old klt: `artifact put --help` is a usage error
            return subprocess.CompletedProcess(argv, 2, "", "invalid choice: 'artifact'")

        with self.assertRaises(es.StoreError) as ctx:
            es.preflight(self.tmp, env=env, which=lambda _n: "/bin/klt", run=no_verb,
                         probe=lambda *_a: None)
        self.assertIn("no `artifact put` verb", str(ctx.exception))

    def test_unreachable_broker_refuses(self) -> None:
        env = {es.ENV_BROKER: "http://127.0.0.1:9", es.ENV_REPO: "o/r"}
        current = json.dumps({"error": {"code": "invalid_manifest",
                                        "problems": ["uri must be artifact:<key>"]}})

        def run(argv, **_kw):
            if "verify" in argv:  # a current klt rejects the legacy-scheme probe offline
                return subprocess.CompletedProcess(argv, 1, "", current)
            return subprocess.CompletedProcess(argv, 0, "", "")

        with self.assertRaises(es.StoreError) as ctx:  # the real probe, nothing listens
            es.preflight(self.tmp, env=env, which=lambda _n: "/bin/klt", run=run)
        self.assertIn("unreachable", str(ctx.exception))

    def test_old_klt_scheme_refuses(self) -> None:
        env = {es.ENV_BROKER: "http://broker.invalid", es.ENV_REPO: "o/r"}
        with self.assertRaises(es.StoreError) as ctx:  # accepts the s3 uri: too old
            es.preflight(self.tmp, env=env, which=lambda _n: "/bin/klt", run=self.run_ok,
                         probe=lambda *_a: None)
        self.assertIn("older than klayout-tools", str(ctx.exception))

    def test_broker_url_is_not_a_plain_base(self) -> None:
        with self.assertRaises(es.StoreError):
            es.probe_broker("http://user:pw@broker.invalid", "o/r")
        with self.assertRaises(es.StoreError):
            es.probe_broker("s3://bucket", "o/r")


class PutTests(TempDirCase):
    def entry(self, sha: str, size: int, name: str, uri: str | None = None) -> dict:
        return {"sha256": sha, "size": size, "kind": "evidence",
                "producer": {"tool": "klt", "version": "0", "loom.repo": "o/r", "commit": None},
                "uri": uri or f"artifact:evidence/o__r/{sha[:2]}/{sha}", "name": name}

    def fake_run(self, mutate=None, rc=0):
        def run(argv, **_kw):
            if rc:
                return subprocess.CompletedProcess(argv, rc, "", '{"error":{"code":"x","message":"y"}}')
            path, name = Path(argv[3]), argv[argv.index("--name") + 1]
            manifest = Path(argv[argv.index("--manifest") + 1])
            data = path.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            e = self.entry(sha, len(data), name)
            if mutate:
                e = mutate(e)
            doc = json.loads(manifest.read_text()) if manifest.exists() else \
                {"schema_version": 1, "entries": []}
            doc["entries"].append(e)
            manifest.write_text(json.dumps(doc))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run

    def files(self) -> list[tuple[Path, str]]:
        return [(self.write("a.log", "alpha\n"), "sim/x/corners/r/a.log"),
                (self.write("b.log", "beta\n"), "sim/x/corners/r/b.log")]

    def test_put_builds_sorted_manifest(self) -> None:
        manifest, empty = es.put_files(self.files(), self.tmp, run=self.fake_run())
        self.assertEqual([e["name"] for e in manifest["entries"]],
                         ["sim/x/corners/r/a.log", "sim/x/corners/r/b.log"])
        self.assertEqual(empty, [])
        self.assertTrue(all(e["uri"].startswith("artifact:") for e in manifest["entries"]))

    def test_failed_put_raises(self) -> None:
        with self.assertRaises(es.StoreError) as ctx:
            es.put_files(self.files(), self.tmp, run=self.fake_run(rc=1))
        self.assertIn("x: y", str(ctx.exception))

    def test_non_artifact_uri_is_rejected(self) -> None:
        bad = lambda e: {**e, "uri": "s3://bucket/key"}  # noqa: E731
        with self.assertRaises(es.StoreError):
            es.put_files(self.files(), self.tmp, run=self.fake_run(mutate=bad))

    def test_entry_not_matching_local_bytes_is_rejected(self) -> None:
        def lie(e):
            sha = "0" * 64
            return self.entry(sha, e["size"], e["name"])
        with self.assertRaises(es.StoreError) as ctx:
            es.put_files(self.files(), self.tmp, run=self.fake_run(mutate=lie))
        self.assertIn("does not match", str(ctx.exception))

    def test_empty_files_are_listed_not_stored(self) -> None:
        files = self.files() + [(self.write("c.log", ""), "sim/x/corners/r/c.log")]
        manifest, empty = es.put_files(files, self.tmp, run=self.fake_run())
        self.assertEqual(empty, ["sim/x/corners/r/c.log"])
        self.assertEqual(len(manifest["entries"]), 2)

    def test_install_manifest_never_overwrites(self) -> None:
        path = self.tmp / "manifests/artifacts/x-r.manifest.json"
        es.install_manifest({"schema_version": 1, "entries": []}, path)
        with self.assertRaises(es.StoreError):
            es.install_manifest({"schema_version": 1, "entries": []}, path)


class WriterFailClosedTests(TempDirCase):
    """`klt_sim_evidence.emit` with the store failing at each stage."""

    def setUp(self) -> None:
        super().setUp()
        self.exp = self.tmp / "sim" / "demo"

    def corner(self, temp: int) -> dict:
        return {"corner_id": f"typ/3.300V/{temp}C", "process": "typ", "temperature_c": temp,
                "supply_v": {"vdd": 3.3}, "status": "pass",
                "measurements": [{"name": "vref", "value": 1.2}],
                "artifacts": {"log": str(self.write(f"work/{temp}.log", f"log {temp}\n")),
                              "deck": str(self.write(f"work/{temp}.cir", f"* deck {temp}\nR1 a b 1\n"))}}

    def report(self) -> dict:
        return {"status": "pass", "corners": [self.corner(27), self.corner(85)]}

    def emit(self, store, rid: str = "rid1"):
        return kse.emit(self.report(), SPEC, self.exp, self.tmp, rid, store=store)

    def committed(self) -> dict[str, bytes]:
        return tree(self.tmp, "sim", "manifests")

    def test_success_commits_manifest_and_record_only(self) -> None:
        store = FakeStore()
        self.assertEqual(self.emit(store), (2, 2))
        t = self.committed()
        self.assertEqual(sorted(p for p in t if p.startswith("sim/demo/")),
                         ["sim/demo/records/rid1.csv", "sim/demo/records/rid1.md"])
        self.assertIn("manifests/artifacts/demo-rid1.manifest.json", t)
        self.assertFalse(list(self.tmp.glob("sim/demo/corners")), "raw logs must not be written")
        self.assertFalse(list(self.tmp.glob("sim/demo/netlist-snapshots")))
        self.assertEqual(len(store.put_names), 4)
        md = t["sim/demo/records/rid1.md"].decode()
        self.assertIn("**Stored evidence**", md)
        manifest = json.loads(t["manifests/artifacts/demo-rid1.manifest.json"])
        for e in manifest["entries"]:
            self.assertTrue(e["uri"].startswith("artifact:"))
            self.assertIn(f"| `{e['name']}` | {e['size']} | `{e['sha256']}` |", md)
        self.assertFalse((self.tmp / es.SCRATCH_DIR).exists(), "scratch is removed on success")

    def test_preflight_failure_writes_nothing(self) -> None:
        for why in ("no artifact broker configured (KLT_ARTIFACT_BROKER is unset)",
                    "`klt` has no `artifact put` verb",
                    "artifact broker unreachable (ConnectionRefusedError)"):
            with self.subTest(why=why):
                with self.assertRaises(SystemExit) as ctx:
                    self.emit(FakeStore(preflight_error=why))
                self.assertIn("nothing written", str(ctx.exception))
                self.assertIn(why, str(ctx.exception))
                self.assertEqual(self.committed(), {})
                self.assertFalse((self.tmp / es.SCRATCH_DIR).exists())

    def test_partial_put_failure_leaves_no_manifest_or_record(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            self.emit(FakeStore(fail_after=2))
        self.assertIn("nothing was committed", str(ctx.exception))
        self.assertEqual(self.committed(), {})
        # the staged bytes survive in the git-ignored scratch tree for a retry
        self.assertTrue((self.tmp / es.SCRATCH_DIR / "demo-rid1" / "corners").is_dir())
        self.emit(FakeStore())  # the id was released, not burned

    def test_real_klt_missing_is_a_clean_refusal(self) -> None:
        import os
        saved = os.environ.pop(es.ENV_BROKER, None)
        try:
            with self.assertRaises(SystemExit) as ctx:
                self.emit(None)  # the real Store: no broker in the environment
        finally:
            if saved is not None:
                os.environ[es.ENV_BROKER] = saved
        self.assertIn("KLT_ARTIFACT_BROKER", str(ctx.exception))
        self.assertEqual(self.committed(), {})

    def test_writer_has_no_byte_committing_option(self) -> None:
        import inspect
        params = set(inspect.signature(kse.emit).parameters)
        self.assertFalse({p for p in params if "legacy" in p or "commit" in p or "local" in p})
        src = Path(kse.__file__).read_text(encoding="utf-8")
        self.assertNotIn('experiment / "corners"', src)

    def test_existing_manifest_blocks_publication(self) -> None:
        m = self.tmp / "manifests/artifacts/demo-rid1.manifest.json"
        m.parent.mkdir(parents=True)
        m.write_bytes(b"precious")
        with self.assertRaises(SystemExit):
            self.emit(FakeStore())
        self.assertEqual(m.read_bytes(), b"precious")
        self.assertFalse((self.exp / "records" / "rid1.csv").exists())


if __name__ == "__main__":
    unittest.main()
