#!/usr/bin/env bash
# sticky-blocked.sh — atomic release + drift repair for issues an operator has
# ruled must PERMANENTLY carry `loom:blocked` (this repo: issue #4).
#
# WHY THIS EXISTS (issue #246)
# ---------------------------
# `loom:blocked` kept disappearing from issue #4 after every sweep pass. The
# label-history evidence (repo-level `GET /repos/:owner/:repo/issues/events`,
# which — unlike the per-issue events endpoint, truncated at 310 events on #4 —
# still records recent label churn) shows the actual shape of the loss:
#
#   2026-09-21T19:23:22Z labeled   loom:blocked    <- settle re-applied it
#   2026-09-21T19:32:39Z unlabeled loom:blocked    <- SOLITARY removal, 9m later
#   2026-09-22T00:39:19Z labeled   loom:blocked
#   2026-09-22T00:54:21Z unlabeled loom:blocked    <- 15m later
#   2026-09-23T02:22:11Z labeled   loom:blocked
#   2026-09-23T02:34:03Z unlabeled loom:blocked    <- 12m later
#   2026-09-23T06:16:27Z labeled   loom:blocked
#   2026-09-23T06:27:55Z unlabeled loom:blocked    <- 11m later
#
# Each removal is a lone `unlabeled loom:blocked` with NO paired label change,
# minutes AFTER the claim was already released — so it is neither the
# dispatch-time `loom:issue` -> `loom:building` flip (those are same-second
# PAIRS) nor a settle pass forgetting step two (the `labeled loom:blocked`
# event proves the re-apply happened every time). It is a later pass running
# the documented `loom:blocked` unblock probe: because #4 already carries
# `loom:issue`, that probe's
# `gh issue edit N --remove-label loom:blocked --add-label loom:issue` emits
# exactly one visible event — the solitary removal above. See
# docs/tracker-4-settle-protocol.md for the full write-up, and
# rjwalters/loom#8742 for the upstream gap (Loom has no concept of a
# permanently/operator-ruled blocked issue, so the probe cannot know to leave
# this one alone).
#
# So this script does two things:
#   settle  — release a `loom:building` claim in ONE atomic `gh issue edit`
#             that names every label the issue must end up with, so the
#             re-apply of `loom:blocked` can never be a separately-skippable
#             second step.
#   verify  — re-assert the invariant afterwards (`--repair`), because an
#             atomic settle alone cannot stop a later unblock probe from
#             stripping the label again.
#
# SCOPE GUARANTEE: the ONLY issues that ever gain `loom:blocked` from this
# script are those listed in .loom/sticky-blocked.json. `settle` on any other
# issue performs the ordinary `loom:building` -> `loom:issue` release and never
# adds `loom:blocked`.
#
# Usage:
#   sticky-blocked.sh settle <ISSUE> [--dry-run] [--repo OWNER/NAME]
#   sticky-blocked.sh verify [<ISSUE>...] [--repair] [--dry-run] [--repo OWNER/NAME]
#   sticky-blocked.sh list
#
# Exit codes:
#   0 — success (settled; or verify found no drift / repaired all drift)
#   2 — usage error
#   3 — verify found drift and --repair was NOT requested
#   4 — a forge mutation failed (settle, or verify --repair)
#   5 — the registry file is missing or unparseable

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR/../..")"
REGISTRY="${LOOM_STICKY_BLOCKED_REGISTRY:-$REPO_ROOT/.loom/sticky-blocked.json}"

# Labels that legitimately move during a normal claim cycle, so `verify` must
# NOT demand their presence (an issue mid-claim carries loom:building where the
# registry's settle_labels say loom:issue). Everything else a registry entry
# names is a sticky invariant.
LIFECYCLE_LABELS="loom:issue loom:building loom:curating loom:evaluating loom:triage"

DRY_RUN=0
REPAIR=0
REPO_FLAG=""

_usage() {
  cat >&2 <<'EOF'
Usage:
  sticky-blocked.sh settle <ISSUE> [--dry-run] [--repo OWNER/NAME]
  sticky-blocked.sh verify [<ISSUE>...] [--repair] [--dry-run] [--repo OWNER/NAME]
  sticky-blocked.sh list
EOF
}

