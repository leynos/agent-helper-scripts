"""Tests for rewriting relative destinations at a pinned tag.

Each case pins one part of the contract: the label, title, angle delimiter,
fragment, and query survive unchanged, while only the destination moves.
"""

from __future__ import annotations

from pathlib import Path
import types

import pytest

from vendor_tagged_guides_test_support import (
    convert_fragment,
    make_config,
    pinned,
)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("[guide](other.md)", f"[guide]({pinned('docs/other.md')})"),
        (
            "[guide](other.md#part)",
            f"[guide]({pinned('docs/other.md')}#part)",
        ),
        (
            '[guide](./other.md "Title")',
            f'[guide]({pinned("docs/other.md")} "Title")',
        ),
        (
            "[guide](<other file.md>)",
            f"[guide](<{pinned('docs/other file.md')}>)",
        ),
        (
            "![diagram](images/diagram.png)",
            (
                "![diagram](https://raw.githubusercontent.com/leynos/cuprum/"
                "v0.2.0-beta2/docs/images/diagram.png)"
            ),
        ),
        (
            "![diagram](<images/one two.png>)",
            (
                "![diagram](<https://raw.githubusercontent.com/leynos/cuprum/"
                "v0.2.0-beta2/docs/images/one two.png>)"
            ),
        ),
        ("[root](/README.md)", f"[root]({pinned('README.md')})"),
        (
            "[directory](adr/)",
            (
                "[directory](https://github.com/leynos/cuprum/tree/"
                "v0.2.0-beta2/docs/adr)"
            ),
        ),
        ("[parent](../README.md)", f"[parent]({pinned('README.md')})"),
        (
            "[migration](v0-2-0-migration-guide.md#moving)",
            "[migration](cuprum-v0-2-0-migration-guide.md#moving)",
        ),
        ("[anchor](#program-catalogue)", "[anchor](#program-catalogue)"),
        (
            "[optional] (default)",
            "[optional] (default)",
        ),
        ("[web](https://example.com/x)", "[web](https://example.com/x)"),
        ("[mail](mailto:dev@example.org)", "[mail](mailto:dev@example.org)"),
        ("[cdn](//cdn.example.org/x)", "[cdn](//cdn.example.org/x)"),
        (
            "prefix[adjacent](other.md)",
            f"prefix[adjacent]({pinned('docs/other.md')})",
        ),
        (
            "[`code`](other.md)",
            f"[`code`]({pinned('docs/other.md')})",
        ),
        (
            "[![alt](images/a.png)](other.md)",
            (
                "[![alt](https://raw.githubusercontent.com/leynos/cuprum/"
                f"v0.2.0-beta2/docs/images/a.png)]({pinned('docs/other.md')})"
            ),
        ),
        (
            "[outer [inner](other.md)]",
            f"[outer [inner]({pinned('docs/other.md')})]",
        ),
    ],
)
def test_inline_link_forms_are_rewritten_without_touching_the_label(
    vendor: types.ModuleType,
    tmp_path: Path,
    markdown: str,
    expected: str,
) -> None:
    """Each inline form keeps its label, delimiter, title, and fragment."""
    converted = convert_fragment(vendor, tmp_path, markdown)

    assert expected in converted, converted


def test_a_query_string_survives_the_rewrite(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A trailing query is carried after the pinned path, not dropped."""
    converted = convert_fragment(vendor, tmp_path, "[view](other.md?plain=1)")

    assert f"[view]({pinned('docs/other.md')}?plain=1)" in converted, converted


def test_links_resolve_against_a_nested_source_directory(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A source in a subdirectory resolves siblings and parent paths correctly."""
    mappings = (
        ("guides/users-guide.md", "cuprum-users-guide.md"),
        ("guides/v0-2-0-migration-guide.md", "cuprum-migration-guide.md"),
    )
    config = make_config(
        vendor,
        tmp_path,
        sources={
            "guides/users-guide.md": "# Users' guide\n",
            "guides/v0-2-0-migration-guide.md": "# Migration guide\n",
        },
        mappings=mappings,
    ).config
    source = (
        "# Users' guide\n\n"
        "See the [sibling](v0-2-0-migration-guide.md#moving), the "
        "[repository guide](../README.md), [another](other.md), and "
        "![diagram](images/architecture.png).\n"
    )

    converted = vendor.convert(source, config, "guides/users-guide.md")

    assert (
        "[sibling](cuprum-migration-guide.md#moving)" in converted
    ), converted
    assert f"[repository guide]({pinned('docs/README.md')})" in converted, converted
    assert f"[another]({pinned('docs/guides/other.md')})" in converted, converted
    assert (
        "![diagram](https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/guides/images/architecture.png)" in converted
    ), converted


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        (
            '[ref]: other.md "A title"',
            f'[ref]: {pinned("docs/other.md")} "A title"',
        ),
        (
            "[ref]: <other.md>",
            f"[ref]: <{pinned('docs/other.md')}>",
        ),
        (
            '[ref]:\n    other.md "A title"',
            f'[ref]:\n    {pinned("docs/other.md")} "A title"',
        ),
        (
            "[ref]:\n    <other.md>",
            f"[ref]:\n    <{pinned('docs/other.md')}>",
        ),
    ],
)
def test_link_reference_definitions_are_rewritten(
    vendor: types.ModuleType,
    tmp_path: Path,
    definition: str,
    expected: str,
) -> None:
    """Definitions keep their label, angle delimiter, and title."""
    converted = convert_fragment(vendor, tmp_path, definition)

    assert expected in converted, converted


