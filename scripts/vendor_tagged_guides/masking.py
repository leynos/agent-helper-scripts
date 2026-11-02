"""Find the text that link rewriting must leave byte for byte.

Fenced code, inline code spans, footnote definitions, and HTML comments are
protected. Each is found by its own pass, in an order that keeps one pass from
opening a construct inside another: fences and footnotes first, then comments,
then code spans over the characters the earlier passes left alive.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

_FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)\Z")
_FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})\s*\Z")
_FOOTNOTE_DEFINITION = re.compile(r" {0,3}\[\^[^\]]+\]:")


def fence_spans(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Find each fenced code block's half-open line range.

    Parameters
    ----------
    lines
        Document lines, without newline characters.

    Returns
    -------
    list[tuple[int, int]]
        ``(first, last)`` pairs, where ``last`` is the line after the closing
        fence, or the line count when the fence is unclosed.
    """
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        opening = _FENCE_OPEN.match(lines[index])
        if opening is None:
            index += 1
            continue
        character = opening.group(1)[0]
        length = len(opening.group(1))
        first = index
        index += 1
        while index < len(lines):
            closing = _FENCE_CLOSE.match(lines[index])
            index += 1
            if _closes_fence(closing, character, length):
                break
        spans.append((first, index))
    return spans


def _closes_fence(
    closing: re.Match[str] | None, character: str, length: int
) -> bool:
    """Say whether a line closes a fence opened with ``character``/``length``."""
    if closing is None:
        return False
    return closing.group(1)[0] == character and len(closing.group(1)) >= length


def fence_line_flags(lines: Sequence[str]) -> list[bool]:
    """Mark lines that belong to a fenced code block.

    Parameters
    ----------
    lines
        Document lines, without newline characters.

    Returns
    -------
    list[bool]
        One flag per line; the fence markers themselves are included.
    """
    flags = [False] * len(lines)
    for first, last in fence_spans(lines):
        for index in range(first, min(last, len(lines))):
            flags[index] = True
    return flags


def footnote_spans(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Find each footnote definition's half-open line range.

    A definition continues through indented continuation lines, adjacent
    definitions, and blank lines that lead into either.

    Parameters
    ----------
    lines
        Document lines, without newline characters.

    Returns
    -------
    list[tuple[int, int]]
        ``(first, last)`` pairs, where ``last`` is the line after the
        definition.
    """
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if not _FOOTNOTE_DEFINITION.match(lines[index]):
            index += 1
            continue
        first = index
        index = _footnote_end(lines, index + 1)
        spans.append((first, index))
    return spans


def _footnote_end(lines: Sequence[str], index: int) -> int:
    """Return the line after a footnote definition that starts before ``index``."""
    while index < len(lines):
        end = _continuation_end(lines, index)
        if end == index:
            break
        index = end
    return index


def _continuation_end(lines: Sequence[str], index: int) -> int:
    """Advance past one continuation line, or a blank run leading into one.

    Returns ``index`` unchanged when the line does not continue the definition,
    which ends the scan.
    """
    if _starts_continuation(lines[index]):
        return index + 1
    if lines[index].strip():
        return index
    lookahead = index
    while lookahead < len(lines) and not lines[lookahead].strip():
        lookahead += 1
    if lookahead < len(lines) and _starts_continuation(lines[lookahead]):
        return lookahead
    return index


def _starts_continuation(line: str) -> bool:
    """Say whether a non-blank line continues a footnote definition."""
    return line.startswith(("    ", "\t")) or bool(
        _FOOTNOTE_DEFINITION.match(line)
    )


def comment_spans(text: str) -> list[tuple[int, int]]:
    """Find each HTML comment's half-open character range.

    Parameters
    ----------
    text
        Document to scan.

    Returns
    -------
    list[tuple[int, int]]
        ``(start, end)`` pairs; an unterminated comment is not returned.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    while True:
        start = text.find("<!--", cursor)
        if start < 0:
            return spans
        end = text.find("-->", start + 4)
        if end < 0:
            return spans
        spans.append((start, end + 3))
        cursor = end + 3


class _LineIndex:
    """Map character ranges and line numbers onto one protection mask.

    Attributes
    ----------
    mask
        One flag per character, ``True`` where the character is protected.
    """

    def __init__(self, lines: Sequence[str], text_length: int) -> None:
        self._lines = lines
        self._text_length = text_length
        self._offsets = [0]
        for line in lines:
            self._offsets.append(self._offsets[-1] + len(line) + 1)
        self.mask = [False] * text_length

    def mark(self, start: int, end: int) -> None:
        """Protect one half-open character range."""
        for index in range(max(start, 0), min(end, self._text_length)):
            self.mask[index] = True

    def mark_lines(self, first: int, last: int) -> None:
        """Protect a half-open range of line numbers."""
        end = (
            self._offsets[last]
            if last < len(self._lines)
            else self._text_length
        )
        self.mark(self._offsets[first], end)


def _mask_code_spans(text: str, index: _LineIndex) -> None:
    """Protect backtick runs that enclose a code span."""
    cursor = 0
    while cursor < len(text):
        if index.mask[cursor] or text[cursor] != "`":
            cursor += 1
            continue
        opening_end = _run_end(text, cursor)
        closing_end = _closing_run(text, index.mask, opening_end, opening_end - cursor)
        if closing_end is None:
            # An unmatched run is an ordinary literal; continue after it.
            cursor = opening_end
            continue
        index.mark(cursor, closing_end)
        cursor = closing_end


def _run_end(text: str, start: int) -> int:
    """Return the offset just after a run of backticks."""
    end = start
    while end < len(text) and text[end] == "`":
        end += 1
    return end


def _closing_run(
    text: str, mask: Sequence[bool], position: int, length: int
) -> int | None:
    """Find the end of a backtick run of exactly ``length`` characters."""
    while position < len(text):
        if mask[position] or text[position] != "`":
            position += 1
            continue
        run_end = _run_end(text, position)
        if run_end - position == length:
            return run_end
        position = run_end
    return None


def masked_regions(text: str) -> list[bool]:
    """Mark text that link rewriting must leave byte for byte.

    Parameters
    ----------
    text
        Document to scan.

    Returns
    -------
    list[bool]
        ``True`` where a character is protected.
    """
    lines = text.split("\n")
    index = _LineIndex(lines, len(text))
    for first, last in fence_spans(lines):
        index.mark_lines(first, last)
    for first, last in footnote_spans(lines):
        index.mark_lines(first, last)
    for start, end in comment_spans(text):
        index.mark(start, end)
    _mask_code_spans(text, index)
    return index.mask