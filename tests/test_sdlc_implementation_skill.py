"""Contract regressions for implementation ownership and PR rebase guidance."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

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
SETUP_COMPLETENESS = (
    "draft creation must name the completeness verdict as the gate's subject"
)


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
    assert READINESS_ANCHOR in handoff, (
        "handoff must link pr-babysitting's readiness clearing rule"
    )
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
    assert (
        "That gate requires a clear whole-plan completeness verdict for the"
        " approved plan revision" in creator
    ), "draft creation must name the completeness verdict as the gate's subject"


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


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (
            "against the whole approved plan, not the declared PR scope; ",
            "",
            WHOLE_PLAN_SUBJECT,
        ),
        (
            "against the whole approved plan",
            "against the declared PR scope",
            WHOLE_PLAN_SUBJECT,
        ),
    ],
    ids=["removed-qualifier", "narrowed-to-declared-scope"],
)
def test_handoff_rejects_a_completeness_packet_that_bounds_its_scope(
    implementation_text: str, setup_text: str, old: str, new: str, expected: str
) -> None:
    """Deleting or narrowing the whole-plan qualifier fails the handoff contract."""
    mutated = mutate_one_clause(implementation_text, old, new)
    with pytest.raises(AssertionError, match=re.escape(expected)):
        _assert_handoff_binds_whole_plan(mutated, setup_text)


def test_handoff_rejects_a_setup_gate_that_omits_its_subject(
    implementation_text: str, setup_text: str
) -> None:
    """A gate description that hides its main requirement cannot satisfy the handoff."""
    mutated = mutate_one_clause(
        setup_text,
        "That gate requires a clear whole-plan completeness verdict for"
        " the approved plan revision,",
        "That gate also requires",
    )
    with pytest.raises(AssertionError, match=re.escape(SETUP_COMPLETENESS)):
        _assert_handoff_binds_whole_plan(implementation_text, mutated)


@pytest.mark.parametrize(
    ("document", "anchor", "expected"),
    [
        ("implementation", READINESS_ANCHOR, HANDOFF_LINK),
        ("setup", SETUP_READINESS_ANCHOR, SETUP_LINK),
    ],
    ids=["moved-readiness-link", "moved-draft-creation-cross-reference"],
)
def test_handoff_rejects_a_readiness_link_moved_out_of_its_section(
    implementation_text: str,
    setup_text: str,
    document: str,
    anchor: str,
    expected: str,
) -> None:
    """A readiness cross-reference pasted outside its section cannot satisfy the contract."""
    source = implementation_text if document == "implementation" else setup_text
    mutated = mutate_one_clause(source, anchor, "", move=True)
    with pytest.raises(AssertionError, match=re.escape(expected)):
        _assert_handoff_binds_whole_plan(
            mutated if document == "implementation" else implementation_text,
            mutated if document == "setup" else setup_text,
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
