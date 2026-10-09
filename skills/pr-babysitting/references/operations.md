# Observation and merge

These are examples for a runtime with authorized access. Replace placeholders;
do not execute mutations while merely drafting or inspecting this skill. Local
repository instructions and the installed companion skills remain controlling
for their respective operations.

## Read the candidate and separate GitHub surfaces

```bash
gh pr view PR_NUMBER --repo OWNER/REPO \
  --json state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,\
mergeable,mergeStateStatus,reviewDecision,statusCheckRollup

gh pr checks PR_NUMBER --repo OWNER/REPO

gh api --paginate repos/OWNER/REPO/pulls/PR_NUMBER/reviews
gh api --paginate repos/OWNER/REPO/pulls/PR_NUMBER/comments
gh api --paginate repos/OWNER/REPO/issues/PR_NUMBER/comments
```

The multi-line `--json` argument above is one shell word. Do not inspect only
`gh pr checks --required`: a current non-required red result also needs
attention. Read workflow runs, check runs, and commit statuses where needed to
establish provenance and rerun/supersession. Record the workflow event and the
PR head/base associated with any synthetic merge result.

Use GraphQL `reviewThreads` for `isResolved` and `isOutdated`. Paginate both
the outer connection and each capped inner comments connection; the REST
comment listing alone does not prove that all threads are resolved. Re-fetch
CodeRabbit's known first issue-comment ID to detect edits:

```bash
gh api repos/OWNER/REPO/issues/comments/COMMENT_ID
```

Prefer actual author login and verified app identity over text in comment
bodies. The observed review identities are `coderabbitai[bot]`,
`sourcery-ai[bot]`, and `chatgpt-codex-connector[bot]`. Rate-limit, unavailable
service, skipped-draft, and clone-failure messages are execution status, not
clean review findings.

## Scrutineer assignment

```text
Observe hosted CI for <repository/PR>, published head <SHA>, base <SHA>.
Identify every relevant run/check, event, tested commit, and attempt. Watch the
runs using the established watcher and gh run watch --exit-status; retrieve
failing-step logs. Do not mutate the repository, rerun/cancel CI, post comments,
request reviews, or merge.

Return the candidate, run/check URLs, conclusions, failed job/step summaries,
redacted log extracts, superseded-run mappings, missing/pending checks, and
watcher/API failures separately from actual CI failures. Preserve the evidence
bundle and identify the next observation or supervisor decision needed.
```

Typical watcher operations:

```bash
gh run watch RUN_ID --repo OWNER/REPO --exit-status
gh run view RUN_ID --repo OWNER/REPO --attempt ATTEMPT --log-failed
```

If failed-step logs are unavailable, preserve that error and obtain the
relevant job log using the supported fallback in the scrutineer workflow. Do
not report an empty log as a passing run. On a rerun, refresh the attempt and
candidate metadata; the watcher alone is not an immutable run-attempt receipt.

For repair validation, provide a separate assignment naming focused tests,
required Makefile gates, exact candidate/worktree, sequential resource
ownership, and expected evidence. The supervisor, not the observational
watcher, decides whether a rerun or a repair is appropriate.

## Ready transition

Require green current-candidate CI, clear CodeScene findings, and substantive
responses clearing all applicable assessments first. Follow
[awaiting CodeRabbit](awaiting-coderabbit.md) for issue-comment answers; the
formal-review check does not answer those questions. Do not queue a review on a
draft to obtain them.

```bash
gh pr ready PR_NUMBER --repo OWNER/REPO
gh pr view PR_NUMBER --repo OWNER/REPO --json isDraft,headRefOid,baseRefOid
```

Use the established authorized lifecycle identity. The random-token rule
applies to manual comments, not to changing Git remotes, merge identity, or
global CLI authentication. Re-read the candidate after the ready transition and
watch review-triggered checks.

## Managed review dispatch

Read `comenq-coderabbit` before invoking its queue. First verify
`isDraft=false` and inspect the current-candidate CodeRabbit check and latest
rate-limit status. In the readiness path, use the queue for a current explicit
review rate limit, not for an unanswered assessment or a draft-skip notice.
Await an active review without enqueueing a duplicate; without a rate limit,
await the automatic review and allow bounded startup time for its check. Other
confirmed review failures need a separately justified recovery decision. See
[formal review observation](awaiting-coderabbit.md#formal-review-after-readiness).
The managed interface is:

```bash
comenq list
comenq hist -n 20
comenq put OWNER/REPO PR_NUMBER "@coderabbitai review"
```

Confirm the deployed interface, preserve any existing suitable pending request,
and use only its configured authorized connection. Do not start another daemon,
choose another seat, bypass cooldowns, or turn a queue problem into a direct
GitHub review request. Verify the commit actually reviewed after delivery.

## CodeScene validation

Use the installed `codescene-cli` and health-rules skills. Example operations:

```bash
cs version
cs check-rules path/to/affected-file
cs check path/to/affected-file
cs delta BASE_SHA HEAD_SHA
```

Use the same comparison basis as hosted analysis. The meaning of a two-ref
delta and any warning-as-error option must match the installed CLI's
documentation. Review the findings as well as the exit status; a CLI that does
not fail on warnings has not thereby established a clean report. Keep hosted
validation separate from the local result.

## Exact-head ordinary squash merge

Only after all merge conditions in `SKILL.md` are satisfied:

```bash
gh pr merge PR_NUMBER --repo OWNER/REPO \
  --squash --match-head-commit ACCEPTED_HEAD_SHA

gh pr view PR_NUMBER --repo OWNER/REPO \
  --json state,mergedAt,mergeCommit,baseRefName
```

Do not add `--admin`. Do not add automatic branch deletion while dependent
branches still need historical boundaries. A mandatory merge queue or native
stack may require its own protected operation; use `github-stacks` and actual
repository policy instead of mechanically applying this ordinary-PR example.

The head guard protects against a changed PR head, not every possible base,
check, or review race. Re-read the base/head, check rollup, review state, and
stack topology immediately before the operation, and rely on enforced
repository protections. Where the required policy cannot be guaranteed, report
the missing guard rather than claiming an atomic gate that the CLI does not
provide.

Verify the final target and landed SHA, then observe required integration jobs.
A successful queue submission is pending delivery, not a completed merge.
