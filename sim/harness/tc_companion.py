#!/usr/bin/env python3
"""Endpoint-method TC companion CSV: the one home for the endpoint derivation.

Issue #496. Two benches measure the same quantity the same way -- the
schematic `sim/closed-loop-vref-pvt` and its extracted twin
`sim/closed-loop-vref-pvt-pex` -- and until this module existed each carried
its own copy of the formula inside `run_klt_sim.sh`'s `pex_record_companion`
hook (the second pasted in *after* the shared driver existed, by PR #491).
The two are compared against each other, and a correction applied to one
copy and not the other would silently leave the other bench reporting the
old derivation, so the derivation gets a single home and a self-test -- the
same argument that moved the box method into `boxtc_companion.py` (issue
#465).

The endpoint method, as the committed `-tc.csv` companions disclose it:

    tc_ppm_per_c = 1e6 * (vref_3ms(125 C) - vref_3ms(-40 C)) / (SPAN_C * vref_3ms(27 C))

over each `(corner, vdd)` group, where `SPAN_C` is the 165 degC of the
-40..125 degC grid. It is a *two-endpoint slope*, not the box method's
worst-case spread: the box figure lives in `boxtc_companion.py` and the two
must not collapse (different column sets, different companions, a ratified
decision record behind one of them).

The committed convention is pass-through of the record's own strings, not
any particular `%.*e` width -- the legacy `run_pvt_sweep.sh` minter echoed
the record's fields verbatim and formatted only `tc`. So every value but
`tc` is carried through as the record writes it (`vdd_v` as `3.30`,
voltages as the record's own `1.04695e+00`), and rows are keyed by the
record's `(corner_label, vdd_v, temp_c)` strings. A group missing any of
the three temperature points, or carrying an unparseable value, is omitted
-- the derivation has no number there. When *every* group is omitted --
the record carried rows but none matched the grid -- `main()` exits
non-zero and names the keys the record carried: empty evidence must be
loud, not a header-only companion reporting success (issue #510). The
refused run leaves no header-only file on disk either (issue #536): the
derivation is checked before the companion path is opened, so a refusal
never creates the file and leaves an earlier run's derivation untouched.

Usage (the shell side is `pex_endpoint_tc_companion` in
sim/harness/pex_vref_runner.sh, which picks the newest minted record):

    python3 sim/harness/tc_companion.py <record.csv> <record-tc.csv>
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from boxtc_companion import key_summary

#: The -40..125 degC grid both endpoint benches sweep, in degC. The committed
#: companions' disclosure names it; it is the formula's denominator span.
SPAN_C = 165

#: Grid axes, in the committed companions' row order.
CORNERS = ("typ", "bcs", "wcs", "sf", "fs")
VDDS = ("2.97", "3.30", "3.63")

#: The three endpoint temperatures, as the committed records write them.
TEMPS = ("-40", "27", "125")

HEADER = [
    "corner_label", "vdd_v", "vref_neg40_v", "vref_27_v", "vref_125_v",
    "tc_ppm_per_c",
]


def companion_rows(rows: list[dict]) -> list[list]:
    """The endpoint-method companion rows for one record's rows, in grid order.

    Every value but `tc` passes through as the record's own string; `float()`
    is used only to compute `tc`, and only `tc` gets a format.
    """
    by = {(r["corner_label"], r["vdd_v"], r["temp_c"]): r for r in rows}
    out: list[list] = []
    for corner in CORNERS:
        for vdd in VDDS:
            try:
                n40 = float(by[(corner, vdd, TEMPS[0])]["vref_3ms_v"])
                v27 = float(by[(corner, vdd, TEMPS[1])]["vref_3ms_v"])
                p125 = float(by[(corner, vdd, TEMPS[2])]["vref_3ms_v"])
            except (KeyError, ValueError):
                continue
            tc = 1e6 * (p125 - n40) / (SPAN_C * v27)
            out.append([
                corner, vdd,
                by[(corner, vdd, TEMPS[0])]["vref_3ms_v"],
                by[(corner, vdd, TEMPS[1])]["vref_3ms_v"],
                by[(corner, vdd, TEMPS[2])]["vref_3ms_v"],
                f"{tc:.3f}",
            ])
    return out


def _write_rows(dst: Path, body: list[list]) -> None:
    """Write the header and `body` rows to `dst`."""
    with dst.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(HEADER)
        for row in body:
            w.writerow(row)


def write_companion(src: Path, dst: Path) -> list[list]:
    """Derive `dst` from the minted record `src`; returns the rows written."""
    with src.open() as fh:
        rows = list(csv.DictReader(fh))
    body = companion_rows(rows)
    _write_rows(dst, body)
    return body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("record", type=Path, help="the minted record CSV")
    ap.add_argument("companion", type=Path, help="the -tc.csv to write")
    args = ap.parse_args(argv)
    with args.record.open() as fh:
        rows = list(csv.DictReader(fh))
    body = companion_rows(rows)
    if not body:
        # A header-only CSV must not be blessed with exit 0 (#510) nor
        # land on disk (#536): refuse before the destination is opened,
        # so a prior companion is never touched.
        if not rows:
            raise SystemExit(
                f"tc companion: {args.record} carries no rows; "
                f"{args.companion} is header-only")
        raise SystemExit(
            f"tc companion: {args.companion} is header-only: every "
            f"(corner, vdd, temp) group missed the grid; keys the record "
            f"carried: {key_summary(rows, ('corner_label', 'vdd_v', 'temp_c'))}")
    _write_rows(args.companion, body)
    print(f"tc companion: {args.companion}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
