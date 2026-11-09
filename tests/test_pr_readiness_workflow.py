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

from dataclasses import dataclass, replace

import pytest
from pr_readiness_model import (
    CLEAR,
    COMPLETENESS,
    DECLARED_SUBSET,
    NOT_CLEAR,
    PENDING,
    PROOF,
    WHOLE_PLAN,
)
from pr_readiness_workflow import (
    CODERABBIT,
    PROOF_ONLY,
    Assignment,
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

#: One proof the request names, as the assignment would list it.
PROOF_ONE = "proofs/refinement/Theorem.lean#refinement_sound"

#: A second proof the request names but the reply may not cover.
PROOF_TWO = "proofs/refinement/Lemma.lean#step_preserves"

#: The inventory a satisfiable proof request names. An applicable proof
#: assessment must name one, so the ordinary case is a named proof rather than
#: an empty list; a test that wants the unnamed case passes an empty inventory.
DEFAULT_PROOFS = (PROOF_ONE,)

#: The ordinary assignment with the proof assessment also applicable.
with_proof = Assignment(proof_applies=True)

#: Neither assessment applies: a plan-authoring-only change.
NOTHING_APPLIES = Assignment(
    completeness_applies=False, proof_applies=False
)


def pull(
    *,
    draft: bool = True,
    revision: str | None = REVISION,
    ci_green: bool = True,
    codescene_clear: bool = True,
    required_proofs: tuple[str, ...] = DEFAULT_PROOFS,
) -> PullRequest:
    """Return a draft PR double for the accepted candidate.

    The proof inventory defaults to a named proof, because an applicable proof
    assessment must name one. A test that wants the unnamed case says so with
    ``required_proofs=()``.
    """
    return PullRequest(
        base=BASE,
        head=HEAD,
        is_draft=draft,
        ci_green=ci_green,
        codescene_clear=codescene_clear,
        approved_plan_revision=revision,
        required_proofs=required_proofs,
    )


def discussion() -> Discussion:
    """Return an empty assessment thread for the accepted candidate."""
    return Discussion(base=BASE, head=HEAD)


@dataclass(frozen=True)
class _Reply:
    """The fields a reply is composed from, with the ordinary case as default."""

    verdict: str = CLEAR
    revision: str | None = REVISION
    echoed: str | None = REVISION
    subject: str = WHOLE_PLAN
    head: str = HEAD
    base: str = BASE
    justification: str = ""
    author: str = CODERABBIT
    # The proofs a proof reply says it cleared. It defaults to the inventory
    # the ordinary request names, so a positive case is the default; a test
    # that wants an uncited or partial reply names its own list.
    proofs: tuple[str, ...] = DEFAULT_PROOFS


#: The default reply content: clear, whole-plan, and candidate-bound.
DEFAULT_REPLY = _Reply()


def reply_with(assessment_id: str, **changes: object) -> Reply:
    """Return a substantive reply to ``assessment_id`` with named fields changed.

    Parameters
    ----------
    assessment_id : str
        The request marker the reply must echo.
    **changes : object
        Fields of ``_Reply`` to replace, such as a stale revision or an
        unrelated author.

    Returns
    -------
    Reply
        The reply the discussion double will observe.
    """
    fields = replace(DEFAULT_REPLY, **changes)  # type: ignore[arg-type]
    return Reply(
        assessment_id=assessment_id,
        author=fields.author,
        base=fields.base,
        head=fields.head,
        verdict=fields.verdict,
        plan_revision=fields.revision,
        echoed_revision=fields.echoed,
        subject=fields.subject,
        justification=fields.justification,
        proofs=fields.proofs,
    )


def test_a_current_verdict_marks_the_draft_ready() -> None:
    """Both applicable assessments clear for this candidate and revision."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert decision.ready, decision.reason
    assert not candidate.is_draft
    assert candidate.ready_transitions == [HEAD]


@pytest.mark.parametrize(
    "candidate_state",
    [
        pytest.param("with-revision", id="single-pr"),
        pytest.param("no-revision", id="no-execplan"),
    ],
)
def test_a_subset_only_verdict_keeps_the_draft_in_place(
    candidate_state: str,
) -> None:
    """A declared-subset verdict is evidence for its scope, not readiness."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID, subject=DECLARED_SUBSET))
    thread.responses.append(reply_with(PROOF_ID))
    revision = REVISION if candidate_state == "with-revision" else None
    candidate = pull(revision=revision)

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == "completeness-declared-subset-does-not-clear"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_a_superseded_revision_keeps_the_draft_in_place() -> None:
    """A verdict for an older revision does not transfer to the new one."""
    thread = discussion()
    thread.responses.append(
        reply_with(COMPLETENESS_ID, revision="rev-previous", echoed="rev-previous")
    )
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == "completeness-superseded-revision"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_a_reply_that_omits_the_revision_keeps_the_draft_in_place() -> None:
    """Echoing only the base/head does not establish what was inspected."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID, echoed=None))
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == "completeness-revision-unbound"
    assert candidate.is_draft


def test_a_pending_proof_keeps_the_draft_in_place() -> None:
    """A clear completeness reply alone is not the gate."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

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
    thread.responses.append(reply_with(COMPLETENESS_ID, author="someone-else"))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread)

    assert not decision.ready
    assert decision.reason == "completeness-pending"
    assert candidate.is_draft


