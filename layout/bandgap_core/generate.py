#!/usr/bin/env python3
"""Generate ``bandgap_core.gds`` -- physical layout of ``design/bandgap_core.sch``.

Drawn directly with the ``klayout.db`` (``pya``-compatible) Python API via
``layout/common.py``'s shared primitives -- see that module's docstring for
why this issue used a manual construction script rather than a PDK-native
PCell run, matching the construction pattern
``gf180-bandgap/layout/bandgap_top/generate.py`` already established for the
fleet's most mature block.

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_core/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against ``design/netlist/bandgap_core.spice``
(``XM1``/``XQ1``/``XM2A``/``XM2B``/``XR2``/``XQ2``/``XM3A``-``XM3C``/``XR1``/
``XQ3``):

    M1  sg13_hv_pmos w=10u l=1u        -- branch 1 mirror leg (vdd/fb -> sns1)
    Q1  npn13G2 Nx=1                   -- branch 1, diode-connected (sns1 -> vss)
    M2A/M2B sg13_hv_pmos w=9u/1u       -- branch 2 mirror leg, 2x parallel
                                           dominant+trim unit fingers
                                           (vdd/fb -> sns2)
    R2  rppd w=2u l=82.7u              -- PTAT resistor (sns2 -> cb2)
    Q2  npn13G2 Nx=8                   -- branch 2, diode-connected (cb2 -> vss)
    M3A-M3C sg13_hv_pmos w=8u/1u/1u    -- output branch mirror leg, 3x
                                           parallel dominant+trim unit
                                           fingers (vdd/fb -> vref)
    R1  rppd w=2u l=37.2u              -- summing resistor's fixed base
                                           (vref -> tn0), issue #229
    XTRIM 255x rppd w=2u l=3.43u       -- the binary-weighted trim ladder
                                           (tn0 -> cb3), issue #229/#272;
                                           see "Trim ladder" below
    Q3  npn13G2 Nx=1                   -- output branch, diode-connected
                                           (cb3 -> vss)

**Trim ladder (issue #272).** Issue #229 split the summing resistor in the
*schematic*: ``XR1`` shrank from ``l=511u`` to ``l=37.2u`` and now runs
``vref -> tn0``, with ``XXTRIM`` (``design/bandgap_trim.sch``, 255 identical
``rppd w=2u l=3.43u`` unit segments in one series string, tapped after
1/3/7/15/31/63/127 units and shunted by eight binary-weighted straps
``RS0``-``RS7``) continuing ``tn0 -> cb3``. This script is the layout
counterpart: it draws the ladder as a flat 17-column x 15-unit serpentine
array of individually-recognised ``rppd`` devices plus the strap links the
**ratified default code 128** selects, and resizes ``R1`` to ``l=37.2u``
(``R1_LEGS = 5``). See ``design/bandgap_trim_network.md`` for the sizing
derivation (and its section 5, which budgeted this re-layout) and
``layout/README.md`` "Trim ladder layout (issue #272)" for the floorplan,
the strap convention, and the LVS consequences.

Two facts about the straps drive everything else here. ``RS0``-``RS7`` are
**not fabricated devices** -- ``design/bandgap_trim_network.md`` section 4
calls them "verification-time models of a metal-option / probe-pad link",
``1e-3 Ohm`` when the link is drawn (bit 0, group shorted out) and
``1e12 Ohm`` when it is cut (bit 1, group in circuit). So:

  1. A layout realises **one** code, not all 256. This cell draws
     ``TRIM_CODE = 128`` (the schematic default): bits 0-6 are 0, so the
     seven links ``t0-t1-t3-t7-t15-t31-t63-t127`` are drawn as real
     ``Metal2`` straps; bit 7 is 1, so the ``t127 -> out`` link is **not**
     drawn and units 128-255 carry the branch current (``Rtrim(128) =
     128 * R_unit``, exactly what ``trim_code=128`` means).
  2. Because every drawn strap is closed and they chain end-to-end, all
     seven are one physical net -- which is why they can be drawn as a
     single overlapping ``Metal2`` chain with no inter-strap spacing
     problem, and why that chain is allowed to run straight over the
     shorted-out units' own interior pads (same-net above, different-layer
     below; see ``_draw_trim_straps``).

**Unit-device decomposition (issue #149, T1 tracker #4 item 4 cause d).**
M1/M2/M3 previously drew as ONE ``sg13_hv_pmos w=10u l=1u`` footprint each --
identical at the recognised-device level, a genuine graph automorphism the
sg13g2 `klt lvs` deck could not resolve (see "LVS" below and
``layout/README.md`` "Permanent blockers" #2). Each leg's *total* mirror
width is unchanged (W/L=10u/1u -- the ratio mirror accuracy depends on),
but M2/M3 are now decomposed into a per-leg-distinct COUNT of parallel
unit fingers -- the minimum pairwise-distinct count set, {1,2,3} (M1
stays a single w=10u unit; M2: 2x, one w=9u dominant + one w=1u trim
finger; M3: 3x, one w=8u dominant + two w=1u trim fingers), each drawn as
its own separate ``draw_hv_mos`` footprint (non-touching, non-merging) and
tied together at every terminal. **This decomposition is NOT electrically
exact** -- see ``design/bandgap_core.sch``'s own header "NOT electrically
exact" section for the quantified real-compact-model mismatch a device-
count-driven (not just width-driven) split like this introduces in
IHP-SG13G2's `sg13_hv_pmos` PSP103 model, why a smaller {1,2,3}
count-spread with dominant+trim fingers (rather than the deeper {1,2,4}
equal-width split this issue's own first draft used) was chosen to
minimize it, and where the closed-loop PVT evidence quantifying the
resulting behavioural delta lives. See ``_route``'s ``_tie_drains`` helper
below for how the drain pads within one branch are physically joined into
a single net before routing on to the branch's resistor/HBT.

**Routing (issue #20).** After placing all 8 devices, this script wires up
every schematic net (``vdd``, ``fb``, ``sns1``, ``sns2``, ``vref``, ``cb2``,
``cb3``, ``vss``) with real ``Metal1``/``Metal2``/``Via1``/``GatPoly``
shapes -- ``layout/common.py``'s ``draw_hv_mos``/``draw_npn13g2``/
``draw_poly_res`` each only draw one device's own isolated footprint, no
wiring *between* devices (see #11/#12's own findings, ``layout/README.md``
"DRC/LVS verification"). The floorplan is column/row structured (MOS row at
``y=22``, HBT row at ``y=0``, resistor rows at ``y=40``/``y=60``), which
this routing exploits directly:

    - ``vdd``/``fb`` (3-terminal, all on the MOS row): one continuous
      horizontal ``Metal1``/``GatPoly`` bar each, spanning all three MOS
      instances' source pads / gates -- touching-and-merging with each
      device's own drawn pad needs no vias at all.
    - ``sns1`` (M1.drain + Q1's diode-connected collector+base, both below
      the MOS row): a single vertical ``Metal1`` strip.
    - ``vss`` (all three HBT emitters, all ``Metal2`` already): one
      horizontal ``Metal2`` bar.
    - ``sns2``/``cb2``/``vref``/``cb3`` (each spans from the HBT row, up
      *past* the ``vdd``/``fb`` Metal1/GatPoly bars, to a resistor row):
      routed on ``Metal2`` for the vertical "riser" that crosses the
      ``vdd``/``fb`` bars' Y-band (a different layer cannot short against
      either bar no matter how it crosses them in plan view), landing back
      on ``Metal1`` at each end via a ``Via1`` tap.

Re-running ``klt drc --deck sg13g2``/``klt lvs`` after this routing is
tracked in ``layout/README.md`` "DRC/LVS verification". **This routing pass
does not, on its own, get the ``pfet`` devices to ``matched``** -- re-running
found two *additional*, independent, out-of-this-issue's-control causes
beyond the original bipolar/resistor-recognition gap, both fully diagnosed
and documented there ("LVS -- still `mismatch`, three independent,
fully-attributed causes"): the curated ``sg13g2`` extraction deck models no
well/substrate-tap layer at all (every MOS body terminal is therefore
either anonymous (PMOS) or tied to a deck-synthesized global net that does
not match the schematic's real `vdd`/`vss` body tie (NMOS) -- structurally
unfixable by routing), and -- **before issue #149** -- `M1`/`M2`/`M3` were
perfectly symmetric at the recognized-device level (identical `w`/`l`,
distinguished in the real schematic only by the downstream bipolar/
resistor devices this deck cannot see), a graph automorphism no amount of
routing or `klt lvs`'s own `hints.same_nets` could resolve (verified:
explicit hints were tried and rejected by the comparer, see the README).
Issue #149 addressed that third cause structurally (unit-device
decomposition above, not routing) -- the well/substrate-tap gap and the
declined bipolar recognition remain, tracked separately. The routing itself
is complete and verified correct (every schematic net is a single
physically-connected shape, confirmed via `klt extract`'s own net/device
breakdown) -- the remaining ``device.unmatched``/``net.unmatched`` findings
are attributed to the two deck-level facts above, not a routing gap.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    L_METAL2,
    L_TEXT,
    Builder,
    draw_hv_mos,
    draw_npn13g2,
    draw_poly_res,
    route_h,
    route_v,
    via1_tap,
)

TOP_CELL = "bandgap_core"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_core.gds")

# Routing widths/sizes -- comfortably clear of the curated sg13g2 deck's own
# minimums (metal1.width.1/metal2.width.1: 0.16/0.20um; via1.width.1:
# 0.19um) with margin, not razor-thin -- see layout/common.py's route_h/
# route_v/via1_tap docstrings for the exact clearance each leaves.
TRUNK_W = 0.3
VIA = 0.25
# Metal2 riser/jog width -- wider than the 0.20um metal2.width.1 floor would
# strictly require on a straight run, because a right-angle T-junction
# between a vertical riser and a horizontal jog of the *same* nominal width
# measures narrower than that nominal width along the junction's diagonal
# (`klt drc`'s `Region.width_check` measures true polygon width, not just
# each straight run in isolation -- confirmed by this issue's own `klt drc`
# re-run: a first pass at ``width=VIA`` (0.25um) violated ``metal2.width.1``
# at every riser/jog corner, each bbox sized ~0.19x0.19um, consistent with
# 0.25um's own diagonal (0.25*cos(45)=0.177um) falling under the 0.20um
# floor). 0.35um clears it with margin (0.35*cos(45)=0.247um).
METAL2_W = 0.35
# Extra margin the Metal1-tie-to-Via1 junction (`_tie_and_riser`) carries
# past the via's own edge, clearing `metal1.enclosing.via1.1` (0.01um
# floor) with real margin -- a first pass that stopped the tie exactly at
# the via's edge (zero enclosure) violated this rule (`klt drc` re-run).
VIA_ENCLOSE = 0.05

# Serpentine fold counts (issue #173). Both resistors used to be drawn as
# single straight bars whose length alone set this cell's bounding box --
# `R1` at l=511u made the cell 516.9um wide against a 64.5um height (8.0:1),
# and `measurements/2026-09-layout-area/` measured the resulting assembly as
# 77.5% aspect-ratio whitespace. Each count is chosen to make its own folded
# block roughly square: with `draw_poly_res`'s `RES_FOLD_GAP_UM` (0.4) and
# w=2u the leg pitch is ~2.4um, and a block is square at
# `legs = sqrt(l / pitch)` -- sqrt(511/2.4) = 14.6 and sqrt(82.7/2.4) = 5.9.
# Both are rounded to an **even** count so each resistor's two terminals come
# out on its own bottom row (an odd count leaves end B on top -- see
# `draw_poly_res`), which is what lets `_riser`/`_tie_and_riser` keep landing
# on both pads from the same Metal2 row.
#
# Folding conserves the drawn conductor length exactly (see
# `_klayout_builder_base.fold_plan`), so neither resistor's nominal value
# moves: `klt extract` reports R1/R2 at the same ohms before and after.
# `R1` is now the trim network's fixed base only (l=37.2u, issue #229), so
# its own fold count drops from 14 to 5. **Odd on purpose**: an odd leg
# count brings end B out on the block's *top* row (see `draw_poly_res`),
# which is what lets `vref` land on end A from the MOS row below while
# `tn0` escapes upward toward the ladder without the two nets' Metal2 jogs
# sharing a pad row -- the exact collision an even count (both pads on the
# bottom row, one net's jog passing straight over the other's via) would
# force. sqrt(37.2/2.4) = 3.9, so 5 is also the nearest odd count to the
# square-block optimum (11.6 x 7.12 um, aspect 1.63).
R1_LEGS = 5
R2_LEGS = 6

# ---------------------------------------------------------------------- #
# Trim ladder geometry (issue #272) -- see this module's own docstring for
# the schematic it realises and the strap convention, and
# `design/bandgap_trim_network.md` for the sizing.
# ---------------------------------------------------------------------- #

#: Number of series unit segments, matching `design/bandgap_trim.sch`'s own
#: XRU1-XRU255 exactly (8-bit ladder: 2^8 - 1).
TRIM_UNITS = 255
TRIM_UNIT_W = 2.0
TRIM_UNIT_L = 3.43
#: Units per column. 17 x 15 = 255 **exactly** -- the only factorisation of
#: 255 (3 x 5 x 17) that gives a block fitting beside the existing cell
#: without a ragged last column: 15 x TRIM_PITCH_Y = 69.25 um tall against
#: 17 x TRIM_PITCH_X = 45.9 um wide (aspect 1.51). A ragged column would
#: make the serpentine's tap arithmetic special-case its own last column
#: for no area gain.
TRIM_COL_UNITS = 15
TRIM_COLS = TRIM_UNITS // TRIM_COL_UNITS  # 17

#: Column pitch. A unit's own Metal1 terminal pad is `w + 0.4` = 2.4 um
#: wide (`draw_poly_res`'s head margin plus the pad's own 0.1 um overhang
#: per side), so 2.7 leaves 0.3 um between two adjacent columns' pads --
#: 0.12 um clear of `metal1.space.1` (0.18). The GatPoly heads underneath
#: are 2.2 um wide, so their own space is 0.5 um.
TRIM_PITCH_X = 2.7
#: Row pitch. A unit occupies `0.5 + l + 0.5` = 4.43 um of y (bottom pad,
#: body, top pad), so 4.63 leaves a 0.2 um Metal1 gap between one unit's
#: top pad and the next unit's bottom pad -- bridged explicitly by
#: `_draw_trim_links` (they are the same series node) -- and 0.4 um of
#: GatPoly space between the two heads, 0.22 um clear of
#: `gatpoly.space.1`. Pitching them to *touch* (4.43) would leave only
#: 0.02 um of margin on that poly space, so the link box is drawn instead.
TRIM_PITCH_Y = 4.63

#: Lower-left corner of unit (column 0, row 0)'s own marked core. The
#: ladder is placed to the **right** of the existing cell rather than above
#: it: `layout/bandgap_top/generate.py` rises the assembly's `vref` port
#: column straight up through the core at local x=120 and stops it 1.4 um
#: above the core's own bbox top, so growing the core *upward* would put
#: new geometry inside an already-verified top-level riser, whereas growing
#: it *rightward* only moves `STARTUP_DX` (every startup riser there is
#: written as `STARTUP_DX + local`, and the buses span their riser set).
TRIM_X0 = 140.0
TRIM_Y0 = 0.0

#: The code this layout's metal-option straps realise -- the schematic
#: default (`design/bandgap_trim.sch`'s own `.param trim_code=128`), which
#: `design/bandgap_trim_network.md` section 3 shows reproduces the pre-#229
#: single-instance 511 um summing resistor to 3 Ohm (0.005%).
TRIM_CODE = 128

#: Strap `b` shunts the group between these two ladder nodes (node `k` is
#: the junction after unit `k`; node 0 is `in`/`tn0`, node 255 is
#: `out`/`cb3`). Transcribed from `design/netlist/bandgap_core.spice`'s own
#: RS0-RS7 cards, not re-derived.
TRIM_STRAP_NODES = ((0, 1), (1, 3), (3, 7), (7, 15), (15, 31), (31, 63), (63, 127), (127, 255))

#: Strap width. These are metal links standing in for a mask option, so
#: their resistance is a real series error against the 478 Ohm unit: the
#: drawn code-128 chain (t0 -> t127) is ~115 um of Metal2, which at 1.0 um
#: wide and this stack's ~0.09 Ohm/sq is ~10 Ohm -- 0.016% of the 66 kOhm
#: summing resistor, well inside the 2.443 mV trim step. At the 0.3 um
#: TRUNK_W it would be ~35 Ohm (0.05%), a third of a step; 1.0 um is the
#: cheapest way to keep the metal option out of the trim's own error
#: budget, and `klt extract --parasitics` measures what it actually is.
TRIM_STRAP_W = 1.0

#: `tn0`'s own Metal1 crossing band -- 3.4 um above R1's end-B pad row and
#: 4.25 um below the ladder's first row-9 pad, i.e. the middle of the only
#: band in the cell with nothing drawn on Metal1 between R1 and the ladder.
TRIM_TN0_Y = 45.0
#: Where `tn0` drops from Metal1 to Metal2 for its vertical run: the 2.6 um
#: channel between the cell's rightmost device geometry (M3C's NWell, out
#: to ~135.5) and the ladder's own leftmost pad edge (139.8).
TRIM_TN0_VIA_X = 138.5
#: `tn0`'s Metal1 width. Wider than TRUNK_W so the Via1 landing at
#: TRIM_TN0_VIA_X keeps 0.125 um of Metal1 enclosure on the long axis
#: (`metal1.enclosing.via1.1` floor: 0.01 um) instead of TRUNK_W's 0.025.
TN0_TRUNK_W = 0.5
#: `cb3`'s Metal2 jog row, above every shape the ladder array draws (its
#: topmost pad edge is TRIM_Y0 + 14*TRIM_PITCH_Y + 3.93 = 68.75).
TRIM_CB3_TOP_Y = 71.5


def build() -> Builder:
    b = Builder(TOP_CELL)

    mos_y = 22.0
    hbt_y = 0.0
    # Both folded resistor blocks share one row above the MOS row (issue
    # #173). Pre-fold they needed a row each, stacked 20um apart, because
    # each was a >80um-long bar starting at x=0 regardless of which branch it
    # belonged to; folded, each block is small enough to sit directly above
    # its own branch, so they share a row and the second one disappears.
    res_y = 34.0

    # Branch 1: M1 -> Q1, no series resistor (Q1 sensed directly at sns1).
    # Left as a single w=10u unit -- issue #149's decomposition only needs
    # to make M1/M2/M3 structurally distinct from EACH OTHER, and M2 (2x)
    # vs M3 (3x) already differ from each other and from M1's single unit.
    x1 = 0.0
    m1 = draw_hv_mos(b, "M1", "pmos", 10.0, 1.0, x1, mos_y, gate_net="fb", source_net="vdd", drain_net="sns1")
    q1 = draw_npn13g2(b, "Q1", 1, x1, hbt_y, collector_net="sns1", base_net="sns1", emitter_net="vss")

    # Branch 2: M2A/M2B (issue #149 -- 2x parallel unit fingers, one
    # dominant (w=9u) + one trim (w=1u), total W/L unchanged at 10u/1u --
    # see design/bandgap_core.sch's own header "NOT electrically exact"
    # section for why a dominant+trim split, not an equal-width one, was
    # chosen) -> R2 -> Q2 (Nx=8, sets the PTAT delta-VBE leg). Pitch (12u)
    # comfortably clears both units' own NWell margins (w/2 + 0.4um per
    # side, <=4.9um for the w=9u dominant finger) so neighbouring wells do
    # not overlap.
    x2_pitch = 12.0
    x2a, x2b = 45.0, 45.0 + x2_pitch
    m2a = draw_hv_mos(b, "M2A", "pmos", 9.0, 1.0, x2a, mos_y, gate_net="fb", source_net="vdd", drain_net="sns2")
    m2b = draw_hv_mos(b, "M2B", "pmos", 1.0, 1.0, x2b, mos_y, gate_net="fb", source_net="vdd", drain_net="sns2")
    q2 = draw_npn13g2(b, "Q2", 8, (x2a + x2b) / 2, hbt_y, collector_net="cb2", base_net="cb2", emitter_net="vss")
    # R2 folded into R2_LEGS legs (issue #173) and placed directly above its
    # own branch (x0=42, i.e. spanning the M2A/M2B pair below it) instead of
    # starting at x=0 the way an 82.7um bar had to. 14.0 x 13.45 um.
    r2 = draw_poly_res(
        b, "R2", "rppd", 2.0, 82.7, 42.0, res_y,
        end_a_net="sns2", end_b_net="cb2", legs=R2_LEGS,
    )

    # Output branch: M3A-M3C (issue #149 -- 3x parallel unit fingers, one
    # dominant (w=8u) + two trim (w=1u each), total W/L unchanged at
    # 10u/1u) -> R1 -> Q3, vref is the mirror node directly. Pitch (12u,
    # matching branch 2's) clears every unit's own NWell margin (<=4.4um
    # per side for the w=8u dominant finger) with room to spare.
    x3_pitch = 12.0
    x3_names = ("M3A", "M3B", "M3C")
    x3_widths = (8.0, 1.0, 1.0)
    x3_xs = [110.0 + i * x3_pitch for i in range(3)]
    m3_legs = [
        draw_hv_mos(b, name, "pmos", w, 1.0, x, mos_y, gate_net="fb", source_net="vdd", drain_net="vref")
        for name, w, x in zip(x3_names, x3_widths, x3_xs)
    ]
    q3 = draw_npn13g2(b, "Q3", 1, sum(x3_xs) / len(x3_xs), hbt_y, collector_net="cb3", base_net="cb3", emitter_net="vss")
    # R1 folded into R1_LEGS legs (issue #173), resized to l=37.2u by issue
    # #272 to match design/bandgap_core.sch's own #229 split: this is now
    # only the summing resistor's *fixed base* (vref -> tn0), with the
    # 255-unit trim ladder below continuing tn0 -> cb3. 11.6 x 7.12 um,
    # still placed directly above its own M3A-M3C branch on the same row as
    # R2 (pre-#229 this was a 33.3 x 36.1 um block that alone set the
    # cell's 137.5 um width).
    r1 = draw_poly_res(
        b, "R1", "rppd", 2.0, 37.2, 104.0, res_y,
        end_a_net="vref", end_b_net="tn0", legs=R1_LEGS,
    )

    # The trim ladder (issue #272) -- 255 individually-recognised rppd unit
    # segments plus the code-128 metal-option straps. Returns the per-node
    # tap pads `_route` needs for `tn0` (node 0) and `cb3` (node 255).
    trim = _draw_trim_ladder(b)

    _route(b, m1, q1, [m2a, m2b], q2, r2, m3_legs, q3, r1, trim)

    return b


def _trim_unit_site(node: int) -> tuple[int, int, bool]:
    """``(column, row, on_top)`` of the pad carrying ladder node ``node``.

    Node ``k`` is the junction *after* unit ``k`` in series order (node 0 is
    the ladder's own ``in``/``tn0`` terminal, node 255 its ``out``/``cb3``
    terminal), which is what ``design/bandgap_trim.sch``'s ``t001``-``t254``
    net names mean and what ``TRIM_STRAP_NODES`` is written in.

    The array is a column-major serpentine: column ``j`` holds units
    ``TRIM_COL_UNITS*j + 1 .. TRIM_COL_UNITS*(j+1)`` in series, running
    **bottom-to-top** in an even column and **top-to-bottom** in an odd one,
    so consecutive columns always meet at the end they share (top for an
    even/odd pair, bottom for an odd/even pair) and a single horizontal link
    box joins them. Each unit is drawn by ``draw_poly_res(..., legs=1)``,
    whose end A is always the bottom pad and end B always the top pad -- so
    "which pad carries node k" is a parity question, not a drawing
    difference, and every unit in the array is geometrically identical
    (which is the whole point: the ladder's binary weights are exact only
    because they are integer counts of one identical device, see
    ``design/bandgap_trim_network.md`` section 1).

    Derivation, for ``k >= 1``: unit ``k`` sits at series position
    ``c = k - 1``, hence column ``j = c // TRIM_COL_UNITS`` and in-column
    series position ``p = c % TRIM_COL_UNITS``. An even column's series
    position *is* its row; an odd column's is counted down from the top.
    Node ``k`` is that unit's downstream end, i.e. its top pad in an even
    column and its bottom pad in an odd one. Node 0 is the free bottom pad
    of column 0, row 0.
    """
    if node == 0:
        return (0, 0, False)
    series = node - 1
    col = series // TRIM_COL_UNITS
    pos = series % TRIM_COL_UNITS
    even = col % 2 == 0
    row = pos if even else TRIM_COL_UNITS - 1 - pos
    return (col, row, even)


def _draw_trim_ladder(b: Builder) -> dict:
    """Draw the 255-unit ``rppd`` trim ladder + its code-``TRIM_CODE``
    straps, returning ``{"node_pad": {node: pad}, "units": [...]}``.

    Every unit is a ``legs=1`` ``draw_poly_res`` call at the schematic's own
    ``w=2u``/``l=3.43u``, so each one is recognised by `klt`'s curated
    ``sg13g2`` deck as its own ``rppd`` device (the deck's resistor
    extractor needs exactly two un-marked ``GatPoly`` contact polygons per
    marked shape, which is exactly what one un-folded unit draws -- see
    ``layout/common.py::draw_poly_res``). 255 devices against the reference
    netlist's 255 ``XRU`` cards, one-to-one.
    """
    node_pad: dict[int, tuple[float, float, float, float]] = {}
    units: list[dict] = []
    for col in range(TRIM_COLS):
        for row in range(TRIM_COL_UNITS):
            x = TRIM_X0 + col * TRIM_PITCH_X
            y = TRIM_Y0 + row * TRIM_PITCH_Y
            # Net labels: only the two free ends carry a schematic net name
            # (`tn0`/`cb3`); every interior junction is an internal ladder
            # node, labeled `t<NNN>` exactly as design/bandgap_trim.sch
            # names it so the extracted netlist reads against the reference
            # by name as well as by topology.
            even = col % 2 == 0
            lower_node = (
                TRIM_COL_UNITS * col + (row if even else TRIM_COL_UNITS - row)
            )
            upper_node = lower_node + (1 if even else -1)
            units.append(
                draw_poly_res(
                    b, f"RU{min(lower_node, upper_node) + 1}", "rppd",
                    TRIM_UNIT_W, TRIM_UNIT_L, x, y,
                    end_a_net=_trim_net_name(lower_node),
                    end_b_net=_trim_net_name(upper_node),
                    legs=1,
                )
            )
    for node in range(TRIM_UNITS + 1):
        col, row, on_top = _trim_unit_site(node)
        unit = units[col * TRIM_COL_UNITS + row]
        node_pad[node] = unit["end_b_pad" if on_top else "end_a_pad"]

    _draw_trim_links(b, units)
    _draw_trim_straps(b, node_pad)
    b.label(
        L_TEXT,
        f"XTRIM({TRIM_UNITS}x rppd w={TRIM_UNIT_W}u l={TRIM_UNIT_L}u, "
        f"code {TRIM_CODE})",
        TRIM_X0 + (TRIM_COLS - 1) * TRIM_PITCH_X / 2,
        TRIM_Y0 + (TRIM_COL_UNITS - 1) * TRIM_PITCH_Y + TRIM_UNIT_L + 1.4,
    )
    return {"node_pad": node_pad, "units": units}


def _trim_net_name(node: int) -> str:
    """``design/bandgap_trim.sch``'s own name for ladder node ``node``."""
    if node == 0:
        return "tn0"
    if node == TRIM_UNITS:
        return "cb3"
    return f"t{node:03d}"


