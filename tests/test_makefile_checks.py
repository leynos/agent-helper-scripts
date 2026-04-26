"""Tests for Makefile validation helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_make(*args: str) -> subprocess.CompletedProcess[str]:
    """Run make from the repository root.

    Parameters
    ----------
    *args
        Make arguments to pass after the executable name.

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
        text=True,
        capture_output=True,
        check=False,
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

    assert result.returncode != 0
    assert f"{script.as_posix()}:1:" in result.stdout
    assert f"{script.as_posix()}:2:" in result.stdout
    assert f"{script.as_posix()}:3:" in result.stdout
    assert f"{script.as_posix()}:4:" in result.stdout
