"""Exercise the documented draft-to-ready gate at the workflow boundary.

The skills state the readiness gate in prose, so these tests drive its
executable specification with whole candidates: accepted base/head, approved
plan revision, and the two assessment verdicts. Each case checks whether the
candidate may leave draft, which is the externally observable transition this
work changes.

The specification is not product code. ``pr_readiness_model`` restates the
gate, and the cases below keep the restatement honest: every reason the model
returns must cite a sentence the shipped documents still contain, so a rule
cannot be dropped from the model or from the prose alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import re
from pathlib import Path

import pr_readiness_model as readiness_module
import pytest
from pr_readiness_model import (
    CLEAR,
    COMPLETENESS,
    DECLARED_SUBSET,
    NOT_APPLICABLE,
    NOT_CLEAR,
    PENDING,
    PROOF,
    REASON_CITATIONS,
    SUBJECTS,
    WHOLE_PLAN,
    Candidate,
    Verdict,
    readiness,
)
from skill_contract_support import normalize, raw_section

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
ASSESSMENT = ROOT / "skills/pr-babysitting/references/execplan-assessment.md"

BASE = "base0000"
HEAD = "head0000"
REVISION = "rev-2026-11-01"


@dataclass(frozen=True)
class _Bounds:
    """The candidate and revisions a verdict is bound to."""

    base: str = BASE
    head: str = HEAD
    revision: str | None = REVISION
    echoed: str | None = REVISION


#: The default bindings, kept as one value so a case overrides a field by name
#: rather than repeating every unchanged one.
BOUND = _Bounds()

#: The proof verdict's default justification and subject.
PROOF_SUBJECT = "named proofs"
NO_PROOF = "No proof is affected by this change."


def bound(**changes: object) -> _Bounds:
    """Return the default bindings with the named fields replaced.

    Parameters
    ----------
    **changes : object
        Fields to rebind, such as a superseded head or plan revision.

    Returns
    -------
    _Bounds
        The bindings a verdict in this case should carry.
    """
    return replace(BOUND, **changes)  # type: ignore[arg-type]


def candidate(
    *,
    revision: str | None = REVISION,
    head: str = HEAD,
    ci_green: bool = True,
    codescene_clear: bool = True,
    required_proofs: tuple[str, ...] = (),
) -> Candidate:
    """Return the accepted candidate, optionally with a plan revision."""
    return Candidate(
        base=BASE,
        head=head,
        approved_plan_revision=revision,
        ci_green=ci_green,
        codescene_clear=codescene_clear,
        required_proofs=required_proofs,
    )


def _verdict(
    bounds: _Bounds,
    *,
    verdict: str,
    subject: str,
    justification: str,
    proofs: tuple[str, ...] = (),
) -> Verdict:
    """Return one assessment verdict bound to ``bounds``."""
    return Verdict(
        verdict=verdict,
        base=bounds.base,
        head=bounds.head,
        plan_revision=bounds.revision,
        echoed_revision=bounds.echoed,
        subject=subject,
        justification=justification,
        proofs=proofs,
    )


def completeness(
    *,
    bounds: _Bounds = BOUND,
    verdict: str = CLEAR,
    subject: str = WHOLE_PLAN,
    justification: str = "",
) -> Verdict:
    """Return a completeness verdict, whole-plan and exact by default."""
    return _verdict(
        bounds, verdict=verdict, subject=subject, justification=justification
    )


def proof(
    *,
    bounds: _Bounds = BOUND,
    verdict: str = NOT_APPLICABLE,
    justification: str = NO_PROOF,
    proofs: tuple[str, ...] = (),
) -> Verdict:
    """Return a proof verdict; the default is a justified not-applicable."""
    return _verdict(
        bounds,
        verdict=verdict,
        subject=PROOF_SUBJECT,
        justification=justification,
        proofs=proofs,
    )


def test_a_valid_current_assessment_allows_readiness() -> None:
    """Clear, candidate-bound, revision-bound assessments mark the PR ready."""
    decision = readiness(candidate(), completeness(), proof())
    assert decision.ready, decision.reason
    assert decision.reason == "ready"


def test_a_clear_proof_under_the_execplan_echoes_the_same_revision() -> None:
    """Ordinary single-PR delivery needs no stack, but keeps the revision."""
    decision = readiness(
        candidate(),
        completeness(subject=WHOLE_PLAN),
        proof(verdict=CLEAR),
    )
    assert decision.ready, decision.reason


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (PENDING, "completeness-pending"),
        (NOT_CLEAR, "completeness-not-clear"),
    ],
    ids=["pending", "not-clear"],
)
def test_an_unsettled_completeness_verdict_keeps_the_pr_in_draft(
    verdict: str, reason: str
) -> None:
    """Pending or not-clear completeness blocks the draft-to-ready transition."""
    decision = readiness(candidate(), completeness(verdict=verdict), proof())
    assert not decision.ready
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("base", "head", "reason"),
    [
        (BASE, "superseded-head", "completeness-candidate-mismatch"),
        ("other-base", HEAD, "completeness-candidate-mismatch"),
    ],
    ids=["stale-head", "other-base"],
)
def test_a_verdict_on_another_candidate_keeps_the_pr_in_draft(
    base: str, head: str, reason: str
) -> None:
    """A verdict must cover the accepted base/head, not one it replaced."""
    decision = readiness(
        candidate(), completeness(bounds=bound(base=base, head=head)), proof()
    )
    assert not decision.ready
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("candidate_state", "reason"),
    [
        pytest.param(
            candidate(),
            "completeness-declared-subset-does-not-clear",
            id="single-pr",
        ),
        # An applicable completeness assessment with no revision in force is
        # refused earlier, by the revision binding, so the subset rule is not
        # the reason a no-ExecPlan candidate holds. Asserting the subset reason
        # here would pass only while that earlier check was missing.
        pytest.param(
            candidate(revision=None),
            "completeness-revision-absent",
            id="no-execplan",
        ),
    ],
)
def test_a_declared_subset_verdict_never_clears_the_gate(
    candidate_state: Candidate, reason: str
) -> None:
    """A subset verdict is evidence for its actual scope only, never clearance."""
    decision = readiness(
        candidate_state,
        completeness(
            subject=DECLARED_SUBSET,
            bounds=bound(
                revision=candidate_state.approved_plan_revision,
                echoed=candidate_state.approved_plan_revision,
            ),
        ),
        proof(),
    )
    assert not decision.ready
    assert decision.reason == reason


@pytest.mark.parametrize(
    "subject",
    ["", "declared-scope", "this PR", "whole plan"],
)
def test_an_unrecognized_subject_keeps_the_pr_in_draft(subject: str) -> None:
    """Only the whole plan or a declared subset is a documented record."""
    decision = readiness(candidate(), completeness(subject=subject), proof())
    assert not decision.ready
    assert decision.reason == "completeness-subject-unrecognized"


@pytest.mark.parametrize(
    ("revision", "echoed", "reason"),
    [
        ("rev-previous", "rev-previous", "completeness-superseded-revision"),
        (REVISION, None, "completeness-revision-unbound"),
    ],
    ids=["superseded-revision", "echo-omits-revision"],
)
def test_an_unbound_plan_revision_keeps_the_pr_in_draft(
    revision: str, echoed: str | None, reason: str
) -> None:
    """A verdict recorded against another revision does not clear the gate."""
    decision = readiness(
        candidate(), completeness(bounds=bound(revision=revision, echoed=echoed)), proof()
    )
    assert not decision.ready
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("revision", "echoed", "approved", "reason"),
    [
        # Whitespace around an identifier is not part of it.
        (" rev-2026-11-01 ", "rev-2026-11-01", REVISION, "ready"),
        (REVISION, "rev-2026-11-01\n", REVISION, "ready"),
        # A blank field identifies no revision. Read as an ordinary value it
        # would be a revision every reply could echo, binding a verdict to
        # nothing; it is the absent case instead, and so lands on the rule for
        # a verdict that names no revision in force.
        ("   ", "   ", REVISION, "completeness-superseded-revision"),
        (REVISION, "", REVISION, "completeness-revision-unbound"),
        (REVISION, REVISION, "", "completeness-revision-absent"),
        (REVISION, REVISION, " \t", "completeness-revision-absent"),
    ],
    ids=[
        "padded-revision-in-force",
        "padded-echo",
        "blank-revision-and-echo",
        "blank-echo",
        "blank-approval",
        "whitespace-approval",
    ],
)
def test_a_blank_revision_identifies_nothing(
    revision: str,
    echoed: str | None,
    approved: str | None,
    reason: str,
) -> None:
    """An identifier's whitespace is not part of it, and a blank one is absent.

    The revision reaches this check through a comment body, a field parser and
    a ledger, and each of those can leave a trailing newline or a space around
    it. A comparison on the raw strings would then hold a verdict whose only
    difference is the whitespace its carrier added, which is not a difference
    in what the candidate was approved against.

    The blank cases are the other direction: `"   "` is a value every reply
    could echo, so treating it as an ordinary revision would bind verdicts to
    an approval that never named one. It is read as absent, which is the rule
    for a candidate with no approved revision at all.
    """
    decision = readiness(
        candidate(revision=approved),
        completeness(bounds=bound(revision=revision, echoed=echoed)),
        proof(),
    )
    assert decision.reason == reason
    assert decision.ready is (reason == "ready")


def test_a_proof_verdict_on_a_superseded_revision_keeps_the_pr_in_draft() -> None:
    """The revision binding applies to whichever assessment is in scope."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=CLEAR, bounds=bound(revision="rev-previous", echoed="rev-previous")),
    )
    assert not decision.ready
    assert decision.reason == "proof-superseded-revision"


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (PENDING, "proof-pending"),
        (NOT_CLEAR, "proof-not-clear"),
    ],
    ids=["pending", "not-clear"],
)
def test_an_unsettled_proof_verdict_keeps_the_pr_in_draft(
    verdict: str, reason: str
) -> None:
    """A clear completeness verdict alone does not satisfy the gate."""
    decision = readiness(
        candidate(), completeness(), proof(verdict=verdict, justification="")
    )
    assert not decision.ready
    assert decision.reason == reason


