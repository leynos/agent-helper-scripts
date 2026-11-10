"""Executable specification of the documented draft-to-ready readiness gate.

The skills are prose: no program in this repository decides readiness. This
module restates the gate the skills state as a small decision model, so the
contract tests can exercise the agent workflow boundary with candidate-bound
verdicts, subjects and plan revisions instead of only matching sentences.

It is a specification rehearsal, not skill enforcement. Every reason it can
return appears in ``REASONS`` and cites the sentence that states the rule, and
``test_pr_readiness_model.py`` requires both to stay in step with the shipped
documents, so the model cannot quietly outlive the prose it encodes. Nothing
here talks to GitHub, posts a comment, or moves a PR out of draft; the
lifecycle double in ``pr_readiness_workflow`` supplies those surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass

CLEAR = "clear"
NOT_CLEAR = "not clear"
PENDING = "pending"
NOT_APPLICABLE = "not applicable"

VERDICTS = (CLEAR, NOT_CLEAR, PENDING, NOT_APPLICABLE)

READY = "ready"
STAY_DRAFT = "stay draft"

#: The ledger records either of these subjects; only the whole plan clears.
WHOLE_PLAN = "whole-plan"
DECLARED_SUBSET = "declared-subset"

SUBJECTS = (WHOLE_PLAN, DECLARED_SUBSET)

COMPLETENESS = "completeness"
PROOF = "proof"


@dataclass(frozen=True)
class Verdict:
    """One assessment verdict with the candidate and subject it was given for.

    ``echoed_revision`` is the plan revision the substantive reply itself
    echoed, which is what binds the verdict to a revision rather than to a
    base/head alone. It stays ``None`` for an assessment with no ExecPlan.
    ``subject`` is the ledger's record of what the verdict covered: the whole
    approved plan, or a declared subset that is evidence for its actual scope
    only and never clears the gate. For a proof assessment it is the named
    proofs the reply says it assessed, which ``readiness`` compares with the
    candidate's proof inventory.
    """

    verdict: str
    base: str
    head: str
    plan_revision: str | None = None
    echoed_revision: str | None = None
    subject: str = WHOLE_PLAN
    justification: str = ""
    proofs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Candidate:
    """The accepted candidate and its approved plan revision.

    ``approved_plan_revision`` is ``None`` for an assignment no ExecPlan
    governs. ``ci_green`` and ``codescene_clear`` are the other two documented
    pre-readiness gates: readiness needs green CI and clear CodeScene findings
    as well as the assessments, so the model refuses to mark a candidate ready
    without them.

    ``required_proofs`` is the proof inventory the assignment's request names.
    A clear proof verdict must cover every entry: a reply that clears the proof
    assessment without saying which proofs it assessed does not establish what
    the gate asks, which is that the listed proofs are substantive.
    """

    base: str
    head: str
    approved_plan_revision: str | None = None
    ci_green: bool = True
    codescene_clear: bool = True
    required_proofs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Readiness:
    """The draft-to-ready decision and the rule that produced it."""

    ready: bool
    reason: str

    def __bool__(self) -> bool:
        """Allow a decision to be tested directly, as in ``if readiness(...)``."""
        return self.ready


#: The sentence in the shipped documents that states each decision's rule.
#: Contract tests assert these remain present, so a reason cannot outlive it.
REASON_CITATIONS = {
    "ci-not-green": (
        "Only when CI is green, CodeScene is clear, and all applicable"
        " pre-readiness assessments hold for the accepted base/head"
    ),
    "codescene-not-clear": (
        "Only when CI is green, CodeScene is clear, and all applicable"
        " pre-readiness assessments hold for the accepted base/head"
    ),
    "assessment-unrecognized-verdict": (
        "A verdict of `clear`, `not clear`, or `pending`, with a justified"
        " `not applicable` for an assessment that does not apply."
    ),
    "not-applicable-undefended": (
        "with a justified `not applicable` for an assessment that does not apply"
    ),
    "completeness-pending": (
        "Both applicable assessments must clear for the accepted candidate"
        " before its draft-to-ready transition."
    ),
    "completeness-declared-not-applicable": (
        "with a justified `not applicable` for an assessment that does not"
        " apply"
    ),
    "completeness-not-clear": (
        "A response that says the implementation is substantially complete but"
        " names remaining in-scope defects has not cleared the gate."
    ),
    "completeness-candidate-mismatch": (
        "Both applicable assessments must clear for the accepted candidate"
        " before its draft-to-ready transition."
    ),
    "completeness-superseded-revision": (
        "a verdict recorded against a revision that has since been superseded"
        " by a newly approved revision does not clear the gate, even when the"
        " base/head is unchanged"
    ),
    "completeness-revision-unbound": (
        "a reply that echoes only the base/head does not establish which"
        " revision was inspected"
    ),
    "completeness-subject-unrecognized": (
        "The completeness assessment's subject is recorded as either the whole"
        " plan or the declared subset"
    ),
    "completeness-declared-subset-does-not-clear": (
        "only the whole approved plan clears the gate, and a declared-subset"
        " verdict is evidence for its actual scope only"
    ),
    "proof-pending": (
        "When the proof assessment applies, readiness also requires its clear"
        " verdict for the same base/head;"
    ),
    "proof-declared-not-applicable": (
        "When the proof assessment applies, readiness also requires its clear"
        " verdict for the same base/head;"
    ),
    "proof-not-clear": (
        "When the proof assessment applies, readiness also requires its clear"
        " verdict for the same base/head;"
    ),
    "proof-candidate-mismatch": (
        "When the proof assessment applies, readiness also requires its clear"
        " verdict for the same base/head;"
    ),
    "proof-superseded-revision": (
        "a verdict recorded against a revision that has since been superseded"
        " by a newly approved revision does not clear the gate, even when the"
        " base/head is unchanged"
    ),
    "proof-revision-unbound": (
        "a proof request under an ExecPlan must also name and echo the revision"
    ),
    "proof-inventory-incomplete": (
        "Require an explicit satisfactory assessment of the listed proofs with"
        " no unresolved substantive proof concern."
    ),
    "proof-inventory-empty": (
        "record a justified `not applicable` instead of posting an empty"
        " inventory or creating a ceremonial proof"
    ),
    "ready": (
        "Only when CI is green, CodeScene is clear, and all applicable"
        " pre-readiness assessments hold for the accepted base/head"
    ),
}
REASONS = frozenset(REASON_CITATIONS)


def delivery_gate(candidate: Candidate) -> Readiness | None:
    """Reject a candidate whose CI or CodeScene state blocks readiness.

    The documented order is green CI and clear CodeScene findings, substantive
    assessment replies, then verified readiness, so the workflow sequence asks
    this before it posts an assessment question. ``readiness()`` asks it too,
    because a decision that assumed an unasked question would accept facts the
    sequence had never established.

    Parameters
    ----------
    candidate : Candidate
        The accepted candidate and its delivery-gate state.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when both gates hold.
    """
    if not candidate.ci_green:
        return _decision("ci-not-green")
    if not candidate.codescene_clear:
        return _decision("codescene-not-clear")
    return None


def _decision(reason: str) -> Readiness:
    """Return the draft-preserving decision for one blocked reason.

    Parameters
    ----------
    reason : str
        One key of ``REASON_CITATIONS``.

    Returns
    -------
    Readiness
        ``stay draft``, carrying the reason.

    Raises
    ------
    AssertionError
        Raised when the reason has no citation, which would let a rule enter
        the model without a sentence that states it.
    """
    assert reason in REASONS, f"uncited readiness reason: {reason}"
    return Readiness(ready=False, reason=reason)


def _cleared() -> Readiness:
    """Return the ready decision, which is cited like every blocking reason.

    Returns
    -------
    Readiness
        ``ready``, the one decision that permits the draft-to-ready transition.

    Raises
    ------
    AssertionError
        Raised when the ready outcome has lost its citation, so the citation
        check would otherwise pass while the shipped rule went unrecorded.
    """
    assert "ready" in REASONS, "uncited readiness reason: ready"
    return Readiness(ready=True, reason="ready")


def _revision_bound(verdict: Verdict, candidate: Candidate, kind: str) -> Readiness | None:
    """Reject a verdict that is not bound to the revision in force.

    Parameters
    ----------
    verdict : Verdict
        The assessment verdict under test, already settled as clear.
    candidate : Candidate
        The accepted candidate whose approved revision is in force.
    kind : str
        ``completeness`` or ``proof``, selecting the reason codes.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the verdict is bound.
    """
    if candidate.approved_plan_revision is None:
        return None
    if verdict.plan_revision != candidate.approved_plan_revision:
        return _decision(f"{kind}-superseded-revision")
    if verdict.echoed_revision != candidate.approved_plan_revision:
        return _decision(f"{kind}-revision-unbound")
    return None


#: The two verdicts that leave an assessment unsettled, keyed to the reason
#: suffix each produces. Both block readiness in the same way, so they share
#: one decision path rather than repeating the shape.
_UNSETTLED = {PENDING: "pending", NOT_CLEAR: "not-clear"}


def _not_applicable(verdict: Verdict, kind: str, applies: bool) -> Readiness | None:
    """Return the decision for a reply that declares its assessment inapplicable.

    Applicability is the assignment's to decide, so a reply that declares an
    applicable assessment ``not applicable`` is a scope narrowing and holds the
    gate. An inapplicable assessment is recorded either way; an undefended one
    is not a documented record at all.

    Parameters
    ----------
    verdict : Verdict
        The assessment verdict under test.
    kind : str
        ``completeness`` or ``proof``, selecting the reason code.
    applies : bool
        Whether the assignment requires this assessment.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the reply is defended.
    """
    if applies:
        return _decision(f"{kind}-declared-not-applicable")
    if verdict.justification.strip():
        return None
    return _decision("not-applicable-undefended")


def _disposition(
    verdict: Verdict, kind: str, candidate: Candidate, applies: bool
) -> Readiness | None:
    """Return the decision that blocks readiness for an unsettled assessment.

    Applicability is decided by the assignment, never by the reply. A reply
    that declares an applicable assessment ``not applicable`` would otherwise
    skip the candidate, revision and subject checks and open the gate with no
    substantive answer at all, which is the defect the rule exists to prevent.

    Parameters
    ----------
    verdict : Verdict
        The assessment verdict under test.
    kind : str
        ``completeness`` or ``proof``, selecting the reason codes.
    candidate : Candidate
        The accepted candidate the verdict must cover.
    applies : bool
        Whether the assignment requires this assessment. Only an inapplicable
        assessment may be recorded as ``not applicable``.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the verdict is settled.
    """
    if verdict.verdict not in VERDICTS:
        return _decision("assessment-unrecognized-verdict")
    if verdict.verdict == NOT_APPLICABLE:
        return _not_applicable(verdict, kind, applies)
    if (suffix := _UNSETTLED.get(verdict.verdict)) is not None:
        return _decision(f"{kind}-{suffix}")
    if (verdict.base, verdict.head) != (candidate.base, candidate.head):
        return _decision(f"{kind}-candidate-mismatch")
    return None


def proof_request(candidate: Candidate, applies: bool) -> Readiness | None:
    """Reject an applicable proof assessment that names no inventory.

    The published question carries the proofs it asks about. An assignment
    that requires the assessment but names none has nothing to publish: the
    documents give exactly two routes when no proof is affected — record a
    justified ``not applicable``, or list the proofs a newly introduced one
    affects — and an empty inventory is neither.

    This is asked before the question is posted, not after its reply arrives.
    Posting it would spend the assessor's reply on a question with no subject,
    and the reply cannot repair the omission: a list it supplied itself would
    be answering a different question from the one the assignment meant to
    ask.

    Parameters
    ----------
    candidate : Candidate
        The accepted candidate, carrying the inventory the request would name.
    applies : bool
        Whether the assignment requires a proof assessment.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when a request may be posted.
    """
    if applies and not candidate.required_proofs:
        return _decision("proof-inventory-empty")
    return None


def _proof_inventory(verdict: Verdict, candidate: Candidate, applies: bool) -> Readiness | None:
    """Reject a proof verdict that does not cover the listed proofs.

    The proof request names an inventory, and the gate asks that those proofs
    are substantive. A reply that clears the assessment without naming them
    answers a question that was never asked, and a reply that covers some of
    them leaves the rest unassessed while still leaving draft.

    An assignment that requires a proof assessment must also name an inventory.
    The documents offer exactly two routes when no proof is affected: say the
    assessment does not apply, or list the proofs a newly introduced one
    affects. An applicable proof assessment with nothing listed is neither, so
    it is a request nobody could answer rather than a clear gate. That
    precondition is checked by ``readiness`` before any reply is read, because
    a reply cannot supply the inventory an assignment never named and a reply
    carrying its own is not evidence of what the request asked.

    Parameters
    ----------
    verdict : Verdict
        The proof assessment's verdict.
    candidate : Candidate
        The accepted candidate, carrying the proof inventory the request named.
    applies : bool
        Whether the assignment requires a proof assessment.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when every listed proof is covered.
    """
    if not applies or verdict.verdict == NOT_APPLICABLE:
        return None
    missing = [proof for proof in candidate.required_proofs if proof not in verdict.proofs]
    if missing:
        return _decision("proof-inventory-incomplete")
    return None


def _subject(subject: Verdict, applies: bool) -> Readiness | None:
    """Reject a subject that is not the whole approved plan.

    The ledger records either the whole plan or a declared subset, and only the
    whole plan clears: a subset verdict is evidence for its actual scope, so a
    managed-stack layer records one without being able to leave draft on it.
    An unrecognized subject is not a documented record at all. The whole-plan
    requirement applies only to the completeness assessment; a proof
    assessment's subject is its named proofs, which ``_proof_inventory`` has
    already compared with the request's inventory.

    Parameters
    ----------
    subject : Verdict
        The completeness verdict, whose subject bounds what it assessed.
    applies : bool
        Whether the completeness assessment applies to this assignment.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the subject is the whole plan.
    """
    if not applies or subject.verdict == NOT_APPLICABLE:
        return None
    if subject.subject == WHOLE_PLAN:
        return None
    if subject.subject not in SUBJECTS:
        return _decision("completeness-subject-unrecognized")
    return _decision("completeness-declared-subset-does-not-clear")


def readiness(
    candidate: Candidate,
    completeness: Verdict,
    proof: Verdict,
    *,
    completeness_applies: bool = True,
    proof_applies: bool = False,
) -> Readiness:
    """Decide whether the accepted candidate may leave draft.

    The documented order is green CI and clear CodeScene findings, substantive
    assessment replies, then the verified ready transition, so the two delivery
    gates are checked before any assessment. An assessment established as
    ``not applicable`` has no reply to bind, so it is skipped rather than
    subjected to the candidate and revision checks.

    Applicability comes from the assignment, not from the verdicts. The
    defaults are the ordinary ExecPlan implementation assignment: completeness
    applies and no proof does. A caller that hands the model a proof assessment
    must say so with ``proof_applies``, because otherwise a reply declaring
    itself ``not applicable`` would clear a gate the assignment requires.

    Parameters
    ----------
    candidate : Candidate
        The accepted base/head, approved plan revision, and delivery-gate state.
    completeness : Verdict
        The completeness assessment's verdict, subject, and candidate.
    proof : Verdict
        The proof assessment's verdict, or a justified ``not applicable``.
    completeness_applies : bool
        Whether the assignment requires a completeness assessment.
    proof_applies : bool
        Whether the assignment requires a proof assessment. A proof-only
        assignment sets this, since it has no ExecPlan to assess instead.

    Returns
    -------
    Readiness
        ``ready`` only when both delivery gates hold and every applicable
        assessment is settled for the accepted candidate; otherwise
        ``stay draft`` with the deciding rule's reason.
    """
    blocked = delivery_gate(candidate)
    if blocked is not None:
        return blocked
    # The proof request's subject is checked before any reply is read: a
    # reply cannot supply the inventory an assignment never named.
    blocked = proof_request(candidate, proof_applies)
    if blocked is not None:
        return blocked
    blocked = _settled(
        candidate,
        completeness,
        proof,
        completeness_applies=completeness_applies,
        proof_applies=proof_applies,
    )
    if blocked is not None:
        return blocked
    blocked = _subject(completeness, completeness_applies)
    if blocked is not None:
        return blocked
    return _cleared()


def _settled(
    candidate: Candidate,
    completeness: Verdict,
    proof: Verdict,
    *,
    completeness_applies: bool,
    proof_applies: bool,
) -> Readiness | None:
    """Return the first assessment that does not settle, or None if both do.

    The checks run in the documented order for each assessment: an applicable
    assessment may not excuse itself, a substantive verdict must be bound to
    the accepted candidate and the revision in force, and a proof verdict must
    cover the inventory the request named. An assessment established as ``not
    applicable`` has no reply to bind, so it is skipped after its disposition.

    The applicability flags are keyword-only. They are two booleans of the same
    type sitting next to each other, so a positional call site can transpose
    them and still read as correct: the candidate would then be judged against
    the proof's applicability and vice versa, with no error raised. Naming them
    at every call makes that transposition impossible to write by accident.

    The helpers are resolved by name at call time, so a module-attribute
    override still replaces the check it names.
    """
    for kind, verdict, applies in (
        (COMPLETENESS, completeness, completeness_applies),
        (PROOF, proof, proof_applies),
    ):
        blocked = _disposition(verdict, kind, candidate, applies)
        if blocked is not None:
            return blocked
        if verdict.verdict == NOT_APPLICABLE:
            continue
        blocked = _revision_bound(verdict, candidate, kind)
        if blocked is not None:
            return blocked
        if kind == PROOF:
            blocked = _proof_inventory(verdict, candidate, applies)
            if blocked is not None:
                return blocked
    return None
