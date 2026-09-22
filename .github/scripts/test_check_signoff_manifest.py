#!/usr/bin/env python3
"""Self-test for `check_signoff_manifest.py`.

    python3 .github/scripts/test_check_signoff_manifest.py

A checker that never fails is indistinguishable from no checker at all, so
each case below builds a synthetic manifest tree in a temp directory with a
stub `klt` on PATH, introduces exactly one defect, and asserts the checker
rejects it with a specific message. Case 0 asserts the undamaged tree
passes, so the failures are attributable to the injected defect rather than
to the fixture.

Black-box on purpose: the checker is invoked as a subprocess, the same way
CI and a human run it. Stdlib only, no PDK, no network — the stub `klt`
stands in for the real CLI, exactly like the fleet roll-up's own test
harness does in 2AMLogic/2am.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_signoff_manifest.py"

GDS_BYTES = b"fake gds fixture content v1"
GDS_HASH = "sha256:" + __import__("hashlib").sha256(GDS_BYTES).hexdigest()

DRC_ENVELOPE = {
    "schema_version": 1,
    "status": "clean",
    "violation_count": 0,
    "file": "fixture_cell.gds",
    "provenance": {"input": {"content_hash": GDS_HASH}},
}

LVS_ENVELOPE = {
    "schema_version": 1,
    "status": "mismatch",
    "file": "fixture_cell.gds",
    "provenance": {"input": None},
}

STUB_REPORT = {
    "schema_version": 1,
    "block": "fixture-block",
    "kind": "analog",
    "tier": None,
    "t1_item_count": 11,
    "t1_met_count": 1,
    "items": [
        {"tier": "T1", "id": 3, "status": "met", "reason": None},
        {"tier": "T1", "id": 4, "status": "unmet", "reason": "check_failed"},
    ],
}


def build_fixture(t: Path, *, gds: bytes = GDS_BYTES, manifest_evidence=None,
                  committed_report=None, stub_exit: int = 3) -> None:
    layout = t / "layout" / "fixture_cell"
    layout.mkdir(parents=True)
    (layout / "fixture_cell.gds").write_bytes(gds)
    (layout / "drc_report.json").write_text(json.dumps(DRC_ENVELOPE))
    (layout / "lvs_report.json").write_text(json.dumps(LVS_ENVELOPE))
    manifests = t / "manifests"
    manifests.mkdir()
    evidence = manifest_evidence if manifest_evidence is not None else {
        "3": {"file": "layout/fixture_cell/drc_report.json", "content_hash": GDS_HASH},
        "4": "layout/fixture_cell/lvs_report.json",
    }
    (manifests / "fixture-block.json").write_text(
        json.dumps({"block": "fixture-block", "kind": "analog", "evidence": evidence})
    )
    report = committed_report if committed_report is not None else STUB_REPORT
    (manifests / "fixture-block.signoff.json").write_text(json.dumps(report))

    # Stub klt: prints the canned report JSON, exits with stub_exit.
    stub_dir = t / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "klt"
    stub.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' {json.dumps(json.dumps(report))}\n"
        f"exit {stub_exit}\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


def run_checker(t: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{t / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env.pop("KLT_BIN", None)
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(t)],
        capture_output=True,
        text=True,
        env=env,
    )


def expect(case: str, proc: subprocess.CompletedProcess, *,
           passes: bool, message_fragment: str) -> bool:
    ok = (proc.returncode == 0) == passes and message_fragment in (
        proc.stdout + proc.stderr
    )
    print(f"  {'ok  ' if ok else 'FAIL'} {case}")
    if not ok:
        print(f"       rc={proc.returncode}")
        print("       stdout:", proc.stdout.strip()[:400])
        print("       stderr:", proc.stderr.strip()[:400])
    return ok


def main() -> int:
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t)
        failures += not expect(
            "case 0: undamaged tree passes (with unpinned-entry note)",
            run_checker(t), passes=True, message_fragment="1",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t)
        path = t / "manifests" / "fixture-block.signoff.json"
        rotted = dict(STUB_REPORT, t1_met_count=2)
        path.write_text(json.dumps(rotted))
        failures += not expect(
            "case 1: committed verdict rotted vs fresh grade",
            run_checker(t), passes=False, message_fragment="ROTTED",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, gds=b"fake gds fixture content v2 -- regenerated")
        failures += not expect(
            "case 2: cited artifact changed since the envelope pinned it",
            run_checker(t), passes=False, message_fragment="STALE",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, manifest_evidence={
            "3": {"file": "layout/fixture_cell/drc_report.json",
                  "content_hash": "sha256:" + "0" * 64},
        })
        failures += not expect(
            "case 3: manifest pin disagrees with the envelope's recorded hash",
            run_checker(t), passes=False,
            message_fragment="pinned content_hash",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, stub_exit=4)
        failures += not expect(
            "case 4: klt exit 4 (refused) is not a valid grade",
            run_checker(t), passes=False, message_fragment="expected 0 or 3",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, stub_exit=1)
        failures += not expect(
            "case 5: klt crash (exit 1) is not a valid grade",
            run_checker(t), passes=False, message_fragment="expected 0 or 3",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t)
        (t / "manifests" / "fixture-block.signoff.json").unlink()
        failures += not expect(
            "case 6: no committed verdict of record",
            run_checker(t), passes=False, message_fragment="verdict-of-record",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        # Item 11's compound shape (klayout-tools#2025): a list of ordinary
        # entries. Valid elements must pass the same per-entry checks.
        build_fixture(t, manifest_evidence={
            "3": {"file": "layout/fixture_cell/drc_report.json",
                  "content_hash": GDS_HASH},
            "4": "layout/fixture_cell/lvs_report.json",
            "11": [
                {"file": "layout/fixture_cell/drc_report.json",
                 "content_hash": GDS_HASH},
                "layout/fixture_cell/lvs_report.json",
            ],
        })
        failures += not expect(
            "case 7: compound (list) citation with valid elements passes",
            run_checker(t), passes=True, message_fragment="1",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, manifest_evidence={
            "3": {"file": "layout/fixture_cell/drc_report.json",
                  "content_hash": GDS_HASH},
            "11": [
                {"file": "layout/fixture_cell/drc_report.json",
                 "content_hash": GDS_HASH},
                42,
            ],
        })
        failures += not expect(
            "case 8: compound citation with a malformed element fails, "
            "naming the element index",
            run_checker(t), passes=False,
            message_fragment="evidence['11'][1]: entry must be a path string",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build_fixture(t, manifest_evidence={
            "3": {"file": "layout/fixture_cell/drc_report.json",
                  "content_hash": GDS_HASH},
            "11": [],
        })
        failures += not expect(
            "case 9: empty citation list is rejected (cite nothing = uncited)",
            run_checker(t), passes=False, message_fragment="empty citation list",
        )

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        # `klt erc` envelopes name their input repo-rooted
        # (`layout/<cell>/<cell>.gds`), not as a sibling of the envelope —
        # the checker must resolve that reading too, not just parent-relative.
        erc = {
            "schema_version": 1,
            "status": "not_checked",
            "erc_status": "clean",
            "erc_finding_count": 0,
            "file": "layout/fixture_cell/fixture_cell.gds",
            "provenance": {"input": {"content_hash": GDS_HASH}},
        }
        build_fixture(t, manifest_evidence={
            "3": {"file": "layout/fixture_cell/drc_report.json",
                  "content_hash": GDS_HASH},
            "11": [{"file": "layout/fixture_cell/erc_report.json",
                    "content_hash": GDS_HASH}],
        })
        (t / "layout" / "fixture_cell" / "erc_report.json").write_text(
            json.dumps(erc)
        )
        failures += not expect(
            "case 10: envelope input named repo-rooted resolves and passes",
            run_checker(t), passes=True, message_fragment="1",
        )

    if failures:
        print(f"\n{failures} case(s) failed", file=sys.stderr)
        return 1
    print("OK: all signoff-manifest checker self-test cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