def test_a_proof_verdict_must_echo_its_revision_under_an_execplan() -> None:
    """A proof request under an ExecPlan names and echoes the revision."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=CLEAR, bounds=bound(echoed=None)),
    )
    assert not decision.ready
    assert decision.reason == "proof-revision-unbound"


THEOREM = "proofs/refinement/Theorem.lean#refinement_sound"
LEMMA = "proofs/refinement/Lemma.lean#step_preserves"


def test_a_clear_proof_verdict_must_cover_the_whole_inventory() -> None:
    """A clear verdict names every proof the request listed.

    The gate asks that the listed proofs are substantive. A reply that says
    only "the proofs are fine" answers a question nobody asked, and the gate
    would open with none of the inventory actually assessed.
    """
    decision = readiness(
        candidate(required_proofs=(THEOREM,)),
        completeness(),
        proof(verdict=CLEAR),
        proof_applies=True,
    )
    assert not decision.ready, "an unnamed proof inventory cleared the gate"
    assert decision.reason == "proof-inventory-incomplete"


def test_an_applicable_proof_assessment_must_name_an_inventory() -> None:
    """An applicable proof request with nothing listed has nothing to clear.

    The shipped documents give exactly two routes when no proof is affected:
    declare the assessment not applicable, or list the proofs a newly
    introduced one affects. A proof assignment that takes neither asks a
    question with no subject, and a clear reply to it would open the gate with
    no proof assessed. The reply's own list cannot substitute: a reply that
    names a proof the request never asked about is answering a different
    question.
    """
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=CLEAR, proofs=(THEOREM,)),
        proof_applies=True,
    )
    assert not decision.ready, "an applicable proof assessment with no inventory cleared"
    assert decision.reason == "proof-inventory-empty"


def test_a_clear_proof_verdict_covering_one_of_two_proofs_is_incomplete() -> None:
    """Covering part of the inventory leaves the rest unassessed.

    This is the scope narrowing the rule forbids: the reply reads as a clear
    assessment while one listed proof has no verdict at all.
    """
    decision = readiness(
        candidate(required_proofs=(THEOREM, LEMMA)),
        completeness(),
        proof(verdict=CLEAR, proofs=(THEOREM,)),
        proof_applies=True,
    )
    assert not decision.ready, "a partly covered proof inventory cleared the gate"
    assert decision.reason == "proof-inventory-incomplete"


def test_a_clear_proof_verdict_covering_the_inventory_allows_readiness() -> None:
    """The positive control: naming every listed proof is sufficient.

    Without it, the inventory rule would pass by refusing everything.
    """
    decision = readiness(
        candidate(required_proofs=(THEOREM, LEMMA)),
        completeness(),
        proof(verdict=CLEAR, proofs=(THEOREM, LEMMA)),
        proof_applies=True,
    )
    assert decision.ready, decision.reason


def test_a_justified_not_applicable_needs_no_inventory() -> None:
    """An unaffected proof has no inventory to cover.

    Reading the rule as applying here would keep draft for a change that
    introduces no proofs at all, which the shipped documents do not require.
    """
    decision = readiness(
        candidate(required_proofs=(THEOREM,)),
        completeness(),
        proof(verdict=NOT_APPLICABLE),
        proof_applies=False,
    )
    assert decision.ready, decision.reason


def test_an_undefended_not_applicable_keeps_the_pr_in_draft() -> None:
    """Not applicable needs evidence; silence is not a disposition."""
    decision = readiness(
        candidate(), completeness(), proof(verdict=NOT_APPLICABLE, justification="  ")
    )
    assert not decision.ready
    assert decision.reason == "not-applicable-undefended"


def test_a_proof_only_assignment_needs_no_plan_revision() -> None:
    """Without an ExecPlan the base/head is the whole candidate.

    The assignment still names the proof it asks about; only the revision echo
    is waived, not the inventory an applicable proof assessment requires.
    """
    decision = readiness(
        candidate(revision=None, required_proofs=(THEOREM,)),
        completeness(verdict=NOT_APPLICABLE,
                     bounds=bound(revision=None, echoed=None),
                     justification="No ExecPlan governs this change."),
        proof(verdict=CLEAR, bounds=bound(revision=None, echoed=None),
              proofs=(THEOREM,)),
        completeness_applies=False,
        proof_applies=True,
    )
    assert decision.ready, decision.reason


def test_an_unaffected_proof_under_an_execplan_needs_no_reply() -> None:
    """A not-applicable proof has no reply to bind, so no revision is echoed."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=NOT_APPLICABLE, bounds=bound(revision=None, echoed=None)),
    )
    assert decision.ready, decision.reason


