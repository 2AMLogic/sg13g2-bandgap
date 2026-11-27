#!/usr/bin/env bash
# test-guide-work-plan-receipt.sh - Regression test for issue #14204
#
# update_work_plan() reported its outcome only through `echo` + exit status
# (1 = current / debounced / provenance-refused, 0 = spliced), and
# create_docs_pr()'s docs-PR body was a fixed heredoc claiming
# "WORK_PLAN.md: Regenerated backlog snapshot from current GitHub label
# state" no matter what had actually happened. A debounced or
# provenance-refused tick therefore filed PRs whose body asserted a
# regeneration that never occurred, and any "unchanged / matches live
# labels" claim in a docs PR was free text written by the LLM with no
# machine-recorded receipt to contradict it.
#
# The #14204 fix makes the outcome machine-recorded:
#   - update_work_plan() classifies each of its return points into the global
#     WORK_PLAN_RECEIPT (`written` / `current` /
#     `debounced (elapsed <X>s < window <Y>s)` / `provenance-refused` /
#     `write-failed` / `debounce-check-failed` / `render-failed`), and
#     fingerprints a complete rendered body into
#     WORK_PLAN_RENDER_HASH (first 12 hex of its sha256).
#   - The tick initializes WORK_PLAN_RECEIPT="NOT RUN" before calling, so a
#     tick that never reached the function is visible rather than silent.
#   - create_docs_pr() renders them verbatim as the PR body's
#     `- **WORK_PLAN check**: <receipt> (render-hash <hash>, <UTC time>)`
#     line — the body's ONLY plan-status claim — replacing the fixed bullet.
#
# Verifies that:
#   1. guide.md's update_work_plan() sets WORK_PLAN_RECEIPT at each of its
#      outcome branches and computes the render hash.
#   2. The NOT RUN default exists (documented tick initialization) and
#      create_docs_pr() falls back to NOT RUN / none when the tick never ran
#      the check.
#   3. create_docs_pr() renders the `WORK_PLAN check:` line with the
#      receipt, the render hash and a UTC timestamp, spliced into a body
#      template that no longer carries the old free-text status bullet.
#   4. The role text carries the no-free-text rule (Step 5 prose + the
#      phase's Constraints list).
#   5. THE RECEIPTS, executed rather than grepped: the exact assignment and
#      splice lines extracted VERBATIM from guide.md, evaluated in a sandbox
#      against fixture values, produce each classification — including NOT
#      RUN for a never-called tick.
#   6. The render-hash line computes the real sha256 prefix of the body.
#   7. The generated SKILL.md mirror is in sync (carries the receipt).
#
# Hermetic: greps + sandboxed eval of extracted lines. No forge, network,
# or `gh` calls.

# Test expressions below intentionally match literal shell source.
# shellcheck disable=SC2016
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# guide.md is shipped (installed at .claude/commands/loom/guide.md), so
# resolve it the way each layout actually lays it out: the installed path
# first (consumer repos, and Loom's own dogfooded checkout), falling back
# to the defaults/ source-tree path (a bare source checkout with no
# .claude/commands/loom/ copy yet). See issue #6194 / #6241.
if [[ -f "$REPO_ROOT/.claude/commands/loom/guide.md" ]]; then
    GUIDE_MD="$REPO_ROOT/.claude/commands/loom/guide.md"
else
    GUIDE_MD="$REPO_ROOT/defaults/.claude/commands/loom/guide.md"
fi

# shellcheck source=lib/assert.sh
source "$SCRIPT_DIR/lib/assert.sh"

# Local assert_eq kept: takes (actual, expected, msg); shared assert_eq is (expected, actual, msg).
assert_eq() {
    local actual="$1" expected="$2" msg="$3"
    if [[ "$actual" == "$expected" ]]; then pass "$msg"; else fail "$msg (got '$actual', expected '$expected')"; fi
}

if [[ ! -f "$GUIDE_MD" ]]; then
    echo -e "${RED}FATAL${NC}: guide.md not found at $GUIDE_MD"
    exit 1
fi

# ---------------------------------------------------------------------------
# Test 1: update_work_plan() records a receipt at each of its outcomes
# ---------------------------------------------------------------------------
echo "Test 1: update_work_plan() sets WORK_PLAN_RECEIPT at every outcome branch"

UWP_BODY="$(awk '/^update_work_plan\(\) \{/{flag=1} flag{print} /^\}/{if(flag){exit}}' "$GUIDE_MD")"
if [[ -n "$UWP_BODY" ]]; then
    pass "extracted update_work_plan() from guide.md"
else
    fail "could not extract update_work_plan() from guide.md"
fi

assert_contains "$UWP_BODY" 'record_work_plan_receipt "current"' \
    "the no-change fast path records receipt 'current'"
assert_contains "$UWP_BODY" 'record_work_plan_receipt "debounced (elapsed ${elapsed}s < window ${debounce_secs}s)"' \
    "the debounce suppression records receipt 'debounced' with elapsed vs window figures"
