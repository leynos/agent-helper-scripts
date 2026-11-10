"""Tests for bounded MD013 exemptions.

The consumer's Markdown gate enforces a prose line length. A vendored paragraph
cannot be reflowed, so the smallest enclosing block is wrapped in one
disable/enable pair. Tables and headings are exempt in the shared
configuration; fenced code has a larger limit, but a long comment line inside a
fence still needs the pair.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import types

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest


def test_a_long_paragraph_is_bracketed_for_the_consumer_gate(
    vendor: types.ModuleType,
) -> None:
    """The smallest enclosing paragraph receives one disable/enable pair."""
    paragraph = (
        "A paragraph whose first line carries a great many words and keeps "
        "going past the limit.\nIt continues on a second line."
    )
    document = f"# Title\n\n{paragraph}\n\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(document), "the fixture must exceed the line limit"
    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        f"{paragraph}\n\n"
        "<!-- markdownlint-enable MD013 -->"
    ) in converted, converted


def test_a_whole_list_is_bracketed_rather_than_one_item(
    vendor: types.ModuleType,
) -> None:
    """A long list item must not split the list into separately judged items."""
    listing = (
        "- A first item with a great many words that runs well past the "
        "eighty column limit and keeps going for another few words.\n"
        "- A second, short item.\n"
    )
    document = f"# Title\n\n{listing}\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    disabled = converted.index("<!-- markdownlint-disable MD013 -->")
    enabled = converted.index("<!-- markdownlint-enable MD013 -->")
    assert converted.index("- A first item") > disabled, converted
    assert converted.index("- A second, short item.") < enabled, converted


def test_a_blockquote_is_bracketed_as_a_whole(
    vendor: types.ModuleType,
) -> None:
    """A long line inside a blockquote exempts the quote, not its neighbours."""
    document = (
        "# Title\n\n"
        "> A quoted sentence with a great many words that runs past the "
        "eighty column limit and keeps going.\n"
        "> A second quoted line.\n\n"
        "After.\n"
    )

    converted = vendor.insert_exemptions(document)

    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        "> A quoted sentence"
    ) in converted, converted
    assert converted.index("> A second quoted line.") < converted.index(
        "<!-- markdownlint-enable MD013 -->"
    ), converted


def test_a_footnote_definition_is_bracketed_as_a_whole(
    vendor: types.ModuleType,
) -> None:
    """A continuation must stay inside the pair, or it renders as code."""
    document = (
        "# Title\n\n"
        "[^1]: A footnote paragraph whose first line carries a great many "
        "words and keeps going past the eighty column limit.\n\n"
        "    A short continuation paragraph.\n\n"
        "After.\n"
    )

    converted = vendor.insert_exemptions(document)

    disabled = converted.index("<!-- markdownlint-disable MD013 -->")
    enabled = converted.index("<!-- markdownlint-enable MD013 -->")
    assert converted.index("[^1]: A footnote paragraph") > disabled, converted
    assert converted.index("    A short continuation paragraph.") < enabled, (
        converted
    )


def test_tables_headings_and_short_code_are_left_alone(
    vendor: types.ModuleType,
) -> None:
    """The shared configuration exempts tables and headings; code has 120."""
    document = (
        "# A heading whose text is comfortably longer than eighty characters "
        "but is exempt\n\n"
        "| Column one | Column two |\n"
        "| --- | --- |\n"
        "| A table cell whose row is deliberately long enough to exceed the "
        "prose limit | Value |\n\n"
        "```text\n" + "x" * 110 + "\n```\n"
    )

    converted = vendor.insert_exemptions(document)

    assert "markdownlint" not in converted, converted
    assert vendor.long_lines(document) == (), vendor.long_lines(document)


def test_a_long_setext_heading_is_not_split_from_its_underline(
    vendor: types.ModuleType,
) -> None:
    """A heading is exempt, and bracketing it would break the heading pair."""
    heading = ("word " * 17 + "end").rstrip() + "   "
    document = f"# Title\n\n{heading}\n---\n\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(document) == (), vendor.long_lines(document)
    assert "markdownlint" not in converted, converted
    assert f"{heading}\n---" in converted, converted


def test_a_long_comment_inside_a_fence_is_bracketed(
    vendor: types.ModuleType,
) -> None:
    """A ``#`` line inside code is not a heading and must still be exempt."""
    comment = "# " + "word " * 30
    document = f"# Title\n\n```text\n{comment}\n```\n\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(document) == (3,), vendor.long_lines(document)
    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        f"```text\n{comment}\n```\n\n"
        "<!-- markdownlint-enable MD013 -->"
    ) in converted, converted


