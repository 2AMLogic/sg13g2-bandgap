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
row -- ``bandgap_core`` (~230 um wide) leftmost, ``bandgap_amp`` (~84 um)
in the middle, ``bandgap_startup`` (~85 um) rightmost -- separated by
30 um gaps that are otherwise **empty at every height** (no cell's own
bounding box reaches into a neighbour's gap at any y), the same property
every leaf cell's own single-metal floorplan already exploits internally::

    core (-10, -3.21)-(220.07, 61.7)
      | 30 um gap (220.07 .. 250.5) |
    amp (250.5, -1.24)-(334.5, 41.7)
      | 30 um gap (334.5 .. 364.8) |
    startup (364.8, -1.2)-(449.4, 52.3)

**Issue #173 re-packed this row.** ``core`` and ``startup`` used to be 840
and 1425 um wide because each contained one straight poly-resistor bar
(647 um and 1411.3 um) whose length alone set the cell's width; folding
those bars into serpentines leaves the row a quarter as wide at the same
30 um gaps. The gaps themselves are unchanged -- they are routing
corridors, not slack. The bus stack above the row was also brought down
from 75..120 to 66..84, since the tallest leaf (``core``, 61.7 um) did not
grow: pre-fold the stack sat 13 um clear of it purely by convention, and
that clearance is now 4 um with 6 um between buses, which is >30x
``metal1.space.1``'s 0.18 um floor.

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
AMP_DX, AMP_DY = 257.5, 0.0
STARTUP_DX, STARTUP_DY = 365.0, 0.0

# Each leaf's own boundary-port map (issue #76), in **its own local
# coordinates** -- reproduced here from that cell's own generate.py `build()`
# printout rather than re-run at generate time, since this module instances
# the already-committed GDS, not the leaf's Python `build()` function.
# Issue #173: ``core``'s ``vss``/``sns2``/``vref`` pads moved with that
# cell's own right edge (830.5 -> 220.0) when its 647 um ``R1`` bar was
# folded, and ``sns2``'s port height rose 50 -> 57 to clear the folded R1
# block (see that cell's own ``Y_SNS2_PORT`` comment). ``vdd``/``fb``/
# ``sns1`` are unchanged -- they sit on the mirror row and the cell's left
# edge, neither of which the fold touched.
_CORE_PORTS_LOCAL = {
    "vdd": (-5.0, 60.64, 185.0, 60.9),
    "vss": (214.39, -2.99, 219.85, 2.99),
    "fb": (-8.38, 59.9, -7.98, 60.1),
    "sns1": (-10.0, 49.75, -9.5, 50.25),
    "sns2": (219.5, 56.75, 220.0, 57.25),
    "vref": (219.5, 39.75, 220.0, 40.25),
}
_AMP_PORTS_LOCAL = {
    "vdd": (15.0, 40.64, 75.0, 40.9),
    "vss": (-5.0, -0.9, 70.0, -0.64),
    "out": (-5.0, 0.64, 5.0, 0.9),
    "in_p": (-7.0, 19.75, -6.5, 20.25),
    "in_n": (76.5, 19.75, 77.0, 20.25),
}
# Issue #173: every ``startup`` port moved. ``vdd`` is ``RPU``'s own end-A
# terminal, which folding turned from the left end of a 1.4 mm bar into the
# bottom-left terminal of a 45 x 44 um block; the other three moved with the
# MSENSE/MKFB cluster, which shifted 1340 um left to sit just past the
# folded block's right edge instead of under the old bar's far end.
_STARTUP_PORTS_LOCAL = {
    "vdd": (-0.2, 7.5, 1.2, 8.0),
    "vss": (50.0, -0.65, 81.0, -0.39),
    "sns1": (47.75, -1.2, 48.25, -0.7),
    "fb": (83.9, 5.75, 84.4, 6.25),
}


def _shift(box: tuple[float, float, float, float], dx: float, dy: float):
    x0, y0, x1, y1 = box
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


CORE = {k: _shift(v, CORE_DX, CORE_DY) for k, v in _CORE_PORTS_LOCAL.items()}
AMP = {k: _shift(v, AMP_DX, AMP_DY) for k, v in _AMP_PORTS_LOCAL.items()}
STARTUP = {k: _shift(v, STARTUP_DX, STARTUP_DY) for k, v in _STARTUP_PORTS_LOCAL.items()}

# Bus heights (Metal1, horizontal), all comfortably above every leaf cell's
# own bounding-box top (core's own 61.7 um is the tallest of the three).
Y_BUS_VDD = 66.0
Y_BUS_VSS = 72.0
Y_BUS_FB = 78.0
Y_BUS_SNS1 = 84.0
BUS_HEIGHT = 1.0

#: bandgap_top's own external port pads (vdd/vss/vref -- the only three
#: nets `design/sg13cmos5l/netlist/bandgap_top.spice`'s own `.subckt
#: bandgap_top vdd vss vref` line declares) sit at the far left of the
#: assembly, clear of every cell and every riser column used below.
X_PORT_VDD = -40.0
X_PORT_VSS = -45.0
X_PORT_VREF = -50.0


def build() -> Builder:
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

    b = Builder(TOP_CELL, layout=layout)

    def u(value_um: float) -> int:
        return int(round(value_um / layout.dbu))

    b.cell.insert(kdb.CellInstArray(core_idx, kdb.Trans(u(CORE_DX), u(CORE_DY))))
    b.cell.insert(kdb.CellInstArray(amp_idx, kdb.Trans(u(AMP_DX), u(AMP_DY))))
    b.cell.insert(kdb.CellInstArray(startup_idx, kdb.Trans(u(STARTUP_DX), u(STARTUP_DY))))

    _route(b)
    return b


#: ``bandgap_startup``'s own ``RPU`` (a deck-unrecognised ``rhigh``
#: resistor, see ``layout/README.md`` "LVS -- ``mismatch``, fully
#: attributed", cause 2) draws its conductor *body* on ``GatPoly``, so any
#: ``GatPoly`` riser that shares a column with it merges into it -- and,
#: transitively, into every other net that body's already-documented deck-gap
#: short pulls in (``vdd``, via ``det``).
#:
#: Before issue #173 that body was one unbroken 1411.3 um bar spanning
#: local ``x=0..1411.3``, i.e. **almost the entire cell**, so both
#: ``sns1``'s and ``vss``'s natural riser columns fell inside it and each
#: needed a ``Metal1`` bridge across the ``(6.8, 9.2)`` band the bar
#: occupied. Folded, the body occupies local ``x=-0.2..44.97`` only, and
#: both of those columns (local 48.0 and 65.0) sit clear of it -- so the
#: bridges are gone rather than merely retuned. The one riser that *would*
#: now land inside the folded block is ``vdd``'s (``RPU``'s own end-A
#: terminal is the block's bottom-left corner, and a straight climb from it
#: goes up leg 0); that one escapes sideways into the amp-startup gap first
#: instead of bridging -- see :func:`_route_vdd`.
#:
#: Kept as a named constant recording the folded block's own local x-span,
#: so a future riser-column choice can be checked against it by name rather
#: than by rediscovering the same short. Verified against the regenerated
#: leaf GDS, not asserted: `klt extract` on this assembly reports the same
#: net set as the pre-fold one.
STARTUP_RPU_BODY_X_LOCAL = (-0.2, 44.972)


def _riser(
    b: Builder,
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
    b: Builder,
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


def _route_vdd(b: Builder) -> None:
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
    x_amp = AMP_DX + 42.5  # within amp's own vdd pad; clear of MTAIL/MP4/MP3
    route_v(b, L_METAL1, x_amp, amp_pad[3], 43.0, width=TRUNK_W)

    # startup: issue #173. Pre-fold this rose straight up from RPU's own
    # end-A pad, which sat at the left end of a 1 um-tall bar with nothing
    # above it. Folded, that same terminal is the *bottom-left corner of the
    # block*, and leg 0 of the serpentine runs straight up from it -- a poly
    # riser on that column would merge into RPU's own body (see
    # STARTUP_RPU_BODY_X_LOCAL). It escapes sideways on Metal1 into the
    # empty amp-startup gap first, then rises there.
    startup_pad = STARTUP["vdd"]
    y_startup = (startup_pad[1] + startup_pad[3]) / 2  # 7.75, mid of the pad
    x_startup = STARTUP_DX - 5.0  # in the amp-startup gap, left of the block
    route_h(b, L_METAL1, y_startup, startup_pad[0], x_startup, width=TRUNK_W)

    _route_bus_net(
        b,
        "vdd",
        Y_BUS_VDD,
        [(x_core, 63.0, None), (x_amp, 43.0, None), (x_startup, y_startup, None)],
        port_x=X_PORT_VDD,
    )


def _route_vss(b: Builder) -> None:
    """``vss``: core, amp, startup, and bandgap_top's own external port.

    ``core``'s own vss pad (Q3's collector ring) and ``amp``'s own vss pad
    (the merged NMOS source rail) both face the shared core-amp gap
    (830.5..860.5, empty at every height) -- each gets a short Metal1
    approach into that gap before rising independently (no need to meet at
    a shared point first: the bus itself is what merges them)."""
    core_pad = CORE["vss"]
    x_core = 222.0  # barely into the core-amp gap
    route_h(b, L_METAL1, 0.0, core_pad[2], x_core, width=TRUNK_W)

    amp_pad = AMP["vss"]
    x_amp = 246.0  # also within the core-amp gap, distinct column
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # -0.77, mid of amp's own vss pad
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["vss"]
    # Issue #173: local x=65, between MSENSE (50..60) and MKFB (77.5..82.5)
    # and -- unlike the pre-fold column -- entirely clear of RPU's own
    # GatPoly body (STARTUP_RPU_BODY_X_LOCAL), so no Metal1 bridge is needed.
    x_startup = STARTUP_DX + 65.0
    # Approach: a vertical stub from the pad's own bottom edge (y0), dropping
    # further down past startup's own bbox bottom (-1.2) before the riser.
    route_v(b, L_METAL1, x_startup, startup_pad[1], -3.0, width=TRUNK_W)

    _route_bus_net(
        b,
        "vss",
        Y_BUS_VSS,
        [
            (x_core, 0.0, None),
            (x_amp, y_amp, None),
            (x_startup, -3.0, None),
        ],
        port_x=X_PORT_VSS,
    )


def _route_fb(b: Builder) -> None:
    """``fb``: core, amp.out, startup -- internal net, no top-level port."""
    core_pad = CORE["fb"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 60.0
    x_core = -15.0
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["out"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 0.77
    x_amp = 240.0  # within the core-amp gap, distinct from vss's own 222/246
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["fb"]
    y_startup = (startup_pad[1] + startup_pad[3]) / 2  # 6.0
    x_startup = STARTUP_DX + 87.0  # open corridor right of startup's right edge
    route_h(b, L_METAL1, y_startup, startup_pad[2], x_startup, width=TRUNK_W)

    _route_bus_net(
        b,
        "fb",
        Y_BUS_FB,
        [(x_core, y_core, None), (x_amp, y_amp, None), (x_startup, y_startup, None)],
    )


def _route_sns1(b: Builder) -> None:
    """``sns1``: core, amp.in_n, startup -- internal net, no top-level port."""
    core_pad = CORE["sns1"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 50.0
    x_core = -20.0  # distinct column from fb's own -15
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["in_n"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 20.0
    x_amp = 350.0  # in the amp-startup gap (334.5 .. 364.8)
    route_h(b, L_METAL1, y_amp, amp_pad[2], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["sns1"]
    x_startup = (startup_pad[0] + startup_pad[2]) / 2  # 413.0 -- the leaf
    # cell's own sns1 poly tab sits at this exact x (X_SNS1_TAB=48 local),
    # so this riser lands directly on top of that cell's own existing sns1
    # tap -- same net, intentional, not a coincidence. Issue #173: this
    # column used to fall *inside* RPU's own 1.4 mm GatPoly body and needed a
    # Metal1 bridge across it; the folded body ends at local x=44.97, so the
    # column is clear and the bridge is gone.
    route_v(b, L_METAL1, x_startup, startup_pad[1], -3.0, width=TRUNK_W)

    _route_bus_net(
        b,
        "sns1",
        Y_BUS_SNS1,
        [
            (x_core, y_core, None),
            (x_amp, y_amp, None),
            (x_startup, -3.0, None),
        ],
    )


def _route_sns2(b: Builder) -> None:
    """``sns2``: core + amp only. Routed directly through the core-amp gap
    -- no bus needed for a 2-cell net. Uses x=232 (distinct from vss's own
    222/246, fb's own 240 and vref's own 226 in the same gap) and y=57/20
    (distinct from vref's own y=40 turn below), entirely on Metal1.

    Issue #173: ``y_core`` follows ``core``'s own ``sns2`` port, which rose
    from 50 to 57 when that cell's folded ``R1`` block took over the y=15..55
    band its poly underpass used to cross at y=50. ``x_mid`` must stay
    **right** of :func:`_route_vref`'s own drop column, or vref's y=40 run
    would cross this net's vertical leg."""
    core_pad = CORE["sns2"]
    amp_pad = AMP["in_p"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 50.0
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # 20.0
    x_mid = 232.0

    route_h(b, L_METAL1, y_core, core_pad[2], x_mid, width=TRUNK_W)
    route_v(b, L_METAL1, x_mid, y_core, y_amp, width=TRUNK_W)
    route_h(b, L_METAL1, y_amp, x_mid, amp_pad[0], width=TRUNK_W)


def _route_vref(b: Builder) -> None:
    """``vref``: core only, brought out to bandgap_top's own external port.

    Routed entirely on Metal1: down from core's own pad (x=226, distinct
    from -- and deliberately left of -- sns2's own x=232) to y=-10 -- a height below every leaf cell's own
    bounding-box bottom (core's own -3.21 is the lowest) *and* below every
    other net's own riser column range drawn above (vdd/vss's risers start
    at y=0 or higher; sns1/fb's core-side columns don't reach below their
    own pad heights either) -- then left, at that same safe height, all the
    way past every cell to the external port. Verified clear of every other
    drawn shape at y=-10, not merely asserted: see this module's own
    docstring for the specific columns checked."""
    core_pad = CORE["vref"]
    y_pad = (core_pad[1] + core_pad[3]) / 2  # 40.0
    x_drop = 226.0
    y_safe = -10.0

    route_h(b, L_METAL1, y_pad, core_pad[2], x_drop, width=TRUNK_W)
    route_v(b, L_METAL1, x_drop, y_pad, y_safe, width=TRUNK_W)
    route_h(b, L_METAL1, y_safe, x_drop, X_PORT_VREF, width=TRUNK_W)
    b.net_label("vref", X_PORT_VREF + 0.25, y_safe)
    # A small square pad at the port itself, matching every leaf cell's own
    # boundary_port() pad footprint (0.5 um square) for visual consistency.
    half = 0.25
    b.box(L_METAL1, X_PORT_VREF - half, y_safe - half, X_PORT_VREF + half, y_safe + half)


def _route(b: Builder) -> None:
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
