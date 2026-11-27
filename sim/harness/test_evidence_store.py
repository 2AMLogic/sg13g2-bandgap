#!/usr/bin/env python3
"""Self-test for `evidence_store.py` and the fail-closed writer (issue #379).

    python3 sim/harness/test_evidence_store.py

No broker, no network and no real `klt`: the store client is faked. The cases
prove the contract the artifact-store adoption rests on -- each of the three
preflight failures (no broker, no `klt artifact put`, unreachable broker) and a
put that fails part-way leave nothing under `sim/` or `manifests/`, and the
writer has no way to commit the bytes instead.

`ProbeEvidenceStepTests` replays the harness self-test's evidence step
(issue #728) over a synthetic one-corner run: it must reach a manifest-backed
scratch record that the production `check_record()` accepts, without reaching
the production store whatever `KLT_ARTIFACT_BROKER` is set to.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
                         ["sim/demo/records/rid1-report.json", "sim/demo/records/rid1.csv",
                          "sim/demo/records/rid1.md"])
        # Design call (#629): the run's own report is committed even when no
        # `report_path` is supplied (there is then simply nothing to scrub).
        self.assertEqual(json.loads(t["sim/demo/records/rid1-report.json"])["status"], "pass")
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

    def test_committed_report_is_scrubbed_of_host_paths(self) -> None:
        work = self.tmp / "work"
        work.mkdir(parents=True, exist_ok=True)
        rep = work / "report.json"
        rep.write_text("{}", encoding="utf-8")
        self.assertEqual(
            kse.emit(self.report(), SPEC, self.exp, self.tmp, "rid1", store=FakeStore(),
                     report_path=rep), (2, 2))
        text = (self.exp / "records" / "rid1-report.json").read_text(encoding="utf-8")
        self.assertNotIn(str(work.resolve()), text)
        self.assertIn("<work>/27.log", text)

    def test_existing_report_blocks_publication(self) -> None:
        r = self.exp / "records" / "rid1-report.json"
        r.parent.mkdir(parents=True)
        r.write_bytes(b"precious")
        with self.assertRaises(SystemExit):
            self.emit(FakeStore())
        self.assertEqual(r.read_bytes(), b"precious")
        self.assertFalse((self.exp / "records" / "rid1.csv").exists())
        self.assertFalse((self.tmp / "manifests/artifacts/demo-rid1.manifest.json").exists())

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


class ProbeEvidenceStepTests(TempDirCase):
    """`run_probe.sh`'s evidence step (issue #728), replayed without a simulator.

    The step is the probe's assertion 5: `kse.emit` through a probe-local store
    into a scratch repository under the probe's work directory, then the
    production `check_record()` and the DUT comparison over the snapshot the
    manifest names; the manifest itself is held to the production manifest
    schema. Everything but the run is the probe's own committed fixture
    -- its record spec, its request's measurement list, its netlist body and
    the trim subcircuit `run_probe.sh` splices out of the design netlist --
    and the checker and the reference DUT are read from the real checkout.
    Only the report and the deck `klt sim` would have written are synthetic.
    """

    RID = "20260101-000000-0000000"
    CORNER = "typ_27c_3.30v"
    CHECKOUT = Path(__file__).resolve().parents[2]
    PROBE_DIR = Path(__file__).resolve().parent / "probe"
    DEAD_BROKER = "http://127.0.0.1:9"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        loader = importlib.util.spec_from_file_location(
            "evidence_step", cls.PROBE_DIR / "evidence_step.py")
        cls.step = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(cls.step)
        scripts = cls.CHECKOUT / ".github" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        loader = importlib.util.spec_from_file_location(
            "check_artifact_manifests", scripts / "check_artifact_manifests.py")
        schema = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(schema)
        cls.manifest_problems = staticmethod(schema.manifest_problems)

    def setUp(self) -> None:
        super().setUp()
        self.work = self.tmp / "work"
        self.pdk = self.tmp / "pdk"
        self.experiment = self.work / "scratch-repo" / "sim" / "scratch-experiment"
        (self.experiment / "testbench").mkdir(parents=True)
        self.report_path = self.work / "report.json"
        spec = json.loads((self.PROBE_DIR / "record-spec.json").read_text(encoding="utf-8"))
        spec["pdk_root"] = str(self.pdk)
        self.spec_path = self.write("work/record-spec.json", json.dumps(spec))

    def write_run(self, *, work: Path | None = None, batch: bool = False, drop: str = "",
                  model_lib: bool = True, missing: str = "") -> None:
        """The probe's body, and the one-corner deck, log and report around it.

        `batch` writes the shapes the batch backend hands back: the corner
        labelled with its HBT section, and a deck whose `.include` names the
        runner instance's job directory.
        """
        work = work or self.work
        work.mkdir(parents=True, exist_ok=True)
        label = "hbt_typ" if batch else "typ"
        corner = f"{label}_27c_3.30v"
        design = (self.CHECKOUT / "design/netlist/bandgap_core.spice").read_text(encoding="utf-8")
        trim = re.search(r"^\.subckt bandgap_trim\b.*?^\.ends\s*$", design,
                        re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(trim, "the design netlist lost its `.subckt bandgap_trim` block")
        (work / "bandgap_trim.inc").write_text(trim.group(0) + "\n", encoding="utf-8")
        osdi = self.pdk / "ihp-sg13g2/libs.tech/ngspice/osdi"
        osdi.mkdir(parents=True, exist_ok=True)
        ladder = "bandgap_trim.inc" if batch else str(work / "bandgap_trim.inc")
        body = (self.PROBE_DIR / "core_open_loop_bias.body.spice").read_text(encoding="utf-8")
        body = body.replace("@@OSDI_DIR@@", str(osdi)).replace("@@TRIM_SUBCKT@@", ladder)
        lines = body.splitlines(keepends=True)
        if drop:
            lines = [line for line in lines if line.split()[:1] != [drop]]
        (work / "body.spice").write_text("".join(lines), encoding="utf-8")
        deck = ["* the corner deck `klt sim` generates around the body (synthetic)"]
        if model_lib:
            models = self.pdk / "ihp-sg13g2/libs.tech/ngspice/models/cornerHBT.lib"
            deck.append(f'.lib "{models}" {label}')
        if batch:
            deck.append(".include /instance/job/inputs/netlist.cir")
            (work / "request.json").write_text(
                json.dumps({"corners": {"process": [label]}}), encoding="utf-8")
        else:
            deck.append(f'.include "{work}/body.spice"')
        (work / f"{corner}.cir").write_text("\n".join(deck) + "\n", encoding="utf-8")
        (work / f"{corner}.log").write_text("ngspice log\n", encoding="utf-8")
        request = json.loads((self.PROBE_DIR / "request.json.tmpl").read_text(encoding="utf-8"))
        anchored = {"vref_v": 1.052707, "r1_ohm": 66057.04}
        measurements = [{"name": m["name"], "value": anchored.get(m["name"], 1.0)}
                        for m in request["measurements"] if m["name"] != missing]
        report = {"status": "pass", "corners": [{
            "corner_id": f"{label}/3.30V/27C", "process": label, "supply_v": {"Vvdd": 3.30},
            "temperature_c": 27, "status": "pass", "measurements": measurements,
            "artifacts": {"log": str(work / f"{corner}.log"), "deck": str(work / f"{corner}.cir")},
        }]}
        (work / "report.json").write_text(json.dumps(report), encoding="utf-8")
        self.report_path = work / "report.json"

    def run_step(self, broker: str | None):
        """Run the step with `KLT_ARTIFACT_BROKER` set to `broker`, or unset."""
        with mock.patch.dict(os.environ):
            os.environ.pop(es.ENV_BROKER, None)
            if broker is not None:
                os.environ[es.ENV_BROKER] = broker
            return self.step.run(self.report_path, self.spec_path, self.experiment,
                                  self.CHECKOUT, self.RID)

    def replay(self, broker: str | None = None, **run_options) -> None:
        self.write_run(**run_options)
        self.run_step(broker)

    @staticmethod
    def files_under(root: Path) -> set[str]:
        return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}

    @contextlib.contextmanager
    def production_store_guarded(self):
        """Both entry points of the real store, replaced by a failing sentinel."""
        sentinel = {"side_effect": es.StoreError("sentinel: the production store was reached")}
        with mock.patch.object(es, "preflight", **sentinel) as preflight, \
                mock.patch.object(es, "put_files", **sentinel) as put:
            yield preflight, put

    def test_stays_local_with_the_broker_unset(self) -> None:
        self.assert_stays_local(broker=None)

    def test_stays_local_with_a_failing_broker(self) -> None:
        """A configured broker is never consulted, so an unroutable one cannot bite."""
        self.assert_stays_local(broker=self.DEAD_BROKER)

    def assert_stays_local(self, broker: str | None) -> None:
        self.write_run()
        before = self.files_under(self.tmp)
        checkout_manifests = tree(self.CHECKOUT, "manifests", "artifacts")
        with self.production_store_guarded() as (preflight, put), \
                contextlib.redirect_stdout(io.StringIO()):
            store = self.run_step(broker)
        preflight.assert_not_called()
        put.assert_not_called()

        prefix = "work/scratch-repo/"
        self.assertEqual(self.files_under(self.tmp) - before, {
            f"{prefix}manifests/artifacts/scratch-experiment-{self.RID}.manifest.json",
            f"{prefix}sim/scratch-experiment/records/{self.RID}.csv",
            f"{prefix}sim/scratch-experiment/records/{self.RID}.md",
            f"{prefix}sim/scratch-experiment/records/{self.RID}-report.json",
        })
        self.assertEqual(tree(self.CHECKOUT, "manifests", "artifacts"), checkout_manifests)
        self.assertFalse((self.work / "scratch-repo" / es.SCRATCH_DIR).exists(),
                         "the staging tree must not outlive the put")

        manifest_path = (self.work / "scratch-repo/manifests/artifacts"
                         / f"scratch-experiment-{self.RID}.manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored = [f"sim/scratch-experiment/corners/{self.RID}/{self.CORNER}.log",
                  f"sim/scratch-experiment/netlist-snapshots/{self.RID}/{self.CORNER}.spice"]
        self.assertEqual([e["name"] for e in manifest["entries"]], stored)
        self.assertEqual(self.manifest_problems(manifest, "scratch-experiment", self.RID), [],
                         "the probe's manifest must be the stored-record shape")
        self.assertFalse((self.experiment / "corners").exists())
        self.assertFalse((self.experiment / "netlist-snapshots").exists())
        self.assertEqual(sorted(store.objects), stored)
        for entry in manifest["entries"]:
            data = store.objects[entry["name"]]
            self.assertEqual((hashlib.sha256(data).hexdigest(), len(data)),
                             (entry["sha256"], entry["size"]))

    def test_missing_dut_instance_fails_naming_it(self) -> None:
        """A valid record is not a complete snapshot: the DUT comparison must fire."""
        out = io.StringIO()
        with self.production_store_guarded(), contextlib.redirect_stdout(out), \
                self.assertRaises(SystemExit) as ctx:
            self.replay(drop="XQ1")
        self.assertIn("check_record() on the adapter's output: ok", out.getvalue())
        self.assertIn("does not inline the DUT's own devices", str(ctx.exception))
        self.assertIn("first missing: ['XQ1']", str(ctx.exception))

    def test_snapshot_without_a_pdk_root_model_path_fails(self) -> None:
        self.write_run(model_lib=False)
        with (self.work / "body.spice").open("a", encoding="utf-8") as body:
            body.write('* .lib "${PDK_ROOT}/ihp-sg13g2/libs.tech/ngspice/models/cornerHBT.lib" hbt_typ\n')
        out = io.StringIO()
        with self.production_store_guarded(), contextlib.redirect_stdout(out), \
                self.assertRaises(SystemExit) as ctx:
            self.run_step(None)
        self.assertIn("check_record() on the adapter's output: ok", out.getvalue())
        self.assertIn("${PDK_ROOT}", str(ctx.exception))

    def test_failed_point_fails_before_the_record_checks(self) -> None:
        """The adapter's verdict is kept: a FAIL point does not PASS the probe."""
        out = io.StringIO()
        with self.production_store_guarded(), contextlib.redirect_stdout(out), \
                self.assertRaises(SystemExit) as ctx:
            self.replay(missing="i_leg2_a")
        self.assertIn("0/1 PASS", str(ctx.exception))
        self.assertNotIn("check_record()", out.getvalue())

    def test_probe_scripts_step_five_as_written_in_both_modes(self) -> None:
        """`run_probe.sh`'s step 5, executed as written over the synthetic run."""
        script = (self.PROBE_DIR / "run_probe.sh").read_text(encoding="utf-8")
        step = script[script.index("# --- 5. "):]
        experiment = "scratch-repo/sim/scratch-experiment"
        inlined = r"^  snapshot inlines \d+ instances; 0 of the DUT's are absent$"
        for batch in (False, True):
            with self.subTest(mode="batch" if batch else "local"):
                work = self.tmp / ("batch" if batch else "local")
                self.write_run(work=work, batch=batch)
                before = self.files_under(work)
                env = {k: v for k, v in os.environ.items() if k != es.ENV_BROKER}
                env.update(WORK=str(work), SCRIPT_DIR=str(self.PROBE_DIR),
                           REPO_ROOT=str(self.CHECKOUT), BATCH_MODE=str(int(batch)),
                           PDK_ROOT=str(self.pdk), BATCH_PDK_ROOT=str(self.pdk))
                completed = subprocess.run(["bash", "-euo", "pipefail", "-c", step], env=env,
                                           capture_output=True, text=True, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                lines = completed.stdout.splitlines()
                self.assertEqual(lines[-1], f"run_probe.sh: PASS (work dir kept at {work})")
                self.assertEqual(lines[-4], "  check_record() on the adapter's output: ok")
                self.assertRegex(lines[-3], inlined)

                self.assertEqual(self.files_under(work) - before, {
                    "record-spec.json",
                    f"scratch-repo/manifests/artifacts/scratch-experiment-{self.RID}.manifest.json",
                    f"{experiment}/records/{self.RID}.csv",
                    f"{experiment}/records/{self.RID}.md",
                    f"{experiment}/records/{self.RID}-report.json",
                    f"{experiment}/run_probe_placeholder.sh",
                    f"{experiment}/testbench/core_open_loop_bias.body.spice",
                    f"{experiment}/testbench/request.json.tmpl",
                })
                for leftover in ("corners", "netlist-snapshots"):
                    self.assertFalse((work / experiment / leftover).exists())
                self.assertFalse((work / "scratch-repo" / es.SCRATCH_DIR).exists())
                manifest = json.loads((work / "scratch-repo/manifests/artifacts"
                                       / f"scratch-experiment-{self.RID}.manifest.json")
                                      .read_text(encoding="utf-8"))
                self.assertEqual(self.manifest_problems(manifest, "scratch-experiment", self.RID),
                                 [])

                with (work / experiment / "records" / f"{self.RID}.csv").open(
                        encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
                self.assertEqual([(r["status"], r["hbt_section"], r["corner_label"]) for r in rows],
                                 [("PASS", "hbt_typ", "hbt_typ" if batch else "typ")])


if __name__ == "__main__":
    unittest.main()
