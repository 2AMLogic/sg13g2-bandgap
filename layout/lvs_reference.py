#!/usr/bin/env python3
"""Convert a schematic-derived reference netlist to `klt lvs`'s required
plain-element SPICE form -- issue #12.

``design/netlist/bandgap_core.spice``/``bandgap_startup.spice`` (landed by
#9) are written in **subckt-call** form (`XM1 d g s b sg13_hv_pmos w=10u
l=1u ...`), the same simulation-deck shape xschem/ngspice flows always
produce (see ``klt lvs``'s own docs, ``docs/cli/lvs.md`` "Netlist form").
`klt lvs` requires the **plain-element** form (`M1 d g s b pfet L=1U W=10U`)
and ships exactly one automatic converter for it
(`reference.form: "subckt-call"`) -- but that converter is **MOS-only**: it
identifies a MOS device call by an `l`/`w` parameter and hard-requires
exactly 4 terminals (`d g s b`), so it cannot represent this circuit's
3-terminal resistor calls (`rppd`/`rhigh`, which also carry `l`/`w` and are
therefore misdetected as malformed MOS calls -- "expected 4 terminals ...
found 3") or its parameter-only bipolar calls (`npn13G2`, which carry no
`l`/`w` at all and so pass through unconverted, corrupting the whole
netlist's topology into an unresolved-subcircuit hierarchy). Concretely
verified running `klt lvs` against both reference netlists as-is for this
issue -- see ``layout/README.md`` "LVS verification". **Filed generically
against `klayout-tools`** per `CLAUDE.md`'s friction protocol (the
converter's MOS-only scope is a tool limitation, not specific to this
design): https://github.com/2AMLogic/klayout-tools/issues (see this
issue's own filing for the exact number).

This script is this repo's own stand-in conversion (not itself a `klt`
capability) -- a small, deterministic, hand-verified transcription covering
exactly the five device models these two schematics use
(`sg13_hv_pmos`/`sg13_hv_nmos`/`npn13G2`/`rppd`/`rhigh`), each mapped to the
matching `klayout.db` built-in device element letter (`M`/`Q`/`R`) per
`NetlistSpiceReader`'s own recognised syntax (verified interactively against
the pip `klayout` package this repo already depends on -- see the module
docstring's own citations below for what each conversion drops and why).

Run from the repo root::

    python3 layout/lvs_reference.py

Output is byte-for-byte deterministic (plain text, no timestamps), so
re-running (after `design/netlist/*.spice` changes) leaves `git diff`
non-empty only when the source netlist actually changed.
"""

from __future__ import annotations

import os
import re

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

# MOS device model -> klt's own EXTRACTION_DECK class name
# (klayout_tools.decks.sg13g2.EXTRACTION_DECK: nfet_class="nfet",
# pfet_class="pfet") -- matching this exactly is what lets NetlistComparer
# pair a layout-extracted device against a reference one of the same class.
_MOS_CLASS = {
    "sg13_hv_pmos": "pfet",
    "sg13_hv_nmos": "nfet",
}

# Poly-resistor sheet resistance, from spec/porting-plan.md's own citation
# table ("Rppd ... ~260 Ohm/sq", "Rhigh ... ~1360 Ohm/sq") -- approximate
# (that table itself says "~"), not a calibrated PDK model value. Used to
# compute the R-element's own literal resistance value below (issue #20:
# now a real, compared device.property, not merely a placeholder -- see
# that issue's own marker-layer work landing `rppd`/`rhigh` recognition in
# klt's curated sg13g2 deck, klayout-tools#1236/#1248).
_RES_SHEET_OHM_PER_SQ = {
    "rppd": 260.0,
    "rhigh": 1360.0,
}


#: A SPICE engineering suffix, as xschem writes them into the netlists this
#: script reads (`1u`, `35e-6`, `1.2k`). `M` is *milli* here, matching
#: ngspice's own case-insensitive suffix table -- these netlists carry no
#: mega-suffixed value, and none of the devices converted below would be
#: sanely expressed in megaohms/megametres if they did.
_SUFFIX = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "g": 1e9}

_NUMBER_WITH_SUFFIX = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)([fpnumkg])(?![\w.])")


