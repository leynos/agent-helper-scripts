"""Tests for the Markdown lint gate and its Makefile wiring."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
LINT_SCRIPT = REPO_ROOT / "markdownlint"
LINT_CONFIG = REPO_ROOT / ".markdownlint-cli2.jsonc"
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Rules kept disabled against the shared template, each of which must carry its
# rationale next to the entry so the deviation is a decision rather than drift.
DEVIATION_RULES = ("MD024", "MD033", "MD036")

DEFAULT_GLOB = "**/*.md"


def strip_jsonc_comments(text: str) -> str:
    """Remove the whole-line comments the configuration files keep.

    Parameters
    ----------
    text
        JSON-with-comments document.

    Returns
    -------
    str
        The same document as plain JSON.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def make_stub(directory: Path) -> Path:
    """Write an executable stand-in for markdownlint-cli2.

    The stub appends its arguments, one per line, to the file named by the
    ``MDLINT_STUB_RECORD`` environment variable, and copies the configuration
    named by ``--config`` to ``MDLINT_STUB_SNAPSHOT`` when that is set.
    Recording the arguments lets the tests assert what the gate asked the
    linter to read without running it.

    Parameters
    ----------
    directory
        Directory to create the stub in.

    Returns
    -------
    pathlib.Path
        Path to the executable stub.
    """
    stub = directory / "markdownlint-cli2-stub"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "${MDLINT_STUB_RECORD}"\n'
        'if [[ "${1:-}" == "--config" && -n "${MDLINT_STUB_SNAPSHOT:-}" ]]; then\n'
        '  cp "${2}" "${MDLINT_STUB_SNAPSHOT}"\n'
        "fi\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def run_lint_script(
    stub: Path,
    record: Path,
    *args: str,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
) -> list[str]:
    """Run the lint script against a recording stub.

    Parameters
    ----------
    stub
        Executable standing in for markdownlint-cli2.
    record
        File the stub writes its arguments to.
    *args
        Arguments to pass to the lint script.
    cwd
        Working directory for the run; the repository root when omitted.
    environment
        Extra environment variables for the run.

    Returns
    -------
    list[str]
        Arguments the script forwarded to the linter.

    Side Effects
    ------------
    Starts a subprocess and writes the recorded arguments to ``record``.
    """
    run_environment = os.environ.copy()
    run_environment["MDLINT_BIN"] = stub.as_posix()
    run_environment["MDLINT_STUB_RECORD"] = record.as_posix()
    if environment:
        run_environment.update(environment)
    completed = subprocess.run(  # noqa: S603,S607 - controlled args, shell=False.
        [LINT_SCRIPT.as_posix(), *args],
        cwd=cwd or REPO_ROOT,
        env=run_environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return record.read_text(encoding="utf-8").split()


def run_make(*args: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run make from the repository root.

    Parameters
    ----------
    *args
        Make arguments to pass after the executable name.
    environment
        Extra environment variables for the run.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed make process with captured output.

    Side Effects
    ------------
    Starts a subprocess in the repository root.
    """
    run_environment = os.environ.copy()
    if environment:
        run_environment.update(environment)
    return subprocess.run(  # noqa: S603,S607 - controlled args, shell=False, repo-root make lookup.
        ["make", *args],
        cwd=REPO_ROOT,
        env=run_environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def load_lint_config() -> dict[str, object]:
    """Parse the JSON-with-comments lint configuration.

    Returns
    -------
    dict[str, object]
        Parsed configuration document.

    Notes
    -----
    Only whole-line comments are stripped, which is how the configuration
    file keeps them.
    """
    return json.loads(strip_jsonc_comments(LINT_CONFIG.read_text(encoding="utf-8")))


def makefile_target_prerequisites(target: str) -> list[str]:
    """List the prerequisites declared for a Makefile target.

    Parameters
    ----------
    target
        Target name to look up.

    Returns
    -------
    list[str]
        Whitespace-separated prerequisites of the target.

    Raises
    ------
    AssertionError
        If the Makefile does not declare the target.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(target)}:([^\n]*)$", makefile, re.MULTILINE)
    assert match, f"Makefile does not declare the {target} target"
    return match.group(1).split()


def test_lint_script_is_executable() -> None:
    """The lint script carries the executable bit its callers rely on."""
    mode = LINT_SCRIPT.stat().st_mode
    assert mode & 0o111, "markdownlint is not executable; callers would need bash"


def test_bare_invocation_lints_every_markdown_file(tmp_path: Path) -> None:
    """A path-less run is widened to the tree instead of linting nothing."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
    )

    assert arguments == [DEFAULT_GLOB], (
        "a bare invocation must name a glob, or markdownlint-cli2 reports a "
        f"clean pass over zero files; got {arguments}"
    )


def test_selected_paths_are_not_widened(tmp_path: Path) -> None:
    """An explicit path narrows the scan to that path."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        "docs/developers-guide.md",
    )

    assert arguments == ["docs/developers-guide.md"], arguments


