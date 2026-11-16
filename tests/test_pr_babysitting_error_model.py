"""Exercise the documented PR-babysitting error dispositions.

The skill states the rules in prose, so these cases drive the executable
specification with whole facts: the hosted and local gate results, the target's
position, and the fix PR and stack context. It also requires every decision to
cite a sentence the shipped skill still contains, and proves each input is
load-bearing by changing it and observing a different decision.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import pr_babysitting_error_model as error_module
from pr_babysitting_error_model import (
    BASE_ON_EXISTING_FIX,
    CONSTRAINT_CITATIONS,
    CREATE_FIX_AND_REBASE_STACK,
    CREATE_FIX_AND_RETARGET,
    CREATE_FIX_STACK_AND_RETARGET,
    INVESTIGATE,
    NO_CI_FAILURE,
    REASON_CITATIONS,
    REBASE_FIRST,
    REPAIR_IN_SCOPE,
    TEMPORARY_FIX_COPY,
    ci_failure_disposition,
    lint_violation_disposition,
)
from skill_contract_support import normalize


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"


def ci_case(
    *, ci_failing: bool, local_gates_pass: bool, behind_target: bool
) -> str:
    """Return the CI disposition for one set of observed facts."""
    return ci_failure_disposition(
        ci_failing=ci_failing,
        local_gates_pass=local_gates_pass,
        behind_target=behind_target,
    )


def lint_case(
    *,
    newer_suite: bool = True,
    out_of_scope: bool = True,
    existing_fix_pr: bool = False,
    in_managed_stack: bool = False,
    stack_tooling: bool = True,
) -> str:
    """Return the lint disposition for one set of observed facts."""
    return lint_violation_disposition(
        newer_suite=newer_suite,
        out_of_scope=out_of_scope,
        existing_fix_pr=existing_fix_pr,
        in_managed_stack=in_managed_stack,
        stack_tooling=stack_tooling,
    )


@pytest.mark.parametrize(
    ("ci_failing", "local_gates_pass", "behind_target", "expected"),
    [
        (False, True, True, NO_CI_FAILURE),
        (False, False, False, NO_CI_FAILURE),
        (True, True, True, REBASE_FIRST),
        (True, True, False, INVESTIGATE),
        (True, False, True, INVESTIGATE),
        (True, False, False, INVESTIGATE),
    ],
    ids=[
        "green-passing-behind",
        "green-failing-current",
        "stale-base",
        "current-branch",
        "local-failure",
        "local-failure-current",
    ],
)
def test_ci_disposition_rebases_only_a_stale_base_with_a_local_pass(
    ci_failing: bool, local_gates_pass: bool, behind_target: bool, expected: str
) -> None:
    """All three facts are required before a red run is diagnosed through a rebase."""
    assert (
        ci_case(
            ci_failing=ci_failing,
            local_gates_pass=local_gates_pass,
            behind_target=behind_target,
        )
        == expected
    )


def test_each_ci_condition_changes_the_decision() -> None:
    """Dropping any one required fact sends the case back to investigation.

    This is the mutation control for the rebase-first rule: a model that
    ignored the local pass, the target position, or the red result would still
    return ``rebase-before-investigation`` here and fail these assertions.
    """
    variants = {
        "no-failure": ci_case(
            ci_failing=False, local_gates_pass=True, behind_target=True
        ),
        "local-failure": ci_case(
            ci_failing=True, local_gates_pass=False, behind_target=True
        ),
        "current-branch": ci_case(
            ci_failing=True, local_gates_pass=True, behind_target=False
        ),
    }
    assert REBASE_FIRST not in variants.values()
    assert variants["no-failure"] == NO_CI_FAILURE
    assert variants["local-failure"] == variants["current-branch"] == INVESTIGATE


@pytest.mark.parametrize(
    ("newer_suite", "out_of_scope", "existing_fix_pr", "in_managed_stack", "stack_tooling", "expected"),
    [
        (False, True, False, False, True, REPAIR_IN_SCOPE),
        (True, False, False, False, True, REPAIR_IN_SCOPE),
        (True, True, True, False, True, BASE_ON_EXISTING_FIX),
        (True, True, True, False, False, BASE_ON_EXISTING_FIX),
        (True, True, False, False, True, CREATE_FIX_STACK_AND_RETARGET),
        (True, True, False, False, False, CREATE_FIX_AND_RETARGET),
        (True, True, True, True, True, TEMPORARY_FIX_COPY),
        (True, True, False, True, True, CREATE_FIX_AND_REBASE_STACK),
        (True, True, False, True, False, CREATE_FIX_AND_REBASE_STACK),
    ],
    ids=[
        "current-suite",
        "in-scope",
        "existing-fix-pr",
        "existing-fix-pr-no-stack-tooling",
        "new-fix-pr-as-stack",
        "new-fix-pr-as-branch",
        "stack-with-existing-fix",
        "stack-with-new-fix",
        "stack-with-new-fix-no-new-tooling",
    ],
)
def test_lint_disposition_places_out_of_scope_violations_beneath_the_feature(
    newer_suite: bool,
    out_of_scope: bool,
    existing_fix_pr: bool,
    in_managed_stack: bool,
    stack_tooling: bool,
    expected: str,
) -> None:
    """Only a newer suite's out-of-scope finding leaves the feature diff."""
    assert (
        lint_case(
            newer_suite=newer_suite,
            out_of_scope=out_of_scope,
            existing_fix_pr=existing_fix_pr,
            in_managed_stack=in_managed_stack,
            stack_tooling=stack_tooling,
        )
        == expected
    )


