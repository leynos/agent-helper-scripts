"""Behavioural tests for the Actions capture procedures Scrutineer documents.

The `scrutineer` entry in `agents/subagents.yml` embeds three fenced `bash`
snippets: the deadline-bounded `gh run watch` call, the attempt-specific
`gh run view` snapshot, and the `--log-failed` retrieval. Those snippets are the
load-bearing part of the evidence contract, so these tests extract them from the
manifest and execute them against a cmd-mox `gh` double rather than merely
asserting that their text occurs.

Extracting rather than restating matters: a test that pasted its own copy of the
snippets would keep passing after the manifest drifted away from it, which is
precisely the regression worth catching. The snippets run verbatim, so a change
that breaks the contract breaks these scenarios.

The double replays representative real `gh` output. `RUN_VIEW_JSON` mirrors the
shape `gh run view --json status,conclusion,headSha,attempt,jobs,url` returns,
down to the `attempts/<n>` run URL and the nested `steps` array, and
`FAILED_STEP_LOG` reproduces the tab-separated `job\tstep\ttimestamp message`
form of `--log-failed`, including the literal `UNKNOWN STEP` attribution that
GitHub genuinely emits and that the instructions warn against trusting.

Three details of this boundary are easy to get wrong:

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
from pytest_bdd import given, parsers, scenarios, then, when
from subagent_manifest import load_subagent_entry

if typ.TYPE_CHECKING:
    from collections.abc import Callable

skip_if_unsupported()

BASH = shutil.which("bash")
TIMEOUT = shutil.which("timeout")

if BASH is None or TIMEOUT is None:  # pragma: no cover - environment guard.
    # Skip rather than raise: a RuntimeError here aborts collection for the
    # whole session, where these procedures are simply unobservable without a
    # shell and GNU coreutils.
    pytest.skip(
        "bash and timeout are required to run the Scrutineer procedure tests",
        allow_module_level=True,
    )

BASH_FENCE_RE = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)

REPOSITORY = "octo/example"
RUN_ID = "34488075549"
ATTEMPT = "2"
JOB_ID = 102907385381
HEAD_SHA = "28c3c64aea4664c17de9f94bd689f8c7c24e70bb"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}/attempts/{ATTEMPT}"
JOB_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}/job/{JOB_ID}"

# Shaped after real `gh run view --json status,conclusion,headSha,attempt,jobs,url`
# output, including the nested per-step array and the `attempts/<n>` run URL.
RUN_VIEW_JSON: dict[str, object] = {
    "attempt": int(ATTEMPT),
    "conclusion": "failure",
    "headSha": HEAD_SHA,
    "status": "completed",
    "url": RUN_URL,
    "jobs": [
        {
            "completedAt": "2026-09-10T14:18:10Z",
            "conclusion": "failure",
            "databaseId": JOB_ID,
            "name": "Makefile gates",
            "startedAt": "2026-09-10T14:17:37Z",
            "status": "completed",
            "url": JOB_URL,
            "steps": [
                {
                    "completedAt": "2026-09-10T14:17:37Z",
                    "conclusion": "success",
                    "name": "Check out repository",
                    "number": 2,
                    "startedAt": "2026-09-10T14:17:36Z",
                    "status": "completed",
                },
                {
                    "completedAt": "2026-09-10T14:18:10Z",
                    "conclusion": "failure",
                    "name": "Run CI gate sequence",
                    "number": 5,
                    "startedAt": "2026-09-10T14:17:37Z",
                    "status": "completed",
                },
            ],
        }
    ],
}

# Real `--log-failed` output is tab separated as `job\tstep\ttimestamp message`,
# and GitHub frequently attributes lines to `UNKNOWN STEP` rather than a real
# step. The instructions warn against trusting that attribution, so the double
# reproduces it rather than an idealized log.
FAILED_STEP_LOG = (
    "Makefile gates\tUNKNOWN STEP\t2026-09-10T14:17:31.5101381Z "
    "Current runner version: '2.337.0'\n"
    "Makefile gates\tRun CI gate sequence\t2026-09-10T14:18:09.8112340Z "
    "E   assert 1 == 2\n"
    "Makefile gates\tRun CI gate sequence\t2026-09-10T14:18:09.8112999Z "
    "make: *** [Makefile:80: test] Error 1\n"
)
LOG_RETRIEVAL_ERROR = (
    "failed to get run log: log expired for this attempt (HTTP 410)\n"
)
# `timeout` kills the shim with SIGTERM before it can report to the journal,
# so a marker written before the handler sleeps is the only durable evidence
# that the watcher actually started.
WATCHER_MARKER = "watcher-started.marker"

scenarios("features/scrutineer_actions_capture.feature")


# --------------------------------------------------------------------------- #
# Manifest extraction
# --------------------------------------------------------------------------- #


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
    preamble = textwrap.dedent(
        f"""\
        set -u
        repo="{REPOSITORY}"
        run_id="{RUN_ID}"
        attempt="{ATTEMPT}"
        bundle_dir="$BUNDLE_DIR"
        deadline_epoch=$(( $(date +%s) + ({deadline_offset}) ))
        """
    )
    report = textwrap.dedent(
        """
        printf 'watch_status=%s\\nview_status=%s\\nlogs_status=%s\\n' \\
          "$watch_status" "$view_status" "$logs_status"
        """
    )
    return preamble + _capture_procedure() + report


# --------------------------------------------------------------------------- #
# The `gh` double and the shell harness
# --------------------------------------------------------------------------- #


def _gh_handler(
    *,
    watch_exit: int,
    watch_delay: float,
    logs_exit: int,
    conclusion: str,
    status: str,
    bundle_dir: Path,
) -> Callable[[Invocation], tuple[str, str, int]]:
    """Build a `gh` double covering the three documented invocations.

    A pending run reports no conclusion at all, which is why `conclusion` is
    dropped rather than set to a placeholder when `status` is not `completed`.
    """
    payload = RUN_VIEW_JSON | {"conclusion": conclusion, "status": status}
    if status != "completed":
        payload = {k: v for k, v in payload.items() if k != "conclusion"}

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        args = invocation.args
        if args[:2] == ["run", "watch"]:
            # Written before sleeping so it survives the SIGTERM that `timeout`
            # sends, which is what stops the journal from witnessing the call.
            (bundle_dir / WATCHER_MARKER).touch()
            if watch_delay:
                time.sleep(watch_delay)
            return (f"✓ {REPOSITORY} Makefile gates\n", "", watch_exit)
        if args[:2] == ["run", "view"] and "--log-failed" in args:
            if logs_exit:
                return ("", LOG_RETRIEVAL_ERROR, logs_exit)
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


# --------------------------------------------------------------------------- #
# Scenario state
# --------------------------------------------------------------------------- #


@pytest.fixture
def capture(tmp_path: Path) -> dict[str, typ.Any]:
    """Hold the run's configuration and, once executed, its evidence."""
    return {
        "bundle_dir": tmp_path,
        "watch_exit": 0,
        "watch_delay": 0.0,
        "logs_exit": 0,
        "conclusion": "failure",
        "status": "completed",
    }


