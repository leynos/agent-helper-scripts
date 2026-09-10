"""Executable specification of the documented comenq-coderabbit dispositions.

This module is not product code and not behavioural coverage. It restates the
dispositions the skill documents as a small decision model, so the contract
tests can name each documented outcome once, cite the skill sentence that
states it, and keep the guard precedence in a single ordered place.

Nothing here touches a queue, a GitHub surface, or a reviewer. The install
boundary is covered separately, by executing the installer's copy step.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from comenq_coderabbit_contract_data import REQUIRED_SKILL_RULES

INSPECTION_INCOMPLETE = "inspection-incomplete"
RETRIEVAL_INCOMPLETE = "surface-retrieval-incomplete"
CANDIDATE_STALE = "candidate-stale"
DUPLICATE_REQUEST = "duplicate-request"
DISPOSITIONS_PENDING = "dispositions-pending"
REVIEW_STATE_UNRESOLVED = "review-state-unresolved"
CHECKS_NOT_GREEN = "checks-not-green"
MERGE_ELIGIBLE = "merge-eligible"
INTEGRATION_FAILED = "integration-failed"

#: The sentence in the skill that states each documented disposition. The
#: contract tests assert these are present, so a classification cannot
#: outlive the rule it applies.
VERDICT_CITATIONS = {
    INSPECTION_INCOMPLETE: REQUIRED_SKILL_RULES["incomplete inspection"],
    RETRIEVAL_INCOMPLETE: (
        "An absent reply in a partial page is not proof of an unanswered thread."
    ),
    CANDIDATE_STALE: REQUIRED_SKILL_RULES["stale candidate handling"],
    DUPLICATE_REQUEST: "Reuse an existing request rather than adding another.",
    DISPOSITIONS_PENDING: (
        "Treat both warning and error rows as requiring an explicit disposition"
    ),
    REVIEW_STATE_UNRESOLVED: REQUIRED_SKILL_RULES["review-state separation"],
    CHECKS_NOT_GREEN: "green required checks on the intended head",
    MERGE_ELIGIBLE: REQUIRED_SKILL_RULES["convergence"],
    INTEGRATION_FAILED: REQUIRED_SKILL_RULES["separate integration verification"],
}


@dataclass(frozen=True)
class ReviewObservation:
    """Observed review facts for one candidate, named after the skill surfaces."""

    head: str
    inspected: str | None
    coverage_complete: bool
    retrieval_complete: bool
    request_state: str
    review_activity: bool
    unresolved_threads: int
    undispositioned_rows: int
    review_decision: str
    required_checks_green: bool
    integration: str | None


@dataclass(frozen=True)
class Rehearsal:
    """One documented rehearsal case and the disposition it must produce."""

    scenario: int | None
    description: str
    observation: ReviewObservation
    expected: str


def observation(
    *,
    head: str = "head1",
    inspected: str | None = "head1",
    coverage_complete: bool = True,
    retrieval_complete: bool = True,
    request_state: str = "posted",
    review_activity: bool = True,
    unresolved_threads: int = 0,
    undispositioned_rows: int = 0,
    review_decision: str = "APPROVED",
    required_checks_green: bool = True,
    integration: str | None = None,
) -> ReviewObservation:
    """Return a fully converged review state with selected facts overridden.

    Parameters
    ----------
    head : str, optional
        Current head commit of the candidate.
    inspected : str or None, optional
        Commit the review actually inspected, or None when unknown.
    coverage_complete : bool, optional
        Whether required inspection coverage is complete.
    retrieval_complete : bool, optional
        Whether every review surface was paginated to completion.
    request_state : str, optional
        Queue request state, such as `posted`, `pending`, or `failed`.
    review_activity : bool, optional
        Whether review activity already exists for the candidate.
    unresolved_threads : int, optional
        Count of unresolved review threads.
    undispositioned_rows : int, optional
        Count of pre-merge rows lacking a disposition.
    review_decision : str, optional
        Current review decision, such as `APPROVED` or `CHANGES_REQUESTED`.
    required_checks_green : bool, optional
        Whether every required check on the intended head is green.
    integration : str or None, optional
        Post-merge integration outcome, or None when not yet known.

    Returns
    -------
    ReviewObservation
        The assembled observation.
    """
    return ReviewObservation(
        head=head,
        inspected=inspected,
        coverage_complete=coverage_complete,
        retrieval_complete=retrieval_complete,
        request_state=request_state,
        review_activity=review_activity,
        unresolved_threads=unresolved_threads,
        undispositioned_rows=undispositioned_rows,
        review_decision=review_decision,
        required_checks_green=required_checks_green,
        integration=integration,
    )


Predicate = Callable[[ReviewObservation], bool]


def integration_failed(observation: ReviewObservation) -> bool:
    """Return whether the post-merge integration job failed.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when integration recorded a failure.
    """
    return observation.integration == "failed"


def coverage_incomplete(observation: ReviewObservation) -> bool:
    """Return whether required inspection coverage is missing or unknown.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when the candidate lacks complete required coverage.
    """
    return not observation.coverage_complete


def retrieval_incomplete(observation: ReviewObservation) -> bool:
    """Return whether the review surfaces were only partially retrieved.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when at least one surface was not paginated to completion.
    """
    return not observation.retrieval_complete


def candidate_stale(observation: ReviewObservation) -> bool:
    """Return whether the inspected commit differs from the current head.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when a commit was inspected and it is not the current head. An
        unknown inspected commit is not evidence of a changed candidate.
    """
    return (
        observation.inspected is not None and observation.inspected != observation.head
    )


def duplicate_request(observation: ReviewObservation) -> bool:
    """Return whether a pending request repeats existing review activity.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when the queue already holds a pending request for a candidate
        that has review activity.
    """
    return observation.request_state == "pending" and observation.review_activity


def dispositions_pending(observation: ReviewObservation) -> bool:
    """Return whether any thread or pre-merge row lacks a disposition.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when at least one unresolved thread or undispositioned row
        remains.
    """
    return bool(observation.unresolved_threads or observation.undispositioned_rows)


def review_state_unresolved(observation: ReviewObservation) -> bool:
    """Return whether the current review decision is not an approval.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when the review decision is anything other than `APPROVED`.
    """
    return observation.review_decision != "APPROVED"


def checks_not_green(observation: ReviewObservation) -> bool:
    """Return whether a required check on the intended head is not green.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts.

    Returns
    -------
    bool
        True when at least one required check is not green.
    """
    return not observation.required_checks_green


#: The documented guard order. Each entry pairs a blocking predicate with the
#: disposition it produces; the first matching predicate wins, and a state
#: that clears every guard is merge eligible.
GUARD_PRECEDENCE: tuple[tuple[Predicate, str], ...] = (
    (integration_failed, INTEGRATION_FAILED),
    (coverage_incomplete, INSPECTION_INCOMPLETE),
    (retrieval_incomplete, RETRIEVAL_INCOMPLETE),
    (candidate_stale, CANDIDATE_STALE),
    (duplicate_request, DUPLICATE_REQUEST),
    (dispositions_pending, DISPOSITIONS_PENDING),
    (review_state_unresolved, REVIEW_STATE_UNRESOLVED),
    (checks_not_green, CHECKS_NOT_GREEN),
)


def classify(observation: ReviewObservation) -> str:
    """Return the documented disposition for one observed review state.

    Parameters
    ----------
    observation : ReviewObservation
        Observed review facts for one candidate: the current head and the
        inspected commit, coverage and retrieval completeness, queue request
        state, existing review activity, unresolved thread and
        undispositioned row counts, the current review decision, required
        check results, and the post-merge integration outcome.

    Returns
    -------
    str
        The documented disposition constant for the first blocking guard that
        the observation trips, or `MERGE_ELIGIBLE` when it clears every guard.

    Notes
    -----
    Order matters and follows the skill: integration is verified separately
    from the pull request, an incomplete inspection can never be a clean
    review, a changed candidate invalidates earlier eligibility before any
    duplicate or disposition question is answered, and a pending request is
    redundant only once the current candidate's inspection is complete.
    """
    for blocked_when, disposition in GUARD_PRECEDENCE:
        if blocked_when(observation):
            return disposition
    return MERGE_ELIGIBLE


#: The recorded rehearsal cases the offline contract exercises by name. The
#: count is pinned by a test so a case cannot be dropped unnoticed.
REHEARSAL_CASE_COUNT = 10


REHEARSALS = (
    Rehearsal(
        scenario=1,
        description="clone failed with no findings is incomplete inspection",
        observation=observation(
            coverage_complete=False, review_decision="REVIEW_REQUIRED"
        ),
        expected=INSPECTION_INCOMPLETE,
    ),
    Rehearsal(
        scenario=None,
        description="a completed review on the current candidate converges",
        observation=observation(),
        expected=MERGE_ELIGIBLE,
    ),
    Rehearsal(
        scenario=2,
        description=(
            "approval with unknown or incomplete required coverage blocks merge"
        ),
        observation=observation(
            coverage_complete=False, review_decision="APPROVED"
        ),
        expected=INSPECTION_INCOMPLETE,
    ),
    Rehearsal(
        scenario=3,
        description="a pending request is redundant beside completed activity",
        observation=observation(request_state="pending", review_activity=True),
        expected=DUPLICATE_REQUEST,
    ),
    Rehearsal(
        scenario=5,
        description="four rows for two defects stay undispositioned work",
        observation=observation(undispositioned_rows=4),
        expected=DISPOSITIONS_PENDING,
    ),
    Rehearsal(
        scenario=8,
        description="resolved threads do not clear stale CHANGES_REQUESTED",
        observation=observation(review_decision="CHANGES_REQUESTED"),
        expected=REVIEW_STATE_UNRESOLVED,
    ),
    Rehearsal(
        scenario=9,
        description="a replayed candidate invalidates earlier eligibility",
        observation=observation(inspected="old1", head="new1"),
        expected=CANDIDATE_STALE,
    ),
    Rehearsal(
        scenario=10,
        description="a capped inner comment page is incomplete retrieval",
        observation=observation(retrieval_complete=False),
        expected=RETRIEVAL_INCOMPLETE,
    ),
    Rehearsal(
        scenario=12,
        description="a green pull request cannot discharge a failing main job",
        observation=observation(integration="failed"),
        expected=INTEGRATION_FAILED,
    ),
    Rehearsal(
        scenario=None,
        description="required checks on the intended head gate merge eligibility",
        observation=observation(required_checks_green=False),
        expected=CHECKS_NOT_GREEN,
    ),
)
