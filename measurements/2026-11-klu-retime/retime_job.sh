#!/usr/bin/env bash
# sg13g2-bandgap -- the `repo-script` batch job entry for issue #518's KLU
# re-time (one job, one instance, cells serial; operator ruling 2026-11-17).
# Runs from the source root the runner unpacked; everything it produces goes
# under measurements/2026-11-klu-retime/out (the job's declared output).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
exec python3 "$here/retimer.py" \
  --out "$here/out" \
  --max-passes "${RETIME_MAX_PASSES:-8}" \
  --budget-s "${RETIME_BUDGET_S:-3240}"
