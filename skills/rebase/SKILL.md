---
name: rebase
description: >
  Rebase a branch onto an explicit target, including restacking after a parent
  PR was squash-merged. Establish and validate the exclusive replay boundary
  before rewriting history; preserve recovery evidence, resolve conflicts,
  audit the replay, and validate the exact new candidate.
---

# Rebase the current branch or restack safely

Establish which commits belong to this branch before running rebase. A parent
PR's squash commit is a landing record, not the old replay boundary. Do not
start replaying commits merely to discover which ones conflict.

## Establish the operation

Use the target the user requested. Otherwise resolve the default branch on the
principal remote; do not assume `origin/main` or a mutable local checkout.

For unattended work, keep the primary checkout read-only and use an exclusively
owned linked worktree. Check its staged, unstaged, and untracked state and any
active Git operation. Stop for unrelated work, another active operation, or a
concurrent owner; do not stash, reset, or clean someone else's work.

Record the branch identity, `OLD_HEAD`, target ref and fetched `TARGET` SHA,
parent relationship, and the expected remote branch head when publication is
in scope. Snapshot useful parent refs before fetching; do not prune during
recovery. Require enough local history to verify ancestry and all range members.

For an existing tool-managed stack, inspect its metadata and follow the
[github-stacks skill](../github-stacks/SKILL.md). Do not bypass its tracking
with an ad-hoc rewrite. Apply this skill's evidence and acceptance requirements
before any stack command that also pushes or prunes.

## Establish OLD_BASE: the exclusive replay boundary

For the linear-history workflow, the intended original series is
`OLD_BASE..OLD_HEAD`. `OLD_BASE` is the last inherited commit, not the first
commit to replay. The graph's ordinary target merge-base is only a topology
fact; it does not identify a squash boundary.

Prefer a current boundary receipt or preserved ref with known provenance.
Otherwise follow [Recover a squash-merged parent](references/squashed-parent.md):
identify the parent PR, recover its historical head, and validate that head
against this branch. Use reflogs when the parent history was rewritten.

A fetched PR head, a merge-base, a title match, a PR association, or a matching
net patch can each supply a candidate. Do not mistake a candidate for proof.
State what evidence shows that no inherited parent commit remains in the replay
range and no child commit falls outside it. Stop and return an uncertainty
report if the evidence cannot establish one boundary. Do not ask a smaller
agent to invent one.

Never automatically substitute the squash SHA, a current PR's `baseRefOid`,
the target merge-base, a guessed `HEAD~N`, or an author's first apparent commit.

## Produce a reviewable plan

For a confirmed squash-merged parent with a known PR identity, use the bundled
planner from the owned worktree. Set `SKILL_DIR` to this installed skill's
absolute directory, not a path guessed relative to the target repository:

```bash
uv run "$SKILL_DIR/scripts/plan_restack.py" . \
  --branch "$BRANCH" --target-ref "$TARGET_REF" \
  --parent-repository "$PARENT_REPOSITORY" --parent-pr "$PARENT_PR"
```

The planner requires a clean, non-shallow checkout and an already fetched target.
It queries `gh`, fetches only the PR head into a fresh private evidence ref, and
prints JSON containing the frozen identities, exact commit list, evidence source,
and proposed argv. It does not rebase, push, prune, update tracking branches,
write `FETCH_HEAD`, or modify the index/worktree. Evidence refs remain for review.
Bounded structured diagnostics go to standard error, keyed by the same
`operation` identifier the plan carries; parse the plan from standard output
alone and never merge the two streams.
The fetch uses the explicit parent repository on github.com, including when the
child lives in a fork; other GitHub hosts need a separately reviewed procedure.

A successful response says `review-required`, not approved or safe to execute.
Confirm the merge method independently: the metadata alone cannot distinguish
squash merge from rebase merge. Apply the ownership, recovery and driver checks
below before running any proposed argv. Exit status 2 and a `blocked` JSON
response mean stop; API, fetch and missing-object errors are not negative
ancestry results. An empty range produces `no-op-decision-required`, without argv.

If the current parent head is not inherited, the planner refuses to pick a
merge-base even when only one exists. Review the advanced/rewritten-parent
procedure in the reference. A maintained `refs/stack-bases/$BRANCH` receipt may
be supplied with `--boundary-ref`; the matching
`branch.$BRANCH.stackParent` must identify the same repository and PR. Such a
plan reports `boundary_corroborated: false`, because only inherited parent
history can prove that no inherited commit follows the receipt. Prove that from
preserved parent history or a reflog, and review receipt freshness and
ownership, before replaying. Discovery does not search
PR titles or silently choose among ambiguous commit-to-PR associations.

## Review the plan before mutation

Record full object IDs and the boundary evidence. Inspect:

