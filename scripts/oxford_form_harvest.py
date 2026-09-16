"""Harvest Oxford-form evidence from Git-tracked repository text.

Curation of `data/typos-oxendict-base.toml` starts from evidence, not from a
suffix match: `advertise`, `exercise`, `promise` and Rust's `usize` all end the
way an Oxford `-ize` family does. This tool emits one JSON object per source
line carrying a candidate form, so a curator can read the context before
proposing a stem.

It is the only spelling tool this repository still owns. Generation, drift
checking, scanning and phrase checking all belong to `typos-config-builder`,
which `make spelling` runs.

The harvesting itself lives here and imports only the standard library, so a
test can drive it directly. The command line is the sibling
``oxford_form_harvest_cli`` module.

Examples
--------
Harvest a neighbouring repository::

    uv run --script scripts/oxford_form_harvest_cli.py --repository ../project
"""

import dataclasses as dc
import logging
from pathlib import Path
import re
import subprocess
import tomllib

LOGGER = logging.getLogger(__name__)
#: The shared dictionary this repository curates, read only for its exclusions.
SHARED_DICTIONARY_PATH = Path(__file__).resolve().parents[1] / (
    "data/typos-oxendict-base.toml"
)
#: A repository's own overlay, whose exclusions extend the shared ones.
LOCAL_OVERLAY_NAME = "typos.local.toml"
OXFORD_FORM = re.compile(
    r"\b[A-Za-z]+(?:isations|izations|isation|ization|isably|izably|isable|izable|"
    r"isers|izers|ising|izing|ised|ized|ises|izes|iser|izer|ise|ize)\b"
)


@dc.dataclass(frozen=True, slots=True)
class ExclusionPolicy:
    """Hold the file exclusions consumed by Oxford-form harvesting.

    Attributes
    ----------
    excluded_files
        Repository-relative components or globs omitted from harvesting.
    """

    excluded_files: tuple[str, ...]


def _excluded_files(path: Path) -> tuple[str, ...]:
    """Return the ``[files] exclude`` entries of one policy document."""
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    excluded = document.get("files", {}).get("exclude", ())
    return tuple(str(entry) for entry in excluded)


def load_exclusion_policy(
    repository: Path,
    *,
    shared: Path = SHARED_DICTIONARY_PATH,
) -> ExclusionPolicy:
    """Merge the shared and repository-local file exclusions.

    Only the exclusions are read. The rest of the spelling policy decides what
    Typos reports, which is the builder's concern rather than this tool's.

    Parameters
    ----------
    repository
        Repository whose optional overlay extends the shared exclusions.
    shared
        Shared dictionary supplying the estate-wide exclusions.

    Returns
    -------
    ExclusionPolicy
        The merged exclusions, deduplicated and sorted.

    Raises
    ------
    OSError
        If a policy document exists but cannot be read.
    tomllib.TOMLDecodeError
        If a policy document is not valid TOML.
    """
    excluded = set(_excluded_files(shared))
    overlay = repository / LOCAL_OVERLAY_NAME
    if overlay.exists():
        excluded.update(_excluded_files(overlay))
    return ExclusionPolicy(excluded_files=tuple(sorted(excluded)))


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


def harvest(repository: Path) -> tuple[dict[str, object], ...]:
    """Harvest a repository under the merged shared and local exclusions.

    Parameters
    ----------
    repository
        Git worktree whose tracked UTF-8 text should be inspected.

    Returns
    -------
    tuple[dict[str, object], ...]
        JSON-serializable path, line, and candidate-form records.

    Raises
    ------
    OSError, subprocess.CalledProcessError
        If repository discovery or a tracked-file read fails.
    """
    return harvest_repository(repository, load_exclusion_policy(repository))
