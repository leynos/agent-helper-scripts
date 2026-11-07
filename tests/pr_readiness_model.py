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

WHOLE_PLAN = "whole-plan"
DECLARED_SUBSET = "declared-subset"

COMPLETENESS = "completeness"
PROOF = "proof"


@dataclass(frozen=True)
class StackLayer:
    """The topology a declared-subset verdict must name to clear its layer.

    A layer clears on a subset only when the stack makes the unimplemented
    milestones demonstrably absent from it, so the evidence names the layer's
    own milestones, the `github-stacks` parent, and the milestones remaining
    above it. An empty ``remaining_above`` means nothing sits above this layer,
    so it carries the plan's remainder and needs the whole-plan verdict.
    """

    milestones: tuple[str, ...]
    parent: str
    remaining_above: tuple[str, ...]
    claims_whole_plan: bool = False

    @property
    def is_final_layer(self) -> bool:
        """Whether nothing sits above this layer, which then carries the rest."""
        return not self.remaining_above

    @property
    def names_its_evidence(self) -> bool:
        """Whether the layer, its parent and the milestones above it are named."""
        return bool(self.milestones) and bool(self.parent)


@dataclass(frozen=True)
class Verdict:
    """One assessment verdict with the candidate and subject it was given for.

    ``echoed_revision`` is the plan revision the substantive reply itself
    echoed, which is what binds the verdict to a revision rather than to a
    base/head alone. It stays ``None`` for an assessment with no ExecPlan.
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
    """The accepted candidate, its approved plan revision, and its stack.

    ``approved_plan_revision`` is ``None`` for an assignment no ExecPlan
    governs. ``stack_layer`` is present only when this PR is one layer of a
    managed stack rather than ordinary single-PR delivery. ``ci_green`` and
    ``codescene_clear`` are the other two documented pre-readiness gates:
    readiness needs green CI and clear CodeScene findings as well as the
    assessments, so the model refuses to mark a candidate ready without them.
    """

    base: str
    head: str
    approved_plan_revision: str | None = None
    stack_layer: StackLayer | None = None
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
    "completeness-whole-plan-required": (
        "Ordinary single-PR delivery and the layer carrying the plan's"
        " remainder keep the whole approved plan as the subject."
    ),
    "completeness-stack-evidence-missing": (
        "name the layer's milestones, the `github-stacks` parent it builds on,"
        " and the milestones remaining above it"
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


def _delivery_gates(candidate: Candidate) -> Readiness | None:
    """Reject a candidate whose CI or CodeScene state blocks readiness.

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


def _subject(subject: Verdict, candidate: Candidate) -> Readiness | None:
    """Reject a declared-subset completeness claim without stack evidence.

    Parameters
    ----------
    subject : Verdict
        The completeness verdict, whose subject bounds what it assessed.
    candidate : Candidate
        The accepted candidate, carrying any stack layer topology.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the subject is admissible.
    """
    if subject.subject == WHOLE_PLAN or subject.verdict == NOT_APPLICABLE:
        return None
    layer = candidate.stack_layer
    if layer is None or layer.claims_whole_plan or layer.is_final_layer:
        return _decision("completeness-whole-plan-required")
    if not layer.names_its_evidence:
        return _decision("completeness-stack-evidence-missing")
    return None


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
        The accepted base/head, approved plan revision, stack topology, and
        delivery-gate state.
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
    blocked = _delivery_gates(candidate)
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
    blocked = _subject(completeness, candidate)
    if blocked is not None:
        return blocked
    return _cleared()
