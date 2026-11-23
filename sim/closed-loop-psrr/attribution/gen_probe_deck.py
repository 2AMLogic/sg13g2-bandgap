#!/usr/bin/env python3
"""Local single-corner DC-PSRR attribution probe deck generator (issue #631).

Emits a STANDALONE ngspice deck for ONE (process, temperature, supply) point
of sim/closed-loop-psrr's own committed bench body, plus optional variant
rewrites, so the vdd->vref supply-rejection paths can be attributed at the
worst corner (bcs/125 C/3.63 V, psrr_dc 59.685 dB in record
20261113-085406-9d568b91) with local `.op`/`.ac` probes -- exactly what the
dispatch hosts allow (single corner only; grids go to the batch fleet
through run_klt_sim.sh --batch).

What the deck is
----------------
`sim/closed-loop-psrr/testbench/closed_loop_psrr.body.spice.tmpl` is a
`klt sim` *body*: no `.lib` cards, no `.options temp=`, no `.end` (the
request supplies those). This generator instantiates that body EXACTLY as
`run_klt_sim.sh` does (same @@ token set, same seed lookup from
sim/closed-loop-startup's newest committed record, same XMSENSE w= read),
then adds ONLY:

  * the three corner `.lib` cards the legacy `run_pvt_sweep.sh` bench
    (tb_closed_loop_psrr.spice.tmpl) used to carry inline,
  * `.options temp=<T> tnom=27`,
  * `.end`,
  * three probe additions INSIDE the body's own `.control` block, right
    after `let psrr_db = -db(v(vref))`:
      - `show` -- the full device small-signal parameter dump (OSDI PSP103
        exposes gm/gds/gmb/ids/vgs/vds per instance; verified against
        ngspice 47 + psp103.osdi),
      - the complex 1 Hz (DC) response `vref_dc = v(vref)[0]`, its PSRR and
        phase, printed on one parseable line,
      - `wrdata` of the psrr_db curve so the probe keeps the same evidence
        shape as the committed bench.

Variants (see VARIANTS below) are line-rewrites of the instantiated body,
each a single bounded change. The quiet-rail ablations move one device
group's supply terminals to a second source Vvddq at the SAME DC potential
but ac 0, removing exactly that group's direct small-signal coupling to
vdd without moving the operating point.

Run the emitted deck with run_probe.sh (it stages the PDK's sibling
`sg13g2_*_mod.lib` includes ngspice resolves relative to its CWD).
"""

import argparse
import os
import re
import sys

REPO_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(REPO_HERE, "..", "..", "harness"))
from klt_corner_bundle import CORNER_LIBS, CORNER_SECTIONS  # noqa: E402  (#682)
from seed_deck import SEED_FIELDS, fill_deck, load_seeds, seed_row  # noqa: E402

# ---------------------------------------------------------------------------
# Variant transforms. Each entry: (one-line description, [functions]).
# A transform takes (lines, ctx) and returns rewritten lines; ctx carries
# vdd so quiet rails can hold the same DC potential.
# ---------------------------------------------------------------------------

def _quiet_rail(dev_pattern, desc_line):
    """Move every device line matching dev_pattern onto the ac-quiet rail.

    Rewrites occurrences of ' vdd vdd ' (source+bulk terminals of the
    sg13_hv_pmos wrapper) or a leading 'vdd ' drain feed (XRPU) to vddq,
    and (once per deck, handled by _QUIET_MARKER) appends the Vvddq source.
    """
    def fn(lines, ctx):
        n = 0
        for i, l in enumerate(lines):
            if re.match(dev_pattern, l):
                new = l.replace(" vdd vdd ", " vddq vddq ")
                new = new.replace("XRPU vdd ", "XRPU vddq ")
                if new != l:
                    lines[i] = new
                    n += 1
        if n == 0:
            sys.exit(f"gen_probe_deck.py: variant {desc_line!r}: no device "
                     f"line matched {dev_pattern!r}")
        return lines
    return fn