def test_an_unaffected_proof_under_the_execplan_still_reaches_ready() -> None:
    """A justified not-applicable proof needs no reply and no revision echo."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread)

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_a_no_execplan_assignment_needs_no_revision_echo() -> None:
    """With no ExecPlan the base/head is the whole candidate."""
    thread = discussion()
    thread.responses.append(
        reply_with(COMPLETENESS_ID, revision=None, echoed=None)
    )
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(candidate, thread)

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_a_red_ci_candidate_never_leaves_draft() -> None:
    """Readiness does not precede the delivery gates."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull(ci_green=False)

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

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

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == reason
    assert thread.requests == [], "no assessment question before the delivery gates"
    assert candidate.is_draft


def test_a_no_execplan_proof_only_assignment_clears_without_revisions() -> None:
    """A proof-only change with no ExecPlan needs no completeness or echo."""
    thread = discussion()
    thread.responses.append(reply_with(PROOF_ID, revision=None, echoed=None))
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, assignment=PROOF_ONLY
    )

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]
    assert [request["kind"] for request in thread.requests] == ["proof"]


def test_a_no_execplan_proof_only_assignment_waits_for_its_reply() -> None:
    """The proof-only path is still gated on the proof reply."""
    thread = discussion()
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, assignment=PROOF_ONLY
    )

    assert not decision.ready
    assert decision.reason == "proof-pending"
    assert candidate.is_draft


def test_the_sequence_never_returns_an_already_ready_pr_to_draft() -> None:
    """Readiness is a one-way transition, as the lifecycle contract requires."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID, verdict=NOT_CLEAR))
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull(draft=False)

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert not candidate.is_draft, "a blocked gate must not redraft a ready PR"
    assert candidate.ready_transitions == []
    assert decision.reason == "completeness-not-clear"


def test_the_questions_posted_carry_the_revision_in_force() -> None:
    """Each posted request names the revision its reply must echo."""
    thread = discussion()
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

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
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID, verdict=verdict))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == reason
    assert candidate.is_draft


def test_a_justified_not_applicable_completeness_allows_readiness() -> None:
    """A plan-authoring PR has no implementation to assess."""
    thread = discussion()
    candidate = pull(revision=None)

    decision = assess_and_maybe_mark_ready(
        candidate, thread, assignment=NOTHING_APPLIES
    )

    assert decision.ready, decision.reason
    assert candidate.ready_transitions == [HEAD]


def test_the_doubles_record_but_never_perform_the_transition() -> None:
    """The ready list is the only side effect, and it names the tested head."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread)

    assert candidate.ready_transitions == [HEAD]
    assert not candidate.is_draft