def _draw_trim_links(b: Builder, units: list[dict]) -> None:
    """Join the array's 254 series junctions with ``Metal1`` link boxes.

    Two kinds, both drawn on the same layer the unit terminal pads already
    use (so they merge with those pads rather than needing a via):

    * **vertical** -- one per adjacent row pair inside a column, bridging
      the ``TRIM_PITCH_Y - 4.43 = 0.2`` um gap between the lower unit's top
      pad and the upper unit's bottom pad. 14 per column x 17 = 238.
    * **horizontal** -- one per adjacent column pair, at the end the
      serpentine turns on (top when the left column index is even, bottom
      when it is odd), bridging the ``TRIM_PITCH_X - 2.4 = 0.3`` um gap
      between the two columns' pads at that row. 16.

    238 + 16 = 254 links, i.e. exactly the 255-unit series string's own
    internal junction count -- asserted below rather than trusted.
    """
    drawn = 0
    for col in range(TRIM_COLS):
        for row in range(TRIM_COL_UNITS - 1):
            lower = units[col * TRIM_COL_UNITS + row]["end_b_pad"]
            upper = units[col * TRIM_COL_UNITS + row + 1]["end_a_pad"]
            b.box(L_METAL1, lower[0], lower[3], lower[2], upper[1])
            drawn += 1
    for col in range(TRIM_COLS - 1):
        row = TRIM_COL_UNITS - 1 if col % 2 == 0 else 0
        key = "end_b_pad" if col % 2 == 0 else "end_a_pad"
        left = units[col * TRIM_COL_UNITS + row][key]
        right = units[(col + 1) * TRIM_COL_UNITS + row][key]
        b.box(L_METAL1, left[2], left[1], right[0], left[3])
        drawn += 1
    assert drawn == TRIM_UNITS - 1, f"{drawn} links for {TRIM_UNITS} units"