def _add_quiet_source(lines, ctx):
    if any("Vvddq" in l for l in lines):
        return lines
    hit = [i for i, l in enumerate(lines) if l.startswith("Vvdd ")]
    if len(hit) != 1:
        sys.exit("gen_probe_deck.py: Vvdd fixture line not found")
    lines.insert(hit[0] + 1,
                 "* probe: Vvddq is the ac-quiet twin of vdd (same DC "
                 "potential, no ripple)")
    lines.insert(hit[0] + 2,
                 f"Vvddq vddq 0 DC {ctx['vdd']} AC 0")
    return lines

def _scale_mos(devices, w_scale, l_scale, desc_line):
    """Scale the w AND l of each named sg13_hv_[pn]mos DUT instance.

    Numerically scales each device's own w/l (they differ: 8u/9u/10u/20u
    legs), so the rewrite cannot be a single regex substitution; it parses
    each line's own numbers. Fails closed if any expected line is missed or
    does not parse, and matches either supply rail (vdd or the quiet vddq),
    so it commutes with the quiet-* ablations.
    """
    pat = re.compile(r"^((X\S+) .* sg13_hv_[pn]mos )w=([0-9.]+)u l=([0-9.]+)u(.*)$")

    def fn(lines, ctx):
        seen = set()
        for i, l in enumerate(lines):
            name = l.split(" ", 1)[0]
            if name not in devices:
                continue
            m = pat.match(l)
            if not m:
                sys.exit("gen_probe_deck.py: variant %r: line %r does not"
                         " parse" % (desc_line, l))
            head, _, w, ln, tail_m = m.groups()
            lines[i] = "%sw=%.6gu l=%.6gu%s" % (
                head, w_scale * float(w), l_scale * float(ln), tail_m)
            seen.add(name)
        missing = sorted(set(devices) - seen)
        if missing:
            sys.exit("gen_probe_deck.py: variant %r: missed %s"
                     % (desc_line, missing))
        return lines
    return fn


def _loop_gain_break(desc_line):
    """Rewrite the closed-loop PSRR body into the loop-gain bench's topology.

    The SAME Middlebrook single-injection break sim/loop-gain-phase-margin/
    testbench/tb_loop_gain.spice.tmpl uses, applied to this generator's own
    instantiated body: fb split into fb_src (the amp's own output: XMP4/XMN3
    drains, XMTAIL gate) and fb_load (the core mirror gates + the startup
    ammeter), joined by Lbreak 1e9 H with Vtest 1V AC in series, the vdd AC
    stimulus removed, and the control block's psrr tail replaced by the
    loop-gain tail (T = v(fb_src)/v(fb_load), the bench's own sign
    convention). Crossover/PM/solve-quality are then read with the bench's
    own tools (find_crossover.awk, solve_quality.py) -- see run_probe.sh.
    """
    def fn(lines, ctx):
        head = [
            (r"^print v\(fb\)$", "print v(fb_load)"),
            (r"^(\.nodeset )v\(fb\)=([0-9.eE+-]+)",
             r"\1v(fb_load)=\2 v(fb_src)=\2"),
            (r"^(\.save )v\(fb\) ", r"\1v(fb_load) v(fb_src) "),
            (r"^Vvdd vdd 0 DC [0-9.]+ AC 1 0$", "Vvdd vdd 0 DC %s" % ctx["vdd"]),
            (r"^(XM1 sns1) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XM2A sns2) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XM2B sns2) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XM3A vref) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XM3B vref) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XM3C vref) fb( vdd)", r"\1 fb_load\2"),
            (r"^(XMTAIL tail) fb( vdd)", r"\1 fb_src\2"),
            (r"^XMP4 fb pn ", "XMP4 fb_src pn "),
            (r"^XMN3 fb d1 ", "XMN3 fb_src d1 "),
            (r"^Vmkfb fb fbx ", "Vmkfb fb_load fbx "),
        ]
        for pat, repl in head:
            hits = [i for i, l in enumerate(lines) if re.match(pat, l)]
            if len(hits) != 1:
                sys.exit("gen_probe_deck.py: loop-gain %r: pattern %r matched"
                         " %d lines (need exactly 1)"
                         % (desc_line, pat, len(hits)))
            lines[hits[0]] = re.sub(pat, repl, lines[hits[0]])
        # control tail: the psrr response becomes the loop-gain response
        tail = ["ac dec 30 1 1e9", "let psrr_db = -db(v(vref))",
                "print psrr_db"]
        new_tail = [
            "ac dec 30 1 1e9",
            "let loopgain_db = db(v(fb_src)/v(fb_load))",
            "let loopgain_ph = cph(v(fb_src)/v(fb_load))*180/PI",
            "wrdata ${AC_OUT} loopgain_db loopgain_ph",
        ]
        idx = [i for i, l in enumerate(lines) if l in tail]
        # each tail line must appear exactly once (the body's control block)
        if sorted(lines[i] for i in idx) != sorted(tail):
            sys.exit("gen_probe_deck.py: loop-gain %r: psrr control tail not"
                     " found intact" % desc_line)
        lines[idx[0]:idx[-1] + 1] = new_tail
        # loop-break fixture after the ground reference
        gnd = [i for i, l in enumerate(lines)
               if l.startswith("Vsub sub! ")]
        if len(gnd) != 1:
            sys.exit("gen_probe_deck.py: loop-gain %r: Vsub fixture not found"
                     % desc_line)
        lines[gnd[0] + 1:gnd[0] + 1] = [
            "* probe: Middlebrook loop break, same as the loop-gain bench",
            "Lbreak fb_src brk 1e9",
            "Vtest brk fb_load dc 0 ac 1 0",
        ]
        return lines
    return fn

