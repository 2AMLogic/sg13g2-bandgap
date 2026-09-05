"""Shared ``klayout.db`` drawing primitives for ``layout/*/generate.py``.

Both ``layout/bandgap_core/generate.py`` and
``layout/bandgap_startup/generate.py`` draw directly with ``klayout.db``
(``pya``-compatible) rather than a PDK-native PCell run -- see each
``generate.py``'s own module docstring, and ``layout/README.md``
"Provenance", for why: SG13G2's *own* PyCell library
(``ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib``) exists and can in
principle run inside KLayout, but (a) its companion compatibility shim
(``pycell4klayout-api``, a separate git submodule the tarball fetch used for
this issue did not include) was not available in this environment, and (b)
``klt gen`` -- the fleet's own built-in headless PCell harness -- has no
generator family that resolves this PDK at all (checked concretely for this
issue; every analog-primitive generator in ``klt gen --list`` returns
``PDK variant '...' is not supported by this generator -- supported
families: gf180mcu, sky130``). This module is this repo's manual-layout
counterpart, following the same construction pattern
``gf180-bandgap/layout/bandgap_top/generate.py`` and
``gf180-bandgap/layout/common/klayout_builder.py`` already established for
the fleet's most mature block.

Every ``(layer, datatype)`` pair below is read directly from the resolved
SG13G2 KLayout technology's own layer-properties file
(``ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp``), not invented -- see
``layout/README.md`` "Layer numbers" for the read-off table.
"""

from __future__ import annotations

import klayout.db as kdb
from _klayout_builder_base import BuilderBase, fold_plan, route_h, route_v  # noqa: F401

# --------------------------------------------------------------------------- #
# SG13G2 GDS layer numbers, read from
# ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp (<source> entries), IHP-Open-PDK
# main @ 22f2a25 (2026-08-05), the same checkout spec/porting-plan.md cites.
# --------------------------------------------------------------------------- #
L_ACTIV = (1, 0)
L_GATPOLY = (5, 0)
L_GATPOLY_LABEL = (5, 1)
L_NSD = (7, 0)
L_CONT = (6, 0)
L_METAL1 = (8, 0)
L_METAL1_LABEL = (8, 1)
L_PSD = (14, 0)
L_VIA1 = (19, 0)
L_METAL2 = (10, 0)
L_METAL2_LABEL = (10, 1)
L_NWELL = (31, 0)
L_EMWIND = (33, 0)
L_POLYRES = (128, 0)
L_POLYRES_LABEL = (128, 1)
L_TEXT = (63, 0)
# rppd/rhigh poly-resistor recognition marker layers (issue #20), read the
# same way as every other layer above -- ihp-sg13g2/libs.tech/klayout/tech/
# sg13g2.lyp's own <source> entries -- and independently confirmed against
# klayout_tools.decks.sg13g2.EXTRACTION_DECK.resistors's own declared
# `requires=((111, 0), (14, 0), (28, 0))` (rppd)/`((111, 0), (14, 0), (7, 0),
# (28, 0))` (rhigh) tuples.
L_EXTBLOCK = (111, 0)
L_SALBLOCK = (28, 0)
# Real net-name text layers for `klt lvs`'s `EXTRACTION_DECK.metal_labels`
# (`klayout_tools.decks.sg13g2.EXTRACTION_DECK`: `metal_labels=((8, 25),
# (10, 25))`) -- **not** the same as `L_METAL1_LABEL`/`L_METAL2_LABEL`
# above ((8, 1)/(10, 1), "Metal1.label"/"Metal2.label" in sg13g2.lyp's own
# layer table), which are a *different*, purely-informational GDS
# text-layer convention `klt extract` does not read for net naming --
# confirmed by running `klt extract` against the pre-routing GDS and
# observing layer 8/1 and 10/1 both reported under `ignored_layers`, while
# every extracted net came back as an auto-generated `$N` name rather than
# the schematic net name the drawn `Metal1.label`/`Metal2.label` text
# already carried (issue #20's own routing gap: no physical wiring *and*
# labels on a layer the deck's own device/net-naming pass does not consult).
# `sg13g2.lyp`'s own `<source>` entries confirm the numbering: `Metal1.text`
# is `8/25`, `Metal2.text` is `10/25` (distinct from `Metal1.label`/
# `Metal2.label`'s `8/1`/`10/1`).
L_METAL1_TEXT = (8, 25)
L_METAL2_TEXT = (10, 25)

# Issue #157: the *real* net-naming layers above (`L_METAL1_TEXT`/
# `L_METAL2_TEXT`, `klt`'s `EXTRACTION_DECK.metal_labels`) and
# `L_GATPOLY_LABEL` (`EXTRACTION_DECK.poly_label=(5, 1)`, issue #152 --
# note this is a *different* purpose than its own name's "informational"
# framing above for `L_METAL1_LABEL`/`L_METAL2_LABEL`: for `GatPoly`,
# datatype 1 *is* the deck's real gate-net-naming layer, there being no
# separate `GatPoly.text` the deck reads instead) get their label text
# upper-cased before being drawn, here, centrally -- not at each call
# site -- to match `klayout.db.NetlistSpiceReader`'s own net-naming
# convention on the reference-conversion side (`layout/lvs_reference.py`).
#
# Root cause, confirmed interactively (not assumed) against the pip
# `klayout` package this repo already depends on: `NetlistSpiceReader`
# upper-cases *every* net name it reads, unconditionally, regardless of
# the input SPICE text's own case --
#
#   >>> nl = kdb.Netlist()
#   >>> nl.read("bandgap_startup.lvs_reference.spice", kdb.NetlistSpiceReader())
#   >>> [n.name for n in nl.top_circuit().each_net()]
#   ['VDD', 'DET', 'SNS1', 'VSS', 'FB']  # the file itself spells them
#                                        # "vdd"/"det"/"sns1"/"vss"/"fb"
#
# -- so a case fix applied to `layout/lvs_reference.py`'s *text* (the
# curation comment's Option 3) is a no-op: whatever case that script
# writes, the reference side always resolves to upper-case once read.
# The only side whose net-name case is actually a free variable is this
# one -- `klt extract`'s net-naming pass reads a GDS text label's case
# back *verbatim* (confirmed the same way: an un-fixed `bandgap_startup`
# `klt lvs --format json` run reports `net: {"layout": "det", "reference":
# "DET"}`, the layout side preserving this module's own lower-case
# schematic-net-name spelling). This is issue #157's own Option 1 (match
# the reader's convention at the label-drawing boundary), applied once,
# centrally, in `Builder.label()` -- not repeated as a literal-case edit
# at every `draw_npn13g2`/`draw_hv_mos`/`draw_poly_res`/`draw_gate_tab`
# net-name argument -- so it generalises to any current or future net
# with no per-net enumeration, unlike a `hints.same_nets` entry (Option 2).
#
# `klt lvs`'s own `NetlistComparer` pairs devices/nets by *structure*, not
# by name (that is the entire point of an LVS compare) -- so this is a
# cosmetic-to-the-compare, case-only change: it does not, and must not,
# alter which physical devices or nets pair against which schematic ones.
_NET_NAME_LAYERS = frozenset({L_METAL1_TEXT, L_METAL2_TEXT, L_GATPOLY_LABEL})

