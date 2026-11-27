#!/usr/bin/env python3
"""Self-test of sim/harness/trim_coverage_klt.py (issue #416). Stdlib only: no
simulator, no PDK -- tiny temp-dir fixtures and in-memory reports."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_ac_report as acr  # noqa: E402
import enrich_pvt_report as epr  # noqa: E402
import enrich_supply_bench_report as esbr  # noqa: E402
import seed_deck  # noqa: E402
import trim_coverage_klt as tc  # noqa: E402
import trim_mc_klt as tm  # noqa: E402

HARNESS_DIR = Path(__file__).resolve().parent

#: Fixture for the shell startup-seed lookups (issue #739): an older record,
#: then the newest one with both companion kinds an enrichment derives from
#: it. Under a linguistic UTF-8 collation bare `sort | tail -1` ignores the
#: `-`/`.` on its first pass, so the unfiltered glob ranks a companion of the
#: newest record after the record itself and hands back the companion.
SEED_FIXTURE = ("20260101-000000-a.csv", "20260101-000002-c.csv",
                "20260101-000002-c-tc.csv", "20260101-000002-c-vs-schematic.csv")
NEWEST_SEED = "20260101-000002-c.csv"

#: Each shell lookup and a stand-in for the script that sources it (both take
#: the sim dir as $1 and source the lookup as $2). nodeset_seed.sh needs
#: SIM_DIR/REPO_ROOT and dut_git_sha() from its caller's
#: sim/lib/pvt_preflight.sh, which cannot be sourced without a PDK: the stub
#: stands in for that function and records that the provenance lookup went
#: through its name.
PREAMBLE_CALLER = """\
set -euo pipefail
SIM_DIR="$1"
source "$2"
klt_sim_newest_seed_csv || exit $?
printf 'SEED_CSV=%s\\n' "${SEED_CSV}"
"""
NODESET_CALLER = """\
set -euo pipefail
SIM_DIR="$1"
REPO_ROOT="${SIM_DIR}/.."
dut_git_sha() { printf 'sha-of:%s' "${1##*/}"; }
source "$2"
printf 'SEED_CSV=%s\\nSEED_GIT_SHA=%s\\n' "${SEED_CSV}" "${SEED_GIT_SHA}"
"""
SHELL_SEED_LOOKUPS = {
    "klt_sim_preamble.sh": (HARNESS_DIR / "klt_sim_preamble.sh", PREAMBLE_CALLER),
    "nodeset_seed.sh": (HARNESS_DIR.parent / "lib" / "nodeset_seed.sh", NODESET_CALLER),
}


def seed_vars(stdout: str) -> dict[str, str]:
    """The `SEED_<NAME>=<value>` lines a caller stand-in prints."""
    return dict(line.split("=", 1) for line in stdout.splitlines()
                if line.startswith("SEED_"))


def corner(label, code, vdd, temp=27, status="pass", **meas):
    base = dict(fb_v=2.0, sns1_v=0.7081, sns2_v=0.7077, vref_v=1.0, det_v=0.01,
                i_mkfb_a=1e-13)
    base.update(meas)
    return {
        "corner_id": f"{label}/novdd/{temp}C/params:trim_code={code}",
        "process": label, "temperature_c": temp, "status": status,
        "params": {"trim_code": code},
        "measurements": [{"name": k, "value": v} for k, v in base.items()],
    }


class GridTests(unittest.TestCase):
    def test_grid_size_and_uniqueness(self):
        pts = tc.expected_points()
        self.assertEqual(len(pts), 15 * 11 + 4)
        self.assertEqual(len(set(pts)), len(pts))
        self.assertIn("typ_code128_-40c_3.30v", pts)
        self.assertIn("fs_code255_27c_3.63v", pts)

    def test_shard_ids_unique(self):
        ids = [tc.shard_id(l, v, t) for l, v, t, _ in tc.shard_plan()]
        self.assertEqual(len(ids), 17)
        self.assertEqual(len(set(ids)), 17)

    def test_unfilled_placeholder_refused(self):
        seeds = {("typ", "27", "3.30"): dict(fb_final_v="1", sns1_final_v="1",
                                              sns2_final_v="1", vref_final_v="1")}
        with self.assertRaises(SystemExit):
            tc.body_text("@@NOPE@@ @@FB_SEED@@", "/o", "typ", 3.30, 27, "10u", seeds, "s.csv")

    def test_unfilled_embedded_placeholder_refused(self):
        """Issue #652: a placeholder embedded in a word (`v(fb)=@@NOPE@@`,
        `temp=@@TEMP_C@@C`) is as unfilled as a standalone one -- the old
        text.split() leftover check was blind to these."""
        seeds = {("typ", "27", "3.30"): dict(fb_final_v="1", sns1_final_v="1",
                                              sns2_final_v="1", vref_final_v="1")}
        with self.assertRaises(SystemExit):
            tc.body_text("v(fb)=@@FB_SEED@@\ntemp=@@NOPE@@C\n", "/o", "typ", 3.30, 27,
                         "10u", seeds, "s.csv")

    def test_missing_seed_row_refused(self):
        with self.assertRaises(SystemExit):
            tc.seed_row({}, "typ", 27, "3.30", "s.csv")


class EnrichTests(unittest.TestCase):
    def run_enrich(self, corners):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "in.json"), Path(d, "out.json")
            src.write_text(json.dumps({"corners": corners}))
            args = type("A", (), {"report": str(src), "output": str(out)})
            tc.enrich(args)
            return json.loads(out.read_text())

    def test_pass_adds_columns(self):
        c = corner("typ_code128", 128, 3.30)
        c["supply_v"] = {"Vvdd": 3.30}
        rep = self.run_enrich([c])
        names = [m["name"] for m in rep["corners"][0]["measurements"]]
        self.assertIn("dvsns_v", names)
        self.assertIn("trim_code", names)
        self.assertEqual(rep["status"], "pass")

    def test_degenerate_equilibrium_fails(self):
        c = corner("typ_code128", 128, 3.30, fb_v=3.29)  # railed
        c["supply_v"] = {"Vvdd": 3.30}
        rep = self.run_enrich([c])
        self.assertEqual(rep["status"], "fail")
        self.assertIn("fb_railed", rep["corners"][0]["diagnostics"][0]["message"])

    def test_loop_not_closed_fails(self):
        c = corner("typ_code128", 128, 3.30, sns2_v=0.60)
        c["supply_v"] = {"Vvdd": 3.30}
        self.assertEqual(self.run_enrich([c])["status"], "fail")

    def test_verdict_follows_the_shared_constants(self):
        # Issue #657: the thresholds are enrich_pvt_report's, where the drift
        # guard reads them, not a copy in this module.
        c = corner("typ_code128", 128, 3.30)
        c["supply_v"] = {"Vvdd": 3.30}
        with mock.patch.object(epr, "DET_RELEASE_FRAC", 0.0):
            rep = self.run_enrich([c])
        self.assertEqual(rep["status"], "fail")
        self.assertIn("startup_not_released", rep["corners"][0]["diagnostics"][0]["message"])

    def test_non_pass_corners_are_named_on_stdout(self):
        """Issue #725: the report tail is enrich_pvt_report's, which names
        every non-pass corner -- this module's own copy had dropped that."""
        good = corner("typ_code0", 0, 3.30)
        good["supply_v"] = {"Vvdd": 3.30}
        bad = corner("typ_code128", 128, 3.30, fb_v=3.29)
        bad["supply_v"] = {"Vvdd": 3.30}
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.run_enrich([good, bad])
        self.assertEqual(printed.getvalue().splitlines(), [
            f"  {bad['corner_id']}: fail fb_railed",
            "enriched: fail passed=1 failed=1 errored=0",
        ])


