"""Run the documented readiness sequence against doubles of its surfaces.

``pr_readiness_model`` decides readiness from facts. This module supplies the
sequence around that decision — post the applicable assessment questions, read
their substantive replies, decide, then mark ready only when the gate holds —
against in-memory doubles for GitHub and CodeRabbit.

The doubles follow the order the skills state: green CI and clear CodeScene
findings, substantive assessment replies, then the ready transition. They do
not talk to any network service, and the ready transition is recorded rather
than performed, so a case that marks a PR ready is evidence about the sequence
and not about the live PR.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pr_readiness_model import (
    COMPLETENESS,
    NOT_APPLICABLE,
    PENDING,
    PROOF,
    WHOLE_PLAN,
    Candidate,
    Readiness,
    StackLayer,
    Verdict,
    delivery_gate,
    readiness,
)

CODERABBIT = "coderabbitai[bot]"


@dataclass
class Reply:
    """One substantive assessment reply, as observed in the discussion."""

    assessment_id: str
    author: str
    base: str
    head: str
    verdict: str
    plan_revision: str | None = None
    echoed_revision: str | None = None
    subject: str = WHOLE_PLAN
    named_milestones: tuple[str, ...] = ()
    justification: str = ""


@dataclass
class Discussion:
    """The PR's issue-comment thread and the assessment questions posted to it.

    ``post`` records the question the workflow would publish, and ``observe``
    returns only a correlated reply from the assessment bot, so an unrelated
    comment cannot be mistaken for a verdict.
    """

    base: str
    head: str
    responses: list[Reply] = field(default_factory=list)
    requests: list[dict[str, str]] = field(default_factory=list)

    def post(self, kind: str, assessment_id: str, plan_revision: str | None) -> str:
        """Record one assessment question and return its request marker.

        Parameters
        ----------
        kind : str
            ``completeness`` or ``proof``.
        assessment_id : str
            Unique request marker the reply is expected to echo.
        plan_revision : str or None
            Revision in force, or None when no ExecPlan applies.

        Returns
        -------
        str
            The recorded request marker.
        """
        self.requests.append(
            {"kind": kind, "id": assessment_id, "revision": plan_revision or ""}
        )
        return assessment_id

    def observe(self, assessment_id: str) -> Reply | None:
        """Return the substantive reply echoing ``assessment_id``, if posted.

        Parameters
        ----------
        assessment_id : str
            Request marker to correlate against.

        Returns
        -------
        Reply or None
            The correlated reply, or None while the assessment is pending.
        """
        for reply in self.responses:
            if reply.assessment_id == assessment_id and reply.author == CODERABBIT:
                return reply
        return None


@dataclass
class PullRequest:
    """A PR double holding only the state the readiness sequence reads."""

    base: str
    head: str
    is_draft: bool = True
    ci_green: bool = True
    codescene_clear: bool = True
    approved_plan_revision: str | None = None
    stack_layer: StackLayer | None = None
    ready_transitions: list[str] = field(default_factory=list)

    def mark_ready(self) -> None:
        """Perform the ready transition, refusing a PR that is already ready.

        Raises
        ------
        AssertionError
            Raised when the workflow tries to transition a PR that has left
            draft, which the lifecycle contract forbids.
        """
        assert self.is_draft, "readiness must not re-transition an already-ready PR"
        self.is_draft = False
        self.ready_transitions.append(self.head)

    def candidate(self) -> Candidate:
        """Return the candidate the readiness model reads for this PR.

        Returns
        -------
        Candidate
            The accepted base/head, revision, stack and delivery-gate state.
        """
        return Candidate(
            base=self.base,
            head=self.head,
            approved_plan_revision=self.approved_plan_revision,
            stack_layer=self.stack_layer,
            ci_green=self.ci_green,
            codescene_clear=self.codescene_clear,
        )


def _verdict(
    kind: str, reply: Reply | None, plan_revision: str | None
) -> Verdict:
    """Return the model verdict for one observed reply, or pending without one.

    Parameters
    ----------
    kind : str
        The assessment kind, used only to label a pending verdict.
    reply : Reply or None
        The correlated reply, or None while none has been observed.
    plan_revision : str or None
        Revision in force, recorded on a pending verdict for traceability.

    Returns
    -------
    Verdict
        The reply's verdict, or ``pending`` when no reply is observed.
    """
    if reply is None:
        return Verdict(
            verdict=PENDING,
            base="unobserved",
            head="unobserved",
            plan_revision=plan_revision,
            subject=WHOLE_PLAN,
            justification=f"{kind} request awaiting a substantive reply",
        )
    return Verdict(
        verdict=reply.verdict,
        base=reply.base,
        head=reply.head,
        plan_revision=reply.plan_revision,
        echoed_revision=reply.echoed_revision,
        subject=reply.subject,
        named_milestones=reply.named_milestones,
        justification=reply.justification,
    )


def _not_applicable(reason: str, pull: PullRequest) -> Verdict:
    """Return a justified ``not applicable`` verdict for an inapplicable check.

    Parameters
    ----------
    reason : str
        The evidence that the assessment does not apply.
    pull : PullRequest
        The candidate the disposition is recorded against.

    Returns
    -------
    Verdict
        A ``not applicable`` verdict carrying its justification.
    """
    return Verdict(
        verdict=NOT_APPLICABLE,
        base=pull.base,
        head=pull.head,
        justification=reason,
    )


def assess_and_maybe_mark_ready(
    pull: PullRequest,
    discussion: Discussion,
    *,
    completeness_id: str = "271-boundary-completeness",
    proof_id: str = "271-boundary-proof",
    proof_applies: bool = False,
    completeness_applies: bool = True,
) -> Readiness:
    """Run the documented sequence for one candidate and return its decision.

    The sequence is the one the skills state: establish green CI and clear
    CodeScene findings, post the applicable assessment questions, read their
    substantive replies, decide readiness, and only then perform the ready
    transition. A pending reply stays pending; it is never read as clearance.
    A blocked delivery gate returns before any question is posted, so the
    assessor is not asked to spend a reply on a candidate that cannot proceed.

    Parameters
    ----------
    pull : PullRequest
        The candidate double, including its delivery-gate state.
    discussion : Discussion
        The assessment thread the questions are posted to and read from.
    completeness_id : str, optional
        Request marker for the completeness question.
    proof_id : str, optional
        Request marker for the proof question.
    proof_applies : bool, optional
        Whether the proof assessment applies to this candidate.
    completeness_applies : bool, optional
        Whether an ExecPlan makes the completeness assessment applicable.

    Returns
    -------
    Readiness
        The decision, after the ready transition has or has not been performed.
    """
    blocked = delivery_gate(pull.candidate())
    if blocked is not None:
        return blocked
    revision = pull.approved_plan_revision
    if completeness_applies:
        posted = discussion.post(COMPLETENESS, completeness_id, revision)
        completeness = _verdict(COMPLETENESS, discussion.observe(posted), revision)
    else:
        completeness = _not_applicable("No ExecPlan governs this change.", pull)
    if proof_applies:
        posted = discussion.post(PROOF, proof_id, revision)
        proof = _verdict(PROOF, discussion.observe(posted), revision)
    else:
        proof = _not_applicable("No proof is affected by this change.", pull)
    decision = readiness(pull.candidate(), completeness, proof)
    if decision.ready and pull.is_draft:
        pull.mark_ready()
    return decision


__all__ = (
    "CODERABBIT",
    "Discussion",
    "PullRequest",
    "Reply",
    "assess_and_maybe_mark_ready",
)
