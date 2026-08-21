#!/usr/bin/env bash
# Validates that this repo's top-level evidence/artifact directories exist
# and follow the repo's README.md convention (a non-empty README.md whose
# first line is a level-1 markdown heading). This only checks that the
# convention is followed, not that the directories contain design/sim/
# layout/measurement content yet — they are expected to be sparse until
# the corresponding issues land (see design/README.md, sim/README.md,
# layout/README.md, measurements/README.md).
#
# Usage: .github/scripts/check-repo-structure.sh
# Exit status: 0 if every directory follows the convention, 1 otherwise.

set -euo pipefail

dirs=(design sim layout measurements)
fail=0

for d in "${dirs[@]}"; do
  if [[ ! -d "$d" ]]; then
    echo "::error::expected directory '$d' does not exist"
    fail=1
    continue
  fi

  readme="$d/README.md"
  if [[ ! -f "$readme" ]]; then
    echo "::error file=$readme::missing $readme"
    fail=1
    continue
  fi

  if [[ ! -s "$readme" ]]; then
    echo "::error file=$readme::$readme is empty"
    fail=1
    continue
  fi

  first_line="$(head -n1 "$readme")"
  if ! [[ "$first_line" =~ ^\#[[:space:]].+ ]]; then
    echo "::error file=$readme::$readme must start with a '# ' level-1 heading (got: '$first_line')"
    fail=1
    continue
  fi

  echo "OK: $readme"
done

exit "$fail"
