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
    Verdict,
    delivery_gate,
    proof_request,
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
    justification: str = ""
    # The proofs a proof assessment says it cleared. Empty for every other
    # kind, and empty for a proof reply that names none, which is exactly the
    # reply the inventory gate must reject.
    proofs: tuple[str, ...] = ()


@dataclass
class Discussion:
    """The PR's issue-comment thread and the assessment questions posted to it.

    ``post`` records the question the workflow would publish, and ``observe``
    returns only a correlated reply from the assessment bot, so an unrelated
    comment cannot be mistaken for a verdict.

    Two rules pull in opposite directions and both have to hold.

    The skill's request template requires each question to carry a *unique*
    request marker. A thread that let two questions share one marker could not
    tell two answers apart: ``observe`` would return the first reply matching
    the marker, so a later question with no answer of its own would be cleared
    by the answer to an earlier one.

    The shipped instructions also say to preserve an unanswered question and
    not repeat it. A thread that minted a fresh marker on every invocation
    would strand the reply to a question that is still outstanding: the answer
    arrives, the next invocation posts a differently-marked duplicate, and the
    verdict that was asked for is never read.

    So the marker is a function of the question, not of the call. ``post``
    returns the marker already outstanding for this kind, revision and proof
    inventory, and mints a new one only when the question differs from
    everything already asked. An unchanged re-ask is the same question, so it
    keeps its marker and the reply that eventually echoes it stays bound.
    """

    base: str
    head: str
    responses: list[Reply] = field(default_factory=list)
    requests: list[dict[str, object]] = field(default_factory=list)

    def post(
        self,
        kind: str,
        assessment_id: str,
        plan_revision: str | None,
        proofs: tuple[str, ...] = (),
    ) -> str:
        """Record one assessment question and return its request marker.

        The proof question's wording names the proofs it asks about, so the
        request records them. Which proofs the request asked about is not
        recoverable from a transcript that keeps only its kind and marker, and
        a reconciliation that cannot see the asked inventory cannot tell a
        narrowed answer from a complete one. That is also why the inventory
        takes part in deciding whether a question is the one already
        outstanding: a re-ask that widens the proof list is a new question and
        gets a marker of its own.

        Parameters
        ----------
        kind : str
            ``completeness`` or ``proof``.
        assessment_id : str
            Stem of the request marker the reply is expected to echo. The
            first use of a stem is recorded as written; a repeat of a stem
            already on the thread for a *different* question is recorded with a
            ``#N`` suffix so the two never share a marker.
        plan_revision : str or None
            Revision in force, or None when no ExecPlan applies.
        proofs : tuple of str, optional
            The proof inventory the question names; empty for every other kind.

        Returns
        -------
        str
            The request marker for this question: the outstanding one when the
            question is unchanged, otherwise a marker unique on the thread.
        """
        question = self._question(kind, plan_revision, proofs)
        asked = self._asked(question)
        if asked is not None:
            return asked["id"]
        marker = self._mint(assessment_id)
        self.requests.append({**question, "id": marker})
        return marker

    def _question(
        self, kind: str, plan_revision: str | None, proofs: tuple[str, ...]
    ) -> dict[str, object]:
        """Return the parts of a request that decide whether it is a new question.

        The candidate is part of the question: the same wording asked about a
        different base/head is a different assessment, and must not inherit a
        verdict obtained for the earlier candidate. So are the revision in
        force and the proof inventory, because those bound what the answer is
        about.

        Parameters
        ----------
        kind : str
            ``completeness`` or ``proof``.
        plan_revision : str or None
            Revision in force, or None when no ExecPlan applies.
        proofs : tuple of str
            The proof inventory the question names.

        Returns
        -------
        dict
            The question's identity, without its marker. The proofs stay a
            tuple rather than a joined string: two inventories that differ only
            in where a comma falls would compare equal once joined, so
            `("a", "b")` and `("a,b",)` would be one question. Keeping the
            structure is what makes "the same question" mean the same proofs.
        """
        return {
            "kind": kind,
            "base": self.base,
            "head": self.head,
            "revision": plan_revision or "",
            "proofs": tuple(proofs),
        }

    def _asked(self, question: dict[str, object]) -> dict[str, object] | None:
        """Return the request already recording ``question``, if there is one.

        The shipped instructions say to preserve an outstanding question and
        not repeat it, so an unchanged question returns the marker it was first
        asked under — whether or not a reply has arrived yet. Reusing the
        marker is what keeps the sequence live: a reply that lands between two
        invocations still answers the question the next invocation is asking,
        because the marker it echoes is the one that is returned here.

        Minting a fresh marker instead would strand that reply, and the run
        would hold forever on a question that was answered.

        Parameters
        ----------
        question : dict
            The question's identity, without its marker.

        Returns
        -------
        dict or None
            The first request recording this question, or None when it has not
            been asked on this thread.
        """
        for request in self.requests:
            if {key: request[key] for key in question} == question:
                return request
        return None

    def _mint(self, stem: str) -> str:
        """Return ``stem``, suffixed if this thread has already used it.

        Refusing to reuse a marker is what makes correlation meaningful. A
        thread that recorded two questions under one marker would answer the
        later one from the earlier reply, and a run that re-asks after a push
        would read a stale verdict as clearance for the new candidate.

        Parameters
        ----------
        stem : str
            The marker to record if it is unused.

        Returns
        -------
        str
            An unused marker derived from ``stem``.
        """
        taken = {request["id"] for request in self.requests}
        if stem not in taken:
            return stem
        attempt = 2
        while f"{stem}#{attempt}" in taken:
            attempt += 1
        return f"{stem}#{attempt}"

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
    # The proof inventory the assignment's request names. The model refuses a
    # clear proof verdict that does not cover every entry, so a double that
    # never carries an inventory cannot exercise that rule at all.
    required_proofs: tuple[str, ...] = ()
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
            ci_green=self.ci_green,
            codescene_clear=self.codescene_clear,
            required_proofs=self.required_proofs,
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
        justification=reply.justification,
        proofs=reply.proofs,
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