assert_contains "$UWP_BODY" 'record_work_plan_receipt "provenance-refused"' \
    "the provenance gate records receipt 'provenance-refused'"
assert_contains "$UWP_BODY" 'record_work_plan_receipt "written"' \
    "the successful splice records receipt 'written'"
assert_contains "$UWP_BODY" 'record_work_plan_receipt "write-failed"' \
    "a failed splice records receipt 'write-failed' instead of leaving a stale value"
assert_contains "$UWP_BODY" 'WORK_PLAN_RENDER_HASH="$(printf' \
    "update_work_plan() fingerprints the rendered body into WORK_PLAN_RENDER_HASH"
assert_contains "$UWP_BODY" 'cut -c1-12' \
    "the render hash is truncated to its first 12 hex characters"

# The receipt variables must NOT be declared local — they have to survive
# into Step 5's create_docs_pr().
if grep -q 'local WORK_PLAN_RECEIPT\|local WORK_PLAN_RENDER_HASH' <<<"$UWP_BODY"; then
    fail "WORK_PLAN_RECEIPT/WORK_PLAN_RENDER_HASH must not be local to update_work_plan() (Step 5 reads them)"
else
    pass "WORK_PLAN_RECEIPT/WORK_PLAN_RENDER_HASH are globals (not declared local)"
fi

# ---------------------------------------------------------------------------
# Test 2: the NOT RUN default — a tick that never ran the check is visible
# ---------------------------------------------------------------------------
echo ""
echo "Test 2: WORK_PLAN_RECEIPT defaults to NOT RUN before the check runs"

assert_grep 'WORK_PLAN_RECEIPT="NOT RUN"' "$GUIDE_MD" \
    "the tick is documented to initialize WORK_PLAN_RECEIPT to NOT RUN before calling update_work_plan()"

# ---------------------------------------------------------------------------
# Test 3: create_docs_pr() renders the machine-recorded check line
# ---------------------------------------------------------------------------
echo ""
echo "Test 3: create_docs_pr() renders the WORK_PLAN check receipt line"

CDP_BODY="$(awk '/^create_docs_pr\(\) \{/{flag=1} flag{print} /^\}/{if(flag){exit}}' "$GUIDE_MD")"
if [[ -n "$CDP_BODY" ]]; then
    pass "extracted create_docs_pr() from guide.md"
else
    fail "could not extract create_docs_pr() from guide.md"
fi

assert_contains "$CDP_BODY" '- **WORK_PLAN check**: ${wp_receipt:-NOT RUN} (render-hash ${wp_hash:-none}' \
    "the rendered line carries the receipt, a NOT RUN fallback and a render-hash fallback"
assert_contains "$CDP_BODY" "%Y-%m-%dT%H:%M:%SZ" \
    "the rendered line carries a UTC timestamp"
assert_contains "$CDP_BODY" '@@WORK_PLAN_RECEIPT_LINE@@' \
    "the body template carries the placeholder the receipt line is spliced into"
assert_contains "$CDP_BODY" 'DOCS_PR_BODY="${DOCS_PR_BODY/"@@WORK_PLAN_RECEIPT_LINE@@"' \
    "create_docs_pr() splices the receipt line into the quoted-heredoc body"

# THE REGRESSION: the old fixed status bullet must be gone from the PR body
# template — it claimed a regeneration that debounced/refused ticks never
# performed.
assert_not_contains "$CDP_BODY" '**WORK_PLAN.md**: Regenerated' \
    "the old free-text 'Regenerated backlog snapshot' bullet is gone from the PR body"

# The PR body heredoc itself (between the quoted PRBODY markers): the
# placeholder must sit in the Changes list, and no other plan-status prose
# may have crept back in.
PR_HEREDOC_COUNT="$(grep -c "cat <<'PRBODY'" "$GUIDE_MD")"
assert_eq "$PR_HEREDOC_COUNT" "1" "guide.md has exactly one PRBODY heredoc (the docs PR body)"
PR_BODY_TEMPLATE="$(awk "/cat <<'PRBODY'/{flag=1; next} /^PRBODY$/{flag=0} flag" "$GUIDE_MD")"
assert_contains "$PR_BODY_TEMPLATE" '@@WORK_PLAN_RECEIPT_LINE@@' \
    "the quoted heredoc holds the receipt placeholder (the quoted delimiter cannot interpolate it inline)"

# ---------------------------------------------------------------------------
# Test 4: the no-free-text rule is stated in the role text
# ---------------------------------------------------------------------------
echo ""
echo "Test 4: the role text forbids plan-status claims outside the receipt line"

assert_grep "is the PR body's only plan-status" "$GUIDE_MD" \
    "Step 5's prose states the check line is the PR body's only plan-status claim"
assert_grep "states WORK_PLAN's status only through the" "$GUIDE_MD" \
    "the phase Constraints list carries the no-free-text rule (#14204)"
assert_grep 'free-text a claim like "WORK_PLAN.md is' "$GUIDE_MD" \
    "the rule names the forbidden free-text form explicitly"

