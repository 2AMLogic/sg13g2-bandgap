#!/usr/bin/env python3
"""The nodeset-seed contract shared by the seeded `klt sim` harnesses (issue #486).

`SEED_FIELDS` and `load_seeds` are one half of a two-sided substitution
contract. This side maps a committed seed CSV's record columns onto the
@@FB_SEED@@/@@SNS1_SEED@@/@@SNS2_SEED@@/@@VREF_SEED@@ deck tokens; the other
side is the deck templates themselves -- the committed `sim/*/testbench/*.tmpl`
files carrying those placeholders. A token added or renamed here must be
matched in every template that names it, so the per-bench harness modules
(trim_mc_klt, trim_coverage_klt, gen_pex_batch_requests, vref_mc_klt) import
both symbols from here instead of re-declaring them: silent drift would leave
an unsubstituted seed literal in a bench's deck -- a convergence aid quietly
dropped from a corner.

`seed_row` and `fill_deck` are the shared rendering half for trim_mc_klt,
vref_mc_klt and trim_coverage_klt, whose lookups are one idiom: an exact
(corner, temp, vdd) tuple match, None -> SystemExit. The supply rides in
pre-formatted (the MC harnesses' `VDD` string constant; trim_coverage_klt's
f"{vdd:.2f}" at its call site). gen_pex_batch_requests deliberately keeps its
own `seed_row` variant: it bakes the 125 C row with a 27 C fallback -- see its
recorded fs/125 singular-matrix rationale. cmos5l_klt takes only `fill_deck`:
it has no seed rows, but its deck and request templates get the same
unresolved-placeholder guard (issue #725).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

SEED_FIELDS = (("@@FB_SEED@@", "fb_final_v"), ("@@SNS1_SEED@@", "sns1_final_v"),
               ("@@SNS2_SEED@@", "sns2_final_v"), ("@@VREF_SEED@@", "vref_final_v"))


def load_seeds(seed_csv: str) -> dict:
    seeds: dict = {}
    with open(seed_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row["status"] == "PASS":
                seeds[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row
    return seeds


def seed_row(seeds: dict, label: str, temp: int, vdd: str, seed_csv: str) -> dict:
    row = seeds.get((label, str(temp), vdd))
    if row is None:
        raise SystemExit(f"no PASS seed row for {label}/{temp}C/{vdd}V in {seed_csv}")
    return row


def newest_seed_csv(sim_dir: str | Path) -> Path:
    """The newest committed startup-seed record under sim_dir
    (`closed-loop-startup/records/*.csv`), skipping the TC companions a
    previous enrichment derived from it (`*-tc.csv`, `*-vs-schematic*` -- the
    same discovery set sim/harness/pex_ac_runner.sh uses). Record ids lead
    with a UTC timestamp, so the lexicographic tail IS the newest record
    (issues #486/#707: the deck generators' private glob copies retired)."""
    records = Path(sim_dir) / "closed-loop-startup" / "records"
    cands = sorted(p for p in records.glob("*.csv")
                   if "-tc.csv" not in p.name and "-vs-schematic" not in p.name)
    if not cands:
        raise SystemExit(f"seed_deck.py: no seed record in {records}")
    return cands[-1]


def read_msense_width(netlist_path: str | Path) -> str:
    """XMSENSE's w= (with its unit suffix) from the live startup netlist --
    the Python twin of sim/lib/msense_width.sh's `w=[0-9.]+u` parse (issues
    #105/#473/#707): same `^XMSENSE` anchor, same required u suffix, first
    w= on the line (the shell's `grep -oE | head -1`)."""
    text = Path(netlist_path).read_text(encoding="utf-8")
    m = re.search(r"^XMSENSE\s.*?\bw=([0-9.]+u)\b", text, re.M)
    if m is None:
        raise SystemExit(f"seed_deck.py: cannot parse XMSENSE w= from {netlist_path}")
    return m.group(1)


def fill_deck(text: str, mapping: dict[str, str], kind: str = "deck") -> str:
    for token, value in mapping.items():
        text = text.replace(token, value)
    # Regex, not text.split(): placeholders embedded inside a word or quote
    # (v(fb)=@@FB_SEED@@, temp=@@TEMP_C@@C, "@@PDK_ROOT@@/...") are just as
    # unfilled as standalone ones (issue #652).
    left = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", text)))
    if left:
        raise SystemExit(f"{kind} template has unfilled placeholders: {left}")
    return text
