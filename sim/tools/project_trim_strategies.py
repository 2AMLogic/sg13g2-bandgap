#!/usr/bin/env python3
"""Project trim strategies from committed evidence (issue #267).

    sim/tools/project_trim_strategies.py            # markdown tables
    sim/tools/project_trim_strategies.py --csv      # the same rows as CSV

**This is a projection, not a measurement.** It combines three committed
records and reports what each candidate trim strategy *would* deliver under a
first-order model. Nothing it prints is evidence in its own right; it exists
so that `design/bandgap_trim_second_knob.md`'s comparison of the #267
candidate knobs is reproducible from the tree rather than asserted, and so
that the trim-domain Monte Carlo a chosen knob must eventually land has a
predicted number to be judged against.

Inputs (all committed, newest record of each experiment by default):

* `sim/trim-knob-jacobian/records/*.csv` — each candidate knob's measured
  `(level, drift)` column on the real loop (issue #267);
* `sim/closed-loop-vref-trim-mc/records/*-draws.csv` — N=300/point
  trim-domain mismatch draws: per die, its chosen `code*`, its measured trim
  unit, and its post-trim `vref` at −40/27/125 °C (issue #229);
* `sim/closed-loop-vref-boxtc-trim/records/*.csv` — the deterministic
  8-temperature `vref` and `VBE(Q3)` curves at code 128 (issue #229).

The model, stated so its limits are visible
---------------------------------------------

A knob moved by `x` volts of 27 °C authority is taken to add
`x · shape_k(T)` to `vref(T)`, with `shape_k` normalised to 1 at 27 °C and
read from the Jacobian record's own secants:

    shape_k(T) = 1 + ddrift_k(T) / dlevel_k

Three assumptions this makes, none of which this script can verify:

1. **Superposition / linearity.** The columns are measured at about ±20 mV of
   authority on the nominal die; §A's strategies apply them at up to ~±150 mV
   on mismatched dies. The Jacobian record bounds the knobs' own 2×
   non-linearity at ≤0.5%, but a 7× extrapolation is an assumption.
2. **Die-independence of the shapes.** The columns are deterministic
   (zero-mismatch) measurements; a mismatched die's own column may differ.
3. **Three temperatures.** §A inherits the trim MC's verify grid
   (−40/27/125 °C) and therefore says nothing about interior extrema; §B
   measures exactly that gap on the deterministic 8-temperature curves and is
   the floor that must be added to §A.

Only a trim-domain MC run with the knob actually in the netlist settles those
three — which is the follow-on this projection exists to size, not replace.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import sys
from pathlib import Path

TARGET = 1.050
MC_TEMPS = (-40.0, 27.0, 125.0)
MC_VDD = "3.30"  # the trim MC holds the supply at 3.30 V
#: trim-MC point label -> the Jacobian record's corner label for its knob columns
POINT_CORNER = {"nominal": "typ", "bcs": "bcs", "wcs": "wcs"}


# --------------------------------------------------------------- tiny linalg
def solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None if singular."""
    n = len(matrix)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-14:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col] / a[col][col]
            for k in range(col, n + 1):
                a[row][k] -= factor * a[col][k]
    return [a[i][n] / a[i][i] for i in range(n)]


def lstsq(rows: list[list[float]], ys: list[float]) -> list[float]:
    """Least-squares fit via the normal equations (small, well-scaled fits)."""
    n = len(rows[0])
    ata = [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)]
    atb = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(n)]
    return solve(ata, atb) or [0.0] * n


