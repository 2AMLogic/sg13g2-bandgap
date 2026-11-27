#!/usr/bin/env bash
# Worktree-local counterpart of the Guide write verbs in rjwalters/loom#15222
# for daemons predating those verbs. Run the copy in the docs-guide worktree.
set -euo pipefail

cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
if [[ ${PWD##*/} != docs-guide || ! -f .git || ! -f .loom-managed ||
      $(git rev-parse --show-toplevel) != "$PWD" ]]; then
    echo "Guide writes require the managed docs-guide worktree." >&2
    exit 1
fi

receipt=.loom-work-plan-receipt
# Match the receiving Judge's marker, stamp and trailing-newline rules.
plan_region() {
    awk '/^<!-- guide:plan-body:start -->$/ { if (start++) exit 1; next }
         /^<!-- guide:plan-body:end -->$/   { if (!start || end++) exit 1; next }
         start && !end { print }
         END { if (start != 1 || end != 1) exit 1 }'
}

unstamped_body() {
    sed '1{/^_Generated: .* (snapshot; compare against live labels)_$/d;}'
}

# Print the verified hash for a pending rewrite, or nothing for an unchanged
# region. Exit 3 means Step 3 can retry a rewrite whose receipt is missing
# or stale. Other failures cannot establish the plan state.
check_written() {
    local source=$1 branch base base_region region base_body body hash
    local -a diff=(git diff --quiet)
    case "$source" in
        staged) diff+=(--cached) ;;
        worktree) ;;
        *) return 2 ;;
    esac
    # shellcheck source=lib/default-branch.sh
    source .loom/scripts/lib/default-branch.sh
    branch=$(loom_default_branch)
    # An earlier Step 5 may already have committed locally on this branch.
    base=$(git merge-base HEAD "refs/remotes/origin/$branch")
    if "${diff[@]}" "$base" -- WORK_PLAN.md; then return 0; fi
    base_region=$(git show "$base:WORK_PLAN.md" | plan_region)
    if [[ $source == staged ]]; then
        region=$(git show :WORK_PLAN.md | plan_region)
    else
        region=$(plan_region < WORK_PLAN.md)
    fi
    if [[ $region == "$base_region" ]]; then return 0; fi
    base_body=$(printf '%s\n' "$base_region" | unstamped_body)
    body=$(printf '%s\n' "$region" | unstamped_body)
    if [[ $body == "$base_body" ]]; then
        echo "Only the generation stamp changed in the plan region." >&2
        return 1
    fi
    hash=$(printf '%s\n' "$body" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-12)
    if ! cmp -s "$receipt" <(printf 'receipt=written\nrender_hash=%s\n' "$hash"); then
        echo "Changed WORK_PLAN.md region lacks a written receipt matching $hash." >&2
        return 3
    fi
    printf '%s\n' "$hash"
}

case "${1:-}" in
    check-written)
        [[ $# == 2 ]] || exit 2
        check_written "$2"
        exit
        ;;
    reset)
        rm -f -- "$receipt"
        exit
        ;;
    record)
        [[ $# == 3 ]] || exit 1
        if [[ $2 == render-failed ]]; then
            [[ $3 == none ]] || exit 1
        else
            [[ $3 =~ ^[0-9a-f]{12}$ ]] || exit 1
        fi
        ;;
    splice)
        [[ -f WORK_PLAN.md && ! -L WORK_PLAN.md ]] || exit 1
        ;;
    *)
        echo "Usage: guide-work-plan.sh reset | record OUTCOME HASH | splice < body | check-written {worktree|staged}" >&2
        exit 2
        ;;
esac

# Replace in the same directory so a failed write leaves the old file intact.
tmp=$(mktemp ./.loom-work-plan.XXXXXX)
trap 'rm -f -- "$tmp"' EXIT
if [[ $1 == record ]]; then
    printf 'receipt=%s\nrender_hash=%s\n' "$2" "$3" > "$tmp"
    mv -f -- "$tmp" "$receipt"
else
    cp -p WORK_PLAN.md "$tmp"
    awk '
        /^<!-- guide:plan-body:start -->$/ {
            if (start++) exit 1
            print
            while ((read_status = getline line < "/dev/stdin") > 0) print line
            if (read_status < 0) exit 1
            next
        }
        /^<!-- guide:plan-body:end -->$/ { if (!start || end++) exit 1 }
        !start || end { print }
        END { if (start != 1 || end != 1) exit 1 }
    ' WORK_PLAN.md > "$tmp"
    mv -f -- "$tmp" WORK_PLAN.md
fi
