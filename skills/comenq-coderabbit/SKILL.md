---
name: comenq-coderabbit
description: >-
  Request CodeRabbit reviews through the managed comenq queue and carry the
  review-response loop through evidence-backed convergence. Use for review
  requests, queue delays, duplicate reviews, clone or service failures, stale
  pre-merge tables, documentation-coverage disputes, unresolved threads, stale
  CHANGES_REQUESTED decisions, review evidence invalidated by a restack, or
  agent-team triage and remediation of CodeRabbit findings.
---

# CodeRabbit reviews via comenq

Use the managed queue for new full reviews and retries. Repair valid findings,
reply to every thread with `@coderabbitai`, then reconcile the current pre-merge
checks. A posted request, completed review, resolved thread, approval, green CI,
and successful integration are different facts. Never substitute one for another.

This is a portable distribution of the review workflow, extended with the
September 2026 implementation-postmortem lessons. Deployment-specific hosts,
sockets, credentials, seat limits, and approved identities remain installation
configuration, not defaults supplied by this skill. Do not copy credentials into
comments or evidence records.

## Read the relevant recovery guide

Read [Failure modes and recovery](references/failure-modes-and-recovery.md)
whenever execution is incomplete, feedback recurs, a percentage is disputed, a
review decision disagrees with thread dispositions, or the candidate changes.
Each case separates the recorded incident, recovery, and evidence needed to exit.

[Evidence and rehearsal](references/evidence-and-rehearsal.md) contains the
handoff and reconciliation templates, incident references, and offline scenarios
for checking this workflow. Historical counts and outcomes are examples, not
current PR status or estate-wide thresholds.

## Connection and routing

Use the existing authorized daemon and account configuration. On its host, call
`comenq` locally. Elsewhere, use the configured SSH host only when authorized.
Do not start a second daemon, select another seat, change cooldowns, or read an
alternate token to work around a queue delay or connection failure.

The examples below use the managed queue interface documented by the deployed
skill: `list`, `put`, `hist`, and `del`. Confirm the installed interface from its
source or an approved non-mutating probe. A different CLI is a deployment issue,
not permission to install or invoke a guessed replacement.

```bash
comenq list
comenq hist -n 20
```

Before enqueueing, inspect both the pending queue and recent PR activity. Reuse
an existing request rather than adding another. Record the intended repository,
PR, base/head commits, queue ID, selected posting identity when observable, and
ETA. The comment body does not pin a review to a commit: verify the commit that
CodeRabbit actually inspected after it runs.

```bash
comenq put OWNER/REPO PR_NUMBER "@coderabbitai review"
```

For remote invocation, preserve the comment body as one remote argument. Use the
configured host in place of the placeholder:

```bash
ssh CONFIGURED_QUEUE_HOST \
  'comenq put OWNER/REPO PR_NUMBER "@coderabbitai review"'
```

Do not send a new full review through a direct GitHub comment or a personal bot
identity. Focused replies to existing findings or pre-merge rows are a different
operation: use only the project's already authorized reply route and identity.
An available credential does not authorize that route. If it is unspecified,
retain the response draft and ask the designated owner to route it.

Use live queue ETA and service activity rather than fixed cooldown assumptions or
minute-by-minute polling. Priority changes require the queue owner's policy and
a recorded blocking dependency. A pending handoff must say it is pending; it is
not a completed review or a promise of an unscheduled background check.

## The review-response loop

1. Establish the intended base/head and changed paths. Have a scrutineer agent
   run the repository's required deterministic gates under its existing
   gate-ownership rules and summarize the results. Keep failed or superseded
   evidence labelled separately from the accepted run.
2. Commit and publish only the validated scope. Confirm the remote head matches
   the intended candidate. Use [GitHub stacks](../github-stacks/SKILL.md) for
   stack mechanics; a replay requires fresh candidate verification.
3. Inspect pending requests, queue history, and automatic review activity. Queue
   one full review only if the current candidate still needs one. Keep its ID
   and ETA; delivery of the comment is not completion of the review.
