"""Contract tests for the gates the shared recipes run.

Each gate lists its own files and runs its tool once over the whole list. That
is what replaces the recipes' pipelines, so these tests pin the two outcomes a
pipeline could not distinguish: a gate whose producer fails or lists nothing
must fail before its tool is invoked, and a gate whose tool reports findings
must exit with that tool's status.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import typing as typ

from cmd_mox import CmdMox, skip_if_unsupported
import pytest

from gate_runner_test_support import GateModules, write_markdown_tree
from spelling_policy_support import REPOSITORY_ROOT

if typ.TYPE_CHECKING:
    from cmd_mox.ipc import Invocation

skip_if_unsupported()

LINTER = "stub-linter"
VALIDATOR = "stub-validator"
CLI_PATH = REPOSITORY_ROOT / "scripts" / "gate_runner_cli.py"
# A name Git tracks and the walk reports unchanged, but which a tool reads as
# an option unless the operand list is introduced by an option terminator.
DASH_FILE = "-guide.md"


def silent(_invocation: Invocation) -> tuple[str, str, int]:
    """Answer a doubled tool that reports nothing."""
    return ("", "", 0)


def test_a_missing_tool_is_reported_as_not_installed(
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A gate names the tool it cannot find instead of failing obscurely."""
    write_markdown_tree(tmp_path, ("README.md",))

    with pytest.raises(gate.runner.GateExecutionError) as failure:
        gate.runner.markdownlint(
            repository=tmp_path,
            linter="markdownlint-not-installed",
        )

    assert "'markdownlint-not-installed' is required, but not installed" in str(
        failure.value
    )
    assert isinstance(failure.value, gate.runner.GATE_ERRORS), (
        "a missing tool must reach the command line's diagnostic boundary"
    )


