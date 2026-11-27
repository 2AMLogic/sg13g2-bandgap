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
tmp=""
base_tmp=""
cleanup() {
    [[ -z $tmp ]] || rm -f -- "$tmp"
    [[ -z $base_tmp ]] || rm -f -- "$base_tmp"
}
trap cleanup EXIT

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

merge_base() {
    local branch
    # shellcheck source=lib/default-branch.sh
    source .loom/scripts/lib/default-branch.sh
    branch=$(loom_default_branch) || return 1
    # An earlier Step 5 may already have committed locally on this branch.
    git merge-base HEAD "refs/remotes/origin/$branch"
}

splice_region() {
    [[ -f WORK_PLAN.md && ! -L WORK_PLAN.md ]] || return 1
    tmp=$(mktemp ./.loom-work-plan.XXXXXX) || return 1
    cp -p WORK_PLAN.md "$tmp" || return 1
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
    ' WORK_PLAN.md > "$tmp" || return 1
    # awk's print terminates the last line; keep an unterminated final line as-is.
    if [[ -s WORK_PLAN.md && -n $(tail -c1 WORK_PLAN.md) ]]; then
        truncate -s -1 "$tmp" || return 1
    fi
    mv -f -- "$tmp" WORK_PLAN.md
}

# Print the verified hash for a pending rewrite, or nothing for an unchanged
# region. Exit 3 means Step 3 can retry a rewrite whose receipt is missing
# or stale. Other failures cannot establish the plan state.
check_written() {
    local source=$1 base base_region region base_body body hash
    local -a diff=(git diff --quiet)
    case "$source" in
        staged) diff+=(--cached) ;;
        worktree) ;;
        *) return 2 ;;
    esac
    base=$(merge_base) || return 1
    if "${diff[@]}" "$base" -- WORK_PLAN.md; then return 0; fi
    base_region=$(git show "$base:WORK_PLAN.md" | plan_region) || return 1
    if [[ $source == staged ]]; then
        region=$(git show :WORK_PLAN.md | plan_region) || return 1
    else
        region=$(plan_region < WORK_PLAN.md) || return 1
    fi
    if [[ $region == "$base_region" ]]; then return 0; fi
    base_body=$(printf '%s\n' "$base_region" | unstamped_body) || return 1
    body=$(printf '%s\n' "$region" | unstamped_body) || return 1
    if [[ $body == "$base_body" ]]; then
        echo "Only the generation stamp changed in the plan region." >&2
        return 1
    fi
    hash=$(printf '%s\n' "$body" | { sha256sum 2>/dev/null || shasum -a 256; } | cut -c1-12) || return 1
    if ! cmp -s "$receipt" <(printf 'receipt=written\nrender_hash=%s\n' "$hash"); then
        echo "Changed WORK_PLAN.md region lacks a written receipt matching $hash." >&2
        return 3
    fi
    printf '%s\n' "$hash"
}

# When the worktree holds a verified pending rewrite and stdin's fresh render
# matches the merge-base body, splice the exact base region back between the
# markers. Exit 3 when no verified pending rewrite reverts to the base body.
restore_base() {
    local pending_hash base base_body new_body
    pending_hash=$(check_written worktree) || return 3
    [[ -n $pending_hash ]] || return 3
    new_body=$(cat) || return 1
    base=$(merge_base) || return 1
    base_tmp=$(mktemp ./.loom-work-plan-base.XXXXXX) || return 1
    git show "$base:WORK_PLAN.md" | plan_region > "$base_tmp" || return 1
    base_body=$(unstamped_body < "$base_tmp") || return 1
    [[ $new_body == "$base_body" ]] || return 3
    splice_region < "$base_tmp" || return 1
    rm -f -- "$receipt" || return 1
}

case "${1:-}" in
    check-written)
        [[ $# == 2 ]] || exit 2
        check_written "$2"
        exit
        ;;
    restore-base)
        [[ $# == 1 ]] || exit 2
        restore_base
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
        tmp=$(mktemp ./.loom-work-plan.XXXXXX)
        printf 'receipt=%s\nrender_hash=%s\n' "$2" "$3" > "$tmp"
        mv -f -- "$tmp" "$receipt"
        ;;
    splice)
        [[ $# == 1 ]] || exit 2
        splice_region
        ;;
    *)
        echo "Usage: guide-work-plan.sh reset | record OUTCOME HASH | splice < body | restore-base < body | check-written {worktree|staged}" >&2
        exit 2
        ;;
esac
