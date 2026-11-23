"""Keep the scripting standards' Cyclopts JSON examples under test.

The published Cyclopts reference scripts and environment test share one
output contract: a JSON object on standard output. These tests execute the
shipped fences and prove that the documented version assertion accepts the
documented version and rejects a mismatch.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from scripting_standards_example_support import (
    example_source,
    execute_example,
    execute_source,
)

DRY_RUN_SCRIPT_EXAMPLES = ("cyclopts-cli", "reference-script")


def _clear_input_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove inherited ``INPUT_*`` variables so an example starts clean."""
    for name in tuple(os.environ):
        if name.startswith("INPUT_"):
            monkeypatch.delenv(name, raising=False)


def _install_scripts_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> types.ModuleType:
    """Register an extracted reference script as the ``scripts.package`` module."""
    scripts_package = types.ModuleType("scripts")
    scripts_package.__path__ = []
    module = types.ModuleType("scripts.package")
    module.__file__ = str(tmp_path / "scripts" / "package.py")
    execute_source(
        source,
        filename=tmp_path / "scripts" / "package.py",
        namespace=module.__dict__,
    )
    monkeypatch.setitem(sys.modules, "scripts", scripts_package)
    monkeypatch.setitem(sys.modules, "scripts.package", module)
    return module


class _VersionOverrideProxy:
    """Forward monkeypatch calls while forcing ``INPUT_VERSION``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, version: str) -> None:
        """Wrap ``monkeypatch`` and record the version to substitute."""
        self._monkeypatch = monkeypatch
        self._version = version

    def setenv(self, name: str, value: str) -> None:
        """Forward ``setenv``, substituting the forced version."""
        if name == "INPUT_VERSION":
            value = self._version
        self._monkeypatch.setenv(name, value)

    def __getattr__(self, name: str) -> Any:
        """Forward any other attribute to the wrapped fixture."""
        return getattr(self._monkeypatch, name)


@pytest.mark.parametrize(
    "case",
    tuple(
        pytest.param(
            (identifier, version),
            id=f"{identifier}-{version}",
        )
        for identifier in DRY_RUN_SCRIPT_EXAMPLES
        for version in ("1.2.3", "9.9.9")
    ),
)
def test_reference_scripts_emit_json_with_the_reported_version(
    case: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both reference scripts report the exact version they are given as JSON."""
    identifier, version = case
    _clear_input_environment(monkeypatch)
    monkeypatch.setenv("INPUT_BIN_NAME", "demo")
    monkeypatch.setenv("INPUT_VERSION", version)
    outdir = tmp_path / "out"

    namespace = execute_example(
        identifier,
        filename=tmp_path / "scripts" / "package.py",
    )
    namespace["app"](
        ["--dry-run", "--outdir", str(outdir)],
        result_action="return_value",
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == version, (
        "the script output must propagate the configured version exactly"
    )
    assert not outdir.exists(), "dry-run must not create the output directory"


def _load_published_environment_test(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Any:
    """Prepare the shipped environment test against the reference script."""
    _clear_input_environment(monkeypatch)
    _install_scripts_package(
        tmp_path,
        monkeypatch,
        example_source("reference-script"),
    )
    return execute_example("pytest-environment")["test_reads_env_and_defaults"]


def test_published_environment_example_accepts_the_reported_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The shipped environment test passes for the documented happy path."""
    published_test = _load_published_environment_test(monkeypatch, tmp_path)

    published_test(monkeypatch, tmp_path, capsys)


def test_published_environment_example_rejects_a_different_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The shipped environment test fails when the reported version differs."""
    published_test = _load_published_environment_test(monkeypatch, tmp_path)
    proxy = _VersionOverrideProxy(monkeypatch, "9.9.9")

    with pytest.raises(AssertionError):
        published_test(proxy, tmp_path, capsys)