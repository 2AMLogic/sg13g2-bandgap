#!/usr/bin/env python3
"""Regression tests for the loop-gain solve-quality gate (issue #289).

Replays COMMITTED responses (read-only) through tools/solve_quality.py and
through the klt_trim_axis.py record path, so the shell bench's helper call and
the fleet recorder are exercised on the same known-corrupted and known-clean
data. Run:  python3 sim/loop-gain-phase-margin/tools/test_solve_quality.py
"""
from __future__ import annotations

import argparse
import cmath
import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
EXP = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import klt_trim_axis as kta  # noqa: E402
import solve_quality as sq  # noqa: E402

CORNERS = EXP / "corners"
# (record, unit) -> committed response
CORRUPT = [
    ("20261001-085806-e5507b2", "wcs_125c_2.97v"),        # the 36.3 deg "margin"
    ("20260829-103017-1d98d88", "fs_125c_3.63v"),         # the 43.9 deg / -16.26 dB
    ("20260829-115938-6fa92b5", "fs_125c_3.63v"),
    ("20261003-151849-bc6b7ce", "wcs_code32_np_125c_2.97v"),    # coarse (dec 30)
    ("20261003-151849-bc6b7ce", "wcs_code192_fine_125c_2.97v"),  # fine (dec 300)
    ("20261003-151849-bc6b7ce", "wcs_code128_np_125c_2.97v"),     # the anchor's deck, coarse
    ("20261003-151849-bc6b7ce", "wcs_code128_np_fine_125c_2.97v"),  # the anchor's deck, fine
]
CLEAN = [
    ("20261003-151849-bc6b7ce", "wcs_code128_125c_2.97v"),        # probe, coarse (carries the NaN msg)
    ("20261003-151849-bc6b7ce", "wcs_code128_fine_125c_2.97v"),   # probe, fine
    ("20261003-151849-bc6b7ce", "wcs_code160_np_125c_2.97v"),     # np, coarse
    ("20261003-151849-bc6b7ce", "wcs_code160_np_fine_125c_2.97v"),  # np, fine
    ("20261003-151849-bc6b7ce", "wcs_code0_np_fine_125c_2.97v"),    # worst clean (0.6643)
]


def load(record: str, unit: str):
    return sq.read_ac_txt(CORNERS / record / f"{unit}.ac.txt")


def smooth_rows(n_per_dec: int = 30, dc_db: float = 46.0, pole_hz: float = 3e7,
                phase_at_xover: float | None = None) -> list[sq.Row]:
    """A clean single-pole-ish response 1 Hz..1 GHz; phase constant-ish."""
    rows = []
    n = 9 * n_per_dec
    for k in range(n + 1):
        f = 10 ** (k / n_per_dec)
        mag = dc_db - 10 * math.log10(1 + (f / pole_hz) ** 2)
        ph = 180.0 if phase_at_xover is None else phase_at_xover
        rows.append((f, mag, ph))
    return rows


