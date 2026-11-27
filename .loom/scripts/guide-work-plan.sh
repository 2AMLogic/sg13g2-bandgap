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
case "${1:-}" in
    reset)
        rm -f -- "$receipt"
        exit
        ;;
    record)
        [[ $# == 3 && $3 =~ ^[0-9a-f]{12}$ ]] || exit 1
        ;;
    splice)
        [[ -f WORK_PLAN.md && ! -L WORK_PLAN.md ]] || exit 1
        ;;
    *)
        echo "Usage: guide-work-plan.sh reset | record OUTCOME HASH | splice < body" >&2
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
