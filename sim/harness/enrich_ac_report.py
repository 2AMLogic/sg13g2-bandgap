#!/usr/bin/env python3
"""Enrich a merged AC-bench report with log-side columns and the verdict.

Issue #278. The AC benches (closed-loop-psrr-pex, closed-loop-zout-pex)
run ramp-settled: the bench body's own `.control` block sequences the
settle transient, the operating-point meas cards and the AC sweep (the
runner image's klt 0.5.0 request schema declares one analysis and has no
`measurements[].expr` -- see the bench body's header). Three classes of
column therefore live in the per-corner LOG, not the request's
measurements, and this module moves them into the report the adapter
consumes:

1. **Operating points** -- the body's `meas tran ... at=3m` cards print
   `name = value` lines into the log; parsed and appended verbatim.
2. **dB conversions** -- the request's `find v(vref) at=<f>` measurements
   are linear magnitudes (a resident-vector `.save` disables `par()`
   inside `.meas find`); each becomes its dB column through
   -20*log10 (PSRR) / +20*log10 (Zout) of the single reported value -- a
   unit conversion, not a differencing, so the 6-s.f. disposition is not
   spent.
3. **Curve extrema** -- the body's `print <name>_db` table (the full AC
   sweep) lands in the log; the worst-case value and its frequency are
   read off it the same way sim/lib/db_summary_common.awk reads them off
   a wrdata curve, including the log10(f)-linear bracketing convention.

Then each corner is re-graded with the four closed-loop criteria
(sim/lib/pvt_verdict_common.sh's pvt_closed_loop_verdict constants --
startup released, loop closed, fb not railed, settled), matching what
sim/harness/enrich_pvt_report.py applies to the transient benches.

Usage:

    python3 sim/harness/enrich_ac_report.py report-merged.json \
        --kind psrr -o report-enriched.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

DET_RELEASE_FRAC = 0.2
I_MKFB_RELEASE_A = 50e-9
DVSNS_CLOSE_V = 0.020
FB_RAIL_MARGIN_V = 0.05

_MEAS_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)\s*$", re.M)
_OP_PRINT_RE = re.compile(
    r"^(?:v\(([a-z0-9_]+)\)|i\(v([a-z0-9_]+)\)|v([a-z0-9_#]+))\s*=\s*([-+0-9.eE]+)\s*$", re.M
)
_NODESET_RE = re.compile(
    r"^\.nodeset\s+(.*)$", re.M | re.I
)
_NODESET_TERM_RE = re.compile(r"v\(([a-z0-9_]+)\)\s*=\s*([-+0-9.eE]+)", re.I)


def _parse_log(log_text: str) -> tuple[dict[str, float], list[tuple[float, float]]]:
    values = {m.group(1): float(m.group(2)) for m in _MEAS_RE.finditer(log_text)}
    # Scalar prints after the seeded `op`: `v(fb) = 2.497221e+00` /
    # `i(vmkfb) = 9.697729e-14` -- mapped onto this repo's *_op_v / i_*_a
    # column names (ngspice lowercases and strips the source's leading V,
    # so i(Vmkfb) prints as i(vmkfb) and is restored to i_vmkfb_a here).
    for m in _OP_PRINT_RE.finditer(log_text):
        node, vsrc, branch, value = m.groups()
        if node:
            values[f"{node}_op_v"] = float(value)
        elif vsrc:
            name = vsrc if vsrc.startswith(("v", "i")) else "v" + vsrc
            values[f"i_{name}_a"] = float(value)
    curve: list[tuple[float, float]] = []
    in_table = False
    for line in log_text.splitlines():
        tok = line.split()
        if not tok:
            in_table = False
            continue
        if tok[0] == "Index":
            in_table = True
            continue
        if in_table and len(tok) >= 3:
            try:
                curve.append((float(tok[1]), float(tok[2])))
            except ValueError:
                in_table = False
    return values, curve


def _nodeset_seeds(deck_text: str) -> dict[str, float]:
    seeds: dict[str, float] = {}
    for m in _NODESET_RE.finditer(deck_text):
        for term in _NODESET_TERM_RE.finditer(m.group(1)):
            seeds[term.group(1).lower()] = float(term.group(2))
    return seeds


def _interp_log(curve: list[tuple[float, float]], target: float) -> float | None:
    for (f0, d0), (f1, d1) in zip(curve, curve[1:]):
        if f0 <= target <= f1:
            if f1 == f0:
                return d0
            frac = (math.log10(target) - math.log10(f0)) / (math.log10(f1) - math.log10(f0))
            return d0 + frac * (d1 - d0)
    return None


_VDD_RE = re.compile(r"^Vvdd\s+vdd\s+0\s+DC\s+([-+0-9.eE]+)", re.M | re.I)


def _splice_deck(deck_path: Path, cwd: Path) -> str:
    """A deck plus its `.include` closure (bounded), so body-side fixtures
    like `Vvdd`/`.nodeset` are visible to the deck-side parses below. The
    batch decks point at locally fixed bodies; local decks at the work
    bodies -- both resolve from the deck's own directory or the cwd."""

    def read_with_includes(path: Path, depth: int = 0) -> str:
        text = path.read_text(encoding="utf-8", errors="replace")
        if depth >= 4:
            return text
        out: list[str] = []
        for line in text.splitlines():
            m = re.match(r"^\s*\.include\s+\"?([^\"\s]+)\"?\s*$", line, re.I)
            if not m:
                out.append(line)
                continue
            target = Path(m.group(1))
            if not target.is_absolute():
                for base in (path.parent, cwd):
                    if (base / target).exists():
                        target = base / target
                        break
            out.append(line)
            if target.exists():
                out.append(read_with_includes(target, depth + 1))
        return "\n".join(out)

    return read_with_includes(deck_path)


