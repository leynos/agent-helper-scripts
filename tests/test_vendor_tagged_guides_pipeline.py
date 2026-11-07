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


def test_an_output_that_would_overwrite_a_source_is_refused_before_writing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """``vendor`` itself refuses the overwrite, so no byte of the source moves."""
    built = make_config(vendor, tmp_path)
    source = built.config.source_directory / "users-guide.md"
    original = source.read_bytes()
    config = replace(
        built.config,
        output_directory=built.config.source_directory,
        mappings=(("users-guide.md", "users-guide.md"),),
    )

    with pytest.raises(
        vendor.VendorError, match="output would overwrite a source file"
    ):
        vendor.vendor(config)

    assert source.read_bytes() == original, source
    assert list(built.consumer.iterdir()) == [], list(built.consumer.iterdir())


def test_an_invalid_second_mapping_leaves_the_first_source_and_output_untouched(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Every mapping is checked before the first conversion or write."""
    built = make_config(vendor, tmp_path)
    source = built.config.source_directory / "users-guide.md"
    original = source.read_bytes()
    config = replace(
        built.config,
        mappings=(
            ("users-guide.md", "first-output.md"),
            ("missing.md", "second-output.md"),
        ),
    )

    with pytest.raises(vendor.VendorError, match="source file does not exist"):
        vendor.vendor(config)

    assert source.read_bytes() == original, source
    assert list(built.consumer.iterdir()) == [], list(built.consumer.iterdir())


def test_an_undecodable_source_is_reported_as_a_vendor_error(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A non-UTF-8 source is a one-line diagnostic, not a traceback."""
    built = make_config(vendor, tmp_path)
    source = built.config.source_directory / "users-guide.md"
    source.write_bytes(b"\xff\xfe# Not UTF-8\n")

    with pytest.raises(vendor.VendorError, match="cannot decode"):
        vendor.vendor(built.config)

    assert list(built.consumer.iterdir()) == [], list(built.consumer.iterdir())


def test_a_write_failure_is_reported_as_a_vendor_error(
    vendor: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only output directory is a one-line diagnostic, not a traceback."""
    built = make_config(vendor, tmp_path)

    def failing_write_text(
        self: Path, *_args: object, **_kwargs: object
    ) -> int:
        """Fail every text write as a read-only filesystem would."""
        raise OSError("read-only file system")

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(vendor.VendorError, match="cannot write"):
        vendor.vendor(built.config)


def test_a_failed_restore_is_reported_and_the_remaining_outputs_are_restored(
    vendor: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One failed restore must not strand the other outputs in converted state."""
    built = make_config(vendor, tmp_path)
    first = built.consumer / "cuprum-users-guide.md"
    second = built.consumer / "cuprum-v0-2-0-migration-guide.md"
    first.write_text("first previous\n", encoding="utf-8", newline="\n")
    second.write_text("second previous\n", encoding="utf-8", newline="\n")
    original_write_bytes = Path.write_bytes

    def failing_write_bytes(self: Path, data: bytes) -> int:
        """Fail the restore of the first output as a full disk would."""
        if self == first:
            raise OSError("disk full")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(vendor.VendorError) as raised:
        vendor.vendor(built.config, format_files=drifting_format)

    message = str(raised.value)
    assert "could not restore previous output" in message, message
    assert str(first) in message, message
    assert "original failure: VendorError" in message, message
    assert second.read_text() == "second previous\n", second


def test_a_later_mapping_without_a_heading_writes_nothing(
    vendor: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every source is converted before the first output is written."""
    built = make_config(
        vendor,
        tmp_path,
        sources={
            "users-guide.md": "# Users\n\nText.\n",
            "v0-2-0-migration-guide.md": "Text without a heading.\n",
        },
        mappings=(
            ("users-guide.md", "aaa-users.md"),
            ("v0-2-0-migration-guide.md", "zzz-migration.md"),
        ),
    )
    first = built.config.output_directory / "aaa-users.md"
    first.write_text("previous\n", encoding="utf-8")
    second = built.config.output_directory / "zzz-migration.md"
    sources_before = {
        path.name: path.read_bytes()
        for path in built.config.source_directory.iterdir()
    }
    writes: list[Path] = []
    original_write_text = Path.write_text

    def recording_write_text(
        self: Path, *args: object, **kwargs: object
    ) -> int:
        """Record every text write before delegating to the real one."""
        writes.append(self)
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)

    with pytest.raises(vendor.VendorError, match="level-one heading"):
        vendor.vendor(built.config)

    assert writes == [], writes

    assert first.read_text(encoding="utf-8") == "previous\n"
    assert not second.exists()
    assert {
        path.name: path.read_bytes()
        for path in built.config.source_directory.iterdir()
    } == sources_before
