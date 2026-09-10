"""Exercise the planner's replay policy as a domain, with no repository at all.

Nothing here builds a Git repository, runs `gh`, or mocks a subprocess. The
boundary and range policy consume typed graph facts, so their whole decision
table is reachable from plain values. A test in this module that needed a
process double would mean discovery had leaked back into the domain layer.
"""

from __future__ import annotations

import dataclasses

import pytest
from rebase_test_support import planner

PARENT = planner.ParentPullRequest("leynos/agent-helper-scripts", 50)
PARENT_HEAD = planner.CommitId("a" * 40)
OLD_HEAD = planner.CommitId("b" * 40)
RECEIPT_COMMIT = planner.CommitId("c" * 40)
OTHER = planner.CommitId("d" * 40)


def _facts(**overrides: object) -> planner.BoundaryFacts:
    """Build boundary facts for an inherited parent head, then apply overrides."""
    values: dict[str, object] = {
        "parent_head": PARENT_HEAD,
        "old_head": OLD_HEAD,
        "parent_head_inherited": True,
        "merge_base_candidates": (),
        "receipt": None,
    }
    values.update(overrides)
    return planner.BoundaryFacts(**values)


def _receipt(**overrides: object) -> planner.ReceiptFacts:
    """Build a valid receipt naming PARENT, then apply overrides."""
    values: dict[str, object] = {
        "ref": "refs/stack-bases/child",
        "commit": RECEIPT_COMMIT,
        "stack_parent": str(PARENT),
        "is_ancestor_of_child": True,
    }
    values.update(overrides)
    return planner.ReceiptFacts(**values)


def test_parent_pull_request_renders_and_matches_its_receipt_identity() -> None:
    """The parent identity round-trips through the receipt config value."""
    assert str(PARENT) == "leynos/agent-helper-scripts#50"
    assert PARENT.matches_receipt_identity("leynos/agent-helper-scripts#50")
    assert PARENT.matches_receipt_identity("LEYNOS/Agent-Helper-Scripts#50"), (
        "a recorded identity must match irrespective of case"
    )
    assert not PARENT.matches_receipt_identity(""), (
        "an unset stackParent must never satisfy the receipt contract"
    )
    assert not PARENT.matches_receipt_identity("leynos/agent-helper-scripts#51")


def test_inherited_parent_head_is_the_corroborated_boundary() -> None:
    """An inherited parent head is itself the boundary, and it is corroborated."""
    boundary = planner.select_boundary(PARENT, _facts())
    assert boundary == planner.Boundary(PARENT_HEAD, "parent-pr-head", True)


def test_noninherited_parent_without_receipt_refuses_and_names_candidates() -> None:
    """Merge-base candidates are reported as non-proof, never chosen."""
    facts = _facts(
        parent_head_inherited=False, merge_base_candidates=(RECEIPT_COMMIT, OTHER)
    )
    with pytest.raises(planner.PlanError) as excinfo:
        planner.select_boundary(PARENT, facts)
    assert excinfo.value.category == planner.CATEGORY_BOUNDARY
    assert RECEIPT_COMMIT in str(excinfo.value), (
        "the refusal must name the candidates it declined to choose between"
    )
    assert "not proof" in str(excinfo.value)


def test_receipt_on_noninherited_history_is_accepted_but_uncorroborated() -> None:
    """The documented recovery path stays open, and says it cannot be proven."""
    facts = _facts(parent_head_inherited=False, receipt=_receipt())
    boundary = planner.select_boundary(PARENT, facts)
    assert boundary.old_base == RECEIPT_COMMIT
    assert boundary.evidence == "maintained-receipt:refs/stack-bases/child"
    assert boundary.corroborated is False, (
        "no inherited history means nothing proves the receipt is the last one"
    )
    assert planner.review_notes(boundary)[0].startswith("The receipt is uncorroborated")


