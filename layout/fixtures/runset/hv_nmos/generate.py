"""Single-device runset-LVS fixture: one sg13_hv_nmos (w=10u l=0.5u) (issue #380).

Draws one device with the shared helper in ``layout/common.py`` -- exactly the
call the cell generators make -- so the PDK LVS runset (``klt lvs`` engine
``klayout-runset``) is graded on the helper's footprint alone. See
``layout/README.md`` "LVS -- PDK runset on single-device fixtures".
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from common import Builder, draw_gate_tab, draw_hv_mos  # noqa: E402

TOP_CELL = "hv_nmos"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hv_nmos.gds")


def build() -> Builder:
    b = Builder(TOP_CELL)
    mos = draw_hv_mos(
        b, "MSENSE", "nmos", 10.0, 0.5, 0.0, 0.0,
        gate_net="sns1", source_net="det", drain_net="vss",
    )
    # The helper leaves the gate unnamed (GatPoly carries no net-name text the
    # runset reads); a Metal1 tab gives the gate net its name and a pin.
    draw_gate_tab(b, mos["gate_box"][2], 0.0, "sns1", "right")
    return b


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
