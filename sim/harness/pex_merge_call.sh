# shellcheck shell=bash
# Shared call construction for the per-(process x supply) PWL-ramp PEX batch
# runners (closed-loop-vref-pvt-pex, closed-loop-psrr-pex; issue #331).
#
# sim/harness/merge_batch_shards.py requires the expected grid (#327). These
# benches bake the supply into a per-supply body variant, so their shard
# reports carry no supply axis: each shard is passed as `label@vdd=path` and
# the declared vdd is the shard's supply identity. The grid axes are derived
# from the experiment's own request template (process labels, temperatures)
# and the runner's VDDS array -- never copied as literals.
#
# Source this file; then call
#   pex_merge_shards REQUEST_TEMPLATE REPORT_DIR OUTPUT
# with HARNESS_DIR, CORNER_LABELS[] and VDDS[] set. Shard i is
# REPORT_DIR/report-<label>-<vid>-fixed.json (vid = vdd with '.' -> 'p').

# Print "<csv processes> <csv temps>" from a request template's corners.
pex_request_axes() {  # $1 = request template json
  python3 - "$1" <<'PY'
import json, pathlib, sys
corners = json.loads(pathlib.Path(sys.argv[1]).read_text())["corners"]
procs, temps = corners["process"], corners["temperature_c"]
if not procs or not temps:
    raise SystemExit("pex_request_axes: request declares no process/temperature axis")
print(",".join(map(str, procs)), ",".join(f"{t:g}" for t in temps))
PY
}

# Print the merger argv (one argument per line) for the declared grid.
pex_merge_args() {  # $1 = request template, $2 = report dir, $3 = output
  local axes procs temps label vdd vid csv_vdds
  axes="$(pex_request_axes "$1")" || return 1
  procs="${axes% *}"
  temps="${axes#* }"
  if [[ "${procs}" != "$(IFS=,; echo "${CORNER_LABELS[*]}")" ]]; then
    echo "pex_merge_args: request processes (${procs}) differ from runner CORNER_LABELS" >&2
    return 1
  fi
  csv_vdds="$(IFS=,; echo "${VDDS[*]}")"
  printf '%s\n' -o "$3" --expect-process "${procs}" \
    --expect-supplies "${csv_vdds}" "--expect-temps=${temps}"
  for label in "${CORNER_LABELS[@]}"; do
    for vdd in "${VDDS[@]}"; do
      vid="$(echo "${vdd}" | tr '.' 'p')"
      echo "${label}@${vdd}=$2/report-${label}-${vid}-fixed.json"
    done
  done
}

pex_merge_shards() {  # $1 = request template, $2 = report dir, $3 = output
  local args
  mapfile -t args < <(pex_merge_args "$1" "$2" "$3") || return 1
  [[ ${#args[@]} -gt 0 ]] || return 1
  python3 "${HARNESS_DIR}/merge_batch_shards.py" "${args[@]}"
}
