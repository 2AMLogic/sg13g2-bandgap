#!/usr/bin/env bash
# tracker-state-comment.sh - Pinned "state" comment convention for a tracker
# issue that cannot reliably accept NEW comments (Issue #248).
#
# ## Why this exists
#
# GitHub caps `addComment` (the mutation behind `gh issue comment` / a plain
# `gh api --method POST .../comments`) at 2500 comments per issue. Issue #4 in
# this repo hit that cap on 2026-09-26: `gh api graphql` against
# `issue(number:4).comments.totalCount` returns exactly `2500`, and every
# subsequent `addComment` attempt fails with
#
#   GraphQL: Commenting is disabled on issues with more than 2500 comments (addComment)
#
# permanently -- this is GitHub's hard cap, not a transient rate limit, so no
# retry or backoff recovers it. `docs/tracker-4-settle-protocol.md`'s
# maintenance-log convention (a fresh "Tracker re-check, <timestamp> ..."
# comment posted on every periodic pass) is built entirely on `addComment` and
# is therefore now permanently broken on #4.
#
# `gh api --method PATCH repos/{owner}/{repo}/issues/comments/<id>` (editing
# an EXISTING comment) is a different mutation with no such cap -- confirmed
# both by GitHub's own API surface (the cap is documented against `addComment`
# specifically) and empirically in THIS repo: `sweep-lease-renew.sh` (#6180)
# already PATCHes its lease comment on #4 every renewal cycle in production,
# and multiple lease comments on #4 show `updated_at` timestamps well after
# their `created_at` (e.g. comment 5846657767: created 13:28:59Z, renewed to
# 13:34:26Z) -- i.e. PATCH is already succeeding against #4 today, cap and
# all.
#
# This script gives the maintenance-log convention the same escape hatch:
# instead of POSTing a new "Tracker re-check" comment every pass, it PATCHes
# ONE pinned comment (identified by a literal first-line marker, exactly the
# `sweep-lease-renew.sh` / `sweep-lease-publish.sh` convention) with the
# latest content. Read `docs/tracker-4-settle-protocol.md` (S7) for the
# convention writeup and why POST-based bootstrap does not work retroactively
# on an already-capped issue.
#
# ## Marker format
#
# The marker is the comment body's LITERAL FIRST LINE:
#
#   <!-- loom:tracker-state -->
#
# Everything after it is free-form content the caller supplies; this script
# never parses it. A trailing `<!-- loom:tracker-state-updated at=... by=... -->`
# line (mirroring `sweep-lease-renew.sh`'s `loom:lease-renewed` trailer) is
# appended/replaced on every write purely so `updated_at` genuinely advances
# and a human skimming the raw body can see when it was last touched -- no
# reader may treat that `at=` value as authoritative; the comment's own
# forge-assigned `updated_at` always is.
#
# ## Commands
#
#   tracker-state-comment.sh ensure <issue> (--body TEXT | --body-file PATH)
#                                            [--marker PREFIX]
#     Find the newest comment on <issue> whose body starts with the marker
#     prefix (default: "<!-- loom:tracker-state -->").
#       - If found: PATCH it with the marker + supplied content. This is the
#         steady-state path and is NOT subject to the addComment cap.
#       - If NOT found: attempt to POST a brand-new comment (this only works
#         on an issue that has not yet hit the cap -- the normal case for
#         every tracker except one already at 2500). On a POST failure this
#         prints a message pointing at `bootstrap` and exits 2 -- it does
#         NOT guess which existing comment to repurpose, since that is a
#         judgment call this script cannot make safely.
#     Exit codes: 0 success (created or updated); 1 usage error; 2 no pinned
#     comment exists AND creating one failed (use `bootstrap`); 3 a `gh`
#     read/write failure.
#
#   tracker-state-comment.sh bootstrap <issue> --comment-id ID
#                                       (--body TEXT | --body-file PATH)
#                                       [--marker PREFIX] --force
#     Explicit, one-time adoption of an EXISTING comment as the pinned state
#     comment -- the only path that works on an issue that already hit the
#     2500-comment cap, since no new comment can ever be POSTed there again.
#     PATCHes comment <ID> to `marker + supplied content`, OVERWRITING
#     whatever that comment held before. Requires --force (no default): this
#     is destructive to the previous content of comment <ID>, and this script
#     will not guess that a human/operator has confirmed it is safe to
#     repurpose. Prints the comment's current first line to stderr before
#     overwriting, as an audit trail.
#     Exit codes: 0 success; 1 usage error (including missing --force); 3 a
#     `gh` read/write failure.
#
#   tracker-state-comment.sh show <issue> [--marker PREFIX]
#     Read-only. Prints "id=<ID>" then the full body of the pinned comment on
#     stdout if one exists; exits 2 with a message on stderr if none is found.
#     Never mutates anything -- safe to run against #4 at any time.
#
# Usage:
#   .loom/scripts/tracker-state-comment.sh show 4
#   .loom/scripts/tracker-state-comment.sh ensure 4 --body-file /tmp/recheck.md
#   .loom/scripts/tracker-state-comment.sh bootstrap 4 --comment-id 5846658947 \
#       --body-file /tmp/recheck.md --force

