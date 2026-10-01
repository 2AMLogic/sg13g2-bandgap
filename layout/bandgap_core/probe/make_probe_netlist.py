#!/usr/bin/env python3
"""Build the one-point sanity probe netlist from ``bandgap_core.pex.spice``.

**This is not an evidence harness.** ``sim/`` records are minted by each
experiment's own ``run_pvt_sweep.sh`` over a full PVT grid, and the five
``*-pex`` experiments' re-runs against this extraction are issue **#275**.
What this script builds is one operating point at typ / 27 °C / 3.30 V,
whose only job is to make ``layout/README.md``'s "One-point probe" table
*checkable* rather than asserted: it is the difference between "the
re-extracted trim-bearing netlist still biases up like the pre-trim one"
being a claim and being a result anyone can re-run in a second.

Why it exists as a generator rather than a committed netlist alone: the
whole lesson of issue #176 is that a hand-spliced copy of an extraction
goes stale silently when the layout changes. Every number below is read out
of ``../bandgap_core.pex.spice`` at generation time, so the probe cannot
drift from the extraction it claims to probe -- re-run it and the netlist
either regenerates identically or tells you the extraction moved.

What it does, card by card (the same hybrid-DUT convention
``sim/core-open-loop-bias-pex/testbench/*.tmpl`` documents at length -- read
that file for the full rationale, this is the short form):

* ``M$1``-``M$6`` (``pfet``) are re-encoded as X-subckt calls to the real
  ``sg13_hv_pmos`` model at their own extracted ``W``/``L``/``AS``/``AD``/
  ``PS``/``PD``; the extraction's native ``M...pfet`` cards name a generic
  placeholder model. Each leg's drain lands on its own extracted drain hub
  node and its source reaches its own source hub through a 0 V ammeter;
  each body is tied to the ideal ``vdd`` rather than through its body hub
  leg (that leg carries no current this probe measures).
* ``X$7``-``X$255+`` (``rppd``: 255 ladder units + ``R1`` + ``R2``) are
  re-encoded as calls to the real ``rppd`` PDK subckt at their own
  extracted ``W``/``L``. The extraction's own cards carry an extra ``r=``
  sheet estimate that the subckt does not take (and that is itself a lower
  bound -- klayout-tools#2652).
* ``XQ1``-``XQ3`` (``npn13G2``) are spliced from
  ``design/netlist/bandgap_core.spice``: the curated sg13g2 deck still does
  not recognise bipolars, so they are not in the extraction at all. They
  attach to the extraction's own real, physically-routed ``sns1``/``cb2``/
  ``cb3``/``vss`` pins.
* Every wire-parasitic card (533 R / 255 C / 44 coupling C) is copied
  verbatim.
* The merged tap net -- ``klt extract`` names it
  ``T001|T003|T007|T015|T031|T063|T127|TN0`` because the code-128 straps
  short all eight tap nodes -- is renamed to ``tn0_merged``: ``|`` is not
  legal in an ngspice node name. Same move the existing templates already
  make for the anonymous ``$9`` gate net.

Usage::

    python3 layout/bandgap_core/probe/make_probe_netlist.py        # regenerate
    python3 layout/bandgap_core/probe/make_probe_netlist.py --check  # verify only

``--check`` regenerates into memory and exits non-zero if the committed
netlist differs, which is what makes this a freshness check and not just a
convenience.

Stdlib only; needs neither ``klt`` nor a PDK to *generate* (running the
result needs ngspice + the PDK + the OSDI models, see ``run_probe.sh``).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CELL_DIR = HERE.parent
REPO_ROOT = CELL_DIR.parent.parent

PEX = CELL_DIR / "bandgap_core.pex.spice"
OUT = HERE / "tb_core_pex_probe.spice"

#: The merged tap net's extracted spelling, and the legal node name this
#: probe substitutes for it. `klt extract --help` is explicit that its net
#: labelling is not a stable contract, so this is read from the file rather
#: than hardcoded as a match target -- see `_merged_net_name`.
MERGED_REPLACEMENT = "tn0_merged"

#: `.op` probe conditions. One point, deliberately: see the module docstring.
CORNER = "typ"
TEMP_C = "27"
VDD_V = "3.30"
HBT_SECTION = "hbt_typ"
MOS_SECTION = "mos_tt"
RES_SECTION = "res_typ"

#: Bipolars, verbatim from `design/netlist/bandgap_core.spice` (XQ1/XQ2/XQ3
#: there), re-pointed at the extraction's own pin names.
BIPOLARS = [
    ("XQ1", "sns1", "sns1", "vss", "vss", 1),
    ("XQ2", "cb2", "cb2", "vss", "vss", 8),
    ("XQ3", "cb3", "cb3", "vss", "vss", 1),
]

CONTINUATION_RE = re.compile(r"^\+\s*(.*)$")
MOS_RE = re.compile(r"^M\$(\d+)\s+(.*)$")
RES_RE = re.compile(r"^X\$(\d+)\s+(.*)$")


def _subckt_body(text: str) -> list[str]:
    """The ``.SUBCKT`` body's cards, comments dropped, continuations folded."""
    body: list[str] = []
    in_subckt = False
    # The `.SUBCKT` header's own pin list wraps onto `+` continuation lines
    # (257 pins here), and those must be dropped with it rather than folded
    # onto the first card or emitted as a stray card of their own.
    in_header = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith(".SUBCKT"):
            in_subckt = True
            in_header = True
            continue
        if stripped.upper().startswith(".ENDS"):
            break
        if not in_subckt or stripped.startswith("*"):
            continue
        cont = CONTINUATION_RE.match(stripped)
        if cont:
            if in_header:
                continue
            if body:
                body[-1] = body[-1].rstrip() + " " + cont.group(1)
                continue
            raise SystemExit(f"continuation line with nothing to continue: {stripped!r}")
        in_header = False
        body.append(stripped)
    return body