_log()  { echo "[sticky-blocked] $*" >&2; }
_fail() { echo "[sticky-blocked] ERROR: $*" >&2; }

# --- registry helpers ---------------------------------------------------------
#
# python3 (not jq) on purpose: the repo's CI image is bash + python3 stdlib only
# (.github/workflows/hygiene.yml), so the unit test stays runnable everywhere.

_registry_python() {
  # $1 = mode ("labels" | "numbers" | "dump"), $2 = issue number (mode=labels)
  python3 - "$REGISTRY" "$@" <<'PY'
import json, sys

path, mode = sys.argv[1], sys.argv[2]
try:
    with open(path) as fh:
        data = json.load(fh)
except FileNotFoundError:
    sys.exit(5)
except (ValueError, OSError):
    sys.exit(5)

entries = data.get("issues") or []
if not isinstance(entries, list):
    sys.exit(5)

by_number = {}
for e in entries:
    if not isinstance(e, dict) or "issue" not in e:
        sys.exit(5)
    by_number[int(e["issue"])] = e

if mode == "numbers":
    print("\n".join(str(n) for n in sorted(by_number)))
elif mode == "labels":
    e = by_number.get(int(sys.argv[3]))
    if e is None:
        sys.exit(1)  # not registered — caller treats this as "ordinary issue"
    labels = e.get("settle_labels") or []
    print(",".join(labels))
elif mode == "dump":
    for n in sorted(by_number):
        e = by_number[n]
        print("#%d  settle_labels=%s  ruling=%s" % (
            n, ",".join(e.get("settle_labels") or []), e.get("ruling", "?")))
        print("      %s" % (e.get("reason", "") or "(no reason recorded)"))
else:
    sys.exit(2)
PY
}

# Prints the comma-joined settle labels for a registered issue; returns 1 when
# the issue is not in the registry; returns 5 when the registry is unreadable.
_settle_labels_for() {
  local out rc
  out="$(_registry_python labels "$1")"
  rc=$?
  [[ $rc -eq 0 ]] && printf '%s' "$out"
  return $rc
}

# --- forge helpers ------------------------------------------------------------

_gh() {
  local args=(gh "$@")
  if [[ -n "$REPO_FLAG" ]]; then
    args+=(--repo "$REPO_FLAG")
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    # Printed, not executed. Each argument is single-quoted so the line stays
    # copy-pasteable and so a test can assert on the exact call shape.
    local a out="DRY-RUN:"
    for a in "${args[@]}"; do out+=" '$a'"; done
    printf '%s\n' "$out"
    return 0
  fi
  "${args[@]}"
}

# Reads the issue's current labels, one per line. REST (not GraphQL) on
# purpose — see .loom/CLAUDE.md "REST vs GraphQL for forge queries": the REST
# budget survives after GraphQL is exhausted under heavy dispatch.
_current_labels() {
  local issue="$1" nwo="$REPO_FLAG"
  if [[ -z "$nwo" ]]; then nwo=":owner/:repo"; fi
  gh api "repos/$nwo/issues/$issue" --jq '.labels[].name' 2>/dev/null
}

# --- commands -----------------------------------------------------------------

cmd_settle() {
  local issue="$1"
  local labels rc
  labels="$(_settle_labels_for "$issue")"
  rc=$?
  if [[ $rc -eq 5 ]]; then
    _fail "registry not readable: $REGISTRY"
    return 5
  fi
  if [[ $rc -ne 0 ]]; then
    # NOT a sticky-blocked issue: ordinary release, and explicitly never
    # `loom:blocked`. This is the guarantee that the fix for #4 cannot leak
    # onto every other issue that goes through a release.
    labels="loom:issue"
    _log "issue #$issue is not in $REGISTRY — ordinary release (loom:blocked NOT applied)"
  else
    _log "issue #$issue is sticky-blocked — single atomic release with: $labels"
  fi

  # ONE mutation. Every label the issue must end up with is named here, so
  # there is no separable "…and then re-apply loom:blocked" step to skip.
  if ! _gh issue edit "$issue" --remove-label "loom:building" --add-label "$labels"; then
    _fail "failed to release claim on issue #$issue"
    return 4
  fi
  return 0
}

