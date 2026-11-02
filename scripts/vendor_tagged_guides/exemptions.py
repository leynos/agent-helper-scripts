"""Add bounded MD013 exemptions to converted Markdown.

The consumer's Markdown gate enforces a prose line length. The vendored text is
verbatim, so a long upstream paragraph cannot be reflowed; instead the smallest
top-level block that contains an over-long line is wrapped in one
disable/enable pair. The pair sits at column zero with blank lines around it, so
the formatter's later reflow cannot disturb it. Detection skips lines that an
existing pair already covers, which makes a second pass change nothing.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
import re

from .config import DEFAULT_CODE_LINE_LENGTH, DEFAULT_LINE_LENGTH
from .masking import fence_line_flags

#: Comment pair that brackets a block too long for the prose limit.
DISABLE_M013 = "<!-- markdownlint-disable MD013 -->"
ENABLE_M013 = "<!-- markdownlint-enable MD013 -->"

_HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]|\Z)")
_FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)\Z")
_LIST_ITEM = re.compile(r" {0,3}(?:[-*+]|\d+[.)])[ \t]")
_THEMATIC_BREAK = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*\Z")
_TABLE_DELIMITER = re.compile(
    r" {0,3}\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*\Z"
)
_HTML_COMMENT_START = re.compile(r" {0,3}<!--")
_DISABLE_BLOCK = re.compile(
    r" {0,3}<!--\s*markdownlint-disable\s+MD013\s*-->\s*\Z"
)
_ENABLE_BLOCK = re.compile(
    r" {0,3}<!--\s*markdownlint-enable\s+MD013\s*-->\s*\Z"
)
_DISABLE_LINE = re.compile(
    r" {0,3}<!--\s*markdownlint-disable-line\s+MD013\s*-->\s*\Z"
)
_DISABLE_NEXT_LINE = re.compile(
    r" {0,3}<!--\s*markdownlint-disable-next-line\s+MD013\s*-->\s*\Z"
)


def table_line_flags(lines: Sequence[str]) -> list[bool]:
    """Mark lines that belong to a Markdown table.

    Markdownlint exempts tables from MD013, so the gate must not report them.

    Parameters
    ----------
    lines
        Document lines, without newline characters.

    Returns
    -------
    list[bool]
        One flag per table line, including the header and delimiter rows.
    """
    flags = [False] * len(lines)
    index = 0
    while index + 1 < len(lines):
        delimiter = _TABLE_DELIMITER.match(lines[index + 1])
        if delimiter is None or "|" not in lines[index]:
            index += 1
            continue
        first = index
        index += 2
        while index < len(lines) and lines[index].strip() and "|" in lines[index]:
            index += 1
        for flag_index in range(first, min(index, len(flags))):
            flags[flag_index] = True
    return flags


def exempt_lines(lines: Sequence[str]) -> set[int]:
    """Collect line numbers covered by an existing MD013 exemption.

    Parameters
    ----------
    lines
        Document lines, without newline characters.

    Returns
    -------
    set[int]
        Zero-based line numbers a later detection pass must ignore.
    """
    exempt: set[int] = set()
    disabled = False
    for index, line in enumerate(lines):
        if _DISABLE_BLOCK.match(line):
            disabled = True
            exempt.add(index)
            continue
        if _ENABLE_BLOCK.match(line):
            disabled = False
            exempt.add(index)
            continue
        if disabled:
            exempt.add(index)
        if _DISABLE_NEXT_LINE.match(line):
            exempt.add(index)
            exempt.add(index + 1)
        if _DISABLE_LINE.match(line):
            exempt.add(index)
    return exempt


def _is_blank(line: str) -> bool:
    """Say whether a line contains only whitespace."""
    return not line.strip()


def _is_block_starter(line: str) -> bool:
    """Say whether a line begins a block that ends a paragraph."""
    return bool(
        _HEADING.match(line)
        or _FENCE_OPEN.match(line)
        or line.lstrip().startswith(">")
        or _LIST_ITEM.match(line)
        or _THEMATIC_BREAK.match(line)
        or _HTML_COMMENT_START.match(line)
        or _TABLE_DELIMITER.match(line)
    )


def _is_indented(line: str) -> bool:
    """Say whether a line is indented enough to continue a list item."""
    return line.startswith(("  ", "\t"))


def _flag_extent(fence_flags: Sequence[bool], index: int) -> int:
    """Return the line after a run of flagged lines."""
    while index < len(fence_flags) and fence_flags[index]:
        index += 1
    return index


def _comment_extent(lines: Sequence[str], index: int) -> int:
    """Return the line after an HTML comment."""
    cursor = index
    while cursor < len(lines) and "-->" not in lines[cursor]:
        cursor += 1
    return min(cursor + 1, len(lines))


def _quote_extent(lines: Sequence[str], index: int) -> int:
    """Return the line after a blockquote."""
    cursor = index + 1
    while cursor < len(lines) and lines[cursor].lstrip().startswith(">"):
        cursor += 1
    return cursor


def _list_extent(lines: Sequence[str], index: int) -> int:
    """Return the line after a list, including blank-separated items."""
    cursor = index
    while cursor + 1 < len(lines):
        following = lines[cursor + 1]
        if _is_blank(following):
            resume = _blank_run_end(lines, cursor + 1)
            if resume is None:
                break
            cursor = resume
            continue
        if _LIST_ITEM.match(following) or _is_indented(following):
            cursor += 1
            continue
        if not _is_block_starter(following):
            cursor += 1
            continue
        break
    return cursor + 1


def _blank_run_end(lines: Sequence[str], index: int) -> int | None:
    """Return the first non-blank line after ``index`` when a list resumes.

    Returns ``None`` when the blank run ends the list instead.
    """
    cursor = index
    while cursor < len(lines) and _is_blank(lines[cursor]):
        cursor += 1
    if cursor < len(lines) and (
        _LIST_ITEM.match(lines[cursor]) or _is_indented(lines[cursor])
    ):
        return cursor
    return None


def _paragraph_extent(lines: Sequence[str], index: int) -> int:
    """Return the line after a paragraph."""
    cursor = index
    while (
        cursor + 1 < len(lines)
        and not _is_blank(lines[cursor + 1])
        and not _is_block_starter(lines[cursor + 1])
    ):
        cursor += 1
    return cursor + 1


def _block_extent(
    lines: Sequence[str],
    index: int,
    fence_flags: Sequence[bool],
    table_flags: Sequence[bool],
) -> int:
    """Return the line after the top-level block starting at ``index``."""
    if fence_flags[index] or table_flags[index]:
        return _flag_extent(
            fence_flags if fence_flags[index] else table_flags, index
        )
    if _HTML_COMMENT_START.match(lines[index]):
        return _comment_extent(lines, index)
    if lines[index].lstrip().startswith(">"):
        return _quote_extent(lines, index)
    if _LIST_ITEM.match(lines[index]):
        return _list_extent(lines, index)
    if _HEADING.match(lines[index]) or _THEMATIC_BREAK.match(lines[index]):
        return index + 1
    return _paragraph_extent(lines, index)


def block_ranges(
    lines: Sequence[str], fence_flags: Sequence[bool], table_flags: Sequence[bool]
) -> tuple[list[tuple[int, int]], list[int]]:
    """Split a document into top-level blocks.

    The ranges let an exemption wrap the smallest paragraph, list, blockquote,
    table, or fenced block that contains an offending line.

    Parameters
    ----------
    lines
        Document lines, without newline characters.
    fence_flags
        Fenced-code map from :func:`~vendor_tagged_guides.masking.fence_line_flags`.
    table_flags
        Table map from :func:`table_line_flags`.

    Returns
    -------
    tuple[list[tuple[int, int]], list[int]]
        Inclusive block ranges in document order, and an owner index per line
        (``-1`` for blank lines).
    """
    ranges: list[tuple[int, int]] = []
    owner = [-1] * len(lines)
    index = 0
    while index < len(lines):
        if _is_blank(lines[index]):
            index += 1
            continue
        end = _block_extent(lines, index, fence_flags, table_flags)
        ranges.append((index, end - 1))
        index = end

    for block, (start, end) in enumerate(ranges):
        for line_number in range(start, end + 1):
            owner[line_number] = block
    return ranges, owner


def _is_too_long(line: str, limit: int) -> bool:
    """Apply MD013's non-strict length check to one line.

    MD013 allows a long line when it has no whitespace beyond the limit, which
    is how long URLs stay legal. Trailing whitespace is not counted, matching
    the rule's non-strict mode.

    Parameters
    ----------
    line
        Line to check, without its newline.
    limit
        Maximum permitted length.

    Returns
    -------
    bool
        ``True`` when the line violates the rule.
    """
    stripped = line.rstrip()
    if len(stripped) <= limit:
        return False
    return any(character.isspace() for character in stripped[limit:])


def _normalized_lines(text: str) -> list[str]:
    """Split a document into lines with ``\\n`` endings."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _overlong_lines(
    lines: Sequence[str],
    fence_flags: Sequence[bool],
    table_flags: Sequence[bool],
    exempt: set[int],
    line_length: int,
    code_line_length: int,
) -> Iterator[int]:
    """Yield lines the consumer's Markdown gate would report.

    A line inside fenced code is always judged against the code limit, even
    when it begins with ``#``: a shell or Python comment is not a Markdown
    heading, so the heading exemption must not hide it. Tables are exempt only
    outside fenced code, where the shared configuration turns their check off.
    """
    for index, line in enumerate(lines):
        if index in exempt:
            continue
        if not fence_flags[index] and (
            table_flags[index] or _HEADING.match(line)
        ):
            continue
        limit = code_line_length if fence_flags[index] else line_length
        if _is_too_long(line, limit):
            yield index


