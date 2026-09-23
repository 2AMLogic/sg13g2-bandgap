#!/usr/bin/env bash
# test-sticky-blocked.sh — unit tests for .loom/scripts/sticky-blocked.sh (#246).
#
# What this suite pins down, and what it deliberately does NOT claim:
#
#   IT DOES pin the *call shape* of the release and repair mutations — that the
#   claim release is ONE `gh issue edit` naming every label the issue must end
#   up with (so the `loom:blocked` re-apply can never be a separable, skippable
#   second step), and that the repair path is purely additive.
#
#   IT DOES NOT — and cannot — prove that `loom:blocked` survives a real
#   claim/settle cycle on issue #4. That loss happens minutes after the settle,
#   in a pass this repository does not run (see the evidence block at the head
#   of sticky-blocked.sh and docs/tracker-4-settle-protocol.md). Only a live
#   dispatch cycle can verify that, which is exactly why the issue's acceptance
#   criteria call it out as out-of-band.
#
# Strategy mirrors test-merge-pr-partial-increment.sh: stub `gh` on PATH so
# every mutating call is recorded verbatim, drive the script end to end, and
# assert on the recorded call log.
#
# Usage:
#   ./.loom/scripts/tests/test-sticky-blocked.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPTS_DIR/../.." && pwd)"
SUT="$SCRIPTS_DIR/sticky-blocked.sh"
REAL_REGISTRY="$REPO_ROOT/.loom/sticky-blocked.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ "$expected" == "$actual" ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Expected: '$expected'"
        echo "    Actual:   '$actual'"
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if grep -qF -- "$needle" <<<"$haystack"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Expected substring: '$needle'"
        echo "    In: '$haystack'"
    fi
}

assert_not_contains() {
    local haystack="$1" needle="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if ! grep -qF -- "$needle" <<<"$haystack"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Unexpected substring: '$needle'"
        echo "    In: '$haystack'"
    fi
}

[[ -x "$SUT" ]] || { echo -e "${RED}FATAL${NC}: $SUT is not executable" >&2; exit 2; }

# --- stub gh on PATH ----------------------------------------------------------
STUB_DIR="$(mktemp -d)"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR" "$FIXTURE_DIR" 2>/dev/null || true' EXIT

cat > "$STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
# Stub gh for test-sticky-blocked.sh.
#   gh api repos/.../issues/N --jq '.labels[].name'
#        -> cat $LOOM_TEST_STUB_DIR/labels-N.txt (exit 1 if absent)
#   gh issue edit N ...   -> append the full argv to $LOOM_TEST_STUB_DIR/gh-calls.log
LOG="${LOOM_TEST_STUB_DIR:?stub gh: LOOM_TEST_STUB_DIR not set}/gh-calls.log"

if [[ "${1:-}" == "api" ]]; then
  shift
  path=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --jq|-q|--field|-f|--raw-field|-F|--header|-H|--method|-X|--input)
        shift; [[ $# -gt 0 ]] && shift; continue ;;
      -*) shift; continue ;;
      *) path="$1"; break ;;
    esac
  done
  num="${path##*/}"
  canned="${LOOM_TEST_STUB_DIR}/labels-${num}.txt"
  if [[ -f "$canned" ]]; then cat "$canned"; exit 0; fi
  echo "stub gh: no canned labels for issue $num" >&2
  exit 1
fi

{ printf 'gh'; printf ' %s' "$@"; printf '\n'; } >> "$LOG"
if [[ "${LOOM_TEST_EDIT_FAILS:-}" == "1" ]]; then
  echo "stub gh: simulated edit failure" >&2
  exit 1
fi
exit 0
STUB
chmod +x "$STUB_DIR/gh"

export LOOM_TEST_STUB_DIR="$STUB_DIR"
export PATH="$STUB_DIR:$PATH"

reset_log() { : > "$STUB_DIR/gh-calls.log"; }
calls()     { cat "$STUB_DIR/gh-calls.log" 2>/dev/null; }

# --- fixture registry ---------------------------------------------------------
cat > "$FIXTURE_DIR/registry.json" <<'JSON'
{
  "issues": [
    {
      "issue": 4,
      "settle_labels": ["loom:issue", "loom:curated", "loom:blocked"],
      "ruling": "2026-09-18T22:32:09Z",
      "reason": "test fixture"
    }
  ]
}
JSON
REG=(--registry "$FIXTURE_DIR/registry.json")

echo ""
echo "=== settle: a registered (sticky-blocked) issue ==="

reset_log
out="$("$SUT" settle 4 "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "settle on a registered issue exits 0"
log="$(calls)"
assert_eq "1" "$(grep -c . <<<"$log")" \
  "settle issues EXACTLY ONE gh mutation (atomic — no separable re-apply step)"
