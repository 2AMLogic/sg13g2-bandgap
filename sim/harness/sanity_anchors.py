#!/usr/bin/env python3
"""The `--sanity` anchor gate, once (issue #458).

Every `klt sim` runner under `sim/` gates grid dispatch on the same decision:
one local typ/27C/3.30V corner must land within an absolute tolerance of the
experiment's newest committed record before any grid is submitted. That
decision was implemented six times -- five inline `python3 - <<'PY'` heredocs
in the runners plus `cmos5l_klt.py`'s tested `check_anchors()` -- and the
copies had already drifted: a 0- or 2-corner report died with a raw
`ValueError`, a report with no `status` key died with a `KeyError`, only one
copy printed the corner diagnostics behind a non-pass grade, and only one
compared magnitudes. This module is the one implementation; the runners call
its CLI:

    python3 sim/harness/sanity_anchors.py <report.json> \
        --anchor vref_v=1.052999:0.0002 --anchor r1_ohm=66123:10 \
        [--magnitude] [--mode local] [--hint "where the anchor came from"]

`--anchor name=value:tol` is the spelling the runners already used for their
`ANCHORS` arrays. `--magnitude` compares `|value|` with the anchor, which the
supply benches need because ngspice's passive sign convention reports
`i(Vvdd)` negative while the supply delivers current. `--mode` labels the
gate's lines (`sanity gate (local): PASS`) for a runner that gates in more
than one place; `--hint` names the record or issue the anchor came from, which
is the one part of the message that is genuinely per-experiment.

Exit 0 with `sanity gate: PASS` is the only answer that permits a dispatch.
Anything else -- a non-pass grade, a corner count other than one, a
measurement that did not come back, a value off its anchor -- exits non-zero
with every problem listed. The gate reads a report and writes no evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_anchor(text: str) -> tuple[str, float, float]:
    """`name=value:tol` -> `(name, value, abs_tol)`."""
    try:
        name, rest = text.split("=", 1)
        value, tol = rest.split(":", 1)
        return name, float(value), float(tol)
    except ValueError:
        raise SystemExit(f"sanity_anchors.py: bad --anchor {text!r} (want name=value:tol)") from None


def gate_tag(mode: str | None = None) -> str:
    return f"sanity gate ({mode})" if mode else "sanity gate"


def check_anchors(
    report: dict,
    anchors: list[tuple[str, float, float]],
    *,
    mode: str | None = None,
    magnitude: bool = False,
) -> tuple[list[str], list[str]]:
    """Gate a one-corner report against committed anchors.

    `anchors` are `(measurement, value, abs_tol)` taken from the experiment's
    newest committed record at typ/27C/3.30V. Returns
    `(per_anchor_lines, problems)`: the lines are operator output, printed
    whatever the verdict, and an empty `problems` list is the only pass.
    """
    tag = gate_tag(mode)
    lines: list[str] = []
    problems: list[str] = []
    corners = report.get("corners") or []
    if report.get("status") != "pass":
        diagnostics = "; ".join(
            str(d.get("message", "")) for c in corners for d in (c.get("diagnostics") or [])
        ).strip("; ")
        problems.append(
            f"{tag}: klt sim graded the run {report.get('status')!r}"
            + (f": {diagnostics[:400]}" if diagnostics else "")
        )
    if len(corners) != 1:
        return lines, problems + [f"{tag}: expected exactly one corner, got {len(corners)}"]
    got = {m["name"]: m.get("value") for m in corners[0].get("measurements") or []}
    width = max((len(name) for name, _, _ in anchors), default=0)
    for name, anchor, tol in anchors:
        value = got.get(name)
        if value is None:
            problems.append(f"{tag}: measurement {name} did not come back")
            continue
        delta = abs(abs(value) - anchor) if magnitude else abs(value - anchor)
        ok = delta <= tol
        lines.append(
            f"  sanity {name:<{width}} = {value!r} (anchor {anchor}, delta {delta:.3g}) "
            f"{'ok' if ok else 'FAIL'}"
        )
        if not ok:
            problems.append(
                f"{tag}: {name} = {value!r} is {delta:.3g} from anchor {anchor} (tol {tol})"
            )
    return lines, problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path, help="the one-corner `klt sim` report JSON")
    ap.add_argument("--anchor", action="append", required=True, metavar="NAME=VALUE:TOL",
                    help="a committed anchor: measurement name, value, absolute tolerance")
    ap.add_argument("--magnitude", action="store_true",
                    help="compare |value| with the anchor (ngspice reports i(Vvdd) negative)")
    ap.add_argument("--mode", help="label for the gate's lines, e.g. `local`")
    ap.add_argument("--hint", default="the bench, not the DUT, is the first suspect",
                    help="where the anchor came from / what to suspect on a FAIL")
    args = ap.parse_args(argv)

    lines, problems = check_anchors(
        json.loads(args.report.read_text(encoding="utf-8")),
        [parse_anchor(a) for a in args.anchor],
        mode=args.mode,
        magnitude=args.magnitude,
    )
    for line in lines:
        print(line)
    if problems:
        raise SystemExit("\n".join(problems) + f"\n  -- {args.hint}; no grid is dispatched")
    print(f"  {gate_tag(args.mode)}: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