set -euo pipefail

MARKER_PREFIX_DEFAULT="<!-- loom:tracker-state -->"
UPDATED_MARKER_PREFIX="<!-- loom:tracker-state-updated "

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# forge_gh_perm_safe (Issue #6541): escalation-ladder-aware `gh` wrapper, same
# resilience convention sweep-lease-renew.sh's PATCH call sites use.
# shellcheck source=./lib/forge-helpers.sh
source "$SCRIPT_DIR/lib/forge-helpers.sh"

usage() {
    awk 'NR < 3 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"
    exit 1
}

gh_repo_args() {
    if [[ -n "${LOOM_REPO:-}" ]]; then
        printf -- '-R\n%s\n' "$LOOM_REPO"
    fi
}

iso_now() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# resolve_body <body> <body-file> -> prints the resolved content, or nothing
# (and a non-zero return) if neither/both were given.
resolve_body() {
    local body="$1" body_file="$2"
    if [[ -n "$body" && -n "$body_file" ]]; then
        echo "ERROR: --body and --body-file are mutually exclusive" >&2
        return 1
    fi
    if [[ -n "$body_file" ]]; then
        [[ -f "$body_file" ]] || {
            echo "ERROR: --body-file '$body_file' does not exist" >&2
            return 1
        }
        cat "$body_file"
        return 0
    fi
    if [[ -n "$body" ]]; then
        printf '%s' "$body"
        return 0
    fi
    echo "ERROR: one of --body or --body-file is required" >&2
    return 1
}

# find_pinned_comment_id <issue> <marker> <repo_args...> -> prints the id of
# the newest comment on <issue> whose body starts with <marker>, nothing if
# none exists. Returns non-zero only on a genuine `gh` read failure.
find_pinned_comment_id() {
    local issue="$1" marker="$2"
    shift 2
    local -a repo_args=("$@")

    local comments_json
    if ! comments_json="$(forge_gh_perm_safe api "${repo_args[@]+"${repo_args[@]}"}" "repos/{owner}/{repo}/issues/${issue}/comments" --paginate)"; then
        echo "ERROR: 'gh api .../issues/${issue}/comments --paginate' failed (escalation ladder exhausted)" >&2
        return 1
    fi

    jq -r --arg marker "$marker" '
        [ .[] | select(.body != null and (.body | startswith($marker))) ]
        | sort_by(.id) | reverse | .[0].id // empty
    ' <<< "$comments_json" 2> /dev/null || true
}

# assemble_body <marker> <content> -> the marker as the literal first line,
# the caller's content, and a freshly-timestamped trailer, mirroring
# sweep-lease-renew.sh's stripped-old-trailer/rewritten-new-trailer shape so
# repeated writes never accumulate duplicate trailer lines.
assemble_body() {
    local marker="$1" content="$2"
    local stripped
    stripped="$(printf '%s\n' "$content" | grep -v "^${UPDATED_MARKER_PREFIX}" || true)"
    printf '%s\n%s\n\n%sat=%s by=tracker-state-comment.sh (#248) -->\n' \
        "$marker" "$stripped" "$UPDATED_MARKER_PREFIX" "$(iso_now)"
}

