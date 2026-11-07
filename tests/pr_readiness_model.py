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
    only and never clears the gate.
    """

    verdict: str
    base: str
    head: str
    plan_revision: str | None = None
    echoed_revision: str | None = None
    subject: str = WHOLE_PLAN
    justification: str = ""


@dataclass(frozen=True)
class Candidate:
    """The accepted candidate and its approved plan revision.

    ``approved_plan_revision`` is ``None`` for an assignment no ExecPlan
    governs. ``ci_green`` and ``codescene_clear`` are the other two documented
    pre-readiness gates: readiness needs green CI and clear CodeScene findings
    as well as the assessments, so the model refuses to mark a candidate ready
    without them.
    """

    base: str
    head: str
    approved_plan_revision: str | None = None
    ci_green: bool = True
    codescene_clear: bool = True


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


def _disposition(
    verdict: Verdict, kind: str, candidate: Candidate
) -> Readiness | None:
    """Return the decision that blocks readiness for an unsettled assessment.

    Parameters
    ----------
    verdict : Verdict
        The assessment verdict under test.
    kind : str
        ``completeness`` or ``proof``, selecting the reason codes.
    candidate : Candidate
        The accepted candidate the verdict must cover.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the verdict is settled.
    """
    if verdict.verdict not in VERDICTS:
        return _decision("assessment-unrecognized-verdict")
    if verdict.verdict == NOT_APPLICABLE:
        if not verdict.justification.strip():
            return _decision("not-applicable-undefended")
        return None
    if verdict.verdict == PENDING:
        return _decision(f"{kind}-pending")
    if verdict.verdict == NOT_CLEAR:
        return _decision(f"{kind}-not-clear")
    if (verdict.base, verdict.head) != (candidate.base, candidate.head):
        return _decision(f"{kind}-candidate-mismatch")
    return None


def _subject(subject: Verdict) -> Readiness | None:
    """Reject a subject that is not the whole approved plan.

    The ledger records either the whole plan or a declared subset, and only the
    whole plan clears: a subset verdict is evidence for its actual scope, so a
    managed-stack layer records one without being able to leave draft on it.
    An unrecognized subject is not a documented record at all.

    Parameters
    ----------
    subject : Verdict
        The completeness verdict, whose subject bounds what it assessed.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the subject is the whole plan.
    """
    if subject.verdict == NOT_APPLICABLE:
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
) -> Readiness:
    """Decide whether the accepted candidate may leave draft.

    The documented order is green CI and clear CodeScene findings, substantive
    assessment replies, then the verified ready transition, so the two delivery
    gates are checked before any assessment. An assessment established as
    ``not applicable`` has no reply to bind, so it is skipped rather than
    subjected to the candidate and revision checks.

    Parameters
    ----------
    candidate : Candidate
        The accepted base/head, approved plan revision, and delivery-gate state.
    completeness : Verdict
        The completeness assessment's verdict, subject, and candidate.
    proof : Verdict
        The proof assessment's verdict, or a justified ``not applicable``.

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
    for kind, verdict in ((COMPLETENESS, completeness), (PROOF, proof)):
        blocked = _disposition(verdict, kind, candidate)
        if blocked is not None:
            return blocked
        if verdict.verdict == NOT_APPLICABLE:
            continue
        blocked = _revision_bound(verdict, candidate, kind)
        if blocked is not None:
            return blocked
    blocked = _subject(completeness)
    if blocked is not None:
        return blocked
    return _cleared()