LAYER_NAMES: dict[tuple[int, int], str] = {
    L_ACTIV: "Activ.drawing",
    L_GATPOLY: "GatPoly.drawing",
    L_GATPOLY_LABEL: "GatPoly.label",
    L_NSD: "nSD.drawing",
    L_CONT: "Cont.drawing",
    L_METAL1: "Metal1.drawing",
    L_METAL1_LABEL: "Metal1.label",
    L_PSD: "pSD.drawing",
    L_VIA1: "Via1.drawing",
    L_METAL2: "Metal2.drawing",
    L_METAL2_LABEL: "Metal2.label",
    L_NWELL: "NWell.drawing",
    L_EMWIND: "EmWind.drawing",
    L_POLYRES: "PolyRes.drawing",
    L_POLYRES_LABEL: "PolyRes.label",
    L_TEXT: "TEXT.drawing",
    L_EXTBLOCK: "EXTBlock.drawing",
    L_SALBLOCK: "SalBlock.drawing",
    L_METAL1_TEXT: "Metal1.text",
    L_METAL2_TEXT: "Metal2.text",
}

# npn13G2's own emitter-stripe pitch and unit emitter-window size, read
# directly from the PDK's native PyCell source
# (ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/ihp/npn13G2_code.py,
# genLayout()) -- not re-derived or guessed. stepX is the X pitch the real
# PCell places each of Nx emitter stripes on; EMITTER_LE/EMITTER_WE are the
# default emitter-window length/width params (le='0.9u', we='0.07u' in
# defineParamSpecs) the schematic's Q1/Q2/Q3 instances leave at default.
HBT_STEP_X_UM = 1.85
EMITTER_LE_UM = 0.9
EMITTER_WE_UM = 0.07
# Half-extent of the outer pSD/TRANS/Activ boundary polygons around a single
# (Nx=1) emitter stripe, read off the same genLayout() Point(...) literals
# (the pSD polygon's x half-extent is stretchX+3.35 / -3.35; its y half-extent
# is 3.33+we/2 / -(2.88+we/2), we~0 at the default we=0.07u -- rounded here to
# a single representative margin since this module draws a simplified
# footprint, not the pcell's exact multi-layer stackup).
HBT_MARGIN_X_UM = 3.35
HBT_HALF_HEIGHT_UM = 3.1


class Builder(BuilderBase):
    """``kdb.Layout``/cell/layer setup plus small box/label/text primitives.

    All coordinates taken by these methods are in microns (float); converted
    to the layout's integer database units (``dbu = 0.001``, i.e. 1 nm) by
    rounding, matching the fleet's existing ``layout/common/klayout_builder.py``
    convention (gf180-bandgap). ``_u``/``box``/``write`` are inherited from
    :class:`_klayout_builder_base.BuilderBase`; ``label`` is SG13G2-specific.

    ``layout``, when given (issue #169's ``bandgap_top/generate.py``), lets a
    hierarchical-assembly script build this cell inside a ``kdb.Layout`` that
    already has other cells read into it (e.g. via ``kdb.Layout.read()`` on
    each leaf cell's own committed GDS) -- the same optional-parameter
    pattern ``layout/common_sg13cmos5l.py``'s own ``Builder`` already
    established for its sibling ``sg13cmos5l-bandgap_top`` assembly. Default
    ``None`` preserves every existing call site's own behaviour exactly (a
    fresh, empty ``kdb.Layout``).
    """

    def __init__(self, top_cell: str, layout: kdb.Layout | None = None) -> None:
        super().__init__(top_cell, LAYER_NAMES, layout=layout)

    def label(self, layer: tuple[int, int], text: str, x: float, y: float) -> None:
        idx = self._layers[layer]
        # Issue #157: fold to upper-case on the deck's real net-naming
        # layers only (see `_NET_NAME_LAYERS`'s own module-level comment) --
        # every other layer (`L_TEXT`, `L_METAL1_LABEL`/`L_METAL2_LABEL`/
        # `L_POLYRES_LABEL`'s purely-informational duplicates, instance-name
        # annotations) is left exactly as each call site spells it.
        if layer in _NET_NAME_LAYERS:
            text = text.upper()
        self.cell.shapes(idx).insert(kdb.Text(text, self._u(x), self._u(y)))


