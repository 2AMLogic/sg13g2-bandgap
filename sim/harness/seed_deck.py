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
recorded fs/125 singular-matrix rationale.
"""
from __future__ import annotations

import csv

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


def fill_deck(text: str, mapping: dict[str, str], kind: str = "deck") -> str:
    for token, value in mapping.items():
        text = text.replace(token, value)
    left = sorted({w for w in text.split() if w.startswith("@@") and w.endswith("@@")})
    if left:
        raise SystemExit(f"{kind} template has unfilled placeholders: {left}")
    return text
