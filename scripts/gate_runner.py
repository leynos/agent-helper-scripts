"""Run a repository gate over one explicit file list.

A recipe that pipes a producer into a checker reports the checker's status.
Without ``pipefail`` a producer that fails, or that matches nothing, hands the
checker an empty list, and ``xargs -r`` exits zero without running it at all.
The gate then passes having examined no file, which is how a broken revision
and a green pipeline end up in the same report.

Every command here discovers its own file list, raises when that list is
empty, and invokes its tool exactly once over the whole list. A recipe is then
a single command, and no shell pipeline carries a status that is not the
tool's.

Examples
--------
Lint every Markdown file in the tree::

    uv run --script scripts/gate_runner_cli.py markdownlint

The commands live here, apart from the command line that reaches them, so a
test can call one with a command double standing in for its tool. The front
end is the sibling ``gate_runner_cli`` module.
"""

from collections.abc import Sequence
from pathlib import Path
import shlex
import shutil
import subprocess

import gate_discovery

#: Markdown linter the shared recipe runs.
DEFAULT_LINTER = "markdownlint-cli2"

#: Mermaid validator the shared recipe runs.
DEFAULT_VALIDATOR = "nixie"

#: Ends option parsing before a discovered file list. Git tracks a name that
#: begins with a dash, and discovery reports a root-relative name as it found
#: it, so ``-guide.md`` arrives as the first operand. A linter refuses it as an
#: unknown flag and reads nothing at all; the terminator goes after the gate's
#: own flags, which still need to parse.
OPTION_TERMINATOR = "--"


class GateExecutionError(RuntimeError):
    """Report that a gate could not complete the run it was asked for."""


#: Failures a gate reports as a one-line diagnostic rather than a traceback.
#: Finding no file is a refusal to evaluate the gate; reading it as a stack
#: trace buries the reason the gate stopped.
GATE_ERRORS = (
    gate_discovery.GateDiscoveryError,
    GateExecutionError,
)


def _resolve(executable: str) -> str:
    """Return the path of a gate's tool, or fail with an actionable message.

    Parameters
    ----------
    executable
        Command name the gate was configured to run.

    Returns
    -------
    str
        Absolute path of the resolved executable.

    Raises
    ------
    GateExecutionError
        If the command cannot be found on ``PATH``.
    """
    resolved = shutil.which(executable)
    if resolved is None:
        message = f"'{executable}' is required, but not installed"
        raise GateExecutionError(message)
    return resolved


def _run(command: Sequence[str], *, cwd: Path) -> None:
    """Run a gate's tool once, leaving its own output on the caller's streams.

    Parameters
    ----------
    command
        Executable and arguments to run.
    cwd
        Repository directory the tool resolves its arguments against.

    Raises
    ------
    GateExecutionError
        If the executable is not installed, or the operating system refuses
        to start it.
    SystemExit
        If the tool reports a non-zero status, which is the gate failing.
    """
    resolved = [_resolve(command[0]), *command[1:]]
    try:
        completed = subprocess.run(  # noqa: S603 - resolved executable, no shell.
            resolved,
            cwd=cwd,
            check=False,
            # ``xargs`` handed its children an empty standard input, so a gate
            # never read from a terminal. Keeping that here stops a tool that
            # would prompt from blocking a pipeline that has no one to answer
            # it.
            stdin=subprocess.DEVNULL,
        )
    except OSError as error:
        # A list too long for ``execve`` (E2BIG) reaches here because a gate
        # names every file on one command line, as does a lost race between
        # resolving the executable and starting it. Both are the operating
        # system refusing the run, so both are the gate failing to run rather
        # than a defect in the tool.
        message = f"could not run '{command[0]}': {error}"
        raise GateExecutionError(message) from error
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def markdownlint(
    repository: Path = Path(),
    linter: str = DEFAULT_LINTER,
    exclude: tuple[str, ...] = gate_discovery.DEFAULT_DIRECTORY_EXCLUDES,
) -> None:
    """Lint every Markdown file the repository contains.

    Parameters
    ----------
    repository
        Directory tree to lint.
    linter
        Command line of the Markdown linter, split with shell rules, run once
        over the discovered files.
    exclude
        Directory names pruned from the walk at any depth.

    Raises
    ------
    GateDiscoveryError
        If the walk finds no Markdown file.
    GateExecutionError
        If the linter is not installed.
    SystemExit
        If the linter reports findings.
    """
    paths = gate_discovery.markdown_paths(
        repository,
        gate="markdownlint",
        excludes=exclude,
    )
    _run(
        [
            *shlex.split(linter),
            OPTION_TERMINATOR,
            *(path.as_posix() for path in paths),
        ],
        cwd=repository,
    )


def nixie(
    repository: Path = Path(),
    validator: str = DEFAULT_VALIDATOR,
    exclude: tuple[str, ...] = gate_discovery.DEFAULT_DIRECTORY_EXCLUDES,
) -> None:
    """Validate every Mermaid diagram in the repository's Markdown.

    Parameters
    ----------
    repository
        Directory tree whose diagrams should be rendered.
    validator
        Command line of the Mermaid validator, split with shell rules, run
        once over the discovered files.
    exclude
        Directory names pruned from the walk at any depth.

    Raises
    ------
    GateDiscoveryError
        If the walk finds no Markdown file.
    GateExecutionError
        If the validator is not installed.
    SystemExit
        If the validator reports a diagram it cannot render.
    """
    paths = gate_discovery.markdown_paths(repository, gate="nixie", excludes=exclude)
    # The sandbox is disabled because the renderer runs Chromium, which is
    # unavailable inside the containers and CI runners this gate serves.
    _run(
        [
            *shlex.split(validator),
            "--no-sandbox",
            OPTION_TERMINATOR,
            *(path.as_posix() for path in paths),
        ],
        cwd=repository,
    )
