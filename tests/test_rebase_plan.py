"""Exercise the real planner and Git graphs through cmd-mox's gh process shim."""

from __future__ import annotations

import dataclasses
import json

import pytest
from rebase_test_support import (
    FIXTURES,
    MANIFEST,
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


def test_deleted_parent_plan_replays_only_child_commits(graph, cmd_mox):
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    result = planner.plan(graph.request())
    assert snapshot(graph.repository) == before
    assert result["status"] == "review-required"
    assert result["old_base"] == graph.b
    assert result["old_base"] not in (graph.trunk, graph.c, graph.landed)
    assert result["commits"] == [graph.c, graph.d]
    assert oid(graph.repository, result["evidence_ref"]) == graph.b
    git(graph.repository, *result["rebase_argv"][1:])
    assert git(
        graph.repository, "log", "--reverse", "--format=%s", f"{graph.target}..HEAD"
    ).stdout.splitlines() == ["C", "D"]
    assert (
        git(
            graph.repository,
            "diff",
            "--exit-code",
            graph.target,
            "HEAD",
            "--",
            "parent.txt",
            "target-only.txt",
        ).returncode
        == 0
    )
    assert (graph.repository / "first.txt").read_text() == "first child change\n"
    assert (graph.repository / "second.txt").read_text() == "second child change\n"


@pytest.mark.parametrize("mode", ["advanced", "rewritten"])
def test_noninherited_parent_refuses_a_unique_but_unproven_merge_base(
    tmp_path, monkeypatch, cmd_mox, mode
):
    graph = make_graph(tmp_path, monkeypatch, mode)
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="Merge-base candidates are not proof"):
        planner.plan(graph.request())
    assert snapshot(graph.repository) == before
    common = git(graph.repository, "merge-base", graph.parent, graph.d).stdout.strip()
    assert common == (graph.b if mode == "advanced" else graph.trunk)


@pytest.mark.parametrize("mode", ["advanced", "rewritten"])
def test_maintained_receipt_recovers_noninherited_parent(
    tmp_path, monkeypatch, cmd_mox, mode
):
    graph = make_graph(tmp_path, monkeypatch, mode)
    receipt = graph.receipt()
    expect_parent(cmd_mox, graph)
    result = planner.plan(graph.request(boundary_ref=receipt))
    assert result["old_base"] == graph.b
    assert result["commits"] == [graph.c, graph.d]
    git(graph.repository, *result["rebase_argv"][1:])
    assert (graph.repository / "first.txt").exists()
    assert (graph.repository / "second.txt").exists()
    assert (graph.repository / "target-only.txt").exists()
    if mode == "advanced":
        assert (graph.repository / "late.txt").exists()


@pytest.mark.parametrize("boundary", ["trunk", "c", "landed"])
def test_stale_off_by_one_or_squash_receipt_is_rejected(graph, cmd_mox, boundary):
    receipt = graph.receipt(getattr(graph, boundary))
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="boundary"):
        planner.plan(graph.request(boundary_ref=receipt))
    assert snapshot(graph.repository) == before


def test_receipt_must_belong_to_the_identified_parent(graph, cmd_mox):
    receipt = graph.receipt()
    git(graph.repository, "config", "branch.child.stackParent", "other/repo#50")
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="stackParent identity"):
        planner.plan(graph.request(boundary_ref=receipt))


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"merged": False}, "has not merged"),
        ({"merged": "true"}, "has not merged"),
        ({"merged_at": None}, "has not merged"),
        ({"head_sha": "bad"}, "valid head_sha"),
        ({"landed": None}, "valid landed"),
        ({"number": 51}, "PR identity"),
        ({"number": True}, "PR identity"),
        ({"base_repository": "other/repo"}, "repository disagrees"),
        ({"base_repository": None}, "repository disagrees"),
    ],
)
def test_invalid_parent_metadata_fails_before_fetch(graph, cmd_mox, overrides, message):
    expect_parent(cmd_mox, graph, stdout=graph.capture(**overrides))
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match=message):
        planner.plan(graph.request())
    assert snapshot(graph.repository) == before
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


