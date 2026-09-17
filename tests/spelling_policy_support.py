"""Paths and helpers shared by the spelling-policy and gate tests.

This repository curates `data/typos-oxendict-base.toml` and no longer carries a
generator: `typos-config-builder` reads that file, renders `typos.toml`, runs
Typos and enforces the phrase corrections. What remains testable here is the
policy document itself, and the harvesting tool that proposes additions to it.
"""

from pathlib import Path
import shutil

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_PATH = REPOSITORY_ROOT / "scripts"
SHARED_DICTIONARY_PATH = REPOSITORY_ROOT / "data" / "typos-oxendict-base.toml"
LOCAL_DICTIONARY_PATH = REPOSITORY_ROOT / "typos.local.toml"
COMMITTED_CONFIG_PATH = REPOSITORY_ROOT / "typos.toml"

__all__ = (
    "COMMITTED_CONFIG_PATH",
    "LOCAL_DICTIONARY_PATH",
    "REPOSITORY_ROOT",
    "SCRIPTS_PATH",
    "SHARED_DICTIONARY_PATH",
    "require_executable",
)


def require_executable(name: str) -> str:
    """Resolve an executable or fail with a clear test-environment error.

    Parameters
    ----------
    name
        Command the test needs to start a subprocess.

    Returns
    -------
    str
        Absolute path of the resolved executable.

    Raises
    ------
    AssertionError
        If the command is unavailable in the test environment.
    """
    executable = shutil.which(name)
    assert executable is not None, f"{name} is unavailable for subprocess test"
    return executable
