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

The three leaf cells are placed in **two horizontal rows** (translation
only, no mirroring) with every inter-cell bus living in the routing channel
between them::

    row B (top, y = 78.8 .. 132.3)
        amp     (-7, 78.76)-(77, 121.7)
          | 22.8 um gap |
        startup (99.8, 78.8)-(184.4, 132.3)

    routing channel (y = 65 .. 75) -- five Metal1 buses, no leaf geometry

    row A (bottom, y = -3.21 .. 61.7)
        core    (-10, -3.21)-(220.07, 61.7)

**Issue #173 re-packed a single left-to-right row** (``core`` | 30 um gap |
``amp`` | 30 um gap | ``startup``, all at ``dy=0``) after folding the two
long poly-resistor bars that used to set ``core``'s and ``startup``'s
widths. **Issue #177 folded that row in half.** The single row's height was
set by its tallest leaf (``core``, 64.9 um) while the two shorter ones left
their share of it empty, and its four buses spanned the whole 502 um width;
measured in ``measurements/2026-09-resistor-fold/`` §3, those two mechanisms
were 51.6% of the assembled footprint. Two rows address both: ~248 x ~136 um
rather than ~503 x ~95 um, with the bus stack tightened from a 6 um to a
2.5 um pitch (1.5 um between 1 um-tall bars, >8x ``metal1.space.1``'s
0.18 um floor) and shortened from 502 to at most 248 um.