def _draw_trim_straps(b: Builder, node_pad: dict) -> None:
    """Draw the ``Metal2`` metal-option straps ``TRIM_CODE`` selects.

    Strap ``b`` is drawn when bit ``b`` of ``TRIM_CODE`` is **0** (link
    present, that binary group shorted out of the string) and omitted when
    it is 1 (link cut, the group carries current) -- the physical reading of
    ``design/bandgap_trim.sch``'s own
    ``{1e-3 + 1e12*(floor(trim_code/2^b) - 2*floor(trim_code/2^(b+1)))}``
    decode, whose ``1e-3`` branch is a closed link and whose ``1e12`` branch
    is an open one.

    Each drawn strap is a ``Via1``-``Metal2``-``Via1`` L-route (horizontal
    at the first tap's own pad row, then vertical at the second tap's own
    column) at ``TRIM_STRAP_W``. Overlapping is harmless and deliberately
    exploited: at any code the drawn straps form a single connected chain
    whenever they are consecutive, and at ``TRIM_CODE = 128`` all seven
    drawn straps are consecutive, so the whole strap network is one net
    (``tn0``) -- so no two strap segments ever need `metal2.space` from each
    other, and the long runs are free to cross the shorted-out units' own
    interior ``Metal1`` pads (different layer, no via, capacitive only; and
    those nodes carry no branch current precisely because they are shorted
    out).
    """
    for bit, (node_a, node_b) in enumerate(TRIM_STRAP_NODES):
        if (TRIM_CODE >> bit) & 1:
            continue  # link cut -- this group stays in circuit
        pad_a, pad_b = node_pad[node_a], node_pad[node_b]
        ax, ay = (pad_a[0] + pad_a[2]) / 2, (pad_a[1] + pad_a[3]) / 2
        bx, by = (pad_b[0] + pad_b[2]) / 2, (pad_b[1] + pad_b[3]) / 2
        via1_tap(b, ax, ay, size=VIA)
        if abs(bx - ax) > 1e-9:
            route_h(b, L_METAL2, ay, ax, bx, width=TRIM_STRAP_W)
        if abs(by - ay) > 1e-9:
            route_v(b, L_METAL2, bx, ay, by, width=TRIM_STRAP_W)
        via1_tap(b, bx, by, size=VIA)