class AnalysisTests(unittest.TestCase):
    def write_group(self, path, label, unit=0.0024, lsb=0.0024, drop=None, extra_rows=()):
        rows = []
        for code in tc.CODES:
            if code == drop:
                continue
            v = 0.7 + unit * code
            if code == 129:
                v = 0.7 + unit * 128 + lsb
            rows.append({"corner_label": f"{label}_code{code}", "temp_c": "27",
                         "vdd_v": "3.30", "status": "PASS", "trim_code": f"{code}.0e+00",
                         "vref_v": f"{v:.9g}"})
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["corner_label", "temp_c", "vdd_v",
                                               "status", "trim_code", "vref_v"])
            w.writeheader()
            w.writerows(rows)

    def analyse(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d, "r.csv"), Path(d, "a.csv")
            self.write_group(src, "typ", **kw)
            tc.analysis(type("A", (), {"csv": str(src), "output": str(out)}))
            return {(r["corner_label"], r["vdd_v"]): r for r in csv.DictReader(out.open())}

    def test_ideal_linear_group_passes(self):
        got = self.analyse()
        self.assertEqual(got[("typ", "3.30")]["group_status"], "PASS")
        self.assertEqual(got[("typ", "3.30")]["monotonic"], "yes")

    def test_missing_groups_fail(self):
        got = self.analyse()  # the other 14 groups have no rows at all
        self.assertEqual(got[("bcs", "3.30")]["group_status"], "FAIL")

    def test_coarse_step_fails_resolution(self):
        # 3 mV/step on a 1.05 V target is 0.29% > 0.25%
        got = self.analyse(unit=0.003, lsb=0.003)
        self.assertEqual(got[("typ", "3.30")]["group_status"], "FAIL")

    def test_missing_code_marks_incomplete(self):
        got = self.analyse(drop=255)
        self.assertEqual(got[("typ", "3.30")]["monotonic"], "incomplete")
        self.assertEqual(got[("typ", "3.30")]["group_status"], "FAIL")