def test_markdown_gate_fails_before_the_linter_when_no_markdown_exists(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A tree without Markdown fails the gate instead of passing vacuously."""
    (tmp_path / "notes.txt").write_text("not Markdown\n", encoding="utf-8")
    linter = cmd_mox.spy(LINTER).runs(silent)

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.runner.markdownlint(repository=tmp_path, linter=LINTER)

    assert "found no Markdown files" in str(failure.value)
    assert linter.call_count == 0, linter.invocations


def test_markdown_gate_lints_every_file_in_one_invocation(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The linter receives the discovered list rather than a glob."""
    written = write_markdown_tree(tmp_path, ("README.md", "docs/guide.md"))
    linter = cmd_mox.spy(LINTER).runs(silent)

    gate.runner.markdownlint(repository=tmp_path, linter=LINTER)

    assert linter.call_count == 1, linter.invocations
    assert list(linter.invocations[0].args) == [
        "--",
        *(path.as_posix() for path in written),
    ], "the linter did not receive every discovered Markdown file"


def test_markdown_gate_honours_the_exclusions_it_is_given(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A caller's exclusions reach the walk rather than being ignored."""
    write_markdown_tree(tmp_path, ("README.md", "vendor/pkg/README.md"))
    linter = cmd_mox.spy(LINTER).runs(silent)

    gate.runner.markdownlint(
        repository=tmp_path,
        linter=LINTER,
        exclude=("vendor",),
    )

    assert list(linter.invocations[0].args) == ["--", "README.md"], (
        "an excluded tree was linted anyway"
    )


def test_nixie_gate_disables_the_sandbox_and_names_every_file(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The validator keeps the container-compatible flags and the full list."""
    written = write_markdown_tree(tmp_path, ("README.md", "docs/guide.md"))
    validator = cmd_mox.spy(VALIDATOR).runs(silent)

    gate.runner.nixie(repository=tmp_path, validator=VALIDATOR)

    assert validator.call_count == 1, validator.invocations
    assert list(validator.invocations[0].args) == [
        "--no-sandbox",
        "--",
        *(path.as_posix() for path in written),
    ]


def test_the_markdown_gates_terminate_options_before_a_dash_prefixed_name(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """Both walks hand a dash-prefixed name where each tool expects a file."""
    written = write_markdown_tree(tmp_path, (DASH_FILE,))
    linter = cmd_mox.spy(LINTER).runs(silent)
    validator = cmd_mox.spy(VALIDATOR).runs(silent)

    gate.runner.markdownlint(repository=tmp_path, linter=LINTER)
    gate.runner.nixie(repository=tmp_path, validator=VALIDATOR)

    assert list(linter.invocations[0].args) == [
        "--",
        *(path.as_posix() for path in written),
    ], "markdownlint-cli2 was handed a name it reads as an option"
    assert list(validator.invocations[0].args) == [
        "--no-sandbox",
        "--",
        *(path.as_posix() for path in written),
    ], "nixie was handed a name it reads as an option"


def recipes(makefile: str) -> dict[str, str]:
    """Return each target's recipe body, keyed by target name.

    Parameters
    ----------
    makefile
        Makefile text to read.

    Returns
    -------
    dict[str, str]
        Recipe lines, joined, for every target that has one.
    """
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in makefile.splitlines():
        if line.startswith("\t"):
            if current is not None:
                current.append(line)
            continue
        current = None
        declared = re.match(r"^([A-Za-z0-9_.-]+):", line)
        if declared:
            current = found.setdefault(declared.group(1), [])
    return {target: "\n".join(lines) for target, lines in found.items()}


def test_no_gate_recipe_pipes_a_producer_into_its_tool() -> None:
    """Each gate is one command, so no producer's status can be discarded.

    A pipeline reports the last command's status. Without ``pipefail``, a
    producer that fails or matches nothing leaves the checker with an empty
    list, and ``xargs -r`` exits zero without running it: the gate passes
    having examined no file, which is the defect this runner replaces.
    """
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    recipes_by_target = recipes(makefile)

    for target in ("markdownlint", "nixie", "spelling"):
        body = recipes_by_target.get(target)
        assert body, f"the Makefile has no recipe for {target}"
        assert "|" not in body, (
            f"the {target} recipe pipes a producer into its tool, so a failing "
            f"producer cannot fail the gate: {body}"
        )
        assert "xargs" not in body, (
            f"the {target} recipe funnels files through xargs, which exits zero "
            f"on no input: {body}"
        )
    for target in ("markdownlint", "nixie"):
        assert "gate_runner_cli.py" in recipes_by_target[target], (
            f"the {target} recipe bypasses the shared gate runner"
        )
    # The spelling gate is not this repository's code to run: the pinned
    # builder discovers its own file list, runs Typos, and enforces the phrase
    # corrections. The recipe therefore names the builder variable and nothing
    # else, and that variable pins a released tag.
    assert "$(TYPOS_CONFIG_BUILDER) gate" in recipes_by_target["spelling"], (
        "the spelling recipe no longer calls the pinned builder"
    )
    assert re.search(
        r"^TYPOS_CONFIG_BUILDER_VERSION\s*\?=\s*v\d+\.\d+\.\d+$",
        makefile,
        re.MULTILINE,
    ), "the builder is not pinned to a released tag"


def test_the_spelling_recipe_gates_this_checkout_against_its_own_dictionary() -> None:
    """The recipe names the working-copy source and the whole tracked tree.

    The arguments are the gate's contract: a pull request that edits the shared
    dictionary must be checked against the file it proposes rather than the
    published copy, and over every tracked file rather than the diff.
    """
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = recipes(makefile)["spelling"]
    command = " ".join(
        line.strip().removesuffix("\\").strip() for line in recipe.splitlines()
    )

    assert "--repository ." in command, (
        f"the spelling recipe does not gate this checkout: {command}"
    )
    assert "--source data/typos-oxendict-base.toml" in command, (
        "the spelling recipe gates against a source other than the working-copy "
        f"dictionary: {command}"
    )
    assert "--scope all" in command, (
        f"the spelling recipe narrows the scan below the tracked tree: {command}"
    )
    version = re.search(
        r"^TYPOS_CONFIG_BUILDER_VERSION\s*\?=\s*(v\d+\.\d+\.\d+)$",
        makefile,
        re.MULTILINE,
    )
    assert version is not None, "the builder is not pinned to a released tag"
    assert "@$(TYPOS_CONFIG_BUILDER_VERSION)" in makefile, (
        "the pinned tag does not reach the builder invocation"
    )


@pytest.mark.slow
def test_the_command_line_reaches_every_gate_the_recipes_run() -> None:
    """The front end the recipes call registers both Markdown gates."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the gate command line")
    result = subprocess.run(
        [uv, "run", "--script", str(CLI_PATH), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    for command in ("markdownlint", "nixie"):
        assert command in result.stdout, (
            f"the command line does not expose {command}: {result.stdout}"
        )


def test_a_multi_token_tool_is_split_into_its_executable_and_arguments(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A configured tool is a command line, exactly as the scanner's is.

    A consumer points the recipe at an override such as
    ``MDLINT='bunx markdownlint-cli2'``. Read as one name, that override is
    looked up on ``PATH`` whole and the gate refuses a linter that is in fact
    installed.
    """
    written = write_markdown_tree(tmp_path, ("README.md",))
    linter = cmd_mox.spy(LINTER).runs(silent)

    gate.runner.markdownlint(
        repository=tmp_path,
        linter=f"{LINTER} --config 'my config.jsonc'",
    )

    assert list(linter.invocations[0].args) == [
        "--config",
        "my config.jsonc",
        "--",
        *(path.as_posix() for path in written),
    ], "the runner treated the configured command line as one executable name"


def test_a_tool_the_operating_system_refuses_to_start_is_a_gate_error(
    gate: GateModules,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused start is reported as the gate failing to run.

    A gate names every file on one command line, so a list long enough for
    ``execve`` to refuse it is the realistic trigger here; a real argument list
    that long is not portable, so the refusal is raised in its place.
    """
    write_markdown_tree(tmp_path, ("README.md",))

    def refuse(*_args: object, **_kwargs: object) -> None:
        """Fail the way an oversized argument list does."""
        raise OSError(7, "Argument list too long")

    monkeypatch.setattr(gate.runner.subprocess, "run", refuse)

    with pytest.raises(gate.runner.GateExecutionError) as failure:
        gate.runner.markdownlint(repository=tmp_path, linter="/bin/true")

    assert "could not run" in str(failure.value), (
        "the operating system's refusal must reach the caller as a gate "
        "diagnostic rather than as an uncaught error"
    )


@pytest.mark.slow
def test_the_command_line_reports_a_failure_as_one_diagnostic(
    tmp_path: Path,
) -> None:
    """A gate failure leaves the front end as one line, not a traceback."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the gate command line")
    result = subprocess.run(
        [
            uv,
            "run",
            "--script",
            str(CLI_PATH),
            "markdownlint",
            "--repository",
            str(tmp_path),
            "--linter",
            "true",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 1, (result.returncode, result.stderr)
    assert "gate_runner: error:" in result.stderr, (
        "the failure did not reach the caller as the gate's own diagnostic"
    )
    assert "Traceback" not in result.stderr, (
        "a gate that finds no file must not report a stack trace"
    )
