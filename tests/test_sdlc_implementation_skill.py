"""Contract regressions for implementation ownership and PR rebase guidance."""

from __future__ import annotations

from pathlib import Path

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


def _read(path: Path) -> str:
    """Read a tracked UTF-8 skill document."""
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    """Ignore prose line wrapping without dropping contract punctuation."""
    return " ".join(text.split())


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