# patch_comment <comment_id> <body> <repo_args...> -- writes <body> to a temp
# file (not a stdin pipe) and PATCHes via `-F body=@<path>`, same as
# sweep-lease-renew.sh's cmd_renew_once: forge_gh_perm_safe's escalation
# ladder can re-run this call across multiple credential rungs, and a stdin
# pipe is only readable once.
patch_comment() {
    local comment_id="$1" body="$2"
    shift 2
    local -a repo_args=("$@")

    local patch_body_file
    patch_body_file="$(mktemp)"
    printf '%s' "$body" > "$patch_body_file"
    if ! forge_gh_perm_safe api "${repo_args[@]+"${repo_args[@]}"}" --method PATCH "repos/{owner}/{repo}/issues/comments/${comment_id}" \
        -F "body=@${patch_body_file}" \
        > /dev/null; then
        rm -f "$patch_body_file"
        return 1
    fi
    rm -f "$patch_body_file"
    return 0
}

# post_comment <issue> <body> <repo_args...> -> prints the new comment id on
# success. Fails (non-zero, message on stderr) on any POST error, including
# the 2500-comment cap -- callers must not swallow this into a silent no-op,
# since it is the signal that `bootstrap` is now required.
post_comment() {
    local issue="$1" body="$2"
    shift 2
    local -a repo_args=("$@")

    local post_out
    if ! post_out="$(printf '%s' "$body" \
        | forge_gh_perm_safe api "${repo_args[@]+"${repo_args[@]}"}" --method POST "repos/{owner}/{repo}/issues/${issue}/comments" -F body=@- 2>&1)"; then
        echo "$post_out" >&2
        return 1
    fi
    jq -r '.id // empty' <<< "$post_out" 2> /dev/null || true
}

cmd_ensure() {
    local issue="${1:-}"
    shift || true
    [[ "$issue" =~ ^[0-9]+$ ]] || {
        echo "ERROR: ensure requires a positive integer issue number (got: '${issue:-}')" >&2
        exit 1
    }

    local body="" body_file="" marker="$MARKER_PREFIX_DEFAULT"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --body)
                body="${2:-}"
                shift 2
                ;;
            --body-file)
                body_file="${2:-}"
                shift 2
                ;;
            --marker)
                marker="${2:-}"
                shift 2
                ;;
            *)
                echo "ERROR: ensure: unknown flag '$1'" >&2
                exit 1
                ;;
        esac
    done

    local content
    content="$(resolve_body "$body" "$body_file")" || exit 1

    local -a repo_args=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && repo_args+=("$line")
    done < <(gh_repo_args)

    local candidate_id
    candidate_id="$(find_pinned_comment_id "$issue" "$marker" "${repo_args[@]+"${repo_args[@]}"}")" || exit 3

    local new_body
    new_body="$(assemble_body "$marker" "$content")"

    if [[ -n "$candidate_id" ]]; then
        if ! patch_comment "$candidate_id" "$new_body" "${repo_args[@]+"${repo_args[@]}"}"; then
            echo "ERROR: PATCH of pinned state comment ${candidate_id} on issue #${issue} failed" >&2
            exit 3
        fi
        echo "OK: updated pinned state comment ${candidate_id} on issue #${issue}" >&2
        exit 0
    fi

    # No pinned comment exists yet. Try to create one -- this only succeeds
    # on an issue below the addComment cap.
    local new_id
    if new_id="$(post_comment "$issue" "$new_body" "${repo_args[@]+"${repo_args[@]}"}")" && [[ -n "$new_id" ]]; then
        echo "OK: created pinned state comment ${new_id} on issue #${issue}" >&2
        exit 0
    fi

    echo "ERROR: no pinned state comment exists on issue #${issue} (marker=${marker}...) and creating one failed" >&2
    echo "  This is expected once an issue has hit GitHub's 2500-comment addComment cap" >&2
    echo "  (see docs/tracker-4-settle-protocol.md S7). Pick an existing comment on the" >&2
    echo "  issue that is safe to repurpose and run:" >&2
    echo "    $0 bootstrap ${issue} --comment-id <ID> --body-file <path> --force" >&2
    exit 2
}

