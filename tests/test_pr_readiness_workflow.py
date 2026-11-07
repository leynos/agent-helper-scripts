"""Drive the readiness sequence end to end against test doubles.

``pr_readiness_model`` is a decision over facts. These cases wrap it in the
sequence the skills describe: post the assessment questions, read the replies,
decide, and only then leave draft. The doubles record the transition instead
of performing it, so a passing case shows the sequence reaches readiness for
the right reasons and a failing one shows where it stops.

Together with the model cases they cover the three shapes the review asked
for: a subset-only verdict, a superseded revision, and a current verdict, each
with the proof assessment applying and with no ExecPlan in force.
"""

from __future__ import annotations

import pytest
from pr_readiness_model import (
    CLEAR,
    DECLARED_SUBSET,
    NOT_CLEAR,
    PENDING,
    WHOLE_PLAN,
    StackLayer,
)
from pr_readiness_workflow import (
    CODERABBIT,
    Discussion,
    PullRequest,
    Reply,
    assess_and_maybe_mark_ready,
)

BASE = "base0000"
HEAD = "head0000"
REVISION = "rev-2026-11-01"
COMPLETENESS_ID = "271-boundary-completeness"
PROOF_ID = "271-boundary-proof"


def pull(
    *,
    draft: bool = True,
    revision: str | None = REVISION,
    layer: StackLayer | None = None,
    ci_green: bool = True,
    codescene_clear: bool = True,
) -> PullRequest:
    """Return a draft PR double for the accepted candidate."""
    return PullRequest(
        base=BASE,
        head=HEAD,
        is_draft=draft,
        ci_green=ci_green,
        codescene_clear=codescene_clear,
        approved_plan_revision=revision,
        stack_layer=layer,
    )


def discussion() -> Discussion:
    """Return an empty assessment thread for the accepted candidate."""
    return Discussion(base=BASE, head=HEAD)


def reply(
    assessment_id: str,
    *,
    verdict: str = CLEAR,
    revision: str | None = REVISION,
    echoed: str | None = REVISION,
    subject: str = WHOLE_PLAN,
    milestones: tuple[str, ...] = (),
    head: str = HEAD,
    base: str = BASE,
    justification: str = "",
    author: str = CODERABBIT,
) -> Reply:
    """Return a substantive assessment reply for one request marker."""
    return Reply(
        assessment_id=assessment_id,
        author=author,
        base=base,
        head=head,
        verdict=verdict,
        plan_revision=revision,
        echoed_revision=echoed,
        subject=subject,
        named_milestones=milestones,
        justification=justification,
    )


def _lower_stack() -> StackLayer:
    """Return a layer with its own milestones, a parent and work above it."""
    return StackLayer(
        milestones=("EP-M1", "EP-M2"),
        parent="stack#12",
        remaining_above=("EP-M3", "EP-M4"),
    )