_STARTUP_RE = None  # per-point seed rows, loaded lazily from --seed-csv


def _load_seed_rows(path: str) -> dict:
    import csv

    rows: dict[tuple[str, str, str], dict] = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            rows[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row
    return rows


def _fmt_vdd(v: float) -> str:
    for cand in (f"{v:g}", f"{v:.2f}", f"{v:.1f}"):
        if cand.endswith("0") and "." in cand:
            continue
        return cand
    return f"{v:g}"


def enrich(report: dict, kind: str, seed_rows: dict | None = None) -> dict:
    sign = -1.0 if kind == "psrr" else 1.0
    prefix = "psrr" if kind == "psrr" else "zout"
    op_names = ("fb_op_v", "sns1_op_v", "sns2_op_v", "vref_op_v", "det_op_v", "i_vmkfb_a")
    op_match_tol_v = 0.05
    # When the body's baked (27 C) seed is the only reference available, the
    # op-match band widens with |T - 27|: fb's own temperature slope is
    # ~0.6 mV/C, so a fixed 50 mV would fail every hot/cold point whose op
    # is nonetheless the true equilibrium. With --seed-csv (the per-point
    # rows the hand-transcribed bench itself seeded from), the check uses
    # the same-temperature reference and keeps the fixed 50 mV.
    op_match_slope_v_per_c = 0.002
    for corner in report.get("corners", []):
        if corner.get("status") != "pass":
            continue
        log_path = (corner.get("artifacts") or {}).get("log")
        deck_path = (corner.get("artifacts") or {}).get("deck")
        got = {m["name"]: m.get("value") for m in corner.get("measurements", [])}
        op: dict[str, float] = {}
        curve: list[tuple[float, float]] = []
        seeds: dict[str, float] = {}
        vdd_baked: float | None = None
        cwd = Path.cwd()
        if log_path:
            p = Path(log_path)
            if not p.is_absolute():
                p = cwd / p
            if p.exists():
                op, curve = _parse_log(p.read_text(encoding="utf-8", errors="replace"))
        if deck_path:
            p = Path(deck_path)
            if not p.is_absolute():
                p = cwd / p
            if p.exists():
                deck_text = _splice_deck(p, cwd)
                seeds = _nodeset_seeds(deck_text)
                m = _VDD_RE.search(deck_text)
                if m:
                    vdd_baked = float(m.group(1))
        if vdd_baked is not None:
            # This bench's supply is baked into its body (an `alter`-driven
            # supply axis would clobber the AC stimulus -- verified on
            # ngspice 46), so the request carries no supply axis and the
            # corner id has no V token. The adapter's corner-id grammar
            # requires exactly one supply: inject the baked value here,
            # where the deck itself is the evidence for it.
            corner["supply_v"] = {"Vvdd": vdd_baked}
            cid = corner.get("corner_id", "")
            if "/novdd/" in cid:
                corner["corner_id"] = cid.replace("/novdd/", f"/{vdd_baked:.2f}V/")
        problems: list[str] = []
        for name in op_names:
            if name in op:
                corner["measurements"].append(
                    {
                        "name": name,
                        "value": op[name],
                        "spice": "log-side: body .control op print (see sim/harness/enrich_ac_report.py)",
                    }
                )
            elif name not in got:
                problems.append(f"missing op print {name}")
        # fb_seed_v: the baked .nodeset value, recorded so the op-match
        # verdict's reference is in the record itself (the hand-transcribed
        # bench's own fb_seed_v column).
        if "fb" in seeds:
            corner["measurements"].append(
                {
                    "name": "fb_seed_v",
                    "value": seeds["fb"],
                    "spice": "deck-side: the body's baked .nodeset v(fb) seed",
                }
            )
        # dB conversions of the request's linear magnitudes.
        for lin, db in (
            (f"{prefix}_dc_lin", f"{prefix}_dc_db"),
            (f"{prefix}_1khz_lin", f"{prefix}_1khz_db"),
            (f"{prefix}_100khz_lin", f"{prefix}_100khz_db"),
            (f"{prefix}_1mhz_lin", f"{prefix}_1mhz_db"),
        ):
            v = got.get(lin)
            if v is None or v <= 0:
                problems.append(f"missing {lin}")
                continue
            corner["measurements"].append(
                {
                    "name": db,
                    "value": sign * 20.0 * math.log10(v),
                    "spice": f"derived: {sign:+.0f}*20*log10({lin}) (see sim/harness/enrich_ac_report.py)",
                }
            )
        # Curve extremum from the log's print table. psrr's worst case is
        # its MINIMUM (the frequency where the rejection is weakest); zout's
        # is its PEAK -- the committed records' own column names
        # (psrr_min_db / zout_peak_db) carry that asymmetry, so the
        # enrichment keeps each experiment's schema.
        if curve:
            if kind == "psrr":
                fx, dx = min(curve, key=lambda q: q[1])
                ext_name, freq_name = "psrr_min_db", "psrr_min_freq_hz"
            else:
                fx, dx = max(curve, key=lambda q: q[1])
                ext_name, freq_name = "zout_peak_db", "zout_peak_freq_hz"
            corner["measurements"].extend(
                [
                    {
                        "name": ext_name,
                        "value": dx,
                        "spice": "log-side: worst-case over the body's printed AC sweep",
                    },
                    {
                        "name": freq_name,
                        "value": fx,
                        "spice": "log-side: frequency of the worst-case point",
                    },
                ]
            )
        else:
            problems.append("no AC sweep table in the log")
        # Op-match verdict: the landed op must sit near the reference the
        # hand-transcribed bench itself used -- sim/closed-loop-startup's
        # per-(corner, temp, vdd) row when --seed-csv provided it (same
        # fixed 50 mV), else this body's own baked 27 C seed with a
        # temperature-aware band (the body bakes one seed set per
        # corner/supply; the seed is a convergence aid, and fb legitimately
        # moves ~0.6 mV/C away from it).
        vdd = None
        cid = corner.get("corner_id", "")
        temp_c = corner.get("temperature_c")
        try:
            vdd = float(cid.split("/")[1].rstrip("V"))
        except (IndexError, ValueError):
            pass
        fb_ref = None
        tol = op_match_tol_v
        if seed_rows and temp_c is not None and vdd is not None:
            label = corner.get("process") or cid.split("/")[0]
            row = seed_rows.get((label, f"{temp_c:g}", f"{vdd:g}")) or seed_rows.get(
                (label, f"{temp_c:g}", f"{vdd:.2f}")
            )
            if row is not None:
                fb_ref = float(row["fb_final_v"])
        if fb_ref is None and seeds:
            fb_ref = seeds.get("fb")
            if temp_c is not None:
                tol += abs(float(temp_c) - 27.0) * op_match_slope_v_per_c
        if fb_ref is not None and "fb_op_v" in op:
            if abs(op["fb_op_v"] - fb_ref) > tol:
                problems.append("op_landed_far_from_seed")
        fb = op.get("fb_op_v")
        if vdd is not None and fb is not None and not (FB_RAIL_MARGIN_V <= fb <= vdd - FB_RAIL_MARGIN_V):
            problems.append("fb_railed")
        det = op.get("det_op_v")
        imk = op.get("i_vmkfb_a")
        if vdd is not None and det is not None and imk is not None:
            if not (det <= DET_RELEASE_FRAC * vdd and abs(imk) <= I_MKFB_RELEASE_A):
                problems.append("startup_not_released")
        s1, s2 = op.get("sns1_op_v"), op.get("sns2_op_v")
        if s1 is not None and s2 is not None and abs(s1 - s2) > DVSNS_CLOSE_V:
            problems.append("loop_not_closed")
        if problems:
            corner["status"] = "fail"
            corner["diagnostics"] = [{"code": "ac_bench_verdict", "message": "; ".join(problems)}]
    corners = report["corners"]
    passed = sum(1 for c in corners if c.get("status") == "pass")
    failed = sum(1 for c in corners if c.get("status") == "fail")
    errored = sum(1 for c in corners if c.get("status") == "error")
    report.update(
        passed=passed, failed=failed, errored=errored, corner_count=len(corners),
        status="fail" if failed else ("error" if errored else "pass"),
    )
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--kind", choices=("psrr", "zout"), required=True)
    ap.add_argument("--seed-csv", type=Path, default=None,
                    help="sim/closed-loop-startup record with per-(corner,temp,vdd) "
                    "op references for the op-match check")
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args(argv)
    seed_rows = _load_seed_rows(str(args.seed_csv)) if args.seed_csv else None
    report = enrich(json.loads(args.report.read_text(encoding="utf-8")), args.kind, seed_rows)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for c in report["corners"]:
        if c.get("status") != "pass":
            diag = "; ".join(d.get("message", "") for d in c.get("diagnostics", []))
            print(f"  {c.get('corner_id')}: {c['status']} {diag[:100]}")
    print(
        f"enriched: {report['status']} passed={report['passed']} "
        f"failed={report['failed']} errored={report['errored']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
