# Issue #4 settle protocol — why `loom:blocked` kept vanishing, and what to run

[Issue #4](https://github.com/2AMLogic/sg13g2-bandgap/issues/4) (the T1/bronze
tracking checklist) must **permanently** carry `loom:blocked`, per the
operator's fleet-wide ruling of **2026-09-18T22:32:09Z** ("this is a tracking
checklist by design … blocked on its own child items").

Since that ruling, every sweep pass that settled #4 re-applied `loom:blocked`
and the *next* pass found it gone again — observed independently at least three
times before [#246](https://github.com/2AMLogic/sg13g2-bandgap/issues/246) was
filed. This document records what the label history actually shows, which of the
candidate causes it rules out, and the protocol that replaces the old manual
two-step settle.

---

## 1. Getting the evidence: the per-issue events endpoint is useless on #4

The obvious read —

```bash
gh api repos/:owner/:repo/issues/4/events --paginate
```

— **silently lies by omission on this issue.** It returns 310 label events whose
newest is `2026-08-22T03:32:11Z`, and GraphQL agrees
(`timelineItems(itemTypes: [LABELED_EVENT, UNLABELED_EVENT]) { totalCount }` =
310). Meanwhile the same issue has 2413 comments and cross-reference events
recorded through today. #4's timeline is large enough (2813 items) that its
label-event history is truncated: **nothing after 2026-08-22 is visible there,
which is the entire period the bug occurs in.**

The **repo-level** events endpoint is not truncated and is the read that works:

```bash
for p in 1 2 3 4 5 6 7 8; do
  gh api "repos/:owner/:repo/issues/events?per_page=100&page=$p" \
    -q '.[] | "\(.created_at)\t\(.issue.number)\t\(.event)\t\(.label.name // "")\tby=\(.actor.login)"'
done | awk -F'\t' '$2==4'
```

It covers roughly the last two weeks of repo-wide issue events. Use it, not the
per-issue endpoint, for any future label-forensics question about #4.

## 2. What the history shows

```
2026-09-21T19:23:22Z  labeled    loom:blocked     <- settle re-applied it
2026-09-21T19:32:39Z  unlabeled  loom:blocked     <- SOLITARY removal, +9m17s
2026-09-22T00:39:19Z  labeled    loom:blocked
2026-09-22T00:54:21Z  unlabeled  loom:blocked     <- +15m02s
2026-09-23T02:22:11Z  labeled    loom:blocked
2026-09-23T02:34:03Z  unlabeled  loom:blocked     <- +11m52s
2026-09-23T06:16:27Z  labeled    loom:blocked
2026-09-23T06:27:55Z  unlabeled  loom:blocked     <- +11m28s
```

Three properties of every removal:

1. **It is solitary.** No paired `labeled`/`unlabeled` event in the same second,
   on #4 or on any other issue in the repo within a ±7-minute window. A
   claim-time flip does not look like this: those are same-second *pairs*
   (`unlabeled loom:issue` + `labeled loom:building`).
2. **It happens ~9–15 minutes AFTER the claim was already released**, not at
   claim time, and not at settle time.
3. **No comment accompanies it.**

## 3. What that rules out

| Candidate from #246 | Verdict | Why |
|---|---|---|
| (a) `loom-daemon`'s `--claim-owned` claim-time flip drops it | **Ruled out** | The claim flips are visible in the history as clean same-second `loom:issue`↔`loom:building` pairs that never touch `loom:blocked`. The removals do not coincide with them. |
| (b) an in-repo script | **Ruled out for the scripts under `.loom/scripts/`** | `grep -rn -- '--remove-label' .loom/scripts/` finds exactly one `loom:blocked` removal (`classify-dependency-block.sh`, which removes `loom:operator-blocked`, not `loom:blocked`). `merge-pr.sh`/`forge_gh_swap_label_rl_safe` are scoped/additive, as the curator already established. |
| (c) the manual two-step settle silently skipping step two | **Ruled out as the mechanism of loss** | The `labeled loom:blocked` event is present at *every* settle. Step two was performed every time; the label was removed later. |

## 4. What it actually is

The removals match the documented **`loom:blocked` unblock probe** — the pass
that scans `loom:blocked` issues, decides the blocker has cleared, and runs:

```bash
gh issue edit <N> --remove-label "loom:blocked" --add-label "loom:issue"
```

Because #4 **already carries `loom:issue`**, the `--add-label` half is a no-op
that emits no event, so the whole operation shows up as exactly one solitary
`unlabeled loom:blocked` — the observed shape.

The probe is behaving as specified. The specification is what does not fit #4:
it decides whether to unblock by parsing a *machine-readable* blocker
declaration (`Blocked by #N` / `Depends on #N`) from the issue body or blocker
comment, and, absent one, is documented to "remove `loom:blocked` and attempt
anyway". **#4's blocked state is an operator ruling recorded in a comment. It is
not expressible in any form the probe reads, and Loom has no concept of a
permanently/operator-ruled blocked issue.** That gap is upstream, in
`rjwalters/loom`; this repository cannot close it.

## 5. The protocol (what to run)

Two commands, both from `.loom/scripts/sticky-blocked.sh`, backed by the
repo-committed registry `.loom/sticky-blocked.json`:

```bash
# At settle, releasing a loom:building claim on #4 — ONE atomic edit that names
# every label the issue must end up with. Replaces the old two-step sequence.
./.loom/scripts/sticky-blocked.sh settle 4

# Re-assert the invariant the unblock probe may have stripped since the last
# settle. You do NOT have to remember this one — a scheduled workflow already
# runs it every 10 minutes (see §5.1). Run it by hand only when you want an
# immediate answer rather than waiting for the next tick.
./.loom/scripts/sticky-blocked.sh verify --repair
```

- `settle <N>` issues **exactly one** `gh issue edit`
  (`--remove-label loom:building --add-label loom:issue,loom:curated,loom:blocked`
  for #4), so the `loom:blocked` re-apply can no longer be a separable step a
  pass can skip.
- `settle <N>` on an issue **not** in the registry performs the ordinary
  `loom:building` → `loom:issue` release and never adds `loom:blocked`. The
  registry is the only thing that makes an issue sticky; nothing here forces
  `loom:blocked` onto the rest of the queue.
- `verify` exits `3` on drift and is read-only; `verify --repair` re-applies
  only the missing labels with a single purely-additive edit.
- `verify` treats `loom:issue` / `loom:building` / `loom:curating` /
  `loom:evaluating` / `loom:triage` as lifecycle labels that legitimately move,
  so an issue mid-claim is not reported as drift. The sticky invariant it
  enforces on #4 is `loom:blocked` and `loom:curated`.

Unit tests: `./.loom/scripts/tests/test-sticky-blocked.sh`.

### 5.1 What actually enforces this — `.github/workflows/sticky-blocked.yml`

`verify --repair` is only worth anything if something runs it on a cadence
tighter than the probe that strips the label. **Documentation cannot be that
something.** Per §4 the removal happens during the probe's *generic* periodic
scan of every `loom:blocked` issue in the repo — it is not triggered by anyone
working #4, so an instruction to "run `verify --repair` at the start of a pass on
#4" leaves the label missing for however long it takes someone to next touch #4.
That is the same "an agent has to remember a manual step" dependency #246 was
opened to eliminate, merely relocated.

So the repair runs from a repo-owned scheduled workflow instead:

| | |
|---|---|
| **File** | `.github/workflows/sticky-blocked.yml` |
| **Triggers** | `schedule: */10 * * * *`; `push` to `main` touching the registry, the script or the workflow; `workflow_dispatch` |
| **Command** | `./.loom/scripts/sticky-blocked.sh verify --repair --repo <owner/name>` |
| **Permissions** | `contents: read`, `issues: write` — the single scope `gh issue edit --add-label` needs; `GH_TOKEN` is the job's `GITHUB_TOKEN` |

This bounds the drift window to **one cron tick (~10 min)** instead of "however
long until someone happens to work #4 next", and 10 minutes is deliberately
tighter than the probe's own documented 15–30 minute cadence, so a stripped label
is normally restored before the next probe pass even sees it.

Three properties that make running it this often safe:

- **Idempotent and additive.** A tick that finds no drift performs no mutation at
  all; a tick that finds drift issues exactly one `gh issue edit --add-label`
  naming only the missing labels, and never removes anything.
- **Registry-scoped.** Only issues listed in `.loom/sticky-blocked.json` are
  touched — today, only #4.
- **Cheap.** One REST label read per registered issue per tick.

It is a **repo-owned** file on purpose. `guide.md` and `sweep.md` — where the
probe procedure itself lives — are vendored Loom surfaces, overwritten by the
recurring `chore: resync installed Loom surfaces` commits, so a patch to the
probe would not survive in-repo. That is why the probe-side fix is filed
upstream (§6) and this workflow is the local mitigation that works without it.

The wiring is pinned by tests (`test-sticky-blocked.sh`, "the scheduled
enforcement workflow actually invokes verify --repair"): the suite fails if the
workflow is deleted, if its cron is loosened past the probe's cadence, if
`issues: write` is dropped, or if the `verify --repair` step loses `GH_TOKEN`.

**Known limits of the mechanism itself:** GitHub only runs `schedule:` workflows
from the **default branch**, so this takes effect when the PR merges, not before;
cron ticks can be delayed or dropped under Actions load (the 10-minute cadence
has headroom for that); and GitHub disables scheduled workflows in repositories
with 60 days of no activity, which does not apply to this repo today but would
need a `workflow_dispatch` nudge if it ever did.

## 6. Honest limits of this fix

**`settle` alone cannot keep `loom:blocked` on #4.** The loss happens minutes
after settle, in a pass this repository does not run. What is fixed here:

- the settle can no longer *contribute* to the loss (it is atomic now), and the
  protocol is committed to the repo instead of living only in sweep-comment
  folklore;
- drift is *detectable and repairable* with one cheap idempotent command, and
  — crucially — that command is now run automatically every 10 minutes by
  `.github/workflows/sticky-blocked.yml` (§5.1) rather than depending on an
  agent remembering to check. The label can still be stripped by the probe; it
  now comes back within a tick instead of staying gone.

The real fix is upstream: `loom:blocked` needs a sticky/operator-ruled mode, or
the unblock probe needs to refuse to strip a label it cannot attribute a
clearing event to. Filed as
[`rjwalters/loom#8742`](https://github.com/rjwalters/loom/issues/8742), which
also records the truncated-label-history finding from §1 so other repos do not
lose a day to it.

**Rejected alternative:** adding explicit hold/defer phrasing (`hold until`,
`do not start`) to #4's body would make the probe leave the label alone, but the
same phrasing is documented to mean "do not build" — which would suppress the
`--claim-owned 4` tracker passes this repo depends on. Adding a
machine-readable `Blocked by #221` line would work only until #221 closes, at
which point the label would start disappearing again. Neither is a durable fix.

**Verification status:** the unit tests establish the *call shape* of settle and
repair and the *wiring* of the scheduled workflow; they do not establish that
`loom:blocked` survives in production. Confirming that needs the post-merge
evidence, which anyone can read directly once this lands:

```bash
# The cron job is running, and each tick either found no drift or repaired it.
gh run list --workflow sticky-blocked.yml --limit 20

# The label has stopped disappearing for longer than a tick: no `unlabeled
# loom:blocked` on #4 that is not followed by a `labeled` within ~10 minutes.
for p in 1 2 3 4; do
  gh api "repos/:owner/:repo/issues/events?per_page=100&page=$p" \
    -q '.[] | "\(.created_at)\t\(.issue.number)\t\(.event)\t\(.label.name // "")"'
done | awk -F'\t' '$2==4 && $4=="loom:blocked"'
```

Note that scheduled workflows only run from the default branch, so neither check
produces data until the PR merges.

## 7. The `addComment` 2500-comment cap (#248) and the pinned-state-comment convention

This section is unrelated to the `loom:blocked` label-drift bug above (§1-6) —
it is a second, independent GitHub limit that hit #4 later, on 2026-09-26.
It is documented here anyway because #4 is the one issue both limits share,
and because the fix below reuses this file as its home per #248's own
acceptance criteria.

### 7.1 What broke

`gh api graphql` against `repository(...).issue(4).comments.totalCount`
returns exactly `2500`. Every `addComment` mutation on #4 — a plain `gh issue
comment 4 ...`, or any `gh api --method POST
repos/{owner}/{repo}/issues/4/comments` — now fails permanently with

```
GraphQL: Commenting is disabled on issues with more than 2500 comments (addComment)
```

This is GitHub's hard cap on the number of comments an issue may carry, not a
rate limit: no retry, backoff, or credential escalation recovers it, and it
will never clear on its own (deleting old comments is the only way to make
room, and nothing in this repo's tooling does that). The maintenance-log
convention this repo had been using — post a fresh "**Tracker re-check,
`<timestamp>` (...)**" comment on every periodic `/loom:sweep 4 --claim-owned
4` pass, summarizing what changed since the previous check — is built
entirely on `addComment` and is therefore now permanently broken on #4. (This
is a distinct GitHub limit from the ~256 KiB **body**-size cap covered in
[`.loom/docs/graphql-body-size-cap.md`](../.loom/docs/graphql-body-size-cap.md)
— that page's own remedy, "switch from editing the body to posting a
comment," is exactly the escape hatch this **comment**-count cap now closes
right back off for #4 specifically. #4 is affected by both caps at once: its
body is long-since near the 256 KiB ceiling, which is why maintenance updates
were comments in the first place, and now its comment count is at its own
ceiling too.)

### 7.2 What still works: PATCH is a different mutation, not subject to this cap

`gh api --method PATCH repos/{owner}/{repo}/issues/comments/<id>` — editing an
**existing** comment's body — is a different GitHub mutation
(`updateIssueComment`) with no documented comment-count cap of its own. This
is not just a theoretical distinction:

- **`sweep-lease-publish.sh` already fails open on this exact failure mode.**
  Its one `POST .../issues/${issue}/comments` call (the initial lease-record
  write, ~line 503-506 as of this writing) catches a non-zero `gh` exit, logs
  "Proceeding without a lease is safe but degrades reclaim evidence
  (best-effort, mirrors #6179's fail-open dispatch write)", and exits `2`.
  Per the sweep pre-flight contract (`.claude/commands/loom/sweep-reference.md`
  Step 1b), an exit `0`/`2` at this step **proceeds** — a sweep claiming #4 is
  never blocked by a failed lease publish, only its reclaim evidence degrades
  from "a lease comment exists" to "none does," exactly as if no lease had
  ever been attempted. This is an observability gap, not a functional one.
- **`sweep-lease-renew.sh` never calls `addComment` at all in its steady-state
  path.** Once a lease comment exists, `renew-once` locates it and PATCHes it
  (`--method PATCH repos/{owner}/{repo}/issues/comments/${candidate_id}`) —
  see that script's own header comment: "This is an idempotent PATCH of the
  EXISTING comment — never a new comment." Renewal is therefore never
  exposed to the comment-count cap; only the one-time initial `publish` call
  is (and that call fails open, per the point above).
- **This is not just theoretical — it is already happening in production on
  #4.** Multiple lease comments on #4 (all written *before* the cap was hit)
  show `updated_at` timestamps well after their `created_at`, i.e. a live
  `sweep-lease-renew.sh` loop has already been PATCHing them successfully
  *after* #4's comment count reached 2500. Example, read live via `gh api
  repos/2AMLogic/sg13g2-bandgap/issues/comments/5846657767`: `created_at:
  2026-09-26T13:28:59Z`, `updated_at: 2026-09-26T13:34:26Z` — one successful
  renewal PATCH, five and a half minutes after creation, on a comment that is
  itself part of the capped 2500. This is the empirical confirmation behind
  §7.4's "did not execute a live mutation" decision: the hypothesis this
  section rests on (PATCH keeps working on a comment-capped issue) is already
  independently proven by existing sweep activity, not merely asserted.

**Not yet traced (explicit, non-blocking follow-up — do not resolve this in
the same pass that reads this note):** whether `.loom/scripts/record-noop-release.sh`
and the `#6485` `loom:lease-yield` stand-down marker share this same
fail-open/PATCH-only contract. Both write comments to a tracker issue as part
of the claim-release path, and neither has been traced with the depth given
to `sweep-lease-publish.sh`/`sweep-lease-renew.sh` above. If either turns out
to hard-fail (rather than fail open, or PATCH an existing record) on a
comment-capped issue, that is a real gap worth its own issue — potentially an
upstream `rjwalters/loom` question, mirroring §6's `rjwalters/loom#8742`
precedent for the label-drift half of this file. Flagging it here is
deliberately as far as this section goes.

### 7.3 The replacement convention: one pinned comment, PATCHed, never re-POSTed

`.loom/scripts/tracker-state-comment.sh` (added by #248) gives the
maintenance-log convention the same escape hatch #7.2 describes for leases:
instead of POSTing a new "Tracker re-check" comment on every pass, maintain
**one** pinned comment — identified by the literal first line
`<!-- loom:tracker-state -->` — and PATCH it in place every time.

```bash
# Steady state: find the pinned comment and PATCH it with fresh content.
# Never POSTs once the pinned comment already exists.
.loom/scripts/tracker-state-comment.sh ensure 4 --body-file /tmp/tracker-4-recheck.md

# Read-only: print the pinned comment's id and current body. Safe to run
# against #4 at any time; never mutates anything.
.loom/scripts/tracker-state-comment.sh show 4
```

`ensure` PATCHes the newest comment whose body starts with the marker if one
exists (the `sweep-lease-renew.sh` steady-state path, reused verbatim: same
`forge_gh_perm_safe`-wrapped escalation ladder, same "write to a temp file,
`-F body=@<path>`" PATCH shape so a mid-write credential escalation retry
never re-reads an already-consumed stdin pipe). If no pinned comment exists
yet, `ensure` tries to POST one — which only succeeds on an issue that has
not yet hit the cap (every tracker issue in this repo except #4 today). A
POST failure at that point is not swallowed into a silent no-op: `ensure`
exits `2` with a message pointing at `bootstrap`.

**Both** of `ensure`'s write paths — the steady-state PATCH and the
create-new POST — use that temp-file `-F body=@<path>` shape, not a stdin
pipe. This is load-bearing, not stylistic: `forge_cmd_perm_safe` re-invokes
the *identical* command on up to three credential rungs when the first 403s
with GitHub's App-installation permission wording, and a pipe is readable
exactly once, so a `-F body=@-` call would hand the retry an empty stdin.
`gh api --method POST … -F body=@-` with empty stdin does not reliably
*fail* — it can succeed with an empty body, i.e. quietly overwrite the
tracker's pinned state with nothing on exactly the retry path the ladder
exists to survive. (`sweep-lease-publish.sh`'s POST is safe with `-F
body=@-` only because it is a bare, unwrapped `gh` call: one attempt, one
stdin read. The two properties — "wrapped in the retrying ladder" and
"piped via stdin" — are only ever a hazard together.) Both retry paths are
covered by `.loom/scripts/tests/test-tracker-state-comment.sh` cases (l)
and (m), which force a rung-1 403 and assert the retried call still carries
a byte-identical, non-empty body.

**Bootstrapping on an issue that is ALREADY at the cap (#4's actual
situation) needs one extra, explicit step**, because `ensure`'s POST fallback
above cannot work retroactively — #4 can never accept another `addComment`,
full stop, so there is no way to *create* a fresh pinned comment on it. The
only option is to **adopt** an existing comment:

```bash
# One-time, explicit, destructive: overwrites <ID>'s body with the marker +
# fresh content. Requires --force -- this script will not guess that an
# existing comment is safe to repurpose.
.loom/scripts/tracker-state-comment.sh bootstrap 4 --comment-id <ID> \
    --body-file /tmp/tracker-4-recheck.md --force
```

Picking `<ID>` is a judgment call this script deliberately does not automate
(see the script's own header comment): the best candidate on #4 today is one
of its own `loom:lease` comments (a genuinely disposable record — "nothing
reads this record yet" per `defaults/docs/lease-record.md`, and dozens of
structurally identical siblings already exist), rather than one of the
substantive "Tracker re-check" comments, which still carry unique historical
content worth preserving. Whoever runs this should re-read the candidate
comment first (`gh api repos/2AMLogic/sg13g2-bandgap/issues/comments/<ID>`)
to confirm it is not currently being renewed by a live claim before
overwriting it. After bootstrap, every future update is a plain `ensure`
call — `bootstrap` is a one-time operation, not a recurring one.

### 7.4 Verification performed for this section

**Automated:** `.loom/scripts/tests/test-tracker-state-comment.sh` covers the
find-or-create/PATCH decision (existing pinned comment vs. none), the
startswith-not-substring marker match, trailer replacement (not
accumulation) across repeated `ensure` calls, the POST-failure → exit 2 →
"use bootstrap" path (simulating the cap without touching a real issue), the
`bootstrap --force` requirement and its overwrite behavior including the
stderr audit line, and `show`'s found/not-found paths — mirroring
`test-sweep-lease-renew.sh`'s stubbing pattern (`gh` stubbed on `PATH`, the
real script run as a subprocess, real `jq` for JSON shape). Wired into
`.loom/scripts/tests/ci-wired.txt`.

**Manual, against the real #4:** confirmed live (read-only) that
`comments.totalCount` is still exactly `2500` and that `addComment` is the
mutation the cap names. Deliberately did **not** perform a new live PATCH
exercise against #4 as part of this change: every existing candidate comment
on #4 is either substantive historical content (the "Tracker re-check"
comments) or an active-format lease record, and there was no comment on #4
that was both identifiable as disposable and safe to mutate without a human
confirming it first — exactly the judgment call §7.3 declines to automate.
Instead, this relies on the **already-existing production evidence** cited in
§7.2 (lease comment 5846657767's `updated_at` genuinely advancing past its
`created_at` after the cap was hit) as the live confirmation that PATCH
works against #4 today. A human who wants to complete the loop can run the
exact `bootstrap` command in §7.3 once a suitable `--comment-id` is chosen.