@pytest.mark.parametrize("stdout", ["not json", "[]", "null"])
def test_malformed_cli_output_is_not_treated_as_missing_history(graph, cmd_mox, stdout):
    expect_parent(cmd_mox, graph, stdout=stdout)
    with pytest.raises(planner.PlanError, match="metadata"):
        planner.plan(graph.request())


def test_real_gh_404_preserves_diagnostic_and_never_fetches(graph, cmd_mox):
    capture = MANIFEST["commands"]["missing-parent"]
    cmd_mox.mock("gh").with_args(*capture["argv"][1:]).returns(
        stdout=(FIXTURES / "missing-parent.stdout").read_text(),
        stderr=(FIXTURES / "missing-parent.stderr").read_text(),
        exit_code=capture["exit_code"],
    )
    with pytest.raises(
        planner.PlanError, match=r"gh exited 1: gh: Not Found \(HTTP 404\)"
    ):
        planner.plan(graph.request(parent_pr=2147483647))
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


def test_metadata_and_fetched_head_must_agree(graph, cmd_mox):
    expect_parent(cmd_mox, graph, stdout=graph.capture(head_sha=graph.a))
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="Fetched PR head disagrees"):
        planner.plan(graph.request())
    assert snapshot(graph.repository) == before


def test_parent_landing_must_be_on_target(graph, cmd_mox):
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="not reachable"):
        planner.plan(graph.request(target_ref=graph.trunk))
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


def test_missing_landing_object_is_an_error_not_negative_ancestry(graph, cmd_mox):
    expect_parent(cmd_mox, graph, stdout=graph.capture(landed="0" * 40))
    with pytest.raises(planner.PlanError, match="git exited"):
        planner.plan(graph.request())


def test_missing_pr_head_does_not_fall_back_to_synthetic_merge_ref(graph, cmd_mox):
    git(graph.remote, "update-ref", "-d", "refs/pull/50/head")
    git(graph.remote, "update-ref", "refs/pull/50/merge", graph.b)
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="git exited"):
        planner.plan(graph.request())


def test_shallow_checkout_stops_before_gh(graph):
    (graph.repository / ".git/shallow").write_text(graph.trunk + "\n")
    with pytest.raises(planner.PlanError, match="Shallow history"):
        planner.plan(graph.request())


@pytest.mark.parametrize(
    "state", ["untracked", "unstaged", "staged", "rebase", "sequencer"]
)
def test_occupied_checkout_stops_without_discarding_work(graph, state):
    if state in ("rebase", "sequencer"):
        (
            graph.repository
            / ".git"
            / ("rebase-merge" if state == "rebase" else "sequencer")
        ).mkdir()
    else:
        path = graph.repository / (
            "unrelated.txt" if state == "untracked" else "first.txt"
        )
        path.write_text("preserve me\n")
        if state == "staged":
            git(graph.repository, "add", "first.txt")
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="active Git operation|Preserve staged"):
        planner.plan(graph.request())
    assert snapshot(graph.repository) == before


def test_merge_containing_child_requires_another_procedure(graph, cmd_mox):
    git(graph.repository, "switch", "-c", "side", graph.b)
    from rebase_test_support import change

    change(graph.repository, "side", "side.txt", "side\n")
    git(graph.repository, "switch", "child")
    git(graph.repository, "merge", "--no-ff", "-m", "merge side", "side")
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="contains merges"):
        planner.plan(graph.request())


def test_empty_series_requires_a_noop_decision(graph, cmd_mox):
    git(graph.repository, "reset", "--hard", graph.b)
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    result = planner.plan(graph.request())
    assert result["status"] == "no-op-decision-required"
    assert result["commits"] == []
    assert result["rebase_argv"] is None
    assert snapshot(graph.repository) == before


def test_cli_main_emits_machine_readable_plan(graph, cmd_mox, capsys):
    expect_parent(cmd_mox, graph)
    planner.main(**dataclasses.asdict(graph.request()))
    result = json.loads(capsys.readouterr().out)
    assert result["commits"] == [graph.c, graph.d]
    assert result["rebase_argv"][-3:] == [graph.target, graph.b, "child"]