class MetricTests(unittest.TestCase):
    def test_committed_corrupted_responses_rejected(self):
        for record, unit in CORRUPT:
            with self.subTest(record=record, unit=unit):
                ok, ripple, reason = sq.assess(load(record, unit))
                self.assertFalse(ok)
                self.assertEqual(reason, "ripple_exceeds_threshold")
                self.assertGreaterEqual(ripple, 4.0985 - 1e-4)

    def test_committed_clean_responses_accepted_coarse_and_fine(self):
        for record, unit in CLEAN:
            with self.subTest(record=record, unit=unit):
                ok, ripple, reason = sq.assess(load(record, unit))
                self.assertTrue(ok, (ripple, reason))
                self.assertEqual(reason, "none")
                self.assertLessEqual(ripple, 0.6643 + 1e-4)

    def test_calibration_gap_over_every_committed_unit(self):
        """No committed ac.txt reads between the clean max and corrupted min,
        so 1.0 dB sits in a gap that is actually empty."""
        values = []
        for ac in CORNERS.glob("*/*.ac.txt"):
            rows = sq.read_ac_txt(ac)
            if rows and len(rows) >= 100 and rows[0][0] <= 1.5 and 20 < rows[0][1] < 60:
                values.append(sq.ripple_db(rows))
        self.assertGreater(len(values), 100)
        self.assertEqual([v for v in values if 0.6644 < v < 4.0984], [])
        self.assertTrue(any(v >= 4.0984 for v in values))

    def test_log_nan_message_is_not_a_criterion(self):
        """Clean units whose logs carry the ngspice 'temperature limiting NaN'
        message are still classified by response quality (accepted)."""
        needle = "temperature limiting function received NaN"
        seen = 0
        for record, unit in CLEAN[:1]:
            log = (CORNERS / record / f"{unit}.log").read_text(encoding="utf-8", errors="replace")
            if needle in log:
                seen += 1
                self.assertTrue(sq.assess(load(record, unit))[0], unit)
        # every committed clean unit that carries the message must be accepted;
        # find at least one such clean unit in the whole record to prove the point
        if not seen:
            for ac in (CORNERS / "20261003-151849-bc6b7ce").glob("*.ac.txt"):
                log = ac.with_name(ac.name[:-len(".ac.txt")] + ".log")
                if needle in log.read_text(encoding="utf-8", errors="replace"):
                    ok, ripple, _ = sq.assess(sq.read_ac_txt(ac))
                    if ok:
                        seen += 1
                        break
        self.assertGreater(seen, 0, "no clean unit with the NaN message found")

    def test_threshold_boundary(self):
        base = smooth_rows(pole_hz=1e15)  # flat, so a spike's ripple is the spike
        band = [n for n, (f, _, _) in enumerate(base) if 1e7 <= f <= 2e8]
        mid = band[len(band) // 2]

        def with_spike(delta):
            rows = list(base)
            f, m, p = rows[mid]
            rows[mid] = (f, m + delta, p)
            return rows

        self.assertTrue(sq.assess(with_spike(sq.RIPPLE_MAX_DB - 0.001))[0])
        self.assertFalse(sq.assess(with_spike(sq.RIPPLE_MAX_DB + 0.001))[0])
        # spike outside the band is not seen (documented limit)
        rows = list(base)
        f, m, p = rows[5]
        rows[5] = (f, m + 20, p)
        self.assertTrue(sq.assess(rows)[0])

    def test_missing_truncated_nonfinite_insufficient(self):
        base = smooth_rows()
        self.assertEqual(sq.assess(None)[2], "no_data")
        self.assertEqual(sq.assess([])[2], "no_data")
        self.assertEqual(sq.assess(base[: len(base) // 2])[2], "truncated_sweep")
        self.assertEqual(sq.assess(base[10:])[2], "truncated_sweep")
        bad = list(base)
        bad[100] = (bad[100][0], math.nan, 0.0)
        self.assertEqual(sq.assess(bad)[2], "non_finite")
        bad[100] = (bad[100][0], math.inf, 0.0)
        self.assertEqual(sq.assess(bad)[2], "non_finite")
        sparse = [r for r in base if not (1e7 <= r[0] <= 2e8)] + [r for r in base if r[0] == 1e7]
        sparse.sort()
        self.assertEqual(sq.assess(sparse)[2], "insufficient_band_points")

    def test_read_ac_txt_unparseable_is_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.ac.txt"
            path.write_text(" 1.0 nan 1.0 0\n 2.0 abc 2.0 0\n", encoding="utf-8")
            self.assertEqual(sq.assess(sq.read_ac_txt(path))[2], "non_finite")
            self.assertIsNone(sq.read_ac_txt(Path(tmp) / "missing"))
            (Path(tmp) / "empty").write_text("", encoding="utf-8")
            self.assertIsNone(sq.read_ac_txt(Path(tmp) / "empty"))

    def test_cli_matches_assess(self):
        """The shell bench's interface (one line, exit 0)."""
        def run(path):
            out = subprocess.run([sys.executable, str(TOOLS / "solve_quality.py"), "check", str(path)],
                                 capture_output=True, text=True, check=True)
            return out.stdout.split()
        bad = run(CORNERS / CORRUPT[0][0] / f"{CORRUPT[0][1]}.ac.txt")
        self.assertEqual(bad[0], "REJECT")
        self.assertEqual(bad[2], "ripple_exceeds_threshold")
        self.assertAlmostEqual(float(bad[1]), 15.0336, places=3)
        good = run(CORNERS / CLEAN[2][0] / f"{CLEAN[2][1]}.ac.txt")
        self.assertEqual(good[0], "OK")
        self.assertEqual(good[2], "none")
        self.assertEqual(run("/nonexistent/x.ac.txt"), ["REJECT", "-", "no_data"])


class DecideTests(unittest.TestCase):
    def test_rejected_cannot_pass_via_any_route(self):
        # a rejected solve with a healthy-looking crossing ...
        self.assertEqual(sq.decide(False, True, "FOUND", 95.0, False)[0], "FAIL")
        # ... and via the marginal-notch exception
        v, crossing_ok, used = sq.decide(False, True, "NONE", None, True)
        self.assertEqual((v, crossing_ok, used), ("FAIL", False, False))

    def test_clean_marginal_notch_still_passes(self):
        self.assertEqual(sq.decide(True, True, "NONE", None, True), ("PASS", True, True))
        self.assertEqual(sq.decide(True, True, "NONE", None, False)[0], "FAIL")

    def test_clean_low_but_positive_margin_passes_unstable_fails(self):
        self.assertEqual(sq.decide(True, True, "FOUND", 3.0, False)[0], "PASS")
        self.assertEqual(sq.decide(True, True, "FOUND", 0.0, False)[0], "FAIL")
        self.assertEqual(sq.decide(True, True, "FOUND", -12.0, True)[0], "FAIL")  # notch can't soften FOUND

    def test_op_check_still_effective(self):
        self.assertEqual(sq.decide(True, False, "FOUND", 60.0, False)[0], "FAIL")

    def test_clean_unstable_crossing_end_to_end(self):
        rows = smooth_rows(pole_hz=2e5, phase_at_xover=-20.0)
        ok, _, _ = sq.assess(rows)
        self.assertTrue(ok)
        with tempfile.TemporaryDirectory() as tmp:
            ac = Path(tmp) / "u.ac.txt"
            kta.write_ac_txt(rows, ac)
            status, _fc, pm, *_ = kta.crossover(ac)
        self.assertEqual(status, "FOUND")
        self.assertLess(float(pm), 0)
        self.assertEqual(sq.decide(ok, True, status, float(pm), False)[0], "FAIL")


def write_raw(path: Path, rows: list[sq.Row], op_fb: float) -> None:
    names = ["frequency", "v(fb_src)", "v(fb_load)", "v(op_fb)"]
    lines = ["Title: test", "Plotname: AC Analysis", "Flags: complex", f"No. Variables: {len(names)}",
             f"No. Points: {len(rows)}", "Variables:"]
    lines += [f"\t{n}\t{nm}\tfrequency" for n, nm in enumerate(names)]
    lines.append("Values:")
    for k, (f, mag, ph) in enumerate(rows):
        t = 10 ** (mag / 20) * cmath.exp(1j * math.radians(ph))
        lines.append(f" {k}\t{f:.9e},0")
        lines.append(f"\t{t.real:.9e},{t.imag:.9e}")
        lines.append("\t1,0")
        lines.append(f"\t{op_fb:.9e},0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RecorderPathTests(unittest.TestCase):
    """cmd_record over a hand-built report: one clean unit (code 128) and one
    corrupted unit (code 64) at the same PVT point -- the fleet recorder's
    verdict path on committed responses."""

    def test_record_rejects_corrupt_and_publishes_clean(self):
        seeds = kta.lookup_seeds("wcs", "125", "2.97")
        seed_fb = float(seeds["fb"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            work = tmp / "work"
            pdir = work / kta.point_name("wcs", "125", "2.97", "bench", "probe")
            pdir.mkdir(parents=True)
            (pdir / "body.spice").write_text("* body\n", encoding="utf-8")
            (pdir / "point.json").write_text(json.dumps({"pdk_root": "/opt/pdk"}), encoding="utf-8")
            units = [(128, CLEAN[0]), (64, CORRUPT[0])]
            corners = []
            for code, (record, unit) in units:
                raw = pdir / f"code{code}.raw"
                write_raw(raw, load(record, unit), seed_fb)
                corners.append({
                    "status": "pass",
                    "supply_v": kta.strap_values(code),
                    "measurements": [{"name": "fb_op_v", "value": seed_fb}],
                    "artifacts": {"raw": str(raw)},
                })
            (pdir / "report.json").write_text(json.dumps({"status": "pass", "corners": corners}),
                                              encoding="utf-8")
            exp = tmp / "exp"
            (exp / "records").mkdir(parents=True)
            args = argparse.Namespace(work=str(work), experiment=str(exp), record_id="20260101-000000-test",
                                      plan="pvt")
            kta.cmd_record(args)
            with (exp / "records" / "20260101-000000-test.csv").open(newline="", encoding="utf-8") as fh:
                rows = {r["trim_code"]: r for r in csv.DictReader(fh)}
            clean, bad = rows["128"], rows["64"]
            self.assertEqual((clean["status"], clean["quality"]), ("PASS", "ok"))
            self.assertTrue(clean["phase_margin_deg"])
            self.assertEqual((bad["status"], bad["quality"]), ("FAIL", "inconclusive"))
            self.assertEqual(bad["reject_reason"], "ripple_exceeds_threshold")
            self.assertEqual((bad["phase_margin_deg"], bad["crossover_hz"]), ("", ""))
            self.assertTrue(bad["ripple_db"] and bad["dc_gain_db"])  # diagnostics kept
            md = (exp / "records" / "20260101-000000-test.md").read_text(encoding="utf-8")
            self.assertIn("Inconclusive points", md)
            self.assertTrue((exp / "corners" / "20260101-000000-test" / "wcs_code64_125c_2.97v.ac.txt").is_file())

    def test_np_twin_must_be_clean_and_op_checked(self):
        """A control (np) row cannot take equilibrium evidence from a corrupted probe twin."""
        seeds = kta.lookup_seeds("wcs", "125", "2.97")
        seed_fb = float(seeds["fb"])
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            work = tmp / "work"
            for variant, resp in (("probe", CORRUPT[3]), ("np", CLEAN[2])):
                pdir = work / kta.point_name("wcs", "125", "2.97", "bench", variant)
                pdir.mkdir(parents=True)
                (pdir / "body.spice").write_text("* body\n", encoding="utf-8")
                (pdir / "point.json").write_text(json.dumps({"pdk_root": "/opt/pdk"}), encoding="utf-8")
                raw = pdir / "u.raw"
                write_raw(raw, load(*resp), seed_fb)
                meas = [{"name": "fb_op_v", "value": seed_fb}] if variant == "probe" else []
                (pdir / "report.json").write_text(json.dumps({"status": "pass", "corners": [{
                    "status": "pass", "supply_v": kta.strap_values(32), "measurements": meas,
                    "artifacts": {"raw": str(raw)}}]}), encoding="utf-8")
            # the np clean response and the corrupted probe twin must agree on DC gain
            # (both are wcs/125/2.97 code-128-matrix DC 46.3857 dB), so only quality differs.
            exp = tmp / "exp"
            (exp / "records").mkdir(parents=True)
            orig = kta.PLANS["characterization"]
            kta.PLANS["test"] = [p for p in orig if p[:2] == ("wcs", "125") and p[2] == "2.97"
                                 and p[3] == "bench"]
            try:
                kta.cmd_record(argparse.Namespace(work=str(work), experiment=str(exp),
                                                  record_id="20260101-000001-test", plan="test"))
            finally:
                del kta.PLANS["test"]
            with (exp / "records" / "20260101-000001-test.csv").open(newline="", encoding="utf-8") as fh:
                rows = {r["deck"]: r for r in csv.DictReader(fh)}
            self.assertEqual(rows["probe"]["status"], "FAIL")
            self.assertEqual(rows["np"]["quality"], "ok")
            self.assertEqual(rows["np"]["status"], "FAIL")  # twin evidence invalid


if __name__ == "__main__":
    unittest.main()