# ---------------------------------------------------------------------------
# Test 5: THE RECEIPTS, executed — extracted lines evaluated verbatim
# ---------------------------------------------------------------------------
echo ""
echo "Test 5: extracted receipt lines, evaluated in a sandbox, classify each outcome"

# Extract the exact receipt-resolution block from create_docs_pr() (#14259: the
# globals-then-file resolution, the WORK_PLAN_CHECK_LINE assignment AND the
# DOCS_PR_BODY splice that consumes it), leading whitespace stripped so it
# evals at top level in the sandbox. `local` is not valid outside a function,
# so the sandbox wraps the block in one.
SPLICE_LINES="$(awk '/local wp_receipt=/{flag=1} flag{print} /DOCS_PR_BODY="\$\{DOCS_PR_BODY\/"@@WORK_PLAN_RECEIPT_LINE@@"/{if(flag){exit}}' "$GUIDE_MD" | sed 's/^[[:space:]]*//')"
if [[ "$(grep -c 'DOCS_PR_BODY="' <<<"$SPLICE_LINES")" -ge 1 && "$(grep -c 'WORK_PLAN_CHECK_LINE=' <<<"$SPLICE_LINES")" -ge 1 ]]; then
    pass "extracted the receipt resolution + WORK_PLAN_CHECK_LINE assignment + DOCS_PR_BODY splice from create_docs_pr()"
else
    fail "could not extract the receipt resolution + WORK_PLAN_CHECK_LINE assignment + DOCS_PR_BODY splice from create_docs_pr()"
fi

# The receipt helpers, extracted verbatim from guide.md for the sandbox.
RECORD_FN="$(awk '/^record_work_plan_receipt\(\) \{/{flag=1} flag{print} /^\}/{flag=0}' "$GUIDE_MD")"
READ_FN="$(awk '/^read_work_plan_receipt_field\(\) \{/{flag=1} flag{print} /^\}/{flag=0}' "$GUIDE_MD")"
if [[ -n "$RECORD_FN" && -n "$READ_FN" ]]; then
    pass "extracted record_work_plan_receipt()/read_work_plan_receipt_field() from guide.md"
else
    fail "could not extract the receipt helper functions from guide.md"
fi

run_pr_body_splice() {
    # $1 = WORK_PLAN_RECEIPT value ("__unset__" = leave unset, the
    #      never-called tick), $2 = WORK_PLAN_RENDER_HASH (same sentinel),
    # $3 = fixture PR body template, $4 = optional receipt-file content
    # (printf-interpreted; empty/absent = no file). Prints the spliced
    # DOCS_PR_BODY.
    local receipt="$1" hash="$2" body="$3" file_content="${4:-}"
    local SANDBOX
    SANDBOX="$(mktemp -d)"
    mkdir -p "$SANDBOX/wt"
    if [ -n "$file_content" ]; then
        printf '%b' "$file_content" > "$SANDBOX/wt/.loom-work-plan-receipt"
    fi
    {
        printf 'DOCS_WT=%q\n' "$SANDBOX/wt"
        printf '%s\n' "$RECORD_FN" "$READ_FN"
        if [ "$receipt" != "__unset__" ]; then printf 'WORK_PLAN_RECEIPT=%q\n' "$receipt"; fi
        if [ "$hash" != "__unset__" ]; then printf 'WORK_PLAN_RENDER_HASH=%q\n' "$hash"; fi
        printf 'DOCS_PR_BODY=%q\n' "$body"
        printf 'f() {\n%s\n}\nf\n' "$SPLICE_LINES"
        printf '%s\n' 'printf "%s\n" "$DOCS_PR_BODY"'
    } > "$SANDBOX/run.sh"
    bash "$SANDBOX/run.sh"
    rm -rf "$SANDBOX"
}

FIXTURE_TEMPLATE='### Changes
- **WORK_LOG.md**: entries
@@WORK_PLAN_RECEIPT_LINE@@
- **README.md**: n/a'

# 5a. THE NEVER-CALLED TICK: both receipt variables unset — the line must
# read NOT RUN / none, visible rather than silent.
RESULT="$(run_pr_body_splice "__unset__" "__unset__" "$FIXTURE_TEMPLATE")"
assert_contains "$RESULT" '- **WORK_PLAN check**: NOT RUN (render-hash none,' \
    "a tick that never called update_work_plan() renders 'NOT RUN (render-hash none, ...)'"
assert_not_contains "$RESULT" '@@WORK_PLAN_RECEIPT_LINE@@' \
    "the placeholder is fully consumed by the splice"

# 5b. A debounced tick: the classification and the refused render's hash
# surface verbatim in the line.
RESULT="$(run_pr_body_splice "debounced (elapsed 300s < window 3600s)" "6c47a827e98f" "$FIXTURE_TEMPLATE")"
assert_contains "$RESULT" '- **WORK_PLAN check**: debounced (elapsed 300s < window 3600s) (render-hash 6c47a827e98f,' \
    "a debounced tick's receipt and render hash render verbatim into the PR body"

# The consumer helper runs only in the Guide's managed linked worktree.
FIXTURE=$(mktemp -d)
trap 'rm -rf -- "$FIXTURE"' EXIT
DOCS_WT="$FIXTURE/docs-guide"
export DOCS_WT
git init -q "$FIXTURE/repo" || exit 1
git -C "$FIXTURE/repo" config user.name "Guide test"
git -C "$FIXTURE/repo" config user.email "guide@example.invalid"
git -C "$FIXTURE/repo" config commit.gpgsign false
git -C "$FIXTURE/repo" commit -q --allow-empty -m fixture || exit 1
git -C "$FIXTURE/repo" worktree add -q -b docs/guide-update-test "$DOCS_WT" || exit 1
mkdir -p "$DOCS_WT/.loom/scripts"
touch "$DOCS_WT/.loom-managed"
cp "$SCRIPT_DIR/../guide-work-plan.sh" "$DOCS_WT/.loom/scripts/" || exit 1

# 5c. The debounced receipt assignment, extracted from update_work_plan(),
# composes its elapsed/window figures from the live arithmetic variables.
DEBOUNCED_LINE="$(grep -m1 'record_work_plan_receipt "debounced' "$GUIDE_MD" | sed 's/^[[:space:]]*//')"
SANDBOX="$(mktemp -d)"
{
    printf '%s\n' "$RECORD_FN"
    printf 'WORK_PLAN_RENDER_HASH=6c47a827e98f\n'
    printf 'elapsed=300\ndebounce_secs=3600\n'
    printf '%s\n' "$DEBOUNCED_LINE"
    printf '%s\n' 'printf "%s\n" "$WORK_PLAN_RECEIPT"'
} > "$SANDBOX/run.sh"
RESULT="$(bash "$SANDBOX/run.sh")"
assert_eq "$RESULT" "debounced (elapsed 300s < window 3600s)" \
    "the extracted debounced assignment composes elapsed/window from the tick's arithmetic"
rm -rf "$SANDBOX"

# 5d. (#14259) SEPARATE SHELL INVOCATIONS: Step 3 runs in one process, Step 5
# in another, so no global survives. The receipt must still arrive populated.
RESULT="$(run_pr_body_splice "__unset__" "__unset__" "$FIXTURE_TEMPLATE" 'receipt=written\nrender_hash=6c47a827e98f\n')"
assert_contains "$RESULT" '- **WORK_PLAN check**: written (render-hash 6c47a827e98f,' \
    "unset globals + receipt file => the PR body line is populated from the file"

# 5e. The tick's `NOT RUN` initialization is not an outcome: it must not mask a
# real receipt file.
RESULT="$(run_pr_body_splice "NOT RUN" "__unset__" "$FIXTURE_TEMPLATE" 'receipt=current\nrender_hash=abcdef012345\n')"
assert_contains "$RESULT" '- **WORK_PLAN check**: current (render-hash abcdef012345,' \
    "a NOT RUN initialization global does not mask a receipt file"

# 5f. Absent file + unset globals keeps the visible NOT RUN fallback.
RESULT="$(run_pr_body_splice "__unset__" "__unset__" "$FIXTURE_TEMPLATE")"
assert_contains "$RESULT" '- **WORK_PLAN check**: NOT RUN (render-hash none,' \
    "absent receipt file => NOT RUN (render-hash none, ...)"

# 5g. Globals still win when set (single-shell execution unchanged).
RESULT="$(run_pr_body_splice "written" "111111111111" "$FIXTURE_TEMPLATE" 'receipt=current\nrender_hash=222222222222\n')"
assert_contains "$RESULT" '- **WORK_PLAN check**: written (render-hash 111111111111,' \
    "a global carrying a real outcome wins over the file"

# 5h. A debounced classification (contains parens and '<') survives the file.
RESULT="$(run_pr_body_splice "__unset__" "__unset__" "$FIXTURE_TEMPLATE" 'receipt=debounced (elapsed 300s < window 3600s)\nrender_hash=6c47a827e98f\n')"
assert_contains "$RESULT" '- **WORK_PLAN check**: debounced (elapsed 300s < window 3600s) (render-hash 6c47a827e98f,' \
    "a debounced receipt round-trips through the file intact"

# 5i. The writer, run as its OWN process, then the reader in a SECOND process.
SANDBOX="$FIXTURE"
{
    printf '%s\n' "$RECORD_FN"
    printf 'WORK_PLAN_RENDER_HASH=cafe00112233\n'
    printf '%s\n' 'record_work_plan_receipt "write-failed"'
} > "$SANDBOX/step3.sh"
{
    printf '%s\n' "$RECORD_FN" "$READ_FN"
    printf '%s\n' 'printf "%s|%s|%s\n" "${WORK_PLAN_RECEIPT:-unset}" "$(read_work_plan_receipt_field receipt)" "$(read_work_plan_receipt_field render_hash)"'
} > "$SANDBOX/step5.sh"
bash "$SANDBOX/step3.sh"
RESULT="$(bash "$SANDBOX/step5.sh")"
assert_eq "$RESULT" "unset|write-failed|cafe00112233" \
    "write-failed recorded by one process is recovered by a second process"

# 5j. The file is never staged: the staging paths are exact names, none of
# which is the receipt file, and no blanket add exists in create_docs_pr().
CDP_CODE="$(grep -v '^[[:space:]]*#' <<<"$CDP_BODY")"
assert_not_contains "$CDP_CODE" 'add -A' "create_docs_pr() never blanket-stages (comments excluded)"
assert_not_contains "$CDP_BODY" '.loom-work-plan-receipt' \
    "create_docs_pr() never stages the receipt file by name"

# 5k. Execute the skip in the SAME worktree where 5i left a receipt.
printf '%s\n' '{"guide":{"docsMaintenance":{"skipDocs":["WORK_PLAN.md"]}}}' > "$DOCS_WT/.loom/config.json"
if bash -c "$UWP_BODY"$'\nupdate_work_plan' || [[ -e "$DOCS_WT/.loom-work-plan-receipt" ]]; then
    fail "a skipped check must clear the preceding receipt"
else
    pass "a skipped check clears the preceding receipt"
fi

# ---------------------------------------------------------------------------
# Test 6: the render-hash line computes the real sha256 prefix
# ---------------------------------------------------------------------------
echo ""
echo "Test 6: WORK_PLAN_RENDER_HASH is the first 12 hex of the body's sha256"

HASH_LINE="$(grep -m1 'WORK_PLAN_RENDER_HASH="$(printf' "$GUIDE_MD" | sed 's/^[[:space:]]*//')"
SANDBOX="$(mktemp -d)"
FIXTURE_RENDER='## Ready

- **#1234**: fixture issue
'
{
    printf 'new_body=%q\n' "$FIXTURE_RENDER"
    printf '%s\n' "$HASH_LINE"
    printf '%s\n' 'printf "%s\n" "$WORK_PLAN_RENDER_HASH"'
} > "$SANDBOX/run.sh"
RESULT="$(bash "$SANDBOX/run.sh")"
EXPECTED_HASH="$(printf '%s\n' "$FIXTURE_RENDER" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-12)"
assert_eq "$RESULT" "$EXPECTED_HASH" \
    "the extracted hash assignment equals an independently computed 12-hex sha256 prefix"
rm -rf "$SANDBOX"

# ---------------------------------------------------------------------------
# Test 7: the generated SKILL.md mirror is in sync (#14204)
# ---------------------------------------------------------------------------
echo ""
echo "Test 7: the loom-guide SKILL.md mirror carries the receipt contract"

# Same installed-first resolution as guide.md above: the skill mirror ships
# under defaults/, and a consumer repo's installed copy (if it has one) sits
# at .agents/skills/. Neither layout present -> nothing to assert here.
if [[ -f "$REPO_ROOT/.agents/skills/loom-guide/SKILL.md" ]]; then
    SKILL_MD="$REPO_ROOT/.agents/skills/loom-guide/SKILL.md"
elif [[ -f "$REPO_ROOT/defaults/.agents/skills/loom-guide/SKILL.md" ]]; then
    SKILL_MD="$REPO_ROOT/defaults/.agents/skills/loom-guide/SKILL.md"
else
    echo "SKIP: no loom-guide SKILL.md mirror in this layout" >&2
    SKILL_MD=""
fi
if [[ -n "$SKILL_MD" ]]; then
    assert_grep 'WORK_PLAN_RECEIPT' "$SKILL_MD" \
        "the generated SKILL.md mirror was regenerated with the receipt variable"
    assert_grep 'WORK_PLAN check' "$SKILL_MD" \
        "the generated SKILL.md mirror was regenerated with the check line"
fi

# Test 8: run the two Guide steps in separate shells. Git pushes to a local
# bare repository. Capture the body passed to gh pr create at the forge boundary.
printf '%s\n' '{}' > "$DOCS_WT/.loom/config.json"
printf '%s\n' 'preamble' '<!-- guide:plan-body:start -->' 'old' \
    '<!-- guide:plan-body:end -->' 'tail' > "$DOCS_WT/WORK_PLAN.md"
touch "$DOCS_WT/README.md" "$DOCS_WT/WORK_LOG.md"
git -C "$DOCS_WT" add WORK_PLAN.md WORK_LOG.md README.md
git -C "$DOCS_WT" commit -qm 'baseline docs' || exit 1
git init -q --bare "$FIXTURE/remote.git" || exit 1
git -C "$DOCS_WT" remote add origin https://github.com/example/fixture.git
git -C "$DOCS_WT" remote set-url --push origin "$FIXTURE/remote.git"
export LOOM_DEFAULT_BRANCH=fixture-base
git -C "$DOCS_WT" update-ref refs/remotes/origin/fixture-base HEAD || exit 1
mkdir -p "$DOCS_WT/.loom/scripts/lib"
cp "$SCRIPT_DIR/../lib/default-branch.sh" "$DOCS_WT/.loom/scripts/lib/" || exit 1
printf '#!/bin/sh\nexit 0\n' > "$DOCS_WT/.loom/scripts/docs-guide-lock.sh"
chmod +x "$DOCS_WT/.loom/scripts/docs-guide-lock.sh"
extract_step() {
    awk -v heading="### Step $1:" '
        !block && /^### / { active = index($0, heading) == 1 }
        active && /^```bash$/ { block = 1; next }
        block && /^```$/ { block = 0; next }
        block { print }
    ' "$GUIDE_MD"
}
extract_step 3 > "$FIXTURE/step3"
extract_step 5 > "$FIXTURE/step5"
for step in step3 step5; do
    assert_grep '^(update_work_plan|create_docs_pr)\(\)' "$FIXTURE/$step" "extracted $step command block"
    for hook in guard-destructive-generic guard-destructive guard-loom-workflow; do
        if decision=$(jq -n --arg cwd "$DOCS_WT" --rawfile cmd "$FIXTURE/$step" \
                '{tool_name:"Bash",cwd:$cwd,tool_input:{command:$cmd}}' \
                | LOOM_ROLE=guide bash "$REPO_ROOT/.loom/hooks/$hook.sh") && [[ -z $decision ]]; then
            pass "$hook allows the Guide's $step"
        else
            fail "$hook refused the Guide's $step"
        fi
    done
done
cp "$FIXTURE/step3" "$FIXTURE/update.sh"
cat >> "$FIXTURE/update.sh" <<'STEP3'
render_plan_body() { printf '%s\n' "${RENDER:-new}"; }
last_work_plan_write_epoch() { echo "${LAST_WRITE:-0}"; }
update_work_plan
STEP3
{
    cat "$FIXTURE/step5"
    cat <<'STEP5'
cd "$DOCS_WT"
WORK_LOG_ARCHIVE_GLOB='work_log/WORK_LOG_*.md'
should_defer_for_pool_pressure() { [[ ${DEFER:-} == yes ]]; }
gh() {
    case "$1 $2" in
        'pr list') return 0 ;;
        'pr create')
            [[ ${7:-} == --body ]] || return 1
            printf '%s\n' "$8" > "$CAPTURE"
            echo captured
            ;;
        *) return 1 ;;
    esac
}
create_docs_pr
STEP5
} > "$FIXTURE/create.sh"
export CAPTURE="$FIXTURE/pr-body" LOOM_WORK_PLAN_DEBOUNCE_SECS=3600
export LOOM_WORK_PLAN_DEBOUNCE_NOW=10000 GH_READ=false

run_create() {
    # These are different Bash processes even when the test was launched by
    # a Guide tick with receipt variables in its environment.
    env -u WORK_PLAN_RECEIPT -u WORK_PLAN_RENDER_HASH bash -e -o pipefail "$FIXTURE/create.sh"
}

# A retry in a fresh process must keep the first write's receipt and region.
bash -e "$FIXTURE/update.sh" || exit 1
first_plan=$(git -C "$DOCS_WT" hash-object WORK_PLAN.md)
if ! LAST_WRITE=9700 bash "$FIXTURE/update.sh"; then fail "retry must recognize the pending write"; fi
assert_eq "$(git -C "$DOCS_WT" hash-object WORK_PLAN.md)" "$first_plan" "retry preserves the pending rewrite byte for byte"
assert_eq "$(cat "$DOCS_WT/.loom-work-plan-receipt")" $'receipt=written\nrender_hash=7aa7a5359173' \
    "retry preserves the matching durable written receipt"
run_create || exit 1
assert_grep '^- \*\*WORK_PLAN check\*\*: written \(render-hash 7aa7a5359173, [0-9TZ:-]+\)$' \
    "$CAPTURE" "fresh Step 5 shell reports the rewritten region hash"
assert_eq "$(grep -c '^- \*\*WORK_PLAN check\*\*:' "$CAPTURE")" 1 "exactly one receipt reaches the forge"
assert_eq "$(sed -n '/^_Generated: /{n;p;}' "$DOCS_WT/WORK_PLAN.md")" new "the spliced region contains the rendered text"
assert_eq "$(git -C "$DOCS_WT" diff-tree --no-commit-id --name-only -r HEAD)" WORK_PLAN.md "only the plan is committed"

# Simulate merge before the next tick, which omits Step 3 entirely.
git -C "$DOCS_WT" update-ref refs/remotes/origin/fixture-base HEAD || exit 1
TICK_RESET=$(grep -m1 '^"\$DOCS_WT/.loom/scripts/guide-work-plan.sh" reset' "$GUIDE_MD")
[[ -n $TICK_RESET ]] && bash -ec "$TICK_RESET" || exit 1
echo log >> "$DOCS_WT/WORK_LOG.md"
run_create || exit 1
assert_grep '^- \*\*WORK_PLAN check\*\*: NOT RUN \(render-hash none,' "$CAPTURE" "skipped tick cannot reuse the preceding written receipt"

# Fail only the receipt write after a successful splice. Even a same-shell
# 'written' global must not allow the staged region to escape without proof.
helper="$DOCS_WT/.loom/scripts/guide-work-plan.sh"
mv "$helper" "$helper.real"
cat > "$helper" <<'FAIL_RECORD'
#!/usr/bin/env bash
if [[ $1 == record && $2 == written ]]; then exit 1; fi
exec "$0.real" "$@"
FAIL_RECORD
chmod +x "$helper"
if RENDER=unrecorded bash "$FIXTURE/update.sh" || git -C "$DOCS_WT" diff --quiet HEAD -- WORK_PLAN.md; then
    fail "fixture must fail the final receipt write after changing the region"
else
    pass "injected failure after splice and before receipt persistence"
fi
mv "$helper.real" "$helper"
unrecorded_hash=$(printf '%s\n' unrecorded | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-12)
expect_refusal() {
    local message=$1 saved_head
    shift
    saved_head=$(git -C "$DOCS_WT" rev-parse HEAD)
    rm -f "$CAPTURE"
    if "$@" ||
        [[ -e $CAPTURE || $(git -C "$DOCS_WT" rev-parse HEAD) != "$saved_head" ||
           $(git --git-dir="$FIXTURE/remote.git" rev-parse refs/heads/docs/guide-update-test) != "$saved_head" ]]; then
        fail "$message"
    else
        pass "$message"
    fi
}
expect_refusal "fresh Step 5 refuses to commit, push or file the unreceipted splice" run_create
WORK_PLAN_RECEIPT=written WORK_PLAN_RENDER_HASH="$unrecorded_hash" \
    expect_refusal "a matching shell global cannot replace the missing receipt" bash "$FIXTURE/create.sh"
"$helper" record current "$unrecorded_hash" || exit 1
expect_refusal "a current receipt with the staged hash cannot authorize a changed region" run_create
"$helper" record written 000000000000 || exit 1
expect_refusal "a written receipt for another body cannot authorize a changed region" run_create
# Recover by rerunning the real Step 3 and publish using its durable result.
RENDER=unrecorded bash -e "$FIXTURE/update.sh" || exit 1
WORK_PLAN_RECEIPT=current WORK_PLAN_RENDER_HASH=000000000000 bash -e "$FIXTURE/create.sh" || exit 1
assert_contains "$(cat "$CAPTURE")" "written (render-hash $unrecorded_hash," "Step 5 publishes the verified staged hash despite stale globals"
# A changed region already committed on this docs branch still needs proof.
"$helper" reset || exit 1
echo followup >> "$DOCS_WT/WORK_LOG.md"
expect_refusal "Step 5 checks an earlier local plan commit against the branch base" run_create
git -C "$DOCS_WT" update-ref refs/remotes/origin/fixture-base HEAD || exit 1
# A change outside the markers can ship on a tick that skipped Step 3.
echo footer >> "$DOCS_WT/WORK_PLAN.md"
run_create || exit 1
assert_contains "$(cat "$CAPTURE")" 'NOT RUN (render-hash none,' "outside-only plan edit can ship on a skipped tick"
sed 's/^_Generated: .* (snapshot/_Generated: 2000-01-01T00:00:00Z (snapshot/' \
    "$DOCS_WT/WORK_PLAN.md" > "$FIXTURE/stamp-only"
cp "$FIXTURE/stamp-only" "$DOCS_WT/WORK_PLAN.md"
"$helper" record written "$unrecorded_hash" || exit 1
expect_refusal "a matching body hash cannot authorize a stamp-only edit" run_create
git -C "$DOCS_WT" restore --source=HEAD --staged --worktree -- WORK_PLAN.md || exit 1

# A deferred tick restores just the documents it staged, including a new archive.
mkdir -p "$DOCS_WT/work_log"
echo deferred >> "$DOCS_WT/WORK_LOG.md"
echo archive > "$DOCS_WT/work_log/WORK_LOG_2026-01.md"
echo unrelated > "$DOCS_WT/work_log/notes.md"
DEFER=yes run_create || exit 1
git -C "$DOCS_WT" diff --exit-code HEAD -- WORK_LOG.md work_log || exit 1
if [[ ! -e "$DOCS_WT/work_log/WORK_LOG_2026-01.md" && -f "$DOCS_WT/work_log/notes.md" ]]; then
    pass "a deferred tick restores only its staged docs"
else
    fail "defer did not restore its archive or touched unrelated files"
fi

# Actual early returns, including provenance and splice failures, leave the
# committed plan intact and classify the attempted render for Step 5.
expect_outcome() {
    local expected="$1"
    shift
    if env "$@" bash "$FIXTURE/update.sh"; then
        fail "expected update_work_plan to return nonzero for $expected"
    fi
    assert_eq "$(sed -n 's/^receipt=//p' "$DOCS_WT/.loom-work-plan-receipt")" "$expected" "recorded $expected"
}
expect_outcome current RENDER=unrecorded
expect_outcome 'debounced (elapsed 300s < window 3600s)' RENDER=different LAST_WRITE=9700
expect_outcome provenance-refused 'RENDER=- **#1**: unavailable'
git -C "$DOCS_WT" diff --exit-code -- WORK_PLAN.md || exit 1
printf '%s\n' 'missing markers' > "$DOCS_WT/WORK_PLAN.md"
expect_outcome write-failed
assert_eq "$(cat "$DOCS_WT/WORK_PLAN.md")" 'missing markers' "failed splice preserves the file"

# Drive the installed renderer with a forge stub. Only the Ready query has a row.
# Require the pinned repository on listings, cache reads and the title endpoint.
cat > "$FIXTURE/gh-read" <<'GH_READ_STUB'
#!/usr/bin/env bash
[[ $GH_REPO == example/fixture && $GH_CACHE_REPO_ID == example/fixture ]] || exit 1
ready_fixture='[{"number":42,"title":"Keep this issue"}]'
case "$1 $2" in
    'api repos/example/fixture/issues/42') echo 'Keep this issue' ;;
    'issue list'|'pr list')
        if [[ $3 == --state && $4 == merged ]]; then
            [[ ${FAIL_LIST:-} != merged ]] || exit 1
            exit 0
        fi
        [[ $3 == --label && $4 != "${FAIL_LIST:-}" ]] || exit 1
        case "$4" in
            loom:issue) echo "${READY_JSON:-$ready_fixture}" ;;
            loom:pr) echo '[]' ;;
        esac
        ;;
    *) exit 1 ;;
