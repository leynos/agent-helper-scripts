"""Discover the file list a gate examines, failing closed on an empty one.

A recipe that pipes a producer into a checker reports the checker's status.
Without ``pipefail`` a producer that fails, or that matches nothing because
the branch is dead or the paths root is wrong, hands the checker an empty
list, and ``xargs -r`` exits zero without running it. The gate then passes
having examined no file.

Discovery therefore lives here, behind ordinary exceptions. A failed producer
and an empty result both raise, so neither can reach a tool as a short list
that reads as a clean run.

Examples
--------
List a repository's Git-tracked paths::

    from gate_discovery import tracked_paths

    paths = tracked_paths(Path.cwd(), gate="spelling")

List its Markdown files::

    from gate_discovery import markdown_paths

    paths = markdown_paths(Path.cwd(), gate="markdownlint")
"""

from collections.abc import Sequence
import os
from pathlib import Path
import subprocess

#: Directory names pruned while walking for Markdown files. They mirror the
#: directory entries of the shared spelling base's ``[files] exclude`` list,
#: so a gate never descends into a build, cache or vendored tree that the
#: spelling policy already treats as outside the repository's own sources.
DEFAULT_DIRECTORY_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".hypothesis",
    ".pytest_cache",
    ".terraform",
    ".tox",
    ".uv-cache",
    ".uv-tools",
    ".venv",
    "dist",
    "node_modules",
    "target",
)


class GateDiscoveryError(RuntimeError):
    """Report that a gate could not produce a non-empty file list.

    Parameters
    ----------
    gate
        Gate whose discovery failed, named in the message.
    reason
        What went wrong, phrased as a clause after the gate name.

    Attributes
    ----------
    gate, reason
        The values the message was built from.
    """

    def __init__(self, gate: str, reason: str) -> None:
        self.gate = gate
        self.reason = reason
        super().__init__(f"the {gate} gate {reason}")


def _require_paths(gate: str, paths: Sequence[Path], subject: str) -> None:
    """Reject an empty discovery result before a tool can read it."""
    if not paths:
        raise GateDiscoveryError(
            gate,
            f"found no {subject}; refusing to pass an empty list to a tool, "
            "because that reads as a clean run",
        )


def tracked_paths(repository: Path, *, gate: str) -> tuple[Path, ...]:
    """Return a repository's Git-tracked paths in deterministic order.

    Parameters
    ----------
    repository
        Git worktree whose tracked files should be listed.
    gate
        Gate the list is being built for, named in any failure.

    Returns
    -------
    tuple[Path, ...]
        Repository-relative tracked paths, sorted.

    Raises
    ------
    GateDiscoveryError
        If Git cannot list the worktree's files, or lists none.
    """
    completed = subprocess.run(  # noqa: S603 - fixed executable, no shell.
        ["git", "-C", str(repository), "ls-files", "-z"],
        capture_output=True,
        check=False,
        # Git does not read standard input here, but a command double standing
        # in for Git does, and a shim waiting on an inherited terminal would
        # wedge the gate rather than fail it.
        stdin=subprocess.DEVNULL,
        text=True,
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr.strip() or f"exit status {completed.returncode}"
        raise GateDiscoveryError(
            gate,
            f"could not list the tracked files of {repository}: {diagnostic}",
        )
    paths = tuple(
        sorted(Path(relative) for relative in completed.stdout.split("\0") if relative)
    )
    _require_paths(gate, paths, "Git-tracked files")
    return paths


def markdown_paths(
    repository: Path,
    *,
    gate: str,
    excludes: Sequence[str] = DEFAULT_DIRECTORY_EXCLUDES,
) -> tuple[Path, ...]:
    """Return a repository's Markdown files, honouring directory exclusions.

    Parameters
    ----------
    repository
        Directory tree whose Markdown files should be listed.
    gate
        Gate the list is being built for, named in any failure.
    excludes
        Directory names pruned from the walk at any depth.

    Returns
    -------
    tuple[Path, ...]
        Repository-relative ``*.md`` paths, sorted.

    Raises
    ------
    GateDiscoveryError
        If the walk finds no Markdown file.
    """
    pruned = frozenset(excludes)
    paths: list[Path] = []
    for current, directories, filenames in os.walk(repository):
        # Pruning in place stops the walk descending into a tree the caller
        # excluded, rather than filtering the files once they have been read.
        directories[:] = sorted(
            directory for directory in directories if directory not in pruned
        )
        paths.extend(
            (Path(current) / name).relative_to(repository)
            for name in sorted(filenames)
            if name.endswith(".md")
        )
    discovered = tuple(sorted(paths))
    _require_paths(gate, discovered, "Markdown files")
    return discovered
