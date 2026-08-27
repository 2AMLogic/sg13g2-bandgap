#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/parent-dir     # must contain BOTH ihp-sg13cmos5l/
#                                            # AND a sibling ihp-sg13g2/ -- see
#                                            # sim/pdk-sg13cmos5l.json
#                                            # "sibling_checkout_requirement"
#   export PDK=ihp-sg13cmos5l
#   sim/sg13cmos5l-core-open-loop-bias/run_pvt_sweep.sh
#
# Requires ngspice on PATH. This PDK ships its OSDI device models prebuilt
# (see sim/pdk-sg13cmos5l.json "osdi_toolchain") -- sim/tools/build-osdi.sh
# --check (which sim/lib/pvt_preflight.sh calls unconditionally) verifies
# them without a compile step. Full testbench rationale, what this sweep
# does and does not exercise, and the pinned PDK revision are documented in
# sim/sg13cmos5l-core-open-loop-bias/README.md and sim/pdk-sg13cmos5l.json --
# read those first if a result here looks surprising.
#
# Runs the full PVT grid (process corner x temperature x supply) from the
# template in testbench/, one ngspice batch invocation per point, and
# writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.md -- see sim/README.md for the
# evidence-record convention this follows.
set -euo pipefail

DUT_NETLIST="design/sg13cmos5l/netlist/bandgap_core.spice"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

# shellcheck source=../lib/pvt_sed_common.sh
source "${SIM_DIR}/lib/pvt_sed_common.sh"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_sg13cmos5l_core_open_loop_bias.spice.tmpl"

echo "corner_label,pnp_section,mos_section,res_section,temp_c,vdd_v,status,vref_v,vfb_v,veb_q1_v,veb_q2_v,veb_q3_v,dveb_ptat_v,i_leg1_a,i_leg2_a,i_leg3_a,r1_ohm,r2_ohm" > "${CSV_OUT}"

# CORNER_LABELS/TEMPS/VDDS/RES_SECTION_OF/MOS_SECTION_OF come from
# sim/lib/pvt_preflight.sh (shared with every SG13G2 experiment in this
# tree -- the front-end MOS/resistor devices and their corner-lib section
# names are literally shared between the two PDKs, see
# sim/pdk-sg13cmos5l.json "relationship_to_ihp_sg13g2"). PNP_SECTION_OF is
# defined HERE, not in the shared file: cornerPNP.lib (pnpMPA's process
# corner file) has no SG13G2 counterpart -- SG13G2's real HBT uses
# cornerHBT.lib instead -- so a shared HBT_SECTION_OF-style map would be
# dead weight for every SG13G2 testbench. Same sf/fs->typ fallback
# HBT_SECTION_OF already uses: cornerPNP.lib has no skewed pnp section
# either (see sim/pdk-sg13cmos5l.json "bipolar_device_note").
declare -A PNP_SECTION_OF=( [typ]=typ [bcs]=bcs [wcs]=wcs [sf]=typ [fs]=typ )

