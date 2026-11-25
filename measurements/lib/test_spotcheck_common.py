"""Regression tests for characterization report figures."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from spotcheck_common import iq


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


if __name__ == "__main__":
    unittest.main()