def _tie_drains(b: Builder, legs: list[dict]) -> tuple[float, float, float, float]:
    """Join every leg's own drain pad (all at the same Y-band, one per
    parallel unit-device finger -- issue #149's decomposition) into a
    single Metal1 strip spanning the leftmost-to-rightmost pad, returning a
    combined "drain_pad"-shaped box the same routing helpers
    (``_riser``/``_tie_and_riser``) already use for a single-device branch.
    A single leg (M1's un-decomposed branch) is returned unchanged, no new
    geometry drawn."""
    if len(legs) == 1:
        return legs[0]["drain_pad"]
    y_lo = min(leg["drain_pad"][1] for leg in legs)
    y_hi = max(leg["drain_pad"][3] for leg in legs)
    x_lo = min(leg["drain_pad"][0] for leg in legs)
    x_hi = max(leg["drain_pad"][2] for leg in legs)
    b.box(L_METAL1, x_lo, y_lo, x_hi, y_hi)
    return (x_lo, y_lo, x_hi, y_hi)


def _route(
    b: Builder,
    m1: dict,
    q1: dict,
    m2_legs: list[dict],
    q2: dict,
    r2: dict,
    m3_legs: list[dict],
    q3: dict,
    r1: dict,
    trim: dict,
) -> None:
    """Wire every schematic net -- see this module's own docstring for the
    routing strategy. Each block below names the net it wires."""

    all_mos = [m1, *m2_legs, *m3_legs]

    # -- vdd: every leg's source pad, across all three branches (M1 plus
    # M2's/M3's decomposed unit fingers -- issue #149) --
    vdd_y_lo = min(m["source_pad"][1] for m in all_mos)
    vdd_y_hi = max(m["source_pad"][3] for m in all_mos)
    vdd_x_lo = min(m["source_pad"][0] for m in all_mos)
    vdd_x_hi = max(m["source_pad"][2] for m in all_mos)
    b.box(L_METAL1, vdd_x_lo, vdd_y_lo, vdd_x_hi, vdd_y_hi)
    # No new net-name label needed here: every draw_hv_mos call already
    # labeled its source pad "vdd" on Metal1.text (issue #20's draw_hv_mos
    # change) -- this box just merges those pads (plus the space between
    # them) into one physically-connected net; the existing labels ride
    # along automatically once merged.

    # -- fb: every leg's gate -- one continuous GatPoly bar spanning every
    # gate box (each already at the same Y-band; a bar merges with each
    # gate's own drawn poly, no contacts needed -- poly-to-poly routing
    # between recognised MOS gates is a supported connectivity pattern, see
    # layout/common.py's draw_gate_tab docstring and klayout_tools.extract's
    # own "ordinary poly routing between two recognised gates" comment).
    fb_y_lo = min(m["gate_y_lo"] for m in all_mos)
    fb_y_hi = max(m["gate_y_hi"] for m in all_mos)
    fb_y_center = (fb_y_lo + fb_y_hi) / 2
    fb_height = 0.3
    fb_x_lo = min(m["gate_box"][0] for m in all_mos)
    fb_x_hi = max(m["gate_box"][2] for m in all_mos)
    route_h(b, L_GATPOLY, fb_y_center, fb_x_lo, fb_x_hi, width=fb_height)

    # -- sns1: M1.drain, Q1.collector, Q1.base -- Q1 is diode-connected
    # (collector==base==sns1 in the schematic), but its own collector rail
    # (top) and base rail (bottom) are two separate drawn Metal1 shapes with
    # nothing tying them together -- a single vertical strip both joins them
    # and reaches up to M1's drain pad.
    sns1_x = (q1["collector_pad"][0] + q1["collector_pad"][2]) / 2
    route_v(b, L_METAL1, sns1_x, q1["base_pad"][1], m1["drain_pad"][3], width=TRUNK_W)

    # -- vss: Q1/Q2/Q3 emitters -- all already Metal2, all at the same
    # Y-band (le=0.9u is constant regardless of Nx) -- one horizontal bar.
    vss_y_lo = q1["emitter_pad"][1]
    vss_y_hi = q1["emitter_pad"][3]
    vss_x_lo = min(q1["emitter_pad"][0], q2["emitter_pad"][0], q3["emitter_pad"][0])
    vss_x_hi = max(q1["emitter_pad"][2], q2["emitter_pad"][2], q3["emitter_pad"][2])
    b.box(L_METAL2, vss_x_lo, vss_y_lo, vss_x_hi, vss_y_hi)

    # -- sns2: M2A/M2B.drain (tied together, issue #149), R2.end_a --
    # crosses the vdd/fb MOS-row bars, so the vertical riser is Metal2 (a
    # different layer cannot short against either Metal1/GatPoly bar),
    # landing on Metal1 at each end via Via1.
    sns2_drain = _tie_drains(b, m2_legs)
    _riser(b, sns2_drain, r2["end_a_pad"], jog_y=_pad_row(r2["end_a_pad"]))

    # -- cb2: R2.end_b, Q2.collector, Q2.base -- Q2's own collector/base tie
    # (mirrors sns1's Q1 tie) plus a riser up to R2's far end.
    cb2_x = (q2["collector_pad"][0] + q2["collector_pad"][2]) / 2 + 6.0
    _tie_and_riser(b, q2, cb2_x, r2["end_b_pad"], jog_y=_pad_row(r2["end_b_pad"]))

    # -- vref: M3A-M3C.drain (tied together, issue #149), R1.end_a --
    # mirrors sns2's design, on R1's own bottom pad row.
    vref_drain = _tie_drains(b, m3_legs)
    _riser(b, vref_drain, r1["end_a_pad"], jog_y=_pad_row(r1["end_a_pad"]))

    # -- tn0 (issue #272): R1.end_b -> the trim ladder's node-0 pad. R1's
    # odd leg count puts end B on its block's *top* row (y=41.37), clear of
    # the vref jog that occupies its bottom row (y=33.75) -- so this net
    # leaves upward on Metal1, crosses the empty band above the resistor
    # row to the channel just left of the ladder, and only then drops to
    # Metal2 for the vertical run down past the MOS/HBT rows.
    #
    # Metal1 for the horizontal leg is load-bearing, not incidental: `cb3`
    # below has to come the other way across the same band on Metal2 (over
    # the ladder's top), and its own Metal2 riser column (`TRIM_CB3_X`)
    # sits *between* R1 and the ladder. One of the two crossings has to be
    # on a different layer, and this is the one that can be -- both of its
    # endpoints are already Metal1 pads.
    tn0_pad = trim["node_pad"][0]
    tn0_x = (r1["end_b_pad"][0] + r1["end_b_pad"][2]) / 2
    route_v(b, L_METAL1, tn0_x, r1["end_b_pad"][1], TRIM_TN0_Y, width=TN0_TRUNK_W)
    # Both metals overrun the Via1 landing by half the cut plus
    # VIA_ENCLOSE: a run that *stops* at the via's centre leaves zero
    # enclosure on that side, which `metal1.enclosing.via1.1` (0.01 um
    # floor) catches -- it did, on this issue's own first `klt drc` pass.
    via_overrun = VIA / 2 + VIA_ENCLOSE
    route_h(b, L_METAL1, TRIM_TN0_Y, tn0_x, TRIM_TN0_VIA_X + via_overrun, width=TN0_TRUNK_W)
    via1_tap(b, TRIM_TN0_VIA_X, TRIM_TN0_Y, size=VIA)
    tn0_y = _pad_row(tn0_pad)
    route_v(b, L_METAL2, TRIM_TN0_VIA_X, tn0_y, TRIM_TN0_Y + via_overrun, width=METAL2_W)
    tn0_target_x = (tn0_pad[0] + tn0_pad[2]) / 2
    route_h(b, L_METAL2, tn0_y, TRIM_TN0_VIA_X, tn0_target_x, width=METAL2_W)
    via1_tap(b, tn0_target_x, tn0_y, size=VIA)

    # -- cb3 (issue #272): the ladder's node-255 pad, Q3.collector,
    # Q3.base. Same Q3 collector/base tie strap and Metal2 riser column
    # (`cb3_x`) the pre-#229 cell used -- what changed is the far end: the
    # jog now runs along the top of the ladder (`TRIM_CB3_TOP_Y`, 2.75um
    # above the array's own topmost pad) rather than across R1's bottom pad
    # row, because the net's other terminal moved from R1's end B to the
    # ladder's far corner.
    cb3_x = (q3["collector_pad"][0] + q3["collector_pad"][2]) / 2 + 3.0
    _tie_and_riser_over_top(b, q3, cb3_x, trim["node_pad"][TRIM_UNITS], TRIM_CB3_TOP_Y)


