"""Rewrite relative link destinations at the pinned tag.

Inline links and images, plus link reference definitions, are recognized by
scanning the document with the protection mask. Every construct keeps its
label, delimiter, title, and fragment; only the destination moves. Destinations
between two mapped guides become the local output filename, so the vendored
guides link to each other.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import posixpath
import re

from .config import VendorConfig, fail

_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_DEFINITION = re.compile(r"(?m)^ {0,3}\[([^\]]+)\]:[ \t]*")


def _skip_link_space(text: str, position: int) -> int | None:
    """Skip link whitespace; return ``None`` after a second line ending."""
    newlines = 0
    while position < len(text) and text[position] in " \t\n":
        if text[position] == "\n":
            newlines += 1
            if newlines > 1:
                return None
        position += 1
    return position


def _find_closing_bracket(text: str, position: int, mask: Sequence[bool]) -> int | None:
    """Return the ``]`` matching a label opener, or ``None`` if unclosed."""
    depth = 0
    while position < len(text):
        if mask[position]:
            position += 1
            continue
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            if depth == 0:
                return position
            depth -= 1
        position += 1
    return None


def _parse_destination(text: str, position: int) -> tuple[int, int, int] | None:
    """Return a destination's start, end, and offset after it, or ``None``."""
    if position >= len(text):
        return None
    if text[position] == "<":
        return _parse_angle_destination(text, position)
    return _parse_bare_destination(text, position)


def _parse_angle_destination(text: str, position: int) -> tuple[int, int, int] | None:
    """Read an ``<angle-bracketed>`` destination."""
    start = position + 1
    cursor = start
    while cursor < len(text) and text[cursor] not in ">\n":
        if text[cursor] == "\\":
            cursor += 1
        cursor += 1
    if cursor >= len(text) or text[cursor] != ">":
        return None
    return start, cursor, cursor + 1


def _parse_bare_destination(text: str, position: int) -> tuple[int, int, int] | None:
    """Read an unbracketed destination, honouring balanced parentheses."""
    start = position
    depth = 0
    cursor = position
    while cursor < len(text):
        character = text[cursor]
        if character == "\\":
            cursor += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        elif character.isspace() or character in "<>":
            break
        cursor += 1
    if depth or cursor == start:
        return None
    return start, cursor, cursor


def _skip_title(text: str, position: int) -> int | None:
    """Skip an optional link title and its trailing space; ``None`` if malformed."""
    cursor = position
    while cursor < len(text) and text[cursor] in " \t\n":
        cursor += 1
    if cursor >= len(text) or text[cursor] not in "\"'(":
        return cursor
    closer = ")" if text[cursor] == "(" else text[cursor]
    cursor += 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == closer:
            cursor += 1
            break
        cursor += 1
    else:
        return None
    while cursor < len(text) and text[cursor] in " \t\n":
        cursor += 1
    return cursor


def _parse_inline_link(
    text: str, position: int, mask: Sequence[bool]
) -> tuple[int, int, int] | None:
    """Return an inline link's destination bounds and end, or ``None``."""
    # CommonMark allows no space between a label's ``]`` and its ``(``.
    cursor = position
    if cursor >= len(text) or text[cursor] != "(":
        return None
    cursor = _skip_link_space(text, cursor + 1)
    if cursor is None:
        return None
    destination = _parse_destination(text, cursor)
    if destination is None:
        return None
    start, end, cursor = destination
    cursor = _skip_title(text, cursor)
    if cursor is None or cursor >= len(text) or text[cursor] != ")":
        return None
    if any(mask[index] for index in range(start, end)):
        return None
    return start, end, cursor + 1


def _mapping_targets(config: VendorConfig) -> dict[str, str]:
    """Map each mapped source's repository path to its output filename."""
    return {
        posixpath.normpath(posixpath.join(config.source_path, name)): output
        for name, output in config.mappings
    }


def _repository_path(config: VendorConfig, source_name: str, path: str) -> str:
    """Resolve a relative destination against the source file's directory."""
    if path.startswith("/"):
        return posixpath.normpath(path.lstrip("/"))
    base = posixpath.join(config.source_path, posixpath.dirname(source_name))
    return posixpath.normpath(posixpath.join(base, path))


def _target_url(
    config: VendorConfig,
    repository_path: str,
    *,
    image: bool,
    trailing_slash: bool,
) -> str:
    """Choose the local filename or tag-pinned URL for a repository path."""
    targets = _mapping_targets(config)
    if repository_path in targets:
        return targets[repository_path]
    if image:
        return (
            f"https://raw.githubusercontent.com/{config.repository}/"
            f"{config.tag}/{repository_path}"
        )
    kind = "tree" if trailing_slash else "blob"
    return (
        f"https://github.com/{config.repository}/{kind}/{config.tag}/"
        f"{repository_path}"
    )


