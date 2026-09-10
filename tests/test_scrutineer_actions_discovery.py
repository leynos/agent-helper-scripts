"""Contract tests for Scrutineer's Actions candidate resolution procedures.

These execute the published discovery, verification, and recheck procedures from
`agents/subagents.yml` against an argument-validating `gh` double. See
`tests/scrutineer_actions_support.py` for the harness and for why the double
refuses anything addressed at the wrong repository, run, attempt, or commit.

The negative controls at the end of this module are load-bearing. They point the
double at a different assignment than the procedures are driven with, and assert
that the mismatch is caught. Without them, a validator that silently accepted
everything would leave every scenario above passing for the wrong reason.
"""

from __future__ import annotations

import typing as typ

import pytest
from cmd_mox import CmdMox, EnvironmentManager, skip_if_unsupported
from pytest_bdd import given, parsers, scenarios, then, when
from scrutineer_actions_support import (
    MISSING_PREREQUISITES,
    PR_CHECKS_TSV_DUPLICATED,
    Assignment,
    GhDouble,
    assert_gh_is_doubled,
    child_environment,
    preamble,
    run_script,
    scrutineer_snippets,
    snippet_containing,
)

if typ.TYPE_CHECKING:
    from pathlib import Path

skip_if_unsupported()

if MISSING_PREREQUISITES:  # pragma: no cover - environment guard.
    pytest.skip(
        f"{', '.join(MISSING_PREREQUISITES)} are required to run the Scrutineer "
        "procedure tests",
        allow_module_level=True,
    )

PUBLISHED_SNIPPET_COUNT = 7

# Each procedure is selected by a fragment unique to it, so reordering the
# manifest cannot silently swap one procedure for another.
PR_RESOLUTION = "gh pr checks"
COMMIT_RESOLUTION = "gh run list"
VERIFICATION = "candidate_state="
RECHECK = "attempt.superseded"

scenarios("features/scrutineer_actions_discovery.feature")


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


@pytest.fixture
def context(tmp_path: Path) -> dict[str, typ.Any]:
    """Hold the assignment, double configuration, and captured evidence."""
    return {
        "bundle_dir": tmp_path,
        "assignment": Assignment(),
        "double_assignment": None,
        "options": {},
    }


def _execute(context: dict[str, typ.Any], procedure: str) -> None:
    """Run a published procedure against the doubled `gh`."""
    assignment = typ.cast("Assignment", context["assignment"])
    bundle_dir = typ.cast("Path", context["bundle_dir"])
    double = GhDouble(
        context["double_assignment"] or assignment,
        bundle_dir=bundle_dir,
        **context["options"],
    )
    manager = EnvironmentManager()
    with CmdMox(environment=manager) as mox:
        mox.stub("gh").runs(double.handler())
        # Registered so an accidental gate or review call is recorded as a
        # command that ran, rather than failing as "not found" and looking like
        # an unrelated error.
        for forbidden in ("make", "coderabbit", "git"):
            mox.register_command(forbidden)
        mox.replay()
        # Built after replay so cmd-mox's PATH and IPC socket are inherited.
        environment = child_environment(bundle_dir)
        shim_dir = manager.shim_dir
        assert shim_dir is not None, "cmd-mox must expose its shim directory"
        assert_gh_is_doubled(environment, shim_dir)
        completed = run_script(
            preamble(assignment) + procedure,
            bundle_dir=bundle_dir,
            environment=environment,
        )
        context["journal"] = list(mox.journal)
    context["double"] = double
    context["completed"] = completed


def _lines(context: dict[str, typ.Any], name: str) -> list[str]:
    """Return the non-empty lines of a bundle artefact, or an empty list."""
    path = context["bundle_dir"] / name
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Given
# --------------------------------------------------------------------------- #


@given("the manifest publishes the Actions monitoring procedures")
def _manifest_publishes_procedures() -> None:
    """The scenarios must exercise the manifest, not a private copy."""
    snippets = scrutineer_snippets()

    assert len(snippets) == PUBLISHED_SNIPPET_COUNT, (
        "Scrutineer's instructions must publish the full monitoring workflow "
        f"as executable snippets, found {len(snippets)}"
    )
    for needle in (PR_RESOLUTION, COMMIT_RESOLUTION, VERIFICATION, RECHECK):
        snippet_containing(needle)


@given("a pull request whose checks include two jobs of the same run")
def _pr_with_duplicate_jobs(context: dict[str, typ.Any]) -> None:
    """Two jobs of one run make the deduplication requirement observable."""
    context["options"]["pr_checks"] = PR_CHECKS_TSV_DUPLICATED


@given("runs exist for the expected commit")
def _runs_exist(context: dict[str, typ.Any]) -> None:
    """Use the double's default run list for the expected commit."""
    context["options"]["run_list"] = None


@given("no runs exist for the expected commit")
def _no_runs(context: dict[str, typ.Any]) -> None:
    """An empty list is the not-yet-created case, not a successful one."""
    context["options"]["run_list"] = []


