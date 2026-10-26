"""Exercise Cuprum examples from the published scripting standards."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from textwrap import indent
from types import ModuleType
from typing import Any

from cmd_mox import CmdMox
from cmd_mox.ipc import Invocation
import pytest
import yaml

from tested_example_test_support import load_tested_examples

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTING_STANDARDS_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "scripting-standards.md"
)
EXAMPLES = {
    example.identifier: example
    for example in load_tested_examples(SCRIPTING_STANDARDS_PATH)
}
PARAMETER_EXAMPLES = {
    "cyclopts-parameter-name",
    "cyclopts-parameter-config",
    "cyclopts-parameter-output",
}


def _example_source(identifier: str) -> str:
    """Return the shipped source for one marked scripting-standard example."""
    return EXAMPLES[identifier].body


def _execute_example(
    identifier: str,
    *,
    filename: Path | None = None,
    extra_globals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one shipped Python example in an isolated module namespace."""
    example = EXAMPLES[identifier]
    assert example.language == "python"
    namespace: dict[str, Any] = {
        "__file__": str(filename or SCRIPTING_STANDARDS_PATH),
        "__name__": "tested_scripting_standards_example",
    }
    if extra_globals is not None:
        namespace.update(extra_globals)
    code = compile(example.body, f"{SCRIPTING_STANDARDS_PATH}:{identifier}", "exec")
    exec(code, namespace)
    return namespace


def _install_project_catalogue(
    monkeypatch: pytest.MonkeyPatch, catalogue_namespace: dict[str, Any]
) -> None:
    """Expose the catalogue-definition example through its documented import."""
    project = ModuleType("project")
    project.__path__ = []  # type: ignore[attr-defined]
    utils = ModuleType("project.utils")
    utils.__path__ = []  # type: ignore[attr-defined]
    commands = ModuleType("project.utils.commands")
    commands.GIT = catalogue_namespace["GIT"]
    commands.PROJECT_CATALOGUE = catalogue_namespace["PROJECT_CATALOGUE"]
    project.utils = utils  # type: ignore[attr-defined]
    utils.commands = commands  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "project", project)
    monkeypatch.setitem(sys.modules, "project.utils", utils)
    monkeypatch.setitem(sys.modules, "project.utils.commands", commands)


def test_python_examples_are_syntactically_valid() -> None:
    """All loaded Python examples parse, including the three parameter fragments."""
    for identifier, example in EXAMPLES.items():
        if example.language != "python":
            continue
        source = example.body
        if identifier in PARAMETER_EXAMPLES:
            source = "def documented_parameters(\n" + indent(source, "    ")
            source += "\n):\n    pass\n"
        compile(source, f"{SCRIPTING_STANDARDS_PATH}:{identifier}", "exec")


