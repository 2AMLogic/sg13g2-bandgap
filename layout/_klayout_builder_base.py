"""Shared ``klayout.db`` drawing primitives common to every PDK-specific
``layout/common*.py`` module -- the byte-identical ``Builder`` methods and
``route_h``/``route_v`` free functions factored out per issue #78. Nothing
PDK-specific lives here; each variant still owns its own ``LAYER_NAMES``
table and subclasses :class:`BuilderBase` to add its own drawing methods.
"""

from __future__ import annotations

import klayout.db as kdb


class BuilderBase:
    """``kdb.Layout``/cell/layer setup plus box/write primitives, in microns
    (converted to ``dbu = 0.001``, i.e. 1 nm, database units by rounding)."""

    def __init__(
        self,
        top_cell: str,
        layer_names: dict[tuple[int, int], str],
        layout: kdb.Layout | None = None,
    ) -> None:
        if layout is None:
            layout = kdb.Layout()
            layout.dbu = 0.001
        self.layout = layout
        self.cell = self.layout.create_cell(top_cell)
        self._layers: dict[tuple[int, int], int] = {}
        for pair, name in layer_names.items():
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

    def write(self, path: str) -> None:
        opts = kdb.SaveLayoutOptions()
        opts.gds2_write_timestamps = False
        self.layout.write(path, opts)


def route_h(b: BuilderBase, layer: tuple[int, int], y_center: float, x0: float, x1: float, width: float = 0.3) -> None:
    """Horizontal routing bar on ``layer`` at ``y_center``, spanning
    ``[x0, x1]`` (order-independent), ``width`` microns tall."""
    half = width / 2
    b.box(layer, min(x0, x1), y_center - half, max(x0, x1), y_center + half)


def route_v(b: BuilderBase, layer: tuple[int, int], x_center: float, y0: float, y1: float, width: float = 0.3) -> None:
    """Vertical routing bar on ``layer`` at ``x_center``, spanning
    ``[y0, y1]`` (order-independent), ``width`` microns wide -- the
    vertical-leg counterpart of :func:`route_h`."""
    half = width / 2
    b.box(layer, x_center - half, min(y0, y1), x_center + half, max(y0, y1))


# --------------------------------------------------------------------------- #
# Serpentine (folded) resistor planning (issue #173) -- PDK-agnostic, so both
# ``layout/common.py`` (SG13G2) and ``layout/common_sg13cmos5l.py`` (CMOS5L)
# fold their poly resistors to exactly the same arithmetic. Only the plan is
# shared; each variant still draws its own layer stack.
# --------------------------------------------------------------------------- #

#: Nanometres per micron. Every quantity :func:`fold_plan` derives is computed
#: in integer nanometres -- the layout's own database unit
#: (``BuilderBase.__init__`` sets ``layout.dbu = 0.001``) -- so a folded
#: resistor's total conductor length is *exactly* the schematic's ``l``, not a
#: float that rounds to it. See :func:`fold_plan`'s docstring.
NM_PER_UM = 1000


