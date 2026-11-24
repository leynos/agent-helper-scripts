"""Tests for Makefile validation helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_make(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run make from the repository root.

    Parameters
    ----------
    *args
        Make arguments to pass after the executable name.
    env
        Complete environment for the child. ``None`` inherits this process's
        environment, which is what most callers want; a supplied mapping
        replaces it, so a caller can control ``RUSTFLAGS`` and the link probes
        exactly.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed make process with captured output.

    Side Effects
    ------------
    Starts a subprocess in the repository root.
    """
    return subprocess.run(  # noqa: S603,S607 - controlled args, shell=False, repo-root make lookup.
        ["make", *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_shell_syntax_check_covers_shipped_skill_scripts() -> None:
    """The syntax gate discovers skill helpers, so removing the wildcard fails here."""
    result = run_make("--dry-run", "shell-syntax-check")

    assert result.returncode == 0, result.stdout + result.stderr
    commands = [line for line in result.stdout.splitlines() if line.startswith("bash -n ")]
    assert len(commands) == 1, f"expected one bash -n command, got: {result.stdout}"
    checked = commands[0].split()[2:]
    assert "skills/pr-babysitting/scripts/post-manual-comment.sh" in checked, (
        "shell-syntax-check must include shipped skill helpers from skills/*/scripts/*.sh"
    )


def test_home_phase_boundary_ignores_comment_only_matches(tmp_path: Path) -> None:
    """Boundary check ignores forbidden words that appear only in comments."""
    script = tmp_path / "home-helper"
    script.write_text(
        "# apt-get install bad\n"
        "# sudo true\n"
        "printf '%s\\n' notapt-getter\n",
    )

    result = run_make(
        "check-home-phase-boundary",
        f"HOME_PHASE_SCRIPTS={script.as_posix()}",
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_home_phase_boundary_rejects_forbidden_commands(tmp_path: Path) -> None:
    """Boundary check fails when a home script invokes system commands."""
    script = tmp_path / "home-helper"
    script.write_text(
        "sudo apt-get update\n"
        "install -m 0755 source target\n"
        "realpath /usr/bin/ld\n"
        "ln -sf /usr/bin/fdfind fd\n",
    )

    result = run_make(
        "check-home-phase-boundary",
        f"HOME_PHASE_SCRIPTS={script.as_posix()}",
    )

    assert result.returncode != 0, (
        "expected non-zero returncode, "
        f"got {result.returncode}, stdout: {result.stdout}"
    )
    assert f"{script.as_posix()}:1:" in result.stdout, (
        f"expected '{script.as_posix()}:1:' in stdout, got: {result.stdout}"
    )
    assert f"{script.as_posix()}:2:" in result.stdout, (
        f"expected '{script.as_posix()}:2:' in stdout, got: {result.stdout}"
    )
    assert f"{script.as_posix()}:3:" in result.stdout, (
        f"expected '{script.as_posix()}:3:' in stdout, got: {result.stdout}"
    )
    assert f"{script.as_posix()}:4:" in result.stdout, (
        f"expected '{script.as_posix()}:4:' in stdout, got: {result.stdout}"
    )


def _dry_run_command(target: str, *, uname: str, mold: str, rustflags: str | None) -> str:
    """Return the recipe make prints for ``target`` under a pinned host shape.

    ``UNAME_S``, ``MOLD`` and ``RUSTFLAGS`` are the three inputs the fallback
    reads, so a test can pin every branch without manipulating ``PATH`` or the
    real toolchain.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "RUSTFLAGS" and not key.startswith("MAKEFLAGS")
    }
    if rustflags is not None:
        env["RUSTFLAGS"] = rustflags
    result = run_make(
        "--dry-run",
        target,
        f"UNAME_S={uname}",
        f"MOLD={mold}",
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def _recipe(output: str) -> str:
    """Return make's dry-run recipe text, which may span several lines."""
    assert output.strip(), "make printed no recipe"
    return output


#: The three commands that resolve the dev environment and can therefore
#: build the pinned femtologging checkout. ``interrogate`` and the typos
#: builder run from isolated ``uv tool`` environments and are deliberately
#: absent.
LINKER_COVERED_TARGETS = ("test", "skill-manifest-validate", "skill-frontmatter-lint")


@pytest.mark.parametrize("target", LINKER_COVERED_TARGETS)
def test_linker_fallback_prefixes_every_dev_environment_command(target: str) -> None:
    """Linux without mold and without caller flags gets the empty prefix."""
    command = _recipe(
        _dry_run_command(target, uname="Linux", mold="", rustflags=None)
    )

    assert "RUSTFLAGS=" in command, (
        f"{target} must carry the platform-linker fallback, got {command!r}"
    )


@pytest.mark.parametrize("target", LINKER_COVERED_TARGETS)
def test_linker_fallback_preserves_a_caller_assigned_rustflags(target: str) -> None:
    """A caller-assigned ``RUSTFLAGS`` is never displaced by the fallback."""
    command = _recipe(
        _dry_run_command(target, uname="Linux", mold="", rustflags="-Dwarnings")
    )

    assert "RUSTFLAGS=" not in command, (
        f"{target} must not override a caller-assigned RUSTFLAGS, got {command!r}"
    )


@pytest.mark.parametrize("target", LINKER_COVERED_TARGETS)
def test_linker_fallback_is_skipped_when_mold_is_installed(target: str) -> None:
    """A host with mold keeps the femtologging build's faster link."""
    command = _recipe(
        _dry_run_command(
            target, uname="Linux", mold="/usr/bin/mold", rustflags=None
        )
    )

    assert "RUSTFLAGS=" not in command, (
        f"{target} must keep mold when it is installed, got {command!r}"
    )


@pytest.mark.parametrize("target", LINKER_COVERED_TARGETS)
def test_linker_fallback_is_linux_only(target: str) -> None:
    """A non-Linux host links with its own platform toolchain."""
    command = _recipe(
        _dry_run_command(target, uname="Darwin", mold="", rustflags=None)
    )

    assert "RUSTFLAGS=" not in command, (
        f"{target} must not carry a Linux-only fallback, got {command!r}"
    )


def test_an_empty_caller_rustflags_is_treated_as_unset() -> None:
    """The CI step's ``RUSTFLAGS: ""`` yields the same command as an unset one."""
    empty = _recipe(
        _dry_run_command("test", uname="Linux", mold="", rustflags="")
    )
    unset = _recipe(
        _dry_run_command("test", uname="Linux", mold="", rustflags=None)
    )

    assert empty == unset, (
        "an empty RUSTFLAGS must not change the resolved command, "
        f"got {empty!r} and {unset!r}"
    )
