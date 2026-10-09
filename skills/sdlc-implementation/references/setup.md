# Setup and identity

Read this reference before branch or PR metadata changes. Examples assume Bash,
`gh`, an established repository and PR, and authorized metadata edits. Replace
placeholders from observed state; do not run examples blindly.

## Resolve the candidate

Inspect the current worktree, branch, remotes, upstream, dirty state, PR head
repository, base/head names and SHAs, draft state, and stack relationships.
Read existing PR content before editing it. Use the exact assigned PR
thereafter, not whichever PR a branch-only query happens to return.

```bash
git status --short --branch
git branch --show-current
git worktree list --porcelain
git remote -v
gh pr view "$pr" --repo "$repo" \
  --json number,url,title,body,isDraft,state,headRefName,headRefOid,\
headRepository,headRepositoryOwner,baseRefName,baseRefOid
```

Keep raw observation output in the approved private scratch location; redact
credential-bearing remote URLs before reporting them. Preserve user-owned
staged, unstaged, and untracked changes before any history operation. A
detached HEAD, ambiguous PR, fork mismatch, or shared-worktree conflict
requires resolving identity before mutation.

If the assignment permits publication and no PR exists, establish the intended
base and create a draft through the repository's normal process. Creating a new
PR must not silently replace an existing planning PR or discard its discussion.

## Branch and upstream

The intended ordinary configuration is local `<slug>` tracking `origin/<slug>`,
with the assigned PR using that same remote branch as its head. Validate the
proposed name with `git check-ref-format --branch "$slug"`. Inspect local and
remote collisions and compare tips before changing anything.

If the PR already uses `origin/<slug>` and only the local name or upstream is
wrong, normalize those local settings and verify them:

```bash
# Run only after the preconditions above hold. Do not use git branch -M.
git branch -m "$slug"                    # Omit when already correctly named.
git branch --set-upstream-to="origin/$slug" "$slug"
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
```

Fetch the exact remote ref first if the local remote-tracking ref is missing.
If no PR or remote branch exists and publishing this candidate is authorized, a
non-forced `git push --set-upstream origin "$slug"` can establish the upstream.
Inspect any server rejection; do not respond by force-pushing.

Renaming a local branch does not rename a remote branch or retarget an existing
PR's head. GitHub documents that renaming the head branch of an open PR closes
that PR. Do not use a remote rename, delete-and-recreate, or replacement PR as
a cosmetic shortcut. Do not retarget the base as an attempted head rename.

If the existing PR head has a different name, preserve the PR and record the
normalization conflict. Use only an explicitly authorized migration procedure
that preserves discussion and stack relationships. Otherwise retain the current
coherent branch/PR relationship and report that naming remains unfulfilled; do
not claim the requested upstream exists. Unambiguous implementation work may
continue under the existing identity when authorized, but not a destructive
metadata migration. Forks and managed stacks follow their documented remote and
branch conventions rather than forcing the ordinary `origin` recipe.

## PR title and Lody session

Read the live title and remove only the exact leading `Plan:` prefix and its
following space. Keep the remainder unchanged, and do not write an empty title.
Compare a fresh title read with the original immediately before editing, then
read the title back and verify the result. Stop and reconcile if either
comparison fails.

```bash
original_title=$(gh pr view "$pr" --repo "$repo" --json title --jq '.title') || exit
title=$original_title
if [[ "$original_title" == 'Plan: '* ]]; then
  title=${original_title#'Plan: '}
  [[ -n "${title//[[:space:]]/}" ]] || {
    printf '%s\n' 'Removing the prefix would leave an empty title.' >&2
    exit 2
  }

  current_title=$(gh pr view "$pr" --repo "$repo" --json title --jq '.title') || exit
  [[ "$current_title" == "$original_title" ]] || {
    printf '%s\n' 'The PR title changed; reconcile before editing.' >&2
    exit 2
  }

  gh pr edit "$pr" --repo "$repo" --title "$title" || exit

  readback_title=$(gh pr view "$pr" --repo "$repo" --json title --jq '.title') || exit
  [[ "$readback_title" == "$title" ]] || {
    printf '%s\n' 'The PR title read-back differs; reconcile before continuing.' >&2
    exit 2
  }
fi
```

The compare and edit are not atomic: `gh pr edit` has no conditional
title-update flag, so another writer could change the title after the
comparison. Serialize title edits across writers when excluding that race is
required. Read-back verifies the observed result but cannot prevent a later
concurrent edit.

Confirm that this is an active Lody session, the CLI is installed, and the
identifier is present before changing its title. A missing capability in a Lody
assignment is a blocker, not a silently skipped step. Outside Lody, record the
session steps as inapplicable; do not invent an identifier or unrelated session.

```bash
: "${LODY_SESSION_ID:?An active Lody session ID is required}"
echo "${LODY_SESSION_ID}"
lody session rename --title "$title"
```

For the source deployment, construct the URL as
`https://lody.ai/leynos/sessions/${LODY_SESSION_ID}`. Other deployments must
supply their actual Lody account/session base URL; do not infer it from the
GitHub owner. Validate the identifier as a URL path segment using the
installation's contract, and verify the rename through the CLI's actual result
or supported read-back. Do not invent a Lody inspection command.

## Description and final References section

Fetch the complete live PR body. Preserve task links, issue-closing keywords,
stack information, attribution, and unrelated human-authored content. Replace
stale plan-only prose with the implementation summary, acceptance evidence,
test and proof results, and any known limitations.

Maintain one final second-level `## References` section containing the
ExecPlan, Lody session when applicable, and existing references. Add a link
only when absent. If the section exists earlier, move its complete content to
the end without dropping nested content. Do not truncate the body or replace it
with a bare session link. Preserve required machine-managed blocks; report an
ordering conflict rather than corrupting them.

Prepare a body file in approved scratch, inspect its diff, and re-read the
remote body immediately before writing to detect intervening edits. Reconcile
changes instead of overwriting another editor. Use `gh pr edit --body-file`,
then read back the complete body and title to verify the result. A failed or
ambiguous write requires observation before retrying.

## Source

[GitHub: renaming a branch](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/renaming-a-branch)
documents the remote-head rename consequence. Read live repository state
before applying any branch migration; this reference is not a migration script.
