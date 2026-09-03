#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/core-open-loop-bias/run_pvt_sweep.sh
#
# (PDK_ROOT/PDK may also be left unset if the PDK is installed under one of
# the usual prefixes sim/env.sh checks -- see that file.) Requires ngspice on
# PATH plus the OSDI device models sim/tools/build-osdi.sh builds; does not
# require xschem or klt. Full testbench rationale, what this sweep does and
# does not exercise, and the pinned PDK revision are documented in
# sim/core-open-loop-bias/README.md and sim/pdk.json -- read those first if a
# result here looks surprising.
#
# Runs the full PVT grid (process corner x temperature x supply) from the
# template in testbench/, one ngspice batch invocation per point, and
# writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.md -- see sim/README.md for the
# evidence-record convention this follows.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_core_open_loop_bias.spice.tmpl"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,vref_v,vfb_v,vbe_q1_v,vbe_q2_v,vbe_q3_v,dvbe_ptat_v,i_leg1_a,i_leg2_a,i_leg3_a,r1_ohm,r2_ohm" > "${CSV_OUT}"

# process-corner label -> (HBT section, MOS-hv section, resistor section)
# grid: CORNER_LABELS/TEMPS/VDDS/HBT_SECTION_OF/RES_SECTION_OF/MOS_SECTION_OF
# come from sim/lib/pvt_preflight.sh (shared across all 5 run_pvt_sweep.sh
# scripts as of issue #51) -- their job is to exercise the remaining two of
# cornerMOShv.lib's five process sections, which no testbench in this repo
# did before issue #22. See that file's header comment for the full pairing
# rationale.
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
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      vref=$(grep -E '^v\(vref\)' "${log}" | awk '{print $3}')
      vfb=$(grep -E '^v\(fb\)' "${log}" | awk '{print $3}')
      vbe1=$(grep -E '^v\(sns1\)' "${log}" | awk '{print $3}')
      vsns2=$(grep -E '^v\(sns2\)' "${log}" | awk '{print $3}')
      vbe2=$(grep -E '^v\(cb2\)' "${log}" | awk '{print $3}')
      vbe3=$(grep -E '^v\(cb3\)' "${log}" | awk '{print $3}')
      i1=$(grep -E '^i\(vm1\)' "${log}" | awk '{print $3}')
      i2=$(grep -E '^i\(vm2\)' "${log}" | awk '{print $3}')
      i3=$(grep -E '^i\(vm3\)' "${log}" | awk '{print $3}')

      if [[ $rc -eq 0 && $model_error -eq 0 && -n "${vref:-}" && -n "${vbe1:-}" \
            && -n "${vbe2:-}" && -n "${i1:-}" && -n "${i2:-}" && -n "${i3:-}" ]]; then
        # dVBE is the PTAT term: VBE(Q1, Nx=1) - VBE(Q2, Nx=8), both at the
        # same mirrored leg current.
        dvbe=$(awk -v a="${vbe1}" -v b="${vbe2}" 'BEGIN{printf "%.6e", a-b}')
        # Effective resistance of the real r3_cmc devices, from the actual
        # DC drop over the actual leg current -- not from rsh*squares, which
        # is what the pre-#22 ideal-R substitution could report.
        r1val=$(awk -v v1="${vref}" -v v2="${vbe3}" -v i="${i3}" 'BEGIN{ if (i+0==0) print ""; else printf "%.6e", (v1-v2)/i }')
        r2val=$(awk -v v1="${vsns2}" -v v2="${vbe2}" -v i="${i2}" 'BEGIN{ if (i+0==0) print ""; else printf "%.6e", (v1-v2)/i }')
        echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},PASS,${vref},${vfb},${vbe1},${vbe2},${vbe3},${dvbe},${i1},${i2},${i3},${r1val},${r2val}" >> "${CSV_OUT}"
        passed=$((passed + 1))
      else
        echo "${corner},${hbt_section},${mos_section},${res_section},${temp},${vdd},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id}")
      fi
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: core-open-loop-bias"
  echo "- **Claim**: sg13g2-bandgap's bandgap_core produces a PTAT delta-VBE"
  echo "  across its real npn13G2 legs (Q1 Nx=1 vs Q2 Nx=8) and a summed"
  echo "  CTAT+PTAT vref, across the full temperature x supply x"
  echo "  HBT/MOS/resistor-process-corner grid, when its real sg13_hv_pmos"
  echo "  mirror is biased open-loop from a diode-connected replica leg (no"
  echo "  error amplifier exists yet -- see README.md). This is"
  echo "  infrastructure/plumbing evidence for issues #10 and #22, NOT a claim"
  echo "  against any ratified spec row (none is ratified yet -- see #125)."
  echo "- **Devices**: all real PDK compact models -- npn13G2 (VBIC level=9),"
  echo "  sg13_hv_pmos (PSP103.6 via psp103.osdi), rppd (r3_cmc via"
  echo "  r3_cmc.osdi). No ideal-primitive device substitutions remain (the"
  echo "  pre-#22 records in this directory used ideal I and R stand-ins)."
  echo "- **Netlist provenance**: schematic (design/netlist/bandgap_core.spice"
  echo "  @ \`${DUT_GIT_SHA}\`), device-for-device, plus the open-loop bias and"
  echo "  ammeter fixtures documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\` (IHP-Open-PDK v0.3.0 as fetched by this repo's"
  echo "  convention; re-verify PDK_ROOT actually resolves to that release"
  echo "  before trusting this record on a different machine)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`"
  echo "  from the PDK's own Verilog-A sources; compiler provenance is pinned"
  echo "  in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (HBT x"
  echo "  MOS-hv x resistor sections -- see README.md for the pairing) x"
  echo "  temperature {-40, 27, 125} C x supply {2.97, 3.30, 3.63} V ="
  echo "  ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, no model-load"
  echo "  error in the log, and all probed node voltages and leg currents"
  echo "  present)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_core_open_loop_bias.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #22."
} > "${MD_OUT}"

write_pvt_summary
