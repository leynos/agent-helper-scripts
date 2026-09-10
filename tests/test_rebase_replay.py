"""Behavioural tripwires for exclusion boundaries and explicit replay options."""

from __future__ import annotations

import re
import shlex

import pytest
from rebase_test_support import (
    ROOT,
    change,
    expect_parent,
    git,
    make_graph,
    oid,
    planner,
    snapshot,
)


@pytest.fixture
def graph(tmp_path, monkeypatch):
    return make_graph(tmp_path, monkeypatch)


def test_first_child_commit_is_not_the_exclusive_boundary(graph):
    """The wrong off-by-one command succeeds while silently dropping C."""
    git(graph.repository, "rebase", "--onto", graph.target, graph.c, "child")
    assert not (graph.repository / "first.txt").exists()
    assert (graph.repository / "second.txt").exists()
    assert git(
        graph.repository, "log", "--format=%s", f"{graph.target}..HEAD"
    ).stdout.splitlines() == ["D"]


def test_target_merge_base_replays_inherited_parent_work(graph):
    """The too-early boundary starts replaying A, not the first child commit."""
    result = git(
        graph.repository,
        "rebase",
        "--onto",
        graph.target,
        graph.trunk,
        "child",
        check=False,
    )
    assert result.returncode != 0
    assert oid(graph.repository, "REBASE_HEAD") == graph.a
    assert git(graph.repository, "ls-files", "--unmerged").stdout


def test_initially_empty_commit_survives_explicit_replay(graph, cmd_mox):
    git(graph.repository, "commit", "--allow-empty", "-m", "intentional empty")
    expect_parent(cmd_mox, graph)
    result = planner.plan(graph.request())
    assert len(result["commits"]) == 3
    git(graph.repository, *result["rebase_argv"][1:])
    assert git(
        graph.repository, "log", "--reverse", "--format=%s", f"{graph.target}..HEAD"
    ).stdout.splitlines() == ["C", "D", "intentional empty"]
    assert oid(graph.repository, "HEAD^{tree}") == oid(
        graph.repository, "HEAD^1^{tree}"
    )


def test_newly_empty_child_commit_stops_instead_of_disappearing(graph, cmd_mox):
    git(graph.repository, "switch", "main")
    target = change(
        graph.repository, "already applied C", "first.txt", "first child change\n"
    )
    git(graph.repository, "update-ref", "refs/remotes/origin/main", target)
    git(graph.repository, "switch", "child")
    expect_parent(cmd_mox, graph)
    result = planner.plan(graph.request())
    replay = git(graph.repository, *result["rebase_argv"][1:], check=False)
    assert replay.returncode != 0
    assert oid(graph.repository, "REBASE_HEAD") == graph.c
    assert (graph.repository / ".git/rebase-merge").is_dir()


def test_target_revert_of_parent_is_not_resurrected(graph, cmd_mox):
    git(graph.repository, "switch", "main")
    target = change(graph.repository, "revert parent", "parent.txt", "base\n")
    git(graph.repository, "update-ref", "refs/remotes/origin/main", target)
    git(graph.repository, "switch", "child")
    expect_parent(cmd_mox, graph)
    result = planner.plan(graph.request())
    git(graph.repository, *result["rebase_argv"][1:])
    assert (graph.repository / "parent.txt").read_text() == "base\n"
    assert (graph.repository / "first.txt").exists()


def test_parent_reflog_recovers_the_old_incarnation(tmp_path, monkeypatch):
    graph = make_graph(tmp_path, monkeypatch, "rewritten")
    ref = "refs/remotes/origin/old-parent"
    git(graph.repository, "update-ref", "--create-reflog", ref, graph.b)
    git(graph.repository, "update-ref", ref, graph.parent, graph.b)
    assert (
        git(graph.repository, "merge-base", "--fork-point", ref, graph.d).stdout.strip()
        == graph.b
    )
    wrong_ref = git(
        graph.repository,
        "merge-base",
        "--fork-point",
        "refs/remotes/origin/main",
        graph.d,
        check=False,
    )
    assert wrong_ref.returncode == 1
    git(graph.repository, "reflog", "expire", "--expire=now", ref)
    assert (
        git(
            graph.repository, "merge-base", "--fork-point", ref, graph.d, check=False
        ).returncode
        == 1
    )