4. Read execution warnings as well as findings. A clone failure, missing required
   inspection, or inconclusive check cannot establish a clean review.
5. Use a wyvern agent team to verify each finding against the current source
   before assigning repairs. Fix only still-valid issues; skip unnecessary
   changes with a brief evidence-backed reason. Explain a different remedy when
   the finding is valid but its proposed implementation is wrong. Follow the
   [delegation workflow](#delegate-verification-repair-and-validation); do not
   weaken a test, safety boundary, or required policy to satisfy a suggestion.
6. Group duplicate reports by underlying defect for implementation, but reply to
   every affected thread with `@coderabbitai`, the relevant commit or path, and
   the disposition. Do not infer that a reply was received or a thread resolved.
7. After inline dispositions are complete, fetch the live walkthrough comment
   and reconcile both warning and error rows against the current candidate and
   already answered threads. Use a focused evidence-backed follow-up for a
   stale row rather than reflexively requesting a full review.
8. Independently read the current review decision, unresolved threads, required
   check results, and remote head. If any required state remains unresolved or
   unknown, stop before merge and record precisely what is missing.

Repeat implementation and validation when a real defect remains. Request another
full review only when the remaining inspection need warrants one; a corrected
comment, title, percentage, or stale table alone does not automatically require
it. Preserve the actual scope of any earlier substantive review.

## Delegate verification, repair, and validation

Use a wyvern agent team to verify every inline finding and pre-merge row against
the current code before editing. Keep this reconnaissance read-only: inspect
implementations, callers, contracts, tests, and documentation, and record the
current base/head, finding ID, evidence, and disposition. Ask the scrutineer to
execute any reproductions needed to decide validity. An old comment anchor alone
neither invalidates a finding nor proves that it still needs work.

Fix only still-valid issues. Skip stale, already-fixed, duplicate, or incorrect
repair requests with a brief reason and evidence; duplicate reports still need
individual replies linked to the one underlying repair. Uncertainty is not a
reason to mark a finding resolved or silently discard it: keep it pending and
use the [uncertain-comment template](references/evidence-and-rehearsal.md#uncertain-comment-disposition).

For large volumes of verified findings, use journeyman and artisan/scribe agent
teams. Group work by underlying defect and affected boundary, assign bounded
batches with explicit file ownership, and avoid competing edits to the same
files. Journeymen own substantive implementation repairs; scribes own
documentation repairs; artisans handle repeated mechanical changes that need an
agent. Keep the supervisor responsible for integration and final dispositions.

Prefer automated fixes and codemods for repeated transformations wherever they
can express the intended change safely. Restrict them to verified findings and
owned paths, preview their diff, and check representative cases before applying
a batch. Do not apply a repository-wide replacement merely because several
comments look similar. Preserve public contracts and avoid unrelated formatting
or refactoring.

For smaller sets, use scribe agents for documentation issues and artisan agents
for repeated mechanical work that cannot be addressed with codemods. Route any
remaining substantive implementation repair to its owning journeyman rather
than treating it as a mechanical substitution. In every case keep changes
minimal, record a brief reason for each skipped repair, and validate the result.

Use a scrutineer agent for execution of tests and summarizing the results. Give
it the exact candidate and relevant focused tests plus required repository
gates. Preserve exclusive sequential ownership of shared build/test resources;
workers must not start competing gates. Its summary must identify the candidate,
commands, exit statuses, passed/failed/skipped results, log locations, and any
unexecuted or unavailable checks. Keep inspection claims separate from execution
evidence. After a repair or replay changes the candidate, renew the relevant
verification and validation before claiming convergence.

## Collect all review surfaces

The walkthrough and pre-merge table live in a top-level issue comment that may
be edited in place. Inline findings, replies, review submissions, thread
resolution, and required checks are separate surfaces. Read each relevant one.

The following are read-only GitHub queries with placeholders to replace:

```bash
gh pr view PR_NUMBER --repo OWNER/REPO \
  --json headRefOid,baseRefOid,reviewDecision,mergeStateStatus,statusCheckRollup
gh api --paginate repos/OWNER/REPO/pulls/PR_NUMBER/reviews
gh api --paginate repos/OWNER/REPO/pulls/PR_NUMBER/comments
gh api --paginate repos/OWNER/REPO/issues/PR_NUMBER/comments
```

Use the GraphQL `reviewThreads` connection for `isResolved` and `isOutdated`.
Paginate the entire thread list and, where necessary, each thread's comments;
outer pagination does not complete a capped inner connection. An absent reply
in a partial page is not proof of an unanswered thread. An outdated thread is
not necessarily resolved or irrelevant.

Track handled IDs to avoid duplicate replies, but re-read edited walkthroughs
and current review state. A highest-seen comment ID does not detect edits to an
older comment. Retain original evidence URLs and timestamps when stripping
boilerplate for reading.

Use a review submission's `commit_id` to identify that review's candidate.
An inline comment's `original_commit_id` identifies its original anchor, not
proof of what a later follow-up inspected. Recheck older findings against the
new tree rather than assuming that an old anchor makes them false.

## Dispositions and convergence

Treat both warning and error rows as requiring an explicit disposition; warnings
are not optional or aspirational. Mark a row resolved only with evidence. Mark
inherited findings with their comparison and owner; unchanged test bytes alone
do not prove unchanged runtime causality. Argue incorrect or contradictory
recommendations with source or tests. For genuinely out-of-scope work, look for
an existing GitHub issue and reference it, or propose one if none exists. Do not
silently dismiss the work or create duplicate issues. Observability (o11y), code
safety, documentation, and validation coverage for changes made by this PR remain
in scope, even when the implementation change is small.

Use the [pre-merge checks template](references/evidence-and-rehearsal.md#pre-merge-checks-reconciliation)
with the live failed checks heading and rows when asking whether repairs have
addressed them. For a comment whose disposition remains uncertain, reply in its
thread using the [uncertain-comment template](references/evidence-and-rehearsal.md#uncertain-comment-disposition).
Both request an AI agent prompt for remaining work. Verify any returned work
against the current code before assigning it; a generated prompt is not an
instruction to apply unverified changes.

For an inconclusive row, perform the missing bounded validation where possible
and submit its evidence. Do not claim that local evidence retroactively completed
a failed hosted inspection. Required service coverage still needs an explicit
accepted disposition through the existing review policy.

Do not tick an Ignore checkbox, suppress a required check, dismiss a review,
manually approve on the bot's behalf, or bypass branch protection to make the
status look green. Resolved inline threads and no new comments do not imply
`APPROVED`; stale `CHANGES_REQUESTED` needs explicit reconciliation and read-back.

Convergence requires evidence-backed dispositions for all required findings,
adequate completed inspection of the candidate, the required current review
state, and green required checks on the intended head. Read-only checking does
not grant authority to merge; the designated owner retains that decision.

After any rebase, server replay, or relevant new commit, record the new base/head
and treat previous merge eligibility as stale. Retain prior evidence for its
actual scope, run the required new-candidate gates, and establish the inspection
needed for the new delta. Never relabel an old full review as a new one.

After an authorized merge, verify the landed commit and required integration
jobs separately. A green PR or approval cannot discharge a failing main job.
Unexpected mutation, incomplete preservation, source/artefact disagreement,
unknown review coverage, or a mismatched head triggers an andon: stop advancing,
preserve evidence, and return the unresolved boundary to its designated owner.

## Installation boundary

`install-skills` copies immediate skill directories into the agent skill paths.
This directory therefore supplies the `comenq-coderabbit` name in this repository.
Before rollout, compare any independently installed copy with this distribution
and choose one authoritative version. Keep approved connection and identity
settings in deployment configuration; do not rely on installer ordering to
combine two different copies. This change does not modify another skill
repository, install the queue service, or authorize new account access.
