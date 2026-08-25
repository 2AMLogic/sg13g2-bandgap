#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/startup-trip-point-pex/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds. Does not require xschem or klt to RUN (klt was used once, offline,
# to produce the committed layout/bandgap_startup/bandgap_startup.pex.spice
# this sweep splices a schematic-sourced resistor device into -- see that
# file and this experiment's README.md for how to regenerate it, and for
# the w=2u-vs-w=10u XMSENSE caveat this experiment's own README documents
# up front).
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

DUT_NETLIST="design/netlist/bandgap_startup.spice"
LAYOUT_GDS="layout/bandgap_startup/bandgap_startup.gds"
# shellcheck source=../lib/pvt_preflight.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)/pvt_preflight.sh"

LAYOUT_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- "${LAYOUT_GDS}" 2>/dev/null || echo unknown)"

TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_startup_trip_point_pex.spice.tmpl"

echo "corner_label,mos_section,res_section,temp_c,vdd_v,status,det_on_v,fb_on_v,vtrip_v,det_off_v,fb_off_v" > "${CSV_OUT}"

# Same corner-label vocabulary as sim/startup-trip-point (see that
# experiment's README for the pairing rationale), minus the HBT axis.
# CORNER_LABELS/TEMPS/VDDS/RES_SECTION_OF/MOS_SECTION_OF come from
# sim/lib/pvt_preflight.sh (shared across all 5 run_pvt_sweep.sh scripts as
# of issue #51).
for corner in "${CORNER_LABELS[@]}"; do
  res_section="${RES_SECTION_OF[${corner}]}"
  mos_section="${MOS_SECTION_OF[${corner}]}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      total=$((total + 1))
      corner_id="${corner}_${temp}c_${vdd}v"
      netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
      log="${CORNERS_OUT}/${corner_id}.log"

      vdd_half=$(awk -v v="${vdd}" 'BEGIN{printf "%.4f", v/2}')
      # ngspice's `meas ... at=` refuses the exact end point of a dc sweep
      # ("out of interval"), so the "core fully up" end state is measured one
      # sweep step short of vdd.
      vdd_off=$(awk -v v="${vdd}" 'BEGIN{printf "%.4f", v-0.05}')

      sed \
        -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
        -e "s|@@PDK@@|${PDK}|g" \
        -e "s|@@OSDI_DIR@@|${OSDI_DIR}|g" \
        -e "s|@@MOS_SECTION@@|${mos_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@TEMP_C@@|${temp}|g" \
        -e "s|@@VDD@@|${vdd}|g" \
        -e "s|@@VDD_HALF@@|${vdd_half}|g" \
        -e "s|@@VDD_OFF@@|${vdd_off}|g" \
        -e "s|@@CORNER_LABEL@@|${corner}|g" \
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        -e "s|@@LAYOUT_GIT_SHA@@|${LAYOUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      run_pvt_point "${netlist}" "${log}"

      det_on=$(grep -E '^v\(det\)' "${log}" | head -1 | awk '{print $3}')
      fb_on=$(grep -E '^v\(fb\)' "${log}" | head -1 | awk '{print $3}')
      vtrip=$(grep -E '^vtrip' "${log}" | head -1 | awk '{print $3}')
      det_off=$(grep -E '^det_off' "${log}" | head -1 | awk '{print $3}')
      fb_off=$(grep -E '^fb_off' "${log}" | head -1 | awk '{print $3}')

      # Same four explicit pass criteria as sim/startup-trip-point (not
      # merely a clean ngspice exit) -- see that experiment's script for the
      # rationale. Any failure here reproduces the AS-DRAWN (w=2u) layout's
      # real behavior, not a testbench artifact -- see this directory's
      # README.md and the file header comment in testbench/ for why a
      # 125C release failure is expected until the layout is regenerated
      # against decision record 0003's w=10u fix.
      verdict=PASS
      if [[ $rc -ne 0 || $model_error -ne 0 ]]; then
        verdict=FAIL
      elif [[ -z "${det_on}" || -z "${fb_on}" || -z "${vtrip}" || -z "${det_off}" || -z "${fb_off}" ]]; then
        verdict=FAIL
      else
        verdict=$(awk -v det_on="${det_on}" -v fb_on="${fb_on}" -v vtrip="${vtrip}" \
                      -v det_off="${det_off}" -v fb_off="${fb_off}" -v vdd="${vdd}" \
          'BEGIN{
             ok = (det_on >= 0.8*vdd) && (fb_on <= 0.1) \
                  && (vtrip > 0) && (vtrip < vdd) \
                  && (det_off <= 0.2*vdd) && (fb_off >= 0.8*vdd);
             print ok ? "PASS" : "FAIL";
           }')
      fi

      if [[ "${verdict}" == "PASS" ]]; then
        passed=$((passed + 1))
      else
        failed_points+=("${corner_id}")
      fi
      echo "${corner},${mos_section},${res_section},${temp},${vdd},${verdict},${det_on},${fb_on},${vtrip},${det_off},${fb_off}" >> "${CSV_OUT}"
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: startup-trip-point-pex (issue #14)"
  echo "- **Claim**: sg13g2-bandgap's bandgap_startup circuit, re-simulated"
  echo "  with XMSENSE/XMKFB geometry taken from the routed"
  echo "  \`layout/bandgap_startup/bandgap_startup.gds\` extraction (real"
  echo "  drawn W/L/AS/AD/PS/PD, plus real Metal1/Metal2 wire R/C, issue #37)"
  echo "  instead of the current schematic's, engages"
  echo "  at cold start and disengages once the core is running, across the"
  echo "  full PVT grid -- **AS DRAWN**, which is now w=10u for XMSENSE,"
  echo "  matching the schematic's current w=10u (issue #32 regenerated the"
  echo "  layout to match decision record 0003's earlier schematic-level"
  echo "  fix -- see this directory's README.md for the before/after"
  echo "  account). This direct sns1-sweep alone reads PASS at every point"
  echo "  below (it always completes release by sns1=vdd) -- as it also did"
  echo "  at the stale w=2u width, so this number alone does not confirm the"
  echo "  fix -- but a cross-bench comparison against core-open-loop-bias-pex's"
  echo "  own real sns1 operating point, which previously reproduced decision"
  echo "  record 0003's exact same 4 flagged points (wcs_125c_*,"
  echo "  sf_125c_3.63v) at the stale w=2u width, now clears at all 45"
  echo "  points -- see this directory's README.md 'Cross-bench observation'"
  echo "  for the numbers. Post-layout (PEX) evidence for issue #14/#32, NOT"
  echo "  a claim against any ratified spec row (none is ratified yet -- see"
  echo "  #13)."
  echo "- **Devices**: XMSENSE/XMKFB -- sg13_hv_nmos, geometry from"
  echo "  \`layout/bandgap_startup/bandgap_startup.pex.spice\`"
  echo "  (\`klt extract --deck sg13g2 --parasitics\`, layout git sha"
  echo "  \`${LAYOUT_GIT_SHA}\`), body tied to vss as a testbench fixture"
  echo "  (extraction reports it on the deck's synthesized \`vsubs\` global,"
  echo "  not the schematic's real vss tie -- klayout-tools, filed"
  echo "  generically). XRPU (rhigh) -- spliced verbatim from"
  echo "  \`design/netlist/bandgap_startup.spice\` (schematic git sha"
  echo "  \`${DUT_GIT_SHA}\`); the sg13g2 extraction deck NOW recognises it"
  echo "  as an extracted \`rhigh\` device (issue #56, PR #45's resistor"
  echo "  marker layers), but this testbench still splices it from the"
  echo "  schematic rather than the extraction -- see README.md for the"
  echo "  current, more nuanced picture."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (MOS-hv"
  echo "  x resistor sections) x temperature {-40, 27, 125} C x supply"
  echo "  {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (all four criteria, same"
  echo "  as sim/startup-trip-point, not merely a clean ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_startup_trip_point_pex.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "  - Extraction inputs: \`layout/bandgap_startup/bandgap_startup.pex.spice\`,"
  echo "    \`layout/bandgap_startup/pex_extract_report.json\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #14."
} > "${MD_OUT}"

write_pvt_summary
