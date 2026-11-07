"""Single-device runset-LVS fixture: one npn13G2 (Nx=1) (issue #380).

Draws one device with the shared helper in ``layout/common.py`` -- exactly the
call the cell generators make -- so the PDK LVS runset (``klt lvs`` engine
``klayout-runset``) is graded on the helper's footprint alone. See
``layout/README.md`` "LVS -- PDK runset on single-device fixtures".
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from common import L_METAL1, Builder, draw_npn13g2, route_v  # noqa: E402

TOP_CELL = "npn13g2"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "npn13g2.gds")


def build() -> Builder:
    b = Builder(TOP_CELL)
    q1 = draw_npn13g2(b, "Q1", 1, 0.0, 0.0, collector_net="sns1", base_net="sns1", emitter_net="vss", substrate_net="sub")
    # Q1 is diode-connected (collector == base == sns1): tie the two rails.
    route_v(b, L_METAL1, q1["tie_x"], q1["base_pad"][1], q1["collector_pad"][3], width=0.3)
    return b


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
