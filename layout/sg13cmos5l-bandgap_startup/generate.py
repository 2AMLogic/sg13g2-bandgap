#!/usr/bin/env python3
"""Generate ``sg13cmos5l-bandgap_startup.gds`` -- physical layout of
``design/sg13cmos5l/bandgap_startup.sch`` (the SG13CMOS5L port, issue #74).

Drawn with ``layout/common_sg13cmos5l.py``'s primitives, the same deliberate
fork of ``layout/common.py`` ``sg13cmos5l-bandgap_core`` uses (see that
module's docstring for the three reasons this port does not share the SG13G2
primitives). Two of them landed for this cell: ``draw_hv_nmos`` (the core is
all-PMOS, so CMOS5L had no NMOS footprint before #74) and ``draw_rhigh``
(the core's only resistor flavour is ``rppd``).

Run from the repo root::

    uv run --with klayout python3 layout/sg13cmos5l-bandgap_startup/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against
``design/sg13cmos5l/netlist/bandgap_startup.spice``:

    RPU    rhigh w=1u l=1411.3u          -- pull-up (vdd -> det)
    MSENSE sg13_hv_nmos w=10u l=0.5u     -- det pulled down once sns1 rises
    MKFB   sg13_hv_nmos w=2u l=0.5u      -- kicks fb down while det is high

Floorplan
---------

Two rows, because ``RPU`` drawn straight at its own ``l=1411.3u`` is a
~1.4 mm bar that sets the whole cell's bounding box (identical choice, and
identical device, to ``layout/bandgap_startup`` on the SG13G2 side -- see
``draw_rhigh``'s docstring)::

    y=8    RPU  [0 .. 1411.3]                       (vdd at the left head,
                                                     det at the right head)
    y=3    ---- det lane ----------------------------
    y=0    sns1 tab | MSENSE (x=1395) | MKFB (x=1420) | det tab

Both transistors sit at the *far right* end, directly under ``RPU``'s
``det`` head, so ``det`` -- the only net in this cell with more than two
members -- never travels the bar's length. ``vdd`` (``RPU``'s left head),
``sns1`` (``MSENSE``'s gate) and ``fb`` (``MKFB``'s drain) are all cell
ports whose only in-cell member is the terminal they name, so each is a
labelled pad with nothing to route.

Single-metal and planar, with no poly underpass needed: this cell's net
graph is a path, so unlike ``bandgap_amp`` it fits the curated deck's
one-metal/no-via stack (klayout-tools#1417) directly. ``MSENSE``'s gate bar
escapes left and ``MKFB``'s escapes right, so the two gate nets -- ``sns1``
and ``det`` -- never share a poly corridor.

What this layout does **not** try to do is force an LVS ``match``: the same
four deck-coverage causes ``layout/README.md`` enumerates for
``bandgap_core`` apply here (no resistor recognition -- which additionally
*shorts* ``RPU``'s own two terminals, merging ``vdd`` into ``det`` -- no HV
MOS flavour, no well/substrate tap; only "no bipolar device class" is moot,
this cell having no bipolar). Each is re-verified against this cell's own
reports rather than restated -- see ``layout/README.md`` "Cell:
``sg13cmos5l-bandgap_startup``".
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common_sg13cmos5l import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    Builder,
    draw_hv_nmos,
    draw_rhigh,
    poly_tab,
    route_h,
    route_v,
)

TOP_CELL = "sg13cmos5l_bandgap_startup"
OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sg13cmos5l-bandgap_startup.gds"
)

#: Routing width for every Metal1 trunk -- same value, and same rationale, as
#: ``sg13cmos5l-bandgap_core``'s: the curated deck's ``metal1.width.1`` floor
#: is 0.16 um and ``metal1.space.1`` is 0.18 um, and 0.30 um clears the width
#: floor with ~2x margin.
TRUNK_W = 0.30

# Row centres (see the floorplan sketch in this module's docstring).
Y_RPU = 8.0
Y_DET_LANE = 3.0
Y_MOS = 0.0

# Device sizes, read from design/sg13cmos5l/netlist/bandgap_startup.spice.
RPU_W, RPU_L = 1.0, 1411.3
MSENSE_W, MSENSE_L = 10.0, 0.5
MKFB_W, MKFB_L = 2.0, 0.5

# Column origins. RPU starts at x=0; the two NMOS sit under its far end.
X_RPU = 0.0
X_MSENSE = 1395.0
X_MKFB = 1420.0
#: ``sns1`` gate tab, ~1.8 um left of ``MSENSE``'s own gate endcap.
X_SNS1_TAB = 1388.0
#: ``det`` gate tab, ~2.3 um right of ``MKFB``'s own gate endcap -- clear of
#: ``MKFB``'s ``fb`` drain pad (which ends at x=1421) by >2 um.
X_DET_TAB = 1423.5


def build() -> Builder:
    b = Builder(TOP_CELL)

    rpu = draw_rhigh(b, "RPU", RPU_W, RPU_L, X_RPU, Y_RPU, end_a_net="vdd", end_b_net="det")
    msense = draw_hv_nmos(
        b, "MSENSE", MSENSE_W, MSENSE_L, X_MSENSE, Y_MOS, "sns1", "vss", "det"
    )
    mkfb = draw_hv_nmos(b, "MKFB", MKFB_W, MKFB_L, X_MKFB, Y_MOS, "det", "vss", "fb")

    _route(b, rpu, msense, mkfb)
    return b


def _route(b: Builder, rpu: dict, msense: dict, mkfb: dict) -> None:
    """Wire every schematic net. Only ``det`` and ``vss`` need routing at
    all; ``vdd``/``sns1``/``fb`` are ports whose single in-cell member the
    device primitives have already labelled."""

    # -- vss: MSENSE and MKFB source pads (both at the bottom of their own
    # footprint, draw_hv_nmos's mirrored orientation), merged by one Metal1
    # bar spanning the row. The pads carry their own "vss" Metal1.pin labels
    # already; this bar only makes the two one physically-connected shape.
    src = msense["source_pad"]
    b.box(L_METAL1, src[0], src[1], mkfb["source_pad"][2], src[3])

    # -- det: RPU's right head -> MSENSE.drain -> MKFB.gate, via one
    # horizontal lane at Y_DET_LANE. The drop off RPU's head is centred on
    # that pad rather than on the bar's own axis, and the drop into
    # MSENSE's drain lands wholly inside that pad -- both for the reason
    # bandgap_core's first DRC run established (a stem that overhangs its
    # landing pad's edge makes the join a step, and `metal1.width.1` flags
    # the notch).
    x_rpu_det = _pad_center_x(rpu["end_b_pad"])
    route_v(b, L_METAL1, x_rpu_det, Y_DET_LANE, rpu["end_b_pad"][1], width=TRUNK_W)
    route_h(b, L_METAL1, Y_DET_LANE, X_MSENSE, X_DET_TAB, width=TRUNK_W)
    route_v(b, L_METAL1, X_MSENSE, msense["drain_pad"][3], Y_DET_LANE, width=TRUNK_W)

    # MKFB's gate escapes right, out from under its own drain pad, to a tab
    # the det lane drops onto. poly_tab must land on field, never over
    # Activ: X_DET_TAB is 2.5 um right of MKFB's diffusion edge.
    route_h(b, L_GATPOLY, Y_MOS, mkfb["gate_box"][2], X_DET_TAB, width=TRUNK_W)
    poly_tab(b, X_DET_TAB, Y_MOS)
    route_v(b, L_METAL1, X_DET_TAB, Y_MOS, Y_DET_LANE, width=TRUNK_W)

    # -- sns1: MSENSE's gate, escaping left to a labelled tab. Without it the
    # net would extract as an anonymous `$N` -- the curated deck declares
    # `poly_label=None`, so a gate net can only be named through a Metal1
    # pad contacted to its poly (same gap bandgap_core's `fb` tap works
    # around, and the same one layout/README.md records for SG13G2's `det`).
    route_h(b, L_GATPOLY, Y_MOS, X_SNS1_TAB, msense["gate_box"][0], width=TRUNK_W)
    poly_tab(b, X_SNS1_TAB, Y_MOS, net="sns1")


def _pad_center_x(pad: tuple[float, float, float, float]) -> float:
    """X centre of a returned terminal pad box."""
    return (pad[0] + pad[2]) / 2


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
