"""Exercise the real planner and Git graphs through cmd-mox's gh process shim."""

from __future__ import annotations

import dataclasses
import json
import typing as typ

import pytest
from rebase_test_support import (
    FIXTURES,
    MANIFEST,
    Graph,
    expect_parent,
    git,
    make_graph,
    oid,
    planner,
    snapshot,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

    from cmd_mox import CmdMox


@pytest.fixture
def graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Graph:
    """Build a fresh three-commit stacked-PR graph for each test."""
    return make_graph(tmp_path, monkeypatch)


def test_deleted_parent_plan_replays_only_child_commits(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Plan and replay only the child commits after the parent branch is deleted."""
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    result = planner.discover_and_plan(graph.request())
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    mode: str,
) -> None:
    """Refuse to trust a merge-base match without a receipt when history moved."""
    graph = make_graph(tmp_path, monkeypatch, mode)
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="Merge-base candidates are not proof"):
        planner.discover_and_plan(graph.request())
    assert snapshot(graph.repository) == before
    common = git(graph.repository, "merge-base", graph.parent, graph.d).stdout.strip()
    assert common == (graph.b if mode == "advanced" else graph.trunk)


@pytest.mark.parametrize("mode", ["advanced", "rewritten"])
def test_maintained_receipt_recovers_noninherited_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cmd_mox: CmdMox,
    mode: str,
) -> None:
    """Recover the correct boundary from a receipt when history has moved."""
    graph = make_graph(tmp_path, monkeypatch, mode)
    receipt = graph.receipt()
    expect_parent(cmd_mox, graph)
    result = planner.discover_and_plan(graph.request(boundary_ref=receipt))
    assert result["old_base"] == graph.b, "the receipt must supply the true boundary B"
    assert result["commits"] == [graph.c, graph.d], (
        "only the child's own commits may enter the replay range"
    )
    # A receipt is accepted here, but the recovered parent head is not in the
    # child's history, so nothing proves no inherited commit follows it.
    assert result["boundary_evidence"] == f"maintained-receipt:{receipt}", (
        "the plan must name the receipt as the boundary's provenance"
    )
    assert result["boundary_corroborated"] is False, (
        "a receipt on non-inherited parent history cannot be corroborated"
    )
    assert (
        result["review"][0]
        == planner.review_notes(
            planner.Boundary(
                graph.b, f"maintained-receipt:{receipt}", corroborated=False
            )
        )[0]
    ), "the uncorroborated-boundary warning must lead the review notes"
    assert result["review"][0].startswith("The receipt is uncorroborated:"), (
        "the leading review note must state the receipt is unproven"
    )
    git(graph.repository, *result["rebase_argv"][1:])
    assert (graph.repository / "first.txt").exists()
    assert (graph.repository / "second.txt").exists()
    assert (graph.repository / "target-only.txt").exists()
    if mode == "advanced":
        assert (graph.repository / "late.txt").exists()


@pytest.mark.parametrize("boundary", ["trunk", "c", "landed"])
def test_stale_off_by_one_or_squash_receipt_is_rejected(
    graph: Graph,
    cmd_mox: CmdMox,
    boundary: str,
) -> None:
    """Reject a receipt naming a stale, off-by-one, or squashed boundary."""
    receipt = graph.receipt(getattr(graph, boundary))
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="boundary"):
        planner.discover_and_plan(graph.request(boundary_ref=receipt))
    assert snapshot(graph.repository) == before


def test_receipt_must_belong_to_the_identified_parent(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Reject a receipt whose stackParent identity disagrees with branch config."""
    receipt = graph.receipt()
    git(graph.repository, "config", "branch.child.stackParent", "other/repo#50")
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="stackParent identity"):
        planner.discover_and_plan(graph.request(boundary_ref=receipt))


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
def test_invalid_parent_metadata_fails_before_fetch(
    graph: Graph,
    cmd_mox: CmdMox,
    overrides: dict[str, object],
    message: str,
) -> None:
    """Reject invalid parent PR metadata before any git fetch occurs."""
    expect_parent(cmd_mox, graph, stdout=graph.capture(**overrides))
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match=message):
        planner.discover_and_plan(graph.request())
    assert snapshot(graph.repository) == before
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


@pytest.mark.parametrize("stdout", ["not json", "[]", "null"])
def test_malformed_cli_output_is_not_treated_as_missing_history(
    graph: Graph,
    cmd_mox: CmdMox,
    stdout: str,
) -> None:
    """Treat malformed gh CLI output as a metadata failure, not missing history."""
    expect_parent(cmd_mox, graph, stdout=stdout)
    with pytest.raises(planner.PlanError, match="metadata"):
        planner.discover_and_plan(graph.request())


