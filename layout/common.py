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

# --------------------------------------------------------------------------- #
# SG13G2 GDS layer numbers, read from
# ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp (<source> entries), IHP-Open-PDK
# main @ 22f2a25 (2026-08-05), the same checkout spec/porting-plan.md cites.
# --------------------------------------------------------------------------- #
L_ACTIV = (1, 0)
L_ACTIV_LABEL = (1, 1)
L_GATPOLY = (5, 0)
L_GATPOLY_LABEL = (5, 1)
L_NSD = (7, 0)
L_CONT = (6, 0)
L_METAL1 = (8, 0)
L_METAL1_LABEL = (8, 1)
L_METAL1_PIN = (8, 2)
L_PSD = (14, 0)
L_VIA1 = (19, 0)
L_METAL2 = (10, 0)
L_METAL2_LABEL = (10, 1)
L_METAL2_PIN = (10, 2)
L_NWELL = (31, 0)
L_NBULAY = (32, 0)
L_EMWIND = (33, 0)
L_POLYRES = (128, 0)
L_POLYRES_LABEL = (128, 1)
L_TEXT = (63, 0)
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

LAYER_NAMES: dict[tuple[int, int], str] = {
    L_ACTIV: "Activ.drawing",
    L_ACTIV_LABEL: "Activ.label",
    L_GATPOLY: "GatPoly.drawing",
    L_GATPOLY_LABEL: "GatPoly.label",
    L_NSD: "nSD.drawing",
    L_CONT: "Cont.drawing",
    L_METAL1: "Metal1.drawing",
    L_METAL1_LABEL: "Metal1.label",
    L_METAL1_PIN: "Metal1.pin",
    L_PSD: "pSD.drawing",
    L_VIA1: "Via1.drawing",
    L_METAL2: "Metal2.drawing",
    L_METAL2_LABEL: "Metal2.label",
    L_METAL2_PIN: "Metal2.pin",
    L_NWELL: "NWell.drawing",
    L_NBULAY: "nBuLay.drawing",
    L_EMWIND: "EmWind.drawing",
    L_POLYRES: "PolyRes.drawing",
    L_POLYRES_LABEL: "PolyRes.label",
    L_TEXT: "TEXT.drawing",
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


class Builder:
    """``kdb.Layout``/cell/layer setup plus small box/label/text primitives.

    All coordinates taken by these methods are in microns (float); converted
    to the layout's integer database units (``dbu = 0.001``, i.e. 1 nm) by
    rounding, matching the fleet's existing ``layout/common/klayout_builder.py``
    convention (gf180-bandgap).
    """

    def __init__(self, top_cell: str) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = 0.001
        self.cell = self.layout.create_cell(top_cell)
        self._layers: dict[tuple[int, int], int] = {}
        for pair, name in LAYER_NAMES.items():
            index = self.layout.layer(*pair)
            self.layout.set_info(index, kdb.LayerInfo(pair[0], pair[1], name))
            self._layers[pair] = index

    def _u(self, value_um: float) -> int:
        return int(round(value_um / self.layout.dbu))

    def box(self, layer: tuple[int, int], x0: float, y0: float, x1: float, y1: float) -> None:
        idx = self._layers[layer]
        self.cell.shapes(idx).insert(
            kdb.Box(self._u(x0), self._u(y0), self._u(x1), self._u(y1))
        )

    def label(self, layer: tuple[int, int], text: str, x: float, y: float) -> None:
        idx = self._layers[layer]
        self.cell.shapes(idx).insert(kdb.Text(text, self._u(x), self._u(y)))

    def write(self, path: str) -> None:
        opts = kdb.SaveLayoutOptions()
        opts.gds2_write_timestamps = False
        self.layout.write(path, opts)


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
) -> dict:
    """Draw a simplified ``sg13_hv_{n,p}mos`` footprint (Activ+GatPoly+Cont).

    A generic single-finger MOS footprint (not read from a PDK PyCell source
    -- ``pmosHV_code.py``/``nmosHV_code.py`` exist in
    ``sg13g2_pycell_lib/ihp/`` but were not parsed for this issue's scope;
    the ``npn13G2``/``pnpMPA`` PyCells were, since those two devices are
    what this issue's tooling-friction checks are actually about). Sized to
    the real ``w``/``l`` the schematic instances (``M1``/``M2``/``M3``:
    ``w=10u l=1u``; startup's ``MSENSE``/``MKFB``: ``w=2u l=0.5u``), with an
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

    Returns a dict of this device's terminal geometry (each a ``(x0, y0,
    x1, y1)`` box in microns; ``"gate_box"`` is the drawn ``GatPoly``
    rectangle, ``"gate_y_lo"``/``"gate_y_hi"`` the channel-length band a
    routing pass can safely widen a connecting poly bar within; plus
    ``"width"`` in microns), for issue #20's routing pass to use -- see
    ``draw_npn13g2``'s docstring for the same convention.
    """
    ext = 0.4
    x_lo = x0 - w_um / 2
    x_hi = x0 + w_um / 2
    y_lo = y0 - (l_um / 2 + ext)
    y_hi = y0 + (l_um / 2 + ext)

    b.box(L_ACTIV, x_lo, y_lo, x_hi, y_hi)
    gate_box = (x_lo - 0.1, y0 - l_um / 2, x_hi + 0.1, y0 + l_um / 2)
    b.box(L_GATPOLY, *gate_box)
    b.label(L_GATPOLY_LABEL, gate_net, x0, y0)

    if flavor == "pmos":
        b.box(L_NWELL, x_lo - 0.4, y_lo - 0.4, x_hi + 0.4, y_hi + 0.4)
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

    b.label(L_TEXT, f"{name}({flavor} w={w_um}u l={l_um}u)", x0, y_hi + 0.6)
    return {
        "width": x_hi - x_lo,
        "source_pad": source_pad,
        "drain_pad": drain_pad,
        "gate_box": gate_box,
        "gate_y_lo": y0 - l_um / 2,
        "gate_y_hi": y0 + l_um / 2,
    }


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
) -> dict:
    """Draw a straight (unfolded) ``rppd``/``rhigh`` resistor body.

    Sized to the schematic's own committed ``w``/``l`` (``rppd`` R1/R2,
    ``rhigh`` RPU) -- drawn as a single straight ``PolyRes`` bar, **not**
    meandered/folded into a compact serpentine. For R1 (``l=694.5u``) and
    RPU (``l=1411.3u``) this makes for a very long, thin body (sub-mm to
    ~1.4 mm) -- an honest, literal rendering of the netlist's own
    (provisional, not yet simulation-verified per
    ``design/bandgap_core.sch``'s own header) sizing, not a claim that this
    is how the resistor would actually be folded for a compact final
    layout. See ``layout/README.md`` "What this layout is / is not".

    End-pad terminals are labeled twice, same convention as
    ``draw_npn13g2``/``draw_hv_mos`` above (``PolyRes.label``/(8,1) plus the
    real net-naming ``Metal1.text``/(8,25)).

    Returns a dict of this device's terminal geometry (``"end_a_pad"``/
    ``"end_b_pad"``, each a ``(x0, y0, x1, y1)`` Metal1 box in microns;
    ``"length"`` in microns), for issue #20's routing pass.
    """
    x_hi = x0 + l_um
    b.box(L_POLYRES, x0, y0 - w_um / 2, x_hi, y0 + w_um / 2)
    b.label(L_POLYRES_LABEL, f"{name}", (x0 + x_hi) / 2, y0)

    end_a_pad = (x0 - 0.2, y0 - w_um / 2 - 0.1, x0 + min(0.3, l_um / 4), y0 + w_um / 2 + 0.1)
    b.box(L_CONT, x0, y0 - w_um / 2, x0 + min(0.3, l_um / 4), y0 + w_um / 2)
    b.box(L_METAL1, *end_a_pad)
    b.label(L_METAL1_LABEL, end_a_net, x0, y0 + w_um / 2 + 0.4)
    b.label(L_METAL1_TEXT, end_a_net, x0, y0 + w_um / 2 + 0.4)

    end_b_pad = (x_hi - min(0.3, l_um / 4), y0 - w_um / 2 - 0.1, x_hi + 0.2, y0 + w_um / 2 + 0.1)
    b.box(L_CONT, x_hi - min(0.3, l_um / 4), y0 - w_um / 2, x_hi, y0 + w_um / 2)
    b.box(L_METAL1, *end_b_pad)
    b.label(L_METAL1_LABEL, end_b_net, x_hi, y0 + w_um / 2 + 0.4)
    b.label(L_METAL1_TEXT, end_b_net, x_hi, y0 + w_um / 2 + 0.4)

    b.label(L_TEXT, f"{name}({flavor} w={w_um}u l={l_um}u)", (x0 + x_hi) / 2, y0 - w_um / 2 - 0.8)
    return {"length": l_um, "end_a_pad": end_a_pad, "end_b_pad": end_b_pad}


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
# --------------------------------------------------------------------------- #


def route_h(b: Builder, layer: tuple[int, int], y_center: float, x0: float, x1: float, width: float = 0.3) -> None:
    """Draw a horizontal routing bar on ``layer`` at ``y_center``, spanning
    ``[x0, x1]`` (order-independent), ``width`` microns tall. Used to tie
    together terminal pads that already share a Y-band (e.g. every ``vdd``
    MOS source pad in ``bandgap_core``) or as one leg of an L-shaped route.
    """
    half = width / 2
    b.box(layer, min(x0, x1), y_center - half, max(x0, x1), y_center + half)


def route_v(b: Builder, layer: tuple[int, int], x_center: float, y0: float, y1: float, width: float = 0.3) -> None:
    """Draw a vertical routing bar on ``layer`` at ``x_center``, spanning
    ``[y0, y1]`` (order-independent), ``width`` microns wide -- the
    vertical-leg counterpart of :func:`route_h`.
    """
    half = width / 2
    b.box(layer, x_center - half, min(y0, y1), x_center + half, max(y0, y1))


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
