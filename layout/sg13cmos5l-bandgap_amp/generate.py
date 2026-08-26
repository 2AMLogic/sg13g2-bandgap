#!/usr/bin/env python3
"""Generate ``sg13cmos5l-bandgap_amp.gds`` -- physical layout of
``design/sg13cmos5l/bandgap_amp.sch`` (the SG13CMOS5L port, issue #74).

Drawn with ``layout/common_sg13cmos5l.py``'s primitives. Two of them landed
for this issue: ``draw_hv_nmos`` (``bandgap_core`` is all-PMOS, so the CMOS5L
fork had no NMOS footprint) and ``poly_underpass`` (see "Not planar" below).

Run from the repo root::

    uv run --with klayout python3 layout/sg13cmos5l-bandgap_amp/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against
``design/sg13cmos5l/netlist/bandgap_amp.spice``:

    MTAIL sg13_hv_pmos w=10u l=1u   -- tail current source (g=out, d=tail)
    MP1   sg13_hv_pmos w=20u l=1u   -- input pair, + side (g=in_p, d=d1)
    MP2   sg13_hv_pmos w=20u l=1u   -- input pair, - side (g=in_n, d=d2)
    MP3   sg13_hv_pmos w=10u l=1u   -- diode-connected mirror head (g=d=pn)
    MP4   sg13_hv_pmos w=10u l=1u   -- mirror leg into the output (d=out)
    MN1   sg13_hv_nmos w=10u l=1u   -- diode-connected load, + side (g=d=d1)
    MN2   sg13_hv_nmos w=10u l=1u   -- diode-connected load, - side (g=d=d2)
    MN3   sg13_hv_nmos w=10u l=1u   -- output-side second stage (g=d1, d=out)
    MN4   sg13_hv_nmos w=10u l=1u   -- mirror-side second stage (g=d2, d=pn)

Floorplan
---------

Three device rows plus two horizontal routing lanes, all on ~90 x 42 um --
this is the first CMOS5L cell in this repo whose bounding box is set by its
own devices rather than by a millimetre-long straight resistor bar::

    y=40.9  ================= vdd rail ==========================
    y=40      MTAIL(x=20)         MP4(x=45)        MP3(x=70)
    y=36      ------- out lane (poly underpass at x=16..24) ------
    y=20.9  ------ tail bar [10..55] -------
    y=20      MP1(x=20)      MP2(x=45)        in_n tab(x=58)
    y=5       -- d1 jog [10..20] --   -- d2 jog [45..55] --
    y=0       MN3(x=0)  MN1(x=20)  MN2(x=45)  MN4(x=65)
    y=-0.9  ================= vss rail ==========================

**Column order is the circuit's own net-adjacency order, not an arbitrary
placement.** Reading the NMOS row left to right, ``MN3 -d1- MN1`` and
``MN2 -d2- MN4`` each become a single continuous ``GatPoly`` bar over field,
with ``MP1``/``MP2`` sitting directly above their own diode-connected load so
``d1``/``d2`` are straight vertical drops. Reading the top PMOS row, the
circuit's own path ``MP3 -pn- MP4 -out- MTAIL`` puts the ``pn`` mirror pair
adjacent (one shared gate bar again) and leaves exactly one tap per net.

Not planar -- one poly underpass, deliberately
----------------------------------------------

``bandgap_core`` is routed strictly planar because the curated ``sg13cmos5l``
deck's extraction stack is ``metals=((8, 0),)`` with ``vias=()`` -- one
routing metal, no via (klayout-tools#1417). **This circuit does not admit a
planar single-metal solution at that constraint**, and the obstruction is
structural rather than a placement accident:

* ``out`` has members in all three rows -- ``MTAIL``'s gate (top),
  ``MP4``'s drain (top) and ``MN3``'s drain (bottom) -- so it must cross the
  band between the top PMOS row and the input pair's row.
* ``MTAIL``'s drain (``tail``) must cross that same band, because its
  source is on the ``vdd`` rail above it and the input pair's sources are
  below it. Its drop therefore lands somewhere inside the ``tail`` bar's own
  span, i.e. inside the input pair's horizontal extent.
* ``out``'s bottom member (``MN3``) is outside that span (the NMOS row's
  net-adjacency order puts ``MN3`` at one end and ``MN4`` at the other), so
  ``out``'s path from the top row to the NMOS row and ``MTAIL``'s drop
  cannot both stay on one layer. Swapping any pair of columns moves the
  crossing, it does not remove it -- the two nets interleave.

The answer is the standard single-metal one, and it is a real crossing
rather than a workaround: ``out``'s lane dips onto ``GatPoly`` for 8 um
(``poly_underpass``, x=16..24 at y=36) and passes *under* ``MTAIL``'s Metal1
drop at x=20. ``GatPoly`` and ``Metal1`` are separate conductors in the
deck's connectivity graph, joined only through ``Cont`` (6/0), so nothing is
shorted -- verified against this cell's own ``klt extract`` output (``out``
comes back as one net, ``tail`` as another), not merely asserted. The
underpass crosses field only; a poly strip over ``Activ`` would be a
parasitic transistor, not a wire.

The bodies
----------

One ``NWell`` spans **both** PMOS rows rather than one well per device or one
per row, so all five PMOS body terminals resolve to a single well net --
matching the schematic, which ties every PMOS body to ``vdd``. As
``bandgap_core`` already established (``layout/README.md`` cause 4), that is
the only part of the body connection the curated deck can express at all: it
declares no tap layer (``tap``/``tap_nplus``/``tap_pplus`` all ``None``), so
no drawn geometry can join a well net to a rail. The NMOS bodies hit the same
gap from the other side -- they fall back to the deck's synthesized ``vsubs``
global, which no drawn substrate tie can resolve to ``vss``.

LVS status is recorded, with each cause re-verified against this cell's own
reports, in ``layout/README.md`` "Cell: ``sg13cmos5l-bandgap_amp``".

Boundary ports for ``bandgap_top`` assembly (issue #76)
---------------------------------------------------------

``vdd`` (top rail), ``vss`` (bottom rail) and ``out`` (``MN3``'s own drain
pad, whose device width happens to reach the cell's left edge) were already
flush with this cell's own bounding box. ``in_p``/``in_n`` were not -- each
is a poly gate tap in the interior (``X_IN_P_TAB=7``, ``X_IN_N_TAB=58``),
same gap issue #76 found in ``bandgap_core``. Both now get a dedicated
:func:`boundary_port`, reached by extending each tap's own gate-link
sideways to a cell edge:

* ``in_p`` -- left, at ``y=20`` (the input pair's own row) -- crossing
  ``out``'s own vertical stub at ``x=0`` (which spans the entire
  ``y=0.64..36`` band between ``MN3``'s drain and the underpass lane) on a
  second :func:`poly_underpass`, distinct from the one this cell already
  uses for ``out`` itself.
* ``in_n`` -- right, at the same ``y=20`` -- crossing ``pn``'s own vertical
  stub at ``x=65`` (``MN4``'s drain up to the ``Y_OUT_LANE`` turn) on a
  third poly underpass.

``build()`` now returns ``(Builder, ports)``, a ``{net: pad_box}`` map
covering all five of this cell's schematic ports.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common_sg13cmos5l import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    L_NWELL,
    Builder,
    boundary_port,
    draw_hv_nmos,
    draw_hv_pmos,
    poly_tab,
    poly_underpass,
    route_h,
    route_v,
)

TOP_CELL = "sg13cmos5l_bandgap_amp"
OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sg13cmos5l-bandgap_amp.gds"
)

#: Routing width for every Metal1 trunk -- same value, and same rationale, as
#: ``sg13cmos5l-bandgap_core``'s: the curated deck's ``metal1.width.1`` floor
#: is 0.16 um and ``metal1.space.1`` is 0.18 um, so 0.30 um clears the width
#: floor with ~2x margin and every clearance below is checked against 0.18 um.
TRUNK_W = 0.30

#: Width of a ``GatPoly`` bar that links two devices' own gate rectangles.
#: Drawn at the devices' channel length (1.0 um) rather than at ``TRUNK_W``
#: so the link and the two gate boxes merge into one plain rectangle with no
#: T-junction at all -- the gate boxes are exactly ``l`` tall.
GATE_LINK_W = 1.0

# Row centres (see the floorplan sketch in this module's docstring).
Y_P1 = 40.0  # MTAIL / MP4 / MP3
Y_OUT_LANE = 36.0
Y_P2 = 20.0  # MP1 / MP2
Y_LOAD_LANE = 5.0
Y_N = 0.0  # MN3 / MN1 / MN2 / MN4

# Column origins, in the net-adjacency order the docstring explains.
X_MN3, X_MN1, X_MN2, X_MN4 = 0.0, 20.0, 45.0, 65.0
X_MP1, X_MP2 = 20.0, 45.0
X_MTAIL, X_MP4, X_MP3 = 20.0, 45.0, 70.0

# Device sizes, read from design/sg13cmos5l/netlist/bandgap_amp.spice.
MOS_L = 1.0
W_TAIL, W_IN, W_MIRROR, W_NMOS = 10.0, 20.0, 10.0, 10.0

#: Gate-tap columns. Each sits over **field** between two devices (never over
#: ``Activ``, which would make the contact a gate-to-channel short) and clear
#: of every Metal1 trunk by several microns.
X_D1_TAB = 10.0  # on the MN3<->MN1 gate bar, between the two devices
X_D2_TAB = 55.0  # on the MN2<->MN4 gate bar
X_OUT_TAB = 10.0  # on MTAIL's gate, escaping left
X_PN_TAB = 57.5  # on the shared MP4<->MP3 gate bar
X_IN_P_TAB = 7.0  # on MP1's gate, escaping left
X_IN_N_TAB = 58.0  # on MP2's gate, escaping right

#: The ``out`` lane's poly underpass, spanning ``MTAIL``'s Metal1 drain drop
#: at x=20 with ~3.8 um of clearance on each side. See "Not planar" in this
#: module's docstring for why the crossing exists at all.
X_UNDERPASS = (16.0, 24.0)

# -- boundary ports for bandgap_top assembly (issue #76) -- see this
# module's own docstring "Boundary ports for bandgap_top assembly".
Y_IN_P_PORT = 20.0
X_IN_P_PORT = -7.0
#: in_p's crossing of out's own vertical stub at x=0 (spans y=0.64..36).
X_IN_P_UNDERPASS = (-2.0, 2.0)
Y_IN_N_PORT = 20.0
X_IN_N_PORT = 77.0
#: in_n's crossing of pn's own vertical stub at x=65 (spans y=0.64..36).
X_IN_N_UNDERPASS = (63.0, 67.0)


def build() -> Builder:
    b = Builder(TOP_CELL)

    # -- NMOS row: four devices, sources down onto the vss rail ------------
    mn3 = draw_hv_nmos(b, "MN3", W_NMOS, MOS_L, X_MN3, Y_N, "d1", "vss", "out")
    mn1 = draw_hv_nmos(b, "MN1", W_NMOS, MOS_L, X_MN1, Y_N, "d1", "vss", "d1")
    mn2 = draw_hv_nmos(b, "MN2", W_NMOS, MOS_L, X_MN2, Y_N, "d2", "vss", "d2")
    mn4 = draw_hv_nmos(b, "MN4", W_NMOS, MOS_L, X_MN4, Y_N, "d2", "vss", "pn")

    # -- input pair, sources up onto the tail bar --------------------------
    mp1 = draw_hv_pmos(b, "MP1", W_IN, MOS_L, X_MP1, Y_P2, "in_p", "tail", "d1",
                       draw_nwell=False)
    mp2 = draw_hv_pmos(b, "MP2", W_IN, MOS_L, X_MP2, Y_P2, "in_n", "tail", "d2",
                       draw_nwell=False)

    # -- top PMOS row, sources up onto the vdd rail ------------------------
    mtail = draw_hv_pmos(b, "MTAIL", W_TAIL, MOS_L, X_MTAIL, Y_P1, "out", "vdd", "tail",
                         draw_nwell=False)
    mp4 = draw_hv_pmos(b, "MP4", W_MIRROR, MOS_L, X_MP4, Y_P1, "pn", "vdd", "out",
                       draw_nwell=False)
    mp3 = draw_hv_pmos(b, "MP3", W_MIRROR, MOS_L, X_MP3, Y_P1, "pn", "vdd", "pn",
                       draw_nwell=False)

    # -- one NWell across both PMOS rows -----------------------------------
    # draw_nwell=False on all five above: five separate wells would extract
    # as five unrelated body nets for a schematic that ties every PMOS body
    # to the same vdd. Deliberately **not** well-labelled, for the reason
    # bandgap_core's own generate.py records at length (layout/README.md
    # cause 4): with no tap layer in the deck, a NWell.pin text names an
    # isolated net without connecting it, and its only real effect is to
    # suppress klt extract's own "no DC bias path" warning -- the most
    # direct evidence of the gap.
    wells = [d["nwell"] for d in (mp1, mp2, mtail, mp4, mp3)]
    b.box(
        L_NWELL,
        min(w[0] for w in wells), min(w[1] for w in wells),
        max(w[2] for w in wells), max(w[3] for w in wells),
    )

    ports = _route(b, mn3, mn1, mn2, mn4, mp1, mp2, mtail, mp4, mp3)
    return b, ports


def _route(
    b: Builder,
    mn3: dict, mn1: dict, mn2: dict, mn4: dict,
    mp1: dict, mp2: dict,
    mtail: dict, mp4: dict, mp3: dict,
) -> dict[str, tuple[float, float, float, float]]:
    """Wire every schematic net. Each block names the net it wires; see the
    module docstring for the floorplan and for the one crossing.

    Returns the ``{net: pad_box}`` boundary-port map (issue #76) covering
    all five of this cell's schematic ports."""

    # -- vdd: MTAIL/MP4/MP3 source pads, merged by one Metal1 bar. The pads
    # already carry their own "vdd" Metal1.pin labels; this bar only makes
    # the three one physically-connected shape. Already flush with the
    # cell's own top+right edges (issue #76's boundary-port survey), so this
    # rail doubles as vdd's own boundary pad.
    src = mtail["source_pad"]
    vdd_pad = (src[0], src[1], mp3["source_pad"][2], src[3])
    b.box(L_METAL1, *vdd_pad)

    # -- vss: all four NMOS source pads (at the *bottom* of their own
    # footprints, draw_hv_nmos's mirrored orientation), same construction.
    # Already flush with the cell's own left+bottom edges, so this rail
    # doubles as vss's own boundary pad (issue #76).
    nsrc = mn3["source_pad"]
    vss_pad = (nsrc[0], nsrc[1], mn4["source_pad"][2], nsrc[3])
    b.box(L_METAL1, *vss_pad)

    # -- tail: MP1/MP2 source pads merged, with MTAIL's drain dropping onto
    # the result. The drop lands wholly inside MP1's own source pad (x=20 is
    # that pad's centre), the T-junction rule bandgap_core's first DRC run
    # established.
    tsrc = mp1["source_pad"]
    b.box(L_METAL1, tsrc[0], tsrc[1], mp2["source_pad"][2], tsrc[3])
    route_v(b, L_METAL1, X_MTAIL, tsrc[3], mtail["drain_pad"][1], width=TRUNK_W)

    # -- d1: MP1.drain -> MN1.drain (straight down, same column), plus the
    # MN3<->MN1 shared gate bar tapped up to that trunk.
    route_v(b, L_METAL1, X_MN1, mn1["drain_pad"][3], mp1["drain_pad"][1], width=TRUNK_W)
    _gate_link(b, Y_N, mn3["gate_box"][2], mn1["gate_box"][0])
    poly_tab(b, X_D1_TAB, Y_N)
    route_v(b, L_METAL1, X_D1_TAB, Y_N, Y_LOAD_LANE, width=TRUNK_W)
    route_h(b, L_METAL1, Y_LOAD_LANE, X_D1_TAB, X_MN1, width=TRUNK_W)

    # -- d2: the mirror image of d1 on the other half of the row.
    route_v(b, L_METAL1, X_MN2, mn2["drain_pad"][3], mp2["drain_pad"][1], width=TRUNK_W)
    _gate_link(b, Y_N, mn2["gate_box"][2], mn4["gate_box"][0])
    poly_tab(b, X_D2_TAB, Y_N)
    route_v(b, L_METAL1, X_D2_TAB, Y_N, Y_LOAD_LANE, width=TRUNK_W)
    route_h(b, L_METAL1, Y_LOAD_LANE, X_MN2, X_D2_TAB, width=TRUNK_W)

    # -- out: MN3.drain (bottom row) -> MP4.drain and MTAIL.gate (top row).
    # The lane at Y_OUT_LANE dips onto GatPoly across X_UNDERPASS to pass
    # under MTAIL's drain drop -- the cell's one crossing, see the module
    # docstring. MN3's own drain pad already reaches the cell's own left
    # edge (its device width places it there), so it doubles as out's own
    # boundary pad (issue #76).
    out_pad = mn3["drain_pad"]
    route_v(b, L_METAL1, X_MN3, mn3["drain_pad"][3], Y_OUT_LANE, width=TRUNK_W)
    route_h(b, L_METAL1, Y_OUT_LANE, X_MN3, X_UNDERPASS[0], width=TRUNK_W)
    poly_underpass(b, Y_OUT_LANE, X_UNDERPASS[0], X_UNDERPASS[1], width=TRUNK_W)
    route_h(b, L_METAL1, Y_OUT_LANE, X_UNDERPASS[1], X_MP4, width=TRUNK_W)
    route_v(b, L_METAL1, X_MP4, Y_OUT_LANE, mp4["drain_pad"][1], width=TRUNK_W)
    # MTAIL's gate escapes left to a tap the lane rises into.
    _gate_link(b, Y_P1, X_OUT_TAB, mtail["gate_box"][0])
    poly_tab(b, X_OUT_TAB, Y_P1)
    route_v(b, L_METAL1, X_OUT_TAB, Y_OUT_LANE, Y_P1, width=TRUNK_W)

    # -- pn: MP3.gate + MP3.drain + MP4.gate (top row) -> MN4.drain (bottom).
    # MP4 and MP3 share one continuous gate bar, tapped in the field between
    # them; MP3's own drain joins that tap along its pad's own y-band.
    _gate_link(b, Y_P1, mp4["gate_box"][2], mp3["gate_box"][0])
    pn_tab = poly_tab(b, X_PN_TAB, Y_P1)
    route_v(b, L_METAL1, X_MN4, mn4["drain_pad"][3], Y_OUT_LANE, width=TRUNK_W)
    route_h(b, L_METAL1, Y_OUT_LANE, X_PN_TAB, X_MN4, width=TRUNK_W)
    route_v(b, L_METAL1, X_PN_TAB, Y_OUT_LANE, Y_P1, width=TRUNK_W)
    drain = mp3["drain_pad"]
    b.box(L_METAL1, pn_tab[0], drain[1], _pad_center_x(drain), drain[3])

    # -- in_p / in_n: the input pair's gates, each escaping to its own
    # labelled tap. Without one the net would extract as an anonymous `$N`:
    # the curated deck declares `poly_label=None`, so a gate net can only be
    # named through a Metal1 pad contacted to its poly.
    _gate_link(b, Y_P2, X_IN_P_TAB, mp1["gate_box"][0])
    poly_tab(b, X_IN_P_TAB, Y_P2, net="in_p")
    _gate_link(b, Y_P2, mp2["gate_box"][2], X_IN_N_TAB)
    poly_tab(b, X_IN_N_TAB, Y_P2, net="in_n")

    # Boundary ports (issue #76): both taps are interior. in_p escapes left
    # at the same y, crossing out's own vertical stub at x=0 (which spans
    # y=0.64..36) on a poly_underpass; in_n escapes right, crossing pn's own
    # vertical stub at x=65 on a second one. See this module's own docstring.
    in_p_pad = boundary_port(b, "in_p", "left", X_IN_P_PORT, Y_IN_P_PORT)
    route_h(b, L_METAL1, Y_IN_P_PORT, in_p_pad[2], X_IN_P_UNDERPASS[0], width=TRUNK_W)
    poly_underpass(b, Y_IN_P_PORT, X_IN_P_UNDERPASS[0], X_IN_P_UNDERPASS[1], width=TRUNK_W)
    route_h(b, L_METAL1, Y_IN_P_PORT, X_IN_P_UNDERPASS[1], X_IN_P_TAB, width=TRUNK_W)

    in_n_pad = boundary_port(b, "in_n", "right", X_IN_N_PORT, Y_IN_N_PORT)
    route_h(b, L_METAL1, Y_IN_N_PORT, X_IN_N_TAB, X_IN_N_UNDERPASS[0], width=TRUNK_W)
    poly_underpass(b, Y_IN_N_PORT, X_IN_N_UNDERPASS[0], X_IN_N_UNDERPASS[1], width=TRUNK_W)
    route_h(b, L_METAL1, Y_IN_N_PORT, X_IN_N_UNDERPASS[1], in_n_pad[0], width=TRUNK_W)

    return {
        "vdd": vdd_pad,
        "vss": vss_pad,
        "out": out_pad,
        "in_p": in_p_pad,
        "in_n": in_n_pad,
    }


def _gate_link(b: Builder, y: float, x0: float, x1: float) -> None:
    """Join two gate rectangles (or a gate and a tap column) with a
    ``GATE_LINK_W``-tall ``GatPoly`` bar at ``y``.

    Drawn at the devices' own channel length rather than at ``TRUNK_W`` so
    the link and the gate boxes it joins merge into a single plain rectangle
    -- no T-junction, and therefore nothing for ``gatpoly.width.1`` to read
    as a notch. Every call below links over **field**: the gate boxes
    already cover their own ``Activ``.
    """
    route_h(b, L_GATPOLY, y, x0, x1, width=GATE_LINK_W)


def _pad_center_x(pad: tuple[float, float, float, float]) -> float:
    """X centre of a returned terminal pad box."""
    return (pad[0] + pad[2]) / 2


if __name__ == "__main__":
    builder, ports = build()
    builder.write(OUTPUT)
    print("ports:", {net: tuple(round(v, 3) for v in box) for net, box in ports.items()})
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
