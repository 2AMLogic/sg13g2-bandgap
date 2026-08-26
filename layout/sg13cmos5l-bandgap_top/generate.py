#!/usr/bin/env python3
"""Generate ``sg13cmos5l-bandgap_top.gds`` -- hierarchical assembly of the
three SG13CMOS5L leaf cells (issue #81, following on from #76's boundary-port
convention).

Unlike every other ``generate.py`` in this repo, this one does **not** draw
device geometry from scratch: it reads the three already-committed leaf GDS
files (``sg13cmos5l-bandgap_core.gds``/``_amp.gds``/``_startup.gds``) as
``klayout.db`` cell instances into one new top-level layout, then draws only
the **inter-cell routing** between each leaf's own ``boundary_port()`` pads
(issue #76) -- the leaf cells' own internal geometry is untouched.

Run from the repo root::

    uv run --with klayout python3 layout/sg13cmos5l-bandgap_top/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty (as long as the three leaf GDS files it reads are
themselves unchanged).

Connectivity, one-to-one against ``design/sg13cmos5l/netlist/
bandgap_top.spice``'s own ``.subckt bandgap_top vdd vss vref`` line::

    Xx1 vdd vss fb sns1 sns2 vref bandgap_core
    Xx2 sns2 sns1 vss fb vdd     bandgap_amp    (in_p in_n vss out vdd)
    Xx3 vdd vss sns1 fb          bandgap_startup

so, per shared net:

    vdd   -- core, amp, startup, and bandgap_top's own external port.
    vss   -- core, amp, startup, and bandgap_top's own external port.
    fb    -- core, amp.out, startup            (internal only -- no top port)
    sns1  -- core, amp.in_n, startup           (internal only -- no top port)
    sns2  -- core, amp.in_p                    (internal only -- no top port)
    vref  -- core only, brought out to bandgap_top's own external port.

Floorplan
---------

The three leaf cells are placed side by side, left to right, in a single
row -- ``bandgap_core`` (~840 um wide) leftmost, ``bandgap_amp`` (~84 um)
in the middle, ``bandgap_startup`` (~1425 um) rightmost -- separated by
30 um gaps that are otherwise **empty at every height** (no cell's own
bounding box reaches into a neighbour's gap at any y), the same property
every leaf cell's own single-metal floorplan already exploits internally::

    core (-10, -3.21)-(830.5, 61.7)
      | 30 um gap (830.5 .. 860.5) |
    amp (860.5, -1.24)-(944.5, 41.7)
      | 30 um gap (944.5 .. 975.0) |
    startup (974.5, -1.2)-(2399.4, 8.6)

Since the three cells occupy **disjoint x-ranges**, a vertical route drawn
anywhere within one cell's own x-span can only ever collide with that same
cell's own geometry -- never a neighbour's -- which is what makes the
"rise straight up/down, then travel" routing below safe to reason about
one net at a time.

Routing: buses + poly risers
-----------------------------

``vdd``, ``vss``, ``fb`` and ``sns1`` each need all **three** cells --
a channel-routing problem four-nets deep, at the assembly's own single
modelled metal (``metals=((8, 0),)``, ``vias=()``, klayout-tools#1417,
same constraint every leaf cell's own floorplan already works within).
Four full-span nets stacked on one metal layer cannot all avoid crossing
each other's connections purely by choice of route (a bus that reaches
every one of three widely-separated cells necessarily spans the x-range
any *other* bus's riser must cross to reach a taller bus) -- so this
follows the same answer the leaf cells already established for their own
internal crossings (``poly_underpass()`` in each cell's own ``_route()``):
cross on ``GatPoly`` instead. Concretely, each net gets:

* **one straight horizontal ``Metal1`` bus**, at a height above (``vdd``/
  ``vss``) or further above (``fb``/``sns1``) every cell's own bounding
  box top (``Y_BUS_VDD=75`` .. ``Y_BUS_SNS1=120``, all comfortably clear
  of ``core``'s own 61.7 um top -- the tallest of the three);
* **one ``GatPoly`` riser per contributing cell**, each at its own
  dedicated column, transitioning ``Metal1`` -> ``GatPoly`` -> ``Metal1``
  via :func:`poly_tab` at both ends (the same primitive every leaf cell's
  own ``poly_underpass``/gate-tap connections already use) -- so a riser
  for one net passes *underneath* every other net's ``Metal1`` bus it
  needs to cross (different conductors, joined only through ``Cont``,
  exactly as already verified for each leaf cell's own internal
  crossings) without touching it.

Since every riser is a plain vertical line at its own column, the only
remaining thing to avoid is two *different* nets' risers sharing a column
-- trivially satisfied here since every column below is chosen from each
cell's own natural pad position (never reused across nets).

``sns2`` (``core``+``amp`` only) and ``vref`` (``core`` + this assembly's
own external port) do not need the bus system at all: each is routed
directly, entirely on ``Metal1``, through a dedicated height/column chosen
to clear every other net's own path (see :func:`_route_sns2`/
:func:`_route_vref`'s own comments for the specific clearances checked).

Verified, not just laid out (see ``layout/README.md`` "Cell:
``sg13cmos5l-bandgap_top``" for the full account): ``klt extract``'s own
net list confirms each of the six shared nets above merges into exactly
one physically-connected net across all of its contributing cells, with
no accidental short to any other net.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import klayout.db as kdb  # noqa: E402
from common_sg13cmos5l import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    LAYER_NAMES,
    Builder,
    poly_tab,
    route_h,
    route_v,
)

HERE = os.path.dirname(os.path.abspath(__file__))
TOP_CELL = "sg13cmos5l_bandgap_top"
OUTPUT = os.path.join(HERE, "sg13cmos5l-bandgap_top.gds")

CORE_CELL = "sg13cmos5l_bandgap_core"
AMP_CELL = "sg13cmos5l_bandgap_amp"
STARTUP_CELL = "sg13cmos5l_bandgap_startup"

CORE_GDS = os.path.join(HERE, "..", "sg13cmos5l-bandgap_core", "sg13cmos5l-bandgap_core.gds")
AMP_GDS = os.path.join(HERE, "..", "sg13cmos5l-bandgap_amp", "sg13cmos5l-bandgap_amp.gds")
STARTUP_GDS = os.path.join(
    HERE, "..", "sg13cmos5l-bandgap_startup", "sg13cmos5l-bandgap_startup.gds"
)

#: Routing width for every Metal1/GatPoly segment this module draws -- same
#: value, and same rationale, as every leaf cell's own ``TRUNK_W``: the
#: curated deck's ``metal1.width.1``/``gatpoly.width.1`` floor is 0.16 um and
#: the corresponding ``space.1`` floor is 0.18 um, so 0.30 um clears the
#: width floor with ~2x margin.
TRUNK_W = 0.30

# --------------------------------------------------------------------------- #
# Floorplan: each leaf cell's own placement offset (translation only -- no
# mirroring needed, since every inter-cell connection below is routed via a
# dedicated bus/column rather than relying on adjacent edges lining up).
# 30 um gaps on both sides of `amp`, chosen only to leave clear routing
# corridors -- see this module's own docstring.
# --------------------------------------------------------------------------- #
CORE_DX, CORE_DY = 0.0, 0.0
AMP_DX, AMP_DY = 867.5, 0.0
STARTUP_DX, STARTUP_DY = 975.0, 0.0

# Each leaf's own boundary-port map (issue #76), in **its own local
# coordinates** -- reproduced here from that cell's own generate.py `build()`
# printout rather than re-run at generate time, since this module instances
# the already-committed GDS, not the leaf's Python `build()` function.
_CORE_PORTS_LOCAL = {
    "vdd": (-5.0, 60.64, 185.0, 60.9),
    "vss": (824.52, -2.99, 829.98, 2.99),
    "fb": (-8.38, 59.9, -7.98, 60.1),
    "sns1": (-10.0, 49.75, -9.5, 50.25),
    "sns2": (830.0, 49.75, 830.5, 50.25),
    "vref": (830.0, 39.75, 830.5, 40.25),
}
_AMP_PORTS_LOCAL = {
    "vdd": (15.0, 40.64, 75.0, 40.9),
    "vss": (-5.0, -0.9, 70.0, -0.64),
    "out": (-5.0, 0.64, 5.0, 0.9),
    "in_p": (-7.0, 19.75, -6.5, 20.25),
    "in_n": (76.5, 19.75, 77.0, 20.25),
}
_STARTUP_PORTS_LOCAL = {
    "vdd": (-0.5, 7.4, 0.0, 8.6),
    "vss": (1390.0, -0.65, 1421.0, -0.39),
    "sns1": (1387.75, -1.2, 1388.25, -0.7),
    "fb": (1423.9, 5.75, 1424.4, 6.25),
}


def _shift(box: tuple[float, float, float, float], dx: float, dy: float):
    x0, y0, x1, y1 = box
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


CORE = {k: _shift(v, CORE_DX, CORE_DY) for k, v in _CORE_PORTS_LOCAL.items()}
AMP = {k: _shift(v, AMP_DX, AMP_DY) for k, v in _AMP_PORTS_LOCAL.items()}
STARTUP = {k: _shift(v, STARTUP_DX, STARTUP_DY) for k, v in _STARTUP_PORTS_LOCAL.items()}

# Bus heights (Metal1, horizontal), all comfortably above every leaf cell's
# own bounding-box top (core's own 61.7 um is the tallest of the three).
Y_BUS_VDD = 75.0
Y_BUS_VSS = 90.0
Y_BUS_FB = 105.0
Y_BUS_SNS1 = 120.0
BUS_HEIGHT = 1.0

#: bandgap_top's own external port pads (vdd/vss/vref -- the only three
#: nets `design/sg13cmos5l/netlist/bandgap_top.spice`'s own `.subckt
#: bandgap_top vdd vss vref` line declares) sit at the far left of the
#: assembly, clear of every cell and every riser column used below.
X_PORT_VDD = -40.0
X_PORT_VSS = -45.0
X_PORT_VREF = -50.0


class TopBuilder(Builder):
    """A :class:`common_sg13cmos5l.Builder` attached to an **existing**
    ``kdb.Layout`` (already populated by reading the three leaf GDS files),
    rather than one that creates a brand-new layout of its own.

    This is the only difference from the parent class -- reusing
    ``Builder``'s ``box``/``net_label``/``_u`` methods lets this module call
    :func:`common_sg13cmos5l.poly_tab`/``route_h``/``route_v`` unchanged
    against the merged assembly layout, exactly as every leaf cell's own
    ``generate.py`` already does against its own private layout.
    """

    def __init__(self, layout: kdb.Layout, top_cell: str) -> None:
        # Deliberately does NOT call BuilderBase.__init__ (which always
        # creates a brand-new kdb.Layout) -- `layout` here already carries
        # the three leaf cells, read in by build() below.
        self.layout = layout
        self.cell = layout.create_cell(top_cell)
        self._layers: dict[tuple[int, int], int] = {}
        for pair, name in LAYER_NAMES.items():
            index = layout.layer(*pair)
            layout.set_info(index, kdb.LayerInfo(pair[0], pair[1], name))
            self._layers[pair] = index


def build() -> TopBuilder:
    layout = kdb.Layout()
    layout.dbu = 0.001

    # Reading each leaf GDS in turn merges their (already-identical, since
    # all three share common_sg13cmos5l.py's own LAYER_NAMES) layer tables
    # into one shared set of layer indices -- verified interactively before
    # writing this module: klayout.db.Layout.read() reuses an existing
    # (layer, datatype) registration rather than duplicating it.
    layout.read(CORE_GDS)
    layout.read(AMP_GDS)
    layout.read(STARTUP_GDS)

    core_idx = layout.cell(CORE_CELL).cell_index()
    amp_idx = layout.cell(AMP_CELL).cell_index()
    startup_idx = layout.cell(STARTUP_CELL).cell_index()

    b = TopBuilder(layout, TOP_CELL)

    def u(value_um: float) -> int:
        return int(round(value_um / layout.dbu))

    b.cell.insert(kdb.CellInstArray(core_idx, kdb.Trans(u(CORE_DX), u(CORE_DY))))
    b.cell.insert(kdb.CellInstArray(amp_idx, kdb.Trans(u(AMP_DX), u(AMP_DY))))
    b.cell.insert(kdb.CellInstArray(startup_idx, kdb.Trans(u(STARTUP_DX), u(STARTUP_DY))))

    _route(b)
    return b


#: ``bandgap_startup``'s own ``RPU`` (a deck-unrecognised ``rhigh`` resistor,
#: see ``layout/README.md`` "LVS -- ``mismatch``, fully attributed", cause 2)
#: draws its conductor *body* as one long, unbroken ``GatPoly`` bar spanning
#: almost the entire cell's own width (``draw_rhigh``'s main span, local
#: ``x=0..1411.3``, ``y=Y_RPU-w/2..Y_RPU+w/2`` = ``7.5..8.5`` at this
#: assembly's own ``STARTUP_DY=0``). Both ``sns1``'s and ``vss``'s own
#: natural riser columns (chosen to reuse each cell's own existing tap/pad
#: locations, see :func:`_route_vss`/:func:`_route_sns1`) fall within that
#: x-span -- a plain ``GatPoly`` riser through it would physically merge
#: with ``RPU``'s own body and, transitively, with every other net that
#: body's own already-documented deck-gap short already pulls in (``vdd``,
#: via its unmodelled-resistor short into ``det`` -- a real, pre-existing
#: gap this assembly inherits, not introduced here).
#:
#: ``(6.8, 9.2)`` -- **not** a bare 0.2 um past the body's own ``7.5..8.5``
#: -- because :func:`poly_tab`'s own ``GatPoly`` landing pad is itself
#: ``TAB_PAD_UM + 2*TAB_POLY_MARGIN_UM`` = 0.70 um tall (0.35 um each side
#: of the transition point), so a transition placed only 0.2 um clear of
#: the body would still have its *own pad* overlap it. 6.8/9.2 keep that
#: 0.35 um pad half-height, plus a further ~0.15 um of clearance, entirely
#: outside 7.5..8.5 (found by direct `klt extract` re-verification after
#: the first, too-tight attempt (7.3, 8.7) still merged sns1/vss into
#: RPU's own already-shorted vdd|det net -- see this issue's own PR
#: description for that failed attempt).
STARTUP_RPU_BODY_Y = (6.8, 9.2)


def _riser(
    b: TopBuilder,
    x: float,
    y_near: float,
    y_bus: float,
    bridge: tuple[float, float] | None = None,
) -> None:
    """One ``Metal1``<->``GatPoly``<->``Metal1`` riser at a fixed column
    ``x``, from ``y_near`` (where the caller's own Metal1 approach stub
    already ends) straight to ``y_bus`` (the target bus's own height).

    Built from the same :func:`poly_tab` primitive every leaf cell's own
    ``poly_underpass()`` uses at each end of a crossing -- the only
    difference here is the poly run in between is much longer (spanning
    however many *other* nets' buses sit between ``y_near`` and ``y_bus``),
    which is exactly why crossing them is safe: those buses are ``Metal1``,
    a different conductor, joined to this riser's own ``GatPoly`` only
    through ``Cont`` at the two :func:`poly_tab` calls below, not anywhere
    it merely passes underneath.

    ``bridge``, when given, names a ``(lo, hi)`` sub-range where this riser
    switches back to ``Metal1`` instead -- the *opposite* crossing, for the
    one case that needs it: a leaf cell's own ``GatPoly`` conductor sharing
    this riser's column (see :data:`STARTUP_RPU_BODY_Y`). A plain ``Metal1``
    bridge across that narrow band is a safe crossing for the same reason a
    poly riser is safe under a ``Metal1`` bus -- different conductor,
    joined only through :func:`poly_tab`'s own ``Cont``, not by passing
    through it.
    """
    poly_tab(b, x, y_near)
    if bridge is None:
        route_v(b, L_GATPOLY, x, y_near, y_bus, width=TRUNK_W)
        poly_tab(b, x, y_bus)
        return
    lo, hi = bridge
    route_v(b, L_GATPOLY, x, y_near, lo, width=TRUNK_W)
    poly_tab(b, x, lo)
    route_v(b, L_METAL1, x, lo, hi, width=TRUNK_W)
    poly_tab(b, x, hi)
    route_v(b, L_GATPOLY, x, hi, y_bus, width=TRUNK_W)
    poly_tab(b, x, y_bus)


def _route_bus_net(
    b: TopBuilder,
    net: str,
    y_bus: float,
    risers: list[tuple[float, float, tuple[float, float] | None]],
    port_x: float | None = None,
) -> None:
    """Draw one net's Metal1 bus plus every one of its risers' landing
    columns, and (if ``port_x`` is given) extend the bus out to that column
    and label it -- bandgap_top's own external port for this net.

    Each entry in ``risers`` is ``(x, y_near, bridge)`` -- see :func:`_riser`
    for what ``bridge`` does."""
    xs = [x for x, _, _ in risers]
    if port_x is not None:
        xs.append(port_x)
    x_lo, x_hi = min(xs) - 0.5, max(xs) + 0.5
    route_h(b, L_METAL1, y_bus, x_lo, x_hi, width=BUS_HEIGHT)
    for x, y_near, bridge in risers:
        _riser(b, x, y_near, y_bus, bridge=bridge)
    if port_x is not None:
        b.net_label(net, port_x + 0.25, y_bus)


def _route_vdd(b: TopBuilder) -> None:
    """``vdd``: core, amp, startup, and bandgap_top's own external port.

    Each cell's own vdd pad sits on (or very near) that cell's own
    bounding-box top -- rising straight up from it, at any x within the
    pad's own span, clears that cell's own footprint immediately (no other
    leaf cell shares that x-range, per this module's own floorplan) with
    nothing else of that same cell's geometry in the way (verified: each
    column below sits away from any device's own centreline)."""
    core_pad = CORE["vdd"]
    x_core = 90.0  # within (-5, 185); clear of M1/M2/M3's own centres (0/45/180)
    route_v(b, L_METAL1, x_core, core_pad[3], 63.0, width=TRUNK_W)

    amp_pad = AMP["vdd"]
    x_amp = 910.0  # within (882.5, 942.5); clear of MTAIL/MP4/MP3 (887.5/912.5/937.5)
    route_v(b, L_METAL1, x_amp, amp_pad[3], 43.0, width=TRUNK_W)

    startup_pad = STARTUP["vdd"]
    x_startup = (startup_pad[0] + startup_pad[2]) / 2  # 974.75, mid of a 0.5 um pad
    route_v(b, L_METAL1, x_startup, startup_pad[3], 10.0, width=TRUNK_W)

    _route_bus_net(
        b,
        "vdd",
        Y_BUS_VDD,
        [(x_core, 63.0, None), (x_amp, 43.0, None), (x_startup, 10.0, None)],
        port_x=X_PORT_VDD,
    )


def _route_vss(b: TopBuilder) -> None:
    """``vss``: core, amp, startup, and bandgap_top's own external port.

    ``core``'s own vss pad (Q3's collector ring) and ``amp``'s own vss pad
    (the merged NMOS source rail) both face the shared core-amp gap
    (830.5..860.5, empty at every height) -- each gets a short Metal1
    approach into that gap before rising independently (no need to meet at
    a shared point first: the bus itself is what merges them)."""
    core_pad = CORE["vss"]
    x_core = 832.0  # barely into the core-amp gap
    route_h(b, L_METAL1, 0.0, core_pad[2], x_core, width=TRUNK_W)

    amp_pad = AMP["vss"]
    x_amp = 858.0  # also within the core-amp gap, distinct column
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # -0.77, mid of amp's own vss pad
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["vss"]
    x_startup = 2380.0  # within (2365, 2396); also within RPU's own body span
    # Approach: a vertical stub from the pad's own bottom edge (y0), dropping
    # further down past startup's own bbox bottom (-1.2) before the riser.
    # This column crosses RPU's own unmodelled GatPoly resistor body (see
    # STARTUP_RPU_BODY_Y) -- the riser below bridges over it on Metal1.
    route_v(b, L_METAL1, x_startup, startup_pad[1], -3.0, width=TRUNK_W)

    _route_bus_net(
        b,
        "vss",
        Y_BUS_VSS,
        [
            (x_core, 0.0, None),
            (x_amp, y_amp, None),
            (x_startup, -3.0, STARTUP_RPU_BODY_Y),
        ],
        port_x=X_PORT_VSS,
    )


def _route_fb(b: TopBuilder) -> None:
    """``fb``: core, amp.out, startup -- internal net, no top-level port."""
    core_pad = CORE["fb"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 60.0
    x_core = -15.0
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["out"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 0.77
    x_amp = 855.0  # within the core-amp gap, distinct from vss's own 832/858
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["fb"]
    y_startup = (startup_pad[1] + startup_pad[3]) / 2  # 6.0
    x_startup = 2405.0  # in the open corridor right of startup's own right edge
    route_h(b, L_METAL1, y_startup, startup_pad[2], x_startup, width=TRUNK_W)

    _route_bus_net(
        b,
        "fb",
        Y_BUS_FB,
        [(x_core, y_core, None), (x_amp, y_amp, None), (x_startup, y_startup, None)],
    )


def _route_sns1(b: TopBuilder) -> None:
    """``sns1``: core, amp.in_n, startup -- internal net, no top-level port."""
    core_pad = CORE["sns1"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 50.0
    x_core = -20.0  # distinct column from fb's own -15
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["in_n"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 20.0
    x_amp = 960.0  # in the amp-startup gap (944.5 .. 975.0)
    route_h(b, L_METAL1, y_amp, amp_pad[2], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["sns1"]
    x_startup = (startup_pad[0] + startup_pad[2]) / 2  # 2363.0 -- the leaf
    # cell's own sns1 poly tab sits at this exact x (X_SNS1_TAB=1388 local),
    # so this riser lands directly on top of that cell's own existing sns1
    # tap -- same net, intentional, not a coincidence. This column is also
    # within RPU's own body span (see STARTUP_RPU_BODY_Y) -- bridged below.
    route_v(b, L_METAL1, x_startup, startup_pad[1], -3.0, width=TRUNK_W)

    _route_bus_net(
        b,
        "sns1",
        Y_BUS_SNS1,
        [
            (x_core, y_core, None),
            (x_amp, y_amp, None),
            (x_startup, -3.0, STARTUP_RPU_BODY_Y),
        ],
    )


def _route_sns2(b: TopBuilder) -> None:
    """``sns2``: core + amp only. Routed directly through the core-amp gap
    -- no bus needed for a 2-cell net. Uses x=845 (distinct from vss's own
    832/858 and fb's own 855 in the same gap) and y=50/20 (distinct from
    vref's own y=40 turn below), entirely on Metal1."""
    core_pad = CORE["sns2"]
    amp_pad = AMP["in_p"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 50.0
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 20.0
    x_mid = 845.0

    route_h(b, L_METAL1, y_core, core_pad[2], x_mid, width=TRUNK_W)
    route_v(b, L_METAL1, x_mid, y_core, y_amp, width=TRUNK_W)
    route_h(b, L_METAL1, y_amp, x_mid, amp_pad[0], width=TRUNK_W)


def _route_vref(b: TopBuilder) -> None:
    """``vref``: core only, brought out to bandgap_top's own external port.

    Routed entirely on Metal1: down from core's own pad (x=838, distinct
    from sns2's own x=845) to y=-10 -- a height below every leaf cell's own
    bounding-box bottom (core's own -3.21 is the lowest) *and* below every
    other net's own riser column range drawn above (vdd/vss's risers start
    at y=0 or higher; sns1/fb's core-side columns don't reach below their
    own pad heights either) -- then left, at that same safe height, all the
    way past every cell to the external port. Verified clear of every other
    drawn shape at y=-10, not merely asserted: see this module's own
    docstring for the specific columns checked."""
    core_pad = CORE["vref"]
    y_pad = (core_pad[1] + core_pad[3]) / 2  # 40.0
    x_drop = 838.0
    y_safe = -10.0

    route_h(b, L_METAL1, y_pad, core_pad[2], x_drop, width=TRUNK_W)
    route_v(b, L_METAL1, x_drop, y_pad, y_safe, width=TRUNK_W)
    route_h(b, L_METAL1, y_safe, x_drop, X_PORT_VREF, width=TRUNK_W)
    b.net_label("vref", X_PORT_VREF + 0.25, y_safe)
    # A small square pad at the port itself, matching every leaf cell's own
    # boundary_port() pad footprint (0.5 um square) for visual consistency.
    half = 0.25
    b.box(L_METAL1, X_PORT_VREF - half, y_safe - half, X_PORT_VREF + half, y_safe + half)


def _route(b: TopBuilder) -> None:
    _route_vdd(b)
    _route_vss(b)
    _route_fb(b)
    _route_sns1(b)
    _route_sns2(b)
    _route_vref(b)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
