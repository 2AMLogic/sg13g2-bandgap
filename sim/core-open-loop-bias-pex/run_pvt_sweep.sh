#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/core-open-loop-bias-pex/run_pvt_sweep.sh
#
# (PDK_ROOT/PDK may also be left unset if the PDK is installed under one of
# the usual prefixes sim/env.sh checks -- see that file.) Requires ngspice on
# PATH plus the OSDI device models sim/tools/build-osdi.sh builds; does not
# require xschem or klt to RUN (klt was used once, offline, to produce the
# committed layout/bandgap_core/bandgap_core.pex.spice this sweep splices
# the schematic-sourced bipolar devices into -- the resistors are extracted
# as of issue #59 -- see that file and this experiment's README.md for how
# to regenerate it).
#
# Runs the full PVT grid (process corner x temperature x supply) from the
# template in testbench/, one ngspice batch invocation per point, and
# writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.md -- see sim/README.md for the
# evidence-record convention this follows, and this experiment's own
# README.md for what this PEX netlist does and does not model.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_core.spice"
LAYOUT_GDS="layout/bandgap_core/bandgap_core.gds"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

LAYOUT_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- "${LAYOUT_GDS}" 2>/dev/null || echo unknown)"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_core_open_loop_bias_pex.spice.tmpl"

echo "corner_label,hbt_section,mos_section,res_section,temp_c,vdd_v,status,vref_v,vpexfb_v,vbe_q1_v,vbe_q2_v,vbe_q3_v,dvbe_ptat_v,i_leg1_a,i_leg2_a,i_leg3_a,r1_ohm,r2_ohm" > "${CSV_OUT}"

# Same corner-label vocabulary and HBT/MOS/resistor section pairing as
# sim/core-open-loop-bias -- CORNER_LABELS/TEMPS/VDDS/HBT_SECTION_OF/
# RES_SECTION_OF/MOS_SECTION_OF come from sim/lib/pvt_preflight.sh (shared
# across all 5 run_pvt_sweep.sh scripts as of issue #51); unchanged here
# since the bipolar devices are the same schematic-sourced instances, and
# both the resistor and MOS corner axes apply to the same rppd/sg13_hv_pmos
# compact models as the schematic-level sweep -- the extracted rppd
# resistors (issue #59) and PMOS legs just carry extracted-layout geometry.
for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="${HBT_SECTION_OF[${corner}]}"
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      total=$((total + 1))
      corner_id="${corner}_${temp}c_${vdd}v"
      netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
      log="${CORNERS_OUT}/${corner_id}.log"

      sed \
        -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
        -e "s|@@PDK@@|${PDK}|g" \
        -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@TEMP_C@@|${temp}|g" \
        -e "s|@@VDD@@|${vdd}|g" \
        -e "s|@@CORNER_LABEL@@|${corner}|g" \
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      vref=$(grep -E '^v\(vref\)' "${log}" | awk '{print $3}')
      vfb=$(grep -E '^v\(pex_fb\)' "${log}" | awk '{print $3}')
      vbe1=$(grep -E '^v\(sns1\)' "${log}" | awk '{print $3}')
      vsns2=$(grep -E '^v\(sns2\)' "${log}" | awk '{print $3}')
      vbe2=$(grep -E '^v\(cb2\)' "${log}" | awk '{print $3}')
      vbe3=$(grep -E '^v\(cb3\)' "${log}" | awk '{print $3}')
      i1=$(grep -E '^i\(vm1\)' "${log}" | awk '{print $3}')
      i2=$(grep -E '^i\(vm2\)' "${log}" | awk '{print $3}')
      i3=$(grep -E '^i\(vm3\)' "${log}" | awk '{print $3}')

      if [[ $rc -eq 0 && $model_error -eq 0 && -n "${vref:-}" && -n "${vbe1:-}" \
            && -n "${vbe2:-}" && -n "${i1:-}" && -n "${i2:-}" && -n "${i3:-}" ]]; then
        dvbe=$(awk -v a="${vbe1}" -v b="${vbe2}" 'BEGIN{printf "%.6e", a-b}')
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
  echo "- **Experiment**: core-open-loop-bias-pex (issue #14)"
  echo "- **Claim**: sg13g2-bandgap's bandgap_core, re-simulated with its"
  echo "  PMOS mirror legs' geometry taken from the routed"
  echo "  \`layout/bandgap_core/bandgap_core.gds\` extraction (real drawn"
  echo "  W/L/AS/AD/PS/PD, no ideal-primitive substitutions) instead of the"
  echo "  schematic's as-drawn defaults, still produces a PTAT delta-VBE and"
  echo "  a summed CTAT+PTAT vref across the full PVT grid. This is"
  echo "  post-layout (PEX) evidence for issue #14 -- see this directory's"
  echo "  README.md for exactly what is and is not extracted/modelled"
  echo "  (bipolar devices are still schematic-sourced, not extracted; the"
  echo "  rppd resistors ARE extracted as of issue #59; Metal1/Metal2 wire"
  echo "  R/C are now modelled, issue #37; PMOS body is a"
  echo "  testbench fixture, not a real extracted tie). NOT a claim against"
  echo "  any ratified spec row (none is ratified yet -- see #13)."
  echo "- **Devices**: XM1/XM2/XM3 -- sg13_hv_pmos, geometry (+ wire R/C,"
  echo "  issue #37) from \`layout/bandgap_core/bandgap_core.pex.spice\`"
  echo "  (\`klt extract --deck sg13g2 --parasitics\`, layout git sha"
  echo "  \`${LAYOUT_GIT_SHA}\`). XQ1-XQ3 (npn13G2) still spliced verbatim"
  echo "  from \`design/netlist/bandgap_core.spice\` (schematic git sha"
  echo "  \`${DUT_GIT_SHA}\`) -- the sg13g2 extraction deck still does not"
  echo "  recognise bipolar devices (klayout-tools, filed generically)."
  echo "  XR1/XR2 (rppd) are now instantiated from the extracted R\$5/R\$4"
  echo "  devices (issue #59) instead of spliced from the schematic -- real"
  echo "  drawn geometry via an X-subckt call to the real rppd PDK subckt,"
  echo "  bulk on vsubs rather than the schematic's sub!. See README.md and"
  echo "  layout/README.md for the current, more nuanced picture."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\` (IHP-Open-PDK v0.3.0 as fetched by this repo's"
  echo "  convention; re-verify PDK_ROOT actually resolves to that release"
  echo "  before trusting this record on a different machine)."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`"
  echo "  from the PDK's own Verilog-A sources; compiler provenance is pinned"
  echo "  in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (HBT x"
  echo "  MOS-hv x resistor sections -- see sim/core-open-loop-bias/README.md"
  echo "  for the pairing, unchanged here) x temperature {-40, 27, 125} C x"
  echo "  supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0, no model-load"
  echo "  error in the log, and all probed node voltages and leg currents"
  echo "  present)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_core_open_loop_bias_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Extraction inputs: \`layout/bandgap_core/bandgap_core.pex.spice\`,"
  echo "    \`layout/bandgap_core/pex_extract_report.json\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #14."
} > "${MD_OUT}"

write_pvt_summary
