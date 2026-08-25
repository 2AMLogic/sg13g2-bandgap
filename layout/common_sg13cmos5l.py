"""Shared ``klayout.db`` drawing primitives for the **SG13CMOS5L** port's
``layout/sg13cmos5l-*/generate.py`` (issue #66, phase 3/4).

A deliberate **fork** of ``layout/common.py`` (this repo's SG13G2 primitives),
not an extension of it, for three reasons that make a single shared module
actively misleading rather than merely awkward:

1. **A different layer table.** The GDS numbers happen to coincide for the
   layers both PDKs share, but CMOS5L's table is genuinely smaller --
   ``Metal5``/``TopMetal2``/``TopVia2``/``Via4`` do not exist, and the
   HBT-specific layers ``common.py`` uses (``EmWind`` 33/0 for
   ``draw_npn13g2``) are *forbidden* in CMOS5L
   (``libs.tech/klayout/tech/lvs/rule_decks/cmos5l_forbidden_check.lvs``
   aborts LVS on them). Sharing a module would leave a forbidden-layer
   constant one careless import away.
2. **A different net-label layer.** ``klt``'s curated ``sg13cmos5l`` deck
   reads net names from ``Metal1.pin`` **(8, 2)**
   (``EXTRACTION_DECK.metal_labels=((8, 2),)``) and well names from
   ``NWell.pin`` **(31, 2)** (``well_label=(31, 2)``) -- *not* the
   ``Metal1.text``/``Metal2.text`` ``(8, 25)``/``(10, 25)`` pair the
   ``sg13g2`` deck reads and ``common.py`` therefore draws. A layout that
   labels the wrong layer extracts every net as an anonymous ``$N``, which
   is exactly the trap issue #20 already fell into once on the SG13G2 side.
3. **A different device set.** CMOS5L has no SiGe HBT at all (only
   ``pnpMPA``, per DR-0004 and ``design/sg13cmos5l/bandgap_core.sch``), so
   ``draw_npn13g2`` has no CMOS5L counterpart; the substrate-PNP footprint
   :func:`draw_pnpmpa` draws instead is a completely different stack
   (emitter p+ ``Activ`` in ``NWell``, n+ base ring inside the same well,
   p+ substrate collector ring outside it).

Every ``(layer, datatype)`` pair below is read directly from the resolved
**CMOS5L** technology's own layer-properties file
(``ihp-sg13cmos5l/libs.tech/klayout/tech/sg13cmos5l.lyp``, IHP release
v0.2.0 as installed at ``~/share/pdk/ihp-sg13cmos5l``), not copied from
``layout/common.py`` and not assumed identical to SG13G2's -- see
``layout/README.md`` "SG13CMOS5L layer numbers" for the read-off table.

Device dimensions are likewise read from CMOS5L's **own** PyCell sources
(``libs.tech/klayout/python/sg13cmos5l_pycell_lib/ihp/{pmosHV,pnpMPA,rppd}_code.py``)
and its own ``sg13cmos5l_tech.json`` ``techParams`` table, cited per
constant below. As with ``layout/common.py``, what these functions draw is
a *simplified representative* footprint -- correct layer stack, correct
device-defining dimensions, contacts and terminal pads -- not a
re-implementation of each PCell's full geometry (guard-ring corner
stitching, thermal pseudo-layers, per-contact arrays sized by the PCell's
own packing loop). See ``layout/README.md`` "What this layout is / is not".
"""

from __future__ import annotations

import klayout.db as kdb

