#!/usr/bin/env bash
# sg13g2-bandgap -- the `repo-script` batch job entry for issue #518's KLU
# re-time (one job, one instance, cells serial; operator ruling 2026-11-17).
# Runs from the source root the runner unpacked; everything it produces goes
# under measurements/2026-11-klu-retime/out (the job's declared output).
set -euo pipefail
cd "$(dirname "$0")/../../.." || exit 2
exec python3 measurements/2026-11-klu-retime/retimer.py \
  --out measurements/2026-11-klu-retime/out \
  --max-passes "${RETIME_MAX_PASSES:-8}" \
  --budget-s "${RETIME_BUDGET_S:-3240}"
