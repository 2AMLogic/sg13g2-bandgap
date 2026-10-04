#!/usr/bin/env python3
"""Self-test for gen_pex_netlist_body.py (issue #278). Stdlib only."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_pex_netlist_body as g  # noqa: E402


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pex = g.DEFAULT_PEX.read_text()
        cls.design = g.DEFAULT_DESIGN.read_text()
        cls.body = g.generate(cls.pex, cls.design)

    def cards(self, prefix: str) -> list[str]:
        return [
            ln for ln in self.body.splitlines() if ln.startswith(prefix) and not ln.startswith("*")
        ]

    def test_committed_extraction_generates_a_valid_chain(self) -> None:
        self.assertEqual(g.verify(self.body), [])

    def test_device_inventory(self) -> None:
        self.assertEqual(len(self.cards("XRU")), 255)
        self.assertEqual(
            sorted(c.split()[0] for c in self.cards("XM")),
            ["XM1", "XM2A", "XM2B", "XM3A", "XM3B", "XM3C"],
        )
        self.assertEqual(sorted(c.split()[0] for c in self.cards("XR2") + self.cards("XR1")), ["XR1", "XR2"])
        self.assertEqual(len(self.cards("XQ")), 3)
        self.assertFalse(self.cards("XXTRIM"))
        self.assertFalse(re.search(r"^RS\d", self.body, re.M | re.I))

    def test_hub_tags_are_read_off_the_cards(self) -> None:
        # M$4 (XM3A) drain/source hubs, straight from the committed card.
        m4 = next(c for c in self.pex.splitlines() if c.startswith("M$4 "))
        nd, _ng, ns, nb = m4.split()[1:5]
        xm3a = self.cards("XM3A")[0].split()
        self.assertEqual(xm3a[1:5], [nd.lower(), "fb", ns.lower(), nb.lower()])

    def test_tap_net_is_legal_and_renamed(self) -> None:
        cards = "\n".join(ln for ln in self.body.splitlines() if not ln.startswith("*"))
        self.assertNotIn("|", cards)
        self.assertNotIn("$", cards)
        self.assertIn("tn0__t0", cards)

    def test_wire_cards_preserved_except_unreferenced_hubs(self) -> None:
        src = len(g._wire_cards(self.pex))
        kept = len([ln for ln in self.body.split("* Wire parasitics\n", 1)[1].splitlines() if ln])
        m = re.search(r"(\d+) unreferenced hub legs dropped", self.body)
        self.assertEqual(kept + int(m.group(1)), src)

    def test_broken_ladder_is_detected(self) -> None:
        lines = self.body.splitlines()
        i = next(n for n, ln in enumerate(lines) if ln.startswith("XRU100 "))
        toks = lines[i].split()
        toks[2] = "vss"  # cut the chain after XRU100
        lines[i] = " ".join(toks)
        problems = g.verify("\n".join(lines))
        self.assertTrue(any("XRU100" in p for p in problems))

    def test_unmatched_device_is_an_error(self) -> None:
        bad = self.pex.replace("W=8U", "W=7U", 1)
        with self.assertRaises(g.GenerationError):
            g.generate(bad, self.design)


class TopGeneratorTests(unittest.TestCase):
    """The bandgap_top cell: three subckts flattened, merged label nets, the
    XMKFB drain split (issue #278's remaining half)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pex = g.TOP_PEX.read_text()
        cls.design = g.TOP_DESIGN.read_text()
        cls.body = g.generate(cls.pex, cls.design, cell="top")

    def cards(self, prefix: str) -> list[str]:
        return [
            ln for ln in self.body.splitlines() if ln.startswith(prefix) and not ln.startswith("*")
        ]

    def test_committed_extraction_generates_a_valid_chain(self) -> None:
        self.assertEqual(g.verify(self.body), [])

    def test_device_inventory(self) -> None:
        self.assertEqual(len(self.cards("XRU")), 255)
        self.assertEqual(
            sorted(c.split()[0] for c in self.cards("XM")),
            [
                "XM1", "XM2A", "XM2B", "XM3A", "XM3B", "XM3C",
                "XMKFB", "XMN1", "XMN2", "XMN3", "XMN4",
                "XMP1", "XMP2", "XMP3", "XMP4", "XMSENSE", "XMTAIL",
            ],
        )
        self.assertEqual(
            sorted(
                c.split()[0]
                for c in self.cards("XR")
                if not c.split()[0].startswith("XRU")
            ),
            ["XR1", "XR2", "XRPU"],
        )
        self.assertEqual(len(self.cards("XQ")), 3)
        self.assertFalse(self.cards("XXTRIM"))
        self.assertFalse(re.search(r"^RS\d", self.body, re.M | re.I))

    def test_xrpu_is_rhigh(self) -> None:
        self.assertIn("rhigh", self.cards("XRPU")[0])

    def test_mkfb_drain_split(self) -> None:
        # XMKFB's own drain terminal moves onto the ammeter probe node and
        # Vmkfb bridges back to the extracted hub leg, + on the fb/net side
        # (the sign convention the hand templates established).
        xmkfb = self.cards("XMKFB")[0].split()
        self.assertEqual(xmkfb[1], "i_mkfb_probe")
        vmkfb = self.cards("Vmkfb")[0].split()
        self.assertEqual(vmkfb, ["Vmkfb", vmkfb[1], "i_mkfb_probe", "dc", "0"])
        self.assertEqual(vmkfb[1], "fb__t1")  # M$6's drain hub, aliased
        self.assertTrue(g.HUB_RE.match(vmkfb[1]))

    def test_merged_label_nets_are_legal_and_renamed(self) -> None:
        cards = "\n".join(ln for ln in self.body.splitlines() if not ln.startswith("*"))
        self.assertNotIn("|", cards)
        self.assertNotIn("$", cards)
        for alias in ("fb", "sns1", "sns2", "tn0"):
            self.assertIn(alias, cards)

    def test_mos_gate_fidelity_against_the_extraction(self) -> None:
        # M$5 is XMSENSE: gate IN_N|SNS1__t0 -> sns1__t0, straight off the card.
        m5 = next(c for c in self.pex.splitlines() if c.startswith("M$5 "))
        _nd, ng, _ns, _nb = m5.split()[1:5]
        xmsense = self.cards("XMSENSE")[0].split()
        self.assertEqual(xmsense[2], ng.lower().replace("in_n|sns1", "sns1"))

    def test_wire_cards_preserved_except_unreferenced_hubs(self) -> None:
        src = len(g._wire_cards(self.pex))
        kept = len([ln for ln in self.body.split("* Wire parasitics\n", 1)[1].splitlines() if ln])
        m = re.search(r"(\d+) unreferenced hub legs dropped", self.body)
        self.assertEqual(kept + int(m.group(1)), src)

    def test_core_cell_is_unchanged_by_the_top_extension(self) -> None:
        # The core cell's generate() must keep its committed shape: same
        # call, same output, so the landed #292 behaviour is byte-stable.
        core = g.DEFAULT_PEX.read_text()
        core_design = g.DEFAULT_DESIGN.read_text()
        self.assertEqual(g.verify(g.generate(core, core_design)), [])


if __name__ == "__main__":
    unittest.main()
