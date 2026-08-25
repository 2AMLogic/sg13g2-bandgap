#!/usr/bin/env python3
"""Generate ``sg13cmos5l-bandgap_core.gds`` -- physical layout of
``design/sg13cmos5l/bandgap_core.sch`` (the SG13CMOS5L port, issue #66,
phase 3/4).

Drawn with ``layout/common_sg13cmos5l.py``'s primitives -- a deliberate fork
of ``layout/common.py``, see that module's docstring for the three reasons
(different layer table, different net-label layer, different device set)
this port does not share the SG13G2 primitives.

Run from the repo root::

    uv run --with klayout python3 layout/sg13cmos5l-bandgap_core/generate.py

Output is byte-for-byte deterministic (GDSII header timestamps disabled via
``SaveLayoutOptions.gds2_write_timestamps = False``), so re-running leaves
``git diff`` empty.

Devices instantiated, one-to-one against
``design/sg13cmos5l/netlist/bandgap_core.spice``:

    M1 sg13_hv_pmos w=10u l=1u   -- branch 1 mirror leg (vdd/fb -> sns1)
    Q1 pnpMPA w=1u l=2u          -- branch 1, grounded-collector (sns1 -> vss)
    M2 sg13_hv_pmos w=10u l=1u   -- branch 2 mirror leg (vdd/fb -> sns2)
    R2 rppd w=2u l=85.1u         -- PTAT resistor (sns2 -> e2)
    Q2 pnpMPA w=8u l=2u          -- branch 2, grounded-collector (e2 -> vss)
    M3 sg13_hv_pmos w=10u l=1u   -- output branch mirror leg (vdd/fb -> vref)
    R1 rppd w=2u l=647.0u        -- summing resistor (vref -> e3)
    Q3 pnpMPA w=1u l=2u          -- output branch, grounded-collector (e3 -> vss)

Single-metal, strictly planar floorplan
---------------------------------------

The curated ``sg13cmos5l`` deck's extraction stack is ``metals=((8, 0),)``
with ``vias=()`` -- **one** routing metal, no via. (SG13G2's deck declares
Metal1/Metal2/.../TopMetal2 plus Via1..TopVia2, which is why
``layout/bandgap_core/generate.py`` can hop onto Metal2 to cross its own
power rails.) A Metal2 jumper here would be invisible to ``klt extract``:
the net would come back split, and the resulting `mismatch` would be an
artifact of the layout rather than of the deck. So every net below is
routed on ``Metal1`` (plus ``GatPoly`` for the gate-to-gate ``fb`` bar), and
the floorplan is arranged so that **no two nets ever need to cross**:

    y=60   MOS row          M1 (x=0)      M2 (x=45)     M3 (x=150)
    y=45   R2 row                         R2 [45 .. 130.1]
    y=30   Q1/Q2 row        Q1 (x=0)                    Q2 (x=130.35)
    y=15   R1 row                                       R1 [150 .. 797]
    y=0    Q3 row                                       Q3 (x=797.25)

Each branch is a left-to-right, top-to-bottom chain (mirror leg -> series
resistor -> PNP), and each resistor *starts* at its own mirror leg's column
so the drain-to-resistor drop is a straight vertical that clears every other
row's horizontal extent. The two long ``rppd`` bars (85.1 um and 647.0 um,
drawn straight -- see ``draw_rppd``) are what forces the columns this far
apart.

``vss`` is the one net that does span rows: the three PNPs' base/collector
rings sit on two different rows with ``R1``'s 647 um bar between them. It
reaches ``Q3``'s row down a dedicated vertical aisle at ``x=87``, which
crosses ``R1``'s row well left of that bar's left head (x=149.6) and lands,
at the top, on the ``Q1``-to-``Q2`` strap (which spans x=2.7..120.6). No
other net has a shape anywhere in that corridor.

What this layout does **not** try to do is force an LVS `match`. The
curated ``sg13cmos5l`` deck recognises MOS devices only -- no bipolar
(``bipolars=()``), no resistor (``resistors=()``), no HV MOS flavour
(``mos_flavours=()``), and no well/substrate tap (``tap=None``) -- so five
of this cell's eight devices cannot be recognised at all, and the three
that can have an unmodellable body terminal. Those are deck-coverage gaps,
filed upstream per ``CLAUDE.md``'s friction protocol and enumerated with
their evidence in ``layout/README.md`` "SG13CMOS5L: LVS -- ``mismatch``,
fully attributed". The layout's own job is to be physically right and DRC
clean, which it is.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common_sg13cmos5l import (  # noqa: E402
    CNT_A,
    CNT_C,
    L_CONT,
    L_GATPOLY,
    L_METAL1,
    L_NWELL,
    Builder,
    draw_hv_pmos,
    draw_pnpmpa,
    draw_rppd,
    route_h,
    route_v,
)

TOP_CELL = "sg13cmos5l_bandgap_core"
OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sg13cmos5l-bandgap_core.gds"
)

#: Routing width for every Metal1 trunk. The curated deck's ``metal1.width.1``
#: floor is 0.16 um and ``metal1.space.1`` is 0.18 um (both transcribed from
#: ``5_16_metal1.drc``'s ``M1.a``/``M1.b``); 0.30 um clears the width floor
#: with ~2x margin, and every clearance below is checked against 0.18 um.
TRUNK_W = 0.30

# Row centres (see the floorplan table in this module's docstring).
Y_MOS = 60.0
Y_R2 = 45.0
Y_Q12 = 30.0
Y_R1 = 15.0
Y_Q3 = 0.0

# Column origins.
X_M1 = 0.0
X_M2 = 45.0
X_M3 = 150.0

# Device sizes, read from design/sg13cmos5l/netlist/bandgap_core.spice.
MOS_W, MOS_L = 10.0, 1.0
R2_W, R2_L = 2.0, 85.1
R1_W, R1_L = 2.0, 647.0
Q_UNIT_W, Q_L = 1.0, 2.0
Q2_W = 8.0

#: The ``vss`` aisle: a clear vertical corridor from the Q1/Q2 row down to
#: the Q3 row. Two constraints, both with tens of microns to spare at 87:
#: it must cross ``R1``'s row left of that bar's left head (x=149.6), and it
#: must land on the ``Q1``-to-``Q2`` strap, i.e. inside x=2.7..120.6 (right
#: of ``Q1``'s outer ring edge, left of ``Q2``'s).
X_VSS_AISLE = 87.0


def build() -> Builder:
    b = Builder(TOP_CELL)

    # -- mirror row: three matched HV PMOS legs in one shared n-well -------
    # draw_nwell=False on each: a single shared NWell is drawn below, so the
    # three body terminals resolve to one well net (the schematic ties all
    # three bodies to vdd), not three unrelated ones.
    m1 = draw_hv_pmos(b, "M1", MOS_W, MOS_L, X_M1, Y_MOS, "fb", "vdd", "sns1", draw_nwell=False)
    m2 = draw_hv_pmos(b, "M2", MOS_W, MOS_L, X_M2, Y_MOS, "fb", "vdd", "sns2", draw_nwell=False)
    m3 = draw_hv_pmos(b, "M3", MOS_W, MOS_L, X_M3, Y_MOS, "fb", "vdd", "vref", draw_nwell=False)
    b.box(
        L_NWELL,
        m1["nwell"][0], m1["nwell"][1], m3["nwell"][2], m3["nwell"][3],
    )
    # Deliberately **not** well-labelled. Tried both ways for this issue:
    # a `NWell.pin` "vdd" text does name the well net, but the deck declares
    # no tap layer at all (`tap`/`tap_nplus`/`tap_pplus` all None), so the
    # well still cannot be *connected* to the vdd metal rail -- the netlist
    # simply comes back with a second, disjoint net called `vdd$1`, and
    # `klt lvs`'s finding count is unchanged (27 either way, re-run to
    # confirm). Labelling it would only suppress `klt extract`'s own
    # "PMOS devices tie their body to an anonymous net with no DC bias path"
    # warning -- the most direct evidence of the tap gap this cell hits --
    # in exchange for a net name that misrepresents a floating well as a
    # supply tie. See layout/README.md "SG13CMOS5L: LVS -- mismatch, fully
    # attributed", cause 4.

    # -- series resistors, each starting at its own mirror leg's column ----
    r2 = draw_rppd(b, "R2", R2_W, R2_L, X_M2, Y_R2, end_a_net="sns2", end_b_net="e2")
    r1 = draw_rppd(b, "R1", R1_W, R1_L, X_M3, Y_R1, end_a_net="vref", end_b_net="e3")

    # -- the three grounded-collector PNPs, each under its own branch ------
    x_q2 = _pad_center_x(r2["end_b_pad"])
    x_q3 = _pad_center_x(r1["end_b_pad"])
    q1 = draw_pnpmpa(b, "Q1", Q_UNIT_W, Q_L, X_M1, Y_Q12, "sns1", "vss", "vss")
    q2 = draw_pnpmpa(b, "Q2", Q2_W, Q_L, x_q2, Y_Q12, "e2", "vss", "vss")
    q3 = draw_pnpmpa(b, "Q3", Q_UNIT_W, Q_L, x_q3, Y_Q3, "e3", "vss", "vss")

    _route(b, m1, m2, m3, r1, r2, q1, q2, q3)
    return b


def _route(b: Builder, m1: dict, m2: dict, m3: dict, r1: dict, r2: dict, q1: dict, q2: dict, q3: dict) -> None:
    """Wire every schematic net. Each block names the net it wires; see the
    module docstring for why all of it is single-metal and planar."""

    # -- vdd: M1/M2/M3 source pads, merged by one horizontal Metal1 bar.
    # The pads already carry their own "vdd" Metal1.pin labels (draw_hv_pmos);
    # this bar only makes the three one physically-connected shape.
    src = m1["source_pad"]
    b.box(L_METAL1, m1["source_pad"][0], src[1], m3["source_pad"][2], src[3])

    # -- fb: M1/M2/M3 gates, one continuous GatPoly bar. Poly-to-poly routing
    # between recognised gates is ordinary connectivity for `klt extract`
    # (deck: `connect(pfet_gate, poly)`), so no contacts are needed between
    # the gates themselves.
    fb_y = (m1["gate_y_lo"] + m1["gate_y_hi"]) / 2
    route_h(b, L_GATPOLY, fb_y, m1["gate_box"][0] - 3.0, m3["gate_box"][2], width=TRUNK_W)
    _fb_tap(b, m1["gate_box"][0] - 3.0, fb_y)

    # -- sns1: M1.drain -> Q1.emitter, straight down column x=0. Enters Q1
    # through the deliberate gap in its base/collector Metal1 rings' top
    # walls (Builder.ring(open_top=True)).
    route_v(b, L_METAL1, X_M1, q1["emitter_pad"][3], m1["drain_pad"][3], width=TRUNK_W)

    # -- sns2: M2.drain -> R2.end_a, straight down column x=45. Centred on
    # R2's end pad (not on the column origin): a vertical that overhangs the
    # pad's edge turns the join into a step rather than a T, and `klt drc`
    # flags the resulting notch as `metal1.width.1` (found on this cell's
    # first DRC run). A 0.30 um stem landing wholly inside a 0.50 um pad
    # measures 0.30*cos(45) = 0.212 um across the T's own diagonal, clear of
    # the 0.16 um floor.
    route_v(b, L_METAL1, _pad_center_x(r2["end_a_pad"]), r2["end_a_pad"][3],
            m2["drain_pad"][3], width=TRUNK_W)

    # -- e2: R2.end_b -> Q2.emitter, straight down (R2's far end sits
    # directly above Q2 by construction).
    x_e2 = _pad_center_x(r2["end_b_pad"])
    route_v(b, L_METAL1, x_e2, q2["emitter_pad"][3], r2["end_b_pad"][1], width=TRUNK_W)

    # -- vref: M3.drain -> R1.end_a, straight down column x=150 (same
    # pad-centred landing as sns2 above). Clears R2's right end (x=130.6)
    # and Q2's right edge by ~10 um.
    route_v(b, L_METAL1, _pad_center_x(r1["end_a_pad"]), r1["end_a_pad"][3],
            m3["drain_pad"][3], width=TRUNK_W)

    # -- e3: R1.end_b -> Q3.emitter, same construction as e2.
    x_e3 = _pad_center_x(r1["end_b_pad"])
    route_v(b, L_METAL1, x_e3, q3["emitter_pad"][3], r1["end_b_pad"][1], width=TRUNK_W)

    # -- vss: every PNP's base ring + collector ring, all tied together.
    for q, y in ((q1, Y_Q12), (q2, Y_Q12), (q3, Y_Q3)):
        _tie_rings(b, q, y)
    # Q1 <-> Q2 along their shared row, then down the aisle to Q3's row.
    route_h(b, L_METAL1, Y_Q12, q1["collector_ring_m1"][2], q2["collector_ring_m1"][0], width=TRUNK_W)
    route_v(b, L_METAL1, X_VSS_AISLE, Y_Q3, Y_Q12, width=TRUNK_W)
    route_h(b, L_METAL1, Y_Q3, X_VSS_AISLE, q3["collector_ring_m1"][0], width=TRUNK_W)


def _tie_rings(b: Builder, q: dict, y: float) -> None:
    """Strap one PNP's base ring to its own collector ring (both are ``vss``
    in this grounded-collector topology, but they are separate drawn shapes)
    with a short horizontal Metal1 stub on the device's left side, clear of
    the emitter escape route through the rings' open top."""
    route_h(b, L_METAL1, y, q["collector_ring_m1"][0], q["base_ring_m1"][0], width=TRUNK_W)


