"""Compose conversion, formatting, and writing into one import.

Every source is converted before any output file is written, so a source that
cannot be converted leaves the consumer's ``docs/`` unchanged. A failure after
the first write attempts to restore every previous output file, so a rejected
run does not normally leave unformatted copies behind. Restoration is best
effort rather than guaranteed: each remaining path is still attempted, and a
restore that fails is reported together with the original failure. The
optional formatter then runs twice with the exemption pass between, and the
pipeline refuses the result unless the second pass changed nothing; that fixed
point is what makes a rerun at the same tag reproduce the same bytes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import stat

from .config import VendorConfig, fail, validate
from .exemptions import insert_exemptions
from .filesystem import DEFAULT_FILE_SYSTEM, FileSystem
from .links import apply_replacements, link_replacements
from .masking import masked_regions
from .note import IMPORT_MARKER, insert_note


def convert(text: str, config: VendorConfig, source_name: str = "") -> str:
    """Convert one upstream document into a vendored copy.

    Parameters
    ----------
    text
        Upstream Markdown, in any newline convention.
    config
        Import description.
    source_name
        Repository-relative source filename, used to resolve links between
        mapped guides. Defaults to the first mapping's source.

    Returns
    -------
    str
        Converted document with ``\\n`` newlines and one trailing newline.

    Raises
    ------
    VendorError
        If the source already carries the canonical note or has no level-one
        heading.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    mask = masked_regions(normalized)
    position = normalized.find(IMPORT_MARKER)
    while position >= 0:
        if not mask[position]:
            fail("source already carries the canonical import marker")
        position = normalized.find(IMPORT_MARKER, position + len(IMPORT_MARKER))
    name = source_name or config.mappings[0][0]
    rewritten = apply_replacements(
        normalized,
        link_replacements(normalized, mask, config, name),
    )
    return insert_note(rewritten, config).rstrip("\n") + "\n"


def _write(filesystem: FileSystem, path: Path, text: str) -> None:
    """Write one converted document with ``\\n`` newlines and one trailing one.

    Raises
    ------
    VendorError
        If the file cannot be written, so the front end reports one diagnostic
        line rather than a traceback.
    """
    try:
        filesystem.write_text(path, text.rstrip("\n") + "\n")
    except OSError as error:
        fail(f"cannot write {path}: {error}")


def _read(filesystem: FileSystem, path: Path) -> str:
    """Read one document and normalize its newlines to ``\\n``.

    Raises
    ------
    VendorError
        If the file cannot be read or is not UTF-8, so the front end reports
        one diagnostic line rather than a traceback.
    """
    try:
        text = filesystem.read_text(path)
    except OSError as error:
        fail(f"cannot read {path}: {error}")
    except UnicodeDecodeError as error:
        fail(f"cannot decode {path} as UTF-8: {error}")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _exempt(text: str, config: VendorConfig) -> str:
    """Bracket over-long blocks using the configured line limits."""
    return insert_exemptions(
        text,
        line_length=config.line_length,
        code_line_length=config.code_line_length,
    )


def _write_and_format(
    config: VendorConfig,
    written: Sequence[Path],
    converted: Sequence[str],
    format_files: Callable[[Sequence[Path]], None] | None,
    filesystem: FileSystem,
) -> None:
    """Write the converted text, then reach the formatter's fixed point."""
    for path, text in zip(written, converted, strict=True):
        _write(filesystem, path, text)

    if format_files is None:
        for path, text in zip(written, converted, strict=True):
            _write(filesystem, path, _exempt(text, config))
        return

    format_files(written)
    exempted = [_exempt(_read(filesystem, path), config) for path in written]
    for path, text in zip(written, exempted, strict=True):
        _write(filesystem, path, text)

    format_files(written)
    for path, text in zip(written, exempted, strict=True):
        if _read(filesystem, path) != text:
            fail(f"formatter did not reach a fixed point for {path}")


