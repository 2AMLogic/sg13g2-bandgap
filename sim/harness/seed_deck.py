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

The per-bench `seed_row` lookups are deliberately NOT hoisted here: each bench
resolves a row against its own point grid (trim_coverage_klt by exact
(corner, temp, vdd); gen_pex_batch_requests bakes the 125 C row -- see its
recorded fs/125 singular-matrix rationale).
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
