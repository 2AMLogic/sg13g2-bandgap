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

**Floorplan: two rows around a shared routing channel (issue #177).**
Translation only, no mirroring. The three leaf cells are placed in **two
horizontal rows** with every inter-cell bus living in the channel between
them::

    row B (top, y = 49.9 .. 123.6)
        bandgap_core     (-5.4, 49.9)-(137.5, 123.6)
          | 17.4 um gap |
        bandgap_startup  (154.9, 51.7)-(205.0, 102.2)

    routing channel (y = 34 .. 46) -- five Metal1 buses, no leaf geometry

    row A (bottom, y = -1.6 .. 32.2)
        bandgap_amp      (-10.8, -1.59)-(205.1, 32.175)

Issue #173 left this a single left-to-right row whose height was set by the
tallest leaf (``bandgap_core``, 73.7 um) while the two shorter leaves left
their share of that height empty, and whose five full-width buses sat above
the whole 482 um-wide row. Two rows fix both at once: the assembly is now
~224 x ~127 um rather than ~482 x ~97 um, and the bus channel -- the other
named mechanism in ``measurements/2026-09-resistor-fold/`` -- is both
shorter (the longest bus is now ~187 um where the row it used to cross was
482) and tighter (3 um bus pitch rather than 5 um, still 15x
``metal1.space.1``'s 0.18 um floor).

Which leaf went where is not arbitrary: it follows each leaf's own **pad
band**. ``bandgap_amp``'s ``vdd``/``sns1``/``sns2`` pads sit on its *top*
edge (y ~= 30 of a 32.2 um-tall cell), so it wants a channel *above* it;
``bandgap_core``'s and ``bandgap_startup``'s pads all sit at y <= 23 and
y <= 5 respectively (both cells are much taller than that -- the space above
is folded resistor), so they want a channel *below* them. One channel
between an amp row and a core+startup row satisfies all three, and every
riser gets *shorter* than it was in the single-row floorplan.

**The routing invariant, re-derived (issue #177).** Through issue #173 this
module's inter-cell routing rested on the three cells occupying **disjoint
x-ranges**, so a vertical route drawn within one cell's x-span could only
ever collide with that same cell's own geometry. Two rows break that
premise -- ``bandgap_amp``'s x-span now covers both of the other two leaves'
-- so it is replaced, not merely deleted, by a two-dimensional form of the
same argument plus one new global rule:

1. **Row disjointness.** The two rows occupy disjoint y-bands, separated by
   the routing channel, which contains no leaf geometry at any x. Cells
   *within* a row still occupy disjoint x-ranges (``bandgap_core`` and
   ``bandgap_startup`` are 17.4 um apart).
2. **Risers never leave their own row.** Every riser runs between its own
   cell's pad and its own net's bus in the channel -- upward from row A,
   downward from row B -- and stops there. So a riser's y-extent lies
   entirely within its own cell's row band plus the channel, and by (1) the
   only *leaf* geometry it can meet is its own cell's. That is exactly the
   property the old disjoint-x invariant bought, re-derived on (row, x)
   instead of x alone, and it is what keeps each leaf-internal crossing
   checkable one net at a time (see the ``_riser_up``/``LANDING_UM``
   comment below for those checks).
3. **Globally distinct riser columns.** What (1) and (2) do *not* give for
   free: risers from *both* rows coexist inside the channel, so two
   different nets' risers may no longer share a column anywhere in the
   assembly, not merely within one cell. Under the old invariant this was
   automatic (different cells were at different x); now it is a real
   obligation, so it is **checked rather than asserted** --
   :func:`_assert_column_pitch` fails the generator if any two different
   nets' riser columns come within :data:`MIN_COLUMN_PITCH_UM`.

Rules (1)-(3) are what make the "rise/drop straight to the channel, then
travel" routing below safe to reason about one net at a time. The
layer-based half of the argument is unchanged and orthogonal: buses are
Metal1 and risers are Metal2, so a riser crossing another net's bus cannot
short regardless of geometry (see the next paragraph).

One net does not fit (2) unaided and is called out because of it:
``bandgap_core``'s ``sns2`` pad cannot reach the channel by dropping
straight down -- ``bandgap_core``'s own ``vss`` bar is a Metal2 slab across
y ``[-0.75, 0.75]``, x ``[-3.05, 125.05]`` in local coordinates, and every
column inside that net's own pad is inside it. It instead rises the 13.7 um
to ``CORE_SNS2_CROSS_DY`` (local y=35, 0.9 um clear of the *top* of every
one of ``bandgap_core``'s own Metal2 shapes, the highest of which ends at
33.925), crosses the cell there, and drops in the left corridor. That run
stays inside row B's own band, so (2) still holds for it.

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
and its honest ``mismatch`` result is committed as-is. Issue #169's own run
found 17 findings, only 5 of which traced to the two already-known
leaf-level causes; the other 11 came from two causes new at this composed
level (an un-propagated resistor ``device_bulk`` reconciliation, and
reference-flatten hierarchy-prefix net-identity conflicts). Issue #171
resolved both of those composed-level causes (a corrected ``device_bulk``
entry pointing at the real, already-existing ``VSS`` net rather than a
per-leaf-private synthetic one, and a `layout/lvs_reference.py` `flatten()`
fix that reconciles both the bare-vs-prefixed and the merged-pin-alias
naming conventions) -- ``lvs_report.json`` now carries 8 findings, all
tracing to the two already-known, permanently-declined leaf-level causes
(plus one inferred instance of the first). See ``layout/README.md``'s
``bandgap_top`` "LVS" section for the itemised breakdown. Post-layout PEX is
deferred and was not run.
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

# Floorplan offsets -- translation only, two rows (see docstring).
#
# Issue #173 re-packed a single left-to-right row (0 / 180 / 421, all at
# dy=0); issue #177 folded that row in half. `bandgap_amp` stays at the
# origin as row A; `bandgap_core` and `bandgap_startup` move up by
# `ROW_B_DY` to form row B above the routing channel.
#
# `ROW_B_DY` is derived, not guessed: the topmost bus bar's own upper edge is
# `Y_BUS_SNS2 + TRUNK_W / 2` = 46.15, and row B's lowest leaf geometry is
# `bandgap_core`'s own bbox bottom at local y=-3.1, so `ROW_B_DY = 53` leaves
# 3.75 um of empty channel above the last bus -- ~20x `metal1.space.1`'s
# 0.18 um floor, and more than the 2.36 um that already separates the lowest
# bus from `bandgap_amp`'s own Metal1 top edge below it.
#
# STARTUP_DX puts `bandgap_startup`'s right edge (local 44.972) level with
# `bandgap_amp`'s (205.1) so neither row overhangs the other, leaving a
# 17.4 um gap to `bandgap_core`'s right edge. Nothing is routed through that
# gap -- under the two-row invariant every riser drops into the channel
# rather than travelling between same-row neighbours -- so it is sized only
# so the two cells' bounding boxes cannot touch.
#
# Every riser column in `_route` below is written as `<CELL>_DX + local`
# rather than as a baked-in absolute, so re-placing moves the columns with
# their cells (issue #173; pre-#173 they were absolutes that silently
# encoded AMP_DX=550 / STARTUP_DX=800).
ROW_B_DY = 53.0
CORE_DX, CORE_DY = 0.0, ROW_B_DY
AMP_DX, AMP_DY = 0.0, 0.0
STARTUP_DX, STARTUP_DY = 160.0, ROW_B_DY

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

# Bus heights (Metal1) -- the routing channel between the two rows (issue
# #177). Distinct per net purely for visual/manufacturing separation --
# correctness does NOT depend on this ordering (see docstring: buses are
# Metal1, risers are Metal2, so no two nets' shapes can ever cross
# regardless of height order).
#
# The floor is set by row A: `bandgap_amp`'s own Metal1 tops out at 31.49
# (its vdd bar) and its Metal2 at 32.175 (its tail jog), so a Metal1 bus at
# 34 clears the nearer, same-layer one by 2.36 um. The 3 um pitch (issue
# #177 tightened it from #173's 5 um) leaves 2.7 um between adjacent bars,
# 15x `metal1.space.1`'s 0.18 um floor; the whole five-bus stack is 12 um
# tall where the single-row one was 20.
Y_BUS_VDD = 34.0
Y_BUS_VSS = 37.0
Y_BUS_FB = 40.0
Y_BUS_SNS1 = 43.0
Y_BUS_SNS2 = 46.0

#: ``bandgap_core``-local height at which that cell's own ``sns2`` riser
#: crosses back to the left corridor -- see the module docstring's "One net
#: does not fit (2) unaided" paragraph. 0.9 um above the top edge (33.925)
#: of every one of `bandgap_core`'s own Metal2 shapes, and 35.6 um below its
#: own bbox top, so the crossing run stays inside row B's band.
CORE_SNS2_CROSS_DY = 35.0

#: Minimum centre-to-centre spacing between two **different** nets' riser
#: columns anywhere in the assembly -- the machine-checked half of the
#: two-row routing invariant (docstring rule 3), enforced by
#: :func:`_assert_column_pitch`. Risers are ``METAL2_W`` = 0.35 um wide, so
#: 2.0 um leaves 1.65 um of edge-to-edge clearance, an order of magnitude
#: above every same-layer spacing floor this deck declares (the tightest
#: this module's own geometry meets is `metal1.space.1`'s 0.18 um). The
#: value is a floorplan-review threshold, not a DRC floor -- `klt drc`
#: still checks the real ones, and would not catch this failure anyway
#: (two overlapping same-layer shapes merge into one clean polygon).
MIN_COLUMN_PITCH_UM = 2.0

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
    # Issue #173: RPU's `vdd` end-A pad moved when RPU was folded -- it is
    # now the folded block's bottom-left terminal (a 1.4 x 0.5 um pad hanging
    # below the core's own bottom edge at y=5) instead of the straight bar's
    # left end pad at y=20. Re-read off the regenerated leaf GDS, same way
    # every other entry in these maps was.
    "vdd": (-0.2, 4.5, 1.2, 5.0),
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


def _assert_column_pitch(columns: list[tuple[str, float]]) -> None:
    """Fail the generator if two **different** nets' riser columns come
    within :data:`MIN_COLUMN_PITCH_UM` of each other.

    This is the machine-checked half of the two-row routing invariant (rule
    3 in this module's own docstring). Under the pre-#177 single-row
    floorplan it was structurally impossible for two cells' risers to share
    a column, because the three cells occupied disjoint x-ranges; with two
    rows every riser passes through the *same* routing channel on its way to
    its own bus, so column collisions between cells are now possible and
    would be a real short that `klt drc` cannot see (two same-layer Metal2
    shapes that overlap merge into one clean polygon -- the exact failure
    mode the ``LANDING_UM`` comment above documents for leaf-internal
    crossings).

    Same-net entries are exempt: two risers of one net *may* share a column
    (they would simply merge, which is what the bus does anyway)."""
    for i, (net_a, x_a) in enumerate(columns):
        for net_b, x_b in columns[i + 1 :]:
            if net_a == net_b:
                continue
            if abs(x_a - x_b) < MIN_COLUMN_PITCH_UM:
                raise AssertionError(
                    f"riser columns for nets {net_a!r} (x={x_a}) and {net_b!r} "
                    f"(x={x_b}) are {abs(x_a - x_b)}um apart, under this "
                    f"module's own {MIN_COLUMN_PITCH_UM}um floor -- two "
                    "different nets' Metal2 risers now share the routing "
                    "channel and would merge (see _assert_column_pitch)"
                )


def _route(b: Builder, core_fb_pad: tuple[float, float, float, float], startup_sns1_pad: tuple[float, float, float, float]) -> None:
    """Wire every schematic net -- see this module's own docstring for the
    two-row routing invariant (row disjointness / risers stay in their own
    row / globally distinct columns) and the "buses are Metal1, risers are
    Metal2" non-crossing argument, plus the ``_riser_up``/``LANDING_UM``
    module comment above for the separate ("leaf-internal Metal2 crossing")
    hazard this function's own column choices below are chosen to avoid.

    Direction of travel is now per row (issue #177): row A
    (``bandgap_amp``) rises into the channel, row B (``bandgap_core``,
    ``bandgap_startup``) drops into it. ``_riser_up`` handles both -- its
    ``route_v`` legs are order-independent -- so nothing but the sign of
    ``bus_y - y_land`` changes for a row-B leg.

    Every column chosen below is registered in ``columns`` and checked by
    :func:`_assert_column_pitch` before this function returns."""
    columns: list[tuple[str, float]] = []

    # -- vdd: core, amp, startup. `bandgap_core`'s own leg jogs sideways
    # (still landed within its own vdd pad, x=-4.9) out to the left
    # corridor, clear of `bandgap_core`'s own bounding box (left edge -5.4)
    # entirely -- nothing of that leaf's own geometry exists there to cross,
    # at any height, by construction. That jog is what lets the leg drop
    # past `bandgap_core`'s own Metal2 vss slab (local y in [-0.75, 0.75],
    # x in [-3.05, 125.05]) rather than through it. amp/startup legs keep
    # their #173 columns and are now *shorter*, not rerouted: amp's own
    # local x=95 sits in the gap between MTAIL's and MP3's own tap rings and
    # outside every one of amp's own Metal2 jogs' x-ranges (its vdd pad's
    # y-land, 30.7, is above all four of them); startup has no internal
    # Metal2 at all.
    x_core = -10.5
    x_amp = AMP_DX + 95.0
    x_startup = STARTUP_DX - 0.3
    columns += [("vdd", x_core), ("vdd", x_amp), ("vdd", x_startup)]
    _riser_up(b, CORE_DX - 4.9, CORE["vdd"], Y_BUS_VDD, jog_to=x_core)
    _riser_up(b, x_amp, AMP["vdd"], Y_BUS_VDD)
    _riser_up(b, x_startup, STARTUP["vdd"], Y_BUS_VDD)
    _bus(b, Y_BUS_VDD, [x_core, x_amp, x_startup])

    # -- vss: core (Metal2 pad -- no via at that end), amp, startup.
    #
    # core's own leg drops **straight down out of its own vss bar**, with no
    # sideways jog at all. Through #173 it jogged left (same-layer, Metal2)
    # into the corridor first, which was harmless while every riser rose
    # *away* from it; under the two-row floorplan that jog would be a
    # horizontal Metal2 bar lying across the corridor at exactly the height
    # (local y=0) every other row-B riser must pass through on its way down,
    # shorting vdd/fb/sns2 into vss. (Not hypothetical: the first two-row
    # draft of this module did exactly that and `klt extract` came back with
    # those four nets merged into one -- rule 2's "risers stay in their own
    # row" says nothing about a *horizontal* run, which is why the jog had
    # to go rather than be re-columned.)
    #
    # The drop needs no jog because `bandgap_core`'s own vss bar *is* the
    # lowest Metal2 that leaf owns (local y in [-0.75, 0.75]; nothing of
    # that leaf's Metal2 exists below it at any x), so a Metal2 leg leaving
    # its underside meets none of it. Local x=30 is clear of that leaf's own
    # Metal1 blocks in the same band too (local x in [-5, 5], [47.65, 67.3]
    # and [118.65, 125.35]) -- not that it would matter for a via-free
    # Metal2 crossing, but it keeps the leg away from their edges.
    #
    # amp's own local x=-3 is outside the combined x-range (local [0, 200])
    # of all four of amp's own internal Metal2 jogs (JOG_D1/D2/OUT/PN) and
    # still within amp's own vss pad (local x in [-5, 205]).
    x_core = CORE_DX + 30.0
    x_amp = AMP_DX - 3.0
    x_startup = STARTUP_DX + 10.0
    columns += [("vss", x_core), ("vss", x_amp), ("vss", x_startup)]
    _riser_up(b, x_core, CORE["vss"], Y_BUS_VSS, pad_layer=L_METAL2)
    _riser_up(b, x_amp, AMP["vss"], Y_BUS_VSS)
    _riser_up(b, x_startup, STARTUP["vss"], Y_BUS_VSS)
    _bus(b, Y_BUS_VSS, [x_core, x_amp, x_startup])

    # -- fb: core (new tab pad, already clear -- see below), amp.out,
    # startup. amp's own leg does not land at its "out" pad's own midpoint
    # (y=15, which sits below amp's own JOG_PN at y~=17); it lands higher up
    # the *same*, already-same-net "out" trunk (y=25, clear of every one of
    # amp's own Metal2 jogs, the highest of which is JOG_PN at y~=17, and
    # still within the trunk's own y in [0.9, 29.1]) -- nothing left to
    # cross once the transition itself is above every jog. core's own tab
    # column (x~=-5.6) is clear by construction: `draw_gate_tab(side="left")`
    # puts the pad entirely left of the gate edge it extends (-5.1), i.e.
    # left of `bandgap_core`'s own leftmost Metal1 (-5.0) and Metal2
    # (-3.05), so the drop meets none of it.
    x_core = (core_fb_pad[0] + core_fb_pad[2]) / 2
    x_amp = AMP_DX + 140.0
    x_startup = STARTUP_DX + 20.0
    columns += [("fb", x_core), ("fb", x_amp), ("fb", x_startup)]
    amp_fb_ride_pad = (AMP["fb"][0], AMP_DY + 24.7, AMP["fb"][2], AMP_DY + 25.3)
    _riser_up(b, x_core, core_fb_pad, Y_BUS_FB)
    _riser_up(b, x_amp, amp_fb_ride_pad, Y_BUS_FB)
    _riser_up(b, x_startup, STARTUP["fb"], Y_BUS_FB)
    _bus(b, Y_BUS_FB, [x_core, x_amp, x_startup])

    # -- sns1: core, amp.in_n, startup (new tab pad). core's own leg jogs
    # (still landed within its own tiny, 0.3um-wide sns1 pad, local x=0.0)
    # out to its own dedicated left-corridor column. startup's own leg is
    # unchanged (no internal Metal2 at all in that leaf). amp's own leg is
    # NOT clear of every one of amp's own Metal2 jogs: amp's own "tail" net
    # has its own riser jog at local y~=32 (`bandgap_amp/generate.py`'s own
    # "tail (bottom band)" section, `tail_jog_y=32.0`) which at this column
    # occupies y in [31.825, 32.175] -- ABOVE amp's sns1 pad's own y-land
    # (30.0), so a straight climb from that pad crosses it. amp's own sns1
    # pad is only 0.4um wide (local x in [50.4, 50.8]) so it cannot jog
    # sideways out of that jog's own x-range without a long detour across
    # the PMOS row itself (risking new crossings); bridging through the
    # narrow band on Metal1 instead, at the same column, is simpler and
    # verified clear there (this leaf's own Metal1 at this column tops out
    # at y=30.9 -- both the "tail" bar and this net's own pad -- well below
    # the bridge's own [31.0, 33.0] window).
    x_core = -15.5
    x_amp = AMP_DX + 50.6
    x_startup = (startup_sns1_pad[0] + startup_sns1_pad[2]) / 2
    columns += [("sns1", x_core), ("sns1", x_amp), ("sns1", x_startup)]
    _riser_up(b, CORE_DX + 0.0, CORE["sns1"], Y_BUS_SNS1, jog_to=x_core)
    _riser_up(b, x_amp, AMP["sns1"], Y_BUS_SNS1, bridges=((AMP_DY + 31.0, AMP_DY + 33.0),))
    _riser_up(b, x_startup, startup_sns1_pad, Y_BUS_SNS1)
    _bus(b, Y_BUS_SNS1, [x_core, x_amp, x_startup])

    # -- sns2: core, amp.in_p (two cells only) -- the one net the two-row
    # invariant's rule 2 does not give for free. See the module docstring's
    # own "One net does not fit (2) unaided" paragraph: core's sns2 pad
    # (local x in [40.5, 57.5]) is entirely inside the x-span of
    # `bandgap_core`'s own Metal2 vss slab (local x in [-3.05, 125.05],
    # y in [-0.75, 0.75]), so no column within that pad can drop to the
    # channel. It goes *up* instead, on the same local x=49 column #173
    # used -- which merges, intentionally and correctly, with
    # `bandgap_core`'s own same-net sns2 jog (local x in [43, 49.175],
    # y in [21.1, 33.925]) -- then crosses the cell at CORE_SNS2_CROSS_DY,
    # 0.9um above the top edge of every Metal2 shape that leaf owns, and
    # drops in the left corridor. amp's own in_p pad sits on that leaf's own
    # left edge (local x in [-10.8, -10.4]), so its leg jogs left on Metal1
    # to a corridor column of its own before rising -- the jog runs at
    # y=30.0, 0.4um clear of amp's own vdd bar (local y in [30.55, 31.49]),
    # the same clearance class the pre-existing LANDING_UM pad at that pad
    # already holds.
    x_core = -8.0
    x_amp = AMP_DX - 18.0
    y_cross = CORE_DY + CORE_SNS2_CROSS_DY
    columns += [("sns2", x_core), ("sns2", x_amp)]
    core_sns2_pad = CORE["sns2"]
    y_land = (core_sns2_pad[1] + core_sns2_pad[3]) / 2
    half = LANDING_UM / 2
    b.box(L_METAL1, CORE_DX + 49.0 - half, y_land - half, CORE_DX + 49.0 + half, y_land + half)
    via1_tap(b, CORE_DX + 49.0, y_land, size=VIA)
    route_v(b, L_METAL2, CORE_DX + 49.0, y_land, y_cross, width=METAL2_W)
    route_h(b, L_METAL2, y_cross, CORE_DX + 49.0, x_core, width=METAL2_W)
    route_v(b, L_METAL2, x_core, y_cross, Y_BUS_SNS2, width=METAL2_W)
    _riser_up(b, AMP_DX - 10.6, AMP["sns2"], Y_BUS_SNS2, jog_to=x_amp)
    _bus(b, Y_BUS_SNS2, [x_core, x_amp])

    # -- vref: core only, brought straight up to bandgap_top's own external
    # port and labeled there (single-terminal net at this level -- no bus
    # needed, mirrors bandgap_startup's own single-terminal-pin reasoning).
    # Local x=120 crosses only `bandgap_core`'s own vref/cb3 jog band at its
    # own vref column (same net, safe) -- it sits left of cb3's own jog leg
    # and right of the sns2/cb2 jog band's own x-extent, so no other-net
    # crossing needs a detour here. Issue #177 stops the stub 1.4um above
    # `bandgap_core`'s own bbox top (local 70.623) instead of carrying it
    # past a bus stack that is no longer up there; the whole path is a
    # subset of the one #173 already proved DRC-clean.
    x_vref = CORE_DX + 120.0
    vref_port_y = CORE_DY + 72.0
    columns.append(("vref", x_vref))
    _riser_up(b, x_vref, CORE["vref"], vref_port_y)
    b.label(L_METAL2, "VREF", x_vref, vref_port_y)

    # bandgap_top's own external vdd/vss ports -- labeled directly on their
    # own bus (a real, physically-connected point on each net), at the
    # core-side riser columns above.
    b.label(L_METAL1, "VDD", -10.5, Y_BUS_VDD)
    b.label(L_METAL1, "VSS", CORE_DX + 30.0, Y_BUS_VSS)

    _assert_column_pitch(columns)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