def test_receipt_agreeing_with_inherited_parent_head_is_corroborated() -> None:
    """A receipt that matches inherited history inherits its corroboration."""
    facts = _facts(receipt=_receipt(commit=PARENT_HEAD))
    boundary = planner.select_boundary(PARENT, facts)
    assert boundary.old_base == PARENT_HEAD
    assert boundary.corroborated is True
    assert planner.review_notes(boundary)[0].startswith("Confirm the parent"), (
        "a corroborated boundary must not carry the uncorroborated warning"
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"stack_parent": ""}, "matching branch stackParent"),
        ({"stack_parent": "leynos/agent-helper-scripts#51"}, "stackParent"),
        ({"stack_parent": "other/repo#50"}, "stackParent"),
        ({"is_ancestor_of_child": False}, "not an ancestor of the child"),
    ],
)
def test_receipt_failing_its_contract_is_refused(
    overrides: dict[str, object], reason: str
) -> None:
    """A receipt must name this parent and lie in the child's own history."""
    facts = _facts(parent_head_inherited=False, receipt=_receipt(**overrides))
    with pytest.raises(planner.PlanError, match=reason) as excinfo:
        planner.select_boundary(PARENT, facts)
    assert excinfo.value.category == planner.CATEGORY_BOUNDARY


def test_receipt_disagreeing_with_inherited_parent_head_is_refused() -> None:
    """When history is inherited, only the parent head may be the boundary."""
    facts = _facts(receipt=_receipt(commit=OTHER))
    with pytest.raises(planner.PlanError, match="disagrees with the inherited parent"):
        planner.select_boundary(PARENT, facts)


@pytest.mark.parametrize("ref", ["refs/heads/child", "refs/tags/v1", "child", ""])
def test_boundary_ref_outside_the_receipt_namespace_is_refused(ref: str) -> None:
    """Only a maintained refs/stack-bases/ receipt may name a boundary."""
    with pytest.raises(planner.PlanError, match="refs/stack-bases/") as excinfo:
        planner.check_receipt_ref(ref)
    assert excinfo.value.category == planner.CATEGORY_BOUNDARY


def test_check_receipt_ref_accepts_the_maintained_namespace() -> None:
    """A receipt under the maintained namespace passes the namespace check."""
    assert planner.check_receipt_ref("refs/stack-bases/child") is None


@pytest.mark.parametrize(
    ("parent_repository", "branch", "reason"),
    [
        ("noslash", "child", "owner/name"),
        ("../escape/repo", "child", "owner/name"),
        ("owner/..", "child", "owner/name"),
        ("owner/name", "", "explicit local branch name"),
        ("owner/name", "--upload-pack=evil", "not an option"),
    ],
)
def test_malformed_identities_are_refused_without_a_repository(
    parent_repository: str, branch: str, reason: str
) -> None:
    """Identity validation is pure, so it needs no repository to refuse."""
    parent = planner.ParentPullRequest(parent_repository, 50)
    with pytest.raises(planner.PlanError, match=reason) as excinfo:
        planner.check_identities(parent, branch)
    assert excinfo.value.category == planner.CATEGORY_IDENTITY


@pytest.mark.parametrize("number", [0, -1, True])
def test_non_positive_or_non_integer_pr_numbers_are_refused(number: object) -> None:
    """A PR number must be a positive int; bool is not an acceptable int here."""
    parent = planner.ParentPullRequest("owner/name", number)  # type: ignore[arg-type]
    with pytest.raises(planner.PlanError, match="positive integer"):
        planner.check_identities(parent, "child")


def test_range_containing_a_merge_is_refused() -> None:
    """A merge in the range means the ordered replay assumption does not hold."""
    facts = planner.RangeFacts(PARENT_HEAD, OLD_HEAD, (RECEIPT_COMMIT,), True)
    with pytest.raises(planner.PlanError, match="contains merges") as excinfo:
        planner.check_range(facts)
    assert excinfo.value.category == planner.CATEGORY_RANGE