def _statuses(stdout: str) -> dict[str, int]:
    """Parse the trailing ``name=value`` status report from the procedure."""
    return {
        key: int(value)
        for key, _, value in (
            line.partition("=") for line in stdout.splitlines() if "=" in line
        )
    }


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #


@given("the manifest publishes the Actions capture procedures")
def _manifest_publishes_procedures() -> None:
    """The scenarios must exercise the manifest, not a private copy."""
    snippets = _scrutineer_snippets()

    assert len(snippets) == 3, (
        "Scrutineer's instructions must document exactly the watch, snapshot, "
        f"and failure-log snippets, found {len(snippets)}"
    )
    for needle in ("gh run watch", "--json status,conclusion", "--log-failed"):
        completed = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
            [BASH, "-n"],
            input=_snippet_containing(needle),
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, (
            f"the documented snippet for {needle!r} is not valid Bash: "
            f"{completed.stderr}"
        )


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
    capture["watch_exit"] = status


@given(parsers.parse("the watcher hangs for {seconds:d} seconds"))
def _watcher_hangs(capture: dict[str, typ.Any], seconds: int) -> None:
    """Make the doubled watcher outlive any plausible budget."""
    capture["watch_delay"] = float(seconds)


@given(parsers.parse("failed-step log retrieval exits with status {status:d}"))
def _logs_exit(capture: dict[str, typ.Any], status: int) -> None:
    """Set the exit status the doubled `--log-failed` retrieval returns."""
    capture["logs_exit"] = status


@when(
    parsers.parse(
        "the capture procedures run with {budget:d} seconds of budget remaining"
    )
)
def _run_procedures(capture: dict[str, typ.Any], budget: int) -> None:
    """Execute the documented snippets against the `gh` double."""
    bundle_dir = typ.cast("Path", capture["bundle_dir"])
    manager = EnvironmentManager()
    started = time.monotonic()
    with CmdMox(environment=manager) as mox:
        mox.stub("gh").runs(
            _gh_handler(
                watch_exit=capture["watch_exit"],
                watch_delay=capture["watch_delay"],
                logs_exit=capture["logs_exit"],
                conclusion=capture["conclusion"],
                status=capture["status"],
                bundle_dir=bundle_dir,
            )
        )
        mox.replay()
        # Built after replay so cmd-mox's PATH and IPC socket are inherited.
        environment = _child_environment(bundle_dir)
        shim_dir = manager.shim_dir
        assert shim_dir is not None, "cmd-mox must expose its shim directory"
        _assert_gh_is_doubled(environment, shim_dir)
        completed = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
            [BASH, "-c", _script(deadline_offset=budget)],
            cwd=bundle_dir,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
            stdin=subprocess.DEVNULL,
            env=environment,
        )
        capture["journal"] = list(mox.journal)
    capture["elapsed"] = time.monotonic() - started
    capture["statuses"] = _statuses(completed.stdout)
    capture["stderr"] = completed.stderr


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
    snapshot = json.loads((capture["bundle_dir"] / "run.json").read_text())

    assert capture["statuses"]["view_status"] == 0, (
        "the snapshot call must succeed regardless of the watcher's outcome"
    )
    assert snapshot["status"] == capture["status"], (
        "the snapshot must report the run's observed status, including a "
        "non-terminal one"
    )
    assert snapshot["attempt"] == int(ATTEMPT), (
        "the snapshot must be pinned to the observed attempt"
    )
    assert snapshot["url"] == RUN_URL


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


@then("no watcher was started")
def _assert_no_watcher(capture: dict[str, typ.Any]) -> None:
    """An already-spent budget must not start a watcher it cannot bound."""
    watches = [
        call for call in capture["journal"] if call.args[:2] == ["run", "watch"]
    ]

    assert watches == [], (
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
    delay = typ.cast("float", capture["watch_delay"])

    assert elapsed < delay, (
        "the deadline must stop the watcher, but the procedures took "
        f"{elapsed:.1f}s against a {delay:.0f}s watcher"
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


@then("every recorded status is zero")
def _assert_clean(capture: dict[str, typ.Any]) -> None:
    """A green run must not manufacture failure evidence."""
    assert capture["statuses"] == {
        "watch_status": 0,
        "view_status": 0,
        "logs_status": 0,
    }
