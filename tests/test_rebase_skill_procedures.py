"""Behavioural tests for the procedures the rebase skill documents.

These use a stub external diff driver to exercise Git's behaviour, so the
skill's patch-recovery recipe is executable rather than merely asserted as
prose. No test depends on any particular diff tool being installed.
"""

from __future__ import annotations

import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    from collections.abc import Iterator

GIT = shutil.which("git")

if GIT is None:  # pragma: no cover - Git is a repository test prerequisite.
    raise RuntimeError("git is required to run the rebase procedure tests")

# Stands in for any external diff tool whose output is not a unified diff.
STUB_EXTERNAL_DIFF = "sh -c 'echo example.py --- 1/2 --- Text'"


def _git(
    repository: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository with captured output."""
    return subprocess.run(  # noqa: S603 - absolute executable and controlled arguments.
        [GIT, *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=check,
        timeout=60,
    )


@pytest.fixture
def repository_with_external_diff(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    """Build a repository with uncommitted work and an external diff driver."""
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "example.py"

    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "Rebase Skill Test")
    _git(repository, "config", "user.email", "rebase-skill@example.invalid")
    source.write_text('def alpha() -> str:\n    return "base"\n', encoding="utf-8")
    _git(repository, "add", "example.py")
    _git(repository, "commit", "--quiet", "-m", "base")

    source.write_text('def alpha() -> str:\n    return "recovered"\n', encoding="utf-8")
    _git(repository, "config", "diff.external", STUB_EXTERNAL_DIFF)
    yield repository, source


def test_plain_git_diff_under_an_external_driver_is_rejected(
    repository_with_external_diff: tuple[Path, Path],
) -> None:
    """`git diff` yields the tool's format, which `git apply` refuses."""
    repository, _ = repository_with_external_diff

    patch = repository / "hijacked.patch"
    patch.write_text(_git(repository, "diff").stdout, encoding="utf-8")

    assert not patch.read_text(encoding="utf-8").startswith("diff --git"), (
        "the external driver must replace the unified diff the skill expects"
    )
    applied = _git(repository, "apply", "--check", "hijacked.patch", check=False)
    assert applied.returncode != 0, "git apply must reject the hijacked output"
    assert "No valid patches in input" in applied.stderr, (
        "the documented symptom must be the error git apply actually prints, got "
        f"{applied.stderr!r}"
    )


def test_no_ext_diff_restores_a_patch_git_apply_accepts(
    repository_with_external_diff: tuple[Path, Path],
) -> None:
    """The documented flag round-trips the change through `git apply`."""
    repository, source = repository_with_external_diff
    recovered = source.read_text(encoding="utf-8")

    patch = repository / "recover.patch"
    patch.write_text(
        _git(repository, "diff", "--no-ext-diff", "--binary").stdout, encoding="utf-8"
    )
    assert patch.read_text(encoding="utf-8").startswith("diff --git"), (
        "the documented check for a valid patch must pass"
    )

    _git(repository, "checkout", "--", "example.py")
    assert source.read_text(encoding="utf-8") != recovered, "the change must be gone"

    _git(repository, "apply", "recover.patch")
    assert source.read_text(encoding="utf-8") == recovered, (
        "applying the patch must restore the discarded work exactly"
    )


@pytest.mark.parametrize(
    "command",
    [
        ("show", "HEAD"),
        ("log", "-p", "-1"),
        ("format-patch", "-1", "--stdout"),
    ],
)
def test_history_commands_already_suppress_external_diff_drivers(
    repository_with_external_diff: tuple[Path, Path], command: tuple[str, ...]
) -> None:
    """The commands the skill calls already safe emit real unified diffs."""
    repository, _ = repository_with_external_diff

    output = _git(repository, *command).stdout

    assert "diff --git a/example.py b/example.py" in output, (
        f"`git {command[0]}` must not be hijacked by the external diff driver"
    )


def test_stash_show_patch_applies_without_the_flag(
    repository_with_external_diff: tuple[Path, Path],
) -> None:
    """`git stash show -p` is safe, as the skill tells the reader to prefer."""
    repository, source = repository_with_external_diff
    stashed = source.read_text(encoding="utf-8")
    _git(repository, "stash", "--quiet")

    patch = repository / "stash.patch"
    patch.write_text(_git(repository, "stash", "show", "-p").stdout, encoding="utf-8")
    assert patch.read_text(encoding="utf-8").startswith("diff --git"), (
        "stash show -p must emit a unified diff despite the external driver"
    )

    _git(repository, "apply", "stash.patch")
    assert source.read_text(encoding="utf-8") == stashed, (
        "the stash must be recoverable as a patch without dropping it"
    )
