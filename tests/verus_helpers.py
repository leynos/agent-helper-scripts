"""Shared helpers for Verus reference script tests.

Provides the fake repository tree builder, script runner, and fake binary
writer used by test_install_verus.py and test_run_verus.py.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from cmd_mox import skip_if_unsupported


skip_if_unsupported()

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "skills" / "verus" / "references" / "install-verus.sh"
RUN_SCRIPT = REPO_ROOT / "skills" / "verus" / "references" / "run-verus.sh"

FAKE_VERSION = "0.2026.01.30.test123"
FAKE_TARGET = "x86-linux"


def make_repo_tree(tmp_path: Path) -> Path:
    """Build a minimal fake repository tree with tools/verus metadata.

    Returns the repo directory. The scripts are symlinked into
    repo/references/ so that BASH_SOURCE[0]-derived ROOT_DIR resolves
    to repo.
    """
    repo = tmp_path / "repo"
    tools = repo / "tools" / "verus"
    tools.mkdir(parents=True)
    refs = repo / "references"
    refs.mkdir()

    (tools / "VERSION").write_text(FAKE_VERSION)

    archive_name = f"verus-{FAKE_VERSION}-{FAKE_TARGET}.zip"
    fake_sha = "a" * 64
    (tools / "SHA256SUMS").write_text(f"{fake_sha}  {archive_name}\n")

    # Symlink the real scripts into the fake repo references/ directory.
    (refs / "install-verus.sh").symlink_to(INSTALL_SCRIPT)
    (refs / "run-verus.sh").symlink_to(RUN_SCRIPT)

    return repo


def run_script(
    script: Path,
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a bash script with optional environment overrides."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        ["bash", str(script)],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def make_fake_verus(path: Path) -> None:
    """Write a fake verus binary that reports a toolchain on --version."""
    path.write_text(
        '#!/bin/sh\n'
        'case "$1" in\n'
        '  --version) echo "Toolchain: nightly-2025-11-05" ;;\n'
        '  *) echo "verified" ;;\n'
        'esac\n'
    )
    path.chmod(0o755)