def test_an_unaffected_completeness_needs_no_subject_or_revision() -> None:
    """A not-applicable completeness is skipped, not checked against a subject."""
    decision = readiness(
        candidate(revision=None),
        completeness(verdict=NOT_APPLICABLE,
                     bounds=bound(revision=None, echoed=None),
                     subject=DECLARED_SUBSET,
                     justification="This PR only authors the plan."),
        proof(verdict=NOT_APPLICABLE, bounds=bound(revision=None, echoed=None)),
        completeness_applies=False,
    )
    assert decision.ready, decision.reason


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("completeness", "completeness-declared-not-applicable"),
        ("proof", "proof-declared-not-applicable"),
    ],
    ids=["applicable-completeness", "applicable-proof"],
)
@pytest.mark.parametrize("justified", [True, False], ids=["justified", "bare"])
def test_an_applicable_assessment_cannot_excuse_itself(
    *, kind: str, reason: str, justified: bool
) -> None:
    """A reply may not declare an applicable assessment not applicable.

    Applicability is a property of the assignment, not of the reply. Accepting
    a self-declared `not applicable` would skip the candidate, revision and
    subject checks, so a PR could open its gate with no substantive answer at
    all. The justification must not matter: a defended excuse is still an
    excuse, which is why this holds with and without one.

    The case is selected by `kind` rather than by a ``None`` sentinel in a
    pre-built dict: the sentinel made the parameter's meaning depend on a
    field's value, and the dict hid which assessment was under test.

    The applicable proof case names an inventory, because otherwise the
    empty-inventory precondition would refuse it first and the excuse would
    never be reached. Without that, the test would still pass while asserting
    nothing about the rule it is named for.
    """
    justification = "I will not assess this." if justified else ""
    excuse = {"verdict": NOT_APPLICABLE, "justification": justification}
    if kind == "completeness":
        completeness_verdict = completeness(**excuse)
        proof_verdict, applies = proof(), {"proof_applies": False}
        accepted = candidate()
    else:
        completeness_verdict = completeness()
        proof_verdict, applies = proof(**excuse), {"proof_applies": True}
        accepted = candidate(required_proofs=(THEOREM,))
    decision = readiness(
        accepted, completeness_verdict, proof_verdict, **applies
    )
    assert not decision.ready, "an applicable assessment excused itself"
    assert decision.reason == reason


