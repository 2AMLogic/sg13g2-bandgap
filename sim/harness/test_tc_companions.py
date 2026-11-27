#!/usr/bin/env python3
"""Self-test for the TC companions: boxtc_companion.py and tc_companion.py.

The box-method TC derivation used to be typed twice, inline, in the two
benches that share it (issue #465), and so did the endpoint method (issue
#496). Now one module per method sits behind the pex_vref_runner.sh seam,
and spec/decision-records/0010-box-method-tc-evidence.md ratifies the box
derivation's output as this block's TC evidence. So each derivation gets a
golden test against the committed records it produced, unit coverage of the
parts a correction would touch, a guard that the duplication cannot come
back, and a check that the CLI refuses an empty derivation loudly (issue
#510). Stdlib only. Every fixture is tiny and lives in memory or a temporary
directory: no ngspice, no PDK, no network, and nothing under sim/ is written.

    python3 sim/harness/test_tc_companions.py
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boxtc_companion as bxc  # noqa: E402
import tc_companion as tcc  # noqa: E402

HARNESS = Path(__file__).resolve().parent
SIM_DIR = HARNESS.parent


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()


# --------------------------------------------------------------------------
# boxtc_companion: the box-method TC derivation (issue #465). It used to be
# typed twice, inline, in the two benches that share it -- and
# spec/decision-records/0010-box-method-tc-evidence.md ratifies its output as
# this block's TC evidence, with the design sitting ON the 20 ppm/degC stretch
# line. So the derivation gets a golden test against the committed records it
# produced, unit coverage of the parts a correction would touch, and a guard
# that the duplication cannot come back.
# --------------------------------------------------------------------------

#: The two box-method benches and the committed record each minted.
BOXTC_BENCHES = {
    "closed-loop-vref-pvt-boxtc": "20260921-194249-77820fc",
    "closed-loop-vref-pvt-pex-boxtc": "20260921-195122-77820fc",
}


def boxtc_rows(points: list[tuple], corner: str = "typ", vdd: str = "3.30") -> list[dict]:
    """Record rows for one (corner, vdd) group from `(temp_c, vref, status)`."""
    return [
        {"corner_label": corner, "vdd_v": vdd, "temp_c": f"{t}",
         "vref_3ms_v": repr(v), "status": s}
        for t, v, s in points
    ]


#: A grid whose extremes are INTERIOR points, so the box method and the
#: endpoint method cannot agree: vref peaks at 50 C and bottoms at 0 C, while
#: -40 C and 125 C sit between them.
INTERIOR_EXTREMA = [
    (-40, 1.0400, "PASS"), (0, 1.0300, "PASS"), (27, 1.0500, "PASS"),
    (50, 1.0600, "PASS"), (125, 1.0450, "PASS"),
]


#: The endpoint benches and the newest committed record/companion pair each
#: carries -- the golden-test inputs for the endpoint derivation (issue #496).
TC_BENCHES = {
    "closed-loop-vref-pvt": "20261001-085908-e5507b2",
    "closed-loop-vref-pvt-pex": "20260905-114438-8abe2aa",
}


def endpoint_rows(points: list[tuple], corner: str = "typ",
                  vdd: str = "3.30") -> list[dict]:
    """Record rows for one (corner, vdd) group from `(temp_c, vref_3ms_v)`.

    `vref` may be a float or an already-rendered string -- the way the
    minted records carry it (`1.04695e+00`).
    """
    return [
        {"corner_label": corner, "vdd_v": vdd, "temp_c": f"{t}",
         "vref_3ms_v": v if isinstance(v, str) else repr(v)}
        for t, v in points
    ]


class BoxTcGoldenTests(unittest.TestCase):
    """The derivation still reproduces the committed evidence, byte for byte."""

    def test_committed_companions_regenerate_byte_identically(self) -> None:
        # The acceptance test for the de-duplication (#465): both benches'
        # committed -boxtc.csv must come back out of the shared module
        # unchanged, compared as raw bytes so a CRLF slip fails. sim/*/records/
        # is append-only evidence, so the same call must leave the committed
        # bytes and mtime untouched (guards against an EXP_DIR-relative
        # default). Read-only on sim/ -- output goes to a temp dir.
        for exp, stem in BOXTC_BENCHES.items():
            with self.subTest(exp=exp):
                records = SIM_DIR / exp / "records"
                committed = records / f"{stem}-boxtc.csv"
                before_mtime = committed.stat().st_mtime_ns
                before_bytes = committed.read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    got = Path(tmp) / "companion.csv"
                    bxc.write_companion(records / f"{stem}.csv", got)
                    self.assertEqual(got.read_bytes(), before_bytes)
                self.assertEqual(
                    (committed.stat().st_mtime_ns, committed.read_bytes()),
                    (before_mtime, before_bytes),
                )


class BoxTcFormulaTests(unittest.TestCase):
    """The parts of the derivation a correction would land on."""

    def one(self, points: list[tuple], **kw) -> list:
        rows = bxc.companion_rows(boxtc_rows(points, **kw))
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_box_is_the_worst_case_spread_not_the_endpoint_slope(self) -> None:
        # The whole point of the box method: the extremes are wherever they
        # fall on the grid, not at its ends. Here they are interior, so a
        # regression to an endpoint derivation changes the reported number.
        row = self.one(INTERIOR_EXTREMA)
        _, _, _, _, vmin, tmin, vmax, tmax, v27, box, endpoint = row
        self.assertEqual((float(vmin), tmin), (1.03, 0))
        self.assertEqual((float(vmax), tmax), (1.06, 50))
        self.assertAlmostEqual(float(box), 1e6 * (1.06 - 1.03) / (165 * 1.05), places=3)
        # ... and the endpoint figure is carried alongside, not instead of it.
        self.assertAlmostEqual(
            float(endpoint), 1e6 * (1.045 - 1.040) / (165 * 1.05), places=3
        )
        self.assertNotAlmostEqual(float(box), float(endpoint), places=1)

    def test_span_is_the_165_degree_grid(self) -> None:
        # The committed records disclose a 165 degC span (-40..125). It is the
        # formula's denominator, so it is a named constant, not a literal
        # repeated per copy.
        self.assertEqual(bxc.SPAN_C, 165)
        row = self.one([(-40, 1.0, "PASS"), (27, 1.0, "PASS"), (125, 1.1, "PASS")])
        self.assertAlmostEqual(float(row[9]), 1e6 * 0.1 / (165 * 1.0), places=3)

    def test_failing_points_are_excluded_from_the_number_but_disclosed(self) -> None:
        # A FAIL point must not set vmin/vmax -- it never converged -- but
        # n_grid still reports it, so n_pass/n_grid discloses the coverage
        # behind the figure.
        row = self.one([
            (-40, 0.5, "FAIL"), (0, 1.04, "PASS"), (27, 1.05, "PASS"),
            (125, 1.06, "PASS"),
        ])
        self.assertEqual((row[2], row[3]), (3, 4))        # n_pass, n_grid
        self.assertEqual(float(row[4]), 1.04)             # vmin, not the 0.5 FAIL
        self.assertEqual(row[10], "")                     # -40 C absent: no endpoint

    def test_group_without_a_passing_27c_point_is_omitted(self) -> None:
        # v27 is the denominator. Without it the derivation has no value, so
        # the group is omitted rather than reported from a substitute.
        for points in (
            [(-40, 1.04, "PASS"), (125, 1.06, "PASS")],                  # no 27 C
            [(-40, 1.04, "PASS"), (27, 1.05, "FAIL"), (125, 1.06, "PASS")],
        ):
            with self.subTest(points=points):
                self.assertEqual(bxc.companion_rows(boxtc_rows(points)), [])

    def test_group_with_no_passing_point_is_omitted(self) -> None:
        self.assertEqual(
            bxc.companion_rows(boxtc_rows([(27, 1.05, "FAIL")])), []
        )

    def test_absent_group_is_skipped_not_reported_empty(self) -> None:
        rows = bxc.companion_rows(boxtc_rows(INTERIOR_EXTREMA, corner="wcs", vdd="2.97"))
        self.assertEqual([(r[0], r[1]) for r in rows], [("wcs", "2.97")])

    def test_rows_follow_the_committed_grid_order(self) -> None:
        # Row order is part of the committed CSV's shape: corner-major over
        # (typ, bcs, wcs, sf, fs) x (2.97, 3.30, 3.63).
        rows: list[dict] = []
        for corner in reversed(bxc.CORNERS):
            for vdd in reversed(bxc.VDDS):
                rows += boxtc_rows(INTERIOR_EXTREMA, corner=corner, vdd=vdd)
        got = [(r[0], r[1]) for r in bxc.companion_rows(rows)]
        self.assertEqual(got, [(c, v) for c in bxc.CORNERS for v in bxc.VDDS])

    def test_header_matches_the_committed_companions(self) -> None:
        for exp, stem in BOXTC_BENCHES.items():
            with self.subTest(exp=exp):
                committed = (SIM_DIR / exp / "records" / f"{stem}-boxtc.csv").read_text()
                self.assertEqual(committed.splitlines()[0], ",".join(bxc.HEADER))

    def test_companion_is_newline_terminated_not_crlf(self) -> None:
        # csv.writer defaults to \r\n; the committed records are \n.
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "r.csv", Path(tmp) / "c.csv"
            with src.open("w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(["corner_label", "vdd_v", "temp_c", "vref_3ms_v", "status"])
                for t, v, s in INTERIOR_EXTREMA:
                    w.writerow(["typ", "3.30", t, v, s])
            bxc.write_companion(src, dst)
            self.assertNotIn(b"\r", dst.read_bytes())


class BoxTcSeamTests(TempDirCase):
    """The shell side: one shared implementation, and it stays shared."""

    def test_both_box_benches_delegate_to_the_shared_companion(self) -> None:
        for exp in BOXTC_BENCHES:
            with self.subTest(exp=exp):
                script = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
                self.assertIn("pex_boxtc_companion", hook)
                # The formula must not be re-typed here -- that is the
                # duplication #465 removed. No inline heredoc, no formula.
                self.assertNotIn("python3 - ", hook)
                self.assertNotIn("1e6", hook)
                self.assertNotIn("csv.writer", hook)
                self.assertIn('source "${HARNESS_DIR}/pex_vref_runner.sh"', script)

    def test_the_shared_companion_defers_the_formula_to_the_module(self) -> None:
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        body = runner.split("pex_boxtc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("boxtc_companion.py", body)
        self.assertNotIn("1e6", body)
        # The input filter is the box benches' own: it drops both companion
        # kinds. The two helpers' filters differ on purpose (#496): the
        # endpoint helper drops -vs-schematic instead.
        self.assertIn("grep -v -e '-boxtc.csv' -e '-tc.csv'", body)

    def test_the_endpoint_bench_keeps_its_own_different_body(self) -> None:
        # Reframed for #496: its premise -- the endpoint bench re-types its
        # own endpoint-method body -- became false by design when that body
        # moved into sim/harness/tc_companion.py. What remains true is the
        # separation it guarded: the endpoint bench delegates to the
        # *endpoint* companion, never the box one.
        script = (SIM_DIR / "closed-loop-vref-pvt-pex" / "run_klt_sim.sh").read_text()
        hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("pex_endpoint_tc_companion", hook)
        self.assertNotIn("pex_boxtc_companion", hook)
        self.assertNotIn("boxtc_companion", hook)

    def test_the_trim_bench_box_derivation_matches_the_module(self) -> None:
        # closed-loop-vref-boxtc-trim carries a third copy of the box
        # derivation: an awk body inside run_pvt_sweep.sh, which does not
        # source pex_vref_runner.sh, so the pex_boxtc_companion seam cannot
        # reach it (#474; delegating it is out of scope there). The copy is
        # load-bearing -- its -boxtc.csv feeds the trim-induced-TC gate that
        # DR-0013 cites -- so a correction applied to boxtc_companion.py
        # alone would silently leave the bench reporting the old derivation.
        # Until the bench delegates, this tripwire makes that divergence red.
        script = (SIM_DIR / "closed-loop-vref-boxtc-trim" / "run_pvt_sweep.sh").read_text()

        # The span is parsed from the bench and compared to the module's:
        # restating 165 on both sides would check nothing.
        span = re.search(r"TEMP_SPAN_C[ \t]*=[ \t]*([0-9]+)", script)
        self.assertIsNotNone(
            span,
            "TEMP_SPAN_C= is gone from the trim bench; its awk span must "
            "still equal boxtc_companion.SPAN_C "
            f"({bxc.SPAN_C}). boxtc_companion.py is the one place to "
            "correct the box derivation.")
        self.assertEqual(
            int(span.group(1)), bxc.SPAN_C,
            f"the trim bench's box span (TEMP_SPAN_C={span.group(1)}) no "
            f"longer equals boxtc_companion.SPAN_C ({bxc.SPAN_C}): correct "
            "boxtc_companion.py first, then this bench.")
        self.assertIn(
            '-v span="${TEMP_SPAN_C}"', script,
            "the trim bench's awk no longer takes its span from "
            "TEMP_SPAN_C; boxtc_companion.py is the one place to correct "
            "the box derivation.")

        # The box awk itself: same formula shape and PASS filter as the
        # module's group loop.
        awk_m = re.search(r"'(.*?)' \"\$\{CSV_OUT\}\"",
                          script.split('-v span="${TEMP_SPAN_C}"', 1)[1],
                          re.DOTALL)
        self.assertIsNotNone(
            awk_m,
            "the trim bench's box-TC awk is gone or no longer writes to "
            "${CSV_OUT}; boxtc_companion.py is the one place to correct "
            "the box derivation.")
        awk_prog = awk_m.group(1)
        self.assertIn(
            "1e6 * (vmax - vmin) / (span * v27)", awk_prog,
            "the trim bench's box formula drifted from the module's "
            "1e6 * (vmax - vmin) / (span * v27); boxtc_companion.py is the "
            "one place to correct the derivation.")
        self.assertIn(
            '$scol == "PASS"', awk_prog,
            "the trim bench's box derivation dropped the PASS-point filter; "
            "boxtc_companion.py is the one place to correct the derivation.")

        # Same rounding the module emits: %.5g voltages, %d integer
        # temperatures and counts, %.3f box_tc_ppm_per_c -- positionally, in
        # the companion header's column order.
        fmt = re.search(r'printf "([^"]+)"', awk_prog)
        self.assertIsNotNone(
            fmt,
            "the trim bench's box printf is gone; its companion rounding "
            "must match boxtc_companion.py's emission.")
        convs = fmt.group(1).split("\\n")[0].split(",")
        self.assertEqual(
            convs,
            ["%s", "%s", "%s", "%d", "%d",
             "%.5g", "%d", "%.5g", "%d", "%.5g", "%.3f"],
            "the trim bench's companion rounding drifted from "
            "boxtc_companion.py's (%.5g voltages, %d temperatures/counts, "
            "%.3f box_tc_ppm_per_c): correct boxtc_companion.py first, "
            "then this bench.")

    def test_shared_companion_picks_the_record_over_its_own_companions(self) -> None:
        # `ls -t` picks the newest CSV, so a companion derived by an earlier
        # run -- which is newer than the record -- must be filtered out, or
        # the derivation would consume its own output.
        records = self.tmp / "records"
        records.mkdir()
        exp, stem = next(iter(BOXTC_BENCHES.items()))
        committed = SIM_DIR / exp / "records"
        (records / f"{stem}.csv").write_bytes((committed / f"{stem}.csv").read_bytes())
        # Companions, all newer than the record, all of which must be skipped.
        for name in (f"{stem}-boxtc.csv", f"{stem}-tc.csv",
                     f"{stem}-vs-schematic-boxtc.csv"):
            (records / name).write_text("corner_label,garbage\nbad,row\n")
            os.utime(records / name, (time.time() + 10, time.time() + 10))
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'EXP_DIR="{self.tmp}"; '
            f'source "$HARNESS_DIR/pex_vref_runner.sh"; pex_boxtc_companion'
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (records / f"{stem}-boxtc.csv").read_text(),
            (committed / f"{stem}-boxtc.csv").read_text(),
        )


class EndpointTcGoldenTests(unittest.TestCase):
    """The endpoint derivation still reproduces the committed evidence."""

    def test_committed_companions_regenerate_byte_identically(self) -> None:
        # The acceptance test for the de-duplication (#496): both benches'
        # committed -tc.csv must come back out of the shared module
        # unchanged, byte for byte -- including the header and the absence
        # of CRLF, which the raw-bytes comparison enforces. sim/*/records/
        # is append-only evidence, so the same call must leave the committed
        # bytes and mtime untouched (guards against an EXP_DIR-relative
        # default). Read-only on sim/ -- output goes to a temp dir.
        for exp, stem in TC_BENCHES.items():
            with self.subTest(exp=exp):
                records = SIM_DIR / exp / "records"
                committed = records / f"{stem}-tc.csv"
                before_mtime = committed.stat().st_mtime_ns
                before_bytes = committed.read_bytes()
                with tempfile.TemporaryDirectory() as tmp:
                    got = Path(tmp) / "companion.csv"
                    tcc.write_companion(records / f"{stem}.csv", got)
                    self.assertEqual(got.read_bytes(), before_bytes)
                self.assertEqual(
                    (committed.stat().st_mtime_ns, committed.read_bytes()),
                    (before_mtime, before_bytes),
                )


class EndpointTcFormulaTests(unittest.TestCase):
    """The parts of the derivation a correction would land on."""

    def one(self, points: list[tuple], **kw) -> list:
        rows = tcc.companion_rows(endpoint_rows(points, **kw))
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_tc_is_the_two_endpoint_slope(self) -> None:
        # 1e6 * (v125 - vn40) / (165 * v27): the grid's endpoints, not the
        # box method's worst-case spread -- interior extrema must not move
        # the number. (The INTERIOR_EXTREMA grid, without status: the
        # endpoint derivation does not read it.)
        row = self.one([(-40, 1.0400), (0, 1.0300), (27, 1.0500),
                        (50, 1.0600), (125, 1.0450)])
        self.assertEqual(row[:2], ["typ", "3.30"])
        self.assertAlmostEqual(
            float(row[5]), 1e6 * (1.045 - 1.04) / (165 * 1.05), places=3)
        self.assertNotAlmostEqual(
            float(row[5]), 1e6 * (1.06 - 1.03) / (165 * 1.05), places=1)

    def test_values_pass_through_verbatim_not_rerendered(self) -> None:
        # The committed convention: the record's own strings are echoed, not
        # re-rendered through Python floats -- vdd_v as `3.30`, voltages at
        # the record's precision. This is exactly the regression the inline
        # hook this module replaces would have minted (#496).
        row = self.one([(-40, "1.04695e+00"), (27, "1.04705e+00"),
                        (125, "1.04201e+00")])
        self.assertEqual(row, ["typ", "3.30", "1.04695e+00", "1.04705e+00",
                               "1.04201e+00", "-28.594"])

    def test_span_is_the_165_degree_grid(self) -> None:
        # The committed companions disclose a 165 degC span (-40..125). It
        # is the formula's denominator, so it is a named constant, not a
        # literal repeated per copy.
        self.assertEqual(tcc.SPAN_C, 165)
        row = self.one([(-40, 1.04), (27, 1.05), (125, 1.14)])
        self.assertAlmostEqual(float(row[5]), 1e6 * 0.1 / (165 * 1.05),
                               places=3)

    def test_group_missing_an_endpoint_temperature_is_omitted(self) -> None:
        # No denominator (27 C), or a missing slope endpoint: the derivation
        # has no value, so the group is omitted rather than reported from a
        # substitute or a crash (the old hook's
        # `except (KeyError, ValueError): continue`).
        for points in (
            [(-40, 1.047), (125, 1.042)],        # no 27 C: no denominator
            [(27, 1.047), (125, 1.042)],         # no -40 C
            [(-40, 1.047), (27, 1.047)],         # no 125 C
        ):
            with self.subTest(points=points):
                self.assertEqual(tcc.companion_rows(endpoint_rows(points)), [])

    def test_unparseable_voltage_is_omitted_not_crashed(self) -> None:
        self.assertEqual(
            tcc.companion_rows(
                endpoint_rows([(-40, 1.047), (27, "not-a-number"),
                               (125, 1.042)])
            ),
            [],
        )

    def test_rows_follow_the_committed_grid_order(self) -> None:
        # Row order is part of the committed CSV's shape: corner-major over
        # (typ, bcs, wcs, sf, fs) x (2.97, 3.30, 3.63).
        rows: list[dict] = []
        for corner in reversed(tcc.CORNERS):
            for vdd in reversed(tcc.VDDS):
                rows += endpoint_rows([(-40, 1.04695), (27, 1.04705),
                                       (125, 1.04201)],
                                      corner=corner, vdd=vdd)
        got = [(r[0], r[1]) for r in tcc.companion_rows(rows)]
        self.assertEqual(got, [(c, v) for c in tcc.CORNERS for v in tcc.VDDS])

    def test_header_matches_the_committed_companions(self) -> None:
        for exp, stem in TC_BENCHES.items():
            with self.subTest(exp=exp):
                committed = (SIM_DIR / exp / "records" / f"{stem}-tc.csv").read_text()
                self.assertEqual(committed.splitlines()[0], ",".join(tcc.HEADER))

    def test_companion_is_newline_terminated_not_crlf(self) -> None:
        # csv.writer defaults to \r\n; the committed companions are \n. The
        # inline hook this module replaces had exactly this bug (#496).
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "r.csv", Path(tmp) / "c.csv"
            with src.open("w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(["corner_label", "vdd_v", "temp_c", "vref_3ms_v"])
                for t, v in [(-40, 1.04695), (27, 1.04705), (125, 1.04201)]:
                    w.writerow(["typ", "3.30", t, repr(v)])
            tcc.write_companion(src, dst)
            self.assertNotIn(b"\r", dst.read_bytes())


class EndpointTcSeamTests(TempDirCase):
    """The shell side: one shared implementation, and it stays shared."""

    ENDPOINT_BENCHES = ("closed-loop-vref-pvt", "closed-loop-vref-pvt-pex")

    def test_both_endpoint_benches_delegate_to_the_shared_companion(self) -> None:
        for exp in self.ENDPOINT_BENCHES:
            with self.subTest(exp=exp):
                script = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                hook = script.split("pex_record_companion() {", 1)[1].split("\n}\n", 1)[0]
                self.assertIn("pex_endpoint_tc_companion", hook)
                # The formula must not be re-typed here -- that is the
                # duplication #496 removed. No inline heredoc, no formula.
                self.assertNotIn("python3 - ", hook)
                self.assertNotIn("1e6", hook)
                self.assertNotIn("csv.writer", hook)
                self.assertIn('source "${HARNESS_DIR}/pex_vref_runner.sh"', script)

    def test_the_shared_companion_defers_the_formula_to_the_module(self) -> None:
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        body = runner.split("pex_endpoint_tc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("tc_companion.py", body)
        self.assertNotIn("1e6", body)
        # The input filter is the endpoint benches' own: it drops the
        # companion kind and the extracted benches' -vs-schematic artifacts
        # (a no-op on the schematic twin). The two helpers' filters differ
        # on purpose (#496).
        self.assertIn("grep -v -e '-tc.csv' -e '-vs-schematic'", body)

    def test_the_two_tc_companions_stay_separate_derivations(self) -> None:
        # The endpoint and box methods must not collapse into one module or
        # one helper: different column sets, different companions, and a
        # ratified decision record behind one of them (#465).
        runner = (SIM_DIR / "harness" / "pex_vref_runner.sh").read_text()
        endpoint = runner.split("pex_endpoint_tc_companion() {", 1)[1].split("\n}\n", 1)[0]
        box = runner.split("pex_boxtc_companion() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("${HARNESS_DIR}/tc_companion.py", endpoint)
        self.assertIn("-tc.csv", endpoint)
        self.assertNotIn("boxtc_companion", endpoint)
        self.assertIn("${HARNESS_DIR}/boxtc_companion.py", box)
        self.assertIn("-boxtc.csv", box)
        self.assertNotIn("${HARNESS_DIR}/tc_companion.py", box)

    def test_shared_companion_picks_the_record_over_its_own_companions(self) -> None:
        # `ls -t` picks the newest CSV, so a companion derived by an earlier
        # run -- which is newer than the record -- must be filtered out, or
        # the derivation would consume its own output.
        records = self.tmp / "records"
        records.mkdir()
        exp, stem = next(iter(TC_BENCHES.items()))
        committed = SIM_DIR / exp / "records"
        (records / f"{stem}.csv").write_bytes((committed / f"{stem}.csv").read_bytes())
        # Companions, all newer than the record, all of which must be skipped.
        for name in (f"{stem}-tc.csv", f"{stem}-vs-schematic.csv"):
            (records / name).write_text("corner_label,garbage\nbad,row\n")
            os.utime(records / name, (time.time() + 10, time.time() + 10))
        script = (
            f'set -euo pipefail; HARNESS_DIR="{SIM_DIR / "harness"}"; '
            f'EXP_DIR="{self.tmp}"; '
            f'source "$HARNESS_DIR/pex_vref_runner.sh"; pex_endpoint_tc_companion'
        )
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(
            (records / f"{stem}-tc.csv").read_text(),
            (committed / f"{stem}-tc.csv").read_text(),
        )


# --------------------------------------------------------------------------
# Loud failure when a derivation omits every group (issue #510). Both
# companions key their grid axes by the record's own strings (#496's
# pass-through convention) and omit any group whose key misses the grid, so
# a drifted key used to mint a header-only CSV and exit 0 -- empty evidence
# published as if it were derived. main() must refuse instead: non-zero
# exit, stderr naming the keys the record actually carried.
#
# Each companion is run the way the shell hooks run it -- `sys.executable
# <script>` -- because the exit status is the contract: the script hands
# main()'s return value to sys.exit, and an in-process call to main() never
# sees it (issue #746: a `return 7` passed every test).
# --------------------------------------------------------------------------


def write_record(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


RECORD_FIELDS = ["corner_label", "vdd_v", "temp_c", "vref_3ms_v", "status"]

#: The endpoint grid, as a healthy record writes it.
ENDPOINT_POINTS = [(-40, 1.04695), (27, 1.04705), (125, 1.04201)]

#: Each companion command by method: the script, the companion it writes,
#: the header that companion must carry, a record that derives, a record
#: whose every group misses the grid, and the keys the refusal must name.
TC_COMMANDS = {
    "endpoint": {
        "script": "tc_companion.py",
        "companion": "record-tc.csv",
        "header": tcc.HEADER,
        "deriving": endpoint_rows(ENDPOINT_POINTS),
        "key_miss": endpoint_rows([(float(t), v) for t, v in ENDPOINT_POINTS]),
        "missed_keys": ("typ/3.30/-40.0", "typ/3.30/27.0", "typ/3.30/125.0"),
    },
    "box": {
        "script": "boxtc_companion.py",
        "companion": "record-boxtc.csv",
        "header": bxc.HEADER,
        "deriving": boxtc_rows(INTERIOR_EXTREMA),
        "key_miss": boxtc_rows(INTERIOR_EXTREMA, vdd="3.31"),
        "missed_keys": ("typ/3.31",),
    },
}


def run_cli(script: str, argv: list[str]) -> subprocess.CompletedProcess:
    """Run a companion script the way the shell hooks do; the result carries the exit status."""
    return subprocess.run(
        [sys.executable, str(HARNESS / script), *argv],
        capture_output=True, text=True)


class TcCompanionCliTests(TempDirCase):
    """Both companion commands refuse an empty derivation (#510)."""

    def record_and_companion(self, method: str) -> tuple[Path, Path]:
        """A `record.csv` and companion path that only this method's runs touch."""
        work = self.tmp / method
        work.mkdir()
        return work / "record.csv", work / TC_COMMANDS[method]["companion"]

    def test_key_miss_exits_nonzero_naming_the_record_keys(self) -> None:
        # The issue's own example: `temperature_c` arrives as a string, so
        # temp_c renders "-40.0" and matches none of TEMPS. The box module
        # keys groups by (corner, vdd) and matches temperature numerically,
        # so there a drifted vdd is what empties every group. Either way the
        # refusal must say what the record carried.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["key_miss"])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "key-miss record still exited 0")
                self.assertIn("header-only", r.stderr)
                for key in spec["missed_keys"]:
                    self.assertIn(key, r.stderr)
                # And the refusal leaves no header-only artifact on disk
                # (#536): records/ is append-only evidence, and a companion
                # whose body is empty is one `git add -A` away from being
                # committed as derived.
                self.assertFalse(dst.exists(), "refused run left the companion on disk")

    def test_empty_record_is_a_distinct_refusal(self) -> None:
        # A record with a header and no rows read: also no evidence, but a
        # different defect than a key miss, and the message says which.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, [])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "empty record still exited 0")
                self.assertIn("no rows", r.stderr)
                self.assertNotIn("keys the record carried", r.stderr)
                self.assertFalse(dst.exists(), "refused run left the companion on disk")

    def test_a_refusal_preserves_a_preexisting_companion_intact(self) -> None:
        # Edge #536 leaves to the Builder: the companion path already holds
        # an earlier good derivation when a rerun refuses. main() refuses
        # before the destination is ever opened, so the prior companion is
        # never touched: a refused run leaves the path exactly as it found
        # it -- no header-only shell, no destroyed prior evidence.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["deriving"])
                first = run_cli(spec["script"], [str(src), str(dst)])
                self.assertEqual(first.returncode, 0, first.stderr)
                prior = dst.read_bytes()
                write_record(src, RECORD_FIELDS, [])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertNotEqual(r.returncode, 0, "empty record still exited 0")
                self.assertEqual(dst.read_bytes(), prior)

    def test_a_deriving_record_still_exits_zero(self) -> None:
        # The check must not turn a healthy derivation into a failure.
        for method, spec in TC_COMMANDS.items():
            with self.subTest(method=method):
                src, dst = self.record_and_companion(method)
                write_record(src, RECORD_FIELDS, spec["deriving"])
                r = run_cli(spec["script"], [str(src), str(dst)])
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(
                    dst.read_text().splitlines()[0], ",".join(spec["header"]))


if __name__ == "__main__":
    unittest.main()