def _pad_row(pad: tuple[float, float, float, float]) -> float:
    """Y at which a Metal2 jog meets a folded resistor's terminal pad.

    Post-fold (issue #173) both of a resistor's Metal1 terminal pads hang
    *below* the block's own bottom edge, in the band
    ``[y0 - RES_HEAD_UM - 0.1, y0]``, rather than sitting on the bar's
    centreline at each end of a long horizontal body. So the Via1 that drops
    a Metal2 jog onto a pad has to land inside that band -- this returns its
    mid-line, which leaves ~0.125um of Metal1 enclosure above and below the
    ``VIA``-sized cut (floor: ``metal1.enclosing.via1.1``, 0.01um) and keeps
    the jog itself clear of the resistor core's own bottom edge.

    The pre-fold code passed ``pad[1] + 1.15`` here, a literal derived from
    the old straight bar's ``w=2u`` end pad; that expression now lands
    *above* the pad, inside the folded core.
    """
    return (pad[1] + pad[3]) / 2


def _riser(b: Builder, drain_pad: tuple[float, float, float, float], target_pad: tuple[float, float, float, float], jog_y: float) -> None:
    """MOS-drain-to-resistor-pad route: Via1 up from ``drain_pad`` to a
    Metal2 riser, a Metal2 horizontal jog at ``jog_y``, Via1 back down to
    ``target_pad``. Crosses the vdd/fb MOS-row bars safely on Metal2 (see
    this module's own docstring)."""
    x = (drain_pad[0] + drain_pad[2]) / 2
    via_y = (drain_pad[1] + drain_pad[3]) / 2
    via1_tap(b, x, via_y, size=VIA)
    route_v(b, L_METAL2, x, drain_pad[1], jog_y, width=METAL2_W)
    target_x = (target_pad[0] + target_pad[2]) / 2
    route_h(b, L_METAL2, jog_y, x, target_x, width=METAL2_W)
    via1_tap(b, target_x, jog_y, size=VIA)


