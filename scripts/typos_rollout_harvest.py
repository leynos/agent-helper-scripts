"""Harvest Oxford-form evidence from Git-tracked repository text."""

import logging
from pathlib import Path
import re
import subprocess
from typing import Protocol

LOGGER = logging.getLogger(__name__)
OXFORD_FORM = re.compile(
    r"\b[A-Za-z]+(?:isations|izations|isation|ization|isably|izably|isable|izable|"
    r"isers|izers|ising|izing|ised|ized|ises|izes|iser|izer|ise|ize)\b"
)


class ExclusionPolicy(Protocol):
    """Expose the file exclusions consumed by Oxford-form harvesting.

    Attributes
    ----------
    excluded_files
        Repository-relative components or globs omitted from harvesting.
    """

    excluded_files: tuple[str, ...]


def harvest_oxford_forms(text: str) -> tuple[str, ...]:
    """Return normalized ``-ise`` and ``-ize`` candidates in text.

    Parameters
    ----------
    text
        UTF-8 text line or document to inspect.

    Returns
    -------
    tuple[str, ...]
        Sorted unique case-folded candidate forms.
    """
    return tuple(
        sorted({match.group(0).casefold() for match in OXFORD_FORM.finditer(text)})
    )


def is_harvest_excluded(relative: Path, dictionary: ExclusionPolicy) -> bool:
    """Report whether merged dictionary policy excludes a relative path.

    Parameters
    ----------
    relative
        Repository-relative path under consideration.
    dictionary
        Merged policy containing file exclusions.

    Returns
    -------
    bool
        ``True`` when an exclusion component or pattern matches.
    """
    return any(
        excluded in relative.parts or relative.match(excluded)
        for excluded in dictionary.excluded_files
    )


def _tracked_relative_paths(repository: Path) -> tuple[Path, ...]:
    """Return a repository's Git-tracked paths in deterministic order."""
    tracked = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        Path(relative) for relative in sorted(filter(None, tracked.split("\0")))
    )


def _log_read_failure(error_class: str, *, level: int) -> None:
    """Emit a bounded tracked-file read diagnostic without a path value."""
    LOGGER.log(
        level,
        "Tracked file could not be read for Oxford-form harvesting",
        extra={
            "operation": "tracked-file-read",
            "source_kind": "repository-file",
            "error_class": error_class,
        },
    )


def _read_tracked_lines(path: Path) -> list[str] | None:
    """Read tracked UTF-8 lines, skipping only undecodable content."""
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        _log_read_failure("unicode-decode", level=logging.INFO)
        return None
    except OSError:
        _log_read_failure("os-error", level=logging.ERROR)
        raise


def harvest_repository(
    repository: Path,
    dictionary: ExclusionPolicy,
) -> tuple[dict[str, object], ...]:
    """Harvest Oxford-form evidence from Git-tracked UTF-8 files.

    Parameters
    ----------
    repository
        Git worktree whose tracked files should be inspected.
    dictionary
        Merged spelling policy containing file exclusions.

    Returns
    -------
    tuple[dict[str, object], ...]
        JSON-serializable path, line, and candidate-form records.

    Raises
    ------
    OSError, subprocess.CalledProcessError
        If repository discovery or a tracked-file read fails.
    """
    findings: list[dict[str, object]] = []
    for relative in _tracked_relative_paths(repository):
        if is_harvest_excluded(relative, dictionary):
            continue
        lines = _read_tracked_lines(repository / relative)
        if lines is None:
            continue
        for number, line in enumerate(lines, start=1):
            forms = harvest_oxford_forms(line)
            if forms:
                findings.append(
                    {
                        "path": str(relative),
                        "line": number,
                        "forms": list(forms),
                    }
                )
    return tuple(findings)
