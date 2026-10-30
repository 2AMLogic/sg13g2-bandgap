#!/usr/bin/env python3
"""Self-test of sim/harness/gen_pex_batch_requests.py (issue #432). Stdlib only: no
simulator, no PDK -- the generated per-variant body/request are read back from a
temp dir. klt 0.8.x refuses an absolute runner-root `.lib` target in a body, so the
`.lib` cards must sit under the submitting host's PDK root while the OSDI path (in
`.control`, which klt does not rewrite) keeps the runner root."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_pex_batch_requests as gen
import klt_corner_bundle as bundle

RUNNER_ROOT = "/opt/pdk"
LIB_ROOT = "/home/u/pdk"
PDK = "ihp-sg13g2"
REQUEST = {"netlist": "@@BODY@@", "models": {"lib": "@@CORNER_BUNDLE@@"}, "corners": {}}
BODY = (
    ".control\npre_osdi @@OSDI_DIR@@/psp103.osdi\n.endc\n.include @@PEX_BODY@@\n"
    "Vdd vdd 0 @@VDD@@\n"
)


class GenPexBatchRequestsTests(unittest.TestCase):
    def run_gen(self, supplies=None, lib_root=LIB_ROOT) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        (tmp / "req.tmpl").write_text(json.dumps(REQUEST))
        (tmp / "body.tmpl").write_text(BODY)
        work = tmp / "work"
        work.mkdir()
        argv = [
            "--request-template",
            str(tmp / "req.tmpl"),
            "--body-template",
            str(tmp / "body.tmpl"),
            "--lib-root",
            lib_root,
            "--provision-script",
            "/p.sh",
            "--pdk",
            PDK,
            "--work",
            str(work),
            "--osdi",
            f"{RUNNER_ROOT}/{PDK}/libs.tech/ngspice/osdi",
        ]
        if supplies is not None:
            argv += ["--supplies", *map(str, supplies)]
        old, sys.argv = sys.argv, ["gen_pex_batch_requests.py", *argv]
        try:
            gen.main()
        finally:
            sys.argv = old
        return work

    def test_lib_cards_use_lib_root_not_runner_root(self) -> None:
        work = self.run_gen()
        for label, (_, mos, res) in bundle.CORNER_SECTIONS.items():
            lines = (work / f"body-{label}.spice").read_text().splitlines()
            libs = [ln for ln in lines if ln.startswith(".lib ")]
            models = f"{LIB_ROOT}/{PDK}/libs.tech/ngspice/models"
            self.assertEqual(
                libs,
                [
                    f'.lib "{models}/cornerMOShv.lib" {mos}',
                    f'.lib "{models}/cornerRES.lib" {res}',
                ],
            )
            self.assertFalse([ln for ln in libs if RUNNER_ROOT in ln])

    def test_osdi_path_keeps_runner_root(self) -> None:
        text = (self.run_gen() / "body-typ.spice").read_text()
        self.assertIn(
            f"pre_osdi {RUNNER_ROOT}/{PDK}/libs.tech/ngspice/osdi/psp103.osdi", text
        )

    def test_request_models_block_is_pdk_relative(self) -> None:
        work = self.run_gen()
        for label, (hbt, _, _) in bundle.CORNER_SECTIONS.items():
            req = json.loads((work / f"request-{label}.json").read_text())
            self.assertEqual(
                req["models"],
                {"pdk": PDK, "lib": "libs.tech/ngspice/models/cornerHBT.lib"},
            )
            self.assertEqual(req["corners"]["process"], [hbt])
            self.assertEqual(req["backend"], "batch")
            self.assertNotIn(RUNNER_ROOT, req["models"]["lib"])

    def test_per_supply_variants_all_avoid_runner_lib_target(self) -> None:
        work = self.run_gen(supplies=[2.97, 3.3])
        bodies = sorted(work.glob("body-*.spice"))
        self.assertEqual(len(bodies), 2 * len(bundle.CORNER_SECTIONS))
        for body in bodies:
            libs = [
                ln for ln in body.read_text().splitlines() if ln.startswith(".lib ")
            ]
            self.assertEqual(len(libs), 2)
            for ln in libs:
                self.assertIn(f'"{LIB_ROOT}/', ln)
                self.assertNotIn(f'"{RUNNER_ROOT}/', ln)


if __name__ == "__main__":
    unittest.main()
