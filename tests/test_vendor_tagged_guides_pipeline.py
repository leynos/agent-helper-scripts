"""Tests for composing conversion, formatting, and writing.

The pipeline writes in mapping order and refuses a formatter that does not
reach a fixed point, so a rerun at the same tag reproduces the same bytes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
import tempfile
import types

from hypothesis import given, settings
from hypothesis import strategies as st
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
    sources = {
        "v0-2-0-migration-guide.md": (
            "# Migration guide\n\n"
            "See the [users' guide](users-guide.md#program-catalogue).\n"
        ),
        "users-guide.md": (
            "# Users' guide\n\n"
            "See the [migration guide](v0-2-0-migration-guide.md#moving)\n"
            "and the [developers' guide](developers-guide.md).\n"
        ),
    }
    config = make_config(
        vendor, tmp_path, sources=sources, mappings=mappings
    ).config

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

    texts = {name: data.decode("utf-8") for name, data in first_bytes.items()}
    for name, text in texts.items():
        assert vendor.IMPORT_MARKER in text, (name, text)
    assert "aaa-users.md" in texts["zzz-migration.md"], texts
    assert "zzz-migration.md" in texts["aaa-users.md"], texts
    assert (
        "https://github.com/leynos/cuprum/blob/v0.2.0-beta2/docs/"
        "developers-guide.md"
    ) in texts["aaa-users.md"], texts


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

    assert (
        "markdownlint-disable MD013"
        in written[0].read_text(encoding="utf-8")
    ), written


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

    assert kept.read_text(encoding="utf-8") == "previous contents\n", kept
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
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A read-only output directory is a one-line diagnostic, not a traceback."""
    built = make_config(vendor, tmp_path)

    class ReadOnlyFileSystem(vendor.LocalFileSystem):
        """Refuse every text write as a read-only mount would."""

        def write_text(self, path: Path, text: str) -> None:
            """Refuse the write without touching the file."""
            raise OSError("read-only file system")

    with pytest.raises(vendor.VendorError, match="cannot write"):
        vendor.vendor(built.config, filesystem=ReadOnlyFileSystem())


def test_a_dangling_output_symlink_is_refused_before_writing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A dangling link must not read as an absent output and be followed."""
    built = make_config(vendor, tmp_path)
    link = built.consumer / "cuprum-users-guide.md"
    target = built.consumer / "missing-target.md"
    link.symlink_to(target.name)

    with pytest.raises(
        vendor.VendorError, match="refusing to write through the symbolic link"
    ):
        vendor.vendor(built.config)

    assert link.is_symlink(), link
    assert not target.exists(), target
    assert not (built.consumer / "cuprum-v0-2-0-migration-guide.md").exists()


def test_an_output_symlink_to_an_existing_file_is_refused_before_writing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A link to a real file must not be written through and then unlinked."""
    built = make_config(vendor, tmp_path)
    target = built.consumer / "target.md"
    target.write_text("keep me\n", encoding="utf-8", newline="\n")
    link = built.consumer / "cuprum-users-guide.md"
    link.symlink_to(target.name)

    with pytest.raises(
        vendor.VendorError, match="refusing to write through the symbolic link"
    ):
        vendor.vendor(built.config)

    assert link.is_symlink(), link
    assert target.read_text(encoding="utf-8") == "keep me\n", target


def test_an_output_inspection_failure_is_reported_and_writes_nothing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """An inspection error is not proof that an output is absent."""
    built = make_config(vendor, tmp_path)

    class UninspectableFileSystem(vendor.LocalFileSystem):
        """Fail the output inspection as a stale handle would."""

        def lstat_mode(self, path: Path) -> int | None:
            """Refuse to inspect any path."""
            raise OSError("stale file handle")

    with pytest.raises(vendor.VendorError, match="cannot inspect or read"):
        vendor.vendor(built.config, filesystem=UninspectableFileSystem())

    assert list(built.consumer.iterdir()) == [], list(built.consumer.iterdir())


def test_a_source_read_failure_is_reported_and_writes_nothing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A failing source read is a one-line diagnostic before any write."""
    built = make_config(vendor, tmp_path)

    class UnreadableFileSystem(vendor.LocalFileSystem):
        """Fail every text read as a failing device would."""

        def read_text(self, path: Path) -> str:
            """Refuse the read."""
            raise OSError("input/output error")

    with pytest.raises(vendor.VendorError, match="cannot read"):
        vendor.vendor(built.config, filesystem=UnreadableFileSystem())

    assert list(built.consumer.iterdir()) == [], list(built.consumer.iterdir())


def test_a_previous_output_read_failure_is_reported_and_writes_nothing(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A failing snapshot read leaves every output as it was found."""
    built = make_config(vendor, tmp_path)
    kept = built.consumer / "cuprum-users-guide.md"
    kept.write_text("previous\n", encoding="utf-8", newline="\n")

    class UnreadableBytesFileSystem(vendor.LocalFileSystem):
        """Fail the previous-output byte read."""

        def read_bytes(self, path: Path) -> bytes:
            """Refuse the read."""
            raise OSError("input/output error")

    with pytest.raises(vendor.VendorError, match="cannot inspect or read"):
        vendor.vendor(built.config, filesystem=UnreadableBytesFileSystem())

    assert kept.read_text(encoding="utf-8") == "previous\n", kept
    assert not (built.consumer / "cuprum-v0-2-0-migration-guide.md").exists()


