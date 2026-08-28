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
(``XM1``/``XQ1``/``XM2``/``XR2``/``XQ2``/``XM3``/``XR1``/``XQ3``):

    M1 sg13_hv_pmos w=10u l=1u   -- branch 1 mirror leg (vdd/fb -> sns1)
    Q1 npn13G2 Nx=1              -- branch 1, diode-connected (sns1 -> vss)
    M2 sg13_hv_pmos w=10u l=1u   -- branch 2 mirror leg (vdd/fb -> sns2)
    R2 rppd w=2u l=82.7u         -- PTAT resistor (sns2 -> cb2)
    Q2 npn13G2 Nx=8              -- branch 2, diode-connected (cb2 -> vss)
    M3 sg13_hv_pmos w=10u l=1u   -- output branch mirror leg (vdd/fb -> vref)
    R1 rppd w=2u l=511u          -- summing resistor (vref -> cb3)
    Q3 npn13G2 Nx=1              -- output branch, diode-connected (cb3 -> vss)

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
unfixable by routing), and, specific to this cell, `M1`/`M2`/`M3` are
perfectly symmetric at the recognized-device level (identical `w`/`l`,
distinguished in the real schematic only by the downstream bipolar/
resistor devices this deck cannot see) -- a graph automorphism no amount of
routing or `klt lvs`'s own `hints.same_nets` can resolve (verified: explicit
hints were tried and rejected by the comparer, see the README). The
routing itself is complete and verified correct (every schematic net is now
a single physically-connected shape, confirmed via `klt extract`'s own
net/device breakdown) -- the remaining ``device.unmatched``/``net.unmatched``
findings are attributed to these two deck-level facts, not a routing gap.
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


def build() -> Builder:
    b = Builder(TOP_CELL)

    mos_y = 22.0
    hbt_y = 0.0
    res_y = 40.0

    # Branch 1: M1 -> Q1, no series resistor (Q1 sensed directly at sns1).
    x1 = 0.0
    m1 = draw_hv_mos(b, "M1", "pmos", 10.0, 1.0, x1, mos_y, gate_net="fb", source_net="vdd", drain_net="sns1")
    q1 = draw_npn13g2(b, "Q1", 1, x1, hbt_y, collector_net="sns1", base_net="sns1", emitter_net="vss")

    # Branch 2: M2 -> R2 -> Q2 (Nx=8, sets the PTAT delta-VBE leg).
    x2 = 45.0
    m2 = draw_hv_mos(b, "M2", "pmos", 10.0, 1.0, x2, mos_y, gate_net="fb", source_net="vdd", drain_net="sns2")
    q2 = draw_npn13g2(b, "Q2", 8, x2, hbt_y, collector_net="cb2", base_net="cb2", emitter_net="vss")
    r2 = draw_poly_res(b, "R2", "rppd", 2.0, 82.7, 0.0, res_y, end_a_net="sns2", end_b_net="cb2")

    # Output branch: M3 -> R1 -> Q3, vref is the mirror node directly.
    x3 = 110.0
    m3 = draw_hv_mos(b, "M3", "pmos", 10.0, 1.0, x3, mos_y, gate_net="fb", source_net="vdd", drain_net="vref")
    q3 = draw_npn13g2(b, "Q3", 1, x3, hbt_y, collector_net="cb3", base_net="cb3", emitter_net="vss")
    # R1 is drawn as a long straight bar (l=511u, see draw_poly_res's own
    # docstring -- resized from 694.5u to match design/bandgap_core.sch's
    # own R1/R2 retune, issue #134/PR #136, per issue #137) on its own row
    # so it does not overlap the compact devices above.
    r1 = draw_poly_res(b, "R1", "rppd", 2.0, 511.0, 0.0, res_y + 20.0, end_a_net="vref", end_b_net="cb3")

    _route(b, m1, q1, m2, q2, r2, m3, q3, r1)

    return b


def _route(b: Builder, m1: dict, q1: dict, m2: dict, q2: dict, r2: dict, m3: dict, q3: dict, r1: dict) -> None:
    """Wire every schematic net -- see this module's own docstring for the
    routing strategy. Each block below names the net it wires."""

    # -- vdd: M1.source, M2.source, M3.source (all on the MOS source band) --
    vdd_y_lo = min(m1["source_pad"][1], m2["source_pad"][1], m3["source_pad"][1])
    vdd_y_hi = max(m1["source_pad"][3], m2["source_pad"][3], m3["source_pad"][3])
    vdd_x_lo = min(m1["source_pad"][0], m2["source_pad"][0], m3["source_pad"][0])
    vdd_x_hi = max(m1["source_pad"][2], m2["source_pad"][2], m3["source_pad"][2])
    b.box(L_METAL1, vdd_x_lo, vdd_y_lo, vdd_x_hi, vdd_y_hi)
    # No new net-name label needed here: M1/M2/M3's own draw_hv_mos calls
    # already labeled their source pads "vdd" on Metal1.text (issue #20's
    # draw_hv_mos change) -- this box just merges those three pads (plus
    # the space between them) into one physically-connected net; the
    # existing labels ride along automatically once merged.

    # -- fb: M1.gate, M2.gate, M3.gate -- one continuous GatPoly bar spanning
    # all three gate boxes (each already at the same Y-band; a bar merges
    # with each gate's own drawn poly, no contacts needed -- poly-to-poly
    # routing between recognised MOS gates is a supported connectivity
    # pattern, see layout/common.py's draw_gate_tab docstring and
    # klayout_tools.extract's own "ordinary poly routing between two
    # recognised gates" comment).
    fb_y_lo = min(m1["gate_y_lo"], m2["gate_y_lo"], m3["gate_y_lo"])
    fb_y_hi = max(m1["gate_y_hi"], m2["gate_y_hi"], m3["gate_y_hi"])
    fb_y_center = (fb_y_lo + fb_y_hi) / 2
    fb_height = 0.3
    fb_x_lo = min(m1["gate_box"][0], m2["gate_box"][0], m3["gate_box"][0])
    fb_x_hi = max(m1["gate_box"][2], m2["gate_box"][2], m3["gate_box"][2])
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

    # -- sns2: M2.drain, R2.end_a -- crosses the vdd/fb MOS-row bars, so the
    # vertical riser is Metal2 (a different layer cannot short against
    # either Metal1/GatPoly bar), landing on Metal1 at each end via Via1.
    _riser(b, m2["drain_pad"], r2["end_a_pad"], jog_y=r2["end_a_pad"][1] + 1.15)

    # -- cb2: R2.end_b, Q2.collector, Q2.base -- Q2's own collector/base tie
    # (mirrors sns1's Q1 tie) plus a riser up to R2's far end.
    cb2_x = (q2["collector_pad"][0] + q2["collector_pad"][2]) / 2 + 6.0
    _tie_and_riser(b, q2, cb2_x, r2["end_b_pad"], jog_y=r2["end_b_pad"][1] + 1.15)

    # -- vref: M3.drain, R1.end_a -- mirrors sns2's design, on R1's row.
    _riser(b, m3["drain_pad"], r1["end_a_pad"], jog_y=r1["end_a_pad"][1] + 1.15)

    # -- cb3: R1.end_b, Q3.collector, Q3.base -- mirrors cb2's design.
    cb3_x = (q3["collector_pad"][0] + q3["collector_pad"][2]) / 2 + 3.0
    _tie_and_riser(b, q3, cb3_x, r1["end_b_pad"], jog_y=r1["end_b_pad"][1] + 1.15)


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
