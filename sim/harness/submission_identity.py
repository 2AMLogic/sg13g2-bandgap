#!/usr/bin/env python3
"""Bind a batch shard's report to the exact inputs that were submitted (#332).

The per-shard batch runners are resumable: a report that already exists and
graded `pass` is not re-submitted. A passing status alone says nothing about
WHICH inputs produced it, so a resumed run that regenerated its body, request
or extraction could combine old measurements with a new DUT. This module
records an immutable *submission identity* beside each report and refuses to
reuse a report whose identity does not match what the resumed campaign would
submit now.

Identity = sha256 of a canonical JSON document holding

* the exact request bytes,
* the local include closure of the request: the netlist it names, the local
  `models.lib` if it is a file, and every `.include`/`.inc`/`.lib` that
  resolves to an existing file relative to its includer (this carries the
  generated DUT body and the generated PEX extraction body),
* any extra files the caller names (`--extra`: templates, generators,
  provision script; a missing one is recorded as MISSING),
* runner-side references that are not local files (e.g. `/opt/pdk/...`),
  recorded as strings, and
* declared identities (`--declare key=value`: klt version, PDK name/root...).

Protocol (sidecar `<report>.identity.json`, snapshot `<report>.submitted/`):

* `begin`  before submission: remove any old sidecar, snapshot the closure
  (so record-side fixup can use the ORIGINAL submitted body) and write a
  *pending* identity. A pending identity never authorises reuse.
* `commit` after submission completed and a report exists: re-verify the
  inputs still hash to the pending identity, then atomically publish the
  sidecar. A crash in between leaves no sidecar, so the shard is unbound.
* `check`  on resume: exit 0 reuse, 1 dispatch, 3 refuse (stale / unbound).

BOUNDARY. The identity attests only to what is visible at submission time on
the submitting host. It cannot attest to unrecorded changes on the remote side
(runner image contents, a klt build that reports the same version string, the
baked PDK files behind `/opt/pdk`). Those are covered only as far as the
caller declares them; to invalidate across such a change, use a new work dir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

SCHEMA = "submission-identity/1"
EXIT_REUSE, EXIT_DISPATCH, EXIT_REFUSE = 0, 1, 3
ENV_ALLOW_LEGACY = "KLT_SIM_ALLOW_UNBOUND_REPORTS"
ENV_REDISPATCH = "KLT_SIM_REDISPATCH_STALE"

_INCLUDE_RE = re.compile(r'^\s*\.(?:include|inc|lib)\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))', re.I | re.M)


class IdentityError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sidecar_path(report: Path) -> Path:
    return report.with_name(report.stem + ".identity.json")


def pending_path(report: Path) -> Path:
    return report.with_name(report.stem + ".identity.pending.json")


def snapshot_dir(report: Path) -> Path:
    return report.with_name(report.stem + ".submitted")


def _walk_includes(path: Path, root: Path, closure: dict[str, str], external: set[str]) -> None:
    rel = os.path.relpath(path, root)
    if rel in closure:
        return
    data = path.read_bytes()
    closure[rel] = sha256_bytes(data)
    for m in _INCLUDE_RE.finditer(data.decode("utf-8", errors="replace")):
        ref = m.group(1) or m.group(2) or m.group(3)
        cand = Path(ref) if os.path.isabs(ref) else path.parent / ref
        # Only files under the request dir are the local closure; anything
        # else (the runner's baked PDK, absolute paths) is an external ref.
        try:
            inside = cand.is_file() and cand.resolve().is_relative_to(root.resolve())
        except OSError:
            inside = False
        if inside:
            _walk_includes(cand, root, closure, external)
        else:
            external.add(ref)


def compute(request: Path, extras: list[Path], declared: dict[str, str]) -> dict:
    request = request.resolve()
    if not request.is_file():
        raise IdentityError(f"request not found: {request}")
    root = request.parent
    req_bytes = request.read_bytes()
    req = json.loads(req_bytes)
    closure: dict[str, str] = {}
    external: set[str] = set()
    netlist = req.get("netlist")
    body_rel = None
    if isinstance(netlist, str):
        body = Path(netlist) if os.path.isabs(netlist) else root / netlist
        if not body.is_file():
            raise IdentityError(f"request netlist missing: {body}")
        # The closure root is the body's directory so bare includes resolve.
        broot = body.parent.resolve()
        sub: dict[str, str] = {}
        _walk_includes(body.resolve(), broot, sub, external)
        closure.update({k: v for k, v in sub.items()})
        body_rel = os.path.relpath(body.resolve(), broot)
    lib = (req.get("models") or {}).get("lib")
    if isinstance(lib, str):
        cand = Path(lib) if os.path.isabs(lib) else root / lib
        if cand.is_file():
            closure[f"models.lib:{cand.name}"] = sha256_file(cand)
        else:
            external.add(lib)
    extra_ids: dict[str, str] = {}
    for e in extras:
        if e.name in extra_ids:
            raise IdentityError(f"duplicate --extra name {e.name!r}")
        extra_ids[e.name] = sha256_file(e) if e.is_file() else "MISSING"
    doc = {
        "schema": SCHEMA,
        "request_sha256": sha256_bytes(req_bytes),
        "closure": dict(sorted(closure.items())),
        "body": body_rel,
        "external_refs": sorted(external),
        "extras": dict(sorted(extra_ids.items())),
        "declared": dict(sorted(declared.items())),
    }
    doc["digest"] = sha256_bytes(json.dumps(
        {k: v for k, v in doc.items() if k != "digest"}, sort_keys=True).encode())
    return doc


def _snapshot(request: Path, ident: dict, report: Path) -> None:
    snap = snapshot_dir(report)
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir(parents=True)
    shutil.copy2(request, snap / "request.json")
    req = json.loads(request.read_text(encoding="utf-8"))
    netlist = req.get("netlist")
    if not ident["body"]:
        return
    body = Path(netlist) if os.path.isabs(netlist) else request.parent / netlist
    broot = body.resolve().parent
    for rel in ident["closure"]:
        if rel.startswith("models.lib:"):
            continue
        dst = snap / "closure" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(broot / rel, dst)


def snapshot_body(report: Path, ident: dict | None = None) -> Path:
    """Path of the ORIGINAL submitted body, verified against the sidecar."""
    side = sidecar_path(report)
    if ident is None:
        if not side.is_file():
            raise IdentityError(f"no submission identity for {report}")
        ident = json.loads(side.read_text(encoding="utf-8"))
    snap = snapshot_dir(report) / "closure"
    for rel, want in ident["closure"].items():
        if rel.startswith("models.lib:"):
            continue
        f = snap / rel
        if not f.is_file() or sha256_file(f) != want:
            raise IdentityError(f"submitted snapshot {f} missing or altered since submission")
    return snap / ident["body"]


def begin(request: Path, report: Path, extras, declared) -> dict:
    sidecar_path(report).unlink(missing_ok=True)
    pending_path(report).unlink(missing_ok=True)
    ident = compute(request, extras, declared)
    _snapshot(request.resolve(), ident, report)
    ident["request"] = str(request.resolve())
    ident["extras_paths"] = [str(e) for e in extras]
    pending_path(report).write_text(json.dumps(ident, indent=2) + "\n", encoding="utf-8")
    return ident


def commit(report: Path) -> dict:
    pend = pending_path(report)
    if not pend.is_file():
        raise IdentityError(f"no pending identity for {report}; run `begin` before submitting")
    if not report.is_file() or report.stat().st_size == 0:
        raise IdentityError(f"submission wrote no report at {report}; identity not committed")
    try:
        json.loads(report.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise IdentityError(f"report {report} is not valid JSON: {exc}") from exc
    ident = json.loads(pend.read_text(encoding="utf-8"))
    now = compute(Path(ident["request"]), [Path(p) for p in ident["extras_paths"]], ident["declared"])
    if now["digest"] != ident["digest"]:
        raise IdentityError("submission inputs changed while the shard was running; identity not committed")
    tmp = sidecar_path(report).with_suffix(".tmp")
    tmp.write_text(json.dumps(ident, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, sidecar_path(report))
    pend.unlink()
    return ident


def check(request: Path, report: Path, extras, declared, env=None) -> tuple[int, str]:
    env = os.environ if env is None else env
    if not report.is_file() or report.stat().st_size == 0:
        return EXIT_DISPATCH, "no report"
    try:
        status = json.loads(report.read_text(encoding="utf-8")).get("status")
    except ValueError:
        return EXIT_DISPATCH, "report unreadable"
    if status != "pass":
        return EXIT_DISPATCH, f"report status {status!r}"
    hint = (f"Use a NEW work dir (unset KLT_SIM_WORK) to redispatch the whole campaign, or delete "
            f"{report.name} (+ .identity.json/.submitted) to redispatch just this shard")
    side = sidecar_path(report)
    if not side.is_file():
        if env.get(ENV_ALLOW_LEGACY) == "1":
            return EXIT_REUSE, (f"WARNING: {report.name} has no submission identity; reusing it UNBOUND "
                                f"because {ENV_ALLOW_LEGACY}=1 (its inputs are unverified)")
        return EXIT_REFUSE, (f"{report.name} passed but has no committed submission identity "
                             f"(legacy report or interrupted before commit), so it cannot be tied to "
                             f"the inputs being submitted now. {hint}; or set {ENV_ALLOW_LEGACY}=1 to "
                             f"accept it unverified")
    old = json.loads(side.read_text(encoding="utf-8"))
    now = compute(request, extras, declared)
    if old.get("digest") == now["digest"]:
        return EXIT_REUSE, "identity matches"
    diffs = []
    for key in ("request_sha256", "body", "external_refs", "extras", "declared"):
        if old.get(key) != now.get(key):
            diffs.append(key)
    oc, nc = old.get("closure", {}), now["closure"]
    diffs += [f"closure:{k}" for k in sorted(set(oc) | set(nc)) if oc.get(k) != nc.get(k)]
    msg = f"{report.name} was produced from different inputs than would be submitted now (changed: {', '.join(diffs)})"
    if env.get(ENV_REDISPATCH) == "1":
        return EXIT_DISPATCH, f"{msg}; redispatching because {ENV_REDISPATCH}=1"
    return EXIT_REFUSE, f"{msg}. {hint}; or set {ENV_REDISPATCH}=1 to redispatch stale shards"


def _parse_declared(items: list[str]) -> dict[str, str]:
    out = {}
    for it in items:
        k, sep, v = it.partition("=")
        if not sep:
            raise IdentityError(f"--declare wants key=value, got {it!r}")
        out[k] = v
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("begin", "check"):
        p = sub.add_parser(name)
        p.add_argument("request", type=Path)
        p.add_argument("report", type=Path)
        p.add_argument("--extra", type=Path, action="append", default=[])
        p.add_argument("--declare", action="append", default=[])
    p = sub.add_parser("commit")
    p.add_argument("report", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "begin":
            ident = begin(args.request, args.report, args.extra, _parse_declared(args.declare))
            print(f"submission identity {ident['digest'][:16]} pending for {args.report.name}")
        elif args.cmd == "commit":
            ident = commit(args.report)
            print(f"submission identity {ident['digest'][:16]} committed for {args.report.name}")
        else:
            rc, msg = check(args.request, args.report, args.extra, _parse_declared(args.declare))
            print(f"submission_identity: {msg}", file=sys.stderr if rc else sys.stdout)
            return rc
    except IdentityError as exc:
        print(f"submission_identity: {exc}", file=sys.stderr)
        return EXIT_REFUSE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
