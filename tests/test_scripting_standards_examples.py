"""Keep the scripting standards' executable examples under test.

These tests load marked Python and YAML examples from the shipped Markdown,
then parse the YAML or execute Python examples in isolated namespaces. They
protect the published examples as an executable contract rather than testing
copied snippets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from textwrap import dedent, indent
from typing import Any

from cmd_mox import CmdMox
from cmd_mox.ipc import Invocation
from hypothesis import given, settings, strategies as st
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
CONCURRENT_SCENARIO_ENV = "SCRIPTING_STANDARDS_CONCURRENT_SCENARIO"
CONCURRENT_STATE_ENV = "SCRIPTING_STANDARDS_CONCURRENT_STATE"


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
    assert example.language == "python", (
        f"tested example {identifier!r} must be a Python fence"
    )
    namespace: dict[str, Any] = {
        "__file__": str(filename or SCRIPTING_STANDARDS_PATH),
        "__name__": "tested_scripting_standards_example",
    }
    if extra_globals is not None:
        namespace.update(extra_globals)
    code = compile(example.body, f"{SCRIPTING_STANDARDS_PATH}:{identifier}", "exec")
    exec(code, namespace)
    return namespace


def _install_concurrent_command_stub(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    exit_codes: list[int],
    delays_ms: list[int],
) -> Path:
    """Install a temporary cargo command that records concurrent activity."""
    binary_directory = tmp_path / "bin"
    binary_directory.mkdir(exist_ok=True)
    executable = binary_directory / "cargo"
    executable.write_text(
        f"#!{sys.executable}\n"
        + dedent(
            """\
            import json
            import os
            import sqlite3
            import sys
            import time

            scenario = json.loads(os.environ["SCRIPTING_STANDARDS_CONCURRENT_SCENARIO"])
            state_path = os.environ["SCRIPTING_STANDARDS_CONCURRENT_STATE"]
            command_index = int(sys.argv[2])

            with sqlite3.connect(state_path, timeout=10) as connection:
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE activity SET active = active + 1, peak = "
                    "MAX(peak, active + 1)"
                )
                connection.commit()

            time.sleep(scenario["delays_ms"][command_index] / 1000)
            print(f"result-{command_index}", flush=True)

            with sqlite3.connect(state_path, timeout=10) as connection:
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("UPDATE activity SET active = active - 1")
                connection.commit()

            sys.exit(scenario["exit_codes"][command_index])
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)

    state_path = tmp_path / "concurrent-activity.sqlite3"
    with sqlite3.connect(state_path) as connection:
        connection.execute("DROP TABLE IF EXISTS activity")
        connection.execute(
            "CREATE TABLE activity (active INTEGER NOT NULL, peak INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO activity VALUES (0, 0)")

    monkeypatch.setenv(
        CONCURRENT_SCENARIO_ENV,
        json.dumps({"exit_codes": exit_codes, "delays_ms": delays_ms}),
    )
    monkeypatch.setenv(CONCURRENT_STATE_ENV, str(state_path))
    monkeypatch.setenv(
        "PATH", os.pathsep.join((str(binary_directory), os.environ.get("PATH", "")))
    )
    return state_path


def _run_concurrent_example_batch(
    namespace: dict[str, Any],
    command_count: int,
    *,
    concurrency: int,
    fail_fast: bool,
) -> Any:
    """Run a generated batch with the catalogue and API from the shipped example."""

    async def run_batch() -> Any:
        with namespace["scoped"](catalogue=namespace["CATALOGUE"]):
            cargo = namespace["sh"].make(namespace["CARGO"])
            commands = [cargo("probe", str(index)) for index in range(command_count)]
            config = namespace["ConcurrentConfig"](
                concurrency=concurrency,
                fail_fast=fail_fast,
            )
            return await namespace["run_concurrent"](*commands, config=config)

    return asyncio.run(run_batch())


def _maximum_concurrent_commands(state_path: Path) -> int:
    """Return the peak number of concurrent stub processes for one batch."""
    with sqlite3.connect(state_path) as connection:
        row = connection.execute("SELECT peak FROM activity").fetchone()
    if row is None:
        raise RuntimeError("the concurrent command stub did not record activity")
    return int(row[0])