```bash
git merge-base --is-ancestor "$OLD_BASE" "$OLD_HEAD"
git rev-list --merges "$OLD_BASE..$OLD_HEAD"
git log --reverse --format='%H %s' "$OLD_BASE..$OLD_HEAD"
git diff --no-ext-diff --no-textconv --stat "$OLD_BASE" "$OLD_HEAD"
```

The ancestry check must succeed and the merge list must be empty for this
linear workflow. Read the actual patches as needed; names and diffstat alone
cannot establish ownership. Account for the entire series, especially the
first replayed commit and the last excluded commit. An empty series requires
an explicit no-op decision, not a branch rewrite by default.

For a squash restack, verify that the identified parent PR merged and its
landing commit is reachable from `TARGET`. This proves landing, not that later
commits have not reverted or changed the functionality. Investigate evidence
of such changes rather than resurrecting old parent work automatically.

Create uniquely named recovery refs for `OLD_HEAD`, `OLD_BASE`, and `TARGET`
before rewriting. Preserve any intended work not represented by these commits
using the [verified recovery procedure](../weave-git-merge/SKILL.md#recover-safely).
Recheck that the operated branch still points to `OLD_HEAD` before starting.
Generate recovery patches with `git diff --no-ext-diff --no-textconv --binary`.
A configured `diff.external` or `GIT_EXTERNAL_DIFF` can replace native patches
with a tool-specific format that `git apply` rejects with
`error: No valid patches in input`. Confirm a saved patch starts with
`diff --git` before applying it. History commands suppress external diff drivers;
prefer
`git stash show -p` when the work to recover is a stash. Disable text conversions
when generating patches for application, not merely for human inspection.
Preserve staged and unstaged work separately, and retain an explicit manifest
and copies of intended untracked files. A patch alone does not include those
files. Verify recovery material before any abort, reset or retry.

## Replay only the accepted range

Follow the [Weave driver-selection policy](../weave-git-merge/SKILL.md#decide-whether-weave-should-participate)
before replay. Do not trust ambient merge-driver selection or a clean exit.
Use `zdiff3` and the merge backend. For an accepted linear plan in the owned
worktree, start with these explicit options:

```bash
git -c merge.conflictStyle=zdiff3 rebase \
  --merge --no-fork-point --no-update-refs --no-autostash \
  --reapply-cherry-picks --keep-empty --empty=stop \
  --onto "$TARGET" "$OLD_BASE" "$BRANCH"
```

Use any authorized driver overrides or per-replay gates in addition to this
command. Check installed Git support; do not silently weaken unsupported
safety options. Preserve initially empty commits. Investigate commits that
become empty, rather than automatically dropping them or skipping conflicts.
Do not flatten a merge-containing series through this linear procedure.

For each conflict, inspect the replayed commit, its parent, and the accumulated
rebased result. Preserve the intended child change while respecting target
changes. Do not select `ours` or `theirs` by remembered branch labels. Stage
only reviewed resolution paths. For lockfiles, preserve manifest intent and
regenerate with the repository's prescribed tool and version; review the result.
Preserve manual resolution work before an abort or retry.

If a conflict resolution looks garbled or a resolved file fails to parse, use
the [weave-git-merge recovery and built-in-merge fallback](../weave-git-merge/SKILL.md#recover-safely)
before continuing the rebase.

## Audit, validate, and report

Record `NEW_HEAD`, then compare the exact old and new series:

```bash
git range-diff "$OLD_BASE..$OLD_HEAD" "$TARGET..$NEW_HEAD"
git diff --no-ext-diff --no-textconv "$TARGET" "$NEW_HEAD"
git diff --check "$TARGET" "$NEW_HEAD"
```

Explain every changed, added, missing, or empty commit. Audit the final target
versus child diff for unintended deletions and resurrection of parent work.
`range-diff` supports review; do not use its textual output or exit status as
a stable machine proof. Follow the Weave semantic audit whenever that driver
participated. Use `OLD_BASE..OLD_HEAD` as the child-owned input for a squash
restack; do not accidentally include the inherited parent changes as child work.

Run the repository's documented formatting, test, lint, and applicable type
checks against the final candidate. Record an inapplicable target as such;
do not suppress a failure because it resembles a missing target. Existing
checks or reviews for `OLD_HEAD` do not authorize acceptance of `NEW_HEAD`.
Commit only deliberate, reviewed post-rebase changes; rerun affected gates
and refresh evidence if these create another candidate.

Report old and new heads, the target and exclusive boundary, evidence source,
replayed series, conflict and omission decisions, gate results, and remaining
uncertainty. Advance boundary metadata only for the accepted result, preserving
the earlier receipt. Push only when authorized; bind any force-with-lease to
the previously recorded remote head, and do not refresh it blindly on failure.
Retain recovery refs until the publication and acceptance policy allows cleanup.