@pytest.mark.parametrize("commits", [(), (RECEIPT_COMMIT,), (RECEIPT_COMMIT, OTHER)])
def test_linear_range_is_accepted_unchanged(
    commits: tuple[planner.CommitId, ...],
) -> None:
    """A linear range is returned exactly as gathered, including when empty."""
    facts = planner.RangeFacts(PARENT_HEAD, OLD_HEAD, commits, False)
    assert planner.check_range(facts) == commits


def _evidence() -> planner.Evidence:
    """Build a frozen snapshot for the identity-recheck policy."""
    return planner.Evidence(
        operation="domain",
        parent=PARENT,
        old_head=OLD_HEAD,
        target=OTHER,
        parent_evidence=planner.ParentEvidence(PARENT_HEAD, OTHER, "refs/x"),
    )


def test_unmoved_identities_are_accepted() -> None:
    """Identities that match the snapshot raise nothing."""
    assert (
        planner.check_unmoved(_evidence(), planner.Identities(OLD_HEAD, OTHER)) is None
    )


@pytest.mark.parametrize(
    ("current", "reason"),
    [
        (planner.Identities(RECEIPT_COMMIT, OTHER), "Child branch moved"),
        (planner.Identities(OLD_HEAD, RECEIPT_COMMIT), "Target ref moved"),
    ],
)
def test_moved_identities_are_refused_as_a_race(
    current: planner.Identities, reason: str
) -> None:
    """A branch or target that moved during discovery invalidates the plan."""
    with pytest.raises(planner.PlanError, match=reason) as excinfo:
        planner.check_unmoved(_evidence(), current)
    assert excinfo.value.category == planner.CATEGORY_RACE


def test_rendered_plan_reports_review_required_and_the_proposed_argv() -> None:
    """A non-empty range renders a review-required plan with an explicit argv."""
    boundary = planner.Boundary(PARENT_HEAD, "parent-pr-head", True)
    plan = planner.render_plan("child", _evidence(), boundary, (RECEIPT_COMMIT,))
    assert plan["status"] == planner.STATUS_REVIEW_REQUIRED
    assert plan["boundary_corroborated"] is True
    assert plan["parent_pr"] == "leynos/agent-helper-scripts#50"
    assert plan["rebase_argv"][-3:] == [OTHER, PARENT_HEAD, "child"]
    assert plan["rebase_argv"][: len(planner.REBASE_PREFIX)] == list(
        planner.REBASE_PREFIX
    )


def test_rendered_plan_reports_a_no_op_decision_for_an_empty_range() -> None:
    """An empty range is a decision for the operator, never a silent success."""
    boundary = planner.Boundary(PARENT_HEAD, "parent-pr-head", True)
    plan = planner.render_plan("child", _evidence(), boundary, ())
    assert plan["status"] == planner.STATUS_NO_OP
    assert plan["commits"] == []
    assert plan["rebase_argv"] is None


def test_rendered_plan_never_claims_authorization() -> None:
    """Neither successful status is an authorization; both demand review."""
    boundary = planner.Boundary(RECEIPT_COMMIT, "maintained-receipt:refs/x", False)
    plan = planner.render_plan("child", _evidence(), boundary, (OTHER,))
    assert plan["status"] in {planner.STATUS_REVIEW_REQUIRED, planner.STATUS_NO_OP}
    assert plan["boundary_corroborated"] is False
    assert plan["review"][0].startswith("The receipt is uncorroborated"), (
        "an uncorroborated boundary must stay review-blocking in the rendered plan"
    )


@pytest.mark.parametrize(
    ("value", "field"),
    [
        (_evidence(), "old_head"),
        (planner.Boundary(PARENT_HEAD, "parent-pr-head", True), "corroborated"),
        (_facts(), "parent_head_inherited"),
        (_receipt(), "stack_parent"),
        (planner.ParentEvidence(PARENT_HEAD, OTHER, "refs/x"), "head"),
        (planner.ErrorContext("op", planner.PHASE_PREFLIGHT), "phase"),
    ],
)
def test_domain_values_are_immutable(value: object, field: str) -> None:
    """Evidence a plan was derived from cannot be edited after the fact."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, field, "mutated")
