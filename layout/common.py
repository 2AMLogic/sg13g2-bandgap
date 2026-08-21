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
) -> float:
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
    scope of the simplification. Returns the drawn cell's total width (um),
    for the caller's own floorplanning.
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
        b.box(L_CONT, xc - 0.15, y0 - EMITTER_LE_UM / 2 - 0.2, xc + 0.15, y0 - EMITTER_LE_UM / 2 - 0.05)
        b.box(L_CONT, xc - 0.15, y0 + EMITTER_LE_UM / 2 + 0.05, xc + 0.15, y0 + EMITTER_LE_UM / 2 + 0.2)

    # Collector rail (top), base rail (bottom), emitter rail (Metal2, over
    # the emitter windows) -- one each, spanning the full stripe row, per
    # the pcell's own single collector-metal / base-metal / Metal2 rects.
    b.box(L_METAL1, x_lo, y_hi - 0.9, x_hi, y_hi - 0.5)
    b.label(L_METAL1_LABEL, f"{collector_net}", x0, y_hi - 0.7)
    b.box(L_METAL1, x_lo, y_lo + 0.5, x_hi, y_lo + 0.9)
    b.label(L_METAL1_LABEL, f"{base_net}", x0, y_lo + 0.7)
    b.box(L_METAL2, x_lo + 0.3, y0 - EMITTER_LE_UM / 2 - 0.3, x_hi - 0.3, y0 + EMITTER_LE_UM / 2 + 0.3)
    b.label(L_METAL2_LABEL, f"{emitter_net}", x0, y0)

    b.label(L_TEXT, f"{name}(npn13G2,Nx={nx})", x0, y_hi + 0.6)
    return x_hi - x_lo


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
) -> float:
    """Draw a simplified ``sg13_hv_{n,p}mos`` footprint (Activ+GatPoly+Cont).

    A generic single-finger MOS footprint (not read from a PDK PyCell source
    -- ``pmosHV_code.py``/``nmosHV_code.py`` exist in
    ``sg13g2_pycell_lib/ihp/`` but were not parsed for this issue's scope;
    the ``npn13G2``/``pnpMPA`` PyCells were, since those two devices are
    what this issue's tooling-friction checks are actually about). Sized to
    the real ``w``/``l`` the schematic instances (``M1``/``M2``/``M3``:
    ``w=10u l=1u``; startup's ``MSENSE``/``MKFB``: ``w=2u l=0.5u``), with an
    ``NWell`` enclosure drawn for ``flavor='pmos'`` (SG13G2 PMOS is an
    n-well device, same as every PDK in the fleet). Returns drawn width (um).
    """
    ext = 0.4
    x_lo = x0 - w_um / 2
    x_hi = x0 + w_um / 2
    y_lo = y0 - (l_um / 2 + ext)
    y_hi = y0 + (l_um / 2 + ext)

    b.box(L_ACTIV, x_lo, y_lo, x_hi, y_hi)
    b.box(L_GATPOLY, x_lo - 0.1, y0 - l_um / 2, x_hi + 0.1, y0 + l_um / 2)
    b.label(L_GATPOLY_LABEL, gate_net, x0, y0)

    if flavor == "pmos":
        b.box(L_NWELL, x_lo - 0.4, y_lo - 0.4, x_hi + 0.4, y_hi + 0.4)
    else:
        b.box(L_NSD, x_lo - 0.1, y_lo - 0.1, x_hi + 0.1, y_hi + 0.1)

    # Source/drain contact + Metal1 pad, one strip each side of the gate.
    b.box(L_CONT, x_lo + 0.15, y_hi - 0.25, x_hi - 0.15, y_hi - 0.1)
    b.box(L_METAL1, x_lo, y_hi - 0.35, x_hi, y_hi)
    b.label(L_METAL1_LABEL, source_net, x0, y_hi - 0.15)

    b.box(L_CONT, x_lo + 0.15, y_lo + 0.1, x_hi - 0.15, y_lo + 0.25)
    b.box(L_METAL1, x_lo, y_lo, x_hi, y_lo + 0.35)
    b.label(L_METAL1_LABEL, drain_net, x0, y_lo + 0.15)

    b.label(L_TEXT, f"{name}({flavor} w={w_um}u l={l_um}u)", x0, y_hi + 0.6)
    return x_hi - x_lo


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
) -> float:
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
    Returns drawn length (um).
    """
    x_hi = x0 + l_um
    b.box(L_POLYRES, x0, y0 - w_um / 2, x_hi, y0 + w_um / 2)
    b.label(L_POLYRES_LABEL, f"{name}", (x0 + x_hi) / 2, y0)

    b.box(L_CONT, x0, y0 - w_um / 2, x0 + min(0.3, l_um / 4), y0 + w_um / 2)
    b.box(L_METAL1, x0 - 0.2, y0 - w_um / 2 - 0.1, x0 + min(0.3, l_um / 4), y0 + w_um / 2 + 0.1)
    b.label(L_METAL1_LABEL, end_a_net, x0, y0 + w_um / 2 + 0.4)

    b.box(L_CONT, x_hi - min(0.3, l_um / 4), y0 - w_um / 2, x_hi, y0 + w_um / 2)
    b.box(L_METAL1, x_hi - min(0.3, l_um / 4), y0 - w_um / 2 - 0.1, x_hi + 0.2, y0 + w_um / 2 + 0.1)
    b.label(L_METAL1_LABEL, end_b_net, x_hi, y0 + w_um / 2 + 0.4)

    b.label(L_TEXT, f"{name}({flavor} w={w_um}u l={l_um}u)", (x0 + x_hi) / 2, y0 - w_um / 2 - 0.8)
    return l_um