def draw_npn13g2(
    b: Builder,
    name: str,
    nx: int,
    x0: float,
    y0: float,
    collector_net: str,
    base_net: str,
    emitter_net: str,
) -> dict:
    """Draw a simplified ``npn13G2`` footprint at ``Nx`` emitter multiplicity.

    Faithfully replicates the *one* geometric fact this issue's tooling-
    friction check turned on: the PDK's own PyCell (``npn13G2_code.py``)
    loops ``for pcIndexX in range(Nx)`` and draws a **separate** ``EmWind``
    window (plus its own local ``Via1``/``Cont`` pair) at each
    ``stepX * pcIndexX`` position -- Nx real, independently-drawn emitter
    stripes on a fixed pitch, not a single shape whose parameters merely
    scale a SPICE model. Collector/base/emitter metal rails are drawn once,
    spanning the full stripe row, matching the same PyCell's own
    ``stretchX = stepX*(Nx-1)``-wide rail rectangles.

    This is a *simplified representative* footprint, not a re-implementation
    of the pcell's full ~15-layer stackup (base poly, STI, nSD block
    polygon, thermal pseudo-layer, etc. are omitted) -- see
    ``layout/README.md`` "What this layout is / is not" for the explicit
    scope of the simplification.

    Each metal terminal is labeled twice: once on ``Metal1.label``/
    ``Metal2.label`` (``(8, 1)``/``(10, 1)``, purely informational -- the
    original convention this module shipped with, issue #11) and once on
    ``Metal1.text``/``Metal2.text`` (``(8, 25)``/``(10, 25)``), the layer
    `klt`'s ``sg13g2`` curated deck's ``EXTRACTION_DECK.metal_labels``
    actually reads for net naming (issue #20 -- see ``layout/common.py``'s
    own module-level comment on ``L_METAL1_TEXT``/``L_METAL2_TEXT`` for how
    this was confirmed).

    Returns a dict of this device's terminal geometry (each a ``(x0, y0,
    x1, y1)`` box in microns, plus ``"width"`` in microns), for
    ``issue #20``'s routing pass (each cell's own ``generate.py``) to wire
    up against the shared nets the schematic declares -- this drawing
    function itself draws no wiring *between* devices, only the one
    device's own footprint and terminal pads (see ``layout/README.md``
    "What this layout is / is not").
    """
    stretch_x = HBT_STEP_X_UM * (nx - 1)
    x_lo = x0 - HBT_MARGIN_X_UM
    x_hi = x0 + stretch_x + HBT_MARGIN_X_UM
    y_lo = y0 - HBT_HALF_HEIGHT_UM
    y_hi = y0 + HBT_HALF_HEIGHT_UM

    # Base diffusion / device outline.
    b.box(L_ACTIV, x_lo, y_lo, x_hi, y_hi)

    # One EmWind + local Via1 pair per emitter stripe -- the real, per-issue
    # multi-stripe check (see docstring above).
    for i in range(nx):
        xc = x0 + HBT_STEP_X_UM * i
        b.box(
            L_EMWIND,
            xc - EMITTER_WE_UM / 2,
            y0 - EMITTER_LE_UM / 2,
            xc + EMITTER_WE_UM / 2,
            y0 + EMITTER_LE_UM / 2,
        )
        # Cont y-extent is 0.18um (>= the deck's cont.width.1 0.16um floor,
        # see layout/README.md "DRC/LVS verification" -- issue #12 found the
        # original 0.15um extent 10nm under threshold and widened it here;
        # only the outer edge moves, growing into the Activ region's own
        # generous margin rather than encroaching on the EmWind gap below).
        b.box(L_CONT, xc - 0.15, y0 - EMITTER_LE_UM / 2 - 0.23, xc + 0.15, y0 - EMITTER_LE_UM / 2 - 0.05)
        b.box(L_CONT, xc - 0.15, y0 + EMITTER_LE_UM / 2 + 0.05, xc + 0.15, y0 + EMITTER_LE_UM / 2 + 0.23)

    # Collector rail (top), base rail (bottom), emitter rail (Metal2, over
    # the emitter windows) -- one each, spanning the full stripe row, per
    # the pcell's own single collector-metal / base-metal / Metal2 rects.
    collector_pad = (x_lo, y_hi - 0.9, x_hi, y_hi - 0.5)
    b.box(L_METAL1, *collector_pad)
    b.label(L_METAL1_LABEL, f"{collector_net}", x0, y_hi - 0.7)
    b.label(L_METAL1_TEXT, collector_net, x0, y_hi - 0.7)

    base_pad = (x_lo, y_lo + 0.5, x_hi, y_lo + 0.9)
    b.box(L_METAL1, *base_pad)
    b.label(L_METAL1_LABEL, f"{base_net}", x0, y_lo + 0.7)
    b.label(L_METAL1_TEXT, base_net, x0, y_lo + 0.7)

    emitter_pad = (x_lo + 0.3, y0 - EMITTER_LE_UM / 2 - 0.3, x_hi - 0.3, y0 + EMITTER_LE_UM / 2 + 0.3)
    b.box(L_METAL2, *emitter_pad)
    b.label(L_METAL2_LABEL, f"{emitter_net}", x0, y0)
    b.label(L_METAL2_TEXT, emitter_net, x0, y0)

    b.label(L_TEXT, f"{name}(npn13G2,Nx={nx})", x0, y_hi + 0.6)
    return {
        "width": x_hi - x_lo,
        "collector_pad": collector_pad,
        "base_pad": base_pad,
        "emitter_pad": emitter_pad,
    }


