#!/usr/bin/env python3
"""Emit a single-file ngspice corner bundle `.lib` for `klt sim` (issue #275).

Why this file exists
--------------------
`klt sim`'s request schema carries exactly **one** model library
(`request.models.lib`, a single path) and selects a corner from it with
`.lib <models_lib> <section>` cards -- see `klt sim --help` and
`klayout_tools.sim._write_corner_deck`. A `corners.process[]` entry may name
several *sections* (`{"name": ..., "sections": [...]}`), but every one of
them is read out of that same single file.

IHP SG13G2 does not ship its corners that way. It splits them across three
per-device-family libraries, each with its own section vocabulary:

    libs.tech/ngspice/models/cornerHBT.lib     hbt_typ / hbt_bcs / hbt_wcs
    libs.tech/ngspice/models/cornerMOShv.lib   mos_tt / mos_ff / mos_ss /
                                               mos_sf / mos_fs
    libs.tech/ngspice/models/cornerRES.lib     res_typ / res_bcs / res_wcs

so this repo's five PVT corner labels are each a *triple* of sections drawn
from three different files (the pairing lives in
`sim/lib/pvt_preflight.sh`'s `HBT_SECTION_OF`/`MOS_SECTION_OF`/
`RES_SECTION_OF` maps, and this module is the single place that pairing is
mirrored for the `klt sim` path -- see `CORNER_SECTIONS` below).

A multi-file corner set cannot be expressed in `klt sim`'s request shape
today; that gap is filed upstream per this repo's friction protocol (see
`sim/harness/README.md` § "Upstream friction"). This generator is the
disclosed workaround: it writes one bundle library whose section names are
this repo's own corner labels, each section nothing but the three `.lib`
cards that corner needs. ngspice resolves nested `.lib` cards (verified
against ngspice 46 -- `sim/harness/probe/run_probe.sh` is the standing
check), so

    .lib <bundle> typ

is exactly equivalent to the three `.lib` cards every `run_pvt_sweep.sh`
template emits inline today.

The bundle is **generated, never committed**: it embeds absolute PDK paths,
which differ per machine and which this repo's evidence records
deliberately do not carry (`sim/env.sh` resolves `PDK_ROOT` per host). Its
content is a pure function of `(PDK_ROOT, PDK)` plus the table below.
"""

from __future__ import annotations

import argparse
import os
import sys

#: This repo's corner label -> (cornerHBT section, cornerMOShv section,
#: cornerRES section). Mirrors `sim/lib/pvt_preflight.sh`'s three associative
#: arrays exactly; `check_corner_sections.py`-style drift is guarded by
#: :func:`sections_from_preflight`, which re-derives the same table from that
#: shell file and is asserted against this one by
#: `sim/harness/probe/run_probe.sh`.
CORNER_SECTIONS: dict[str, tuple[str, str, str]] = {
    "typ": ("hbt_typ", "mos_tt", "res_typ"),
    "bcs": ("hbt_bcs", "mos_ff", "res_bcs"),
    "wcs": ("hbt_wcs", "mos_ss", "res_wcs"),
    "sf": ("hbt_typ", "mos_sf", "res_typ"),
    "fs": ("hbt_typ", "mos_fs", "res_typ"),
}

#: The three per-family corner libraries, in the order every existing
#: template emits them (HBT, MOS-hv, resistor).
CORNER_LIBS = ("cornerHBT.lib", "cornerMOShv.lib", "cornerRES.lib")

_PREFLIGHT_MAPS = {
    "HBT_SECTION_OF": 0,
    "MOS_SECTION_OF": 1,
    "RES_SECTION_OF": 2,
}


