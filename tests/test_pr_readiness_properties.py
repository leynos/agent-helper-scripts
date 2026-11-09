"""Property tests for the draft-to-ready decision model.

``test_pr_readiness_model.py`` states selected cases. This module states the
invariant over generated ones: the model permits the draft-to-ready transition
exactly when every documented condition holds, and blocks it otherwise.

The oracle below is written from the shipped rule rather than from the model's
control flow, so a change that makes the model more or less permissive than the
prose shows up as a disagreement in either direction. Soundness catches a gate
that opens too easily; completeness catches one that never opens at all.
Reporting them separately tells the reader which way the model drifted.

States are built rather than sampled. A uniformly drawn verdict almost never
survives the six checks that precede the subject check, so a random generator
tests the early branches and leaves the last ones effectively unexercised — a
mutant that accepted a stale plan revision passed every generated example.
Each state here starts from one that satisfies every condition and then
*breaks* a named, applicable subset of them, so every branch is reached by
construction. A single-break state additionally names the reason the model must
return, which keeps the generator's vocabulary tied to the model's own.

States are also generated at the workflow boundary: ``pr_readiness_workflow``
posts an assessment question only for an applicable assessment and records a
justified ``not applicable`` otherwise, so an inapplicable assessment carrying
a substantive verdict is not a state any caller can produce.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from hypothesis import given, settings
from hypothesis import strategies as st

import pr_readiness_workflow as workflow
from pr_readiness_model import (
    CLEAR,
    COMPLETENESS,
    DECLARED_SUBSET,
    NOT_APPLICABLE,
    NOT_CLEAR,
    PENDING,
    PROOF,
    VERDICTS,
    WHOLE_PLAN,
    Candidate,
    Readiness,
    Verdict,
    readiness,
)

BASE = "base0000"
HEAD = "head0000"
REVISION = "rev-2026-11-01"
PRIOR_REVISION = "rev-2026-10-01"
OTHER = "ffff0000"

#: One value outside ``VERDICTS``, so a reply the rule does not recognize at
#: all is generated alongside the four it does.
UNRECOGNIZED_VERDICT = "substantially complete"

#: One value outside ``SUBJECTS``, so a malformed ledger subject is generated
#: alongside the two documented ones.
UNRECOGNIZED_SUBJECT = "the milestones I chose"

#: The proof assessment's subject is the named proofs it covers, which the
#: whole-plan rule does not constrain.
PROOF_SUBJECT = "named proofs"

#: The one proof the generated candidates list, so a clear proof verdict must
#: name it to clear.
PROOF_ONE = "proofs/refinement/Theorem.lean#refinement_sound"

DEFENDED = "No assessment applies to this change."
UNDEFENDED = "   "

REVISIONS = st.sampled_from([None, REVISION])
HEADS = st.sampled_from([HEAD, OTHER])


@dataclass(frozen=True)
class State:
    """One combination of candidate, applicability, revisions and verdicts."""

    ci_green: bool
    codescene_clear: bool
    revision: str | None
    completeness_applies: bool
    proof_applies: bool
    completeness: Verdict
    proof: Verdict
    #: The proof inventory the request names. Fixed rather than generated: the
    #: property under test is that a verdict must cover whatever it names, and
    #: one named proof is enough to exercise both sides of that comparison.
    required_proofs: tuple[str, ...] = (PROOF_ONE,)

    def candidate(self) -> Candidate:
        """Return the accepted candidate this state describes."""
        return Candidate(
            base=BASE,
            head=HEAD,
            approved_plan_revision=self.revision,
            ci_green=self.ci_green,
            codescene_clear=self.codescene_clear,
            required_proofs=self.required_proofs,
        )

    def with_assessment(self, kind: str, **changes: object) -> State:
        """Return this state with one assessment's verdict fields replaced."""
        current = self.completeness if kind == COMPLETENESS else self.proof
        return replace(self, **{kind: replace(current, **changes)})

    def assessment(self, kind: str) -> Verdict:
        """Return the verdict for ``kind``."""
        return self.completeness if kind == COMPLETENESS else self.proof

    def applies(self, kind: str) -> bool:
        """Return whether the assignment requires ``kind``."""
        return self.completeness_applies if kind == COMPLETENESS else self.proof_applies