@given(parsers.parse('a candidate run for event "{event}" at the expected commit'))
def _candidate_at_expected(context: dict[str, typ.Any], event: str) -> None:
    """Configure a candidate whose head matches the assignment."""
    assignment = typ.cast("Assignment", context["assignment"])
    context["options"]["candidate"] = {
        "databaseId": int(assignment.run_id),
        "workflowName": "CI",
        "event": event,
        "headSha": assignment.expected_sha,
        "status": "completed",
        "conclusion": "success",
        "attempt": int(assignment.attempt),
        "url": f"https://github.com/{assignment.repo}/actions/runs/{assignment.run_id}",
    }


@given(parsers.parse('a candidate run for event "{event}" at commit "{sha}"'))
def _candidate_at_other(context: dict[str, typ.Any], event: str, sha: str) -> None:
    """Configure a candidate whose head does not match the assignment."""
    assignment = typ.cast("Assignment", context["assignment"])
    context["options"]["candidate"] = {
        "databaseId": int(assignment.run_id),
        "workflowName": "CI",
        "event": event,
        "headSha": sha,
        "status": "completed",
        "conclusion": "success",
        "attempt": int(assignment.attempt),
        "url": f"https://github.com/{assignment.repo}/actions/runs/{assignment.run_id}",
    }


@given(parsers.parse('the latest attempt is now "{attempt}"'))
def _latest_attempt(context: dict[str, typ.Any], attempt: str) -> None:
    """Set the attempt the recheck will observe upstream."""
    context["options"]["latest_attempt"] = attempt


# --------------------------------------------------------------------------- #
# When
# --------------------------------------------------------------------------- #


@when("the PR candidate resolution procedure runs")
def _run_pr_resolution(context: dict[str, typ.Any]) -> None:
    """Execute the published PR candidate resolution procedure."""
    _execute(context, snippet_containing(PR_RESOLUTION))


@when("the commit candidate resolution procedure runs")
def _run_commit_resolution(context: dict[str, typ.Any]) -> None:
    """Execute the published exact-commit resolution procedure."""
    _execute(context, snippet_containing(COMMIT_RESOLUTION))


@when("the candidate verification procedure runs")
def _run_verification(context: dict[str, typ.Any]) -> None:
    """Execute the published candidate verification procedure."""
    _execute(context, snippet_containing(VERIFICATION))


@when("the attempt recheck procedure runs")
def _run_recheck(context: dict[str, typ.Any]) -> None:
    """Execute the published attempt recheck procedure."""
    _execute(context, snippet_containing(RECHECK))


@when("the full monitoring-only workflow runs")
def _run_full_workflow(context: dict[str, typ.Any]) -> None:
    """Execute resolution, verification, watch, snapshot, and recheck in order."""
    procedure = "\n".join(
        (
            snippet_containing(PR_RESOLUTION),
            snippet_containing(VERIFICATION),
            snippet_containing("gh run watch"),
            snippet_containing("--json status,conclusion"),
            snippet_containing(RECHECK),
        )
    )
    _execute(context, procedure)


# --------------------------------------------------------------------------- #
# Then
# --------------------------------------------------------------------------- #


@then(parsers.parse('the candidate runs are exactly "{expected}"'))
def _assert_candidates(context: dict[str, typ.Any], expected: str) -> None:
    """Candidate IDs must be parsed from the links and deduplicated."""
    wanted = [item.strip() for item in expected.split(",")]

    assert _lines(context, "candidate-runs.txt") == wanted


@then("the candidate runs are empty")
def _assert_no_candidates(context: dict[str, typ.Any]) -> None:
    """A commit with no runs must yield no candidates to watch."""
    assert _lines(context, "candidate-runs.txt") == []


@then("the pull request head and base are recorded")
def _assert_pr_recorded(context: dict[str, typ.Any]) -> None:
    """PR-head evidence needs the head and base it is associated with."""
    import json

    assignment = typ.cast("Assignment", context["assignment"])
    payload = json.loads((context["bundle_dir"] / "pr.json").read_text())

    assert payload["headRefOid"] == assignment.expected_sha
    assert payload["baseRefName"] == assignment.base_ref


@then(parsers.parse('the non-Actions checks are recorded as "{expected}"'))
def _assert_non_actions(context: dict[str, typ.Any], expected: str) -> None:
    """App and status checks are classified, never treated as workflow runs."""
    wanted = [item.strip() for item in expected.split(",")]

    assert _lines(context, "non-actions-checks.txt") == wanted


@then("no non-Actions check appears among the candidate runs")
def _assert_no_leak(context: dict[str, typ.Any]) -> None:
    """A check without an Actions link must not become a run identity."""
    candidates = _lines(context, "candidate-runs.txt")

    assert all(candidate.isdigit() for candidate in candidates), candidates
    for name in _lines(context, "non-actions-checks.txt"):
        assert name not in candidates


@then("the run list was requested for the expected commit")
def _assert_commit_query(context: dict[str, typ.Any]) -> None:
    """Commit-scoped resolution must query the exact commit, not a branch."""
    assignment = typ.cast("Assignment", context["assignment"])
    calls = context["double"].calls("run", "list")

    assert calls, "the procedure must call `gh run list`"
    assert "--commit" in calls[0]
    assert calls[0][calls[0].index("--commit") + 1] == assignment.expected_sha


