#!/usr/bin/env python3
"""Generate ``bandgap_amp.gds`` -- physical layout of ``design/bandgap_amp.sch``.

Same construction pattern as ``layout/bandgap_core/generate.py``/
``layout/bandgap_startup/generate.py`` -- manual ``klayout.db`` construction
via ``layout/common.py``'s shared primitives. See ``layout/common.py``'s
module docstring for the full provenance note (why a PDK-native PCell run
was not used).

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_amp/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against ``design/netlist/bandgap_amp.spice``
(a 9-device pure-CMOS 2-stage OTA -- no bipolar/resistor devices, unlike
``bandgap_core``/``bandgap_startup``):

    MTAIL sg13_hv_pmos w=10u l=1u  -- tail current source (gate=out, vdd->tail)
    MP1   sg13_hv_pmos w=20u l=1u  -- diff-pair leg 1 (gate=in_p, tail->d1)
    MP2   sg13_hv_pmos w=20u l=1u  -- diff-pair leg 2 (gate=in_n, tail->d2)
    MP3   sg13_hv_pmos w=10u l=1u  -- 2nd-stage mirror diode (gate=drain=pn)
    MP4   sg13_hv_pmos w=10u l=1u  -- 2nd-stage mirror output (gate=pn, vdd->out)
    MN1   sg13_hv_nmos w=10u l=1u  -- 1st-stage load diode 1 (gate=source=d1)
    MN2   sg13_hv_nmos w=10u l=1u  -- 1st-stage load diode 2 (gate=source=d2)
    MN3   sg13_hv_nmos w=10u l=1u  -- 2nd-stage NMOS (gate=d1, out->vss)
    MN4   sg13_hv_nmos w=10u l=1u  -- 2nd-stage NMOS (gate=d2, pn->vss)

**Body ties (documented simplification, LVS *resolution* deferred -- #169).**
``layout/common.py``'s ``draw_hv_mos`` bridges a device's tap island to
whichever *pad* (source, for pmos; drain, for nmos) its own ``tap_at_source``
convention selects -- a bridge that is only electrically correct when
``body_net`` equals that same pad's own net (every existing caller in this
repo, ``bandgap_core``/``bandgap_startup``, satisfies this by construction).
``MP1``/``MP2``'s *real* schematic body tie is ``vdd`` -- distinct from
either of their own channel nets (``tail``/``d1`` or ``tail``/``d2``) -- so
passing ``body_net="vdd"`` explicitly would make ``draw_hv_mos`` bridge its
tap (correctly labeled ``vdd``) directly into the ``tail``-net source pad,
physically *shorting* ``tail`` to ``vdd``. Every call below instead leaves
``body_net`` at its default (source_net for pmos, drain_net for nmos) --
i.e. every device's tap ties to its own already-drawn channel pad, exactly
as ``draw_hv_mos`` was designed for every other call site in this repo. For
``MP1``/``MP2`` this means the drawn tap differs from the schematic's real
``vdd`` body tie (tied to ``tail`` instead) -- a known, documented
simplification, consistent with every other "what this layout is / is not"
simplification already catalogued in ``layout/README.md``, and explicitly
out of scope to *resolve* here (issue #169 scopes LVS fixing out; see this
file's own header comment and the issue's acceptance criteria). ``klt lvs``
*was* run once for this cell, and the two ``device.unmatched`` findings it
reports on ``MP1``/``MP2`` are exactly this simplification showing up -- a
follow-up LVS pass would need to address it, most likely by fixing the
underlying assumption in ``draw_hv_mos`` itself.

**Floorplan.** PMOS row (``y=30``, left to right): MP1, MP2, MTAIL, MP3, MP4
-- ordered so ``vdd``-carrying source pads (MTAIL/MP3/MP4, all draw ``vdd``
at their own *source*, i.e. top-of-row) sit contiguously, and
``tail``-carrying source pads (MP1/MP2) sit contiguously in a separate group
-- letting both be a single straight Metal1 bar each, with no crossing.
NMOS row (``y=0``): MN1 under MP1 (``d1``), MN2 under MP2 (``d2``), MN3
under MP4 (``out``), MN4 further right (its own ``d2``-net gate and
``pn``-net source pad need cross-column routing regardless of placement).

**Routing.** ``vdd``/``tail`` are each a single Metal1 bar across their own
contiguous source-pad group (no vias needed). ``vss`` is a single Metal1 bar
across all four NMOS drain pads. ``d1``/``d2``/``out`` are single vertical
Metal1 trunks straight through the gap between the two rows (aligned
columns), each ``CROSS_TRUNK_W`` wide for comfortable Via1 landing margin.
``MTAIL``'s own ``tail``-net drain pad (bottom of row, opposite band from
MP1/MP2's ``tail``-net source pads) needs one riser up into the ``tail``
bar. ``MN1``/``MN2``'s own diode-connected gates (``d1``/``d2``, tied to
their own source pad) and ``MP3``'s own diode-connected gate (``pn``, tied
to its own drain pad) need a local ``draw_gate_tab`` + short Metal1 tie
(same pattern ``bandgap_startup``'s ``MKFB`` established). ``MN3``'s gate
(``d1``), ``MN4``'s gate (``d2``), and ``MTAIL``'s gate (``out``) are each
routed to their target trunk via a Metal2 riser/jog/riser, at a distinct
jog height per net (``JOG_D1 < JOG_D2 < JOG_OUT < JOG_PN``, chosen so no two
nets' Metal2 jogs can cross each other -- see ``_route``'s own inline
comment for the exact non-crossing argument). ``pn`` (``MP3``'s own tie
point, ``MP4``'s poly-connected gate, and ``MN4``'s source pad) is routed
the same way, plus a continuous ``GatPoly`` bar tying ``MP3``'s and ``MP4``'s
gates together directly (poly-to-poly, same idiom as ``bandgap_core``'s
``fb`` net).

``in_p``/``in_n`` (``MP1``/``MP2``'s own gates) are each a single-terminal
net within this cell -- no *internal* routing needed (a single-terminal net
is already complete; see ``bandgap_startup/generate.py``'s own docstring for
the same reasoning about its ``vdd``/``sns1``/``fb`` external pins). Each
still gets a ``draw_gate_tab`` bringing it out to a real Metal1 pad (a bare
``GatPoly`` gate has no metal contact of its own otherwise) -- needed so
``bandgap_top`` (issue #169) can route each one from outside this cell.

DRC verification (``klt drc --deck sg13g2``) and LVS scope are tracked in
``layout/README.md``. **Resolving LVS is explicitly deferred** (issue #169's
own scope boundary), but ``klt lvs`` itself was run once against this cell --
the repo's CI evidence-format gate requires a committed ``lvs_report.json`` --
and its honest ``mismatch`` result (2 ``device.unmatched`` findings on
``MP1``/``MP2``, the body-tie simplification above) is committed as-is.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import (  # noqa: E402
    L_GATPOLY,
    L_METAL1,
    L_METAL2,
    Builder,
    draw_gate_tab,
    draw_hv_mos,
    route_h,
    route_v,
    via1_tap,
)

TOP_CELL = "bandgap_amp"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_amp.gds")

# Routing widths/sizes -- same values bandgap_core/bandgap_startup already
# verified DRC-clean against the curated sg13g2 deck's own metal1.width.1/
# metal2.width.1/via1.width.1 floors (see layout/common.py's route_h/
# route_v/via1_tap docstrings for the exact clearance each leaves).
TRUNK_W = 0.3
# Wider than TRUNK_W for the three full-gap vertical trunks (d1/d2/out) --
# these each host a mid-span Via1 landing (from a cross-column Metal2 jog),
# so the extra width leaves generous metal1.enclosing.via1.1 margin at that
# landing point without needing a separate widened "landing pad" shape.
CROSS_TRUNK_W = 0.6
VIA = 0.25
METAL2_W = 0.35
VIA_ENCLOSE = 0.05

PMOS_Y = 30.0
NMOS_Y = 0.0

# Jog heights for the four Metal2 cross-column nets (MN3.gate->d1 trunk,
# MN4.gate->d2 trunk, MTAIL.gate->out trunk, MP3/MP4.tie->MN4.source pn
# net). Strictly increasing (JOG_D1 < JOG_D2 < JOG_OUT < JOG_PN) -- see
# _route()'s own comment for why this ordering guarantees no two nets'
# Metal2 jogs can cross each other.
JOG_D1 = 5.0
JOG_D2 = 9.0
JOG_OUT = 13.0
JOG_PN = 17.0


def build() -> Builder:
    b = Builder(TOP_CELL)

    # PMOS row, left to right: MP1, MP2, MTAIL, MP3, MP4 -- ordered so the
    # vdd-carrying source pads (MTAIL/MP3/MP4) are contiguous, and the
    # tail-carrying source pads (MP1/MP2) are contiguous in their own group
    # (see this module's own docstring "Floorplan").
    mp1 = draw_hv_mos(b, "MP1", "pmos", 20.0, 1.0, 0.0, PMOS_Y, gate_net="in_p", source_net="tail", drain_net="d1")
    mp2 = draw_hv_mos(b, "MP2", "pmos", 20.0, 1.0, 40.0, PMOS_Y, gate_net="in_n", source_net="tail", drain_net="d2")
    mtail = draw_hv_mos(b, "MTAIL", "pmos", 10.0, 1.0, 80.0, PMOS_Y, gate_net="out", source_net="vdd", drain_net="tail")
    mp3 = draw_hv_mos(b, "MP3", "pmos", 10.0, 1.0, 110.0, PMOS_Y, gate_net="pn", source_net="vdd", drain_net="pn")
    mp4 = draw_hv_mos(b, "MP4", "pmos", 10.0, 1.0, 140.0, PMOS_Y, gate_net="pn", source_net="vdd", drain_net="out")

    # NMOS row -- MN1 under MP1 (d1), MN2 under MP2 (d2), MN3 under MP4
    # (out); MN4 placed further right (its own d2-gate and pn-source pads
    # need cross-column routing regardless of placement -- see docstring).
    mn1 = draw_hv_mos(b, "MN1", "nmos", 10.0, 1.0, 0.0, NMOS_Y, gate_net="d1", source_net="d1", drain_net="vss")
    mn2 = draw_hv_mos(b, "MN2", "nmos", 10.0, 1.0, 40.0, NMOS_Y, gate_net="d2", source_net="d2", drain_net="vss")
    mn3 = draw_hv_mos(b, "MN3", "nmos", 10.0, 1.0, 140.0, NMOS_Y, gate_net="d1", source_net="out", drain_net="vss")
    mn4 = draw_hv_mos(b, "MN4", "nmos", 10.0, 1.0, 200.0, NMOS_Y, gate_net="d2", source_net="pn", drain_net="vss")

    _route(b, mp1, mp2, mtail, mp3, mp4, mn1, mn2, mn3, mn4)

    # in_p/in_n (MP1.gate/MP2.gate) are single-terminal *within this cell*
    # (see this module's own docstring), but bandgap_top (issue #169) needs
    # a real Metal1 pad to route each one to sns2/sns1 from outside this
    # cell -- a bare GatPoly gate has no metal contact of its own otherwise.
    # Extended away from every other device (MP1 is the row's own leftmost
    # device -- extend further left; MP2 extends right, into the >20um-wide
    # clear gap before MTAIL) -- no further routing needed, same
    # single-terminal-net reasoning as every other bare boundary pin.
    draw_gate_tab(b, mp1["gate_box"][0], PMOS_Y, "in_p", side="left")
    draw_gate_tab(b, mp2["gate_box"][2], PMOS_Y, "in_n", side="right")

    return b


def _tie_boxes(b: Builder, pad_a: tuple[float, float, float, float], pad_b: tuple[float, float, float, float]) -> None:
    """Draw the Metal1 bounding-box hull of two same-net pads, connecting
    them -- the same "merge by bounding rectangle" idiom
    ``bandgap_core/generate.py``'s own ``_tie_drains`` uses. Safe here
    because every call site below passes two pads that are already close
    together with nothing else of a different net inside their hull (each
    is a single device's own gate-tab-to-channel-pad local tie)."""
    x0 = min(pad_a[0], pad_b[0])
    y0 = min(pad_a[1], pad_b[1])
    x1 = max(pad_a[2], pad_b[2])
    y1 = max(pad_a[3], pad_b[3])
    b.box(L_METAL1, x0, y0, x1, y1)


def _route(
    b: Builder,
    mp1: dict,
    mp2: dict,
    mtail: dict,
    mp3: dict,
    mp4: dict,
    mn1: dict,
    mn2: dict,
    mn3: dict,
    mn4: dict,
) -> None:
    """Wire every schematic net -- see this module's own docstring for the
    overall strategy and the non-crossing argument for the four Metal2
    cross-column jogs.

    **Non-crossing argument (JOG_D1 < JOG_D2 < JOG_OUT < JOG_PN).** Each of
    the four cross-column nets (d1, d2, out, pn) draws exactly one local
    Metal2 vertical (from its own gate-tab/tie point up or down to its own
    jog height) plus one Metal2 horizontal (at its own jog height, spanning
    from its tab's X to its target trunk's X). Two nets' Metal2 shapes can
    only collide if one net's horizontal (at height J_A, spanning X-range
    R_A) crosses another net's vertical (at column X_B, spanning height
    range [tab_y_B, J_B]) -- i.e. X_B in R_A and J_A in [tab_y_B, J_B].
    Every local vertical below starts near the NMOS row (tab_y ~ 0) or
    the PMOS row (tie point ~29-30) and runs to its OWN jog height, so its
    height range always has J_B as one endpoint. Choosing every jog height
    distinct AND strictly ordered D1 < D2 < OUT < PN, together with each
    net's own tab column lying outside every *lower*-numbered net's own
    horizontal X-range (verified for this exact floorplan below, column by
    column), keeps every horizontal clear of every other net's vertical.
    """
    # -- vss: all four NMOS drain pads, one Metal1 bar. --
    vss_x_lo = min(m["drain_pad"][0] for m in [mn1, mn2, mn3, mn4])
    vss_x_hi = max(m["drain_pad"][2] for m in [mn1, mn2, mn3, mn4])
    vss_y_lo = min(m["drain_pad"][1] for m in [mn1, mn2, mn3, mn4])
    vss_y_hi = max(m["drain_pad"][3] for m in [mn1, mn2, mn3, mn4])
    b.box(L_METAL1, vss_x_lo, vss_y_lo, vss_x_hi, vss_y_hi)

    # -- vdd: MTAIL/MP3/MP4's own source pads -- contiguous by
    # construction (floorplan ordering), one Metal1 bar. --
    vdd_x_lo = min(m["source_pad"][0] for m in [mtail, mp3, mp4])
    vdd_x_hi = max(m["source_pad"][2] for m in [mtail, mp3, mp4])
    vdd_y_lo = min(m["source_pad"][1] for m in [mtail, mp3, mp4])
    vdd_y_hi = max(m["source_pad"][3] for m in [mtail, mp3, mp4])
    b.box(L_METAL1, vdd_x_lo, vdd_y_lo, vdd_x_hi, vdd_y_hi)

    # -- tail (top band): MP1/MP2's own source pads -- contiguous, one
    # Metal1 bar, disjoint in X from the vdd bar above. --
    tail_x_lo = min(m["source_pad"][0] for m in [mp1, mp2])
    tail_x_hi = max(m["source_pad"][2] for m in [mp1, mp2])
    tail_y_lo = min(m["source_pad"][1] for m in [mp1, mp2])
    tail_y_hi = max(m["source_pad"][3] for m in [mp1, mp2])
    b.box(L_METAL1, tail_x_lo, tail_y_lo, tail_x_hi, tail_y_hi)

    # -- tail (bottom band): MTAIL's own drain pad needs one riser up into
    # the tail bar above -- via1 up from MTAIL.drain, Metal2 up to a jog
    # comfortably above every PMOS device's own tap ring (>=31.49, see
    # layout/common.py's TAP_* constants) but still below the vdd/tail
    # bars themselves are not reached (bars sit at y<=30.9, well below the
    # tap band -- this riser only needs to clear the tap band, not avoid
    # the bars, since the final via lands INSIDE the tail bar deliberately).
    tail_jog_y = 32.0
    mtail_x = (mtail["drain_pad"][0] + mtail["drain_pad"][2]) / 2
    mtail_via_y = (mtail["drain_pad"][1] + mtail["drain_pad"][3]) / 2
    via1_tap(b, mtail_x, mtail_via_y, size=VIA)
    route_v(b, L_METAL2, mtail_x, mtail_via_y, tail_jog_y, width=METAL2_W)
    tail_bar_x = (mp1["source_pad"][0] + mp2["source_pad"][2]) / 2
    route_h(b, L_METAL2, tail_jog_y, mtail_x, tail_bar_x, width=METAL2_W)
    tail_landing_y = (tail_y_lo + tail_y_hi) / 2
    route_v(b, L_METAL2, tail_bar_x, tail_jog_y, tail_landing_y, width=METAL2_W)
    via1_tap(b, tail_bar_x, tail_landing_y, size=VIA)

    # -- d1: MP1.drain -> straight Metal1 trunk -> MN1.source (aligned
    # columns). --
    d1_x = (mp1["drain_pad"][0] + mp1["drain_pad"][2]) / 2
    route_v(b, L_METAL1, d1_x, mp1["drain_pad"][1], mn1["source_pad"][3], width=CROSS_TRUNK_W)

    # -- d2: MP2.drain -> straight Metal1 trunk -> MN2.source. --
    d2_x = (mp2["drain_pad"][0] + mp2["drain_pad"][2]) / 2
    route_v(b, L_METAL1, d2_x, mp2["drain_pad"][1], mn2["source_pad"][3], width=CROSS_TRUNK_W)

    # -- out: MP4.drain -> straight Metal1 trunk -> MN3.source (aligned
    # columns, both at x=140). --
    out_x = (mp4["drain_pad"][0] + mp4["drain_pad"][2]) / 2
    route_v(b, L_METAL1, out_x, mp4["drain_pad"][1], mn3["source_pad"][3], width=CROSS_TRUNK_W)

    # -- MN1's own diode connection (gate=source=d1): local tab + tie. --
    mn1_tab = draw_gate_tab(b, mn1["gate_box"][0], NMOS_Y, "d1", side="left")
    _tie_boxes(b, mn1_tab, mn1["source_pad"])

    # -- MN2's own diode connection (gate=source=d2): local tab + tie. --
    mn2_tab = draw_gate_tab(b, mn2["gate_box"][0], NMOS_Y, "d2", side="left")
    _tie_boxes(b, mn2_tab, mn2["source_pad"])

    # -- MP3's own diode connection (gate=drain=pn): local tab + tie. --
    mp3_tab = draw_gate_tab(b, mp3["gate_box"][0], PMOS_Y, "pn", side="left")
    _tie_boxes(b, mp3_tab, mp3["drain_pad"])

    # -- pn (poly leg): MP3.gate -- MP4.gate, a continuous GatPoly bar
    # spanning both gates directly (poly-to-poly, same idiom as
    # bandgap_core's fb net). --
    pn_gate_y_lo = min(mp3["gate_box"][1], mp4["gate_box"][1])
    pn_gate_y_hi = max(mp3["gate_box"][3], mp4["gate_box"][3])
    pn_gate_y_center = (pn_gate_y_lo + pn_gate_y_hi) / 2
    route_h(b, L_GATPOLY, pn_gate_y_center, mp3["gate_box"][0], mp4["gate_box"][2], width=pn_gate_y_hi - pn_gate_y_lo)

    # -- MN3.gate (d1) -> d1 trunk: Metal2 riser/jog/riser, jog=JOG_D1
    # (the lowest jog -- see _route's own non-crossing argument). --
    mn3_tab = draw_gate_tab(b, mn3["gate_box"][0], NMOS_Y, "d1", side="left")
    mn3_tab_x = (mn3_tab[0] + mn3_tab[2]) / 2
    mn3_tab_y = (mn3_tab[1] + mn3_tab[3]) / 2
    via1_tap(b, mn3_tab_x, mn3_tab_y, size=VIA)
    route_v(b, L_METAL2, mn3_tab_x, mn3_tab_y, JOG_D1, width=METAL2_W)
    route_h(b, L_METAL2, JOG_D1, mn3_tab_x, d1_x, width=METAL2_W)
    via1_tap(b, d1_x, JOG_D1, size=VIA)

    # -- MN4.gate (d2) -> d2 trunk: Metal2 riser/jog/riser, jog=JOG_D2. --
    mn4_tab = draw_gate_tab(b, mn4["gate_box"][0], NMOS_Y, "d2", side="left")
    mn4_tab_x = (mn4_tab[0] + mn4_tab[2]) / 2
    mn4_tab_y = (mn4_tab[1] + mn4_tab[3]) / 2
    via1_tap(b, mn4_tab_x, mn4_tab_y, size=VIA)
    route_v(b, L_METAL2, mn4_tab_x, mn4_tab_y, JOG_D2, width=METAL2_W)
    route_h(b, L_METAL2, JOG_D2, mn4_tab_x, d2_x, width=METAL2_W)
    via1_tap(b, d2_x, JOG_D2, size=VIA)

    # -- MTAIL.gate (out) -> out trunk: Metal2 riser/jog/riser,
    # jog=JOG_OUT. --
    mtail_out_tab = draw_gate_tab(b, mtail["gate_box"][2], PMOS_Y, "out", side="right")
    mtail_tab_x = (mtail_out_tab[0] + mtail_out_tab[2]) / 2
    mtail_tab_y = (mtail_out_tab[1] + mtail_out_tab[3]) / 2
    via1_tap(b, mtail_tab_x, mtail_tab_y, size=VIA)
    route_v(b, L_METAL2, mtail_tab_x, mtail_tab_y, JOG_OUT, width=METAL2_W)
    route_h(b, L_METAL2, JOG_OUT, mtail_tab_x, out_x, width=METAL2_W)
    via1_tap(b, out_x, JOG_OUT, size=VIA)

    # -- pn (metal leg): MP3's own tie point -> MN4.source, Metal2
    # riser/jog/riser, jog=JOG_PN (the highest jog -- see _route's own
    # non-crossing argument). --
    pn_tie_x = (mp3["drain_pad"][0] + mp3["drain_pad"][2]) / 2
    pn_tie_y = (mp3["drain_pad"][1] + mp3["drain_pad"][3]) / 2
    via1_tap(b, pn_tie_x, pn_tie_y, size=VIA)
    route_v(b, L_METAL2, pn_tie_x, pn_tie_y, JOG_PN, width=METAL2_W)
    mn4_source_x = (mn4["source_pad"][0] + mn4["source_pad"][2]) / 2
    route_h(b, L_METAL2, JOG_PN, pn_tie_x, mn4_source_x, width=METAL2_W)
    mn4_source_y = (mn4["source_pad"][1] + mn4["source_pad"][3]) / 2
    route_v(b, L_METAL2, mn4_source_x, JOG_PN, mn4_source_y, width=METAL2_W)
    via1_tap(b, mn4_source_x, mn4_source_y, size=VIA)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