def long_lines(
    text: str,
    *,
    line_length: int = DEFAULT_LINE_LENGTH,
    code_line_length: int = DEFAULT_CODE_LINE_LENGTH,
) -> tuple[int, ...]:
    """List lines that the consumer's Markdown gate would report.

    Headings and tables are skipped because the shared configuration disables
    their length checks. Lines already covered by an MD013 exemption are
    skipped so the function stays idempotent.

    Parameters
    ----------
    text
        Document to inspect.
    line_length
        Prose limit.
    code_line_length
        Limit applied inside fenced code.

    Returns
    -------
    tuple[int, ...]
        Zero-based line numbers in document order.
    """
    lines = _normalized_lines(text)
    fence_flags = fence_line_flags(lines)
    table_flags = table_line_flags(lines)
    exempt = exempt_lines(lines)
    return tuple(
        _overlong_lines(
            lines,
            fence_flags,
            table_flags,
            exempt,
            line_length,
            code_line_length,
        )
    )


def insert_exemptions(
    text: str,
    *,
    line_length: int = DEFAULT_LINE_LENGTH,
    code_line_length: int = DEFAULT_CODE_LINE_LENGTH,
) -> str:
    """Bracket every offending top-level block in an MD013 exemption.

    One disable/enable pair wraps the smallest paragraph, list, blockquote,
    table, or fenced block that contains an over-long line. Running the function
    twice changes nothing because lines between an existing pair are skipped.

    Parameters
    ----------
    text
        Document to adjust.
    line_length
        Prose limit.
    code_line_length
        Limit applied inside fenced code.

    Returns
    -------
    str
        Document with bounded exemptions and one trailing newline.
    """
    lines = _normalized_lines(text.rstrip("\n"))
    fence_flags = fence_line_flags(lines)
    table_flags = table_line_flags(lines)
    exempt = exempt_lines(lines)
    ranges, owner = block_ranges(lines, fence_flags, table_flags)

    targets = _offending_blocks(
        lines, fence_flags, table_flags, exempt, owner, line_length, code_line_length
    )
    for block in sorted(targets, reverse=True):
        lines = _bracket(lines, *ranges[block])
    return "\n".join(lines).rstrip("\n") + "\n"


def _offending_blocks(
    lines: Sequence[str],
    fence_flags: Sequence[bool],
    table_flags: Sequence[bool],
    exempt: set[int],
    owner: Sequence[int],
    line_length: int,
    code_line_length: int,
) -> set[int]:
    """Return the block indices that contain an over-long line."""
    return {
        owner[index]
        for index in _overlong_lines(
            lines,
            fence_flags,
            table_flags,
            exempt,
            line_length,
            code_line_length,
        )
        if owner[index] >= 0
    }


def _bracket(lines: Sequence[str], start: int, end: int) -> list[str]:
    """Wrap one inclusive line range in a padded disable/enable pair."""
    before = [""] if start > 0 and not _is_blank(lines[start - 1]) else []
    after = (
        [""]
        if end + 1 < len(lines) and not _is_blank(lines[end + 1])
        else []
    )
    return [
        *lines[:start],
        *before,
        DISABLE_M013,
        "",
        *lines[start : end + 1],
        "",
        ENABLE_M013,
        *after,
        *lines[end + 1 :],
    ]