@then("no missing-candidates note is written")
def _assert_no_missing_note(context: dict[str, typ.Any]) -> None:
    """A populated run list is not a missing-run case."""
    assert not (context["bundle_dir"] / "candidates.missing").exists()


@then("a missing-candidates note names the expected commit")
def _assert_missing_note(context: dict[str, typ.Any]) -> None:
    """An empty run list must be recorded, never read as success."""
    assignment = typ.cast("Assignment", context["assignment"])
    note = (context["bundle_dir"] / "candidates.missing").read_text()

    assert assignment.expected_sha in note, note


@then(parsers.parse('the candidate state is "{state}"'))
def _assert_candidate_state(context: dict[str, typ.Any], state: str) -> None:
    """Identity verification must classify the candidate explicitly."""
    identity = (context["bundle_dir"] / "candidate-identity.txt").read_text()

    assert f"state={state}" in identity, identity


@then("the candidate was verified before any watch or evidence call")
def _assert_verify_first(context: dict[str, typ.Any]) -> None:
    """Only verified identities may enter the watch and evidence steps."""
    invocations = context["double"].invocations
    verifying = [
        index
        for index, args in enumerate(invocations)
        if args[:2] == ["run", "view"] and "--json" in args
    ]

    assert verifying, "the procedure must verify the candidate with `gh run view`"
    watching = [
        index for index, args in enumerate(invocations) if args[:2] == ["run", "watch"]
    ]
    assert all(verifying[0] < index for index in watching), invocations


@then(parsers.parse('the evidence is marked superseded by attempt "{attempt}"'))
def _assert_superseded(context: dict[str, typ.Any], attempt: str) -> None:
    """A rerun must not silently inherit the previous attempt's verdict."""
    note = (context["bundle_dir"] / "attempt.superseded").read_text()

    assert f"latest attempt {attempt}" in note, note


@then("the evidence is not marked superseded")
def _assert_not_superseded(context: dict[str, typ.Any]) -> None:
    """An unchanged attempt must not be reported as stale."""
    assert not (context["bundle_dir"] / "attempt.superseded").exists()


@then("no local gate or review command was invoked")
def _assert_monitoring_only(context: dict[str, typ.Any]) -> None:
    """Monitoring-only assignments must not launch unrequested work."""
    forbidden = [
        call.command
        for call in context["journal"]
        if call.command in {"make", "coderabbit"}
    ]

    assert forbidden == [], (
        f"a monitoring-only assignment invoked {forbidden}; gates and review "
        "must be reported as not-requested rather than run"
    )


@then("every gh call addressed the assigned repository and run")
def _assert_no_violations(context: dict[str, typ.Any]) -> None:
    """The double validates every argument; nothing may have slipped through."""
    assert context["double"].violations == [], context["double"].violations


# --------------------------------------------------------------------------- #
# Negative controls
#
# These prove the double actually validates. Each drives the procedures with the
# correct assignment while the double expects a different one, so a validator
# that accepted anything would make these fail.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("field", "wrong_value", "expected_fragment"),
    [
        ("repo", "octo/other", "--repo must be"),
        ("run_id", "99999999", "run ID must be"),
        ("attempt", "9", "--attempt must be"),
        ("expected_sha", "0" * 40, "--commit must be"),
        ("pr_number", "999", "PR number must be"),
    ],
)
def test_double_rejects_a_mismatched_identity(
    tmp_path: Path,
    field: str,
    wrong_value: str,
    expected_fragment: str,
) -> None:
    """A procedure addressing the wrong identity must not pass unnoticed."""
    import dataclasses as dc

    context: dict[str, typ.Any] = {
        "bundle_dir": tmp_path,
        "assignment": Assignment(),
        # The double expects a different identity than the procedures use.
        "double_assignment": dc.replace(Assignment(), **{field: wrong_value}),
        "options": {"pr_checks": PR_CHECKS_TSV_DUPLICATED},
    }
    procedure = "\n".join(
        (
            snippet_containing(PR_RESOLUTION),
            snippet_containing(COMMIT_RESOLUTION),
            snippet_containing(VERIFICATION),
            snippet_containing("gh run watch"),
            snippet_containing("--json status,conclusion"),
        )
    )

    _execute(context, procedure)

    violations = context["double"].violations
    assert any(expected_fragment in violation for violation in violations), (
        f"a wrong {field} must be caught, got {violations}"
    )


def test_required_flags_are_enforced(tmp_path: Path) -> None:
    """A procedure dropping a required flag must be caught, not tolerated."""
    context: dict[str, typ.Any] = {
        "bundle_dir": tmp_path,
        "assignment": Assignment(),
        "double_assignment": None,
        "options": {},
    }
    # Stand in for a manifest that regressed by dropping `--exit-status`.
    mutated = snippet_containing("gh run watch").replace(" --exit-status", "")

    _execute(context, mutated)

    assert any("--exit-status" in violation for violation in context["double"].violations), (
        context["double"].violations
    )
