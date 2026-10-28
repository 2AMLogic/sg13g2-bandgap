#!/usr/bin/env python3
"""Self-test of sim/harness/trim_coverage_klt.py (issue #416). Stdlib only: no
simulator, no PDK -- tiny temp-dir fixtures and in-memory reports."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trim_coverage_klt as tc  # noqa: E402


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

    def test_missing_seed_row_refused(self):
        with self.assertRaises(SystemExit):
            tc.seed_row({}, "typ", 27, 3.30, "s.csv")


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


if __name__ == "__main__":
    unittest.main()