def _eng_eval(expr: str) -> float:
    """Evaluate a braced xschem parameter expression to a float in SI units.

    ``design/sg13cmos5l/netlist/bandgap_core.spice`` carries ``pnpMPA``'s
    size as *expressions*, not literals -- ``a={ 1u * 2u }``,
    ``p={ ( 1u + 2u ) * 2 }`` -- because ``pnpMPA``'s SPICE interface is
    emitter area/perimeter rather than ``w``/``l`` (confirmed against the
    device's own ``.subckt`` in ``sg13cmos5l_pnpMPA_mod.lib``, per DR-0004).
    Suffixed literals are expanded to plain floats and the arithmetic is
    evaluated with an **empty** builtins namespace -- the input is a file
    this repo generates from its own schematics, but there is no reason for
    this helper to be able to call anything.
    """
    expanded = _NUMBER_WITH_SUFFIX.sub(
        lambda m: repr(float(m.group(1)) * _SUFFIX[m.group(2).lower()]), expr
    )
    return float(eval(expanded, {"__builtins__": {}}, {}))  # noqa: S307


def _pnpmpa_a_p(params: dict[str, str]) -> tuple[float, float]:
    """``(emitter area in um^2, emitter perimeter in um)`` for one ``pnpMPA``
    call, from its own ``a=``/``p=`` parameters."""
    area_m2 = _eng_eval(params["a"].strip("{}"))
    perim_m = _eng_eval(params["p"].strip("{}"))
    return area_m2 * 1e12, perim_m * 1e6


def _parse_device_line(line: str) -> tuple[str, list[str], str, dict[str, str]]:
    """Split one ``X<name> node... model param=value...`` line.

    Brace-aware: xschem writes multi-token parameter *expressions* as
    ``a={ 1u * 2u }`` (see :func:`_eng_eval`), which a plain ``line.split()``
    would shred into five tokens. Braced groups are collapsed to one token
    first, so ``params["a"] == "{1u*2u}"``.
    """
    line = re.sub(r"\{([^}]*)\}", lambda m: "{" + m.group(1).replace(" ", "") + "}", line)
    tokens = line.split()
    instance = tokens[0][1:]  # drop leading "X"
    rest = tokens[1:]
    first_param_idx = next((i for i, t in enumerate(rest) if "=" in t), len(rest))
    positional = rest[:first_param_idx]
    params = dict(t.split("=", 1) for t in rest[first_param_idx:])
    model = positional[-1]
    nodes = positional[:-1]
    return instance, nodes, model, params


def _um(raw: str) -> str:
    """``"10u"`` -> ``"10U"`` (klayout's own micrometre-literal convention)."""
    value = raw.rstrip("uU")
    return f"{float(value):g}U"


def _element_name(instance: str, letter: str) -> str:
    """Prefix ``instance`` (already ``X``-stripped) with ``letter`` unless it
    already starts with it -- ``"M1"`` -> ``"M1"``, ``"1"`` -> ``"M1"``, the
    same idiom `klayout_tools.netlist_normalize._instance_name` uses for its
    own MOS-only conversion (see this module's docstring)."""
    return instance if instance[:1].upper() == letter else f"{letter}{instance}"


def _cmos5l_rppd_ohms(w_um: float, l_um: float) -> float:
    """SG13CMOS5L ``rppd`` resistance, evaluated with **that PDK's own**
    symbol formula rather than the flat sheet-resistance approximation
    ``_RES_SHEET_OHM_PER_SQ`` uses for the SG13G2 port.

    Read verbatim from ``ihp-sg13cmos5l/libs.tech/xschem/sg13cmos5l_pr/
    rppd.sym``'s ``value=`` expression::

        (70.0e-6/@w + 260.0*((@b+1)*@l + (1.081*(@w+6.0e-9)+0.18e-6)*@b)
         / (@w+6.0e-9)) / @m

    with ``b=0`` (no bends -- every ``rppd`` instance in
    ``design/sg13cmos5l/bandgap_core.sch`` is drawn straight, ``b=0``) and
    ``m=1``, i.e. a ``70 uOhm*m`` end/contact term plus a 260 Ohm/sq body
    term over the width-corrected ``w + 6 nm``. Worth keeping distinct from
    the SG13G2 path: CMOS5L's ``techParams`` table carries **two** sheet
    values (``rppd_rspec = 250.0`` and ``rppdG2_rspec = 260.0``), and it is
    the symbol -- not the bare ``rppd_rspec`` -- that says which one the
    schematic's own annotated value uses.
    """
    w_m, l_m = w_um * 1e-6, l_um * 1e-6
    return 70.0e-6 / w_m + 260.0 * l_m / (w_m + 6.0e-9)