@pytest.mark.parametrize(
    "verdict",
    ["acknowledged", "posted", "answered", "substantially complete"],
)
def test_an_unrecognized_verdict_is_not_settled(verdict: str) -> None:
    """Only the four documented verdicts settle an assessment."""
    decision = readiness(
        candidate(),
        Verdict(verdict=verdict, base=BASE, head=HEAD,
                plan_revision=REVISION, echoed_revision=REVISION),
        proof(),
    )
    assert not decision.ready
    assert decision.reason == "assessment-unrecognized-verdict"


@pytest.mark.parametrize(
    ("ci_green", "codescene_clear", "reason"),
    [
        (False, True, "ci-not-green"),
        (True, False, "codescene-not-clear"),
        (False, False, "ci-not-green"),
    ],
    ids=["red-ci", "open-codescene", "both"],
)
def test_the_delivery_gates_precede_the_assessments(
    ci_green: bool, codescene_clear: bool, reason: str
) -> None:
    """Green CI and clear CodeScene findings come before any ready transition."""
    decision = readiness(
        candidate(ci_green=ci_green, codescene_clear=codescene_clear),
        completeness(verdict=PENDING),
        proof(),
    )
    assert not decision.ready
    assert decision.reason == reason, "delivery gates must be checked first"


@pytest.mark.parametrize(("reason", "citation"), sorted(REASON_CITATIONS.items()))
def test_each_readiness_reason_cites_a_sentence_in_the_shipped_documents(
    reason: str, citation: str
) -> None:
    """No reason may outlive the prose that states it."""
    documents = normalize(SKILL.read_text()) + " " + normalize(ASSESSMENT.read_text())
    assert normalize(citation) in documents, (
        f"reason {reason!r} cites a sentence no shipped document states: {citation}"
    )