def test_a_directive_inside_a_fence_does_not_exempt_later_prose(
    vendor: types.ModuleType,
) -> None:
    """A fenced example of a disable directive is not an instruction."""
    paragraph = (
        "A paragraph whose first line carries a great many words and keeps "
        "going past the limit.\nIt continues on a second line."
    )
    document = (
        "# Title\n\n"
        "```markdown\n"
        "<!-- markdownlint-disable MD013 -->\n"
        "```\n\n"
        f"{paragraph}\n"
    )

    converted = vendor.insert_exemptions(document)

    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        f"{paragraph}\n\n"
        "<!-- markdownlint-enable MD013 -->"
    ) in converted, converted


def test_exemption_insertion_is_idempotent(vendor: types.ModuleType) -> None:
    """A second pass sees the first pass's bounded exemptions and adds none."""
    document = (
        "# Title\n\nA paragraph with enough words to exceed the configured "
        "prose line limit by a comfortable margin and keep going.\n"
    )

    once = vendor.insert_exemptions(document)
    twice = vendor.insert_exemptions(once)

    assert once == twice, twice


@given(document=st.text(max_size=200))
@settings(max_examples=30, deadline=None)
def test_exemption_insertion_is_idempotent_for_generated_documents(
    vendor: types.ModuleType, document: str
) -> None:
    """Any input reaches a fixed point after one exemption pass."""
    once = vendor.insert_exemptions(document)

    assert vendor.insert_exemptions(once) == once, once


@given(document=st.text(alphabet="ab #-*>|`~\n", max_size=200))
@settings(max_examples=30, deadline=None)
def test_exemption_insertion_is_idempotent_with_small_limits(
    vendor: types.ModuleType, document: str
) -> None:
    """Small limits and block syntax reach the bracketing path."""
    limits = {"line_length": 8, "code_line_length": 12}
    once = vendor.insert_exemptions(document, **limits)

    assert vendor.insert_exemptions(once, **limits) == once, once


_LONG_PARAGRAPH = (
    "A paragraph with a great many words that runs well past the configured "
    "prose limit and keeps going to the end."
)

_LONG_LIST_ITEM = (
    "- a list item with a great many words that runs well past the limit and "
    "keeps going"
)
_LONG_QUOTE = (
    "> a blockquote with a great many words that runs well past the limit "
    "and keeps going"
)
_LONG_COMMENT = (
    "<!-- a comment with a great many words that runs well past the limit "
    "and keeps going -->"
)
_TABLE = "| a | b |\n| --- | --- |\n| c | d |"

#: Non-strict MD013 measures this fenced line as 101 columns: it collapses the
#: final word to one character and counts the trailing space.
_CODE_LINE = "code " * 20
_CODE_BLOCK = f"```text\n{_CODE_LINE}\n\n{_CODE_LINE}\n```"

_BLOCKS = (
    "# Title",
    "A short paragraph.",
    _LONG_PARAGRAPH,
    _LONG_LIST_ITEM,
    _LONG_QUOTE,
    _CODE_BLOCK,
    _TABLE,
    _LONG_COMMENT,
)

#: Whether each block must be bracketed, given the drawn limits.
#:
#: This is a handwritten oracle. It deliberately does not call
#: ``long_lines``, so a misclassification shared by detection and insertion
#: cannot make the property pass.
_EXPECTATIONS: dict[str, Callable[[dict[str, int]], bool]] = {
    "# Title": lambda _limits: False,
    "A short paragraph.": lambda _limits: False,
    _LONG_PARAGRAPH: lambda _limits: True,
    _LONG_LIST_ITEM: lambda _limits: True,
    _LONG_QUOTE: lambda _limits: True,
    _CODE_BLOCK: lambda limits: limits["code_line_length"] < 101,
    _TABLE: lambda _limits: False,
    _LONG_COMMENT: lambda _limits: True,
}

#: First lines of blocks the limits leave alone, so no pair may wrap them.
_SHORT_LINES = frozenset({"# Title", "A short paragraph."})


@st.composite
def _block_documents(draw: st.DrawFn) -> list[str]:
    """Draw a document as a list of whole Markdown blocks."""
    return draw(st.lists(st.sampled_from(_BLOCKS), min_size=1, max_size=5))


