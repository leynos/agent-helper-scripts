"""Rewrite relative link destinations at the pinned tag.

Inline links and images, link reference definitions, and the reference forms
that name them are recognized by scanning the document with the protection
mask. Every construct keeps its label, delimiter, title, and fragment; only the
destination moves. A definition used by an image is rewritten as an image
source, whether the image writes the label in full, collapsed, or shortcut
form. Destinations between two mapped guides become the local output filename,
so the vendored guides link to each other.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import posixpath
import re

from .config import VendorConfig, fail

_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
#: A definition label may contain escaped brackets. ``_reference_label`` keeps
#: the escapes too, so both sides normalize to the same text.
_DEFINITION = re.compile(r"(?m)^ {0,3}\[((?:\\.|[^\\\]])+)\]:[ \t]*")
_LABEL_SPACE = re.compile(r"\s+")
_BLANK_LINE = re.compile(r"\n[ \t\r]*\n")

#: Longest link label CommonMark allows, counting the characters between the
#: brackets.
_MAX_LABEL = 999


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


def _is_escaped(text: str, position: int, mask: Sequence[bool]) -> bool:
    """Report whether a character follows an odd run of backslashes."""
    backslashes = 0
    cursor = position - 1
    while cursor >= 0 and text[cursor] == "\\" and not mask[cursor]:
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _is_image_marker(text: str, position: int, mask: Sequence[bool]) -> bool:
    """Report whether the bracket at ``position`` opens an image.

    The ``!`` must be present, outside protected text, and not escaped itself:
    ``\\![alt]`` renders as a literal ``!`` followed by a shortcut link.
    """
    if position == 0 or text[position - 1] != "!" or mask[position - 1]:
        return False
    return not _is_escaped(text, position - 1, mask)


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
        image = _is_image_marker(text, cursor, mask)
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


def _normalize_label(label: str) -> str:
    """Normalize a reference label the way CommonMark matches labels."""
    return _LABEL_SPACE.sub(" ", label.strip()).casefold()


def _has_unescaped_bracket(label: str) -> bool:
    """Report whether a label contains a bracket that is not backslash-escaped."""
    cursor = 0
    while cursor < len(label):
        if label[cursor] == "\\":
            cursor += 2
            continue
        if label[cursor] in "[]":
            return True
        cursor += 1
    return False


def _is_valid_label(label: str) -> bool:
    """Report whether text between brackets can be a CommonMark link label.

    A label needs one character that is not whitespace, cannot contain an
    unescaped bracket, cannot cross a blank line, and holds at most 999
    characters. Anything else is not a label, so the reference falls back to
    the shortcut form.
    """
    return (
        bool(label.strip())
        and len(label) <= _MAX_LABEL
        and _BLANK_LINE.search(label) is None
        and not _has_unescaped_bracket(label)
    )


def _reference_label(
    text: str, position: int, mask: Sequence[bool], alt: str
) -> str:
    """Return the label an image reference names, defaulting to its alt text.

    ``![alt][label]`` is a full reference, ``![alt][]`` is collapsed, and
    ``![alt]`` is a shortcut; both of the last two use the alt text as the
    label. A malformed full reference such as ``![alt][ ]`` or
    ``![alt][outer[inner]]`` is not a link at all and falls back to the
    shortcut ``![alt]``. An inline ``![alt](destination)`` has no label, but it
    never reaches this function because the caller only runs on bracket forms.
    """
    if position < len(text) and text[position] == "[" and not mask[position]:
        end = _find_closing_bracket(text, position + 1, mask)
        if end is not None:
            inner = text[position + 1 : end]
            if _is_valid_label(inner):
                return _normalize_label(inner)
            return _normalize_label(alt)
    return _normalize_label(alt)


def _inline_image_end(
    text: str, position: int, mask: Sequence[bool]
) -> int | None:
    """Return the end of an inline image's destination, or ``None``.

    :func:`_parse_inline_link` rejects an empty destination, but CommonMark
    accepts ``![alt]()`` as an inline image, so that form is recognized here.
    An unterminated destination such as ``![alt](unterminated`` is not an
    inline image: CommonMark falls back to the shortcut reference ``![alt]``.
    """
    parsed = _parse_inline_link(text, position, mask)
    if parsed is not None:
        return parsed[2]
    if position >= len(text) or text[position] != "(":
        return None
    cursor = _skip_link_space(text, position + 1)
    if cursor is None or cursor >= len(text) or text[cursor] != ")":
        return None
    return cursor + 1


def _image_reference_labels(text: str, mask: Sequence[bool]) -> set[str]:
    """Collect the labels that reference-style images in the document name.

    A definition's destination must render as an image, so the definition has
    to be rewritten as an image source. Scanning the usages is the only way to
    know that: a definition alone, ``[diagram]: images/diagram.png``, does not
    say whether a link or an image will use it.
    """
    labels: set[str] = set()
    cursor = 0
    while cursor < len(text):
        if mask[cursor] or text[cursor] != "[":
            cursor += 1
            continue
        if not _is_image_marker(text, cursor, mask):
            cursor += 1
            continue
        label_end = _find_closing_bracket(text, cursor + 1, mask)
        if label_end is None:
            cursor += 1
            continue
        alt = text[cursor + 1 : label_end]
        if _inline_image_end(text, label_end + 1, mask) is not None:
            # An inline image names no definition; ``_inline_replacements``
            # rewrites it directly.
            cursor += 1
            continue
        labels.add(_reference_label(text, label_end + 1, mask, alt))
        cursor += 1
    return labels


def _definition_replacements(
    text: str,
    mask: Sequence[bool],
    config: VendorConfig,
    source_name: str,
) -> list[tuple[int, int, str]]:
    """Collect replacements for link reference definitions.

    A definition used by an image is rewritten as an image source, even when a
    link shares the same label: a ``blob`` URL renders as a broken image,
    whereas a ``raw`` URL still resolves when followed as a link.
    """
    image_labels = _image_reference_labels(text, mask)
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
            image=_normalize_label(match.group(1)) in image_labels,
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