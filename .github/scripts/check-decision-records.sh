#!/usr/bin/env bash
# Validates every spec/decision-records/*.md file (except TEMPLATE.md itself)
# against the structure TEMPLATE.md requires: a numbered title line, the
# three metadata bullets, and the four required section headers.
#
# Usage: .github/scripts/check-decision-records.sh
# Exit status: 0 if every record is well-formed, 1 if any record is missing
# a required piece (with details printed for each failure).

set -euo pipefail

DR_DIR="spec/decision-records"
TEMPLATE="$DR_DIR/TEMPLATE.md"

if [[ ! -d "$DR_DIR" ]]; then
  echo "::error::expected directory '$DR_DIR' does not exist"
  exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
  echo "::error::missing $TEMPLATE — decision records have nothing to be checked against"
  exit 1
fi

required_fields=(
  "- **Status**:"
  "- **Date**:"
  "- **Decided by**:"
)

required_headers=(
  "## Context"
  "## Decision"
  "## Alternatives considered"
  "## Consequences"
)

fail=0
checked=0

shopt -s nullglob
for f in "$DR_DIR"/*.md; do
  base="$(basename "$f")"
  [[ "$base" == "TEMPLATE.md" ]] && continue
  checked=$((checked + 1))

  errors=()

  # First non-blank line must be a "# NNNN: <title>" heading.
  first_line="$(grep -m1 -n '[^[:space:]]' "$f" | head -n1 | cut -d: -f2-)"
  if ! [[ "$first_line" =~ ^\#[[:space:]][0-9]{4}:[[:space:]].+ ]]; then
    errors+=("missing/invalid title line (expected '# NNNN: <title>', got: '${first_line:-<empty file>}')")
  fi

  for field in "${required_fields[@]}"; do
    if ! grep -qF -- "$field" "$f"; then
      errors+=("missing required metadata field: $field")
    fi
  done

  for header in "${required_headers[@]}"; do
    if ! grep -qxF -- "$header" "$f"; then
      errors+=("missing required section header: $header")
    fi
  done

  if (( ${#errors[@]} > 0 )); then
    fail=1
    echo "::error file=$f::decision record does not follow $TEMPLATE"
    for e in "${errors[@]}"; do
      echo "  - $e"
    done
  else
    echo "OK: $f"
  fi
done

if (( checked == 0 )); then
  echo "OK: no decision records to check yet (only $TEMPLATE present)"
fi

exit "$fail"