def _previous_outputs(
    filesystem: FileSystem, written: Sequence[Path]
) -> dict[Path, bytes | None]:
    """Record each output's bytes, or ``None`` when it does not exist yet.

    An output that is a symbolic link is refused before anything is written.
    Following the link would let a write create a target outside the output
    directory, and a later restore would remove only the link, leaving that
    target behind. The link's own mode is inspected, so a dangling link is
    refused too, and an inspection failure is reported rather than read as an
    absent output.

    Raises
    ------
    VendorError
        If an output is a symbolic link, or an existing output cannot be
        inspected or read, so no conversion starts.
    """
    previous: dict[Path, bytes | None] = {}
    for path in written:
        try:
            mode = filesystem.lstat_mode(path)
            if mode is not None and stat.S_ISLNK(mode):
                fail(f"refusing to write through the symbolic link {path}")
            previous[path] = (
                filesystem.read_bytes(path) if mode is not None else None
            )
        except OSError as error:
            fail(f"cannot inspect or read {path}: {error}")
    return previous


def _restore(
    filesystem: FileSystem, previous: dict[Path, bytes | None]
) -> list[str]:
    """Attempt every restore and return one message per path that failed.

    One failed restore must not prevent the others: every output is attempted,
    so a single I/O error cannot strand the remaining files in their converted
    state. The caller reports every failure together with the original one.
    """
    failures: list[str] = []
    for path, content in previous.items():
        try:
            if content is None:
                filesystem.unlink(path)
            else:
                filesystem.write_bytes(path, content)
        except OSError as error:
            failures.append(f"{path}: {error}")
    return failures


def vendor(
    config: VendorConfig,
    *,
    format_files: Callable[[Sequence[Path]], None] | None = None,
    filesystem: FileSystem = DEFAULT_FILE_SYSTEM,
) -> tuple[Path, ...]:
    """Convert, format, and write every mapped guide.

    Parameters
    ----------
    config
        Import description. Its arguments are validated before any file is
        written.
    format_files
        Optional callable that rewrites the supplied paths in place. The front
        end supplies a cuprum-backed ``mdtablefix`` runner; tests supply a
        deterministic double.
    filesystem
        Boundary used for every read, write, and restore. The default reaches
        the local machine; a caller may substitute a double that records the
        operations or injects a failure.

    Returns
    -------
    tuple[Path, ...]
        Written paths in mapping order.

    Raises
    ------
    VendorError
        If an argument is unusable, a source cannot be read or decoded, a
        source already carries the note, an output is a symbolic link or
        cannot be inspected, the formatter does not reach a fixed point, or an
        output cannot be written. Any failure after the first
        write, including an interruption or an I/O error, attempts to restore
        the previous output files before it propagates. Restoration is best
        effort: the remaining outputs are still attempted, and a restore that
        fails is reported. An ordinary exception becomes a ``VendorError``
        carrying that report; an interruption is re-raised with the report
        attached as a note.
    """
    validate(config, filesystem)
    converted = [
        convert(
            _read(filesystem, config.source_directory / source_name),
            config,
            source_name,
        )
        for source_name, _ in config.mappings
    ]
    written = [
        config.output_directory / output_name
        for _, output_name in config.mappings
    ]
    previous = _previous_outputs(filesystem, written)
    try:
        _write_and_format(config, written, converted, format_files, filesystem)
    except BaseException as error:
        # Any failure, including an interruption or an I/O error, must attempt
        # to leave the consumer's directory as it was found. Every output is
        # attempted and every restore failure is reported with the original
        # failure.
        failures = _restore(filesystem, previous)
        if failures:
            summary = "could not restore previous output: " + "; ".join(
                failures
            )
            # An interruption must stay an interruption. Replacing it with a
            # VendorError would make the CLI report status 1 as if the run had
            # merely been refused, so only an ordinary exception is converted.
            if isinstance(error, Exception):
                fail(
                    f"{summary}; original failure: "
                    f"{type(error).__name__}: {error}"
                )
            error.add_note(summary)
        raise
    return tuple(written)