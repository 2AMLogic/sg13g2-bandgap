#!/usr/bin/env bash
# sg13g2-bandgap -- local single-corner DC-PSRR attribution probe (issue #631).
#
#   sim/closed-loop-psrr/attribution/run_probe.sh CORNER TEMP VDD [VARIANT] [--loop-gain]
#
# Generates the standalone probe deck (gen_probe_deck.py) for ONE point,
# stages the PDK's sg13g2_*_mod.lib includes ngspice resolves relative to
# its CWD, runs ngspice -b once (single corner: allowed on dispatch hosts;
# grids go through run_klt_sim.sh --batch), and prints one RESULT line:
#
#   RESULT corner=... temp=... vdd=... variant=... psrr_dc_db=... \
#          vref_dc_phase_deg=... fb_op_v=... vref_op_v=... iq_a=...
#
# With --loop-gain the deck is the Middlebrook loop-break probe instead
# (stability check for the fix candidates) and the RESULT line carries
# lg_* fields -- crossover/PM/notch from the loop-gain bench's own
# find_crossover.awk and the #289 solve-quality gate, applied to the same
# wrdata shape that bench emits.
#
# Leaves <variant>_<corner>_<temp>c_<vdd>v.{spice,log,ac.txt} in the CWD
# (run it from a scratch dir; the record's decks are the same bytes with
# ${PDK_ROOT} tokens, under attribution/decks/).
#
# Environment: PDK_ROOT (or --pdk-root to the generator) must name an
# open_pdks-shaped ihp-sg13g2 install with sim/tools/build-osdi.sh's OSDI
# models built. Sourcing sim/env.sh is enough.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORNER="${1:?corner (typ|bcs|wcs|sf|fs)}"
TEMP="${2:?temp C (-40|27|125)}"
VDD="${3:?vdd V (2.97|3.30|3.63)}"
VARIANT="${4:-asbuilt}"
LG=0
[[ "${5:-}" == "--loop-gain" ]] && LG=1

: "${PDK_ROOT:?set PDK_ROOT (source sim/env.sh) or export it}"
PDK=ihp-sg13g2
MODELS="${PDK_ROOT}/${PDK}/libs.tech/ngspice/models"

STEM="${VARIANT}_${CORNER}_${TEMP}c_${VDD}v"
LG_ARGS=()
[[ "${LG}" == 1 ]] && LG_ARGS=(--loop-gain)
python3 "${HERE}/gen_probe_deck.py" --corner "${CORNER}" --temp "${TEMP}" \
  --vdd "${VDD}" --variant "${VARIANT}" "${LG_ARGS[@]}" -o "${STEM}.spice"

# The PDK's corner libs .include their sibling sg13g2_*_mod.lib device
# wrappers by BARE filename; ngspice resolves those relative to its CWD
# (the same staging klt sim's local backend does for itself).
for f in "${MODELS}"/*.lib; do ln -sf "${f}" "$(basename "${f}")"; done

ngspice -b "${STEM}.spice" > "${STEM}.log" 2>&1 \
  || { echo "ngspice failed (see ${STEM}.log)" >&2; exit 1; }

# emit_result LOG NAME=REGEX ... -- FIELD ...
# One RESULT line per probe run: the two back-to-back `python3 - "${STEM}.log"`
# grab() heredocs this file used to carry, collapsed into one parameterized
# helper (issue #707). Each NAME=REGEX grab takes its first capture group out
# of LOG (split at the FIRST '=', so the regex itself may contain '='), then
# the FIELD words print after the RESULT keyword with {NAME} references
# resolved to the grabbed values. A grab that does not match exits naming
# the field.
emit_result() {
  python3 - "$@" <<'PY'
import re, sys
args = sys.argv[1:]
sep = args.index("--")
log = open(args[0]).read()
grabbed = {}
for pair in args[1:sep]:
    name, pat = pair.split("=", 1)
    m = re.search(pat, log)
    if not m:
        sys.exit(f"run_probe.sh: {name} not found in {args[0]}")
    grabbed[name] = m.group(1)
fields = []
for field in args[sep + 1:]:
    for name, value in grabbed.items():
        field = field.replace("{" + name + "}", value)
    fields.append(field)
print("RESULT " + " ".join(fields))
PY
}

if [[ "${LG}" == 1 ]]; then
  # Loop-gain post-processing with the loop-gain bench's OWN tools (no
  # re-derivation): the solve-quality gate (#289/#297) and the crossover/
  # phase-margin finder, applied to the same wrdata shape that bench emits.
  LG_DIR="${HERE}/../../loop-gain-phase-margin/tools"
  QUALITY="$(python3 "${LG_DIR}/solve_quality.py" check "${STEM}.spice.ac.txt")"
  # shellcheck disable=SC2034  # Q_REASON only consumes the check line's third
  # word so Q_WORD/Q_RIPPLE bind; the RESULT line carries the quality word.
  read -r Q_WORD Q_RIPPLE Q_REASON <<< "${QUALITY}"
  XOVER="$(awk -f "${LG_DIR}/find_crossover.awk" "${STEM}.spice.ac.txt")"
  read -r X_STATUS X_FREQ X_PM X_DCGAIN X_NCROSS X_NOTCH X_NOTCHF <<< "${XOVER}"
  emit_result "${STEM}.log" \
    'fb_load_op_v=v\(fb_load\) = ([0-9.eE+-]+)' \
    'vref_op_v=v\(vref\) = ([0-9.eE+-]+)' \
    -- "corner=${CORNER}" "temp=${TEMP}" "vdd=${VDD}" "variant=${VARIANT}" \
    "lg_quality=${Q_WORD}" "lg_ripple_db=${Q_RIPPLE}" "lg_status=${X_STATUS}" \
    "lg_crossover_hz=${X_FREQ}" "lg_phase_margin_deg=${X_PM}" \
    "lg_dc_gain_db=${X_DCGAIN}" "lg_n_crossings=${X_NCROSS}" \
    "lg_notch_min_db=${X_NOTCH}" "lg_notch_min_hz=${X_NOTCHF}" \
    'fb_load_op_v={fb_load_op_v}' 'vref_op_v={vref_op_v}'
  exit 0
fi

emit_result "${STEM}.log" \
  'psrr_dc_db=psrr_dc_probe_db = ([0-9.eE+-]+)' \
  'vref_dc_phase_deg=vref_dc_phase_deg = ([0-9.eE+-]+)' \
  'fb_op_v=v\(fb\) = ([0-9.eE+-]+)' \
  'vref_op_v=v\(vref\) = ([0-9.eE+-]+)' \
  'iq_a=i\(vvdd\) = (-?[0-9.eE+-]+)' \
  -- "corner=${CORNER}" "temp=${TEMP}" "vdd=${VDD}" "variant=${VARIANT}" \
  'psrr_dc_db={psrr_dc_db}' 'vref_dc_phase_deg={vref_dc_phase_deg}' \
  'fb_op_v={fb_op_v}' 'vref_op_v={vref_op_v}' 'iq_a={iq_a}'