cmd_verify() {
  local -a targets=("$@")
  if [[ ${#targets[@]} -eq 0 ]]; then
    mapfile -t targets < <(_registry_python numbers) || true
    if [[ ${#targets[@]} -eq 0 ]]; then
      _fail "registry not readable or empty: $REGISTRY"
      return 5
    fi
  fi

  local drift=0 failed=0
  local issue labels rc
  for issue in "${targets[@]}"; do
    labels="$(_settle_labels_for "$issue")"
    rc=$?
    if [[ $rc -eq 5 ]]; then
      _fail "registry not readable: $REGISTRY"
      return 5
    fi
    if [[ $rc -ne 0 ]]; then
      _log "issue #$issue is not in the registry — nothing to verify"
      continue
    fi

    local -a required=()
    local want
    while IFS= read -r want; do
      [[ -z "$want" ]] && continue
      case " $LIFECYCLE_LABELS " in
        *" $want "*) continue ;;   # legitimately swapped during a claim
      esac
      required+=("$want")
    done < <(tr ',' '\n' <<<"$labels")

    local present
    present="$(_current_labels "$issue")"
    if [[ -z "$present" ]]; then
      _fail "could not read current labels for issue #$issue"
      failed=1
      continue
    fi

    local -a missing=()
    for want in "${required[@]}"; do
      if ! grep -qxF -- "$want" <<<"$present"; then
        missing+=("$want")
      fi
    done

    if [[ ${#missing[@]} -eq 0 ]]; then
      _log "issue #$issue OK — sticky labels present: ${required[*]}"
      continue
    fi

    drift=1
    local joined
    joined="$(IFS=,; echo "${missing[*]}")"
    _fail "issue #$issue DRIFTED — missing: $joined"
    if [[ $REPAIR -eq 1 ]]; then
      # Purely additive, single call: re-assert only what went missing and
      # never touch a label this script does not own.
      if _gh issue edit "$issue" --add-label "$joined"; then
        _log "issue #$issue repaired — re-applied: $joined"
      else
        _fail "issue #$issue repair FAILED for: $joined"
        failed=1
      fi
    fi
  done

  [[ $failed -eq 1 ]] && return 4
  if [[ $drift -eq 1 && $REPAIR -eq 0 ]]; then
    return 3
  fi
  return 0
}

cmd_list() {
  if ! _registry_python dump; then
    _fail "registry not readable: $REGISTRY"
    return 5
  fi
  return 0
}

# --- argument parsing ---------------------------------------------------------

[[ $# -eq 0 ]] && { _usage; exit 2; }

COMMAND="$1"; shift
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --repair)  REPAIR=1; shift ;;
    --repo)    REPO_FLAG="${2:-}"; shift 2 ;;
    --registry) REGISTRY="${2:-}"; shift 2 ;;
    -h|--help) _usage; exit 0 ;;
    --*)       _fail "unknown option: $1"; _usage; exit 2 ;;
    *)         POSITIONAL+=("$1"); shift ;;
  esac
done

case "$COMMAND" in
  settle)
    if [[ ${#POSITIONAL[@]} -ne 1 || ! "${POSITIONAL[0]}" =~ ^[0-9]+$ ]]; then
      _fail "settle requires exactly one numeric <ISSUE>"
      _usage
      exit 2
    fi
    cmd_settle "${POSITIONAL[0]}"
    exit $?
    ;;
  verify)
    for arg in "${POSITIONAL[@]+"${POSITIONAL[@]}"}"; do
      if [[ ! "$arg" =~ ^[0-9]+$ ]]; then
        _fail "verify arguments must be issue numbers: $arg"
        _usage
        exit 2
      fi
    done
    cmd_verify "${POSITIONAL[@]+"${POSITIONAL[@]}"}"
    exit $?
    ;;
  list)
    cmd_list
    exit $?
    ;;
  -h|--help)
    _usage; exit 0 ;;
  *)
    _fail "unknown command: $COMMAND"
    _usage
    exit 2
    ;;
esac
