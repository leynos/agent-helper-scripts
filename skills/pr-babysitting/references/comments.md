# Comment routes and templates

Replace every placeholder and remove unsupported claims before posting. Read
back the posted body and URL. Keep comments specific to the finding,
candidate, and evidence; do not claim that CodeRabbit ran a requested analysis
unless its response establishes that it did.

## Route and identity rules

Every manually posted comment or inline reply uses an authorized token
selected with `shuf` from `~/.local/share/github-tokens`. This includes CI
investigation, rebuttals, confirmations, pre-merge reconciliation, and the
final approval request. Do not use a connector's implicit identity instead.
Full and incremental review requests, retries, and review-resume actions
belong to `comenq-coderabbit`. Its dispatcher retains its own configured
identity and cooldown policy; do not wrap it with a randomly selected
manual-comment token.

Use the inline reply endpoint for an inline finding. Its reply target is the
thread's root review-comment ID, not a review ID, GraphQL thread ID, or
another reply's ID. For a review banner or top-level finding, create a new
issue comment and link back to the original. Always mention `@coderabbitai`;
retain the original reviewer's identity in the explanation.

A request to confirm a specific fix or disposition is not a request for a new
review. Do not add `review`, `full review`, `resume`, or a natural-language
whole-PR review request to a manually posted comment. Requesting final
approval is the explicit exception described by this skill, not an excuse to
bypass a required review.

On an ambiguous posting failure, fetch the discussion and check whether the
comment already exists before retrying. Honour HTTP retry advice and service
cooldowns. Do not keep selecting another token until a request succeeds. If
the authorized route is unavailable, retain the draft and report the blocker.

## Token-scoped posting example

This Bash recipe assumes the token pool is a regular file containing one raw
authorized GitHub token per nonblank line; blank lines and full-line comments
are ignored. It does not assume a directory or a shell configuration file and
must never `source` the pool. Where the installation uses another format, use
its documented reader rather than guessing or dumping the contents.

The function is an example for a controlled agent runtime, not an autonomous
babysitting daemon. It does not prove that the candidate was pushed or the
body is an authorized disposition: establish those conditions before calling
it. It requires Bash, `awk`, GNU `shuf`, `jq`, and `gh`.

```bash
post_manual_comment() (
  # Disable tracing before any credential is read or expanded.
  set +x
  set -euo pipefail
  unset GH_DEBUG

  repo=${1:?Supply OWNER/REPO}
  pr=${2:?Supply PR number}
  body_file=${3:?Supply a prepared Markdown body file}
  root_comment_id=${4:-}
  pool="$HOME/.local/share/github-tokens"

  [[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || {
    printf '%s\n' 'Invalid repository.' >&2; exit 2;
  }
  [[ "$pr" =~ ^[1-9][0-9]*$ ]] || {
    printf '%s\n' 'Invalid PR number.' >&2; exit 2;
  }
  [[ -f "$body_file" && -r "$body_file" && -s "$body_file" ]] || {
    printf '%s\n' 'Comment body missing, empty, or unreadable.' >&2; exit 2;
  }
  [[ -f "$pool" && -r "$pool" ]] || {
    printf '%s\n' 'Authorized token pool unavailable.' >&2; exit 2;
  }

  endpoint="repos/$repo/issues/$pr/comments"
  if [[ -n "$root_comment_id" ]]; then
    [[ "$root_comment_id" =~ ^[1-9][0-9]*$ ]] || {
      printf '%s\n' 'Invalid root review-comment ID.' >&2; exit 2;
    }
    endpoint="repos/$repo/pulls/$pr/comments/$root_comment_id/replies"
  fi

  token=$(
    awk '{ sub(/\r$/, "") }
         NF && $0 !~ /^[[:space:]]*#/ { print }' "$pool" |
      shuf -n 1
  )
  [[ -n "$token" && "$token" != *[[:space:]]* ]] || {
    printf '%s\n' 'No valid token record selected.' >&2; exit 2;
  }

  jq -n --rawfile body "$body_file" '{body: $body}' |
    GH_TOKEN="$token" GITHUB_TOKEN="$token" \
      gh api --hostname github.com --method POST "$endpoint" \
        --input - --jq '.html_url'
)
```

The credential is scoped to the posting process and subshell; never log the
selected record, enable HTTP debug output, put it in an argument/header
string, or write it into evidence. A successful command returns the comment
URL, not proof that a bot received, resolved, or approved anything. Keep the
pool private under the installation's credential-storage policy.

Examples, after preparing and inspecting the body file:

```bash
# New top-level response to a banner or pre-merge check.
post_manual_comment OWNER/REPO 123 /tmp/pr-123-response.md

# Reply to an inline finding, using the thread's root comment ID.
post_manual_comment OWNER/REPO 123 /tmp/pr-123-response.md 456789
```

## CI investigation

Use the exact investigation template in `SKILL.md`. Add this framing outside
it:

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
<check name>: <disposition; validation>.

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

Before sending, ensure the final-round and substantive-disposition conditions
in `SKILL.md` hold. Use a new top-level comment, not an inline reply.

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
attempting approval. It requires the request-changes workflow setting to
submit an approval. Preserve the pre-command finding inventory and inspect the
result; never treat the command's thread-resolution side effect as evidence of
a fix.
