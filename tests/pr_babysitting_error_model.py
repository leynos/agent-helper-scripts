"""Executable specification of the documented PR-babysitting error handling.

The skill states two dispositions in prose: a failing hosted check is rebased
before it is investigated when the same commit gates pass locally and the branch
is behind its target, and a newer lint suite's out-of-scope violations become a
prerequisite fix PR rather than feature repairs. This module restates both
decisions, so the contract tests can exercise every branch by name instead of
matching sentences.

It is a specification rehearsal, not skill enforcement. Every decision it can
return appears in ``REASON_CITATIONS`` with the sentence that states the rule,
and ``test_pr_babysitting_error_model.py`` requires both to stay in step with
the shipped skill. Nothing here talks to GitHub, runs Git, or changes a PR.
"""

from __future__ import annotations

#: Outcomes for a hosted CI failure the supervisor has to diagnose.
NO_CI_FAILURE = "no-ci-failure"
REBASE_FIRST = "rebase-before-investigation"
INVESTIGATE = "investigate"

#: Outcomes for a lint suite that reports violations against a candidate.
REPAIR_IN_SCOPE = "repair-in-scope"
BASE_ON_EXISTING_FIX = "base-on-existing-fix"
CREATE_FIX_AND_RETARGET = "create-fix-and-retarget"
CREATE_FIX_STACK_AND_RETARGET = "create-fix-stack-and-retarget"
TEMPORARY_FIX_COPY = "temporary-fix-copy"
CREATE_FIX_AND_REBASE_STACK = "create-fix-and-rebase-stack"

#: The sentence in the shipped skill that states each decision's rule.
#: Contract tests assert these remain present, so a decision cannot outlive it.
REASON_CITATIONS = {
    NO_CI_FAILURE: (
        "A green hosted result needs no diagnosis, and this rebase rule applies"
        " only to a red current candidate."
    ),
    REBASE_FIRST: (
        "Do not read failure logs, post an investigation comment, or dispatch a"
        " repair until the rebased candidate has its own CI result."
    ),
    INVESTIGATE: (
        "When local gates also fail, or the branch is already up to date,"
        " diagnose the failure normally"
    ),
    REPAIR_IN_SCOPE: (
        "A newer lint-suite release, such as a new Whitaker version, may report"
        " violations in code the candidate did not change."
    ),
    BASE_ON_EXISTING_FIX: (
        "First look for an open PR targeting the same target branch that already"
        " addresses the violations, and base this PR on that branch until it"
        " merges."
    ),
    CREATE_FIX_AND_RETARGET: (
        "Otherwise, create a new base PR targeting the target branch that fixes"
        " exactly the newly reported violations, rebase this PR onto it, and"
        " retarget this PR to the new branch."
    ),
    CREATE_FIX_STACK_AND_RETARGET: (
        "For the new base PR in step 2, create the chain as a managed stack"
        " with `github-stacks` when the tooling is available and enabled."
    ),
    TEMPORARY_FIX_COPY: (
        "If an existing fix PR applies, base the stack on a temporary copy of"
        " that fix PR."
    ),
    CREATE_FIX_AND_REBASE_STACK: (
        "If no existing fix PR applies, create the fix PR and rebase the whole"
        " stack onto it with `github-stacks`."
    ),
}
REASONS = frozenset(REASON_CITATIONS)

#: Constraints the dispositions must respect. A PR belongs to only one stack,
#: so an existing fix PR is reused as a plain base branch rather than added to
#: this feature's stack. The citation keeps that reason next to the model.
CONSTRAINT_CITATIONS = {
    "one-stack-per-pr": (
        "Reuse it as a base branch, not as a new stack layer: a PR can belong to"
        " only one stack, and the existing fix PR may already be in one."
    ),
}
CONSTRAINTS = frozenset(CONSTRAINT_CITATIONS)


def ci_failure_disposition(
    *, ci_failing: bool, local_gates_pass: bool, behind_target: bool
) -> str:
    """Choose between rebasing and investigating a hosted failure.

    The rebase-first rule needs all three facts: the hosted candidate is
    failing, the same commit gates pass locally, and the target contains
    commits the branch does not. Reading a local pass alone as evidence of a
    branch defect would send the agent into logs for a failure the rebased
    candidate may not reproduce.

    Parameters
    ----------
    ci_failing : bool
        Whether the current head has a red hosted run or check.
    local_gates_pass : bool
        Whether the repository's commit gates pass for that same head locally.
    behind_target : bool
        Whether the live target contains commits the branch does not.

    Returns
    -------
    str
        ``rebase-before-investigation`` when all three hold,
        ``investigate`` when a gate fails or the branch is current, and
        ``no-ci-failure`` when there is no failure to diagnose.
    """
    if not ci_failing:
        return NO_CI_FAILURE
    if local_gates_pass and behind_target:
        return REBASE_FIRST
    return INVESTIGATE


def lint_violation_disposition(
    *,
    newer_suite: bool,
    out_of_scope: bool,
    existing_fix_pr: bool,
    in_managed_stack: bool,
    stack_tooling: bool,
) -> str:
    """Choose where a newer lint suite's violations are repaired.

    Only a newer suite reporting against code the candidate did not change is
    prerequisite work. Such a violation moves beneath the feature: an existing
    fix PR is reused, or a new fix PR is created and the feature retargeted.
    A managed stack rebases as a whole, and an existing fix PR already moving
    under a stack is pinned as a temporary copy until it merges.

    An existing fix PR is reused only as a base branch. A PR can belong to only
    one stack, so it is never added to a new stack for this feature, even when
    stack tooling is available.

    Parameters
    ----------
    newer_suite : bool
        Whether the violation comes from a newer release of the lint suite
        rather than the rules the candidate was written against.
    out_of_scope : bool
        Whether the reported code lies outside the candidate's changes.
    existing_fix_pr : bool
        Whether an open PR already fixes the same violations.
    in_managed_stack : bool
        Whether this PR is a layer in an existing managed stack.
    stack_tooling : bool
        Whether ``github-stacks`` is available and enabled for a new chain.

    Returns
    -------
    str
        The base or repair action the skill prescribes. In-scope findings and
        findings from the candidate's own rule set return
        ``repair-in-scope``.
    """
    if not (newer_suite and out_of_scope):
        return REPAIR_IN_SCOPE
    if in_managed_stack:
        if existing_fix_pr:
            return TEMPORARY_FIX_COPY
        return CREATE_FIX_AND_REBASE_STACK
    if existing_fix_pr:
        return BASE_ON_EXISTING_FIX
    if stack_tooling:
        return CREATE_FIX_STACK_AND_RETARGET
    return CREATE_FIX_AND_RETARGET