@pytest.mark.parametrize(
    ("usage", "definition"),
    [
        ("![diagram][img]", "[img]: images/diagram.png"),
        ("![diagram][]", "[diagram]: images/diagram.png"),
        ("![diagram]", "[diagram]: images/diagram.png"),
        ("![Diagram  Label][]", "[diagram label]: images/diagram.png"),
    ],
)
def test_a_definition_used_by_an_image_becomes_a_raw_source(
    vendor: types.ModuleType,
    tmp_path: Path,
    usage: str,
    definition: str,
) -> None:
    """Full, collapsed, and shortcut image references all name the definition."""
    converted = convert_fragment(vendor, tmp_path, f"{usage}\n\n{definition}\n")

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/diagram.png" in converted
    ), converted


def test_an_unterminated_inline_image_falls_back_to_its_shortcut_reference(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """CommonMark reads ``![diagram](unterminated`` as the shortcut ``![diagram]``."""
    markdown = "![diagram](unterminated\n\n[diagram]: images/diagram.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/diagram.png" in converted
    ), converted


def test_an_inline_image_with_an_empty_destination_names_no_definition(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """``![diagram]()`` is an inline image, so the definition keeps a blob URL."""
    markdown = "![diagram]()\n\n[diagram]: images/diagram.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert "github.com/leynos/cuprum/blob/" in converted, converted
    assert "raw.githubusercontent.com" not in converted, converted


def test_a_definition_label_with_an_escaped_bracket_is_rewritten(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """An escaped ``]`` is part of the label, so its definition still moves."""
    markdown = "![a\\]b]\n\n[a\\]b]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted
    assert "]: images/a.png" not in converted, converted


def test_an_invalid_nested_reference_label_falls_back_to_the_shortcut(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A label containing an unescaped ``[`` is invalid, so ``![alt]`` is used."""
    markdown = "![alt][outer[inner]]\n\n[alt]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_a_whitespace_only_second_bracket_uses_the_shortcut_label(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A label needs one non-space character, so ``![a][ ]`` is ``![a]``."""
    markdown = "![diagram][ ]\n\n[diagram]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_an_escaped_image_marker_names_a_link_definition(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """``\\![alt]`` is a literal ``!`` and a shortcut link, not an image."""
    markdown = "\\![guide]\n\n[guide]: other.md\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert f"[guide]: {pinned('docs/other.md')}" in converted, converted
    assert "raw.githubusercontent.com" not in converted, converted


def test_an_image_inside_a_link_is_rewritten_on_its_own(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The inner image and the outer link each keep their own destination."""
    markdown = "[![diagram](images/a.png)](other.md)\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "![diagram](https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png)" in converted
    ), converted
    assert f"]({pinned('docs/other.md')})" in converted, converted


@pytest.mark.parametrize(
    "usage",
    ["`![diagram]`", "```text\n![diagram]\n```"],
    ids=["inline-code", "fenced-code"],
)
def test_an_image_reference_inside_protected_text_names_no_definition(
    vendor: types.ModuleType, tmp_path: Path, usage: str
) -> None:
    """Image syntax that renders as code does not make a definition an image."""
    markdown = f"{usage}\n\n[diagram]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert "github.com/leynos/cuprum/blob/" in converted, converted
    assert "raw.githubusercontent.com" not in converted, converted


def test_a_reference_label_across_a_blank_line_uses_the_shortcut_label(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A label cannot contain a blank line, so the shortcut form applies."""
    markdown = "![alt][a\n\nb]\n\n[alt]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_an_overlong_reference_label_uses_the_shortcut_label(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A link label holds at most 999 characters, so a longer one is ignored."""
    label = "x" * 1000
    markdown = f"![alt][{label}]\n\n[alt]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_reference_labels_match_across_case_folding(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """CommonMark matches labels case-insensitively; U+1E9E folds to ``ss``."""
    markdown = "![ẞ][]\n\n[ss]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_an_escaped_label_does_not_match_its_unescaped_form(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Label matching uses the raw text, so ``foo\\!`` differs from ``foo!``."""
    markdown = "![foo\\!]\n\n[foo!]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert "github.com/leynos/cuprum/blob/" in converted, converted
    assert "raw.githubusercontent.com" not in converted, converted


def test_an_escaped_label_matches_the_same_escaped_definition(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Both sides keep the escape, so ``foo\\!`` matches a ``foo\\!`` label."""
    markdown = "![foo\\!]\n\n[foo\\!]: images/a.png\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/a.png" in converted
    ), converted


def test_a_definition_shared_by_a_link_and_an_image_renders_as_an_image(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A blob URL would break the image, while raw still works as a link."""
    markdown = (
        "![diagram][shared]\n\n"
        "[the same file][shared]\n\n"
        "[shared]: images/diagram.png\n"
    )

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert (
        "https://raw.githubusercontent.com/leynos/cuprum/"
        "v0.2.0-beta2/docs/images/diagram.png" in converted
    ), converted
    assert "github.com/leynos/cuprum/blob/" not in converted, converted


def test_a_definition_used_only_by_links_stays_a_blob_url(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A link to a file is not an image, so it keeps the rendered view."""
    markdown = "[guide][ref]\n\n[ref]: other.md\n"

    converted = convert_fragment(vendor, tmp_path, markdown)

    assert f"[ref]: {pinned('docs/other.md')}" in converted, converted


def test_a_link_escaping_the_repository_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A relative link cannot resolve above the upstream repository root."""
    with pytest.raises(vendor.VendorError, match="escapes the upstream repository"):
        convert_fragment(vendor, tmp_path, "[outside](../../elsewhere.md)")
