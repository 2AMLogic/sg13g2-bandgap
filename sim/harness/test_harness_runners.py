#!/usr/bin/env python3
"""Integration tests for the klt-sim shell runners and submission identity.

The tests exercise the runner scripts with fixture reports and a mock klt.
Run from the repository root with python3 sim/harness/test_harness_runners.py.
"""

from __future__ import annotations

import ast
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixup_batch_report as fbr
import submission_identity as si

HARNESS = Path(__file__).resolve().parent
SIM_DIR = HARNESS.parent


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


def report_of(corners: list[dict]) -> dict:
    counts = Counter(c["status"] for c in corners)
    status = "fail" if counts["fail"] else "error" if counts["error"] else "pass"
    return {
        "status": status,
        "corner_count": len(corners),
        "passed": counts["pass"],
        "failed": counts["fail"],
        "errored": counts["error"],
        "corners": corners,
        "provenance": {"klt_version": "0.5.0"},
    }


# --------------------------------------------------------------------------
# submission identity / resumable shards (#332)
# --------------------------------------------------------------------------

MOCK_KLT = """#!/usr/bin/env bash
# mock `klt`: counts submissions, writes a passing report, runs no simulator
if [[ "$1" == "--version" ]]; then echo "mock-klt 1.0"; exit 0; fi
echo "$2" >> "${MOCK_COUNT}"
echo '{"status": "pass", "corners": [{"corner_id": "typ/27C", "artifacts": {"deck": "deck.cir"}}]}'
"""


