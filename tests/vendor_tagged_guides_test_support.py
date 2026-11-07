"""Shared fixtures and helpers for the tagged-guide vendoring tests.

The vendoring core is a package under ``scripts/`` that is not installed, so
the fixture loads it by putting that directory on ``sys.path``. The helpers
build small upstream and consumer trees, and :func:`run_cli` is the single
place the tests start the PEP 723 front end through ``uv``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest

from spelling_policy_support import REPOSITORY_ROOT, SCRIPTS_PATH

CLI_PATH = SCRIPTS_PATH / "vendor_tagged_guides_cli.py"
MARKDOWNLINT_CONFIG = REPOSITORY_ROOT / ".markdownlint-cli2.jsonc"
REAL_FORMATTER = "mdtablefix"
REAL_LINTER = "markdownlint-cli2"

#: Formatter arguments the shared Markdown baseline uses. ``--check`` and
#: ``--in-place`` are mutually exclusive, so the write mode is added by the
#: caller.
FORMATTER_ARGUMENTS = (
    "--wrap",
    "--renumber",
    "--breaks",
    "--ellipsis",
    "--fences",
)

__all__ = (
    "CLI_PATH",
    "FORMATTER_ARGUMENTS",
    "MARKDOWNLINT_CONFIG",
    "REAL_FORMATTER",
    "REAL_LINTER",
    "convert_fragment",
    "make_config",
    "pinned",
    "run_cli",
    "vendor_fixture",
    "write_upstream",
)


@pytest.fixture(name="vendor", scope="module")
def vendor_fixture() -> Iterator[types.ModuleType]:
    """Load the vendoring core from ``scripts/`` by path.

    Yields
    ------
    types.ModuleType
        The vendoring core module, imported from ``scripts/``.
    """
    script_directory = str(SCRIPTS_PATH)
    sys.path.insert(0, script_directory)
    try:
        yield importlib.import_module("vendor_tagged_guides")
    finally:
        sys.path.remove(script_directory)


def write_upstream(root: Path, sources: dict[str, str]) -> Path:
    """Write an upstream ``docs/`` tree.

    Parameters
    ----------
    root
        Temporary directory that holds the tree.
    sources
        Source filename and content pairs.

    Returns
    -------
    pathlib.Path
        Directory the sources were written to.
    """
    directory = root / "upstream" / "docs"
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in sources.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return directory


def make_config(
    vendor: types.ModuleType,
    tmp_path: Path,
    *,
    sources: dict[str, str] | None = None,
    mappings: tuple[tuple[str, str], ...] | None = None,
) -> types.SimpleNamespace:
    """Build a valid import description and its consumer directory.

    Parameters
    ----------
    vendor
        Loaded core module.
    tmp_path
        Temporary directory for the upstream and consumer trees.
    sources
        Upstream files, defaulting to two minimal guides.
    mappings
        Filename pairs, defaulting to the two minimal guides.

    Returns
    -------
    types.SimpleNamespace
        ``config`` and the ``consumer`` directory.
    """
    source_directory = write_upstream(
        tmp_path,
        sources
        if sources is not None
        else {
            "users-guide.md": "# Users' guide\n\nText.\n",
            "v0-2-0-migration-guide.md": "# Migration guide\n\nText.\n",
        },
    )
    consumer = tmp_path / "consumer" / "docs"
    consumer.mkdir(parents=True)
    config = vendor.VendorConfig(
        tag="v0.2.0-beta2",
        repository="leynos/cuprum",
        source_directory=source_directory,
        output_directory=consumer,
        mappings=mappings
        if mappings is not None
        else (
            ("users-guide.md", "cuprum-users-guide.md"),
            ("v0-2-0-migration-guide.md", "cuprum-v0-2-0-migration-guide.md"),
        ),
        source_path="docs",
    )
    return types.SimpleNamespace(config=config, consumer=consumer)


def convert_fragment(vendor: types.ModuleType, tmp_path: Path, markdown: str) -> str:
    """Convert one Markdown fragment under a valid configuration.

    Parameters
    ----------
    vendor
        Loaded core module.
    tmp_path
        Temporary directory for the upstream and consumer trees.
    markdown
        Fragment to place below the document's level-one heading.

    Returns
    -------
    str
        Converted document.
    """
    config = make_config(vendor, tmp_path, sources={"users-guide.md": "# Title\n"})
    return vendor.convert(f"# Title\n\n{markdown}\n", config.config, "users-guide.md")


def pinned(path: str, *, tag: str = "v0.2.0-beta2") -> str:
    """Build the blob URL the tool should emit for one source path.

    Parameters
    ----------
    path
        Repository-relative source path.
    tag
        Upstream tag the destination is pinned to.

    Returns
    -------
    str
        Tag-pinned ``blob`` URL.
    """
    return f"https://github.com/leynos/cuprum/blob/{tag}/{path}"


def run_cli(
    *arguments: str,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run the vendoring front end through ``uv``.

    Parameters
    ----------
    arguments
        Command-line arguments after the script path.
    cwd
        Working directory the front end resolves relative paths from.
    env
        Extra environment variables, merged over the current environment.
    timeout
        Seconds to allow the command.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed process with captured output.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the command line")
    environment = None if env is None else {**os.environ, **env}
    return subprocess.run(  # noqa: S603 - fixed argument list, no shell.
        [uv, "run", "--script", str(CLI_PATH), *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