def _tie_and_riser_over_top(
    b: Builder,
    hbt: dict,
    tie_x: float,
    target_pad: tuple[float, float, float, float],
    top_y: float,
) -> None:
    """``_tie_and_riser`` with the jog carried *over* the trim ladder
    (issue #272) instead of landing on a pad row inside the device field.

    Same Q3 collector+base ``Metal1`` tie strap and same ``Via1``-to-Metal2
    riser as ``_tie_and_riser``; the difference is that the Metal2 run goes
    all the way up to ``top_y`` (above every shape in the ladder array),
    crosses to the target's own column there, and drops back down to the
    target pad -- so the only thing it passes over on the way is the array's
    own ``GatPoly``/``Metal1`` geometry, on a different layer, with no via.
    """
    tie_y_lo = hbt["base_pad"][1]
    via_y_lo = hbt["collector_pad"][3]
    via_y_hi = via_y_lo + VIA
    route_v(b, L_METAL1, tie_x, tie_y_lo, via_y_hi + VIA_ENCLOSE, width=TRUNK_W)
    via_y = (via_y_lo + via_y_hi) / 2
    via1_tap(b, tie_x, via_y, size=VIA)
    route_v(b, L_METAL2, tie_x, via_y_lo, top_y, width=METAL2_W)
    target_x = (target_pad[0] + target_pad[2]) / 2
    target_y = _pad_row(target_pad)
    route_h(b, L_METAL2, top_y, tie_x, target_x, width=METAL2_W)
    route_v(b, L_METAL2, target_x, target_y, top_y, width=METAL2_W)
    via1_tap(b, target_x, target_y, size=VIA)


