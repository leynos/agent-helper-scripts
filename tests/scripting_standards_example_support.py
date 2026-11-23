"""Shared loading helpers for the scripting standards' tested examples.

The published guide marks each executable fence with an identifier. These
helpers load those fences from the shipped Markdown and execute the Python
ones in an isolated module namespace, so the example tests exercise the
document rather than a copied snippet.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any

from tested_example_test_support import load_tested_examples

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTING_STANDARDS_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "scripting-standards.md"
)
EXAMPLES = {
    example.identifier: example
    for example in load_tested_examples(SCRIPTING_STANDARDS_PATH)
}


def example_source(identifier: str) -> str:
    """Return the shipped source for one marked scripting-standard example."""
    return EXAMPLES[identifier].body


def execute_source(
    source: str,
    *,
    filename: Path,
    namespace: dict[str, Any],
    module_filename: str = "example.py",
) -> None:
    """Load extracted source as a file-backed module into ``namespace``.

    The source is a fence from a repository-owned guide, read at test time,
    not untrusted input. Writing it to a temporary module and loading that
    module through ``importlib`` avoids direct ``exec`` while preserving the
    caller's ``__file__``, ``__name__`` and other globals. ``module_filename``
    names the temporary module so tracebacks retain the example identifier.
    """
    with tempfile.TemporaryDirectory() as directory:
        module_path = Path(directory) / module_filename
        module_path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(
            str(namespace.get("__name__", "tested_example")),
            module_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load example source from {filename}")
        module = importlib.util.module_from_spec(spec)
        module.__dict__.update(namespace)
        spec.loader.exec_module(module)
        namespace.update(module.__dict__)


def execute_example(
    identifier: str,
    *,
    filename: Path | None = None,
    extra_globals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one shipped Python example in an isolated module namespace."""
    example = EXAMPLES[identifier]
    assert example.language == "python", (
        f"tested example {identifier!r} must be a Python fence"
    )
    example_filename = filename or SCRIPTING_STANDARDS_PATH
    namespace: dict[str, Any] = {
        "__file__": str(example_filename),
        "__name__": "tested_scripting_standards_example",
    }
    if extra_globals is not None:
        namespace.update(extra_globals)
    execute_source(
        example.body,
        filename=example_filename,
        namespace=namespace,
        module_filename=f"{identifier}.py",
    )
    return namespace