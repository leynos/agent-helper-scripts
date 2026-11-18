"""Exercise the documented PR-babysitting error dispositions.

The skill states the rules in prose, so these cases drive the executable
specification with whole facts: the hosted and local gate results, the target's
position, and the fix PR and stack context. It also requires every decision to
cite a sentence the shipped skill still contains, and proves each input is
load-bearing by changing it and observing a different decision.

Which shipped sentences each group guards:

- ``test_model_*`` cases exercise ``pr_babysitting_error_model`` itself, not the
  shipped behaviour. They state what the specification decides for a fact set.
- ``test_each_reason_cites_a_sentence_in_the_skill`` and
  ``test_each_constraint_cites_a_sentence_in_the_skill`` guard the action
  sentence for each decision and constraint in ``SKILL.md``.
- ``test_each_reason_states_its_trigger_conditions`` and
  ``test_dropping_any_trigger_condition_is_detected`` guard the trigger and
  selection clauses: the three rebase conditions, the out-of-scope condition,
  the fix-PR selection rule, and the stack-selection clauses. Dropping or
  inverting one fails the guard.
- ``test_model_ci_disposition_is_exhaustive_over_its_fact_space`` and
  ``test_model_lint_disposition_is_exhaustive_over_its_fact_space`` enumerate
  all 16 CI and 32 lint fact combinations, so the parameterized tables above
  are samples of a space whose every point satisfies the stated rule.
- ``test_rebase_reference_*`` guards the stale-base and prerequisite procedures
  in ``references/rebase.md``, not only their headings.
- ``test_pr_babysitting_examples.py`` runs the reference's fenced Git commands
  against a temporary Git repository and checks the rehearsal rows and
  lifecycle diagram. It does not verify the hosted operations, which are named
  in its own docstrings.
"""

from __future__ import annotations

from itertools import product
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
    PREREQUISITE_FIX,
    REASON_CITATIONS,
    REASON_CONDITIONS,
    REASONS,
    REBASE_FIRST,
    REPAIR_IN_SCOPE,
    TEMPORARY_FIX_COPY,
    ci_failure_disposition,
    lint_violation_disposition,
)
from skill_contract_support import mutate_one_clause, normalize, section


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
REBASE = ROOT / "skills/pr-babysitting/references/rebase.md"


def ci_case(
    *,
    ci_failing: bool,
    local_gates_pass: bool,
    behind_target: bool,
    hosted_out_of_scope_lint: bool = False,
) -> str:
    """Return the CI disposition for one set of observed facts.

    ``hosted_out_of_scope_lint`` defaults to ``False`` so a case that does not
    mention a newer lint suite states that its red failure is an ordinary one.
    """
    return ci_failure_disposition(
        ci_failing=ci_failing,
        local_gates_pass=local_gates_pass,
        behind_target=behind_target,
        hosted_out_of_scope_lint=hosted_out_of_scope_lint,
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
    (
        "ci_failing",
        "local_gates_pass",
        "behind_target",
        "hosted_out_of_scope_lint",
        "expected",
    ),
    [
        (False, True, True, False, NO_CI_FAILURE),
        (False, False, False, False, NO_CI_FAILURE),
        (True, True, True, False, REBASE_FIRST),
        (True, True, False, False, INVESTIGATE),
        (True, False, True, False, INVESTIGATE),
        (True, False, False, False, INVESTIGATE),
        (True, True, False, True, PREREQUISITE_FIX),
        (True, False, True, True, PREREQUISITE_FIX),
        (True, False, False, True, PREREQUISITE_FIX),
    ],
    ids=[
        "green-passing-behind",
        "green-failing-current",
        "stale-base",
        "current-branch",
        "local-failure",
        "local-failure-current",
        "current-branch-out-of-scope-lint",
        "local-failure-out-of-scope-lint",
        "local-failure-current-out-of-scope-lint",
    ],
)
def test_model_ci_disposition_rebases_only_a_stale_base_with_a_local_pass(
    ci_failing: bool,
    local_gates_pass: bool,
    behind_target: bool,
    hosted_out_of_scope_lint: bool,
    expected: str,
) -> None:
    """All three facts are required before a red run is diagnosed through a rebase."""
    assert (
        ci_case(
            ci_failing=ci_failing,
            local_gates_pass=local_gates_pass,
            behind_target=behind_target,
            hosted_out_of_scope_lint=hosted_out_of_scope_lint,
        )
        == expected
    )