# Well/substrate-tap ring geometry (issue #155, T1 tracker #4 item 4's last
# remaining `bandgap_startup` LVS gap). `klt`'s curated `sg13g2` deck draws
# no distinct tap mask of its own (`EXTRACTION_DECK.tap=None`) -- instead it
# *derives* an equivalent tap region from the opposite-doping implant marker
# already used for ordinary MOS source/drain recognition
# (`tap_nplus=(7,0)`/nSD, `tap_pplus=(14,0)`/pSD, `klayout-tools#1273`,
# mirroring gf180mcu's own #1084): an nSD-covered `Activ` shape *inside*
# `NWell` is a well tie (opposite doping from a PMOS's own source/drain,
# which this module draws with no implant marker at all under the
# active/poly/nwell idiom -- see below), and a pSD-covered `Activ` shape
# *outside* every `NWell` is a substrate tie (opposite doping from an NMOS's
# own `nSD`-marked source/drain, drawn just above). Before this issue,
# `draw_hv_mos` drew neither, so every MOS body terminal extracted to an
# anonymous (`pfet`, no tap-to-`NWell` connectivity at all) or
# deck-synthesized global `vsubs` (`nfet`, the deck's own `connect_global`
# fallback) net -- never the schematic's real body tie.
#
# Placement: a compact tap island sits `TAP_GAP_UM` clear of the device's
# own `Activ` box (>= `activ.space.1`'s 0.21um floor, margin) on whichever
# side (`+y`/"source" or `-y`/"drain") the tap's own body net matches an
# already-drawn terminal pad, plus a short `Metal1` bridge that physically
# overlaps that pad by `TAP_BRIDGE_OVERLAP_UM` -- so the tap rides along on
# *real* geometric connectivity to whatever net that pad's own later routing
# resolves to (each cell's own `_route()` already merges every leg's source
# pad into one continuous `vdd` rail / drain pad into one continuous `vss`
# rail -- see `bandgap_core/generate.py`'s and `bandgap_startup/generate.py`'s
# own module docstrings), not merely a same-spelled label on an otherwise
# disconnected island. The tap's own `Metal1` pad is labeled with the body
# net too (belt-and-suspenders, same double-labeling convention as every
# other terminal in this module) -- for an `nfet` body this is also what
# resolves the deck's synthesized `vsubs` global to the real net name (see
# `klayout_tools.extract`'s own `_detect_diode_substrate_label_divergence`
# docstring: "a p+/Comp tap contacted up to a VSS-labelled Metal1 gives the
# ... net VSS, not vsubs" -- the identical mechanism, confirmed against the
# installed `klayout-tools` source for this issue, not merely assumed).
#
# Issue #184: the bridge above is only drawn when `body_net` actually equals
# the terminal pad it would overlap (`source_net` on the `+y` side,
# `drain_net` on the `-y` side) -- an instance whose body ties to neither
# (`draw_hv_mos`'s own "External-body mode" docstring paragraph) still gets
# this same tap island, drawn and labeled identically, but left physically
# isolated: bridging it unconditionally would short `body_net` into a
# channel net it does not belong to. The caller's own routing pass wires
# the isolated tap to the real `body_net` elsewhere instead.
#
# No DRC rule in this curated deck's own `DECK` list constrains `NWell`,
# `nSD`, or `pSD` directly (only `Activ`/`GatPoly`/`Cont`/`Metal1`+ carry
# checks) -- so the only floors this geometry must clear are the ordinary
# `Activ`/`Cont`/`Metal1` ones already cited throughout this module
# (`activ.width.1` 0.15um, `activ.space.1` 0.21um,
# `activ.enclosing.cont.1`/`gatpoly.enclosing.cont.1` 0.07um, `cont.width.1`
# 0.16um, `metal1.width.1` 0.16um) -- all satisfied with real margin below.
TAP_GAP_UM = 0.25
TAP_ACTIV_UM = 0.34
TAP_IMPLANT_MARGIN_UM = 0.1
TAP_CONT_UM = 0.16
TAP_BRIDGE_W_UM = 0.2
TAP_BRIDGE_OVERLAP_UM = 0.05
TAP_NWELL_MARGIN_UM = 0.1


