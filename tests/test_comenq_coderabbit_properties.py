"""Property-based checks for the comenq-coderabbit decision invariant.

`classify` orders eight documented guards over eleven observed fields. The
rehearsal cases in `test_comenq_coderabbit_rehearsal.py` stay the readable
examples; this module generates review states instead, so the invariant is
checked across combinations no handwritten table enumerates.

Each property restates one documented rule rather than the model's mechanics:
every state classifies as one documented disposition, a required blocker
prevents merge eligibility, a failing integration job is reported independently
of the pull request, an unknown inspected commit is not evidence of a stale
candidate, and the guard precedence keeps the order the skill documents.
"""

from __future__ import annotations

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from comenq_coderabbit_decisions import (
    CANDIDATE_STALE,
    CHECKS_NOT_GREEN,
    DISPOSITIONS_PENDING,
    DUPLICATE_REQUEST,
    GUARD_PRECEDENCE,
    INSPECTION_INCOMPLETE,
    INTEGRATION_FAILED,
    MERGE_ELIGIBLE,
    RETRIEVAL_INCOMPLETE,
    REVIEW_STATE_UNRESOLVED,
    ReviewObservation,
    classify,
)

#: The guard order the skill documents, restated as disposition constants.
#: Pinning it here means a reordering of the model's table fails a test rather
#: than silently changing which blocker a state reports.
DOCUMENTED_GUARD_ORDER = (
    INTEGRATION_FAILED,
    INSPECTION_INCOMPLETE,
    RETRIEVAL_INCOMPLETE,
    CANDIDATE_STALE,
    DUPLICATE_REQUEST,
    DISPOSITIONS_PENDING,
    REVIEW_STATE_UNRESOLVED,
    CHECKS_NOT_GREEN,
)

DOCUMENTED_DISPOSITIONS = (*DOCUMENTED_GUARD_ORDER, MERGE_ELIGIBLE)

HEADS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12
)
COUNTS = st.integers(min_value=0, max_value=5)
REQUEST_STATES = st.sampled_from(("pending", "posted", "failed", "cancelled"))
REVIEW_DECISIONS = st.sampled_from(
    ("APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED", "COMMENTED")
)
INTEGRATION_STATES = st.sampled_from((None, "verified", "failed", "pending"))


@st.composite
def candidate_states(draw: st.DrawFn) -> tuple[str, str | None]:
    """Draw a head commit and the commit actually inspected.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    tuple
        A `(head, inspected)` pair covering an equal candidate, a changed
        candidate, and an unknown inspected commit.
    """
    kind = draw(st.sampled_from(("equal", "changed", "absent")))
    head = draw(HEADS)
    if kind == "equal":
        return head, head
    if kind == "changed":
        return head, draw(HEADS.filter(lambda other: other != head))
    return head, None


@st.composite
def review_states(draw: st.DrawFn) -> ReviewObservation:
    """Draw an arbitrary observation across every documented review surface.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    ReviewObservation
        A state combining candidate, coverage, retrieval, queue, disposition,
        review-decision, check, and integration values.
    """
    head, inspected = draw(candidate_states())
    return ReviewObservation(
        head=head,
        inspected=inspected,
        coverage_complete=draw(st.booleans()),
        retrieval_complete=draw(st.booleans()),
        request_state=draw(REQUEST_STATES),
        review_activity=draw(st.booleans()),
        unresolved_threads=draw(COUNTS),
        undispositioned_rows=draw(COUNTS),
        review_decision=draw(REVIEW_DECISIONS),
        required_checks_green=draw(st.booleans()),
        integration=draw(INTEGRATION_STATES),
    )


def test_documented_guard_order_is_stable() -> None:
    """The guard table must keep the precedence the skill documents."""
    actual = tuple(disposition for _, disposition in GUARD_PRECEDENCE)

    assert actual == DOCUMENTED_GUARD_ORDER, (
        "the documented guard precedence must not be reordered: "
        f"expected {DOCUMENTED_GUARD_ORDER} but found {actual}"
    )


@settings(deadline=None, max_examples=50)
@given(state=review_states())
def test_classify_returns_only_documented_dispositions(
    state: ReviewObservation,
) -> None:
    """Every generated state must classify as one documented disposition."""
    actual = classify(state)

    assert actual in DOCUMENTED_DISPOSITIONS, (
        f"a review state must classify as one of {DOCUMENTED_DISPOSITIONS}, "
        f"but {state!r} produced {actual!r}"
    )


@settings(deadline=None, max_examples=50)
@given(state=review_states())
def test_no_blocked_state_reaches_merge_eligibility(
    state: ReviewObservation,
) -> None:
    """A state tripping any documented guard must never be merge eligible."""
    blocked = [
        disposition
        for blocked_when, disposition in GUARD_PRECEDENCE
        if blocked_when(state)
    ]
    actual = classify(state)

    if blocked:
        assert actual != MERGE_ELIGIBLE, (
            f"a state tripping the {blocked[0]!r} guard must not be "
            f"{MERGE_ELIGIBLE!r}, but {state!r} produced {actual!r}"
        )
    else:
        assert actual == MERGE_ELIGIBLE, (
            f"a state that clears every documented guard must be "
            f"{MERGE_ELIGIBLE!r}, but {state!r} produced {actual!r}"
        )


@settings(deadline=None, max_examples=50)
@given(state=review_states())
def test_first_documented_guard_decides_the_reported_disposition(
    state: ReviewObservation,
) -> None:
    """The earliest tripped guard in the documented order must be reported."""
    tripped = [
        disposition
        for blocked_when, disposition in GUARD_PRECEDENCE
        if blocked_when(state)
    ]
    expected = tripped[0] if tripped else MERGE_ELIGIBLE
    actual = classify(state)

    assert actual == expected, (
        f"the documented guard order reports {expected!r} for {state!r}, "
        f"but classify returned {actual!r}"
    )


@settings(deadline=None, max_examples=50)
@given(state=review_states())
def test_integration_failure_is_reported_ahead_of_every_other_surface(
    state: ReviewObservation,
) -> None:
    """A failing post-merge job must be reported whatever else the state says."""
    failed = replace(state, integration="failed")
    actual = classify(failed)

    assert actual == INTEGRATION_FAILED, (
        "a green pull request cannot discharge a failing integration job, so "
        f"{failed!r} must classify as {INTEGRATION_FAILED!r} rather than "
        f"{actual!r}"
    )


@settings(deadline=None, max_examples=50)
@given(state=review_states())
def test_an_unknown_inspected_commit_is_not_treated_as_stale(
    state: ReviewObservation,
) -> None:
    """An unknown inspected commit must not be reported as a stale candidate."""
    unknown = replace(state, inspected=None)
    actual = classify(unknown)

    assert actual != CANDIDATE_STALE, (
        "an unknown inspected commit is not evidence that the candidate "
        f"changed, so {unknown!r} must not classify as {CANDIDATE_STALE!r}"
    )
