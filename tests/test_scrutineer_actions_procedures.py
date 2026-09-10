"""Behavioural tests for the Actions capture procedures Scrutineer documents.

The `scrutineer` entry in `agents/subagents.yml` embeds three fenced `bash`
snippets: the bounded `gh run watch` call, the attempt-specific `gh run view`
snapshot, and the `--log-failed` retrieval. Those snippets are the load-bearing
part of the evidence contract, so these tests extract them from the manifest and
execute them against a cmd-mox `gh` double rather than merely asserting that
their text occurs.

Extracting rather than restating matters: a test that pasted its own copy of the
snippets would keep passing after the manifest drifted away from it, which is
precisely the regression worth catching. The snippets run verbatim, so a change
that breaks the contract breaks these tests.

Two details of this boundary are easy to get wrong:

- A cmd-mox shim reads its standard input, so the shell runs with
  `stdin=DEVNULL`. Inheriting pytest's stdin wedges the shim and the shell
  waiting on it.
- cmd-mox rewrites `PATH` and `CMOX_IPC_SOCKET` in `os.environ` when replay
  starts, so the child environment must be built *after* `mox.replay()`.
- `BASH_ENV` makes a non-interactive `bash -c` source a startup file, and such a
  file commonly prepends a directory to `PATH`. That silently shadows the shim
  with the operator's real `gh`, which would turn these tests into live GitHub
  calls. It is cleared, and `_assert_gh_is_doubled` then refuses to run the
  procedure unless `gh` still resolves inside the shim directory.

Only `gh` is doubled. `bash`, `date`, and `timeout` are the real programs,
because the deadline mechanism under test is precisely the interaction between
`timeout` and the watcher's exit status.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
import time
import typing as typ
from pathlib import Path

import pytest
from cmd_mox import CmdMox, EnvironmentManager, skip_if_unsupported
from cmd_mox.ipc import Invocation
from subagent_manifest import load_subagent_entry

if typ.TYPE_CHECKING:
    from collections.abc import Callable

skip_if_unsupported()

BASH = shutil.which("bash")
TIMEOUT = shutil.which("timeout")

if BASH is None:  # pragma: no cover - bash is a repository test prerequisite.
    raise RuntimeError("bash is required to run the Scrutineer procedure tests")

if TIMEOUT is None:  # pragma: no cover - coreutils is a test prerequisite.
    raise RuntimeError("timeout is required to run the Scrutineer procedure tests")

BASH_FENCE_RE = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)

REPOSITORY = "octo/example"
RUN_ID = "12345"
ATTEMPT = "2"

# `gh run view --json ...` output for a run that completed unsuccessfully.
FAILED_RUN_JSON = {
    "status": "completed",
    "conclusion": "failure",
    "headSha": "0" * 40,
    "attempt": int(ATTEMPT),
    "jobs": [{"databaseId": 99, "name": "gates", "conclusion": "failure"}],
    "url": f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}",
}
SUCCESSFUL_RUN_JSON = FAILED_RUN_JSON | {"conclusion": "success", "jobs": []}
FAILED_STEP_LOG = "gates\tRun make test\tE   assert 1 == 2\n"


def _scrutineer_snippets() -> list[str]:
    """Return the fenced bash snippets from Scrutineer's instructions."""
    instructions = typ.cast("str", load_subagent_entry("scrutineer")["instructions"])
    return [
        textwrap.dedent(match.group("body"))
        for match in BASH_FENCE_RE.finditer(instructions)
    ]


def _snippet_containing(needle: str) -> str:
    """Return the single documented snippet that contains ``needle``.

    Selecting by content rather than by position keeps the tests bound to the
    procedure they exercise, so reordering the manifest cannot silently swap one
    snippet for another.
    """
    matches = [snippet for snippet in _scrutineer_snippets() if needle in snippet]
    if len(matches) != 1:
        message = (
            f"expected exactly one documented snippet containing {needle!r}, "
            f"found {len(matches)}"
        )
        raise AssertionError(message)
    return matches[0]


def _capture_procedure() -> str:
    """Compose the documented snippets into the order the instructions give."""
    return "\n".join(
        (
            _snippet_containing("gh run watch"),
            _snippet_containing("--json status,conclusion"),
            _snippet_containing("--log-failed"),
        )
    )