def test_model_hosted_out_of_scope_lint_is_prerequisite_work() -> None:
    """A red hosted gate reporting only newer-suite out-of-scope findings never investigates.

    The finding is prerequisite work wherever the failing gate sits, so the
    current-branch case that would otherwise investigate is routed beneath the
    feature instead. The stale-base rule still runs first: a behind-target
    branch is rebased and re-observed whatever the failure reports, and a green
    result needs no routing at all.
    """
    current = {
        "ci_failing": True,
        "local_gates_pass": True,
        "behind_target": False,
    }
    assert ci_case(**current, hosted_out_of_scope_lint=False) == INVESTIGATE
    assert ci_case(**current, hosted_out_of_scope_lint=True) == PREREQUISITE_FIX
    assert (
        ci_case(
            ci_failing=True,
            local_gates_pass=True,
            behind_target=True,
            hosted_out_of_scope_lint=True,
        )
        == REBASE_FIRST
    ), "the stale-base rebase rule must stay ahead of the lint exception"
    assert (
        ci_case(
            ci_failing=False,
            local_gates_pass=True,
            behind_target=True,
            hosted_out_of_scope_lint=True,
        )
        == NO_CI_FAILURE
    ), "a green hosted result needs no routing"


def test_model_ci_conditions_are_load_bearing() -> None:
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
def test_model_lint_disposition_places_out_of_scope_violations_beneath_the_feature(
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


def test_model_lint_conditions_are_load_bearing() -> None:
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


def expected_ci_disposition(
    *,
    ci_failing: bool,
    local_gates_pass: bool,
    behind_target: bool,
    hosted_out_of_scope_lint: bool,
) -> str:
    """State the routing rule independently of the model under test.

    This is a second written statement of the prose, not a call to
    ``ci_failure_disposition``, so the exhaustive test compares two
    calculations instead of the model with itself.
    """
    if not ci_failing:
        return NO_CI_FAILURE
    if local_gates_pass and behind_target:
        return REBASE_FIRST
    if hosted_out_of_scope_lint:
        return PREREQUISITE_FIX
    return INVESTIGATE


def expected_lint_disposition(
    *,
    newer_suite: bool,
    out_of_scope: bool,
    existing_fix_pr: bool,
    in_managed_stack: bool,
    stack_tooling: bool,
) -> str:
    """State the prerequisite rule independently of the model under test."""
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


def test_model_ci_disposition_is_exhaustive_over_its_fact_space() -> None:
    """Enumerate all sixteen CI fact combinations against the stated rule.

    This is a specification-only test: it asserts what the model decides, not
    what the shipped skill does.

    The parameterized cases above sample the space; this covers all of it, so
    no combination of the four facts reaches a disposition the prose does not
    state. ``rebase-before-investigation`` is returned exactly when the run is
    red, the same head passes locally, and the branch is behind its target;
    ``prerequisite-fix`` when a red run reporting only newer-suite, out-of-scope
    findings is not already covered by that rebase rule.
    """
    seen = set()
    for facts in product((False, True), repeat=4):
        (
            ci_failing,
            local_gates_pass,
            behind_target,
            hosted_out_of_scope_lint,
        ) = facts
        expected = expected_ci_disposition(
            ci_failing=ci_failing,
            local_gates_pass=local_gates_pass,
            behind_target=behind_target,
            hosted_out_of_scope_lint=hosted_out_of_scope_lint,
        )
        outcome = ci_failure_disposition(
            ci_failing=ci_failing,
            local_gates_pass=local_gates_pass,
            behind_target=behind_target,
            hosted_out_of_scope_lint=hosted_out_of_scope_lint,
        )
        assert outcome in REASONS, (
            f"unstated CI disposition {outcome!r} for facts {facts}; expected {expected!r}"
        )
        assert outcome == expected, (
            f"CI facts {facts}: expected {expected!r}, got {outcome!r}"
        )
        seen.add(outcome)
    assert seen == {
        NO_CI_FAILURE,
        REBASE_FIRST,
        PREREQUISITE_FIX,
        INVESTIGATE,
    }, f"the CI fact space reached {sorted(seen)}"


def test_model_lint_disposition_is_exhaustive_over_its_fact_space() -> None:
    """Enumerate all 32 lint fact combinations against the stated rule.

    This is a specification-only test: it asserts what the model decides, not
    what the shipped skill does.

    Only a newer suite's out-of-scope finding leaves the feature diff. An
    existing fix PR is never added to a new stack, whatever the stack tooling
    reports, and only an existing stack changes how the fix is applied.
    """
    seen = set()
    for facts in product((False, True), repeat=5):
        (
            newer_suite,
            out_of_scope,
            existing_fix_pr,
            in_managed_stack,
            stack_tooling,
        ) = facts
        expected = expected_lint_disposition(
            newer_suite=newer_suite,
            out_of_scope=out_of_scope,
            existing_fix_pr=existing_fix_pr,
            in_managed_stack=in_managed_stack,
            stack_tooling=stack_tooling,
        )
        outcome = lint_violation_disposition(
            newer_suite=newer_suite,
            out_of_scope=out_of_scope,
            existing_fix_pr=existing_fix_pr,
            in_managed_stack=in_managed_stack,
            stack_tooling=stack_tooling,
        )
        assert outcome in REASONS, (
            f"unstated lint disposition {outcome!r} for facts {facts}; expected {expected!r}"
        )
        assert outcome == expected, (
            f"lint facts {facts}: expected {expected!r}, got {outcome!r}"
        )
        if newer_suite and out_of_scope and existing_fix_pr and not in_managed_stack:
            assert outcome == BASE_ON_EXISTING_FIX, (
                f"an existing fix PR reached {outcome!r} for facts {facts}, expected {BASE_ON_EXISTING_FIX!r}"
            )
        seen.add(outcome)
    assert seen == {
        REPAIR_IN_SCOPE,
        BASE_ON_EXISTING_FIX,
        CREATE_FIX_AND_RETARGET,
        CREATE_FIX_STACK_AND_RETARGET,
        TEMPORARY_FIX_COPY,
        CREATE_FIX_AND_REBASE_STACK,
    }, f"the lint fact space reached {sorted(seen)}"


#: The clauses that choose between an existing stack, a new stack, and a plain
#: prerequisite branch. Each is guarded on its own below, as well as by the
#: generic clause-deletion control.
STACK_SELECTION_CLAUSES = (
    (
        TEMPORARY_FIX_COPY,
        "When this PR is already a layer in a managed stack, apply the fix"
        " underneath the whole stack, not between two layers:",
    ),
    (
        CREATE_FIX_AND_REBASE_STACK,
        "When this PR is already a layer in a managed stack, apply the fix"
        " underneath the whole stack, not between two layers:",
    ),
    (
        CREATE_FIX_AND_RETARGET,
        "A plain prerequisite branch relationship is the fallback when stacks"
        " are unavailable",
    ),
)


@pytest.mark.parametrize(
    ("reason", "clause"),
    STACK_SELECTION_CLAUSES,
    ids=[f"{reason}-stack-selection" for reason, _ in STACK_SELECTION_CLAUSES],
)
def test_each_stack_selection_clause_is_stated_and_load_bearing(
    reason: str, clause: str
) -> None:
    """The stack-selection clause is in the model, the prose, and the guard.

    Deleting the shipped sentence must leave that reason's conditions
    unsatisfied, so the clause cannot be dropped from the skill while the model
    keeps deciding between an existing stack and a new base branch.
    """
    assert clause in REASON_CONDITIONS[reason]
    assert not _missing(SKILL.read_text(), (clause,)), (
        f"reason {reason!r} cites a stack-selection clause the skill does not"
        f" state: {clause}"
    )
    mutated = mutate_one_clause(SKILL.read_text(), clause, "")
    assert clause in _missing(mutated, (clause,)), (
        f"dropping {clause!r} left reason {reason!r} satisfied"
    )


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


def test_model_existing_fix_pr_never_joins_a_new_stack() -> None:
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
    "prerequisite-fix": ci_case(
        ci_failing=True,
        local_gates_pass=True,
        behind_target=False,
        hosted_out_of_scope_lint=True,
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


def test_model_every_reason_is_reachable_and_no_other_reason_is_returned() -> None:
    """Every cited decision has a case, and the cases produce nothing else."""
    assert set(REACHABLE) == set(REASON_CITATIONS)
    assert all(reason == expected for reason, expected in REACHABLE.items())
    assert set(error_module.REASONS) == set(REASON_CITATIONS)


def _missing(document: str, clauses: tuple[str, ...]) -> list[str]:
    """Return the clauses the document no longer states, ignoring wrapping."""
    text = normalize(document)
    return [clause for clause in clauses if normalize(clause) not in text]


def test_every_reason_states_its_trigger_conditions() -> None:
    """Each decision names the clauses that make it apply, in the same set."""
    assert set(REASON_CONDITIONS) == set(REASON_CITATIONS)
    for reason, clauses in REASON_CONDITIONS.items():
        missing = _missing(SKILL.read_text(), clauses)
        assert not missing, f"reason {reason!r} no longer states {missing}"


@pytest.mark.parametrize(
    ("reason", "clause"),
    [
        (reason, clause)
        for reason in sorted(REASON_CONDITIONS)
        for clause in REASON_CONDITIONS[reason]
    ],
    ids=lambda value: value[:40],
)
def test_dropping_any_trigger_condition_is_detected(
    reason: str, clause: str
) -> None:
    """Removing or inverting one trigger clause fails the condition contract."""
    mutated = mutate_one_clause(SKILL.read_text(), clause, "")
    assert clause in _missing(mutated, REASON_CONDITIONS[reason]), (
        f"dropping {clause!r} left reason {reason!r} satisfied"
    )


#: The reasons the CI model decides, as opposed to the lint model. The clause
#: map below uses this to pick the model that owns each reason.
CI_REASONS = frozenset({NO_CI_FAILURE, REBASE_FIRST, PREREQUISITE_FIX, INVESTIGATE})


def _ci_facts(**overrides: bool) -> dict[str, bool]:
    """Return a red hosted fact set with passing local gates on a current branch."""
    facts = {
        "ci_failing": True,
        "local_gates_pass": True,
        "behind_target": False,
        "hosted_out_of_scope_lint": False,
    }
    facts.update(overrides)
    return facts


def _lint_facts(**overrides: bool) -> dict[str, bool]:
    """Return a newer-suite, out-of-scope violation with no fix PR or stack yet."""
    facts = {
        "newer_suite": True,
        "out_of_scope": True,
        "existing_fix_pr": False,
        "in_managed_stack": False,
        "stack_tooling": True,
    }
    facts.update(overrides)
    return facts


def decision_for(reason: str, facts: dict[str, bool]) -> str:
    """Return the decision the model owning ``reason`` makes for ``facts``."""
    if reason in CI_REASONS:
        return ci_case(**facts)
    return lint_case(**facts)


#: For each trigger or selection clause, the facts it guards: the set that
#: satisfies the reason, and the same set with that clause's fact flipped.
#: Clauses are named by their position in ``REASON_CONDITIONS`` so the map
#: cannot drift from the model's own clause list. Each pair differs in exactly
#: one fact, so a changed decision is attributable to the clause under test.
#: The test below asserts both properties, so a clause that survives as
#: decorative prose, or a pair whose changed decision could belong to another
#: fact, fails the suite instead of passing a presence check.
GUARDED_DECISIONS = {
    (NO_CI_FAILURE, 0): (
        _ci_facts(ci_failing=False),
        _ci_facts(),
    ),
    (REBASE_FIRST, 0): (
        _ci_facts(behind_target=True),
        _ci_facts(behind_target=True, ci_failing=False),
    ),
    (REBASE_FIRST, 1): (
        _ci_facts(behind_target=True),
        _ci_facts(behind_target=True, local_gates_pass=False),
    ),
    (REBASE_FIRST, 2): (
        _ci_facts(behind_target=True),
        _ci_facts(behind_target=False),
    ),
    (REBASE_FIRST, 3): (
        _ci_facts(behind_target=True),
        _ci_facts(behind_target=True, local_gates_pass=False),
    ),
    (PREREQUISITE_FIX, 0): (
        _ci_facts(hosted_out_of_scope_lint=True),
        _ci_facts(),
    ),
    (PREREQUISITE_FIX, 1): (
        _ci_facts(hosted_out_of_scope_lint=True),
        _ci_facts(),
    ),
    (INVESTIGATE, 0): (
        _ci_facts(local_gates_pass=False, behind_target=True),
        _ci_facts(local_gates_pass=True, behind_target=True),
    ),
    (REPAIR_IN_SCOPE, 0): (
        _lint_facts(newer_suite=False),
        _lint_facts(newer_suite=True),
    ),
    (REPAIR_IN_SCOPE, 1): (
        _lint_facts(out_of_scope=False),
        _lint_facts(out_of_scope=True),
    ),
    (BASE_ON_EXISTING_FIX, 0): (
        _lint_facts(existing_fix_pr=True),
        _lint_facts(existing_fix_pr=True, newer_suite=False),
    ),
    (BASE_ON_EXISTING_FIX, 1): (
        _lint_facts(existing_fix_pr=True),
        _lint_facts(existing_fix_pr=False),
    ),
    (CREATE_FIX_AND_RETARGET, 0): (
        _lint_facts(stack_tooling=False),
        _lint_facts(stack_tooling=False, newer_suite=False),
    ),
    (CREATE_FIX_AND_RETARGET, 1): (
        _lint_facts(stack_tooling=False),
        _lint_facts(stack_tooling=True),
    ),
    (CREATE_FIX_AND_RETARGET, 2): (
        _lint_facts(stack_tooling=False),
        _lint_facts(stack_tooling=True),
    ),
    (CREATE_FIX_STACK_AND_RETARGET, 0): (
        _lint_facts(),
        _lint_facts(newer_suite=False),
    ),
    (CREATE_FIX_STACK_AND_RETARGET, 1): (
        _lint_facts(),
        _lint_facts(stack_tooling=False),
    ),
    (TEMPORARY_FIX_COPY, 0): (
        _lint_facts(existing_fix_pr=True, in_managed_stack=True),
        _lint_facts(existing_fix_pr=False, in_managed_stack=True),
    ),
    (TEMPORARY_FIX_COPY, 1): (
        _lint_facts(existing_fix_pr=True, in_managed_stack=True),
        _lint_facts(existing_fix_pr=True, in_managed_stack=False),
    ),
    (TEMPORARY_FIX_COPY, 2): (
        _lint_facts(existing_fix_pr=True, in_managed_stack=True),
        _lint_facts(existing_fix_pr=False, in_managed_stack=True),
    ),
    (CREATE_FIX_AND_REBASE_STACK, 0): (
        _lint_facts(in_managed_stack=True),
        _lint_facts(existing_fix_pr=True, in_managed_stack=True),
    ),
    (CREATE_FIX_AND_REBASE_STACK, 1): (
        _lint_facts(in_managed_stack=True),
        _lint_facts(in_managed_stack=False),
    ),
}


def test_each_trigger_clause_guards_a_model_decision() -> None:
    """Flipping the fact a clause names changes the decision it states.

    The presence check in ``test_dropping_any_trigger_condition_is_detected``
    only proves the sentence exists. This test binds each clause to the fact it
    guards, so a clause whose fact no longer affects the model is reported as
    decorative. Each pair must also differ in exactly one fact: a pair that
    flips two facts cannot say which one moved the decision, and the clause
    would pass on the other fact's strength. These are specification-only
    cases: they constrain the model, not the shipped skill's behaviour.
    """
    expected = {
        (reason, index)
        for reason, clauses in REASON_CONDITIONS.items()
        for index in range(len(clauses))
    }
    assert set(GUARDED_DECISIONS) == expected, (
        "the guarded-fact map must cover every trigger clause exactly once"
    )
    for (reason, index), (baseline, flipped) in GUARDED_DECISIONS.items():
        clause = REASON_CONDITIONS[reason][index]
        differing = [fact for fact in baseline if baseline[fact] != flipped[fact]]
        assert len(differing) == 1, (
            f"{clause!r} must flip exactly one fact, but flips {differing}"
        )
        baseline_decision = decision_for(reason, baseline)
        flipped_decision = decision_for(reason, flipped)
        assert baseline_decision == reason, (
            f"baseline for {clause!r} reached {baseline_decision!r}, not {reason!r}"
        )
        assert flipped_decision != reason, (
            f"{clause!r} is decorative: flipping its fact still reached"
            f" {reason!r}"
        )


def test_reference_states_replay_and_stack_steps_in_order() -> None:
    """The reference orders the prerequisite, replay, validation, and stack steps.

    Independent substring checks would accept the same sentences in any order.
    The staged replay is only correct if the fix PR is found or created before
    the feature is replayed, and if each replayed layer is validated before the
    next one is replayed and before the old stack's merged, merging, or queued
    PRs are reconciled.
    """
    body = section(REBASE.read_text(), "Retarget onto a prerequisite fix branch")
    ordered = (
        "look for an open fix PR",
        "create one that fixes exactly those violations",
        'git rebase --onto "$FIX_BRANCH"',
        "Replay every layer's own commits onto the copy bottom to top",
        'git rebase --onto "$COPY_BRANCH"',
        "Replay the next layer only after that validation",
        'git rebase --onto "$BOTTOM_LAYER"',
        "`gh stack unstack` cannot remove merged, merging, or queued PRs",
        "Reconcile those states before recreating",
    )
    positions = [body.index(step) for step in ordered]
    assert positions == sorted(positions), (
        f"the documented steps are out of order: {ordered}"
    )


def test_rebase_reference_withholds_logs_until_the_rebased_candidate_reports() -> None:
    """The stale-base procedure states the trigger, the action, and the re-observation."""
    body = section(REBASE.read_text(), "Diagnose a stale base before reading logs")
    assert (
        "When the same repository commit gates pass locally for the current head"
        " and the live target contains commits the branch does not, freeze and"
        " replay onto that target before reading or acting on the scrutineer's"
        " captured failure logs or failure summary" in body
    )
    assert "Re-observe the rebased candidate's CI before investigating." in body
    assert (
        "When local gates also fail, or the branch already contains the target"
        " head, continue with normal failure diagnosis." in body
    )


def test_rebase_reference_retargets_and_restacks_onto_the_prerequisite() -> None:
    """The prerequisite procedure states the scope boundary, fork handling, and stack replay."""
    body = section(REBASE.read_text(), "Retarget onto a prerequisite fix branch")
    required = (
        "A violation the candidate's accepted scope covers stays in this PR's diff.",
        "classify it before"
        " routing the failed gate to investigation",
        "base this PR on a temporary branch in the base repository created at that"
        " head",
        "a PR can belong to only one stack, so reuse that PR as a plain base branch"
        " instead",
        "Replay every layer's own commits onto the copy bottom to top",
        "validate each replayed layer before it joins the new stack",
        "`gh stack unstack` cannot remove merged, merging, or queued PRs",
        "Reconcile those states before recreating",
    )
    missing = _missing(body, required)
    assert not missing, f"prerequisite procedure no longer states {missing}"