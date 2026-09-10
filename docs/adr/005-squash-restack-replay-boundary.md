# ADR 005: Squash-restack replay boundary

**Status:** Proposed

## Context

The `rebase` skill restacks a child branch after its parent PR has
squash-merged. A squash merge collapses the parent's original commits into one
landing commit on the target, so the child's own replay boundary — the last
commit it inherited from the parent, `OLD_BASE` — is no longer present on the
target as a distinguishable object. Three identities look similar but are not
interchangeable:

- the original parent PR head (the last commit the child actually forked
  from, or inherited via subsequent rebases);
- the parent's squash landing commit (`merge_commit_sha`), a new commit on the
  target that never existed in the child's history;
- the apparent first child-authored commit, which is only correct when no
  rebase, amend, or history rewrite has ever touched the boundary.

Treating any of these as the replay boundary is unsound in the general case:

- the target merge-base is only a topology fact about the current graph. If
  the parent advanced or was rewritten after the child forked, the ordinary
  merge-base can silently return an earlier, wrong commit, or several
  candidates with no way to choose between them;
- the squash SHA never appears in the child's own history, so using it as
  `OLD_BASE` for `git rebase --onto TARGET OLD_BASE BRANCH` is a type error
  against the intended operation: it cannot bound the child's own commit
  series correctly, and using it directly as a `--onto` target beside a
  non-ancestor `OLD_BASE` produces a rebase that does not do what the operator
  intended;
- the apparent first child commit is not an intrinsic property of the graph.
  It depends on how many commits the parent contributed before the child
  branched, information that is not recoverable from the child branch alone
  and that guessing gets silently wrong whenever the parent's history is
  longer or shorter than assumed.

Earlier iterations of this skill described this boundary problem only in
prose (`skills/rebase/references/squashed-parent.md`). Without an executable,
tested planner, an operator or a smaller agent could still substitute one of
the unsound candidates above, discover the mistake only after a rebase had
partially run, or never discover it at all. The branch under review adds
`skills/rebase/scripts/plan_restack.py`, a query-only planner that gathers
GitHub and Git evidence, refuses when that evidence cannot prove an exclusive
boundary, and otherwise returns a `review-required` plan for a human or agent
to inspect before any replay runs. This record captures why the planner
refuses rather than infers, and why a maintained receipt is a precondition for
recovering a non-inherited parent head rather than a routine input.

## Decision

Require that every squash-restack plan carry an explicit, evidence-backed
exclusive replay boundary, and refuse to produce a plan when the available
evidence cannot establish one. The planner never guesses a boundary from
positional or heuristic reasoning; it accepts only two forms of proof:

1. **Inherited parent head.** `discover()` fetches the parent PR's actual head
   commit (never the synthetic `refs/pull/N/merge` ref) from github.com into a
   private `refs/agent-rebase/<uuid>/parent-head` evidence ref, and
   `build_plan()` checks whether that commit is an ancestor of the child
   branch. If it is, the parent head itself is the boundary, with provenance
   `parent-pr-head`, and it is corroborated: the child's own retained history
   proves no inherited parent commit follows it.
2. **Maintained receipt, only when corroborated by inherited history.** If the
   parent head is not an ancestor of the child — because the parent advanced
   or was rewritten after the child last incorporated it — the planner accepts
   a boundary only from a `refs/stack-bases/<branch>` receipt whose paired
   `branch.<branch>.stackParent` config value names the same parent repository
   and PR. Even then, the receipt is marked uncorroborated whenever the
   recovered parent head is not inherited, because no evidence in that case
   proves that no inherited parent commit follows the receipted boundary; the
   plan still carries `boundary_corroborated: false` and `review_notes()`
   prepends an explicit warning demanding that the receipt be proven from
   preserved parent history or reflog before replay.

In every other case — no receipt, a malformed receipt, a receipt naming an
unrelated parent, or a receipt that is not an ancestor of the child — the
planner raises `PlanError`, which the CLI reports as
`{"status": "blocked", "reason": ...}` on stderr with exit status 2. A
successful plan is always `review-required` or `no-op-decision-required`,
never an authorization to replay.

### Alternatives considered

- **Infer from the target merge-base.** Rejected because the merge-base is a
  pure topology fact. When the parent advanced past the fork point, the
  merge-base can return an earlier, incorrect commit without any signal that
  it is wrong; when the parent history was rewritten, it can return the
  original trunk instead of any parent-authored work at all. The planner's
  own test graphs demonstrate this: an advanced or rewritten parent still
  produces a single "candidate" merge-base that is provably wrong, which is
  exactly the trap this decision exists to avoid.
- **Infer from the squash SHA.** Rejected because the squash landing commit is
  a new commit on the target, not a commit the child ever inherited; it
  cannot serve as `OLD_BASE` for the child's own replay range. The landing
  commit remains useful evidence that the parent PR integrated onto the
  target (`discover()` still resolves and checks it), but only as a landing
  check, never as the boundary itself.
- **Infer from the apparent first child commit.** Rejected because the number
  of commits the parent contributed before the child branched is not
  recoverable from the child branch in isolation. Guessing this boundary
  either drops genuine child commits or replays inherited parent commits as
  if they were the child's own work, and there is no local signal that
  distinguishes a correct guess from an incorrect one.
- **Always require a maintained receipt.** Rejected as the sole mechanism
  because it would force operators to record a receipt even in the common
  case where the parent head is still directly reachable from the child and
  needs no external record. The planner instead prefers the inherited parent
  head when it is available, corroborated, and provable from real ancestry,
  and falls back to a receipt only when that proof is unavailable — and even
  then treats an uncorroborated receipt as review-required rather than
  authoritative, since a receipt alone cannot prove the absence of a later,
  unrecorded parent commit.

## Consequences

- Restacking after an advanced or rewritten parent history, with no
  maintained receipt, is blocked by design. The planner exits with a
  `blocked` status rather than proposing a plan built on an unproven
  candidate; operators must recover stronger evidence (a preserved ref,
  reflog, or PR history) before a plan can be produced at all.
- Operators who expect a parent's history to move must maintain
  `refs/stack-bases/<branch>` receipts and the paired
  `branch.<branch>.stackParent` config at branch creation or after each
  successful restack, per the "Prefer a maintained receipt" procedure in
  `skills/rebase/references/squashed-parent.md`. A stale or mismatched
  receipt is rejected rather than silently accepted.
- The helper never authorizes a replay by itself. Every successful plan is
  `review-required` or `no-op-decision-required`, both of which still demand
  the ownership, recovery, and driver checks documented in
  `skills/rebase/SKILL.md` before any rebase argv from the plan is executed.
- The command/query split (`discover()` performs all `gh` and Git-network
  interaction and returns an immutable snapshot; `build_plan()` performs only
  local graph queries against that snapshot) keeps the refusal and
  corroboration logic testable without a live network dependency, at the cost
  of an extra data-passing layer between discovery and planning.
- Maintainers must keep this document,
  `skills/rebase/references/squashed-parent.md`, and the "Squash-restack
  replay boundary" section of
  [docs/developers-guide.md](../developers-guide.md) in step: a change to the
  boundary rules in `plan_restack.py` without a corresponding update to all
  three is a documentation regression even if the tests still pass.