for corner in "${CORNER_LABELS[@]}"; do
  pnp_section="${PNP_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      next_corner_id "${corner}" "${temp}" "${vdd}"

      common_pvt_sed_args "${temp}" "${vdd}" "${corner}"
      sed \
        "${COMMON_SED_ARGS[@]}" \
        -e "s|@@PNP_SECTION@@|${pnp_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      vref=$(grep -E '^v\(vref\)' "${log}" | awk '{print $3}')
      vfb=$(grep -E '^v\(fb\)' "${log}" | awk '{print $3}')
      veb1=$(grep -E '^v\(sns1\)' "${log}" | awk '{print $3}')
      vsns2=$(grep -E '^v\(sns2\)' "${log}" | awk '{print $3}')
      veb2=$(grep -E '^v\(e2\)' "${log}" | awk '{print $3}')
      veb3=$(grep -E '^v\(e3\)' "${log}" | awk '{print $3}')
      i1=$(grep -E '^i\(vm1\)' "${log}" | awk '{print $3}')
      i2=$(grep -E '^i\(vm2\)' "${log}" | awk '{print $3}')
      i3=$(grep -E '^i\(vm3\)' "${log}" | awk '{print $3}')

      if [[ $rc -eq 0 && $model_error -eq 0 && -n "${vref:-}" && -n "${veb1:-}" \
            && -n "${veb2:-}" && -n "${i1:-}" && -n "${i2:-}" && -n "${i3:-}" ]]; then
        # dVEB is the PTAT term: VEB(Q1, unit) - VEB(Q2, 8x area), both at the
        # same mirrored leg current -- pnpMPA's V(E)-V(B) with base grounded,
        # so V(sns1)/V(e2) themselves ARE VEB (see testbench header).
        dveb=$(awk -v a="${veb1}" -v b="${veb2}" 'BEGIN{printf "%.6e", a-b}')
        # Effective resistance of the real r3_cmc devices, from the actual
        # DC drop over the actual leg current.
        r1val=$(awk -v v1="${vref}" -v v2="${veb3}" -v i="${i3}" 'BEGIN{ if (i+0==0) print ""; else printf "%.6e", (v1-v2)/i }')
        r2val=$(awk -v v1="${vsns2}" -v v2="${veb2}" -v i="${i2}" 'BEGIN{ if (i+0==0) print ""; else printf "%.6e", (v1-v2)/i }')
        echo "${corner},${pnp_section},${mos_section},${res_section},${temp},${vdd},PASS,${vref},${vfb},${veb1},${veb2},${veb3},${dveb},${i1},${i2},${i3},${r1val},${r2val}" >> "${CSV_OUT}"
        passed=$((passed + 1))
      else
        echo "${corner},${pnp_section},${mos_section},${res_section},${temp},${vdd},FAIL,,,,,,,,,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id}")
      fi
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: sg13cmos5l-core-open-loop-bias"
  echo "- **Claim**: sg13g2-bandgap's SG13CMOS5L bandgap_core"
  echo "  (design/sg13cmos5l/bandgap_core.sch, issue #64) produces a PTAT"
  echo "  delta-VEB across its real pnpMPA legs (Q1 unit vs Q2 8x-area, both"
  echo "  grounded-collector/diode-connected) and a summed CTAT+PTAT vref,"
  echo "  across the full temperature x supply x MOS/resistor-process-corner"
  echo "  x pnpMPA-process-corner grid, when its real sg13_hv_pmos mirror is"
  echo "  biased open-loop from a diode-connected replica leg (isolating the"
  echo "  core's own PTAT/CTAT generation from the real amplifier's loop"
  echo "  dynamics -- see README.md; sim/sg13cmos5l-closed-loop-startup is the"
  echo "  companion experiment with the real loop closed). This is"
  echo "  infrastructure/plumbing evidence for issue #65, NOT a claim against"
  echo "  any ratified spec row (this repo's spec/ tracks no ratified"
  echo "  SG13CMOS5L accuracy target -- see spec/porting-plan-sg13cmos5l.md)."
  echo "- **Devices**: all real PDK compact models -- pnpMPA (Gummel-Poon,"
  echo "  same model card SG13G2's own DR-0001 evaluation read), sg13_hv_pmos"
  echo "  (PSP103.6 via psp103.osdi), rppd (r3_cmc via r3_cmc.osdi). No ideal-"
  echo "  primitive device substitutions."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/sg13cmos5l/netlist/bandgap_core.spice @ \`${DUT_GIT_SHA}\`),"
  echo "  device-for-device, plus the open-loop bias and ammeter fixtures"
  echo "  documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned revision: see"
  echo "  \`sim/pdk-sg13cmos5l.json\` (git commit pin, not a tagged release --"
  echo "  re-verify PDK_ROOT actually resolves to that commit before trusting"
  echo "  this record on a different machine)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- shipped prebuilt by this PDK"
  echo "  checkout (no sim/tools/build-osdi.sh compile step needed); see"
  echo "  \`sim/pdk-sg13cmos5l.json\` \"osdi_toolchain\"."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (pnpMPA"
  echo "  x MOS-hv x resistor sections -- see README.md for the pairing) x"
  echo "  temperature {-40, 27, 125} C x supply {2.97, 3.30, 3.63} V ="
  echo "  ${total} points. Supply grid is the 3.3V HV-flavor analog rail only"
  echo "  (+-10%) -- this block instantiates no 1.2V LV-flavor device, see"
  echo "  \`sim/pdk-sg13cmos5l.json\` \"supply_rails\"."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, no model-load"
  echo "  error in the log, and all probed node voltages and leg currents"
  echo "  present)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_sg13cmos5l_core_open_loop_bias.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #65."
} > "${MD_OUT}"

write_pvt_summary