# DUT device groups for the resize variants (instance names as in the body).
CORE_PMOS = ("XM1", "XM2A", "XM2B", "XM3A", "XM3B", "XM3C")
AMP_NMOS = ("XMN1", "XMN2", "XMN3", "XMN4")
AMP_P12 = ("XMP1", "XMP2")
AMP_P34 = ("XMP3", "XMP4")
AMP_TAIL = ("XMTAIL",)
ALL_PMOS = CORE_PMOS + AMP_TAIL + AMP_P12 + AMP_P34


VARIANTS = {
    "asbuilt": ("the committed DUT, unchanged (baseline)", []),
    'xmn435': (
                "PR #435's unmerged amp NMOS-mirror resize: XMN1-4 w=10u l=1u -> "
        "w=40u l=4u (feature/issue-303 tip 50c460f, only electrical change "
        "in that PR's design/ diff)",
        [_scale_mos(AMP_NMOS, 4, 4, 'xmn435')]),
    "quiet-core": (
        "ablation: core PMOS mirror legs XM1, XM2A/B, XM3A/B/C moved to the "
        "ac-quiet rail (removes the core mirror's direct vdd coupling; the "
        "amp, startup and bipolars keep seeing ripple)",
        [_quiet_rail(r"^XM(1|2A|2B|3A|3B|3C) ", "quiet-core"),
         _add_quiet_source]),
    "quiet-amp": (
        "ablation: amp supply devices XMTAIL, XMP1-XMP4 (sources/bulks) "
        "moved to the ac-quiet rail (removes the amplifier's own vdd "
        "coupling; core and startup keep seeing ripple)",
        [_quiet_rail(r"^XM(TAIL|P1|P2|P3|P4) ", "quiet-amp"),
         _add_quiet_source]),
    "quiet-startup": (
        "ablation: startup pull-up XRPU fed from the ac-quiet rail (removes "
        "the startup branch's vdd coupling; core and amp keep seeing ripple)",
        [_quiet_rail(r"^XRPU ", "quiet-startup"),
         _add_quiet_source]),
    "quiet-tail": (
        "sub-ablation: only the amp tail XMTAIL on the ac-quiet rail",
        [_quiet_rail(r"^XMTAIL ", "quiet-tail"),
         _add_quiet_source]),
    "quiet-p34": (
        "sub-ablation: only the amp output mirror XMP3/XMP4 on the "
        "ac-quiet rail",
        [_quiet_rail(r"^XMP[34] ", "quiet-p34"),
         _add_quiet_source]),
    "quiet-p12": (
        "sub-ablation: only the amp input pair bulks XMP1/XMP2 on the "
        "ac-quiet rail",
        [_quiet_rail(r"^XMP[12] ", "quiet-p12"),
         _add_quiet_source]),
    "quiet-all": (
        "ablation: core + amp + startup all on the ac-quiet rail (no vdd "
        "coupling should remain; the method's null control -- PSRR must "
        "collapse to the solver floor)",
        [_quiet_rail(r"^XM(1|2A|2B|3A|3B|3C|TAIL|P1|P2|P3|P4) ", "quiet-all"),
         _quiet_rail(r"^XRPU ", "quiet-all"),
         _add_quiet_source]),
    'corepmos-l2': (
                "fix candidate: core PMOS mirror legs at double length, double W "
        "(same current density and Vgs): XM1 20u/2u, XM2A 18u/2u, XM2B "
        "2u/2u, XM3A 16u/2u, XM3B 2u/2u, XM3C 2u/2u",
        [_scale_mos(CORE_PMOS, 2, 2, 'corepmos-l2')]),
    'corepmos-l4': (
                "fix candidate: core PMOS mirror legs at quadruple length, "
        "quadruple W: XM1 40u/4u, XM2A 36u/4u, XM2B 4u/4u, XM3A 32u/4u, "
        "XM3B 4u/4u, XM3C 4u/4u",
        [_scale_mos(CORE_PMOS, 4, 4, 'corepmos-l4')]),
    'xmp34-l2': (
                "fix candidate: amp PMOS mirror XMP3/XMP4 at double length, double "
        "W: 10u/1u -> 20u/2u (amp supply coupling + loop-gain term)",
        [_scale_mos(AMP_P34, 2, 2, 'xmp34-l2')]),
    'xmp34-l4': (
                "fix candidate: amp PMOS mirror XMP3/XMP4 at quadruple length, "
        "quadruple W: 10u/1u -> 40u/4u",
        [_scale_mos(AMP_P34, 4, 4, 'xmp34-l4')]),
    'tail-l2': (
                "fix candidate: amp tail XMTAIL at double length, double W: "
        "10u/1u -> 20u/2u",
        [_scale_mos(AMP_TAIL, 2, 2, 'tail-l2')]),
    'tail-l4': (
                "fix candidate: amp tail XMTAIL at quadruple length, quadruple W: "
        "10u/1u -> 40u/4u",
        [_scale_mos(AMP_TAIL, 4, 4, 'tail-l4')]),
    'p12-l2': (
                "fix candidate: amp input pair XMP1/XMP2 at double length, double "
        "W: 20u/1u -> 40u/2u (same Vgs/current; raises the pair's ro and "
        "with it the amp's DC gain, at the cost of a slower d1/d2 node)",
        [_scale_mos(AMP_P12, 2, 2, 'p12-l2')]),
    'p12-w2': (
                "fix candidate: amp input pair XMP1/XMP2 at double W, same L: "
        "20u/1u -> 40u/1u (more gm at the pair's fixed tail current; the "
        "d1/d2 node capacitance doubles but the node keeps l=1u devices)",
        [_scale_mos(AMP_P12, 2, 1, 'p12-w2')]),
    'p12-w3': (
                "fix candidate: amp input pair XMP1/XMP2 at triple W, same L: "
        "20u/1u -> 60u/1u (between p12-w2 and the PM-dead p12-w4)",
        [_scale_mos(AMP_P12, 3, 1, 'p12-w3')]),
    'p12-w4': (
                "fix candidate: amp input pair XMP1/XMP2 at quadruple W, same L: "
        "20u/1u -> 80u/1u (the p12-w2 knob taken one step further)",
        [_scale_mos(AMP_P12, 4, 1, 'p12-w4')]),
    'xmp34-w2': (
                "fix candidate: amp output mirror XMP3/XMP4 at double W, same L: "
        "10u/1u -> 20u/1u (stiffer pn follower, more gm4; the pn pole "
        "drops only ~1.5x, not the 4x of the l=2u scaling)",
        [_scale_mos(AMP_P34, 2, 1, 'xmp34-w2')]),
    'allpmos-l2': (
                "fix candidate: EVERY sg13_hv_pmos supply device in the DUT at "
        "double length and double W (core mirror legs, amp tail, input "
        "pair, output mirror): same current density and Vgs everywhere, "
        "lower gds on every vdd-coupled device at once -- the one-knob "
        "version of shrinking all supply-coupling terms together instead "
        "of rebalancing their cancellation",
        [_scale_mos(ALL_PMOS, 2, 2, 'allpmos-l2')]),
}