def draw_hv_mos(
    b: Builder,
    name: str,
    flavor: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    gate_net: str,
    source_net: str,
    drain_net: str,
    body_net: str | None = None,
) -> dict:
    """Draw a simplified ``sg13_hv_{n,p}mos`` footprint (Activ+GatPoly+Cont),
    plus one well/substrate-tap ring (issue #155, see the ``TAP_*`` module
    constants' own comment above).

    A generic single-finger MOS footprint (not read from a PDK PyCell source
    -- ``pmosHV_code.py``/``nmosHV_code.py`` exist in
    ``sg13g2_pycell_lib/ihp/`` but were not parsed for this issue's scope;
    the ``npn13G2``/``pnpMPA`` PyCells were, since those two devices are
    what this issue's tooling-friction checks are actually about). Sized to
    the real ``w``/``l`` the schematic instances (``M1``/``M2``/``M3``:
    ``w=10u l=1u``; startup's ``MSENSE``: ``w=10u l=0.5u`` (issue #32);
    ``MKFB``: ``w=2u l=0.5u``), with an
    ``NWell`` enclosure drawn for ``flavor='pmos'`` (SG13G2 PMOS is an
    n-well device, same as every PDK in the fleet).

    Source/drain terminals are labeled twice (``Metal1.label`` (8,1) for
    the original visual convention, ``Metal1.text`` (8,25) for `klt`'s real
    net-naming layer -- see ``draw_npn13g2``'s docstring for why). The gate
    terminal has no such second label: this curated deck declares no
    ``poly_label`` layer at all (``EXTRACTION_DECK.poly_label=None``), so a
    gate net's *name* can only come from a Metal1 pad it is wired to (see
    ``bandgap_startup/generate.py``'s ``draw_gate_tab`` use for ``det``) or,
    when a gate net's only members are other gates (``bandgap_core``'s
    ``fb``), it is never named at all -- LVS topology matching does not
    require it.

    ``body_net`` (issue #155) is the schematic's real body-terminal net for
    this instance -- every existing caller in this repo ties a PMOS's body
    to its own ``source_net`` and an NMOS's body to its own ``drain_net``
    (verified against every ``XM*``/``XQ*`` instance line in
    ``design/netlist/bandgap_core.spice``/``bandgap_startup.spice``: e.g.
    ``XM1 sns1 fb vdd vdd sg13_hv_pmos`` -- drain/gate/source/body =
    sns1/fb/vdd/vdd -- and ``XMSENSE det sns1 vss vss sg13_hv_nmos`` --
    drain/gate/source/body = det/sns1/vss/vss), so that pairing is this
    parameter's default when the caller leaves it unset, keeping every
    existing call site unchanged.

    **External-body mode (issue #184).** Pass ``body_net`` explicitly for an
    instance whose body ties to *neither* of its own ``source_net``/
    ``drain_net`` (``design/netlist/bandgap_amp.spice``'s ``MP1``/``MP2``:
    body tied to ``vdd``, channel nets ``tail``/``d1`` and ``tail``/``d2``).
    In that case this function still draws and labels the tap pad (on
    whichever side -- source or drain -- the flavor's own convention below
    selects) but skips the ``Metal1`` bridge that would otherwise connect it
    to that side's own channel pad: the bridge is only electrically correct
    when ``body_net`` actually equals that pad's own net, and drawing it
    unconditionally for a ``body_net`` that matches neither would physically
    short the channel net (here, ``tail``) to the body net (here, ``vdd``).
    The returned ``"tap_pad"`` is left for the caller's own routing pass to
    wire to the real ``body_net`` elsewhere (e.g. a cell's own ``vdd``
    trunk) -- see ``bandgap_amp/generate.py``'s own ``_route()`` for the
    concrete example.

    Returns a dict of this device's terminal geometry (each a ``(x0, y0,
    x1, y1)`` box in microns; ``"gate_box"`` is the drawn ``GatPoly``
    rectangle, ``"gate_y_lo"``/``"gate_y_hi"`` the channel-length band a
    routing pass can safely widen a connecting poly bar within; ``"tap_pad"``
    the drawn tap ring's own ``Metal1`` box; plus ``"width"`` in microns),
    for issue #20's routing pass to use -- see ``draw_npn13g2``'s docstring
    for the same convention.
    """
    ext = 0.4
    x_lo = x0 - w_um / 2
    x_hi = x0 + w_um / 2
    y_lo = y0 - (l_um / 2 + ext)
    y_hi = y0 + (l_um / 2 + ext)

    if body_net is None:
        body_net = source_net if flavor == "pmos" else drain_net
    # Which existing terminal (source, at the +y/top edge, or drain, at the
    # -y/bottom edge -- this module's own fixed drawing convention) the tap
    # ring's bridge reaches for. Defaults to the flavor's own documented
    # convention above when `body_net` matches neither exactly, so a future
    # caller passing an unrelated `body_net` still gets a labeled (if
    # unbridged) tap rather than a `KeyError`/crash.
    tap_at_source = body_net == source_net or (
        body_net != drain_net and flavor == "pmos"
    )
    if tap_at_source:
        tap_y_lo = y_hi + TAP_GAP_UM
        tap_y_hi = tap_y_lo + TAP_ACTIV_UM
    else:
        tap_y_hi = y_lo - TAP_GAP_UM
        tap_y_lo = tap_y_hi - TAP_ACTIV_UM
    tap_x_lo = x0 - TAP_ACTIV_UM / 2
    tap_x_hi = x0 + TAP_ACTIV_UM / 2

    b.box(L_ACTIV, x_lo, y_lo, x_hi, y_hi)
    gate_box = (x_lo - 0.1, y0 - l_um / 2, x_hi + 0.1, y0 + l_um / 2)
    b.box(L_GATPOLY, *gate_box)
    b.label(L_GATPOLY_LABEL, gate_net, x0, y0)

    if flavor == "pmos":
        # NWell must enclose the tap ring too (the well-tie derivation
        # requires the tap's own nSD-marked Activ to sit *inside* this same
        # NWell island) -- extended on whichever side the tap landed on,
        # past its own outer edge by TAP_NWELL_MARGIN_UM; the opposite edge
        # keeps the original 0.4um margin unchanged.
        nwell_y_lo = y_lo - 0.4
        nwell_y_hi = y_hi + 0.4
        if tap_at_source:
            nwell_y_hi = max(nwell_y_hi, tap_y_hi + TAP_NWELL_MARGIN_UM)
        else:
            nwell_y_lo = min(nwell_y_lo, tap_y_lo - TAP_NWELL_MARGIN_UM)
        b.box(L_NWELL, x_lo - 0.4, nwell_y_lo, x_hi + 0.4, nwell_y_hi)
    else:
        b.box(L_NSD, x_lo - 0.1, y_lo - 0.1, x_hi + 0.1, y_hi + 0.1)

    # Source/drain contact + Metal1 pad, one strip each side of the gate.
    # Cont y-extent is 0.18um (>= the deck's cont.width.1 0.16um floor, same
    # margin/rationale as draw_npn13g2's own Cont boxes above -- widening
    # only the edge closer to the gate, still fully inside the Metal1 pad).
    b.box(L_CONT, x_lo + 0.15, y_hi - 0.28, x_hi - 0.15, y_hi - 0.1)
    source_pad = (x_lo, y_hi - 0.35, x_hi, y_hi)
    b.box(L_METAL1, *source_pad)
    b.label(L_METAL1_LABEL, source_net, x0, y_hi - 0.15)
    b.label(L_METAL1_TEXT, source_net, x0, y_hi - 0.15)

    b.box(L_CONT, x_lo + 0.15, y_lo + 0.1, x_hi - 0.15, y_lo + 0.28)
    drain_pad = (x_lo, y_lo, x_hi, y_lo + 0.35)
    b.box(L_METAL1, *drain_pad)
    b.label(L_METAL1_LABEL, drain_net, x0, y_lo + 0.15)
    b.label(L_METAL1_TEXT, drain_net, x0, y_lo + 0.15)

    # Tap ring: a small, separate Activ island (never touching the device's
    # own source/drain Activ above -- TAP_GAP_UM clears activ.space.1) on
    # the opposite-doping implant marker, contacted and landed on Metal1,
    # bridged into whichever pad (source or drain) carries this instance's
    # own body_net.
    tap_implant = L_NSD if flavor == "pmos" else L_PSD
    b.box(L_ACTIV, tap_x_lo, tap_y_lo, tap_x_hi, tap_y_hi)
    b.box(
        tap_implant,
        tap_x_lo - TAP_IMPLANT_MARGIN_UM,
        tap_y_lo - TAP_IMPLANT_MARGIN_UM,
        tap_x_hi + TAP_IMPLANT_MARGIN_UM,
        tap_y_hi + TAP_IMPLANT_MARGIN_UM,
    )
    tap_y_center = (tap_y_lo + tap_y_hi) / 2
    cont_half = TAP_CONT_UM / 2
    b.box(
        L_CONT,
        x0 - cont_half,
        tap_y_center - cont_half,
        x0 + cont_half,
        tap_y_center + cont_half,
    )
    tap_pad = (tap_x_lo, tap_y_lo, tap_x_hi, tap_y_hi)
    b.box(L_METAL1, *tap_pad)
    b.label(L_METAL1_LABEL, body_net, x0, tap_y_center)
    b.label(L_METAL1_TEXT, body_net, x0, tap_y_center)

    # Issue #184: only draw the bridge when body_net actually matches the
    # terminal pad tap_at_source/tap_at_drain selected -- every existing
    # call site satisfies this (body_net defaults to that same terminal, see
    # this function's own docstring), so this is a no-op there. When it does
    # not match (external-body mode), the tap pad above is still drawn and
    # labeled, but left physically isolated for the caller's own routing
    # pass -- bridging it here would short body_net into a channel net it
    # does not actually belong to.
    bridge_target_net = source_net if tap_at_source else drain_net
    if body_net == bridge_target_net:
        bridge_x_lo, bridge_x_hi = x0 - TAP_BRIDGE_W_UM / 2, x0 + TAP_BRIDGE_W_UM / 2
        if tap_at_source:
            bridge_y_lo, bridge_y_hi = y_hi - TAP_BRIDGE_OVERLAP_UM, tap_y_lo
        else:
            bridge_y_lo, bridge_y_hi = tap_y_hi, y_lo + TAP_BRIDGE_OVERLAP_UM
        b.box(L_METAL1, bridge_x_lo, bridge_y_lo, bridge_x_hi, bridge_y_hi)

    b.label(L_TEXT, f"{name}({flavor} w={w_um}u l={l_um}u)", x0, y_hi + 0.6)
    return {
        "width": x_hi - x_lo,
        "source_pad": source_pad,
        "drain_pad": drain_pad,
        "gate_box": gate_box,
        "gate_y_lo": y0 - l_um / 2,
        "gate_y_hi": y0 + l_um / 2,
        "tap_pad": tap_pad,
    }


