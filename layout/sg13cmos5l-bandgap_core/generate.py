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

    M1 sg13_hv_pmos w=10u l=1u    -- branch 1 mirror leg (vdd/fb -> sns1)
    Q1 pnpMPA w=1u l=2u           -- branch 1, grounded-collector (sns1 -> vss)
    M2 sg13_hv_pmos w=10u l=1u    -- branch 2 mirror leg (vdd/fb -> sns2)
    R2 rppd w=2u l=85.1u          -- PTAT resistor (sns2 -> e2)
    Q2 8x pnpMPA w=1u l=2u m=8    -- branch 2, grounded-collector (e2 -> vss),
                                     drawn as 8 parallel unit-geometry PCell
                                     instances (issue #73, DR-0005) -- see
                                     "Q2: 8 parallel unit devices" below
    M3 sg13_hv_pmos w=10u l=1u    -- output branch mirror leg (vdd/fb -> vref)
    R1 rppd w=2u l=647.0u         -- summing resistor (vref -> e3)
    Q3 pnpMPA w=1u l=2u           -- output branch, grounded-collector (e3 -> vss)

Q2: 8 parallel unit devices (issue #73, DR-0005)
-------------------------------------------------

The schematic's ``Q2`` is ``pnpMPA a={1u*2u} p={(1u+2u)*2} m=8`` -- 8 parallel
copies of the same unit device ``Q1``/``Q3`` use, not one wide emitter. A
single ``w=8u`` instance cannot be PCell-generated at all: CMOS5L's
``pnpMPA_maxW`` is 2.0 um (``sg13cmos5l_tech.json``), and ``pnpMPA_code.py``'s
``genLayout()`` sizes the emitter window directly from ``w``/``l`` with no
internal arraying (its own ``m`` "Multiplier" param spec is declared but
never read by ``genLayout()``). This layout therefore calls
:func:`draw_pnpmpa` (the same helper drawing ``Q1``/``Q3``) 8 times at
``w=1u l=2u`` -- each individually well inside ``pnpMPA_maxW`` -- and wires
all 8 in parallel:

* **Emitters** all tie to ``e2`` via a shared Metal1 trunk (``Q2_BUS_Y``,
  chosen above every unit's own collector-ring outer top edge so the trunk
  never touches a ring's Metal1 -- see the sizing comment next to
  ``Q2_BUS_Y`` below), which ``R2`` then drops onto from above -- the same
  "emitter escapes straight up through its own ring's open-top gap"
  construction every other ``pnpMPA`` instance in this cell already uses,
  just repeated per unit and then bussed.
* **Base/collector rings** (both ``vss``) are tied unit-to-unit exactly like
  the former ``Q1``-to-``Q2`` strap was (:func:`_tie_rings` per unit, then a
  chain of :func:`route_h` straps between consecutive units) -- the ``vss``
  aisle down to ``Q3``'s row still taps this chain at ``X_VSS_AISLE`` (87),
  which lies inside the *first* link of the chain (``Q1`` to ``Q2`` unit 0),
  unchanged from before.

``X_M3`` (and everything positioned relative to it -- ``R1``, ``Q3``, the
``vref``/``e3`` routing) shifted right, 150 -> 180, to make room for the
8-unit row: at ``Q2_PITCH_X=6.0`` um centre-to-centre (a unit's own
collector-ring bbox is 5.5 um wide, so this clears the deck's
``activ.space.1`` rule with 0.5 um margin either side), the row spans
``Q2_X0=123.75`` to ``165.75``, versus the single ``w=8u`` device's former
``120.6``..``140.1`` -- about 25 um wider, comfortably inside the new gap to
``X_M3``. This is electrically inert (DR-0005 shows the 8-unit-device and
single-wide-device constructions are the same circuit to the compact
model) -- a pure floorplan consequence of the PCell not supporting an
internal array.

Single-metal routing
--------------------

The curated ``sg13cmos5l`` deck models one routing metal (``Metal1``) and no vias.
The core routes on ``Metal1``, with ``GatPoly`` for the shared mirror gates
and the ``sns2`` underpass. Folded resistors ``R1`` and ``R2`` sit below
their respective mirror legs.

What this layout does **not** try to do is force an LVS `match`. The
curated ``sg13cmos5l`` deck recognises MOS devices only -- no bipolar
(``bipolars=()``), no resistor (``resistors=()``), no HV MOS flavour
(``mos_flavours=()``), and no well/substrate tap (``tap=None``) -- so 12 of
this cell's 15 devices (10 bipolar unit instances -- ``Q1``, 8x ``Q2``,
``Q3`` -- plus 2 resistors) cannot be recognised at all, and the 3 that can
(``M1``-``M3``) have an unmodellable body terminal. Those are deck-coverage
gaps, filed upstream per ``CLAUDE.md``'s friction protocol and enumerated
with their evidence in ``layout/README.md`` "SG13CMOS5L: LVS --
``mismatch``, fully attributed". The layout's own job is to be physically
right and DRC clean, which it is.

Boundary ports for ``bandgap_top`` assembly (issue #76)
---------------------------------------------------------

Three interior drain trunks branch out to :func:`boundary_port` pads for
the parent assembly. The ``X_*_PORT`` and ``Y_*_PORT`` constants below
locate each pad.

* ``sns1`` runs left on ``Metal1`` between the top of Q1's grounded rings
  and M1's drain pad.
* ``sns2`` runs right on ``Metal1``. Above folded R1, :func:`poly_underpass`
  carries it beneath the ``vref`` trunk on ``GatPoly``. See ``Y_SNS2_PORT``
  and ``X_SNS2_UNDERPASS`` for the crossing height and span.
* ``vref`` runs right on ``Metal1`` above the Q2 emitter bus and the
  ``vss`` aisle, below the ``sns2`` crossing.

``build()`` returns the builder and a map of all six port boxes. Alongside
these three pads, it returns the source rail for ``vdd``, M1's gate tap
for ``fb`` and Q3's collector ring for ``vss``.
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
    boundary_port,
    draw_hv_pmos,
    draw_pnpmpa,
    draw_rppd,
    draw_well_tap,
    pad_center_x,
    poly_underpass,
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

# MOS and PNP rows are centred at the given heights. Y_R1 and Y_R2 set
# the bottom edges of the folded resistor cores so their tops clear the
# mirror row's NWell and ThickGateOx.
Y_MOS = 60.0
Y_R2 = 44.0
Y_Q12 = 30.0
Y_R1 = 15.0
Y_Q3 = 0.0

#: Serpentine fold counts (issue #173). Pre-fold, `R1` was a single 647 um
#: straight bar that alone set this cell's 840.5 um width against a 64.9 um
#: height (12.9:1). Each count is chosen to make its own folded block
#: roughly square -- with `RES_FOLD_GAP_UM` (0.4) and w=2u the leg pitch is
#: ~2.4 um, and a block is square at `legs = sqrt(l / pitch)`:
#: sqrt(647/2.4) = 16.4 and sqrt(85.1/2.4) = 6.0. Both rounded to an
#: **even** count so each resistor's two terminals come out on its own
#: bottom row (odd counts leave end B on top -- see `_draw_poly_res`), which
#: is what keeps `e2`/`e3`'s drops into the PNP rows below unchanged in
#: kind. Folding conserves the drawn conductor length exactly
#: (`_klayout_builder_base.fold_plan`), so neither nominal value moves.
#: Measured: R1 38.6 x 40.025 um (issue #573 put the fold gap itself on the
#: 5 nm manufacturing grid, widening R1 from the 1 nm-step fold's
#: 38.12 x 40.055 -- gap 0.408 -> 0.44, pitch 2.408 -> 2.44), R2
#: 14.0 x 13.85 um unchanged (its 1 nm-step fold already landed on-grid).
R1_LEGS = 16
R2_LEGS = 6

# Column origins. X_M3 shifted 150 -> 180 (issue #73/DR-0005) to make room
# for Q2's 8-unit row -- see this module's own docstring.
X_M1 = 0.0
X_M2 = 45.0
X_M3 = 180.0

# Device sizes, read from design/sg13cmos5l/netlist/bandgap_core.spice.
MOS_W, MOS_L = 10.0, 1.0
R2_W, R2_L = 2.0, 85.1
R1_W, R1_L = 2.0, 647.0
Q_UNIT_W, Q_L = 1.0, 2.0

#: Q2's construction (issue #73, DR-0005): 8 parallel *unit*-geometry
#: ``pnpMPA`` instances (``Q_UNIT_W``/``Q_L``, same as Q1/Q3), not one wide
#: emitter -- see this module's own docstring. ``Q2_PITCH_X`` clears a unit
#: device's own collector-ring bbox (5.5 um wide -- computed from
#: ``pnpmpa_extent(1.0, 2.0)`` the same way ``common_sg13cmos5l.py`` derives
#: it) with 0.5 um margin either side against the deck's ``activ.space.1``
#: rule. ``Q2_X0`` is the leftmost unit's own centre x, chosen so the row's
#: left edge (121.0) clears ``X_VSS_AISLE`` (87) with the same margin the
#: former single-device Q2 left it (120.6).
Q2_N = 8
Q2_PITCH_X = 6.0
Q2_X0 = 123.75

#: Shared Metal1 trunk every Q2 unit's emitter escapes straight up onto
#: (through its own ring's open-top gap, same construction every other
#: ``pnpMPA`` instance in this cell already uses). A unit device's own
#: collector-ring outer top edge sits at ``Y_Q12 + h3act + d3act = 33.01``
#: um (``pnpmpa_extent(1.0, 2.0)``'s ``h3act`` plus the ring's own
#: ``d3act=0.35`` half-width); 34.0 clears that with ~1 um margin, so the
#: trunk never touches a ring's Metal1.
Q2_BUS_Y = 34.0

#: The vss aisle taps the strap between Q1 and the first Q2 unit and
#: descends to Q3's row to the left of folded R1.
X_VSS_AISLE = 87.0

# Port positions for the escape routes in "Boundary ports for bandgap_top assembly".
Y_SNS1_PORT = 50.0
X_SNS1_PORT = -10.0
#: Keep the GatPoly underpass and its landing pads in the field between
#: folded R1 and the mirror row's NWell/ThickGateOx. Overlapping R1's
#: GatPoly here would short sns2 to the resistor.
Y_SNS2_PORT = 57.0
X_SNS2_PORT = 220.0
#: The two poly contacts straddle the vref Metal1 trunk.
X_SNS2_UNDERPASS = (176.75, 185.25)
Y_VREF_PORT = 40.0
X_VREF_PORT = 220.0

#: The shared mirror well's n+ tap (issue #240), placed in the well's own
#: interior field between ``M1`` and ``M2``: x=22.5 sits ~17 um clear of
#: either leg's own ``Activ``/``pSD`` (M1 ends at x=5.58, M2 starts at
#: 39.42), y=59.15 keeps the 0.34 um tap island (plus its 0.1 um ``nSD``
#: margin) below the ``fb`` gate bar (y 59.85..60.15), above the well's own
#: bottom edge (58.48), and level with the drain-pad band it never overlaps
#: in x -- and off every leg's ``ThickGateOx`` (each spans only +-5.27 um
#: around its leg). ``_route()`` wires the returned pad up into the vdd rail
#: with a Metal1 stub that crosses the ``fb`` bar -- Metal1 over GatPoly
#: with no ``Cont`` is no connection.
X_MIRROR_TAP = 22.5
Y_MIRROR_TAP = 59.15


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
    # The well's own n+ tap (issue #240): an ``nSD``-covered ``Activ`` island
    # (``draw_well_tap``) inside this shared well, wired up into the vdd rail
    # by ``_route()`` below -- the deck-derived ``tap_nplus`` connection the
    # curated ``sg13cmos5l`` deck has recognised since klayout-tools#1414.
    # Until this issue the well was deliberately left floating, and the
    # comment here recorded why: the 0.3.0-era deck declared no tap
    # derivation at all, so a ``NWell.pin`` "vdd" label could only *name* the
    # isolated well (a second, disjoint ``vdd$1`` net) while suppressing
    # ``klt extract``'s own "no DC bias path" warning -- the most direct
    # evidence of the tap gap (layout/README.md "SG13CMOS5L: LVS --
    # ``mismatch``, fully attributed", cause 4). With the tap drawn the well
    # is physically connected to vdd, so no well label is needed to name it
    # and none is drawn.
    mirror_tap = draw_well_tap(b, X_MIRROR_TAP, Y_MIRROR_TAP, "vdd")

    # -- series resistors, each starting at its own mirror leg's column ----
    r2 = draw_rppd(b, "R2", R2_W, R2_L, X_M2, Y_R2, end_a_net="sns2", end_b_net="e2",
                   legs=R2_LEGS)
    r1 = draw_rppd(b, "R1", R1_W, R1_L, X_M3, Y_R1, end_a_net="vref", end_b_net="e3",
                   legs=R1_LEGS)

    # -- the grounded-collector PNPs, each under its own branch -------------
    x_q3 = pad_center_x(r1["end_b_pad"])
    q1 = draw_pnpmpa(b, "Q1", Q_UNIT_W, Q_L, X_M1, Y_Q12, "sns1", "vss", "vss")
    q2_units = [
        draw_pnpmpa(b, f"Q2_{i}", Q_UNIT_W, Q_L, Q2_X0 + i * Q2_PITCH_X, Y_Q12, "e2", "vss", "vss")
        for i in range(Q2_N)
    ]
    q3 = draw_pnpmpa(b, "Q3", Q_UNIT_W, Q_L, x_q3, Y_Q3, "e3", "vss", "vss")

    ports = _route(b, m1, m2, m3, r1, r2, q1, q2_units, q3, mirror_tap)
    return b, ports


def _route(
    b: Builder,
    m1: dict,
    m2: dict,
    m3: dict,
    r1: dict,
    r2: dict,
    q1: dict,
    q2_units: list[dict],
    q3: dict,
    mirror_tap: tuple[float, float, float, float],
) -> dict[str, tuple[float, float, float, float]]:
    """Wire every schematic net. Each block names the net it wires; see the
    module docstring for why all of it is single-metal and planar.

    Returns the ``{net: pad_box}`` boundary-port map (issue #76) covering
    all six of this cell's schematic ports -- see this module's own
    docstring, "Boundary ports for bandgap_top assembly"."""

    # -- vdd: M1/M2/M3 source pads, merged by one horizontal Metal1 bar.
    src = m1["source_pad"]
    vdd_pad = (m1["source_pad"][0], src[1], m3["source_pad"][2], src[3])
    b.box(L_METAL1, *vdd_pad)

    # -- the shared well's tap, rising into that same vdd rail (issue #240).
    # One Metal1 stub from the tap pad's top edge up through the fb bar
    # (Metal1 over GatPoly with no Cont is no connection) onto the rail.
    route_v(b, L_METAL1, X_MIRROR_TAP, mirror_tap[3], vdd_pad[3], width=TRUNK_W)

    # -- fb: M1/M2/M3 gates, one continuous GatPoly bar. Poly-to-poly routing
    # between recognised gates is ordinary connectivity for `klt extract`
    # (deck: `connect(pfet_gate, poly)`), so no contacts are needed between
    # the gates themselves.
    fb_y = (m1["gate_y_lo"] + m1["gate_y_hi"]) / 2
    route_h(b, L_GATPOLY, fb_y, m1["gate_box"][0] - 3.0, m3["gate_box"][2], width=TRUNK_W)
    fb_pad = _fb_tap(b, m1["gate_box"][0] - 3.0, fb_y)

    # -- sns1: M1.drain -> Q1.emitter through the opening in Q1's rings.
    route_v(b, L_METAL1, X_M1, q1["emitter_pad"][3], m1["drain_pad"][3], width=TRUNK_W)
    sns1_pad = boundary_port(b, "sns1", "left", X_SNS1_PORT, Y_SNS1_PORT)
    route_h(b, L_METAL1, Y_SNS1_PORT, sns1_pad[2], X_M1, width=TRUNK_W)

    # -- sns2: M2.drain -> R2.end_a. Centring the drop on the resistor
    # pad keeps the T-junction clear of the metal1.width.1 notch rule.
    x_sns2 = pad_center_x(r2["end_a_pad"])
    route_v(b, L_METAL1, x_sns2, r2["end_a_pad"][3],
            m2["drain_pad"][3], width=TRUNK_W)
    sns2_pad = boundary_port(b, "sns2", "right", X_SNS2_PORT, Y_SNS2_PORT)
    route_h(b, L_METAL1, Y_SNS2_PORT, x_sns2, X_SNS2_UNDERPASS[0], width=TRUNK_W)
    poly_underpass(b, Y_SNS2_PORT, X_SNS2_UNDERPASS[0], X_SNS2_UNDERPASS[1], width=TRUNK_W)
    route_h(b, L_METAL1, Y_SNS2_PORT, X_SNS2_UNDERPASS[1], sns2_pad[0], width=TRUNK_W)

    # -- e2: R2.end_b -> Q2 emitters. R2's drop lies west of the first
    # emitter, so the shared bus must extend to the drop to connect it.
    for q in q2_units:
        route_v(b, L_METAL1, pad_center_x(q["emitter_pad"]), Q2_BUS_Y,
                q["emitter_pad"][3], width=TRUNK_W)
    x_e2 = pad_center_x(r2["end_b_pad"])
    x_bus_lo = min(pad_center_x(q2_units[0]["emitter_pad"]), x_e2)
    x_bus_hi = pad_center_x(q2_units[-1]["emitter_pad"])
    route_h(b, L_METAL1, Q2_BUS_Y, x_bus_lo, x_bus_hi, width=TRUNK_W)
    route_v(b, L_METAL1, x_e2, Q2_BUS_Y, r2["end_b_pad"][1], width=TRUNK_W)

    # -- vref: M3.drain -> R1.end_a, centred on the resistor pad.
    x_vref = pad_center_x(r1["end_a_pad"])
    route_v(b, L_METAL1, x_vref, r1["end_a_pad"][3],
            m3["drain_pad"][3], width=TRUNK_W)
    vref_pad = boundary_port(b, "vref", "right", X_VREF_PORT, Y_VREF_PORT)
    route_h(b, L_METAL1, Y_VREF_PORT, x_vref, vref_pad[0], width=TRUNK_W)

    # -- e3: Q3 is centred on R1.end_b so the drop lands on its emitter.
    x_e3 = pad_center_x(r1["end_b_pad"])
    route_v(b, L_METAL1, x_e3, q3["emitter_pad"][3], r1["end_b_pad"][1], width=TRUNK_W)

    # -- vss: every PNP's base ring + collector ring, all tied together.
    _tie_rings(b, q1, Y_Q12)
    for q in q2_units:
        _tie_rings(b, q, Y_Q12)
    _tie_rings(b, q3, Y_Q3)
    # The aisle to Q3 taps the first link in the chain of collector rings.
    chain = [q1, *q2_units]
    for left, right in zip(chain, chain[1:]):
        route_h(b, L_METAL1, Y_Q12, left["collector_ring_m1"][2], right["collector_ring_m1"][0],
                width=TRUNK_W)
    route_v(b, L_METAL1, X_VSS_AISLE, Y_Q3, Y_Q12, width=TRUNK_W)
    route_h(b, L_METAL1, Y_Q3, X_VSS_AISLE, q3["collector_ring_m1"][0], width=TRUNK_W)

    vss_pad = q3["collector_ring_m1"]

    return {
        "vdd": vdd_pad,
        "vss": vss_pad,
        "fb": fb_pad,
        "sns1": sns1_pad,
        "sns2": sns2_pad,
        "vref": vref_pad,
    }


def _tie_rings(b: Builder, q: dict, y: float) -> None:
    """Strap one PNP's base ring to its own collector ring (both are ``vss``
    in this grounded-collector topology, but they are separate drawn shapes)
    with a short horizontal Metal1 stub on the device's left side, clear of
    the emitter escape route through the rings' open top."""
    route_h(b, L_METAL1, y, q["collector_ring_m1"][0], q["base_ring_m1"][0], width=TRUNK_W)


def _fb_tap(b: Builder, x: float, y: float) -> tuple[float, float, float, float]:
    """Bring the ``fb`` gate net out to a labelled Metal1 pad.

    The curated deck declares ``poly_label=None``: a gate net can only be
    *named* through a Metal1 pad contacted to its poly (exactly the gap
    ``layout/README.md`` records for SG13G2's ``bandgap_startup`` ``det``
    net). Without this tap, ``fb`` -- whose only other members are three
    gates -- would extract as an anonymous ``$N``. The pad sits ~3 um left of
    M1's own diffusion, so it clears every Metal1 shape on the mirror row by
    far more than ``metal1.space.1``'s 0.18 um floor -- and, as it happens,
    already flush with the cell's own left edge, so it doubles as fb's own
    boundary port (issue #76). Returns the drawn Metal1 pad's box.
    """
    pad_w, pad_h = 0.40, 0.34
    b.box(L_GATPOLY, x - pad_w / 2 - 0.1, y - pad_h / 2, x + pad_w / 2 + 0.1, y + pad_h / 2)
    b.box(L_CONT, x - CNT_A / 2, y - CNT_A / 2, x + CNT_A / 2, y + CNT_A / 2)
    pad = (x - pad_w / 2, y - pad_h / 2 + CNT_C, x + pad_w / 2, y + pad_h / 2 - CNT_C)
    b.box(L_METAL1, *pad)
    b.net_label("fb", x, y)
    return pad


if __name__ == "__main__":
    builder, ports = build()
    builder.write(OUTPUT)
    print("ports:", {net: tuple(round(v, 3) for v in box) for net, box in ports.items()})
    print(f"wrote {OUTPUT}: bbox={builder.cell.dbbox()}")
