"""Shared fixtures and constants for typos rollout tests."""

import importlib.util
from pathlib import Path
import shutil
import types

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "typos_rollout.py"
SHARED_DICTIONARY_PATH = REPOSITORY_ROOT / "data" / "typos-oxendict-base.toml"
LOCAL_DICTIONARY_PATH = REPOSITORY_ROOT / "typos.local.toml"
COMMITTED_CONFIG_PATH = REPOSITORY_ROOT / "typos.toml"


@pytest.fixture(name="rollout", scope="module")
def rollout_fixture() -> types.ModuleType:
    """Load the executable script as a module for focused unit tests."""
    spec = importlib.util.spec_from_file_location("typos_rollout", SCRIPT_PATH)
    assert spec is not None, "could not create a module specification"
    assert spec.loader is not None, "module specification has no loader"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dictionary_text(*, stem: str = "organ", accepted: str = "oxendict") -> str:
    """Return a minimal valid shared dictionary document."""
    return (
        'schema = 1\n\n[oxford]\n'
        f'stems = ["{stem}"]\n\n'
        f'[words]\naccepted = ["{accepted}"]\n\n'
        '[words.corrections]\n\n[patterns]\nignore = []\n\n'
        '[files]\nexclude = [".git"]\n'
    )


def require_executable(name: str) -> str:
    """Resolve an executable or fail with a clear test-environment error."""
    executable = shutil.which(name)
    assert executable is not None, f"{name} is unavailable for subprocess test"
    return executable
