#!/usr/bin/env bash
# Shared PVT closed-loop pass-criteria constants and verdict logic, sourced
# (not executed) by six experiments' run_pvt_sweep.sh under sim/*/ --
# sim/closed-loop-iq, sim/closed-loop-startup,
# sim/sg13cmos5l-closed-loop-startup, sim/sg13cmos5l-closed-loop-startup-pex,
# sim/closed-loop-vref-pvt and sim/startup-core-handover. Extracted in issue
# #114 because the four tolerance constants below were byte-identical (where
# used) across all six, and the startup_released/loop_closed/not_railed[/
# settled] verdict awk formula was duplicated near-identically across five
# of the six (every one of them except sim/startup-core-handover, whose
# testbench co-simulates only core+startup -- no amplifier, hence no sns2/fb
# loop to close or rail-margin to check, hence no shared verdict call there;
# see that script's own smaller inline awk). Same shape of duplication
# sim/lib/pvt_preflight.sh (#28/#103), sim/lib/msense_width.sh (#105/#107)
# and sim/lib/pvt_sed_common.sh (#108/#109) were extracted to fix.
#
# Caller contract:
#   - Source this AFTER sim/lib/pvt_preflight.sh -- matches the sourcing
#     order every other sim/lib/*.sh file in this tree uses, though this
#     file's own contents do not themselves reach into pvt_preflight.sh's
#     variables.
#   - Source this file directly from the experiment script's top level
#     (matches sim/lib/pvt_sed_common.sh's convention) -- pvt_closed_loop_
#     verdict() below needs no `${BASH_SOURCE[1]}` caller-identity trick, so
#     unlike sim/lib/msense_width.sh this is not load-bearing here, but
#     keeping the convention uniform across sim/lib/*.sh avoids a
#     special-cased exception a future reader would have to notice.
#   - Call `pvt_closed_loop_verdict det_v i_mkfb_a fb_v dvsns_v vdd
#     [sdelta sdelta_thresh]` once per PVT point, after computing dvsns_v
#     (the |sns1-sns2| loop-closure residual) yourself -- that one-line abs
#     diff remains the caller's own (it differs only in which two measured
#     signals it diffs, not in a way worth sharing). Omit the trailing
#     sdelta/sdelta_thresh pair entirely for a 3-criteria verdict (the three
#     closed-loop-startup* variants, whose own startup-release check is
#     itself the settledness claim); pass both for a 4-criteria verdict that
#     additionally ANDs in an experiment-specific settledness bound
#     (closed-loop-iq's Iq-settling check, closed-loop-vref-pvt's
#     vref-settling check).
#
# Provides on return:
#   DET_RELEASE_FRAC, I_MKFB_RELEASE_A, DVSNS_CLOSE_V, FB_RAIL_MARGIN_V --
#     the four tolerance constants (see rationale below)
#   pvt_closed_loop_verdict() function -- see its own header comment below
#
# Callers still own everything else: their own signal-specific `.measure`
# extraction (the `iq_*`/`vref_*` measurements, TC computation), the
# dvsns_v abs-diff, and their own records/*.md narrative -- none of that is
# shared here on purpose (it differs substantively per experiment).
#
# Pass criteria -- three independent claims, all required, at the end of
# the transient (fully ramped + settled):
#   1. Startup released: v(det) <= DET_RELEASE_FRAC*vdd (same release sense
#      sim/startup-trip-point and sim/startup-core-handover use) AND
#      |i(XMKFB)| <= I_MKFB_RELEASE_A (1% of the ~5 uA/leg open-loop design
#      current).
#   2. Loop closed: |sns1 - sns2| <= DVSNS_CLOSE_V -- the amplifier's whole
#      job is forcing these two nodes equal; a finite-gain single-stage OTA
#      cannot make them exactly equal, so this is a loop-closure tolerance,
#      not a spec claim. 20 mV is a generous bound relative to the ~55 mV
#      dVBE(Q1,Q2) design swing (roughly 3x the ~0.4-7 mV residual measured
#      in this schematic's own dev-time nominal-corner check) -- loose
#      enough to tolerate real PVT-driven loop-gain variation, tight enough
#      that a genuinely unclosed loop (e.g. a polarity bug making this
#      positive feedback) fails it.
#   3. Not railed: fb sits strictly inside (vss, vdd), away from either
#      supply rail by at least FB_RAIL_MARGIN_V -- confirms the amplifier
#      found a real interior equilibrium (a working negative-feedback
#      servo) rather than saturating to one supply (what a positive-
#      feedback/polarity-bug loop would do instead).
#
# A caller ANDing in a fourth, experiment-specific settledness claim passes
# its own sdelta (the measured delta between two time points) and
# sdelta_thresh (that experiment's own tolerance, e.g. closed-loop-iq's
# SETTLE_TOL_A or closed-loop-vref-pvt's SETTLE_TOL_V) -- see each caller's
# own comment for that constant's rationale, kept local to the caller since
# it is not shared across all six scripts the way the four constants below
# are.
DET_RELEASE_FRAC="0.2"
I_MKFB_RELEASE_A="50e-9"
DVSNS_CLOSE_V="0.020"
FB_RAIL_MARGIN_V="0.05"

# pvt_closed_loop_verdict DET_V I_MKFB_A FB_V DVSNS_V VDD [SDELTA SDELTA_THRESH]
#   Prints PASS or FAIL (matching every caller's own pre-extraction verdict
#   string) to stdout, for a single PVT point, given that point's own
#   measured det/i_mkfb/fb/dvsns values and vdd. SDELTA/SDELTA_THRESH are
#   optional (see caller contract above); when omitted, both awk-side
#   variables are left unset, "" <= "" (both operands non-numeric-looking
#   strnums) compares true, and the settledness term is a no-op -- exactly
#   the 3-criteria verdict the closed-loop-startup* variants compute today.
#
#   Callers still compute rc/model_error/-z-emptiness FAIL checks themselves
#   before calling this (those differ slightly per script in which signals
#   they check for emptiness) -- this function only wraps the final awk
#   formula, matching sim/lib/pvt_sed_common.sh's common_pvt_sed_args(),
#   which likewise wraps only the shared portion of its callers' `sed` call.
pvt_closed_loop_verdict() {
  local det_v="$1" i_mkfb_a="$2" fb_v="$3" dvsns_v="$4" vdd="$5"
  local sdelta="${6:-}" sdelta_thresh="${7:-}"
  awk -v det_v="${det_v}" -v i_mkfb_a="${i_mkfb_a}" \
      -v vdd="${vdd}" -v det_frac="${DET_RELEASE_FRAC}" -v i_thresh="${I_MKFB_RELEASE_A}" \
      -v dvsns="${dvsns_v}" -v dvsns_thresh="${DVSNS_CLOSE_V}" \
      -v fb="${fb_v}" -v rail_margin="${FB_RAIL_MARGIN_V}" \
      -v sdelta="${sdelta}" -v sdelta_thresh="${sdelta_thresh}" \
    'BEGIN{
       i_abs = (i_mkfb_a < 0) ? -i_mkfb_a : i_mkfb_a;
       startup_released = (det_v <= det_frac*vdd) && (i_abs <= i_thresh);
       loop_closed = (dvsns <= dvsns_thresh);
       not_railed = (fb >= rail_margin) && (fb <= vdd - rail_margin);
       settled = (sdelta <= sdelta_thresh);
       ok = startup_released && loop_closed && not_railed && settled;
       print ok ? "PASS" : "FAIL";
     }'
}