Which leaf went where follows each leaf's own **pad band**, not convenience:
``core``'s pads face up or sideways out of its own edges (``vdd`` on its top
edge, ``fb``/``sns1`` on its left, ``vss``/``sns2``/``vref`` on its right),
so it wants a channel *above* it, while ``amp``'s and ``startup``'s pads sit
at or near their own bottom edges (``amp``'s ``vss``/``out``; all four of
``startup``'s, at local y <= 8 of a 53.5 um-tall cell), so they want a
channel *below* them. One channel between a ``core`` row and an
``amp``+``startup`` row satisfies all three at once.

The routing invariant, re-derived (issue #177)
----------------------------------------------

Through issue #173 the routing below rested on the three cells occupying
**disjoint x-ranges**, so a vertical route drawn within one cell's own
x-span could only ever collide with that same cell's own geometry. Two rows
break that premise -- ``core``'s x-span now covers both of the others' --
so it is replaced, not merely deleted, by a two-dimensional form of the same
argument plus one new global rule:

1. **Row disjointness.** The two rows occupy disjoint y-bands separated by
   the routing channel, which holds no leaf geometry at any x. Cells
   *within* a row still occupy disjoint x-ranges (``amp`` and ``startup``
   are 22.8 um apart).
2. **Risers never leave their own row.** Every riser runs between its own
   cell's ``boundary_port()`` approach stub and its own net's bus in the
   channel -- upward from row A, downward from row B -- and stops there. Its
   y-extent therefore lies entirely within its own cell's row band plus the
   channel, so by (1) the only *leaf* geometry it can meet is its own
   cell's: exactly what the old disjoint-x invariant bought, re-derived on
   (row, x) rather than x alone.
3. **Globally distinct riser columns.** What (1) and (2) do *not* give for
   free: risers from *both* rows now coexist inside the channel, so two
   different nets' risers may no longer share a column anywhere in the
   assembly, not merely within one cell. Under the old invariant that was
   automatic. It is now a real obligation, so it is **checked rather than
   asserted** -- :func:`_assert_column_pitch` fails the generator if two
   different nets' riser columns come within :data:`MIN_COLUMN_PITCH_UM`.

Two corollaries this module holds itself to, both consequences of (2) on a
single-metal deck:

* **Every riser starts outside its own cell's bounding box.** Each net's
  approach stub carries its ``Metal1`` pad clear of the leaf first (out of
  an edge, or -- for the pads that face *into* their own row rather than the
  channel -- along the top of the cell and off its side), and only then does
  :func:`poly_tab` drop to ``GatPoly``. That keeps every ``Cont`` this
  module places over field, never over a leaf's own ``Activ``/``GatPoly``,
  which is the same rule :func:`poly_tab`'s own docstring states.
* **A riser may cross any number of buses but no horizontal run of its own
  row.** Buses and approach stubs are ``Metal1``; risers are ``GatPoly``;
  the two are joined only through ``Cont``. That is what makes bus *order*
  irrelevant (see below) and it is unchanged by the re-placement -- it is
  the layer-based half of the argument, orthogonal to (1)-(3).

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

* **one straight horizontal ``Metal1`` bus**, in the inter-row channel
  (``Y_BUS_VDD=65`` .. ``Y_BUS_SNS2=75``, 2.8 um clear of row A's own top
  edge below and 3.3 um clear of row B's own bottom edge above);
* **one ``GatPoly`` riser per contributing cell**, each at its own
  dedicated column, transitioning ``Metal1`` -> ``GatPoly`` -> ``Metal1``
  via :func:`poly_tab` at both ends (the same primitive every leaf cell's
  own ``poly_underpass``/gate-tap connections already use) -- so a riser
  for one net passes *underneath* every other net's ``Metal1`` bus it
  needs to cross (different conductors, joined only through ``Cont``,
  exactly as already verified for each leaf cell's own internal
  crossings) without touching it.

Since every riser is a plain vertical line at its own column, the only
remaining thing to avoid is two *different* nets' risers sharing a column.
Through issue #173 that was trivially satisfied, because every column came
from a cell's own natural pad position and the three cells were at disjoint
x. Two rows removed that guarantee (invariant rule 3 above), so it is now
machine-checked: :func:`_assert_column_pitch`.

``sns2`` gains a bus of its own (issue #177): ``core``'s ``sns2`` pad faces
right and ``amp``'s ``in_p`` faces left, and with ``amp`` no longer sitting
to ``core``'s right the direct ``Metal1`` dog-leg between them that #81 used
would have to cross the whole channel on the one modelled metal. A fifth bus
is the same answer the other four already use.

``vref`` (``core`` + this assembly's own external port) still needs no bus:
one ``GatPoly`` riser carries it from ``core``'s own right-edge pad up to a
port pad in the channel, passing under the ``sns2`` bus on the way (see
:func:`_route_vref`). Issue #173's ``vref`` route ran the other way -- down
to ``y=-10``, below every cell, then 250 um left to a port at ``x=-50`` --
which cost the assembly ~7 um of height and ~40 um of width for one
single-terminal net; the ``vdd``/``vss`` ports likewise no longer extend
their own buses leftward to ``x=-40``/``-45`` but are labelled on a real,
physically-connected point of the bus they already have.

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
#
# Issue #177 turned #173's single row (0 / 257.5 / 365, all at dy=0) into two.
# `core` stays at the origin as row A; `amp` and `startup` move up by
# `ROW_B_DY` to form row B above the routing channel.
#
# `ROW_B_DY` is derived, not guessed. Row B's two cells reach the channel
# through `Metal1` stubs that drop `ROW_B_APPROACH_DROP_UM` below their own
# bounding boxes before transitioning to `GatPoly`, so the binding clearance
# is between the `poly_tab` pad those stubs end on (a TAB_PAD_UM square, i.e.
# 0.25 um below the stub's end) and the topmost bus bar's own upper edge
# (`Y_BUS_SNS2 + BUS_HEIGHT / 2` = 75.5): ROW_B_DY = 80 leaves 1.25 um, ~7x
# `metal1.space.1`'s 0.18 um floor, and 3.26 um of empty channel to row B's
# own lowest leaf geometry (`amp`'s bbox bottom, local -1.24).
#
# STARTUP_DX leaves a 22.8 um gap to `amp`'s right edge -- wide enough for
# the three riser columns that land in it (`amp`'s own `vdd` and `sns1`
# escapes at 80 and 85, `startup`'s `vdd` escape at 95) at a 5 um pitch,
# with >2.8 um to either cell's own bounding box. Nothing else is routed
# through it: under the two-row invariant every riser drops into the channel
# rather than travelling between same-row neighbours.
# --------------------------------------------------------------------------- #
ROW_B_DY = 80.0
CORE_DX, CORE_DY = 0.0, 0.0
AMP_DX, AMP_DY = 0.0, ROW_B_DY
STARTUP_DX, STARTUP_DY = 100.0, ROW_B_DY

#: How far below its own bounding box a row-B cell's ``Metal1`` approach stub
#: drops before :func:`poly_tab` transitions it to ``GatPoly`` -- see the
#: "Every riser starts outside its own cell's bounding box" corollary in this
#: module's docstring. 3 um clears ``amp``'s own bbox bottom (local -1.24)
#: and ``startup``'s (local -1.2) with >1.7 um to spare.
ROW_B_APPROACH_DROP_UM = 3.0

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

# Bus heights (Metal1, horizontal) -- the routing channel between the two
# rows (issue #177). Bus *order* is irrelevant to correctness (see the
# docstring: buses are Metal1, risers are GatPoly, joined only through
# Cont), so this is the #173 order with `sns2` appended.
#
# The floor is set by row A: `core`'s own bounding box tops out at 61.7 and
# `_route_vdd`'s approach stub carries a poly_tab pad to 63.25, so a 1 um
# bar centred at 65 clears the nearer of those by 1.25 um. The 2.5 um pitch
# (issue #177 tightened it from #173's 6 um) leaves 1.5 um between adjacent
# bars, >8x `metal1.space.1`'s 0.18 um floor; the whole five-bus stack is
# 11 um tall where the four-bus one was 19.
Y_BUS_VDD = 65.0
Y_BUS_VSS = 67.5
Y_BUS_FB = 70.0
Y_BUS_SNS1 = 72.5
Y_BUS_SNS2 = 75.0
BUS_HEIGHT = 1.0

#: bandgap_top's own external port columns (vdd/vss/vref -- the only three
#: nets `design/sg13cmos5l/netlist/bandgap_top.spice`'s own `.subckt
#: bandgap_top vdd vss vref` line declares).
#:
#: Issue #177 moved all three *onto geometry the assembly already draws*
#: rather than out past its own left edge. `vdd`/`vss` are labelled on their
#: own bus at a column that bus already spans (a real, physically-connected
#: point on the net, and the same convention the SG13G2 `bandgap_top`
#: already uses), so neither bus is extended by a single micron to carry a
#: port; through #173 they ran out to x=-40/-45 and `vref` to x=-50, which
#: cost ~40 um of assembly width for three labels. `vref`'s port is a
#: `poly_tab` pad at the top of its own riser -- see :func:`_route_vref`.
X_PORT_VDD = 90.0
X_PORT_VSS = 165.0
X_PORT_VREF = 225.0
Y_PORT_VREF = 78.0

#: Minimum centre-to-centre spacing between two **different** nets' riser
#: columns anywhere in the assembly -- the machine-checked half of the
#: two-row routing invariant (docstring rule 3), enforced by
#: :func:`_assert_column_pitch`. Risers are ``TRUNK_W`` = 0.30 um wide, so
#: 2.0 um leaves 1.7 um of edge-to-edge clearance, ~9x this deck's
#: `gatpoly.space.1` floor; the value is a floorplan-review threshold, not
#: the DRC floor itself (`klt drc` still checks the real one).
MIN_COLUMN_PITCH_UM = 2.0


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
    this riser's column (see :data:`STARTUP_RPU_BODY_X_LOCAL`). No caller
    needs one since issue #173 folded that body; it is kept because the
    hazard it answers is a property of the deck, not of one placement. A
    plain ``Metal1``
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
    columns, and (if ``port_x`` is given) label it there -- bandgap_top's own
    external port for this net.

    ``port_x`` still widens the bus if it falls outside every riser's own
    column, but since issue #177 both callers that pass one pass a column the
    bus already spans, so no bus is extended to carry a label (see
    :data:`X_PORT_VDD`).

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


def _assert_column_pitch(columns: list[tuple[str, float]]) -> None:
    """Fail the generator if two **different** nets' riser columns come
    within :data:`MIN_COLUMN_PITCH_UM` of each other.

    This is the machine-checked half of the two-row routing invariant (rule
    3 in this module's own docstring). Under the pre-#177 single-row
    floorplan it was structurally impossible for two cells' risers to share
    a column -- the three cells occupied disjoint x-ranges, so each cell's
    natural pad positions were automatically disjoint from every other
    cell's. With two rows every riser passes through the *same* routing
    channel to reach its bus, so a collision between cells is now possible,
    and it would be a real short that `klt drc` cannot see (two overlapping
    same-layer GatPoly shapes merge into one clean polygon, violating no
    width or space rule).

    Same-net entries are exempt: two risers of one net *may* share a column
    -- they would simply merge, which is what their shared bus does anyway.
    """
    for i, (net_a, x_a) in enumerate(columns):
        for net_b, x_b in columns[i + 1 :]:
            if net_a == net_b:
                continue
            if abs(x_a - x_b) < MIN_COLUMN_PITCH_UM:
                raise AssertionError(
                    f"riser columns for nets {net_a!r} (x={x_a}) and {net_b!r} "
                    f"(x={x_b}) are {abs(x_a - x_b)}um apart, under this "
                    f"module's own {MIN_COLUMN_PITCH_UM}um floor -- two "
                    "different nets' GatPoly risers now share the routing "
                    "channel and would merge (see _assert_column_pitch)"
                )


def _row_b_drop(b: Builder, x: float, y_pad_edge: float) -> float:
    """Carry a row-B pad's own ``Metal1`` straight down past that cell's own
    bounding box, returning the y the caller's riser starts from.

    Used for the two row-B pads that already face the channel (``amp``'s
    ``vss``, ``startup``'s ``vss``/``sns1``): their columns sit *inside*
    their own cell's footprint, so :func:`poly_tab` must not be placed at
    the pad itself -- its ``Cont`` would land on that cell's own ``Activ``.
    Dropping ``ROW_B_APPROACH_DROP_UM`` below the bbox first puts the
    transition over field, per this module's docstring's "every riser starts
    outside its own cell's bounding box" corollary."""
    y_drop = ROW_B_DY - ROW_B_APPROACH_DROP_UM
    route_v(b, L_METAL1, x, y_pad_edge, y_drop, width=TRUNK_W)
    return y_drop


def _route_vdd(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``vdd``: core, amp, startup, and bandgap_top's own external port.

    ``core`` (row A) rises out of its own top-edge vdd pad; ``amp`` and
    ``startup`` (row B) drop into the channel. Neither row-B pad faces the
    channel -- ``amp``'s vdd pad is on that cell's *top* edge and
    ``startup``'s is on its left -- so each first travels along ``Metal1``
    to the nearest column outside its own bounding box, in the 22.8 um
    amp-startup gap, and drops there."""
    core_pad = CORE["vdd"]
    x_core = 90.0  # within (-5, 185); clear of M1/M2/M3's own centres (0/45/180)
    # 63.0 is above `core`'s own bbox top (61.7), so the poly_tab that ends
    # this stub sits over field -- and 1.25 um under the vdd bar's own
    # bottom edge (64.5).
    route_v(b, L_METAL1, x_core, core_pad[3], 63.0, width=TRUNK_W)

    # amp: its vdd pad is the *top* rail of the cell (local y in
    # [40.64, 40.9]), so the leg runs right off the pad's own end (local
    # x=75) to a column 3 um past amp's own bbox right edge (77) and drops
    # the full height of the cell there. Verified against the leaf GDS
    # rather than assumed: at local x in [75, 80] and y in [40, 41.5] that
    # cell owns nothing but the pad itself (its GatPoly stops at 75.18,
    # below y=40.5), so the stub extends its own net and meets no other.
    amp_pad = AMP["vdd"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2
    x_amp = AMP_DX + 80.0
    route_h(b, L_METAL1, y_amp, amp_pad[2], x_amp, width=TRUNK_W)

    # startup: unchanged from #173 -- RPU's own end-A terminal is the folded
    # block's bottom-left corner and a poly riser on that column would merge
    # into RPU's own GatPoly body (see STARTUP_RPU_BODY_X_LOCAL), so the leg
    # escapes sideways on Metal1 into the amp-startup gap first. Only the
    # direction it then travels changed (down, not up).
    startup_pad = STARTUP["vdd"]
    y_startup = (startup_pad[1] + startup_pad[3]) / 2  # local 7.75, mid of the pad
    x_startup = STARTUP_DX - 5.0  # in the amp-startup gap, left of the block
    route_h(b, L_METAL1, y_startup, startup_pad[0], x_startup, width=TRUNK_W)

    columns += [("vdd", x_core), ("vdd", x_amp), ("vdd", x_startup)]
    _route_bus_net(
        b,
        "vdd",
        Y_BUS_VDD,
        [(x_core, 63.0, None), (x_amp, y_amp, None), (x_startup, y_startup, None)],
        port_x=X_PORT_VDD,
    )


def _route_vss(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``vss``: core, amp, startup, and bandgap_top's own external port.

    ``core``'s own vss pad (Q3's collector ring) sits at that cell's own
    bottom-right corner and reaches its riser through the empty corridor
    right of the cell; ``amp``'s and ``startup``'s both sit on their own
    cells' bottom edges, already facing the channel, and only need
    :func:`_row_b_drop` to get their transition over field."""
    core_pad = CORE["vss"]
    x_core = 222.0  # 1.78 um right of core's own bbox right edge (220.07)
    route_h(b, L_METAL1, 0.0, core_pad[2], x_core, width=TRUNK_W)

    amp_pad = AMP["vss"]
    x_amp = AMP_DX + 30.0  # within amp's own vss pad (local x in [-5, 70])
    y_amp = _row_b_drop(b, x_amp, amp_pad[1])

    startup_pad = STARTUP["vss"]
    # Local x=65, between MSENSE (50..60) and MKFB (77.5..82.5) and -- since
    # #173 folded it -- entirely clear of RPU's own GatPoly body
    # (STARTUP_RPU_BODY_X_LOCAL), so no Metal1 bridge is needed.
    x_startup = STARTUP_DX + 65.0
    y_startup = _row_b_drop(b, x_startup, startup_pad[1])

    columns += [("vss", x_core), ("vss", x_amp), ("vss", x_startup)]
    _route_bus_net(
        b,
        "vss",
        Y_BUS_VSS,
        [
            (x_core, 0.0, None),
            (x_amp, y_amp, None),
            (x_startup, y_startup, None),
        ],
        port_x=X_PORT_VSS,
    )


def _route_fb(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``fb``: core, amp.out, startup -- internal net, no top-level port.

    All three pads face sideways out of their own cells (``core``'s and
    ``amp``'s to the left, ``startup``'s to the right), so each leg is a
    short Metal1 run off its own cell's edge followed by a riser."""
    core_pad = CORE["fb"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 60.0
    x_core = -15.0
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["out"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # local 0.77
    x_amp = AMP_DX - 9.0  # 2 um past amp's own bbox left edge (-7)
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["fb"]
    y_startup = (startup_pad[1] + startup_pad[3]) / 2  # local 6.0
    x_startup = STARTUP_DX + 87.0  # open corridor right of startup's right edge
    route_h(b, L_METAL1, y_startup, startup_pad[2], x_startup, width=TRUNK_W)

    columns += [("fb", x_core), ("fb", x_amp), ("fb", x_startup)]
    _route_bus_net(
        b,
        "fb",
        Y_BUS_FB,
        [(x_core, y_core, None), (x_amp, y_amp, None), (x_startup, y_startup, None)],
    )


def _route_sns1(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``sns1``: core, amp.in_n, startup -- internal net, no top-level port."""
    core_pad = CORE["sns1"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 50.0
    x_core = -18.0  # distinct column from fb's own -15
    route_h(b, L_METAL1, y_core, core_pad[0], x_core, width=TRUNK_W)

    amp_pad = AMP["in_n"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # local 20.0
    x_amp = AMP_DX + 85.0  # in the amp-startup gap, right of amp's own vdd escape
    route_h(b, L_METAL1, y_amp, amp_pad[2], x_amp, width=TRUNK_W)

    startup_pad = STARTUP["sns1"]
    x_startup = (startup_pad[0] + startup_pad[2]) / 2  # local 48 -- the leaf
    # cell's own sns1 poly tab sits at this exact x (X_SNS1_TAB=48 local), so
    # this riser lands directly under that cell's own existing sns1 tap --
    # same net, intentional, not a coincidence. Issue #173: this column used
    # to fall *inside* RPU's own 1.4 mm GatPoly body and needed a Metal1
    # bridge across it; the folded body ends at local x=44.97, so the column
    # is clear and the bridge is gone.
    y_startup = _row_b_drop(b, x_startup, startup_pad[1])

    columns += [("sns1", x_core), ("sns1", x_amp), ("sns1", x_startup)]
    _route_bus_net(
        b,
        "sns1",
        Y_BUS_SNS1,
        [
            (x_core, y_core, None),
            (x_amp, y_amp, None),
            (x_startup, y_startup, None),
        ],
    )


def _route_sns2(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``sns2``: core + amp only -- given its own bus by issue #177.

    Through #173 this was a direct three-segment ``Metal1`` dog-leg through
    the core-amp gap, which worked because ``amp`` sat immediately right of
    ``core`` at the same height. Two rows put ``amp``'s own ``in_p`` pad
    (that cell's left edge) and ``core``'s own ``sns2`` pad (this cell's
    right edge) on opposite sides of the assembly *and* in different rows, so
    a direct route would have to cross the whole channel on the one modelled
    metal -- i.e. cross four other nets' buses with nothing to cross *on*.
    A fifth bus and two risers is the same answer the other four nets use,
    and it is the only one that keeps invariant rule 2 intact for this net."""
    core_pad = CORE["sns2"]
    y_core = (core_pad[1] + core_pad[3]) / 2  # 57.0
    x_core = 229.0  # right corridor; distinct from vss's 222 and vref's 225
    route_h(b, L_METAL1, y_core, core_pad[2], x_core, width=TRUNK_W)

    amp_pad = AMP["in_p"]
    y_amp = (amp_pad[1] + amp_pad[3]) / 2  # local 20.0
    x_amp = AMP_DX - 12.0  # left corridor; distinct from fb's -9 / -15
    route_h(b, L_METAL1, y_amp, amp_pad[0], x_amp, width=TRUNK_W)

    columns += [("sns2", x_core), ("sns2", x_amp)]
    _route_bus_net(
        b,
        "sns2",
        Y_BUS_SNS2,
        [(x_core, y_core, None), (x_amp, y_amp, None)],
    )


def _route_vref(b: Builder, columns: list[tuple[str, float]]) -> None:
    """``vref``: core only, brought out to bandgap_top's own external port.

    ``core``'s own vref pad faces right (local y=40), so the leg runs out
    into the right corridor and rises on ``GatPoly`` to a port pad in the
    channel. The riser passes under two ``Metal1`` runs on the way -- this
    module's own ``sns2`` approach at y=57 and the ``sns2`` bus at y=75 --
    both safe crossings for the same reason every other riser's are
    (different conductors, joined only through ``Cont``). Nothing else
    reaches x=225: the ``vss`` bus stops at 222.5 and the ``sns2`` bus is
    the only bar that spans this far right.

    Issue #177 replaced #173's route, which dropped to y=-10 (below every
    cell) and ran ~275 um left to a port at x=-50 -- ~7 um of assembly
    height and ~40 um of width spent on one single-terminal net's label."""
    core_pad = CORE["vref"]
    y_pad = (core_pad[1] + core_pad[3]) / 2  # 40.0
    x_drop = X_PORT_VREF

    route_h(b, L_METAL1, y_pad, core_pad[2], x_drop, width=TRUNK_W)
    columns.append(("vref", x_drop))
    _riser(b, x_drop, y_pad, Y_PORT_VREF)
    b.net_label("vref", x_drop, Y_PORT_VREF)


def _route(b: Builder) -> None:
    """Wire every schematic net, then check the one part of the two-row
    routing invariant that is not structural -- see this module's docstring
    ("The routing invariant, re-derived") and :func:`_assert_column_pitch`."""
    columns: list[tuple[str, float]] = []
    _route_vdd(b, columns)
    _route_vss(b, columns)
    _route_fb(b, columns)
    _route_sns1(b, columns)
    _route_sns2(b, columns)
    _route_vref(b, columns)
    _assert_column_pitch(columns)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