def test_equal_net_patches_do_not_establish_unique_boundary(graph):
    extra = change(graph.repository, "extra", "parent.txt", "temporary\n")
    git(graph.repository, "revert", "--no-edit", extra)
    restored = oid(graph.repository)
    # These prefixes have identical trees but different ownership boundaries.
    assert oid(graph.repository, f"{restored}^{{tree}}") == oid(
        graph.repository, f"{graph.d}^{{tree}}"
    )
    assert git(
        graph.repository, "rev-list", f"{graph.d}..{restored}"
    ).stdout.splitlines() == [restored, extra]


def test_discovery_detects_child_race(graph, cmd_mox):
    before = snapshot(graph.repository)

    def moved_during_gh(_invocation):
        git(graph.repository, "update-ref", "refs/heads/child", graph.c, graph.d)
        return graph.capture(), "", 0

    expect_parent(cmd_mox, graph).runs(moved_during_gh)
    with pytest.raises(planner.PlanError, match="Child branch moved"):
        planner.plan(graph.request())
    assert oid(graph.repository, "refs/heads/child") == graph.c
    # Do not roll back another owner's concurrent change.
    assert snapshot(graph.repository)[0] != before[0]


def test_discovery_detects_target_race(graph, cmd_mox):
    def moved_during_gh(_invocation):
        git(
            graph.repository,
            "update-ref",
            "refs/remotes/origin/main",
            graph.landed,
            graph.target,
        )
        return graph.capture(), "", 0

    expect_parent(cmd_mox, graph).runs(moved_during_gh)
    with pytest.raises(planner.PlanError, match="Target ref moved"):
        planner.plan(graph.request())


def test_documented_replay_command_matches_the_executable_planner():
    skill = (ROOT / "skills/rebase/SKILL.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)\n```", skill, re.DOTALL)
    replay = next(block for block in blocks if "--onto" in block)
    argv = shlex.split(replay.replace("\\\n", ""))
    assert argv == [*planner.REBASE_PREFIX, "$TARGET", "$OLD_BASE", "$BRANCH"]


def test_documented_metadata_query_matches_the_recorded_cli_command():
    from rebase_test_support import MANIFEST

    reference = (ROOT / "skills/rebase/references/squashed-parent.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)\n```", reference, re.DOTALL)
    metadata = next(block for block in blocks if "--jq" in block)
    argv = shlex.split(metadata.replace("\\\n", ""))
    recorded = MANIFEST["commands"]["merged-parent"]["argv"]
    assert argv[:2] == recorded[:2]
    assert argv[-2:] == recorded[-2:]


def test_weave_audit_uses_child_boundary_not_target_merge_base(graph):
    """Execute the documented path classification and exclude inherited parent work."""
    import os
    import subprocess

    skill = (ROOT / "skills/weave-git-merge/SKILL.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)\n```", skill, re.DOTALL)
    paths = next(block for block in blocks if "weave-branch-paths.z" in block)
    paths = paths.replace("/tmp/weave-", str(graph.repository.parent / "weave-"))
    subprocess.run(
        ["bash", "-euc", paths],
        cwd=graph.repository,
        env={
            **os.environ,
            "OLD_HEAD": graph.d,
            "TARGET": graph.target,
            "BRANCH_BASE": graph.b,
            "MERGE_BASE": graph.trunk,
        },
        capture_output=True,
        check=True,
        timeout=30,
    )
    branch_paths = (
        (graph.repository.parent / "weave-branch-paths.z").read_bytes().split(b"\0")
    )
    assert b"first.txt" in branch_paths
    assert b"second.txt" in branch_paths
    assert b"parent.txt" not in branch_paths