def destination_url(
    destination: str,
    *,
    config: VendorConfig,
    image: bool,
    source_name: str,
) -> str:
    """Rewrite one relative destination as a tag-pinned URL.

    Parameters
    ----------
    destination
        Destination exactly as Markdown wrote it.
    config
        Import description.
    image
        Whether the destination belongs to an image.
    source_name
        Repository-relative name of the source file being converted.

    Returns
    -------
    str
        The rewritten destination, or the original when it is absolute,
        scheme-relative, fragment-only, or already a URL.

    Raises
    ------
    VendorError
        If a relative destination escapes the upstream repository root.
    """
    if destination.startswith(("#", "//")):
        return destination
    if _SCHEME.match(destination):
        return destination
    path, _, fragment = destination.partition("#")
    path, _, query = path.partition("?")
    if not path:
        return destination

    trailing_slash = path.endswith("/")
    repository_path = _repository_path(config, source_name, path)
    if repository_path == ".." or repository_path.startswith("../"):
        fail(
            f"link in {source_name} escapes the upstream repository: "
            f"{destination}"
        )

    rewritten = _target_url(
        config,
        repository_path,
        image=image,
        trailing_slash=trailing_slash,
    )
    if query:
        rewritten += f"?{query}"
    if fragment:
        rewritten += f"#{fragment}"
    return rewritten


def _inline_replacements(
    text: str,
    mask: Sequence[bool],
    config: VendorConfig,
    source_name: str,
) -> list[tuple[int, int, str]]:
    """Collect replacements for inline links and images."""
    replacements: list[tuple[int, int, str]] = []
    resume_at: dict[int, int] = {}
    cursor = 0
    while cursor < len(text):
        if cursor in resume_at:
            cursor = resume_at[cursor]
            continue
        if mask[cursor] or text[cursor] != "[":
            cursor += 1
            continue
        image = cursor > 0 and text[cursor - 1] == "!" and not mask[cursor - 1]
        label_end = _find_closing_bracket(text, cursor + 1, mask)
        if label_end is None:
            cursor += 1
            continue
        parsed = _parse_inline_link(text, label_end + 1, mask)
        if parsed is None:
            # The label is not a link, but a nested link inside it may be.
            cursor += 1
            continue
        start, end, after = parsed
        original = text[start:end]
        rewritten = destination_url(
            original,
            config=config,
            image=image,
            source_name=source_name,
        )
        if rewritten != original:
            replacements.append((start, end, rewritten))
        # Resume inside the label; the parsed destination is already handled.
        resume_at[label_end + 1] = after
        cursor += 1
    return replacements


def _definition_replacements(
    text: str,
    mask: Sequence[bool],
    config: VendorConfig,
    source_name: str,
) -> list[tuple[int, int, str]]:
    """Collect replacements for link reference definitions."""
    replacements: list[tuple[int, int, str]] = []
    for match in _DEFINITION.finditer(text):
        if mask[match.start()] or match.group(1).startswith("^"):
            continue
        position = _skip_link_space(text, match.end())
        if position is None:
            continue
        parsed = _parse_destination(text, position)
        if parsed is None:
            continue
        start, end, _ = parsed
        if any(mask[index] for index in range(start, end)):
            continue
        original = text[start:end]
        rewritten = destination_url(
            original,
            config=config,
            image=False,
            source_name=source_name,
        )
        if rewritten != original:
            replacements.append((start, end, rewritten))
    return replacements


def link_replacements(
    text: str,
    mask: Sequence[bool],
    config: VendorConfig,
    source_name: str,
) -> list[tuple[int, int, str]]:
    """Collect destination replacements for inline links and definitions.

    Parameters
    ----------
    text
        Document being scanned.
    mask
        Protected-character map.
    config
        Import description.
    source_name
        Repository-relative name of the source file being converted.

    Returns
    -------
    list[tuple[int, int, str]]
        ``(start, end, replacement)`` triples in document order.
    """
    return [
        *_inline_replacements(text, mask, config, source_name),
        *_definition_replacements(text, mask, config, source_name),
    ]


def apply_replacements(
    text: str, replacements: Iterable[tuple[int, int, str]]
) -> str:
    """Apply destination replacements without disturbing any other byte.

    Parameters
    ----------
    text
        Document to rewrite.
    replacements
        Spans and their replacements, in any order.

    Returns
    -------
    str
        Document with only the named spans replaced.

    Raises
    ------
    VendorError
        If two replacements overlap, which would make the result ambiguous.
    """
    ordered = sorted(replacements, reverse=True)
    previous_start = len(text)
    for start, end, replacement in ordered:
        if end > previous_start:
            fail("internal error: overlapping link replacements")
        text = text[:start] + replacement + text[end:]
        previous_start = start
    return text