def test_ci_example_is_valid_yaml_and_maps_inputs() -> None:
    """The published workflow example remains parseable and maps Cyclopts inputs."""
    example = EXAMPLES["ci-build-workflow"]
    assert example.language == "yaml"
    steps = yaml.safe_load(example.body)
    assert steps[0]["name"] == "Build"
    assert steps[0]["env"]["INPUT_BIN_NAME"] == "${{ inputs.bin-name }}"
    assert "uv run" in steps[0]["run"]


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_shared_catalogue_example_runs_a_registered_git_command(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared catalogue resolves the registered program and command result."""
    catalogue_namespace = _execute_example("catalogue-definition")
    _install_project_catalogue(monkeypatch, catalogue_namespace)
    cmd_mox.mock("git").with_args(
        "--no-pager", "log", "-1", "--pretty=%H"
    ).returns(stdout="a1b2c3\n")
    cmd_mox.replay()

    namespace = _execute_example("catalogue-scoped-use")

    cmd_mox.verify()
    assert namespace["last_commit"] == "a1b2c3"


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_capture_output_example_returns_the_successful_stdout(
    cmd_mox: CmdMox, capsys: pytest.CaptureFixture[str]
) -> None:
    """The output example captures and echoes beta2 command output."""
    cmd_mox.mock("git").with_args("status", "--short").returns(
        stdout=" M script.py\n"
    )
    cmd_mox.replay()

    namespace = _execute_example("capture-output")

    cmd_mox.verify()
    assert namespace["result"].ok
    assert namespace["status"] == " M script.py\n"
    assert " M script.py" in capsys.readouterr().out


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_capture_output_example_keeps_nonzero_results_explicit(
    cmd_mox: CmdMox,
) -> None:
    """A completed nonzero command follows the example's exit-code path."""
    cmd_mox.mock("git").with_args("status", "--short").returns(
        exit_code=7, stderr="repository unavailable"
    )
    cmd_mox.replay()

    with pytest.raises(SystemExit) as failure:
        _execute_example("capture-output")

    cmd_mox.verify()
    assert failure.value.code == 7


def test_capture_output_example_surfaces_a_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A registered program absent from PATH raises at launch in beta2."""
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))

    with pytest.raises(FileNotFoundError, match="git"):
        _execute_example("capture-output")


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_execution_context_example_runs_with_cwd_environment_and_stdin(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """The beta2 context and stdin arguments reach both successful commands."""
    def git_handler(invocation: Invocation) -> tuple[str, str, int]:
        if invocation.args == ["var", "GIT_AUTHOR_IDENT"]:
            return "CI <ci@example.org> 123456789 +0000\n", "", 0
        if invocation.args == ["hash-object", "--stdin"]:
            return "123456\n", "", 0
        return "", "unexpected git arguments", 97

    git = cmd_mox.mock("git").times(2).runs(git_handler)
    cmd_mox.replay()

    namespace = _execute_example(
        "execution-context-input",
        filename=tmp_path / "scripts" / "publish.py",
    )

    cmd_mox.verify()
    author_call = next(
        invocation
        for invocation in git.invocations
        if invocation.args == ["var", "GIT_AUTHOR_IDENT"]
    )
    hash_call = next(
        invocation
        for invocation in git.invocations
        if invocation.args == ["hash-object", "--stdin"]
    )
    assert namespace["repo_dir"] == tmp_path.resolve()
    assert author_call.env["GIT_AUTHOR_NAME"] == "CI"
    assert author_call.env["GIT_AUTHOR_EMAIL"] == "ci@example.org"
    assert hash_call.stdin == "release notes\n"
    assert namespace["result"].stdout.startswith("CI <ci@example.org>")
    assert namespace["hashed"].stdout.strip() == "123456"


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_presence_flag_example_builds_the_expected_argv(cmd_mox: CmdMox) -> None:
    """The shipped assertion and command execution preserve Cargo's flag form."""
    cmd_mox.mock("cargo").with_args(
        "build", "--release", "--target=x86_64-unknown-linux-gnu"
    ).returns()
    cmd_mox.replay()

    namespace = _execute_example("presence-flags")

    cmd_mox.verify()
    assert namespace["command"].argv == (
        "build",
        "--release",
        "--target=x86_64-unknown-linux-gnu",
    )


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_pipeline_example_checks_all_stages_and_returns_final_stdout(
    cmd_mox: CmdMox,
) -> None:
    """The pipeline example executes both registered stages and captures grep."""
    cmd_mox.mock("git").with_args(
        "--no-pager", "log", "--oneline"
    ).returns(stdout="a1b2c3 fix observer\n")
    cmd_mox.mock("grep").with_args("fix").returns(stdout="a1b2c3 fix observer\n")
    cmd_mox.replay()

    namespace = _execute_example("pipeline-results")

    cmd_mox.verify()
    assert namespace["result"].ok
    assert namespace["shortlog"] == "a1b2c3 fix observer\n"


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_concurrent_example_runs_bounded_commands_in_submission_order(
    cmd_mox: CmdMox,
) -> None:
    """The beta2 concurrent runner returns both successful commands in order."""
    def cargo_handler(invocation: Invocation) -> tuple[str, str, int]:
        if invocation.args == ["check", "--all-targets"]:
            return "checked", "", 0
        if invocation.args == ["fmt", "--check"]:
            return "formatted", "", 0
        return "", "unexpected cargo arguments", 97

    cargo = cmd_mox.mock("cargo").times(2).runs(cargo_handler)
    cmd_mox.replay()
    namespace = _execute_example("concurrent-commands")

    aggregate = asyncio.run(namespace["run_all"]())

    cmd_mox.verify()
    assert {tuple(invocation.args) for invocation in cargo.invocations} == {
        ("check", "--all-targets"),
        ("fmt", "--check"),
    }
    assert aggregate.ok
    assert len(aggregate.results) == 2
    assert [result.stdout for result in aggregate.results] == ["checked", "formatted"]


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_observer_example_filters_non_exit_events_and_logs_exit(
    cmd_mox: CmdMox,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A real non-exit ExecEvent is ignored before exit-only fields are read."""
    cmd_mox.mock("cargo").with_args("check").returns()
    cmd_mox.replay()
    caplog.set_level(logging.INFO)

    _execute_example("observer-exit")

    cmd_mox.verify()
    records = [record for record in caplog.records if record.msg.startswith("Completed")]
    assert len(records) == 1
    assert records[0].getMessage() == "Completed with exit code 0"


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_cmd_mox_happy_path_example_replays_and_verifies(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """The published cmd-mox happy-path test runs against the beta2 API."""
    namespace = _execute_example("cmd-mox-tests")

    namespace["test_git_tag_happy_path"](cmd_mox, tmp_path)


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_cmd_mox_failure_example_preserves_stderr_and_exit_code(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """The published failure test distinguishes nonzero results from exceptions."""
    namespace = _execute_example("cmd-mox-tests")

    namespace["test_git_tag_failure_surface_error"](cmd_mox, tmp_path)


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_cmd_mox_spy_example_records_passthrough_arguments(
    cmd_mox: CmdMox, tmp_path: Path
) -> None:
    """The published spy example records the real command's single argument."""
    namespace = _execute_example("cmd-mox-spy")

    namespace["test_spy_and_record"](cmd_mox, tmp_path)
