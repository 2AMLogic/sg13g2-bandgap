#!/usr/bin/env bash
# Run the one-point PEX sanity probe (issue #272) and write probe.log.
#
#   layout/bandgap_core/probe/run_probe.sh
#
# Resolves the PDK the same way every sim/*/run_*.sh does (sim/env.sh), then
# substitutes @PDK@/@OSDI@ into the generated netlist and runs ONE ngspice
# batch operating point. Single corner, ~0.3 s: this is deliberately not a
# grid, and must not grow into one here -- the five *-pex experiments' PVT
# grids against this extraction are issue #275, and this repo's hosts route
# multi-corner work to a batch backend rather than a local loop.
#
# NOT an evidence harness: nothing it writes goes under sim/records/, and
# probe.log is gitignored scratch (the repo-wide *.log rule), overwritten on
# each run rather than appended. The probe's *recorded* numbers live in
# layout/README.md's "One-point probe" table; this script is how you check
# them. See also make_probe_netlist.py's module docstring.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../.." && pwd)"

# shellcheck source=../../../sim/env.sh
source "${REPO_ROOT}/sim/env.sh"

if [[ -z "${PDK_ROOT:-}" ]]; then
  echo "probe: no ${PDK} install resolved -- see sim/env.sh" >&2
  exit 1
fi

# Keep the committed netlist honest against the committed extraction before
# simulating it: a stale probe netlist would report a stale number with no
# other sign that anything was wrong.
python3 "${HERE}/make_probe_netlist.py" --check

NETLIST="${HERE}/tb_core_pex_probe.spice"
RESOLVED="$(mktemp -t probe-XXXXXX.spice)"
trap 'rm -f "${RESOLVED}"' EXIT
sed -e "s|@PDK@|${PDK_ROOT}/${PDK}|g" \
    -e "s|@OSDI@|${SG13G2_OSDI_DIR}|g" \
    "${NETLIST}" > "${RESOLVED}"

ngspice -b "${RESOLVED}" > "${HERE}/probe.log" 2>&1 || {
  echo "probe: ngspice failed -- see ${HERE}/probe.log" >&2
  tail -20 "${HERE}/probe.log" >&2
  exit 1
}

# Derive the two quantities layout/README.md's table quotes but ngspice does
# not print directly: the summing resistor's effective value, and the
# ladder's measured unit count. Both come from the same three node voltages
# plus the output leg's own summed ammeter currents, so neither depends on
# the drawn geometry this probe is meant to check.
python3 - "${HERE}/probe.log" <<'PY'
import re, sys
log = open(sys.argv[1]).read()
v = {}
for name, val in re.findall(r"^(v\([\w.$|]+\)|i\(vm\d+\))\s*=\s*([-\d.e+]+)", log, re.M):
    v[name] = float(val)
# The ammeters are 0 V sources in each leg's source branch, so their
# readings are the leg's own device current; sum the output leg's three
# fingers (XM4/XM5/XM6, the extraction's M$4-M$6) the way
# sim/core-open-loop-bias-pex's run_pvt_sweep.sh does.
i_leg3 = abs(v["i(vm4)"] + v["i(vm5)"] + v["i(vm6)"])
vref, tn0, cb3 = v["v(vref)"], v["v(tn0_merged)"], v["v(cb3)"]
print(f"vref      = {vref:.6f} V")
print(f"i_leg3    = {i_leg3*1e6:.6f} uA")
print(f"R1_eff    = {(vref - cb3) / i_leg3:.1f} ohm   (vref -> cb3, base + ladder)")
print(f"R_ladder  = {(tn0 - cb3) / i_leg3:.1f} ohm")
print(f"R_base    = {(vref - tn0) / i_leg3:.1f} ohm")
print(f"ladder/base ratio = {(tn0 - cb3) / (vref - tn0):.4f}  (design nominal 12.64)")
PY