def sections_from_preflight(preflight_path: str) -> dict[str, tuple[str, str, str]]:
    """Re-derive :data:`CORNER_SECTIONS` from `sim/lib/pvt_preflight.sh`.

    The shell maps are the authority for the `run_pvt_sweep.sh` path, so the
    `klt sim` path must not be allowed to drift from them silently. Parsing
    them back out is cheap and makes the drift check mechanical rather than
    a review-time eyeball.
    """
    found: dict[str, dict[str, str]] = {name: {} for name in _PREFLIGHT_MAPS}
    with open(preflight_path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line.startswith("declare -A "):
                continue
            body = line[len("declare -A ") :]
            name, _, rest = body.partition("=")
            name = name.strip()
            if name not in _PREFLIGHT_MAPS:
                continue
            rest = rest.strip().lstrip("(").rstrip(")").strip()
            for token in rest.split():
                key, _, value = token.partition("]=")
                found[name][key.lstrip("[")] = value
    labels = sorted(found["MOS_SECTION_OF"])
    table: dict[str, tuple[str, str, str]] = {}
    for label in labels:
        triple = ["", "", ""]
        for name, index in _PREFLIGHT_MAPS.items():
            triple[index] = found[name].get(label, "")
        table[label] = (triple[0], triple[1], triple[2])
    return table


def render_bundle(
    models_dir: str,
    sections: dict[str, tuple[str, str, str]] | None = None,
) -> str:
    """Render the bundle library text for a PDK's `ngspice/models` directory."""
    table = CORNER_SECTIONS if sections is None else sections
    out = [
        "* sg13g2-bandgap -- generated ngspice corner bundle for `klt sim`.",
        "* Generated by sim/harness/klt_corner_bundle.py -- DO NOT COMMIT and",
        "* DO NOT EDIT BY HAND: it embeds absolute PDK paths, which are",
        "* host-specific (sim/env.sh resolves PDK_ROOT per machine).",
        "*",
        "* Each section below is one of this repo's PVT corner labels and",
        "* expands to exactly the three per-family `.lib` cards every",
        "* sim/*/testbench/*.tmpl emits inline today. See the module docstring",
        "* in sim/harness/klt_corner_bundle.py for why the bundle is needed at",
        f"* all.  PDK models dir: {models_dir}",
    ]
    for label in sorted(table):
        hbt, mos, res = table[label]
        out.append("")
        out.append(f".lib {label}")
        for lib, section in zip(CORNER_LIBS, (hbt, mos, res), strict=True):
            out.append(f'.lib "{os.path.join(models_dir, lib)}" {section}')
        out.append(f".endl {label}")
    out.append("")
    return "\n".join(out)


def resolve_models_dir(pdk_root: str | None, pdk: str | None) -> str:
    pdk_root = pdk_root or os.environ.get("PDK_ROOT") or ""
    pdk = pdk or os.environ.get("PDK") or "ihp-sg13g2"
    if not pdk_root:
        raise SystemExit(
            "klt_corner_bundle.py: PDK_ROOT is unset and --pdk-root was not given; "
            "source sim/env.sh first (see sim/README.md)."
        )
    models_dir = os.path.join(pdk_root, pdk, "libs.tech", "ngspice", "models")
    if not os.path.isdir(models_dir):
        raise SystemExit(f"klt_corner_bundle.py: no such models dir: {models_dir}")
    for lib in CORNER_LIBS:
        if not os.path.isfile(os.path.join(models_dir, lib)):
            raise SystemExit(f"klt_corner_bundle.py: missing corner library: {lib}")
    return models_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", help="write here instead of stdout")
    parser.add_argument("--pdk-root", help="override $PDK_ROOT")
    parser.add_argument("--pdk", help="override $PDK (default ihp-sg13g2)")
    parser.add_argument(
        "--check-preflight",
        metavar="PATH",
        help="assert CORNER_SECTIONS still matches sim/lib/pvt_preflight.sh's "
        "own maps and exit; emits nothing",
    )
    args = parser.parse_args(argv)

    if args.check_preflight:
        derived = sections_from_preflight(args.check_preflight)
        if derived != CORNER_SECTIONS:
            print(
                "klt_corner_bundle.py: CORNER_SECTIONS has drifted from "
                f"{args.check_preflight}\n  preflight: {derived}\n  bundle:    "
                f"{CORNER_SECTIONS}",
                file=sys.stderr,
            )
            return 1
        print(
            "klt_corner_bundle.py: CORNER_SECTIONS matches "
            f"{os.path.basename(args.check_preflight)} "
            f"({len(CORNER_SECTIONS)} corner labels)"
        )
        return 0

    text = render_bundle(resolve_models_dir(args.pdk_root, args.pdk))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
