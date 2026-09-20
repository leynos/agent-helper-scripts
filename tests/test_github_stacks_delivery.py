"""Repeatable bare-remote evidence for the partial-stack delivery procedure.

Negative controls deliberately weaken commands in disposable repositories to
show that the behavioural assertions distinguish the documented safeguards.
No test claims to complete a live GitHub publication or metadata reconciliation.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from github_stacks_delivery_support import (
    PROCEDURE, ROOT, Delivery, commit, git, make_delivery, publication_commands,
)


@pytest.fixture
def delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Delivery:
    """Provide independent Git state for every scenario and negative control."""
    return make_delivery(tmp_path, monkeypatch)


def test_frontier_publication_leaves_unvalidated_upper_unchanged(
    delivery: Delivery,
) -> None:
    """The extracted command publishes only the candidate's destination ref."""
    before, push, after = publication_commands()
    assert delivery.read(before) == delivery.expected
    result = delivery.run(push)
    assert result.returncode == 0, result.stderr
    assert delivery.read(after) == delivery.candidate
    assert git(delivery.remote, "rev-parse", "refs/heads/upper") == delivery.upper


@pytest.mark.parametrize("remove_protection", [False, True], ids=["documented", "mutant"])
def test_no_follow_tags_overrides_repository_push_configuration(
    delivery: Delivery, remove_protection: bool,
) -> None:
    """Removing the explicit no-tag flag actually leaks a reachable annotation."""
    git(delivery.repository, "config", "push.followTags", "true")
    git(delivery.repository, "tag", "-a", "private-evidence", "-m", "local evidence")
    before, push, after = publication_commands()
    assert delivery.read(before) == delivery.expected
    if remove_protection:
        push = push.replace("--no-follow-tags", "")
    result = delivery.run(push)
    assert result.returncode == 0, result.stderr
    assert delivery.read(after) == delivery.candidate
    tags = git(delivery.remote, "for-each-ref", "--format=%(refname)", "refs/tags")
    assert bool(tags) is remove_protection


@pytest.mark.parametrize("use_branch", [False, True], ids=["documented", "mutant"])
def test_selected_source_sha_survives_local_branch_movement(
    delivery: Delivery, use_branch: bool,
) -> None:
    """A branch-name source would publish new, unvalidated local work instead."""
    before, push, after = publication_commands()
    assert delivery.read(before) == delivery.expected
    moved = commit(delivery.repository, "unvalidated movement after gates")
    if use_branch:
        push = push.replace("$CANDIDATE:refs/heads/$BRANCH", "$BRANCH:refs/heads/$BRANCH")
    result = delivery.run(push)
    assert result.returncode == 0, result.stderr
    published = delivery.read(after)
    assert published == (moved if use_branch else delivery.candidate)
    assert (published == delivery.candidate) is not use_branch


@pytest.mark.parametrize("implicit_lease", [False, True], ids=["documented", "mutant"])
def test_stale_explicit_lease_rejects_race_even_after_tracking_fetch(
    delivery: Delivery, implicit_lease: bool,
) -> None:
    """A fetched tracking ref must not silently authorize replacing new work."""
    before, push, after = publication_commands()
    assert delivery.read(before) == delivery.expected
    competing = delivery.compete()
    git(delivery.repository, "fetch", "origin")
    assert git(delivery.repository, "rev-parse", "origin/frontier") == competing
    if implicit_lease:
        push = push.replace(
            '--force-with-lease="refs/heads/$BRANCH:$EXPECTED_REMOTE_HEAD"',
            "--force-with-lease",
        )
    result = delivery.run(push)
    assert (result.returncode == 0) is implicit_lease, result.stderr
    assert delivery.read(after) == (delivery.candidate if implicit_lease else competing)


def test_preflight_mismatch_stops_before_publication(delivery: Delivery) -> None:
    """A stale initial receipt is a stop condition, not an invitation to push."""
    competing = delivery.compete()
    before, _, _ = publication_commands()
    assert delivery.read(before) != delivery.expected
    assert git(delivery.remote, "rev-parse", "frontier") == competing


def test_successful_push_is_not_receipt_when_remote_moves_again(
    delivery: Delivery,
) -> None:
    """The final read detects a rewrite after a successful transport result."""
    before, push, after = publication_commands()
    assert delivery.read(before) == delivery.expected
    result = delivery.run(push)
    assert result.returncode == 0, result.stderr
    rewritten = commit(delivery.repository, "server-side descendant rewrite stand-in")
    git(delivery.repository, "push", str(delivery.remote), f"{rewritten}:refs/heads/frontier")
    assert delivery.read(after) != delivery.candidate


def test_diagram_uses_the_canonical_publication_command() -> None:
    """The accessible overview must carry the same safeguards as the recipe."""
    _, push, _ = publication_commands()
    assert shlex.split(push) == [
        "git", "push", "--no-follow-tags",
        "--force-with-lease=refs/heads/$BRANCH:$EXPECTED_REMOTE_HEAD",
        "$REMOTE", "$CANDIDATE:refs/heads/$BRANCH",
    ]
    guide = (ROOT / "docs/users-guide.md").read_text()
    diagram_push, = [line.partition(": ")[2] for line in guide.splitlines()
                     if "Owner->>Remote: git push" in line]
    assert diagram_push.split() == push.split()


@pytest.mark.parametrize("requirement", [
    "Confirm that the remote has exactly the expected branch head",
    "Run these individually and inspect each result.",
    "Verify that the final remote SHA equals `CANDIDATE`",
    "read the PR's `headRefOid` and base from GitHub",
    "Do not refresh a rejected lease blindly",
    "Never add `--force`, a wildcard refspec, `--all` or `--mirror`",
    "Re-read remote descendants in case GitHub changed them",
    "reconcile the owned local stack tracking through its supported workflow",
    "before the next managed write",
    "read back every intended ref even after a non-zero exit",
])
def test_human_inspection_and_reconciliation_contract_is_retained(requirement: str) -> None:
    """Pin required human checks that bare Git alone cannot implement or prove."""
    prose = " ".join(PROCEDURE.read_text().split())
    assert requirement in prose
