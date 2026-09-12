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
Run the shared spelling gate::

    uv run --script scripts/gate_runner_cli.py spelling

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
import sys

import gate_discovery
import typos_rollout

#: Pinned spelling scanner the shared recipe runs. A repository's Makefile
#: overrides it with its own ``TYPOS_VERSION``, and the test suite pins the two
#: together so the default cannot drift from the version that ships.
DEFAULT_TYPOS = "uv tool run typos@1.48.0"

#: Markdown linter the shared recipe runs.
DEFAULT_LINTER = "markdownlint-cli2"

#: Mermaid validator the shared recipe runs.
DEFAULT_VALIDATOR = "nixie"


class GateExecutionError(RuntimeError):
    """Report that a gate could not complete the run it was asked for."""


#: Failures a gate reports as a one-line diagnostic rather than a traceback.
#: Finding no file, and being unable to reach the shared policy, are both
#: refusals to evaluate the gate; reading them as a stack trace buries the
#: reason the gate stopped.
GATE_ERRORS = (
    gate_discovery.GateDiscoveryError,
    GateExecutionError,
    typos_rollout.NetworkUnavailableError,
    typos_rollout.InsecureSourceError,
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


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git in a repository with captured output.

    Standard input is closed, as it is for the tools ``_run`` starts. Git does
    not read it here, but a command double standing in for Git does, and a
    shim waiting on an inherited terminal would wedge the gate.
    """
    return subprocess.run(  # noqa: S603 - fixed executable, no shell.
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
        text=True,
    )


def _require_tracked(repository: Path, relative: str) -> None:
    """Reject a generated file that is not in the index.

    An untracked generated file is written afresh on every run, so drift
    between the merged policy and what CI checks out is invisible.

    Raises
    ------
    GateExecutionError
        If Git does not know the path.
    """
    completed = _git(repository, "ls-files", "--error-unmatch", "--", relative)
    if completed.returncode != 0:
        message = (
            f"{relative} is not tracked; commit it so the generated policy is "
            "reviewable and drift is detectable"
        )
        raise GateExecutionError(message)


def _require_undrifted(repository: Path, relative: str) -> None:
    """Reject a generated file that differs from the merged policy.

    Raises
    ------
    GateExecutionError
        If the worktree copy differs from the index.
    """
    completed = _git(
        repository,
        "diff",
        "--no-ext-diff",
        "--exit-code",
        "--",
        relative,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        # Flush before the diagnostic so the two streams stay in order when a
        # caller captures both into one log, as ``tee`` does in CI.
        sys.stdout.flush()
        sys.stderr.write(completed.stderr)
        message = (
            f"{relative} drifted from the merged spelling policy; commit the "
            "regenerated configuration"
        )
        raise GateExecutionError(message)


def _require_correct_phrases(
    repository: Path,
    dictionary: typos_rollout.Dictionary,
) -> None:
    """Report prohibited exact phrases, failing when any is present.

    Typos splits a form such as ``hand-written`` into two valid tokens, so the
    curated phrase table needs a pass of its own over tracked UTF-8 text.

    Raises
    ------
    SystemExit
        With status two when at least one prohibited phrase is present.
    """
    findings = typos_rollout.check_phrase_corrections(repository, dictionary)
    for finding in findings:
        print(
            f"{finding.path}:{finding.line}:{finding.column}: "
            f"{finding.phrase} -> {finding.correction}"
        )
    if findings:
        raise SystemExit(2)


def spelling(
    repository: Path = Path(),
    source: str = typos_rollout.DEFAULT_BASE_URL,
    typos: str = DEFAULT_TYPOS,
    config: Path = Path("typos.toml"),
    offline: bool = False,
) -> None:
    """Generate the shared spelling configuration and check tracked text.

    The scanner runs against the generated configuration alone, so policy it
    would otherwise discover beside the tracked files cannot decide the verdict
    this gate reports.

    Parameters
    ----------
    repository
        Repository root to generate configuration into and check.
    source
        Local path or HTTPS URL for the authoritative shared base.
    typos
        Command line of the spelling scanner, split with shell rules.
    config
        Repository-relative generated configuration path.
    offline
        Reuse an existing valid base cache without contacting the source.

    Raises
    ------
    GateDiscoveryError
        If the tracked file list cannot be produced or is empty.
    GateExecutionError
        If the generated configuration is untracked or has drifted, or the
        scanner is not installed.
    SystemExit
        If a prohibited phrase is present, or the scanner reports findings.
    """
    # The configuration is generated where the option says it will be, not at
    # a fixed name. Generated anywhere else, a tracked custom configuration
    # would satisfy the checks below without ever having been regenerated from
    # the merged policy, and the scanner would read a stale file the gate had
    # just certified.
    generated = typos_rollout.generate_config(
        repository,
        source,
        destination=repository / config,
        offline=offline,
    )
    print(f"{generated.status}: {generated.path}")
    # Discovery comes first so a producer that fails or lists nothing is
    # reported as such. Left until later, a broken producer surfaces as an
    # untracked configuration or, through the phrase checker's own listing, as
    # an uncaught subprocess failure rather than a named gate diagnostic.
    paths = gate_discovery.tracked_paths(repository, gate="spelling")
    relative = config.as_posix()
    _require_tracked(repository, relative)
    _require_undrifted(repository, relative)
    _require_correct_phrases(repository, generated.dictionary)
    _run(
        [
            *shlex.split(typos),
            # The scan applies the configuration the gate generated and no
            # other. Without this, typos merges a ``typos.toml`` it discovers
            # beside a file it reads, so nested or custom-named policy the gate
            # never tracked or checked for drift could soften a verdict the
            # gate reports as that configuration's.
            "--isolated",
            "--config",
            relative,
            "--force-exclude",
            *(path.as_posix() for path in paths),
        ],
        cwd=repository,
    )


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
        [*shlex.split(linter), *(path.as_posix() for path in paths)],
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
            *(path.as_posix() for path in paths),
        ],
        cwd=repository,
    )