assert_contains "$log" "gh issue edit 4 --remove-label loom:building --add-label loom:issue,loom:curated,loom:blocked" \
  "the single release edit names loom:blocked alongside loom:issue and loom:curated"

echo ""
echo "=== settle: an UNregistered issue must NOT gain loom:blocked ==="

reset_log
out="$("$SUT" settle 777 "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "settle on an unregistered issue exits 0"
log="$(calls)"
assert_contains "$log" "gh issue edit 777 --remove-label loom:building --add-label loom:issue" \
  "an unregistered issue gets the ordinary loom:building -> loom:issue release"
assert_not_contains "$log" "loom:blocked" \
  "loom:blocked is NEVER forced onto an issue absent from the registry"
assert_contains "$out" "loom:blocked NOT applied" \
  "the unregistered path says so explicitly on stderr"

echo ""
echo "=== settle: a failing forge mutation is reported, not swallowed ==="

reset_log
out="$(LOOM_TEST_EDIT_FAILS=1 "$SUT" settle 4 "${REG[@]}" 2>&1)"; rc=$?
assert_eq "4" "$rc" "a failed release exits 4 rather than pretending to succeed"

echo ""
echo "=== verify: no drift ==="

printf 'loom:issue\nloom:curated\nloom:blocked\n' > "$STUB_DIR/labels-4.txt"
reset_log
out="$("$SUT" verify "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "verify exits 0 when the sticky labels are present"
assert_eq "" "$(calls)" "verify performs no mutation when there is no drift"

echo ""
echo "=== verify: drift detected (the observed #4 failure mode) ==="

printf 'loom:issue\nloom:curated\n' > "$STUB_DIR/labels-4.txt"
reset_log
out="$("$SUT" verify "${REG[@]}" 2>&1)"; rc=$?
assert_eq "3" "$rc" "verify exits 3 when loom:blocked has been stripped"
assert_contains "$out" "DRIFTED" "verify names the drift on stderr"
assert_eq "" "$(calls)" "verify without --repair never mutates"

echo ""
echo "=== verify --repair: additive re-assert of only what went missing ==="

reset_log
out="$("$SUT" verify --repair "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "verify --repair exits 0 after repairing"
log="$(calls)"
assert_eq "1" "$(grep -c . <<<"$log")" "repair issues exactly one gh mutation"
assert_contains "$log" "gh issue edit 4 --add-label loom:blocked" \
  "repair is purely additive and re-applies only the missing label"
assert_not_contains "$log" "--remove-label" \
  "repair never removes a label it does not own"

echo ""
echo "=== verify: mid-claim (loom:building) is not treated as drift ==="

# While a claim is live the issue carries loom:building instead of loom:issue.
# The sticky invariant is loom:blocked, not the lifecycle label.
printf 'loom:building\nloom:curated\nloom:blocked\n' > "$STUB_DIR/labels-4.txt"
reset_log
out="$("$SUT" verify "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "an issue mid-claim does not register as drift"
assert_eq "" "$(calls)" "no mutation for a mid-claim issue"

echo ""
echo "=== verify: an unregistered issue is a no-op, never forced blocked ==="

printf 'loom:issue\n' > "$STUB_DIR/labels-888.txt"
reset_log
out="$("$SUT" verify 888 --repair "${REG[@]}" 2>&1)"; rc=$?
assert_eq "0" "$rc" "verify on an unregistered issue exits 0"
assert_eq "" "$(calls)" "verify never adds loom:blocked to an unregistered issue"

echo ""
echo "=== usage / argument validation ==="

out="$("$SUT" settle 2>&1)"; rc=$?
assert_eq "2" "$rc" "settle without an issue number is a usage error"
out="$("$SUT" settle abc "${REG[@]}" 2>&1)"; rc=$?
assert_eq "2" "$rc" "settle with a non-numeric issue is a usage error"
out="$("$SUT" bogus 2>&1)"; rc=$?
assert_eq "2" "$rc" "an unknown command is a usage error"
out="$("$SUT" verify --registry "$FIXTURE_DIR/does-not-exist.json" 2>&1)"; rc=$?
assert_eq "5" "$rc" "a missing registry exits 5 rather than silently doing nothing"

echo ""
echo "=== the committed registry is well-formed and covers issue #4 ==="

out="$("$SUT" list 2>&1)"; rc=$?
assert_eq "0" "$rc" "the committed .loom/sticky-blocked.json parses"
assert_contains "$out" "#4" "the committed registry covers issue #4"
assert_contains "$out" "loom:blocked" "the committed #4 entry carries loom:blocked"
assert_contains "$out" "2026-09-18T22:32:09Z" \
  "the committed #4 entry cites the operator ruling that created the invariant"