@dataclass(frozen=True)
class Selection:
    """One assessment's role in an assignment.

    ``applies`` false carries the ``reason`` recorded as its justified
    not-applicable verdict, so an inapplicable assessment is still an explicit
    ledger entry rather than an absence.
    """

    kind: str
    assessment_id: str
    applies: bool
    reason: str


@dataclass(frozen=True)
class Assignment:
    """Which assessments an assignment makes applicable, and their markers."""

    completeness_id: str = "271-boundary-completeness"
    proof_id: str = "271-boundary-proof"
    proof_applies: bool = False
    completeness_applies: bool = True

    def selections(self) -> tuple[Selection, Selection]:
        """Return the completeness and proof selections this assignment makes."""
        return (
            Selection(
                COMPLETENESS,
                self.completeness_id,
                self.completeness_applies,
                "No ExecPlan governs this change.",
            ),
            Selection(
                PROOF,
                self.proof_id,
                self.proof_applies,
                "No proof is affected by this change.",
            ),
        )


#: The ordinary ExecPlan implementation assignment.
IMPLEMENTATION = Assignment()

#: A proof-only assignment with no ExecPlan in force.
PROOF_ONLY = Assignment(proof_applies=True, completeness_applies=False)


def _assess(
    discussion: Discussion, pull: PullRequest, selection: Selection
) -> Verdict:
    """Post and read one applicable assessment, or record it not applicable.

    Parameters
    ----------
    discussion : Discussion
        The assessment thread the question is posted to and read from.
    pull : PullRequest
        The candidate double supplying the revision in force.
    selection : Selection
        The assessment, its request marker, and whether it applies.

    Returns
    -------
    Verdict
        The observed verdict, or a justified not-applicable verdict.
    """
    if not selection.applies:
        return _not_applicable(selection.reason, pull)
    # The question's marker is minted from the discussion's own base and head,
    # while the revision and inventory it asks about come from the pull
    # request. If the two doubles drift apart, the marker names a candidate the
    # request does not, and a reply naming the request's head could inherit a
    # marker minted for the other one. Refuse rather than post that question.
    assert (discussion.base, discussion.head) == (pull.base, pull.head), (
        "the discussion and the pull request describe different candidates:"
        f" {(discussion.base, discussion.head)} != {(pull.base, pull.head)}"
    )
    revision = pull.approved_plan_revision
    posted = discussion.post(
        selection.kind,
        selection.assessment_id,
        revision,
        pull.required_proofs if selection.kind == PROOF else (),
    )
    return _verdict(selection.kind, discussion.observe(posted), revision)


def assess_and_maybe_mark_ready(
    pull: PullRequest,
    discussion: Discussion,
    assignment: Assignment = IMPLEMENTATION,
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
    assignment : Assignment, optional
        Which assessments apply and the markers they are posted under.

    Returns
    -------
    Readiness
        The decision, after the ready transition has or has not been performed.
    """
    blocked = delivery_gate(pull.candidate())
    if blocked is not None:
        return blocked
    # A proof assessment that names no inventory has no question to publish,
    # so the sequence stops before spending any reply on one. Like a blocked
    # delivery gate, this returns before the assessment questions are posted.
    blocked = proof_request(pull.candidate(), assignment.proof_applies)
    if blocked is not None:
        return blocked
    completeness, proof = (
        _assess(discussion, pull, selection)
        for selection in assignment.selections()
    )
    decision = readiness(
        pull.candidate(),
        completeness,
        proof,
        # The assignment decides applicability; handing the model the replies
        # alone would let one that declares itself `not applicable` skip the
        # checks the same assignment requires.
        completeness_applies=assignment.completeness_applies,
        proof_applies=assignment.proof_applies,
    )
    if decision.ready and pull.is_draft:
        pull.mark_ready()
    return decision


__all__ = (
    "CODERABBIT",
    "IMPLEMENTATION",
    "PROOF_ONLY",
    "Assignment",
    "Discussion",
    "PullRequest",
    "Reply",
    "assess_and_maybe_mark_ready",
)