@st.composite
def _limits(draw: st.DrawFn) -> dict[str, int]:
    """Draw prose and code limits that classify the blocks differently."""
    return {
        "line_length": draw(st.sampled_from((30, 40, 60))),
        "code_line_length": draw(st.sampled_from((40, 60, 120))),
    }


def _content_indexes(vendor: types.ModuleType, text: str) -> list[int]:
    """Return the line numbers of content, without blank or directive lines."""
    directives = {vendor.DISABLE_MD013, vendor.ENABLE_MD013}
    return [
        index
        for index, line in enumerate(text.splitlines())
        if line.strip() and line not in directives
    ]


def _reconstruct(
    vendor: types.ModuleType, lines: Sequence[str]
) -> list[str]:
    """Rebuild the source lines from converted lines, removing pair padding."""
    directives = {vendor.DISABLE_MD013, vendor.ENABLE_MD013}
    starts = dict(_regions(vendor, lines))
    rebuilt: list[str] = []
    index = 0
    while index < len(lines):
        if index in starts:
            end = starts[index]
            inner = lines[index + 1 : end]
            assert inner[:1] == [""] and inner[-1:] == [""], lines
            rebuilt.extend(inner[1:-1])
            index = end + 1
            continue
        assert lines[index] not in directives, lines
        rebuilt.append(lines[index])
        index += 1
    return rebuilt


def _assert_structure_preserved(
    vendor: types.ModuleType, document: str, converted: str
) -> None:
    """Assert that only directive pairs and their blank padding were added."""
    rebuilt = _reconstruct(vendor, converted.splitlines())
    assert rebuilt == document.splitlines(), converted


def _is_list_item(block: str) -> bool:
    """Say whether a block is a list item, which merges with a neighbour."""
    return block.lstrip().startswith(("- ", "* ", "+ "))


def _groups(blocks: Sequence[str]) -> list[list[str]]:
    """Group blocks the way Markdown merges them: adjacent list items join."""
    groups: list[list[str]] = []
    for block in blocks:
        if groups and _is_list_item(block) and _is_list_item(groups[-1][-1]):
            groups[-1].append(block)
        else:
            groups.append([block])
    return groups


def _regions(
    vendor: types.ModuleType, lines: Sequence[str]
) -> list[tuple[int, int]]:
    """Return the line range between each disable directive and its enable.

    The directives must be balanced and ordered: a disable that is still open
    when another disable or the end of the document arrives, and an enable
    without a disable, both fail the assertions.
    """
    regions: list[tuple[int, int]] = []
    start: int | None = None
    for index, line in enumerate(lines):
        if line == vendor.DISABLE_MD013:
            assert start is None, f"nested disable at line {index}: {lines}"
            start = index
        elif line == vendor.ENABLE_MD013:
            assert start is not None, (
                f"unmatched enable at line {index}: {lines}"
            )
            regions.append((start, index))
            start = None
    assert start is None, f"unmatched disable at line {start}: {lines}"
    return regions


def _assert_pairs_match_groups(
    groups: Sequence[Sequence[int]], regions: Sequence[tuple[int, int]]
) -> None:
    """Assert one pair per offending block group and no pair splitting one."""
    for group in groups:
        enclosing = [
            (start, end)
            for start, end in regions
            if start < min(group) and max(group) < end
        ]
        assert len(enclosing) == 1, (group, enclosing, regions)
        start, end = enclosing[0]
        assert all(start < index < end for index in group), (group, regions)
        assert not any(
            min(group) < boundary < max(group)
            for other in regions
            for boundary in other
        ), (group, regions)
    for start, end in regions:
        inside = [
            group
            for group in groups
            if any(start < index < end for index in group)
        ]
        assert len(inside) == 1, (start, end, inside, regions)


def test_the_pair_invariant_rejects_merged_and_split_pairs(
    vendor: types.ModuleType,
) -> None:
    """One pair may not merge two groups, and pairs may not split one block."""
    disable = vendor.DISABLE_MD013
    enable = vendor.ENABLE_MD013
    merged = [
        disable,
        "",
        "one",
        "",
        "two",
        "",
        enable,
        "",
        disable,
        "",
        "three",
        "",
        enable,
    ]
    split = [
        disable,
        "",
        "```text",
        "",
        enable,
        "",
        disable,
        "",
        "code",
        "",
        "```",
        "",
        enable,
    ]

    with pytest.raises(AssertionError):
        _assert_pairs_match_groups(
            [[2], [4], [10]], _regions(vendor, merged)
        )
    with pytest.raises(AssertionError):
        _assert_pairs_match_groups(
            [[2, 8, 10]], _regions(vendor, split)
        )


