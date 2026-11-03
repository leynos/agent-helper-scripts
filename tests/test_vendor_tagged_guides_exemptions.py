"""Tests for bounded MD013 exemptions.

The consumer's Markdown gate enforces a prose line length. A vendored paragraph
cannot be reflowed, so the smallest enclosing block is wrapped in one
disable/enable pair. Tables and headings are exempt in the shared
configuration; fenced code has a larger limit, but a long comment line inside a
fence still needs the pair.
"""

from __future__ import annotations

import types

from hypothesis import given, settings
from hypothesis import strategies as st


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
