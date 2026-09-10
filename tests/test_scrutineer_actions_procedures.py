"""Contract tests for Scrutineer's Actions evidence-capture procedures.

These execute the published watch, snapshot, and failure-log procedures from
`agents/subagents.yml` verbatim against an argument-validating `gh` double. See
`tests/scrutineer_actions_support.py` for the harness, the network-isolation
guards, and why the double refuses calls addressed at the wrong run or attempt.

`tests/test_scrutineer_actions_discovery.py` covers the resolution and
verification procedures that select a candidate before any of this runs.
"""

from __future__ import annotations

import json
import time
import typing as typ

import pytest
from cmd_mox import CmdMox, EnvironmentManager, skip_if_unsupported
from pytest_bdd import given, parsers, scenarios, then, when
from scrutineer_actions_support import (
    MISSING_PREREQUISITES,
    Assignment,
    GhDouble,
    assert_gh_is_doubled,
    child_environment,
    preamble,
    run_script,
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

WATCH = "gh run watch"
SNAPSHOT = "--json status,conclusion"
FAILURE_LOGS = "--log-failed"
WATCHER_MARKER = "watcher-started.marker"

scenarios("features/scrutineer_actions_capture.feature")


def _capture_procedure() -> str:
    """Compose the published capture procedures in the documented order."""
    return "\n".join(
        (
            snippet_containing(WATCH),
            snippet_containing(SNAPSHOT),
            snippet_containing(FAILURE_LOGS),
        )
    )


def _report() -> str:
    """Ask the shell for the status variables the procedures set."""
    return (
        "\nprintf 'watch_status=%s\\nview_status=%s\\nlogs_status=%s\\n' "
        '"$watch_status" "$view_status" "$logs_status"\n'
    )


def _statuses(stdout: str) -> dict[str, int]:
    """Parse the trailing ``name=value`` status report from the procedures."""
    return {
        key: int(value)
        for key, _, value in (
            line.partition("=") for line in stdout.splitlines() if "=" in line
        )
    }


@pytest.fixture
def capture(tmp_path: Path) -> dict[str, typ.Any]:
    """Hold the run's configuration and, once executed, its evidence."""
    return {
        "bundle_dir": tmp_path,
        "assignment": Assignment(),
        "conclusion": "failure",
        "status": "completed",
        "options": {},
    }


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #


@given("the manifest publishes the Actions capture procedures")
def _manifest_publishes_procedures() -> None:
    """The scenarios must exercise the manifest, not a private copy."""
    for needle in (WATCH, SNAPSHOT, FAILURE_LOGS):
        snippet_containing(needle)


@given(parsers.parse('a run that completed with conclusion "{conclusion}"'))
def _run_conclusion(capture: dict[str, typ.Any], conclusion: str) -> None:
    """Set the conclusion the doubled snapshot reports."""
    capture["conclusion"] = conclusion


@given(parsers.parse('a run that is still "{status}"'))
def _run_pending(capture: dict[str, typ.Any], status: str) -> None:
    """Set a non-terminal status, for which no conclusion exists yet."""
    capture["status"] = status
    capture["conclusion"] = ""


@given(parsers.parse("the watcher exits with status {status:d}"))
def _watcher_exit(capture: dict[str, typ.Any], status: int) -> None:
    """Set the exit status the doubled watcher returns."""
    capture["options"]["watch_exit"] = status


@given(parsers.parse("the watcher hangs for {seconds:d} seconds"))
def _watcher_hangs(capture: dict[str, typ.Any], seconds: int) -> None:
    """Make the doubled watcher outlive any plausible budget."""
    capture["options"]["watch_delay"] = float(seconds)


@given(parsers.parse("failed-step log retrieval exits with status {status:d}"))
def _logs_exit(capture: dict[str, typ.Any], status: int) -> None:
    """Set the exit status the doubled `--log-failed` retrieval returns."""
    capture["options"]["logs_exit"] = status


@when(
    parsers.parse(
        "the capture procedures run with {budget:d} seconds of budget remaining"
    )
)
def _run_procedures(capture: dict[str, typ.Any], budget: int) -> None:
    """Execute the published capture procedures against the `gh` double."""
    assignment = typ.cast("Assignment", capture["assignment"])
    bundle_dir = typ.cast("Path", capture["bundle_dir"])
    candidate: dict[str, object] = {
        "databaseId": int(assignment.run_id),
        "workflowName": "CI",
        "event": "pull_request",
        "headSha": assignment.expected_sha,
        "status": capture["status"],
        "conclusion": capture["conclusion"],
        "attempt": int(assignment.attempt),
        "url": (
            f"https://github.com/{assignment.repo}/actions/runs/"
            f"{assignment.run_id}/attempts/{assignment.attempt}"
        ),
        "jobs": [],
    }
    if capture["status"] != "completed":
        # A pending run reports no conclusion at all, so the key is dropped
        # rather than set to a placeholder the real CLI would never emit.
        del candidate["conclusion"]

    double = GhDouble(
        assignment,
        candidate=candidate,
        bundle_dir=bundle_dir,
        watcher_marker=WATCHER_MARKER,
        **capture["options"],
    )
    manager = EnvironmentManager()
    started = time.monotonic()
    with CmdMox(environment=manager) as mox:
        mox.stub("gh").runs(double.handler())
        mox.replay()
        # Built after replay so cmd-mox's PATH and IPC socket are inherited.
        environment = child_environment(bundle_dir)
        shim_dir = manager.shim_dir
        assert shim_dir is not None, "cmd-mox must expose its shim directory"
        assert_gh_is_doubled(environment, shim_dir)
        completed = run_script(
            preamble(assignment, deadline_offset=budget)
            + _capture_procedure()
            + _report(),
            bundle_dir=bundle_dir,
            environment=environment,
        )
        capture["journal"] = list(mox.journal)
    capture["elapsed"] = time.monotonic() - started
    capture["statuses"] = _statuses(completed.stdout)
    capture["stderr"] = completed.stderr
    capture["double"] = double

    assert double.violations == [], double.violations


@then(parsers.parse("the watcher status is recorded as {status:d}"))
def _assert_watch_status(capture: dict[str, typ.Any], status: int) -> None:
    """The watcher's own outcome must survive verbatim."""
    assert capture["statuses"]["watch_status"] == status, (
        f"expected watch_status {status}, got {capture['statuses']}; "
        f"stderr: {capture['stderr']}"
    )


@then(parsers.parse("the log retrieval status is recorded as {status:d}"))
def _assert_logs_status(capture: dict[str, typ.Any], status: int) -> None:
    """Retrieval failure is recorded on its own, not folded into the verdict."""
    assert capture["statuses"]["logs_status"] == status, (
        f"expected logs_status {status}, got {capture['statuses']}"
    )


@then("the attempt snapshot is captured")
def _assert_snapshot(capture: dict[str, typ.Any]) -> None:
    """`run.json` is unconditional evidence, whatever the watcher did."""
    assignment = typ.cast("Assignment", capture["assignment"])
    snapshot = json.loads((capture["bundle_dir"] / "run.json").read_text())

    assert capture["statuses"]["view_status"] == 0, (
        "the snapshot call must succeed regardless of the watcher's outcome"
    )
    assert snapshot["status"] == capture["status"], (
        "the snapshot must report the run's observed status, including a "
        "non-terminal one"
    )
    assert snapshot["attempt"] == int(assignment.attempt), (
        "the snapshot must be pinned to the observed attempt"
    )
    assert assignment.run_id in snapshot["url"]


@then(parsers.parse('the recorded conclusion is "{conclusion}"'))
def _assert_conclusion(capture: dict[str, typ.Any], conclusion: str) -> None:
    """The observed conclusion must not be rewritten by any later step."""
    snapshot = json.loads((capture["bundle_dir"] / "run.json").read_text())

    assert snapshot["conclusion"] == conclusion


@then("the failed-step log is captured")
def _assert_failed_log(capture: dict[str, typ.Any]) -> None:
    """Failure-log collection is never gated on the watcher succeeding."""
    failed_log = (capture["bundle_dir"] / "failed.log").read_text()

    assert capture["statuses"]["logs_status"] == 0
    assert "E   assert 1 == 2" in failed_log, (
        "the decisive failure line must reach the bundle"
    )
    assert "UNKNOWN STEP" in failed_log, (
        "real --log-failed output carries UNKNOWN STEP lines; the bundle must "
        "preserve them rather than discard the surrounding context"
    )


@then("the retrieval error is preserved in the bundle")
def _assert_retrieval_error(capture: dict[str, typ.Any]) -> None:
    """A missing log is evidence in itself and must not be silently dropped."""
    stderr_path = capture["bundle_dir"] / "failed-log.stderr"

    assert stderr_path.read_text().strip(), (
        "the retrieval error must be preserved in the bundle"
    )


@then("no failure-log artefact is written")
def _assert_no_failure_artefacts(capture: dict[str, typ.Any]) -> None:
    """Failure logs belong only to a run that completed unsuccessfully."""
    bundle = typ.cast("Path", capture["bundle_dir"])

    for name in ("failed.log", "failed-log.stderr"):
        assert not (bundle / name).exists(), (
            f"{name} must not exist for a run that did not complete "
            "unsuccessfully; an empty artefact is indistinguishable from a "
            "retrieval that returned nothing"
        )


@then(
    parsers.parse(
        'the omission records status "{status}" and conclusion "{conclusion}"'
    )
)
def _assert_omission_recorded(
    capture: dict[str, typ.Any],
    status: str,
    conclusion: str,
) -> None:
    """An absent artefact must say why, not merely be missing."""
    note = (capture["bundle_dir"] / "failed-log.omitted").read_text()

    assert f"status={status}" in note, note
    assert f"conclusion={conclusion}" in note, note


@then("no watcher was started")
def _assert_no_watcher(capture: dict[str, typ.Any]) -> None:
    """An already-spent budget must not start a watcher it cannot bound."""
    assert capture["double"].calls("run", "watch") == [], (
        "no watcher may start once the observation deadline has passed"
    )
    assert not (capture["bundle_dir"] / WATCHER_MARKER).exists(), (
        "the watcher double must never have been entered"
    )


@then("the watcher was started")
def _assert_watcher_started(capture: dict[str, typ.Any]) -> None:
    """Separate a bounded watcher from one that never ran.

    Both report `watch_status=124`, so without this the scenario could pass on
    the exhausted-budget path it is meant to be distinct from.
    """
    assert (capture["bundle_dir"] / WATCHER_MARKER).exists(), (
        "the watcher must have started before the deadline stopped it"
    )


@then("the procedures finish before the watcher would have")
def _assert_bounded(capture: dict[str, typ.Any]) -> None:
    """`gh run watch` has no timeout flag, so `timeout` must supply the bound.

    Only the upper bound is asserted. A lower bound on elapsed time would be a
    wall-clock race, and it is not what distinguishes this scenario anyway: the
    watcher-started marker already separates "started, then stopped" from "never
    started because the budget was spent".
    """
    elapsed = typ.cast("float", capture["elapsed"])
    delay = typ.cast("float", capture["options"]["watch_delay"])

    assert elapsed < delay, (
        "the deadline must stop the watcher, but the procedures took "
        f"{elapsed:.1f}s against a {delay:.0f}s watcher"
    )


@then("every recorded status is zero")
def _assert_clean(capture: dict[str, typ.Any]) -> None:
    """A green run must not manufacture failure evidence."""
    assert capture["statuses"] == {
        "watch_status": 0,
        "view_status": 0,
        "logs_status": 0,
    }
