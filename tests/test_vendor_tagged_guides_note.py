"""Tests for the canonical import note and whole-document conversion.

The note is the vendored file's provenance record. It is inserted once, below
the first level-one heading outside fenced code, and a source that already
carries it is refused so a rerun cannot stack a second copy.
"""

from __future__ import annotations

from pathlib import Path
import types

import pytest

from vendor_tagged_guides_test_support import make_config

SNAPSHOT_SOURCE = """\
# Cuprum users' guide

Cuprum helps Python applications run external programs. See the
[migration guide](v0-2-0-migration-guide.md#migrating-from-0-1) and the
[developers' guide](developers-guide.md).

![Architecture diagram](images/architecture.png)

Inline `[sample](examples/sample.py)` is code, but [the guide](guide.md) is a
link.

```markdown
[fenced](should-not-change.md)
```

[reference]: <reference-target.md> "Reference title"

A sentence with a footnote.[^1]

[^1]: A footnote with [a link](footnote-target.md).
"""


def test_converted_document_matches_the_snapshot(
    vendor: types.ModuleType, tmp_path: Path, snapshot: object
) -> None:
    """The whole conversion, note included, is pinned as one snapshot."""
    config = make_config(
        vendor,
        tmp_path,
        sources={"users-guide.md": SNAPSHOT_SOURCE},
        mappings=(("users-guide.md", "cuprum-users-guide.md"),),
    )

    converted = vendor.convert(
        SNAPSHOT_SOURCE, config.config, "users-guide.md"
    )

    assert converted == snapshot, converted


def test_the_note_is_inserted_once_after_the_first_heading(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The canonical note follows the H1 with one blank line on each side."""
    config = make_config(
        vendor,
        tmp_path,
        sources={"users-guide.md": "# Title\n\n\nBody.\n"},
    )

    converted = vendor.convert(
        "# Title\n\n\nBody.\n", config.config, "users-guide.md"
    )
    note = vendor.NOTE_TEMPLATE.format(
        project="cuprum", tag="v0.2.0-beta2", repository="leynos/cuprum"
    )

    assert converted == f"# Title\n\n{note}\nBody.\n", converted


def test_a_source_carrying_the_note_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A second conversion of an already vendored file would stack notes."""
    config = make_config(vendor, tmp_path)

    with pytest.raises(vendor.VendorError, match="canonical import marker"):
        vendor.convert(
            f"# Title\n\n> {vendor.IMPORT_MARKER}cuprum `v1`.**\n",
            config.config,
            "users-guide.md",
        )


def test_a_marker_inside_a_fence_is_not_a_previous_import(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Only a marker in live Markdown shows that the source was vendored."""
    config = make_config(vendor, tmp_path)
    source = (
        "```markdown\n"
        f"{vendor.IMPORT_MARKER}example `v1`.**\n"
        "```\n\n"
        "# Title\n\n"
        "Body.\n"
    )

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert f"```markdown\n{vendor.IMPORT_MARKER}example" in converted, converted
    assert converted.count("Imported from") == 2, converted


def test_a_source_without_a_heading_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The note has a fixed insertion point, so a heading is required."""
    config = make_config(vendor, tmp_path)

    with pytest.raises(vendor.VendorError, match="level-one heading"):
        vendor.convert("Body without a heading.\n", config.config, "users-guide.md")


@pytest.mark.parametrize(
    ("source", "heading"),
    [
        (
            "<!--\n# Example heading\n-->\n\n# Actual guide\n\nBody.\n",
            "# Actual guide",
        ),
        (
            "`code\n# Not a heading\nmore`\n\n# Actual guide\n\nBody.\n",
            "# Actual guide",
        ),
        ("#\tActual guide\n\nBody.\n", "#\tActual guide"),
    ],
)
def test_a_protected_heading_does_not_receive_the_note(
    vendor: types.ModuleType, tmp_path: Path, source: str, heading: str
) -> None:
    """A heading that renders as nothing is not the insertion point."""
    config = make_config(vendor, tmp_path)

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.count("Imported from") == 1, converted
    assert (
        converted.index(heading)
        < converted.index("Imported from")
        < converted.index("Body.")
    ), converted


def test_a_setext_heading_receives_the_note_after_its_underline(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A Setext H1 ends at its underline, so the note follows both lines."""
    config = make_config(vendor, tmp_path)
    source = "Cuprum users' guide\n====================\n\nBody.\n"

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.startswith(
        "Cuprum users' guide\n====================\n\n> **Imported from "
    ), converted
    assert converted.count("Imported from") == 1, converted


def test_a_setext_heading_inside_a_fence_does_not_receive_the_note(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A protected underline is not a heading, so the live ATX H1 wins."""
    config = make_config(vendor, tmp_path)
    source = "```markdown\nNot a heading\n==============\n```\n\n# Title\n\nBody.\n"

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.index("# Title") < converted.index("Imported from"), converted
    assert converted.count("Imported from") == 1, converted


def test_a_setext_level_two_heading_is_not_the_insertion_point(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Only a level-one heading takes the note, so the ATX H1 is used."""
    config = make_config(vendor, tmp_path)
    source = "Section\n-------\n\n# Title\n\nBody.\n"

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.index("# Title") < converted.index("Imported from"), converted
    assert converted.count("Imported from") == 1, converted


def test_a_heading_inside_a_fence_does_not_receive_the_note(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The first ATX H1 outside fenced code is the insertion point."""
    config = make_config(vendor, tmp_path)
    source = "```markdown\n# Not a heading\n```\n\n# Title\n\nBody.\n"

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.index("```markdown") < converted.index(
        "Imported from"
    ), converted
    assert converted.count("Imported from") == 1, converted
    assert converted.index("Imported from") < converted.index("Body."), converted
