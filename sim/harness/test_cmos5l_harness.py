#!/usr/bin/env python3
"""Self-test for the SG13CMOS5L klt-sim conversion (issue #337). Stdlib only.

Fixture tests for `cmos5l_klt.py`, the four `sim/sg13cmos5l-*` request
templates / bench bodies / record specs and their runners. Like
`test_harness_transformers.py` this runs no ngspice, no PDK and no network,
submits nothing to any fleet, and writes nothing under sim/ -- every fixture
lives in memory or a temporary directory.

    python3 sim/harness/test_cmos5l_harness.py

What it pins, per the issue's acceptance criteria:
  * the PNP/MOS/resistor corner mapping, against the legacy scripts that
    generated every committed record (and against a PDK's section names when
    one is supplied);
  * the generated request shapes (sanity and batch shards) for the full
    45-point grid of each experiment;
  * the record shapes: the CSV header the adapter builds from each record
    spec equals the legacy CSV header, FAIL rows and missing measurements,
    provenance text, and the PEX record refusing to publish unbound;
  * the legacy verdict formulas, including partial corner failure;
  * the runners' fail-closed behaviour (no batch without the provisioning
    acknowledgement).
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmos5l_klt as ck  # noqa: E402
import enrich_pvt_report as epr  # noqa: E402
import klt_corner_bundle as kcb  # noqa: E402
import klt_sim_evidence as kse  # noqa: E402
import merge_batch_shards as mbs  # noqa: E402
from test_evidence_store import FakeStore  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]

#: experiment -> (stem, kind, families, shard count, has supply axis in request)
EXPERIMENTS = {
    "sg13cmos5l-core-open-loop-bias": ("sg13cmos5l_core_open_loop_bias", "core-open-loop", "pnp,mos,res", 5, True),
    "sg13cmos5l-startup-trip-point": ("sg13cmos5l_startup_trip_point", "trip-point", "mos,res", 15, True),
    "sg13cmos5l-closed-loop-startup": ("sg13cmos5l_closed_loop_startup", "closed-loop", "pnp,mos,res", 15, False),
    "sg13cmos5l-closed-loop-startup-pex": ("sg13cmos5l_closed_loop_startup_pex", "closed-loop", "pnp,mos,res", 15, False),
}


def tb(exp: str, suffix: str) -> Path:
    return SIM_DIR / exp / "testbench" / f"{EXPERIMENTS[exp][0]}.{suffix}"


def request(exp: str) -> dict:
    return json.loads(tb(exp, "request.json.tmpl").read_text(encoding="utf-8"))


def spec(exp: str) -> dict:
    return json.loads(tb(exp, "record-spec.json").read_text(encoding="utf-8"))


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# corner mapping
# --------------------------------------------------------------------------


class MappingTests(TempDirCase):
    def test_matches_legacy_scripts(self) -> None:
        self.assertEqual(ck.check_legacy_mapping(), [])

    def test_pnp_map_is_cmos5l_not_hbt(self) -> None:
        # SG13G2's HBT mapping is not evidence: the section NAMES differ.
        for label, (pnp, _mos, _res) in ck.CORNER_SECTIONS.items():
            self.assertNotIn("hbt", pnp)
            self.assertEqual(pnp, {"typ": "typ", "bcs": "bcs", "wcs": "wcs"}.get(label, "typ"))
        self.assertNotEqual(
            {k: v[0] for k, v in ck.CORNER_SECTIONS.items()},
            {k: v[0] for k, v in kcb.CORNER_SECTIONS.items()},
        )
        # ...while the MOS and resistor columns ARE SG13G2's (symlinked libs).
        self.assertEqual(
            {k: v[1:] for k, v in ck.CORNER_SECTIONS.items()},
            {k: v[1:] for k, v in kcb.CORNER_SECTIONS.items()},
        )

    def test_drift_from_a_legacy_script_is_caught(self) -> None:
        sim = self.tmp / "sim"
        (sim / "lib").mkdir(parents=True)
        (sim / "lib" / "pvt_preflight.sh").write_text(
            (SIM_DIR / "lib" / "pvt_preflight.sh").read_text(encoding="utf-8"), encoding="utf-8")
        for rel in ck.LEGACY_PNP_SCRIPTS:
            text = (SIM_DIR / rel).read_text(encoding="utf-8")
            if rel.startswith("sg13cmos5l-closed-loop-startup/"):
                text = text.replace("[sf]=typ", "[sf]=bcs")
            path = sim / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        problems = ck.check_legacy_mapping(sim)
        self.assertEqual(len(problems), 1)
        self.assertIn("closed-loop-startup/run_pvt_sweep.sh", problems[0])

    def fake_models(self, drop: str | None = None) -> Path:
        models = self.tmp / "models"
        files = {
            "cornerPNP.lib": ["typ", "stat", "bcs", "wcs"],
            "cornerMOShv.lib": ["mos_tt", "mos_ss", "mos_ff", "mos_sf", "mos_fs"],
            "cornerRES.lib": ["res_typ", "res_bcs", "res_wcs"],
        }
        for name, sections in files.items():
            body = "".join(f".LIB {s}\n.ENDL {s}\n" for s in sections if s != drop)
            self.write(f"models/{name}", body)
        return models

    def test_pdk_sections_present_and_missing(self) -> None:
        self.assertEqual(ck.check_pdk_sections(self.fake_models()), [])
        problems = ck.check_pdk_sections(self.fake_models(drop="wcs"))
        self.assertTrue(any("no section 'wcs'" in p for p in problems), problems)

    def test_bundle_sections(self) -> None:
        text = ck.render_bundle("/pdk/models")
        block = re.search(r"^\.lib sf\n(.*?)^\.endl sf", text, re.M | re.S).group(1)
        self.assertEqual(block.splitlines(), [
            '.lib "/pdk/models/cornerPNP.lib" typ',
            '.lib "/pdk/models/cornerMOShv.lib" mos_sf',
            '.lib "/pdk/models/cornerRES.lib" res_typ',
        ])
        self.assertNotIn("cornerHBT", text)
        no_pnp = ck.render_bundle("/pdk/models", "mos,res")
        self.assertNotIn("cornerPNP", no_pnp)
        self.assertIn('"/pdk/models/cornerMOShv.lib" mos_tt', no_pnp)

    def test_sg13g2_bundle_unchanged(self) -> None:
        text = kcb.render_bundle("/pdk/models")
        self.assertIn('.lib "/pdk/models/cornerHBT.lib" hbt_typ', text)
        self.assertNotIn("cornerPNP", text)

    def test_bad_families_rejected(self) -> None:
        for bad in ("res,mos", "pnp,xyz", ""):
            with self.assertRaises(SystemExit):
                ck.families_for(bad)


# --------------------------------------------------------------------------
# templates, specs, request shapes
# --------------------------------------------------------------------------


class TemplateTests(unittest.TestCase):
    def test_full_grid_declared(self) -> None:
        for exp, (_stem, _kind, _fam, _n, has_supply) in EXPERIMENTS.items():
            with self.subTest(exp=exp):
                corners = request(exp)["corners"]
                self.assertEqual(corners["process"], list(ck.CORNER_LABELS))
                self.assertEqual(corners["temperature_c"], [-40, 27, 125])
                if has_supply:
                    self.assertEqual(corners["supply_v"], {"Vvdd": [2.97, 3.3, 3.63]})
                else:
                    self.assertNotIn("supply_v", corners)

    def test_meas_card_names_match_measurement_names(self) -> None:
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                names = set()
                for m in request(exp)["measurements"]:
                    card = re.match(r"\.meas\s+(\w+)\s+(\w+)", m["spice"])
                    self.assertIsNotNone(card, m)
                    self.assertEqual(card.group(2), m["name"])
                    self.assertNotIn(m["name"], names)
                    names.add(m["name"])
                self.assertTrue(set(spec(exp)["pass_requires"]) <= names)

    def test_record_spec_columns_follow_corner_sections(self) -> None:
        for exp, (_s, _k, fam, *_r) in EXPERIMENTS.items():
            with self.subTest(exp=exp):
                cols = spec(exp)["extra_columns"]
                index = {"pnp": 0, "mos": 1, "res": 2}
                want = {
                    ck.EXTRA_COLUMN_NAMES[index[f]]: {l: t[index[f]] for l, t in ck.CORNER_SECTIONS.items()}
                    for f in fam.split(",")
                }
                self.assertEqual(cols, want)

    def test_spec_and_request_point_at_each_other(self) -> None:
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                s = spec(exp)
                self.assertEqual(s["Experiment"], exp)
                self.assertEqual(s["request"], f"sim/{exp}/testbench/{EXPERIMENTS[exp][0]}.request.json.tmpl")
                self.assertTrue((SIM_DIR.parent / s["request"]).is_file())
                self.assertIn("ihp-sg13cmos5l", s["PDK"])

    def test_pex_flag(self) -> None:
        self.assertTrue(spec("sg13cmos5l-closed-loop-startup-pex")["pex"])
        for exp in EXPERIMENTS:
            if not exp.endswith("-pex"):
                self.assertNotIn("pex", spec(exp))
                self.assertTrue(kse.is_pex(spec(exp), SIM_DIR / exp) is False)
        self.assertTrue(kse.is_pex(spec("sg13cmos5l-closed-loop-startup-pex"),
                                   SIM_DIR / "sg13cmos5l-closed-loop-startup-pex"))

    def test_legacy_csv_header_equals_adapter_header(self) -> None:
        """The record the adapter would build has the legacy record's columns."""
        for exp, (_s, kind, *_r) in EXPERIMENTS.items():
            with self.subTest(exp=exp):
                latest = sorted((SIM_DIR / exp / "records").glob("*.csv"))[-1]
                with latest.open(encoding="utf-8") as fh:
                    legacy = next(csv.reader(fh))
                names = [m["name"] for m in request(exp)["measurements"]]
                if kind == "closed-loop":
                    names.append("dvsns_final_v")  # appended by `enrich`
                s = ck.augment_spec(spec(exp), "10u" if exp.endswith("startup") else None)
                corner = {
                    "corner_id": "typ/3.300V/27C", "process": "typ", "temperature_c": 27,
                    "supply_v": {"Vvdd": 3.3}, "status": "pass",
                    "measurements": [{"name": n, "value": 1.0} for n in names],
                }
                rows, passed = kse.build_csv({"corners": [corner]}, s, names)
                self.assertEqual(passed, 1)
                header = list(rows[0])
                if exp == "sg13cmos5l-closed-loop-startup":
                    # msense_w rides with the extra columns, ahead of temp_c/vdd_v.
                    self.assertEqual(sorted(header), sorted(legacy))
                else:
                    self.assertEqual(header, legacy)


