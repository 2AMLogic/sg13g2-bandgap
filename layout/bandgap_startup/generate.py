#!/usr/bin/env python3
"""Generate ``bandgap_startup.gds`` -- layout of ``design/bandgap_startup.sch``.

Same construction pattern as ``layout/bandgap_core/generate.py`` -- see that
file and ``layout/common.py``'s module docstring for the full provenance
note (manual ``klayout.db`` construction; why a PDK-native PCell run was not
used for this issue).

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_startup/generate.py

Devices instantiated, one-to-one against
``design/netlist/bandgap_startup.spice``:

    RPU    rhigh w=1u l=1411.3u    -- always-on weak pull-up (vdd -> det)
    MSENSE sg13_hv_nmos w=2u l=0.5u -- current-sense switch (gate=sns1, det->vss)
    MKFB   sg13_hv_nmos w=2u l=0.5u -- mirror-kick switch (gate=det, fb->vss)

No bipolar device is instantiated here (DR-0001's BVCEO/BVEBO constraint
does not bind on this circuit by construction -- see the schematic's own
header comment). Floorplan-level, simplified representative layout, not
DRC-clean/LVS-verified -- see ``layout/README.md``.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import Builder, draw_hv_mos, draw_poly_res  # noqa: E402

TOP_CELL = "bandgap_startup"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_startup.gds")


def build() -> Builder:
    b = Builder(TOP_CELL)

    mos_y = 0.0
    res_y = 20.0

    draw_hv_mos(
        b, "MSENSE", "nmos", 2.0, 0.5, 0.0, mos_y,
        gate_net="sns1", source_net="det", drain_net="vss",
    )
    draw_hv_mos(
        b, "MKFB", "nmos", 2.0, 0.5, 20.0, mos_y,
        gate_net="det", source_net="fb", drain_net="vss",
    )
    # RPU (l=1411.3u) is a very long straight bar (see draw_poly_res's own
    # docstring) -- on its own row so it does not overlap the compact
    # MSENSE/MKFB devices above.
    draw_poly_res(b, "RPU", "rhigh", 1.0, 1411.3, 0.0, res_y, end_a_net="vdd", end_b_net="det")

    return b


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