def convert(reference_path: str, pdk: str = "sg13g2") -> list[str]:
    """Convert one subckt-call reference netlist to plain-element lines.

    ``pdk`` selects the device-model vocabulary and the resistor-value
    formula: ``"sg13g2"`` (default) for this repo's original port,
    ``"sg13cmos5l"`` for the CMOS5L port (issue #66), whose device set is
    ``sg13_hv_pmos``/``rppd``/``pnpMPA`` -- no HBT, and an ``rppd`` whose
    value comes from CMOS5L's own symbol formula (see
    :func:`_cmos5l_rppd_ohms`).
    """
    out: list[str] = [
        "* Auto-generated by layout/lvs_reference.py -- DO NOT EDIT BY HAND.",
        f"* Source: {os.path.relpath(reference_path, REPO_ROOT)}",
        "* Plain-element form for `klt lvs` (see this file's own module",
        "* docstring for why the subckt-call form above cannot be used",
        '* directly, and why klt\'s own `reference.form: "subckt-call"`',
        "* converter cannot handle this circuit's mixed MOS/BJT/resistor",
        "* device set either).",
    ]
    if pdk != "sg13g2":
        # Emitted only for a non-default PDK, deliberately: the SG13G2 pair's
        # own committed `lvs_report.json`s pin this file's exact bytes
        # (`environment.reference_sha256`, checked by
        # `.github/scripts/check_evidence_formats.py`), so adding a header
        # line to *their* output would mark two still-fresh, unrelated
        # reports stale for a cosmetic change. New PDKs get the provenance
        # line from the start.
        out.append(f"* PDK: {pdk}")
    with open(reference_path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line.startswith("X"):
                continue
            instance, nodes, model, params = _parse_device_line(line)
            model_lower = model.lower()

            if model_lower == "pnpmpa":
                # SG13CMOS5L's only bipolar device (DR-0004) -- a *three*-
                # terminal subckt call (C B E), unlike SG13G2's 4-terminal
                # npn13G2 below. `NetlistSpiceReader` accepts a 3-node
                # Q-element directly (verified interactively against the
                # pip `klayout` package: produces a PNPMPA-named class with
                # terminals C/B/E and AE/PE/... parameters). The schematic's
                # own `a`/`p` (emitter area/perimeter, the parameters
                # pnpMPA's model card is scaled by -- there is no w/l on
                # this device's SPICE line at all) are carried across as the
                # reader's own AE/PE, so a future deck that *does* recognise
                # this device class has real parameters to compare against.
                # Moot for today's compare: klt's curated sg13cmos5l
                # EXTRACTION_DECK declares `bipolars=()`.
                c, b, e = nodes
                area_um2, perim_um = _pnpmpa_a_p(params)
                out.append(
                    f"{_element_name(instance, 'Q')} {c} {b} {e} {model_lower} "
                    f"AE={area_um2:g}P PE={perim_um:g}U"
                )
            elif model_lower == "rppd" and pdk == "sg13cmos5l":
                # Same 2-terminal R-element shape as the SG13G2 path below
                # (third, substrate-tie node dropped; model name written as
                # the positional model token so the reader assigns an RPPD
                # device class rather than the generic "RES"), but valued
                # with CMOS5L's own symbol formula.
                n1, n2, _sub = nodes
                l_um = float(params["l"].rstrip("uU"))
                w_um = float(params["w"].rstrip("uU"))
                r_ohm = _cmos5l_rppd_ohms(w_um, l_um)
                out.append(
                    f"{_element_name(instance, 'R')} {n1} {n2} {r_ohm:.1f} "
                    f"{model_lower} L={_um(params['l'])} W={_um(params['w'])}"
                )
            elif model_lower in _MOS_CLASS:
                d, g, s, b = nodes
                out.append(
                    f"{_element_name(instance, 'M')} {d} {g} {s} {b} "
                    f"{_MOS_CLASS[model_lower]} "
                    f"L={_um(params['l'])} W={_um(params['w'])}"
                )
            elif model_lower == "npn13g2":
                # 4-terminal Q-element (C B E S) -- NetlistSpiceReader
                # accepts this directly (verified interactively: produces a
                # BJT4Transistor-style class with terminals C/B/E/S). `Nx`
                # (emitter stripe multiplicity) has no plain-element
                # counterpart and is dropped -- moot for this compare since
                # klt's sg13g2 EXTRACTION_DECK does not recognise bipolar
                # devices at all (see this file's module docstring).
                c, b, e, s = nodes
                out.append(
                    f"{_element_name(instance, 'Q')} {c} {b} {e} {s} {model_lower}"
                )
            elif model_lower in _RES_SHEET_OHM_PER_SQ:
                # 2-terminal R-element -- the third (substrate-tie) node
                # this circuit's XR* calls carry is dropped; klayout's
                # built-in resistor device class is 2-terminal only
                # (verified interactively: terminals A/B).
                #
                # Model-name form (issue #20): `R<name> n1 n2 <value> <model>
                # L=... W=...` -- **not** a bare `R<name> n1 n2 <value>`
                # card. `NetlistSpiceReader` names a bare-value R-element's
                # device class the fixed generic "RES" (verified
                # interactively), which never matches klt's sg13g2 deck's
                # own `rppd`/`rhigh` `ResistorDevice.name` on the layout
                # side -- `NetlistComparer.same_device_classes` pairs by
                # name (case-insensitively, per its own docs; confirmed
                # against this repo's own `nfet`/`pfet` MOS classes, which
                # already round-trip through the same reader's uppercasing
                # unaffected), so a literally different word ("RES" vs
                # "rppd") never pairs regardless of case. Writing the real
                # schematic model name (`rppd`/`rhigh`, matching
                # `layout/common.py::draw_poly_res`'s own class-selecting
                # marker-layer choice for each flavour) as the positional
                # model token lets `NetlistSpiceReader` assign the device
                # class from it instead (verified interactively: produces a
                # `RPPD`/`RHIGH`-named class, `NetlistComparer` pairs case-
                # insensitively against the layout's own lowercase
                # `rppd`/`rhigh`).
                n1, n2, _sub = nodes
                l_um = float(params["l"].rstrip("uU"))
                w_um = float(params["w"].rstrip("uU"))
                r_ohm = _RES_SHEET_OHM_PER_SQ[model_lower] * (l_um / w_um)
                out.append(
                    f"{_element_name(instance, 'R')} {n1} {n2} {r_ohm:.1f} "
                    f"{model_lower} L={_um(params['l'])} W={_um(params['w'])}"
                )
            else:
                raise ValueError(f"unrecognised device model {model!r} on line: {line}")

    out.append(".end")
    return out


def _write(reference_path: str, output_path: str, pdk: str = "sg13g2") -> None:
    lines = convert(reference_path, pdk=pdk)
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    _write(
        os.path.join(REPO_ROOT, "design/netlist/bandgap_core.spice"),
        os.path.join(REPO_ROOT, "layout/bandgap_core/bandgap_core.lvs_reference.spice"),
    )
    _write(
        os.path.join(REPO_ROOT, "design/netlist/bandgap_startup.spice"),
        os.path.join(
            REPO_ROOT, "layout/bandgap_startup/bandgap_startup.lvs_reference.spice"
        ),
    )
    # SG13CMOS5L port (issue #66) -- same conversion, that PDK's own device
    # vocabulary. Directory name mirrors sim/'s own `sg13cmos5l-<slug>`
    # per-PDK prefix convention (see layout/README.md "SG13CMOS5L port").
    _write(
        os.path.join(REPO_ROOT, "design/sg13cmos5l/netlist/bandgap_core.spice"),
        os.path.join(
            REPO_ROOT,
            "layout/sg13cmos5l-bandgap_core/sg13cmos5l-bandgap_core.lvs_reference.spice",
        ),
        pdk="sg13cmos5l",
    )
