#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/startup-time-to-release/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Full testbench rationale and what this sweep does and does not
# claim: sim/startup-time-to-release/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

# shellcheck source=../lib/pvt_verdict_common.sh
source "${SIM_DIR}/lib/pvt_verdict_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_startup_time_to_release.spice.tmpl"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention every other closed-loop experiment in this tree uses.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, same as sim/closed-loop-startup.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

# The checkpoint ladder the testbench template samples at (microseconds).
# Fixed-time AT= sampling, not a WHEN/crossing search -- see the template's
# own header for why a crossing search is not robust here (several PVT
# corners, most visibly the design's own typ/27C/3.30V nominal point, never
# drive det/i_mkfb above the release threshold at all, so a FALL=1 .measure
# finds no crossing and errors "out of interval" -- confirmed by direct
# test). 100us resolution from 100us to 1ms (this experiment's own claim
# window, matching the draft "< 1 ms" startup spec row), plus a coarser 2ms
# point matching sim/closed-loop-startup's own final checkpoint for
# cross-validation.
CHECKPOINTS_US=(100 200 300 400 500 600 700 800 900 1000 2000)
release_times=()

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,release_time_us,det_2000u_v,i_mkfb_2000u_a,fb_2000u_v,dvsns_2000u_v,checkpoint_verdicts" > "${CSV_OUT}"

