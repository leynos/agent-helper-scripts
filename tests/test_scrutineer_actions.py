"""Pin Scrutineer's Actions monitoring and evidence hand-off instructions.

These are manifest contract tests, not live GitHub integration tests. They
protect the delegated workflow without changing provider permissions or
introducing a second implementation of the GitHub CLI.
"""

from __future__ import annotations

import re
import shlex
from typing import cast

import pytest
from subagent_manifest import load_subagent_entry


def _text(field: str) -> str:
    """Return one Scrutineer field with prose wrapping normalized."""
    return " ".join(cast("str", load_subagent_entry("scrutineer")[field]).split())


def _commands(prefix: str) -> list[list[str]]:
    """Extract complete inline command examples with the requested prefix."""
    examples = re.findall(r"`([^`]+)`", _text("instructions"))
    return [shlex.split(example) for example in examples if example.startswith(prefix)]


@pytest.mark.parametrize(
    "capability",
    (
        "deterministic commit gates",
        "CodeRabbit review monitoring",
        "gh run watch",
        "summary bundle",
        "captured failure logs",
        "summoning agent",
    ),
)
def test_description_advertises_all_scrutineer_capabilities(capability: str) -> None:
    """Agent selection must expose Actions watching as well as existing roles."""
    assert capability in _text("description")


def test_actions_only_scope_does_not_trigger_gates_or_review() -> None:
    """Remote observation must not implicitly spend local gate or review work."""
    instructions = _text("instructions")
    assert "Actions-only assignment, record `monitoring-only` gate scope" in instructions
    assert "do not run local gates or request CodeRabbit unless separately instructed" in instructions
    assert "does not waive the gate prerequisite" in instructions
    assert "every applicable deterministic gate above passed" in instructions


def test_watch_command_is_noninteractive_scoped_and_failure_aware() -> None:
    """The runnable watch example must identify its run and preserve failure."""
    assert _commands('gh run watch "$run_id"') == [
        [
            "gh", "run", "watch", "$run_id", "--repo", "$repo",
            "--interval", "10", "--exit-status",
        ]
    ]
    instructions = _text("instructions")
    assert "actual watcher exit status in `watch.exit`" in instructions
    assert "A nonzero exit must not abort evidence collection" in instructions
    assert "Retain the execution session handle" in instructions
    assert "At the monitoring deadline, stop the local watcher, not the remote workflow" in instructions


def test_run_discovery_and_metadata_examples_have_valid_argument_boundaries() -> None:
    """Wrapped JSON field lists must remain a single command-line argument."""
    examples = _commands("gh ")
    json_commands = [command for command in examples if "--json" in command]
    assert len(json_commands) == 4
    for command in json_commands:
        assert command[command.index("--repo") + 1] == "$repo"
        fields = command[command.index("--json") + 1:]
        assert len(fields) == 1, f"JSON fields split across arguments: {command}"
        assert all(re.fullmatch(r"[A-Za-z]+", field) for field in fields[0].split(","))
    discovery = _commands("gh run list")
    assert len(discovery) == 1
    assert discovery[0][discovery[0].index("--commit") + 1] == "$expected_sha"


@pytest.mark.parametrize(
    "contract",
    (
        "Keep PR-head results separate from post-merge integration results",
        "workflow and its run ID, URL, event, head SHA, and attempt",
        "A truncated list or no matching runs is incomplete evidence, not success",
        "For a synthetic PR or merge-queue commit",
        "report `superseded`; never mix a failed attempt with a later successful rerun",
        "Only `status=completed` with `conclusion=success` establishes run success",
        "monitoring error separate from any independently observed CI result",
        "Missing runs, pending runs, and unavailable checks cannot support an all-green verdict",
    ),
)
def test_monitoring_preserves_identity_and_evidence_limits(contract: str) -> None:
    """A watcher exit or an unrelated green run must not become CI evidence."""
    assert contract in _text("instructions")


def test_failure_log_commands_pin_attempt_and_offer_job_fallback() -> None:
    """Failure evidence must be captured, not replaced by a short summary."""
    views = _commands('gh run view "$run_id"')
    failed = [command for command in views if "--log-failed" in command]
    jobs = [command for command in views if "--log" in command]
    assert len(failed) == len(jobs) == 1
    for command in failed + jobs:
        assert command[command.index("--repo") + 1] == "$repo"
        assert command[command.index("--attempt") + 1] == "$attempt"
    assert jobs[0][jobs[0].index("--job") + 1] == "$job_id"
    instructions = _text("instructions")
    assert "Save retrieval stderr separately as `failed-log.stderr` and its exit status" in instructions
    assert "report `logs-unavailable` with the reason" in instructions


@pytest.mark.parametrize(
    "contract",
    (
        "Do not rerun, cancel, or dispatch workflows, approve deployments",
        "Do not change credentials or install tools",
        "redact secrets from excerpts",
        "do not post raw logs publicly or commit them to the repository",
        "Keep local gate, CodeRabbit, and GitHub Actions verdicts separate",
        "Never substitute a five-line excerpt for the captured log",
    ),
)
def test_monitoring_remains_observation_only(contract: str) -> None:
    """Monitoring authority must not expand into repair or publication."""
    assert contract in _text("instructions")


@pytest.mark.parametrize(
    "evidence",
    (
        "summary.md", "runs.json", "before.json", "run.json", "watch.log",
        "watch.exit", "failed.log", "failed-log.stderr",
    ),
)
def test_actions_bundle_names_required_evidence(evidence: str) -> None:
    """The caller must receive metadata, progress output, and failure evidence."""
    assert f"`{evidence}`" in _text("instructions")


def test_report_returns_actions_results_and_accessible_bundle() -> None:
    """Actions evidence must be part of the mandatory summoning-agent report."""
    raw = cast("str", load_subagent_entry("scrutineer")["instructions"])
    report = raw.split("Output exactly this structure:", 1)[1]
    assert report.index("## CodeRabbit Review") < report.index("## GitHub Actions Results")
    assert report.index("## GitHub Actions Results") < report.index("## Next Action")
    for field in ("- Monitoring:", "- Scope:", "- CI verdict:", "- Runs:", "- Failures:", "- Bundle:", "- Evidence gaps:"):
        assert field in report
    instructions = _text("instructions")
    assert "Verify that it can access these files" in instructions
    assert "attachment or context-pack hand-off when filesystems differ" in instructions
