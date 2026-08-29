#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/loop-gain-phase-margin/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds, AND at least one committed sim/closed-loop-startup/records/*.csv
# (this experiment reads that experiment's own most recent record for its
# per-corner .nodeset DC-bias seed values -- see README.md "Nodeset
# provenance"; a fresh sim/closed-loop-startup/run_pvt_sweep.sh run is NOT
# required if a committed record already exists, which it does in this repo).
#
# Full testbench rationale and what this sweep does and does not claim:
# sim/loop-gain-phase-margin/README.md.
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

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_loop_gain.spice.tmpl"
CROSSOVER_AWK="${EXPERIMENT_DIR}/tools/find_crossover.awk"

# XMSENSE's W is read from the live design/netlist/bandgap_startup.spice,
# same convention every closed-loop experiment in this tree uses.
# shellcheck source=../lib/msense_width.sh
source "${SIM_DIR}/lib/msense_width.sh"
read_msense_width "design/netlist/bandgap_startup.spice"

# shellcheck source=../lib/nodeset_seed.sh
source "${SIM_DIR}/lib/nodeset_seed.sh"

# preflight derives DUT_GIT_SHA from DUT_NETLIST (bandgap_core.spice); this
# experiment co-simulates three DUTs, so alias it as the core half and
# compute the amp/startup halves' SHAs separately.
alias_dut_git_shas AMP=design/netlist/bandgap_amp.spice STARTUP=design/netlist/bandgap_startup.spice

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,msense_w,status,fb_seed_v,fb_op_v,sns1_op_v,sns2_op_v,vref_op_v,dc_gain_db,crossover_hz,phase_margin_deg,n_crossings,notch_min_db,notch_min_hz,notch_margin_flag" > "${CSV_OUT}"

