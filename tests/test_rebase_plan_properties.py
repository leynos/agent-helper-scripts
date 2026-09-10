"""Property tests for the replay range the squash-restack planner derives.

These exercise `build_plan` directly. The query/command split means plan
construction needs no GitHub CLI and no fetch, so a generated history can be
checked many times over without a process double.
"""

from __future__ import annotations

import itertools
import os
import typing as typ

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from rebase_test_support import change, git, oid, planner

if typ.TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# The `build` fixture is function-scoped and so is not reset between generated
# inputs. That is safe here because each call creates its own repository
# directory, so no state carries between examples.
SAFE_REUSE = (HealthCheck.function_scoped_fixture, HealthCheck.too_slow)

PARENT_LENGTHS = st.integers(min_value=1, max_value=4)
CHILD_LENGTHS = st.integers(min_value=0, max_value=4)
TARGET_LENGTHS = st.integers(min_value=0, max_value=2)


class Linear(typ.NamedTuple):
    """A generated linear history and the identities a plan must respect."""

    repository: Path
    parent: list[str]
    child: list[str]
    target: str
    landed: str


@pytest.fixture
def build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[int, int, int], Linear]:
    """Return a builder producing one isolated linear history per call."""
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    counter = itertools.count()

    def make(parent_length: int, child_length: int, target_length: int) -> Linear:
        """Build one M-P*-C* graph with a squash landing and a target tip."""
        repository = tmp_path / f"graph-{next(counter)}"
        repository.mkdir()
        git(repository, "init", "--quiet", "--initial-branch=main")
        git(repository, "config", "user.name", "Rebase property test")
        git(repository, "config", "user.email", "rebase@example.invalid")
        git(repository, "config", "commit.gpgsign", "false")
        change(repository, "M", "root.txt", "root\n")
        git(repository, "switch", "--quiet", "-c", "old-parent")
        parent = [
            change(repository, f"P{index}", "parent.txt", f"parent {index}\n")
            for index in range(parent_length)
        ]
        git(repository, "switch", "--quiet", "-c", "child")
        child = [
            change(repository, f"C{index}", f"child-{index}.txt", f"child {index}\n")
            for index in range(child_length)
        ]
        git(repository, "switch", "--quiet", "main")
        git(repository, "merge", "--squash", "old-parent")
        git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", "S")
        landed = oid(repository)
        for index in range(target_length):
            change(repository, f"T{index}", f"target-{index}.txt", f"target {index}\n")
        target = oid(repository)
        git(repository, "update-ref", "refs/remotes/origin/main", target)
        git(repository, "switch", "--quiet", "child")
        git(repository, "branch", "-D", "old-parent")
        return Linear(repository, parent, child, target, landed)

    return make


def _evidence(graph: Linear, parent_head: str) -> object:
    """Freeze the observations `discover` would have gathered for this graph."""
    return planner.Evidence(
        operation="property",
        old_head=graph.child[-1] if graph.child else parent_head,
        target=graph.target,
        landed=graph.landed,
        parent_head=parent_head,
        evidence_ref="refs/agent-rebase/property/parent-head",
        metadata={},
    )


def _request(graph: Linear, **overrides: object) -> object:
    """Build a planner request naming the generated child branch."""
    values: dict[str, object] = {
        "repository": graph.repository,
        "branch": "child",
        "target_ref": "refs/remotes/origin/main",
        "parent_repository": "leynos/agent-helper-scripts",
        "parent_pr": 50,
    }
    values.update(overrides)
    return planner.Request(**values)


@settings(deadline=None, max_examples=25, suppress_health_check=SAFE_REUSE)
@given(
    parent_length=PARENT_LENGTHS,
    child_length=CHILD_LENGTHS,
    target_length=TARGET_LENGTHS,
)
def test_inherited_parent_replays_child_commits_and_nothing_else(
    build, parent_length: int, child_length: int, target_length: int
) -> None:
    """An inherited parent head yields exactly the child commits, in order."""
    graph = build(parent_length, child_length, target_length)
    parent_head = graph.parent[-1]
    result = planner.build_plan(_request(graph), _evidence(graph, parent_head))

    assert result["old_base"] == parent_head
    assert result["boundary_evidence"] == "parent-pr-head"
    assert result["boundary_corroborated"] is True
    assert result["commits"] == graph.child
    assert not set(result["commits"]) & set(graph.parent)
    assert graph.landed not in result["commits"]
    if graph.child:
        assert result["status"] == "review-required"
        assert result["rebase_argv"][-3:] == [graph.target, parent_head, "child"]
    else:
        assert result["status"] == "no-op-decision-required"
        assert result["rebase_argv"] is None


@settings(deadline=None, max_examples=25, suppress_health_check=SAFE_REUSE)
@given(
    parent_length=st.integers(min_value=2, max_value=4),
    child_length=st.integers(min_value=1, max_value=3),
    receipt_index=st.integers(min_value=0, max_value=3),
)
def test_receipt_disagreeing_with_inherited_parent_head_is_refused(
    build, parent_length: int, child_length: int, receipt_index: int
) -> None:
    """A receipt naming any earlier inherited commit never authorizes a replay."""
    graph = build(parent_length, child_length, 1)
    parent_head = graph.parent[-1]
    boundary = graph.parent[receipt_index % (parent_length - 1)]
    git(graph.repository, "update-ref", "refs/stack-bases/child", boundary)
    git(
        graph.repository,
        "config",
        "branch.child.stackParent",
        "leynos/agent-helper-scripts#50",
    )
    request = _request(graph, boundary_ref="refs/stack-bases/child")

    with pytest.raises(planner.PlanError, match="disagrees with the inherited parent"):
        planner.build_plan(request, _evidence(graph, parent_head))
