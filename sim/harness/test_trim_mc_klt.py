#!/usr/bin/env python3
"""Self-test of sim/harness/trim_mc_klt.py (issue #423). Stdlib only: no simulator,
no PDK -- tiny temp-dir fixtures standing in for klt's `decks` result trees."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trim_mc_klt as tm  # noqa: E402

TEMPLATE = ("* point=@@POINT_LABEL@@ stage=@@STAGE@@ corner=@@CORNER_LABEL@@ temp=@@TEMP_C@@ "
            "draw=@@DRAW_INDEX@@ rndseed=@@SEED@@ code=@@TRIM_CODE@@ mode=@@MISMATCH_MODE@@\n"
            ".nodeset v(fb)=@@FB_SEED@@ v(sns1)=@@SNS1_SEED@@ v(sns2)=@@SNS2_SEED@@ "
            "v(vref)=@@VREF_SEED@@\n.lib \"@@PDK_ROOT@@/@@PDK@@/m.lib\" @@HBT_SECTION@@ "
            "@@MOS_SECTION@@ @@RES_SECTION@@ w=@@MSENSE_W@@ @@OSDI_DIR@@ @@DUT_GIT_SHA@@ @@VDD@@\n")


def seeds_for(temps=(-40, 27, 125)):
    row = dict(fb_final_v="2.0", sns1_final_v="0.7", sns2_final_v="0.7", vref_final_v="1.05")
    return {(c, str(t), "3.30"): row for c in ("typ", "bcs", "wcs") for t in temps}


def ctx(**kw):
    base = dict(seeds=seeds_for(), seed_csv="s.csv", seed=100, pdk="pdk", pdk_root="/r",
                osdi_dir="/o", msense_w="10u", dut_sha="sha")
    base.update(kw)
    return base


def stdout(vref):
    return f"v(fb) = 2\nv(vref) = {vref}\n"


def put_unit(root: Path, stem: str, uid: str, text: str | None, status="pass"):
    if text is None:
        return
    d = root / stem / uid
    d.mkdir(parents=True)
    (d / "stdout.bin").write_bytes(text.encode())
    (d / "unit.json").write_text(json.dumps({"result": {"id": uid, "status": status}}))


class RenderTests(unittest.TestCase):
    def test_sections_and_substitution(self):
        text = tm.render_deck(TEMPLATE, ctx(), "bcs", 7, 125, 200, "verify")
        self.assertIn("point=bcs stage=verify corner=bcs temp=125 draw=7 rndseed=107 code=200 "
                      "mode=mismatch", text)
        self.assertIn("hbt_bcs_mismatch mos_ff_mismatch res_bcs_mismatch w=10u /o sha 3.30", text)
        self.assertIn('.lib "/r/pdk/m.lib"', text)

    def test_negctrl_uses_plain_sections(self):
        text = tm.render_deck(TEMPLATE, ctx(), "negctrl", 0, 27, 0, "fit")
        self.assertIn("hbt_typ mos_tt res_typ", text)
        self.assertNotIn("_mismatch ", text.split("mode=")[1].split("\n")[1])

    def test_same_die_across_a_draws_decks(self):
        # die identity: only temp / code differ inside one draw
        a = tm.render_deck(TEMPLATE, ctx(), "nominal", 3, 27, 0, "fit").replace("temp=27", "T").replace("code=0", "C")
        b = tm.render_deck(TEMPLATE, ctx(), "nominal", 3, 27, 255, "fit").replace("temp=27", "T").replace("code=255", "C")
        self.assertEqual(a, b)

    def test_missing_seed_row_and_unfilled_placeholder_refused(self):
        with self.assertRaises(SystemExit):
            tm.render_deck(TEMPLATE, ctx(seeds={}), "nominal", 0, 27, 0, "fit")
        with self.assertRaises(SystemExit):
            tm.render_deck(TEMPLATE + "@@NOPE@@\n", ctx(), "nominal", 0, 27, 0, "fit")


class CodeStarTests(unittest.TestCase):
    def test_round_and_clip_match_the_awk(self):
        self.assertEqual(tm.clip_round(128.4), 128)
        self.assertEqual(tm.clip_round(128.5), 129)
        self.assertEqual(tm.clip_round(-0.4), 0)    # awk int(-0.9) -> 0
        self.assertEqual(tm.clip_round(-7.0), 0)    # railed low
        self.assertEqual(tm.clip_round(300.2), 255)  # railed high

    def test_unit_ids_are_single_path_segments(self):
        for uid in (tm.fit_id("nominal", 12, 255), tm.verify_id("wcs", 299, -40, 0)):
            self.assertRegex(uid, r"^[A-Za-z0-9._-]+$")


def write_seed_csv(path: Path, temps=(-40, 27, 125)):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["corner_label", "temp_c", "vdd_v", "status", "fb_final_v", "sns1_final_v",
                    "sns2_final_v", "vref_final_v"])
        for c in ("typ", "bcs", "wcs"):
            for t in temps:
                w.writerow([c, str(t), "3.30", "PASS", "2", "0.7", "0.7", "1.05"])


def mk_args(work, art, fit_art, n, **kw):
    ns = dict(work=str(work), artifacts=str(art), fit_artifacts=str(fit_art), n=n, seed=100,
              msense_w="10u", template=str(work / "t.tmpl"), seed_csv=str(work / "s.csv"), dut_sha="sha",
              pdk="pdk", local_pdk_root="/r", local_osdi_dir="/o",
              draws_out=str(work / "draws.csv"), report_out=str(work / "report.json"),
              klt_version="x", job_log=None, batch_pdk_root="/opt/pdk", batch_osdi_dir="/opt/o")
    ns.update(kw)
    return argparse.Namespace(**ns)


class CampaignFixture:
    """N=2 draws x 4 points, linear vref(code) = a + 0.002*code; negctrl identical."""

    def __init__(self, tmp: Path, n=2, break_unit=None, drop_unit=None):
        self.work, self.n = tmp, n
        self.fit_art, self.ver_art = tmp / "fit", tmp / "ver"
        (tmp / "t.tmpl").write_text(TEMPLATE)
        write_seed_csv(tmp / "s.csv")
        self.fit_manifest, self.ver_manifest = [], []
        self.codes = {}
        for point in tm.POINTS:
            ids = []
            for d in range(n):
                a = 0.80 if point == "negctrl" else 0.75 + 0.01 * d
                unit = 0.002
                ids += [tm.fit_id(point, d, c) for c in tm.FIT_CODES]
                for c in tm.FIT_CODES:
                    put_unit(self.fit_art, f"request-fit-{point}-00", tm.fit_id(point, d, c),
                             stdout(f"{a + unit * c:.6e}"))
                ideal = (1.050 - float(f"{a:.6e}")) / ((float(f"{a + 255 * unit:.6e}") - float(f"{a:.6e}")) / 255)
                self.codes[(point, d)] = (a, unit, tm.clip_round(ideal))
            self.fit_manifest.append({"request": "x", "stem": f"request-fit-{point}-00",
                                      "point": point, "ids": ids})
        (tmp / "manifest-fit.json").write_text(json.dumps(self.fit_manifest))
        res = tm.Results(self.fit_art, self.fit_manifest)
        res.require_complete("fit")
        argparse_args = argparse.Namespace(work=str(tmp), artifacts=str(self.fit_art), n=n)
        tm.codes(argparse_args)
        fits = json.loads((tmp / "codes.json").read_text())
        for point in tm.POINTS:
            ids = []
            for d in range(n):
                code = fits[f"{point}|{d}"]["code_star"]
                a, unit, _ = self.codes[(point, d)]
                for t in tm.VERIFY_TEMPS:
                    uid = tm.verify_id(point, d, t, code)
                    ids.append(uid)
                    # temperature droop 1 mV per 25 C so deviations are tiny but nonzero
                    v = a + unit * code - 4e-5 * (t - 27)
                    text = stdout(f"{v:.6e}")
                    if uid == break_unit:
                        text = "Simulation interrupted\n"
                    if uid != drop_unit:
                        put_unit(self.ver_art, f"request-verify-{point}-00", uid, text)
            self.ver_manifest.append({"request": "y", "stem": f"request-verify-{point}-00",
                                      "point": point, "ids": ids})
        (tmp / "manifest-verify.json").write_text(json.dumps(self.ver_manifest))

    def args(self):
        return mk_args(self.work, self.ver_art, self.fit_art, self.n)


class AssembleTests(unittest.TestCase):
    def assemble(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fx = CampaignFixture(Path(tmp.name), **kw)
        a = fx.args()
        tm.assemble(a)
        return fx, a

    def test_draws_csv_shape_and_digest(self):
        fx, a = self.assemble()
        text = Path(a.draws_out).read_text().splitlines()
        self.assertEqual(text[0], tm.DRAWS_HEADER)
        self.assertEqual(len(text), 1 + 4 * 2)
        rows = list(csv.DictReader(Path(a.draws_out).open()))
        self.assertEqual({r["verify_status"] for r in rows}, {"PASS"})
        self.assertEqual(len(rows[0]), 21)
        report = json.loads(Path(a.report_out).read_text())
        self.assertEqual([c["process"] for c in report["corners"]],
                         ["typ_mismatch", "typ_negctrl", "bcs_mismatch", "wcs_mismatch"])
        by = {c["process"]: {m["name"]: m["value"] for m in c["measurements"]}
              for c in report["corners"]}
        self.assertEqual(by["typ_negctrl"]["three_sigma_max_dev_pct"], 0.0)
        self.assertEqual(by["typ_mismatch"]["n_draws"], 2.0)
        for c in report["corners"]:
            for k in ("log", "deck"):
                self.assertTrue(Path(c["artifacts"][k]).is_file())

    def test_negative_control_spread_aborts_without_a_record(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fx = CampaignFixture(Path(tmp.name))
        # perturb one negctrl verify log
        victim = next(iter((fx.ver_art / "request-verify-negctrl-00").iterdir()))
        (victim / "stdout.bin").write_text(stdout("1.2"))
        a = fx.args()
        with self.assertRaises(SystemExit) as cm:
            tm.assemble(a)
        self.assertIn("NEGATIVE CONTROL FAILED", str(cm.exception))
        self.assertFalse(Path(a.report_out).exists())

    def test_failed_deck_is_a_verify_fail_row(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # find nominal draw 0's code* first, then break its 125 C deck
        pre = CampaignFixture(Path(tmp.name))
        code = json.loads((Path(tmp.name) / "codes.json").read_text())["nominal|0"]["code_star"]
        uid = tm.verify_id("nominal", 0, 125, code)
        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        fx = CampaignFixture(Path(tmp2.name), break_unit=uid)
        a = fx.args()
        tm.assemble(a)
        rows = list(csv.DictReader(Path(a.draws_out).open()))
        r0 = next(r for r in rows if r["point"] == "nominal" and r["draw_index"] == "0")
        self.assertEqual(r0["verify_status"], "FAIL")
        self.assertEqual(r0["vref_27c_v"], "")
        report = json.loads(Path(a.report_out).read_text())
        nominal = next(c for c in report["corners"] if c["process"] == "typ_mismatch")
        self.assertEqual(nominal["status"], "fail")  # n_pass 1 != n_draws 2

    def test_timed_out_unit_is_a_fail_row(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        fx = CampaignFixture(Path(tmp.name))
        unit = next(iter((fx.ver_art / "request-verify-bcs-00").iterdir()))
        rec = unit / "unit.json"
        rec.write_text(json.dumps({"result": {"status": "timeout"}}))
        a = fx.args()
        tm.assemble(a)
        rows = list(csv.DictReader(Path(a.draws_out).open()))
        self.assertEqual(sum(r["verify_status"] == "FAIL" for r in rows), 1)

    def test_partial_draw_set_is_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pre = CampaignFixture(Path(tmp.name))
        code = json.loads((Path(tmp.name) / "codes.json").read_text())["wcs|1"]["code_star"]
        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        fx = CampaignFixture(Path(tmp2.name), drop_unit=tm.verify_id("wcs", 1, -40, code))
        a = fx.args()
        with self.assertRaises(SystemExit) as cm:
            tm.assemble(a)
        self.assertIn("partial draw set is never recorded", str(cm.exception))
        self.assertFalse(Path(a.draws_out).exists())

    def test_railed_code_sets_railed_flag(self):
        # a die whose a(0) is far too high rails code* at 0
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_path = Path(tmp.name)
        fit_art = tmp_path / "fit"
        (tmp_path / "t.tmpl").write_text(TEMPLATE)
        ids = []
        for c in tm.FIT_CODES:
            uid = tm.fit_id("nominal", 0, c)
            ids.append(uid)
            put_unit(fit_art, "r", uid, stdout(f"{1.2 + 0.002 * c:.6e}"))
        (tmp_path / "manifest-fit.json").write_text(
            json.dumps([{"request": "x", "stem": "r", "point": "nominal", "ids": ids}]))
        old = tm.POINTS
        try:
            tm.POINTS = ("nominal",)
            tm.codes(argparse.Namespace(work=str(tmp_path), artifacts=str(fit_art), n=1))
        finally:
            tm.POINTS = old
        fits = json.loads((tmp_path / "codes.json").read_text())
        self.assertEqual(fits["nominal|0"]["code_star"], 0)


class CommittedRecordTests(unittest.TestCase):
    """The digest port reproduces the committed #229 digest from its own draws CSV."""

    RECORD = Path(__file__).resolve().parents[1] / "closed-loop-vref-trim-mc/records/20260930-232155-affdefe"

    def test_digest_matches_committed_record(self):
        draws = self.RECORD.parent / (self.RECORD.name + "-draws.csv")
        digest = self.RECORD.parent / (self.RECORD.name + ".csv")
        if not (draws.is_file() and digest.is_file()):
            self.skipTest("committed record not present")
        with draws.open(newline="") as fh:
            rows = list(csv.reader(fh))[1:]
        with digest.open(newline="") as fh:
            want = {r["corner_label"]: list(r.values()) for r in csv.DictReader(fh)}
        for point in tm.POINTS:
            got, _ = tm.digest_row(argparse.Namespace(msense_w="10u"), point, rows)
            self.assertEqual(got, want[tm.DIGEST_LABEL_OF[point]], point)


