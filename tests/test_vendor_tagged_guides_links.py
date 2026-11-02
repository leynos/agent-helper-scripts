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
            "![diagram](https://raw.githubusercontent.com/leynos/cuprum/"
            "v0.2.0-beta2/docs/images/diagram.png)",
        ),
        (
            "![diagram](<images/one two.png>)",
            "![diagram](<https://raw.githubusercontent.com/leynos/cuprum/"
            "v0.2.0-beta2/docs/images/one two.png>)",
        ),
        ("[root](/README.md)", f"[root]({pinned('README.md')})"),
        (
            "[directory](adr/)",
            "[directory](https://github.com/leynos/cuprum/tree/"
            "v0.2.0-beta2/docs/adr)",
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
            "[![alt](https://raw.githubusercontent.com/leynos/cuprum/"
            f"v0.2.0-beta2/docs/images/a.png)]({pinned('docs/other.md')})",
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


def test_a_link_escaping_the_repository_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A relative link cannot resolve above the upstream repository root."""
    with pytest.raises(vendor.VendorError, match="escapes the upstream repository"):
        convert_fragment(vendor, tmp_path, "[outside](../../elsewhere.md)")