def _settled(
    revision: str | None, completeness_applies: bool, proof_applies: bool
) -> State:
    """Return a state in which every documented condition holds.

    An applicable assessment is clear, whole-plan where that applies, true of
    the accepted candidate, and bound to the revision in force. An inapplicable
    one is a justified ``not applicable``, which is the only shape the workflow
    records for it.
    """

    def verdict(kind: str, subject: str) -> Verdict:
        """Return one assessment that satisfies every condition it can."""
        applies = completeness_applies if kind == COMPLETENESS else proof_applies
        if not applies:
            fields = {
                "verdict": NOT_APPLICABLE,
                "subject": subject,
                "justification": DEFENDED,
            }
        else:
            fields = {"verdict": CLEAR, "subject": subject, "justification": ""}
        return Verdict(
            base=BASE,
            head=HEAD,
            plan_revision=revision,
            echoed_revision=revision,
            # A clear proof verdict names the candidate's inventory, so the
            # settled state covers what the request asked about.
            proofs=(PROOF_ONE,) if kind == PROOF else (),
            **fields,
        )

    return State(
        ci_green=True,
        codescene_clear=True,
        revision=revision,
        completeness_applies=completeness_applies,
        proof_applies=proof_applies,
        completeness=verdict(COMPLETENESS, WHOLE_PLAN),
        proof=verdict(PROOF, PROOF_SUBJECT),
    )


@dataclass(frozen=True)
class Break:
    """One documented condition, the states it can be broken in, and its reason.

    ``key`` labels the condition for the generated input. ``expected`` is the
    reason the model must return when this is the only broken condition, so the
    generator cannot drift away from the model's own vocabulary.
    """

    key: str
    applies: Callable[[State], bool]
    violate: Callable[[State], State]
    expected: str


def _assessment_breaks(kind: str, *, subject: bool) -> tuple[Break, ...]:
    """Return the conditions one assessment can break, and how to break them.

    Parameters
    ----------
    kind : str
        ``completeness`` or ``proof``.
    subject : bool
        Whether to include the whole-plan subject conditions, which bind only
        the completeness assessment.
    """

    def required(state: State) -> bool:
        """Whether this assessment is applicable, so a reply is expected."""
        return state.applies(kind)

    def bound(state: State) -> bool:
        """Whether a plan revision is in force, so a verdict must cite it."""
        return state.applies(kind) and state.revision is not None

    def blank(state: State) -> bool:
        """Whether this assessment is inapplicable, so only a defence applies."""
        return not state.applies(kind)

    breaks = (
        Break(
            f"{kind}-unrecognized",
            required,
            lambda s: s.with_assessment(kind, verdict=UNRECOGNIZED_VERDICT),
            "assessment-unrecognized-verdict",
        ),
        Break(
            f"{kind}-declared-not-applicable",
            required,
            lambda s: s.with_assessment(
                kind, verdict=NOT_APPLICABLE, justification=UNDEFENDED
            ),
            f"{kind}-declared-not-applicable",
        ),
        Break(
            f"{kind}-not-clear",
            required,
            lambda s: s.with_assessment(kind, verdict=NOT_CLEAR),
            f"{kind}-not-clear",
        ),
        Break(
            f"{kind}-pending",
            required,
            lambda s: s.with_assessment(kind, verdict=PENDING),
            f"{kind}-pending",
        ),
        Break(
            f"{kind}-candidate-mismatch",
            required,
            lambda s: s.with_assessment(kind, head=OTHER),
            f"{kind}-candidate-mismatch",
        ),
        Break(
            f"{kind}-superseded-revision",
            bound,
            lambda s: s.with_assessment(kind, plan_revision=PRIOR_REVISION),
            f"{kind}-superseded-revision",
        ),
        Break(
            f"{kind}-revision-unbound",
            bound,
            lambda s: s.with_assessment(kind, echoed_revision=None),
            f"{kind}-revision-unbound",
        ),
        Break(
            f"{kind}-not-applicable-undefended",
            blank,
            lambda s: s.with_assessment(kind, justification=UNDEFENDED),
            "not-applicable-undefended",
        ),
    )
    if kind == PROOF:
        # The inventory rule binds only the proof assessment, and only when it
        # is applicable: an unaffected proof has no inventory to cover.
        breaks = breaks + (
            Break(
                f"{kind}-inventory-incomplete",
                required,
                lambda s: s.with_assessment(kind, proofs=()),
                "proof-inventory-incomplete",
            ),
        )
    if not subject:
        return breaks
    return breaks + (
        Break(
            f"{kind}-declared-subset",
            required,
            lambda s: s.with_assessment(kind, subject=DECLARED_SUBSET),
            f"{kind}-declared-subset-does-not-clear",
        ),
        Break(
            f"{kind}-subject-unrecognized",
            required,
            lambda s: s.with_assessment(kind, subject=UNRECOGNIZED_SUBJECT),
            f"{kind}-subject-unrecognized",
        ),
    )


#: The candidate-level conditions, which no assessment can alter.
_CANDIDATE_BREAKS = (
    Break(
        "ci-not-green",
        lambda s: True,
        lambda s: replace(s, ci_green=False),
        "ci-not-green",
    ),
    Break(
        "codescene-not-clear",
        lambda s: True,
        lambda s: replace(s, codescene_clear=False),
        "codescene-not-clear",
    ),
)

