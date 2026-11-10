"""Narrow filesystem boundary for validation, reads, writes, and restoration.

The importer's core is standard-library only, but it does not reach the
operating system through ``pathlib`` directly. Replacing ``Path`` methods to
observe a write or inject a read, write, or restore failure changes the
behaviour of every caller in the process, which makes such a test a blunt
instrument and hides what the importer itself asked for. :class:`FileSystem`
names the operations the importer performs, :class:`LocalFileSystem` performs
them on the local machine, and ``validate`` and ``vendor`` accept a substitute.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileSystem(Protocol):
    """Name the file operations the importer performs."""

    def resolve(self, path: Path) -> Path:
        """Return the absolute path with symbolic links resolved."""
        ...

    def stat_mode(self, path: Path) -> int | None:
        """Return a path's mode bits, or ``None`` when it does not exist."""
        ...

    def lstat_mode(self, path: Path) -> int | None:
        """Return a path's own mode bits without following a symbolic link."""
        ...

    def read_text(self, path: Path) -> str:
        """Read one UTF-8 text file."""
        ...

    def read_bytes(self, path: Path) -> bytes:
        """Read one file's bytes."""
        ...

    def write_text(self, path: Path, text: str) -> None:
        """Write UTF-8 text with ``\\n`` newlines."""
        ...

    def write_bytes(self, path: Path, data: bytes) -> None:
        """Write raw bytes over one file."""
        ...

    def unlink(self, path: Path) -> None:
        """Remove a file, tolerating one that is already gone."""
        ...


class LocalFileSystem:
    """Perform the boundary's operations through ``pathlib``.

    A test double subclasses this and overrides one method, so the operations
    it does not override keep their real behaviour.
    """

    def resolve(self, path: Path) -> Path:
        """Return the absolute path with symbolic links resolved."""
        return path.resolve()

    def stat_mode(self, path: Path) -> int | None:
        """Return a path's mode bits, or ``None`` when it does not exist.

        ``Path.is_dir`` and ``Path.is_file`` swallow some filesystem errors on
        newer interpreters, so a permission denial would read as a missing
        path. ``Path.stat`` reports the denial, which the caller translates
        into a one-line diagnostic.
        """
        try:
            return path.stat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            return None

    def lstat_mode(self, path: Path) -> int | None:
        """Return a path's own mode bits without following a symbolic link.

        ``Path.exists`` follows a link, so a dangling output symlink would read
        as an absent file and a later write would create its target. ``lstat``
        reports the link itself, and an inspection failure is raised rather
        than reported as absence.
        """
        try:
            return path.lstat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            return None

    def read_text(self, path: Path) -> str:
        """Read one UTF-8 text file."""
        return path.read_text(encoding="utf-8")

    def read_bytes(self, path: Path) -> bytes:
        """Read one file's bytes."""
        return path.read_bytes()

    def write_text(self, path: Path, text: str) -> None:
        """Write UTF-8 text with ``\\n`` newlines."""
        path.write_text(text, encoding="utf-8", newline="\n")

    def write_bytes(self, path: Path, data: bytes) -> None:
        """Write raw bytes over one file."""
        path.write_bytes(data)

    def unlink(self, path: Path) -> None:
        """Remove a file, tolerating one that is already gone."""
        path.unlink(missing_ok=True)


#: Boundary used when a caller does not supply one.
DEFAULT_FILE_SYSTEM: FileSystem = LocalFileSystem()