registry_json="$(cat "$REAL_REGISTRY")"
TESTS_RUN=$((TESTS_RUN + 1))
if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$REAL_REGISTRY" 2>/dev/null; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: .loom/sticky-blocked.json is valid JSON"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: .loom/sticky-blocked.json is not valid JSON"
fi
assert_not_contains "$registry_json" '"issue": 246' \
  "the registry does not accidentally list this issue itself"

echo ""
echo "=== the scheduled enforcement workflow actually invokes verify --repair ==="

# `verify --repair` only helps if something runs it on a cadence tighter than the
# unblock probe that strips the label (every 15-30 min per
# .claude/commands/loom/guide.md). These assertions pin that wiring so a future
# edit cannot quietly reduce the fix back to "an agent has to remember to run it"
# — the exact failure mode #246 was opened about.

WORKFLOW="$REPO_ROOT/.github/workflows/sticky-blocked.yml"

TESTS_RUN=$((TESTS_RUN + 1))
if [[ -f "$WORKFLOW" ]]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: .github/workflows/sticky-blocked.yml exists"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: .github/workflows/sticky-blocked.yml is missing — nothing runs verify --repair automatically"
fi

if [[ -f "$WORKFLOW" ]]; then
    workflow_text="$(cat "$WORKFLOW")"

    # Structural assertions that need no YAML library, so this check is never
    # vacuous on a host without PyYAML.
    assert_contains "$workflow_text" "sticky-blocked.sh verify --repair" \
      "the workflow runs 'sticky-blocked.sh verify --repair'"
    assert_contains "$workflow_text" "issues: write" \
      "the workflow grants issues: write so gh issue edit can mutate labels"
    assert_contains "$workflow_text" "GH_TOKEN:" \
      "the workflow exports GH_TOKEN for the gh CLI"
    assert_contains "$workflow_text" "cron:" \
      "the workflow is scheduled, not only manually dispatchable"

    # Semantic assertions (YAML parse + cron cadence). PyYAML is not in the
    # python3 stdlib; when it is absent the structural assertions above still
    # ran, and this block reports a visible SKIP rather than a silent pass.
    if python3 -c "import yaml" 2>/dev/null; then
        facts="$(python3 - "$WORKFLOW" <<'PY'
import sys, yaml

with open(sys.argv[1]) as fh:
    doc = yaml.safe_load(fh)

# `on:` is parsed as the boolean True under YAML 1.1 (PyYAML's default).
triggers = doc.get("on", doc.get(True)) or {}

print("parses=yes")

perms = (doc.get("permissions") or {})
print("permissions_issues=%s" % perms.get("issues", "MISSING"))

schedules = triggers.get("schedule") or []
crons = [s.get("cron") for s in schedules if isinstance(s, dict)]
print("cron_count=%d" % len(crons))

# Cadence, in minutes, of the tightest `*/N` minute-field schedule present.
best = None
for c in crons:
    minute = (c or "").split()[0] if c else ""
    if minute.startswith("*/") and minute[2:].isdigit():
        n = int(minute[2:])
        best = n if best is None else min(best, n)
print("cadence_minutes=%s" % (best if best is not None else "UNKNOWN"))
# The probe runs every 15-30 min; the repair must not be looser than that.
print("cadence_beats_probe=%s" % ("yes" if best is not None and best <= 15 else "no"))

steps = []
for job in (doc.get("jobs") or {}).values():
    steps.extend(job.get("steps") or [])
repair_steps = [s for s in steps if "verify --repair" in (s.get("run") or "")]
print("repair_steps=%d" % len(repair_steps))
print("repair_step_has_token=%s" % (
    "yes" if repair_steps and "GH_TOKEN" in (repair_steps[0].get("env") or {}) else "no"))
PY
)"
        rc=$?
        assert_eq "0" "$rc" "the workflow YAML parses"
        assert_contains "$facts" "permissions_issues=write" \
          "parsed workflow grants issues: write"
        assert_contains "$facts" "cadence_beats_probe=yes" \
          "parsed cron cadence is at least as tight as the probe's 15-30 min scan"
        assert_contains "$facts" "repair_steps=1" \
          "exactly one job step runs verify --repair"
        assert_contains "$facts" "repair_step_has_token=yes" \
          "the verify --repair step is given GH_TOKEN"
    else
        echo -e "  SKIP: PyYAML unavailable — semantic workflow checks not run"
        echo "        (structural assertions above still ran)"
    fi
fi

echo ""
echo "────────────────────────────────"
echo "Results: $TESTS_PASSED/$TESTS_RUN passed, $TESTS_FAILED failed"
[[ $TESTS_FAILED -gt 0 ]] && exit 1
exit 0
