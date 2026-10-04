#!/usr/bin/env python3
"""Generate a PEX netlist body for `bandgap_core` from its committed extraction.

Issue #278 (the remainder of #275). The five PEX experiments carried a
hand-transcribed copy of the extraction in each `.spice.tmpl`. #272's
trim-bearing re-extraction made that untenable (255 `rppd` ladder units, 533
wire resistors, 255 ground caps, 44 coupling caps instead of 9/7/9), and #275
says in as many words that the body must be *generated*. This is that
generator, for the `bandgap_core` cell. It is a pure text transform over two
committed files -- `layout/bandgap_core/bandgap_core.pex.spice` and
`design/netlist/bandgap_core.spice` -- needing no `klt`, ngspice or PDK.

It builds on `dump_pex_wire_parasitics.py` (which separates device cards from
wire parasitics) and handles the three traps #275 names:

1. **Hub tags are read off the cards, never assumed.** Every device terminal
   keeps the exact per-device hub node (`VREF__t0`, `SNS2__t2`, ...) its own
   extracted card carries, so a renumbering on re-extraction flows through
   with no template edit. Nothing here hard-codes a tag.
2. **The merged tap net is renamed to a legal node.** `klt extract` names the
   net the metal straps short together `T001|T003|...|T127|TN0`; `|` is not a
   legal ngspice node character. The group is renamed to its `tn0` member (the
   ladder's own input node in the schematic) -- in node names, hub names and
   instance names alike.
3. **Ladder units get the schematic's own `XRU<n>` names** (the instance names
   D2 keys on -- see `sim/harness/README.md` "D2 and the mask option"). The
   extraction names them `X$7`, `X$8`, ...; the mapping is derived from the
   `t001`-`t254` labels on their hub nodes. Within a tap-shorted group the
   assignment is a *permutation* (see "Permutation" below).

Other conversions, each one the same convention the existing templates apply:

* `M$n ... pfet L= W= AS= ...` becomes an `sg13_hv_pmos` subcircuit call named
  after the schematic's own `XM<leg>` by matching (drain net, W) against
  `design/netlist/bandgap_core.spice`. The extraction's `nd=vdd ns=<leg>`
  convention is the reverse of the schematic's `d=<leg> s=vdd`; PSP103 is
  symmetric under that exchange for AS=AD, PS=PD (true of every leg).
* `X$n ... rppd r= L= W=` becomes `X<name> a b bulk rppd w= l= m=1 b=0`. The
  card's own `r=` estimate is dropped: it is klt's `rsh*l/w` first-order
  figure, and the PDK subcircuit computes the real value (see the PEX
  experiments' READMEs).
* `XQ*` bipolars are NOT extracted -- klt's deck does not extract them yet --
  so they are spliced verbatim from the design netlist, on bare net names.
* Hub resistor legs that no device terminal references are dropped and
  counted in the output header rather than silently ignored.

Permutation
-----------
All 255 ladder units are geometrically identical. Where a ladder tap is
shorted into the merged net, a non-merged tap `tN` that sits between two
merged taps (e.g. `t002`, between `t001` and `t003`) is adjacent to two units,
and which of them is `XRU<N>` and which `XRU<N+1>` is not recoverable from the
extraction -- the two units are indistinguishable by construction. The
generator assigns them by a deterministic matching (extraction order). That is
electrically exact and D2-equivalent (D2 compares the instance set and device
parameters, not which of two identical resistors carries which name) but it is
a permutation, not a read-off, and the output header says so with the count.
`--check` (and the test) verify the assignment is a valid chain: every
`XRU<n>` b-terminal lands on the same net as `XRU<n+1>`'s a-terminal.

`bandgap_top` (issue #278's remaining half) is the second cell. It adds, on
top of the same ladder/tap machinery:

* **Three subcircuits flattened.** `design/netlist/bandgap_top.spice` holds
  `bandgap_core`, `bandgap_amp` and `bandgap_startup`; the extraction is one
  flat deck for the assembled block, so the design inventory is flattened
  through the file's own `Xx1`/`Xx2`/`Xx3` instantiation lines before names
  are matched.
* **MOS matching by (gate, non-rail terminal set, model, W).** With the amp
  and startup devices in the pool, the core cell's (source-leg, W) key is no
  longer unique -- XM1 and XMSENSE are both sns1 10 u devices, distinguished
  only by which terminal of the pair is the gate. The key is D/S-order
  agnostic, which is also what makes the extractor's occasional drain/source
  reversal harmless (PSP103 is symmetric for AS=AD, PS=PD, true of every
  device here).
* **Merged label nets.** The top extraction reports `FB|OUT`, `IN_N|SNS1`
  and `IN_P|SNS2` as merged labels (the layout ties bandgap_amp's
  `out`/`in_n`/`in_p` pins onto the core/startup's `fb`/`sns1`/`sns2` nets --
  `layout/README.md` documents the derivation). They are renamed to the
  schematic names `fb`/`sns1`/`sns2`, the same convention the hand templates
  applied.
* **The XMKFB drain split.** Every closed-loop bench probes (or keeps, for
  topology parity) the startup circuit's contribution to the shared fb node
  through a 0 V ammeter in series with XMKFB's own drain terminal and its
  wire-parasitic hub leg, so the measured current is upstream of that leg's
  IR drop. The generator emits that split (`i_mkfb_probe` + `Vmkfb`) with
  the sign convention the hand templates established: + on the fb/net side,
  - on the device-drain side, so positive i(Vmkfb) is current flowing from
  fb into the device.

Usage:

    python3 sim/tools/gen_pex_netlist_body.py                    # core, stdout
    python3 sim/tools/gen_pex_netlist_body.py --cell top        # top, stdout
    python3 sim/tools/gen_pex_netlist_body.py -o body.inc
    python3 sim/tools/gen_pex_netlist_body.py --check           # verify only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dump_pex_wire_parasitics as dpw  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PEX = REPO_ROOT / "layout" / "bandgap_core" / "bandgap_core.pex.spice"
DEFAULT_DESIGN = REPO_ROOT / "design" / "netlist" / "bandgap_core.spice"
TOP_PEX = REPO_ROOT / "layout" / "bandgap_top" / "bandgap_top.pex.spice"
TOP_DESIGN = REPO_ROOT / "design" / "netlist" / "bandgap_top.spice"

#: Merged label nets in the top extraction that are NOT the tap strap: the
#: layout ties bandgap_amp's `out`/`in_n`/`in_p` pins directly onto the
#: core/startup `fb`/`sns1`/`sns2` nets (design/netlist/bandgap_top.spice's
#: own `Xx2 sns2 sns1 vss fb vdd bandgap_amp` instance line; the derivation
#: is documented in layout/README.md). Renamed to the schematic names, the
#: same convention the hand templates established (issue #186's guidance).
TOP_LABEL_ALIASES = {
    "fb|out": "fb",
    "in_n|sns1": "sns1",
    "in_p|sns2": "sns2",
}

MODEL = {"pfet": "sg13_hv_pmos", "nfet": "sg13_hv_nmos"}
LADDER_UNITS = 255
HUB_RE = re.compile(r"^(?P<net>.+?)__t(?P<n>\d+)$", re.IGNORECASE)
TAP_RE = re.compile(r"^t(\d{3})$")


class GenerationError(Exception):
    """The extraction does not have the shape this generator knows."""


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _params(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for tok in tokens:
        if "=" in tok:
            key, _, val = tok.partition("=")
            out[key.lower()] = val.lower()
    return out


def _split_hub(node: str) -> tuple[str, str]:
    """`T030__t1` -> (`t030`, `__t1`); a bare net -> (net, '')."""
    m = HUB_RE.match(node)
    if m:
        return m.group("net").lower(), f"__t{m.group('n')}"
    return node.lower(), ""


def _device_cards(pex_text: str) -> list[list[str]]:
    cards = []
    for card in dpw.dump(pex_text, devices=True, wires=False).splitlines():
        cards.append(card.split())
    return cards


def _wire_cards(pex_text: str) -> list[list[str]]:
    return [c.split() for c in dpw.dump(pex_text, devices=False, wires=True).splitlines()]


def _tap_groups(pex_text: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Map every `a|b|c` merged-net name found in the extraction to a legal alias.

    The alias is the group's `tn0` member when it has one (the ladder input,
    which is what the schematic calls the shorted node), the `extra` table's
    schematic name when one is declared for the group (the top cell's merged
    label nets), otherwise the members joined with `_`.
    """
    groups: dict[str, str] = dict(extra or {})
    for token in set(re.findall(r"[A-Za-z0-9$]+(?:\|[A-Za-z0-9$]+)+", pex_text)):
        members = token.lower().split("|")
        if token.lower() in groups:
            continue
        groups[token.lower()] = "tn0" if "tn0" in members else "_".join(members)
    return groups


