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

from gate_runner_test_support import (
    GIT,
    SHARED_DICTIONARY_PATH,
    GateModules,
    git_handler,
    write_markdown_tree,
)
from typos_rollout_test_support import REPOSITORY_ROOT

if typ.TYPE_CHECKING:
    from cmd_mox.ipc import Invocation

skip_if_unsupported()

SCANNER = "stub-scanner"
LINTER = "stub-linter"
VALIDATOR = "stub-validator"
CLI_PATH = REPOSITORY_ROOT / "scripts" / "gate_runner_cli.py"
NOT_A_REPOSITORY = "fatal: not a git repository (or any of the parent directories)"
# Split so the repository's own spelling gate does not flag this fixture; the
# compound it builds is one the shipped policy prohibits.
HYPHENATED_HANDWRITTEN = "hand" + "-written"
SAMPLE_FINDING = f"README.md:1:8: {HYPHENATED_HANDWRITTEN} -> handwritten"


def silent(_invocation: Invocation) -> tuple[str, str, int]:
    """Answer a doubled tool that reports nothing."""
    return ("", "", 0)


def test_the_gate_fails_before_the_scanner_when_nothing_is_tracked(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """An empty producer fails the gate instead of scanning an empty list."""
    scanner = cmd_mox.spy(SCANNER).runs(silent)
    cmd_mox.spy(GIT).runs(git_handler(listed=""))

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.runner.spelling(
            repository=tmp_path,
            source=SHARED_DICTIONARY_PATH,
            typos=SCANNER,
        )

    assert "found no Git-tracked files" in str(failure.value)
    assert isinstance(failure.value, gate.runner.GATE_ERRORS), (
        "a refusal the command line does not catch surfaces as a traceback "
        "instead of the one diagnostic line the recipe reports"
    )
    assert scanner.call_count == 0, (
        "the scanner ran over a list the gate should have refused; a green "
        "scan of nothing is the failure this gate exists to prevent"
    )


def test_the_gate_fails_before_the_scanner_when_the_producer_fails(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """A producer that exits non-zero fails the gate with its own diagnostic."""
    scanner = cmd_mox.spy(SCANNER).runs(silent)
    cmd_mox.spy(GIT).runs(git_handler(status=128, diagnostic=NOT_A_REPOSITORY))

    with pytest.raises(gate.discovery.GateDiscoveryError) as failure:
        gate.runner.spelling(
            repository=tmp_path,
            source=SHARED_DICTIONARY_PATH,
            typos=SCANNER,
        )

    assert NOT_A_REPOSITORY in str(failure.value), (
        "the failure must name what the producer reported, not the gate's "
        "next step, or a broken producer reads as a policy problem"
    )
    assert scanner.call_count == 0, scanner.invocations


def test_the_scanner_runs_once_over_every_tracked_file(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """The whole list reaches one scanner run, in a stable order."""
    written = write_markdown_tree(tmp_path, ("README.md", "docs/guide.md"))
    cmd_mox.spy(GIT).runs(
        git_handler(listed="\0".join(path.as_posix() for path in written) + "\0"),
    )
    scanner = cmd_mox.spy(SCANNER).runs(silent)

    gate.runner.spelling(
        repository=tmp_path,
        source=SHARED_DICTIONARY_PATH,
        typos=SCANNER,
    )

    assert scanner.call_count == 1, scanner.invocations
    assert list(scanner.invocations[0].args) == [
        "--config",
        "typos.toml",
        "--force-exclude",
        *(path.as_posix() for path in written),
    ], "the scanner did not receive the generated config and every file"


def test_the_scanner_status_is_the_gate_status(
    cmd_mox: CmdMox,
    gate: GateModules,
    tmp_path: Path,
) -> None:
    """Findings fail the gate with the scanner's own status."""
    written = write_markdown_tree(tmp_path, ("README.md",))
    cmd_mox.spy(GIT).runs(
        git_handler(listed="\0".join(path.as_posix() for path in written) + "\0"),
    )
    scanner = cmd_mox.spy(SCANNER).runs(
        lambda _invocation: (f"{SAMPLE_FINDING}\n", "", 2),
    )

    with pytest.raises(SystemExit) as exit_info:
        gate.runner.spelling(
            repository=tmp_path,
            source=SHARED_DICTIONARY_PATH,
            typos=SCANNER,
        )

    assert exit_info.value.code == 2, (
        "the recipe must report what the scanner reported, not a status of "
        "its own invention"
    )
    assert scanner.call_count == 1, scanner.invocations


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
        path.as_posix() for path in written
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

    assert list(linter.invocations[0].args) == ["README.md"], (
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
        *(path.as_posix() for path in written),
    ]


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
        assert "gate_runner_cli.py" in body, (
            f"the {target} recipe bypasses the shared gate runner: {body}"
        )


def test_the_default_scanner_matches_the_makefile_version_pin(
    gate: GateModules,
) -> None:
    """The runner's default scanner cannot drift from the version that ships."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TYPOS_VERSION\s*\?=\s*(\S+)", makefile, re.MULTILINE)
    assert match is not None, "Makefile does not pin a typos version"

    assert gate.runner.DEFAULT_TYPOS == f"uv tool run typos@{match.group(1)}", (
        "the runner's default scanner and the Makefile pin disagree"
    )


@pytest.mark.slow
def test_the_command_line_reaches_every_gate_the_recipes_run() -> None:
    """The front end the recipes call registers all three gates."""
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
    for command in ("markdownlint", "nixie", "spelling"):
        assert command in result.stdout, (
            f"the command line does not expose {command}: {result.stdout}"
        )
