#!/usr/bin/env python3
"""Generate ``bandgap_startup.gds`` -- layout of ``design/bandgap_startup.sch``.

Same construction pattern as ``layout/bandgap_core/generate.py`` -- see that
file and ``layout/common.py``'s module docstring for the full provenance
note (manual ``klayout.db`` construction; why a PDK-native PCell run was not
used for this issue).

Run from the repo root::

    uv run --with klayout python3 layout/bandgap_startup/generate.py

Devices instantiated, one-to-one against
``design/netlist/bandgap_startup.spice``:

    RPU    rhigh w=1u l=1411.3u    -- always-on weak pull-up (vdd -> det)
    MSENSE sg13_hv_nmos w=10u l=0.5u -- current-sense switch (gate=sns1, det->vss)
    MKFB   sg13_hv_nmos w=2u l=0.5u -- mirror-kick switch (gate=det, fb->vss)

**MSENSE width (issue #32).** Originally drawn at ``w=2u`` (issue #11/PR
#19), before [decision record
0003](../../spec/decision-records/0003-startup-sense-nmos-resize.md)
(issue #24/PR #29) widened ``XMSENSE`` to ``w=10u`` in
``design/netlist/bandgap_startup.spice`` to fix a real 125 °C
startup-release margin bug -- the layout was never regenerated to match
until now. ``_route()``'s geometry below was re-verified (not merely
assumed still valid) against this wider footprint -- see its own inline
comments at the affected callsites.

No bipolar device is instantiated here (DR-0001's BVCEO/BVEBO constraint
does not bind on this circuit by construction -- see the schematic's own
header comment).

**Routing (issue #20).** Reading ``design/netlist/bandgap_startup.spice``
net-by-net: ``vdd`` (``RPU.end_a`` only), ``sns1`` (``MSENSE.gate`` only),
and ``fb`` (``MKFB.source`` only) are each single-terminal *within this
cell* -- a single-terminal net is already a complete, valid net with no
wiring needed (LVS topology matching does not require it, and these three
nets' cross-cell counterparts in ``bandgap_core`` are a separate GDS file
routing cannot physically join anyway). Only two nets are genuinely
multi-terminal and need real wiring:

    - ``vss`` (2-terminal: ``MSENSE.drain``, ``MKFB.drain``) -- a single
      horizontal ``Metal1`` bar; both drain pads already sit at the same
      Y-band.
    - ``det`` (3-terminal: ``RPU.end_b``, ``MSENSE.source``, ``MKFB.gate``)
      -- ``MKFB.gate`` is a bare ``GatPoly`` gate with no Metal1 pad of its
      own (unlike ``bandgap_core``'s ``fb``, this net's *other* members are
      not gates, so it cannot be routed gate-to-gate on poly alone);
      ``layout/common.py``'s ``draw_gate_tab`` extends it with a small
      ``Cont``/``Metal1`` pad first. From there, an all-``Metal1`` L-route
      (no ``Via1``/``Metal2`` needed -- unlike ``bandgap_core``, nothing in
      this floorplan blocks a same-layer path) reaches ``MSENSE.source``
      and, via a long run the length of ``RPU``'s own resistor body,
      ``RPU.end_b``.

Re-running ``klt drc --deck sg13g2``/``klt lvs`` after this routing is
tracked in ``layout/README.md`` "DRC/LVS verification". **This routing does
not, on its own, get `MSENSE`/`MKFB` to `matched`**: this deck's curated
``sg13g2`` extraction models no well/substrate-tap layer at all, so both
``nfet`` devices' body terminals extract to a deck-synthesized global
``vsubs`` net rather than the schematic's real body-tied-to-``vss`` --
a structural mismatch routing cannot fix (see README for the full,
diagnosed cause list, same root fact ``bandgap_core`` hits).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import (  # noqa: E402
    L_METAL1,
    Builder,
    draw_gate_tab,
    draw_hv_mos,
    draw_poly_res,
    route_h,
    route_v,
)

TOP_CELL = "bandgap_startup"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bandgap_startup.gds")

TRUNK_W = 0.3

#: How many serpentine legs ``RPU``'s 1411.3 um of ``rhigh`` conductor is
#: folded into (issue #173). Chosen to make the folded block roughly square:
#: with ``draw_poly_res``'s own ``RES_FOLD_GAP_UM`` (0.4) and ``w=1u`` the
#: leg pitch is 1.4 um, so the block is ``(l/legs)`` tall by ``legs*1.4``
#: wide and the two are equal at ``legs = sqrt(l / pitch) = sqrt(1411.3 /
#: 1.4) = 31.7``. 32 rounds that to an **even** count, which is what puts
#: both terminals on the block's bottom row (odd counts leave end B on top --
#: see ``draw_poly_res``). Measured result: 44.4 um wide x 43.7 um tall,
#: aspect 0.98, against the straight bar's 1411.3 x 1.
#:
#: The block's *footprint* is ~``l * pitch`` (1975 um2) for **any** leg
#: count -- folding trades aspect ratio, not area, and the area it does cost
#: over the bare conductor is the inter-leg gap, which DRC requires. So this
#: number is purely an aspect-ratio choice and nothing downstream depends on
#: its exact value.
RPU_LEGS = 32

#: Y of the bottom edge of ``RPU``'s folded core. Its two Metal1 terminal
#: pads hang ``RES_HEAD_UM + 0.1`` (0.5 um) below this, i.e. down to y=4.5,
#: and ``DET_TRUNK_Y`` runs below *that*; the MSENSE/MKFB row tops out around
#: y=1.4. Every one of those clearances is checked by this cell's own `klt
#: drc` run, not assumed.
RES_Y = 5.0

#: Y of the horizontal ``det`` trunk. Deliberately **below** RPU's terminal
#: pads (which occupy y in [4.5, 5.0]) rather than on the resistor's own row:
#: post-fold, RPU's `vdd`-net end A pad and its `det`-net end B pad sit on the
#: *same* row 43.4 um apart, so a trunk run at pad height would short them.
DET_TRUNK_Y = 3.0


def build() -> Builder:
    b = Builder(TOP_CELL)

    mos_y = 0.0

    msense = draw_hv_mos(
        b, "MSENSE", "nmos", 10.0, 0.5, 0.0, mos_y,
        gate_net="sns1", source_net="det", drain_net="vss",
    )
    mkfb = draw_hv_mos(
        b, "MKFB", "nmos", 2.0, 0.5, 20.0, mos_y,
        gate_net="det", source_net="fb", drain_net="vss",
    )
    # RPU (l=1411.3u) folded into RPU_LEGS serpentine legs (issue #173) --
    # a ~44 x 44 um block instead of the 1.4 mm bar that used to
    # single-handedly set this cell's bounding box. Placed above the compact
    # MSENSE/MKFB row; both its terminals come out on its own bottom row.
    rpu = draw_poly_res(
        b, "RPU", "rhigh", 1.0, 1411.3, 0.0, RES_Y,
        end_a_net="vdd", end_b_net="det", legs=RPU_LEGS,
    )

    _route(b, msense, mkfb, rpu)

    return b


def _route(b: Builder, msense: dict, mkfb: dict, rpu: dict) -> None:
    """Wire the two genuinely multi-terminal nets -- see this module's own
    docstring for why ``vdd``/``sns1``/``fb`` need no routing at all.

    **Re-verified at MSENSE w=10u (issue #32).** Every geometric value used
    below is read off ``msense``/``mkfb``/``rpu``'s own returned pad
    dictionaries -- none of the offsets here are literals baked in for the
    old ``w=2u`` footprint -- so widening MSENSE only shifts its own
    ``source_pad``/``drain_pad``/``gate_box`` X-extents (its Y-extents and
    MKFB's entire footprint are unaffected, since only MSENSE's ``w``
    changed). MSENSE now spans ``x in [-5, 5]`` (was ``[-1, 1]``); MKFB is
    unchanged at ``x in [19, 21]`` (``x0=20``, ``w=2u``) -- still >=14um
    clear of MSENSE's new right edge, so no floorplan collision and no
    change to MKFB's own placement was needed. Re-run ``klt drc --deck
    sg13g2`` after this change: still clean (see ``layout/README.md``).
    """

    # -- vss: MSENSE.drain, MKFB.drain -- both already at the same Y-band.
    # Held below y=-0.4 (not the full drain-pad height up to -0.3) so the
    # bar keeps >=0.18um clearance from det's MKFB gate-tab riser below
    # (see `_riser_x`) -- verified against this issue's own `klt drc` run.
    # (issue #32: this bar is now wider, x in [-5, 21] instead of [-1, 21],
    # since it spans min/max of the two drain pads' own X-extents -- still
    # entirely within both drain pads' unchanged Y-band, so the >=0.18um
    # det-riser clearance below is unaffected by MSENSE's width.)
    vss_x_lo = min(msense["drain_pad"][0], mkfb["drain_pad"][0])
    vss_x_hi = max(msense["drain_pad"][2], mkfb["drain_pad"][2])
    route_h(b, L_METAL1, -0.5, vss_x_lo, vss_x_hi, width=0.2)

    # -- det: RPU.end_b, MSENSE.source, MKFB.gate --
    # MKFB's gate has no Metal1 pad of its own (unlike bandgap_core's `fb`,
    # this net's other members are not gates) -- extend it with a tab.
    # Attached on the LEFT (away from MKFB's own `fb`-net source pad, which
    # sits only 0.1um past the bare gate's right edge -- see
    # draw_gate_tab's own docstring for why a flush attachment there would
    # violate metal1.space.1).
    gate_edge_x = mkfb["gate_box"][0]
    tab_pad = draw_gate_tab(b, gate_edge_x, 0.0, "det", side="left")
    tab_x = (tab_pad[0] + tab_pad[2]) / 2

    # Issue #173: RPU is folded, so its two terminal pads share one row --
    # the trunk cannot run *at* pad height any more without shorting `vdd`
    # (end A) to `det` (end B). It runs below both pads instead and rises
    # into end B at that pad's own x.
    jog_y = DET_TRUNK_Y

    # MSENSE.source -> a riser column clear of MKFB's own footprint -> the
    # det trunk at RPU's row. `riser_x` is the midpoint between MSENSE's own
    # source-pad right edge and MKFB's own drain-pad left edge -- both read
    # off the returned pad dicts, so widening MSENSE (source_pad right edge
    # moves from x=1 to x=5) only moves riser_x from x=10 to x=12; it stays
    # inside the still-14um-wide clear column between the two devices
    # (issue #32 -- re-verified, not assumed).
    riser_x = (mkfb["drain_pad"][0] - msense["source_pad"][2]) / 2 + msense["source_pad"][2]
    source_y = (msense["source_pad"][1] + msense["source_pad"][3]) / 2
    route_h(b, L_METAL1, source_y, msense["source_pad"][0], riser_x, width=TRUNK_W)
    route_v(b, L_METAL1, riser_x, source_y, jog_y, width=TRUNK_W)

    # MKFB's gate tab -> the same det trunk.
    route_v(b, L_METAL1, tab_x, tab_pad[1], jog_y, width=TRUNK_W)

    # The det trunk itself, from the MSENSE riser across to below RPU.end_b,
    # then a short riser up into that pad. The trunk's own row
    # (`DET_TRUNK_Y`) clears RPU's `vdd`-net end_a pad -- which post-fold
    # sits on the same row as end_b, not 1.4 mm away -- by 1.5 um in y,
    # so the two nets never come close; verified by this cell's own `klt
    # drc` run (0 violations, `metal1.space.1` floor 0.18 um).
    target_x = (rpu["end_b_pad"][0] + rpu["end_b_pad"][2]) / 2
    route_h(b, L_METAL1, jog_y, riser_x, target_x, width=TRUNK_W)
    route_v(b, L_METAL1, target_x, jog_y, rpu["end_b_pad"][1] + 0.1, width=TRUNK_W)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