def _pad_center_x(pad: tuple[float, float, float, float]) -> float:
    """X centre of a returned terminal pad box."""
    return (pad[0] + pad[2]) / 2


def _fb_tap(b: Builder, x: float, y: float) -> None:
    """Bring the ``fb`` gate net out to a labelled Metal1 pad.

    The curated deck declares ``poly_label=None``: a gate net can only be
    *named* through a Metal1 pad contacted to its poly (exactly the gap
    ``layout/README.md`` records for SG13G2's ``bandgap_startup`` ``det``
    net). Without this tap, ``fb`` -- whose only other members are three
    gates -- would extract as an anonymous ``$N``. The pad sits ~3 um left of
    M1's own diffusion, so it clears every Metal1 shape on the mirror row by
    far more than ``metal1.space.1``'s 0.18 um floor.
    """
    pad_w, pad_h = 0.40, 0.34
    b.box(L_GATPOLY, x - pad_w / 2 - 0.1, y - pad_h / 2, x + pad_w / 2 + 0.1, y + pad_h / 2)
    b.box(L_CONT, x - CNT_A / 2, y - CNT_A / 2, x + CNT_A / 2, y + CNT_A / 2)
    b.box(L_METAL1, x - pad_w / 2, y - pad_h / 2 + CNT_C, x + pad_w / 2, y + pad_h / 2 - CNT_C)
    b.net_label("fb", x, y)


if __name__ == "__main__":
    builder = build()
    builder.write(OUTPUT)
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
