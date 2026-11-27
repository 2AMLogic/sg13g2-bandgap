"""Regression tests for characterization report figures."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from spotcheck_common import iq, iq_signed_grade


def iq_envelope(corners, *, limits_min=-5e-05):
    """A closed-loop-iq `klt sim` envelope over `corners`.

    Each corner is `(corner_id, avg, sample, margin, status)`: the graded
    average, the two time samples (both `sample`) and the stored margin.
    """
    report = {
        "measurements": [
            {"name": "iq_2ms_a", "unit": None, "limits": None, "status": "pass", "worst_case": None},
            {"name": "iq_3ms_a", "unit": None, "limits": None, "status": "pass", "worst_case": None},
        ],
        "corners": [],
    }
    graded = None
    for corner_id, avg, sample, margin, status in corners:
        report["corners"].append({
            "corner_id": corner_id,
            "status": status,
            "measurements": [
                {"name": "iq_2ms_a", "value": sample, "status": "pass", "margin": None},
                {"name": "iq_3ms_a", "value": sample, "status": "pass", "margin": None},
                {"name": "iq_avg_a", "value": avg, "unit": "A", "status": status, "margin": margin},
            ],
        })
        if graded is None or margin < graded["margin"]:
            graded = {"corner_id": corner_id, "value": avg, "margin": margin}
    report["measurements"].append({
        "name": "iq_avg_a", "unit": "A", "limits": {"min": limits_min}, "status": "pass",
        "worst_case": graded, "spec_row": "iq",
    })
    return report


SIGNED = [  # avg keeps ngspice's sign; margin = avg - (-5e-05)
    ("wcs/-40C/2.97V", -1.95769e-05, 1.95769e-05, 3.04231e-05, "pass"),
    ("bcs/125C/3.63V", -4.17771e-05, 4.17771e-05, 8.2229e-06, "pass"),
]
LINE = (
    "Iq signed grade: 2/2 corners re-derived (avg < 0, samples >= 0, margin = avg - limits.min); "
    "limits.min -5e-05 A; binding bcs/125C/3.63V: avg -4.17771e-05 A, margin 8.2229e-06 A, pass; "
    "rollup names a smallest-margin corner"
)


class IqSpotcheckTests(unittest.TestCase):
    def test_signed_and_unsigned_csvs_report_the_same_current_magnitudes(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "iq"
            for sign in ("-", ""):
                with self.subTest(sign=sign):
                    record.with_suffix(".csv").write_text(
                        "corner_label,temp_c,vdd_v,status,iq_avg_a,iq_settle_delta_a\n"
                        f"wcs,-40,2.97,PASS,{sign}1.958e-5,0\n"
                        f"bcs,125,3.63,PASS,{sign}4.178e-5,0\n"
                        "typ,27,3.30,FAIL,,\n",
                        encoding="utf-8",
                    )
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        iq(str(record))
                    self.assertEqual(
                        output.getvalue().strip(),
                        "Iq sch trim-bearing: 2/3 PASS; 19.58..41.78 uA; "
                        "<50 uA: 2/2; <20 uA: 1/2; worst bcs/125C/3.63V; "
                        "margin to 50 uA 16.4%; max settle delta 0 A",
                    )


class IqSignedGradeTests(unittest.TestCase):
    def check(self, corners, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "iq"
            record.with_name("iq-report.json").write_text(
                json.dumps(iq_envelope(corners, **kwargs)), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                iq_signed_grade(str(record))
            return output.getvalue().strip()

    def test_rederives_every_corner_and_the_binding_corner(self):
        self.assertEqual(self.check(SIGNED), LINE)

    def test_rollup_may_name_either_of_two_equally_binding_corners(self):
        tied = SIGNED + [("typ/125C/3.63V", -4.17771e-05, 4.17771e-05, 8.2229e-06, "pass")]
        self.assertIn("rollup names a smallest-margin corner", self.check(tied))

    def test_refuses_the_pre_648_magnitude_rewritten_envelope(self):
        # The November 22 shape: the average was rewritten to a magnitude
        # while the margin stayed the one graded from the signed value.
        rewritten = [("bcs/125C/3.63V", 4.17771e-05, 4.17771e-05, 8.2229e-06, "pass")]
        with self.assertRaisesRegex(ValueError, "bcs/125C/3.63V: iq_avg_a 4.17771e-05"):
            self.check(rewritten)

    def test_refuses_a_negative_time_sample(self):
        with self.assertRaisesRegex(ValueError, "sf/27C/3.30V: iq_2ms_a -2.76224e-05 is not a magnitude"):
            self.check(SIGNED + [("sf/27C/3.30V", -2.76224e-05, -2.76224e-05, 2.23776e-05, "pass")])

    def test_refuses_a_margin_that_does_not_rederive(self):
        with self.assertRaisesRegex(ValueError, "margin 1e-05 differs from avg - limits.min"):
            self.check(SIGNED + [("sf/27C/3.30V", -2.76224e-05, 2.76224e-05, 1e-05, "pass")])

    def test_refuses_a_margin_whose_sign_disagrees_with_the_grade(self):
        with self.assertRaisesRegex(ValueError, "margin -1e-05 but status pass"):
            self.check(SIGNED + [("sf/27C/3.30V", -6e-05, 6e-05, -1e-05, "pass")])

    def test_refuses_a_rollup_that_names_a_corner_that_is_not_binding(self):
        envelope = iq_envelope(SIGNED)
        envelope["measurements"][-1]["worst_case"] = dict(envelope["measurements"][-1]["worst_case"],
                                                          corner_id="wcs/-40C/2.97V")
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "iq"
            record.with_name("iq-report.json").write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "rollup worst case names wcs/-40C/2.97V"):
                iq_signed_grade(str(record))

    def test_refuses_any_other_lower_limit(self):
        with self.assertRaisesRegex(ValueError, "limits.min -4e-05, not -5e-05"):
            self.check(SIGNED, limits_min=-4e-05)


if __name__ == "__main__":
    unittest.main()
