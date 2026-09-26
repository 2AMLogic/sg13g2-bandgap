#!/usr/bin/env bash
# test-tracker-state-comment.sh - Unit tests for tracker-state-comment.sh
# (#248, the pinned-comment replacement for the addComment-cap-broken
# maintenance-log convention).
#
# Black-box tests, mirroring test-sweep-lease-renew.sh's stubbing pattern:
# `gh` is stubbed on PATH (real `jq` is used unstubbed), the real script is
# invoked as a subprocess, assertions run against stdout/stderr/exit code.
#
# Covers:
#   (a) ensure creates a NEW pinned comment (POST) when none exists yet and
#       the issue is below the comment cap
#   (b) ensure PATCHes the EXISTING pinned comment (never POSTs a duplicate)
#       once one exists, preserving the marker as the literal first line
#   (c) ensure ignores a comment that merely CONTAINS the marker text without
#       it being the first line (startswith, not substring)
#   (d) ensure's trailer is replaced, not accumulated, across repeated calls
#   (e) ensure with no pinned comment AND a failing POST (simulating the
#       2500-comment cap) -> exit 2, message points at `bootstrap`
#   (f) bootstrap refuses without --force (no PATCH performed)
#   (g) bootstrap with --force PATCHes the named EXISTING comment, overwrites
#       its body, and logs the previous first line to stderr as an audit trail
#   (h) bootstrap requires a numeric --comment-id
#   (i) show finds and prints the pinned comment; exits 2 when none exists
#   (j) --body and --body-file are mutually exclusive; at least one required
#   (k) --marker overrides the default prefix end-to-end (ensure + show)
#
# Usage:
#   ./.loom/scripts/tests/test-tracker-state-comment.sh

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$TEST_DIR/.." && pwd)"
SCRIPT="$SCRIPTS_DIR/tracker-state-comment.sh"

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
    if [[ "$haystack" == *"$needle"* ]]; then
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
    if [[ "$haystack" != *"$needle"* ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Did not expect substring: '$needle'"
        echo "    In: '$haystack'"
    fi
}

if [[ ! -x "$SCRIPT" ]]; then
    echo -e "${RED}FATAL${NC}: $SCRIPT not found or not executable" >&2
    exit 2
fi

STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR" 2>/dev/null || true' EXIT

# --- Stub gh on PATH ---------------------------------------------------
#   gh api [-R repo] repos/{owner}/{repo}/issues/<N>/comments --paginate
#       -> cat $D/comments.json (or "[]"; fails if comments-fail exists)
#   gh api [-R repo] --method POST repos/{owner}/{repo}/issues/<N>/comments -F body=@-
#       -> fails if post-fail exists (simulates the 2500-comment cap);
#          otherwise reads stdin, assigns the next id (starting at 9000),
#          appends to $D/post-calls.log, prints {"id": <id>}
#   gh api [-R repo] repos/{owner}/{repo}/issues/comments/<id> [--jq EXPR]
#       -> cat $D/get-<id>.json (fails if get-fail exists), piped through the
#          real `jq -r EXPR` when --jq was given, mirroring real `gh api`
#          semantics
#   gh api [-R repo] --method PATCH repos/{owner}/{repo}/issues/comments/<id> -F body=@<path>
#       -> reads the file the -F value's "@" prefix references into
#          $D/patch-<id>-N.body, appends "<id>" to $D/patch-calls.log,
#          prints "{}" (fails if patch-fail exists)
cat > "$STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
D="${LOOM_TEST_STUB_DIR:?stub gh: LOOM_TEST_STUB_DIR not set}"
if [[ "$1" == "api" ]]; then
  shift
  method="GET"
  path=""
  field_flag=""
  field_kv=""
  jq_expr=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --method) method="$2"; shift 2 ;;
      -R) shift 2 ;;
      --paginate) shift ;;
      --jq) jq_expr="$2"; shift 2 ;;
      -f|--raw-field) field_flag="-f"; field_kv="$2"; shift 2 ;;
      -F|--field) field_flag="-F"; field_kv="$2"; shift 2 ;;
      *)
        if [[ -z "$path" ]]; then path="$1"; fi
        shift
        ;;
    esac
  done

  # --- Single-comment GET/PATCH: repos/*/issues/comments/<id> (NOTE: no
  # issue-number segment -- must be checked BEFORE the per-issue list route)
  if [[ "$path" == repos/*/issues/comments/* ]]; then
    id="${path##*/}"
    if [[ "$method" == "GET" ]]; then
      if [[ -f "$D/get-fail" ]]; then
        echo "stub gh: get single comment failed" >&2
        exit 1
      fi
      canned="$D/get-$id.json"
      body_json="{}"
      [[ -f "$canned" ]] && body_json="$(cat "$canned")"
      if [[ -n "$jq_expr" ]]; then
        echo "$body_json" | jq -r "$jq_expr"
      else
        echo "$body_json"
      fi
      exit 0
    fi
    if [[ "$method" == "PATCH" ]]; then
      n=$(( $(cat "$D/patch-count-$id" 2>/dev/null || echo 0) + 1 ))
      echo "$n" > "$D/patch-count-$id"
      if [[ -f "$D/patch-fail" ]]; then
        echo "stub gh: patch failed" >&2
        exit 1
      fi
      val="${field_kv#*=}"
      if [[ "$field_flag" == "-F" && "$val" == "@-" ]]; then
        cat > "$D/patch-$id-$n.body"
      elif [[ "$field_flag" == "-F" && "$val" == @* ]]; then
        cat "${val#@}" > "$D/patch-$id-$n.body" 2>/dev/null || true
      else
        printf '%s' "$val" > "$D/patch-$id-$n.body"
      fi
      echo "$id" >> "$D/patch-calls.log"
      echo '{}'
      exit 0
    fi
    echo "stub gh: unhandled single-comment method: $method" >&2
    exit 3
  fi

  # --- Per-issue comment list: repos/*/issues/*/comments ------------------
  if [[ "$method" == "GET" && "$path" == repos/*/issues/*/comments ]]; then
    if [[ -f "$D/comments-fail" ]]; then
      echo "stub gh: comments fetch failed" >&2
      exit 1
    fi
    canned="$D/comments.json"
    if [[ -f "$canned" ]]; then cat "$canned"; else echo "[]"; fi
    exit 0
  fi
  if [[ "$method" == "POST" && "$path" == repos/*/issues/*/comments ]]; then
    if [[ -f "$D/post-fail" ]]; then
      echo "GraphQL: Commenting is disabled on issues with more than 2500 comments (addComment)" >&2
      exit 1
    fi
    body="$(cat)"
    n=$(( $(cat "$D/post-count" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$D/post-count"
    new_id=$((9000 + n))
    printf '%s' "$body" > "$D/post-$new_id.body"
    echo "$new_id" >> "$D/post-calls.log"
    printf '{"id": %s}' "$new_id"
    exit 0
  fi

  echo "stub gh: unhandled api args: method=$method path=$path" >&2
  exit 3
fi
echo "stub gh: unhandled args: $*" >&2
exit 3
STUB
chmod +x "$STUB_DIR/gh"

# A `github-app-token.sh` stub speaking the "not configured" envelope so
# forge_gh_perm_safe's escalation ladder has nothing beyond rung 1 (ambient)
# to try -- these tests only exercise rung 1, which the `gh` stub above
# handles deterministically.
cat > "$STUB_DIR/github-app-token.sh" <<'MINT'
#!/usr/bin/env bash
echo '{"status":"not_configured","message":"github app not configured"}'
MINT
chmod +x "$STUB_DIR/github-app-token.sh"

export LOOM_TEST_STUB_DIR="$STUB_DIR"
export PATH="$STUB_DIR:$PATH"
export LOOM_GITHUB_APP_SCRIPT="$STUB_DIR/github-app-token.sh"

reset_state() {
    rm -f "$STUB_DIR"/comments.json "$STUB_DIR"/comments-fail
    rm -f "$STUB_DIR"/post-fail "$STUB_DIR"/post-count "$STUB_DIR"/post-calls.log "$STUB_DIR"/post-*.body
    rm -f "$STUB_DIR"/get-fail "$STUB_DIR"/get-*.json
    rm -f "$STUB_DIR"/patch-fail "$STUB_DIR"/patch-*.body "$STUB_DIR"/patch-count-* "$STUB_DIR"/patch-calls.log
    unset LOOM_PERSONAL_GH_TOKEN 2> /dev/null || true
}

run_script() {
    OUT="$("$SCRIPT" "$@" 2>"$STUB_DIR/stderr.log")"
    RC=$?
    ERR="$(cat "$STUB_DIR/stderr.log" 2>/dev/null || true)"
}

echo "Testing tracker-state-comment.sh..."

# --- (a) ensure creates a new pinned comment when none exists yet ---------
reset_state
echo "[]" > "$STUB_DIR/comments.json"
run_script ensure 4 --body "First tracker re-check content."
assert_eq "0" "$RC" "(a) ensure exits 0 when it creates a new pinned comment"
POST_CALLS_A="$(cat "$STUB_DIR/post-calls.log" 2>/dev/null || echo "")"
assert_eq "9001" "$POST_CALLS_A" "(a) exactly one POST was made"
NEW_BODY_A="$(cat "$STUB_DIR/post-9001.body" 2>/dev/null || echo MISSING)"
FIRST_LINE_A="$(head -n1 <<< "$NEW_BODY_A")"
assert_eq "<!-- loom:tracker-state -->" "$FIRST_LINE_A" "(a) the marker is the literal first line of the created comment"
assert_contains "$NEW_BODY_A" "First tracker re-check content." "(a) the created comment carries the supplied content"
assert_contains "$NEW_BODY_A" "<!-- loom:tracker-state-updated " "(a) the created comment carries the updated-trailer"

# --- (b) ensure PATCHes the existing pinned comment, never POSTs again ----
reset_state
cat > "$STUB_DIR/comments.json" <<'JSON'
[
  {"id": 1, "body": "unrelated comment, no marker here"},
  {"id": 42, "body": "<!-- loom:tracker-state -->\nOld re-check content."}
]
JSON
run_script ensure 4 --body "Second tracker re-check content."
assert_eq "0" "$RC" "(b) ensure exits 0 when it updates the existing pinned comment"
assert_eq "" "$(cat "$STUB_DIR/post-calls.log" 2>/dev/null || echo "")" "(b) no POST is made once a pinned comment already exists"
PATCH_CALLS_B="$(cat "$STUB_DIR/patch-calls.log" 2>/dev/null || echo "")"
assert_eq "42" "$PATCH_CALLS_B" "(b) exactly one PATCH, targeting the existing comment id"
BODY_B="$(cat "$STUB_DIR/patch-42-1.body" 2>/dev/null || echo MISSING)"
FIRST_LINE_B="$(head -n1 <<< "$BODY_B")"
assert_eq "<!-- loom:tracker-state -->" "$FIRST_LINE_B" "(b) the marker is preserved as the literal first line"
assert_contains "$BODY_B" "Second tracker re-check content." "(b) the PATCH body carries the new content"
assert_not_contains "$BODY_B" "Old re-check content." "(b) the PATCH body replaces (not appends to) the old content"

# --- (c) startswith, not substring ----------------------------------------
reset_state
cat > "$STUB_DIR/comments.json" <<'JSON'
[
  {"id": 7, "body": "Discussing the format: `<!-- loom:tracker-state -->` is the marker, but this is prose."}
]
JSON
run_script ensure 4 --body "New content."
assert_eq "9001" "$(cat "$STUB_DIR/post-calls.log" 2>/dev/null || echo "")" "(c) a comment merely mentioning the marker (not as its first line) is not treated as the pinned comment -- ensure creates a NEW one instead"

# --- (d) trailer replaced, not accumulated, across repeated calls --------
reset_state
cat > "$STUB_DIR/comments.json" <<'JSON'
[
  {"id": 42, "body": "<!-- loom:tracker-state -->\nRound one."}
]
JSON
run_script ensure 4 --body "Round one."
sleep 1.1
jq --rawfile body "$STUB_DIR/patch-42-1.body" \
    '(.[] | select(.id == 42) | .body) = $body' \
    "$STUB_DIR/comments.json" > "$STUB_DIR/comments.json.tmp"
mv "$STUB_DIR/comments.json.tmp" "$STUB_DIR/comments.json"
run_script ensure 4 --body "Round two."
TRAILER_COUNT_D="$(grep -c "loom:tracker-state-updated" "$STUB_DIR/patch-42-2.body" 2>/dev/null || echo 0)"
assert_eq "1" "$TRAILER_COUNT_D" "(d) exactly ONE updated-trailer line after two ensure calls (no accumulation)"
assert_not_contains "$(cat "$STUB_DIR/patch-42-2.body")" "Round one." "(d) the second ensure's content replaces the first's"

# --- (e) no pinned comment + POST fails (simulated cap) -> exit 2 --------
reset_state
echo "[]" > "$STUB_DIR/comments.json"
touch "$STUB_DIR/post-fail"
run_script ensure 4 --body "Content that cannot be posted."
assert_eq "2" "$RC" "(e) a failing POST (simulated 2500-comment cap) is exit 2, not a crash"
assert_contains "$ERR" "bootstrap" "(e) the error message points the caller at 'bootstrap'"

# --- (f) bootstrap refuses without --force --------------------------------
reset_state
echo '{"id": 55, "body": "Some pre-existing comment content."}' > "$STUB_DIR/get-55.json"
run_script bootstrap 4 --comment-id 55 --body "Adopted content."
assert_eq "1" "$RC" "(f) bootstrap without --force exits 1"
assert_contains "$ERR" "force" "(f) the refusal message mentions --force"
assert_eq "" "$(cat "$STUB_DIR/patch-calls.log" 2>/dev/null || echo "")" "(f) no PATCH is performed without --force"

# --- (g) bootstrap with --force overwrites the named EXISTING comment ----
reset_state
echo '{"id": 55, "body": "Some pre-existing comment content."}' > "$STUB_DIR/get-55.json"
run_script bootstrap 4 --comment-id 55 --body "Adopted content." --force
assert_eq "0" "$RC" "(g) bootstrap with --force succeeds"
assert_contains "$ERR" "Some pre-existing comment content." "(g) the previous first line is logged to stderr as an audit trail"
PATCH_CALLS_G="$(cat "$STUB_DIR/patch-calls.log" 2>/dev/null || echo "")"
assert_eq "55" "$PATCH_CALLS_G" "(g) exactly one PATCH, targeting the requested comment id"
BODY_G="$(cat "$STUB_DIR/patch-55-1.body" 2>/dev/null || echo MISSING)"
assert_eq "<!-- loom:tracker-state -->" "$(head -n1 <<< "$BODY_G")" "(g) bootstrap prepends the marker as the literal first line"
assert_contains "$BODY_G" "Adopted content." "(g) bootstrap writes the supplied content"
assert_not_contains "$BODY_G" "Some pre-existing comment content." "(g) bootstrap OVERWRITES the previous body, not appends to it"

# --- (h) bootstrap requires a numeric --comment-id ------------------------
reset_state
run_script bootstrap 4 --comment-id abc --body "x" --force
assert_eq "1" "$RC" "(h) a non-numeric --comment-id is a usage error"

# --- (i) show finds and prints the pinned comment; exit 2 if none --------
reset_state
cat > "$STUB_DIR/comments.json" <<'JSON'
[
  {"id": 42, "body": "<!-- loom:tracker-state -->\nCurrent state."}
]
JSON
echo '{"id": 42, "body": "<!-- loom:tracker-state -->\nCurrent state."}' > "$STUB_DIR/get-42.json"
run_script show 4
assert_eq "0" "$RC" "(i) show exits 0 when a pinned comment exists"
assert_contains "$OUT" "id=42" "(i) show prints the comment id"
assert_contains "$OUT" "Current state." "(i) show prints the comment body"

reset_state
echo "[]" > "$STUB_DIR/comments.json"
run_script show 4
assert_eq "2" "$RC" "(i) show exits 2 when no pinned comment exists"

# --- (j) --body/--body-file mutual exclusion and requiredness -------------
reset_state
run_script ensure 4 --body "x" --body-file /tmp/does-not-matter
assert_eq "1" "$RC" "(j) --body and --body-file together is a usage error"

reset_state
run_script ensure 4
assert_eq "1" "$RC" "(j) neither --body nor --body-file is a usage error"

# --- (k) --marker overrides the default prefix end-to-end -----------------
reset_state
echo "[]" > "$STUB_DIR/comments.json"
run_script ensure 4 --body "Custom-marker content." --marker "<!-- loom:custom-state -->"
assert_eq "0" "$RC" "(k) ensure with a custom --marker succeeds"
NEW_BODY_K="$(cat "$STUB_DIR/post-9001.body" 2>/dev/null || echo MISSING)"
assert_eq "<!-- loom:custom-state -->" "$(head -n1 <<< "$NEW_BODY_K")" "(k) the custom marker is used as the literal first line"
# Feed it back as the forge's held state, then confirm `show` with the SAME
# custom marker finds it, and the DEFAULT marker does not.
jq -n --arg id "42" --arg body "$NEW_BODY_K" '[{id: ($id|tonumber), body: $body}]' > "$STUB_DIR/comments.json"
echo "$NEW_BODY_K" | jq -Rs '{id: 42, body: .}' > "$STUB_DIR/get-42.json"
run_script show 4 --marker "<!-- loom:custom-state -->"
assert_eq "0" "$RC" "(k) show with the matching custom marker finds the comment"
run_script show 4
assert_eq "2" "$RC" "(k) show with the DEFAULT marker does not find a custom-marker comment"

# --- Summary ---------------------------------------------------------------
echo ""
echo "Tests run: $TESTS_RUN, Passed: $TESTS_PASSED, Failed: $TESTS_FAILED"
if [[ "$TESTS_FAILED" -gt 0 ]]; then
    exit 1
fi
exit 0
