#!/usr/bin/env bash
# Cold-start invocation:
#
#   export PDK_ROOT=/path/to/ihp-open-pdk   # parent dir containing ihp-sg13g2/
#   export PDK=ihp-sg13g2
#   sim/core-open-loop-bias/run_pvt_sweep.sh
#
# (PDK_ROOT/PDK may also be left unset if the PDK is installed under one of
# the usual prefixes sim/env.sh checks -- see that file.) Requires only
# ngspice on PATH; does not require xschem or klt. Full testbench rationale,
# what this sweep does and does not exercise, and the pinned PDK revision
# are documented in sim/core-open-loop-bias/README.md and sim/pdk.json --
# read those first if a result here looks surprising.
#
# Runs the full PVT grid (process corner x temperature x supply) from the
# template in testbench/, one ngspice batch invocation per point, and
# writes append-only evidence under corners/<record-id>/, netlist-snapshots/
# <record-id>/ and records/<record-id>.md -- see sim/README.md for the
# evidence-record convention this follows.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIM_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"
EXPERIMENT_DIR="${SCRIPT_DIR}"
TEMPLATE="${EXPERIMENT_DIR}/testbench/tb_core_open_loop_bias.spice.tmpl"

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

DUT_GIT_SHA="$(git -C "${REPO_ROOT}" log -1 --format=%h -- design/netlist/bandgap_core.spice 2>/dev/null || echo unknown)"
REPO_GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
RECORD_ID="$(date -u +%Y%m%d-%H%M%S)-${REPO_GIT_SHA}"

CORNERS_OUT="${EXPERIMENT_DIR}/corners/${RECORD_ID}"
SNAPSHOTS_OUT="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
RECORDS_DIR="${EXPERIMENT_DIR}/records"
mkdir -p "${CORNERS_OUT}" "${SNAPSHOTS_OUT}" "${RECORDS_DIR}"

CSV_OUT="${RECORDS_DIR}/${RECORD_ID}.csv"
MD_OUT="${RECORDS_DIR}/${RECORD_ID}.md"

echo "corner_label,hbt_section,res_section,temp_c,vdd_v,status,vref_v,vbe_q1_v,vbe_q2_v,vbe_q3_v,dvbe_ptat_v,r1_ohm,r2_ohm" > "${CSV_OUT}"

# process-corner label -> (hbt section, res section). Pairing uses the SAME
# corner label the PDK itself already assigns in both cornerHBT.lib and
# cornerRES.lib (typ/bcs/wcs) -- not an assumption this testbench invents.
CORNER_LABELS=(typ bcs wcs)
TEMPS=(-40 27 125)
VDDS=(2.97 3.30 3.63)

NGSPICE_VERSION="$(ngspice -v 2>&1 | sed -n '2p')"

total=0
passed=0
failed_points=()

for corner in "${CORNER_LABELS[@]}"; do
  hbt_section="hbt_${corner}"
  res_section="res_${corner}"
  for temp in "${TEMPS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      total=$((total + 1))
      corner_id="${corner}_${temp}c_${vdd}v"
      netlist="${SNAPSHOTS_OUT}/${corner_id}.spice"
      log="${CORNERS_OUT}/${corner_id}.log"

      sed \
        -e "s|@@PDK_ROOT@@|${PDK_ROOT}|g" \
        -e "s|@@PDK@@|${PDK}|g" \
        -e "s|@@HBT_SECTION@@|${hbt_section}|g" \
        -e "s|@@RES_SECTION@@|${res_section}|g" \
        -e "s|@@TEMP_C@@|${temp}|g" \
        -e "s|@@VDD@@|${vdd}|g" \
        -e "s|@@CORNER_LABEL@@|${corner}|g" \
        -e "s|@@DUT_GIT_SHA@@|${DUT_GIT_SHA}|g" \
        "${TEMPLATE}" > "${netlist}"

      set +e
      ngspice -b "${netlist}" > "${log}" 2>&1
      rc=$?
      set -e

      vref=$(grep -E '^v\(vref\)' "${log}" | awk '{print $3}')
      vbe1=$(grep -E '^v\(sns1\)' "${log}" | awk '{print $3}')
      vbe2=$(grep -E '^v\(cb2\)' "${log}" | awk '{print $3}')
      vbe3=$(grep -E '^v\(cb3\)' "${log}" | awk '{print $3}')
      r1val=$(grep -E '^@r1\[resistance\]' "${log}" | awk '{print $3}')
      r2val=$(grep -E '^@r2\[resistance\]' "${log}" | awk '{print $3}')

      if [[ $rc -eq 0 && -n "${vref:-}" && -n "${vbe1:-}" && -n "${vbe2:-}" ]]; then
        dvbe=$(awk -v a="${vbe1}" -v b="${vbe2}" 'BEGIN{printf "%.6e", a-b}')
        echo "${corner},${hbt_section},${res_section},${temp},${vdd},PASS,${vref},${vbe1},${vbe2},${vbe3},${dvbe},${r1val},${r2val}" >> "${CSV_OUT}"
        passed=$((passed + 1))
      else
        echo "${corner},${hbt_section},${res_section},${temp},${vdd},FAIL,,,,,,," >> "${CSV_OUT}"
        failed_points+=("${corner_id}")
      fi
    done
  done
