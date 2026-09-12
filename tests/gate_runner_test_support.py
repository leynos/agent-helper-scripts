"""Shared fixtures and doubles for the gate runner's fail-closed tests.

The runner and the discovery layer it composes are loaded from ``scripts/`` by
path, the way the spelling rollout tests load their facade, because that
directory is not a package on the import path. The command doubles then stand
in for the two commands a gate drives: the producer that lists the files, and
the tool that reads them.

A double is reached through ``PATH``, which is what an unmodified
``subprocess.run(["git", ...])`` consults, so these tests exercise the same
resolution the real gate uses rather than a substituted one.
"""

from collections.abc import Callable, Iterator
import importlib
from pathlib import Path
import sys
import types

from cmd_mox.ipc import Invocation
import pytest

from typos_rollout_test_support import REPOSITORY_ROOT, SHARED_DICTIONARY_PATH

SCRIPTS_PATH = REPOSITORY_ROOT / "scripts"
GIT = "git"

__all__ = ("SHARED_DICTIONARY_PATH", "GateModules", "git_handler", "gate_fixture")


class GateModules:
    """Hold the runner under test and the discovery layer it composes.

    Attributes
    ----------
    runner
        Loaded ``gate_runner`` module.
    discovery
        Loaded ``gate_discovery`` module.
    """

    def __init__(self, runner: types.ModuleType, discovery: types.ModuleType) -> None:
        self.runner = runner
        self.discovery = discovery


@pytest.fixture(name="gate", scope="module")
def gate_fixture() -> Iterator[GateModules]:
    """Load the runner and its discovery sibling through the runtime path."""
    script_directory = str(SCRIPTS_PATH)
    sys.path.insert(0, script_directory)
    try:
        # The modules stay in ``sys.modules`` after the directory leaves the
        # path, so a second module-scoped request reuses the loaded copies
        # instead of re-executing them against a shortened path.
        yield GateModules(
            importlib.import_module("gate_runner"),
            importlib.import_module("gate_discovery"),
        )
    finally:
        sys.path.remove(script_directory)


def git_handler(
    *,
    listed: str = "",
    status: int = 0,
    diagnostic: str = "",
    respond: Callable[[Invocation], tuple[str, str, int] | None] | None = None,
) -> Callable[[Invocation], tuple[str, str, int]]:
    """Build a Git double that lists files or reports a failure.

    Parameters
    ----------
    listed
        Repository-relative paths to report, separated by NUL bytes as
        ``git ls-files -z`` does.
    status
        Exit status for the listing call.
    diagnostic
        Standard error for the listing call.
    respond
        Optional override consulted first. Returning ``None`` falls through to
        the behaviour above, so a test can answer one kind of Git call
        specifically and leave the rest to the defaults.

    Returns
    -------
    Callable[[Invocation], tuple[str, str, int]]
        Handler answering a doubled ``git`` with ``(stdout, stderr, status)``.
    """

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        """Answer one doubled Git call."""
        if respond is not None:
            answer = respond(invocation)
            if answer is not None:
                return answer
        if "-z" not in invocation.args:
            return ("", "", 0)
        if status != 0:
            return ("", diagnostic, status)
        return (listed, "", 0)

    return handler


def write_markdown_tree(root: Path, names: tuple[str, ...]) -> tuple[Path, ...]:
    """Write one Markdown file per repository-relative name.

    Parameters
    ----------
    root
        Directory to write into.
    names
        Repository-relative file names, including any subdirectory.

    Returns
    -------
    tuple[Path, ...]
        The repository-relative paths that were written, in sorted order.
    """
    written: list[Path] = []
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {target.stem}\n", encoding="utf-8")
        written.append(Path(name))
    return tuple(sorted(written))