#: One candidate and verdict pair per reason the model can return. Every entry
#: is a state, so the coverage test can require the model to produce exactly
#: the cited reasons rather than a sample of them.
REASON_STATES = {
    "ci-not-green": (candidate(ci_green=False), completeness(), proof()),
    "codescene-not-clear": (
        candidate(codescene_clear=False), completeness(), proof()
    ),
    "assessment-unrecognized-verdict": (
        candidate(),
        Verdict(verdict="acknowledged", base=BASE, head=HEAD),
        proof(),
    ),
    "not-applicable-undefended": (
        candidate(),
        completeness(),
        proof(verdict=NOT_APPLICABLE, justification="  "),
    ),
    "completeness-pending": (
        candidate(), completeness(verdict=PENDING), proof()
    ),
    "completeness-declared-not-applicable": (
        candidate(),
        completeness(verdict=NOT_APPLICABLE, justification="I will not assess this."),
        proof(),
    ),
    "completeness-not-clear": (
        candidate(), completeness(verdict=NOT_CLEAR), proof()
    ),
    "completeness-candidate-mismatch": (
        candidate(), completeness(bounds=bound(head="superseded-head")), proof()
    ),
    "completeness-superseded-revision": (
        candidate(), completeness(bounds=bound(revision="rev-previous", echoed="rev-previous")),
        proof(),
    ),
    "completeness-revision-unbound": (
        candidate(), completeness(bounds=bound(echoed=None)), proof()
    ),
    "completeness-revision-absent": (
        candidate(revision=None),
        completeness(bounds=bound(revision=None, echoed=None)),
        proof(verdict=NOT_APPLICABLE, bounds=bound(revision=None, echoed=None)),
    ),
    "completeness-subject-unrecognized": (
        candidate(), completeness(subject="declared-scope"), proof()
    ),
    "completeness-declared-subset-does-not-clear": (
        candidate(), completeness(subject=DECLARED_SUBSET), proof()
    ),
    "proof-pending": (
        candidate(required_proofs=(THEOREM,)),
        completeness(),
        proof(verdict=PENDING, justification=""),
        {"proof_applies": True},
    ),
    "proof-declared-not-applicable": (
        candidate(required_proofs=(THEOREM,)),
        completeness(),
        proof(verdict=NOT_APPLICABLE, justification="No proofs are affected."),
        {"proof_applies": True},
    ),
    "proof-not-clear": (
        candidate(), completeness(), proof(verdict=NOT_CLEAR, justification="")
    ),
    "proof-candidate-mismatch": (
        candidate(), completeness(), proof(verdict=CLEAR, bounds=bound(head="superseded-head"))
    ),
    "proof-superseded-revision": (
        candidate(), completeness(),
        proof(verdict=CLEAR, bounds=bound(revision="rev-previous", echoed="rev-previous")),
    ),
    "proof-revision-unbound": (
        candidate(), completeness(), proof(verdict=CLEAR, bounds=bound(echoed=None))
    ),
    "proof-inventory-incomplete": (
        candidate(required_proofs=(THEOREM,)),
        completeness(),
        proof(verdict=CLEAR),
        {"proof_applies": True},
    ),
    "proof-inventory-empty": (
        candidate(),
        completeness(),
        proof(verdict=CLEAR),
        {"proof_applies": True},
    ),
    "ready": (candidate(), completeness(), proof()),
}


