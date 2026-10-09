#!/usr/bin/env python3
"""Self-test for `check_report_dependencies.py`.

    python3 .github/scripts/test_check_report_dependencies.py

Same discipline as `test_check_signoff_manifest.py`: a checker that never
fails is indistinguishable from no checker at all. Each case builds a
synthetic repository in a temp directory — a block manifest citing an item-8
envelope, the report it pins, a dependency inventory, a spec table, decision
records, DUT netlists, `sim/` experiments and a waiver file — introduces
exactly one defect (or one change that must NOT fail) and asserts the
verdict and a specific message. Case 0 asserts the undamaged tree passes, so
each failure is attributable to the injected defect rather than the fixture.

Black-box on purpose: the checker runs as a subprocess, as CI runs it. Only
the spec-table digest helper is imported, to write the fixture's inventory;
the reflow and unrelated-edit cases check that helper's normalisation from
the outside. Stdlib only, no PDK, no simulator, no network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_report_dependencies.py"

_spec = importlib.util.spec_from_file_location("_crd", CHECKER)
_crd = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(CHECKER.parent))
_spec.loader.exec_module(_crd)

REPORT_DIR = "measurements/2026-10-report"
OLD_REPORT_DIR = "measurements/2026-09-report"
CUR = "20261001-000000-aaaaaaa"
STALE = "20260901-000000-bbbbbbb"
IQ_REC = "20261002-000000-fffffff"

TOP_README = """# fixture block

Intro prose.

## Target specification (RATIFIED)

| Parameter | Target | Stretch |
|---|---|---|
| Output reference | 1.050 V | — |
| Iq | < 50 µA | < 20 µA |

## Other section

More prose.
"""

REPORT = f"""# Characterization report