def test_option_only_invocation_still_lints_the_tree(tmp_path: Path) -> None:
    """Options are forwarded and the scan is still widened."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        "--fix",
    )

    assert arguments == ["--fix", DEFAULT_GLOB], arguments


def test_repository_without_a_config_uses_the_bundled_one(tmp_path: Path) -> None:
    """A consumer repository falls back to the configuration shipped with the script."""
    snapshot = tmp_path / "bundled-config.jsonc"
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        cwd=tmp_path,
        environment={"MDLINT_STUB_SNAPSHOT": snapshot.as_posix()},
    )

    assert arguments[0] == "--config", arguments
    assert arguments[2:] == [DEFAULT_GLOB], arguments
    bundled = json.loads(strip_jsonc_comments(snapshot.read_text(encoding="utf-8")))
    assert bundled["config"]["MD013"]["line_length"] == 80, bundled["config"]["MD013"]
    assert bundled["config"]["MD013"]["code_block_line_length"] == 120, bundled["config"]
    assert not Path(arguments[1]).exists(), "the temporary config was not cleaned up"


def test_makefile_declares_the_markdown_gates() -> None:
    """Both Markdown targets exist and are phony."""
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert re.search(r"^markdownlint:", makefile, re.MULTILINE), (
        "the markdownlint target the scrutineer runs is missing"
    )
    assert re.search(r"^nixie:", makefile, re.MULTILINE), (
        "the nixie target the scrutineer runs is missing"
    )
    phony = [
        target
        for line in makefile.splitlines()
        if line.startswith(".PHONY:")
        for target in line.removeprefix(".PHONY:").split()
    ]
    # `markdownlint` is also a file at the repository root, so without .PHONY
    # make treats the target as up to date and never lints anything.
    assert {"markdownlint", "nixie"} <= set(phony), phony
    assert re.search(r"^MDLINT\s*\?=\s*\./markdownlint\s*$", makefile, re.MULTILINE), (
        "the Makefile does not dogfood the repository's own lint script"
    )


def test_ci_runs_the_markdown_lint_gate_only() -> None:
    """CI gates Markdown lint; Mermaid validation stays local."""
    prerequisites = makefile_target_prerequisites("ci")

    assert "markdownlint" in prerequisites, prerequisites
    assert "nixie" not in prerequisites, (
        "nixie needs a Mermaid renderer the CI runner does not provide"
    )


def test_make_markdownlint_target_lints_the_tree(tmp_path: Path) -> None:
    """The target hands a glob to the linter rather than passing no paths."""
    stub = make_stub(tmp_path)
    record = tmp_path / "recorded-args.txt"

    completed = run_make(
        "markdownlint",
        f"MDLINT={stub.as_posix()}",
        environment={"MDLINT_STUB_RECORD": record.as_posix()},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert record.read_text(encoding="utf-8").split() == [DEFAULT_GLOB]


def test_lint_config_adopts_the_template_rule_set() -> None:
    """Line lengths match the shared template and its rules are enabled."""
    config = load_lint_config()["config"]

    assert config["MD013"]["line_length"] == 80, config["MD013"]
    assert config["MD013"]["code_block_line_length"] == 120, config["MD013"]
    assert "MD040" not in config, "MD040 must stay enabled to fence code blocks"
    assert "MD041" not in config, "MD041 must stay enabled to require a heading"


def test_lint_config_records_why_it_deviates() -> None:
    """Every rule kept from the template's defaults carries its rationale."""
    lines = LINT_CONFIG.read_text(encoding="utf-8").splitlines()

    for rule in DEVIATION_RULES:
        matching = [line for line in lines if f'"{rule}"' in line and "//" not in line]
        assert len(matching) == 1, f"expected one {rule} entry, found {len(matching)}"
        index = lines.index(matching[0])
        rationale: list[str] = []
        cursor = index - 1
        while cursor >= 0 and lines[cursor].lstrip().startswith("//"):
            rationale.append(lines[cursor])
            cursor -= 1
        assert "Deviates from the shared template" in " ".join(rationale), (
            f"{rule} is disabled without recording why it deviates"
        )


def test_ci_workflow_installs_the_pinned_linter() -> None:
    """The CI image installs the same linter the gate invokes, at a pinned version."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    pinned = re.search(r"^  MARKDOWNLINT_CLI2_VERSION: (\S+)$", workflow, re.MULTILINE)
    assert pinned, "the CI workflow does not pin markdownlint-cli2"
    assert re.fullmatch(r"\d+\.\d+\.\d+", pinned.group(1)), pinned.group(1)
    assert "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}" in workflow, (
        "the CI workflow does not install the pinned version it declares"
    )
    assert "run: make ci" in workflow, "CI does not run the gate sequence"