def test_the_structure_check_rejects_a_removed_paragraph_separator(
    vendor: types.ModuleType,
) -> None:
    """Removing the blank line between two paragraphs merges their blocks."""
    with pytest.raises(AssertionError):
        _assert_structure_preserved(vendor, "one\n\ntwo\n", "one\ntwo\n")


def test_a_blank_line_inside_a_fenced_block_survives_the_pass(
    vendor: types.ModuleType,
) -> None:
    """The blank padding around a pair is not the block's own blank line."""
    document = f"# Title\n\n{_CODE_BLOCK}\n"
    converted = vendor.insert_exemptions(
        document, line_length=40, code_line_length=60
    )

    assert vendor.DISABLE_MD013 in converted, converted
    _assert_structure_preserved(vendor, document, converted)


def test_the_structure_check_rejects_a_pair_that_drops_a_block_line(
    vendor: types.ModuleType,
) -> None:
    """A pair must carry every original block line, blank lines included."""
    document = f"# Title\n\n{_CODE_BLOCK}\n"
    converted = vendor.insert_exemptions(
        document, line_length=40, code_line_length=60
    )
    damaged = converted.replace(f"{_CODE_LINE}\n\n", f"{_CODE_LINE}\n", 1)

    assert damaged != converted, converted
    with pytest.raises(AssertionError):
        _assert_structure_preserved(vendor, document, damaged)


@given(blocks=_block_documents(), limits=_limits())
@settings(max_examples=60, deadline=None)
def test_each_long_block_is_bracketed_and_the_other_lines_survive(
    vendor: types.ModuleType, blocks: list[str], limits: dict[str, int]
) -> None:
    """Every over-long block gets one bounded pair; nothing else changes."""
    document = "\n\n".join(blocks) + "\n"
    converted = vendor.insert_exemptions(document, **limits)
    lines = converted.splitlines()
    regions = _regions(vendor, lines)
    covered = {
        index for start, end in regions for index in range(start + 1, end)
    }

    _assert_structure_preserved(vendor, document, converted)
    assert vendor.insert_exemptions(converted, **limits) == converted, converted

    mapping = dict(
        zip(
            _content_indexes(vendor, document),
            _content_indexes(vendor, converted),
            strict=True,
        )
    )
    offending = 0
    offending_groups: list[list[int]] = []
    start = 0
    for group in _groups(blocks):
        text = "\n\n".join(group)
        end = start + len(text.splitlines()) - 1
        converted_indexes = [
            mapping[index] for index in range(start, end + 1) if index in mapping
        ]
        expected = any(_EXPECTATIONS[block](limits) for block in group)
        if expected:
            offending += 1
            offending_groups.append(converted_indexes)
            assert converted_indexes, (group, converted)
            assert all(index in covered for index in converted_indexes), (
                group,
                converted,
            )
        else:
            assert not any(index in covered for index in converted_indexes), (
                group,
                converted,
            )
        start = end + 2

    assert len(regions) == offending, (regions, offending, converted)
    _assert_pairs_match_groups(offending_groups, regions)

    for start, end in regions:
        inside = lines[start + 1 : end]
        assert any(line.strip() for line in inside), converted
        swallowed = sorted(_SHORT_LINES.intersection(inside))
        assert swallowed == [], (swallowed, converted)


def test_a_hard_break_after_the_final_allowed_column_is_detected(
    vendor: types.ModuleType,
) -> None:
    """MD013 measures a break that lands just past the limit, so bracket it."""
    paragraph = "x" * 79 + " y"
    document = f"# Title\n\n{paragraph}\n"

    assert vendor.long_lines(document) == (2,), vendor.long_lines(document)

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(converted) == (), converted
    assert "<!-- markdownlint-disable MD013 -->" in converted, converted


def test_trailing_whitespace_counts_but_an_unbreakable_word_stays_exempt(
    vendor: types.ModuleType,
) -> None:
    """Non-strict MD013 exempts only a last word that crosses the limit."""
    trailing = "word " * 16 + "end" + "   "
    unbreakable = "x" * 200
    at_limit = "w" * 76 + " end"
    document = f"# Title\n\n{trailing}\n\n{unbreakable}\n\n{at_limit}\n"

    assert len(at_limit) == 80, len(at_limit)
    assert vendor.long_lines(document) == (2,), vendor.long_lines(document)

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(converted) == (), converted