# Pass criteria:
#   1. .op converged near its own .nodeset seed (|fb_op - fb_seed| <=
#      OP_MATCH_TOL_V) -- confirms the DC bias this AC analysis linearizes
#      around is the intended closed-loop equilibrium, not the degenerate
#      one (see README "op landed near its seed").
#   2. Either a falling 0 dB crossing was found in the swept range (1 Hz-
#      1 GHz), OR the sweep's own resonant gain notch (see
#      tools/find_crossover.awk's notch_min_db, README "Multiple 0 dB
#      crossings") sits within +-NOTCH_GUARD_DB of 0 dB -- i.e. it is
#      "marginal": too close to 0 dB for a single AC sweep to reliably
#      resolve which side of 0 dB it truly sits on. A notch that clearly
#      misses 0 dB by more than the guard band (no crossing AND the notch
#      minimum is not marginal) still fails outright -- see issue #146.
#   3. If a crossing WAS found, phase margin at that crossing must be
#      > PM_MIN_DEG -- the hard stability bar (PM <= 0 means the loop is
#      not unconditionally stable at this corner) -- unaffected by the
#      notch-guard-band relaxation in #2, which only ever softens a NONE
#      (no crossing) verdict, never a FOUND-but-unstable one.
#
# NOTCH_GUARD_DB rationale (issue #146): re-running this experiment's
# `bcs`/125C/2.97V corner twice (records/20260826-103412-014570b.md,
# records/20260829-103017-1d98d88.md) against IDENTICAL device netlists
# (bit-identical dc_gain_db both times) produced notch minima of -0.0506 dB
# and +0.0620 dB purely from solver-level numerical sensitivity (gmin
# stepping / OSDI Newton iteration, both logged active at this corner) --
# i.e. the notch minimum is not reproducible to better than roughly a tenth
# of a dB at this corner even with nothing else changed. 1.0 dB is an order
# of magnitude more headroom than that observed noise floor while still
# catching a genuine multi-dB regression (a notch minimum rising clearly
# and robustly above 0 dB, well outside solver noise, still fails -- see
# README "Pass/fail criteria").
OP_MATCH_TOL_V="0.05"
PM_MIN_DEG="0"
NOTCH_GUARD_DB="1.0"
# Corner IDs where the guard band in criterion #2 above is the reason the
# point PASSed (no crossing was actually found, but the notch minimum was
# within NOTCH_GUARD_DB of 0 dB) -- reported in the record for transparency,
# same convention as `failed_points` from sim/lib/pvt_preflight.sh.
marginal_points=()

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"
      ac_out="${CORNERS_OUT}/${corner_id}.ac.txt"

      fb_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" fb_final_v)"
      sns1_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns1_final_v)"
      sns2_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" sns2_final_v)"
      vref_seed="$(lookup_seed "${corner}" "${temp}" "${vdd}" vref_final_v)"

      if [[ -z "${fb_seed}" || -z "${sns1_seed}" || -z "${sns2_seed}" || -z "${vref_seed}" ]]; then
        echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},FAIL,,,,,,,,,0,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id} (no seed in ${SEED_CSV})")
        continue
      fi

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@MSENSE_W@@|${MSENSE_W}|g" \
        -e "s|@@FB_SEED@@|${fb_seed}|g" \
        -e "s|@@SNS1_SEED@@|${sns1_seed}|g" \
        -e "s|@@SNS2_SEED@@|${sns2_seed}|g" \
        -e "s|@@VREF_SEED@@|${vref_seed}|g" \
        -e "s|@@AC_OUT@@|${ac_out}|g" \
        -e "s|@@DUT_GIT_SHA@@|core=${DUT_CORE_GIT_SHA} amp=${DUT_AMP_GIT_SHA} startup=${DUT_STARTUP_GIT_SHA} seeds=${SEED_CSV##*/}@${SEED_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      # `|| true`: same rationale as every other run_pvt_sweep.sh in this
      # tree -- a single non-convergent corner must not abort the sweep
      # under `set -euo pipefail`.
      fb_op=$(grep -E '^v\(fb_load\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      sns1_op=$(grep -E '^v\(sns1\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      sns2_op=$(grep -E '^v\(sns2\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)
      vref_op=$(grep -E '^v\(vref\)' "${log}" | head -1 | awk -F'=' '{print $2}' | tr -d ' ' || true)

      verdict=PASS
      dc_gain=""
      crossover_hz=""
      pm_deg=""
      ncross=0
      notch_min_db=""
      notch_min_hz=""
      notch_margin_flag=""
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${fb_op}" || ! -s "${ac_out}" ]]; then
        verdict=FAIL
      else
        op_delta=$(awk -v a="${fb_op}" -v b="${fb_seed}" 'BEGIN{d=a-b; print (d<0)?-d:d}')
        read -r status crossover_hz pm_deg dc_gain ncross notch_min_db notch_min_hz < <(awk -f "${CROSSOVER_AWK}" "${ac_out}")
        op_ok=$(awk -v d="${op_delta}" -v tol="${OP_MATCH_TOL_V}" 'BEGIN{print (d<=tol)?1:0}')
        # notch_margin_flag: "marginal" when the sweep's own resonant notch
        # sits within +-NOTCH_GUARD_DB of 0 dB -- indistinguishable from
        # solver noise at that resolution (see NOTCH_GUARD_DB comment
        # above) -- else "clear" (the notch robustly misses 0 dB in either
        # direction). Computed unconditionally (whether or not a crossing
        # was FOUND) so it is visible in the CSV even for a normal,
        # comfortably-passing corner.
        notch_margin_flag=$(awk -v m="${notch_min_db}" -v g="${NOTCH_GUARD_DB}" \
          'BEGIN{v=(m<0)?-m:m; print (v<=g)?"marginal":"clear"}')
        pm_ok=0
        crossing_ok=0
        if [[ "${status}" == "FOUND" ]]; then
          pm_ok=$(awk -v pm="${pm_deg}" -v minpm="${PM_MIN_DEG}" 'BEGIN{print (pm>minpm)?1:0}')
          crossing_ok="${pm_ok}"
        elif [[ "${notch_margin_flag}" == "marginal" ]]; then
          # No crossing was found (the notch never dipped below 0 dB in
          # THIS sweep), but the notch minimum sits within the solver-noise
          # guard band of 0 dB -- issue #146's exact bcs/125C case, where
          # an independent identical-netlist re-run found this same notch
          # a couple hundredths of a dB on the OTHER side of 0 dB. Treat as
          # a marginal pass rather than a hard fail; crossover_hz/pm_deg
          # stay unpopulated below since no real crossing was measured to
          # report a phase margin for.
          crossing_ok=1
          marginal_points+=("${corner_id} (notch_min=${notch_min_db} dB)")
        fi
        if [[ "${op_ok}" != "1" || "${crossing_ok}" != "1" ]]; then
          verdict=FAIL
        fi
        if [[ "${status}" != "FOUND" ]]; then
          crossover_hz=""
          pm_deg=""
        fi
      fi

      tally_verdict "${verdict}" "${corner_id}"
      echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},${MSENSE_W},${verdict},${fb_seed},${fb_op},${sns1_op},${sns2_op},${vref_op},${dc_gain},${crossover_hz},${pm_deg},${ncross},${notch_min_db},${notch_min_hz},${notch_margin_flag}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: loop-gain-phase-margin"
  echo "- **Claim**: through the SAME co-simulated closed-loop topology"
  echo "  sim/closed-loop-startup uses (bandgap_core + bandgap_amp +"
  echo "  bandgap_startup, wired exactly as design/bandgap_top.sch"
  echo "  specifies, real devices throughout), with the shared \`fb\` node"
  echo "  split into fb_src (amp output) / fb_load (everything fb_src"
  echo "  drives) and bridged by a large (1e9 H) break inductor plus a"
  echo "  series AC injection source (Middlebrook single voltage-injection"
  echo "  loop-gain probe -- see README \"loop-break method\"), the loop's"
  echo "  small-signal gain and phase are measured by AC analysis"
  echo "  (1 Hz-1 GHz) around a DC operating point seeded via .nodeset from"
  echo "  sim/closed-loop-startup's own most recent per-corner converged"
  echo "  transient endpoint (README \"Nodeset provenance\") and"
  echo "  re-verified per point (README \"op landed near its seed\"). Phase"
  echo "  margin is the phase of T(s)=V(fb_src)/V(fb_load) at the frequency"
  echo "  where |T|=1 (0 dB) -- see README \"Sign convention\" for why this"
  echo "  ratio (no extra sign flip) is the correct phase-margin"
  echo "  convention for THIS testbench's own injection polarity."
  echo "- **XMSENSE width this run used**: w=${MSENSE_W} (read from the live"
  echo "  design/netlist/bandgap_startup.spice at run time)."
  echo "- **Devices**: all real PDK compact models, all three DUTs copied"
  echo "  verbatim from design/netlist/bandgap_core.spice,"
  echo "  design/netlist/bandgap_amp.spice and"
  echo "  design/netlist/bandgap_startup.spice (identical device set to"
  echo "  sim/closed-loop-startup) plus the Lbreak/Vtest loop-break fixture"
  echo "  documented in testbench/ and README.md. No fixture stands in for"
  echo "  any real device -- only the injection/break elements are added,"
  echo "  same discipline as every closed-loop experiment in this tree."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_core.spice @ \`${DUT_CORE_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_amp.spice @ \`${DUT_AMP_GIT_SHA}\`,"
  echo "  design/netlist/bandgap_startup.spice @ \`${DUT_STARTUP_GIT_SHA}\`),"
  echo "  device-for-device, wired exactly as design/bandgap_top.sch"
  echo "  specifies except for the deliberate fb_src/fb_load split."
  echo "- **Nodeset seed provenance**: \`${SEED_CSV#"${REPO_ROOT}"/}\`"
  echo "  @ \`${SEED_GIT_SHA}\` (sim/closed-loop-startup's own most recent"
  echo "  committed record) -- see README \"Nodeset provenance\"."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs}"
  echo "  (HBT x MOS-hv x resistor sections) x temperature {-40, 27, 125} C"
  echo "  x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (.op landed within"
  echo "  ${OP_MATCH_TOL_V} V of its own .nodeset seed, AND EITHER a"
  echo "  falling 0 dB crossing was found in 1 Hz-1 GHz with phase margin"
  echo "  at that crossing exceeding ${PM_MIN_DEG} deg, OR no crossing was"
  echo "  found but the sweep's own resonant notch minimum sits within"
  echo "  +-${NOTCH_GUARD_DB} dB of 0 dB -- a guard band added by issue"
  echo "  #146 for solver noise indistinguishable from a real regression"
  echo "  at that resolution; see \`notch_min_db\`/\`notch_margin_flag\` in"
  echo "  \`records/${RECORD_ID}.csv\` and README \"Pass/fail criteria\")."
  if [[ ${#marginal_points[@]} -gt 0 ]]; then
    echo "- **Marginal-notch points** (PASS only via the"
    echo "  \`+-${NOTCH_GUARD_DB} dB\` guard band above -- no falling 0 dB"
    echo "  crossing was actually measured at these points, so"
    echo "  \`crossover_hz\`/\`phase_margin_deg\` are blank for them in the"
    echo "  CSV; the notch was simply too close to 0 dB for this single"
    echo "  AC sweep to resolve which side it truly sits on):"
    echo "  ${marginal_points[*]}"
  fi
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_loop_gain.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs + AC sweep data: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #86."
} > "${MD_OUT}"

write_pvt_summary
