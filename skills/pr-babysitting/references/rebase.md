# Conflicted or outdated PRs

## Resolve the remote target before planning a replay

Use this procedure when the PR conflicts, becomes outdated under repository
policy, changes target, or needs a stack replay. Resolve the live PR's target
repository and `baseRefName`, not the repository default, local `main`, or the
feature branch's tracking upstream. If it targets `main` on the repository
mapped to `origin`, the target is `origin/main`; if it targets a release or
prerequisite branch, use that remote branch instead. Forks may use a different
verified remote for the target and for publishing the PR head.

Load `rebase` and `sem`. Inspect effective attributes and load
`weave-git-merge` whenever Weave is enabled or selected; follow its actual
driver-selection, recovery, and semantic-audit policy. Loading that skill is
not permission to enable a driver or bypass its unattended-replay safeguards.
Use `github-stacks` for an existing managed stack, preserving its topology.

In an exclusively owned linked worktree, establish staged, unstaged, and
untracked state, active operations, and other owners. Preserve recovery refs
and verified recovery material through `rebase`; do not reset, stash, clean,
or overwrite unrelated work. Record `OLD_HEAD`, the live remote PR-head SHA
as `EXPECTED_REMOTE_HEAD`, and the verified push remote/ref before rewriting.
Do not update that lease just because a later fetch observes another writer.

Read PR metadata with an explicit repository and number. Having verified
`target_remote` maps to the target repository and `target_branch` is its live
base ref, fetch that branch and freeze its object ID:

```bash
git check-ref-format "refs/heads/$target_branch"
git fetch --no-tags "$target_remote" \
  "refs/heads/$target_branch:refs/remotes/$target_remote/$target_branch"
TARGET_REF="refs/remotes/$target_remote/$target_branch"
TARGET=$(git rev-parse --verify "$TARGET_REF^{commit}")
```

Check each command's success before continuing. Re-read live PR metadata and
reconcile target movement; do not replay against an obsolete or unrelated
branch. Establish the exclusive `OLD_BASE` and proposed commit series through
`rebase`, including squash-parent evidence when needed. A PR's base SHA or
ordinary merge-base does not establish a squash-restack boundary. Execute
only the reviewed replay plan from that skill, with the fetched `TARGET`
as its explicit target, the merge backend, and `merge.conflictStyle=zdiff3`.

## Plan each conflict before editing

At every stop, inspect `git status`, unmerged paths and index stages, the
replayed commit and its parent, the accumulated rebased result, and both
branches' relevant history. Use `sem` for entity-level diffs and impact,
alongside native textual diffs, callers, tests, and design decisions. Record
a resolution plan for each conflict: what each side intended, pertinent
changes to retain, the proposed combined behaviour, risks, and validation.
Do this before editing or staging, not as an explanation after guessing.

Preserve the current branch's purpose while incorporating target-branch
improvements. Understand why a change exists; retaining both textual hunks
can still break the contract. Escalate incompatible requirements or uncertain
ownership rather than deleting a side. During rebase, `ours` and `theirs`
are not reliable human branch labels: inspect the stage blobs and use explicit
object IDs. Stage only reviewed resolutions, apply the repository's cheap
structural checks, and continue with the same authorized driver settings.
Do not automatically skip empty or conflicted commits.

When Weave participates, preserve its diagnostic output and inspect clean
regions and automatic resolutions too. Apply its per-replay checks and final
semantic audit; a clean driver exit, parse, or test pass is not sufficient.
Use its recovery procedure for malformed or garbled output before continuing.

## Packaging lockfiles

Resolve manifests and dependency requirements semantically from both branches.
For a conflicted generated packaging lockfile that exists at the frozen
`TARGET`, use only that target branch's lockfile as the resolution baseline:

```bash
git restore --source="$TARGET" --staged --worktree -- "$lockfile"
```

This means the actual PR target, not hard-coded `main` and not blindly
`--ours` or `--theirs`. Do not hand-merge lock entries or discard the feature's
manifest requirements. Record each lockfile needing regeneration. If a
lockfile is new, removed, renamed, absent at the target, or coupled to a
package-manager change, inspect that intent and record a plan; do not invent
a target file or resurrect a deliberate deletion.

After the replay finishes, rebuild affected lockfiles from the combined
manifests using the repository's prescribed package manager, version, and
lock-generation command. Regenerate sooner as well if a per-replay gate
requires a coherent manifest/lock pair. Review the resulting dependency diff,
preserve both branches' requirements, and avoid unrelated upgrades. A target
baseline is not the final lockfile when the feature changes dependencies.

## Validate, finish outstanding work, and publish with a lease

Audit the old/new commit series and final target diff through `rebase` and
`sem`, explaining changed, missing, added, and empty commits and unintended
deletions. Retain the operation receipt and conflict decisions. Have a
scrutineer run these required gates sequentially on the completed result:

```bash
make check-fmt
make test
make typecheck
make lint
```

Include additional repository-required gates and review/proof obligations.
Use the repository's mandated order when it defines one, but retain all four
checks. Record a genuinely inapplicable target with evidence; a failed or
missing required command is a blocker, not an implicit exemption.

Validate and commit any deliberate outstanding changes, including regenerated
lockfiles, before publication. Never commit someone else's changes or create
an empty commit merely because the rebase completed. Rerun affected gates for
post-rebase repairs and record the final accepted `CANDIDATE` SHA.

Immediately before pushing, recheck the PR target, remote topology, and head.
For an ordinary authorized branch, use a single explicit refspec and the
remote-head lease recorded before rewriting:

```bash
git push --no-follow-tags \
  --force-with-lease="refs/heads/$head_branch:$EXPECTED_REMOTE_HEAD" \
  "$push_remote" "$CANDIDATE:refs/heads/$head_branch"
```

A rejected lease stops publication. Inspect the concurrent work and reconcile;
never use unconditional force or refresh the expected SHA merely to overwrite
it. Managed stacks use `github-stacks`' protected publication and receipt
procedure rather than an ad-hoc push that bypasses their metadata.

Verify the actual remote head equals `CANDIDATE` and the PR still targets the
intended branch. Return to the parent skill's scrutineer CI monitoring and
review reconciliation with fresh base/head evidence. Old approvals and green
checks do not transfer automatically. Retain recovery refs until publication
and acceptance policy permit cleanup.

## Sources and rehearsal

The operational contracts live in [rebase](../../rebase/SKILL.md),
[sem](../../sem/SKILL.md), and
[weave-git-merge](../../weave-git-merge/SKILL.md). Git documents
[rebase side semantics](https://git-scm.com/docs/git-rebase) and
[explicit push leases](https://git-scm.com/docs/git-push).

Rehearse a PR targeting a non-default release branch; a squash-merged parent;
a conflict where both branches improve behaviour; a lockfile conflict with
feature-only manifest changes; a target-side lockfile deletion; Weave's clean
but incorrect output; a failing post-rebase gate; and a concurrent push that
rejects the lease. Each case must preserve provenance and either demonstrate
the correct combined result or stop before unsafe publication.
