"""Contract regressions for implementation ownership and PR rebase guidance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pytest

import pr_readiness_workflow as workflow
from assessment_mutation_cases import (
    HANDOFF_DEFERS,
    HANDOFF_PACKET_EXCEPTION,
    HANDOFF_SUBSET_EVIDENCE,
)
from pr_readiness_model import (
    CLEAR,
    DECLARED_SUBSET,
    PROOF,
    WHOLE_PLAN,
    Readiness,
)
from skill_contract_support import (
    mutate_one_clause,
    normalize,
    raw_section,
    section,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO_ROOT / "skills" / "sdlc-implementation"
DELIVERY = REPO_ROOT / "skills" / "pr-babysitting" / "references"
LIFECYCLE_COMMANDS = (
    "gh pr ready",
    "gh pr merge",
    "gh run watch",
    "gh run rerun",
    "post_manual_comment()",
    "@coderabbitai please assess the implementation",
    "@coderabbitai are you satisfied",
)
REBASE_REQUIREMENTS = (
    "live PR's target repository and `baseRefName`",
    "exclusive `OLD_BASE`",
    "merge.conflictStyle=zdiff3",
    "resolution plan for each conflict",
    "before editing or staging",
    'git restore --source="$TARGET" --staged --worktree -- "$lockfile"',
    "rebuild affected lockfiles from the combined manifests",
    "make check-fmt",
    "make test",
    "make typecheck",
    "make lint",
    "commit any deliberate outstanding changes",
    '--force-with-lease="refs/heads/$head_branch:$EXPECTED_REMOTE_HEAD"',
    "A rejected lease stops publication",
    "weave-git-merge",
    "`sem`",
)


READINESS_ANCHOR = (
    "../pr-babysitting/references/execplan-assessment.md"
    "#readiness-and-later-changes"
)
SETUP_READINESS_ANCHOR = (
    "../../pr-babysitting/references/execplan-assessment.md"
    "#readiness-and-later-changes"
)
COMPLETENESS_PACKET_PREFIX = "ExecPlan completeness/correctness assessment:"
WHOLE_PLAN_SUBJECT = "completeness assessment must name the whole approved plan as its subject"
HANDOFF_LINK = "handoff must link pr-babysitting's readiness clearing rule"
SETUP_LINK = "draft creation must link the readiness clearing rule"
HANDOFF_DEFERRAL = "read them there rather than expecting a second copy here"
#: Clearing conditions that only pr-babysitting may state. The handoff names
#: the subset *subject*, which is not a clearing condition.
HANDOFF_CLEARING_CONDITIONS = (
    "it never clears the gate",
    "the whole-plan verdict is still required",
    "the stack does not count as delivered",
    "never qualifies either",
)
SETUP_SINGLE_RULE = (
    "draft creation must point at the single clearing rule instead of"
    " restating its conditions"
)
#: Phrases from the clearing rule that only pr-babysitting may state. If one
#: reappears in `sdlc-implementation`, the readiness contract has two copies.
RESTATED_CONDITIONS = (
    "whole-plan completeness verdict",
    "declared-subset verdict",
    "green CI",
    "CodeScene findings",
    "proof verdict",
)


def _assert_single_clearing_rule(creator: str) -> None:
    """The draft creator defers to the clearing rule rather than copying it."""
    assert "read its conditions there" in creator, SETUP_SINGLE_RULE
    restated = [phrase for phrase in RESTATED_CONDITIONS if phrase in creator]
    assert not restated, f"{SETUP_SINGLE_RULE}: {restated}"


@pytest.fixture(scope="module")
def implementation_text() -> str:
    """Return the implementation skill document once per module."""
    return _read(IMPLEMENTATION / "SKILL.md")


@pytest.fixture(scope="module")
def setup_text() -> str:
    """Return the setup reference once per module."""
    return _read(IMPLEMENTATION / "references" / "setup.md")


def _read(path: Path) -> str:
    """Read a tracked UTF-8 skill document."""
    return path.read_text(encoding="utf-8")


def _handoff_section(document: str) -> str:
    """Return the raw handoff section that carries the completeness packet."""
    return raw_section(document, "4. Hand PR delivery to pr-babysitting")


def _completeness_packet_line(document: str) -> str:
    """Return the single whole-plan completeness packet line of the handoff."""
    matches = [
        line
        for line in _handoff_section(document).splitlines()
        if line.startswith(COMPLETENESS_PACKET_PREFIX)
    ]
    assert len(matches) == 1, "expected one completeness packet line"
    return normalize(matches[0])


def _assert_handoff_binds_whole_plan(implementation: str, setup: str) -> None:
    """The handoff and draft creation defer to the readiness clearing rule."""
    packet = _completeness_packet_line(implementation)
    assert "against the whole approved plan" in packet, (
        "completeness assessment must name the whole approved plan as its subject"
    )
    assert "declared-subset" not in packet, HANDOFF_PACKET_EXCEPTION
    assert "not the declared PR scope" in packet, (
        "completeness assessment must exclude the declared PR scope as its subject"
    )
    assert "evidence or pending" in packet, (
        "handoff must still distinguish evidence from pending"
    )
    handoff = normalize(_handoff_section(implementation))
    assert "does not bound it" in handoff, (
        "handoff must state that a delivered subset does not bound the assessment"
    )
    subset_evidence = (
        "A managed-stack layer records its declared-subset verdict as evidence"
        " for its actual scope only"
    )
    assert subset_evidence in handoff, HANDOFF_SUBSET_EVIDENCE
    assert HANDOFF_DEFERRAL in handoff, HANDOFF_DEFERS
    assert READINESS_ANCHOR in handoff, (
        "handoff must link pr-babysitting's readiness clearing rule"
    )
    # Compare case-insensitively: a restated condition may begin a sentence,
    # and a case-sensitive match would let that copy through unnoticed.
    folded = handoff.casefold()
    restated = [
        phrase for phrase in HANDOFF_CLEARING_CONDITIONS if phrase in folded
    ]
    assert not restated, f"{HANDOFF_DEFERS}: {restated}"
    creator = section(setup, "Resolve the candidate")
    assert "stays draft until `pr-babysitting` marks it ready" in creator, (
        "draft creation must bind the draft's end to pr-babysitting"
    )
    assert "does not mark the draft ready and does not end it" in creator, (
        "draft creation must state this skill does not end the draft"
    )
    assert SETUP_READINESS_ANCHOR in creator, (
        "draft creation must link the readiness clearing rule"
    )
    _assert_single_clearing_rule(creator)


def _assert_no_delivery_loop(text: str) -> None:
    """Keep operational delivery commands in the PR lifecycle owner."""
    normalized = normalize(text)
    for command in LIFECYCLE_COMMANDS:
        assert command not in normalized, f"duplicated lifecycle command: {command}"


def _assert_rebase_contract(text: str) -> None:
    """Require the explicit replay and publication safeguards."""
    normalized = normalize(text)
    for requirement in REBASE_REQUIREMENTS:
        assert requirement in normalized, f"missing rebase requirement: {requirement}"


def test_implementation_has_no_duplicate_delivery_loop() -> None:
    """Every implementation reference delegates hosted PR delivery."""
    paths = sorted(IMPLEMENTATION.rglob("*.md"))
    assert paths, "the implementation skill must exist"
    for path in paths:
        _assert_no_delivery_loop(_read(path))


@pytest.mark.parametrize("command", LIFECYCLE_COMMANDS)
def test_contract_rejects_reintroduced_delivery_commands(command: str) -> None:
    """A seeded lifecycle command cannot hide in implementation guidance."""
    text = _read(IMPLEMENTATION / "SKILL.md") + f"\n{command}\n"
    with pytest.raises(AssertionError, match="duplicated lifecycle command"):
        _assert_no_delivery_loop(text)


def test_handoff_binds_the_whole_plan_to_the_readiness_rule(
    implementation_text: str, setup_text: str
) -> None:
    """The whole approved plan is the assessment subject, not the declared scope."""
    _assert_handoff_binds_whole_plan(implementation_text, setup_text)


@dataclass(frozen=True)
class Clause:
    """One clause mutation and the contract message it must provoke."""

    old: str
    new: str
    expected: str


#: Mutations of the handoff's completeness packet, in contract order.
PACKET_MUTATIONS = (
    pytest.param(
        Clause("against the whole approved plan, not the declared PR scope;", "",
               WHOLE_PLAN_SUBJECT),
        id="removed-qualifier",
    ),
    pytest.param(
        Clause("against the whole approved plan", "against the declared PR scope",
               WHOLE_PLAN_SUBJECT),
        id="narrowed-to-declared-scope",
    ),
    pytest.param(
        Clause(
            "execplan-assessment readiness rule; evidence or pending.",
            "execplan-assessment readiness rule; evidence or pending, except a"
            " managed-stack layer clearing on its declared-subset verdict.",
            HANDOFF_PACKET_EXCEPTION,
        ),
        id="reintroduced-subset-exception",
    ),
    pytest.param(
        Clause(
            "A managed-stack layer records its declared-subset verdict as"
            " evidence for its actual scope only",
            "A managed-stack layer may clear on its declared-subset verdict",
            HANDOFF_SUBSET_EVIDENCE,
        ),
        id="subset-evidence-widened",
    ),
    pytest.param(
        Clause("read them there rather than expecting a second copy here.", "",
               HANDOFF_DEFERS),
        id="deferral-dropped",
    ),
    pytest.param(
        Clause(
            "read them there rather than expecting a second copy here.",
            "read them there rather than expecting a second copy here. That"
            " record never clears the gate, and the whole-plan verdict is"
            " still required.",
            HANDOFF_DEFERS,
        ),
        id="restates-subset-clearing",
    ),
    pytest.param(
        Clause(
            "read them there rather than expecting a second copy here.",
            "read them there rather than expecting a second copy here. The"
            " stack does not count as delivered until the layer carrying the"
            " remainder obtains one.",
            HANDOFF_DEFERS,
        ),
        id="restates-stack-delivery",
    ),
)


@pytest.mark.parametrize("mutation", PACKET_MUTATIONS)
def test_handoff_rejects_a_completeness_packet_that_bounds_or_widens_its_scope(
    implementation_text: str, setup_text: str, mutation: Clause
) -> None:
    """Deleting, narrowing, or inventing an exception fails the handoff contract."""
    mutated = mutate_one_clause(implementation_text, mutation.old, mutation.new)
    with pytest.raises(AssertionError, match=re.escape(mutation.expected)):
        _assert_handoff_binds_whole_plan(mutated, setup_text)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "read its conditions there rather than expecting a second copy here.",
            (
                "read its conditions there rather than expecting a second copy here."
                " It requires a clear whole-plan completeness verdict."
            ),
        ),
        (
            "read its conditions there rather than expecting a second copy here.",
            (
                "read its conditions there rather than expecting a second copy here."
                " It also requires green CI."
            ),
        ),
        (
            "read its conditions there rather than expecting a second copy here.",
            (
                "read its conditions there rather than expecting a second copy here."
                " It also requires CodeScene findings."
            ),
        ),
        (
            "read its conditions there rather than expecting a second copy here.",
            "",
        ),
    ],
    ids=[
        "restates-the-verdict",
        "restates-green-ci",
        "restates-codescene-findings",
        "drops-the-pointer",
    ],
)
def test_handoff_rejects_a_setup_gate_that_restates_or_drops_the_rule(
    implementation_text: str, setup_text: str, old: str, new: str
) -> None:
    """A second copy of the clearing conditions fails the single-rule contract."""
    mutated = mutate_one_clause(setup_text, old, new)
    with pytest.raises(AssertionError, match=re.escape(SETUP_SINGLE_RULE)):
        _assert_handoff_binds_whole_plan(implementation_text, mutated)


@dataclass(frozen=True)
class LinkSite:
    """A readiness cross-reference and the contract message it must provoke."""

    document: str
    anchor: str
    expected: str


#: The two documents that cross-reference the readiness clearing rule.
LINK_SITES = (
    pytest.param(
        LinkSite("implementation", READINESS_ANCHOR, HANDOFF_LINK),
        id="moved-readiness-link",
    ),
    pytest.param(
        LinkSite("setup", SETUP_READINESS_ANCHOR, SETUP_LINK),
        id="moved-draft-creation-cross-reference",
    ),
)


@pytest.mark.parametrize("site", LINK_SITES)
def test_handoff_rejects_a_readiness_link_moved_out_of_its_section(
    implementation_text: str, setup_text: str, site: LinkSite
) -> None:
    """A readiness cross-reference pasted outside its section cannot satisfy the contract."""
    documents = {"implementation": implementation_text, "setup": setup_text}
    documents[site.document] = mutate_one_clause(
        documents[site.document], site.anchor, "", move=True
    )
    with pytest.raises(AssertionError, match=re.escape(site.expected)):
        _assert_handoff_binds_whole_plan(
            documents["implementation"], documents["setup"]
        )


def test_handoff_accepts_red_draft_candidate() -> None:
    """Delivery starts before hosted success, with explicit assessment state."""
    text = normalize(_read(IMPLEMENTATION / "SKILL.md"))
    assert (
        "even if the published PR is still draft or its CI is red" in text
    ), "missing red/draft candidate handoff contract"
    assert "existing ledger" in text, "handoff must retain the existing ledger"
    assert "Proof inventory and verifier evidence" in text, (
        "handoff must include the proof inventory and verifier evidence"
    )
    assert "Authorized publication/merge actions" in text, (
        "handoff must document authorized publication and merge actions"
    )
    assert "milestone CLI" in text, (
        "implementation must retain milestone CLI assessments"
    )


def test_assessments_remain_in_babysitting() -> None:
    """The lifecycle owner retains both original questions and proof criteria."""
    text = _read(DELIVERY / "execplan-assessment.md")
    assert (
        "@coderabbitai please assess the implementation in this PR for "
        "completeness and correctness against the execplan:"
    ) in text, (
        "missing ExecPlan completeness and correctness assessment question"
    )
    assert (
        "@coderabbitai are you satisfied that the introduced proof(s) "
        "(<proof file paths with named proof references>) is substantive, "
        "rigorous, and well-founded?"
    ) in text, (
        "missing substantive, rigorous, well-founded proof assessment question"
    )
    normalized = normalize(text)
    for requirement in (
        "CrossHair, Kani, Verus, LemmaScript",
        "non-vacuity",
        "Both applicable assessments must clear",
        "before its draft-to-ready transition",
        "Assessment conversations never go through `comenq`",
        "`comenq-coderabbit`",
        "An already-ready PR stays ready",
        "Do not set the PR back to draft",
        "Generic approval cannot discharge missing proof scrutiny",
    ):
        assert requirement in normalized, f"missing requirement: {requirement}"


def test_pr_rebase_contract() -> None:
    """Rebase guidance retains actual-target and explicit-lease requirements."""
    _assert_rebase_contract(_read(DELIVERY / "rebase.md"))


@pytest.mark.parametrize("requirement", REBASE_REQUIREMENTS)
def test_contract_rejects_missing_rebase_safeguard(requirement: str) -> None:
    """Removing each safeguard makes the contract fail independently."""
    text = normalize(_read(DELIVERY / "rebase.md"))
    assert requirement in text, (
        f"mutation fixture is missing rebase requirement: {requirement}"
    )
    mutated = text.replace(requirement, "")
    with pytest.raises(AssertionError, match="missing rebase requirement"):
        _assert_rebase_contract(mutated)


def test_bounded_delegation_and_external_evidence() -> None:
    """Agent packets retain narrow scope, evidence, and escalation boundaries."""
    text = normalize(_read(IMPLEMENTATION / "references" / "delegation.md"))
    for requirement in (
        "firecrawl-mcp",
        "version-matched documentation",
        "Wyvern: one read-only reconnaissance question",
        "Artisan: one independently testable change",
        "Exit clauses:",
        "must not spawn subagents",
        "monitoring-only scrutineer workflow",
        "pr-babysitting",
    ):
        assert requirement in text, f"missing requirement: {requirement}"


# --------------------------------------------------------------------------
# The handoff exercised as a handoff: the packet's own fields drive the
# readiness sequence, rather than each side being asserted in prose.
# --------------------------------------------------------------------------

#: The packet lines the receiving lifecycle needs to run its assessments. The
#: handoff calls these out by name, so they are read from the shipped text
#: rather than re-declared here: a packet that renamed or dropped one would
#: otherwise leave this test passing against a shape no handoff produces. The
#: completeness entry is the packet's whole line, not its label: applicability
#: is stated in the value the implementation fills in, which follows the label.
PACKET_FIELDS = {
    "candidate": "Repository, PR, worktree, target, and verified base/head:",
    "plan": "Approved ExecPlan path and revision; accepted scope and tolerances:",
    "status": "Implementation status and acceptance evidence; remaining in-scope work:",
    "proof": "Proof-specific assessment: required when applicable; evidence or pending.",
}


#: The candidate the handoff is exercised for, and its approved revision. They
#: stand for what a real packet carries on its base/head and plan lines, which
#: are placeholders in the template rather than fixed values.
BASE = "handed0001"
HEAD = "handed0002"
REVISION = "rev-2026-11-01"
PROOF_ONE = "proofs/refinement/Theorem.lean#refinement_sound"

#: The marker the workflow posts the completeness request under when the
#: caller does not name another. Read from the assignment rather than invented,
#: so a renamed default moves this test with it.
WORKFLOW_COMPLETENESS_ID = workflow.IMPLEMENTATION.completeness_id


def packet() -> dict[str, str]:
    """Return the handoff packet's fields, read from the implementation skill.

    Each field is the packet line's label and the value the implementation
    skill supplies for it. The values are placeholders, as they are in the
    template; what matters here is that every field the receiving lifecycle
    reads is present in the shipped packet and carries a distinct slot.

    Returns
    -------
    dict
        Mapping of field key to the packet line that carries it.

    Raises
    ------
    AssertionError
        Raised when the packet has lost a field the handoff contract names.
    """
    handoff = normalize(_handoff_section(_read(IMPLEMENTATION / "SKILL.md")))
    found = {}
    for key, label in PACKET_FIELDS.items():
        assert label in handoff, f"handoff packet lost its {key} field: {label}"
        found[key] = label
    return found


def test_the_shipped_handoff_packet_reaches_the_readiness_sequence() -> None:
    """A handoff's packet is the input the readiness sequence consumes.

    This crosses the boundary the two skills share rather than restating it.
    The packet is read from `sdlc-implementation`, and the candidate, revision,
    proof inventory and applicability the receiver derives from it are the
    values the workflow is driven with. A subset verdict on that handoff keeps
    the draft; a whole-plan verdict for the same candidate and revision clears
    it. Both directions are asserted, so a sequence that never opened would
    fail one half and a sequence that never closed would fail the other.

    The handoff's own line says the completeness assessment is required
    against the whole approved plan, so the receiver reads applicability from
    the packet rather than from whatever a reply claims about itself.
    """
    fields = packet()
    completeness_line = _completeness_packet_line(_read(IMPLEMENTATION / "SKILL.md"))
    # The receiver derives these from the packet's own wording: the
    # completeness line states whether the assessment is required, and the
    # proof line states when it applies. The values a handoff for this
    # repository would carry are what these read; the test is that the derived
    # shape drives the sequence, not that these strings are the only accepted
    # ones.
    completeness_applies = "required" in completeness_line.casefold()
    proof_applies = "required when applicable" in fields["proof"].casefold()
    assert completeness_applies, "the handoff no longer requires completeness"
    assert proof_applies, "the handoff no longer conditions the proof assessment"

    assignment = workflow.Assignment(
        completeness_applies=completeness_applies,
        proof_applies=proof_applies,
    )
    revision = REVISION

    def run(subject: str) -> tuple[workflow.PullRequest, Readiness]:
        """Drive the readiness sequence for one completeness subject."""
        pull = workflow.PullRequest(
            base=BASE,
            head=HEAD,
            approved_plan_revision=revision,
            required_proofs=(PROOF_ONE,),
        )
        thread = workflow.Discussion(base=BASE, head=HEAD)
        for selection in assignment.selections():
            # The reply is composed from the packet, so its candidate and
            # revision are the handoff's rather than a second set of literals.
            thread.responses.append(
                workflow.Reply(
                    assessment_id=selection.assessment_id,
                    author=workflow.CODERABBIT,
                    base=BASE,
                    head=HEAD,
                    verdict=CLEAR,
                    plan_revision=revision,
                    echoed_revision=revision,
                    subject=subject,
                    proofs=(PROOF_ONE,) if selection.kind == PROOF else (),
                )
            )
        return pull, workflow.assess_and_maybe_mark_ready(pull, thread, assignment)

    subset_pull, subset = run(DECLARED_SUBSET)
    assert not subset.ready, "a subset verdict on a handoff cleared the gate"
    assert subset.reason == "completeness-declared-subset-does-not-clear", (
        f"the subset handoff held for {subset.reason!r}"
    )
    assert subset_pull.is_draft, (
        "a subset handoff left the draft:"
        f" {subset_pull.ready_transitions}"
    )

    whole_pull, whole = run(WHOLE_PLAN)
    assert whole.ready, f"a whole-plan handoff was refused: {whole.reason}"
    assert whole_pull.ready_transitions == [HEAD], (
        f"the whole-plan handoff recorded {whole_pull.ready_transitions}"
    )


def test_a_handoff_that_omits_the_approved_revision_cannot_clear() -> None:
    """The packet's plan line is what the receiver binds the verdict to.

    An implementation handoff names the approved ExecPlan revision; the
    readiness rule binds an applicable completeness verdict to it. A handoff
    whose plan line records none leaves the receiver nothing to bind to, and
    the sequence must refuse rather than treat the absence as "nothing to
    reconcile" — which is what it did before the rule was added.
    """
    fields = packet()
    assert "revision" in fields["plan"].casefold(), (
        "the handoff packet no longer asks the implementation for a revision"
    )

    pull = workflow.PullRequest(base=BASE, head=HEAD, approved_plan_revision=None)
    thread = workflow.Discussion(base=BASE, head=HEAD)
    thread.responses.append(
        workflow.Reply(
            assessment_id=WORKFLOW_COMPLETENESS_ID,
            author=workflow.CODERABBIT,
            base=BASE,
            head=HEAD,
            verdict=CLEAR,
            plan_revision=None,
            echoed_revision=None,
            subject=WHOLE_PLAN,
        )
    )
    decision = workflow.assess_and_maybe_mark_ready(
        pull, thread, assignment=workflow.IMPLEMENTATION
    )

    assert not decision.ready, "a handoff with no revision cleared the gate"
    assert decision.reason == "completeness-revision-absent", (
        f"the revision-less handoff held for {decision.reason!r}"
    )
    assert pull.is_draft, (
        f"a revision-less handoff left the draft: {pull.ready_transitions}"
    )