# --------------------------------------------------------------------------- #
# SG13CMOS5L GDS layer numbers, read from
# ihp-sg13cmos5l/libs.tech/klayout/tech/sg13cmos5l.lyp's own <name>/<source>
# entries (IHP release v0.2.0, ~/share/pdk/ihp-sg13cmos5l).
# --------------------------------------------------------------------------- #
L_ACTIV = (1, 0)
L_GATPOLY = (5, 0)
L_CONT = (6, 0)
L_NSD = (7, 0)
L_METAL1 = (8, 0)
# `klt`'s curated sg13cmos5l deck's own net-name layer:
# `klayout_tools.decks.sg13cmos5l.EXTRACTION_DECK.metal_labels == ((8, 2),)`
# ("Metal1.pin" in the .lyp table) -- deliberately different from the
# sg13g2 deck's (8, 25) "Metal1.text". Drawn here as *text only*, never as
# a box: CMOS5L's own PCells also place pin *rectangles* on this layer, a
# convention this simplified layout does not follow (it would add shapes
# `klt extract` reads as labels' host geometry for no benefit here).
L_METAL1_PIN = (8, 2)
L_PSD = (14, 0)
L_SALBLOCK = (28, 0)
L_NWELL = (31, 0)
# `EXTRACTION_DECK.well_label == (31, 2)` ("NWell.pin"), the deck's own
# well-net-naming layer -- the sg13g2 deck declares `well_label=None` and
# has no counterpart at all.
L_NWELL_PIN = (31, 2)
L_THICKGATEOX = (44, 0)
L_TEXT = (63, 0)
L_EXTBLOCK = (111, 0)
L_POLYRES = (128, 0)

LAYER_NAMES: dict[tuple[int, int], str] = {
    L_ACTIV: "Activ.drawing",
    L_GATPOLY: "GatPoly.drawing",
    L_CONT: "Cont.drawing",
    L_NSD: "nSD.drawing",
    L_METAL1: "Metal1.drawing",
    L_METAL1_PIN: "Metal1.pin",
    L_PSD: "pSD.drawing",
    L_SALBLOCK: "SalBlock.drawing",
    L_NWELL: "NWell.drawing",
    L_NWELL_PIN: "NWell.pin",
    L_THICKGATEOX: "ThickGateOx.drawing",
    L_TEXT: "TEXT.drawing",
    L_EXTBLOCK: "EXTBlock.drawing",
    L_POLYRES: "PolyRes.drawing",
}

# --------------------------------------------------------------------------- #
# CMOS5L process constants, read from
# libs.tech/klayout/python/sg13cmos5l_pycell_lib/sg13cmos5l_tech.json's own
# `techParams` table (the same table each PCell above reads at generate
# time), not from SG13G2's and not guessed.
# --------------------------------------------------------------------------- #
CNT_A = 0.16  # Cnt_a  -- contact size
CNT_B = 0.18  # Cnt_b  -- contact-to-contact space
CNT_C = 0.07  # Cnt_c  -- Activ enclosure of Cont
M1_C1 = 0.05  # M1_c1  -- Metal1 endcap over contact row
PSD_C = 0.18  # pSD_c  -- pSD enclosure of p+ Activ in NWell
PSD_I1 = 0.40  # pSD_i1 -- pSD enclosure of a PFET gate
NW_C1 = 0.62  # NW_c1  -- NWell enclosure of p+ Activ
GAT_C = 0.18  # Gat_c  -- GatPoly overlap of Activ (gate endcap)
TGO_A = 0.27  # TGO_a  -- ThickGateOx overlay over Activ
TGO_C = 0.34  # TGO_c  -- ThickGateOx overlay over GatPoly

#: Contact pitch used by :func:`cont_array` -- ``Cnt_a + Cnt_b``, the same
#: pitch CMOS5L's own ``contactArray()`` helper packs a contact row on.
CONT_PITCH = CNT_A + CNT_B


