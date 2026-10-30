#!/usr/bin/env python3
"""Write the per-variant batch requests + bodies for a PEX runner's --batch.

Shared by the closed-loop-{vref-pvt,psrr,zout}-pex and core-open-loop-bias-pex
`run_klt_sim.sh` runners (via sim/harness/pex_runner.sh). One request per
process corner (the runner image's klt carries one model library and SG13G2's
corner set spans three per-device-family files, klayout-tools#2668); with
--supplies, one per (process x supply) so the supply rides in a per-supply body
variant, optionally seeded from a committed record (--seed-csv).
"""
import argparse
import csv
import json
import pathlib

import klt_corner_bundle as bundle

SEED_FIELDS = (("@@FB_SEED@@", "fb_final_v"), ("@@SNS1_SEED@@", "sns1_final_v"),
               ("@@SNS2_SEED@@", "sns2_final_v"), ("@@VREF_SEED@@", "vref_final_v"))


def seed_row(seeds: dict, label: str, vdd: float, seed_csv: str) -> dict:
    # Bake the 125 C row: the seeds are one set per (corner, supply) shared by
    # the three temperatures a request sweeps, and the hot corner is the stiff
    # one -- the fs/125 point singular-matrixed from the 27 C seed on the
    # refreshed extraction while every other point converged from either. A
    # 27 C-vs-125 C seed difference is ~30-60 mV of initial guess, immaterial to
    # the points that converge and decisive for the one that does not; the
    # op-match check itself uses the per-temperature reference via --seed-csv.
    for temp_row in ("125", "27"):
        row = seeds.get((label, temp_row, f"{vdd:g}")) or seeds.get((label, temp_row, f"{vdd:.2f}"))
        if row is not None:
            return row
    raise SystemExit(f"no 27C seed row for {label}/{vdd} in {seed_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--request-template", required=True)
    ap.add_argument("--body-template", required=True)
    ap.add_argument("--lib-root", required=True,
                    help="PDK root of the body's `.lib` cards: the submitting host's "
                         "$PDK_ROOT, which klt rewrites for the runner (it refuses an "
                         "absolute runner path there). OSDI paths are --osdi, unrewritten.")
    ap.add_argument("--provision-script", required=True)
    ap.add_argument("--pdk", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--osdi", required=True)
    ap.add_argument("--supplies", nargs="*", type=float, default=None,
                    help="per-supply body variants (omit: one request per process)")
    ap.add_argument("--supply-word", default="supply",
                    help="how the per-supply comment names the supply")
    ap.add_argument("--seed-csv", default=None)
    a = ap.parse_args()

    seeds: dict = {}
    if a.seed_csv:
        with open(a.seed_csv) as fh:
            for row in csv.DictReader(fh):
                if row["status"] == "PASS":
                    seeds[(row["corner_label"], row["temp_c"], row["vdd_v"])] = row

    body_tmpl = pathlib.Path(a.body_template)
    base = json.loads(pathlib.Path(a.request_template).read_text())
    models_dir = f"{a.lib_root}/{a.pdk}/libs.tech/ngspice/models"
    out = pathlib.Path(a.work)

    for label, (hbt, mos, res) in bundle.CORNER_SECTIONS.items():
        for vdd in (a.supplies if a.supplies is not None else [None]):
            vid = "" if vdd is None else "-" + f"{vdd:.2f}".replace(".", "p")
            text = (body_tmpl.read_text()
                    .replace("@@OSDI_DIR@@", a.osdi)
                    .replace("@@PEX_BODY@@", "pex_body.inc"))
            where = f"Corner: {label}"
            if vdd is not None:
                text = text.replace("@@VDD@@", f"{vdd}")
                where += f"; {a.supply_word}: {vdd} V"
            if a.seed_csv and vdd is not None:
                row = seed_row(seeds, label, vdd, a.seed_csv)
                for token, field in SEED_FIELDS:
                    text = text.replace(token, row[field])
            text += f"""
* Batch mode only (issue #278 per-process bridge): the two families the
* request's single models.lib (klt 0.5.0 on the runner) cannot reach, as
* selection-form `.lib` cards under the submitting host's PDK root (klt rewrites them). Same
* CORNER_SECTIONS entry the request's models.lib selects the HBT family
* from. {where}{'.' if vdd is not None else ''}
.lib "{models_dir}/cornerMOShv.lib" {mos}
.lib "{models_dir}/cornerRES.lib" {res}
"""
            body = out / f"body-{label}{vid}.spice"
            body.write_text(text)
            req = json.loads(json.dumps(base)
                             .replace("@@BODY@@", str(body))
                             .replace("@@CORNER_BUNDLE@@", "UNUSED-BATCH"))
            req["backend"] = "batch"
            req["models"] = {"pdk": a.pdk, "lib": "libs.tech/ngspice/models/cornerHBT.lib"}
            req["corners"]["process"] = [hbt]
            req["batch"] = {"provision_script_path": a.provision_script}
            (out / f"request-{label}{vid}.json").write_text(json.dumps(req, indent=2) + "\n")
    print("per-variant requests written" if a.supplies is not None else "per-process requests written")


if __name__ == "__main__":
    main()