def _script(*, deadline_offset: int) -> str:
    """Wrap the documented snippets in the bindings the instructions assume.

    ``set -u`` is deliberate: an unbound variable in a documented snippet is a
    defect in the manifest, not something the harness should paper over.
    """
    return textwrap.dedent(
        f"""\
        set -u
        repo="{REPOSITORY}"
        run_id="{RUN_ID}"
        attempt="{ATTEMPT}"
        bundle_dir="$BUNDLE_DIR"
        deadline_epoch=$(( $(date +%s) + ({deadline_offset}) ))
        """
    ) + _capture_procedure() + textwrap.dedent(
        """
        printf 'watch_status=%s\\nview_status=%s\\nlogs_status=%s\\n' \\
          "$watch_status" "$view_status" "$logs_status"
        """
    )


def _gh_handler(
    *,
    watch_exit: int = 0,
    watch_delay: float = 0.0,
    logs_exit: int = 0,
    run_json: dict[str, object] | None = None,
) -> Callable[[Invocation], tuple[str, str, int]]:
    """Build a `gh` double covering the three documented invocations."""
    payload = FAILED_RUN_JSON if run_json is None else run_json

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        args = invocation.args
        if args[:2] == ["run", "watch"]:
            if watch_delay:
                time.sleep(watch_delay)
            return (f"* gates in {REPOSITORY}\n", "", watch_exit)
        if args[:2] == ["run", "view"] and "--log-failed" in args:
            if logs_exit:
                return ("", "log expired for this attempt\n", logs_exit)
            return (FAILED_STEP_LOG, "", 0)
        if args[:2] == ["run", "view"] and "--json" in args:
            return (json.dumps(payload), "", 0)
        return ("", f"unexpected gh invocation: {args}\n", 2)  # pragma: no cover

    return handler


def _child_environment(bundle_dir: Path) -> dict[str, str]:
    """Build the child environment cmd-mox's shim needs, and nothing else.

    `BASH_ENV` is dropped deliberately: a startup file that edits `PATH` would
    shadow the shim with a real `gh`.
    """
    environment = os.environ | {"BUNDLE_DIR": str(bundle_dir)}
    environment.pop("BASH_ENV", None)
    return environment


def _assert_gh_is_doubled(environment: dict[str, str], shim_dir: Path) -> None:
    """Fail loudly rather than let the procedure reach the real `gh`."""
    resolved = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
        [BASH, "-c", "command -v gh"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        stdin=subprocess.DEVNULL,
        env=environment,
    ).stdout.strip()

    if Path(resolved).parent != shim_dir:
        message = (
            f"`gh` must resolve to the cmd-mox shim in {shim_dir}, but the shell "
            f"resolved it to {resolved!r}; refusing to run against a real `gh`"
        )
        raise AssertionError(message)


def _run_procedure(
    bundle_dir: Path,
    *,
    deadline_offset: int = 300,
    **handler_options: object,
) -> tuple[subprocess.CompletedProcess[str], list[Invocation]]:
    """Execute the documented snippets against a cmd-mox `gh` double."""
    manager = EnvironmentManager()
    with CmdMox(environment=manager) as mox:
        mox.stub("gh").runs(_gh_handler(**handler_options))  # type: ignore[arg-type]
        mox.replay()
        # Built after replay so cmd-mox's PATH and IPC socket are inherited.
        environment = _child_environment(bundle_dir)
        shim_dir = manager.shim_dir
        assert shim_dir is not None, "cmd-mox must expose its shim directory"
        _assert_gh_is_doubled(environment, shim_dir)
        completed = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
            [BASH, "-c", _script(deadline_offset=deadline_offset)],
            cwd=bundle_dir,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
            stdin=subprocess.DEVNULL,
            env=environment,
        )
        journal = list(mox.journal)
    return completed, journal


def _statuses(completed: subprocess.CompletedProcess[str]) -> dict[str, int]:
    """Parse the trailing ``name=value`` status report from the procedure."""
    return {
        key: int(value)
        for key, _, value in (
            line.partition("=") for line in completed.stdout.splitlines() if "=" in line
        )
    }


def _watch_invocations(journal: list[Invocation]) -> list[Invocation]:
    """Return the `gh run watch` calls recorded by the double."""
    return [call for call in journal if call.args[:2] == ["run", "watch"]]


def test_manifest_documents_exactly_three_capture_snippets() -> None:
    """The procedures under test must be the ones the manifest publishes."""
    snippets = _scrutineer_snippets()

    assert len(snippets) == 3, (
        "Scrutineer's instructions must document exactly the watch, snapshot, "
        f"and failure-log snippets, found {len(snippets)}"
    )


@pytest.mark.parametrize(
    "needle",
    ["gh run watch", "--json status,conclusion", "--log-failed"],
)
def test_documented_snippets_are_valid_bash(needle: str) -> None:
    """A snippet the agent is told to run must at least parse as Bash."""
    snippet = _snippet_containing(needle)

    completed = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
        [BASH, "-n"],
        input=snippet,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, (
        f"the documented snippet for {needle!r} is not valid Bash: "
        f"{completed.stderr}"
    )