def test_real_gh_404_preserves_diagnostic_and_never_fetches(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Preserve the real gh 404 diagnostic and never attempt a fetch."""
    capture = MANIFEST["commands"]["missing-parent"]
    cmd_mox.mock("gh").with_args(*capture["argv"][1:]).returns(
        stdout=(FIXTURES / "missing-parent.stdout").read_text(),
        stderr=(FIXTURES / "missing-parent.stderr").read_text(),
        exit_code=capture["exit_code"],
    )
    with pytest.raises(
        planner.PlanError, match=r"gh exited 1: gh: Not Found \(HTTP 404\)"
    ):
        planner.discover_and_plan(graph.request(parent_pr=2147483647))
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


def test_metadata_and_fetched_head_must_agree(graph: Graph, cmd_mox: CmdMox) -> None:
    """Reject metadata whose head_sha disagrees with the fetched PR head."""
    expect_parent(cmd_mox, graph, stdout=graph.capture(head_sha=graph.a))
    before = snapshot(graph.repository)
    with pytest.raises(planner.PlanError, match="Fetched PR head disagrees"):
        planner.discover_and_plan(graph.request())
    assert snapshot(graph.repository) == before


def test_parent_landing_must_be_on_target(graph: Graph, cmd_mox: CmdMox) -> None:
    """Reject a parent landing commit that is not reachable from the target."""
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="not reachable"):
        planner.discover_and_plan(graph.request(target_ref=graph.trunk))
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout


def test_missing_landing_object_is_an_error_not_negative_ancestry(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Treat a missing landing object as a git error, not negative ancestry."""
    expect_parent(cmd_mox, graph, stdout=graph.capture(landed="0" * 40))
    with pytest.raises(planner.PlanError, match="git exited"):
        planner.discover_and_plan(graph.request())


def test_missing_pr_head_does_not_fall_back_to_synthetic_merge_ref(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Refuse to fall back to the synthetic merge ref when the PR head is missing."""
    git(graph.remote, "update-ref", "-d", "refs/pull/50/head")
    git(graph.remote, "update-ref", "refs/pull/50/merge", graph.b)
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="git exited"):
        planner.discover_and_plan(graph.request())


def test_shallow_checkout_stops_before_gh(graph: Graph) -> None:
    """Stop on a shallow checkout before invoking gh."""
    (graph.repository / ".git/shallow").write_text(graph.trunk + "\n")
    with pytest.raises(planner.PlanError, match="Shallow history"):
        planner.discover_and_plan(graph.request())


@pytest.mark.parametrize(
    "state", ["untracked", "unstaged", "staged", "rebase", "sequencer"]
)
def test_occupied_checkout_stops_without_discarding_work(
    graph: Graph,
    state: str,
) -> None:
    """Stop without discarding work when the checkout has other pending state."""
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
        planner.discover_and_plan(graph.request())
    assert snapshot(graph.repository) == before


def test_merge_containing_child_requires_another_procedure(
    graph: Graph,
    cmd_mox: CmdMox,
) -> None:
    """Refuse to plan when the child branch history contains a merge commit."""
    git(graph.repository, "switch", "-c", "side", graph.b)
    from rebase_test_support import change

    change(graph.repository, "side", "side.txt", "side\n")
    git(graph.repository, "switch", "child")
    git(graph.repository, "merge", "--no-ff", "-m", "merge side", "side")
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError, match="contains merges"):
        planner.discover_and_plan(graph.request())


def test_empty_series_requires_a_noop_decision(graph: Graph, cmd_mox: CmdMox) -> None:
    """Require an explicit no-op decision when the commit series is empty."""
    git(graph.repository, "reset", "--hard", graph.b)
    expect_parent(cmd_mox, graph)
    before = snapshot(graph.repository)
    result = planner.discover_and_plan(graph.request())
    assert result["status"] == "no-op-decision-required"
    assert result["commits"] == []
    assert result["rebase_argv"] is None
    assert snapshot(graph.repository) == before


def test_cli_main_emits_machine_readable_plan(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Emit a machine-readable JSON plan from the CLI entry point."""
    expect_parent(cmd_mox, graph)
    planner.main(**dataclasses.asdict(graph.request()))
    result = json.loads(capsys.readouterr().out)
    assert result["commits"] == [graph.c, graph.d]
    assert result["rebase_argv"][-3:] == [graph.target, graph.b, "child"]


def test_cli_main_blocks_with_status_two_and_no_plan_on_stdout(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report a blocked run as exit status 2 and a JSON reason on stderr alone."""
    # An unmerged parent is refused deterministically, before any fetch.
    expect_parent(cmd_mox, graph, stdout=graph.capture(merged=False, merged_at=None))
    with pytest.raises(SystemExit) as excinfo:
        planner.main(**dataclasses.asdict(graph.request()))

    assert excinfo.value.code == 2, "a blocked run must exit with status 2"
    captured = capsys.readouterr()
    assert captured.out == "", "a blocked run must not print a plan on stdout"
    blocked = json.loads(captured.err.strip().splitlines()[-1])
    assert blocked == {
        "status": "blocked",
        "reason": "The parent PR has not merged",
        "category": planner.CATEGORY_METADATA,
    }, "the blocked object must carry the status, reason and bounded category"
    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout, (
        "a blocked run must leave no evidence ref behind"
    )
