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
    change,
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


def _records(stderr: str) -> list[dict[str, object]]:
    """Parse every diagnostic line; each must be one bounded JSON object."""
    records = []
    for line in stderr.strip().splitlines():
        record = json.loads(line)
        assert isinstance(record, dict), "every stderr line must be a JSON object"
        records.append(record)
    return records


def _finished(records: list[dict[str, object]], phase: str) -> dict[str, object]:
    """Return the single `phase-finished` record closing the named phase."""
    matches = [
        record
        for record in records
        if record.get("event") == "phase-finished" and record.get("phase") == phase
    ]
    assert len(matches) == 1, f"expected exactly one phase-finished for {phase}"
    return matches[0]


def test_cli_main_blocks_with_status_two_and_no_plan_on_stdout(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report a blocked run as exit 2 and one bounded terminal record on stderr."""
    # An unmerged parent is refused deterministically, in a known phase,
    # before any fetch, so every asserted field below is stable.
    expect_parent(cmd_mox, graph, stdout=graph.capture(merged=False, merged_at=None))
    before = snapshot(graph.repository)
    with pytest.raises(SystemExit) as excinfo:
        planner.main(**dataclasses.asdict(graph.request()))

    assert excinfo.value.code == 2, "a blocked run must exit with status 2"
    captured = capsys.readouterr()
    assert captured.out == "", "a blocked run must not print a plan on stdout"

    records = _records(captured.err)
    blocked = records[-1]
    assert set(blocked) == {
        "status",
        "operation",
        "phase",
        "outcome",
        "category",
        "reason",
    }, "the terminal record must carry exactly the documented bounded fields"
    assert blocked["status"] == planner.STATUS_BLOCKED
    assert blocked["phase"] == planner.PHASE_PARENT_METADATA, (
        "the failing phase must come from typed context, not parsed prose"
    )
    assert blocked["outcome"] == planner.OUTCOME_BLOCKED
    assert blocked["category"] == planner.CATEGORY_METADATA
    assert blocked["reason"] == "The parent PR has not merged"
    assert blocked["operation"], "the terminal record must carry the operation ID"
    assert {record.get("operation") for record in records} == {blocked["operation"]}, (
        "every diagnostic must share the one operation identifier"
    )

    # The operation span closes as blocked, naming the phase that refused.
    span = next(record for record in records if record["event"] == "operation-finished")
    assert span["outcome"] == planner.OUTCOME_BLOCKED
    assert span["phase"] == planner.PHASE_PARENT_METADATA
    assert span["error_category"] == planner.CATEGORY_METADATA

    assert not git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout, (
        "a blocked run must leave no evidence ref behind"
    )
    assert snapshot(graph.repository) == before, (
        "a blocked run must not move a ref or touch the index or worktree"
    )


def test_process_boundary_failure_closes_its_phase_as_blocked(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failing Git process closes landing-validation with the process category."""
    # A landing commit that is not an object makes git exit non-zero, which is a
    # process-boundary failure rather than a negative ancestry answer.
    expect_parent(cmd_mox, graph, stdout=graph.capture(landed="0" * 40))
    with pytest.raises(planner.PlanError) as excinfo:
        planner.discover_and_plan(graph.request())

    assert excinfo.value.category == planner.CATEGORY_PROCESS
    assert excinfo.value.context is not None, "a refusal must carry typed context"
    assert excinfo.value.context.phase == planner.PHASE_LANDING_VALIDATION

    finished = _finished(_records(capsys.readouterr().err), "landing-validation")
    assert finished["outcome"] == planner.OUTCOME_BLOCKED
    assert finished["error_category"] == planner.CATEGORY_PROCESS
    assert isinstance(finished["elapsed_ms"], int), (
        "the phase record must carry a bounded elapsed duration"
    )


def test_graph_policy_failure_closes_its_phase_as_blocked(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A merge inside the range closes graph-planning with the range category."""
    git(graph.repository, "switch", "-c", "side", graph.b)
    change(graph.repository, "side", "side.txt", "side\n")
    git(graph.repository, "switch", "child")
    git(graph.repository, "merge", "--no-ff", "-m", "merge side", "side")
    expect_parent(cmd_mox, graph)
    with pytest.raises(planner.PlanError) as excinfo:
        planner.discover_and_plan(graph.request())

    assert excinfo.value.category == planner.CATEGORY_RANGE
    assert excinfo.value.context is not None, "a refusal must carry typed context"
    assert excinfo.value.context.phase == planner.PHASE_GRAPH_PLANNING

    records = _records(capsys.readouterr().err)
    finished = _finished(records, "graph-planning")
    assert finished["outcome"] == planner.OUTCOME_BLOCKED
    assert finished["error_category"] == planner.CATEGORY_RANGE
    assert isinstance(finished["elapsed_ms"], int)
    # Earlier phases still closed cleanly, so a late refusal stays attributable.
    assert _finished(records, "preflight")["outcome"] == planner.OUTCOME_OK
    assert _finished(records, "boundary-selection")["outcome"] == planner.OUTCOME_OK


def test_successful_run_closes_every_phase_and_the_operation_span(
    graph: Graph,
    cmd_mox: CmdMox,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every phase and the operation span report ok with a bounded duration."""
    expect_parent(cmd_mox, graph)
    planner.main(**dataclasses.asdict(graph.request()))

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == planner.STATUS_REVIEW_REQUIRED
    records = _records(captured.err)
    for name in (
        "preflight",
        "parent-metadata",
        "landing-validation",
        "parent-head-fetch",
        "boundary-selection",
        "graph-planning",
    ):
        finished = _finished(records, name)
        assert finished["outcome"] == planner.OUTCOME_OK, f"{name} must close as ok"
        assert isinstance(finished["elapsed_ms"], int), f"{name} must be timed"
        assert "error_category" not in finished, (
            f"{name} succeeded, so it must report no error category"
        )

    span = next(record for record in records if record["event"] == "operation-finished")
    assert span["outcome"] == planner.OUTCOME_OK
    assert span["phase"] == planner.PHASE_OPERATION
    assert isinstance(span["elapsed_ms"], int)


def test_build_plan_never_invokes_the_discovery_command_layer(
    graph: Graph, cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The read path plans from a snapshot without gh, a fetch, or a new ref."""
    expect_parent(cmd_mox, graph)
    evidence = planner.discover(graph.request())

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("build_plan must not invoke the discovery operation")

    monkeypatch.setattr(planner, "discover", forbidden)
    monkeypatch.setattr(planner, "_new_evidence_ref", forbidden)
    monkeypatch.setattr(planner, "_new_operation_id", forbidden)

    seen: list[tuple[str, ...]] = []
    real = planner.Subprocess(graph.repository)

    def recording(program: str, /, *argv: str, allowed: tuple[int, ...] = (0,)) -> str:
        seen.append((program, *argv))
        return real(program, *argv, allowed=allowed)

    before = snapshot(graph.repository)
    refs_before = git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout
    result = planner.build_plan(graph.request(), evidence, recording)

    assert result["commits"] == [graph.c, graph.d]
    assert result["operation"] == evidence.operation, (
        "the read path must reuse the snapshot's operation, never mint one"
    )
    assert seen, "the read path is expected to query the local graph"
    assert all(program == "git" for program, *_ in seen), (
        "the read path must never run gh"
    )
    assert not any("fetch" in argv for _, *argv in seen), (
        "the read path must never fetch"
    )
    assert not any(
        argv[0] in {"update-ref", "push", "rebase", "commit"}
        for _, *argv in seen
        if argv
    ), "the read path must never write a ref or mutate history"
    assert git(graph.repository, "for-each-ref", "refs/agent-rebase").stdout == (
        refs_before
    ), "the read path must create no new evidence ref"
    assert snapshot(graph.repository) == before


def test_build_plan_is_repeatable_on_one_snapshot(
    graph: Graph, cmd_mox: CmdMox
) -> None:
    """Re-planning the same snapshot yields the same plan, so it is a query."""
    expect_parent(cmd_mox, graph)
    evidence = planner.discover(graph.request())
    first = planner.build_plan(graph.request(), evidence)
    second = planner.build_plan(graph.request(), evidence)
    assert first == second, "the read path must be free of run-to-run state"
