#!/usr/bin/env python3
"""Generate ``bandgap_core.gds`` -- physical layout of ``design/bandgap_core.sch``.

Drawn directly with the ``klayout.db`` (``pya``-compatible) Python API via
``layout/common.py``'s shared primitives -- see that module's docstring for
why this issue used a manual construction script rather than a PDK-native
PCell run, matching the construction pattern
``gf180-bandgap/layout/bandgap_top/generate.py`` already established for the
fleet's most mature block.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_core/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against ``design/netlist/bandgap_core.spice``
(``XM1``/``XQ1``/``XM2``/``XR2``/``XQ2``/``XM3``/``XR1``/``XQ3``):

    M1 sg13_hv_pmos w=10u l=1u   -- branch 1 mirror leg (vdd/fb -> sns1)
    Q1 npn13G2 Nx=1              -- branch 1, diode-connected (sns1 -> vss)
    M2 sg13_hv_pmos w=10u l=1u   -- branch 2 mirror leg (vdd/fb -> sns2)
    R2 rppd w=2u l=82.7u         -- PTAT resistor (sns2 -> cb2)
    Q2 npn13G2 Nx=8              -- branch 2, diode-connected (cb2 -> vss)
    M3 sg13_hv_pmos w=10u l=1u   -- output branch mirror leg (vdd/fb -> vref)
    R1 rppd w=2u l=694.5u        -- summing resistor (vref -> cb3)
    Q3 npn13G2 Nx=1              -- output branch, diode-connected (cb3 -> vss)

This is a **floorplan-level, simplified representative layout, not a
DRC-clean or LVS-verified one** -- see ``layout/README.md`` "What this
layout is / is not". DRC/LVS verification against this geometry is tracked
separately in issue #12, per this issue's own acceptance criteria (layout
capture is explicitly not gated on a clean DRC run).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import Builder, draw_hv_mos, draw_npn13g2, draw_poly_res  # noqa: E402

TOP_CELL = "bandgap_core"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_core.gds")


def build() -> Builder:
    b = Builder(TOP_CELL)

    mos_y = 22.0
    hbt_y = 0.0
    res_y = 40.0

    # Branch 1: M1 -> Q1, no series resistor (Q1 sensed directly at sns1).
    x1 = 0.0
    draw_hv_mos(b, "M1", "pmos", 10.0, 1.0, x1, mos_y, gate_net="fb", source_net="vdd", drain_net="sns1")
    draw_npn13g2(b, "Q1", 1, x1, hbt_y, collector_net="sns1", base_net="sns1", emitter_net="vss")

    # Branch 2: M2 -> R2 -> Q2 (Nx=8, sets the PTAT delta-VBE leg).
    x2 = 45.0
    draw_hv_mos(b, "M2", "pmos", 10.0, 1.0, x2, mos_y, gate_net="fb", source_net="vdd", drain_net="sns2")
    draw_npn13g2(b, "Q2", 8, x2, hbt_y, collector_net="cb2", base_net="cb2", emitter_net="vss")
    draw_poly_res(b, "R2", "rppd", 2.0, 82.7, 0.0, res_y, end_a_net="sns2", end_b_net="cb2")

    # Output branch: M3 -> R1 -> Q3, vref is the mirror node directly.
    x3 = 110.0
    draw_hv_mos(b, "M3", "pmos", 10.0, 1.0, x3, mos_y, gate_net="fb", source_net="vdd", drain_net="vref")
    draw_npn13g2(b, "Q3", 1, x3, hbt_y, collector_net="cb3", base_net="cb3", emitter_net="vss")
    # R1 is drawn as a long straight bar (l=694.5u, see draw_poly_res's own
    # docstring) on its own row so it does not overlap the compact devices
    # above -- runs from x=0 out past x3's column.
    draw_poly_res(b, "R1", "rppd", 2.0, 694.5, 0.0, res_y + 20.0, end_a_net="vref", end_b_net="cb3")

    return b


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