class FitFailureTests(unittest.TestCase):
    def test_failed_fit_gives_minus_one_and_na_row(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fit_art = tmp / "fit"
            ids = []
            for c in tm.FIT_CODES:
                uid = tm.fit_id("nominal", 0, c)
                ids.append(uid)
                put_unit(fit_art, "r", uid, "Unable to find definition of model x\n" if c == 255
                         else stdout("0.9"))
            (tmp / "manifest-fit.json").write_text(
                json.dumps([{"request": "x", "stem": "r", "point": "nominal", "ids": ids}]))
            old = tm.POINTS
            try:
                tm.POINTS = ("nominal",)
                tm.codes(argparse.Namespace(work=str(tmp), artifacts=str(fit_art), n=1))
            finally:
                tm.POINTS = old
            fit = json.loads((tmp / "codes.json").read_text())["nominal|0"]
            self.assertEqual(fit["code_star"], -1)
            self.assertIsNone(fit["v255"])
            row = tm.draw_row(argparse.Namespace(seed=5), "nominal", 0, fit, tm.Results(fit_art, []))
            self.assertEqual(row[11], "FAIL")
            self.assertEqual(row[7], "NA")
            self.assertEqual(row[10], "-1")


class RequestTests(unittest.TestCase):
    def test_requests_chunk_per_point_and_carry_deck_list_fields(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "t.tmpl").write_text(TEMPLATE)
            seed_csv = work / "s.csv"
            with seed_csv.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["corner_label", "temp_c", "vdd_v", "status", "fb_final_v",
                            "sns1_final_v", "sns2_final_v", "vref_final_v"])
                for c in ("typ", "bcs", "wcs"):
                    w.writerow([c, "27", "3.30", "PASS", "2", "0.7", "0.7", "1.05"])
            a = argparse.Namespace(
                stage="fit", work=str(work), template=str(work / "t.tmpl"), seed_csv=str(seed_csv),
                msense_w="10u", dut_sha="s", pdk="pdk", local_pdk_root="/lr", local_osdi_dir="/lo",
                seed=1, n=3, codes=None, batch_pdk_root="/opt/pdk", batch_osdi_dir="/opt/o",
                provision="/prov.sh", sanity_backend="local", draws_per_request=2,
                capacity_wait_s=60)
            tm.prepare(a)
            reqs = sorted(p.name for p in work.glob("request-fit-*.json"))
            self.assertEqual(len(reqs), 4 * 2)   # 3 draws at 2 per request -> 2 chunks per point
            req = json.loads((work / "request-fit-nominal-00.json").read_text())
            self.assertEqual(len(req["decks"]), 2 * 3)
            self.assertEqual(req["backend"], "batch")
            self.assertEqual(req["models"], {"pdk": "pdk", "pdk_root": "/opt/pdk"})
            self.assertEqual(req["batch"]["capacity_wait_s"], 60)
            self.assertEqual(req["decks"][0]["timeout_s"], 300)
            self.assertNotIn("netlist", req)
            self.assertNotIn("corners", req)
            deck = (work / req["decks"][0]["deck"]).read_text()
            self.assertIn('.lib "/opt/pdk/pdk/m.lib"', deck)   # runner paths in fleet decks
            self.assertIn("rndseed=1 ", deck)

    def test_sanity_request_is_local_and_two_units(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "t.tmpl").write_text(TEMPLATE)
            seed_csv = work / "s.csv"
            with seed_csv.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["corner_label", "temp_c", "vdd_v", "status", "fb_final_v",
                            "sns1_final_v", "sns2_final_v", "vref_final_v"])
                w.writerow(["typ", "27", "3.30", "PASS", "2", "0.7", "0.7", "1.05"])
            a = argparse.Namespace(
                stage="sanity", work=str(work), template=str(work / "t.tmpl"),
                seed_csv=str(seed_csv), msense_w="10u", dut_sha="s", pdk="pdk",
                local_pdk_root="/lr", local_osdi_dir="/lo", seed=20260930, n=300, codes=None,
                batch_pdk_root="/opt/pdk", batch_osdi_dir="/opt/o", provision=None,
                sanity_backend="local", draws_per_request=100, capacity_wait_s=60)
            tm.prepare(a)
            req = json.loads((work / "request-sanity.json").read_text())
            self.assertEqual(req["backend"], "local")
            self.assertEqual([u["id"] for u in req["decks"]], ["sanity-negctrl", "sanity-nominal"])
            self.assertIn('"/lr/pdk/m.lib"', (work / "decks/sanity-negctrl.spice").read_text())


class SanityGateTests(unittest.TestCase):
    def anchor(self, d: Path):
        p = d / "anchor.csv"
        p.write_text("point,mismatch_mode,draw_index,seed,corner_label,fit0_vref_v\n"
                     "nominal,mismatch,0,100,typ,7.14e-01\nnegctrl,negctrl,0,100,typ,7.33e-01\n")
        return p

    def run_gate(self, neg, nom, tol=5e-4):
        with tempfile.TemporaryDirectory() as d:
            art = Path(d) / "art"
            put_unit(art, "", "sanity-negctrl", stdout(neg))
            put_unit(art, "", "sanity-nominal", stdout(nom))
            tm.check_sanity(argparse.Namespace(artifacts=str(art), anchor_csv=str(self.anchor(Path(d))),
                                               seed=100, tol=tol))

    def test_negctrl_match_passes_even_if_nominal_draw_differs(self):
        self.run_gate("7.33e-01", "7.50e-01")

    def test_negctrl_mismatch_fails(self):
        with self.assertRaises(SystemExit):
            self.run_gate("7.40e-01", "7.14e-01")


if __name__ == "__main__":
    unittest.main()