def test_watcher_failure_still_captures_metadata_and_failure_logs(
    tmp_path: Path,
) -> None:
    """A failing watcher must not suppress the evidence the summoner needs."""
    completed, _journal = _run_procedure(tmp_path, watch_exit=1)
    statuses = _statuses(completed)

    assert statuses["watch_status"] == 1, "the watcher's failure must be preserved"
    assert statuses["view_status"] == 0, (
        "the attempt snapshot must still be captured after a failing watcher"
    )
    assert statuses["logs_status"] == 0, (
        "failure-log retrieval must not be gated on watcher success"
    )
    assert json.loads((tmp_path / "run.json").read_text())["conclusion"] == "failure"
    assert FAILED_STEP_LOG in (tmp_path / "failed.log").read_text()


def test_expired_deadline_skips_the_watcher_but_still_snapshots(
    tmp_path: Path,
) -> None:
    """An already-spent budget must not start a watcher it cannot bound."""
    completed, journal = _run_procedure(tmp_path, deadline_offset=-5)
    statuses = _statuses(completed)

    assert statuses["watch_status"] == 124, (
        "an exhausted deadline must report the deadline-reached status"
    )
    assert _watch_invocations(journal) == [], (
        "no watcher may start once the observation deadline has passed"
    )
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "completed", (
        "the attempt snapshot must be captured even when no watcher ran"
    )


def test_slow_watcher_is_bounded_by_the_observation_deadline(
    tmp_path: Path,
) -> None:
    """`gh run watch` has no timeout flag, so `timeout` must supply the bound."""
    started = time.monotonic()
    completed, _journal = _run_procedure(
        tmp_path,
        deadline_offset=1,
        watch_delay=30.0,
    )
    elapsed = time.monotonic() - started
    statuses = _statuses(completed)

    assert statuses["watch_status"] == 124, (
        "a watcher outliving the deadline must report the deadline-reached "
        "status rather than a workflow verdict"
    )
    # The journal cannot witness this call: `timeout` kills the shim before it
    # reports back, which is exactly the behaviour under test. Elapsed time is
    # the available evidence that the watcher started and was then bounded.
    assert 1 <= elapsed < 30, (
        "the watcher must run until the deadline and then stop, but it ran for "
        f"{elapsed:.1f}s"
    )
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "completed", (
        "the attempt snapshot must be captured after the deadline stops the watcher"
    )


@pytest.mark.parametrize("watch_exit", [0, 1, 124, 143])
def test_snapshot_capture_is_independent_of_the_watcher_outcome(
    tmp_path: Path,
    watch_exit: int,
) -> None:
    """No watcher exit status may suppress the attempt snapshot.

    The watcher's exit status forms a small closed set — success, workflow
    failure, deadline, and signal — so these are enumerated rather than
    generated. The invariant is that `view_status` is derived from the snapshot
    call alone and never from `watch_status`.
    """
    completed, _journal = _run_procedure(tmp_path, watch_exit=watch_exit)
    statuses = _statuses(completed)

    assert statuses["watch_status"] == watch_exit, (
        "the watcher's own exit status must be preserved verbatim"
    )
    assert statuses["view_status"] == 0, (
        f"the snapshot must be captured after watcher exit {watch_exit}"
    )
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "completed"


def test_failure_log_retrieval_error_is_recorded_separately(tmp_path: Path) -> None:
    """A missing log is a retrieval failure, not a change to the conclusion."""
    completed, _journal = _run_procedure(tmp_path, watch_exit=1, logs_exit=1)
    statuses = _statuses(completed)

    assert statuses["logs_status"] == 1, (
        "the log-retrieval exit code must be recorded on its own"
    )
    assert statuses["watch_status"] == 1, (
        "log-retrieval failure must not overwrite the watcher's outcome"
    )
    assert json.loads((tmp_path / "run.json").read_text())["conclusion"] == "failure", (
        "the observed conclusion must survive a failed log retrieval"
    )
    assert (tmp_path / "failed-log.stderr").read_text().strip(), (
        "the retrieval error must be preserved in the bundle"
    )


def test_successful_run_records_clean_statuses(tmp_path: Path) -> None:
    """A green run must not manufacture failure evidence."""
    completed, _journal = _run_procedure(tmp_path, run_json=SUCCESSFUL_RUN_JSON)
    statuses = _statuses(completed)

    assert statuses == {"watch_status": 0, "view_status": 0, "logs_status": 0}
    assert json.loads((tmp_path / "run.json").read_text())["conclusion"] == "success"
