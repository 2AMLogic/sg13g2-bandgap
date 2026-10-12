#!/usr/bin/env python3
"""Self-test for `check_design_source_dependencies.py` (issue #324).

    python3 .github/scripts/test_check_design_source_dependencies.py

Each case builds a synthetic repository in a temp directory (block manifest
citing an item-1 envelope, an attestation, its inventory, design sources and
an out-of-scope SG13CMOS5L variant), injects exactly one defect -- or one
change that must NOT fail -- and asserts the verdict and a specific message.
Case 0 asserts the undamaged fixture passes. The checker runs as a
subprocess, as CI runs it. Stdlib only; no PDK, no xschem, no network.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "check_design_source_dependencies.py"

SOURCES = {
    "design/cell_a.sch": "v {xschem version=3.4.4}\nA\n",
    "design/cell_b.sch": "v {xschem version=3.4.4}\nB\n",
    "design/cell_a.sym": "sym A\n",
    "design/netlist/cell_a.spice": "* netlist A\n.subckt cell_a\n.ends\n",
    "design/netlist/cell_b.spice": "* netlist B\n.subckt cell_b\n.ends\n",
    "design/xschemrc": "set PDK ihp-sg13g2\n",
    "design/sg13cmos5l/cell_a.sch": "variant A\n",
    "design/sg13cmos5l/netlist/cell_a.spice": "* variant netlist\n",
}
INPUTS = [p for p in SOURCES if "sg13cmos5l" not in p and p != "design/xschemrc"]
ROLE = {".sch": "schematic", ".sym": "symbol", ".spice": "netlist"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(t: Path, rel: str, data: str) -> None:
    path = t / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def build(t: Path, *, inventory_mutator=None, attest_extra: str = "") -> None:
    for rel, data in SOURCES.items():
        write(t, rel, data)
    lines = ["# attestation", "", "## Sources"]
    for rel in INPUTS:
        lines.append(f"{sha(SOURCES[rel].encode())}  {rel}")
    lines += ["", "## Not attested -- design/sg13cmos5l/",
              f"{sha(SOURCES['design/sg13cmos5l/cell_a.sch'].encode())}  design/sg13cmos5l/cell_a.sch", ""]
    write(t, "manifests/evidence/design-sources.txt", "\n".join(lines) + attest_extra)
    write(t, "manifests/evidence/design-sources.json", json.dumps(
        {"t1_item": 1, "source": "design-sources.txt", "status": "pass"}))
    write(t, "manifests/block.json", json.dumps(
        {"block": "x", "evidence": {"1": {"file": "manifests/evidence/design-sources.json"}}}))
    attest_bytes = (t / "manifests/evidence/design-sources.txt").read_bytes()
    inv = {
        "schema_version": 1, "t1_item": 1,
        "attestation": "manifests/evidence/design-sources.txt",
        "attestation_sha256": "sha256:" + sha(attest_bytes),
        "scope": {"include": ["design/*.sch", "design/*.sym", "design/netlist/*.spice"],
                  "exclude": ["design/sg13cmos5l"]},
        "inputs": [{"path": p, "sha256": "sha256:" + sha(SOURCES[p].encode()),
                    "role": ROLE[Path(p).suffix]} for p in INPUTS],
        "export_config": [{"path": "design/xschemrc",
                           "sha256": "sha256:" + sha(SOURCES["design/xschemrc"].encode())}],
    }
    if inventory_mutator:
        inventory_mutator(inv)
    write(t, "manifests/evidence/design-sources.inventory.json", json.dumps(inv))


def run(t: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(CHECKER), "--root", str(t)],
                       capture_output=True, text=True, check=False)
    return p.returncode, p.stdout + p.stderr


FAILED: list[str] = []


def case(name: str, expect_ok: bool, needles: list[str], *, setup=None, **build_kw) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        build(t, **build_kw)
        if setup:
            setup(t)
        code, out = run(t)
    ok = (code == 0) == expect_ok and all(n in out for n in needles)
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if not ok:
        FAILED.append(name)
        print(f"  exit={code} expected_ok={expect_ok} needles={needles}\n  output:\n{out}")


def append(rel: str, extra: str = "x\n"):
    def f(t: Path) -> None:
        with (t / rel).open("a", encoding="utf-8") as fh:
            fh.write(extra)
    return f


def mut(fn):
    return {"inventory_mutator": fn}


def main() -> int:
    case("0 undamaged fixture passes", True, ["OK:", "not a new export-equivalence proof"])

    # acceptance: in-scope input changes fail although attestation bytes are unchanged
    for rel in ("design/cell_a.sch", "design/cell_a.sym", "design/netlist/cell_a.spice",
                "design/xschemrc"):
        case(f"changed {rel} fails naming path", False,
             [rel, "AUDITED INPUT CHANGED", "fresh explicit export audit"], setup=append(rel))

    def del_input(rel):
        return lambda t: (t / rel).unlink()
    case("deleted in-scope cell fails", False, ["design/cell_b.sch", "MISSING AUDITED INPUT"],
         setup=del_input("design/cell_b.sch"))
    case("deleted export config fails", False, ["design/xschemrc", "MISSING AUDITED INPUT"],
         setup=del_input("design/xschemrc"))
    case("added in-scope schematic fails", False, ["UNAUDITED SOURCE", "design/cell_c.sch"],
         setup=lambda t: write(t, "design/cell_c.sch", "new\n"))
    case("added in-scope netlist fails", False, ["UNAUDITED SOURCE", "design/netlist/cell_c.spice"],
         setup=lambda t: write(t, "design/netlist/cell_c.spice", "new\n"))
    case("added in-scope symbol fails", False, ["UNAUDITED SOURCE", "design/cell_c.sym"],
         setup=lambda t: write(t, "design/cell_c.sym", "new\n"))

    # negative controls: must NOT invalidate
    case("unrelated documentation edits pass", True, ["OK:"], setup=lambda t: (
        write(t, "README.md", "docs\n"), write(t, "design/README.md", "notes\n"),
        write(t, "design/notes.md", "n\n"), write(t, "spec/x.md", "s\n"),
        append("design/README.md")(t)))
    case("out-of-scope SG13CMOS5L edit passes", True, ["OK:"],
         setup=append("design/sg13cmos5l/cell_a.sch"))
    case("out-of-scope SG13CMOS5L add/delete passes", True, ["OK:"], setup=lambda t: (
        write(t, "design/sg13cmos5l/new.sch", "n\n"),
        write(t, "design/sg13cmos5l/netlist/new.spice", "n\n"),
        (t / "design/sg13cmos5l/netlist/cell_a.spice").unlink()))
    case("non-recursive scope: nested non-listed dir not implicitly attested", True, ["OK:"],
         setup=lambda t: write(t, "design/other/deep.sch", "n\n"))

    # inventory <-> attestation consistency
    def drift_hash(inv):
        inv["inputs"][0]["sha256"] = "sha256:" + "0" * 64
    case("inventory hash disagreeing with attestation fails", False,
         ["CHANGED", "hash differs between inventory"], **mut(drift_hash))
    case("inventory missing an attested file fails", False,
         ["in the attestation but not in the inventory"],
         **mut(lambda inv: inv["inputs"].pop()))
    case("changed attestation bytes need a re-written inventory", False,
         ["now hashes to"], setup=append("manifests/evidence/design-sources.txt", "# edit\n"))

    # missing / malformed inventories and escaping paths
    case("missing inventory fails clearly", False, ["MISSING", "no dependency inventory"],
         setup=lambda t: (t / "manifests/evidence/design-sources.inventory.json").unlink())
    case("invalid JSON inventory fails", False, ["not valid JSON"],
         setup=lambda t: write(t, "manifests/evidence/design-sources.inventory.json", "{nope"))
    case("non-object inventory fails", False, ["must be a JSON object"],
         setup=lambda t: write(t, "manifests/evidence/design-sources.inventory.json", "[]"))
    case("wrong schema_version fails", False, ["schema_version"],
         **mut(lambda inv: inv.update(schema_version=2)))
    case("missing inputs field fails", False, ["required field 'inputs'"],
         **mut(lambda inv: inv.pop("inputs")))
    case("empty inputs fails", False, ["inputs must not be empty"],
         **mut(lambda inv: inv.update(inputs=[])))
    case("malformed sha256 fails", False, ["malformed sha256"],
         **mut(lambda inv: inv["inputs"][0].update(sha256="abc")))
    case("unknown role fails", False, ["role must be one of"],
         **mut(lambda inv: inv["inputs"][0].update(role="gds")))
    case("inventory for another attestation fails", False, ["is for attestation"],
         **mut(lambda inv: inv.update(attestation="manifests/evidence/old.txt")))
    case("absolute input path fails", False, ["is absolute"],
         **mut(lambda inv: inv["inputs"][0].update(path="/etc/passwd")))
    case("repository-escaping input path fails", False, ["escapes the repository"],
         **mut(lambda inv: inv["inputs"][0].update(path="../outside.sch")))
    case("repository-escaping export_config fails", False, ["escapes the repository"],
         **mut(lambda inv: inv["export_config"][0].update(path="design/../../x")))
    case("escaping scope glob fails", False, ["without '..'"],
         **mut(lambda inv: inv["scope"]["include"].append("../*.sch")))
    case("recursive scope glob fails", False, ["recursive"],
         **mut(lambda inv: inv["scope"]["include"].append("design/**/*.sch")))
    case("scope glob reaching into out-of-scope fails", False, ["out-of-scope"],
         **mut(lambda inv: inv["scope"]["include"].append("design/sg13cmos5l/*.sch")))
    case("out-of-scope path listed as input fails", False, ["out-of-scope"],
         **mut(lambda inv: inv["inputs"].append(
             {"path": "design/sg13cmos5l/cell_a.sch", "role": "schematic",
              "sha256": "sha256:" + sha(SOURCES["design/sg13cmos5l/cell_a.sch"].encode())})))

    def symlink_escape(t: Path) -> None:
        outside = t.parent / (t.name + "-outside.sch")
        outside.write_text("x\n", encoding="utf-8")
        (t / "design/linked.sch").symlink_to(outside)
    case("in-scope symlink escaping the repository fails", False, ["outside the repository"],
         setup=symlink_escape)

    # citation plumbing
    case("no item-1 citation is noted, not failed", True, ["nothing to check"],
         setup=lambda t: write(t, "manifests/block.json", json.dumps({"evidence": {}})))
    case("envelope without source fails", False, ["names no 'source'"],
         setup=lambda t: write(t, "manifests/evidence/design-sources.json", "{}"))
    case("attestation absent fails", False, ["does not exist"],
         setup=lambda t: (t / "manifests/evidence/design-sources.txt").unlink())

    # superseded audit stays historical
    def superseded(t: Path) -> None:
        write(t, "manifests/evidence/old-sources.inventory.json", json.dumps(
            {"schema_version": 1, "inputs": [{"path": "design/gone.sch", "sha256": "bad"}]}))
    case("superseded audit inventory is historical, not checked", True,
         ["old-sources.inventory.json", "not actively cited"], setup=superseded)

    def repoint(t: Path) -> None:
        # a new audit becomes active; the old inventory stays and is not required to track
        write(t, "manifests/evidence/design-sources-v2.txt",
              (t / "manifests/evidence/design-sources.txt").read_text() + "# v2\n")
        write(t, "manifests/evidence/design-sources-v2.json", json.dumps(
            {"t1_item": 1, "source": "design-sources-v2.txt"}))
        write(t, "manifests/block.json", json.dumps(
            {"evidence": {"1": "manifests/evidence/design-sources-v2.json"}}))
    case("re-pointing item 1 requires the new audit's own inventory", False,
         ["design-sources-v2.inventory.json", "no dependency inventory"], setup=repoint)

    if FAILED:
        print(f"\n{len(FAILED)} case(s) failed: {', '.join(FAILED)}", file=sys.stderr)
        return 1
    print("\nall cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