class PrepareTests(TempDirCase):
    def args(self, exp: str, mode: str, **over: str) -> object:
        stem, kind, fam, *_ = EXPERIMENTS[exp]
        work = self.tmp / f"work-{exp}-{mode}"
        work.mkdir(exist_ok=True)
        ns = dict(
            mode=mode, kind=kind, families=fam, request_template=str(tb(exp, "request.json.tmpl")),
            body_template=str(tb(exp, "body.spice.tmpl")), work=str(work), osdi_dir="/osdi",
            msense_w="10u" if exp.endswith("startup") else None, bundle="/tmp/bundle.lib",
            pdk="ihp-sg13cmos5l", batch_pdk_root="/opt/pdk", local_pdk_root="/local/pdk",
            provision="/prov.sh",
        )
        ns.update(over)
        return type("NS", (), ns)()

    def test_sanity_request_is_one_local_corner(self) -> None:
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                a = self.args(exp, "sanity")
                ck.prepare_sanity(a)
                req = json.loads((Path(a.work) / "request.json").read_text())
                self.assertEqual(req["corners"]["process"], ["typ"])
                self.assertEqual(req["corners"]["temperature_c"], [27])
                if EXPERIMENTS[exp][4]:
                    self.assertEqual(req["corners"]["supply_v"], {"Vvdd": [3.3]})
                self.assertEqual(req["models"], {"lib": "/tmp/bundle.lib"})
                self.assertNotIn("@@", json.dumps(req))
                body = (Path(a.work) / "body.spice").read_text()
                self.assertNotIn("@@", body)
                self.assertIn("pre_osdi /osdi/psp103.osdi", body)
                self.assertEqual(req["netlist"], str(Path(a.work) / "body.spice"))

    def test_batch_shards_cover_the_whole_grid(self) -> None:
        for exp, (_s, kind, fam, n_shards, has_supply) in EXPERIMENTS.items():
            with self.subTest(exp=exp):
                a = self.args(exp, "batch")
                ck.prepare_batch(a)
                work = Path(a.work)
                rows = [l.split("\t") for l in (work / "manifest.tsv").read_text().splitlines()]
                self.assertEqual(len(rows), n_shards)
                seen = []
                first_lib = "cornerPNP.lib" if "pnp" in fam else "cornerMOShv.lib"
                for sid, label, vdd, reqf, repf, artf, bodyf, fixedf, decks in rows:
                    req = json.loads((work / reqf).read_text())
                    fixed = (work / bodyf).read_text()
                    self.assertEqual(bodyf, f"body-fixed-{sid}.spice")  # what fixup_batch_report --body consumes
                    body = (work / f"body-{sid}.spice").read_text()
                    self.assertEqual(req["backend"], "batch")
                    self.assertEqual(req["models"], {"pdk": "ihp-sg13cmos5l",
                                                     "lib": f"libs.tech/ngspice/models/{first_lib}"})
                    sections = ck.families_for(fam)[1][label]
                    self.assertEqual(req["corners"]["process"], [sections[0]])
                    self.assertEqual(req["batch"], {"provision_script_path": "/prov.sh"})
                    # remaining families ride as body `.lib` cards on the baked root
                    for lib, section in zip(ck.families_for(fam)[0][1:], sections[1:]):
                        self.assertIn(f'.lib "/opt/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models/{lib}" {section}', body)
                        self.assertIn(f'.lib "/local/pdk/ihp-sg13cmos5l/libs.tech/ngspice/models/{lib}" {section}', fixed)
                    self.assertNotIn("/opt/pdk", fixed.replace("/opt/pdk/ihp-sg13cmos5l/libs.tech/ngspice/osdi", ""))
                    self.assertNotIn("@@", body)
                    self.assertNotIn("@@", json.dumps(req))
                    temps = req["corners"]["temperature_c"]
                    self.assertEqual(temps, [-40, 27, 125])
                    if kind == "core-open-loop":
                        self.assertEqual(vdd, "-")
                        supplies = req["corners"]["supply_v"]["Vvdd"]
                    elif has_supply:
                        supplies = req["corners"]["supply_v"]["Vvdd"]
                        self.assertEqual(supplies, [float(vdd)])
                    else:
                        self.assertNotIn("supply_v", req["corners"])
                        self.assertIn(f"PWL(0 0 200u {vdd} 2m {vdd})", body)
                        supplies = [float(vdd)]
                    for s in supplies:
                        seen.append((label, s))
                self.assertEqual(sorted(seen), sorted((l, s) for l in ck.CORNER_LABELS for s in
                                                       ([2.97, 3.3, 3.63])))

    def test_trip_point_levels_follow_the_legacy_awk(self) -> None:
        a = self.args("sg13cmos5l-startup-trip-point", "batch")
        ck.prepare_batch(a)
        req = json.loads((Path(a.work) / "request-typ-2p97.json").read_text())
        self.assertEqual(req["analysis"], {"kind": "dc", "args": "Vsns1 0 2.97 0.005"})
        cards = {m["name"]: m["spice"] for m in req["measurements"]}
        self.assertIn("when v(det)=1.4850 cross=1", cards["vtrip_v"])   # %.4f of 2.97/2
        self.assertIn("at=2.9200", cards["det_off_v"])                  # %.4f of 2.97-0.05
        req = json.loads((Path(a.work) / "request-wcs-3p63.json").read_text())
        self.assertIn("at=3.5800", {m["name"]: m["spice"] for m in req["measurements"]}["fb_off_v"])
        self.assertEqual(req["corners"]["process"], ["mos_ss"])

    def test_msense_width_substituted_and_required(self) -> None:
        a = self.args("sg13cmos5l-closed-loop-startup", "batch", msense_w="12u")
        ck.prepare_batch(a)
        body = (Path(a.work) / "body-typ-3p30.spice").read_text()
        self.assertIn("XMSENSE det sns1 vss vss sg13_hv_nmos w=12u", body)
        with self.assertRaises(SystemExit) as ctx:
            ck.prepare_batch(self.args("sg13cmos5l-closed-loop-startup", "batch", msense_w=None))
        self.assertIn("@@MSENSE_W@@", str(ctx.exception))

    def test_pex_body_geometry_is_transcribed_not_dropped(self) -> None:
        body = tb("sg13cmos5l-closed-loop-startup-pex", "body.spice.tmpl").read_text()
        self.assertEqual(len(re.findall(r"^X\w+ .*sg13_hv_[pn]mos .* as=\S+ ad=\S+ ps=\S+ pd=\S+", body, re.M)), 14)
        self.assertIn("rppd", body)
        self.assertIn("HAND-TRANSCRIBED", body)

    def test_unresolved_placeholder_is_refused(self) -> None:
        tmpl = self.tmp / "bad.body"
        tmpl.write_text("Vvdd vdd 0 dc @@NEW_TOKEN@@\n.control\n@@OSDI_DIR@@\n.endc\n")
        with self.assertRaises(SystemExit):
            ck.prepare_batch(self.args("sg13cmos5l-core-open-loop-bias", "batch", body_template=str(tmpl)))

    def test_process_axis_drift_refused(self) -> None:
        req = request("sg13cmos5l-core-open-loop-bias")
        req["corners"]["process"] = ["typ", "bcs"]
        path = self.write("req.json", json.dumps(req))
        with self.assertRaises(SystemExit):
            ck.prepare_batch(self.args("sg13cmos5l-core-open-loop-bias", "batch", request_template=str(path)))

    def test_bench_devices_match_the_legacy_templates(self) -> None:
        """Every X-device line of a legacy template is in the new body (and v.v.)."""
        legacy_of = {
            "sg13cmos5l-core-open-loop-bias": "tb_sg13cmos5l_core_open_loop_bias.spice.tmpl",
            "sg13cmos5l-startup-trip-point": "tb_sg13cmos5l_startup_trip_point.spice.tmpl",
            "sg13cmos5l-closed-loop-startup": "tb_sg13cmos5l_closed_loop_startup.spice.tmpl",
            "sg13cmos5l-closed-loop-startup-pex": "tb_sg13cmos5l_closed_loop_startup_pex.spice.tmpl",
        }

        def devices(text: str) -> set[str]:
            out = set()
            for line in text.splitlines():
                if re.match(r"^(X|V|I|R)\w* ", line) and not line.startswith(("Vvdd", "Vsub")):
                    out.add(re.sub(r"@@MSENSE_W@@", "W", re.sub(r"w=10u(?= l=0\.5u)", "w=W", line)).strip())
            return out

        for exp, name in legacy_of.items():
            with self.subTest(exp=exp):
                old = devices((SIM_DIR / exp / "testbench" / name).read_text())
                new = devices(tb(exp, "body.spice.tmpl").read_text())
                self.assertEqual(old, new)


