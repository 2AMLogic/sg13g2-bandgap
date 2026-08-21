#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/tools/build-osdi.sh                 # one-time: build the OSDI models
#   sim/startup-trip-point/run_pvt_sweep.sh
#
# Requires ngspice on PATH plus the OSDI device models sim/tools/build-osdi.sh
# builds -- every device in design/netlist/bandgap_startup.spice is OSDI-gated,
# so this experiment cannot run at all without them. Full testbench rationale
# and what this sweep does and does not claim: sim/startup-trip-point/README.md.
#
# Writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.{md,csv} -- see sim/README.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
EXPERIMENT_DIR="${SCRIPT_DIR}"
TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_startup_trip_point.spice.tmpl"

# shellcheck source=/dev/null
source "${SIM_DIR}/env.sh"

if [[ -z "${PDK_ROOT:-}" || ! -d "${PDK_ROOT}/${PDK}/libs.tech/ngspice" ]]; then
  echo "run_pvt_sweep.sh: no resolvable ${PDK:-ihp-sg13g2} install -- see sim/env.sh output above." >&2
  exit 3
fi

if ! command -v ngspice >/dev/null 2>&1; then
  echo "run_pvt_sweep.sh: ngspice not found on PATH." >&2
  exit 3
fi

if ! "${SIM_DIR}/tools/build-osdi.sh" --check >/dev/null 2>&1; then
  echo "run_pvt_sweep.sh: OSDI device models missing or not loadable." >&2
  echo "run_pvt_sweep.sh: run  sim/tools/build-osdi.sh  first (see sim/README.md)." >&2
  "${SIM_DIR}/tools/build-osdi.sh" --check >&2 || true
  exit 3
fi
OSDI_DIR="${SG13G2_OSDI_DIR:-${PDK_ROOT}/${PDK}/libs.tech/ngspice/osdi}"

DUT_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_startup.spice 2>/dev/null || echo unknown)"
REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"

CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
mkdir -p "${CORNERS_OUT}" "${SNAPSHOTS_OUT}" "${RECORDS_DIR}"

CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.csv"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"

echo "corner_label,mos_section,res_section,temp_c,vdd_v,status,det_on_v,fb_on_v,vtrip_v,det_off_v,fb_off_v" > "${CSV_OUT}"

# Same corner-label vocabulary as sim/core-open-loop-bias (see that
# experiment's README for the pairing rationale), minus the HBT axis: the
# startup circuit contains no bipolar device.
CORNER_LABELS=(typ bcs wcs sf fs)
declare -A RES_SECTION_OF=( [typ]=res_typ [bcs]=res_bcs [wcs]=res_wcs [sf]=res_typ [fs]=res_typ )
declare -A MOS_SECTION_OF=( [typ]=mos_tt [bcs]=mos_ff [wcs]=mos_ss [sf]=mos_sf [fs]=mos_fs )

TEMPS=(-40 27 125)
VDDS=(2.97 3.30 3.63)

NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

total=0
passed=0
failed_points=()

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
        "${TEMPLATE}" > "${netlist}"

      set +e
      ngspice -b "${netlist}" > "${log}" 2>&1
      rc=$?
      set -e

      det_on=$(grep -E '^v\(det\)' "${log}" | head -1 | awk '{print $3}')
      fb_on=$(grep -E '^v\(fb\)' "${log}" | head -1 | awk '{print $3}')
      vtrip=$(grep -E '^vtrip' "${log}" | head -1 | awk '{print $3}')
      det_off=$(grep -E '^det_off' "${log}" | head -1 | awk '{print $3}')
      fb_off=$(grep -E '^fb_off' "${log}" | head -1 | awk '{print $3}')

      model_error=0
      if grep -qiE "Unable to find definition of model|couldn't be loaded|Unknown model type" "${log}"; then
        model_error=1
      fi

      # Pass criteria, all four checked explicitly (not just "ngspice exited 0"):
      #   1. cold start engages: det pulled to >= 80% of vdd with sns1 = 0
      #   2. cold start drives the mirror: fb held below 100 mV
      #   3. a disengage trip point exists strictly inside (0, vdd)
      #   4. running core disengages: det below 20% of vdd, fb released above 80%
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
  echo "- **Experiment**: startup-trip-point"
  echo "- **Claim**: sg13g2-bandgap's bandgap_startup circuit engages at cold"
  echo "  start (core sense node at 0 V => det pulled to >= 80% of vdd, fb held"
  echo "  below 100 mV, i.e. the PMOS mirror is forced on) and disengages once"
  echo "  the core is running (core sense node near vdd => det below 20% of"
  echo "  vdd and fb released above 80% of vdd), with a well-defined trip"
  echo "  point strictly inside (0, vdd), across the full temperature x supply"
  echo "  x MOS/resistor-process-corner grid. Infrastructure/plumbing evidence"
  echo "  for issue #22, NOT a claim against any ratified spec row (none is"
  echo "  ratified yet -- see #13)."
  echo "- **Devices**: all real PDK compact models -- sg13_hv_nmos (PSP103.6"
  echo "  via psp103.osdi) x2 and rhigh (r3_cmc via r3_cmc.osdi). Before"
  echo "  issue #22 built the OSDI models, this netlist could not be simulated"
  echo "  at all: every device in it is OSDI-gated."
  echo "- **Netlist provenance**: schematic"
  echo "  (design/netlist/bandgap_startup.spice @ \`${DUT_GIT_SHA}\`),"
  echo "  device-for-device, plus the sns1 stimulus source and the 10 Mohm fb"
  echo "  pull-up fixture documented in testbench/ and README.md."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\`."
  echo "- **OSDI models**: \`${OSDI_DIR}\` -- built by \`sim/tools/build-osdi.sh\`;"
  echo "  compiler provenance pinned in \`sim/pdk.json\` (\"osdi_toolchain\")."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs, sf, fs} (MOS-hv"
  echo "  x resistor sections) x temperature {-40, 27, 125} C x supply"
  echo "  {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (all four criteria above, not"
  echo "  merely a clean ngspice exit)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_startup_trip_point.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #22."
} > "${MD_OUT}"

echo "Wrote ${passed}/${total} PASS -> ${MD_OUT}"
if [[ ${#failed_points[@]} -gt 0 ]]; then
  echo "FAILED POINTS: ${failed_points[*]}" >&2
  exit 1
fi