def minimax(basis: list[list[float]], errors: list[float]) -> float:
    """min over c of max_i |errors[i] - (basis @ c)[i]|, exactly.

    `basis` is one column per knob (each a list over the temperature points).
    The optimum of a linear Chebyshev problem equioscillates on `len(c)+1`
    points, so every candidate active set is tried and the largest feasible
    deviation is the answer.
    """
    n_pts, n_par = len(errors), len(basis)
    if n_pts <= n_par:
        return 0.0
    best = None
    for active in itertools.combinations(range(n_pts), n_par + 1):
        for signs in itertools.product((1.0, -1.0), repeat=n_par + 1):
            if signs[0] < 0:  # the overall sign is a symmetry; fix it
                continue
            matrix = [[basis[j][i] for j in range(n_par)] + [signs[k]]
                      for k, i in enumerate(active)]
            sol = solve(matrix, [errors[i] for i in active])
            if sol is None:
                continue
            coeffs, h = sol[:-1], abs(sol[-1])
            worst = max(abs(errors[i] - sum(coeffs[j] * basis[j][i] for j in range(n_par)))
                        for i in range(n_pts))
            if worst <= h * (1 + 1e-9) and (best is None or h < best):
                best = h
    return best if best is not None else 0.0


def stats(values: list[float]) -> dict[str, float]:
    n = len(values)
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    return {
        "n": n, "mean": mean, "sd": sd, "three_sigma": 3 * sd,
        "mean_plus_3sd": mean + 3 * sd, "worst": max(values),
        "frac_within_0p5_pct": 100.0 * sum(1 for v in values if v <= 0.5) / n,
    }


