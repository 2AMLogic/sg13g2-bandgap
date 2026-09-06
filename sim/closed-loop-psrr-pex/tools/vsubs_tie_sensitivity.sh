#!/usr/bin/env bash
# vsubs_tie_sensitivity.sh -- quantify how much this experiment's ONE
# modelling choice that is not inherited from an existing testbench actually
# moves the measured PSRR curve.
#
#   sim/closed-loop-psrr-pex/tools/vsubs_tie_sensitivity.sh [record-id]
#
# Every extracted ground capacitance in layout/bandgap_top/bandgap_top.pex.spice
# returns to the node `vsubs` (the extractor's substrate/far-plate convention).
# The DC/transient PEX benches in this tree (sim/core-open-loop-bias-pex,
# sim/closed-loop-vref-pvt-pex) tie that node to 0 through a 1 TOhm resistor --
# a DC tie, adequate for their purpose. This experiment instead shorts vsubs to
# vss (see ../README.md "The vsubs tie matters here"). This script re-runs
# committed per-point netlist snapshots BOTH ways -- as committed, and with the
# single `Vvsubs vsubs vss dc 0` line swapped back to `Rvsubs_dctie vsubs 0
# 1e12` -- and prints the resulting PSRR difference, so the choice is a measured
# number in ../vsubs-tie-sensitivity.md rather than an asserted argument.
#
# Reads only committed artifacts (a record's own netlist snapshots and the
# sibling summariser); writes nothing into the append-only evidence tree --
# scratch output goes to a mktemp dir. Requires ngspice + the OSDI models
# (sim/tools/build-osdi.sh), same as any sweep in this tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SIM_DIR="$(cd "${EXPERIMENT_DIR}/.." && pwd)"
SUMMARY_AWK="${SIM_DIR}/closed-loop-psrr/tools/psrr_summary.awk"
COMMON_AWK="${SIM_DIR}/lib/db_summary_common.awk"

if ! command -v ngspice >/dev/null 2>&1; then
  echo "vsubs_tie_sensitivity.sh: ngspice not found on PATH." >&2
  exit 3
fi

RECORD_ID="${1:-}"
if [[ -z "${RECORD_ID}" ]]; then
  RECORD_ID="$(basename "$(find "${EXPERIMENT_DIR}/netlist-snapshots" -maxdepth 1 -mindepth 1 -type d | sort | tail -1)")"
fi
SNAP_DIR="${EXPERIMENT_DIR}/netlist-snapshots/${RECORD_ID}"
if [[ ! -d "${SNAP_DIR}" ]]; then
  echo "vsubs_tie_sensitivity.sh: no netlist-snapshots/${RECORD_ID}/ to re-run." >&2
  exit 3
fi

# Three representative points rather than all 45: one nominal, one
# worst-case-slow/hot/low-supply, one best-case-fast/cold/high-supply. The
# effect under test is a passive-network property (where the extracted ground
# caps return to), so it does not need the full grid to be characterized -- but
# it does need more than one bias point to show it is not corner-specific.
POINTS=("typ_27c_3.30v" "wcs_125c_2.97v" "bcs_-40c_3.63v")

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "record: ${RECORD_ID}"
echo "point,tie,psrr_dc_db,psrr_min_db,psrr_min_freq_hz,psrr_1khz_db,psrr_100khz_db,psrr_1mhz_db"
for point in "${POINTS[@]}"; do
  snap="${SNAP_DIR}/${point}.spice"
  if [[ ! -f "${snap}" ]]; then
    echo "vsubs_tie_sensitivity.sh: missing snapshot ${snap}" >&2
    exit 3
  fi
  for tie in vss_short 1tohm_float; do
    ac_out="${WORK}/${point}.${tie}.ac.txt"
    netlist="${WORK}/${point}.${tie}.spice"
    if [[ "${tie}" == "vss_short" ]]; then
      sed -e "s|^wrdata .*|wrdata ${ac_out} psrr_db vref_phase_deg|" "${snap}" > "${netlist}"
    else
      sed -e "s|^Vvsubs vsubs vss dc 0|Rvsubs_dctie vsubs 0 1e12|" \
          -e "s|^wrdata .*|wrdata ${ac_out} psrr_db vref_phase_deg|" "${snap}" > "${netlist}"
    fi
    ngspice -b "${netlist}" > "${WORK}/${point}.${tie}.log" 2>&1
    read -r dc mn mnf k1 k100 m1 < <(awk -v extremum=min -f "${COMMON_AWK}" -f "${SUMMARY_AWK}" "${ac_out}")
    echo "${point},${tie},${dc},${mn},${mnf},${k1},${k100},${m1}"
  done
done