# rppd/rhigh recognition geometry constants (issue #20). klt's curated
# sg13g2 deck's `ResistorDevice.body` for every poly-resistor flavour is
# `GatPoly.drawing` (5, 0) -- **not** `PolyRes.drawing` (128, 0), which is
# only the *marker* layer ANDed with it (`klayout_tools.decks.sg13g2
# .EXTRACTION_DECK.resistors`'s own `body=(5, 0)` field; confirmed reading
# `klayout_tools.extract._resolve_resistors`, whose `body = base(GatPoly) &
# marker(PolyRes) & requires... - excludes...`). Before this issue,
# `draw_poly_res` drew only `PolyRes` -- with no `GatPoly` present at all,
# `body` always came out empty and the resistor was never recognised,
# independent of which marker layers were drawn. Fixing that means drawing a
# `GatPoly` bar *longer* than the `PolyRes`/`EXTBlock`/`pSD`/`SalBlock`
# marked "core" segment: the recognised device's own terminals are `body -
# segment` (the deck's own `terminal` field defaults to `body`, i.e.
# `GatPoly` again) -- if `GatPoly` exactly matched the core's extent, the
# whole bar would BE the recognised segment and no `GatPoly` conductor would
# remain to contact for either terminal. `RES_HEAD_UM` is that extra
# per-end length, `RES_GATPOLY_Y_MARGIN_UM` is the GatPoly-widens-past-the-
# marked-core Y-margin `gatpoly.enclosing.cont.1` (0.07um floor) needs once
# the previously poly-absent end contacts land on real GatPoly (both
# verified DRC-clean by this issue's own `klt drc` re-run, not merely
# asserted).
RES_HEAD_UM = 0.4
RES_GATPOLY_Y_MARGIN_UM = 0.1
RES_CONT_LEN_UM = 0.2
RES_CONT_MARGIN_UM = 0.1

#: Minimum drawn space between two adjacent serpentine legs (issue #173's
#: fold). The notch between two legs of one folded resistor is an ordinary
#: `GatPoly` space, whose floor is `gatpoly.space.1` = 0.18 um -- 0.4 um
#: clears it by 0.22 um, and still leaves 0.3 um of clearance once a
#: terminal head's `RES_GATPOLY_Y_MARGIN_UM` overhang eats into the gap next
#: to its neighbouring leg. This is a *floor*, not the drawn value:
#: :func:`~_klayout_builder_base.fold_plan` may return a gap up to `legs`
#: nanometres larger, which is how it keeps the folded conductor's total
#: length exactly equal to the schematic's own `l` (see its docstring).
RES_FOLD_GAP_UM = 0.4