class FullDiskFileSystem:
    """Boundary that fails one path's byte write and delegates the rest."""

    def __init__(self, vendor: types.ModuleType, refusing: Path) -> None:
        """Wrap the real boundary and name the path that cannot be restored."""
        self._delegate = vendor.LocalFileSystem()
        self._refusing = refusing

    def __getattr__(self, name: str) -> object:
        """Delegate every operation but ``write_bytes`` to the real boundary."""
        return getattr(self._delegate, name)

    def write_bytes(self, path: Path, data: bytes) -> None:
        """Refuse the restore of one path as a full disk would."""
        if path == self._refusing:
            raise OSError("disk full")
        self._delegate.write_bytes(path, data)


def test_a_failed_restore_is_reported_and_the_remaining_outputs_are_restored(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """One failed restore must not strand the other outputs in converted state."""
    built = make_config(vendor, tmp_path)
    first = built.consumer / "cuprum-users-guide.md"
    second = built.consumer / "cuprum-v0-2-0-migration-guide.md"
    first.write_text("first previous\n", encoding="utf-8", newline="\n")
    second.write_text("second previous\n", encoding="utf-8", newline="\n")

    with pytest.raises(vendor.VendorError) as raised:
        vendor.vendor(
            built.config,
            format_files=drifting_format,
            filesystem=FullDiskFileSystem(vendor, first),
        )

    message = str(raised.value)
    assert "could not restore previous output" in message, message
    assert str(first) in message, message
    assert "original failure: VendorError" in message, message
    assert second.read_text(encoding="utf-8") == "second previous\n", second


def test_an_interruption_is_reraised_when_a_restore_fails(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A restore failure must not replace an interruption with a VendorError."""
    built = make_config(vendor, tmp_path)
    first = built.consumer / "cuprum-users-guide.md"
    second = built.consumer / "cuprum-v0-2-0-migration-guide.md"
    first.write_text("first previous\n", encoding="utf-8", newline="\n")
    second.write_text("second previous\n", encoding="utf-8", newline="\n")

    def interrupting_format(_paths: Sequence[Path]) -> None:
        """Interrupt once every output has been written."""
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt) as raised:
        vendor.vendor(
            built.config,
            format_files=interrupting_format,
            filesystem=FullDiskFileSystem(vendor, first),
        )

    notes = getattr(raised.value, "__notes__", [])
    assert any(
        "could not restore previous output" in note for note in notes
    ), notes
    assert second.read_text(encoding="utf-8") == "second previous\n", second


@settings(max_examples=25, deadline=None)
@given(
    cases=st.lists(
        st.tuples(
            st.one_of(st.none(), st.text(alphabet="abc \n", max_size=16)),
            st.booleans(),
        ),
        min_size=1,
        max_size=4,
    )
)
def test_a_failed_run_restores_every_previous_output_or_reports_it(
    vendor: types.ModuleType,
    cases: list[tuple[str | None, bool]],
) -> None:
    """Every previous output is restored, or named in the one-line report."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources = {
            f"guide-{index}.md": f"# Guide {index}\n\nText.\n"
            for index in range(len(cases))
        }
        mappings = tuple(
            (f"guide-{index}.md", f"out-{index}.md")
            for index in range(len(cases))
        )
        built = make_config(vendor, root, sources=sources, mappings=mappings)
        restricted: set[Path] = set()
        for index, (content, refuse) in enumerate(cases):
            path = built.consumer / f"out-{index}.md"
            if content is not None:
                path.write_text(content, encoding="utf-8", newline="\n")
                if refuse:
                    restricted.add(path)

        class RestoreFailingFileSystem:
            """Boundary that refuses writes once the formatter has failed."""

            def __init__(self) -> None:
                """Wrap the real boundary with no refusal yet."""
                self._delegate = vendor.LocalFileSystem()
                self.failing = False

            def __getattr__(self, name: str) -> object:
                """Delegate every operation but ``write_bytes``."""
                return getattr(self._delegate, name)

            def write_bytes(self, path: Path, data: bytes) -> None:
                """Refuse a restore after the formatter has failed."""
                if self.failing and path in restricted:
                    raise OSError("disk full")
                self._delegate.write_bytes(path, data)

        filesystem = RestoreFailingFileSystem()

        def failing_format(_paths: Sequence[Path]) -> None:
            """Fail the run after every output has been written."""
            filesystem.failing = True
            raise RuntimeError("formatter exploded")

        with pytest.raises(Exception) as raised:
            vendor.vendor(
                built.config,
                format_files=failing_format,
                filesystem=filesystem,
            )

        error = raised.value
        if restricted:
            assert isinstance(error, vendor.VendorError), error
            message = str(error)
            assert "could not restore previous output" in message, message
            assert (
                "original failure: RuntimeError: formatter exploded"
                in message
            ), message
            for path in restricted:
                assert str(path) in message, message
        else:
            assert isinstance(error, RuntimeError), error

        for index, (content, _) in enumerate(cases):
            path = built.consumer / f"out-{index}.md"
            if path in restricted:
                continue
            if content is None:
                assert not path.exists(), path
            else:
                assert path.read_text(encoding="utf-8") == content, path


def test_a_later_mapping_without_a_heading_writes_nothing(
    vendor: types.ModuleType, tmp_path: Path
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

    class RecordingFileSystem(vendor.LocalFileSystem):
        """Record every text write the pipeline attempts."""

        def write_text(self, path: Path, text: str) -> None:
            """Record the path, then write through the real boundary."""
            writes.append(path)
            super().write_text(path, text)

    with pytest.raises(vendor.VendorError, match="level-one heading"):
        vendor.vendor(built.config, filesystem=RecordingFileSystem())

    assert writes == [], writes

    assert first.read_text(encoding="utf-8") == "previous\n"
    assert not second.exists()
    assert {
        path.name: path.read_bytes()
        for path in built.config.source_directory.iterdir()
    } == sources_before