#: Every condition the rule states, over every state that can break it.
BREAKS = (
    _CANDIDATE_BREAKS
    + _assessment_breaks(COMPLETENESS, subject=True)
    + _assessment_breaks(PROOF, subject=False)
)


def _with_breaks(state: State, breaks: frozenset[str]) -> State:
    """Return ``state`` with every named condition violated."""
    for candidate_break in BREAKS:
        if candidate_break.key in breaks and candidate_break.applies(state):
            state = candidate_break.violate(state)
    return state


@st.composite
def _perturbed_states(draw: st.DrawFn) -> tuple[State, frozenset[str]]:
    """Draw a state and the set of conditions it violates.

    The shape is chosen first — untouched, exactly one condition, or several —
    so a single broken condition is drawn with the same frequency as any other
    shape. Drawing a subset element by element would make single-condition
    states vanishingly rare against this vocabulary, and they are the states
    that decide whether each branch works at all.
    """
    state = _settled(
        revision=draw(REVISIONS),
        completeness_applies=draw(st.booleans()),
        proof_applies=draw(st.booleans()),
    )
    applicable = tuple(b.key for b in BREAKS if b.applies(state))
    shape = draw(st.sampled_from(["untouched", "one", "several"]))
    if shape == "untouched" or not applicable:
        chosen: frozenset[str] = frozenset()
    elif shape == "one":
        chosen = frozenset([draw(st.sampled_from(applicable))])
    else:
        chosen = frozenset(
            draw(st.sets(st.sampled_from(applicable), max_size=len(applicable)))
        )
    return _with_breaks(state, chosen), chosen


def _assessment_holds(
    verdict: Verdict, applies: bool, candidate: Candidate, *, inventory: bool = False
) -> bool:
    """Return whether one assessment satisfies the documented condition.

    An applicable assessment may not excuse itself, a substantive verdict must
    be true of the accepted candidate, and under an ExecPlan it must also
    record and echo the revision in force. A proof verdict additionally has to
    cover the inventory the request named: clearing the proof gate without
    saying which proofs were assessed does not establish that they are sound.
    """
    if verdict.verdict not in VERDICTS:
        return False
    if verdict.verdict == NOT_APPLICABLE:
        return not applies and bool(verdict.justification.strip())
    if verdict.verdict in (NOT_CLEAR, PENDING):
        return False
    if (verdict.base, verdict.head) != (candidate.base, candidate.head):
        return False
    if inventory and any(
        proof not in verdict.proofs for proof in candidate.required_proofs
    ):
        return False
    if candidate.approved_plan_revision is None:
        return True
    return (
        verdict.plan_revision == candidate.approved_plan_revision
        and verdict.echoed_revision == candidate.approved_plan_revision
    )


def _subject_holds(completeness: Verdict, applies: bool) -> bool:
    """Return whether the completeness subject satisfies the documented rule.

    Only the completeness assessment is bounded by its subject; the proof
    assessment's subject is the named proofs it covers.
    """
    if not applies or completeness.verdict == NOT_APPLICABLE:
        return True
    return completeness.subject == WHOLE_PLAN


def _holds(state: State) -> bool:
    """Return whether every documented readiness condition holds.

    Written from the shipped rule: green CI and clear CodeScene findings, then
    each applicable assessment settled for the accepted candidate, then a
    whole-plan completeness subject.
    """
    candidate = state.candidate()
    return (
        state.ci_green
        and state.codescene_clear
        and _assessment_holds(
            state.completeness, state.completeness_applies, candidate
        )
        and _assessment_holds(state.proof, state.proof_applies, candidate, inventory=True)
        and _subject_holds(state.completeness, state.completeness_applies)
    )


def _decide(state: State) -> Readiness:
    """Return the model's decision for one generated state."""
    return readiness(
        state.candidate(),
        state.completeness,
        state.proof,
        completeness_applies=state.completeness_applies,
        proof_applies=state.proof_applies,
    )


@settings(deadline=None, max_examples=300)
@given(_perturbed_states())
def test_the_generator_breaks_what_it_claims(
    case: tuple[State, frozenset[str]],
) -> None:
    """The generated state violates a condition exactly when it claims to.

    Without this the generator could quietly stop producing a violation — a
    break whose field no longer matters, or one masked by another — and every
    other property here would pass while testing nothing.
    """
    state, breaks = case
    # `_holds` returns a bool and `breaks` is a frozenset, so `is not` between
    # them compared two different objects and passed on every input. The claim
    # is that the state holds exactly when nothing was broken, which is a
    # comparison of the bool with the emptiness of the set.
    assert _holds(state) == (not breaks), (
        "generated state does not match the conditions it claims to break: "
        f"breaks={sorted(breaks)}; holds={_holds(state)}; "
        f"cr={state.completeness}; proof={state.proof}; "
        f"ci={state.ci_green}; codescene={state.codescene_clear}; "
        f"revision={state.revision}; "
        f"applies=({state.completeness_applies}, {state.proof_applies})"
    )


