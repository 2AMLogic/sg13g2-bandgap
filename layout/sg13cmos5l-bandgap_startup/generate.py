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

Boundary ports for ``bandgap_top`` assembly (issue #76)
---------------------------------------------------------

``vdd`` (``RPU``'s own left head) already sits flush against the cell's own
left+top edges; ``vss`` (the merged NMOS source rail) already sits flush
against the bottom edge. ``sns1``/``fb`` did not -- each is an interior gate
tab (``X_SNS1_TAB=1388``, ``MKFB``'s own drain pad at ``x=1419..1421``).
Both now get a dedicated :func:`boundary_port`:

* ``sns1`` -- straight down from its own tap to the bottom edge. The tap
  sits at ``x=1388``, 2 um clear of the ``vss`` rail's own left edge
  (``x=1390``), so the drop needs no crossing at all.
* ``fb`` -- ``MKFB``'s own drain pad sits directly above the ``vss`` rail
  (whose x-span, ``1390..1421``, includes the pad's own x-position), so a
  straight drop down would short ``fb`` to ``vss``. Instead it jogs *up*
  first, clear of ``det``'s own tap column (which only reaches
  ``y=Y_DET_LANE=3``), then right to the cell's right edge.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common_sg13cmos5l import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    Builder,
    boundary_port,
    draw_hv_nmos,
    draw_rhigh,
    pad_center_x,
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
# Issue #173: Y_RPU is now the *bottom edge* of RPU's folded core
# (draw_rhigh's (x0, y0) is its lower-left corner post-fold), not a straight
# bar's centreline. Its two Metal1 terminal pads hang 0.5 um below it, down
# to y=7.5 -- still well clear of the det lane at y=3.
Y_RPU = 8.0
Y_DET_LANE = 3.0
Y_MOS = 0.0

#: How many serpentine legs ``RPU``'s 1411.3 um of ``rhigh`` conductor is
#: folded into (issue #173). Pre-fold this cell was a **145:1** rectangle
#: (1424.9 x 9.8 um) -- the single most extreme aspect ratio in the repo, and
#: the one `measurements/2026-09-layout-area/` identified as the direct cause
#: of the assembled top's 77.5% whitespace. Chosen to make the folded block
#: roughly square: with ``RES_FOLD_GAP_UM`` (0.4) and ``w=1u`` the leg pitch
#: is ~1.4 um, and a block is square at ``legs = sqrt(l / pitch)`` =
#: sqrt(1411.3 / 1.4) = 31.7. 32 rounds that to an **even** count, which is
#: what keeps both terminals on the block's bottom row (odd counts leave end
#: B on top -- see ``_draw_poly_res``) and therefore keeps this cell's
#: `vdd`/`det` escape topology unchanged in kind. Measured: 44.772 x 43.704
#: um, aspect 1.02. Identical count, and identical resulting geometry, to
#: the SG13G2 port's own ``RPU`` -- the two cells draw the same device.
RPU_LEGS = 32

# Device sizes, read from design/sg13cmos5l/netlist/bandgap_startup.spice.
RPU_W, RPU_L = 1.0, 1411.3
MSENSE_W, MSENSE_L = 10.0, 0.5
MKFB_W, MKFB_L = 2.0, 0.5

# Column origins. RPU starts at x=0; the two NMOS sit just past its right
# edge, the same relative topology they had pre-fold (they used to sit under
# the 1.4 mm bar's far end, at x=1395; folded, that far end -- RPU's own
# `det` terminal -- is at x=44.3, so the whole cluster moves left by 1340 um
# and keeps every one of its internal clearances unchanged). The 3 um step
# from the folded block's right edge (44.972) to the `sns1` tab clears that
# tab's own 0.7 um-wide GatPoly landing pad against RPU's own end-B head
# poly (which ends at 44.872) with ~2.8 um to spare -- checked, because a
# tighter placement would merge the two conductors outright.
X_RPU = 0.0
X_MSENSE = 55.0
X_MKFB = 80.0
#: ``sns1`` gate tab, ~1.8 um left of ``MSENSE``'s own gate endcap.
X_SNS1_TAB = 48.0
#: ``det`` gate tab, ~2.3 um right of ``MKFB``'s own gate endcap -- clear of
#: ``MKFB``'s ``fb`` drain pad (which ends at x=81) by >2 um.
X_DET_TAB = 83.5

# -- boundary ports for bandgap_top assembly (issue #76) -- see this
# module's own docstring "Boundary ports for bandgap_top assembly".
Y_SNS1_PORT = -1.2
#: fb jogs up to this height before turning right to the cell's own edge --
#: above det's own horizontal lane at Y_DET_LANE=3, which spans the entire
#: x=1395..1423.5 run (MSENSE to the det tab) and therefore crosses fb's own
#: column at x=1420. That crossing is resolved with a vertical poly
#: underpass spanning Y_FB_UNDERPASS, the same single-metal crossing
#: technique bandgap_amp/bandgap_core use, oriented across a horizontal
#: metal lane instead of a vertical one. The underpass's own landing pads
#: (0.5 um square, centred 2.0 um from det's lane) clear `metal1.space.1`'s
#: 0.18 um floor against that lane's own Metal1 by a wide margin -- a
#: tighter first attempt (pads 0.25 um from the lane) did not.
Y_FB_JOG = 6.0
Y_FB_UNDERPASS = (2.0, 4.0)
X_FB_PORT = 84.4


def build() -> Builder:
    b = Builder(TOP_CELL)

    rpu = draw_rhigh(b, "RPU", RPU_W, RPU_L, X_RPU, Y_RPU, end_a_net="vdd",
                     end_b_net="det", legs=RPU_LEGS)
    msense = draw_hv_nmos(
        b, "MSENSE", MSENSE_W, MSENSE_L, X_MSENSE, Y_MOS, "sns1", "vss", "det"
    )
    mkfb = draw_hv_nmos(b, "MKFB", MKFB_W, MKFB_L, X_MKFB, Y_MOS, "det", "vss", "fb")

    ports = _route(b, rpu, msense, mkfb)
    return b, ports


def _route(b: Builder, rpu: dict, msense: dict, mkfb: dict) -> dict[str, tuple[float, float, float, float]]:
    """Wire every schematic net. Only ``det`` and ``vss`` need routing at
    all; ``vdd``/``sns1``/``fb`` are ports whose single in-cell member the
    device primitives have already labelled.

    Returns the ``{net: pad_box}`` boundary-port map (issue #76) covering
    all four of this cell's schematic ports."""

    # -- vss: MSENSE and MKFB source pads (both at the bottom of their own
    # footprint, draw_hv_nmos's mirrored orientation), merged by one Metal1
    # bar spanning the row. The pads carry their own "vss" Metal1.pin labels
    # already; this bar only makes the two one physically-connected shape.
    # Already flush with the cell's own bottom edge, so this rail doubles
    # as vss's own boundary pad (issue #76).
    src = msense["source_pad"]
    vss_pad = (src[0], src[1], mkfb["source_pad"][2], src[3])
    b.box(L_METAL1, *vss_pad)

    # -- det: RPU's right head -> MSENSE.drain -> MKFB.gate, via one
    # horizontal lane at Y_DET_LANE. The drop off RPU's head is centred on
    # that pad rather than on the bar's own axis, and the drop into
    # MSENSE's drain lands wholly inside that pad -- both for the reason
    # bandgap_core's first DRC run established (a stem that overhangs its
    # landing pad's edge makes the join a step, and `metal1.width.1` flags
    # the notch).
    x_rpu_det = pad_center_x(rpu["end_b_pad"])
    route_v(b, L_METAL1, x_rpu_det, Y_DET_LANE, rpu["end_b_pad"][1], width=TRUNK_W)
    # Issue #173: the lane now starts at RPU's own drop column rather than at
    # X_MSENSE. Pre-fold the drop landed at x=1411.5, *right* of MSENSE, so
    # the lane's own X_MSENSE..X_DET_TAB span already covered it; folded, the
    # drop is at x=44.3, left of the whole MOS cluster, so the lane has to
    # reach out to it. It stays clear of `sns1`'s own tab column (x=48) --
    # that tab's Metal1 never rises above y=0.25, 2.75 um below this lane.
    route_h(b, L_METAL1, Y_DET_LANE, min(X_MSENSE, x_rpu_det), X_DET_TAB, width=TRUNK_W)
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
    sns1_tab = poly_tab(b, X_SNS1_TAB, Y_MOS, net="sns1")
    # Boundary port (issue #76): straight down to the bottom edge -- the tab
    # sits 2 um clear of the vss rail's own left edge (x=1390), so no
    # crossing is needed. See this module's own docstring.
    sns1_pad = boundary_port(b, "sns1", "bottom", Y_SNS1_PORT, X_SNS1_TAB)
    route_v(b, L_METAL1, X_SNS1_TAB, sns1_pad[3], sns1_tab[1], width=TRUNK_W)

    # Boundary port (issue #76): fb's own drain pad sits directly above the
    # vss rail (whose x-span, 1390..1421, includes the pad's own position),
    # so it jogs up first, then right to the cell's own edge -- crossing
    # det's own horizontal lane at Y_DET_LANE=3 (which spans the entire
    # x=1395..1423.5 run) on a vertical poly underpass, since that lane
    # covers fb's own column (x=1420) too.
    x_fb = pad_center_x(mkfb["drain_pad"])
    fb_pad = boundary_port(b, "fb", "right", X_FB_PORT, Y_FB_JOG)
    route_v(b, L_METAL1, x_fb, mkfb["drain_pad"][3], Y_FB_UNDERPASS[0], width=TRUNK_W)
    poly_tab(b, x_fb, Y_FB_UNDERPASS[0])
    route_v(b, L_GATPOLY, x_fb, Y_FB_UNDERPASS[0], Y_FB_UNDERPASS[1], width=TRUNK_W)
    poly_tab(b, x_fb, Y_FB_UNDERPASS[1])
    route_v(b, L_METAL1, x_fb, Y_FB_UNDERPASS[1], Y_FB_JOG, width=TRUNK_W)
    route_h(b, L_METAL1, Y_FB_JOG, x_fb, fb_pad[0], width=TRUNK_W)

    # vdd's own boundary pad (issue #76): RPU's own end-A head already sits
    # flush with the cell's own left edge (post-fold it is the block's
    # bottom-left terminal rather than a bar's left end), so it doubles as
    # vdd's own boundary pad -- no new geometry needed.
    vdd_pad = rpu["end_a_pad"]

    return {
        "vdd": vdd_pad,
        "vss": vss_pad,
        "sns1": sns1_pad,
        "fb": fb_pad,
    }


if __name__ == "__main__":
    builder, ports = build()
    builder.write(OUTPUT)
    print("ports:", {net: tuple(round(v, 3) for v in box) for net, box in ports.items()})
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
