#!/usr/bin/env python3
"""Generate ``bandgap_top.gds`` -- hierarchical assembly of the three SG13G2
leaf cells (``bandgap_core``, ``bandgap_amp``, ``bandgap_startup``, issue
#169), following the same "instance the already-committed leaf GDS files,
route only the inter-cell connections" pattern
``layout/sg13cmos5l-bandgap_top/generate.py`` already established for the
SG13CMOS5L variant (issue #81) -- this module does **not** draw any device
geometry from scratch; the three leaf cells' own internal geometry is
untouched.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_top/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty (as long as the three leaf GDS files it reads are
themselves unchanged).

Connectivity, one-to-one against ``design/netlist/bandgap_top.spice``'s own
``.subckt bandgap_top vdd vss vref`` line -- verified against that file's
exact port order, not assumed::

    Xx1 vdd vss fb sns1 sns2 vref bandgap_core   (vdd vss fb sns1 sns2 vref)
    Xx2 sns2 sns1 vss fb vdd     bandgap_amp     (in_p in_n vss out vdd)
    Xx3 vdd vss sns1 fb          bandgap_startup (vdd vss sns1 fb)

``bandgap_core``'s and ``bandgap_startup``'s own subckt port names already
match the call-site net names exactly (no renaming) -- only ``bandgap_amp``'s
own port names differ from the nets they connect to at this level
(``in_p``->``sns2``, ``in_n``->``sns1``, ``out``->``fb``). So, per shared
net:

    vdd   -- core, amp, startup, and bandgap_top's own external port.
    vss   -- core, amp, startup, and bandgap_top's own external port.
    fb    -- core, amp.out, startup            (internal only -- no top port)
    sns1  -- core, amp.in_n, startup           (internal only -- no top port)
    sns2  -- core, amp.in_p                    (internal only -- no top port)
    vref  -- core only, brought out to bandgap_top's own external port.

**Two boundary-pad additions (issue #169), touching no leaf cell's own
committed GDS.** Two of the six nets above have no metal contact at all in
their *originating* leaf cell, because each is a bare, single-terminal
``GatPoly`` gate there (no metal pad needed for that cell's own, already-
verified DRC/LVS scope): ``bandgap_core``'s ``fb`` (every member is a MOS
gate, routed gate-to-gate on poly only -- see
``bandgap_core/generate.py``'s own docstring) and ``bandgap_startup``'s
``sns1`` (``MSENSE.gate`` only). Both need a real Metal1 pad here so this
module can route them from *outside* those cells. Rather than editing
``bandgap_core.gds``/``bandgap_startup.gds`` (which would touch already-
committed, already-DRC/LVS-verified artifacts, out of this issue's own
scope), this module draws one extra ``draw_gate_tab`` each, in its **own**
top cell, positioned to touch that leaf's own ``GatPoly`` gate polygon at
its known (placement-adjusted) absolute edge coordinate -- the identical
mechanism ``draw_gate_tab`` already uses at every existing call site
(extending an existing device's own gate edge), just with the "existing
gate" belonging to a placed sub-cell instance rather than a shape this
script drew itself. Every coordinate used for this (and for every other
port location referenced below) was read directly off each leaf's own
committed GDS with ``klayout.db`` (not hand-derived from the source and
trusted blind) -- see this issue's own PR description for the verification
commands. ``bandgap_amp``'s own ``in_p``/``in_n`` needed the same treatment,
but that tab was added directly in ``bandgap_amp/generate.py`` itself
(issue #169, a new cell with no prior committed geometry to disturb) rather
than worked around here.

**Floorplan.** The three leaf cells are placed side by side, left to right,
translation only (no mirroring): ``bandgap_core`` at the origin (bbox
``(-5.4,-3.1)``-``(511.5,61.4)``), ``bandgap_amp`` at ``dx=550``
(``(539.2,-1.59)``-``(755.1,32.175)``), ``bandgap_startup`` at ``dx=800``
(``(794.9,-1.34)``-``(2206.8,20.9)``) -- each gap comfortably larger than
any DRC spacing floor this deck declares (>=28 um, vs. sub-micron floors),
chosen only so neighbouring cells' bounding boxes cannot touch.

**Routing: Metal1 buses + Metal2 risers, cleanly non-crossing by
construction.** ``vdd``, ``vss``, ``fb``, and ``sns1`` each need multiple
widely-separated cells -- every one of these buses necessarily spans nearly
the cells' entire combined width, so every bus's own horizontal span
inevitably covers every *other* net's own riser column too (there is no
column ordering that avoids this once more than ~2 full-width nets are
involved). This module resolves it structurally rather than by column
ordering: **every bus is Metal1, every riser is Metal2** (transitioning
Metal1<->Metal2 via ``via1_tap`` at both ends, except where a leaf's own
pad is already Metal2 -- ``bandgap_core``'s ``vss``, extended by a plain
Metal2 box with no via needed at that end). A horizontal Metal1 line and a
vertical Metal2 line can cross anywhere with no possible short (different
layers, and no via is drawn at any point other than each riser's own two
intended ends) -- so bus height *order* is irrelevant, and the only
remaining rule is that two *different* nets' own Metal2 risers must not
share the same X column at the same cell (trivially satisfied: each
riser's X is chosen independently within its own pad's available X-range,
and this module picks distinct values for every net at every cell it
touches -- verified by inspection below, not merely assumed). ``sns2``
(core+amp only) uses the same bus+riser pattern with just two risers.
``vref`` (core only) needs no bus at all -- a single Metal2 stub straight
up from its own core-side pad to bandgap_top's own external port, labeled
there.

``in_p``/``in_n`` are internal to ``bandgap_amp`` and already wired to
``sns2``/``sns1`` by the risers above -- nothing else references
``bandgap_amp``'s own pin *names* at this level.

**This module's own inter-cell buses/risers never cross each other** -- but
each leaf cell's own *internal* routing (unmodified, already committed
before this issue) also uses Metal2 in places, and a new riser can still
merge with one of those if its column happens to fall inside that leaf's
own internal Metal2 footprint. See the ``_riser_up``/``LANDING_UM`` module
comment below (just above that function) for the specific leaf-internal
crossings this issue's own `klt extract` re-run found and how each was
fixed -- `klt drc` alone cannot catch this class of bug (see that comment).

DRC verification (``klt drc --deck sg13g2``) and net-connectivity
verification (``klt extract``, device-free net extraction -- not a
reference-comparison LVS run) are tracked in ``layout/README.md``.

**LVS**: *resolving* the LVS verdict is deferred (issue #169's own scope
boundary), but ``klt lvs`` itself was run once against this cell -- the
repo's CI evidence-format gate requires a committed ``lvs_report.json`` --
and its honest ``mismatch`` result is committed as-is. Only 5 of its 17
findings trace to the two already-known leaf-level causes; the other 11 come
from two causes new at this composed level (an un-propagated resistor
``device_bulk`` reconciliation, and reference-flatten hierarchy-prefix
net-identity conflicts), both unresolved and tracked in issue #171. See
``layout/README.md``'s ``bandgap_top`` "LVS" section for the itemised
breakdown. Post-layout PEX is deferred and was not run.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import klayout.db as kdb  # noqa: E402
from common import (  # noqa: E402
    L_METAL1,
    L_METAL2,
    Builder,
    draw_gate_tab,
    route_h,
    route_v,
    via1_tap,
)

HERE = os.path.dirname(os.path.abspath(__file__))
TOP_CELL = "bandgap_top"
OUTPUT = os.path.join(HERE, "bandgap_top.gds")

CORE_CELL = "bandgap_core"
AMP_CELL = "bandgap_amp"
STARTUP_CELL = "bandgap_startup"

CORE_GDS = os.path.join(HERE, "..", "bandgap_core", "bandgap_core.gds")
AMP_GDS = os.path.join(HERE, "..", "bandgap_amp", "bandgap_amp.gds")
STARTUP_GDS = os.path.join(HERE, "..", "bandgap_startup", "bandgap_startup.gds")

# Floorplan offsets -- translation only, left to right (see docstring).
CORE_DX, CORE_DY = 0.0, 0.0
AMP_DX, AMP_DY = 550.0, 0.0
STARTUP_DX, STARTUP_DY = 800.0, 0.0

TRUNK_W = 0.3
METAL2_W = 0.35
VIA = 0.25
#: Extra same-layer overshoot past a jog/bridge transition's own via1_tap
#: point (see `_riser_up`'s own docstring) -- must clear the via's own
#: half-width (``VIA / 2 = 0.125``) plus `metal1.enclosing.via1.1`'s 0.01um
#: floor, not just the floor alone (an earlier, too-small 0.1 value left a
#: bare 0.025um sliver of the via poking past a too-short Metal1 run,
#: caught by this issue's own `klt drc` re-run) -- 0.15 clears
#: ``VIA / 2`` with the same 0.025um margin already proven sufficient
#: elsewhere in this module (e.g. every jog's own perpendicular ``TRUNK_W``
#: vs. ``VIA`` clearance).
OVERSHOOT_UM = 0.15

# Bus heights (Metal1) -- comfortably above every leaf cell's own bounding
# box top (bandgap_core's own 61.4 um is the tallest of the three). Distinct
# per net purely for visual/manufacturing separation -- correctness does
# NOT depend on this ordering (see docstring: buses are Metal1, risers are
# Metal2, so no two nets' shapes can ever cross regardless of height order).
Y_BUS_VDD = 70.0
Y_BUS_VSS = 75.0
Y_BUS_FB = 80.0
Y_BUS_SNS1 = 85.0
Y_BUS_SNS2 = 90.0

#: Every port pad location below was read directly off each leaf's own
#: committed GDS with ``klayout.db`` (``klt layers``-style shape dump,
#: restricted by Y-band per net) -- not hand-derived from the leaf's own
#: source and trusted blind. See this module's own docstring for the two
#: pads (``core.fb``, ``startup.sns1``) that needed a new tab added here
#: rather than already existing. All boxes are in each leaf's own **local**
#: coordinates (pre-placement-shift) -- shifted by ``_shift()`` below.
_CORE_PORTS_LOCAL = {
    "vdd": (-5.0, 22.55, 134.5, 22.9),
    "vss": (-3.05, -0.75, 125.05, 0.75),
    "sns1": (-0.15, -2.6, 0.15, 21.45),
    "sns2": (40.5, 21.1, 57.5, 21.45),
    "vref": (106.0, 21.1, 134.5, 21.45),
}
# core's fb: no metal pad exists yet (bare GatPoly gate bar, see docstring)
# -- edge_x/y_center for the new draw_gate_tab call, read off the GatPoly
# bar's own known left edge (-5.1, 21.85-22.15 -> y_center=22.0).
_CORE_FB_GATE_EDGE_X = -5.1
_CORE_FB_GATE_Y_CENTER = 22.0

_AMP_PORTS_LOCAL = {
    "vdd": (75.0, 30.55, 145.0, 30.9),
    "vss": (-5.0, -0.9, 205.0, -0.55),
    "fb": (139.7, 0.9, 140.3, 29.1),  # amp's own "out" net -- see docstring
    "sns1": (50.4, 29.83, 50.8, 30.17),  # amp's own "in_n" net
    "sns2": (-10.8, 29.83, -10.4, 30.17),  # amp's own "in_p" net
}

_STARTUP_PORTS_LOCAL = {
    "vdd": (-0.5, 19.4, 0.0, 20.6),
    "vss": (-5.0, -0.6, 21.0, -0.4),
    "fb": (19.0, 0.3, 21.0, 0.65),
}
# startup's sns1: no metal pad exists yet (bare GatPoly gate, MSENSE.gate
# only) -- edge_x/y_center for the new draw_gate_tab call, read off
# MSENSE's own known gate box (-5.1..5.1, -0.25..0.25 -> y_center=0.0).
_STARTUP_SNS1_GATE_EDGE_X = -5.1
_STARTUP_SNS1_GATE_Y_CENTER = 0.0


def _shift(box: tuple[float, float, float, float], dx: float, dy: float) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = box
    return (x0 + dx, y0 + dy, x1 + dx, y1 + dy)


CORE = {k: _shift(v, CORE_DX, CORE_DY) for k, v in _CORE_PORTS_LOCAL.items()}
AMP = {k: _shift(v, AMP_DX, AMP_DY) for k, v in _AMP_PORTS_LOCAL.items()}
STARTUP = {k: _shift(v, STARTUP_DX, STARTUP_DY) for k, v in _STARTUP_PORTS_LOCAL.items()}


def build() -> Builder:
    layout = kdb.Layout()
    layout.dbu = 0.001

    # Reading each leaf GDS in turn merges their (already-identical, since
    # all three share common.py's own LAYER_NAMES) layer tables into one
    # shared set of layer indices -- same technique
    # layout/sg13cmos5l-bandgap_top/generate.py already verified for the
    # sibling PDK variant.
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

    # Two new boundary pads (issue #169) -- see this module's own docstring.
    core_fb_pad = draw_gate_tab(
        b, _CORE_FB_GATE_EDGE_X + CORE_DX, _CORE_FB_GATE_Y_CENTER + CORE_DY, "fb", side="left"
    )
    startup_sns1_pad = draw_gate_tab(
        b, _STARTUP_SNS1_GATE_EDGE_X + STARTUP_DX, _STARTUP_SNS1_GATE_Y_CENTER + STARTUP_DY, "sns1", side="left"
    )

    _route(b, core_fb_pad, startup_sns1_pad)

    return b


#: Extra square Metal1 landing pad drawn under every Via1 this module places
#: on a Metal1 pad (issue #169's own `klt drc` re-run caught this: some
#: leaf pads are thinner than VIA + 2*metal1.enclosing.via1.1's 0.01um floor
#: in their own short axis -- e.g. bandgap_startup's own vss bar is only
#: 0.2um tall, under VIA=0.25um -- so a via landed directly on the bare pad
#: pokes out on both edges. LANDING_UM comfortably clears VIA on every side
#: regardless of the target pad's own thickness; drawing it as an extra,
#: merged Metal1 box (not a replacement) is safe since it is always placed
#: fully inside/against an already-same-net pad, well clear of every other
#: net's own riser column at that cell (>=5um separation, verified by
#: inspection -- see _route()'s own per-net riser-x comments).
LANDING_UM = 0.5

#: **Leaf-internal Metal2 crossings -- a real short `klt drc` cannot catch,
#: found and fixed by this issue's own `klt extract` re-run.** This module's
#: risers are Metal2, same as this module's own inter-cell buses' claim
#: ("buses are Metal1, risers are Metal2, so no two *this-module's* nets can
#: ever cross") -- but `bandgap_core`'s own **internal**, already-committed
#: routing (issue #20, unrelated to and unmodified by this issue) ALSO uses
#: Metal2 for two of its own horizontal jogs: the ``sns2``/``cb2`` riser jog
#: at ``y~=40`` (``bandgap_core/generate.py``'s own ``_riser``, x in
#: roughly ``[-0.25, 49]`` and ``[63.5, 83]``) and the ``vref``/``cb3`` jog
#: at ``y~=60`` (``_tie_and_riser``, x in roughly ``[-0.25, 120.25]`` and
#: ``[125, 511.25]``, together spanning nearly `bandgap_core`'s *entire*
#: width). A brand-new top-level Metal2 riser climbing straight through
#: those Y-bands at a column inside either X-range physically merges with
#: that jog -- same layer, real overlap, no via required for a same-layer
#: merge -- which is exactly the kind of same-net-looking, `klt drc`-clean
#: short this issue's own test plan flagged ("a swapped sns1/sns2/fb
#: connection is a silent bug DRC won't catch"): `klt drc` never complains
#: because the result is one clean merged polygon, not two shapes placed too
#: close together. Caught here only by re-running `klt extract` (device-free
#: net extraction, not a reference-comparison LVS run -- still out of this
#: issue's own LVS scope) and finding far fewer nets than pins (`vdd`,
#: `vss`, `sns1`, `sns2`, `vref` all merged into one net; separately,
#: `bandgap_amp`'s own internal ``pn``-net jog at its ``y~=17`` Metal2 band
#: merged into the new ``fb`` riser passing through `bandgap_amp` at the
#: same column). Two independent fixes below, chosen per net:
#:
#: 1. **Route around the leaf's own busy Y-band entirely** (``jog_to``,
#:    used for `bandgap_core`'s own ``vdd``/``vss``/``sns1``) -- a short,
#:    same-Y jog (on the pad's own layer) from the pad's own column out to
#:    a column left of `bandgap_core`'s own bounding box (``x < -5.4``,
#:    verified empty at every height by construction -- no leaf geometry
#:    exists there at all), then a single uninterrupted Metal2 climb with
#:    nothing left to cross.
#: 2. **Bridge through the busy Y-band on Metal1** (``bridges``, used for
#:    `bandgap_core`'s own ``sns2``, whose own pad column (``x=49``) cannot
#:    move without leaving its own pad's X-range) -- Metal2 up to just below
#:    the busy band, a short Metal1 detour across it (verified clear: this
#:    deck's own Metal1 there is only two small resistor end-pads, at
#:    ``x<=0`` and ``x>=82.7``, both well clear of every bridge column used
#:    below), Metal2 again above it.
#:
#: `bandgap_amp`'s own ``fb`` (``out``-net) riser uses a third fix: since
#: `bandgap_amp` already draws a real Metal1 conductor (its own ``out``
#: trunk) spanning the *entire* Y-range this riser needs to cross, landing
#: the Metal1->Metal2 transition higher up that same, already-same-net
#: trunk (``y=25``, clear of every one of `bandgap_amp`'s own Metal2 jogs,
#: the highest of which sits at ``y~=17``) reaches the same electrical point
#: with nothing left to cross at all. `bandgap_amp`'s own ``vss`` riser
#: needed only a column change (``x=547``, clear of every one of
#: `bandgap_amp`'s own four Metal2 jogs' combined ``x`` span,
#: ``[550, 750]``) -- see ``_route``'s own per-net comments for the mapping.
#:
#: Verified, not just reasoned through: after this fix, `klt extract`
#: (`layout/bandgap_top/bandgap_top.gds`) reports exactly six nets, one per
#: `bandgap_top`'s own external pin (``vdd``, ``vss``, ``fb``, ``sns1``,
#: ``sns2``, ``vref``), with no unexpected merges -- see this issue's own PR
#: description for the exact command/output.
def _riser_up(
    b: Builder,
    x: float,
    pad: tuple[float, float, float, float],
    bus_y: float,
    pad_layer=L_METAL1,
    jog_to: float | None = None,
    bridges: tuple[tuple[float, float], ...] = (),
) -> None:
    """One Metal2 riser from ``x`` (within ``pad``'s own X-range) up to
    ``bus_y`` -- a Metal1<->Metal2 transition at the bottom (via ``via1_tap``,
    landing inside a reinforced ``LANDING_UM``-square Metal1 pad merged onto
    ``pad``) unless ``pad_layer`` is already ``L_METAL2`` (``bandgap_core``'s
    own ``vss`` -- see this module's own docstring), in which case the riser
    is a plain Metal2 box merged directly onto ``pad``, no via needed.

    ``jog_to``, when given, first jogs sideways (on ``pad``'s own layer, a
    same-layer extension -- no via needed for the jog itself) from ``x`` to
    a column clear of the originating leaf's own internal Metal2 routing,
    before rising -- see the ``LANDING_UM`` module comment above ("Avoiding
    leaf-internal Metal2 crossings").

    ``bridges``, when given, is a sequence of ascending, non-overlapping
    ``(lo, hi)`` Y-windows (each within ``[y_land, bus_y]``) where the riser
    detours onto Metal1 instead of Metal2 -- a safe way to duck under/over
    a leaf's own internal Metal2 shape occupying that exact column at that
    height, transitioning back to Metal2 immediately above.

    Every transition via1_tap below is landed ``OVERSHOOT_UM`` inside its
    own same-layer run's far end (not exactly at that run's own bare
    endpoint) -- a via placed flush with a run's endpoint is enclosed by
    that layer on only one side, violating ``metal1.enclosing.via1.1``
    (0.01um floor) on the other (caught by this issue's own `klt drc`
    re-run after the jog/bridge fix above; `_bus()`'s own vias never hit
    this since every riser there lands mid-span on a bar that already
    extends ``0.5um`` past every riser's own column on both sides)."""
    y_land = (pad[1] + pad[3]) / 2
    cur_x = x
    if pad_layer is L_METAL2:
        if jog_to is not None:
            far_x = jog_to + (OVERSHOOT_UM if jog_to > x else -OVERSHOOT_UM)
            route_h(b, L_METAL2, y_land, x, far_x, width=METAL2_W)
            cur_x = jog_to
    else:
        half = LANDING_UM / 2
        b.box(L_METAL1, x - half, y_land - half, x + half, y_land + half)
        via1_tap(b, x, y_land, size=VIA)
        if jog_to is not None:
            far_x = jog_to + (OVERSHOOT_UM if jog_to > x else -OVERSHOOT_UM)
            route_h(b, L_METAL1, y_land, x, far_x, width=TRUNK_W)
            via1_tap(b, jog_to, y_land, size=VIA)
            cur_x = jog_to
    y = y_land
    for lo, hi in bridges:
        route_v(b, L_METAL2, cur_x, y, lo + OVERSHOOT_UM, width=METAL2_W)
        via1_tap(b, cur_x, lo, size=VIA)
        route_v(b, L_METAL1, cur_x, lo - OVERSHOOT_UM, hi + OVERSHOOT_UM, width=TRUNK_W)
        via1_tap(b, cur_x, hi, size=VIA)
        y = hi - OVERSHOOT_UM
    route_v(b, L_METAL2, cur_x, y, bus_y, width=METAL2_W)


def _bus(b: Builder, bus_y: float, riser_xs: list[float]) -> None:
    """The bus itself -- a single Metal1 bar spanning every riser's own X,
    plus a Via1 landing at each riser's own top end (Metal2 riser -> Metal1
    bus)."""
    x_lo, x_hi = min(riser_xs) - 0.5, max(riser_xs) + 0.5
    route_h(b, L_METAL1, bus_y, x_lo, x_hi, width=TRUNK_W)
    for x in riser_xs:
        via1_tap(b, x, bus_y, size=VIA)


def _route(b: Builder, core_fb_pad: tuple[float, float, float, float], startup_sns1_pad: tuple[float, float, float, float]) -> None:
    """Wire every schematic net -- see this module's own docstring for the
    "buses are Metal1, risers are Metal2" non-crossing argument, and the
    ``_riser_up``/``LANDING_UM`` module comment above for the separate
    ("leaf-internal Metal2 crossing") hazard this function's own column
    choices below are chosen to avoid."""

    # -- vdd: core, amp, startup. `bandgap_core`'s own leg jogs sideways
    # (still landed within its own vdd pad, x=-4.9) out to x=-10, clear of
    # `bandgap_core`'s own bounding box (left edge -5.4) entirely -- nothing
    # of that leaf's own geometry exists there to cross, at any height, by
    # construction. amp/startup legs are unchanged (already verified clear:
    # amp's own x=645 sits in the gap between MTAIL's and MP3's own tap
    # rings and outside every one of amp's own Metal2 jogs' x-ranges since
    # its own vdd pad's y-land, 30.7, sits above all four of them; startup
    # has no internal Metal2 at all).
    x_core = -10.0
    x_amp = 645.0
    x_startup = 799.7
    _riser_up(b, -4.9, CORE["vdd"], Y_BUS_VDD, jog_to=x_core)
    _riser_up(b, x_amp, AMP["vdd"], Y_BUS_VDD)
    _riser_up(b, x_startup, STARTUP["vdd"], Y_BUS_VDD)
    _bus(b, Y_BUS_VDD, [x_core, x_amp, x_startup])

    # -- vss: core (Metal2 pad -- no via at that end), amp, startup. core's
    # own leg jogs (same-layer, Metal2) from x=-3.0 (still within its own
    # vss pad, the wide vss bar itself) out to x=-13, the same
    # clear-of-the-leaf's-own-bbox trick as vdd above, on its own distinct
    # column. amp's own column moves from 575 to 547 -- outside the
    # combined x-range ([550, 750]) of all four of amp's own internal
    # Metal2 jogs (JOG_D1/D2/OUT/PN), still within amp's own vss pad
    # (x in [545, 755]).
    x_core = -13.0
    x_amp = 547.0
    x_startup = 810.0
    _riser_up(b, -3.0, CORE["vss"], Y_BUS_VSS, pad_layer=L_METAL2, jog_to=x_core)
    _riser_up(b, x_amp, AMP["vss"], Y_BUS_VSS)
    _riser_up(b, x_startup, STARTUP["vss"], Y_BUS_VSS)
    _bus(b, Y_BUS_VSS, [x_core, x_amp, x_startup])

    # -- fb: core (new tab pad, already clear -- see below), amp.out,
    # startup. amp's own leg no longer lands at its "out" pad's own
    # midpoint (y=15, which sits below amp's own JOG_PN at y~=17); instead
    # it lands higher up the *same*, already-same-net "out" trunk (y=25,
    # clear of every one of amp's own Metal2 jogs, the highest of which is
    # JOG_PN at y~=17, and still within the trunk's own y in [0.9, 29.1]) --
    # nothing left to cross once the transition itself is above every jog.
    # core's own tab column (x~=-5.6) was already clear by construction (it
    # sits left of `bandgap_core`'s own busy-jog x-ranges, both of which
    # start at x=-0.25) -- unchanged.
    x_core = (core_fb_pad[0] + core_fb_pad[2]) / 2
    x_amp = 690.0
    x_startup = 820.0
    amp_fb_ride_pad = (AMP["fb"][0], 24.7, AMP["fb"][2], 25.3)
    _riser_up(b, x_core, core_fb_pad, Y_BUS_FB)
    _riser_up(b, x_amp, amp_fb_ride_pad, Y_BUS_FB)
    _riser_up(b, x_startup, STARTUP["fb"], Y_BUS_FB)
    _bus(b, Y_BUS_FB, [x_core, x_amp, x_startup])

    # -- sns1: core, amp.in_n, startup (new tab pad). core's own leg jogs
    # (still landed within its own tiny, 0.3um-wide sns1 pad, x=0.0) out to
    # x=-16, its own dedicated clear-of-the-bbox column (distinct from
    # vdd's -10 and vss's -13). startup's own leg is unchanged (no internal
    # Metal2 at all in that leaf). amp's own leg is NOT clear of every one
    # of amp's own Metal2 jogs (a fact this issue's own first draft of this
    # fix missed): amp's own "tail" net has its own riser jog at y~=32
    # (`bandgap_amp/generate.py`'s own "tail (bottom band)" section,
    # `tail_jog_y=32.0`, x in [570, 630] global) -- ABOVE amp's sns1 pad's
    # own y-land (30.0), so a straight climb from that pad crosses it. amp's
    # own sns1 pad is only 0.4um wide (x in [600.4, 600.8]) so it cannot
    # jog sideways out of that jog's own x-range without a long detour
    # across the PMOS row itself (risking new crossings); bridging through
    # the narrow y~=32 band on Metal1 instead, at the same column, is
    # simpler and verified clear there (this leaf's own Metal1 at this
    # column tops out at y=30.9 -- both the "tail" bar and this net's own
    # pad -- well below the bridge's own [31.0, 33.0] window).
    x_core = -16.0
    x_amp = 600.6
    x_startup = (startup_sns1_pad[0] + startup_sns1_pad[2]) / 2
    _riser_up(b, 0.0, CORE["sns1"], Y_BUS_SNS1, jog_to=x_core)
    _riser_up(b, x_amp, AMP["sns1"], Y_BUS_SNS1, bridges=((31.0, 33.0),))
    _riser_up(b, x_startup, startup_sns1_pad, Y_BUS_SNS1)
    _bus(b, Y_BUS_SNS1, [x_core, x_amp, x_startup])

    # -- sns2: core, amp.in_p (two cells only). core's own leg cannot jog
    # away from x=49 (its own sns2 pad only spans x in [40.5, 57.5]) --
    # instead it bridges through `bandgap_core`'s own vref/cb3 jog band
    # (y in [59.875, 60.225]) on Metal1 for one narrow window, verified
    # clear there (that band's only Metal1 at this column-adjacent region
    # is two small resistor end-pads at x<=0 and x>=82.7, both well clear
    # of x=49). The window's own upper edge (60.75, not 60.5) is chosen so
    # the Metal2 resuming above it (at ``60.75 - OVERSHOOT_UM = 60.6``)
    # clears the jog's own top edge (60.225) by >=0.21um --
    # `metal2.space.1`'s real floor, caught by this issue's own `klt drc`
    # re-run when a tighter window left only ~0.175um there. Crossing
    # `bandgap_core`'s own *sns2* jog at y~=40 needs no such detour -- same
    # net, an intentional, correct merge, not a short.
    x_core = 49.0
    x_amp = 539.4
    _riser_up(b, x_core, CORE["sns2"], Y_BUS_SNS2, bridges=((59.5, 60.75),))
    _riser_up(b, x_amp, AMP["sns2"], Y_BUS_SNS2)
    _bus(b, Y_BUS_SNS2, [x_core, x_amp])

    # -- vref: core only, brought straight up to bandgap_top's own external
    # port and labeled there (single-terminal net at this level -- no bus
    # needed, mirrors bandgap_startup's own single-terminal-pin reasoning).
    # x=120 crosses only `bandgap_core`'s own vref/cb3 jog band at its own
    # vref column (same net, safe) -- it sits left of cb3's own jog leg
    # (x in [125, 511.25]) and right of the sns2/cb2 jog band's own
    # x-extent, so no other-net crossing needs a detour here.
    x_vref = 120.0
    vref_port_y = Y_BUS_VDD + 10.0
    _riser_up(b, x_vref, CORE["vref"], vref_port_y)
    b.label(L_METAL2, "VREF", x_vref, vref_port_y)

    # bandgap_top's own external vdd/vss ports -- labeled directly on their
    # own bus (a real, physically-connected point on each net), at the
    # (moved) core-side riser columns above.
    b.label(L_METAL1, "VDD", -10.0, Y_BUS_VDD)
    b.label(L_METAL1, "VSS", -13.0, Y_BUS_VSS)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
