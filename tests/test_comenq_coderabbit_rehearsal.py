"""Offline rehearsal cases for the comenq-coderabbit workflow.

The skill documents 17 rehearsal scenarios and a set of dispositions. This
module holds both to a contract:

- Every scenario in the evidence reference must keep the claims that make it
  a semantic acceptance check rather than a numbered heading.
- The recorded rehearsal cases must produce the documented disposition, and
  the decision model is an executable specification — not behavioural
  coverage of the workflow. The installer boundary is exercised separately in
  `test_comenq_coderabbit_install.py`.
"""

from __future__ import annotations

import re

import pytest

from comenq_coderabbit_contract_data import (
    REHEARSAL_SCENARIO_COUNT,
    REHEARSAL_SCENARIOS,
    ScenarioContract,
)
from comenq_coderabbit_decisions import (
    CANDIDATE_STALE,
    INSPECTION_INCOMPLETE,
    INTEGRATION_FAILED,
    MERGE_ELIGIBLE,
    REHEARSALS,
    REHEARSAL_CASE_COUNT,
    VERDICT_CITATIONS,
    Rehearsal,
    classify,
    observation,
)
from comenq_coderabbit_support import (
    EVIDENCE_PATH,
    SCENARIO_BLOCK_RE,
    SCENARIO_RE,
    SKILL_PATH,
    normalize,
    read,
    without,
)


def scenario_blocks(evidence: str) -> dict[int, str]:
    """Return each numbered rehearsal scenario's text, keyed by its number.

    Parameters
    ----------
    evidence : str
        Contents of the evidence-and-rehearsal reference.

    Returns
    -------
    dict
        Scenario number mapped to that scenario's title and body.
    """
    return {
        int(match.group("number")): f"{match.group('title')}{match.group('body')}"
        for match in SCENARIO_BLOCK_RE.finditer(evidence)
    }


def validate_scenario_semantics(evidence: str, scenario: ScenarioContract) -> None:
    """Require one scenario to keep every claim its contract states.

    Parameters
    ----------
    evidence : str
        Contents of the evidence-and-rehearsal reference.
    scenario : ScenarioContract
        The scenario and the claims it must state.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when the scenario or one of its claims is missing.
    """
    blocks = scenario_blocks(evidence)
    assert scenario.number in blocks, (
        f"the evidence reference must keep scenario {scenario.number} "
        f"({scenario.title!r})"
    )
    text = normalize(blocks[scenario.number])
    for phrase in scenario.required:
        assert normalize(phrase) in text, (
            f"scenario {scenario.number} ({scenario.title!r}) must keep stating "
            f"{phrase!r}; it currently reads: {text!r}"
        )


def test_scenario_contract_covers_every_documented_scenario() -> None:
    """The semantic contract must cover each numbered scenario exactly once."""
    documented = [int(number) for number in SCENARIO_RE.findall(read(EVIDENCE_PATH))]
    covered = [scenario.number for scenario in REHEARSAL_SCENARIOS]

    assert len(documented) == REHEARSAL_SCENARIO_COUNT, (
        f"the evidence reference must document {REHEARSAL_SCENARIO_COUNT} "
        f"scenarios, found {len(documented)}"
    )
    assert covered == documented, (
        "the semantic scenario contract must cover every documented scenario in "
        f"order, documented={documented}, covered={covered}"
    )


@pytest.mark.parametrize(
    "scenario",
    REHEARSAL_SCENARIOS,
    ids=[f"scenario-{scenario.number}" for scenario in REHEARSAL_SCENARIOS],
)
def test_every_rehearsal_scenario_states_its_semantics(
    scenario: ScenarioContract,
) -> None:
    """Each documented scenario must keep the claims that make it a check."""
    validate_scenario_semantics(read(EVIDENCE_PATH), scenario)


