"""Tests for text the conversion must leave byte for byte.

Fenced code, inline code, footnote definitions, and HTML comments are all
protected. The cases that matter most are the ones where two constructs meet:
an unmatched opener in one must not consume text belonging to the other.
"""

from __future__ import annotations

from pathlib import Path
import types

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from vendor_tagged_guides_test_support import convert_fragment, pinned


@pytest.mark.parametrize(
    "markdown",
    [
        "```markdown\n[guide](other.md)\n```",
        "~~~\n[guide](other.md)\n~~~",
        "Inline `[guide](other.md)` stays code.",
        "A sentence with a footnote.[^1]\n\n[^1]: [guide](other.md)",
        "<!-- [guide](other.md) -->",
    ],
)
def test_protected_text_is_left_byte_for_byte(
    vendor: types.ModuleType,
    tmp_path: Path,
    markdown: str,
) -> None:
    """Fences, inline code, footnotes, and comments carry no rewritten link."""
    converted = convert_fragment(vendor, tmp_path, markdown)

    assert markdown in converted, converted


def test_an_unmatched_comment_opener_in_a_fence_does_not_mask_a_later_link(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A fence's literal ``<!--`` cannot pair with a genuine comment's close."""
    markdown = (
        "```markdown\n"
        "<!-- not a comment\n"
        "```\n\n"
        "[guide](other.md)\n\n"
        "<!-- a real comment with [hidden](hidden.md) -->\n"
    )

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert f"[guide]({pinned('docs/other.md')})" in converted, converted
    assert "[hidden](hidden.md)" in converted, converted


def test_a_comment_opener_in_inline_code_does_not_mask_a_later_link(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """An inline code span is consumed before its literal ``<!--`` is seen."""
    markdown = (
        "Inline `<!-- not a comment` then text, a [guide](other.md), "
        "and a literal --> marker.\n"
    )

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert "`<!-- not a comment`" in converted, converted
    assert f"[guide]({pinned('docs/other.md')})" in converted, converted


def test_a_backtick_inside_a_genuine_comment_does_not_start_a_code_span(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The comment is consumed first, so its backtick stays literal."""
    markdown = (
        "<!-- a comment with a ` backtick --> then a [guide](other.md) "
        "and a later ` marker.\n"
    )

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert "<!-- a comment with a ` backtick -->" in converted, converted
    assert f"[guide]({pinned('docs/other.md')})" in converted, converted


def test_an_unmatched_backtick_does_not_mask_a_later_paragraph(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A code span cannot cross a blank line, so the later link stays live."""
    markdown = (
        "The lone ` key in one paragraph.\n\n"
        "[guide](other.md) then another ` marker.\n"
    )

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert f"[guide]({pinned('docs/other.md')})" in converted, converted


FENCE_BODY = st.text(
    alphabet=st.characters(exclude_characters="`\r"),
    max_size=60,
)


@given(body=FENCE_BODY)
@settings(max_examples=30, deadline=None)
def test_fenced_code_is_preserved_under_generated_content(
    vendor: types.ModuleType, body: str
) -> None:
    """No generated fence body has a byte rewritten by link conversion."""
    config = vendor.VendorConfig(
        tag="v1.0.0",
        repository="owner/project",
        source_directory=Path("/unused"),
        output_directory=Path("/unused"),
        mappings=(("users-guide.md", "out.md"),),
    )
    document = f"# Title\n\n```text\n{body}\n```\n"

    converted = vendor.convert(document, config, "users-guide.md")

    assert f"```text\n{body}\n```" in converted, converted
