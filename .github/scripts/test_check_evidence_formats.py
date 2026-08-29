#!/usr/bin/env python3
"""Self-test for `check_evidence_formats.py`.

    python3 .github/scripts/test_check_evidence_formats.py

A format checker that never fails is indistinguishable from no checker at all,
so each case below builds a synthetic evidence tree in a temp directory,
introduces exactly one defect, and asserts the checker rejects it with a
specific message. Case 0 asserts the undamaged tree passes, so the failures are
attributable to the injected defect rather than to the fixture.

Black-box on purpose: the checker is invoked as a subprocess, the same way CI
and a human run it. Stdlib only, no PDK, no network.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_evidence_formats.py"

RECORD_ID = "20260101-000000-abcdef1"
CORNERS = ("typ_27c_3.30v", "wcs_125c_3.63v")

RECORD_MD = """# Record {rid}

- **Experiment**: synthetic-experiment (self-test fixture)
- **Claim**: the fixture claim under test.
- **Netlist provenance**: `design/netlist/synthetic.spice` at git sha `0000000`.
- **PDK**: `ihp-sg13g2` — pinned release: see `sim/pdk.json`.
- **ngspice**: `** ngspice-46 : Circuit level simulation program`
- **Corner matrix run**: process {{typ, wcs}} x temperature {{27, 125}} C.
- **Result**: {passed}/{total} points PASS (fixture criteria).
- **Links**:
  - Per-point raw ngspice logs: `corners/{rid}/`