# --------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------


def shard_report(label: str, vdd: float | None, temps=(-40, 27, 125), status="pass") -> dict:
    corners = [{
        "corner_id": f"{label}/{'novdd' if vdd is None else f'{vdd:.3f}V'}/{t}C", "process": label,
        "temperature_c": t, "status": status,
        **({"supply_v": {"Vvdd": vdd}} if vdd is not None else {}),
        "measurements": [{"name": "x", "value": 1.0}],
    } for t in temps]
    n = len(corners)
    return {"status": "pass" if status == "pass" else "fail", "corner_count": n,
            "passed": n if status == "pass" else 0, "failed": 0 if status == "pass" else n,
            "errored": 0, "corners": corners}


class MergeTests(TempDirCase):
    def stage(self, exp: str, drop: tuple[str, str] | None = None) -> Path:
        a = PrepareTests().args.__func__(self, exp, "batch")  # reuse the arg builder
        ck.prepare_batch(a)
        work = Path(a.work)
        for line in (work / "manifest.tsv").read_text().splitlines():
            sid, label, vdd, *_rest, fixed, _decks = line.split("\t")
            if drop and (label, vdd) == drop:
                continue
            req = json.loads((work / f"request-{sid}.json").read_text())
            supplies = (req["corners"].get("supply_v") or {}).get("Vvdd") or [float(vdd)]
            reports = [shard_report(label, s) for s in supplies]
            merged = reports[0]
            for extra in reports[1:]:
                merged["corners"].extend(extra["corners"])
            # distinct corner ids per supply, like klt
            if not (req["corners"].get("supply_v")):
                for c in merged["corners"]:
                    c["corner_id"] = f"{label}/novdd/{c['temperature_c']}C"
            merged["corner_count"] = merged["passed"] = len(merged["corners"])
            (work / fixed).write_text(json.dumps(merged))
        self.work = work
        return work

    def test_complete_grid_merges_for_every_experiment(self) -> None:
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                work = self.stage(exp)
                merged = ck.merge_manifest(work / "manifest.tsv", tb(exp, "request.json.tmpl"), work)
                self.assertEqual(len(merged["corners"]), 45)
                self.assertTrue(merged["grid"]["complete"])
                self.assertEqual(merged["status"], "pass")

    def test_missing_shard_refused(self) -> None:
        for exp, drop in (("sg13cmos5l-core-open-loop-bias", ("fs", "-")),
                          ("sg13cmos5l-closed-loop-startup", ("bcs", "3.63"))):
            with self.subTest(exp=exp):
                work = self.stage(exp, drop=drop)
                with self.assertRaises((SystemExit, FileNotFoundError)):
                    ck.merge_manifest(work / "manifest.tsv", tb(exp, "request.json.tmpl"), work)

    def test_short_shard_refused(self) -> None:
        exp = "sg13cmos5l-startup-trip-point"
        work = self.stage(exp)
        line = (work / "manifest.tsv").read_text().splitlines()[0].split("\t")
        path = work / line[7]
        rep = json.loads(path.read_text())
        rep["corners"].pop()
        rep["corner_count"] = rep["passed"] = len(rep["corners"])
        path.write_text(json.dumps(rep))
        with self.assertRaises(SystemExit) as ctx:
            ck.merge_manifest(work / "manifest.tsv", tb(exp, "request.json.tmpl"), work)
        self.assertIn("missing", str(ctx.exception))


