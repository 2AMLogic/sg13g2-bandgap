#!/usr/bin/env python3
"""Repoint a per-process batch report's decks at locally resolvable files.

Issue #278's per-process bridge runs each grid slice on the batch fleet,
and the per-corner decks that come back reference the RUNNER's filesystem:
`.include /var/tmp/eda-job-<id>/inputs/netlist.cir` (the staged body) and
`.lib /opt/pdk/...` (the image's baked PDK root). Neither resolves on the
submitting host, so `klt_sim_evidence.py`'s `inline_deck` -- which splices
`.include`s so the committed snapshot carries the DUT's devices -- finds
nothing to splice and the record ships a device-less snapshot.

This module rewrites, for one report:

* every deck's runner-side netlist include to a local body copy,
* every `/opt/pdk` reference (deck `.lib` lines and, in the body copy, the
  two family `.lib` cards the bridge appended) to the local PDK_ROOT, which
  the adapter then relativizes to `${PDK_ROOT}` in the committed snapshot,
* each corner's `artifacts.deck` to the patched copy.

The body copy is a RECORD-side artifact only -- the submission bodies keep
the image's baked paths, because that is what the runner resolves.

Usage:

    python3 sim/harness/fixup_batch_report.py report.json \
        --body body-fixed-typ.spice [--allow-unbound] \
        --runner-pdk-root /opt/pdk --local-pdk-root "$PDK_ROOT" \
        -o report-fixed.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import submission_identity as si  # noqa: E402

_RUNNER_INCLUDE_RE = re.compile(r'^(\s*\.include\s+").*?/inputs/netlist\.cir(")', re.M)


def fixup(
    report_path: Path,
    body: Path,
    runner_pdk_root: str,
    local_pdk_root: str,
    out_dir: Path,
) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for corner in report.get("corners", []):
        deck = (corner.get("artifacts") or {}).get("deck")
        if not deck:
            continue
        deck_path = Path(deck)
        if not deck_path.is_absolute():
            # The batch reports were written with the work dir as cwd, so
            # their artifact paths are relative to it -- the report's own
            # directory.
            deck_path = report_path.parent / deck_path
        if not deck_path.exists():
            continue
        text = deck_path.read_text(encoding="utf-8")
        text = _RUNNER_INCLUDE_RE.sub(lambda m: f"{m.group(1)}{body}{m.group(2)}", text)
        text = text.replace(f'"{runner_pdk_root}/', f'"{local_pdk_root}/')
        # klt 0.7 writes the deck's `.lib <path> <section>` card unquoted.
        text = re.sub(
            rf"(^\s*\.(?:lib|include)\s+){re.escape(runner_pdk_root)}/",
            lambda m: f"{m.group(1)}{local_pdk_root}/",
            text,
            flags=re.M,
        )
        # The runner's deck writes the include bare (no quotes); handle that
        # spelling too.
        text = re.sub(
            r"^(\s*\.include\s+)\S*?/inputs/netlist\.cir(\s*)$",
            lambda m: f"{m.group(1)}{body}{m.group(2)}",
            text,
            flags=re.M,
        )
        fixed = out_dir / (corner.get("corner_id", "corner").replace("/", "_") + ".cir")
        fixed.write_text(text, encoding="utf-8")
        corner["artifacts"]["deck"] = str(fixed)
    return report


def submitted_body(report_path: Path, runner_pdk_root: str, local_pdk_root: str,
                   out_dir: Path) -> Path:
    """Local, PDK-repointed copy of the body the report's shard ACTUALLY ran.

    Reads the snapshot taken at submission (verified against the committed
    identity), never today's regenerated body (#332). The whole include
    closure is copied so bare includes (the PEX body) resolve to the original
    submitted files.
    """
    src = si.snapshot_body(report_path)
    dst = out_dir / "submitted-body"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src.parent, dst)
    body = dst / src.name
    body.write_text(
        body.read_text(encoding="utf-8").replace(f'"{runner_pdk_root}/', f'"{local_pdk_root}/'),
        encoding="utf-8",
    )
    return body


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("report", type=Path)
    ap.add_argument("--body", type=Path,
                    help="UNBOUND fallback: local body copy the decks' include is repointed "
                         "at. Only used with --allow-unbound; it is not proof of what ran")
    ap.add_argument("--allow-unbound", action="store_true",
                    help="accept a report with no committed submission identity "
                         "(legacy opt-in; uses --body)")
    ap.add_argument("--runner-pdk-root", default="/opt/pdk")
    ap.add_argument("--local-pdk-root", required=True)
    ap.add_argument("--decks-out", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args(argv)
    args.decks_out.mkdir(parents=True, exist_ok=True)
    if si.sidecar_path(args.report).is_file():
        try:
            body = submitted_body(args.report, args.runner_pdk_root, args.local_pdk_root,
                                  args.decks_out)
        except si.IdentityError as exc:
            ap.error(str(exc))
    elif args.allow_unbound and args.body:
        print(f"fixup_batch_report: WARNING {args.report.name} is unbound; using --body "
              "(not necessarily what was submitted)", file=sys.stderr)
        body = args.body
    else:
        ap.error(f"{args.report} has no submission identity; refusing to substitute a "
                 "regenerated body. Redispatch in a new work dir, or pass --allow-unbound "
                 "--body for a legacy report")
    report = fixup(
        args.report, body, args.runner_pdk_root, args.local_pdk_root, args.decks_out
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