| Row | Record | Fresh? |
|---|---|---|
| Output reference | `sim/vref-pvt/records/{CUR}.csv` | **Current** |
| Output reference, untrimmed | `sim/vref-mc/records/{STALE}.csv` | **Predates the current
netlist** (waived, #273) |
| Iq | `sim/iq/records/{IQ_REC}.csv` | Current |
"""

DR_TEXT = "# 0007: Ratification\n\n- **Status**: ratified\n- **Date**: 2026-09-15\n"


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write(t: Path, rel: str, data: str | bytes) -> None:
    path = t / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def fhash(t: Path, rel: str) -> str:
    return sha((t / rel).read_bytes())


def add_record(t: Path, slug: str, rid: str) -> list[str]:
    md = f"sim/{slug}/records/{rid}.md"
    csv = f"sim/{slug}/records/{rid}.csv"
    write(t, md, f"# {slug} {rid}\n\nNetlist provenance: design/netlist/core.spice\n")
    write(t, csv, "corner_label,status\ntyp,PASS\n")
    return [md, csv]


def inventory(t: Path, **override) -> dict:
    exps = []
    for slug, rid, rows, fresh in (("vref-pvt", CUR, ["Output reference"], "current"),
                                   ("vref-mc", STALE, ["Output reference"], "stale"),
                                   ("iq", IQ_REC, ["Iq"], "current")):
        files = {r: fhash(t, r) for r in (f"sim/{slug}/records/{rid}.md",
                                          f"sim/{slug}/records/{rid}.csv")}
        e = {"path": f"sim/{slug}", "spec_rows": rows, "selected_record": rid,
             "freshness": fresh, "files": files}
        if fresh == "current":
            e["dut"] = ["design/netlist/core.spice"]
        else:
            e["disclosure"] = "predates the current netlist"
            e["waiver_issue"] = "#273"
        exps.append(e)
    inv = {
        "schema_version": 1,
        "report": f"{REPORT_DIR}/README.md",
        "report_sha256": fhash(t, f"{REPORT_DIR}/README.md"),
        "dut": [{"path": "design/netlist/core.spice",
                 "sha256": fhash(t, "design/netlist/core.spice")}],
        "spec": {
            "table": {"source": "README.md", "heading": "## Target specification",
                      "rows": _crd.spec_table_rows(TOP_README, "## Target specification")},
            "decision_records": [{"path": "spec/decision-records/0007-ratify.md",
                                  "status": "ratified"}],
            "absent": ["spec/decision-records/0012-*.md"],
        },
        "experiments": exps,
    }
    inv.update(override)
    return inv


def envelope(report_hash: str) -> dict:
    return {"schema_version": 1, "kind": "generic", "status": "pass", "t1_item": 8,
            "source": "README.md",
            "provenance": {"input": {"content_hash": report_hash, "path": "README.md"}}}


def build_fixture(t: Path, *, cite: bool = True) -> None:
    write(t, "README.md", TOP_README)
    write(t, "spec/decision-records/0007-ratify.md", DR_TEXT)
    write(t, "design/netlist/core.spice", ".subckt core a b\nR1 a b 511\n.ends\n")
    write(t, "design/README.md", "# design\n")
    for slug, rid in (("vref-pvt", CUR), ("vref-mc", STALE), ("iq", IQ_REC),
                      ("unrelated", CUR)):
        add_record(t, slug, rid)
    # Older history in an experiment: must not matter, the newest is selected.
    add_record(t, "vref-pvt", "20260801-000000-ccccccc")
    write(t, "sim/evidence-freshness-waivers.json", json.dumps({"waivers": [{
        "report": f"sim/vref-mc/records/{STALE}.md",
        "check": "design/netlist/core.spice",
        "recorded_hash": "sha256:" + "0" * 64, "issue": "#273", "reason": "pre-trim",
    }]}))
    write(t, f"{REPORT_DIR}/README.md", REPORT)
    report_hash = fhash(t, f"{REPORT_DIR}/README.md")
    write(t, f"{REPORT_DIR}/envelope.json", json.dumps(envelope(report_hash)))
    write(t, f"{REPORT_DIR}/dependencies.json", json.dumps(inventory(t)))
    evidence = {"8": {"file": f"{REPORT_DIR}/envelope.json",
                      "content_hash": report_hash}} if cite else {}
    write(t, "manifests/fixture-block.json",
          json.dumps({"block": "fixture-block", "kind": "analog", "evidence": evidence}))
    write(t, "manifests/fixture-block.signoff.json", "{}")


def edit_inventory(t: Path, mutate) -> None:
    path = t / REPORT_DIR / "dependencies.json"
    inv = json.loads(path.read_text())
    mutate(inv)
    path.write_text(json.dumps(inv))


def rebind_report(t: Path, text: str) -> None:
    """Rewrite the report and re-bind envelope, inventory and manifest pin to it."""
    write(t, f"{REPORT_DIR}/README.md", text)
    report_hash = fhash(t, f"{REPORT_DIR}/README.md")
    write(t, f"{REPORT_DIR}/envelope.json", json.dumps(envelope(report_hash)))
    edit_inventory(t, lambda inv: inv.update(report_sha256=report_hash))
    mpath = t / "manifests" / "fixture-block.json"
    m = json.loads(mpath.read_text())
    m["evidence"]["8"]["content_hash"] = report_hash
    mpath.write_text(json.dumps(m))


def run_checker(t: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), "--root", str(t)],
                          capture_output=True, text=True)


def expect(case: str, proc: subprocess.CompletedProcess, *,
           passes: bool, message_fragment: str) -> bool:
    ok = (proc.returncode == 0) == passes and message_fragment in (proc.stdout + proc.stderr)
    print(f"  {'ok  ' if ok else 'FAIL'} {case}")
    if not ok:
        print(f"       rc={proc.returncode}")
        print("       stdout:", proc.stdout.strip()[:600])
        print("       stderr:", proc.stderr.strip()[:600])
    return ok


def exp_index(inv: dict, slug: str) -> dict:
    return next(e for e in inv["experiments"] if e["path"] == f"sim/{slug}")


def main() -> int:
    failures = 0

    def case(name, *, passes, fragment, mutate=None, cite=True):
        nonlocal failures
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            build_fixture(t, cite=cite)
            if mutate:
                mutate(t)
            failures += not expect(name, run_checker(t), passes=passes,
                                   message_fragment=fragment)

    case("case 0: undamaged tree passes", passes=True, fragment="OK:")

    # ---- the acceptance-criteria defect classes ----
    case("case 1: changed DUT input fails, naming the affected experiments",
         passes=False, fragment="DUT INPUT CHANGED",
         mutate=lambda t: write(t, "design/netlist/core.spice",
                                ".subckt core a b\nR1 a b 300\n.ends\n"))
    case("case 1b: the DUT failure names the current experiments it affects",
         passes=False, fragment="affected: sim/vref-pvt, sim/iq",
         mutate=lambda t: write(t, "design/netlist/core.spice", "changed\n"))
    case("case 2: a newer record in a summarized experiment fails",
         passes=False, fragment="NEWER RECORD — 20261009-000000-ddddddd now supersedes",
         mutate=lambda t: add_record(t, "iq", "20261009-000000-ddddddd"))
    case("case 3: a changed spec bound fails, naming the row",
         passes=False, fragment="SPEC ROW CHANGED — 'Iq'",
         mutate=lambda t: write(t, "README.md", TOP_README.replace("< 50 µA", "< 60 µA")))
    case("case 3b: a removed spec row fails",
         passes=False, fragment="spec row 'Iq' no longer exists",
         mutate=lambda t: write(t, "README.md", TOP_README.replace(
             "| Iq | < 50 µA | < 20 µA |\n", "")))
    case("case 3c: an added spec row the report does not cover fails",
         passes=False, fragment="spec row 'Startup' was added",
         mutate=lambda t: write(t, "README.md", TOP_README.replace(
             "| Iq | < 50 µA | < 20 µA |\n",
             "| Iq | < 50 µA | < 20 µA |\n| Startup | < 1 ms | — |\n")))
    case("case 4: missing dependency (a cited record file) fails",
         passes=False, fragment="MISSING DEPENDENCY — record file sim/iq/records",
         mutate=lambda t: (t / f"sim/iq/records/{IQ_REC}.csv").unlink())
    case("case 4b: missing dependency (a DUT netlist) fails",
         passes=False, fragment="MISSING DEPENDENCY — DUT input design/netlist/core.spice",
         mutate=lambda t: (t / "design/netlist/core.spice").unlink())
    case("case 4c: missing dependency (the spec table heading) fails",
         passes=False, fragment="no table under heading",
         mutate=lambda t: write(t, "README.md", TOP_README.replace(
             "## Target specification", "## Targets")))
    case("case 4d: missing dependency inventory beside the active report fails",
         passes=False, fragment="has no dependency inventory",
         mutate=lambda t: (t / REPORT_DIR / "dependencies.json").unlink())
    case("case 5: honest stale-evidence disclosure passes (and is noted)",
         passes=True, fragment=f"{STALE} disclosed as stale")

    # ---- honesty of the freshness marks ----
    def mark_stale_current(t):
        def m(inv):
            e = exp_index(inv, "vref-mc")
            e["freshness"] = "current"
            e["dut"] = ["design/netlist/core.spice"]
        edit_inventory(t, m)
    case("case 6: a waived-stale record marked current is an overclaim",
         passes=False, fragment="OVERCLAIM", mutate=mark_stale_current)
    case("case 7: stale disclosure not present in the report fails",
         passes=False, fragment="does not appear in the report",
         mutate=lambda t: edit_inventory(t, lambda inv: exp_index(inv, "vref-mc").update(
             disclosure="re-run pending under #999")))
    case("case 8: stale disclosure citing a waiver that does not exist fails",
         passes=False, fragment="carries no DUT-staleness waiver",
         mutate=lambda t: edit_inventory(t, lambda inv: exp_index(inv, "vref-mc").update(
             waiver_issue="#999")))
    case("case 9: stale entry without a disclosure phrase fails",
         passes=False, fragment="must carry the report's disclosure phrase",
         mutate=lambda t: edit_inventory(t, lambda inv: exp_index(inv, "vref-mc").pop(
             "disclosure")))
    case("case 10: selected record not cited by the (re-bound) report fails",
         passes=False, fragment="cites neither the selected record",
         mutate=lambda t: rebind_report(
             t, REPORT.replace(f"`sim/iq/records/{IQ_REC}.csv`", "see the Iq bench")))
    case("case 10b: a re-bound report that keeps its citations passes",
         passes=True, fragment="OK:",
         mutate=lambda t: rebind_report(t, REPORT + "\nA clarifying note.\n"))

    # ---- changes that must NOT force a new report ----
    case("case 11: unrelated README prose edit passes",
         passes=True, fragment="OK:",
         mutate=lambda t: write(t, "README.md", TOP_README.replace(
             "More prose.", "Much more prose, rewritten.")))
    case("case 12: whitespace re-flow of the spec table passes",
         passes=True, fragment="OK:",
         mutate=lambda t: write(t, "README.md", TOP_README.replace(
             "| Iq | < 50 µA | < 20 µA |", "|  Iq  |  < 50 µA |   < 20 µA |")))
    case("case 13: unrelated design/ documentation edit passes",
         passes=True, fragment="OK:",
         mutate=lambda t: write(t, "design/README.md", "# design\n\nNew notes.\n"))
    case("case 14: a new record in an experiment outside the inventory passes",
         passes=True, fragment="OK:",
         mutate=lambda t: add_record(t, "unrelated", "20261009-000000-eeeeeee"))

    def historical(t):
        # A superseded report with its own (now stale) inventory: not cited,
        # so it must not be required to track newer inputs.
        write(t, f"{OLD_REPORT_DIR}/README.md", "# old report\n")
        write(t, f"{OLD_REPORT_DIR}/dependencies.json", json.dumps({
            "schema_version": 1, "report": f"{OLD_REPORT_DIR}/README.md",
            "report_sha256": "sha256:" + "f" * 64, "dut": [], "spec": {},
            "experiments": [{"path": "sim/iq", "selected_record": STALE}]}))
    case("case 15: a historical, uncited report's stale inventory is not checked",
         passes=True, fragment="not actively cited", mutate=historical)

    # ---- binding and malformed inputs ----
    case("case 16: report edited after its inventory was written fails",
         passes=False, fragment="needs its dependency inventory re-audited",
         mutate=lambda t: write(t, f"{REPORT_DIR}/README.md", REPORT + "\nAddendum.\n"))
    case("case 17: malformed inventory JSON fails",
         passes=False, fragment="not valid JSON",
         mutate=lambda t: write(t, f"{REPORT_DIR}/dependencies.json", "{not json"))
    case("case 18: inventory path escaping the repository is rejected",
         passes=False, fragment="escapes the repository",
         mutate=lambda t: edit_inventory(t, lambda inv: inv["dut"].append(
             {"path": "../../../../etc/hostname", "sha256": "sha256:" + "0" * 64})))
    case("case 19: absolute inventory path is rejected",
         passes=False, fragment="is absolute",
         mutate=lambda t: edit_inventory(t, lambda inv: inv["dut"].append(
             {"path": "/etc/hostname", "sha256": "sha256:" + "0" * 64})))
    case("case 20: malformed sha256 is rejected",
         passes=False, fragment="malformed sha256",
         mutate=lambda t: edit_inventory(t, lambda inv: inv["dut"][0].update(sha256="abc")))
    case("case 21: decision-record status change fails",
         passes=False, fragment="DECISION RECORD STATUS CHANGED",
         mutate=lambda t: write(t, "spec/decision-records/0007-ratify.md",
                                DR_TEXT.replace("ratified", "proposed")))
    case("case 22: a path the report states is absent now exists",
         passes=False, fragment="the report states nothing matches",
         mutate=lambda t: write(t, "spec/decision-records/0012-recast.md", DR_TEXT))
    case("case 23: unknown freshness value fails",
         passes=False, fragment="freshness must be one of",
         mutate=lambda t: edit_inventory(t, lambda inv: exp_index(inv, "iq").update(
             freshness="fresh-ish")))
    case("case 24: spec_rows naming an unaudited row fails",
         passes=False, fragment="not an audited spec row",
         mutate=lambda t: edit_inventory(t, lambda inv: exp_index(inv, "iq").update(
             spec_rows=["Quiescent current"])))
    case("case 25: missing required inventory field fails",
         passes=False, fragment="required field 'experiments'",
         mutate=lambda t: edit_inventory(t, lambda inv: inv.pop("experiments")))
    case("case 26: no item-8 citation at all passes with a note",
         passes=True, fragment="no item-8 citation", cite=False)

    if failures:
        print(f"\n{failures} case(s) failed", file=sys.stderr)
        return 1
    print("OK: all report-dependency checker self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
