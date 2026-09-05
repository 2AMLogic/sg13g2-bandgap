#!/usr/bin/env python3
"""Dump a `.pex.spice` file's device cards and wire-parasitic legs separately.

Issue #176 traced a class of bug: three PEX testbench templates
(`sim/core-open-loop-bias-pex`, `sim/startup-trip-point-pex`,
`sim/sg13cmos5l-closed-loop-startup-pex`) hand-splice a *copy* of their DUT
cell's `klt extract --deck ... --parasitics` output into a `.spice.tmpl`
file rather than reading the `.pex.spice` at run time. When the layout
changes (a re-route, a device decomposition, a well/substrate-tap ring
addition -- see issue #173/#158), the extraction's own per-terminal
"hub" resistor/capacitor legs and their `<NET>__t<N>` tags are regenerated
from scratch, but nothing forces the hand-spliced copy in the `.tmpl` to
follow along -- it goes stale silently.

This tool does not attempt to auto-generate a finished template (each
testbench re-encodes its own MOS/bipolar/resistor devices as X-subckt calls
to real PDK models, applies its own body/bulk-tie fixtures, and picks which
of a multi-terminal net's several hub legs its own circuit topology
actually uses -- all genuinely testbench-specific decisions, not something
a generic `.pex.spice` parse can infer). Instead it mechanically separates
a `.pex.spice`'s own two halves so a human/agent refreshing a template's
spliced block can diff against the current committed extraction without
hand-transcribing numbers (the actual root cause of the drift #176 fixed):

  - **Devices**: the `.SUBCKT`'s own `M$N`/`R$N` device instance cards, in
    extraction order, with the net name attached to each of their
    terminals (drain/gate/source/body for M-cards; a/b/bulk for R-cards).
  - **Wire parasitics**: every other card -- the per-net star-hub
    resistors (`R<NET>_t<N> <NET>__t<N> <NET> <ohms>`), ground caps
    (`C<NET> <NET> vsubs <farads>`), net-to-net coupling caps
    (`Ccc_<a>_<b> <a> <b> <farads>`), and the substrate DC-tie
    (`R<vsubs>_dctie vsubs 0 <ohms>`) -- printed lower-cased in the same
    card order the source file uses, matching this repo's existing
    template convention (SPICE is case-insensitive; the templates already
    lower-case node/instance names for readability).

Usage:

    python3 sim/tools/dump_pex_wire_parasitics.py layout/bandgap_core/bandgap_core.pex.spice
    python3 sim/tools/dump_pex_wire_parasitics.py --devices-only layout/bandgap_startup/bandgap_startup.pex.spice
    python3 sim/tools/dump_pex_wire_parasitics.py --wires-only layout/bandgap_core/bandgap_core.pex.spice

Stdlib only; does not require `klt`, ngspice, or a PDK checkout -- it is a
pure text transform over an already-committed `.pex.spice` file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# A device card's instance name starts with M or R and is immediately
# followed by a literal "$" (klt's own anonymous-instance convention, e.g.
# `M$1`, `R$7`) -- this is what distinguishes a *device* from a
# *wire-parasitic* card, whose instance names are always
# `R<NET>[_t<N>]`/`C<NET>`/`Ccc_<a>_<b>` with no `$`.
DEVICE_RE = re.compile(r"^(M|R)\$\d+\s+(.*)$", re.IGNORECASE)
WIRE_RE = re.compile(r"^([A-Za-z][\w.$\\]*)\s+(.*)$")

# klt line-continuation: a card whose card line is split gets a "+"
# continuation line. Fold those back onto the previous card before parsing.
CONTINUATION_RE = re.compile(r"^\+\s*(.*)$")


def _fold_continuations(lines: list[str]) -> list[str]:
    folded: list[str] = []
    for line in lines:
        m = CONTINUATION_RE.match(line)
        if m and folded:
            folded[-1] = folded[-1].rstrip() + " " + m.group(1)
        else:
            folded.append(line)
    return folded


def _subckt_body(text: str) -> list[str]:
    lines = text.splitlines()
    in_subckt = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith(".SUBCKT"):
            in_subckt = True
            continue
        if stripped.upper().startswith(".ENDS"):
            break
        if not in_subckt:
            continue
        if stripped.startswith("*"):
            continue
        body.append(line)
    return _fold_continuations(body)


def dump(text: str, *, devices: bool, wires: bool) -> str:
    out: list[str] = []
    for line in _subckt_body(text):
        stripped = line.strip()
        dev_m = DEVICE_RE.match(stripped)
        if dev_m:
            if devices:
                out.append(stripped)
            continue
        wire_m = WIRE_RE.match(stripped)
        if wire_m and wires:
            out.append(stripped.lower())
    return "\n".join(out) + ("\n" if out else "")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pex_spice", type=Path, help="path to a .pex.spice file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--devices-only",
        action="store_true",
        help="print only the M$N/R$N device instance cards",
    )
    group.add_argument(
        "--wires-only",
        action="store_true",
        help="print only the wire-parasitic (star-hub R/C, coupling, dctie) cards",
    )
    args = parser.parse_args(argv)

    text = args.pex_spice.read_text()
    devices = not args.wires_only
    wires = not args.devices_only
    sys.stdout.write(dump(text, devices=devices, wires=wires))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