esac
GH_READ_STUB
chmod +x "$FIXTURE/gh-read"
run_renderer() {
    env GH_READ="$FIXTURE/gh-read" GUIDE_DOCS_PR_EXCLUDE=true "$@" \
        bash -c 'source "$1" && update_work_plan' _ "$FIXTURE/step3"
}
for origin in ssh://git@github.com/example/fixture.git git@github.com:example/fixture.git \
    https://github.com/example/fixture.git; do
    git -C "$DOCS_WT" remote set-url origin "$origin" || exit 1
    git -C "$DOCS_WT" restore -- WORK_PLAN.md || exit 1
    if run_renderer && grep -Fxq -- '- **#42**: Keep this issue' "$DOCS_WT/WORK_PLAN.md" &&
        grep -Fxq receipt=written "$DOCS_WT/.loom-work-plan-receipt"; then
        pass "verified and wrote the Ready row for $origin"
    else
        fail "could not verify and write the Ready row for $origin"
    fi
done

# Establish a complete plan, then fail one listing or its JSON transformation.
run_create || exit 1
git -C "$DOCS_WT" update-ref refs/remotes/origin/fixture-base HEAD || exit 1
failures=(READY_JSON=malformed)
for label in very-important important issue building review-requested pr curated architect hermit epic; do
    failures+=("FAIL_LIST=loom:$label")
