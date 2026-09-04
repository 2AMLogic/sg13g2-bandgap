#!/usr/bin/env python3
"""Measure the committed layouts' area from the committed GDS files.

The ``Area`` row of ``spec/porting-plan.md`` Sec 6 (``< 0.05 mm2``, drafted,
unratified) is the one row of that seven-row table with **no** evidence
artifact of any kind in this repo -- ``sim/closed-loop-iq/README.md`` says so
explicitly ("area is the only remaining gap, and is a layout-geometry metric,
out of ``sim/``-testbench scope").  It is out of ``sim/`` scope because it is
not a PVT-cornered simulation: it is a geometry measurement of committed GDS,
which is what this script performs.

It measures, per committed cell, exactly two numbers plus their ratio:

``footprint_um2``
    The top cell's bounding-box area (``width x height`` from ``klt stats``).
    This is the number the drafted spec row is about -- the silicon a block
    occupies is its footprint, not the sum of its drawn shapes.

``drawn_area_um2``
    The total area of drawn polygons (``klt stats`` ``total.area_um2``).  A
    strict lower bound on any re-floorplanned version of the same devices,
    and therefore the part of the footprint that a placement change cannot
    remove.

``density``
    ``drawn_area_um2 / footprint_um2`` -- how much of the footprint is real
    geometry rather than the whitespace an unfolded aspect ratio drags in.
    Reported by ``klt stats`` directly; recomputed here and cross-checked.

No verdict is emitted.  ``spec/porting-plan.md`` Sec 6 is a draft table (#125,
PR #128), so this script records measurements as evidence, exactly as the
``sim/`` testbenches do, and leaves the comparison to a ratified row to
whatever ratification eventually lands.  See ``README.md`` next to this file.

Usage
-----

    python3 measurements/2026-09-layout-area/measure_area.py            # print
    python3 measurements/2026-09-layout-area/measure_area.py --write    # commit
    python3 measurements/2026-09-layout-area/measure_area.py --check    # verify

``--check`` re-derives every geometry number from the committed GDS files and
diffs it against the committed ``area_record.json``, failing (exit 1) on any
drift.  It deliberately ignores the provenance block (``klt`` version,
timestamp), which is not a property of the geometry: the reproducibility claim
here is "the same GDS yields the same areas", not "the same machine".

Requires ``klt`` on ``PATH`` (klayout-tools).  Nothing else -- no PDK, no
ngspice, no ``klayout`` python module -- so it is cheap to re-run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RECORD = HERE / "area_record.json"

SCHEMA_VERSION = 1

#: The drafted, *unratified* target this measurement is evidence for. Recorded
#: in the JSON so a reader never has to guess which row a number relates to --
#: never used to emit a pass/fail verdict (see module docstring).
DRAFT_AREA_ROW = {
    "source": "spec/porting-plan.md",
    "section": "6",
    "row": "Area",
    "target_mm2": 0.05,
    "ratified": False,
    "ratification_tracking": ["#125", "PR #128"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def klt_version() -> str:
    out = subprocess.run(
        ["klt", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return out


def klt_stats(gds: Path) -> dict:
    out = subprocess.run(
        ["klt", "stats", str(gds), "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def discover_cells(root: Path) -> list[Path]:
    """Every ``layout/<cell>/<cell>.gds`` committed in the repo, sorted.

    Matches the same ``<dir>/<dir>.gds`` convention
    ``.github/scripts/check_evidence_formats.py`` ``check_layout()`` enforces,
    so a cell that gains a layout is picked up here with no edit to this file.
    """
    layout = root / "layout"
    cells = []
    for cell_dir in sorted(p for p in layout.iterdir() if p.is_dir()):
        gds = cell_dir / f"{cell_dir.name}.gds"
        if gds.is_file():
            cells.append(gds)
    return cells


def measure(gds: Path, root: Path) -> dict:
    stats = klt_stats(gds)
    bbox = stats["bbox_um"]
    width = float(bbox["width"])
    height = float(bbox["height"])
    footprint_um2 = width * height
    drawn_um2 = float(stats["total"]["area_um2"])

    # klt reports density against its own notion of the bbox; recompute it from
    # the two numbers recorded here so the record is internally checkable, and
    # assert the two agree rather than silently preferring one.
    density = drawn_um2 / footprint_um2 if footprint_um2 else 0.0
    reported = float(stats["total"]["density"])
    if abs(density - reported) > 1e-9:
        raise SystemExit(
            f"{gds}: recomputed density {density!r} disagrees with "
            f"klt stats total.density {reported!r} -- the bbox klt measured "
            "area against is not the bbox it reported"
        )

    return {
        "cell_dir": str(gds.parent.relative_to(root)),
        "top_cell": stats["top_cell"],
        "gds": str(gds.relative_to(root)),
        "gds_sha256": sha256_file(gds),
        "bbox_um": {
            "left": bbox["left"],
            "bottom": bbox["bottom"],
            "right": bbox["right"],
            "top": bbox["top"],
            "width": width,
            "height": height,
        },
        "footprint_um2": round(footprint_um2, 6),
        "footprint_mm2": round(footprint_um2 / 1e6, 9),
        "drawn_area_um2": round(drawn_um2, 6),
        "density": round(density, 9),
        "aspect_ratio": round(max(width, height) / min(width, height), 6),
        "polygon_count": stats["total"]["polygon_count"],
    }


def build_record(root: Path) -> dict:
    cells = discover_cells(root)
    if not cells:
        raise SystemExit("no layout/<cell>/<cell>.gds found -- nothing to measure")
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": "layout-area",
        "generated_by": "measurements/2026-09-layout-area/measure_area.py",
        "draft_spec_row": DRAFT_AREA_ROW,
        "verdict": None,
        "verdict_note": (
            "No pass/fail is recorded: spec/porting-plan.md Sec 6 is a draft, "
            "unratified table (#125, PR #128). These are measurements, not a "
            "conformance claim -- see README.md next to this record."
        ),
        "provenance": {
            "klt_version": klt_version(),
            "measured_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        },
        "cells": [measure(gds, root) for gds in cells],
    }


def geometry_only(record: dict) -> list[dict]:
    """The part of a record that is a property of the GDS, not of the machine."""
    return record.get("cells", [])


def format_table(record: dict) -> str:
    rows = [
        "| cell | bbox (um) | footprint (um^2) | footprint (mm^2) | drawn (um^2) | density | aspect |",
        "|---|---|---|---|---|---|---|",
    ]
    for cell in record["cells"]:
        bbox = cell["bbox_um"]
        rows.append(
            "| `{top}` | {w:.2f} x {h:.2f} | {fu:,.1f} | {fm:.4f} | {du:,.1f} | "
            "{d:.3f} | {a:.1f}:1 |".format(
                top=cell["top_cell"],
                w=bbox["width"],
                h=bbox["height"],
                fu=cell["footprint_um2"],
                fm=cell["footprint_mm2"],
                du=cell["drawn_area_um2"],
                d=cell["density"],
                a=cell["aspect_ratio"],
            )
        )
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write", action="store_true", help="write area_record.json next to this script"
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="re-derive geometry and diff against the committed area_record.json",
    )
    args = parser.parse_args(argv)

    if shutil.which("klt") is None:
        print(
            "klt not found on PATH -- install klayout-tools to run this "
            "measurement (the committed area_record.json is the evidence; this "
            "script is how to reproduce it)",
            file=sys.stderr,
        )
        return 2

    record = build_record(ROOT)

    if args.check:
        if not RECORD.is_file():
            print(f"{RECORD} does not exist -- nothing to check against", file=sys.stderr)
            return 1
        committed = json.loads(RECORD.read_text(encoding="utf-8"))
        if geometry_only(committed) == geometry_only(record):
            print(f"OK: {len(record['cells'])} cells re-measure identically to {RECORD.name}")
            return 0
        print("DRIFT: re-measured geometry differs from the committed record", file=sys.stderr)
        print("--- committed ---", file=sys.stderr)
        print(json.dumps(geometry_only(committed), indent=2), file=sys.stderr)
        print("--- re-measured ---", file=sys.stderr)
        print(json.dumps(geometry_only(record), indent=2), file=sys.stderr)
        return 1

    if args.write:
        RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")

    print(format_table(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