def test_a_current_verdict_marks_the_draft_ready() -> None:
    """Both applicable assessments clear for this candidate and revision."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert decision.ready, decision.reason
    assert not candidate.is_draft
    assert candidate.ready_transitions == [HEAD]


def test_a_subset_only_verdict_keeps_the_draft_in_place() -> None:
    """A PR that claims the whole plan cannot leave draft on its subset."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID, subject=DECLARED_SUBSET))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == "completeness-whole-plan-required"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_a_lower_stack_layer_clears_on_its_named_subset() -> None:
    """The managed-stack exception is what makes a subset verdict sufficient."""
    thread = discussion()
    thread.responses.append(
        reply(
            COMPLETENESS_ID,
            subject=DECLARED_SUBSET,
            milestones=_lower_stack().milestones,
        )
    )
    thread.responses.append(reply(PROOF_ID))
    candidate = pull(layer=_lower_stack())

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_a_superseded_revision_keeps_the_draft_in_place() -> None:
    """A verdict for an older revision does not transfer to the new one."""
    thread = discussion()
    thread.responses.append(
        reply(COMPLETENESS_ID, revision="rev-previous", echoed="rev-previous")
    )
    thread.responses.append(reply(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == "completeness-superseded-revision"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_a_reply_that_omits_the_revision_keeps_the_draft_in_place() -> None:
    """Echoing only the base/head does not establish what was inspected."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID, echoed=None))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == "completeness-revision-unbound"
    assert candidate.is_draft


def test_a_pending_proof_keeps_the_draft_in_place() -> None:
    """A clear completeness reply alone is not the gate."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == "proof-pending"
    assert candidate.is_draft


def test_an_unanswered_completeness_request_keeps_the_draft_in_place() -> None:
    """A posted request with no substantive reply is pending, not clearance."""
    thread = discussion()
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread)

    assert not decision.ready
    assert decision.reason == "completeness-pending"
    assert candidate.is_draft


def test_a_reply_from_another_author_is_not_a_verdict() -> None:
    """Only the assessment bot's reply is correlated with a request."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID, author="someone-else"))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread)

    assert not decision.ready
    assert decision.reason == "completeness-pending"
    assert candidate.is_draft


def test_an_unaffected_proof_under_the_execplan_still_reaches_ready() -> None:
    """A justified not-applicable proof needs no reply and no revision echo."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=False)

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_a_no_execplan_assignment_needs_no_revision_echo() -> None:
    """With no ExecPlan the base/head is the whole candidate."""
    thread = discussion()
    thread.responses.append(
        reply(COMPLETENESS_ID, revision=None, echoed=None)
    )
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=False)

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_a_red_ci_candidate_never_leaves_draft() -> None:
    """Readiness does not precede the delivery gates."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull(ci_green=False)

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == "ci-not-green"
    assert candidate.is_draft


@pytest.mark.parametrize(
    ("ci_green", "codescene_clear", "reason"),
    [
        (False, True, "ci-not-green"),
        (True, False, "codescene-not-clear"),
    ],
    ids=["red-ci", "open-codescene"],
)
def test_a_blocked_delivery_gate_asks_no_assessment_question(
    ci_green: bool, codescene_clear: bool, reason: str
) -> None:
    """The sequence establishes the gates before it spends a reply on them."""
    thread = discussion()
    candidate = pull(ci_green=ci_green, codescene_clear=codescene_clear)

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == reason
    assert thread.requests == [], "no assessment question before the delivery gates"
    assert candidate.is_draft


def test_a_no_execplan_proof_only_assignment_clears_without_revisions() -> None:
    """A proof-only change with no ExecPlan needs no completeness or echo."""
    thread = discussion()
    thread.responses.append(reply(PROOF_ID, revision=None, echoed=None))
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, completeness_applies=False, proof_applies=True
    )

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]
    assert [request["kind"] for request in thread.requests] == ["proof"]


def test_a_no_execplan_proof_only_assignment_waits_for_its_reply() -> None:
    """The proof-only path is still gated on the proof reply."""
    thread = discussion()
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, completeness_applies=False, proof_applies=True
    )

    assert not decision.ready
    assert decision.reason == "proof-pending"
    assert candidate.is_draft


def test_the_sequence_never_returns_an_already_ready_pr_to_draft() -> None:
    """Readiness is a one-way transition, as the lifecycle contract requires."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID, verdict=NOT_CLEAR))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull(draft=False)

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert not candidate.is_draft, "a blocked gate must not redraft a ready PR"
    assert candidate.ready_transitions == []
    assert decision.reason == "completeness-not-clear"


def test_the_questions_posted_carry_the_revision_in_force() -> None:
    """Each posted request names the revision its reply must echo."""
    thread = discussion()
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert [request["kind"] for request in thread.requests] == [
        "completeness",
        "proof",
    ]
    assert all(request["revision"] == REVISION for request in thread.requests)


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [(PENDING, "proof-pending"), (NOT_CLEAR, "proof-not-clear")],
    ids=["pending", "not-clear"],
)
def test_an_unsettled_proof_verdict_blocks_the_transition(
    verdict: str, reason: str
) -> None:
    """The proof assessment is not optional when it applies."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    thread.responses.append(reply(PROOF_ID, verdict=verdict))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert not decision.ready
    assert decision.reason == reason
    assert candidate.is_draft


def test_a_justified_not_applicable_completeness_allows_readiness() -> None:
    """A plan-authoring PR has no implementation to assess."""
    thread = discussion()
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, proof_applies=False, completeness_applies=False
    )

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_the_doubles_record_but_never_perform_the_transition() -> None:
    """The ready list is the only side effect, and it names the tested head."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID))
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread, proof_applies=False)

    assert candidate.ready_transitions == [HEAD]
    assert not candidate.is_draft


def test_a_verdict_subject_other_than_the_reply_default_is_carried_through() -> None:
    """The workflow passes the reply's subject rather than assuming one."""
    thread = discussion()
    thread.responses.append(reply(COMPLETENESS_ID, subject=DECLARED_SUBSET))
    thread.responses.append(reply(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert decision.reason == "completeness-whole-plan-required"


def test_both_requests_are_posted_before_the_decision() -> None:
    """The sequence asks both questions, then decides once."""
    thread = discussion()
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread, proof_applies=True)

    assert len(thread.requests) == 2
    assert candidate.is_draft