@st.composite
def _concurrent_batch_scenarios(
    draw: Any,
) -> tuple[list[int], list[int], int]:
    """Generate bounded command batches with varied outcomes and finish order."""
    command_count = draw(st.integers(min_value=1, max_value=4))
    exit_codes = draw(
        st.lists(
            st.integers(min_value=0, max_value=7),
            min_size=command_count,
            max_size=command_count,
        )
    )
    completion_order = draw(st.permutations(tuple(range(command_count))))
    concurrency = draw(st.integers(min_value=1, max_value=command_count))
    completion_ranks = {
        command_index: rank
        for rank, command_index in enumerate(completion_order)
    }
    delays_ms = [completion_ranks[index] * 40 for index in range(command_count)]
    return exit_codes, delays_ms, concurrency


@st.composite
def _fail_fast_batch_scenarios(draw: Any) -> tuple[int, int]:
    """Generate batches with a later command failing before slower work."""
    command_count = draw(st.integers(min_value=2, max_value=4))
    failure_index = draw(st.integers(min_value=1, max_value=command_count - 1))
    return command_count, failure_index


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
    assert example.language == "yaml", "the workflow example must use a YAML fence"
    steps = yaml.safe_load(example.body)
    assert steps[0]["name"] == "Build", "the workflow must start with its Build step"
    assert steps[0]["env"]["INPUT_BIN_NAME"] == "${{ inputs.bin-name }}", (
        "the workflow must map bin-name to INPUT_BIN_NAME"
    )
    assert "uv run" in steps[0]["run"], "the workflow must run the build with uv"


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_shared_catalogue_example_runs_a_registered_git_command(
    cmd_mox: CmdMox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The shared catalogue resolves the registered program and command result."""
    package_path = tmp_path / "project"
    utils_path = package_path / "utils"
    utils_path.mkdir(parents=True)
    (package_path / "__init__.py").write_text("", encoding="utf-8")
    (utils_path / "__init__.py").write_text("", encoding="utf-8")
    (utils_path / "commands.py").write_text(
        _example_source("catalogue-definition") + "\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    cmd_mox.mock("git").with_args(
        "--no-pager", "log", "-1", "--pretty=%H"
    ).returns(stdout="a1b2c3\n")
    cmd_mox.replay()

    namespace = _execute_example("catalogue-scoped-use")

    cmd_mox.verify()
    assert namespace["last_commit"] == "a1b2c3", (
        "the catalogue-scoped example must capture the registered commit hash"
    )


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
    assert namespace["result"].ok, "the successful status command must be ok"
    assert namespace["status"] == " M script.py\n", (
        "the output example must preserve the captured status"
    )
    assert " M script.py" in capsys.readouterr().out, (
        "the output example must echo the captured status"
    )


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
    assert failure.value.code == 7, "the example must preserve the command exit code"


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
    assert namespace["repo_dir"] == tmp_path.resolve(), (
        "the context example must resolve the repository from its script path"
    )
    assert author_call.env["GIT_AUTHOR_NAME"] == "CI", (
        "the scoped environment must set the Git author name"
    )
    assert author_call.env["GIT_AUTHOR_EMAIL"] == "ci@example.org", (
        "the scoped environment must set the Git author email"
    )
    assert hash_call.stdin == "release notes\n", (
        "the context example must pass release notes to git hash-object"
    )
    assert namespace["result"].stdout.startswith("CI <ci@example.org>"), (
        "the author-ident command must return the scoped identity"
    )
    assert namespace["hashed"].stdout.strip() == "123456", (
        "the hash-object command must return its captured hash"
    )


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
    ), "presence flags must be passed as separate argv entries"


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
    assert namespace["result"].ok, "both pipeline stages must succeed"
    assert namespace["shortlog"] == "a1b2c3 fix observer\n", (
        "the pipeline must return the final stage's captured stdout"
    )


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
    }, "the example must launch both registered Cargo checks"
    assert aggregate.ok, "both successful commands must produce an ok aggregate"
    assert len(aggregate.results) == 2, "the aggregate must contain both results"
    assert [result.stdout for result in aggregate.results] == [
        "checked",
        "formatted",
    ], "concurrent results must retain command submission order"


@settings(max_examples=10, derandomize=True, deadline=None)
@given(scenario=_concurrent_batch_scenarios())
def test_concurrent_example_generated_batches_keep_order_and_bounds(
    tmp_path_factory: pytest.TempPathFactory,
    scenario: tuple[list[int], list[int], int],
) -> None:
    """Bounded Hypothesis cases cover batch sizes, completion orders and outcomes."""
    exit_codes, delays_ms, concurrency = scenario
    tmp_path = tmp_path_factory.mktemp("concurrent-command-batch")
    with pytest.MonkeyPatch.context() as monkeypatch:
        state_path = _install_concurrent_command_stub(
            tmp_path,
            monkeypatch,
            exit_codes=exit_codes,
            delays_ms=delays_ms,
        )
        namespace = _execute_example("concurrent-commands")
        aggregate = _run_concurrent_example_batch(
            namespace,
            len(exit_codes),
            concurrency=concurrency,
            fail_fast=False,
        )

        expected_failures = tuple(
            index for index, exit_code in enumerate(exit_codes) if exit_code != 0
        )
        assert aggregate.submission_indices == tuple(range(len(exit_codes))), (
            "collect-all results must preserve every command's submission index"
        )
        assert [result.stdout.strip() for result in aggregate.results] == [
            f"result-{index}" for index in range(len(exit_codes))
        ], "generated completion orders must not reorder the results"
        assert aggregate.failures == expected_failures, (
            "failure positions must match the generated non-zero outcomes"
        )
        assert aggregate.failure_submission_indices == expected_failures, (
            "each generated failure must map back to its submitted command"
        )
        assert aggregate.ok is (not expected_failures), (
            "the aggregate must fail exactly when a command exits non-zero"
        )
        assert _maximum_concurrent_commands(state_path) <= concurrency, (
            "generated command batches must obey the configured concurrency bound"
        )


@settings(max_examples=5, derandomize=True, deadline=None)
@given(scenario=_fail_fast_batch_scenarios())
def test_concurrent_example_fail_fast_maps_compacted_results_to_submissions(
    tmp_path_factory: pytest.TempPathFactory,
    scenario: tuple[int, int],
) -> None:
    """Generated fail-fast batches map the surviving result to its input index."""
    command_count, failure_index = scenario
    exit_codes = [0] * command_count
    exit_codes[failure_index] = 7
    delays_ms = [2000] * command_count
    delays_ms[failure_index] = 0
    tmp_path = tmp_path_factory.mktemp("fail-fast-command-batch")

    with pytest.MonkeyPatch.context() as monkeypatch:
        state_path = _install_concurrent_command_stub(
            tmp_path,
            monkeypatch,
            exit_codes=exit_codes,
            delays_ms=delays_ms,
        )
        namespace = _execute_example("concurrent-commands")
        aggregate = _run_concurrent_example_batch(
            namespace,
            command_count,
            concurrency=command_count,
            fail_fast=True,
        )

        assert not aggregate.ok, "a generated non-zero exit must make the aggregate fail"
        assert aggregate.submission_indices == (failure_index,), (
            "the surviving result must map to its original submission index"
        )
        assert aggregate.failures == (0,), (
            "the failed result occupies position zero after earlier work is cancelled"
        )
        assert aggregate.failure_submission_indices == (failure_index,), (
            "the compacted failure must map back to the failing command"
        )
        assert aggregate.results[0].exit_code == 7, (
            "the partial failure result must preserve its non-zero exit code"
        )
        assert _maximum_concurrent_commands(state_path) <= command_count, (
            "fail-fast execution must obey the generated concurrency limit"
        )


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
    assert len(records) == 1, "only the exit event must emit a completion record"
    assert records[0].getMessage() == "Completed with exit code 0", (
        "the exit event must be logged with its exit code"
    )


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
