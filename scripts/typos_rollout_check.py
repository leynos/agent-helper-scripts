"""Enforce exact phrase corrections alongside the Typos word scanner."""

from collections.abc import Sequence
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import subprocess
from typing import Protocol

import typos_rollout_policy

LOGGER = logging.getLogger(__name__)
PHRASE_POLICY_PATHS = frozenset(
    {
        Path("data/typos-oxendict-base.toml"),
        Path("typos.local.toml"),
    }
)


class SpellingPolicy(Protocol):
    """Expose policy fields consumed by phrase checking.

    Attributes
    ----------
    phrase_corrections
        Exact prohibited phrase and canonical replacement pairs.
    ignore_patterns
        Bounded regular expressions whose matches are masked.
    excluded_files
        Repository-relative components or globs omitted from checks.
    """

    phrase_corrections: tuple[tuple[str, str], ...]
    ignore_patterns: tuple[str, ...]
    excluded_files: tuple[str, ...]


@dataclass(frozen=True)
class PhraseFinding:
    """Describe one prohibited phrase found in tracked text.

    Attributes
    ----------
    path, line, column
        Repository-relative location of the finding.
    phrase, correction
        Observed prohibited phrase and its canonical replacement.
    """

    path: Path
    line: int
    column: int
    phrase: str
    correction: str


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


def _is_excluded(relative: Path, dictionary: SpellingPolicy) -> bool:
    """Report whether merged dictionary policy excludes a relative path."""
    return any(
        excluded in relative.parts or relative.match(excluded)
        for excluded in dictionary.excluded_files
    )


def _log_read_failure(error_class: str, *, level: int) -> None:
    """Emit a bounded tracked-file read diagnostic without a path value."""
    LOGGER.log(
        level,
        "Tracked file could not be read for phrase checking",
        extra={
            "operation": "tracked-file-read",
            "source_kind": "repository-file",
            "error_class": error_class,
        },
    )


def _read_tracked_text(path: Path) -> str | None:
    """Read tracked UTF-8 text, skipping only undecodable content."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _log_read_failure("unicode-decode", level=logging.INFO)
        return None
    except OSError:
        _log_read_failure("os-error", level=logging.ERROR)
        raise


def _mask_ignored_text(
    text: str,
    patterns: tuple[re.Pattern[str], ...],
) -> str:
    """Blank ignored text while preserving line and column positions."""

    def blank(match: re.Match[str]) -> str:
        """Replace non-newline match characters with spaces."""
        return "".join(
            "\n" if character == "\n" else " " for character in match.group()
        )

    for pattern in patterns:
        text = pattern.sub(blank, text)
    return text


def _phrase_matchers(
    corrections: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    """Compile exact phrase boundaries for the curated correction table."""
    return tuple(
        (
            phrase,
            correction,
            re.compile(
                rf"(?<![\w-]){re.escape(phrase)}(?![\w-])",
                re.IGNORECASE,
            ),
        )
        for phrase, correction in corrections
    )


def _find_in_text(
    relative: Path,
    text: str,
    masked: str,
    matchers: Sequence[tuple[str, str, re.Pattern[str]]],
) -> tuple[PhraseFinding, ...]:
    """Return all curated phrase findings in position-preserving text."""
    findings: list[PhraseFinding] = []
    for _phrase, correction, matcher in matchers:
        for match in matcher.finditer(masked):
            previous_newline = masked.rfind("\n", 0, match.start())
            findings.append(
                PhraseFinding(
                    path=relative,
                    line=masked.count("\n", 0, match.start()) + 1,
                    column=match.start() - previous_newline,
                    phrase=text[match.start() : match.end()],
                    correction=correction,
                )
            )
    return tuple(findings)


def check_phrase_corrections(
    repository: Path,
    dictionary: SpellingPolicy,
) -> tuple[PhraseFinding, ...]:
    """Find prohibited exact phrases in tracked UTF-8 text.

    Parameters
    ----------
    repository
        Git worktree whose tracked text should be checked.
    dictionary
        Merged shared and repository-local spelling policy.

    Returns
    -------
    tuple[PhraseFinding, ...]
        Findings ordered by tracked path, policy order, and source position.

    Raises
    ------
    OSError, subprocess.CalledProcessError, ValueError
        If discovery, file reading or regular expression validation fails.
    """
    patterns = typos_rollout_policy.compile_ignore_patterns(
        dictionary.ignore_patterns
    )
    matchers = _phrase_matchers(dictionary.phrase_corrections)
    findings: list[PhraseFinding] = []
    for relative in _tracked_relative_paths(repository):
        if relative in PHRASE_POLICY_PATHS or _is_excluded(relative, dictionary):
            continue
        text = _read_tracked_text(repository / relative)
        if text is None:
            continue
        findings.extend(
            _find_in_text(
                relative,
                text,
                _mask_ignored_text(text, patterns),
                matchers,
            )
        )
    return tuple(findings)
