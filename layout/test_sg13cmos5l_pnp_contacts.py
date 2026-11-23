"""Check the raw PNP ring contacts in the generated SG13CMOS5L streams."""

from itertools import combinations
from math import hypot
from pathlib import Path
import unittest

import klayout.db as kdb

from common_sg13cmos5l import (
    CNT_A, CNT_B, CNT_C, M1_C1, L_ACTIV, L_CONT, L_METAL1, L_NSD, L_NWELL, L_PSD,
)


class PnpRingContactsTest(unittest.TestCase):
    def check_ring(self, polygon, cuts, metal, dbu, expected_count):
        ring = kdb.Region(polygon)
        contacts = list(cuts.overlapping(ring).each())
        size = round(CNT_A / dbu)
        boxes = []
        for cut in contacts:
            box = cut.bbox()
            self.assertTrue(cut.is_box(), box)
            self.assertEqual((box.width(), box.height()), (size, size), box)
            for landing, margin in ((ring, CNT_C), (metal, M1_C1)):
                uncovered = kdb.Region(box.enlarged(round(margin / dbu))) - landing
                self.assertTrue(uncovered.is_empty(), box)
            boxes.append(box)
        for a, b in combinations(boxes, 2):
            dx = max(a.left - b.right, b.left - a.right, 0)
            dy = max(a.bottom - b.top, b.bottom - a.top, 0)
            self.assertGreaterEqual(hypot(dx, dy), round(CNT_B / dbu), (a, b))
        self.assertEqual(len(boxes), expected_count)

    def test_drawn_contacts(self):
        for cell in ("core", "top"):
            name = f"sg13cmos5l-bandgap_{cell}"
            layout = kdb.Layout()
            layout.read(str(Path(__file__).parent / name / f"{name}.gds"))

            def region(layer):
                return kdb.Region(layout.top_cell().begin_shapes_rec(layout.layer(*layer)))

            active, well = region(L_ACTIV), region(L_NWELL)
            metal, cuts = region(L_METAL1), region(L_CONT)
            # A Boolean merge would turn overlapping corner cuts into one polygon.
            cuts.merged_semantics = False
            rings = (
                ("base", active & region(L_NSD) & well, 24),
                ("collector", (active & region(L_PSD)) - well, 48),
            )
            for terminal, diffusion, expected_count in rings:
                # The base and collector surround the emitter. A MOS tap has no hole.
                polygons = [p for p in diffusion.each_merged() if p.holes() == 1]
                self.assertEqual(len(polygons), 10, (cell, terminal))
                for polygon in polygons:
                    with self.subTest(cell=cell, terminal=terminal, ring=polygon.bbox()):
                        self.check_ring(polygon, cuts, metal, layout.dbu, expected_count)


if __name__ == "__main__":
    unittest.main()