def test_a_verdict_subject_other_than_the_reply_default_is_carried_through() -> None:
    """The workflow passes the reply's subject rather than assuming one."""
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID, subject="declared-scope"))
    thread.responses.append(reply_with(PROOF_ID))
    candidate = pull()

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert decision.reason == "completeness-subject-unrecognized"


def test_the_workflow_carries_the_requested_proof_inventory() -> None:
    """The double's inventory reaches the model rather than being dropped.

    The proof inventory lives in the candidate, so a double that never passes
    one leaves `proof-inventory-incomplete` unreachable however the workflow
    is driven. Both halves are checked: the inventory the request names is the
    one the model compares against, and a reply covering it clears.
    """
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID, proofs=(PROOF_ONE,)))
    candidate = pull(required_proofs=(PROOF_ONE,))

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert candidate.ready_transitions == [HEAD], decision.reason
    assert not candidate.is_draft


def test_an_incomplete_proof_inventory_keeps_the_draft_in_place() -> None:
    """A clear proof verdict covering one of two proofs does not clear the gate.

    The reply is otherwise well formed — clear, the whole plan, candidate-bound
    — so the only reason it can fail is the proof it never named. That is what
    distinguishes this from the unsettled-verdict cases beside it.
    """
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID, proofs=(PROOF_ONE,)))
    candidate = pull(required_proofs=(PROOF_ONE, PROOF_TWO))

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready
    assert decision.reason == "proof-inventory-incomplete"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_the_proof_request_records_the_inventory_it_asked_about() -> None:
    """The posted proof question names the inventory, and only that question.

    A transcript that keeps only a kind and a marker cannot show what the
    request asked, so a reconciliation cannot tell a narrowed answer from a
    complete one. The inventory belongs to the request for the same reason the
    revision does, and the completeness question names none.
    """
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(
        reply_with(PROOF_ID, proofs=(PROOF_ONE, PROOF_TWO))
    )
    candidate = pull(required_proofs=(PROOF_ONE, PROOF_TWO))

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert decision.ready, decision.reason
    posted = {request["kind"]: request for request in thread.requests}
    assert posted[PROOF]["proofs"] == f"{PROOF_ONE},{PROOF_TWO}", (
        f"the proof request recorded {posted[PROOF]['proofs']!r}"
    )
    assert posted[COMPLETENESS]["proofs"] == "", (
        "only the proof question names a proof inventory"
    )


def test_an_applicable_proof_request_with_no_inventory_keeps_the_draft() -> None:
    """An applicable proof assessment must name what it asks about.

    The shipped documents offer two routes when no proof is affected: declare
    the assessment not applicable, or list the proofs a new one touches. A
    proof assignment that takes neither posts a question with nothing to
    assess, and a clear reply to it would clear a gate that never existed. The
    reply here names a proof of its own, which cannot supply the inventory the
    request failed to ask for.
    """
    thread = discussion()
    thread.responses.append(reply_with(COMPLETENESS_ID))
    thread.responses.append(reply_with(PROOF_ID, proofs=(PROOF_ONE,)))
    candidate = pull(required_proofs=())

    decision = assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert not decision.ready, "an unnamed proof inventory cleared the gate"
    assert decision.reason == "proof-inventory-empty"
    assert candidate.is_draft
    assert candidate.ready_transitions == []


def test_both_requests_are_posted_before_the_decision() -> None:
    """The sequence asks both questions, then decides once."""
    thread = discussion()
    candidate = pull()

    assess_and_maybe_mark_ready(candidate, thread, assignment=with_proof)

    assert len(thread.requests) == 2
    assert candidate.is_draft
