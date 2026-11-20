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
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time

import cyclopts
from cyclopts import App
from cuprum import (
    ExecutionContext,
    Program,
    ProgramCatalogue,
    RunOutputOptions,
    scoped,
    sh,
)

import model_check

#: Where the pinned release is unpacked unless ``--home`` says otherwise. The
#: directory name keeps the 680 MB tree out of code indexes and the Markdown
#: gate's walk.
DEFAULT_HOME = Path.home() / ".cache" / "fizzbee"

#: Where run directories, traces and the report are written. ``build`` is
#: ignored by Git and pruned by the repository's discovery walks.
DEFAULT_REPORT = Path("build") / "model-check"

#: The one platform the pinned archive supports.
SUPPORTED_PLATFORM = ("Linux", "x86_64")


def _run_command(command: Sequence[str], cwd: Path, timeout: int) -> model_check.ProcessResult:
    """Run one command through Cuprum, cancelling it at the timeout.

    A signal's exit status is reported as no exit status at all, so the
    judgement cannot mistake an interrupted checker for one that finished.
    """
    executable, *arguments = command
    program = Program(executable)
    catalogue = ProgramCatalogue.from_programs(program, name="model-check")
    # The checker's launcher creates a scratch file with mktemp and leaves
    # it; pointing TMPDIR at the run directory keeps it with the run.
    context = ExecutionContext(cwd=cwd, env={"TMPDIR": str(cwd)})
    started = time.monotonic()

    async def bounded() -> model_check.ProcessResult:
        """Await the command, or cancel it when the timeout expires."""
        with scoped(catalogue=catalogue):
            task = sh.make(program)(*arguments).run(
                context=context,
                output=RunOutputOptions(capture=True, echo=False),
            )
            try:
                result = await asyncio.wait_for(task, timeout=timeout)
            except TimeoutError:
                return model_check.ProcessResult(
                    exit_code=None,
                    stdout="",
                    stderr="",
                    timed_out=True,
                    seconds=time.monotonic() - started,
                )
        code = result.exit_code
        return model_check.ProcessResult(
            exit_code=None if code is None or code < 0 or code > 128 else code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            seconds=time.monotonic() - started,
        )

    try:
        return asyncio.run(bounded())
    except FileNotFoundError as error:
        raise model_check.ModelCheckError(
            f"'{executable}' is required, but not installed"
        ) from error


def _fetch(url: str, destination: Path) -> None:
    """Download ``url`` with curl, failing on an HTTP error or a short read."""
    result = _run_command(
        (
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--retry",
            "3",
            "--output",
            str(destination),
            url,
        ),
        destination.parent,
        1800,
    )
    if result.timed_out or result.exit_code != 0:
        raise model_check.ModelCheckError(
            f"download of {url} failed: {result.stderr.strip() or 'no diagnostic'}"
        )


def _require_platform() -> None:
    """Refuse a platform the pinned archive was not built for."""
    here = (platform.system(), platform.machine())
    if here != SUPPORTED_PLATFORM:
        raise model_check.ModelCheckError(
            f"the pinned FizzBee archive supports {SUPPORTED_PLATFORM[0]}"
            f" {SUPPORTED_PLATFORM[1]} only; this is {here[0]} {here[1]}."
            " The model-check gate is unsupported here."
        )


def install(*, suite: Path, home: Path = DEFAULT_HOME) -> None:
    """Fetch, verify and unpack the checker a suite pins.

    Parameters
    ----------
    suite
        The suite manifest naming the release and its digests.
    home
        Directory the release is unpacked into.

    Returns
    -------
    None
        Prints the verified launcher's path. Nothing is downloaded when the
        pinned release is already present and intact.
    """
    _require_platform()
    loaded = model_check.load_suite(suite)
    fizz = model_check.install_checker(home, loaded.checker, _fetch)
    print(f"FizzBee {loaded.checker.version} verified at {fizz}")


def check(
    *,
    suite: Path,
    tier: str = "routine",
    only: list[str] | None = None,
    home: Path = DEFAULT_HOME,
    report: Path = DEFAULT_REPORT,
    jobs: int = 0,
) -> None:
    """Run a suite and exit non-zero unless every run met its expectation.

    Parameters
    ----------
    suite
        The suite manifest.
    tier
        ``routine`` runs the mandatory checks. ``extended`` runs those and
        the larger explorations.
    only
        Run identifiers to restrict the run to while iterating. A subset is
        reported as partial and is not a gate result.
    home
        Directory the pinned release was unpacked into.
    report
        Directory for run directories, traces and ``report.json``.
    jobs
        Checker processes to run at once; zero selects up to four, bounded
        by the available processors.

    Returns
    -------
    None
        Prints the summary. Exits with status one when a run did not meet
        its expectation, was interrupted, or could not be judged.
    """
    _require_platform()
    loaded = model_check.load_suite(suite)
    problems = model_check.unknown_assertions(loaded)
    if problems:
        raise model_check.ModelCheckError("; ".join(problems))
    fizz = model_check.locate_checker(home, loaded.checker)
    runs = model_check.select(loaded, tier, only or ())
    shutil.rmtree(report, ignore_errors=True)
    report.mkdir(parents=True)
    workers = jobs or max(1, min(4, os.cpu_count() or 1))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(
            pool.map(
                lambda run: model_check.execute(
                    run, loaded, fizz, report.resolve() / run.id, _run_command
                ),
                runs,
            )
        )
    document = model_check.report(loaded, outcomes, tier=tier, partial=bool(only))
    document["wall_seconds"] = round(time.monotonic() - started, 1)
    document["jobs"] = workers
    # The high-water mark over every checker process this invocation waited
    # for, which is the figure a runner's memory limit has to accommodate
    # per process.
    document["peak_child_rss_kib"] = resource.getrusage(
        resource.RUSAGE_CHILDREN
    ).ru_maxrss
    (report / "report.json").write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    print(model_check.summarize(outcomes, partial=bool(only)))
    print(
        f"FizzBee {loaded.checker.version}; tier {tier}; {workers} at a time;"
        f" {document['wall_seconds']}s; peak checker RSS"
        f" {document['peak_child_rss_kib'] // 1024} MiB;"
        f" report in {report / 'report.json'}"
    )
    if not document["ok"]:
        raise SystemExit(1)


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface.

    Returns
    -------
    None
        Cyclopts parses arguments and dispatches the selected command. A
        suite, checker or execution failure is reported as one diagnostic
        line and exits with status one; an interrupt exits with status 130.
    """
    app = App(
        name="model_check",
        config=cyclopts.config.Env("MODEL_CHECK_", command=False),
        help="Run a pinned FizzBee model-checking suite.",
    )
    app.command(install)
    app.command(check)
    try:
        app()
    except model_check.ModelCheckError as error:
        print(f"model_check: error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    except KeyboardInterrupt as error:
        print("model_check: interrupted; no result", file=sys.stderr)
        raise SystemExit(130) from error


if __name__ == "__main__":
    cli()
