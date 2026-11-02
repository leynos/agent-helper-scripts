"""Tests for composing conversion, formatting, and writing.

The pipeline writes in mapping order and refuses a formatter that does not
reach a fixed point, so a rerun at the same tag reproduces the same bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
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


def test_a_formatter_that_does_not_reach_a_fixed_point_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A formatter that changes its own output on every pass fails loudly."""
    config = make_config(vendor, tmp_path).config

    def drifting_format(paths: Sequence[Path]) -> None:
        """Append one line on every invocation."""
        for path in paths:
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\nformatter noise\n")

    with pytest.raises(vendor.VendorError, match="did not reach a fixed point"):
        vendor.vendor(config, format_files=drifting_format)