def _apply_aliases(text: str, groups: dict[str, str]) -> str:
    for group, alias in sorted(groups.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(group, alias)
        text = text.replace(group.replace("|", "_"), alias)
    return text


# --------------------------------------------------------------------------
# Design netlist (for names the extraction does not carry)
# --------------------------------------------------------------------------


def _design(design_text: str) -> dict:
    top = design_text.split(".subckt bandgap_trim", 1)[0]
    mos: dict[tuple[str, str], list[str]] = {}
    res: dict[tuple[str, str], list[str]] = {}
    bipolars: list[str] = []
    for line in top.splitlines():
        tok = line.split()
        if not tok or line.startswith(("*", ".")):
            continue
        name = tok[0]
        p = _params(tok[1:])
        if name.upper().startswith("XM"):
            mos.setdefault((tok[1].lower(), p["w"]), []).append(name)
        elif name.upper().startswith("XR") and "rppd" in line:
            res.setdefault((p["w"], p["l"]), []).append(name)
        elif name.upper().startswith("XQ"):
            bipolars.append(line.strip())
    return {"mos": mos, "res": res, "bipolars": bipolars}


#: The top cell's subckt instantiations (design/netlist/bandgap_top.spice):
#: formal pin position -> the top-level net that pin is tied to. Extraction
#: nets are flat across the assembled block, so the design inventory has to
#: be flattened through exactly these lines before any name matching.
_TOP_SUBCKT_PINS = {
    "bandgap_core": ["vdd", "vss", "fb", "sns1", "sns2", "vref"],
    "bandgap_amp": ["in_p", "in_n", "vss", "out", "vdd"],
    "bandgap_startup": ["vdd", "vss", "sns1", "fb"],
}


def _flatten_top(design_text: str) -> tuple[list[str], list[str]]:
    """Flatten the top design's three subckts into extraction-shaped cards.

    Returns `(device_lines, bipolar_lines)` on top-level nets: XM/XR cards
    with every formal pin replaced by the net its `Xx<n>` instance line ties
    it to (internal nets keep their own names), plus the XQ cards (their
    nets are all top-level once bandgap_core is flattened). The
    `bandgap_trim` subckt is skipped -- the extraction realises code 128 as
    mask metal and carries no XXTRIM.
    """
    lines = design_text.splitlines()

    # The three instantiation lines (`Xx1 vdd vss fb sns1 sns2 vref
    # bandgap_core`, ...), each tying its subckt's formal pins to top-level
    # nets.
    instances: dict[str, list[str]] = {}
    for line in lines:
        tok = line.split()
        if len(tok) >= 2 and tok[-1] in _TOP_SUBCKT_PINS:
            instances[tok[-1]] = tok[1:-1]

    out_devices: list[str] = []
    out_bipolars: list[str] = []
    inside: str | None = None
    for line in lines:
        tok = line.split()
        if not tok or line.startswith("*"):
            continue
        low = tok[0].lower()
        if low == ".subckt":
            inside = tok[1] if tok[1] in _TOP_SUBCKT_PINS else None
            continue
        if low == ".ends":
            inside = None
            continue
        if inside is None or not low.startswith(("xm", "xr", "xq")):
            continue
        pinmap = dict(zip(_TOP_SUBCKT_PINS[inside], instances[inside]))
        nterm = 4 if low.startswith("xm") else 3
        nets = [pinmap.get(tok[i].lower(), tok[i].lower()) for i in range(1, 1 + nterm)]
        card = " ".join([tok[0], *nets, *tok[1 + nterm:]])
        out_devices.append(card)
        if low.startswith("xq"):
            out_bipolars.append(card)
    return out_devices, out_bipolars


# --------------------------------------------------------------------------
# Ladder-unit naming
# --------------------------------------------------------------------------


def _tap_numbers(node: str) -> set[int]:
    """The ladder tap indices a terminal's net stands for (t0 is `tn0`)."""
    base, _ = _split_hub(node)
    nums: set[int] = set()
    for member in base.split("|"):
        if member == "tn0":
            nums.add(0)
        elif member == "cb3":
            nums.add(LADDER_UNITS)
        else:
            m = TAP_RE.match(member)
            if m:
                nums.add(int(m.group(1)))
    return nums


def _match_units(units: list[tuple[str, str]]) -> list[tuple[int, bool]]:
    """Assign each extracted unit its schematic index k (1..255).

    Returns, per unit, `(k, swapped)`; unit `k` is `XRU<k>` joining tap
    `k-1` to tap `k`, and `swapped` says the extracted terminals are listed
    b-first. Kuhn's augmenting-path matching, in extraction order, so the
    result is deterministic.
    """
    candidates: list[list[tuple[int, bool]]] = []
    for a, b in units:
        ta, tb = _tap_numbers(a), _tap_numbers(b)
        cands = []
        for k in range(1, LADDER_UNITS + 1):
            if (k - 1) in ta and k in tb:
                cands.append((k, False))
            elif (k - 1) in tb and k in ta:
                cands.append((k, True))
        if not cands:
            raise GenerationError(f"ladder unit {a} -- {b} joins no adjacent taps")
        candidates.append(cands)

    owner: dict[int, int] = {}

    def augment(u: int, seen: set[int]) -> bool:
        for k, _ in candidates[u]:
            if k in seen:
                continue
            seen.add(k)
            if k not in owner or augment(owner[k], seen):
                owner[k] = u
                return True
        return False

    for u in range(len(units)):
        if not augment(u, set()):
            raise GenerationError("ladder units do not form a complete 1..255 chain")
    if sorted(owner) != list(range(1, LADDER_UNITS + 1)):
        raise GenerationError(f"ladder indices {sorted(owner)[:3]}... incomplete")
    result: list[tuple[int, bool]] = [(0, False)] * len(units)
    for k, u in owner.items():
        swapped = next(s for kk, s in candidates[u] if kk == k)
        result[u] = (k, swapped)
    return result


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def generate(
    pex_text: str,
    design_text: str,
    *,
    source: str = "",
    cell: str = "core",
    ammeters: dict[str, tuple[int, str]] | None = None,
) -> str:
    """Generate a PEX netlist body.

    `ammeters` maps a device name to `(terminal, voltmeter_name)`: that
    1-based terminal position of the emitted card is moved onto
    `<voltmeter_name>_p` and bridged back to its original net with a 0 V
    source named `<voltmeter_name>` -- the same drain-split the top cell
    applies to XMKFB, offered as a general mechanism so a bench can put its
    per-leg ammeters in series with exactly the DUT terminals it measures
    (`.meas ... find par('i(<voltmeter_name>)')`, the only current-measuring
    form ngspice's `.meas` accepts).
    """
    if cell not in ("core", "top"):
        raise GenerationError(f"unknown cell {cell!r}")
    is_top = cell == "top"
    ammeters = dict(ammeters or {})
    groups = _tap_groups(pex_text, TOP_LABEL_ALIASES if is_top else None)
    design = _design(design_text)
    flat_devices: list[str] = []
    flat_bipolars: list[str] = []
    if is_top:
        flat_devices, flat_bipolars = _flatten_top(design_text)
    lines: list[str] = []
    devices = _device_cards(pex_text)

    ladder_unit_geom = None
    ladder_cards: list[list[str]] = []
    other_res: list[list[str]] = []
    mos_cards: list[list[str]] = []
    for card in devices:
        kind = card[0][0].upper()
        if kind == "M":
            mos_cards.append(card)
        elif kind == "X":
            ladder_cards.append(card)
        else:
            raise GenerationError(f"unexpected device card {card[0]}")

    # Split rppd/rhigh cards into the ladder's identical units (the most
    # common rppd geometry, 255 of them) and the standalone resistors.
    geoms: dict[tuple[str, str, str], list[list[str]]] = {}
    for card in ladder_cards:
        p = _params(card[4:])
        geoms.setdefault((card[4].lower(), p["w"], p["l"]), []).append(card)
    ladder_unit_geom = max(geoms, key=lambda g: len(geoms[g]))
    unit_cards = geoms.pop(ladder_unit_geom)
    for g_cards in geoms.values():
        other_res.extend(g_cards)
    if len(unit_cards) != LADDER_UNITS:
        raise GenerationError(
            f"expected {LADDER_UNITS} ladder units of one geometry, found {len(unit_cards)}"
        )

    assignment = _match_units([(c[1], c[2]) for c in unit_cards])
    perm_units = sum(1 for c in unit_cards if len(_tap_numbers(c[1]) | _tap_numbers(c[2])) > 2)

    out_cards: list[str] = []
    used_nodes: set[str] = set()

    def node(n: str) -> str:
        n = _apply_aliases(n.lower(), groups)
        used_nodes.add(n)
        return n

    def emit_mos(name: str, nd: str, ng: str, ns: str, nb: str, model: str, p: dict) -> None:
        card = (
            f"{name} {node(nd)} {node(ng)} {node(ns)} {node(nb)} {model} "
            f"w={p['w']} l={p['l']} ng=1 m=1 as={p['as']} ad={p['ad']} ps={p['ps']} pd={p['pd']}"
        )
        if name in ammeters:
            pos, vm = ammeters[name]
            if not 1 <= pos <= 4:
                raise GenerationError(
                    f"--ammeter {name}: terminal {pos} out of range 1..4 (net positions)"
                )
            toks = card.split()
            orignet = toks[pos]
            probe = f"{vm.lower()}_p"
            toks[pos] = probe
            card = " ".join(toks)
            out_cards.append(card)
            # + on the device-terminal (probe) side, - on the original net:
            # positive i(<vm>) reads as current flowing OUT of the device
            # terminal into its original net -- the orientation the
            # committed core-bench records report their per-leg currents in.
            out_cards.append(f"{vm} {probe} {orignet} dc 0")
        else:
            out_cards.append(card)

    # MOS legs, named from the design. Core cell: the (source-leg, W) key the
    # committed generator established. Top cell: (gate, non-rail terminal
    # set, model, W) -- with amp and startup devices in the pool the source
    # leg is no longer unique (XM1 and XMSENSE are both sns1 10 u), and the
    # gate is what separates them; D/S-order agnostic, so the extractor's
    # occasional drain/source reversal (symmetric under PSP103 for
    # AS=AD/PS=PD, true of every device here) cannot mis-key a match.
    design_mos_lines = flat_devices if is_top else None
    if is_top:
        mos_inventory: dict[tuple, list[str]] = {}
        res_inventory: dict[tuple[str, str, str], list[str]] = {}
        for line in flat_devices:
            tok = line.split()
            p = _params(tok[1:])
            name = tok[0]
            if name.upper().startswith("XM"):
                gate = _apply_aliases(tok[2].lower(), groups)
                nonrail = frozenset(
                    _apply_aliases(t.lower(), groups)
                    for t in (tok[1], tok[3])
                    if _apply_aliases(t.lower(), groups) not in ("vdd", "vss")
                )
                mos_inventory.setdefault(
                    (gate, nonrail, tok[5].lower(), p["w"]), []
                ).append(name)
            elif name.upper().startswith("XR"):
                res_inventory.setdefault(
                    (tok[4].lower(), p["w"], p["l"]), []
                ).append(name)
        pool_top = {k: list(v) for k, v in mos_inventory.items()}
        for card in mos_cards:
            nd, ng, ns, nb = card[1:5]
            p = _params(card[6:])
            gate = _split_hub(_apply_aliases(ng.lower(), groups))[0]
            nonrail = frozenset(
                _split_hub(_apply_aliases(t.lower(), groups))[0]
                for t in (nd, ns)
                if _split_hub(_apply_aliases(t.lower(), groups))[0] not in ("vdd", "vss")
            )
            key = (gate, nonrail, MODEL[card[5].lower()], p["w"])
            if not pool_top.get(key):
                raise GenerationError(
                    f"no schematic XM matches gate {gate} rails {sorted(nonrail)} "
                    f"{card[5].lower()} w={p['w']} ({card[0]})"
                )
            name = pool_top[key].pop(0)
            emit_mos(name, nd, ng, ns, nb, MODEL[card[5].lower()], p)
            if is_top and name == "XMKFB" and "XMKFB" not in ammeters:
                # Drain split: move XMKFB's drain onto the ammeter probe node
                # and bridge back to its extracted hub leg with Vmkfb (sign
                # convention: + on the fb/net side, so positive i(Vmkfb) is
                # current flowing from fb into the device -- the convention
                # the hand templates established and every closed-loop bench
                # measures).
                toks = out_cards[-1].split()
                drain_hub = toks[1]
                toks[1] = "i_mkfb_probe"
                out_cards[-1] = " ".join(toks)
                out_cards.append(f"Vmkfb {drain_hub} i_mkfb_probe dc 0")
        leftover = [n for names in pool_top.values() for n in names]
        if leftover:
            raise GenerationError(f"schematic XM cards never matched an extracted device: {leftover}")
    else:
        pool = {k: list(v) for k, v in design["mos"].items()}
        for card in mos_cards:
            nd, ng, ns, nb = card[1:5]
            p = _params(card[6:])
            leg = _split_hub(ns)[0]
            key = (leg, p["w"])
            if not pool.get(key):
                raise GenerationError(f"no schematic XM matches leg {leg} w={p['w']} ({card[0]})")
            name = pool[key].pop(0)
            emit_mos(name, nd, ng, ns, nb, MODEL[card[5].lower()], p)
        leftover = [n for names in pool.values() for n in names]
        if leftover:
            raise GenerationError(f"schematic XM cards never matched an extracted device: {leftover}")

    # Standalone resistors, named from the design by (model, w, l).
    rpool = (
        {k: list(v) for k, v in res_inventory.items()}
        if is_top
        else {( "rppd", *k): list(v) for k, v in design["res"].items()}
    )
    for card in other_res:
        p = _params(card[4:])
        key = (card[4].lower(), p["w"], p["l"])
        if not rpool.get(key):
            raise GenerationError(
                f"no schematic XR matches {card[4].lower()} w={p['w']} l={p['l']}"
            )
        name = rpool[key].pop(0)
        out_cards.append(
            f"{name} {node(card[1])} {node(card[2])} {node(card[3])} {card[4].lower()} "
            f"w={p['w']} l={p['l']} m=1 b=0"
        )
    rleft = [n for names in rpool.values() for n in names]
    if rleft:
        raise GenerationError(f"schematic XR cards never matched an extracted device: {rleft}")

    # Ladder units under the schematic's XRU<n> names.
    _ladder_model, w, l = ladder_unit_geom
    ladder_out: dict[int, str] = {}
    for card, (k, swapped) in zip(unit_cards, assignment):
        a, b = (card[2], card[1]) if swapped else (card[1], card[2])
        ladder_out[k] = f"XRU{k} {node(a)} {node(b)} vsubs {_ladder_model} w={w} l={l} m=1 b=0"
    out_cards.extend(ladder_out[k] for k in range(1, LADDER_UNITS + 1))

    # Wire parasitics: drop hub legs no device terminal uses.
    wire_out: list[str] = []
    dropped = 0
    for card in _wire_cards(pex_text):
        text = _apply_aliases(" ".join(card), groups)
        tok = text.split()
        if tok[0].startswith("r") and HUB_RE.match(tok[1]) and tok[1] not in used_nodes:
            dropped += 1
            continue
        wire_out.append(text)

    # Devices not in the extraction: bipolars from the schematic.
    out_cards.extend(flat_bipolars if is_top else design["bipolars"])

    if is_top:
        merged_note = "* Merged nets renamed: " + ", ".join(
            f"{g} -> {a}" for g, a in sorted(groups.items()) if len(g) > 20 or g in TOP_LABEL_ALIASES
        )
        lines += [
            f"* PEX netlist body for bandgap_top -- GENERATED by sim/tools/gen_pex_netlist_body.py --cell top",
            f"* from {source or 'layout/bandgap_top/bandgap_top.pex.spice'} and"
            " design/netlist/bandgap_top.spice (three subckts, flattened). Do not edit; regenerate.",
            f"* {len(mos_cards)} MOS legs, {len(other_res)} standalone resistors, {LADDER_UNITS}"
            " ladder units (XRU<n>), 3 spliced bipolars, 1 Vmkfb drain split;",
            f"* {len(wire_out)} wire-parasitic cards kept, {dropped} unreferenced hub legs dropped.",
            merged_note,
            f"* Ladder naming: {perm_units} units touch a tap-shorted group; where one tap sits",
            "* between two merged taps the two adjacent units are geometrically identical and",
            "* their XRU<n> names are a deterministic permutation, electrically exact and",
            "* D2-equivalent (see sim/tools/gen_pex_netlist_body.py, 'Permutation').",
            "* No XXTRIM and no RS<bit> cards: the realised trim code is mask metal.",
            "",
            "* Devices",
            *out_cards,
            "",
            "* Wire parasitics",
            *wire_out,
        ]
    else:
        lines += [
            "* PEX netlist body for bandgap_core -- GENERATED by sim/tools/gen_pex_netlist_body.py",
            f"* from {source or 'layout/bandgap_core/bandgap_core.pex.spice'} and"
            " design/netlist/bandgap_core.spice. Do not edit; regenerate.",
            f"* {len(mos_cards)} MOS legs, {len(other_res)} standalone rppd, {LADDER_UNITS} ladder"
            " units (XRU<n>), 3 spliced bipolars;",
            f"* {len(wire_out)} wire-parasitic cards kept, {dropped} unreferenced hub legs dropped.",
            "* Merged tap net renamed: " + ", ".join(f"{g} -> {a}" for g, a in sorted(groups.items())),
            f"* Ladder naming: {perm_units} units touch a tap-shorted group; where one tap sits",
            "* between two merged taps the two adjacent units are geometrically identical and",
            "* their XRU<n> names are a deterministic permutation, electrically exact and",
            "* D2-equivalent (see sim/tools/gen_pex_netlist_body.py, 'Permutation').",
            "* No XXTRIM and no RS<bit> cards: the realised trim code is mask metal.",
            "",
            "* Devices",
            *out_cards,
            "",
            "* Wire parasitics",
            *wire_out,
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def verify(body: str) -> list[str]:
    """Return problems found in a generated body (empty list == clean)."""
    problems: list[str] = []
    cards = "\n".join(ln for ln in body.splitlines() if not ln.startswith("*"))
    if "|" in cards or "$" in cards:
        problems.append("body still contains `|` or `$` (illegal node characters)")
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    xru: dict[int, tuple[str, str]] = {}
    for line in body.splitlines():
        tok = line.split()
        if not tok or tok[0].startswith("*"):
            continue
        if tok[0].lower().startswith("r") and HUB_RE.match(tok[1]):
            parent[find(tok[1])] = find(tok[2])  # a hub leg is a wire: short it
        m = re.match(r"XRU(\d+)$", tok[0])
        if m:
            xru[int(m.group(1))] = (tok[1], tok[2])
    if sorted(xru) != list(range(1, LADDER_UNITS + 1)):
        problems.append("XRU names are not exactly 1..255")
        return problems
    for k in range(1, LADDER_UNITS):
        if find(xru[k][1]) != find(xru[k + 1][0]):
            problems.append(f"XRU{k} output is not on XRU{k + 1}'s input net")
    if find(xru[1][0]) != find("tn0"):
        problems.append("XRU1 input is not the tn0 net")
    if find(xru[LADDER_UNITS][1]) != find("cb3"):
        problems.append("XRU255 output is not the cb3 net")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--cell",
        choices=("core", "top"),
        default="core",
        help="which extraction to generate from (default: core)",
    )
    ap.add_argument("--pex", type=Path, default=None)
    ap.add_argument("--design", type=Path, default=None)
    ap.add_argument(
        "--ammeter",
        action="append",
        default=[],
        metavar="DEVICE:TERMINAL:NAME",
        help="split that device's 1-based terminal through a 0 V source NAME"
        " (repeatable; e.g. --ammeter XM1:3:Vm1)",
    )
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--check", action="store_true", help="verify only, print nothing")
    args = ap.parse_args(argv)
    if args.pex is None:
        args.pex = TOP_PEX if args.cell == "top" else DEFAULT_PEX
    if args.design is None:
        args.design = TOP_DESIGN if args.cell == "top" else DEFAULT_DESIGN
    ammeters: dict[str, tuple[int, str]] = {}
    for spec in args.ammeter:
        try:
            dev, term, name = spec.split(":")
            ammeters[dev] = (int(term), name)
        except ValueError:
            print(f"gen_pex_netlist_body: bad --ammeter {spec!r}" " (want DEVICE:TERMINAL:NAME)", file=sys.stderr)
            return 2
    try:
        rel = args.pex.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = args.pex.as_posix()
    body = generate(
        args.pex.read_text(), args.design.read_text(), source=rel, cell=args.cell, ammeters=ammeters
    )
    problems = verify(body)
    for p in problems:
        print(f"gen_pex_netlist_body: {p}", file=sys.stderr)
    if problems:
        return 1
    if args.check:
        return 0
    if args.output:
        args.output.write_text(body)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
