"""Tests for composing conversion, formatting, and writing.

The pipeline writes in mapping order and refuses a formatter that does not
reach a fixed point, so a rerun at the same tag reproduces the same bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
import types

import pytest

from vendor_tagged_guides_test_support import make_config


def test_vendor_writes_in_mapping_order_and_is_reproducible(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The same tag, sources, and deterministic formatter produce the same bytes."""
    mappings = (
        ("v0-2-0-migration-guide.md", "zzz-migration.md"),
        ("users-guide.md", "aaa-users.md"),
    )
    config = make_config(vendor, tmp_path, mappings=mappings).config

    def deterministic_format(paths: Sequence[Path]) -> None:
        """Rewrite every file with its own content, changing nothing."""
        for path in paths:
            path.write_bytes(path.read_bytes())

    first = vendor.vendor(config, format_files=deterministic_format)
    first_bytes = {path.name: path.read_bytes() for path in first}
    second = vendor.vendor(config, format_files=deterministic_format)
    second_bytes = {path.name: path.read_bytes() for path in second}

    assert [path.name for path in first] == [
        "zzz-migration.md",
        "aaa-users.md",
    ], first
    assert first_bytes == second_bytes, (first_bytes, second_bytes)


def test_the_configured_line_limits_control_exemptions(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A library caller's limits reach the exemption pass, not the defaults."""
    line = "word " * 10 + "end.\n"
    built = make_config(
        vendor,
        tmp_path,
        sources={"users-guide.md": f"# Title\n\n{line}"},
        mappings=(("users-guide.md", "out.md"),),
    )
    config = replace(built.config, line_length=40)

    written = vendor.vendor(config)

    assert "markdownlint-disable MD013" in written[0].read_text(), written


def drifting_format(paths: Sequence[Path]) -> None:
    """Append one line on every invocation, so no fixed point is reached."""
    for path in paths:
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\nformatter noise\n")


def test_a_failed_formatting_run_restores_previous_outputs(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A rejected run leaves existing files untouched and new files absent."""
    built = make_config(vendor, tmp_path)
    kept = built.consumer / "cuprum-users-guide.md"
    absent = built.consumer / "cuprum-v0-2-0-migration-guide.md"
    kept.write_text("previous contents\n", encoding="utf-8", newline="\n")

    with pytest.raises(vendor.VendorError, match="did not reach a fixed point"):
        vendor.vendor(built.config, format_files=drifting_format)

    assert kept.read_text() == "previous contents\n", kept
    assert not absent.exists(), absent