- **Timestamp / author**: 2026-01-01T00:00:00Z, self-test fixture.
"""

RECORD_CSV = """corner_label,temp_c,vdd_v,status,vref_v
typ,27,3.30,{status_a},1.240000e+00
wcs,125,3.63,{status_b},1.235000e+00
"""

#: The committed schematic DUT the record above names as its own provenance.
DUT_NETLIST = """* synthetic DUT
.subckt synthetic vdd vss out
XM1 out bias vdd vdd sg13_hv_pmos w=10u l=1u ng=1 m=1
XR1 out cb sub! rppd w=2u l=511u m=1 b=0
.ends
.end
"""

#: A per-point netlist snapshot carrying that DUT. Deliberately unlike the DUT
#: file in two ways the freshness check must tolerate: the DUT's ports are
#: rewired to the fixture's own nets, and the PMOS carries extra geometry
#: parameters (as a PEX-sourced device would). Neither is a design change.
SNAPSHOT = """* per-point netlist snapshot
XM1 outx biasx vdd vdd sg13_hv_pmos w=10u l=1u ng=1 m=1 as=4p ad=4p
XR1 outx cbx sub! rppd w=2u l=511u m=1 b=0
Vsupply vdd 0 3.3
.tran 1n 1u
.end
"""

SIM_WAIVER_FILE = "sim/evidence-freshness-waivers.json"
SIM_RECORD_REL = f"sim/synthetic-experiment/records/{RECORD_ID}.md"
SIM_DUT_REL = "design/netlist/synthetic.spice"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_fixture(root: Path) -> None:
    """Write a minimal but fully valid evidence tree."""
    sim = root / "sim"
    (sim).mkdir(parents=True)
    (sim / "pdk.json").write_text(
        json.dumps({"source": "IHP-GmbH/IHP-Open-PDK", "release_tag": "v0.3.0",
                    "tarball_sha256": "0" * 64}),
        encoding="utf-8",
    )

    experiment = sim / "synthetic-experiment"
    (experiment / "testbench").mkdir(parents=True)
    (experiment / "README.md").write_text("# synthetic-experiment\n", encoding="utf-8")
    (experiment / "run_pvt_sweep.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (experiment / "testbench" / "tb_synthetic.spice.tmpl").write_text("* tb\n", encoding="utf-8")

    (experiment / "records").mkdir()
    (experiment / "records" / f"{RECORD_ID}.md").write_text(
        RECORD_MD.format(rid=RECORD_ID, passed=2, total=2), encoding="utf-8"
    )
    (experiment / "records" / f"{RECORD_ID}.csv").write_text(
        RECORD_CSV.format(status_a="PASS", status_b="PASS"), encoding="utf-8"
    )
    dut = root / "design" / "netlist"
    dut.mkdir(parents=True)
    (dut / "synthetic.spice").write_text(DUT_NETLIST, encoding="utf-8")

    for kind, suffix, body in (
        ("netlist-snapshots", ".spice", SNAPSHOT),
        ("corners", ".log", "ngspice output\n"),
    ):
        directory = experiment / kind / RECORD_ID
        directory.mkdir(parents=True)
        for corner in CORNERS:
            (directory / f"{corner}{suffix}").write_text(body, encoding="utf-8")

    cell = root / "layout" / "synth_cell"
    cell.mkdir(parents=True)
    gds_bytes = b"not really a gds, but it hashes just fine\n"
    (cell / "synth_cell.gds").write_bytes(gds_bytes)
    reference_bytes = b".SUBCKT synth_cell\n.ENDS\n"
    (cell / "synth_cell.lvs_reference.spice").write_bytes(reference_bytes)

    deck = {"name": "sg13g2", "content_hash": "sha256:" + "a" * 64, "released": False}
    (cell / "drc_report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "file": "layout/synth_cell/synth_cell.gds",
            "deck": "sg13g2",
            "status": "clean",
            "violation_count": 0,
            "violations": [],
            "coverage": {"rules_skipped": [], "layers_checked": []},
            "provenance": {"klt_version": "0.3.0", "klayout_version": "0.30.10",
                           "deck": deck,
                           "input": {"content_hash": "sha256:" + sha256_bytes(gds_bytes)}},
        }, indent=1),
        encoding="utf-8",
    )
    (cell / "lvs_report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "engine": "klayout",
            "layout": "synth_cell.gds",
            "reference": "synth_cell.lvs_reference.spice",
            "status": "mismatch",
            "mismatch_count": 3,
            "counts": {"nets": {"matched": 0}, "devices": {"matched": 0}, "pins": {"matched": 0}},
            "environment": {"engine": "klayout",
                            "layout_sha256": sha256_bytes(gds_bytes),
                            "reference_sha256": sha256_bytes(reference_bytes)},
            "provenance": {"klt_version": "0.3.0", "deck": deck},
        }, indent=1),
        encoding="utf-8",
    )

    # extract_report.json (plain klt extract) and pex_extract_report.json
    # (parasitic extract) share the same status vocabulary and freshness
    # checks in check_evidence_formats.py — cover both report kinds here.
    plain_netlist_bytes = b".SUBCKT synth_cell\n.ENDS\n"
    (cell / "synth_cell.spice").write_bytes(plain_netlist_bytes)
    (cell / "extract_report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "netlist_path": "synth_cell.spice",
            "netlist_sha256": sha256_bytes(plain_netlist_bytes),
            "status": "extracted",
            "provenance": {"klt_version": "0.3.0", "deck": deck,
                           "input": {"content_hash": "sha256:" + sha256_bytes(gds_bytes)}},
        }, indent=1),
        encoding="utf-8",
    )

    pex_netlist_bytes = b".SUBCKT synth_cell\n* pex\n.ENDS\n"
    (cell / "synth_cell.pex.spice").write_bytes(pex_netlist_bytes)
    (cell / "pex_extract_report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "netlist_path": "synth_cell.pex.spice",
            "netlist_sha256": sha256_bytes(pex_netlist_bytes),
            "status": "extracted",
            "provenance": {"klt_version": "0.3.0", "deck": deck,
                           "input": {"content_hash": "sha256:" + sha256_bytes(gds_bytes)}},
        }, indent=1),
        encoding="utf-8",
    )


def run_checker(root: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--skip-append-only", *extra],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def edit_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


# --- cases -------------------------------------------------------------------
#
# Each case mutates the fixture in place and returns the substring the checker's
# output must contain. A case returning None must leave the checker passing.


def case_valid(_root: Path):
    return None


def case_result_overclaims_total(root: Path):
    record = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.md"
    record.write_text(RECORD_MD.format(rid=RECORD_ID, passed=45, total=45), encoding="utf-8")
    return "claims 45 points but"


def case_result_overclaims_passes(root: Path):
    csv_path = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.csv"
    csv_path.write_text(RECORD_CSV.format(status_a="PASS", status_b="FAIL"), encoding="utf-8")
    return "claims 2 PASS but"


def case_missing_required_field(root: Path):
    record = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.md"
    text = record.read_text(encoding="utf-8")
    record.write_text(
        "\n".join(line for line in text.splitlines() if not line.startswith("- **ngspice**")),
        encoding="utf-8",
    )
    return "missing required field '- **ngspice**:'"


def case_no_provenance_field(root: Path):
    record = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.md"
    text = record.read_text(encoding="utf-8")
    record.write_text(
        "\n".join(line for line in text.splitlines()
                  if not line.startswith("- **Netlist provenance**")),
        encoding="utf-8",
    )
    return "no netlist-provenance field"


def case_dropped_log(root: Path):
    (root / "sim/synthetic-experiment/corners" / RECORD_ID / f"{CORNERS[1]}.log").unlink()
    return "disagree on PVT points"


def case_bad_corner_id(root: Path):
    logs = root / "sim/synthetic-experiment/corners" / RECORD_ID
    (logs / f"{CORNERS[0]}.log").rename(logs / "not-a-corner-id.log")
    return "corner id does not parse"


def case_heading_mismatch(root: Path):
    record = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.md"
    text = record.read_text(encoding="utf-8").replace(f"# Record {RECORD_ID}", "# Record")
    record.write_text(text, encoding="utf-8")
    return "expected '# Record"


def case_missing_csv(root: Path):
    (root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.csv").unlink()
    return "no machine-readable sibling"


def case_missing_run_script(root: Path):
    (root / "sim/synthetic-experiment/run_pvt_sweep.sh").unlink()
    return "no run_*.sh cold-start entry point"


def case_stale_drc_input(root: Path):
    gds = root / "layout/synth_cell/synth_cell.gds"
    gds.write_bytes(gds.read_bytes() + b"one more polygon\n")
    return "STALE"


def case_stale_lvs_reference(root: Path):
    reference = root / "layout/synth_cell/synth_cell.lvs_reference.spice"
    reference.write_bytes(reference.read_bytes() + b"* edited\n")
    return "lvs_report.json [reference netlist]"


def case_drc_status_contradiction(root: Path):
    edit_json(root / "layout/synth_cell/drc_report.json",
              lambda d: d.update(violation_count=7))
    return "contradicts violation_count 7"


def case_lvs_status_contradiction(root: Path):
    edit_json(root / "layout/synth_cell/lvs_report.json",
              lambda d: d.update(status="match"))
    return "contradicts mismatch_count 3"


def case_missing_coverage(root: Path):
    edit_json(root / "layout/synth_cell/drc_report.json", lambda d: d.pop("coverage"))
    return "coverage gaps must be enumerated"


def case_unhashed_deck(root: Path):
    edit_json(root / "layout/synth_cell/drc_report.json",
              lambda d: d["provenance"]["deck"].update(content_hash="the current one"))
    return "content_hash' is not a sha256 digest"


def case_extract_report_bad_status(root: Path):
    edit_json(root / "layout/synth_cell/extract_report.json",
              lambda d: d.update(status="bogus"))
    return "status 'bogus' not in"


def case_extract_report_missing_netlist_path(root: Path):
    edit_json(root / "layout/synth_cell/extract_report.json",
              lambda d: d.pop("netlist_path"))
    return "missing 'netlist_path'"


def case_extract_report_stale_netlist(root: Path):
    netlist = root / "layout/synth_cell/synth_cell.spice"
    netlist.write_bytes(netlist.read_bytes() + b"* edited\n")
    return "extract_report.json [extracted netlist]"


def case_pex_extract_report_bad_status(root: Path):
    edit_json(root / "layout/synth_cell/pex_extract_report.json",
              lambda d: d.update(status="bogus"))
    return "status 'bogus' not in"


def case_pex_extract_report_missing_netlist_path(root: Path):
    edit_json(root / "layout/synth_cell/pex_extract_report.json",
              lambda d: d.pop("netlist_path"))
    return "missing 'netlist_path'"


def case_pex_extract_report_stale_netlist(root: Path):
    netlist = root / "layout/synth_cell/synth_cell.pex.spice"
    netlist.write_bytes(netlist.read_bytes() + b"* edited\n")
    return "pex_extract_report.json [extracted netlist]"


def case_waiver_without_issue(root: Path):
    case_stale_drc_input(root)
    (root / "layout/evidence-freshness-waivers.json").write_text(
        json.dumps({"waivers": [{
            "report": "layout/synth_cell/drc_report.json",
            "check": "input gds",
            "recorded_hash": "sha256:" + "b" * 64,
            "reason": "because I said so",
        }]}),
        encoding="utf-8",
    )
    return "missing required key(s): issue"


def case_waiver_silences_only_its_own_check(root: Path):
    """A waiver for the DRC input must not silence a stale LVS reference."""
    drc = json.loads((root / "layout/synth_cell/drc_report.json").read_text(encoding="utf-8"))
    case_stale_lvs_reference(root)
    (root / "layout/evidence-freshness-waivers.json").write_text(
        json.dumps({"waivers": [{
            "report": "layout/synth_cell/drc_report.json",
            "check": "input gds",
            "recorded_hash": drc["provenance"]["input"]["content_hash"],
            "issue": "#56",
            "reason": "unrelated waiver",
        }]}),
        encoding="utf-8",
    )
    return "lvs_report.json [reference netlist]"


def case_obsolete_waiver_self_expires(root: Path):
    """A waiver left behind after the evidence went fresh again is a failure."""
    drc = json.loads((root / "layout/synth_cell/drc_report.json").read_text(encoding="utf-8"))
    (root / "layout/evidence-freshness-waivers.json").write_text(
        json.dumps({"waivers": [{
            "report": "layout/synth_cell/drc_report.json",
            "check": "input gds",
            "recorded_hash": drc["provenance"]["input"]["content_hash"],
            "issue": "#56",
            "reason": "stale once, fresh now",
        }]}),
        encoding="utf-8",
    )
    return "waiver is obsolete"


def case_waiver_guards_nothing(root: Path):
    (root / "layout/evidence-freshness-waivers.json").write_text(
        json.dumps({"waivers": [{
            "report": "layout/no_such_cell/drc_report.json",
            "check": "input gds",
            "recorded_hash": "sha256:" + "c" * 64,
            "issue": "#56",
            "reason": "points at nothing",
        }]}),
        encoding="utf-8",
    )
    return "waiver matches no report/check"


def case_valid_waiver_passes(root: Path):
    """The whole point of the waiver: loud notes, exit 0.

    Editing the GDS invalidates *every* report that names it as its input, so
    each such check has to be waived by name — which is the property being
    demonstrated.
    """
    drc = json.loads((root / "layout/synth_cell/drc_report.json").read_text(encoding="utf-8"))
    lvs = json.loads((root / "layout/synth_cell/lvs_report.json").read_text(encoding="utf-8"))
    extract = json.loads(
        (root / "layout/synth_cell/extract_report.json").read_text(encoding="utf-8"))
    pex = json.loads(
        (root / "layout/synth_cell/pex_extract_report.json").read_text(encoding="utf-8"))
    case_stale_drc_input(root)
    (root / "layout/evidence-freshness-waivers.json").write_text(
        json.dumps({"waivers": [
            {
                "report": "layout/synth_cell/drc_report.json",
                "check": "input gds",
                "recorded_hash": drc["provenance"]["input"]["content_hash"],
                "issue": "#56",
                "reason": "tracked follow-up",
            },
            {
                "report": "layout/synth_cell/lvs_report.json",
                "check": "layout",
                "recorded_hash": lvs["environment"]["layout_sha256"],
                "issue": "#56",
                "reason": "tracked follow-up",
            },
            {
                "report": "layout/synth_cell/extract_report.json",
                "check": "input gds",
                "recorded_hash": extract["provenance"]["input"]["content_hash"],
                "issue": "#56",
                "reason": "tracked follow-up",
            },
            {
                "report": "layout/synth_cell/pex_extract_report.json",
                "check": "input gds",
                "recorded_hash": pex["provenance"]["input"]["content_hash"],
                "issue": "#56",
                "reason": "tracked follow-up",
            },
        ]}),
        encoding="utf-8",
    )
    return None


def _resize_dut(root: Path) -> None:
    """Retune the committed DUT the way #134 retuned R1, leaving the record behind."""
    dut = root / SIM_DUT_REL
    dut.write_text(dut.read_text(encoding="utf-8").replace("l=511u", "l=694.5u"),
                   encoding="utf-8")