done
for failure in "${failures[@]}"; do
    if ! run_renderer "$failure" && git -C "$DOCS_WT" diff --quiet HEAD -- WORK_PLAN.md &&
        grep -Fxq receipt=render-failed "$DOCS_WT/.loom-work-plan-receipt" &&
        grep -Fxq render_hash=none "$DOCS_WT/.loom-work-plan-receipt"; then
        pass "preserved the complete plan and recorded the failure for $failure"
    else
        fail "plan or failure receipt was wrong for $failure"
    fi
done
echo log >> "$DOCS_WT/WORK_LOG.md"
run_create || exit 1
assert_grep '^- \*\*WORK_PLAN check\*\*: render-failed \(render-hash none,' "$CAPTURE" \
    "fresh Step 5 shell reports the failed render without a hash"

# The debounce listing runs after a complete render, so its failure keeps the hash.
if ! run_renderer FAIL_LIST=merged 'READY_JSON=[]' &&
    git -C "$DOCS_WT" diff --quiet HEAD -- WORK_PLAN.md &&
    grep -Fxq receipt=debounce-check-failed "$DOCS_WT/.loom-work-plan-receipt" &&
    grep -Eq '^render_hash=[0-9a-f]{12}$' "$DOCS_WT/.loom-work-plan-receipt"; then
    pass "failed history lookup preserves the plan and the complete render's hash"
else
    fail "failed history lookup did not preserve the plan and record its outcome"
fi

# ---------------------------------------------------------------------------
echo ""
echo "================================"
echo "Tests run:    $TESTS_RUN"
echo -e "Tests passed: ${GREEN}${TESTS_PASSED}${NC}"
if [[ $TESTS_FAILED -gt 0 ]]; then
    echo -e "Tests failed: ${RED}${TESTS_FAILED}${NC}"
    exit 1
fi
echo "All tests passed"
exit 0