def _decide(state: tuple) -> readiness_module.Readiness:
    """Decide one ``REASON_STATES`` entry, applying any applicability flags.

    An entry is ``(candidate, completeness, proof)``, or the same with a final
    mapping of keyword arguments. Only the assignments that require a proof
    assessment pass the mapping, so most entries stay plain three-tuples.
    """
    pull, completeness_verdict, proof_verdict, *rest = state
    return readiness(
        pull, completeness_verdict, proof_verdict, **(rest[0] if rest else {})
    )


def test_the_model_produces_exactly_the_reasons_it_cites() -> None:
    """Every cited reason is reachable, and no other reason is returned."""
    produced = {reason: _decide(state).reason for reason, state in REASON_STATES.items()}
    wrong = {reason: got for reason, got in produced.items() if got != reason}
    assert not wrong, f"states produced a different reason: {wrong}"
    assert set(produced) == set(REASON_CITATIONS), (
        "cited reasons and reachable reasons must match: "
        f"{sorted(set(produced) ^ set(REASON_CITATIONS))}"
    )
    assert set(readiness_module.REASONS) == set(REASON_CITATIONS)


@pytest.mark.parametrize("reason", sorted(REASON_CITATIONS))
def test_dropping_any_single_citation_is_detected(reason: str) -> None:
    """No citation can be deleted without failing the model's own check."""
    reduced = {
        key: value for key, value in REASON_CITATIONS.items() if key != reason
    }
    assert set(REASON_STATES) != set(reduced), (
        f"dropping {reason!r} would leave the reachable reasons unchanged"
    )
    real_state = REASON_STATES[reason]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(readiness_module, "REASON_CITATIONS", reduced)
        monkeypatch.setattr(readiness_module, "REASONS", frozenset(reduced))
        with pytest.raises(AssertionError):
            _decide(real_state)


def test_the_readiness_section_states_the_transition_under_assessment() -> None:
    """The prose and the model agree on where the gate sits in the lifecycle."""
    readiness_text = normalize(raw_section(ASSESSMENT.read_text(), "Readiness and later changes"))
    assert "before its draft-to-ready transition" in readiness_text, (
        "readiness gate must still precede the draft-to-ready transition"
    )
    assert "An already-ready PR stays ready; obtain missing assessments before merge" in readiness_text, (
        "a blocked gate must not return the PR to draft"
    )
    assert re.search(r"Do not set the PR back to draft", readiness_text), (
        "readiness section must keep the redrafting prohibition"
    )


def test_readiness_model_names_the_completeness_and_proof_kinds() -> None:
    """The model's assessment kinds match the two documented assessments."""
    assert (COMPLETENESS, PROOF) == ("completeness", "proof")


def _subject_accepting_declared_subset(
    subject: Verdict, applies: bool
) -> readiness_module.Readiness | None:
    """Let the recorded subset clear, but keep rejecting unknown subjects."""
    if subject.verdict == NOT_APPLICABLE or subject.subject in SUBJECTS:
        return None
    return _real_subject(subject, applies)


def _subject_accepting_any_subject(_subject: Verdict, applies: bool) -> None:
    """Drop the subject rule entirely, as a widened gate would."""