def fold_plan(
    w_um: float,
    l_um: float,
    legs: int,
    gap_min_um: float,
) -> dict:
    """Plan a serpentine fold of a ``w_um`` x ``l_um`` resistor into ``legs``
    parallel legs, **conserving the drawn conductor length exactly**.

    Geometry (drawn by each variant's own ``draw_*`` function): ``legs``
    *vertical* bars of width ``w_um``, on a horizontal pitch of
    ``w_um + gap``, joined end-to-end by ``w_um``-thick links that alternate
    top / bottom -- leg 0 links to leg 1 at the top, leg 1 to leg 2 at the
    bottom, and so on. The result is one continuous conductor whose two free
    ends are leg 0's bottom and (for an even ``legs``) leg ``legs-1``'s
    bottom, or (odd ``legs``) its top.

    **Length conservation is exact, by construction, not by measurement.**
    Write ``h`` for a leg's drawn height and ``g`` for the gap. Walking the
    conductor's centreline from one free end to the other traverses
    ``h - w/2`` on the first leg, ``h - w`` on each interior leg,
    ``h - w/2`` on the last, plus ``w + g`` across each of the ``legs-1``
    links -- which sums to::

        L = legs * h + (legs - 1) * g

    independent of ``w``. That is also exactly ``area / w``: the drawn core's
    area is ``legs*h*w + (legs-1)*g*w`` (the links contribute only the ``g``-
    wide span *between* two legs; the corner squares are already counted in
    the legs' own boxes). Both facts matter downstream:

    * ``L == l_um`` keeps the *nominal* resistance identical to the straight
      bar's -- the drawn conductor is neither longer nor shorter, only bent.
    * KLayout's ``DeviceExtractorResistor`` derives the recognised device's
      ``R`` from the marked core's drawn geometry, so an exactly-conserved
      ``area / w`` keeps the *extracted* ``R`` identical too, and with it the
      LVS device-parameter compare against the schematic's own R card.

    Solving ``L = l_um`` for ``h`` needs ``(l - (legs-1)*g)`` to be divisible
    by ``legs`` **in database units**, or the conserved length would only be
    conserved to float precision and the drawn boxes would round. Rather than
    force the caller to hand-tune ``l``, this function keeps ``h`` an exact
    integer number of nanometres and *searches ``g`` upward* from
    ``gap_min_um`` for the first value that divides evenly. Incrementing ``g``
    by 1 nm changes the numerator by ``-(legs-1)`` nm, i.e. by ``+1`` modulo
    ``legs``, so the residue cycles through every value and a solution always
    exists within ``legs`` nanometres of the floor -- at most 0.03 um wider
    than the requested minimum for the leg counts this repo uses. The
    resulting ``g`` is therefore always **at least** the DRC-driven minimum
    the caller asked for, never below it.

    ``legs=1`` is the degenerate, unfolded case: one vertical bar of length
    ``l_um``, no links, ``gap`` unused.

    Returns a dict of ``legs``, ``leg_len_um`` (``h``), ``gap_um`` (``g``),
    ``pitch_um`` (``w + g``), ``width_um`` / ``height_um`` (the marked core's
    own bounding box) and ``centerline_um`` (``L``, which is ``l_um`` exactly
    -- returned so a caller or a test can assert conservation rather than
    trust this docstring).
    """
    if legs < 1:
        raise ValueError(f"legs must be >= 1, got {legs}")
    w_nm = int(round(w_um * NM_PER_UM))
    l_nm = int(round(l_um * NM_PER_UM))
    gap_min_nm = int(round(gap_min_um * NM_PER_UM))
    if w_nm <= 0 or l_nm <= 0:
        raise ValueError(f"w_um/l_um must be positive, got w={w_um} l={l_um}")

    if legs == 1:
        leg_nm, gap_nm = l_nm, gap_min_nm
    else:
        for gap_nm in range(gap_min_nm, gap_min_nm + legs):
            remainder = l_nm - (legs - 1) * gap_nm
            if remainder > 0 and remainder % legs == 0:
                leg_nm = remainder // legs
                break
        else:  # pragma: no cover -- unreachable: see the docstring's residue argument
            raise ValueError(
                f"no gap >= {gap_min_um}um divides l={l_um}um into {legs} whole-nm legs"
            )
        if leg_nm <= w_nm:
            raise ValueError(
                f"{legs} legs of l={l_um}um gives a {leg_nm / NM_PER_UM}um leg, which is "
                f"not longer than the resistor's own w={w_um}um -- use fewer legs"
            )

    pitch_nm = w_nm + gap_nm
    return {
        "legs": legs,
        "leg_len_um": leg_nm / NM_PER_UM,
        "gap_um": gap_nm / NM_PER_UM,
        "pitch_um": pitch_nm / NM_PER_UM,
        "width_um": ((legs - 1) * pitch_nm + w_nm) / NM_PER_UM,
        "height_um": leg_nm / NM_PER_UM,
        "centerline_um": (legs * leg_nm + (legs - 1) * gap_nm) / NM_PER_UM,
    }
