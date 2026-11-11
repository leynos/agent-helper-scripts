"""Tests for refusing an unusable import before any file is written.

Validation is a pure check over the frozen configuration. Each case names one
argument class the front end must reject, and the diagnostic it reports.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
import types

import pytest

from vendor_tagged_guides_test_support import make_config


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"repository": "cuprum"}, "repository must be"),
        ({"repository": "https://github.com/leynos/cuprum"}, "repository must be"),
        ({"tag": ""}, "tag is not a valid"),
        ({"tag": "v1/../main"}, "tag is not a valid"),
        ({"line_length": 0}, "line length must be positive"),
        ({"code_line_length": 0}, "code line length must be positive"),
        ({"source_path": "../docs"}, "source path must stay inside"),
        ({"mappings": ()}, "at least one source/output mapping"),
        ({"mappings": (("missing.md", "out.md"),)}, "source file does not exist"),
        (
            {"mappings": (("users-guide.md", "sub/out.md"),)},
            "output name must be a bare filename",
        ),
        (
            {"mappings": (("users-guide.md", "out.txt"),)},
            "output name must end in '.md'",
        ),
        (
            {
                "mappings": (
                    ("users-guide.md", "one.md"),
                    ("users-guide.md", "two.md"),
                )
            },
            "source is mapped more than once",
        ),
        (
            {
                "mappings": (
                    ("users-guide.md", "same.md"),
                    ("v0-2-0-migration-guide.md", "same.md"),
                )
            },
            "output is mapped more than once",
        ),
    ],
)
def test_arguments_are_validated_before_any_file_is_written(
    vendor: types.ModuleType,
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    """An unusable argument produces a one-line refusal."""
    config = make_config(vendor, tmp_path).config
    candidate = dataclasses.replace(config, **change)

    with pytest.raises(vendor.VendorError, match=message):
        vendor.validate(candidate)


def test_a_missing_source_or_output_directory_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Directories are checked before conversion starts."""
    config = make_config(vendor, tmp_path).config

    with pytest.raises(vendor.VendorError, match="source directory does not exist"):
        vendor.validate(
            dataclasses.replace(config, source_directory=tmp_path / "absent")
        )
    with pytest.raises(vendor.VendorError, match="output directory does not exist"):
        vendor.validate(
            dataclasses.replace(config, output_directory=tmp_path / "absent")
        )


def test_a_source_symlink_that_escapes_the_source_directory_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Following a link would import content that is not at the pinned tag."""
    config = make_config(vendor, tmp_path).config
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n\nText.\n", encoding="utf-8", newline="\n")
    (config.source_directory / "linked.md").symlink_to(outside)
    candidate = dataclasses.replace(
        config, mappings=(("linked.md", "linked-guide.md"),)
    )

    with pytest.raises(
        vendor.VendorError, match="source must stay inside the source directory"
    ):
        vendor.validate(candidate)


@pytest.mark.parametrize("link_output", [False, True])
def test_an_output_that_resolves_to_a_source_is_refused(
    vendor: types.ModuleType, tmp_path: Path, *, link_output: bool
) -> None:
    """The tool must not overwrite an upstream source with its converted copy."""
    config = make_config(vendor, tmp_path).config
    output_directory = config.source_directory
    if link_output:
        output_directory = tmp_path / "linked-output"
        output_directory.symlink_to(config.source_directory, target_is_directory=True)
    candidate = dataclasses.replace(
        config,
        output_directory=output_directory,
        mappings=(("users-guide.md", "users-guide.md"),),
    )

    with pytest.raises(
        vendor.VendorError, match="output would overwrite a source file"
    ):
        vendor.validate(candidate)


def test_an_inaccessible_source_directory_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A permission error while inspecting a path is a VendorError."""
    config = make_config(vendor, tmp_path).config

    class DeniedFileSystem(vendor.LocalFileSystem):
        """Report a permission denial for the source directory."""

        def stat_mode(self, path: Path) -> int | None:
            """Refuse inspection of the source directory only."""
            if path == config.source_directory:
                raise PermissionError(13, "Permission denied", str(path))
            return super().stat_mode(path)

    with pytest.raises(
        vendor.VendorError, match="cannot inspect the import paths"
    ):
        vendor.validate(config, DeniedFileSystem())


def test_a_path_resolution_failure_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """An environmental error while resolving a path is a VendorError."""
    config = make_config(vendor, tmp_path).config

    class StaleFileSystem(vendor.LocalFileSystem):
        """Fail to resolve the mapped source file only."""

        def resolve(self, path: Path) -> Path:
            """Raise an I/O error for the mapped source file only."""
            if path.name == "users-guide.md":
                raise OSError("stale file handle")
            return super().resolve(path)

    with pytest.raises(
        vendor.VendorError, match="cannot inspect the import paths"
    ):
        vendor.validate(config, StaleFileSystem())


def test_validation_never_writes_or_removes_a_file(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Validation inspects and resolves paths, and changes nothing."""
    config = make_config(vendor, tmp_path).config
    mutations: list[str] = []

    class MutationGuard(vendor.LocalFileSystem):
        """Record any write or removal validation attempts."""

        def write_text(self, path: Path, text: str) -> None:
            """Record a text write, then perform it."""
            mutations.append(f"write_text {path}")
            super().write_text(path, text)

        def write_bytes(self, path: Path, data: bytes) -> None:
            """Record a byte write, then perform it."""
            mutations.append(f"write_bytes {path}")
            super().write_bytes(path, data)

        def unlink(self, path: Path) -> None:
            """Record a removal, then perform it."""
            mutations.append(f"unlink {path}")
            super().unlink(path)

    vendor.validate(config, MutationGuard())

    assert mutations == [], mutations