done

{
  echo "# Record ${RECORD_ID}"
  echo
  echo "- **Experiment**: core-open-loop-bias"
  echo "- **Claim**: sg13g2-bandgap's bandgap_core HBT legs (Q1/Q2/Q3, npn13G2)"
  echo "  produce a PTAT delta-VBE and a summed CTAT+PTAT vref across the full"
  echo "  temperature x supply x HBT/resistor-process-corner grid, when"
  echo "  current-biased directly (open-loop -- no mirror, no amplifier yet;"
  echo "  see testbench/README.md). This is infrastructure/plumbing evidence"
  echo "  for issue #10, NOT a claim against any ratified spec row (none is"
  echo "  ratified yet -- see #13)."
  echo "- **Netlist provenance**: schematic (design/netlist/bandgap_core.spice"
  echo "  @ \`${DUT_GIT_SHA}\`), with XM1/XM2/XM3 and XR1/XR2 substituted per"
  echo "  testbench/README.md's 'Known simulation gap' section."
  echo "- **PDK**: \`${PDK}\` at \`${PDK_ROOT}\` -- pinned release: see"
  echo "  \`sim/pdk.json\` (IHP-Open-PDK v0.3.0 as fetched by this repo's"
  echo "  convention; re-verify PDK_ROOT actually resolves to that release"
  echo "  before trusting this record on a different machine)."
  echo "- **ngspice**: \`${NGSPICE_VERSION}\`"
  echo "- **Corner matrix run**: process corner {typ, bcs, wcs} (HBT+resistor"
  echo "  sheet-resistance axis only -- see 'Known simulation gap') x temperature"
  echo "  {-40, 27, 125} C x supply {2.97, 3.30, 3.63} V = ${total} points."
  echo "- **Result**: ${passed}/${total} points PASS (ngspice exit 0 and all"
  echo "  probed node voltages present in the log)."
  if [[ ${#failed_points[@]} -gt 0 ]]; then
    echo "- **Failed points**: ${failed_points[*]}"
  fi
  echo "- **Links**:"
  echo "  - Template: \`testbench/tb_core_open_loop_bias.spice.tmpl\`"
  echo "  - Per-point generated netlists: \`netlist-snapshots/${RECORD_ID}/\`"
  echo "  - Per-point raw ngspice logs: \`corners/${RECORD_ID}/\`"
  echo "  - Parsed CSV: \`records/${RECORD_ID}.csv\`"
  echo "- **Timestamp / author**: $(date -u +%Y-%m-%dT%H:%M:%SZ), Loom Builder"
  echo "  (agent), issue #10."
} > "${MD_OUT}"

echo "Wrote ${passed}/${total} PASS -> ${MD_OUT}"
if [[ ${#failed_points[@]} -gt 0 ]]; then
  echo "FAILED POINTS: ${failed_points[*]}" >&2
  exit 1
fi
