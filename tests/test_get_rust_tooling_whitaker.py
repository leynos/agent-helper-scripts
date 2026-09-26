"""Process-level tests for `get-rust-tooling`'s Whitaker install.

The function under test is extracted from the script and run in Bash with
stubbed `cargo` and `whitaker-installer` on `PATH`. The stubs record their
arguments and exit with configured statuses, so the tests assert the commands
the script builds, never the behaviour of the real tools, and nothing touches a
package manager, the network or the real home directory.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import typing as typ
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "get-rust-tooling"

#: A stub that appends its arguments to a log named after itself and exits
#: with the status in `<NAME>_STATUS`, defaulting to success.
_STUB = """#!/usr/bin/env bash
name="$(basename "$0")"
printf '%s\\n' "$*" >> "$STUB_LOG_DIR/$name.log"
status_var="$(printf '%s' "$name" | tr 'a-z-' 'A-Z_')_STATUS"
exit "${!status_var:-0}"
"""


class Run(typ.NamedTuple):
    """One run of the function and the commands its stubs recorded."""

    completed: subprocess.CompletedProcess[str]
    cargo: list[str]
    installer: list[str]


def _function_source() -> str:
    """Return Bash that defines `install_whitaker_tooling` from the script."""
    return (
        "source <(awk '\n"
        "  /^function install_whitaker_tooling[[:space:]]*[(][)]/ { emit=1 }\n"
        "  emit { print }\n"
        "  emit && /^}[[:space:]]*$/ { exit }\n"
        f"' {shlex.quote(str(SCRIPT))})"
    )


def _log(directory: Path, name: str) -> list[str]:
    """Return the argument lines a stub recorded, or none if it never ran."""
    path = directory / f"{name}.log"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _run(tmp_path: Path, env: dict[str, str] | None = None) -> Run:
    """Run `install_whitaker_tooling` with stubbed tools and *env*."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("cargo", "whitaker-installer"):
        stub = stubs / name
        stub.write_text(_STUB, encoding="utf-8")
        stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    process_env = {
        "HOME": str(home),
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG_DIR": str(tmp_path),
        **(env or {}),
    }
    completed = subprocess.run(  # noqa: S603,S607 - fixed bash argv, no shell or user input.
        ["bash", "--norc", "--noprofile"],
        input=f"set -euo pipefail\n{_function_source()}\ninstall_whitaker_tooling\n",
        cwd=tmp_path,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )
    return Run(completed, _log(tmp_path, "cargo"), _log(tmp_path, "whitaker-installer"))


def test_the_script_calls_the_function() -> None:
    """The function is what the bootstrap runs, not dead code beside it."""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()

    assert "install_whitaker_tooling" in lines


def test_without_whitaker_nothing_is_installed(tmp_path: Path) -> None:
    """Whitaker is opt-in; the default bootstrap never runs its installer."""
    run = _run(tmp_path)

    assert run.completed.returncode == 0, run.completed.stderr
    assert run.cargo == []
    assert run.installer == []


def test_the_default_pins_the_installer_and_refuses_source_builds(
    tmp_path: Path,
) -> None:
    """0.2.9 is installed, and the installer runs with the flag alone."""
    run = _run(tmp_path, {"WITH_WHITAKER": "1"})

    assert run.completed.returncode == 0, run.completed.stderr
    assert run.cargo == ["binstall --locked --no-confirm whitaker-installer@0.2.9"]
    assert run.installer == ["--no-source-fallback"]


def test_an_overridden_version_is_honoured(tmp_path: Path) -> None:
    """A caller may pin a newer installer; the flag stays."""
    run = _run(
        tmp_path, {"WITH_WHITAKER": "1", "WHITAKER_INSTALLER_VERSION": "0.2.10"}
    )

    assert run.cargo == ["binstall --locked --no-confirm whitaker-installer@0.2.10"]
    assert run.installer == ["--no-source-fallback"]


@pytest.mark.parametrize(
    ("experimental", "arguments"),
    [
        pytest.param("1", "--no-source-fallback --experimental", id="on"),
        pytest.param("0", "--no-source-fallback", id="off"),
    ],
)
def test_experimental_lints_are_added_only_on_request(
    tmp_path: Path, experimental: str, arguments: str
) -> None:
    """`--experimental` follows the flag; `--no-source-fallback` never moves."""
    run = _run(
        tmp_path,
        {"WITH_WHITAKER": "1", "WITH_WHITAKER_EXPERIMENTAL": experimental},
    )

    assert run.installer == [arguments]


def test_a_failed_installer_download_warns_and_skips_the_installer(
    tmp_path: Path,
) -> None:
    """Whitaker is optional: a failed download warns, and nothing else runs."""
    run = _run(tmp_path, {"WITH_WHITAKER": "1", "CARGO_STATUS": "1"})

    assert run.completed.returncode == 0, run.completed.stderr
    assert run.installer == []
    assert "Whitaker is not currently available" in run.completed.stdout


def test_a_refused_source_build_warns_and_builds_nothing(tmp_path: Path) -> None:
    """A missing published asset fails the installer, and no build follows.

    The installer exits non-zero when `--no-source-fallback` refuses a source
    build. The bootstrap warns and carries on, and Cargo is never asked to
    install anything but the pinned installer.
    """
    run = _run(tmp_path, {"WITH_WHITAKER": "1", "WHITAKER_INSTALLER_STATUS": "34"})

    assert run.completed.returncode == 0, run.completed.stderr
    assert run.cargo == ["binstall --locked --no-confirm whitaker-installer@0.2.9"]
    assert "Whitaker is not currently available" in run.completed.stdout