DEFECTIVE_RULES = (
    pytest.param(
        "_subject",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_subject", _subject_accepting_declared_subset
        ),
        (candidate(), completeness(subject=DECLARED_SUBSET), proof()),
        "completeness-declared-subset-does-not-clear",
        id="declared-subset-accepted",
    ),
    pytest.param(
        "_subject",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_subject", _subject_accepting_any_subject
        ),
        (candidate(), completeness(subject="declared-scope"), proof()),
        "completeness-subject-unrecognized",
        id="unrecognized-subject-accepted",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, reason: None
        ),
        (candidate(), completeness(bounds=bound(revision="rev-previous", echoed="rev-previous")),
         proof()),
        "completeness-superseded-revision",
        id="revision-binding-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand, applies: (
                None
                if kind == PROOF
                else _real_disposition(verdict, kind, cand, applies)
            ),
        ),
        (candidate(), completeness(), proof(verdict=PENDING, justification="")),
        "proof-pending",
        id="proof-disposition-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand, applies: (
                None
                if verdict.verdict == NOT_CLEAR
                else _real_disposition(verdict, kind, cand, applies)
            ),
        ),
        (candidate(), completeness(verdict=NOT_CLEAR), proof()),
        "completeness-not-clear",
        id="not-clear-treated-as-settled",
    ),
    pytest.param(
        "delivery_gate",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "delivery_gate",
            lambda cand: (
                _real_delivery_gates(cand)
                if not cand.codescene_clear
                else None
            ),
        ),
        (candidate(ci_green=False), completeness(), proof()),
        "ci-not-green",
        id="ci-gate-dropped",
    ),
    pytest.param(
        "delivery_gate",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "delivery_gate",
            lambda cand: (
                _real_delivery_gates(cand) if not cand.ci_green else None
            ),
        ),
        (candidate(codescene_clear=False), completeness(), proof()),
        "codescene-not-clear",
        id="codescene-gate-dropped",
    ),
    pytest.param(
        "VERDICTS",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "VERDICTS", (*readiness_module.VERDICTS, "acknowledged")
        ),
        (candidate(),
         Verdict(verdict="acknowledged", base=BASE, head=HEAD,
                 plan_revision=REVISION, echoed_revision=REVISION),
         proof()),
        "assessment-unrecognized-verdict",
        id="unrecognized-verdict-accepted",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, kind: None
        ),
        (candidate(), completeness(), proof(verdict=CLEAR, bounds=bound(echoed=None))),
        "proof-revision-unbound",
        id="proof-revision-binding-dropped",
    ),
    pytest.param(
        "proof_request",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "proof_request",
            # Drops only the empty-inventory rule, the way a model that read
            # an unnamed inventory as nothing to compare would: every listed
            # proof is trivially covered when none is listed.
            lambda _cand, _applies: None,
        ),
        (candidate(), completeness(), proof(verdict=CLEAR, proofs=(THEOREM,)),
         {"proof_applies": True}),
        "proof-inventory-empty",
        id="empty-inventory-accepted",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, kind: None
        ),
        (candidate(), completeness(bounds=bound(echoed=None)), proof()),
        "completeness-revision-unbound",
        id="completeness-echo-binding-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand, applies: (
                None
                if verdict.verdict == NOT_APPLICABLE
                and not verdict.justification.strip()
                else _real_disposition(verdict, kind, cand, applies)
            ),
        ),
        (candidate(), completeness(), proof(verdict=NOT_APPLICABLE, justification="  ")),
        "not-applicable-undefended",
        id="undefended-not-applicable-accepted",
    ),
    pytest.param(
        "applicability",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            # Ignores `applies`, the way a model that trusted the reply would:
            # any defended `not applicable` settles the assessment.
            lambda verdict, kind, cand, applies: (
                None
                if verdict.verdict == NOT_APPLICABLE and verdict.justification.strip()
                else _real_disposition(verdict, kind, cand, applies)
            ),
        ),
        (
            candidate(),
            completeness(verdict=NOT_APPLICABLE, justification="I will not assess this."),
            proof(),
        ),
        "completeness-declared-not-applicable",
        id="applicable-assessment-excused-itself",
    ),
)
_real_disposition = readiness_module._disposition
_real_delivery_gates = readiness_module.delivery_gate
_real_subject = readiness_module._subject


@pytest.mark.parametrize(
    ("rule", "defect", "state", "reason"),
    DEFECTIVE_RULES,
)
def test_a_defective_readiness_rule_is_detected_by_its_case(
    rule: str,
    defect: Callable[[pytest.MonkeyPatch], None],
    state: tuple[Candidate, Verdict, Verdict],
    reason: str,
) -> None:
    """Each mutation control proves its case discriminates, not just passes."""
    real = _decide(state)
    assert not real.ready and real.reason == reason, (
        f"{rule} control's case must fail on the real model"
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        defect(monkeypatch)
        mutated = _decide(state)
    assert mutated.ready, (
        f"case {reason!r} does not detect a dropped {rule} rule"
    )
    assert reason in REASON_CITATIONS, (
        f"mutation control cites an uncited reason: {reason}"
    )
