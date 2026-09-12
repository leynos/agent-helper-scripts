"""Contract tests for the file list a gate discovers before it runs a tool.

A gate that examines no file reports no finding, and a recipe that pipes a
producer into a checker cannot tell the two apart. These tests pin the
discovery layer's half of the fix: a producer that fails, and a producer that
reports nothing, each raise rather than handing a tool a short list that reads
as a clean run.

The Git double answers through ``PATH``, which is how the undisguised
``subprocess.run(["git", ...])`` resolves it, so the failing and empty cases
are reached the way the real gate reaches them.
"""

from __future__ import annotations

from pathlib import Path
import typing as typ

from cmd_mox import CmdMox, skip_if_unsupported
import pytest

from gate_runner_test_support import GIT, GateModules, git_handler

if typ.TYPE_CHECKING:
    from cmd_mox.ipc import Invocation

skip_if_unsupported()

GATE = "spelling"
NOT_A_REPOSITORY = "fatal: not a git repository (or any of the parent directories)"


def test_a_failing_producer_raises_rather_than_listing_files(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A producer that exits non-zero fails the gate with its own diagnostic."""
    cmd_mox.spy(GIT).runs(git_handler(status=128, diagnostic=NOT_A_REPOSITORY))

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.discovery.tracked_paths(tmp_path, gate=GATE)

    message = str(failure.value)
    assert NOT_A_REPOSITORY in message, (
        f"the producer's own diagnostic must reach the gate, got {message!r}"
    )
    assert GATE in message, message


def test_an_empty_producer_raises_rather_than_listing_nothing(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A producer that succeeds with no output refuses to pass an empty list."""
    cmd_mox.spy(GIT).runs(git_handler(listed=""))

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.discovery.tracked_paths(tmp_path, gate=GATE)

    message = str(failure.value)
    assert "found no Git-tracked files" in message, message
    assert "reads as a clean run" in message, (
        "the refusal must name what an empty list would have looked like"
    )


def test_the_producer_is_asked_about_the_repository_under_test(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """Discovery names its repository, so a wrong root cannot list another tree."""
    spy = cmd_mox.spy(GIT).runs(git_handler(listed="README.md\0"))

    gate.discovery.tracked_paths(tmp_path, gate=GATE)

    assert spy.call_count == 1, spy.invocations
    assert list(spy.invocations[0].args) == ["-C", str(tmp_path), "ls-files", "-z"]


def test_tracked_paths_are_sorted_and_repository_relative(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The list is normalized, so two runs of a gate examine the same files."""
    cmd_mox.spy(GIT).runs(
        git_handler(listed="docs/guide.md\0AGENTS.md\0README.md\0"),
    )

    assert gate.discovery.tracked_paths(tmp_path, gate=GATE) == (
        Path("AGENTS.md"),
        Path("README.md"),
        Path("docs/guide.md"),
    )


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


def test_a_nul_delimited_name_with_a_newline_survives_discovery(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A path holding a newline is one entry, not two split ones."""
    awkward = "docs/odd\nname.md"
    cmd_mox.spy(GIT).runs(git_handler(listed=f"{awkward}\0README.md\0"))

    discovered = gate.discovery.tracked_paths(tmp_path, gate=GATE)

    assert Path(awkward) in discovered, (
        "NUL-delimited output must not be split on newlines, or a path "
        f"containing one becomes two files that do not exist; got {discovered}"
    )


def test_the_handler_override_can_answer_one_call_specifically(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The double can single out a call while leaving the rest to its defaults."""

    def respond(invocation: Invocation) -> tuple[str, str, int] | None:
        if "diff" in invocation.args:
            return ("", "", 1)
        return None

    cmd_mox.spy(GIT).runs(git_handler(listed="README.md\0", respond=respond))

    assert gate.discovery.tracked_paths(tmp_path, gate=GATE) == (Path("README.md"),)