class MergeTests(unittest.TestCase):
    def test_merge_relabels_and_checks_grid(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            rows = []
            exp_pts = []
            for label, vdd, temp, codes in tc.shard_plan()[:1]:
                sid = tc.shard_id(label, vdd, temp)
                rep = {"status": "pass", "passed": len(codes), "failed": 0, "errored": 0,
                       "corner_count": len(codes),
                       "corners": [corner("hbt_typ", c, vdd, temp) for c in codes]}
                (work / f"report-{sid}-fixed.json").write_text(json.dumps(rep))
                rows.append("\t".join([sid, label, f"{vdd:.2f}", str(temp), "r", "p", "a",
                                       "b", f"report-{sid}-fixed.json", "d",
                                       ",".join(map(str, codes))]))
                exp_pts += [tc.point_id(label, c, temp, vdd) for c in codes]
            (work / "m.tsv").write_text("\n".join(rows) + "\n")
            (work / "g.json").write_text(json.dumps({"points": exp_pts}))
            out = work / "merged.json"
            tc.merge(type("A", (), {"manifest": str(work / "m.tsv"), "work": str(work),
                                    "expect_grid": str(work / "g.json"), "output": str(out)}))
            merged = json.loads(out.read_text())
            ids = [c["corner_id"] for c in merged["corners"]]
            self.assertEqual(len(ids), 11)
            self.assertTrue(ids[0].startswith("typ_code0/2.97V/"))
            self.assertEqual(len(set(ids)), 11)

    def test_merge_refuses_worker_without_params_echo(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            c = corner("hbt_typ", 128, 2.97)
            del c["params"]
            (work / "r.json").write_text(json.dumps({"corners": [c]}))
            (work / "m.tsv").write_text("\t".join(
                ["s", "typ", "2.97", "27", "r", "p", "a", "b", "r.json", "d", "128"]) + "\n")
            (work / "g.json").write_text(json.dumps({"points": ["typ_code128_27c_2.97v"]}))
            with self.assertRaises(SystemExit):
                tc.merge(type("A", (), {"manifest": str(work / "m.tsv"), "work": str(work),
                                        "expect_grid": str(work / "g.json"),
                                        "output": str(work / "o.json")}))

    def test_merge_refuses_missing_point(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            rep = {"status": "pass", "passed": 1, "failed": 0, "errored": 0, "corner_count": 1,
                   "corners": [corner("hbt_typ", 128, 2.97)]}
            (work / "r.json").write_text(json.dumps(rep))
            (work / "m.tsv").write_text("\t".join(
                ["s", "typ", "2.97", "27", "r", "p", "a", "b", "r.json", "d", "128"]) + "\n")
            (work / "g.json").write_text(json.dumps({"points": [
                "typ_code128_27c_2.97v", "typ_code129_27c_2.97v"]}))
            with self.assertRaises(SystemExit):
                tc.merge(type("A", (), {"manifest": str(work / "m.tsv"), "work": str(work),
                                        "expect_grid": str(work / "g.json"),
                                        "output": str(work / "o.json")}))


class SharedSeamTests(unittest.TestCase):
    """Issue #463: load_seeds is trim_mc_klt's, not a second copy here. The two
    copies parsed the same committed startup-seed CSV, so a drift between them
    would silently seed two campaigns' decks differently."""

    def test_load_seeds_is_not_re_implemented(self):
        self.assertIs(tc.load_seeds, tm.load_seeds)

    def test_only_pass_rows_are_kept_keyed_by_corner_temp_vdd(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "s.csv"
            with csv_path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["corner_label", "temp_c", "vdd_v", "status", "fb_final_v"])
                w.writerow(["typ", "27", "3.30", "PASS", "2.0"])
                w.writerow(["wcs", "-40", "2.97", "FAIL", "9.9"])
            seeds = tc.load_seeds(str(csv_path))
            self.assertEqual(list(seeds), [("typ", "27", "3.30")])
            self.assertEqual(seeds[("typ", "27", "3.30")]["fb_final_v"], "2.0")

    def test_enrich_ac_report_seed_loader_is_seed_decks(self):
        """Issue #707: enrich_ac_report's private seed-CSV reader (which
        skipped the PASS filter) is retired onto seed_deck.load_seeds."""
        self.assertIs(acr.load_seeds, seed_deck.load_seeds)

    def test_enrichers_share_the_report_writer(self):
        """Issue #725: the JSON write, the non-pass corner lines and the
        `enriched:` summary are enrich_pvt_report.write_enriched_report.
        Issue #739: the fifth enricher, enrich_supply_bench_report, joins
        them."""
        self.assertIs(acr.write_enriched_report, epr.write_enriched_report)
        self.assertIs(tc.write_enriched_report, epr.write_enriched_report)
        self.assertIs(esbr.write_enriched_report, epr.write_enriched_report)

    def test_supply_bench_enricher_main_ends_with_the_shared_writer(self):
        """Issue #739: enrich_supply_bench_report.main() hands its enriched
        report to the shared writer; its own inline JSON write, non-pass
        corner loop and `enriched:` tally are gone."""
        with tempfile.TemporaryDirectory() as d:
            report = Path(d) / "report-merged.json"
            report.write_text(json.dumps({"corners": []}), encoding="utf-8")
            out = Path(d) / "report-enriched.json"
            for bench in sorted(esbr.BENCHES) + [esbr.LADDER_BENCH]:
                with self.subTest(bench=bench), \
                        mock.patch.object(esbr, "write_enriched_report") as write:
                    rc = esbr.main(["--bench", bench, str(report), "-o", str(out)])
                    self.assertEqual(rc, 0)
                    write.assert_called_once_with(mock.ANY, out)
                    self.assertEqual(write.call_args.args[0]["status"], "pass")

    def test_shell_seed_lookups_skip_companion_csvs(self):
        """Issue #739: klt_sim_newest_seed_csv (sim/harness/klt_sim_preamble.sh)
        and sim/lib/nodeset_seed.sh skip the *-tc.csv / *-vs-schematic*
        companions and sort in the C locale -- the shell twin of
        seed_deck.newest_seed_csv (issue #707). The bare `ls | sort | tail -1`
        they retired is the positive control: under a UTF-8 collation it
        picks a companion of the newest record, so when the control already
        picks the seed the host lacks that collation and the leg is not
        exercisable here."""
        for locale in ("C", "en_US.UTF-8"):
            with self.subTest(locale=locale), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                records = self._write_seed_fixture(root)
                env = {**os.environ, "LC_ALL": locale}
                bare = subprocess.run(
                    ["bash", "-c", 'ls -1 "$1"/*.csv | sort | tail -1', "ctl", str(records)],
                    env=env, capture_output=True, text=True, check=True,
                ).stdout.strip()
                if locale == "C":
                    # Why LC_ALL=C is half the fix: byte order ranks '-'
                    # before '.', so the record sorts after its companions.
                    self.assertEqual(Path(bare).name, NEWEST_SEED, bare)
                elif Path(bare).name == NEWEST_SEED:
                    self.skipTest(f"{locale}: bare sort already picks the seed; "
                                  "no punctuation-ignoring collation here")
                else:
                    self.assertNotEqual(Path(bare).name, NEWEST_SEED, bare)
                for key, (sourced, caller) in SHELL_SEED_LOOKUPS.items():
                    with self.subTest(lookup=key):
                        run = self._run_seed_lookup(root, key, sourced, caller, env)
                        self.assertEqual(run.returncode, 0, run.stderr)
                        picked = seed_vars(run.stdout)
                        self.assertEqual(Path(picked["SEED_CSV"]).name, NEWEST_SEED)
                        if key == "nodeset_seed.sh":
                            # SEED_GIT_SHA is dut_git_sha SEED_CSV, not a
                            # re-typed `git log` (the stub names its argument).
                            self.assertEqual(picked["SEED_GIT_SHA"], f"sha-of:{NEWEST_SEED}")

    def test_shell_seed_lookups_refuse_an_empty_records_dir(self):
        """Issue #739: closed-loop-vref-mc and trim-coverage had no missing-seed
        check (a bare `ls` failing inside the assignment). Both lookups name
        the empty directory: the preamble helper RETURNS 3 -- its
        return-not-exit contract, so the caller's `|| exit $?` decides -- and
        nodeset_seed.sh itself EXITS 3."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            records = root / "sim" / "closed-loop-startup" / "records"
            records.mkdir(parents=True)
            for key, (sourced, caller) in SHELL_SEED_LOOKUPS.items():
                with self.subTest(lookup=key):
                    run = self._run_seed_lookup(root, key, sourced, caller, dict(os.environ))
                    self.assertEqual(run.returncode, 3, run.stderr)
                    self.assertIn("closed-loop-startup/records", run.stderr)

    @staticmethod
    def _write_seed_fixture(root: Path) -> Path:
        records = root / "sim" / "closed-loop-startup" / "records"
        records.mkdir(parents=True)
        for name in SEED_FIXTURE:
            (records / name).write_text("", encoding="utf-8")
        return records

    @staticmethod
    def _run_seed_lookup(root: Path, key: str, sourced: Path, caller: str,
                         env: dict) -> subprocess.CompletedProcess:
        # The stand-in goes in a file: nodeset_seed.sh labels its diagnostics
        # with basename "${BASH_SOURCE[1]}", its sourcing script's own path.
        script = root / f"caller-{key}"
        script.write_text(caller, encoding="utf-8")
        return subprocess.run(["bash", str(script), str(root / "sim"), str(sourced)],
                              capture_output=True, text=True, env=env)

    def test_enrich_ac_report_never_uses_fail_seed_rows_as_reference(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "c.log"
            log.write_text("v(fb) = 2.0\n", encoding="utf-8")

            def messages(status):
                seed_csv = Path(d) / f"{status}.csv"
                seed_csv.write_text(
                    "corner_label,temp_c,vdd_v,status,fb_final_v\n"
                    f"typ,27,3.30,{status},9.9\n", encoding="utf-8")
                corner = {"corner_id": "typ/3.30V/27C/ac", "process": "typ",
                          "temperature_c": 27, "supply_v": {"Vvdd": 3.30},
                          "status": "pass", "measurements": [],
                          "artifacts": {"log": str(log)}}
                report = acr.enrich({"corners": [corner]}, "psrr",
                                    acr.load_seeds(str(seed_csv)))
                return "; ".join(x.get("message", "")
                                 for x in report["corners"][0].get("diagnostics", []))

            # positive control: the PASS row IS the op-match reference and
            # trips the band (fb_op 2.0 vs fb_final 9.9) -- the pre-#707
            # loader would have tripped it for the FAIL row too.
            msgs = {status: messages(status) for status in ("PASS", "FAIL")}
        self.assertIn("op_landed_far_from_seed", msgs["PASS"])
        self.assertNotIn("op_landed_far_from_seed", msgs["FAIL"])

    def test_newest_seed_csv_skips_companion_csvs(self):
        with tempfile.TemporaryDirectory() as d:
            records = Path(d) / "closed-loop-startup" / "records"
            records.mkdir(parents=True)
            self.assertRaises(SystemExit, seed_deck.newest_seed_csv, d)
            for name in ("20260101-000000-a.csv", "20260101-000000-a-tc.csv",
                         "20260101-000001-b-vs-schematic.csv",
                         "20260101-000002-c.csv"):
                (records / name).write_text("", encoding="utf-8")
            picked = seed_deck.newest_seed_csv(d)
        self.assertEqual(picked.name, "20260101-000002-c.csv")

    def test_read_msense_width_parses_w_and_rejects_missing(self):
        with tempfile.TemporaryDirectory() as d:
            net = Path(d) / "startup.spice"
            net.write_text("XMSENSE det sns1 vss vss sg13_hv_nmos w=10u l=0.5u\n",
                           encoding="utf-8")
            self.assertEqual(seed_deck.read_msense_width(net), "10u")
            net.write_text("XMSENSE det sns1 vss vss sg13_hv_nmos l=0.5u\n",
                           encoding="utf-8")
            self.assertRaises(SystemExit, seed_deck.read_msense_width, net)
            net.write_text("* no msense device here\n", encoding="utf-8")
            self.assertRaises(SystemExit, seed_deck.read_msense_width, net)

    def test_pex_vref_runner_mode_arms_appear_once(self):
        """Issue #707: the --sanity | --batch | --record switch is shared
        (_vref_main), so each arm appears exactly once in the file."""
        text = (Path(__file__).resolve().parent / "pex_vref_runner.sh").read_text(
            encoding="utf-8")
        for arm in ("--sanity)", "--batch)", "--record)"):
            self.assertEqual(text.count(arm), 1, arm)


if __name__ == "__main__":
    unittest.main()
