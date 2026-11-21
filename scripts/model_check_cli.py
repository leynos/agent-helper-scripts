#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5", "cuprum==0.2.0b2"]
# ///
"""Install the pinned FizzBee release and run a model-checking suite.

The judgement lives in the sibling ``model_check`` module, which imports
nothing beyond the standard library. This module is its command line and its
process boundary: Cuprum launches the checker and the one download, and a
checker that outlives its timeout is cancelled, which Cuprum turns into
``SIGTERM`` and then ``SIGKILL``.

Examples
--------
Fetch and verify the pinned checker, then run the mandatory suite::

    uv run --script scripts/model_check_cli.py install \\
        --suite specs/pr-readiness/suite.toml
    uv run --script scripts/model_check_cli.py check \\
        --suite specs/pr-readiness/suite.toml

Parameters are environment-aware, so ``MODEL_CHECK_HOME`` relocates the
checker and ``MODEL_CHECK_JOBS`` sets the parallelism.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
import contextlib
import os
from pathlib import Path
import platform
import resource
import sys
import threading
import time
from typing import Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import (
    ExecutionContext,
    ProcessGroupPolicy,
    Program,
    ProgramCatalogue,
    RunOutputOptions,
    scoped,
    sh,
)

import model_check

#: How long one download may take.
DOWNLOAD_TIMEOUT_SECONDS = 1800

#: How often a running command checks for its deadline and for an interrupt.
POLL_SECONDS = 0.2


def current_host() -> model_check.Host:
    """Return the facts about the running machine the commands read.

    This is the only place the commands read the platform, the processor
    count, the home directory, the clock or the resource counters. The
    checker home is under ``~/.cache``, whose name keeps the 680 MB tree out
    of code indexes and the Markdown gate's walk.
    """
    return model_check.Host(
        platform=(platform.system(), platform.machine()),
        cpu_count=os.cpu_count() or 1,
        home=Path.home() / ".cache" / "fizzbee",
        clock=time.monotonic,
        peak_child_rss_kib=lambda: resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    )


def _process_result(result: object, seconds: float) -> model_check.ProcessResult:
    """Return what Cuprum reported, with a signal read as no exit status.

    A signal's exit status is reported as no exit status at all, so the
    judgement cannot mistake an interrupted checker for one that finished.
    """
    code = getattr(result, "exit_code", None)
    stopped = code is None or not 0 <= code <= 128
    return model_check.ProcessResult(
        exit_code=None if stopped else code,
        stdout=getattr(result, "stdout", None) or "",
        stderr=getattr(result, "stderr", None) or "",
        seconds=seconds,
    )


async def _await_or_stop(
    task: asyncio.Future, deadline: float, clock: Callable[[], float], cancelled: threading.Event
) -> str:
    """Wait for ``task``, or stop it at the deadline or on an interrupt.

    Returns ``finished``, ``timeout`` or ``interrupt``. Stopping cancels the
    Cuprum task and waits for it, which is what sends the command's process
    group ``SIGTERM`` and then ``SIGKILL``.
    """
    while not task.done():
        if cancelled.is_set():
            reason = "interrupt"
        elif clock() >= deadline:
            reason = "timeout"
        else:
            await asyncio.wait({task}, timeout=POLL_SECONDS)
            continue
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return reason
    return "finished"


def _stopped_result(
    reason: str, task: asyncio.Future, executable: str, seconds: float
) -> model_check.ProcessResult:
    """Return what a command that finished or was stopped leaves behind.

    Raises
    ------
    ModelCheckError
        Raised when the command was stopped by an interrupt: there is no
        result to judge.
    """
    if reason == "interrupt":
        raise model_check.ModelCheckError(f"'{executable}' was stopped by an interrupt")
    if reason == "timeout":
        return model_check.ProcessResult(
            exit_code=None, stdout="", stderr="", timed_out=True, seconds=seconds
        )
    return _process_result(task.result(), seconds)


def _launch(executable: str, bounded: Callable[[], object]) -> model_check.ProcessResult:
    """Run ``bounded`` on its own event loop, naming a command that cannot start."""
    try:
        return asyncio.run(bounded())
    except FileNotFoundError as error:
        raise model_check.ModelCheckError(
            f"'{executable}' is required, but not installed"
        ) from error
    except OSError as error:
        raise model_check.ModelCheckError(f"cannot start '{executable}': {error}") from error


def process_runner(
    clock: Callable[[], float], cancelled: threading.Event | None = None
) -> model_check.Runner:
    """Return a runner that executes one command through Cuprum.

    An executable that is absent, or that exists and cannot be started, such
    as a pinned checker without execute permission, is a named
    ``ModelCheckError`` rather than a launch error escaping the command line.

    The runner stops the command when its timeout expires, or as soon as
    ``cancelled`` is set, which is how an interrupt reaches commands running
    on worker threads. Cuprum turns the stop into ``SIGTERM`` and then
    ``SIGKILL``, and the runner times the command with ``clock``. The command
    runs in its own process group, and the signals go to the group: the
    pinned release's ``fizz`` launcher starts the checker as a child without
    ``exec``, so signalling the launcher alone would leave the checker
    running. Being in its own group also keeps a terminal's interrupt away
    from it, which is why the interrupt is passed on through ``cancelled``.
    """
    stop = cancelled or threading.Event()

    def run(command: Sequence[str], cwd: Path, timeout: int) -> model_check.ProcessResult:
        """Run ``command`` in ``cwd``, stopping it after ``timeout`` seconds."""
        executable, *arguments = command
        program = Program(executable)
        catalogue = ProgramCatalogue.from_programs(program, name="model-check")
        # The checker's launcher creates a scratch file with mktemp and
        # leaves it; pointing TMPDIR at the run directory keeps it there.
        context = ExecutionContext(
            cwd=cwd,
            env={"TMPDIR": str(cwd)},
            process_group=ProcessGroupPolicy.OWN_GROUP,
        )
        started = clock()

        async def bounded() -> model_check.ProcessResult:
            """Await the command, or report how it was stopped."""
            with scoped(catalogue=catalogue):
                task = asyncio.ensure_future(
                    sh.make(program)(*arguments).run(
                        context=context, output=RunOutputOptions(capture=True, echo=False)
                    )
                )
                reason = await _await_or_stop(task, started + timeout, clock, stop)
            return _stopped_result(reason, task, executable, clock() - started)

        return _launch(executable, bounded)

    return run


def fetcher(runner: model_check.Runner) -> model_check.Fetcher:
    """Return a downloader that runs curl through ``runner``."""

    def fetch(url: str, destination: Path) -> None:
        """Download ``url``, failing on an HTTP error or a short read."""
        command = (
            "curl", "--fail", "--location", "--silent", "--show-error",
            "--retry", "3", "--output", str(destination), url,
        )
        result = runner(command, destination.parent, DOWNLOAD_TIMEOUT_SECONDS)
        if result.timed_out or result.exit_code != 0:
            raise model_check.ModelCheckError(
                f"download of {url} failed: {result.stderr.strip() or 'no diagnostic'}"
            )

    return fetch


def install(*, suite: Path, home: Path | None = None) -> None:
    """Fetch, verify and unpack the checker a suite pins.

    Parameters
    ----------
    suite
        The suite manifest naming the release and its digests.
    home
        Directory the release is unpacked into; by default
        ``~/.cache/fizzbee``.

    Returns
    -------
    None
        Prints the verified launcher's path. Nothing is downloaded when the
        pinned release is already present and intact.
    """
    host = current_host()
    model_check.require_platform(host)
    loaded = model_check.load_suite(suite)
    fetch = fetcher(process_runner(host.clock))
    fizz = model_check.install_checker(home or host.home, loaded.checker, fetch)
    print(f"FizzBee {loaded.checker.version} verified at {fizz}")


def check(options: Annotated[model_check.CheckOptions, Parameter(name="*")]) -> None:
    """Run a suite and exit non-zero unless every run met its expectation.

    Parameters
    ----------
    options
        The suite, tier, selection, checker home, report directory and
        parallelism; see ``CheckOptions``.

    Returns
    -------
    None
        Prints the summary. Exits with status one when a run did not meet
        its expectation, was interrupted, or could not be judged, and with
        ``model_check.PARTIAL_STATUS`` when every run met its expectation but only a
        named subset ran: a subset is never a gate result.
    """
    host = current_host()
    model_check.require_platform(host)
    cancelled = threading.Event()
    runner = process_runner(host.clock, cancelled)
    session, runs = model_check.load_session(options, host, runner)
    model_check.reset_report(session.report)
    jobs = model_check.workers(options.jobs, host)
    started = host.clock()
    outcomes = model_check.run_suite(session, runs, jobs, cancel=cancelled.set)
    document = model_check.gate_document(
        session.suite,
        outcomes,
        selection=(options.tier, bool(options.only)),
        cost=(host.clock() - started, jobs, host.peak_child_rss_kib()),
    )
    target = model_check.write_report(document, options.report)
    print(model_check.summarize(outcomes, partial=bool(document["partial"])))
    print(model_check.run_line(document, target))
    status = model_check.exit_status(document)
    if status:
        raise SystemExit(status)


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the selected command. A
        suite, checker or execution failure is reported as one diagnostic
        line, followed by a note line for each note the error carries, such
        as a failed cleanup after a failed install, and exits with status
        one; an interrupt exits with status 130.
    """
    app = App(
        name="model_check",
        config=cyclopts.config.Env("MODEL_CHECK_", command=False),
        help="Run a pinned FizzBee model-checking suite.",
        # The interrupt is reported below, with the launcher's own diagnostic;
        # Cyclopts would otherwise exit 130 silently.
        suppress_keyboard_interrupt=False,
    )
    app.command(install)
    app.command(check)
    try:
        app()
    except model_check.ModelCheckError as error:
        print(f"model_check: error: {error}", file=sys.stderr)
        for note in getattr(error, "__notes__", ()):
            print(f"model_check: note: {note}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt as error:
        print("model_check: interrupted; no result", file=sys.stderr)
        raise SystemExit(130) from error


if __name__ == "__main__":
    cli()
