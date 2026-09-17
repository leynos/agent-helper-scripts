"""Shared fixtures and doubles for the gate runner's fail-closed tests.

The runner and the discovery layer it composes are loaded from ``scripts/`` by
path, because that directory is not a package on the import path. A command
double then stands in for the tool each gate drives.

A double is reached through ``PATH``, which is what the gate's own
``subprocess.run`` consults, so these tests exercise the same resolution the
real gate uses rather than a substituted one.
"""

from collections.abc import Iterator
import importlib
from pathlib import Path
import sys
import types

import pytest

from spelling_policy_support import SCRIPTS_PATH

__all__ = ("GateModules", "gate_fixture", "write_markdown_tree")


class GateModules:
    """Hold the runner under test and the discovery layer it composes.

    Attributes
    ----------
    runner
        Loaded ``gate_runner`` module.
    discovery
        Loaded ``gate_discovery`` module.
    """

    def __init__(self, runner: types.ModuleType, discovery: types.ModuleType) -> None:
        self.runner = runner
        self.discovery = discovery


@pytest.fixture(name="gate", scope="module")
def gate_fixture() -> Iterator[GateModules]:
    """Load the runner and its discovery sibling through the runtime path."""
    script_directory = str(SCRIPTS_PATH)
    sys.path.insert(0, script_directory)
    try:
        # The modules stay in ``sys.modules`` after the directory leaves the
        # path, so a second module-scoped request reuses the loaded copies
        # instead of re-executing them against a shortened path.
        yield GateModules(
            importlib.import_module("gate_runner"),
            importlib.import_module("gate_discovery"),
        )
    finally:
        sys.path.remove(script_directory)


def write_markdown_tree(root: Path, names: tuple[str, ...]) -> tuple[Path, ...]:
    """Write one Markdown file per repository-relative name.

    Parameters
    ----------
    root
        Directory to write into.
    names
        Repository-relative file names, including any subdirectory.

    Returns
    -------
    tuple[Path, ...]
        The repository-relative paths that were written, in sorted order.
    """
    written: list[Path] = []
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {target.stem}\n", encoding="utf-8")
        written.append(Path(name))
    return tuple(sorted(written))