def newest_seed_csv():
    startup_records = os.path.join(REPO_HERE, "..", "..",
                                   "closed-loop-startup", "records")
    cands = sorted(f for f in os.listdir(startup_records)
                   if f.endswith(".csv"))
    if not cands:
        sys.exit("gen_probe_deck.py: no closed-loop-startup records")
    return os.path.join(startup_records, cands[-1])


def msense_w():
    path = os.path.join(REPO_HERE, "..", "..", "..", "design", "netlist",
                        "bandgap_startup.spice")
    text = open(path).read()
    m = re.search(r"^XMSENSE .*\bw=([0-9.]+u)\b.*$",
                  text, re.M)
    if not m:
        sys.exit("gen_probe_deck.py: XMSENSE w= not found")
    return m.group(1)



def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corner", required=True, choices=sorted(CORNER_SECTIONS))
    ap.add_argument("--temp", required=True, type=float)
    ap.add_argument("--vdd", required=True, type=float)
    ap.add_argument("--variant", default="asbuilt",
                    help="variant name, or several '+'-composed (e.g. "
                         "corepmos-l2+quiet-amp); choices: %s"
                         % ", ".join(sorted(VARIANTS)))
    ap.add_argument("--pdk-root", default=os.environ.get("PDK_ROOT", ""))
    ap.add_argument("--token-paths", action="store_true",
                    help="emit ${PDK_ROOT} tokens instead of the resolved "
                         "path (for decks committed as evidence)")
    ap.add_argument("--loop-gain", action="store_true",
                    help="emit the loop-gain probe instead of the PSRR "
                         "probe: the same Middlebrook fb break "
                         "sim/loop-gain-phase-margin uses (T = "
                         "v(fb_src)/v(fb_load)), for stability checks on "
                         "the variants")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    if not args.token_paths and not args.pdk_root:
        sys.exit("gen_probe_deck.py: --pdk-root or $PDK_ROOT required")

    tmpl_path = os.path.join(REPO_HERE, "..", "testbench",
                             "closed_loop_psrr.body.spice.tmpl")
    text = open(tmpl_path).read()

    seed_csv = newest_seed_csv()
    seed = seed_row(load_seeds(seed_csv), args.corner, f"{args.temp:g}",
                    f"{args.vdd:.2f}", seed_csv)
    pdk = "ihp-sg13g2"
    osdi = "${PDK_ROOT}/%s/libs.tech/ngspice/osdi" % pdk if args.token_paths \
        else "%s/%s/libs.tech/ngspice/osdi" % (args.pdk_root, pdk)
    models = "${PDK_ROOT}/%s/libs.tech/ngspice/models" % pdk \
        if args.token_paths else \
        "%s/%s/libs.tech/ngspice/models" % (args.pdk_root, pdk)

    mapping = {"@@OSDI_DIR@@": osdi, "@@VDD@@": "%.2f" % args.vdd,
               "@@MSENSE_W@@": msense_w()}
    mapping.update({tok: seed[col] for tok, col in SEED_FIELDS})
    text = fill_deck(text, mapping, "body")

    # probe additions inside the body's own .control block (PSRR mode only;
    # loop-gain mode swaps the control tail wholesale in _loop_gain_break)
    if not args.loop_gain:
        probe_ctl = (
            "* ---- attribution probe additions (issue #631) ----\n"
            "* full device small-signal dump (OSDI PSP103 gm/gds/gmb/ids)\n"
            "show\n"
            "* complex DC (1 Hz) response: PSRR and phase on one line\n"
            "let vref_dc = v(vref)[0]\n"
            "let psrr_dc_probe_db = -db(vref_dc)\n"
            "let vref_dc_phase_deg = 180*cph(vref_dc)/pi\n"
            "print psrr_dc_probe_db vref_dc_phase_deg\n"
            "wrdata ${AC_OUT} psrr_db\n")
        anchor = "let psrr_db = -db(v(vref))\n"
        if text.count(anchor) != 1:
            sys.exit("gen_probe_deck.py: control-block anchor not found")
        text = text.replace(anchor, anchor + probe_ctl)

        # Total block supply current (the Iq row's quantity,
        # sim/closed-loop-iq's iq_avg_a), printed at the DC op -- BEFORE the
        # ac sweep so the vector is the op point's, not a per-frequency AC
        # value. The body's resident-vector .save list does not carry it, so
        # the probe deck widens that list by one.
        iq_anchor = "print i(Vmkfb)\n"
        if text.count(iq_anchor) != 1:
            sys.exit("gen_probe_deck.py: i(Vmkfb) anchor not found")
        text = text.replace(iq_anchor, iq_anchor + "print i(Vvdd)\n")
        save_anchor = ".save v(fb) v(sns1) v(sns2) v(vref) v(det) i(Vmkfb)\n"
        if text.count(save_anchor) != 1:
            sys.exit("gen_probe_deck.py: .save anchor not found")
        text = text.replace(save_anchor,
                            save_anchor.rstrip("\n") + " i(Vvdd)\n")

    # Variant transforms on the line level. --variant accepts a
    # '+'-composed list (e.g. corepmos-l2+quiet-amp): applied left to
    # right, so an ablation can be stacked ON TOP of a fix candidate to
    # measure that candidate's remaining single-path magnitude.
    names = args.variant.split("+")
    descs = []
    transforms = []
    for name in names:
        if name not in VARIANTS:
            sys.exit("gen_probe_deck.py: unknown variant %r (have %s)"
                     % (name, ", ".join(sorted(VARIANTS))))
        d, t = VARIANTS[name]
        descs.append(d)
        transforms.extend(t)
    if args.loop_gain:
        transforms.append(_loop_gain_break("loop-gain probe"))
        descs.append("loop-gain break (Middlebrook, as the loop-gain bench)")
    lines = text.splitlines()
    ctx = {"vdd": "%.2f" % args.vdd}
    for fn in transforms:
        lines = fn(lines, ctx)
    text = "\n".join(lines) + "\n"

    # corner libs + temp + .end (the body itself has none of these)
    libs = "".join('.lib "%s/%s" %s\n' % (models, lib, sec)
                   for lib, sec in zip(CORNER_LIBS, CORNER_SECTIONS[args.corner]))
    text += (
        "\n* ---- standalone-probe wrap (issue #631; the klt sim request "
        "supplies these in the harness path) ----\n"
        + libs +
        ".options temp=%s tnom=27\n"
        ".end\n"
        % ("%g" % args.temp))

    text = text.replace("${AC_OUT}",
                        os.path.abspath(args.output) + ".ac.txt")

    header = (
        "* sg13g2-bandgap -- sim/closed-loop-psrr/attribution local probe "
        "(issue #631)\n"
        "* corner=%s temp=%gC vdd=%.2fV variant=%s\n"
        "* variant description: %s\n"
        "* generated by sim/closed-loop-psrr/attribution/gen_probe_deck.py "
        "from the committed bench body\n"
        "* (testbench/closed_loop_psrr.body.spice.tmpl); seeds from %s\n"
        % (args.corner, args.temp, args.vdd, args.variant, " + ".join(descs),
           os.path.basename(seed_csv)))

    with open(args.output, "w") as fh:
        fh.write(header + text)
    print("wrote %s (corner=%s temp=%g vdd=%.2f variant=%s)"
          % (args.output, args.corner, args.temp, args.vdd, args.variant),
          file=sys.stderr)


if __name__ == "__main__":
    main()