class Builder:
    """``kdb.Layout``/cell/layer setup plus small box/label/text primitives.

    Micron-in, database-unit-out (``dbu = 0.001``, i.e. 1 nm -- matching
    ``sg13cmos5l.lyt``'s own ``<dbu>0.001</dbu>`` and `klt`'s
    ``decks.get_nominal_dbu("sg13cmos5l") == 0.001``), same convention as
    ``layout/common.py``'s own ``Builder``.
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

    def ring(
        self,
        layer: tuple[int, int],
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        width: float,
        open_top: bool = False,
    ) -> None:
        """Draw a rectangular ring whose *outer* edge is ``(x0, y0, x1, y1)``
        and whose walls are ``width`` microns thick, as four (or, with
        ``open_top``, three) separate boxes.

        ``open_top=True`` omits the top wall, leaving a gap an inner
        terminal's escape route can pass through without shorting to the
        ring -- what :func:`draw_pnpmpa` needs for the emitter Metal1 pad
        trapped inside the base/collector rings (CMOS5L's own ``pnpMPA``
        PCell closes both rings, because a PCell has no route to get out
        through; this layout has to).
        """
        self.box(layer, x0, y0, x0 + width, y1)  # left wall
        self.box(layer, x1 - width, y0, x1, y1)  # right wall
        self.box(layer, x0, y0, x1, y0 + width)  # bottom wall
        if not open_top:
            self.box(layer, x0, y1 - width, x1, y1)

    def net_label(self, text: str, x: float, y: float) -> None:
        """Place a net name on ``Metal1.pin`` (8, 2) -- the layer the curated
        ``sg13cmos5l`` deck's ``EXTRACTION_DECK.metal_labels`` actually reads
        for net naming. Must land on a real ``Metal1.drawing`` shape (the
        deck's ``connect(metals[0], metal_labels[0])``) to name anything."""
        idx = self._layers[L_METAL1_PIN]
        self.cell.shapes(idx).insert(kdb.Text(text, self._u(x), self._u(y)))

    def well_label(self, text: str, x: float, y: float) -> None:
        """Place a well-net name on ``NWell.pin`` (31, 2) -- the deck's own
        ``EXTRACTION_DECK.well_label`` layer, which names the n-well net a
        PMOS body terminal resolves to."""
        idx = self._layers[L_NWELL_PIN]
        self.cell.shapes(idx).insert(kdb.Text(text, self._u(x), self._u(y)))

    def annotate(self, text: str, x: float, y: float) -> None:
        """Human-readable annotation on ``TEXT.drawing`` (63, 0) -- read by
        nothing in the DRC/LVS flow, drawn so the GDS is legible in a
        viewer (the same role ``layout/common.py``'s ``L_TEXT`` labels
        play)."""
        idx = self._layers[L_TEXT]
        self.cell.shapes(idx).insert(kdb.Text(text, self._u(x), self._u(y)))

    def write(self, path: str) -> None:
        opts = kdb.SaveLayoutOptions()
        opts.gds2_write_timestamps = False
        self.layout.write(path, opts)


def cont_array(b: Builder, x0: float, y0: float, x1: float, y1: float) -> None:
    """Fill ``(x0, y0)-(x1, y1)`` with ``Cnt_a``-sized contacts on a
    ``Cnt_a + Cnt_b`` pitch, centred in the box -- a simplified stand-in for
    CMOS5L's own ``contactArray()`` helper (``ihp/geometry.py``), which packs
    the same size/pitch but additionally switches to the wider ``Cnt_b1``
    spacing once the landing area is large enough. Draws nothing if the box
    cannot hold a single contact.
    """
    span_x, span_y = x1 - x0, y1 - y0
    nx = int((span_x + CNT_B + 1e-9) // CONT_PITCH)
    ny = int((span_y + CNT_B + 1e-9) // CONT_PITCH)
    if nx < 1 or ny < 1:
        return
    used_x = nx * CONT_PITCH - CNT_B
    used_y = ny * CONT_PITCH - CNT_B
    ox = x0 + (span_x - used_x) / 2
    oy = y0 + (span_y - used_y) / 2
    for i in range(nx):
        for j in range(ny):
            cx = ox + i * CONT_PITCH
            cy = oy + j * CONT_PITCH
            b.box(L_CONT, cx, cy, cx + CNT_A, cy + CNT_A)


def draw_hv_pmos(
    b: Builder,
    name: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    gate_net: str,
    source_net: str,
    drain_net: str,
    draw_nwell: bool = True,
) -> dict:
    """Draw a simplified single-finger ``sg13_hv_pmos`` footprint.

    Layer stack taken from CMOS5L's own ``pmosHV_code.py`` ``genLayout()``:
    ``Activ`` (1/0) channel+source/drain, ``GatPoly`` (5/0) gate with a
    ``Gat_c`` (0.18 um) endcap past the diffusion, ``pSD`` (14/0) p+ implant
    enclosing the diffusion by ``pSD_c`` (0.18 um) and the gate by
    ``pSD_i1`` (0.40 um), ``NWell`` (31/0) enclosing the diffusion by
    ``NW_c1`` (0.62 um), and ``ThickGateOx`` (44/0) -- the layer that makes
    this the **HV** (thick-gate-oxide) flavour the schematic instantiates
    rather than the LV one -- sized per the PCell's own rule (the larger of
    its ``TGO_a``/``TGO_c`` overlays and the NWell extent).

    ``ThickGateOx`` is drawn deliberately, knowing `klt`'s curated
    ``sg13cmos5l`` deck does **not** model it: that deck's
    ``EXTRACTION_DECK.mos_flavours`` is empty (LV-only starter), so it binds
    this transistor to the plain ``pfet`` class regardless. Drawing the
    marker makes `klt` itself report the gap -- ``klt extract``/``klt drc``
    emit a ``voltage_domain_warnings`` entry for any MOS geometry
    overlapping a registered-but-unmodelled marker (44/0 is registered in
    ``decks.get_unmodeled_voltage_markers("sg13cmos5l")``) -- rather than
    hiding an HV device behind LV-looking geometry that reads clean. See
    ``layout/README.md`` "HV flavour: drawn, not modelled".

    ``draw_nwell=False`` suppresses the per-device well so a caller can draw
    one shared ``NWell`` across a matched mirror row instead (what
    ``sg13cmos5l-bandgap_core`` does for ``M1``/``M2``/``M3``): three
    separate wells would extract as three separate, unrelated body nets for
    a schematic that ties all three bodies to the same ``vdd``.

    Returns this device's terminal geometry for the caller's routing pass:
    ``source_pad``/``drain_pad`` (``(x0, y0, x1, y1)`` Metal1 boxes),
    ``gate_box`` (the drawn ``GatPoly`` rectangle), ``gate_y_lo``/
    ``gate_y_hi`` (the channel-length band a poly route may widen within),
    ``nwell`` (the well box, or the box a shared well must cover when
    ``draw_nwell=False``), and ``width``.
    """
    ext = 0.4  # source/drain diffusion extension past the gate edge
    x_lo, x_hi = x0 - w_um / 2, x0 + w_um / 2
    y_lo, y_hi = y0 - (l_um / 2 + ext), y0 + (l_um / 2 + ext)

    b.box(L_ACTIV, x_lo, y_lo, x_hi, y_hi)

    gate_box = (x_lo - GAT_C, y0 - l_um / 2, x_hi + GAT_C, y0 + l_um / 2)
    b.box(L_GATPOLY, *gate_box)

    # p+ implant: enclose the diffusion by pSD_c, the gate by pSD_i1.
    b.box(
        L_PSD,
        min(x_lo - PSD_C, gate_box[0] - PSD_I1),
        y_lo - PSD_C,
        max(x_hi + PSD_C, gate_box[2] + PSD_I1),
        y_hi + PSD_C,
    )

    nwell = (x_lo - NW_C1, y_lo - NW_C1, x_hi + NW_C1, y_hi + NW_C1)
    if draw_nwell:
        b.box(L_NWELL, *nwell)

    # ThickGateOx: max(TGO overlay, NWell extent), per pmosHV_code.py's own
    # "now check, if NWell is drawn bigger" branch.
    b.box(
        L_THICKGATEOX,
        min(x_lo - TGO_A, nwell[0]),
        min(y_lo - TGO_C, nwell[1]),
        max(x_hi + TGO_A, nwell[2]),
        max(y_hi + TGO_C, nwell[3]),
    )

    # Source (top) and drain (bottom) contact rows + Metal1 pads.
    source_pad = (x_lo, y_hi - (CNT_A + 2 * M1_C1), x_hi, y_hi)
    b.box(L_METAL1, *source_pad)
    cont_array(b, x_lo + CNT_C, y_hi - CNT_C - CNT_A, x_hi - CNT_C, y_hi - CNT_C)
    b.net_label(source_net, x0, (source_pad[1] + source_pad[3]) / 2)

    drain_pad = (x_lo, y_lo, x_hi, y_lo + (CNT_A + 2 * M1_C1))
    b.box(L_METAL1, *drain_pad)
    cont_array(b, x_lo + CNT_C, y_lo + CNT_C, x_hi - CNT_C, y_lo + CNT_C + CNT_A)
    b.net_label(drain_net, x0, (drain_pad[1] + drain_pad[3]) / 2)

    b.annotate(f"{name}(sg13_hv_pmos w={w_um}u l={l_um}u g={gate_net})", x0, y_hi + 0.8)
    return {
        "width": x_hi - x_lo,
        "source_pad": source_pad,
        "drain_pad": drain_pad,
        "gate_box": gate_box,
        "gate_y_lo": y0 - l_um / 2,
        "gate_y_hi": y0 + l_um / 2,
        "nwell": nwell,
    }


def pnpmpa_extent(w_um: float, l_um: float) -> dict[str, float]:
    """Half-extents of every ring in a ``pnpMPA`` footprint, computed with
    CMOS5L's **own** ``pnpMPA_code.py`` ``genLayout()`` formulae (variable
    names kept verbatim from that source so the two can be diffed):

    ``hact = l/2``/``wact = w/2`` (the emitter window -- note this makes the
    drawn emitter area exactly ``w * l``, matching the ``a={w*l}`` the
    schematic's own netlist passes), then ``wpsd = wact + 0.21``,
    ``w2act = wpsd + pSD_c``, ``dw2act = max(wact, 0.3)``, ``dh2act = 0.29``,
    ``wbulay = w2act + dw2act + 0.05``, ``wnwell = wbulay + 0.26``,
    ``w2psd = wnwell + 0.5``, ``d2psd = 0.75``, ``w3act = w2psd + 0.2``,
    ``d3act = 0.35`` (and the ``h*`` counterparts).

    ``wbulay``/``hbulay`` are retained as *dimension* intermediates only --
    CMOS5L's own PCell computes them and, unlike SG13G2's, draws **no**
    ``nBuLay`` shape, consistent with ``nBuLay`` (32/0) being on CMOS5L's
    LVS forbidden-layer list. Nothing in this module ever draws that layer.
    """
    wact, hact = w_um / 2, l_um / 2
    wpsd, hpsd = wact + 0.21, hact + 0.18
    w2act, h2act = wpsd + PSD_C, hpsd + PSD_C
    dw2act, dh2act = max(wact, 0.3), 0.29
    wbulay, hbulay = w2act + dw2act + 0.05, h2act + dh2act + 0.05
    wnwell, hnwell = wbulay + 0.26, hbulay + 0.26
    w2psd, h2psd = wnwell + 0.5, hnwell + 0.5
    w3act, h3act = w2psd + 0.2, h2psd + 0.2
    return {
        "wact": wact, "hact": hact,
        "wpsd": wpsd, "hpsd": hpsd,
        "w2act": w2act, "h2act": h2act, "dw2act": dw2act, "dh2act": dh2act,
        "wnwell": wnwell, "hnwell": hnwell,
        "w2psd": w2psd, "h2psd": h2psd, "d2psd": 0.75,
        "w3act": w3act, "h3act": h3act, "d3act": 0.35,
    }


def draw_pnpmpa(
    b: Builder,
    name: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    emitter_net: str,
    base_net: str,
    collector_net: str,
) -> dict:
    """Draw a simplified ``pnpMPA`` (substrate PNP) footprint.

    CMOS5L's only bipolar device -- there is no SiGe HBT in this PDK at all
    (see this module's docstring and DR-0004), so this has no
    ``layout/common.py`` counterpart to port; the stack is read from
    CMOS5L's own ``pnpMPA_code.py``:

    * **emitter** -- a ``w x l`` p+ ``Activ`` window (``pSD``-covered)
      inside the n-well, contacted to a Metal1 pad;
    * **base** -- an n+ ``Activ`` ring inside the *same* n-well (no ``pSD``
      over it), contacted to a Metal1 ring: the well itself is the base;
    * **collector** -- a p+ ``Activ`` ring **outside** the n-well
      (``pSD``-covered), i.e. a substrate tie: the p-substrate is the
      collector. This is why the schematic wires collector and base
      together to ``vss``.

    Both Metal1 rings are drawn ``open_top`` (see :meth:`Builder.ring`) so
    the emitter pad has an escape route; the ``Activ``/``pSD`` rings under
    them stay closed, as the PCell draws them.

    **What this footprint is not**: `klt`'s curated ``sg13cmos5l`` deck
    recognises no bipolar device class at all
    (``EXTRACTION_DECK.bipolars == ()``), so this geometry extracts as three
    unrelated diffusion nets rather than one ``pnpMPA`` device -- a
    documented deck-coverage gap, not a layout defect. See
    ``layout/README.md`` "LVS -- ``mismatch``, fully attributed".

    Returns ``emitter_pad``/``base_ring``/``collector_ring`` boxes plus the
    device's overall ``bbox`` for the caller's routing pass.
    """
    d = pnpmpa_extent(w_um, l_um)

    # -- emitter: p+ Activ window + pSD + contacts + Metal1 pad ------------
    b.box(L_ACTIV, x0 - d["wact"], y0 - d["hact"], x0 + d["wact"], y0 + d["hact"])
    b.box(L_PSD, x0 - d["wpsd"], y0 - d["hpsd"], x0 + d["wpsd"], y0 + d["hpsd"])
    cont_array(
        b,
        x0 - d["wact"] + CNT_C, y0 - d["hact"] + CNT_C,
        x0 + d["wact"] - CNT_C, y0 + d["hact"] - CNT_C,
    )
    emitter_pad = (
        x0 - d["wact"] + 0.02, y0 - d["hact"] + 0.02,
        x0 + d["wact"] - 0.02, y0 + d["hact"] - 0.02,
    )
    b.box(L_METAL1, *emitter_pad)
    b.net_label(emitter_net, x0, y0)

    # -- base: n+ Activ ring in the same NWell + Metal1 ring ---------------
    br_x0, br_y0 = x0 - d["w2act"] - d["dw2act"], y0 - d["h2act"] - d["dh2act"]
    br_x1, br_y1 = x0 + d["w2act"] + d["dw2act"], y0 + d["h2act"] + d["dh2act"]
    b.ring(L_ACTIV, br_x0, br_y0, br_x1, br_y1, min(d["dw2act"], d["dh2act"]))
    base_ring_m1 = (br_x0 + 0.02, br_y0 + 0.02, br_x1 - 0.02, br_y1 - 0.02)
    b.ring(
        L_METAL1, *base_ring_m1,
        width=min(d["dw2act"], d["dh2act"]) - 0.04, open_top=True,
    )
    wall = min(d["dw2act"], d["dh2act"])
    cont_array(b, br_x0 + CNT_C, br_y0 + CNT_C, br_x0 + wall - CNT_C, br_y1 - CNT_C)
    cont_array(b, br_x1 - wall + CNT_C, br_y0 + CNT_C, br_x1 - CNT_C, br_y1 - CNT_C)
    cont_array(b, br_x0 + CNT_C, br_y0 + CNT_C, br_x1 - CNT_C, br_y0 + wall - CNT_C)
    base_ring = (br_x0, br_y0, br_x1, br_y1)
    b.net_label(base_net, br_x0 + wall / 2, y0)

    # -- the well itself: the PNP's base region ----------------------------
    # Left deliberately unlabelled (no ``NWell.pin`` text): the well *is*
    # the PNP's base, but the curated deck declares no tap layer
    # (``tap``/``tap_nplus``/``tap_pplus`` all ``None``), so a well net can
    # never be connected to the n+ base ring drawn inside it. A label here
    # would assert an electrical identity the extraction cannot honour --
    # verified concretely: with the label, `klt extract` reports the same
    # net count and simply drops the isolated well region, and `klt lvs`'s
    # finding count is unchanged. See ``layout/README.md`` "SG13CMOS5L: LVS
    # -- ``mismatch``, fully attributed", cause 4.
    b.box(L_NWELL, x0 - d["wnwell"], y0 - d["hnwell"], x0 + d["wnwell"], y0 + d["hnwell"])

    # -- collector: p+ substrate ring outside the well ---------------------
    cr_x0, cr_y0 = x0 - d["w3act"] - d["d3act"], y0 - d["h3act"] - d["d3act"]
    cr_x1, cr_y1 = x0 + d["w3act"] + d["d3act"], y0 + d["h3act"] + d["d3act"]
    b.ring(
        L_PSD,
        x0 - d["w2psd"] - d["d2psd"], y0 - d["h2psd"] - d["d2psd"],
        x0 + d["w2psd"] + d["d2psd"], y0 + d["h2psd"] + d["d2psd"], d["d2psd"],
    )
    b.ring(L_ACTIV, cr_x0, cr_y0, cr_x1, cr_y1, d["d3act"])
    collector_ring_m1 = (cr_x0 + 0.02, cr_y0 + 0.02, cr_x1 - 0.02, cr_y1 - 0.02)
    b.ring(L_METAL1, *collector_ring_m1, width=d["d3act"] - 0.04, open_top=True)
    cont_array(b, cr_x0 + CNT_C, cr_y0 + CNT_C, cr_x0 + d["d3act"] - CNT_C, cr_y1 - CNT_C)
    cont_array(b, cr_x1 - d["d3act"] + CNT_C, cr_y0 + CNT_C, cr_x1 - CNT_C, cr_y1 - CNT_C)
    cont_array(b, cr_x0 + CNT_C, cr_y0 + CNT_C, cr_x1 - CNT_C, cr_y0 + d["d3act"] - CNT_C)
    collector_ring = (cr_x0, cr_y0, cr_x1, cr_y1)
    b.net_label(collector_net, cr_x0 + d["d3act"] / 2, y0)

    b.annotate(f"{name}(pnpMPA w={w_um}u l={l_um}u)", x0, cr_y1 + 0.8)
    return {
        "emitter_pad": emitter_pad,
        # ``*_ring`` are the Activ ring outlines; ``*_ring_m1`` are the
        # Metal1 rings drawn 0.02 um inside them (the PCell's own
        # Metal1-inside-Activ inset). A routing pass must strap against the
        # **_m1** boxes: a stub that stops at the Activ outline leaves a
        # 0.02 um Metal1 gap, which `klt drc` correctly flags as a
        # ``metal1.space.1`` notch rather than a connection (found exactly
        # that way on this cell's first DRC run).
        "base_ring": base_ring,
        "base_ring_m1": base_ring_m1,
        "collector_ring": collector_ring,
        "collector_ring_m1": collector_ring_m1,
        "bbox": collector_ring,
    }


# rppd geometry constants -- same "dog-bone" construction ``layout/common.py``
# ``draw_poly_res`` uses on the SG13G2 side (a marked core exactly ``w`` tall,
# wider un-marked heads for the terminal contacts), kept identical here so the
# two ports' resistor footprints stay comparable. The construction's *reason*
# differs: on SG13G2 the split into two disjoint head polygons is what
# `klt`'s resistor extractor requires to recognise the device at all; the
# curated ``sg13cmos5l`` deck recognises no resistor
# (``EXTRACTION_DECK.resistors == ()``), so here the shape is drawn for
# physical fidelity to ``rppd_code.py``'s own head/body split, not to satisfy
# an extractor.
RES_HEAD_UM = 0.4
RES_GATPOLY_Y_MARGIN_UM = 0.1
RES_CONT_MARGIN_UM = 0.1


def draw_rppd(
    b: Builder,
    name: str,
    w_um: float,
    l_um: float,
    x0: float,
    y0: float,
    end_a_net: str,
    end_b_net: str,
) -> dict:
    """Draw a straight (unfolded) ``rppd`` poly resistor body.

    Layer stack read from CMOS5L's own ``rppd_code.py``: ``GatPoly`` (5/0)
    is the physical conductor (its ``contpolylayer``), ``PolyRes`` (128/0)
    marks the resistive body (``bodypolylayer``), and ``pSD`` (14/0),
    ``SalBlock`` (28/0) and ``EXTBlock`` (111/0) are the implant/silicide-
    block/extraction markers over that body -- the same five layers, at the
    same GDS numbers, SG13G2's ``rppd`` uses.

    Drawn as one straight bar at the schematic's own ``w``/``l``, **not**
    meandered: for ``R1`` (``l=647.0u``) that is a ~0.65 mm bar dominating
    the cell's bounding box. That is an honest rendering of the netlist's
    own sizing, not a claim about how a real compact layout would fold it --
    identical to the choice ``layout/common.py``'s ``draw_poly_res`` already
    documents for SG13G2. See ``layout/README.md`` "What this layout is /
    is not".

    Returns ``end_a_pad``/``end_b_pad`` (Metal1 boxes) and ``length``.
    """
    x_hi = x0 + l_um

    # GatPoly conductor: narrow core (exactly w tall, coincident with the
    # markers below) plus a wider head at each end for the contacts.
    b.box(
        L_GATPOLY,
        x0 - RES_HEAD_UM, y0 - w_um / 2 - RES_GATPOLY_Y_MARGIN_UM,
        x0, y0 + w_um / 2 + RES_GATPOLY_Y_MARGIN_UM,
    )
    b.box(L_GATPOLY, x0, y0 - w_um / 2, x_hi, y0 + w_um / 2)
    b.box(
        L_GATPOLY,
        x_hi, y0 - w_um / 2 - RES_GATPOLY_Y_MARGIN_UM,
        x_hi + RES_HEAD_UM, y0 + w_um / 2 + RES_GATPOLY_Y_MARGIN_UM,
    )

    for layer in (L_POLYRES, L_EXTBLOCK, L_PSD, L_SALBLOCK):
        b.box(layer, x0, y0 - w_um / 2, x_hi, y0 + w_um / 2)

    # End A / end B: contacts on the un-marked heads + Metal1 pads.
    cont_a_x0 = x0 - RES_HEAD_UM + RES_CONT_MARGIN_UM
    cont_array(b, cont_a_x0, y0 - w_um / 2 + CNT_C, cont_a_x0 + CNT_A, y0 + w_um / 2 - CNT_C)
    end_a_pad = (x0 - RES_HEAD_UM - 0.1, y0 - w_um / 2 - 0.1, x0, y0 + w_um / 2 + 0.1)
    b.box(L_METAL1, *end_a_pad)
    b.net_label(end_a_net, (end_a_pad[0] + end_a_pad[2]) / 2, y0)

    cont_b_x1 = x_hi + RES_HEAD_UM - RES_CONT_MARGIN_UM
    cont_array(b, cont_b_x1 - CNT_A, y0 - w_um / 2 + CNT_C, cont_b_x1, y0 + w_um / 2 - CNT_C)
    end_b_pad = (x_hi, y0 - w_um / 2 - 0.1, x_hi + RES_HEAD_UM + 0.1, y0 + w_um / 2 + 0.1)
    b.box(L_METAL1, *end_b_pad)
    b.net_label(end_b_net, (end_b_pad[0] + end_b_pad[2]) / 2, y0)

    b.annotate(f"{name}(rppd w={w_um}u l={l_um}u)", (x0 + x_hi) / 2, y0 - w_um / 2 - 0.9)
    return {"length": l_um, "end_a_pad": end_a_pad, "end_b_pad": end_b_pad}


# --------------------------------------------------------------------------- #
# Routing primitives. **Metal1 and GatPoly only** -- the curated sg13cmos5l
# deck's extraction stack is `metals=((8, 0),)` with `vias=()`, i.e. it
# models exactly one routing metal and no via at all, so a Metal2 shape
# would be invisible to `klt extract` and any net routed through it would
# come back broken. (`layout/common.py`'s SG13G2 counterpart routes freely
# on Metal2/Via1 because that deck's stack declares them.) The consequence
# for this cell is a strictly planar, single-metal floorplan -- see
# `layout/sg13cmos5l-bandgap_core/generate.py`'s own docstring.
# --------------------------------------------------------------------------- #


def route_h(b: Builder, layer: tuple[int, int], y_center: float, x0: float, x1: float, width: float = 0.3) -> None:
    """Horizontal routing bar on ``layer`` at ``y_center``, spanning
    ``[x0, x1]`` (order-independent), ``width`` microns tall."""
    half = width / 2
    b.box(layer, min(x0, x1), y_center - half, max(x0, x1), y_center + half)


def route_v(b: Builder, layer: tuple[int, int], x_center: float, y0: float, y1: float, width: float = 0.3) -> None:
    """Vertical routing bar on ``layer`` at ``x_center``, spanning
    ``[y0, y1]`` (order-independent), ``width`` microns wide."""
    half = width / 2
    b.box(layer, x_center - half, min(y0, y1), x_center + half, max(y0, y1))