def _write_sim_waiver(root: Path, **overrides) -> None:
    entry = {
        "report": SIM_RECORD_REL,
        "check": SIM_DUT_REL,
        "recorded_hash": "sha256:" + sim_signature_digest(root),
        "issue": "#141",
        "reason": "tracked re-run",
    }
    entry.update(overrides)
    (root / SIM_WAIVER_FILE).write_text(json.dumps({"waivers": [entry]}), encoding="utf-8")


def sim_signature_digest(root: Path) -> str:
    """The digest the checker will report for the fixture's snapshot signature.

    Imported from the checker rather than recomputed here on purpose: a waiver
    entry has to carry the exact digest the checker derives, and duplicating the
    signature grammar in the test would let the two drift apart silently.
    """
    sys.path.insert(0, str(CHECKER.parent))
    import check_evidence_formats as checker  # noqa: PLC0415

    dut = checker.spice_instances((root / SIM_DUT_REL).read_text(encoding="utf-8"))
    snapshot = checker.spice_instances(
        (root / "sim/synthetic-experiment/netlist-snapshots" / RECORD_ID
         / f"{CORNERS[0]}.spice").read_text(encoding="utf-8")
    )
    return checker.sha256_text(checker.dut_signature(dut, snapshot))


def case_stale_dut_resize(root: Path):
    """The record's snapshots must still match the committed DUT's sizing."""
    _resize_dut(root)
    return f"{SIM_RECORD_REL} [{SIM_DUT_REL}]"


