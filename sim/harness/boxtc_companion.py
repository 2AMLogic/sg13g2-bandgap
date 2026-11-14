#!/usr/bin/env python3
"""Box-method TC companion CSV: the one home for the box-TC derivation.

Issue #465. Two benches measure the same quantity the same way -- the
schematic `sim/closed-loop-vref-pvt-boxtc` and its extracted twin
`sim/closed-loop-vref-pvt-pex-boxtc` -- and until this module existed each
carried its own byte-identical copy of the formula inside
`run_klt_sim.sh`'s `pex_record_companion` hook. The two are compared against
each other (`*-vs-schematic-boxtc.csv`), and
`spec/decision-records/0010-box-method-tc-evidence.md` ratifies their output
as the block's temperature-coefficient evidence -- with the design sitting
*on* the 20 ppm/degC stretch line, decided at the third decimal place. A
correction applied to one copy and not the other would silently leave the
other bench reporting the old derivation, so the derivation gets a single
home and a self-test.

The box method, as the committed records disclose it:

    box_tc = 1e6 * (vmax - vmin) / (SPAN_C * vref_27c)

over the PASS points of each (corner, vdd) group, where `vmin`/`vmax` are
the extrema of `vref_3ms_v` across the temperature grid and `SPAN_C` is the
165 degC of the -40..125 degC grid. It is a *box* (worst-case spread), not a
two-endpoint slope: the endpoint figure is carried alongside, in
`endpoint_tc_ppm_per_c`, from the -40 and 125 degC points when both passed.
A group with no PASS point, or whose PASS points miss 27 degC, is omitted --
the derivation has no denominator there.

This is the box-method companion only. `sim/closed-loop-vref-pvt-pex`
supplies a genuinely different endpoint-method body to the same hook
(6 columns, `-tc.csv`, rows keyed by exact `(corner, vdd, temp)`); it is not
this derivation and does not belong here.

Usage (the shell side is `pex_boxtc_companion` in
sim/harness/pex_vref_runner.sh, which picks the newest minted record):

    python3 sim/harness/boxtc_companion.py <record.csv> <record-boxtc.csv>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

#: The -40..125 degC grid both box-TC benches sweep, in degC. The committed
#: records' disclosure names it; it is the formula's denominator span.
SPAN_C = 165

#: Grid axes, in the committed records' row order.
CORNERS = ("typ", "bcs", "wcs", "sf", "fs")
VDDS = ("2.97", "3.30", "3.63")

HEADER = [
    "corner_label", "vdd_v", "n_pass", "n_grid", "vmin_v", "vmin_temp_c",
    "vmax_v", "vmax_temp_c", "vref_27c_v", "box_tc_ppm_per_c",
    "endpoint_tc_ppm_per_c",
]


def group_by_corner_vdd(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Bucket record rows by their `(corner_label, vdd_v)` strings.

    Every row is bucketed, PASS or not: `n_grid` reports the points the grid
    attempted, against which `n_pass` discloses how many informed the number.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["corner_label"], r["vdd_v"]), []).append(r)
    return groups


def companion_rows(rows: list[dict]) -> list[list]:
    """The box-method companion rows for one record's rows, in grid order."""
    groups = group_by_corner_vdd(rows)
    out: list[list] = []
    for corner in CORNERS:
        for vdd in VDDS:
            grp = [r for r in groups.get((corner, vdd), [])
                   if r["status"] == "PASS"]
            n_grid = len(groups.get((corner, vdd), []))
            if not grp:
                continue
            pts = [(float(r["temp_c"]), float(r["vref_3ms_v"])) for r in grp]
            v27 = next((v for t, v in pts if t == 27), None)
            if v27 is None:
                continue
            (tmin, vmin), (tmax, vmax) = (min(pts, key=lambda p: p[1]),
                                          max(pts, key=lambda p: p[1]))
            box = 1e6 * (vmax - vmin) / (SPAN_C * v27)
            row = [corner, vdd, len(grp), n_grid, f"{vmin:.5g}", int(tmin),
                   f"{vmax:.5g}", int(tmax), f"{v27:.5g}", f"{box:.3f}"]
            vn40 = next((v for t, v in pts if t == -40), None)
            v125 = next((v for t, v in pts if t == 125), None)
            row.append(f"{1e6 * (v125 - vn40) / (SPAN_C * v27):.3f}"
                       if vn40 is not None and v125 is not None else "")
            out.append(row)
    return out


def write_companion(src: Path, dst: Path) -> list[list]:
    """Derive `dst` from the minted record `src`; returns the rows written."""
    with src.open() as fh:
        rows = list(csv.DictReader(fh))
    body = companion_rows(rows)
    with dst.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        for row in body:
            w.writerow(row)
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("record", type=Path, help="the minted record CSV")
    ap.add_argument("companion", type=Path, help="the -boxtc.csv to write")
    args = ap.parse_args(argv)
    write_companion(args.record, args.companion)
    print(f"boxtc companion: {args.companion}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
