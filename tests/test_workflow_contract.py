"""Contract tests for the mutation-testing caller workflow.

The executable logic lives in the ``leynos/shared-actions`` reusable
workflow, which carries its own unit and integration tests; this
repository's caller is declarative configuration. These tests parse the
caller with PyYAML and assert the contract it must uphold: that it
references the correct reusable workflow, pinned to a commit SHA (not a
mutable branch or tag), with the expected permissions, triggers, and
inputs. Dependabot owns the pinned SHA value itself, so these tests do
not assert which SHA is pinned — only that one is. Drift (repointing the
pin at a branch, widening permissions, or losing the hooks/
configuration) fails CI on the pull request rather than surfacing in a
scheduled or manual run.

Run via the repository ``make test`` target or directly with pytest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "mutation-testing.yml"
)

pytestmark = pytest.mark.skipif(
    not WORKFLOW_PATH.exists(),
    reason="workflow file not present in this working copy (e.g. "
    "inside mutmut's mutants/ sandbox, which does not copy .github/)",
)

#: Matches the mutmut reusable workflow pinned to a full 40-character
#: lowercase-hex commit SHA. Dependabot owns the SHA value; this test
#: only asserts the shape of the pin, not which commit it points at.
USES_RE = re.compile(
    r"^leynos/shared-actions/\.github/workflows/mutation-mutmut\.yml@"
    r"[0-9a-f]{40}$"
)

EXPECTED_WITH = {
    "paths": "hooks/",
    "module-prefix-strip": "",
}


def _load() -> dict[str, object]:
    """Parse the workflow file."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _triggers(workflow: dict[str, object]) -> dict[str, object]:
    """Return the ``on:`` mapping (PyYAML parses the bare key as True)."""
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "the workflow must declare an on: mapping"
    return triggers


def _mutation_job(workflow: dict[str, object]) -> dict[str, object]:
    """Return the single calling job."""
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "the workflow must declare a jobs mapping"
    assert list(jobs) == ["mutation"], (
        f"expected a single job named 'mutation', found {sorted(jobs or {})}"
    )
    return jobs["mutation"]


def test_uses_reference_is_pinned_to_a_commit_sha() -> None:
    """The job must call the correct shared workflow, pinned to a commit SHA.

    The exact SHA is not asserted: Dependabot owns bumping it, and a test
    that pinned the value would fail every Dependabot bump PR in lockstep.
    """
    uses = _mutation_job(_load()).get("uses")
    assert uses is not None, "jobs.mutation.uses is missing"
    assert USES_RE.match(uses), (
        f"jobs.mutation.uses must reference mutation-mutmut.yml pinned to a "
        f"full 40-character lowercase-hex commit SHA (not a branch or tag), "
        f"got {uses!r}"
    )


def test_job_permissions_are_exactly_least_privilege() -> None:
    """The job grants contents: read and id-token: write, nothing broader."""
    permissions = _mutation_job(_load()).get("permissions")
    assert permissions == {"contents": "read", "id-token": "write"}, (
        "jobs.mutation.permissions must be exactly "
        f"{{'contents': 'read', 'id-token': 'write'}}, got {permissions!r}"
    )


def test_workflow_default_permissions_are_empty() -> None:
    """The workflow-level default token scope is empty."""
    workflow = _load()
    assert workflow.get("permissions") == {}, (
        f"top-level permissions must be an empty mapping, got "
        f"{workflow.get('permissions')!r}"
    )


def test_concurrency_serializes_per_ref_without_cancelling() -> None:
    """Runs queue per ref instead of cancelling one another."""
    concurrency = _load().get("concurrency")
    assert isinstance(concurrency, dict), "the workflow must declare concurrency"
    assert concurrency.get("group") == "mutation-testing-${{ github.ref }}", (
        f"concurrency.group must key on the triggering ref, got "
        f"{concurrency.get('group')!r}"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        f"concurrency.cancel-in-progress must be false, got "
        f"{concurrency.get('cancel-in-progress')!r}"
    )


def test_triggers_keep_schedule_and_plain_dispatch() -> None:
    """The daily schedule stays; dispatch declares no inputs."""
    triggers = _triggers(_load())
    schedule = triggers.get("schedule")
    assert schedule == [{"cron": "50 12 * * *"}], (
        f"on.schedule must be the daily 12:50 UTC cron, got {schedule!r}"
    )
    assert "workflow_dispatch" in triggers, "on.workflow_dispatch is missing"
    dispatch = triggers.get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    assert not inputs, (
        f"on.workflow_dispatch must declare no inputs, got {sorted(inputs)}"
    )


def test_with_block_carries_the_caller_configuration() -> None:
    """The caller passes exactly the hooks/ flat-layout configuration."""
    with_block = _mutation_job(_load()).get("with")
    assert with_block == EXPECTED_WITH, (
        f"jobs.mutation.with must be exactly {EXPECTED_WITH!r}, "
        f"got {with_block!r}"
    )