def case_dut_device_dropped(root: Path):
    """A DUT device missing from the snapshots is a design change, not rewiring."""
    snapshots = root / "sim/synthetic-experiment/netlist-snapshots" / RECORD_ID
    for corner in CORNERS:
        path = snapshots / f"{corner}.spice"
        path.write_text(
            "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                      if not line.startswith("XR1")) + "\n",
            encoding="utf-8",
        )
    return "STALE"


def case_snapshots_disagree_on_dut(root: Path):
    """One record cannot have simulated two different designs."""
    path = (root / "sim/synthetic-experiment/netlist-snapshots" / RECORD_ID
            / f"{CORNERS[1]}.spice")
    path.write_text(path.read_text(encoding="utf-8").replace("l=511u", "l=694.5u"),
                    encoding="utf-8")
    return "snapshots disagree on the DUT's own devices"


def case_sim_waiver_without_issue(root: Path):
    _resize_dut(root)
    _write_sim_waiver(root, issue="")
    return "missing required key(s): issue"


def case_obsolete_sim_waiver_self_expires(root: Path):
    """A waiver left behind after the record went fresh again is a failure."""
    _write_sim_waiver(root)
    return "waiver is obsolete"


def case_valid_sim_waiver_passes(root: Path):
    """The whole point of the sim waiver: a loud note, exit 0."""
    _write_sim_waiver(root)
    _resize_dut(root)
    return None