# ------------------------------------------------------------- record access
def newest(directory: Path, pattern: str) -> Path:
    found = sorted(directory.glob(pattern))
    if not found:
        sys.exit(f"project_trim_strategies.py: no {pattern} under {directory}")
    return found[-1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def knob_shapes(jacobian_csv: Path) -> dict[str, dict[str, list[float]]]:
    """`{corner: {knob: shape over MC_TEMPS}}` from the Jacobian record's own rows.

    Computed from the raw per-point rows rather than the `-jacobian.csv`
    digest, because the projection needs every knob's COLD leg too (the digest
    reports it only for A and C).
    """
    rows = [r for r in read_rows(jacobian_csv) if r["vdd_v"] == MC_VDD and r["status"] == "PASS"]
    byc: dict[str, dict[tuple[str, float], float]] = {}
    for row in rows:
        corner = row["corner_label"].rsplit("_" + row["knob_id"], 1)[0]
        byc.setdefault(corner, {})[(row["knob_id"], float(row["temp_c"]))] = float(row["vref_v"])
    shapes: dict[str, dict[str, list[float]]] = {}
    for corner, v in byc.items():
        out = {}
        for knob, label in (("a_hi", "A"), ("b_1", "B"), ("c_1", "C"), ("d_1", "D")):
            dlevel = v[(knob, 27.0)] - v[("base", 27.0)]
            out[label] = [1.0 + ((v[(knob, t)] - v[("base", t)]) - dlevel) / dlevel
                          if t != 27.0 else 1.0 for t in MC_TEMPS]
        shapes[corner] = out
    return shapes


def boxtc_curves(boxtc_csv: Path) -> dict[tuple[str, str], dict[float, tuple[float, float]]]:
    """`{(corner, vdd): {temp: (vref, vbe)}}` for the code-128 deterministic curves."""
    out: dict[tuple[str, str], dict[float, tuple[float, float]]] = {}
    for row in read_rows(boxtc_csv):
        if row["status"] != "PASS" or row["trim_code"] != "128":
            continue
        label = row["corner_label"]
        if not label.endswith("_code128"):
            continue
        key = (label[: -len("_code128")], row["vdd_v"])
        out.setdefault(key, {})[float(row["temp_c"])] = (float(row["vref_v"]), float(row["vbeq3_v"]))
    return out


# -------------------------------------------------------- section A: per-die
def section_a(draws_csv: Path, shapes: dict[str, dict[str, list[float]]]) -> list[dict]:
    draws = [r for r in read_rows(draws_csv) if r["verify_status"] == "PASS"]
    rows: list[dict] = []
    rules: dict[str, list[float]] = {}

    def dies(point: str) -> list[dict]:
        out = []
        for r in draws:
            if r["point"] != point:
                continue
            out.append({
                "v": [float(r["vref_n40c_v"]), float(r["vref_27c_v"]), float(r["vref_125c_v"])],
                "unit": float(r["unit_v"]), "code": int(r["code_star"]),
                "fit0": float(r["fit0_vref_v"]),
            })
        return out

    def dev(curve: list[float]) -> float:
        return 100.0 * max(abs(x - TARGET) for x in curve) / TARGET

    def moved(die: dict, codes: float, shape: list[float]) -> list[float]:
        step = codes * die["unit"]
        return [v + step * s for v, s in zip(die["v"], shape)]

    for point, corner in POINT_CORNER.items():
        shape_a, shape_c, shape_d = (shapes[corner][k] for k in "ACD")
        pool = dies(point)

        # S0 -- as built: one knob, 27 C aim. Reproduces the committed digest.
        s0 = [dev(d["v"]) for d in pool]

        # S1 -- one knob, minimax aim over the three verify temps (integer codes,
        #       so it needs per-die temperature knowledge: >= 2 insertions).
        s1 = []
        for d in pool:
            best = min(
                (dev(moved(d, m, shape_a)) for m in range(-60, 61)
                 if 0 <= d["code"] + m <= 255),
                default=dev(d["v"]))
            s1.append(best)

        # S2 -- one knob, ONE 27 C insertion: a population code-offset rule
        #       m = round(k0 + k1*code*), fitted on the typ point only and
        #       applied as-is to bcs/wcs (so those two columns are out-of-sample).
        if not rules:
            best_rule, best_score = (0.0, 0.0), None
            for k0 in [x / 4 for x in range(-32, 33)]:
                for k1 in [x / 400 for x in range(-40, 9)]:
                    vals = [dev(moved(d, max(-d["code"], min(255 - d["code"],
                                                             round(k0 + k1 * d["code"]))), shape_a))
                            for d in dies("nominal")]
                    st = stats(vals)
                    score = st["mean_plus_3sd"]
                    if best_score is None or score < best_score:
                        best_rule, best_score = (k0, k1), score
            rules["s2"] = list(best_rule)
        k0, k1 = rules["s2"]
        s2 = [dev(moved(d, max(-d["code"], min(255 - d["code"], round(k0 + k1 * d["code"]))),
                        shape_a)) for d in pool]

        # S3 -- two knobs (A + C), minimax over the three verify temps: the
        #       2-temperature-informed joint solve. Knob C is continuous here.
        basis = [shape_a, shape_c]
        s3 = [100.0 * minimax(basis, [TARGET - x for x in d["v"]]) / TARGET for d in pool]

        # S3 authority: the exact (A, C) solve that nulls level and hot drift,
        #       reported in the units a designer sizes with.
        auth_a, auth_c, code_tot = [], [], []
        for d in pool:
            sol = solve([[shape_a[1], shape_c[1]],
                         [shape_a[2] - shape_a[1], shape_c[2] - shape_c[1]]],
                        [TARGET - d["v"][1], -(d["v"][2] - d["v"][1])])
            if sol is None:
                continue
            auth_a.append(1e3 * sol[0])
            auth_c.append(1e3 * sol[1])
            code_tot.append(d["code"] + sol[0] / d["unit"])

        # S4 -- two knobs (A + C), ONE 27 C insertion: both settings predicted
        #       by a linear rule in room-temperature observables the fit stage
        #       already measures per die -- vref(code 0) (~VBE(Q3)), the die's
        #       own trim unit, and vref(27 C) at code*. Fitted on typ, applied
        #       out-of-sample to bcs/wcs.
        def observables(d: dict) -> list[float]:
            return [1.0, d["fit0"], d["unit"], d["v"][1]]

        if "s4a" not in rules:
            train = dies("nominal")
            xs = [observables(d) for d in train]
            ya, yc = [], []
            for d in train:
                sol = solve([[shape_a[1], shape_c[1]],
                             [shape_a[2] - shape_a[1], shape_c[2] - shape_c[1]]],
                            [TARGET - d["v"][1], -(d["v"][2] - d["v"][1])])
                ya.append(sol[0] if sol else 0.0)
                yc.append(sol[1] if sol else 0.0)
            rules["s4a"] = lstsq(xs, ya)
            rules["s4c"] = lstsq(xs, yc)
        s4 = []
        for d in pool:
            obs = observables(d)
            a = sum(b * x for b, x in zip(rules["s4a"], obs))
            c = sum(b * x for b, x in zip(rules["s4c"], obs))
            s4.append(dev([v + a * sa + c * sc
                           for v, sa, sc in zip(d["v"], shape_a, shape_c)]))

        # S5 -- a LEVEL-ONLY knob (D) and no R1 trim at all: the die sits at
        #       code 128 and its 27 C level is corrected by scaling the whole
        #       reference, which converts no offset into drift. This is the
        #       literal "null the level without moving the PTAT gain" knob.
        s5 = []
        for d in pool:
            at128 = moved(d, 128 - d["code"], shape_a)
            k = TARGET / at128[1]
            s5.append(dev([k * x for x in at128]))

        for name, vals, silicon, insertions in (
            ("S0 as built: knob A, 27 C null", s0, "none (as built)", "1"),
            ("S1 knob A, minimax aim", s1, "none", ">=2"),
            ("S2 knob A, code-offset rule from code*", s2, "none", "1"),
            ("S5 level-only knob (D), no R1 trim", s5, "scaling knob", "1"),
            ("S4 knobs A+C from 27 C observables", s4, "CTAT knob", "1"),
            ("S3 knobs A+C, minimax aim", s3, "CTAT knob", ">=2"),
        ):
            st = stats(vals)
            rows.append({"point": point, "strategy": name, "silicon": silicon,
                         "sort_insertions": insertions, **st})
        rows.append({
            "point": point, "strategy": "S3 authority needed", "silicon": "CTAT knob",
            "sort_insertions": ">=2",
            "n": len(auth_a),
            "knob_a_mv_min": min(auth_a), "knob_a_mv_max": max(auth_a),
            "knob_c_mv_min": min(auth_c), "knob_c_mv_max": max(auth_c),
            "code_total_min": min(code_tot), "code_total_max": max(code_tot),
            "code_railed_frac_pct": 100.0 * sum(1 for c in code_tot if c < 0 or c > 255) / len(code_tot),
        })
    rows.append({"point": "rule", "strategy": "S2 code offset = round(k0 + k1*code*)",
                 "k0": rules["s2"][0], "k1": rules["s2"][1]})
    return rows


# ------------------------------------------- section B: deterministic 8-temp
def section_b(curves: dict[tuple[str, str], dict[float, tuple[float, float]]]) -> list[dict]:
    """What the 8-temperature grid leaves that the MC's 3 temperatures cannot see.

    The knob basis here is the SHAPE pair the Jacobian record confirms -- knob
    A proportional to absolute temperature (its ratio matches dT/T to 1.4-2.5%)
    and knob C proportional to this record's own measured VBE(Q3) (to 6-8%) --
    evaluated at all eight temperatures of the committed box-TC grid rather
    than at the trim MC's three.
    """
    rows = []
    for (corner, vdd), curve in sorted(curves.items()):
        temps = sorted(curve)
        if 27.0 not in temps or len(temps) < 7:
            continue
        vref = [curve[t][0] for t in temps]
        shape_a = [(t + 273.15) / 300.15 for t in temps]
        shape_c = [curve[t][1] / curve[27.0][1] for t in temps]
        errors = [TARGET - v for v in vref]
        i27 = temps.index(27.0)

        def residual(coeffs: list[float], basis: list[list[float]]) -> float:
            return 100.0 * max(abs(errors[i] - sum(c * b[i] for c, b in zip(coeffs, basis)))
                               for i in range(len(temps))) / TARGET

        one_null = residual([errors[i27] / shape_a[i27]], [shape_a])
        one_mm = 100.0 * minimax([shape_a], errors) / TARGET
        two_mm = 100.0 * minimax([shape_a, shape_c], errors) / TARGET
        two_null = float("nan")
        if 125.0 in temps:
            i125 = temps.index(125.0)
            sol = solve([[shape_a[i27], shape_c[i27]], [shape_a[i125], shape_c[i125]]],
                        [errors[i27], errors[i125]])
            if sol:
                two_null = residual(sol, [shape_a, shape_c])
        rows.append({"corner": corner, "vdd_v": vdd, "n_temps": len(temps),
                     "one_knob_null_27c_pct": one_null, "one_knob_minimax_pct": one_mm,
                     "two_knob_null_27_125c_pct": two_null, "two_knob_minimax_pct": two_mm})
    return rows


# ------------------------------------------------------------------- output
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", action="store_true", help="emit CSV instead of markdown")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    sim = args.root / "sim"

    jac = newest(sim / "trim-knob-jacobian" / "records", "*-[0-9a-f]*.csv")
    jac = newest(sim / "trim-knob-jacobian" / "records",
                 "*.csv") if not jac.name.endswith("-jacobian.csv") else jac
    raw_jac = next(p for p in sorted((sim / "trim-knob-jacobian" / "records").glob("*.csv"))
                   if not p.name.endswith("-jacobian.csv"))
    draws = newest(sim / "closed-loop-vref-trim-mc" / "records", "*-draws.csv")
    boxtc = next(p for p in sorted((sim / "closed-loop-vref-boxtc-trim" / "records").glob("*.csv"))
                 if not p.name.endswith(("-boxtc.csv", "-trimdtc.csv")))

    shapes = knob_shapes(raw_jac)
    rows_a = section_a(draws, shapes)
    rows_b = section_b(boxtc_curves(boxtc))

    if args.csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(["section", "key", "value"])
        for row in rows_a + rows_b:
            for key, value in row.items():
                writer.writerow(["A" if row in rows_a else "B", key, value])
        return

    print(f"Inputs: {raw_jac.name} | {draws.name} | {boxtc.name}")
    print("\n### A. Per-die trimmed line, projected over the MC's three verify temperatures\n")
    print("| point | strategy | silicon | sort | mean % | sd % | 3σ % | mean+3σ % | worst % | within ±0.5% |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for row in rows_a:
        if "mean" not in row:
            continue
        print("| {point} | {strategy} | {silicon} | {sort_insertions} | {mean:.3f} | {sd:.3f} | "
              "{three_sigma:.3f} | {mean_plus_3sd:.3f} | {worst:.3f} | {frac_within_0p5_pct:.1f}% |"
              .format(**row))
    print("\n| point | knob A authority (mV) | knob C authority (mV) | total code | railed |")
    print("|---|---|---|---|---|")
    for row in rows_a:
        if "knob_a_mv_min" not in row:
            continue
        print("| {point} | {knob_a_mv_min:+.1f} … {knob_a_mv_max:+.1f} | "
              "{knob_c_mv_min:+.1f} … {knob_c_mv_max:+.1f} | {code_total_min:.0f} … "
              "{code_total_max:.0f} | {code_railed_frac_pct:.1f}% |".format(**row))
    for row in rows_a:
        if "k0" in row:
            print(f"\nS2 rule (fitted on typ, applied out-of-sample to bcs/wcs): "
                  f"m = round({row['k0']:+.2f} {row['k1']:+.4f}·code*)")
    print("\n### B. Deterministic 8-temperature residual (the bow the three-temperature "
          "projection cannot see)\n")
    print("| corner | vdd | temps | 1 knob, 27 °C null | 1 knob, minimax | "
          "2 knobs, 27+125 °C null | 2 knobs, minimax |")
    print("|---|---|---|---|---|---|---|")
    for row in rows_b:
        print("| {corner} | {vdd_v} | {n_temps} | {one_knob_null_27c_pct:.3f}% | "
              "{one_knob_minimax_pct:.3f}% | {two_knob_null_27_125c_pct:.3f}% | "
              "{two_knob_minimax_pct:.3f}% |".format(**row))


if __name__ == "__main__":
    main()