def _tie_and_riser(b: Builder, hbt: dict, tie_x: float, target_pad: tuple[float, float, float, float], jog_y: float) -> None:
    """Diode-connected-HBT-to-resistor-pad route: a Metal1 tie strap joining
    ``hbt``'s collector+base pads (its own diode connection has no wiring
    between the two rails otherwise -- same gap ``sns1`` above fixes for
    Q1), extended slightly past the collector pad to host a Via1 up to a
    Metal2 riser, then the same jog/Via1-back-down pattern as ``_riser``."""
    tie_y_lo = hbt["base_pad"][1]
    via_y_lo = hbt["collector_pad"][3]
    via_y_hi = via_y_lo + VIA
    route_v(b, L_METAL1, tie_x, tie_y_lo, via_y_hi + VIA_ENCLOSE, width=TRUNK_W)
    via_y = (via_y_lo + via_y_hi) / 2
    via1_tap(b, tie_x, via_y, size=VIA)
    route_v(b, L_METAL2, tie_x, via_y_lo, jog_y, width=METAL2_W)
    target_x = (target_pad[0] + target_pad[2]) / 2
    route_h(b, L_METAL2, jog_y, tie_x, target_x, width=METAL2_W)
    via1_tap(b, target_x, jog_y, size=VIA)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