def draw_poly_res(
    b: Builder,
    name: str,
    flavor: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    end_a_net: str,
    end_b_net: str,
    legs: int = 1,
) -> dict:
    """Draw a folded (serpentine) ``rppd``/``rhigh`` resistor body.

    Sized to the schematic's own committed ``w``/``l`` (``rppd`` R1/R2,
    ``rhigh`` RPU). ``legs`` is how many parallel vertical bars the ``l_um``
    of conductor is folded into; ``legs=1`` is the degenerate straight bar.

    **Why this is folded (issue #173).** Drawn straight, ``R1``
    (``l=511u``) and ``RPU`` (``l=1411.3u``) are sub-mm to ~1.4 mm bars that
    single-handedly set their cells' bounding boxes:
    ``measurements/2026-09-layout-area/`` measured ``bandgap_startup`` at
    **63.7:1** and the ``sg13cmos5l`` assembly at 77.5% aspect-ratio
    whitespace. Folding attacks exactly that: the same conductor, bent, so
    the cell's footprint stops being set by one dimension of one device.
    ``legs`` is chosen per call site (see each ``generate.py``) rather than
    derived here -- a resistor's fold count is a floorplan decision, not a
    property of the device.

    **The fold conserves length exactly, so it conserves resistance.**
    :func:`~_klayout_builder_base.fold_plan` derives the leg height and the
    inter-leg gap in whole nanometres such that ``legs*h + (legs-1)*gap`` is
    ``l_um`` exactly -- see its docstring for the derivation and for why the
    gap it returns can exceed ``RES_FOLD_GAP_UM`` by a few nanometres. This
    is a nominal-value-preserving transform, not a re-sizing: what folding
    *does* change is the device's parasitics (a compact block couples
    differently than a 1.4 mm bar) and its matching behaviour (a folded
    block sees a far smaller across-die gradient than a bar 1.4 mm long, so
    ``R1``/``R2`` matching improves rather than degrades). It also leaves the
    drawn *area* and *perimeter* of the marked core unchanged from the
    straight bar (``area == l_um * w_um`` either way -- ``fold_plan``), so
    the substrate-coupling parasitic the PEX flow extracts from this device
    is not systematically shifted by the fold either.

    **Geometry.** ``legs`` vertical bars, leg ``i`` spanning
    ``x in [x0 + i*pitch, x0 + i*pitch + w_um]`` and
    ``y in [y0, y0 + leg_len]``, joined by ``w_um``-thick links that
    alternate top (even ``i``) and bottom (odd ``i``). ``(x0, y0)`` is
    therefore the **lower-left corner of the marked core**, not a bar
    centreline as in the pre-fold signature. The two free ends are leg 0's
    bottom and, for an even ``legs``, leg ``legs-1``'s bottom (so both
    terminals sit on the same row, the way the straight bar's two ends
    sat on the same row) -- or, for an odd ``legs``, leg ``legs-1``'s top.

    **rppd/rhigh recognition (issue #20, preserved through the fold).** The
    marked "core" -- the serpentine itself -- is drawn on ``GatPoly`` (the
    deck's real resistor *body* layer, see the ``RES_*`` module constants'
    own docstring above) plus the marker layers each flavour's own
    recognition requires
    (``klayout_tools.decks.sg13g2.EXTRACTION_DECK.resistors``): ``rppd``
    needs ``EXTBlock`` (111,0), ``pSD`` (14,0), ``SalBlock`` (28,0);
    ``rhigh`` needs those same three **plus** ``nSD`` (7,0) over the same
    segment -- the one layer that positively disambiguates it from ``rppd``
    (whose own ``excludes`` drops any segment carrying ``nSD``, precisely so
    a segment carrying both implants can only ever match ``rhigh``, never
    ``rppd``). ``flavor="rhigh"`` (``RPU``) therefore additionally draws
    ``nSD``; ``flavor="rppd"`` (``R1``/``R2``) does not. Every marker layer
    is drawn on **exactly** the same box set as the ``GatPoly`` core, so the
    recognised segment is the whole serpentine and no fold corner is left
    un-marked (which would split one device into a series chain the
    reference netlist's single R card could not pair against).

    ``GatPoly`` extends ``RES_HEAD_UM`` microns past each of the two free
    ends as a *wider* "dog-bone" head -- the recognised device's un-marked
    terminal, which is where the end contacts land. Each head is
    ``RES_GATPOLY_Y_MARGIN_UM`` microns wider than the leg's own ``w_um``
    (clearing ``gatpoly.enclosing.cont.1``'s 0.07um floor around the end
    contacts) -- but the legs and links themselves stay exactly ``w_um``
    across, with **no** margin added. This matters beyond DRC: `klt`'s
    native resistor extractor (``kdb.DeviceExtractorResistor``) requires the
    *un-marked* conductor left after the marked core is cut out to split
    into exactly **two** disjoint polygons (one per terminal), and the only
    un-marked ``GatPoly`` this function draws is those two heads.
    (Historically, an early uniform-width version of the straight bar left a
    thin un-marked sliver along the core's edge joining both heads into one
    polygon, and `klt extract` logged ``"Expected two polygons on contacts
    interacting with one resistor shape (found 1) - resistor shape ignored"``
    and dropped the device -- verified directly at the time, and the reason
    the no-margin-on-the-core rule is stated as a rule here.)

    The inter-leg gap ``fold_plan`` returns is a real DRC quantity: the notch
    between two adjacent legs is a ``GatPoly`` space, floor 0.18um
    (``gatpoly.space.1``). ``RES_FOLD_GAP_UM`` (0.4) clears it with 0.22um to
    spare, which is also what keeps each head's ``RES_GATPOLY_Y_MARGIN_UM``
    overhang clear of its neighbouring leg (0.3um of the 0.4um gap survives
    the overhang).

    End-pad terminals are labeled twice, same convention as
    ``draw_npn13g2``/``draw_hv_mos`` above (``Metal1.label``/(8,1) plus the
    real net-naming ``Metal1.text``/(8,25)).

    Returns this device's terminal geometry (``"end_a_pad"``/``"end_b_pad"``,
    each a ``(x0, y0, x1, y1)`` Metal1 box in microns), its ``"length"``, the
    ``"plan"`` :func:`fold_plan` produced, and ``"bbox"`` -- the drawn
    footprint including both heads' Metal1 pads, for a caller's own
    floorplanning.
    """
    plan = fold_plan(w_um, l_um, legs, RES_FOLD_GAP_UM)
    leg_len = plan["leg_len_um"]
    pitch = plan["pitch_um"]
    y_top = y0 + leg_len

    def leg_x(i: int) -> float:
        return x0 + i * pitch

    # -- the marked core: `legs` vertical bars plus the alternating links.
    core: list[tuple[float, float, float, float]] = [
        (leg_x(i), y0, leg_x(i) + w_um, y_top) for i in range(legs)
    ]
    for i in range(legs - 1):
        if i % 2 == 0:  # link at the top of legs i / i+1
            core.append((leg_x(i) + w_um, y_top - w_um, leg_x(i + 1), y_top))
        else:  # link at the bottom
            core.append((leg_x(i) + w_um, y0, leg_x(i + 1), y0 + w_um))

    core_layers = [L_GATPOLY, L_POLYRES, L_EXTBLOCK, L_PSD, L_SALBLOCK]
    if flavor == "rhigh":
        core_layers.append(L_NSD)
    for layer in core_layers:
        for box in core:
            b.box(layer, *box)
    b.label(L_POLYRES_LABEL, f"{name}", x0 + plan["width_um"] / 2, (y0 + y_top) / 2)

    def _terminal(index: int, at_top: bool, net: str) -> tuple[float, float, float, float]:
        """Draw one free end's dog-bone head + Cont + Metal1 pad; return the pad."""
        head_x0 = leg_x(index) - RES_GATPOLY_Y_MARGIN_UM
        head_x1 = leg_x(index) + w_um + RES_GATPOLY_Y_MARGIN_UM
        if at_top:
            head_y0, head_y1 = y_top, y_top + RES_HEAD_UM
            cont_y1 = head_y1 - RES_CONT_MARGIN_UM
            cont_y0 = cont_y1 - RES_CONT_LEN_UM
            pad = (head_x0 - 0.1, head_y0, head_x1 + 0.1, head_y1 + 0.1)
        else:
            head_y0, head_y1 = y0 - RES_HEAD_UM, y0
            cont_y0 = head_y0 + RES_CONT_MARGIN_UM
            cont_y1 = cont_y0 + RES_CONT_LEN_UM
            pad = (head_x0 - 0.1, head_y0 - 0.1, head_x1 + 0.1, head_y1)
        b.box(L_GATPOLY, head_x0, head_y0, head_x1, head_y1)
        b.box(L_CONT, leg_x(index), cont_y0, leg_x(index) + w_um, cont_y1)
        b.box(L_METAL1, *pad)
        pad_cx, pad_cy = (pad[0] + pad[2]) / 2, (pad[1] + pad[3]) / 2
        b.label(L_METAL1_LABEL, net, pad_cx, pad_cy)
        b.label(L_METAL1_TEXT, net, pad_cx, pad_cy)
        return pad

    # End A is always leg 0's bottom. End B is the last leg's *free* end:
    # bottom for an even leg count (both terminals on the same row), top for
    # an odd one -- the links alternate, so the parity fixes which it is.
    end_a_pad = _terminal(0, at_top=False, net=end_a_net)
    end_b_pad = _terminal(legs - 1, at_top=(legs % 2 == 1), net=end_b_net)

    b.label(
        L_TEXT,
        f"{name}({flavor} w={w_um}u l={l_um}u x{legs})",
        x0 + plan["width_um"] / 2,
        y_top + RES_HEAD_UM + 0.5 if legs % 2 == 1 else y_top + 0.5,
    )
    bbox = (
        min(end_a_pad[0], end_b_pad[0], x0),
        min(end_a_pad[1], end_b_pad[1], y0),
        max(end_a_pad[2], end_b_pad[2], x0 + plan["width_um"]),
        max(end_a_pad[3], end_b_pad[3], y_top),
    )
    return {
        "length": l_um,
        "end_a_pad": end_a_pad,
        "end_b_pad": end_b_pad,
        "plan": plan,
        "bbox": bbox,
    }


