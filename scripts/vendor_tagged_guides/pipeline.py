"""Compose conversion, formatting, and writing into one import.

Every source is converted before any output file is written, so a source that
cannot be converted leaves the consumer's ``docs/`` unchanged. The optional
formatter then runs twice with the exemption pass between, and the pipeline
refuses the result unless the second pass changed nothing; that fixed point is
what makes a rerun at the same tag reproduce the same bytes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from .config import VendorConfig, fail, validate
from .exemptions import insert_exemptions
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


def _write(path: Path, text: str) -> None:
    """Write one converted document with ``\\n`` newlines.

    Parameters
    ----------
    path
        Destination file.
    text
        Document content.
    """
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8", newline="\n")


def _read(path: Path) -> str:
    """Read one document and normalize its newlines.

    Parameters
    ----------
    path
        File to read.

    Returns
    -------
    str
        Content with ``\\n`` newlines.
    """
    return (
        path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    )


def _exempt(text: str, config: VendorConfig) -> str:
    """Bracket over-long blocks using the configured line limits."""
    return insert_exemptions(
        text,
        line_length=config.line_length,
        code_line_length=config.code_line_length,
    )


def vendor(
    config: VendorConfig,
    *,
    format_files: Callable[[Sequence[Path]], None] | None = None,
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

    Returns
    -------
    tuple[Path, ...]
        Written paths in mapping order.

    Raises
    ------
    VendorError
        If an argument is unusable, a source already carries the note, or the
        formatter does not reach a fixed point.
    """
    validate(config)
    converted = [
        convert(_read(config.source_directory / source_name), config, source_name)
        for source_name, _ in config.mappings
    ]
    written = [
        config.output_directory / output_name
        for _, output_name in config.mappings
    ]
    for path, text in zip(written, converted, strict=True):
        _write(path, text)

    if format_files is None:
        for path, text in zip(written, converted, strict=True):
            _write(path, _exempt(text, config))
        return tuple(written)

    format_files(written)
    exempted = [_exempt(_read(path), config) for path in written]
    for path, text in zip(written, exempted, strict=True):
        _write(path, text)

    format_files(written)
    for path, text in zip(written, exempted, strict=True):
        if _read(path) != text:
            fail(f"formatter did not reach a fixed point for {path}")
    return tuple(written)