# --------------------------------------------------------------------------
# verdicts / enrichment (failed + missing measurements, partial failure)
# --------------------------------------------------------------------------

TRIP_OK = {"det_on_v": 3.3, "fb_on_v": 2.7e-4, "vtrip_v": 0.56, "det_off_v": 2.5e-4, "fb_off_v": 3.3}
LOOP_OK = {"det_final_v": 4e-3, "i_mkfb_final_a": 2.5e-9, "fb_final_v": 2.5, "sns1_final_v": 0.7805,
           "sns2_final_v": 0.7803, "vref_final_v": 1.197, "det_early_v": 0.32, "fb_early_v": 0.15}


def corner(meas: dict, *, label="typ", t=27, vdd=3.3, status="pass") -> dict:
    return {
        "corner_id": f"{label}/{vdd:.3f}V/{t}C", "process": label, "temperature_c": t,
        "supply_v": {"Vvdd": vdd}, "status": status,
        "measurements": [{"name": k, "value": v} for k, v in meas.items() if v is not None],
    }


def rep(*corners: dict) -> dict:
    return {"status": "pass", "corners": list(corners)}


class VerdictTests(unittest.TestCase):
    def run_kind(self, kind: str, meas: dict, **kw) -> dict:
        return ck.enrich(rep(corner(meas, **kw)), kind)["corners"][0]

    def test_constants_match_the_shell_verdicts(self) -> None:
        text = (SIM_DIR / "lib" / "pvt_verdict_common.sh").read_text()
        for name, value in (("DET_RELEASE_FRAC", epr.DET_RELEASE_FRAC), ("I_MKFB_RELEASE_A", epr.I_MKFB_RELEASE_A),
                            ("DVSNS_CLOSE_V", epr.DVSNS_CLOSE_V), ("FB_RAIL_MARGIN_V", epr.FB_RAIL_MARGIN_V)):
            m = re.search(rf'^{name}="([^"]+)"', text, re.M)
            self.assertEqual(float(m.group(1)), value, name)
        self.assertIn("ok = (det_on >= 0.8*vdd) && (fb_on <= 0.1)", re.sub(r"\s+", " ", text))
        self.assertIn("(det_off <= 0.2*vdd) && (fb_off >= 0.8*vdd)", re.sub(r"\s+", " ", text))

    def test_trip_point_pass(self) -> None:
        self.assertEqual(self.run_kind("trip-point", TRIP_OK)["status"], "pass")

    def test_trip_point_each_criterion(self) -> None:
        cases = {
            "det_on_not_engaged": {"det_on_v": 2.0},
            "fb_on_not_driving_mirror": {"fb_on_v": 0.2},
            "vtrip_not_above_zero": {"vtrip_v": 0.0},
            "vtrip_not_below_vdd": {"vtrip_v": 3.3},
            "det_off_not_released": {"det_off_v": 1.0},
            "fb_off_not_released": {"fb_off_v": 1.0},
        }
        for crit, change in cases.items():
            with self.subTest(crit=crit):
                c = self.run_kind("trip-point", {**TRIP_OK, **change})
                self.assertEqual(c["status"], "fail")
                self.assertEqual(c["diagnostics"][0]["message"], crit)

    def test_trip_point_scales_with_supply(self) -> None:
        # det_on 2.5 V passes the 0.8*vdd bar at 2.97 V (2.376) but not at 3.63 V (2.904).
        self.assertEqual(self.run_kind("trip-point", {**TRIP_OK, "det_on_v": 2.5}, vdd=2.97)["status"], "pass")
        self.assertEqual(self.run_kind("trip-point", {**TRIP_OK, "det_on_v": 2.5}, vdd=3.63)["status"], "fail")

    def test_closed_loop_pass_appends_dvsns(self) -> None:
        c = self.run_kind("closed-loop", LOOP_OK)
        self.assertEqual(c["status"], "pass")
        d = {m["name"]: m["value"] for m in c["measurements"]}
        self.assertAlmostEqual(d["dvsns_final_v"], 0.0002, places=9)
        self.assertEqual(c["measurements"][-1]["name"], "dvsns_final_v")

    def test_closed_loop_each_criterion(self) -> None:
        cases = {
            "startup_not_released": {"det_final_v": 1.0},
            "startup_not_released ": {"i_mkfb_final_a": -1e-6},
            "loop_not_closed": {"sns1_final_v": 0.82},
            "fb_railed": {"fb_final_v": 0.01},
            "fb_railed ": {"fb_final_v": 3.29},
        }
        for crit, change in cases.items():
            with self.subTest(crit=crit):
                c = self.run_kind("closed-loop", {**LOOP_OK, **change})
                self.assertEqual(c["status"], "fail")
                self.assertEqual(c["diagnostics"][0]["message"], crit.strip())

    def test_no_settledness_term(self) -> None:
        # The closed-loop-startup* verdict is the 3-criteria form: vref drift is not graded.
        c = self.run_kind("closed-loop", {**LOOP_OK, "vref_final_v": 0.1})
        self.assertEqual(c["status"], "pass")

    def test_missing_verdict_operand_fails_never_passes(self) -> None:
        for kind, ok, drop in (("trip-point", TRIP_OK, "vtrip_v"), ("closed-loop", LOOP_OK, "i_mkfb_final_a"),
                               ("closed-loop", LOOP_OK, "sns2_final_v")):
            with self.subTest(kind=kind, drop=drop):
                c = self.run_kind(kind, {**ok, drop: None})
                self.assertEqual(c["status"], "fail")
                self.assertEqual(c["diagnostics"][0]["code"], "verdict_operands_missing")
                self.assertIn(drop, c["diagnostics"][0]["message"])

    def test_partial_failure_recounts_and_keeps_klt_grades(self) -> None:
        report = rep(
            corner(TRIP_OK, t=-40),
            corner({**TRIP_OK, "vtrip_v": 0.0}, t=27),
            corner(TRIP_OK, t=125, status="error"),
        )
        out = ck.enrich(report, "trip-point")
        self.assertEqual([c["status"] for c in out["corners"]], ["pass", "fail", "error"])
        self.assertEqual((out["passed"], out["failed"], out["errored"], out["corner_count"]), (1, 1, 1, 3))
        self.assertEqual(out["status"], "fail")
        self.assertNotIn("diagnostics", out["corners"][2])

    def test_core_open_loop_is_presence_graded_only(self) -> None:
        c = self.run_kind("core-open-loop", {"vref_v": 1.2})
        self.assertEqual(c["status"], "pass")
        self.assertEqual(c["measurements"], [{"name": "vref_v", "value": 1.2}])

    def test_unknown_kind_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            ck.enrich(rep(), "nope")