# --------------------------------------------------------------------------- #
# Routing primitives (issue #20) -- top-level Metal1/Metal2/Via1 wiring
# connecting the terminal pads the three ``draw_*`` functions above return,
# to the shared nets ``design/netlist/bandgap_core.spice``/
# ``bandgap_startup.spice`` declare. Each cell's own ``generate.py`` calls
# these directly with its own net map (see each file's module docstring)
# rather than this module owning a generic net-list-driven autorouter --
# the two cells' floorplans are different enough (row/column layout vs.
# devices spread across a >1mm resistor bar) that a bespoke per-net call
# sequence is clearer than a one-size-fits-all algorithm here.
# ``route_h``/``route_v`` are PDK-agnostic (issue #78); re-exported above
# from ``_klayout_builder_base`` so this module's own name stays stable.
# --------------------------------------------------------------------------- #


def via1_tap(b: Builder, x_center: float, y_center: float, size: float = 0.25) -> None:
    """Drop a square ``Via1`` landing at ``(x_center, y_center)``, bridging
    an already-overlapping ``Metal1`` shape below to an already-overlapping
    ``Metal2`` shape above (the caller is responsible for ensuring both
    metal shapes actually cover this footprint -- this only draws the via
    cut itself). ``size=0.25`` clears the curated deck's ``via1.width.1``
    floor (0.19um) with margin, and (with the default ``route_h``/
    ``route_v`` width of 0.3) leaves >=0.01um `Metal1`/`Metal2` enclosure
    on every side, clearing ``metal1.enclosing.via1.1`` (0.01um; this deck
    does not model a Metal2-encloses-Via1 rule at all -- see
    ``klayout_tools.decks.sg13g2``'s own ``DECK`` list).
    """
    half = size / 2
    b.box(L_VIA1, x_center - half, y_center - half, x_center + half, y_center + half)


def draw_gate_tab(
    b: Builder,
    edge_x: float,
    y_center: float,
    net: str,
    side: str,
    reach: float = 0.7,
    pad_w: float = 0.4,
    tab_h: float = 0.34,
    cont_size: float = 0.16,
) -> tuple[float, float, float, float]:
    """Extend a ``GatPoly`` gate edge with a poly tab + ``Cont`` + ``Metal1``
    pad, bringing an otherwise metal-inaccessible gate net out to Metal1 for
    routing to a *non*-gate terminal elsewhere (contrast ``bandgap_core``'s
    ``fb`` net, routed gate-to-gate directly on ``GatPoly`` with no tab at
    all -- see that cell's ``generate.py``). Needed by
    ``bandgap_startup``'s ``MKFB.gate`` (``det``), which must reach
    ``RPU.end_b``/``MSENSE.source`` -- both Metal1 pads.

    ``edge_x`` is the existing gate rectangle's own edge (its drawn
    ``GatPoly`` box's left or right X coordinate, e.g. ``draw_hv_mos``'s
    returned ``"gate_box"`` entry); ``side='right'`` extends the tab from
    that edge in +x, ``side='left'`` in -x. The ``Cont``/``Metal1`` pad is
    placed in the tab's *outer* ``pad_w`` microns (away from ``edge_x``),
    not flush against it -- so the new Metal1 pad clears
    ``metal1.space.1``'s 0.18um floor against whatever Metal1 the original
    device already drew close to that same gate edge (e.g. MKFB's own
    ``fb``-net source pad sits only 0.1um past the bare gate edge; flush
    tab placement would put the two different-net Metal1 shapes 0.1um
    apart, a real violation -- pushing the pad out by ``reach - pad_w``
    first clears it, verified by this issue's own ``klt drc`` re-run).

    Default sizing clears every DRC rule this issue's routing exercises:
    ``tab_h=0.34``/``cont_size=0.16`` gives a symmetric 0.09um ``GatPoly``-
    encloses-``Cont`` margin (``gatpoly.enclosing.cont.1`` floor: 0.07um);
    ``pad_w=0.4``/``cont_size=0.16`` gives the same 0.12um margin in the
    other axis. A poly-only ``Cont`` (no ``Activ`` underneath) is exempt
    from ``activ.enclosing.cont.1`` by construction -- that rule's
    ``other_region.interacting(region)`` pre-filter only flags ``Cont``
    shapes that already touch ``Activ`` somewhere (see
    ``klayout_tools.drc._run_check``'s own docstring), which this tab's
    ``Cont`` never does.

    Returns the drawn Metal1 pad's ``(x0, y0, x1, y1)`` box for the
    caller's own routing.
    """
    if side == "right":
        tab_x0, tab_x1 = edge_x, edge_x + reach
        pad_x0, pad_x1 = edge_x + reach - pad_w, edge_x + reach
    elif side == "left":
        tab_x0, tab_x1 = edge_x - reach, edge_x
        pad_x0, pad_x1 = edge_x - reach, edge_x - reach + pad_w
    else:
        raise ValueError(f"side must be 'left' or 'right', got {side!r}")

    y0, y1 = y_center - tab_h / 2, y_center + tab_h / 2
    b.box(L_GATPOLY, tab_x0, y0, tab_x1, y1)

    cont_margin_x = (pad_w - cont_size) / 2
    cont_margin_y = (tab_h - cont_size) / 2
    b.box(L_CONT, pad_x0 + cont_margin_x, y0 + cont_margin_y, pad_x1 - cont_margin_x, y1 - cont_margin_y)

    pad = (pad_x0, y0, pad_x1, y1)
    b.box(L_METAL1, *pad)
    b.label(L_METAL1_LABEL, net, (pad_x0 + pad_x1) / 2, y_center)
    b.label(L_METAL1_TEXT, net, (pad_x0 + pad_x1) / 2, y_center)
    return pad