CASES = [
    ("undamaged fixture passes", case_valid),
    ("Result headline overclaims point count", case_result_overclaims_total),
    ("Result headline overclaims PASS count", case_result_overclaims_passes),
    ("record drops a required field", case_missing_required_field),
    ("record has no netlist-provenance field", case_no_provenance_field),
    ("a per-point log goes missing", case_dropped_log),
    ("a log filename breaks the corner-id grammar", case_bad_corner_id),
    ("record heading disagrees with its filename", case_heading_mismatch),
    ("record has no machine-readable CSV", case_missing_csv),
    ("experiment ships no cold-start run script", case_missing_run_script),
    ("DRC report is stale vs the committed GDS", case_stale_drc_input),
    ("LVS reference netlist edited after the run", case_stale_lvs_reference),
    ("DRC status contradicts its own violation count", case_drc_status_contradiction),
    ("LVS status contradicts its own mismatch count", case_lvs_status_contradiction),
    ("DRC report drops its coverage-gap enumeration", case_missing_coverage),
    ("deck is not identified by content hash", case_unhashed_deck),
    ("extract_report.json rejects a status outside the vocabulary",
     case_extract_report_bad_status),
    ("extract_report.json rejects a missing netlist_path", case_extract_report_missing_netlist_path),
    ("extract_report.json rejects a netlist edited after extraction",
     case_extract_report_stale_netlist),
    ("pex_extract_report.json rejects a status outside the vocabulary",
     case_pex_extract_report_bad_status),
    ("pex_extract_report.json rejects a missing netlist_path",
     case_pex_extract_report_missing_netlist_path),
    ("pex_extract_report.json rejects a netlist edited after extraction",
     case_pex_extract_report_stale_netlist),
    ("waiver without a tracking issue is rejected", case_waiver_without_issue),
    ("waiver silences only its own check", case_waiver_silences_only_its_own_check),
    ("obsolete waiver self-expires", case_obsolete_waiver_self_expires),
    ("waiver that guards nothing is rejected", case_waiver_guards_nothing),
    ("valid waiver downgrades a stale report to a note", case_valid_waiver_passes),
    ("record is stale after the committed DUT is resized", case_stale_dut_resize),
    ("a DUT device vanishes from the netlist snapshots", case_dut_device_dropped),
    ("per-point snapshots disagree on the DUT", case_snapshots_disagree_on_dut),
    ("sim waiver without a tracking issue is rejected", case_sim_waiver_without_issue),
    ("obsolete sim waiver self-expires", case_obsolete_sim_waiver_self_expires),
    ("valid sim waiver downgrades a stale record to a note", case_valid_sim_waiver_passes),
]