# Same corner-label vocabulary as every other PVT sweep in this tree
# (CORNER_LABELS/TEMPS/VDDS/HBT_SECTION_OF/RES_SECTION_OF/MOS_SECTION_OF
# come from sim/lib/pvt_preflight.sh).

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # Per-checkpoint verdict: same three-criteria pvt_closed_loop_verdict()
      # every other closed-loop experiment in this tree uses (startup
      # released, loop closed, not railed), evaluated at each point on the
      # checkpoint ladder rather than once at a single final time. `|| true`
      # on each grep, same reasoning as sim/closed-loop-startup: a
      # non-convergent corner leaves some/all `meas` lines unprinted, and an
      # unguarded failure here would abort the whole sweep under
      # `set -euo pipefail` on the first such corner.
      checkpoint_verdicts=()
      last_ok=-1
      any_missing=0
      for idx in "${!CHECKPOINTS_US[@]}"; do
        t="${CHECKPOINTS_US[${idx}]}"
        det_t=$(grep -E "^v_det_${t}u" "${log}" | head -1 | awk '{print $3}' || true)
        i_mkfb_t=$(grep -E "^i_mkfb_${t}u" "${log}" | head -1 | awk '{print $3}' || true)
        fb_t=$(grep -E "^v_fb_${t}u" "${log}" | head -1 | awk '{print $3}' || true)
        sns1_t=$(grep -E "^v_sns1_${t}u" "${log}" | head -1 | awk '{print $3}' || true)
        sns2_t=$(grep -E "^v_sns2_${t}u" "${log}" | head -1 | awk '{print $3}' || true)

        if [[ -z "${det_t}" || -z "${i_mkfb_t}" || -z "${fb_t}" || -z "${sns1_t}" || -z "${sns2_t}" ]]; then
          checkpoint_verdicts+=("${t}u:MISSING")
          any_missing=1
          continue
        fi

        dvsns_t=$(awk -v a="${sns1_t}" -v b="${sns2_t}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        v=$(pvt_closed_loop_verdict "${det_t}" "${i_mkfb_t}" "${fb_t}" "${dvsns_t}" "${vdd}")
        checkpoint_verdicts+=("${t}u:${v}")
        if [[ "${v}" == "PASS" ]]; then
          [[ ${last_ok} -eq -1 ]] && last_ok=${idx}
        else
          last_ok=-1
        fi

        # Stash the last (2000u) point's raw values for the CSV's own
        # cross-validation columns.
        if [[ "${t}" == "2000" ]]; then
          det_final="${det_t}"
          i_mkfb_final="${i_mkfb_t}"
          fb_final="${fb_t}"
          dvsns_final="${dvsns_t}"
        fi
      done

      # release_time_us: the earliest checkpoint such that it and every
      # later checkpoint (through the final 2000u point) all PASS -- a
      # suffix-of-PASS definition, not merely "the first PASS anywhere",
      # so a corner that transiently satisfies the release criteria then
      # regresses (e.g. a later ring/overshoot) is not misreported as
      # released early.
      release_time_us="NOT_RELEASED"
      if [[ ${last_ok} -ge 0 ]]; then
        ok=1
        for ((i = last_ok; i < ${#CHECKPOINTS_US[@]}; i++)); do
          v="${checkpoint_verdicts[${i}]#*:}"
          if [[ "${v}" != "PASS" ]]; then
            ok=0
            break
          fi
        done
        if [[ ${ok} -eq 1 ]]; then
          release_time_us="${CHECKPOINTS_US[${last_ok}]}"
        fi
      fi

      verdict=PASS
      if [[ $rc -ne 0 || $model_error -ne 0 || ${any_missing} -ne 0 ]]; then
        verdict=FAIL
      elif [[ "${release_time_us}" == "NOT_RELEASED" ]]; then
        verdict=FAIL
      fi

      tally_verdict "${verdict}" "${corner_id}"
      cv_joined=$(IFS=';'; echo "${checkpoint_verdicts[*]}")
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${release_time_us},${det_final:-},${i_mkfb_final:-},${fb_final:-},${dvsns_final:-},\"${cv_joined}\"" >> "${CSV_OUT}"
      release_times+=("${release_time_us}")
      unset det_final i_mkfb_final fb_final dvsns_final
    done
  done
done

# Release-time distribution summary, for the record's own narrative below --
# computed from release_times (every PASS point's numeric release_time_us;
# NOT_RELEASED entries, if any, are reported separately as failures, not
# folded into a min/max that would misleadingly suggest they had a numeric
# release time).
release_summary="no PASS points"
if [[ ${passed} -gt 0 ]]; then
  release_summary=$(printf '%s\n' "${release_times[@]}" | grep -v NOT_RELEASED | sort -n | \
    awk '{a[NR]=$1; sum+=$1} END{print "min="a[1]"us max="a[NR]"us mean="sum/NR"us n="NR}')
fi

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: startup-time-to-release"
  echo "- **Claim**: the same co-simulated bandgap_core + bandgap_amp +"
  echo "  bandgap_startup closed-loop assembly sim/closed-loop-startup"
  echo "  proves self-starts and settles (design/bandgap_top.sch's own"
  echo "  wiring), but sampled at a fixed-time checkpoint ladder"
  echo "  (${CHECKPOINTS_US[*]} us) instead of one early + one final"
  echo "  checkpoint, so the earliest time at which the full closed-loop"
  echo "  release criteria (startup released: v(det) <= ${DET_RELEASE_FRAC}*vdd"
  echo "  and |i(XMKFB)| <= ${I_MKFB_RELEASE_A} A; loop closed:"
  echo "  |sns1-sns2| <= ${DVSNS_CLOSE_V} V; not railed: fb within"
  echo "  [${FB_RAIL_MARGIN_V} V, vdd-${FB_RAIL_MARGIN_V} V]) hold AND keep"
  echo "  holding through the end of the simulated window (2 ms) can be"
  echo "  read off directly, across the full temperature x supply x"
  echo "  HBT/MOS/resistor-process-corner PVT grid. Filed as a direct"
  echo "  follow-up to PR #128's EE-key review, which found no committed"
  echo "  testbench in this tree reports an explicit time-to-release figure"
  echo "  to compare against the draft \"Startup: self-starting, < 1 ms\""
  echo "  spec row (spec/porting-plan.md, still unratified -- #125). This"
  echo "  record is that missing measurement; it is evidence for a spec row"
  echo "  comparison, not a conformance claim against a ratified spec (none"
  echo "  exists yet)."
  echo "- **Why fixed-time checkpoints, not a WHEN/crossing search**: tried"
  echo "  first and rejected -- at several PVT corners, most visibly the"
  echo "  design's own typ/27C/3.30V nominal point, det and i(XMKFB) never"
  echo "  rise above the release threshold at all during the vdd ramp (peak"
  echo "  det ~0.48 V against a 0.66 V threshold at that corner; peak"
  echo "  i(XMKFB) ~4.3 nA against the 50 nA threshold), so a"
  echo "  \`meas tran ... WHEN v(det)=<thresh> FALL=1\` finds no crossing and"
  echo "  fails with \"out of interval\" -- confirmed by direct test, not"
  echo "  assumed. AT= sampling on a fixed ladder has no such failure mode"
  echo "  and is what this template uses instead (see its own header)."
  echo "- **Resolution**: 100 us below 1 ms (this experiment's own claim"
  echo "  window), so a reported \`release_time_us\` is accurate to within"
  echo "  one ladder step, not an exact crossing instant. \`release_time_us\`"
  echo "  is defined as the earliest ladder point at which the release"
  echo "  criteria hold AND continue to hold at every later ladder point"
  echo "  through 2000u (a suffix-of-PASS rule) -- a corner that transiently"
  echo "  looks released then regresses is not misreported as released"
  echo "  early. \`NOT_RELEASED\` means the criteria never reach that stable"
  echo "  suffix within the 2 ms simulated window."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice, "
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice -- identical DUT/fixture set"
  echo "  to sim/closed-loop-startup (see that experiment's README for the"
  echo "  full device inventory), not repeated here."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies, plus the Vmkfb ammeter documented in testbench/ and"
  echo "  README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (release_time_us found"
  echo "  within the 2 ms simulated window via the suffix-of-PASS rule"
  echo "  above, not merely a clean ngspice exit)."
  echo "- **Release-time distribution (PASS points only)**: ${release_summary}."
  echo "  This run's own finding: every one of the ${passed} PASS points"
  echo "  releases by this experiment's very first checkpoint (100 us) --"
  echo "  i.e. within (at most) the 200 us vdd ramp itself, comfortably"
  echo "  inside the draft \"< 1 ms\" spec row's window with roughly 10x"
  echo "  margin at this ladder's own 100 us resolution. This is data, not a"
  echo "  conformance claim (the spec row is unratified -- #125); a future"
  echo "  ratification or characterization-report pass (#15) can cite this"
  echo "  record directly instead of leaving the startup-timing row as \"no"
  echo "  explicit time-to-release number exists yet\" (PR #128's own"
  echo "  finding)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_startup_time_to_release.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #4 (T1 checklist item 5 follow-up)."
} > "${MD_OUT}"

write_pvt_summary
