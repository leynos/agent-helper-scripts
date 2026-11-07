"""Executable specification of the documented draft-to-ready readiness gate.

The skills are prose: no program in this repository decides readiness. This
module restates the gate the skills state as a small decision model, so the
contract tests can exercise the agent workflow boundary with candidate-bound
verdicts, subjects and plan revisions instead of only matching sentences.

It is a specification rehearsal, not skill enforcement. Every reason it can
return cites the sentence that states the rule, and
``test_pr_readiness_model.py`` requires that sentence to remain in the shipped
documents, so the model cannot quietly outlive the prose it encodes. Nothing
here talks to GitHub, posts a comment, or moves a PR out of draft.
"""

from __future__ import annotations

from dataclasses import dataclass

CLEAR = "clear"
NOT_CLEAR = "not clear"
PENDING = "pending"
NOT_APPLICABLE = "not applicable"

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
    managed stack rather than ordinary single-PR delivery.
    """

    base: str
    head: str
    approved_plan_revision: str | None = None
    stack_layer: StackLayer | None = None


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
    "completeness-whole-plan-required": (
        "Ordinary single-PR delivery and the layer carrying the plan's"
        " remainder keep the whole approved plan as the subject."
    ),
    "completeness-stack-evidence-missing": (
        "name the layer's milestones, the `github-stacks` parent it builds on,"
        " and the milestones remaining above it"
    ),
    "completeness-superseded-revision": (
        "a verdict recorded against a revision that has since been superseded"
        " by a newly approved revision does not clear the gate, even when the"
        " base/head is unchanged"
    ),
    "proof-superseded-revision": (
        "a verdict recorded against a revision that has since been superseded"
        " by a newly approved revision does not clear the gate, even when the"
        " base/head is unchanged"
    ),
    "completeness-revision-unbound": (
        "a reply that echoes only the base/head does not establish which"
        " revision was inspected"
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
    "proof-revision-unbound": (
        "a proof request under an ExecPlan must also name and echo the revision"
    ),
    "not-applicable-undefended": (
        "with a justified `not applicable` for an assessment that does not apply"
    ),
    "ready": (
        "Only when CI is green, CodeScene is clear, and all applicable"
        " pre-readiness assessments hold for the accepted base/head"
    ),
}


def _decision(reason: str) -> Readiness:
    """Return the draft-preserving decision for one blocked reason."""
    return Readiness(ready=False, reason=reason)


def _revision_bound(verdict: Verdict, candidate: Candidate, reason: str) -> Readiness | None:
    """Reject a verdict that is not bound to the revision in force.

    Parameters
    ----------
    verdict : Verdict
        The assessment verdict under test.
    candidate : Candidate
        The accepted candidate whose approved revision is in force.
    reason : str
        Reason code to report when the verdict names another revision.

    Returns
    -------
    Readiness or None
        A draft-preserving decision, or None when the verdict is bound.
    """
    if candidate.approved_plan_revision is None:
        return None
    if verdict.plan_revision != candidate.approved_plan_revision:
        return _decision(f"{reason}-superseded-revision")
    if verdict.echoed_revision != candidate.approved_plan_revision:
        return _decision(f"{reason}-revision-unbound")
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
        A draft-preserving decision, or None when the verdict has settled.
    """
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
    if subject.subject == WHOLE_PLAN:
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

    Parameters
    ----------
    candidate : Candidate
        The accepted base/head, approved plan revision, and stack topology.
    completeness : Verdict
        The completeness assessment's verdict, subject, and candidate.
    proof : Verdict
        The proof assessment's verdict, or a justified ``not applicable``.

    Returns
    -------
    Readiness
        ``ready`` only when every applicable assessment holds for the accepted
        candidate; otherwise ``stay draft`` with the deciding rule's reason.
    """
    for kind, verdict in ((COMPLETENESS, completeness), (PROOF, proof)):
        blocked = _disposition(verdict, kind, candidate)
        if blocked is not None:
            return blocked
        blocked = _revision_bound(verdict, candidate, kind)
        if blocked is not None:
            return blocked
    blocked = _subject(completeness, candidate)
    if blocked is not None:
        return blocked
    return Readiness(ready=True, reason="ready")