def test_scenario_contract_rejects_missing_semantics() -> None:
    """Removing a scenario's stated claim must fail the semantic contract."""
    scenario = REHEARSAL_SCENARIOS[2]
    phrase = scenario.required[0]
    evidence = without(read(EVIDENCE_PATH), phrase)

    with pytest.raises(AssertionError, match=re.escape(phrase)):
        validate_scenario_semantics(evidence, scenario)


@pytest.mark.parametrize(
    "rehearsal",
    REHEARSALS,
    ids=[rehearsal.description for rehearsal in REHEARSALS],
)
def test_documented_decisions_for_rehearsal_cases(rehearsal: Rehearsal) -> None:
    """Each recorded rehearsal case produces its documented disposition."""
    actual = classify(rehearsal.observation)

    assert actual == rehearsal.expected, (
        f"the {rehearsal.description!r} case must classify as "
        f"{rehearsal.expected!r}, but the documented guard order returned "
        f"{actual!r} for {rehearsal.observation!r}"
    )


def test_every_classification_cites_a_rule_the_skill_states() -> None:
    """No classification may outlive the skill sentence that grounds it."""
    normalized_skill = normalize(read(SKILL_PATH))
    for verdict, citation in VERDICT_CITATIONS.items():
        assert normalize(citation) in normalized_skill, (
            f"the {verdict} classification must stay grounded in the skill: "
            f"`{citation}`"
        )


def test_rehearsal_fixtures_reference_documented_scenarios() -> None:
    """Every fixture that names a scenario must name a documented one."""
    documented = {int(number) for number in SCENARIO_RE.findall(read(EVIDENCE_PATH))}
    used = {
        rehearsal.scenario
        for rehearsal in REHEARSALS
        if rehearsal.scenario is not None
    }
    assert used, "at least one fixture must be tied to a documented scenario"
    assert used <= documented, (
        f"fixtures must reference documented scenarios, unknown: "
        f"{sorted(used - documented)}"
    )


def test_every_recorded_rehearsal_case_is_retained() -> None:
    """Dropping a recorded rehearsal case must fail rather than shrink coverage."""
    assert len(REHEARSALS) == REHEARSAL_CASE_COUNT, (
        f"the rehearsal table must keep its {REHEARSAL_CASE_COUNT} recorded "
        f"cases, found {len(REHEARSALS)}"
    )


def test_clone_failure_cannot_be_reported_as_a_clean_review() -> None:
    """Incomplete coverage must never classify as merge eligible."""
    observation_state = observation(
        coverage_complete=False, review_decision="REVIEW_REQUIRED"
    )
    actual = classify(observation_state)

    assert actual != MERGE_ELIGIBLE, (
        "a clone failure with no findings must never be reported as "
        f"{MERGE_ELIGIBLE!r}, but the guard order returned {actual!r} for "
        f"{observation_state!r}"
    )
    assert actual == INSPECTION_INCOMPLETE, (
        f"an incomplete inspection must classify as {INSPECTION_INCOMPLETE!r}, "
        f"but the guard order returned {actual!r} for {observation_state!r}"
    )


def test_approval_on_a_superseded_candidate_is_not_merge_eligible() -> None:
    """An approval inspected an earlier candidate, so eligibility is stale."""
    observation_state = observation(inspected="old1", head="new1")
    actual = classify(observation_state)

    assert actual == CANDIDATE_STALE, (
        f"an approval recorded against an earlier commit must classify as "
        f"{CANDIDATE_STALE!r} rather than {MERGE_ELIGIBLE!r}, but the guard "
        f"order returned {actual!r} for {observation_state!r}"
    )


def test_green_pull_request_does_not_discharge_a_failing_integration_job() -> None:
    """Integration state is checked before any pull-request convergence."""
    observation_state = observation(integration="failed")
    actual = classify(observation_state)

    assert actual == INTEGRATION_FAILED, (
        f"a failing post-merge job must be reported as {INTEGRATION_FAILED!r} "
        f"even when the pull request converged, but the guard order returned "
        f"{actual!r} for {observation_state!r}"
    )