class BakedSupplyTests(TempDirCase):
    def test_pwl_supply_injected_for_pass_and_fail_corners(self) -> None:
        for status in ("pass", "fail"):
            with self.subTest(status=status):
                deck = self.write(f"{status}/deck.cir", "* d\nVvdd vdd 0 PWL(0 0 200u 3.63 2m 3.63)\n")
                c = {"corner_id": "typ/novdd/27C", "process": "typ", "temperature_c": 27, "status": status,
                     "artifacts": {"deck": str(deck)},
                     "measurements": [{"name": k, "value": v} for k, v in LOOP_OK.items()]}
                out = ck.enrich(rep(c), "closed-loop", cwd=self.tmp)["corners"][0]
                self.assertEqual(out["corner_id"], "typ/3.63V/27C")
                self.assertEqual(out["supply_v"], {"Vvdd": 3.63})
                self.assertEqual(kse.corner_id(out)[0], "typ_27c_3.63v")
                if status == "pass":
                    self.assertEqual(out["status"], "pass", out.get("diagnostics"))

    def test_pvt_enrich_behaviour_unchanged_by_the_refactor(self) -> None:
        deck = self.write("d/deck.cir", "Vvdd vdd 0 PWL(0 0 200u 3.3 3m 3.3)\n")
        c = {"corner_id": "typ/novdd/27C", "status": "pass", "artifacts": {"deck": str(deck)},
             "measurements": [{"name": k, "value": v} for k, v in
                              {"sns1_v": 0.7, "sns2_v": 0.695, "vref_2ms_v": 1.2, "vref_3ms_v": 1.2004,
                               "det_v": 0.1, "i_mkfb_a": 1e-9, "fb_v": 1.0}.items()]}
        out = epr.enrich({"status": "pass", "corners": [c]})["corners"][0]
        self.assertEqual(out["corner_id"], "typ/3.30V/27C")
        self.assertEqual(out["status"], "pass")