def test_append_only(tmp: Path) -> str | None:
    """Editing a committed record must fail against the merge base."""
    root = tmp / "append-only"
    root.mkdir()
    build_fixture(root)

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "selftest@example.invalid")
    git("config", "user.name", "self test")
    git("add", "-A")
    git("commit", "-qm", "fixture")

    record = root / "sim/synthetic-experiment/records" / f"{RECORD_ID}.csv"
    record.write_text(RECORD_CSV.format(status_a="PASS", status_b="PASS") + "typ,27,3.30,PASS,9\n",
                      encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "edit committed evidence")

    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root),
         "--base-ref", "main~1", "--require-append-only"],
        capture_output=True, text=True, check=False,
    )
    output = proc.stdout + proc.stderr
    if proc.returncode == 0:
        return f"expected non-zero exit, got 0\n{output}"
    if "append-only" not in output:
        return f"expected an append-only complaint, got:\n{output}"
    return None


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for index, (name, mutate) in enumerate(CASES):
            root = tmp / f"case{index:02d}"
            root.mkdir()
            build_fixture(root)
            expected = mutate(root)
            code, output = run_checker(root)
            if expected is None:
                ok = code == 0
                detail = "expected exit 0"
            else:
                ok = code != 0 and expected in output
                detail = f"expected non-zero exit and {expected!r} in output"
            if ok:
                print(f"  ok   {name}")
            else:
                failures += 1
                print(f"  FAIL {name}: {detail}\n{output}")
            shutil.rmtree(root)

        problem = test_append_only(tmp)
        if problem is None:
            print("  ok   editing committed evidence trips the append-only check")
        else:
            failures += 1
            print(f"  FAIL editing committed evidence trips the append-only check: {problem}")

    total = len(CASES) + 1
    if failures:
        print(f"\n{failures}/{total} self-test case(s) FAILED", file=sys.stderr)
        return 1
    print(f"\nOK: {total}/{total} self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