def test_each_lint_condition_changes_the_decision() -> None:
    """Dropping any required fact moves the repair back in scope or changes its base.

    The four stack cases and the two non-stack cases together show that no
    input is decorative: ignoring the suite age, scope, existing fix PR, stack
    membership, or stack tooling changes the action the skill prescribes.
    """
    assert lint_case(newer_suite=False) == REPAIR_IN_SCOPE
    assert lint_case(out_of_scope=False) == REPAIR_IN_SCOPE
    assert (
        lint_case(existing_fix_pr=True)
        != lint_case(existing_fix_pr=False)
    ), "the existing fix PR must change the base"
    assert (
        lint_case(in_managed_stack=True)
        != lint_case(in_managed_stack=False)
    ), "stack membership must change the replay strategy"
    assert (
        lint_case(stack_tooling=False)
        != lint_case(stack_tooling=True)
    ), "stack tooling must change whether a managed stack is created"


@pytest.mark.parametrize("reason", sorted(REASON_CITATIONS))
def test_each_reason_cites_a_sentence_in_the_skill(reason: str) -> None:
    """No decision may outlive the prose that states it."""
    documents = normalize(SKILL.read_text())
    assert normalize(REASON_CITATIONS[reason]) in documents, (
        f"reason {reason!r} cites a sentence the skill does not state:"
        f" {REASON_CITATIONS[reason]}"
    )


@pytest.mark.parametrize("constraint", sorted(CONSTRAINT_CITATIONS))
def test_each_constraint_cites_a_sentence_in_the_skill(constraint: str) -> None:
    """A constraint that stops being documented must fail the model's contract."""
    documents = normalize(SKILL.read_text())
    assert normalize(CONSTRAINT_CITATIONS[constraint]) in documents, (
        f"constraint {constraint!r} cites a sentence the skill does not state:"
        f" {CONSTRAINT_CITATIONS[constraint]}"
    )


def test_an_existing_fix_pr_is_never_added_to_a_new_stack() -> None:
    """A PR belongs to one stack, so an existing fix PR is only a base branch.

    The stack tooling being available must not turn reuse into a second stack
    membership for the fix PR. Only a newly created fix PR becomes a layer.
    """
    assert error_module.CONSTRAINTS == frozenset(CONSTRAINT_CITATIONS)
    for stack_tooling in (False, True):
        assert (
            lint_case(existing_fix_pr=True, stack_tooling=stack_tooling)
            == BASE_ON_EXISTING_FIX
        ), "an existing fix PR was moved into a new stack"


#: One case per decision the model can return. The coverage test requires the
#: case keys and the cited decisions to be the same set, so a new branch cannot
#: enter the model without a citation and a case.
REACHABLE = {
    "no-ci-failure": (
        ci_case(ci_failing=False, local_gates_pass=True, behind_target=True)
    ),
    "rebase-before-investigation": (
        ci_case(ci_failing=True, local_gates_pass=True, behind_target=True)
    ),
    "investigate": (
        ci_case(ci_failing=True, local_gates_pass=False, behind_target=False)
    ),
    "repair-in-scope": lint_case(newer_suite=False),
    "base-on-existing-fix": lint_case(existing_fix_pr=True),
    "create-fix-and-retarget": lint_case(stack_tooling=False),
    "create-fix-stack-and-retarget": lint_case(stack_tooling=True),
    "temporary-fix-copy": lint_case(
        existing_fix_pr=True, in_managed_stack=True
    ),
    "create-fix-and-rebase-stack": lint_case(in_managed_stack=True),
}


def test_every_reason_is_reachable_and_no_other_reason_is_returned() -> None:
    """Every cited decision has a case, and the cases produce nothing else."""
    assert set(REACHABLE) == set(REASON_CITATIONS)
    assert all(reason == expected for reason, expected in REACHABLE.items())
    assert set(error_module.REASONS) == set(REASON_CITATIONS)


@pytest.mark.parametrize("reason", sorted(REASON_CITATIONS))
def test_dropping_any_single_citation_is_detected(reason: str) -> None:
    """No citation can be deleted without breaking the coverage equality.

    A decision that leaves ``REASON_CITATIONS`` while its case remains in
    ``REACHABLE`` makes the two sets differ, which is what the coverage test
    above checks. This control proves that difference exists for every reason.
    """
    reduced = {
        key: value for key, value in REASON_CITATIONS.items() if key != reason
    }
    assert set(REACHABLE) != set(reduced), (
        f"dropping {reason!r} would leave the reachable decisions unchanged"
    )