cmd_bootstrap() {
    local issue="${1:-}"
    shift || true
    [[ "$issue" =~ ^[0-9]+$ ]] || {
        echo "ERROR: bootstrap requires a positive integer issue number (got: '${issue:-}')" >&2
        exit 1
    }

    local comment_id="" body="" body_file="" marker="$MARKER_PREFIX_DEFAULT" force=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --comment-id)
                comment_id="${2:-}"
                shift 2
                ;;
            --body)
                body="${2:-}"
                shift 2
                ;;
            --body-file)
                body_file="${2:-}"
                shift 2
                ;;
            --marker)
                marker="${2:-}"
                shift 2
                ;;
            --force)
                force=1
                shift
                ;;
            *)
                echo "ERROR: bootstrap: unknown flag '$1'" >&2
                exit 1
                ;;
        esac
    done

    [[ "$comment_id" =~ ^[0-9]+$ ]] || {
        echo "ERROR: bootstrap requires --comment-id <positive integer> (got: '${comment_id:-}')" >&2
        exit 1
    }
    if [[ "$force" -ne 1 ]]; then
        echo "ERROR: bootstrap: refusing without --force -- this OVERWRITES comment ${comment_id}'s current body permanently. Re-run with --force once you have confirmed that comment is safe to repurpose." >&2
        exit 1
    fi

    local content
    content="$(resolve_body "$body" "$body_file")" || exit 1

    local -a repo_args=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && repo_args+=("$line")
    done < <(gh_repo_args)

    local old_body
    if ! old_body="$(forge_gh_perm_safe api "${repo_args[@]+"${repo_args[@]}"}" "repos/{owner}/{repo}/issues/comments/${comment_id}" --jq '.body // empty')"; then
        echo "ERROR: could not read existing comment ${comment_id} on issue #${issue} before overwriting it -- aborting without writing anything" >&2
        exit 3
    fi
    local old_first_line="${old_body%%$'\n'*}"
    echo "AUDIT: overwriting comment ${comment_id} on issue #${issue}; its previous first line was: ${old_first_line}" >&2

    local new_body
    new_body="$(assemble_body "$marker" "$content")"
    if ! patch_comment "$comment_id" "$new_body" "${repo_args[@]+"${repo_args[@]}"}"; then
        echo "ERROR: PATCH of comment ${comment_id} on issue #${issue} failed -- bootstrap did not complete" >&2
        exit 3
    fi
    echo "OK: bootstrapped comment ${comment_id} on issue #${issue} as the pinned state comment (marker=${marker})" >&2
}

cmd_show() {
    local issue="${1:-}"
    shift || true
    [[ "$issue" =~ ^[0-9]+$ ]] || {
        echo "ERROR: show requires a positive integer issue number (got: '${issue:-}')" >&2
        exit 1
    }

    local marker="$MARKER_PREFIX_DEFAULT"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --marker)
                marker="${2:-}"
                shift 2
                ;;
            *)
                echo "ERROR: show: unknown flag '$1'" >&2
                exit 1
                ;;
        esac
    done

    local -a repo_args=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && repo_args+=("$line")
    done < <(gh_repo_args)

    local candidate_id
    candidate_id="$(find_pinned_comment_id "$issue" "$marker" "${repo_args[@]+"${repo_args[@]}"}")" || exit 3

    if [[ -z "$candidate_id" ]]; then
        echo "no pinned state comment found for issue #${issue} (marker=${marker}...)" >&2
        exit 2
    fi

    local body
    body="$(forge_gh_perm_safe api "${repo_args[@]+"${repo_args[@]}"}" "repos/{owner}/{repo}/issues/comments/${candidate_id}" --jq '.body // empty')"
    echo "id=${candidate_id}"
    printf '%s\n' "$body"
}

main() {
    local cmd="${1:-}"
    shift || true
    case "$cmd" in
        ensure) cmd_ensure "$@" ;;
        bootstrap) cmd_bootstrap "$@" ;;
        show) cmd_show "$@" ;;
        -h | --help | "") usage ;;
        *)
            echo "ERROR: unknown command '$cmd'" >&2
            usage
            ;;
    esac
}

main "$@"
