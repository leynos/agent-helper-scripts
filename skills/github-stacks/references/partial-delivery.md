# Partial-stack delivery and recovery

Use this procedure when the managed stack cannot safely publish just the
validated merge frontier. It is not permission to bypass replay acceptance,
required gates, repository protections or the user's mutation scope.

## Establish the smallest publishable scope

1. Inspect the installed `gh stack` version and command help. Do not invent a
   single-branch flag: `push` can publish every active layer, while `submit` and
   `link` can also change PR metadata. Prefer a supported scoped operation when
   its complete mutation set is known and validated.
2. Record live remote topology and local stack metadata before mutation. For
   each affected layer, retain its PR/base, branch, old head, exclusive replay
   boundary and expected remote head. Record the authoritative candidate's
   absolute worktree and `git rev-parse --git-common-dir`; identical branch
   names in separate clones do not identify the same candidate.
3. If no safe scoped stack command exists, use a recorded native-Git recovery
   operation for the frontier only. Review the
   [rebase acceptance procedure](../../rebase/SKILL.md) and preserve recovery
   refs and verified patches first. Review means perform the evidence checks;
   it does not require fresh permission for an already authorized operation.
4. Use an exclusively owned checkout. If shared refs, dirty descendants or
   managed metadata prevent isolation, prepare a separate recovery clone and
   explicitly transfer the candidate and boundary evidence. Do not truncate
   live stack metadata, dissolve the remote stack or reset another owner's refs
   merely to make a push command narrower.
5. Replay only the accepted range when replay is necessary. Audit the result
   and run the required gates on that exact candidate. Do not reinterpret a
   provisional experiment or earlier green ancestor as this evidence.

If the boundary, topology or supported reconciliation route remains uncertain,
stop this mutation and report the exact missing evidence. Keep independent
work moving; do not turn uncertainty into repeated speculative stack rewrites.

## Publish one existing PR branch

This fallback is for an existing, unqueued frontier PR with a verified base
and an authorized branch update. It does not create or retarget PRs. If a base
change is needed, handle it as a separately reviewed metadata operation.

Assign `REMOTE`, `BRANCH`, `EXPECTED_REMOTE_HEAD` and `CANDIDATE` from the
reviewed receipt, using full object IDs and the inspected GitHub remote.
Confirm that the remote has exactly the expected branch head before executing
the push; stop on a mismatch. The explicit lease also protects the interval
between this read and the update.

```bash
git ls-remote --exit-code "$REMOTE" "refs/heads/$BRANCH"
git push --no-follow-tags \
  --force-with-lease="refs/heads/$BRANCH:$EXPECTED_REMOTE_HEAD" \
  "$REMOTE" "$CANDIDATE:refs/heads/$BRANCH"
git ls-remote --exit-code "$REMOTE" "refs/heads/$BRANCH"
```

Run these individually and inspect each result. Verify that the final remote
SHA equals `CANDIDATE`, then read the PR's `headRefOid` and base from GitHub.
An explicit source SHA prevents a concurrent local branch movement from changing
the content being pushed. Do not refresh a rejected lease blindly: inspect the
new remote work and reassess the candidate. Never add `--force`, a wildcard
refspec, `--all` or `--mirror` to get past a rejection.

Record that descendant branches were deliberately not published and may now
need replay. Re-read remote descendants in case GitHub changed them, then
reconcile the owned local stack tracking through its supported workflow before
the next managed write. Keep preserved boundary receipts until reconciliation
is verified. If reconciliation is blocked, report that blocker rather than
running a stack-wide push from stale metadata. A disposable-remote experiment
tests the mechanism only; it does not complete this live publication step.

For stack-wide pushes, read back every intended ref even after a non-zero exit:
the operation is not atomic and some leases may have succeeded. Revalidate only
the unresolved publication decisions; do not blindly replay or retry the whole
stack. The installed help and
[GitHub's CLI reference](https://docs.github.com/en/pull-requests/reference/stacked-prs-cli-commands)
describe this partial-success behaviour.

## Delivery handoff

When a team is already authorized, assign one owner through replay, gates,
publication and the next hosted handoff. Include owned paths/review findings,
candidate identities, allowed mutations, gate commands and a measurable
completion condition. A reconnaissance task names the delivery owner that
will consume its answer; it does not end in another unowned investigation.

Keep gates sequential where required, with frontier work first. A terminal
candidate-specific failure releases the gate queue to independent work; reserve
a global stop for shared integrity or resource failures.

## Publication receipt

Return the PR and parent identity, old/new local and remote SHAs, replay
boundary, exact candidate gate results, push result and GitHub read-back.
Include untouched descendants, pending metadata reconciliation, the next
authorized hosted action and its owner. Once published, readiness, review
request delivery, completed review and merge are separate state transitions.
Do not close a delivery task merely because its local patch or report is ready.
