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

    def __init__(self, top_cell: str, layer_names: dict[tuple[int, int], str]) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = 0.001
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