@settings(deadline=None, max_examples=300)
@given(_perturbed_states())
def test_readiness_opens_only_when_every_documented_condition_holds(
    case: tuple[State, frozenset[str]],
) -> None:
    """A permitted transition is sound: no condition was skipped to reach it."""
    state, breaks = case
    decision = _decide(state)
    assert decision.ready == _holds(state), (
        "readiness disagrees with the documented rule: "
        f"breaks={sorted(breaks)}; ready={decision.ready}; "
        f"reason={decision.reason}; cr={state.completeness}; "
        f"proof={state.proof}; ci={state.ci_green}; "
        f"codescene={state.codescene_clear}; revision={state.revision}; "
        f"applies=({state.completeness_applies}, {state.proof_applies})"
    )


@settings(deadline=None, max_examples=300)
@given(_perturbed_states())
def test_a_single_broken_condition_returns_its_own_reason(
    case: tuple[State, frozenset[str]],
) -> None:
    """One broken condition is reported as that condition, not another.

    The gate is only useful if it names the thing that is actually wrong; a
    model that blocked for the wrong reason would send the operator to repair
    work that was already correct.
    """
    state, breaks = case
    if len(breaks) != 1:
        return
    key = next(iter(breaks))
    expected = next(b.expected for b in BREAKS if b.key == key)
    decision = _decide(state)
    assert not decision.ready
    assert decision.reason == expected, (
        f"breaking {key!r} returned {decision.reason!r}, not {expected!r}: "
        f"cr={state.completeness}; proof={state.proof}; "
        f"ci={state.ci_green}; codescene={state.codescene_clear}; "
        f"revision={state.revision}; "
        f"applies=({state.completeness_applies}, {state.proof_applies})"
    )


@st.composite
def _observed_reply(draw: st.DrawFn) -> workflow.Reply | None:
    """Draw one reply the assessor posted, or None while it has not answered.

    The request marker is filled in by the caller, because it belongs to the
    assignment rather than to the reply's content.
    """
    if not draw(st.booleans()):
        return None
    return workflow.Reply(
        assessment_id="",
        author=workflow.CODERABBIT,
        base=BASE,
        head=draw(HEADS),
        verdict=draw(st.sampled_from([*VERDICTS, UNRECOGNIZED_VERDICT])),
        plan_revision=draw(st.sampled_from([None, REVISION, PRIOR_REVISION])),
        echoed_revision=draw(st.sampled_from([None, REVISION, PRIOR_REVISION])),
        subject=draw(
            st.sampled_from([WHOLE_PLAN, DECLARED_SUBSET, UNRECOGNIZED_SUBJECT])
        ),
        justification=draw(st.sampled_from(["", UNDEFENDED, DEFENDED])),
    )


@settings(deadline=None, max_examples=200)
@given(
    ci_green=st.booleans(),
    codescene_clear=st.booleans(),
    revision=REVISIONS,
    completeness_applies=st.booleans(),
    proof_applies=st.booleans(),
    replies=st.tuples(_observed_reply(), _observed_reply()),
)
def test_the_workflow_transitions_a_double_only_on_a_ready_decision(
    ci_green: bool,
    codescene_clear: bool,
    revision: str | None,
    completeness_applies: bool,
    proof_applies: bool,
    replies: tuple[workflow.Reply | None, workflow.Reply | None],
) -> None:
    """The ready transition happens exactly when the model permits it.

    The double's transition list is the observable effect, so it is compared
    with the model's own decision rather than with a second implementation of
    the rule. A workflow that marked ready on a blocked decision, or left a
    ready decision in draft, fails here whatever the reason code was.
    """
    pull = workflow.PullRequest(
        base=BASE,
        head=HEAD,
        ci_green=ci_green,
        codescene_clear=codescene_clear,
        approved_plan_revision=revision,
    )
    assignment = workflow.Assignment(
        completeness_applies=completeness_applies,
        proof_applies=proof_applies,
    )
    discussion = workflow.Discussion(base=BASE, head=HEAD)
    for selection, reply in zip(assignment.selections(), replies, strict=True):
        if reply is not None:
            discussion.responses.append(
                replace(reply, assessment_id=selection.assessment_id)
            )

    decision = workflow.assess_and_maybe_mark_ready(pull, discussion, assignment)

    expected = [HEAD] if decision.ready else []
    assert pull.ready_transitions == expected, (
        "the double's transition disagrees with its own decision: "
        f"reason={decision.reason}; transitions={pull.ready_transitions}"
    )
    assert pull.is_draft is not decision.ready