class ResumeIdentityTests(TempDirCase):
    def setUp(self) -> None:
        super().setUp()
        self.klt = self.write("bin/klt", MOCK_KLT)
        self.klt.chmod(0o755)
        self.count = self.tmp / "count.txt"
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.tmpl = self.write("tmpl/body.tmpl", "* template v1\n.include @@PEX@@\n")
        self.extraction = "R1 a b 1\n"
        self.make_inputs()

    def make_inputs(self, template=None, extraction=None, body_extra="", measure="vref_v",
                    axis=(-40, 27)) -> None:
        """Mimic a runner's regeneration of body / PEX include / request."""
        if template is not None:
            self.tmpl.write_text(template, encoding="utf-8")
        (self.work / "pex_body.inc").write_text(extraction or self.extraction, encoding="utf-8")
        body = self.tmpl.read_text().replace("@@PEX@@", "pex_body.inc") + body_extra
        (self.work / "body-typ.spice").write_text(body, encoding="utf-8")
        req = {"netlist": str(self.work / "body-typ.spice"),
               "corners": {"temperature_c": list(axis)},
               "measurements": [{"name": measure, "spice": f".meas tran {measure} find v(a) at=1m"}]}
        (self.work / "request-typ.json").write_text(json.dumps(req), encoding="utf-8")

    def shard(self, **env) -> subprocess.CompletedProcess:
        script = (
            f'set -euo pipefail; WORK="{self.work}"; HARNESS_DIR="{HARNESS}"; KLT_BIN="{self.klt}"; '
            f'IDENT_ARGS=(--declare "klt_version=mock" --extra "{self.tmpl}"); '
            f'source "{HARNESS}/submission_identity.sh"; '
            'si_shard request-typ.json report-typ.json artifacts-typ "typ (test)"'
        )
        e = {**os.environ, "MOCK_COUNT": str(self.count)}
        e.pop(si.ENV_ALLOW_LEGACY, None)
        e.pop(si.ENV_REDISPATCH, None)
        e.update(env)
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e)

    def submissions(self) -> int:
        return len(self.count.read_text().split()) if self.count.exists() else 0

    def first_run(self) -> None:
        r = self.shard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 1)
        self.assertTrue(si.sidecar_path(self.work / "report-typ.json").is_file())

    def test_unchanged_resume_reuses_without_redispatch(self) -> None:
        self.first_run()
        self.make_inputs()  # regeneration is byte-identical
        r = self.shard()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 1)
        self.assertIn("skipping", r.stdout)

    def test_mutations_invalidate_reuse(self) -> None:
        cases = {
            "template": dict(template="* template v2\n.include @@PEX@@\n"),
            "included extraction": dict(extraction="R1 a b 2\n"),
            "request measurement": dict(measure="vref_other"),
            "request axis": dict(axis=(-40, 27, 125)),
            "generated body": dict(body_extra=".param x=1\n"),
        }
        for name, mut in cases.items():
            with self.subTest(name):
                self.setUp()
                self.first_run()
                self.make_inputs(**mut)
                r = self.shard()
                self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
                self.assertEqual(self.submissions(), 1)  # refused, not silently reused
                self.assertIn("different inputs", r.stderr)
                self.assertIn("new work dir", r.stderr.lower())
                self.tearDown()

    def test_stale_redispatch_opt_in_resubmits_and_rebinds(self) -> None:
        self.first_run()
        self.make_inputs(extraction="R1 a b 2\n")
        r = self.shard(**{si.ENV_REDISPATCH: "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 2)
        self.assertEqual(self.shard().returncode, 0)  # now bound to the new inputs
        self.assertEqual(self.submissions(), 2)

    def test_declared_identity_change_invalidates(self) -> None:
        self.first_run()
        r = subprocess.run(
            [sys.executable, str(HARNESS / "submission_identity.py"), "check",
             str(self.work / "request-typ.json"), str(self.work / "report-typ.json"),
             "--declare", "klt_version=other", "--extra", str(self.tmpl)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, si.EXIT_REFUSE)
        self.assertIn("declared", r.stderr)

    def test_seed_renderer_provenance_on_resume(self) -> None:
        request = self.work / "request-typ.json"
        report = self.work / "report-typ.json"
        seeds = self.write("seeds.csv", "corner_label,temp_c\ntyp,27\n")
        renderer = self.write("seed_deck.py", (HARNESS / "seed_deck.py").read_text())
        old_extras = [self.tmpl, seeds]
        extras = [*old_extras, renderer]

        def bind(files: list[Path]) -> None:
            si.begin(request, report, files, {})
            report.write_text('{"status": "pass"}')
            si.commit(report)

        bind(old_extras)
        self.assertEqual(si.check(request, report, old_extras, {}, env={})[0], si.EXIT_REUSE)
        self.assertEqual(si.check(request, report, extras, {}, env={})[0], si.EXIT_REFUSE)
        bind(extras)
        self.assertEqual(si.check(request, report, extras, {}, env={})[0], si.EXIT_REUSE)
        with renderer.open("a") as f:
            f.write("\n# renderer edit\n")
        rc, message = si.check(request, report, extras, {}, env={})
        self.assertEqual(rc, si.EXIT_REFUSE)
        self.assertIn("changed: extras", message)

    def test_legacy_report_without_sidecar_is_refused_not_trusted(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "pass"}')
        r = self.shard()
        self.assertEqual(r.returncode, 4)
        self.assertEqual(self.submissions(), 0)
        self.assertIn("no committed submission identity", r.stderr)

    def test_legacy_report_explicit_opt_in_reuses_with_warning(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "pass"}')
        r = self.shard(**{si.ENV_ALLOW_LEGACY: "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.submissions(), 0)
        self.assertIn("UNBOUND", r.stdout)

    def test_sidecar_only_written_after_submission_completes(self) -> None:
        report = self.work / "report-typ.json"
        si.begin(self.work / "request-typ.json", report, [], {})
        self.assertFalse(si.sidecar_path(report).exists())
        self.assertTrue(si.pending_path(report).exists())
        # a pending identity never authorises reuse
        report.write_text('{"status": "pass"}')
        rc, _ = si.check(self.work / "request-typ.json", report, [], {}, env={})
        self.assertEqual(rc, si.EXIT_REFUSE)
        # no report written => commit refuses and no sidecar appears
        report.unlink()
        with self.assertRaises(si.IdentityError):
            si.commit(report)
        self.assertFalse(si.sidecar_path(report).exists())

    def test_inputs_changing_during_submission_are_not_committed(self) -> None:
        report = self.work / "report-typ.json"
        si.begin(self.work / "request-typ.json", report, [], {})
        report.write_text('{"status": "pass"}')
        (self.work / "pex_body.inc").write_text("R1 a b 99\n")
        with self.assertRaises(si.IdentityError):
            si.commit(report)
        self.assertFalse(si.sidecar_path(report).exists())

    def test_non_pass_report_is_redispatched(self) -> None:
        (self.work / "report-typ.json").write_text('{"status": "fail"}')
        self.assertEqual(self.shard().returncode, 0)
        self.assertEqual(self.submissions(), 1)

    def test_fixup_snapshots_original_submitted_body_not_regenerated(self) -> None:
        self.first_run()
        report = self.work / "report-typ.json"
        deck = self.work / "deck.cir"
        deck.write_text('.include "/var/tmp/eda-job-1/inputs/netlist.cir"\n')
        # the world moves on after submission: body, include, template regenerate
        self.make_inputs(template="* CHANGED\n.include @@PEX@@\n", extraction="R1 a b 777\n")
        out = self.tmp / "fixed"
        rc = fbr.main([str(report), "--runner-pdk-root", "/opt/pdk", "--local-pdk-root", "/p",
                       "--decks-out", str(out), "-o", str(self.tmp / "fixed.json")])
        self.assertEqual(rc, 0)
        fixed = json.loads((self.tmp / "fixed.json").read_text())
        deck_text = Path(fixed["corners"][0]["artifacts"]["deck"]).read_text()
        body_path = Path(deck_text.split('"')[1])
        self.assertIn("template v1", body_path.read_text())
        self.assertNotIn("CHANGED", body_path.read_text())
        self.assertEqual((body_path.parent / "pex_body.inc").read_text(), self.extraction)

    def test_fixup_refuses_tampered_snapshot_and_unbound_report(self) -> None:
        self.first_run()
        report = self.work / "report-typ.json"
        (si.snapshot_dir(report) / "closure" / "pex_body.inc").write_text("tampered")
        with self.assertRaises(SystemExit):
            fbr.main([str(report), "--local-pdk-root", "/p", "--decks-out",
                      str(self.tmp / "o"), "-o", str(self.tmp / "o.json")])
        legacy = self.work / "report-legacy.json"
        legacy.write_text('{"status": "pass", "corners": []}')
        body = self.write("b.spice", "x")
        with self.assertRaises(SystemExit):  # regenerated --body alone is not accepted
            fbr.main([str(legacy), "--body", str(body), "--local-pdk-root", "/p",
                      "--decks-out", str(self.tmp / "o2"), "-o", str(self.tmp / "o2.json")])
        self.assertEqual(fbr.main([str(legacy), "--body", str(body), "--allow-unbound",
                                   "--local-pdk-root", "/p", "--decks-out", str(self.tmp / "o3"),
                                   "-o", str(self.tmp / "o3.json")]), 0)


# --------------------------------------------------------------------------
# PWL-ramp PEX runners' merge call (issue #331): the real shell helper both
# runners source, driven against synthetic fixed shard reports.
# --------------------------------------------------------------------------

LABELS = ("typ", "bcs", "wcs", "sf", "fs")
HBT = {"typ": "hbt_typ", "bcs": "hbt_bcs", "wcs": "hbt_wcs", "sf": "hbt_typ", "fs": "hbt_typ"}
SUPPLIES = ("2.97", "3.30", "3.63")
PEX_RUNNERS = {
    "closed-loop-vref-pvt-pex": "closed_loop_vref_pvt_pex",
    "closed-loop-psrr-pex": "closed_loop_psrr_pex",
}


class PexMergeCallTests(TempDirCase):
    def template(self, exp: str) -> Path:
        return SIM_DIR / exp / "testbench" / f"{PEX_RUNNERS[exp]}.request.json.tmpl"

    def temps(self, exp: str) -> list:
        return json.loads(self.template(exp).read_text())["corners"]["temperature_c"]

    def shards(self, exp: str, skip: tuple = (), dup: tuple = ()) -> Path:
        """Per-(label, vdd) `-fixed` reports as the runner leaves them: no
        supply axis (the ramp is baked in); vref_v encodes the shard's vdd."""
        d = self.tmp / "work"
        d.mkdir(exist_ok=True)
        for label in LABELS:
            for vdd in SUPPLIES:
                if (label, vdd) in skip:
                    continue
                corners = [
                    {
                        "corner_id": f"{HBT[label]}/novdd/{t:g}C",
                        "process": HBT[label],
                        "temperature_c": t,
                        "status": "pass",
                        "measurements": [{"name": "vref_v", "value": float(vdd)}],
                    }
                    for t in self.temps(exp)
                ]
                if (label, vdd) in dup:
                    corners = corners + corners[:1]
                rep = report_of(corners)
                (d / f"report-{label}-{vdd.replace('.', 'p')}-fixed.json").write_text(json.dumps(rep))
        return d

    def call(self, exp: str, work: Path, fn: str = "pex_merge_shards") -> subprocess.CompletedProcess:
        out = self.tmp / "report-merged.json"
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'source "$HARNESS_DIR/pex_merge_call.sh"; '
            f'CORNER_LABELS=({" ".join(LABELS)}); VDDS=({" ".join(SUPPLIES)}); '
            f'{fn} "{self.template(exp)}" "{work}" "{out}"'
        )
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    def test_complete_grid_merges_then_reaches_enrichment(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                r = self.call(exp, work)
                self.assertEqual(r.returncode, 0, r.stderr)
                merged = json.loads((self.tmp / "report-merged.json").read_text())
                n = len(LABELS) * len(SUPPLIES) * len(self.temps(exp))
                self.assertEqual(merged["corner_count"], n)
                self.assertTrue(merged["grid"]["complete"])
                self.assertEqual(len(merged["grid"]["expected"]), n)
                enriched = self.tmp / "report-enriched.json"
                e = subprocess.run(
                    [sys.executable, str(SIM_DIR / "harness" / "enrich_pvt_report.py"),
                     str(self.tmp / "report-merged.json"), "-o", str(enriched)],
                    capture_output=True, text=True, cwd=self.tmp,
                )
                self.assertEqual(e.returncode, 0, e.stderr)
                self.assertTrue(enriched.exists())
                (self.tmp / "report-merged.json").unlink()

    def test_supply_hint_matches_each_shards_declared_supply(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                r = self.call(exp, work, "pex_merge_args")
                self.assertEqual(r.returncode, 0, r.stderr)
                args = r.stdout.splitlines()
                shard_args = [a for a in args if "@" in a]
                self.assertEqual(len(shard_args), len(LABELS) * len(SUPPLIES))
                for a in shard_args:
                    spec, path = a.split("=", 1)
                    label, vdd = spec.split("@")
                    self.assertTrue(path.endswith(f"report-{label}-{vdd.replace('.', 'p')}-fixed.json"), a)
                # End to end: every merged corner's baked vdd (vref_v) equals
                # the supply identity the hint gave it.
                self.assertEqual(self.call(exp, work).returncode, 0)
                merged = json.loads((self.tmp / "report-merged.json").read_text())
                ids = merged["grid"]["expected"]
                for c, ident in zip(merged["corners"], ids):
                    self.assertTrue(ident.endswith(f"_{c['measurements'][0]['value']:.2f}v"), ident)
                axes = args[args.index("--expect-process") + 1], args[args.index("--expect-supplies") + 1]
                self.assertEqual(axes, (",".join(LABELS), ",".join(SUPPLIES)))
                self.assertIn(
                    "--expect-temps=" + ",".join(f"{t:g}" for t in self.temps(exp)), args)
                (self.tmp / "report-merged.json").unlink()

    def test_omitted_shard_rejected_before_publication(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp)
                (work / "report-wcs-3p63-fixed.json").unlink()
                r = self.call(exp, work)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_shard_missing_a_point_rejected(self) -> None:
        exp = "closed-loop-vref-pvt-pex"
        work = self.shards(exp)
        f = work / "report-fs-2p97-fixed.json"
        rep = json.loads(f.read_text())
        rep["corners"].pop()
        f.write_text(json.dumps(report_of(rep["corners"])))
        r = self.call(exp, work)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing", r.stderr)
        self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_duplicate_identities_rejected(self) -> None:
        for exp in PEX_RUNNERS:
            with self.subTest(exp=exp):
                work = self.shards(exp, dup=(("typ", "3.30"),))
                r = self.call(exp, work)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("duplicate", r.stderr)
                self.assertFalse((self.tmp / "report-merged.json").exists())

    def test_runners_no_longer_call_merger_without_a_grid(self) -> None:
        # The merge call lives once, in the shared driver every PEX runner sources.
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        self.assertIn("pex_merge_shards", driver)
        self.assertNotIn("merge_batch_shards.py", driver)
        for exp in PEX_RUNNERS:
            text = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
            self.assertIn("harness/pex_runner.sh", text)
            self.assertNotIn("merge_batch_shards.py", text.replace("(sim/harness/merge_batch_shards.py)", ""))


# --------------------------------------------------------------------------
# submission_identity.sh si_set_* -- concurrent `klt sim --batch-set` dispatch
# --------------------------------------------------------------------------

#: mock `klt --batch-set`: records the invocation, writes one per-member
#: report where the real client writes it (<outdir>/<request stem>/report.json)
#: and prints the aggregate envelope. Runs no simulator and touches no fleet.
#: MOCK_SKIP (a request stem) omits that member's report, standing in for a
#: member the set could not run.
MOCK_KLT_SET = """#!/usr/bin/env bash
if [[ "$1" == "--version" ]]; then echo "mock-klt 1.0"; exit 0; fi
args=("$@"); outdir=""; requests=(); collecting=0
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    --batch-set) collecting=1 ;;
    -o) outdir="${args[$((i + 1))]}"; collecting=0 ;;
    --*) collecting=0 ;;
    *) [[ ${collecting} -eq 1 ]] && requests+=("${args[$i]}") ;;
  esac
done
printf '%s\n' "${args[@]}" >> "${MOCK_COUNT}"
for req in "${requests[@]}"; do
  stem="$(basename "${req}" .json)"
  [[ "${stem}" == "${MOCK_SKIP:-}" ]] && continue
  mkdir -p "${outdir}/${stem}"
  printf '{"status": "pass", "corners": [{"corner_id": "%s", "artifacts": {"deck": "%s/%s/deck.cir"}}]}\n' \
    "${stem}" "${outdir}" "${stem}" > "${outdir}/${stem}/report.json"
done
echo '{"schema_version": 1, "status": "pass", "requests": []}'
"""

SHARDS = ("typ", "bcs")


class SetDispatchTests(TempDirCase):
    """si_set_add / si_set_dispatch: the 15 independent requests of a PVT
    campaign go to ONE `klt sim --batch-set` (issue #402) instead of one
    blocking `klt sim` each, without loosening the #332 identity contract.
    """

    def setUp(self) -> None:
        super().setUp()
        self.klt = self.write("bin/klt", MOCK_KLT_SET)
        self.klt.chmod(0o755)
        self.count = self.tmp / "count.txt"
        self.work = self.tmp / "work"
        self.work.mkdir()
        self.tmpl = self.write("tmpl/body.tmpl", "* template v1\n")
        self.make_inputs()

    def make_inputs(self, body_extra: str = "") -> None:
        for label in SHARDS:
            body = self.work / f"body-{label}.spice"
            body.write_text(self.tmpl.read_text() + body_extra, encoding="utf-8")
            (self.work / f"request-{label}.json").write_text(
                json.dumps({"netlist": str(body), "corners": {"temperature_c": [27]}}),
                encoding="utf-8",
            )

    def dispatch(self, in_flight: int = 2, **env) -> subprocess.CompletedProcess:
        adds = "; ".join(
            f'si_set_add request-{label}.json report-{label}.json "{label}"'
            for label in SHARDS
        )
        script = (
            f'set -euo pipefail; WORK="{self.work}"; HARNESS_DIR="{HARNESS}"; '
            f'KLT_BIN="{self.klt}"; '
            f'IDENT_ARGS=(--declare "klt_version=mock" --extra "{self.tmpl}"); '
            f'source "{HARNESS}/submission_identity.sh"; '
            f'si_set_reset; {adds}; si_set_dispatch batch-set {in_flight}'
        )
        e = {**os.environ, "MOCK_COUNT": str(self.count)}
        e.pop(si.ENV_ALLOW_LEGACY, None)
        e.pop(si.ENV_REDISPATCH, None)
        e.update(env)
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e)

    def invocations(self) -> list[list[str]]:
        if not self.count.exists():
            return []
        text = self.count.read_text()
        return [block.splitlines() for block in text.split("--batch-set\n")[1:]]

    def test_one_invocation_carries_every_shard(self) -> None:
        r = self.dispatch()
        self.assertEqual(r.returncode, 0, r.stderr)
        # The whole campaign is ONE client run, not one per shard.
        self.assertEqual(len(self.invocations()), 1, self.count.read_text())
        argv = self.count.read_text().split()
        for label in SHARDS:
            self.assertIn(f"request-{label}.json", argv)
        self.assertIn("--max-in-flight", argv)
        self.assertIn("--wait-for-capacity", argv)

    def test_member_reports_are_harvested_and_bound(self) -> None:
        r = self.dispatch()
        self.assertEqual(r.returncode, 0, r.stderr)
        for label in SHARDS:
            report = self.work / f"report-{label}.json"
            # Copied to the per-shard path the fixup/merge steps read...
            self.assertTrue(report.is_file(), f"{label} report not harvested")
            self.assertEqual(
                json.loads(report.read_text())["corners"][0]["corner_id"], f"request-{label}"
            )
            # ...and bound to the inputs it was submitted with (#332).
            self.assertTrue(si.sidecar_path(report).is_file(), f"{label} left unbound")

    def test_capacity_wait_is_always_passed(self) -> None:
        # The fleet is vCPU-budgeted: a submit that does not wait out
        # `batch_no_capacity` fails the campaign instead of queueing.
        self.dispatch()
        argv = self.count.read_text().split()
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "600")
        # A completed shard is not re-submitted, so clear the results first.
        self.count.unlink()
        for label in SHARDS:
            report = self.work / f"report-{label}.json"
            report.unlink()
            si.sidecar_path(report).unlink()
        self.dispatch(**{"KLT_SIM_CAPACITY_WAIT_S": "900"})
        argv = self.count.read_text().split()
        self.assertEqual(argv[argv.index("--wait-for-capacity") + 1], "900")

    def test_member_shard_concurrency_is_bounded_when_asked(self) -> None:
        # The fleet's shared vCPU budget, not the client, is what a campaign
        # actually runs out of: MAX_IN_FLIGHT x `remote.hosts` jobs are wanted
        # at once and the overflow is refused, so both bounds must be settable.
        self.dispatch()
        self.assertNotIn("--max-concurrent-jobs", self.count.read_text().split())
        self.count.unlink()
        for label in SHARDS:
            report = self.work / f"report-{label}.json"
            report.unlink()
            si.sidecar_path(report).unlink()
        self.dispatch(**{"KLT_SIM_MAX_CONCURRENT_JOBS": "3"})
        argv = self.count.read_text().split()
        self.assertEqual(argv[argv.index("--max-concurrent-jobs") + 1], "3")

    def test_unchanged_rerun_submits_nothing(self) -> None:
        self.assertEqual(self.dispatch().returncode, 0)
        self.count.unlink()
        self.make_inputs()  # regeneration is byte-identical
        r = self.dispatch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.invocations(), [])  # nothing re-submitted
        self.assertIn("nothing to submit", r.stdout)

    def test_changed_inputs_refuse_rather_than_reuse(self) -> None:
        self.assertEqual(self.dispatch().returncode, 0)
        self.make_inputs(body_extra=".param x=1\n")
        r = self.dispatch()
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("different inputs", r.stderr)

    def test_missing_member_report_is_reported_and_left_unbound(self) -> None:
        # A member the set could not run must not be silently bound to a
        # stale/absent report -- the merge is what refuses a partial grid,
        # and a resume has to re-dispatch exactly this shard.
        r = self.dispatch(**{"MOCK_SKIP": "request-typ"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("the set returned no report", r.stderr)
        self.assertFalse((self.work / "report-typ.json").exists())
        self.assertFalse(si.sidecar_path(self.work / "report-typ.json").is_file())
        # ...while its siblings still land.
        self.assertTrue(si.sidecar_path(self.work / "report-bcs.json").is_file())

    def test_a_previous_runs_member_report_is_never_harvested_again(self) -> None:
        # The same regression, into a work dir that has ALREADY been used --
        # the resumable case this harness exists for. `--batch-set` writes its
        # member reports into <outdir>/<stem>/ and does not clear them, so a
        # member it cannot run this time leaves the previous run's file
        # sitting there. Harvesting it would `commit` old measurements under
        # the identity si_set_add just `begin`-ed for the CURRENT inputs: a
        # verified binding of a stale report to a new DUT (#332).
        self.assertEqual(self.dispatch().returncode, 0)
        member = self.work / "batch-set" / "request-typ" / "report.json"
        self.assertTrue(member.is_file(), "first run left no member report to go stale")
        first = (self.work / "report-typ.json").read_text()

        self.make_inputs(body_extra=".param x=1\n")  # the DUT body changes
        r = self.dispatch(**{si.ENV_REDISPATCH: "1", "MOCK_SKIP": "request-typ"})

        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("the set returned no report", r.stderr)
        # Cleared before the submit, so "no report" is not satisfied by last
        # time's file...
        self.assertFalse(member.is_file(), "stale member report survived the submit")
        # ...the shard is left unbound (`begin` dropped the old sidecar and
        # nothing re-published it), so a resume re-dispatches exactly it...
        self.assertFalse(
            si.sidecar_path(self.work / "report-typ.json").is_file(),
            "stale report was bound to the new inputs",
        )
        self.assertEqual((self.work / "report-typ.json").read_text(), first)
        # ...while the sibling that DID run is harvested and bound as usual.
        bcs = self.work / "report-bcs.json"
        self.assertTrue(si.sidecar_path(bcs).is_file())
        self.assertEqual(
            si.check(
                self.work / "request-bcs.json", bcs, [self.tmpl], {"klt_version": "mock"}
            )[0],
            si.EXIT_REUSE,
        )


class SetDispatchWiringTests(unittest.TestCase):
    """The shared driver offers the concurrent path, and the 120-point
    box-TC campaign (#402, the DUT whose sequential run was 7+ h) opts in.
    """

    def test_driver_dispatches_a_set_when_opted_in(self) -> None:
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        self.assertIn("PEX_BATCH_MAX_IN_FLIGHT", driver)
        self.assertIn("si_set_dispatch", driver)
        self.assertIn("si_shard", driver)  # the default path is still there

    def test_boxtc_runner_opts_in(self) -> None:
        runner = (SIM_DIR / "closed-loop-vref-pvt-boxtc" / "run_klt_sim.sh").read_text()
        self.assertIn("PEX_BATCH_MAX_IN_FLIGHT", runner)

    def test_boxtc_runner_defaults_to_the_measured_concurrency(self) -> None:
        # The out-of-the-box invocation must be the configuration that was
        # measured to complete, not one measured to lose shards: the fleet is
        # shared and vCPU-budgeted, and 3 requests x 8 shard jobs overran it
        # (384 vCPU vs BATCH_MAX_VCPU=224, ~half the campaign's shards lost).
        # 2 x 3 lost none. Both stay overridable from the environment.
        runner = (SIM_DIR / "closed-loop-vref-pvt-boxtc" / "run_klt_sim.sh").read_text()
        self.assertIn('PEX_BATCH_MAX_IN_FLIGHT="${PEX_BATCH_MAX_IN_FLIGHT:-2}"', runner)
        self.assertIn(
            'KLT_SIM_MAX_CONCURRENT_JOBS="${KLT_SIM_MAX_CONCURRENT_JOBS:-3}"', runner
        )

    def test_every_batch_submit_waits_out_a_capacity_refusal(self) -> None:
        helper = (SIM_DIR / "harness" / "submission_identity.sh").read_text()
        for fn in ("si_shard", "si_set_dispatch"):
            body = helper.split(f"{fn}() {{", 1)[1]
            self.assertIn("--wait-for-capacity", body.split("\n}\n", 1)[0], fn)

    def test_pex_boxtc_runner_overrides_the_body_template_before_sourcing_the_driver(self) -> None:
        assignment = (
            'BODY_TEMPLATE="${_here}/../closed-loop-vref-pvt-pex/testbench/'
            'closed_loop_vref_pvt_pex.body.spice.tmpl"'
        )
        runner = (SIM_DIR / "closed-loop-vref-pvt-pex-boxtc" / "run_klt_sim.sh").read_text()
        self.assertIn(assignment, runner)
        source_line = 'source "${_here}/../harness/pex_runner.sh"'
        self.assertIn(source_line, runner)
        # The ordering is the contract: the override only reaches the
        # submission identity when it precedes the source line.
        self.assertLess(runner.index(assignment), runner.index(source_line))

    def test_pex_driver_resolves_the_body_template_only_at_the_default(self) -> None:
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        occurrences = [
            line
            for line in driver.splitlines()
            if "${STEM}.body.spice.tmpl" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            occurrences,
            [
                'BODY_TEMPLATE="${BODY_TEMPLATE:-${EXP_DIR}/testbench/${STEM}.body.spice.tmpl}"',
                # pex_schematic_dut_setup's default render source (#650): the
                # committed per-stem template. An override reaches the render
                # only as the explicit --dut-template flag, never an ambient
                # DUT_TEMPLATE variable (#670), so the sed itself names no
                # template path.
                '  local default_dut="${EXP_DIR}/testbench/${STEM}.body.spice.tmpl"',
            ],
        )

    def test_shared_pex_body_template_exists_and_the_per_stem_copy_does_not(self) -> None:
        shared = (
            SIM_DIR / "closed-loop-vref-pvt-pex"
            / "testbench" / "closed_loop_vref_pvt_pex.body.spice.tmpl"
        )
        self.assertTrue(shared.is_file(), shared)
        # Stem-exact on purpose: the non-PEX closed-loop-vref-pvt-boxtc bench
        # legitimately keeps its own ..._boxtc.body.spice.tmpl on main.
        per_stem = (
            SIM_DIR / "closed-loop-vref-pvt-pex-boxtc"
            / "testbench" / "closed_loop_vref_pvt_pex_boxtc.body.spice.tmpl"
        )
        self.assertFalse(per_stem.exists(), per_stem)


class SchematicDutSeamTests(unittest.TestCase):
    """The shell side of the six schematic-DUT benches: one shared setup,
    one shared record mint, one shared AC flow -- kept shared (#650).
    """

    #: the six schematic-DUT wrappers and the identity extra each appends
    WRAPPERS = {
        "closed-loop-iq": "enrich_supply_bench_report.py",
        "closed-loop-startup": "enrich_supply_bench_report.py",
        "startup-time-to-release": "enrich_supply_bench_report.py",
        "closed-loop-vref-pvt": None,
        "closed-loop-vref-pvt-boxtc": None,
        "closed-loop-psrr": "enrich_ac_report.py",
    }

    NETLISTS = ("bandgap_startup.spice", "bandgap_core.spice", "bandgap_amp.spice")

    def test_every_wrapper_delegates_to_the_shared_setup(self) -> None:
        for exp, extra in self.WRAPPERS.items():
            with self.subTest(exp=exp):
                script = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                call = "pex_schematic_dut_setup"
                if extra is not None:
                    call += f' "${{HARNESS_DIR}}/{extra}"'
                self.assertIn(call, script)
                # The setup must not be re-typed here -- that is the
                # duplication #650 removed. No msense read, no template
                # render, no netlist list.
                self.assertNotIn("read_msense_width", script)
                self.assertNotIn("@@MSENSE_W@@", script)
                for netlist in self.NETLISTS:
                    self.assertNotIn(
                        f'--extra "${{REPO_ROOT}}/design/netlist/{netlist}"', script)
                # The flow is the family runner's, not a local case block.
                self.assertNotIn('case "${MODE}"', script)

    def test_the_shared_setup_carries_the_schematic_dut(self) -> None:
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        body = driver.split("pex_schematic_dut_setup() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('source "${SIM_DIR}/lib/msense_width.sh"', body)
        self.assertIn('"${WORK}/msense_w.txt"', body)
        self.assertIn('BODY_TEMPLATE="${WORK}/body.spice.tmpl"', body)
        for netlist in self.NETLISTS:
            self.assertIn(f'--extra "${{REPO_ROOT}}/design/netlist/{netlist}"', body)

    def test_every_schematic_record_delegates_to_the_shared_mint(self) -> None:
        # The --extraction-sources-less twin of pex_record_mint: defined once
        # beside it, and none of its callers re-types the adapter call.
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        self.assertIn("schematic_record_mint() {", driver)
        mint = driver.split("schematic_record_mint() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("klt_sim_evidence.py", mint)
        self.assertNotIn("--extraction-sources", mint)
        for rel in ("harness/pex_vref_runner.sh", "harness/supply_bench_runner.sh"):
            with self.subTest(rel=rel):
                text = (SIM_DIR / rel).read_text()
                self.assertIn("schematic_record_mint", text)
                self.assertNotIn("klt_sim_evidence.py", text)

    def test_the_psrr_wrapper_delegates_its_flow_to_the_ac_runner(self) -> None:
        # closed-loop-psrr used to re-type pex_ac_main's --sanity/--batch/
        # --record arms inline; the schematic twin is a runner function now.
        script = (SIM_DIR / "closed-loop-psrr" / "run_klt_sim.sh").read_text()
        self.assertIn("schematic_ac_main", script)
        self.assertNotIn("klt_sim_evidence.py", script)
        runner = (SIM_DIR / "harness" / "pex_ac_runner.sh").read_text()
        self.assertIn("schematic_ac_main() {", runner)
        self.assertIn("_ac_main() {", runner)
        # One flow, not two: the arms live once, in _ac_main.
        for arm in ("--sanity)", "--batch)", "--record)"):
            self.assertEqual(runner.count(arm), 1, arm)

    # -- #670: the render source and record spec are explicit flags on the
    # shared setup, not ambient variables the caller's environment can set.
    # The tests below run the real function bodies (extracted from
    # pex_runner.sh) in a stubbed subshell: a fake msense_width.sh, a fake
    # klt_sim_evidence.py that captures its argv, and small committed /
    # variant / decoy template+spec files. No SPICE, no PDK, no klt.

    def _schematic_stub_tree(self) -> Path:
        tmp = tempfile.TemporaryDirectory(prefix="schematic-dut-seam-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel in ("sim/lib", "repo", "exp/testbench", "exp/variants",
                    "work", "harness"):
            (root / rel).mkdir(parents=True)
        (root / "sim" / "lib" / "msense_width.sh").write_text(
            'read_msense_width() { MSENSE_W="0.42"; }\n'
        )
        (root / "exp" / "testbench" / "stubstem.body.spice.tmpl").write_text(
            "body @@MSENSE_W@@ committed\n"
        )
        (root / "exp" / "testbench" / "stubstem.record-spec.json").write_text("{}\n")
        (root / "exp" / "variants" / "proposal.body.spice.tmpl").write_text(
            "body @@MSENSE_W@@ variant\n"
        )
        (root / "exp" / "variants" / "proposal.record-spec.json").write_text("{}\n")
        # The decoys an exported DUT_TEMPLATE / RECORD_SPEC / _SCHEMATIC_
        # RECORD_SPEC would point at: distinguishable by content.
        (root / "evil.body.spice.tmpl").write_text("body evil-dut\n")
        (root / "evil.record-spec.json").write_text("{}\n")
        (root / "harness" / "klt_sim_evidence.py").write_text(
            "import os, sys\n"
            'open(os.environ["SPEC_CAPTURE"], "w").write("\\n".join(sys.argv[1:]))\n'
        )
        return root

    def _run_schematic_setup(self, root: Path, call: str) -> subprocess.CompletedProcess:
        """Run the real pex_schematic_dut_setup + schematic_record_mint
        bodies from sim/harness/pex_runner.sh in a stubbed `set -euo
        pipefail` subshell, with the environment polluted exactly the way
        #670 fears, then dump IDENT_ARGS, the spec state and the mint's
        captured argv for the assertions."""
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        setup = driver.split("pex_schematic_dut_setup() {", 1)[1].split("\n}\n", 1)[0]
        mint = driver.split("schematic_record_mint() {", 1)[1].split("\n}\n", 1)[0]
        default_spec = root / "exp" / "testbench" / "stubstem.record-spec.json"
        script = "\n".join([
            "set -euo pipefail",
            f'SIM_DIR="{root}/sim"',
            f'REPO_ROOT="{root}/repo"',
            f'EXP_DIR="{root}/exp"',
            'STEM="stubstem"',
            f'WORK="{root}/work"',
            f'HARNESS_DIR="{root}/harness"',
            f'SPEC_CAPTURE="{root}/spec-capture.txt"',
            "export SPEC_CAPTURE",
            # The pollution under test: exported harness-generic names.
            f'export DUT_TEMPLATE="{root}/evil.body.spice.tmpl"',
            f'export RECORD_SPEC="{root}/evil.record-spec.json"',
            f'export _SCHEMATIC_RECORD_SPEC="{root}/evil.record-spec.json"',
            # What pex_runner.sh's source time already contributed: the
            # committed per-stem template rides the identity from there.
            "IDENT_ARGS=("
            f'--extra "{root}/exp/testbench/stubstem.body.spice.tmpl")',
            f"pex_schematic_dut_setup() {{\n{setup}\n}}",
            f"schematic_record_mint() {{\n{mint}\n}}",
            call,
            f'printf \'%s\\n\' "${{_SCHEMATIC_RECORD_SPEC}}" > "{root}/spec-state.txt"',
            f'printf \'%s\\n\' "${{IDENT_ARGS[@]}}" > "{root}/ident.txt"',
            'schematic_record_mint report.json',
        ])
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    def _ident(self, root: Path) -> list[str]:
        return (root / "ident.txt").read_text().splitlines()

    def test_exported_dut_template_and_record_spec_cannot_reach_the_helpers(self) -> None:
        root = self._schematic_stub_tree()
        enricher = root / "harness" / "enricher.py"
        enricher.write_text("# enricher\n")
        default_spec = root / "exp" / "testbench" / "stubstem.record-spec.json"
        committed = root / "exp" / "testbench" / "stubstem.body.spice.tmpl"
        r = self._run_schematic_setup(
            root,
            # The wrapper's exact call pattern (closed-loop-psrr): the empty
            # VARIANT_SETUP_ARGS must expand cleanly under `set -u` on the
            # as-built path (#670).
            f'VARIANT_SETUP_ARGS=(); pex_schematic_dut_setup "{enricher}" '
            '${VARIANT_SETUP_ARGS[@]+"${VARIANT_SETUP_ARGS[@]}"}',
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # The render came from the committed template, not the decoy.
        self.assertEqual(
            (root / "work" / "body.spice.tmpl").read_text(), "body 0.42 committed\n"
        )
        # The identity kept the source-time committed template exactly once
        # (no duplicate re-add) and gained exactly the netlists + enricher.
        self.assertEqual(self._ident(root), [
            "--extra", str(committed),
            "--extra", f"{root}/repo/design/netlist/bandgap_startup.spice",
            "--extra", f"{root}/repo/design/netlist/bandgap_core.spice",
            "--extra", f"{root}/repo/design/netlist/bandgap_amp.spice",
            "--extra", str(enricher),
        ])
        # The mint bound the harness default spec, not the exported decoys.
        self.assertEqual(
            (root / "spec-state.txt").read_text().strip(), str(default_spec)
        )
        argv = (root / "spec-capture.txt").read_text().splitlines()
        self.assertEqual(
            argv[argv.index("--spec") + 1], str(default_spec)
        )

    def test_dut_template_flag_binds_the_variant_render_source_to_the_identity(self) -> None:
        root = self._schematic_stub_tree()
        enricher = root / "harness" / "enricher.py"
        enricher.write_text("# enricher\n")
        committed = root / "exp" / "testbench" / "stubstem.body.spice.tmpl"
        variant = root / "exp" / "variants" / "proposal.body.spice.tmpl"
        r = self._run_schematic_setup(
            root,
            f'pex_schematic_dut_setup "{enricher}" --dut-template "{variant}"',
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (root / "work" / "body.spice.tmpl").read_text(), "body 0.42 variant\n"
        )
        ident = self._ident(root)
        # Both templates ride the identity, each exactly once: the committed
        # one from source time, the variant one from the flag (#670).
        self.assertEqual(ident.count(str(committed)), 1)
        self.assertEqual(ident.count(str(variant)), 1)

    def test_dut_template_equal_to_the_default_leaves_the_identity_alone(self) -> None:
        root = self._schematic_stub_tree()
        committed = root / "exp" / "testbench" / "stubstem.body.spice.tmpl"
        r = self._run_schematic_setup(
            root, f'pex_schematic_dut_setup --dut-template "{committed}"'
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        # submission_identity.py refuses a duplicate --extra basename; an
        # explicit default must not re-add what source time already hashed.
        self.assertEqual(self._ident(root).count(str(committed)), 1)

    def test_record_spec_flag_is_forwarded_to_the_shared_mint(self) -> None:
        root = self._schematic_stub_tree()
        variant_spec = root / "exp" / "variants" / "proposal.record-spec.json"
        r = self._run_schematic_setup(
            root, f'pex_schematic_dut_setup --record-spec "{variant_spec}"'
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (root / "spec-state.txt").read_text().strip(), str(variant_spec)
        )
        argv = (root / "spec-capture.txt").read_text().splitlines()
        self.assertEqual(argv[argv.index("--spec") + 1], str(variant_spec))

    def test_unknown_and_valueless_options_fail_closed(self) -> None:
        for call in ("pex_schematic_dut_setup --bogus",
                     "pex_schematic_dut_setup --dut-template",
                     "pex_schematic_dut_setup --record-spec",
                     "pex_schematic_dut_setup --record-spec --bogus",
                     'pex_schematic_dut_setup --record-spec ""',
                     "pex_schematic_dut_setup --dut-template --help"):
            with self.subTest(call=call):
                root = self._schematic_stub_tree()
                r = self._run_schematic_setup(root, call)
                self.assertEqual(r.returncode, 2, r.stderr)
                # Failed before any render: no WORK side effects.
                self.assertFalse((root / "work" / "body.spice.tmpl").exists())

    def test_empty_extras_and_bash43_unbound_arrays(self) -> None:
        # Zero positional extras under `set -u` (Bash < 4.4 treats an empty
        # array expansion as unbound).
        root = self._schematic_stub_tree()
        r = self._run_schematic_setup(root, "pex_schematic_dut_setup")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_record_spec_relative_path_is_anchored_to_the_caller(self) -> None:
        root = self._schematic_stub_tree()
        (root / "chosen.json").write_text('{"who": "caller"}\n')
        (root / "work" / "chosen.json").write_text('{"who": "work"}\n')
        r = self._run_schematic_setup(
            root,
            f'cd "{root}"; pex_schematic_dut_setup --record-spec chosen.json; '
            f'cd "{root}/work"',
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (root / "spec-state.txt").read_text().strip(), str(root / "chosen.json")
        )

    def test_relative_spelling_of_the_committed_template_is_the_default(self) -> None:
        root = self._schematic_stub_tree()
        committed = root / "exp" / "testbench" / "stubstem.body.spice.tmpl"
        r = self._run_schematic_setup(
            root,
            f'cd "{root}"; pex_schematic_dut_setup '
            "--dut-template exp/testbench/stubstem.body.spice.tmpl",
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._ident(root).count(str(committed)), 1)

    def test_the_psrr_wrapper_passes_variant_overrides_as_explicit_flags(self) -> None:
        # #670: the variant render source and record spec reach the shared
        # setup as --dut-template / --record-spec flags; the wrapper no
        # longer sets ambient DUT_TEMPLATE / RECORD_SPEC variables or
        # appends the identity --extra itself.
        script = (SIM_DIR / "closed-loop-psrr" / "run_klt_sim.sh").read_text()
        self.assertIn("--dut-template", script)
        self.assertIn("--record-spec", script)
        self.assertIn("VARIANT_SETUP_ARGS=()", script)
        self.assertNotIn("DUT_TEMPLATE=", script)
        self.assertNotIn("RECORD_SPEC=", script)
        self.assertNotIn('IDENT_ARGS+=(--extra "${DUT_TEMPLATE}")', script)

    def test_the_driver_binds_the_record_spec_as_harness_state_only(self) -> None:
        driver = (SIM_DIR / "harness" / "pex_runner.sh").read_text()
        # Unconditional at source time: an inherited _SCHEMATIC_RECORD_SPEC
        # is overwritten the moment the driver is sourced (#670).
        self.assertIn(
            '_SCHEMATIC_RECORD_SPEC="${EXP_DIR}/testbench/${STEM}.record-spec.json"',
            driver,
        )
        mint = driver.split("schematic_record_mint() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('--spec "${_SCHEMATIC_RECORD_SPEC}"', mint)
        # The ambient-environment seam is gone, not merely shadowed.
        self.assertNotIn("${DUT_TEMPLATE", driver)
        self.assertNotIn("${RECORD_SPEC", driver)


# --------------------------------------------------------------------------
# Runner identity coverage (#661, #729). Changes to request generation or
# the shared verdict code must invalidate the reports produced with them.
# --------------------------------------------------------------------------

#: Every non-test module in sim/harness/, by import name.
HARNESS_PY = {
    p.stem: p
    for p in HARNESS.glob("*.py")
    if not p.name.startswith("test_")
}

#: The shared verdict module every enricher's constants come from (#661).
VERDICT_MODULE = "enrich_pvt_report"

#: A runner participates in the submission-identity scaffold when its own
#: script builds an identity (IDENT_ARGS) or enters a shared dispatch main.
#: sim/closed-loop-vref-mc deliberately does neither -- klt's own --resume
#: owns reuse there, and no IDENT_ARGS list exists to extend.
IDENTITY_ENTRY = re.compile(
    r"IDENT_ARGS|si_shard|si_set_|pex_batch_dispatch|[a-z_]+_main\b"
)


def first_party_import_closure(modules: set, *, exclude=()) -> set:
    """Follow imports within sim/harness, stopping at excluded modules."""
    seen: set = set()
    stack = list(modules)
    while stack:
        name = stack.pop()
        if name in seen or name in exclude or name not in HARNESS_PY:
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(HARNESS_PY[name].read_text())):
            if isinstance(node, ast.Import):
                stack.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                stack.append(node.module)
    return seen


#: Non-comment `source` statement targeting a `.sh` file (#663). Handles nested
#: double quotes inside `$(...)` such as `$(dirname "${BASH_SOURCE[0]}")/...`
#: and `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/...`, while stopping
#: before `#` comments so prose/comment mentions do not over-match.
SOURCE_SH_RE = re.compile(
    r'^\s*source\s+["\']?(?:[^\n#]*?/)?([A-Za-z0-9_.-]+\.sh)(?:["\'\s;&|<>#]|$)',
    re.MULTILINE,
)


#: A `source` in command position (line start, or after `;` `&` `|` `(` `{`,
#: `then`/`do`/`else`, or `$(`/backtick), independent of SOURCE_SH_RE (#680).
SOURCE_CMD_RE = re.compile(
    r"(?:^|[;&|({`]|\b(?:then|do|else)\b)\s*source\s+(?=(?P<arg>[^\n]*))"
)
_SH_BASENAME_RE = re.compile(r"([A-Za-z0-9_.-]+\.sh)\b")


def _inside_quotes(prefix: str) -> bool:
    """True when PREFIX ends inside an open '...' or "..." string; a quote of
    the other kind inside an open string is literal (`"it's"`)."""
    state = None
    for ch in prefix:
        if ch in "\"'" and state in (None, ch):
            state = None if state else ch
    return state is not None


def executable_harness_sources(text: str, harness_names: set) -> list:
    """(lineno, helper, line) for every executable `source` command (several
    per line are each considered) whose first literal `*.sh` argument is a
    sim/harness helper. Found without
    SOURCE_SH_RE, so a sourcing idiom the regex cannot see is still listed.
    Comment lines, trailing comments, and `source` inside an open double
    quote (echo/printf prose, `${VAR:?...(source x)...}` diagnostics) are
    not commands and are skipped.
    """
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for m in SOURCE_CMD_RE.finditer(line):
            before = line[: m.start("arg")]
            if _inside_quotes(before):
                continue  # inside a quoted string: prose, not a command
            arg = m.group("arg").split(" #")[0]
            hit = _SH_BASENAME_RE.search(arg)
            if hit and hit.group(1) in harness_names:
                found.append((lineno, hit.group(1), line))
    return found


def unrecognized_harness_sources(
    scripts, harness_names: set, root: Path = SIM_DIR
) -> list:
    """(script, lineno, helper) for each executable harness `source` that
    SOURCE_SH_RE does not recognize *at that line*, so a second recognized
    source of the same helper on another line cannot mask it.
    """
    misses = []
    for script in scripts:
        for lineno, helper, line in executable_harness_sources(
            script.read_text(), harness_names
        ):
            if helper not in {m.group(1) for m in SOURCE_SH_RE.finditer(line)}:
                try:
                    shown = script.relative_to(root.parent)
                except ValueError:
                    shown = script
                misses.append((str(shown), lineno, helper))
    return misses


def harness_shell_names() -> set:
    return {p.name for p in HARNESS.glob("*.sh")}


def runner_shell_closure(runner: Path) -> dict[Path, str]:
    """RUNNER plus every sim/harness/*.sh it sources, transitively: the
    family bases and, through them, the shared preamble and identity
    helpers whose --extra lists build the runner's submission identity.
    """
    closure: dict[Path, str] = {}
    stack = [runner]
    while stack:
        path = stack.pop()
        if path in closure:
            continue
        text = path.read_text()
        closure[path] = text
        for match in SOURCE_SH_RE.finditer(text):
            sourced = HARNESS / match.group(1)
            if sourced != path and sourced.is_file():
                stack.append(sourced)
    return closure


class EnricherIdentityCoverageTests(TempDirCase):
    """Bind request generators, their request-shaping imports, and verdict code."""

    def _batch_probe_env(self) -> dict:
        """Run the batch generators and capture the first shard's check arguments.

        The model files satisfy the shell preflight. Stub extraction, klt
        and sanity checks so the probe needs neither a simulator nor a PDK.
        """
        for pdk in ("ihp-sg13g2", "ihp-sg13cmos5l"):
            for model in ("osdi/psp103.osdi", "osdi/r3_cmc.osdi",
                          "models/cornerMOShv.lib", "models/cornerRES.lib"):
                self.write(f"{pdk}/libs.tech/ngspice/{model}", "")
        probe = self.write("probe.sh", r'''
python3() {
  if [[ "$1" == */submission_identity.py && "$2" == check ]]; then
    printf '%s\n' "${@:5}" > "${WORK}/identity-args"
    exit 0
  fi
  if [[ "${MODE}" == --batch && " $* " == *" --request-template "* &&
        " $* " != *" --mode sanity "* ]]; then
    printf '%s\n' "$1" >> "${WORK}/generators"
    command python3 "$@"
  fi
}
''')
        return {
            "PATH": os.environ["PATH"], "HOME": str(self.tmp), "BASH_ENV": str(probe),
            "PDK_ROOT": str(self.tmp), "KLT_SIM_CMOS5L_BATCH_READY": "1",
            "KLT_SIM_KLT": "true", "KLT_BATCH_PROVISION_SCRIPT": shutil.which("true"),
        }

    def test_runners_hash_request_generators_and_verdict_code(self) -> None:
        env = self._batch_probe_env()
        for script in sorted(SIM_DIR.glob("*/run_klt_sim.sh")):
            if not IDENTITY_ENTRY.search(script.read_text()):
                continue
            with self.subTest(runner=script.parent.name):
                work = self.tmp / script.parent.name
                run = subprocess.run(
                    ["bash", str(script), "--batch"], cwd=SIM_DIR.parent,
                    env={**env, "KLT_SIM_WORK": str(work)}, capture_output=True, text=True,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                generators = {Path(s).resolve() for s in (work / "generators").read_text().splitlines()}
                self.assertTrue(generators)
                for generator in generators:
                    self.assertEqual(generator, HARNESS_PY.get(generator.stem))
                # The multi-command generators also import their merge and
                # enrichment code. Only prepare shapes the shard request.
                required = first_party_import_closure(
                    {g.stem for g in generators}, exclude={"merge_batch_shards", VERDICT_MODULE})
                union = "\n".join(runner_shell_closure(script).values())
                named = {m for m in HARNESS_PY if re.search(rf"\b{m}\.py\b", union)}
                if VERDICT_MODULE in first_party_import_closure(named):
                    required.add(VERDICT_MODULE)
                args = (work / "identity-args").read_text().splitlines()
                extras = [Path(value).resolve() for flag, value in zip(args, args[1:])
                          if flag == "--extra"]
                for module in sorted(required):
                    with self.subTest(module=module):
                        self.assertEqual(extras.count(HARNESS_PY[module]), 1)

    def test_shell_closure_resolves_shared_runners_and_transitive_deps(self) -> None:
        # #663: guard against the source-line regex silently dropping
        # nested-quote idioms such as `$(dirname "${BASH_SOURCE[0]}")/...`.
        expected_pex_chain = {
            "pex_runner.sh",
            "klt_sim_preamble.sh",
            "submission_identity.sh",
            "pex_merge_call.sh",
        }
        iq_names = {
            p.name for p in runner_shell_closure(SIM_DIR / "closed-loop-iq/run_klt_sim.sh")
        }
        self.assertTrue(
            expected_pex_chain | {"supply_bench_runner.sh"} <= iq_names,
            f"closed-loop-iq closure missing expected harness scripts: {sorted(iq_names)}",
        )

        # Edge case: pre-resolved variable (`source "${_here}/../harness/pex_runner.sh"`).
        boxtc_names = {
            p.name
            for p in runner_shell_closure(
                SIM_DIR / "closed-loop-vref-pvt-pex-boxtc/run_klt_sim.sh"
            )
        }
        self.assertTrue(
            expected_pex_chain | {"pex_vref_runner.sh"} <= boxtc_names,
            f"closed-loop-vref-pvt-pex-boxtc closure incomplete: {sorted(boxtc_names)}",
        )

        # CMOS5L base also sources klt_sim_preamble.sh via nested quotes.
        cmos5l_names = {
            p.name
            for p in runner_shell_closure(
                SIM_DIR / "sg13cmos5l-closed-loop-startup/run_klt_sim.sh"
            )
        }
        self.assertTrue(
            {"cmos5l_runner.sh", "klt_sim_preamble.sh", "submission_identity.sh"}
            <= cmos5l_names,
            f"sg13cmos5l-closed-loop-startup closure incomplete: {sorted(cmos5l_names)}",
        )

        # Every runner that sources pex_runner.sh must resolve the full chain.
        # Discovery is independent of SOURCE_SH_RE (#680), so a mid-line
        # source cannot hide a runner from this loop.
        names_h = harness_shell_names()
        pex_runners = [
            s
            for s in sorted(SIM_DIR.glob("*/run_klt_sim.sh"))
            if any(
                h == "pex_runner.sh"
                for _, h, _ in executable_harness_sources(s.read_text(), names_h)
            )
        ]
        self.assertGreater(len(pex_runners), 0)
        for script in pex_runners:
            names = {p.name for p in runner_shell_closure(script)}
            self.assertTrue(
                expected_pex_chain <= names,
                f"{script.parent.name} closure missing transitive pex_runner chain: {sorted(names)}",
            )

    def test_shell_closure_ignores_comments_and_prose(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "run_klt_sim.sh"
            script.write_text(
                "#!/usr/bin/env bash\n"
                '# source "$(dirname "${BASH_SOURCE[0]}")/../harness/pex_ac_runner.sh"\n'
                "# prose mention of ../harness/pex_vref_runner.sh\n"
                'echo "source ../harness/supply_bench_runner.sh"\n'
                'source "${HARNESS_DIR}/pex_merge_call.sh" # unlike ../harness/pex_ac_runner.sh\n'
                'source "${EXP_DIR}/foo.env" # unlike ../harness/pex_vref_runner.sh\n'
            )
            names = {p.name for p in runner_shell_closure(script)}
        self.assertEqual(names, {"run_klt_sim.sh", "pex_merge_call.sh"})

    def test_shell_closure_regex_recognizes_every_harness_source(self) -> None:
        # #680: SOURCE_SH_RE is line-anchored on purpose; make that assumption
        # a checked one so an unsupported idiom fails loudly, not silently.
        names = harness_shell_names()
        scripts = sorted(SIM_DIR.rglob("*.sh"))
        self.assertTrue(
            any(executable_harness_sources(p.read_text(), names) for p in scripts)
        )
        misses = unrecognized_harness_sources(scripts, names)
        self.assertEqual(
            misses, [], f"harness source the closure regex cannot see: {misses}"
        )

    def test_shell_closure_reports_unrecognized_source_idioms(self) -> None:
        names = {"pex_runner.sh", "pex_merge_call.sh"}
        cases = {
            "standalone": ('  source "${H}/pex_runner.sh"\n', []),
            "nested": (
                'source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/pex_runner.sh"\n',
                [],
            ),
            "and_list": ('[[ -f x ]] && source "${H}/pex_runner.sh"\n', [1]),
            "inline_then": (
                'if [[ -n "${P}" ]]; then source "${H}/pex_runner.sh"; fi\n',
                [1],
            ),
            "cmd_subst": ('x=$(source "${H}/pex_runner.sh")\n', [1]),
            "masked_by_second": (
                'source "${H}/pex_runner.sh"\n'
                '[[ -f x ]] && source "${H}/pex_runner.sh"\n',
                [2],
            ),
            "two_sources_one_line": (
                'source "${H}/pex_merge_call.sh" && source "${H}/pex_runner.sh"\n',
                [1],
            ),
            "two_sources_semicolon": (
                'source "${H}/pex_merge_call.sh"; source "${H}/pex_runner.sh"\n',
                [1],
            ),
            "nonharness_then_harness": (
                'source "${H}/env.sh" && source "${H}/pex_runner.sh"\n',
                [1],
            ),
            "apostrophe_earlier": (
                'echo "it\'s fine"; source "${H}/pex_runner.sh"\n',
                [1],
            ),
            "comment": ('# [[ x ]] && source "${H}/pex_runner.sh"\n', []),
            "echo": ('echo "source ${H}/pex_runner.sh"\n', []),
            "printf": ("printf 'a; source %s/pex_runner.sh' x\n", []),
            "diagnostic": (
                ': "${PDK_ROOT:?set PDK_ROOT (source ${H}/pex_runner.sh) or export it}"\n',
                [],
            ),
            "trailing_comment": (
                'source "${H}/pex_merge_call.sh" # unlike pex_runner.sh\n',
                [],
            ),
        }
        with tempfile.TemporaryDirectory() as td:
            for label, (body, expected) in cases.items():
                script = Path(td) / f"{label}.sh"
                script.write_text("#!/usr/bin/env bash\n" + body)
                got = unrecognized_harness_sources([script], names, root=Path(td))
                # lines are offset by the shebang line
                self.assertEqual(
                    [lineno - 1 for _, lineno, _ in got], expected, label
                )
                for _, _, helper in got:
                    self.assertIn(helper, names, label)

    def test_shell_closure_discovers_mid_line_pex_runner_source(self) -> None:
        names = {"pex_runner.sh"}
        text = '[[ -f x ]] && source "${H}/pex_runner.sh"\n'
        self.assertEqual(
            [h for _, h, _ in executable_harness_sources(text, names)],
            ["pex_runner.sh"],
        )

    def test_the_shared_verdict_module_still_exists(self) -> None:
        # The probe above keys on this module by name; if it is ever renamed
        # or split, the coverage test above silently stops checking anything.
        self.assertIn(VERDICT_MODULE, HARNESS_PY)
        self.assertTrue(
            any(
                VERDICT_MODULE in first_party_import_closure({name})
                for name in ("enrich_supply_bench_report", "enrich_ac_report")
            ),
            "the enrichers no longer import the shared verdict module; "
            "update VERDICT_MODULE",
        )


# --------------------------------------------------------------------------
# AC-bench node seeds (issue #740). pex_ac_runner.sh picked the startup seed
# record by mtime and read it by column position. 73c420a2's record dropped
# the msense_w column the four records before it carried, every positional
# field after it moved by one, and `SEEDS_OF typ 3.30` -- the lookup all three
# AC benches make before their --sanity point -- came back empty. Which record
# a checkout picked was a tie-break artefact of its mtimes, so the failure was
# environment-dependent. The record is now picked by name through the shared
# klt_sim_newest_seed_csv and read by header, like every other seed consumer.
# --------------------------------------------------------------------------

#: The two committed startup-record headers: the four records before
#: 73c420a2, then 73c420a2's own, which has no msense_w.
SEED_HEADER_WITH_MSENSE = (
    "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,"
    "det_early_v,fb_early_v,fb_final_v,sns1_final_v,sns2_final_v,vref_final_v,"
    "det_final_v,i_mkfb_final_a,dvsns_final_v")
SEED_HEADER_SANS_MSENSE = SEED_HEADER_WITH_MSENSE.replace(",msense_w", "")

#: Stand-in for an AC bench's run_klt_sim.sh, with a fixture tree standing in
#: for sim/: the same two sources, in the order the bench takes them
#: (pex_runner.sh sources the preamble at its own source time, then the bench
#: sources pex_ac_runner.sh, which selects the record as it is sourced). It
#: names the record selected, then does one of
#:   lookup   the --sanity gate's own SEEDS_OF call;
#:   sanity   the real _ac_main --sanity, with the deck write replaced by an
#:            echo into the deck file, the simulator by a read of the deck it
#:            was handed, and the enricher and the anchor gate by no-ops -- so
#:            what would reach the deck is the test's evidence, and nothing
#:            simulates.
AC_BENCH_STANDIN = """\
set -euo pipefail
SIM_DIR="$1"; HARNESS_DIR="$2"; ACTION="$3"
IDENT_ARGS=()
source "${HARNESS_DIR}/klt_sim_preamble.sh"
source "${HARNESS_DIR}/pex_ac_runner.sh"
printf 'SEED_CSV=%s\\n' "${SEED_CSV}"
case "${ACTION}" in
  lookup) SEEDS_OF typ 3.30 ;;
  sanity)
    MODE=--sanity; WORK="$4"; OSDI_DIR=/models; KIND=psrr
    pex_instantiate_body() { printf 'DECK %s\\n' "$*"; }
    pex_sanity_local() { echo "SIMULATED"; cat "${WORK}/body.spice"; }
    python3() { :; }
    check_anchors() { :; }
    _ac_main body.inc pex_record_mint ;;
esac
"""


def seed_values(tag: str) -> tuple[str, str, str, str]:
    """FB, SNS1, SNS2 and VREF for one row, in the records' own `%.6e`
    rendering, with TAG (one digit) in every value: each row's four voltages
    are its own, so a lookup that matched a decoy, or read a neighbouring
    column, cannot return the string the test expects."""
    return (f"{tag}.111110e+00", f"0.{tag}111100e+00",
            f"0.{tag}111200e+00", f"1.{tag}111300e+00")


def seed_rows(tag: str) -> list[dict]:
    """A startup record's rows: one typ/27C/3.30V PASS row carrying the seeds
    TAG marks, then four decoys that each differ from it in exactly one key --
    status, temperature, supply, corner -- while carrying their own."""
    def row(corner: str, temp: int, vdd: str, status: str, tag_: str) -> dict:
        fb, sns1, sns2, vref = seed_values(tag_)
        return {"corner_label": corner, "hbt_section": "hbt_typ",
                "mos_section": "mos_tt", "res_section": "res_typ",
                "temp_c": temp, "vdd_v": vdd, "msense_w": "10u", "status": status,
                "det_early_v": "0.1", "fb_early_v": "0.2", "fb_final_v": fb,
                "sns1_final_v": sns1, "sns2_final_v": sns2, "vref_final_v": vref,
                "det_final_v": "0.01", "i_mkfb_final_a": "1e-14",
                "dvsns_final_v": "0.0004"}

    return [row("typ", 27, "3.30", "PASS", tag),
            row("typ", 27, "3.30", "FAIL", "9"),
            row("typ", 125, "3.30", "PASS", "8"),
            row("typ", 27, "2.97", "PASS", "7"),
            row("bcs", 27, "3.30", "PASS", "6")]


def seed_csv(header: str, rows: list[dict]) -> str:
    """ROWS as a startup record under HEADER (one comma-joined line), in its
    column order; a column a row carries that HEADER lacks is dropped."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=header.split(","), lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class AcBenchSeedTests(TempDirCase):
    """The three AC benches' node seeds: which record, and how it is read."""

    #: the benches that take their --sanity | --batch | --record flow from
    #: pex_ac_runner.sh
    BENCHES = ("closed-loop-psrr", "closed-loop-psrr-pex", "closed-loop-zout-pex")

    #: the record a lookup test is pointed at, alone in its directory
    RECORD = "20261118-082945-3e600d97.csv"

    def _run_ac_bench(self, action: str, records: dict[str, str] | None = None,
                      mtimes: dict[str, int] | None = None,
                      root: Path | None = None) -> tuple[subprocess.CompletedProcess, Path]:
        """AC_BENCH_STANDIN doing ACTION against a sim/ tree under ROOT whose
        closed-loop-startup/records/ holds RECORDS ({name: text}); MTIMES
        ({name: seconds}) is stamped on after the writes."""
        root = root or self.tmp
        records_dir = root / "sim" / "closed-loop-startup" / "records"
        records_dir.mkdir(parents=True)
        for name, text in (records or {}).items():
            (records_dir / name).write_text(text, encoding="utf-8")
        for name, mtime in (mtimes or {}).items():
            os.utime(records_dir / name, (mtime, mtime))
        (root / "work").mkdir()
        standin = self.write("ac-bench.sh", AC_BENCH_STANDIN)
        run = subprocess.run(
            ["bash", str(standin), str(root / "sim"), str(HARNESS), action,
             str(root / "work")],
            capture_output=True, text=True,
        )
        return run, records_dir

    def test_the_sanity_seeds_are_read_by_column_name(self) -> None:
        """Issue #740: the four voltages come back exact, FB SNS1 SNS2 VREF,
        from the PASS row at typ/27C/3.30V -- not from the decoys beside it --
        under both committed headers and under a shuffled one."""
        shuffled = ",".join(reversed(SEED_HEADER_SANS_MSENSE.split(",")))
        headers = {"with-msense-w": (SEED_HEADER_WITH_MSENSE, "1"),
                   "without-msense-w": (SEED_HEADER_SANS_MSENSE, "2"),
                   "shuffled": (shuffled, "3")}
        for case, (header, tag) in headers.items():
            with self.subTest(header=case):
                run, records_dir = self._run_ac_bench(
                    "lookup", {self.RECORD: seed_csv(header, seed_rows(tag))},
                    root=self.tmp / case)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stderr, "")
                self.assertEqual(
                    run.stdout,
                    f"SEED_CSV={records_dir / self.RECORD}\n"
                    f"{' '.join(seed_values(tag))}\n")

    def test_a_record_without_a_usable_pass_row_is_refused(self) -> None:
        """Issue #740: no PASS row at the point, a seed column the header
        lacks, or an empty seed value -- each prints nothing (so nothing can
        seed a deck), exits 3, and names its one cause on stderr."""
        rows = seed_rows("1")
        cases = {
            "no-pass-row": (SEED_HEADER_SANS_MSENSE, rows[1:],
                            "no typ/27C/3.30 seed row in {record}"),
            "column-missing": (SEED_HEADER_SANS_MSENSE.replace(",vref_final_v", ""),
                               rows, "no vref_final_v column in {record}"),
            "value-empty": (SEED_HEADER_SANS_MSENSE,
                            [{**rows[0], "vref_final_v": ""}, *rows[1:]],
                            "typ/27C/3.30 PASS row in {record} has an empty vref_final_v"),
        }
        for case, (header, case_rows, cause) in cases.items():
            with self.subTest(case=case):
                run, records_dir = self._run_ac_bench(
                    "lookup", {self.RECORD: seed_csv(header, case_rows)},
                    root=self.tmp / case)
                self.assertEqual(run.returncode, 3, run.stderr)
                self.assertEqual(run.stdout, f"SEED_CSV={records_dir / self.RECORD}\n")
                self.assertEqual(
                    run.stderr,
                    f"run_klt_sim.sh: {cause}\n".format(
                        record=records_dir / self.RECORD))

    def test_sanity_passes_the_four_voltage_tokens_to_the_deck(self) -> None:
        rows = seed_rows("1")
        rows[0].update(fb_final_v="0", sns1_final_v="-.25", sns2_final_v="+2.",
                       vref_final_v=" 1.23456789E-01 ")
        run, records_dir = self._run_ac_bench(
            "sanity", {self.RECORD: seed_csv(SEED_HEADER_WITH_MSENSE, rows)})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, "")
        self.assertEqual(run.stdout, (
            f"SEED_CSV={records_dir / self.RECORD}\nSIMULATED\n"
            "DECK /models body.inc VDD=3.30 FB_SEED=0 SNS1_SEED=-.25"
            " SNS2_SEED=+2. VREF_SEED=1.23456789E-01\n"))

    def test_an_unusable_seed_row_never_reaches_the_deck(self) -> None:
        cases = (("vref_final_v", "", "empty"),
                 ("sns1_final_v", " ", "empty"),
                 ("sns2_final_v", "nan", "invalid"),
                 ("fb_final_v", "1e999", "invalid"),
                 ("vref_final_v", "0.7 0.8", "invalid"))
        for index, (column, value, cause) in enumerate(cases):
            with self.subTest(column=column, value=value):
                rows = seed_rows("1")
                rows[0][column] = value
                root = self.tmp / str(index)
                run, records_dir = self._run_ac_bench(
                    "sanity", {self.RECORD: seed_csv(SEED_HEADER_SANS_MSENSE, rows)},
                    root=root)
                self.assertEqual(run.returncode, 3, run.stderr)
                self.assertFalse((root / "work" / "body.spice").exists())
                self.assertEqual(run.stdout, f"SEED_CSV={records_dir / self.RECORD}\n")
                self.assertEqual(run.stderr, (
                    "run_klt_sim.sh: typ/27C/3.30 PASS row in"
                    f" {records_dir / self.RECORD} has an {cause} {column}\n"))

    def test_the_record_is_the_newest_by_name_whatever_the_mtimes(self) -> None:
        """Issue #740: `ls -t | head -1` made the choice a tie-break artefact
        of a fresh checkout's mtimes. The greatest timestamped primary wins
        by filename, whether the older record is newer by mtime or both share
        one, and the *-tc.csv / *-vs-schematic* companions -- newer-named
        than their own record, one newer-named than every record -- never
        win."""
        older, newer = "20261001-083332-e5507b2.csv", self.RECORD
        records = {older: seed_csv(SEED_HEADER_WITH_MSENSE, seed_rows("1")),
                   newer: seed_csv(SEED_HEADER_SANS_MSENSE, seed_rows("2")),
                   newer[:-4] + "-tc.csv": seed_csv(SEED_HEADER_SANS_MSENSE, seed_rows("5")),
                   newer[:-4] + "-vs-schematic.csv":
                       seed_csv(SEED_HEADER_SANS_MSENSE, seed_rows("5")),
                   "20261231-235959-fffffff-tc.csv":
                       seed_csv(SEED_HEADER_SANS_MSENSE, seed_rows("5")),
                   newer[:-4] + ".md": "the record's narrative"}
        t0 = 1_700_000_000
        scenarios = {"older-record-newest-by-mtime": {older: t0 + 3600, newer: t0},
                     "equal-mtimes": {older: t0, newer: t0}}
        for case, mtimes in scenarios.items():
            with self.subTest(mtimes=case):
                run, records_dir = self._run_ac_bench(
                    "lookup", records, mtimes, root=self.tmp / case)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stderr, "")
                self.assertEqual(
                    run.stdout,
                    f"SEED_CSV={records_dir / newer}\n{' '.join(seed_values('2'))}\n")

    def test_companions_alone_are_no_seed_record(self) -> None:
        """Issue #740: a records directory holding only companions, or
        nothing, is named on stderr and exits 3 before any lookup."""
        records = {self.RECORD[:-4] + "-tc.csv": "a companion",
                   self.RECORD[:-4] + "-vs-schematic.csv": "a companion"}
        for case, files in {"companions-only": records, "empty": {}}.items():
            with self.subTest(records=case):
                run, records_dir = self._run_ac_bench("lookup", files, root=self.tmp / case)
                self.assertEqual(run.returncode, 3)
                self.assertEqual(run.stdout, "")
                self.assertEqual(
                    run.stderr, f"run_klt_sim.sh: no seed record in {records_dir}/\n")

    def test_the_three_ac_benches_select_the_record_through_the_shared_helper(self) -> None:
        """Issue #740: pex_ac_runner.sh -- the one flow all three AC benches
        source -- takes its record from klt_sim_newest_seed_csv, with no
        private glob left beside it, and each bench stays in the identity
        probe's discovery set: that probe is what runs all three entry points
        through --batch and its nested --sanity to the lookup."""
        runner = (HARNESS / "pex_ac_runner.sh").read_text()
        self.assertIn("klt_sim_newest_seed_csv || exit $?", runner)
        for retired in ("*.csv", '$8=="PASS"', "$11, $12, $13, $14"):
            self.assertNotIn(retired, runner)
        for bench in self.BENCHES:
            with self.subTest(bench=bench):
                script = (SIM_DIR / bench / "run_klt_sim.sh").read_text()
                self.assertIn('source "${HARNESS_DIR}/pex_ac_runner.sh"', script)
                self.assertTrue(IDENTITY_ENTRY.search(script))


if __name__ == "__main__":
    unittest.main()
