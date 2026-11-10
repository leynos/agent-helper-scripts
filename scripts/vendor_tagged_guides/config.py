"""Describe and validate one tagged import.

The configuration is a frozen dataclass so a caller can share it between
conversion helpers without any of them mutating it. Validation is separate from
construction so tests can build an unusable configuration and assert on the
diagnostic, and so the pipeline can check everything before writing a file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import posixpath
import re
import stat
from pathlib import Path
from typing import NoReturn

from .filesystem import DEFAULT_FILE_SYSTEM, FileSystem

#: Repository-relative directory the upstream sources live in, used to build
#: absolute URLs for relative links.
DEFAULT_SOURCE_PATH = "docs"

#: Prose line length the consuming repository's Markdown gate enforces.
DEFAULT_LINE_LENGTH = 80

#: Line length the same gate allows inside fenced code blocks.
DEFAULT_CODE_LINE_LENGTH = 120

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]*\Z")


class VendorError(RuntimeError):
    """Report that a guide could not be converted as requested."""


#: Failures the front end reports as a one-line diagnostic rather than a
#: traceback. The tuple mirrors ``gate_runner.GATE_ERRORS``.
VENDOR_ERRORS = (VendorError,)


@dataclass(frozen=True)
class VendorConfig:
    """Describe one tagged import.

    Attributes
    ----------
    tag
        Upstream tag to pin, for example ``v0.2.0-beta2``.
    repository
        Upstream repository in ``owner/name`` form, without a host or scheme.
    source_directory
        Directory holding the upstream Markdown sources.
    output_directory
        Directory the converted files are written to.
    mappings
        ``(source filename, output filename)`` pairs, in output order.
    project
        Display name used by the import note. Defaults to the repository name.
    source_path
        Repository-relative directory of the sources, used to resolve relative
        links. Defaults to ``docs``.
    line_length
        Prose line length the consuming repository enforces.
    code_line_length
        Line length the consuming repository allows in fenced code.
    """

    tag: str
    repository: str
    source_directory: Path
    output_directory: Path
    mappings: tuple[tuple[str, str], ...]
    project: str = ""
    source_path: str = DEFAULT_SOURCE_PATH
    line_length: int = DEFAULT_LINE_LENGTH
    code_line_length: int = DEFAULT_CODE_LINE_LENGTH


def fail(message: str) -> NoReturn:
    """Raise :class:`VendorError` with a one-line message.

    Parameters
    ----------
    message
        Explanation printed by the front end.

    Raises
    ------
    VendorError
        Always.
    """
    raise VendorError(message)


def validate_relative_name(value: str, *, role: str) -> str:
    """Normalize one repository-relative path supplied by a caller.

    Parameters
    ----------
    value
        Path text to validate.
    role
        Short description used in the error message.

    Returns
    -------
    str
        The path with redundant separators removed.

    Raises
    ------
    VendorError
        If the path is empty, absolute, Windows-style, or escapes its root.
    """
    if not value:
        fail(f"{role} must not be empty")
    if "\\" in value:
        fail(f"{role} must use '/', not '\\': {value}")
    if value.startswith("/"):
        fail(f"{role} must be relative: {value}")
    normalized = posixpath.normpath(value)
    if normalized == ".." or normalized.startswith("../"):
        fail(f"{role} must stay inside its root: {value}")
    return normalized


def _validate_names(source_name: str, output_name: str) -> tuple[str, str]:
    """Normalize one mapping pair and check its output filename."""
    source_relative = validate_relative_name(source_name, role="source name")
    output_relative = validate_relative_name(output_name, role="output name")
    if posixpath.basename(output_relative) != output_relative:
        fail(f"output name must be a bare filename: {output_name}")
    if not output_relative.endswith(".md"):
        fail(f"output name must end in '.md': {output_name}")
    return source_relative, output_relative


def _stat_mode(filesystem: FileSystem, path: Path) -> int | None:
    """Return a path's mode bits, or ``None`` when it does not exist.

    ``Path.is_dir`` and ``Path.is_file`` swallow some filesystem errors on
    newer interpreters, so a permission denial would read as a missing path.
    The boundary reports the denial, which is translated here rather than
    escaping as a traceback.
    """
    try:
        return filesystem.stat_mode(path)
    except OSError as error:
        fail(f"cannot inspect the import paths: {error}")


def _is_directory(filesystem: FileSystem, path: Path) -> bool:
    """Report whether a path is a directory, refusing an inspectable error."""
    mode = _stat_mode(filesystem, path)
    return mode is not None and stat.S_ISDIR(mode)


def _is_file(filesystem: FileSystem, path: Path) -> bool:
    """Report whether a path is a regular file, refusing an inspectable error."""
    mode = _stat_mode(filesystem, path)
    return mode is not None and stat.S_ISREG(mode)


def _validate_mapping(
    mappings: Sequence[tuple[str, str]],
    source_directory: Path,
    output_directory: Path,
    filesystem: FileSystem,
) -> None:
    """Refuse a pair that repeats a side, misses a source, or overwrites one."""
    if not mappings:
        fail("at least one source/output mapping is required")
    seen_sources: set[str] = set()
    seen_outputs: set[str] = set()
    resolved_source = filesystem.resolve(source_directory)
    for source_name, output_name in mappings:
        source_relative, output_relative = _validate_names(
            source_name, output_name
        )
        if source_relative in seen_sources:
            fail(f"source is mapped more than once: {source_name}")
        if output_relative in seen_outputs:
            fail(f"output is mapped more than once: {output_name}")
        source_file = filesystem.resolve(source_directory / source_relative)
        if not source_file.is_relative_to(resolved_source):
            fail(f"source must stay inside the source directory: {source_name}")
        if not _is_file(filesystem, source_file):
            fail(f"source file does not exist: {source_file}")
        seen_sources.add(source_relative)
        seen_outputs.add(output_relative)

    source_files = {
        filesystem.resolve(source_directory / name) for name in seen_sources
    }
    output_files = {
        filesystem.resolve(output_directory / name) for name in seen_outputs
    }
    overlap = sorted(source_files & output_files)
    if overlap:
        fail(f"output would overwrite a source file: {overlap[0]}")


def _validate_filesystem(config: VendorConfig, filesystem: FileSystem) -> None:
    """Check the directories and mappings that touch the filesystem."""
    if not _is_directory(filesystem, config.source_directory):
        fail(f"source directory does not exist: {config.source_directory}")
    if not _is_directory(filesystem, config.output_directory):
        fail(f"output directory does not exist: {config.output_directory}")
    _validate_mapping(
        config.mappings,
        config.source_directory,
        config.output_directory,
        filesystem,
    )


def validate(
    config: VendorConfig, filesystem: FileSystem = DEFAULT_FILE_SYSTEM
) -> None:
    """Check every argument before the first file is written.

    Parameters
    ----------
    config
        Import description to check.
    filesystem
        Boundary used to inspect the directories and mapped paths. The default
        reads the local machine; a caller may substitute a double that records
        the inspection or injects an environmental error.

    Raises
    ------
    VendorError
        If the tag, repository, directory, limit, or mapping is unusable.
    """
    if not _REPOSITORY.fullmatch(config.repository):
        fail(
            "repository must be 'owner/name' without a host or scheme: "
            f"{config.repository}"
        )
    if not _TAG.fullmatch(config.tag):
        fail(f"tag is not a valid ref name: {config.tag}")
    if any(part in {"", ".", ".."} for part in config.tag.split("/")):
        fail(f"tag is not a valid ref name: {config.tag}")
    if config.line_length < 1:
        fail(f"line length must be positive: {config.line_length}")
    if config.code_line_length < 1:
        fail(f"code line length must be positive: {config.code_line_length}")
    validate_relative_name(config.source_path, role="source path")
    try:
        _validate_filesystem(config, filesystem)
    except OSError as error:
        # Path resolution can still raise an environmental error. The front
        # end promises one diagnostic line, so translate it here as well.
        fail(f"cannot inspect the import paths: {error}")


def project_name(config: VendorConfig) -> str:
    """Return the note's project name, defaulting to the repository name.

    Parameters
    ----------
    config
        Import description.

    Returns
    -------
    str
        Explicit project name, or the repository's final path segment.
    """
    return config.project or config.repository.rsplit("/", 1)[-1]