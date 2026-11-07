"""Contract regressions for implementation ownership and PR rebase guidance."""

from __future__ import annotations

from pathlib import Path
import re

import pytest


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


def _read(path: Path) -> str:
    """Read a tracked UTF-8 skill document."""
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """Ignore prose line wrapping without dropping contract punctuation."""
    return " ".join(text.split())


def section(text: str, heading: str) -> str:
    """Find one second-level section without accepting guards moved elsewhere."""
    matches = re.findall(
        r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    assert len(matches) == 1, f"expected unique section: {heading}"
    return matches[0]


def _handoff_section(document: str) -> str:
    """Return the raw handoff section that carries the completeness packet."""
    return section(document, "4. Hand PR delivery to pr-babysitting")


def _completeness_packet_line(document: str) -> str:
    """Return the single whole-plan completeness packet line of the handoff."""
    matches = [
        line
        for line in _handoff_section(document).splitlines()
        if line.startswith(COMPLETENESS_PACKET_PREFIX)
    ]
    assert len(matches) == 1, "expected one completeness packet line"
    return _normalize(matches[0])


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
    handoff = _normalize(_handoff_section(implementation))
    assert "does not bound it" in handoff, (
        "handoff must state that a delivered subset does not bound the assessment"
    )
    assert READINESS_ANCHOR in handoff, (
        "handoff must link pr-babysitting's readiness clearing rule"
    )
    creator = _normalize(section(setup, "Resolve the candidate"))
    assert "stays draft until `pr-babysitting` marks it ready" in creator, (
        "draft creation must bind the draft's end to pr-babysitting"
    )
    assert "neither marks it ready nor ends the draft" in creator, (
        "draft creation must state this skill does not end the draft"
    )
    assert SETUP_READINESS_ANCHOR in creator, (
        "draft creation must link the readiness clearing rule"
    )


def _assert_no_delivery_loop(text: str) -> None:
    """Keep operational delivery commands in the PR lifecycle owner."""
    normalized = _normalize(text)
    for command in LIFECYCLE_COMMANDS:
        assert command not in normalized, f"duplicated lifecycle command: {command}"


def _assert_rebase_contract(text: str) -> None:
    """Require the explicit replay and publication safeguards."""
    normalized = _normalize(text)
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


def test_handoff_binds_the_whole_plan_to_the_readiness_rule() -> None:
    """The whole approved plan is the assessment subject, not the declared scope."""
    _assert_handoff_binds_whole_plan(
        _read(IMPLEMENTATION / "SKILL.md"),
        _read(IMPLEMENTATION / "references" / "setup.md"),
    )


def _mutate_one_clause(source: str, old: str, new: str) -> str:
    """Replace the one clause matching ``old`` regardless of its line wrapping."""
    pattern = r"\s+".join(map(re.escape, old.split()))
    matches = list(re.finditer(pattern, source))
    assert len(matches) == 1, "mutation fixture must identify one binding clause"
    match = matches[0]
    return source[: match.start()] + new + source[match.end() :]


WHOLE_PLAN_SUBJECT = "completeness assessment must name the whole approved plan as its subject"
HANDOFF_LINK = "handoff must link pr-babysitting's readiness clearing rule"
SETUP_LINK = "draft creation must link the readiness clearing rule"


@pytest.mark.parametrize(
    ("document", "old", "new", "move_link", "expected"),
    [
        (
            "implementation",
            "against the whole approved plan, not the declared PR scope; ",
            "",
            "",
            WHOLE_PLAN_SUBJECT,
        ),
        (
            "implementation",
            "against the whole approved plan",
            "against the declared PR scope",
            "",
            WHOLE_PLAN_SUBJECT,
        ),
        ("implementation", "", "", READINESS_ANCHOR, HANDOFF_LINK),
        ("setup", "", "", SETUP_READINESS_ANCHOR, SETUP_LINK),
    ],
    ids=[
        "removed-qualifier",
        "narrowed-to-declared-scope",
        "moved-readiness-link",
        "moved-draft-creation-cross-reference",
    ],
)
def test_handoff_contract_rejects_narrowed_or_moved_whole_plan_binding(
    document: str, old: str, new: str, move_link: str, expected: str
) -> None:
    """Removing, narrowing, or relocating the binding fails the intended check."""
    implementation = _read(IMPLEMENTATION / "SKILL.md")
    setup = _read(IMPLEMENTATION / "references" / "setup.md")
    source = implementation if document == "implementation" else setup

    if move_link:
        assert source.count(move_link) == 1, "moved reference must be unique"
        mutated = source.replace(move_link, "", 1)
        mutated += "\n## Unrelated notes\n\n" + move_link + "\n"
    else:
        mutated = _mutate_one_clause(source, old, new)

    with pytest.raises(AssertionError, match=re.escape(expected)):
        _assert_handoff_binds_whole_plan(
            mutated if document == "implementation" else implementation,
            mutated if document == "setup" else setup,
        )


def test_handoff_accepts_red_draft_candidate() -> None:
    """Delivery starts before hosted success, with explicit assessment state."""
    text = _normalize(_read(IMPLEMENTATION / "SKILL.md"))
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
    normalized = _normalize(text)
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
    text = _normalize(_read(DELIVERY / "rebase.md"))
    assert requirement in text, (
        f"mutation fixture is missing rebase requirement: {requirement}"
    )
    mutated = text.replace(requirement, "")
    with pytest.raises(AssertionError, match="missing rebase requirement"):
        _assert_rebase_contract(mutated)


def test_bounded_delegation_and_external_evidence() -> None:
    """Agent packets retain narrow scope, evidence, and escalation boundaries."""
    text = _normalize(_read(IMPLEMENTATION / "references" / "delegation.md"))
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