# --------------------------------------------------------------------------
# sanity gate
# --------------------------------------------------------------------------


class AnchorTests(unittest.TestCase):
    ANCHORS = [("vref_v", 1.2, 0.001), ("r1_ohm", 8.0e4, 100.0)]

    def report(self, **meas: float | None) -> dict:
        return {"status": "pass", "corners": [corner({"vref_v": 1.2, "r1_ohm": 8.0e4, **meas})]}

    def test_pass(self) -> None:
        self.assertEqual(ck.check_anchors(self.report(), self.ANCHORS), [])

    def test_off_anchor_fails(self) -> None:
        problems = ck.check_anchors(self.report(vref_v=1.21), self.ANCHORS)
        self.assertEqual(len(problems), 1)
        self.assertIn("vref_v", problems[0])

    def test_missing_measurement_fails(self) -> None:
        problems = ck.check_anchors(self.report(r1_ohm=None), self.ANCHORS)
        self.assertTrue(any("r1_ohm did not come back" in p for p in problems), problems)

    def test_non_pass_and_wrong_corner_count_fail(self) -> None:
        bad = self.report()
        bad["status"] = "fail"
        self.assertTrue(ck.check_anchors(bad, self.ANCHORS))
        two = {"status": "pass", "corners": [corner({"vref_v": 1.2}), corner({"vref_v": 1.2}, t=85)]}
        self.assertTrue(any("exactly one corner" in p for p in ck.check_anchors(two, self.ANCHORS)))

    def test_anchor_parsing(self) -> None:
        self.assertEqual(ck.parse_anchor("vref_v=1.2:0.001"), ("vref_v", 1.2, 0.001))
        with self.assertRaises(SystemExit):
            ck.parse_anchor("vref_v=1.2")

    def test_runner_anchors_equal_the_newest_legacy_records(self) -> None:
        for exp, row_key in (("sg13cmos5l-core-open-loop-bias", None), ("sg13cmos5l-startup-trip-point", None),
                             ("sg13cmos5l-closed-loop-startup", None), ("sg13cmos5l-closed-loop-startup-pex", None)):
            with self.subTest(exp=exp):
                text = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                anchors = re.findall(r'^\s*"(\w+)=([-0-9.e]+):([-0-9.e]+)"', text, re.M)
                self.assertTrue(anchors)
                latest = sorted((SIM_DIR / exp / "records").glob("*.csv"))[-1]
                with latest.open(encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
                row = next(r for r in rows if r["corner_label"] == "typ" and r["temp_c"] == "27"
                           and r["vdd_v"] == "3.30")
                for name, value, tol in anchors:
                    # the legacy CSV spells the columns differently only where
                    # the measurement was renamed (none are for these anchors,
                    # except the VEB naming which the anchors do not use)
                    legacy = float(row[name])
                    self.assertLessEqual(abs(legacy - float(value)), 1e-5 * max(1.0, abs(legacy)),
                                         f"{name}: legacy {legacy} vs anchor {value}")
                    self.assertGreater(float(tol), 0)


# --------------------------------------------------------------------------
# record shapes + provenance, through the real adapter
# --------------------------------------------------------------------------


class RecordTests(TempDirCase):
    def full_corner(self, exp: str, label: str, t: int, vdd: float, *, drop: str | None = None,
                    status: str = "pass") -> dict:
        names = [m["name"] for m in request(exp)["measurements"]]
        log = self.write(f"art/{label}-{t}-{vdd}.log", f"log {label} {t}\n")
        deck = self.write(f"art/{label}-{t}-{vdd}.cir", f"* deck {label}\nXM1 a b c d sg13_hv_pmos w=10u l=1u\n")
        return {"corner_id": f"{label}/{vdd:.3f}V/{t}C", "process": label, "temperature_c": t,
                "supply_v": {"Vvdd": vdd}, "status": status,
                "measurements": [{"name": n, "value": 1.0 + 0.1 * i} for i, n in enumerate(names) if n != drop],
                "artifacts": {"log": str(log), "deck": str(deck)}}

    def emit(self, exp: str, corners: list[dict], **kw) -> tuple[Path, tuple[int, int]]:
        experiment = self.tmp / "sim" / exp
        bad = any(c["status"] != "pass" for c in corners)
        report = {"status": "fail" if bad else "pass", "corners": corners}
        out = kse.emit(report, ck.augment_spec(spec(exp), kw.pop("msense_w", None)), experiment, self.tmp,
                       "20260101-000000-abc1234", store=FakeStore(), **kw)
        return experiment, out

    @staticmethod
    def read_rows(experiment: Path) -> list[dict]:
        with (experiment / "records/20260101-000000-abc1234.csv").open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_core_record_shape_and_provenance(self) -> None:
        exp = "sg13cmos5l-core-open-loop-bias"
        experiment, (passed, total) = self.emit(exp, [self.full_corner(exp, "typ", 27, 3.3),
                                                      self.full_corner(exp, "sf", 27, 3.3)])
        self.assertEqual((passed, total), (2, 2))
        rows = self.read_rows(experiment)
        self.assertEqual([r["corner_label"] for r in rows], ["typ", "sf"])
        sf = rows[1]
        self.assertEqual((sf["pnp_section"], sf["mos_section"], sf["res_section"]), ("typ", "mos_sf", "res_typ"))
        self.assertEqual((rows[0]["pnp_section"], rows[0]["mos_section"]), ("typ", "mos_tt"))
        md = (experiment / "records/20260101-000000-abc1234.md").read_text()
        for needle in ("**Experiment**: sg13cmos5l-core-open-loop-bias", "ihp-sg13cmos5l",
                       "sim/pdk-sg13cmos5l.json", "UNVERIFIED",
                       "sim/sg13cmos5l-core-open-loop-bias/testbench/sg13cmos5l_core_open_loop_bias.request.json.tmpl",
                       "issue #337", "2/2 points PASS", "NOT a claim against any ratified spec row"):
            self.assertIn(needle, md)
        self.assertNotIn("run_pvt_sweep.sh shell loop)", md.replace("(not a `run_pvt_sweep.sh` shell loop)", ""))
        manifest = json.loads((self.tmp / "manifests/artifacts" / f"{exp}-20260101-000000-abc1234.manifest.json").read_text())
        names = {e["name"] for e in manifest["entries"]}
        self.assertIn(f"sim/{exp}/netlist-snapshots/20260101-000000-abc1234/sf_27c_3.30v.spice", names)
        self.assertIn(f"sim/{exp}/corners/20260101-000000-abc1234/typ_27c_3.30v.log", names)
        self.assertFalse((experiment / "corners").exists())
        self.assertFalse((experiment / "netlist-snapshots").exists())

    def test_missing_required_measurement_is_a_fail_row(self) -> None:
        exp = "sg13cmos5l-core-open-loop-bias"
        experiment, (passed, total) = self.emit(exp, [self.full_corner(exp, "typ", 27, 3.3),
                                                      self.full_corner(exp, "bcs", 27, 3.3, drop="i_leg2_a")])
        self.assertEqual((passed, total), (1, 2))
        csv_text = (experiment / "records/20260101-000000-abc1234.csv").read_text()
        bad = next(l for l in csv_text.splitlines() if l.startswith("bcs,"))
        self.assertIn(",FAIL,", bad)
        self.assertIn("**Failed points**: bcs_27c_3.30v",
                      (experiment / "records/20260101-000000-abc1234.md").read_text())

    def test_klt_failed_corner_is_a_fail_row_even_with_all_measurements(self) -> None:
        exp = "sg13cmos5l-startup-trip-point"
        experiment, (passed, total) = self.emit(exp, [self.full_corner(exp, "typ", 27, 3.3),
                                                      self.full_corner(exp, "wcs", 125, 3.63, status="fail")])
        self.assertEqual((passed, total), (1, 2))
        text = (experiment / "records/20260101-000000-abc1234.csv").read_text()
        self.assertTrue(next(l for l in text.splitlines() if l.startswith("wcs,")).split(",")[4] == "3.63")
        self.assertIn("wcs_125c_3.63v", (experiment / "records/20260101-000000-abc1234.md").read_text())
        self.assertEqual(text.splitlines()[0].split(",")[:3], ["corner_label", "mos_section", "res_section"])

    def test_closed_loop_msense_column_is_recorded(self) -> None:
        exp = "sg13cmos5l-closed-loop-startup"
        experiment, _ = self.emit(exp, [self.full_corner(exp, "typ", 27, 3.3)], msense_w="10u")
        rows = self.read_rows(experiment)
        self.assertEqual(rows[0]["msense_w"], "10u")

    def test_pex_record_refuses_to_publish_unbound(self) -> None:
        exp = "sg13cmos5l-closed-loop-startup-pex"
        with self.assertRaises(SystemExit) as ctx:
            self.emit(exp, [self.full_corner(exp, "typ", 27, 3.3)])
        self.assertIn("unbound PEX record", str(ctx.exception))
        self.assertFalse((self.tmp / "sim" / exp).exists())

    def test_incomplete_batch_grid_is_refused_by_the_adapter(self) -> None:
        exp = "sg13cmos5l-core-open-loop-bias"
        report = {"status": "pass", "corners": [self.full_corner(exp, "typ", 27, 3.3)],
                  "grid": {"expected": ["typ_27c_3.30v", "bcs_27c_3.30v"], "complete": True}}
        with self.assertRaises(SystemExit) as ctx:
            kse.emit(report, spec(exp), self.tmp / "sim" / exp, self.tmp, "rid-x", store=FakeStore())
        self.assertIn("missing", str(ctx.exception))

    def test_augment_spec_does_not_mutate_the_committed_spec(self) -> None:
        s = spec("sg13cmos5l-closed-loop-startup")
        out = ck.augment_spec(s, "10u")
        self.assertIn("msense_w", out["extra_columns"])
        self.assertNotIn("msense_w", s["extra_columns"])
        self.assertEqual(ck.augment_spec(s, None), s)


# --------------------------------------------------------------------------
# runners: fail-closed behaviour (no klt call, no simulation)
# --------------------------------------------------------------------------


class RunnerTests(TempDirCase):
    def run_runner(self, exp: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        base = {"PATH": os.environ["PATH"], "HOME": str(self.tmp)}
        base.update(env or {})
        return subprocess.run(["bash", str(SIM_DIR / exp / "run_klt_sim.sh"), *args],
                              capture_output=True, text=True, env=base, timeout=60, check=False)

    def fake_pdk(self) -> Path:
        root = self.tmp / "pdk"
        models = root / "ihp-sg13cmos5l" / "libs.tech" / "ngspice" / "models"
        osdi = root / "ihp-sg13cmos5l" / "libs.tech" / "ngspice" / "osdi"
        osdi.mkdir(parents=True)
        (osdi / "psp103.osdi").write_text("")
        models.mkdir(parents=True)
        sections = {"cornerPNP.lib": ["typ", "bcs", "wcs"],
                    "cornerMOShv.lib": ["mos_tt", "mos_ff", "mos_ss", "mos_sf", "mos_fs"],
                    "cornerRES.lib": ["res_typ", "res_bcs", "res_wcs"]}
        for name, names in sections.items():
            (models / name).write_text("".join(f".LIB {s}\n.ENDL {s}\n" for s in names))
        return root

    def fake_klt(self) -> Path:
        marker = self.tmp / "klt-was-called"
        klt = self.tmp / "klt"
        klt.write_text(f"#!/usr/bin/env bash\n[[ \"$1\" == --version ]] && {{ echo klt-fake; exit 0; }}\ntouch {marker}\nexit 99\n")
        klt.chmod(0o755)
        return klt

    def test_usage_error(self) -> None:
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                for args in ((), ("--nope",)):
                    r = self.run_runner(exp, *args)
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIn("usage", r.stderr)

    def test_batch_refuses_without_the_provisioning_acknowledgement(self) -> None:
        pdk, klt = self.fake_pdk(), self.fake_klt()
        for exp in EXPERIMENTS:
            with self.subTest(exp=exp):
                r = self.run_runner(exp, "--batch", env={
                    "KLT_SIM_KLT": str(klt), "PDK_ROOT": str(pdk), "KLT_SIM_WORK": str(self.tmp / f"w-{exp}"),
                    "KLT_BATCH_PROVISION_SCRIPT": str(self.tmp / "absent.sh")})
                self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
                self.assertIn("refusing --batch", r.stderr)
                self.assertIn("NO", r.stderr)
                self.assertFalse((self.tmp / "klt-was-called").exists())
                self.assertFalse((self.tmp / f"w-{exp}" / "request.json").exists())

    def test_missing_klt_and_missing_pdk_are_refused(self) -> None:
        exp = "sg13cmos5l-startup-trip-point"
        r = self.run_runner(exp, "--sanity", env={"KLT_SIM_KLT": str(self.tmp / "no-such-klt")})
        self.assertEqual(r.returncode, 3)
        r = self.run_runner(exp, "--sanity", env={"KLT_SIM_KLT": str(self.fake_klt()),
                                                  "PDK_ROOT": str(self.tmp / "empty")})
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.tmp / "klt-was-called").exists())

    def test_record_needs_a_work_dir(self) -> None:
        exp = "sg13cmos5l-core-open-loop-bias"
        r = self.run_runner(exp, "--record", env={"KLT_SIM_KLT": str(self.fake_klt()),
                                                  "PDK_ROOT": str(self.fake_pdk())})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("KLT_SIM_WORK", r.stderr)

    def test_runners_declare_the_experiment_consistently(self) -> None:
        for exp, (stem, kind, fam, *_r) in EXPERIMENTS.items():
            with self.subTest(exp=exp):
                text = (SIM_DIR / exp / "run_klt_sim.sh").read_text()
                self.assertIn(f'EXP="{exp}"', text)
                self.assertIn(f'STEM="{stem}"', text)
                self.assertIn(f'KIND="{kind}"', text)
                self.assertIn(f'FAMILIES="{fam}"', text)
                self.assertTrue(os.access(SIM_DIR / exp / "run_klt_sim.sh", os.X_OK))
                # no hand-launched grid on the dispatch host
                for banned in ("ngspice -b", "xargs -P", "parallel", "nohup", "setsid"):
                    self.assertNotIn(banned, text)
        runner = (SIM_DIR / "harness" / "cmos5l_runner.sh").read_text()
        for banned in ("ngspice -b", "xargs -P", "nohup", "setsid"):
            self.assertNotIn(banned, runner)
        self.assertIn("--backend local", runner)       # the sanity corner only
        self.assertEqual(runner.count("--backend local"), 1)


if __name__ == "__main__":
    unittest.main()
