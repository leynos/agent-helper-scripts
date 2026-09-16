"""Contract tests for the file list a gate discovers before it runs a tool.

A gate that examines no file reports no finding, and a recipe that pipes a
producer into a checker cannot tell the two apart. These tests pin the
discovery layer's half of the fix: a walk that reports nothing, and a directory
it cannot read, each raise rather than handing a tool a short list that reads
as a clean run.
"""

from __future__ import annotations

import os
from pathlib import Path

from cmd_mox import skip_if_unsupported
import pytest

from gate_runner_test_support import GateModules

skip_if_unsupported()


def test_a_tree_without_markdown_raises_rather_than_linting_nothing(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The walk's empty result fails the gate instead of reading as a pass."""
    (tmp_path / "notes.txt").write_text("not Markdown\n", encoding="utf-8")

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.discovery.markdown_paths(tmp_path, gate="markdownlint")

    assert "found no Markdown files" in str(failure.value)


def test_markdown_discovery_prunes_excluded_directories(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A vendored or generated tree is skipped, and the rest is reported."""
    for name in ("README.md", "docs/guide.md", "node_modules/pkg/README.md"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Title\n", encoding="utf-8")
    (tmp_path / "target" / "doc").mkdir(parents=True)
    (tmp_path / "target" / "doc" / "README.md").write_text("# Title\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")

    assert gate.discovery.markdown_paths(tmp_path, gate="markdownlint") == (
        Path("AGENTS.md"),
        Path("README.md"),
        Path("docs/guide.md"),
    )


def test_markdown_discovery_honours_a_replaced_exclusion_list(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A caller's exclusions replace the defaults rather than adding to them."""
    for name in ("README.md", "docs/guide.md", "node_modules/pkg/README.md"):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Title\n", encoding="utf-8")

    assert gate.discovery.markdown_paths(
        tmp_path,
        gate="markdownlint",
        excludes=("node_modules", "docs"),
    ) == (Path("README.md"),)


def test_markdown_discovery_reports_paths_relative_to_the_repository(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """Paths are relative, so a tool run from the root names the same files."""
    repository = tmp_path / "checkout"
    (repository / "docs").mkdir(parents=True)
    (repository / "docs" / "guide.md").write_text("# Title\n", encoding="utf-8")

    discovered = gate.discovery.markdown_paths(repository, gate="markdownlint")

    assert discovered == (Path("docs/guide.md"),), discovered


def test_an_uppercase_markdown_suffix_is_discovered(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """Markdown is Markdown whatever case the suffix was written in."""
    (tmp_path / "NOTES.Md").write_text("# notes\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    (tmp_path / "data.json").write_text("{}\n", encoding="utf-8")

    discovered = gate.discovery.markdown_paths(tmp_path, gate="markdownlint")

    assert discovered == (Path("NOTES.Md"), Path("README.md")), (
        "a document whose suffix differs only in case is still Markdown, and a "
        f"non-Markdown file is still not; got {discovered}"
    )


def test_a_directory_that_cannot_be_read_fails_the_walk(
    gate: GateModules,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable subtree fails the gate instead of being silently skipped.

    ``os.walk`` swallows a ``scandir`` failure unless it is handed an
    ``onerror`` callback. Without one the readable file below keeps the list
    non-empty, the linter runs over a subset, and the gate reports a pass over
    a tree it never finished reading.

    The refusal is raised in the operating system's place, because a directory
    mode that denies a read is not portable: root, and a process holding
    ``CAP_DAC_OVERRIDE``, read the directory anyway, and a platform without
    POSIX modes never denies it at all.
    """
    (tmp_path / "README.md").write_text("# readme\n", encoding="utf-8")
    private = tmp_path / "private"
    private.mkdir()
    (private / "SECRET.md").write_text("# secret\n", encoding="utf-8")
    scandir = os.scandir

    def refuse(path: str) -> typ.Iterator[os.DirEntry[str]]:
        """Deny one directory the way an unreadable one denies the walk."""
        if Path(path) == private:
            raise PermissionError(13, "Permission denied", path)
        return scandir(path)

    monkeypatch.setattr(os, "scandir", refuse)

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.discovery.markdown_paths(tmp_path, gate="markdownlint")

    message = str(failure.value)
    assert "markdownlint" in message, message
    assert "could not read" in message, (
        f"the failure must name the tree it could not read, got {message!r}"
    )
