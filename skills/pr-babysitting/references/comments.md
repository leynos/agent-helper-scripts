# Comment routes and templates

Replace every placeholder and remove unsupported claims before posting. Read
back the posted body and URL. Keep comments specific to the finding, candidate,
and evidence; do not claim that CodeRabbit ran a requested analysis unless its
response establishes that it did.

## Route and identity rules

Follow the
[manual-comment identity contract](../SKILL.md#manual-comment-identity-contract).
Every manually posted comment or inline reply uses an authorized token
selected with `shuf` from the owner-provisioned `~/.local/share/github-tokens`
pool, through the [posting helper](#posting-helper). Pool accounts deliberately
authenticate as identities other than the lifecycle account, because CodeRabbit
rate-limits conversations per commenting account and the lifecycle account's
allowance is kept for its reviews. That difference is expected and requires no
additional permission for comments already within the assignment. Do not search
the pool for the lifecycle account's token, compare its principal with the PR
author, or substitute the normal CLI account. The configured pool is the
authorized comment route, not an unrelated identity.

This route covers CI investigation, assessment questions and follow-ups,
rebuttals, confirmations, pre-merge reconciliation, and the final approval
request. Select one token for the operation and verify that token's identity
under the same command-scoped credentials. A pool token that authenticates as
the lifecycle account is a pool configuration problem; stop before posting and
report it. Authentication as another account is not itself a permission
failure, but GitHub must still permit the requested operation. Read back the
comment and verify its author against the selected account, not against the
lifecycle account.

Do not use a connector's implicit identity, change `gh auth` configuration, or
export the selected token into the parent shell. The executable path, including
`/usr/bin/gh`, does not select the GitHub account. Git publication, readiness,
and merges retain the normal authorized lifecycle identity without this token.

Full and incremental review requests, retries, and review-resume actions belong
to `comenq-coderabbit`. Its dispatcher retains its own configured identity and
cooldown policy; do not wrap it with a randomly selected manual-comment token.

The completeness/correctness and proof-specific questions in
[ExecPlan assessments](execplan-assessment.md) are assessment conversations,
not formal review requests. Each initial question and necessary candidate-bound
follow-up uses this manual-token procedure after its prerequisites hold.
Assessment conversations never go through `comenq`. Formal review requests and
their recovery require verified readiness and `comenq-coderabbit`. Neither
route authorizes duplicate requests or cooldown bypasses.

Before a question is posted, capture its observation baseline. Afterwards,
record its ID, URL, server timestamps, and candidate, then actively await the
substantive reply with [awaiting CodeRabbit](awaiting-coderabbit.md). The user
should not have to copy the bot's answer back into the agent conversation.
Posting, receiving a reply, and satisfying an assessment are separate states.

Use the inline reply endpoint for an inline finding. Its reply target is the
thread's root review-comment ID, not a review ID, GraphQL thread ID, or another
reply's ID. For a review banner or top-level finding, create a new issue
comment and link back to the original. Always mention `@coderabbitai`; retain
the original reviewer's identity in the explanation.

A request to confirm a specific fix or disposition is not a request for a new
review. Do not add `review`, `full review`, `resume`, or a natural-language
whole-PR review request to a manually posted disposition comment. Requesting
final approval is an explicit exception described by this skill, not an excuse
to bypass a required review. Assessment conversations above have their own
applicability and prerequisites; do not convert them into queued formal reviews.

On an ambiguous posting failure, fetch the discussion and check whether the
comment already exists before retrying. Honour HTTP retry advice and service
cooldowns. Selecting the configured account before posting is normal routing,
not permission to rotate accounts after a rate-limit response. Authentication,
permission, and rate-limit errors remain their actual errors: do not fall back
to the lifecycle account, try successive tokens, or enqueue the comment. Retain
the draft and report the specific blocker when the authorized operation cannot
proceed.

## Posting helper

Post every manual comment with the shipped helper,
`scripts/post-manual-comment.sh` in the `pr-babysitting` skill directory.
Invoke it by path; do not transcribe, abbreviate, or reimplement it. It is a
tool for a controlled agent runtime, not an autonomous babysitting daemon. It
does not prove that the candidate was pushed or that the body is an authorized
disposition: establish those conditions before calling it.

The helper assumes the token pool is a regular file containing one raw
authorized GitHub token per nonblank line; blank lines and full-line comments
are ignored. It never sources the pool. Where the installation uses another
format, use its documented reader rather than guessing or dumping the contents.
It requires Bash, `awk`, GNU `shuf`, GNU `date`, `jq`, and `gh`.

For each run, the helper:

1. selects one pool token with `shuf`;
2. reads the lifecycle account from the stored `gh` login with `GH_TOKEN` and
   `GITHUB_TOKEN` removed. It uses `PR_BABYSITTING_LIFECYCLE_LOGIN` only when
   that lookup is unavailable, for example when the lifecycle account
   authenticates only through an environment token. When both logins exist and
   differ case-insensitively, it fails closed with
   `lifecycle_identity_mismatch`; a malformed override fails with
   `invalid_lifecycle_override`;
3. verifies the selected token's login, rejecting one that matches the
   lifecycle account case-insensitively; and
4. posts once with that token scoped to the command, printing the comment URL.

It fails closed when the pool, the lifecycle account, or the selected token's
identity cannot be established, and it never retries with another token or the
normal account. It checks only the selected pool token, never every pool entry
looking for the lifecycle account. Standard error receives bounded JSON
diagnostics for the `token_selection`, `lifecycle_identity`,
`identity_preflight`, and `post` stages, with the operation, a random
per-invocation `run_id` shared by every stage, comment surface, repository/PR,
failure category, exit status, elapsed time, and recognized HTTP status. A
failed lifecycle lookup keeps its exit status and is classified as
`authentication_failed`, `permission_denied`, `rate_limited`, or
`github_api_failed`, like the later stages. Diagnostics omit credentials,
comment bodies, account names, and raw GitHub error text. They are the helper's
complete telemetry: there is no separate metrics sink, and the per-stage
`elapsed_ms` values already give each external call's latency.

The credential is scoped to the helper's process; never log the selected
record, enable HTTP debug output, put it in an argument/header string, or write
it into evidence. A successful command returns the comment URL, not proof that
a bot received, resolved, or approved anything. Keep the pool private under the
installation's credential-storage policy.

The
[GitHub CLI environment reference](https://cli.github.com/manual/gh_help_environment)
documents that `GH_TOKEN` and `GITHUB_TOKEN` override stored credentials, in
that precedence order. The identity read and POST both set them explicitly;
normal lifecycle authentication remains unchanged when the helper exits.

Examples, after preparing and inspecting the body file, with `SKILL_DIR` set to
the installed `pr-babysitting` directory:

```bash
# New top-level response to a banner or pre-merge check.
"$SKILL_DIR/scripts/post-manual-comment.sh" OWNER/REPO 123 \
  /tmp/pr-123-response.md

# Reply to an inline finding, using the thread's root comment ID.
"$SKILL_DIR/scripts/post-manual-comment.sh" OWNER/REPO 123 \
  /tmp/pr-123-response.md 456789
```

## CI investigation

Use the exact investigation template in `SKILL.md`. Add this framing outside it:

```text
@coderabbitai

Investigation and an AI coding agent prompt only, please. Do not apply changes,
create commits, or open another PR.

Candidate: <full head SHA>; base: <full base SHA>.
Failed job/attempt: <job name, run ID, attempt>.
Established so far: <facts and reproduction evidence, not guesses>.

<insert the preserved investigation template with redacted logs and run URL>
```

## Addressed inline finding, including Sourcery and Codex

Post only after the repair is pushed and remote parity verified. Use the same
thread even when CodeRabbit was not the original reviewer.

```text
@coderabbitai Has this finding now been resolved in <published head SHA>?

Original finding: <reviewer and finding URL>.
Repair: <commit SHA, paths, and what changed>.
Validation: <candidate-bound commands/results and CI URLs>.

Please use codegraph exploration and the current source to check the fix.
If resolved, please confirm that and mark the thread resolved where permitted.
Otherwise, identify the remaining defect and provide an AI coding agent prompt
for the work still needed. Please state any analysis or access limitations.
```

For duplicate comments, retain individual replies and link each to the same
repair. For already-fixed findings, identify the existing published commit; do
not imply that a new change was made.

## Invalid or incorrect finding

```text
@coderabbitai Please check the disposition of this <original reviewer> finding
against <published head SHA>, based on <base SHA>.

I believe the finding is invalid because <specific claim and reasoning>.
Evidence: <source/contract/test links that discriminate between the claims>.
No code change was made for this finding.

Please confirm whether the finding can be closed. If it remains valid, explain
the remaining defect or a counterexample and provide an AI coding agent prompt
for the necessary fix. Please distinguish an incorrect proposed remedy from
an invalid underlying concern.
```

## Review-banner findings

Post a new top-level issue comment. Each item must identify its original
finding and receive a separate disposition, even when several share one
underlying fix.

```text
@coderabbitai Please reconcile the findings in <review banner URL> for
<published head SHA>, based on <base SHA>.

<finding 1>: <fixed/already fixed/invalid/out of scope>; <evidence>.
<finding 2>: <disposition>; <evidence>.

All referenced repairs have been pushed. Please confirm which findings are
resolved and provide an AI coding agent prompt for any valid remaining work.
This is a focused reconciliation, not a request for a fresh whole-PR review.
```

## Pre-merge checks

Copy the live failed/warning heading and relevant table rows. Preserve the
check names and severities rather than substituting a remembered summary.

```text
@coderabbitai Have the following pre-merge findings now been resolved for
<published head SHA>, based on <base SHA>?

<live heading and relevant failed/warning table rows>

Dispositions and evidence:
<check name>: <published repair or evidence-backed rebuttal; validation>.

Documentation scope: <what changed for users, what changed for developers,
and the appropriate documentation or evidence of inapplicability>.

Do not treat warnings as optional or aspirational. Please confirm the resolved
rows and provide an AI coding agent prompt for any valid remaining work.
Please keep separately planned follow-up actions outside this PR's scope.
```

## Sourcery follow-up scope

```text
@coderabbitai Please confirm the scope disposition of Sourcery's finding at
<finding URL> for <published head SHA> and issue <original issue URL>.

The PR delivers <agreed code changes and acceptance criteria>.
The requested action is <future rollout/operational task/later milestone> and
is outside this PR's accepted scope; it is not an omitted code requirement.
Evidence: <issue/plan scope and current implementation/tests>.
Follow-up: <existing issue or recorded owner, when available>.

Please confirm that no change is required in this PR for that follow-up, or
identify the concrete in-scope code or documentation gap that remains.
```

Do not automatically create new issues unless authorized. The assignment to
create a necessary prerequisite PR is not authority to proliferate unrelated
follow-up issues.

## Final approval request

Before sending, ensure the final-round and substantive-disposition conditions in
`SKILL.md` hold. Use a new top-level comment, not an inline reply.

```text
@coderabbitai approve

Published head: <full SHA>; base: <full SHA>.
The latest completed review round is <clean / documentation or comment
formatting only>. Its valid findings have been addressed and pushed.
Earlier substantive findings: <dispositions and confirmation links>.
Pre-merge checks: <current results or accepted row dispositions>.
CI: <current candidate-bound results>.
Rebase/stack state: <verified target and prerequisites>.

Please approve if those findings are resolved. If approval remains blocked,
identify the specific unresolved finding or missing required inspection.
```

CodeRabbit documents `approve` as resolving its unresolved threads before
attempting approval. It requires the request-changes workflow setting to submit
an approval. Preserve the pre-command finding inventory and inspect the result;
never treat the command's thread-resolution side effect as evidence of a fix.