def _merged_net_name(cards: list[str]) -> str | None:
    """The one extracted net name carrying ``|`` (klt's merged-net spelling).

    Raises if there is more than one: this probe's rename is a single
    substitution, and a second merged class would silently go unrenamed
    (and then fail in ngspice with a far less obvious error).
    """
    found = {
        tok.split("__")[0]
        for card in cards
        for tok in card.split()
        if "|" in tok
    }
    if len(found) > 1:
        raise SystemExit(f"more than one merged net: {sorted(found)}")
    return found.pop() if found else None


def _params(fields: list[str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, _, v in (f.partition("=") for f in fields)
        if _ and k
    }


def build() -> str:
    cards = _subckt_body(PEX.read_text())
    merged = _merged_net_name(cards)

    def net(name: str) -> str:
        """An extracted node name, lower-cased and made ngspice-legal."""
        if merged and name.startswith(merged):
            name = MERGED_REPLACEMENT + name[len(merged):]
        return name.lower()

    mosfets: list[tuple[str, list[str], dict[str, str]]] = []
    resistors: list[tuple[str, list[str], dict[str, str]]] = []
    wires: list[str] = []
    for card in cards:
        mos = MOS_RE.match(card)
        if mos:
            fields = mos.group(2).split()
            mosfets.append((mos.group(1), fields[:4], _params(fields[5:])))
            continue
        res = RES_RE.match(card)
        if res:
            fields = res.group(2).split()
            resistors.append((res.group(1), fields[:3], _params(fields[4:])))
            continue
        wires.append(" ".join(net(tok) for tok in card.split()))

    out: list[str] = []
    w = out.append
    w("* sg13g2-bandgap -- bandgap_core PEX one-point sanity probe (issue #272).")
    w("* GENERATED by layout/bandgap_core/probe/make_probe_netlist.py from")
    w("* layout/bandgap_core/bandgap_core.pex.spice -- do not edit by hand;")
    w("* edit the generator and re-run it (`--check` verifies this file is")
    w("* current against the committed extraction).")
    w("*")
    w("* NOT an evidence record. One operating point at")
    w(f"* corner={CORNER} temp={TEMP_C}C vdd={VDD_V}V, whose job is to make")
    w('* layout/README.md\'s "One-point probe" table re-runnable. The five')
    w("* *-pex experiments' own PVT grids against this extraction are #275.")
    w("*")
    w(f"* Extracted devices re-encoded: {len(mosfets)} pfet, {len(resistors)} rppd.")
    w(f"* Wire-parasitic cards copied verbatim: {len(wires)}.")
    w("* Bipolars (XQ1-XQ3) spliced from design/netlist/bandgap_core.spice --")
    w("* the curated sg13g2 deck does not recognise npn13G2, so they are not")
    w("* in the extraction; see layout/README.md 'Permanent blockers'.")
    if merged:
        w(f"* Merged tap net {merged} renamed to")
        w(f"* {MERGED_REPLACEMENT} ('|' is not a legal ngspice node name).")
    w("")
    w('.lib "@PDK@/libs.tech/ngspice/models/cornerHBT.lib" ' + HBT_SECTION)
    w('.lib "@PDK@/libs.tech/ngspice/models/cornerMOShv.lib" ' + MOS_SECTION)
    w('.lib "@PDK@/libs.tech/ngspice/models/cornerRES.lib" ' + RES_SECTION)
    w("")
    w(f".options temp={TEMP_C} tnom=27")
    w("")
    w(f"Vvdd vdd 0 dc {VDD_V}")
    w("Vvss vss 0 dc 0")
    w("")
    w("* FIXTURE 1 -- open-loop mirror bias (no error amplifier in this cell):")
    w("* a diode-connected replica carrying a 5 uA reference sets the shared")
    w("* gate net, exactly as sim/core-open-loop-bias-pex does.")
    w("XM0 fb fb vdd vdd sg13_hv_pmos w=10u l=1u ng=1 m=1")
    w("Ibias fb vss dc 5u")
    w("")
    w("* FIXTURE 2 -- per-leg ammeter; FIXTURE 3 -- body tied to the ideal vdd")
    w("* rather than through its own body hub leg (that leg carries no current")
    w("* this probe measures). Drain/source hub nodes are each leg's own, read")
    w("* off its extracted card.")
    for idx, (inst, nodes, params) in enumerate(mosfets, start=1):
        nd, ng, ns, _nb = (net(n) for n in nodes)
        geom = " ".join(
            f"{k}={params[k]}" for k in ("w", "l", "as", "ad", "ps", "pd") if k in params
        )
        w(f"XM{idx} {nd} {ng} m{idx}s vdd sg13_hv_pmos {geom} ng=1 m=1")
        w(f"Vm{idx} m{idx}s {ns} dc 0")
    w("")
    w("* Extracted rppd devices -- the 255 ladder units plus R1 (l=37.2u) and")
    w("* R2 (l=82.7u), each at its own extracted geometry. The extraction's")
    w("* `r=` field is klt's sheet estimate, not a subckt parameter, and is a")
    w("* lower bound on a short segment (klayout-tools#2652) -- dropped here;")
    w("* the real r3_cmc compact model computes the value from w/l.")
    for inst, nodes, params in resistors:
        a, b, bulk = (net(n) for n in nodes)
        w(f"XR{inst} {a} {b} {bulk} rppd w={params['w']} l={params['l']} m=1 b=0")
    w("")
    w("* Bipolar devices -- schematic-sourced (see header).")
    for inst, c, b, e, s, nx in BIPOLARS:
        w(f"{inst} {c} {b} {e} {s} npn13G2 Nx={nx}")
    w("")
    w("* Wire parasitics -- verbatim from the extraction, node names lowered")
    w("* and the merged tap net renamed (see header).")
    out.extend(wires)
    w("")
    w(".op")
    w(".control")
    for model in ("psp103", "psp103_nqs", "mosvar", "r3_cmc"):
        w(f"pre_osdi @OSDI@/{model}.osdi")
    w("run")
    w("* vref/tn0/cb3 give the summing resistor's two halves separately, which")
    w("* is what lets the ladder be measured as a unit count rather than")
    w("* trusted from the drawn geometry (see layout/README.md).")
    w("print v(vref) v(fb) v(sns1) v(sns2) v(cb2) v(cb3)")
    w(f"print v({MERGED_REPLACEMENT})")
    w("print " + " ".join(f"i(vm{i})" for i in range(1, len(mosfets) + 1)))
    w(".endc")
    w(".end")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed netlist matches a fresh generation; do not write",
    )
    args = parser.parse_args(argv)

    text = build()
    if args.check:
        if not OUT.exists():
            print(f"MISSING: {OUT}", file=sys.stderr)
            return 1
        if OUT.read_text() != text:
            print(
                f"STALE: {OUT.relative_to(REPO_ROOT)} differs from a fresh "
                "generation against bandgap_core.pex.spice -- re-run this "
                "script without --check and re-run the probe.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {OUT.relative_to(REPO_ROOT)} is current")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
