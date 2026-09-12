"""Tests for the Markdown lint gate and its Makefile wiring."""

from __future__ import annotations

from collections.abc import Sequence
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LINT_SCRIPT = REPO_ROOT / "markdownlint"
LINT_CONFIG = REPO_ROOT / ".markdownlint-cli2.jsonc"
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
REAL_LINTER = "markdownlint-cli2"

# Rules kept disabled against the shared template, each paired with the setting
# it must hold, so a rule silently flipped back on fails a test rather than
# passing on the strength of its rationale comment alone.
DEVIATION_RULES: dict[str, object] = {
    "MD024": {"siblings_only": True},
    "MD033": False,
    "MD036": False,
}

DEFAULT_GLOB = "**/*.md"

#: Non-source trees the gate's walk prunes. A file from one of these in the
#: recorded arguments means the walk descended somewhere the spelling policy
#: already treats as outside the repository's own sources.
PRUNED_DIRECTORIES = (".git", ".venv", "dist", "node_modules", "target")

# The upstream action CI lints through. Its release carries the linter and its
# dependency graph, and Dependabot manages the version with the other actions.
MARKDOWNLINT_ACTION = "DavidAnson/markdownlint-cli2-action"


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


def make_stub(
    directory: Path,
    name: str = REAL_LINTER,
    exit_status: int = 0,
) -> Path:
    """Write an executable stand-in for markdownlint-cli2.

    The stub appends its arguments, one per line, to the file named by the
    ``STUB_ARGUMENT_RECORD`` environment variable, copies the configuration
    named by ``--config`` to ``STUB_CONFIG_SNAPSHOT`` when that is set, and
    exits with ``exit_status``. Recording the arguments lets the tests assert
    what the gate asked the linter to read without running it.

    Parameters
    ----------
    directory
        Directory to create the stub in.
    name
        File name for the stub. The default is the name the lint script
        resolves on ``PATH``; pass another to stand in for a different tool.
    exit_status
        Status the stub reports, so failure paths are reachable.

    Returns
    -------
    pathlib.Path
        Path to the executable stub.
    """
    stub = directory / name
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "${STUB_ARGUMENT_RECORD}"\n'
        'if [[ "${1:-}" == "--config" && -n "${STUB_CONFIG_SNAPSHOT:-}" ]]; then\n'
        '  cp "${2}" "${STUB_CONFIG_SNAPSHOT}"\n'
        "fi\n"
        f"exit {exit_status}\n",
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
    expected_returncode: int = 0,
    use_override: bool = True,
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
    expected_returncode
        Status the lint script is expected to exit with.
    use_override
        Whether to point ``MDLINT_BIN`` at the stub. Clear it to leave the
        linter to be resolved from ``PATH`` or from ``HOME`` instead.

    Returns
    -------
    list[str]
        Arguments the script forwarded to the linter.

    Side Effects
    ------------
    Starts a subprocess and writes the recorded arguments to ``record``.
    """
    run_environment = os.environ.copy()
    if use_override:
        run_environment["MDLINT_BIN"] = stub.as_posix()
    else:
        run_environment.pop("MDLINT_BIN", None)
    run_environment["STUB_ARGUMENT_RECORD"] = record.as_posix()
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
    assert completed.returncode == expected_returncode, (
        completed.stdout + completed.stderr
    )
    return record.read_text(encoding="utf-8").split()


def run_make(
    *args: str,
    environment: dict[str, str] | None = None,
    unset: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    """Run make from the repository root.

    Parameters
    ----------
    *args
        Make arguments to pass after the executable name.
    environment
        Extra environment variables for the run.
    unset
        Names removed from the inherited environment first, so an override the
        caller was itself invoked with cannot decide what the run observes.

    Returns
    -------
    subprocess.CompletedProcess[str]
        Completed make process with captured output.

    Side Effects
    ------------
    Starts a subprocess in the repository root.
    """
    run_environment = os.environ.copy()
    for name in unset:
        run_environment.pop(name, None)
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


#: Names the gate probe clears before it starts make. CI passes
#: CI_SKIP_MARKDOWNLINT on make's command line, and make exports a command-line
#: definition to everything the gate sequence then runs, this suite included;
#: MAKEFLAGS and MAKEOVERRIDES carry the same definition into a sub-make.
#: Clearing them keeps these tests on the sequence they asked for rather than
#: the one CI is running them from.
GATE_OVERRIDES = ("CI_SKIP_MARKDOWNLINT", "MAKEFLAGS", "MAKEOVERRIDES")


def ci_gates(*assignments: str) -> list[str]:
    """List the gates `make ci` runs, as make itself expands them.

    Parameters
    ----------
    *assignments
        Variable assignments to pass on make's command line.

    Returns
    -------
    list[str]
        Whitespace-separated gate names, in the order make would run them.

    Raises
    ------
    AssertionError
        If make fails or prints nothing the caller can parse.

    Side Effects
    ------------
    Starts a subprocess in the repository root.
    """
    completed = run_make(
        "--no-print-directory",
        "--eval=print-ci-gates: ; @echo [$(CI_GATES)]",
        "print-ci-gates",
        *assignments,
        unset=GATE_OVERRIDES,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    match = re.fullmatch(r"\[(.*)\]\n", completed.stdout)
    assert match, f"unexpected make output: {completed.stdout!r}"
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


def test_stdin_target_is_not_widened(tmp_path: Path) -> None:
    """A standalone `-` reads the file list from stdin, so nothing else is added."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        "-",
    )

    assert arguments == ["-"], (
        "the stdin marker is an explicit target; appending a glob would lint the "
        f"whole tree as well as the piped file list; got {arguments}"
    )


def test_config_operands_are_not_mistaken_for_targets(tmp_path: Path) -> None:
    """`--config FILE` names a configuration, so the tree is still linted."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        "--config",
        "custom.jsonc",
    )

    assert arguments == ["--config", "custom.jsonc", DEFAULT_GLOB], (
        "the operand of --config is not a document to lint; treating it as one "
        f"leaves the invocation with no globs at all; got {arguments}"
    )


def test_config_pointer_operands_are_not_mistaken_for_targets(tmp_path: Path) -> None:
    """`--configPointer POINTER` is likewise an operand, not a target."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        "--configPointer",
        "/tool/markdownlint-cli2",
    )

    assert arguments == [
        "--configPointer",
        "/tool/markdownlint-cli2",
        DEFAULT_GLOB,
    ], arguments


def test_repository_without_a_config_uses_the_bundled_one(tmp_path: Path) -> None:
    """A consumer repository falls back to the configuration shipped with the script."""
    snapshot = tmp_path / "bundled-config.jsonc"
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        cwd=tmp_path,
        environment={"STUB_CONFIG_SNAPSHOT": snapshot.as_posix()},
    )

    assert arguments[0] == "--config", arguments
    assert arguments[2:] == [DEFAULT_GLOB], arguments
    bundled = json.loads(strip_jsonc_comments(snapshot.read_text(encoding="utf-8")))
    assert bundled["config"]["MD013"]["line_length"] == 80, bundled["config"]["MD013"]
    assert bundled["config"]["MD013"]["code_block_line_length"] == 120, bundled["config"]
    assert not Path(arguments[1]).exists(), "the temporary config was not cleaned up"


def test_linter_is_resolved_from_path(tmp_path: Path) -> None:
    """A linter installed by a package manager is used without an override."""
    arguments = run_lint_script(
        make_stub(tmp_path),
        tmp_path / "recorded-args.txt",
        use_override=False,
        environment={"PATH": os.pathsep.join([tmp_path.as_posix(), os.environ["PATH"]])},
    )

    assert arguments == [DEFAULT_GLOB], arguments


def test_linter_falls_back_to_the_bun_global_install(tmp_path: Path) -> None:
    """With no linter on PATH the script uses the bun global install."""
    home = tmp_path / "home"
    bun_bin = home / ".bun" / "bin"
    bun_bin.mkdir(parents=True)
    shims = tmp_path / "shims"
    shims.mkdir()
    # Keep the script runnable on a PATH that deliberately lacks the linter.
    for tool in ("bash", "cat", "mktemp", "rm"):
        resolved = shutil.which(tool)
        assert resolved, f"{tool} is required to run the lint script"
        (shims / tool).symlink_to(resolved)

    arguments = run_lint_script(
        make_stub(bun_bin),
        tmp_path / "recorded-args.txt",
        use_override=False,
        environment={"HOME": home.as_posix(), "PATH": shims.as_posix()},
    )

    assert arguments == [DEFAULT_GLOB], arguments


def test_a_failing_linter_fails_the_gate_and_cleans_up(tmp_path: Path) -> None:
    """A lint failure propagates and still removes the temporary configuration."""
    arguments = run_lint_script(
        make_stub(tmp_path, exit_status=3),
        tmp_path / "recorded-args.txt",
        cwd=tmp_path,
        expected_returncode=3,
    )

    assert arguments[0] == "--config", arguments
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
    # The gate calls the linter the shared baseline provisions rather than the
    # repository's own `markdownlint` wrapper, which only covers the case where
    # markdownlint-cli2 is not installed.
    assert re.search(
        r"^MDLINT\s*\?=\s*markdownlint-cli2\s*$", makefile, re.MULTILINE
    ), "the Makefile does not call markdownlint-cli2 directly"


def test_ci_runs_the_markdown_lint_gate_only() -> None:
    """CI gates Markdown lint; Mermaid validation stays local."""
    gates = ci_gates()

    assert "markdownlint" in gates, gates
    assert "nixie" not in gates, (
        "nixie needs a Mermaid renderer the CI runner does not provide"
    )


def test_ci_target_runs_the_declared_gate_list() -> None:
    """The `ci` target takes its prerequisites from the shared gate list.

    Without this, the target could name its gates itself while the list above it
    drifted, and the difference CI runs would no longer be the one the workflow
    names.
    """
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert re.search(r"^ci: \$\(CI_GATES\)$", makefile, re.MULTILINE), (
        "the ci target no longer runs the declared gate list"
    )


def test_ci_skips_only_the_gate_the_action_supplies() -> None:
    """CI runs every gate `make ci` runs, minus the one the action supplies.

    The workflow names the gate it does not run rather than repeating the list,
    so this pins the difference between the two sequences to exactly that gate:
    a gate added to the Makefile still reaches CI.
    """
    gates = ci_gates()
    in_ci = ci_gates("CI_SKIP_MARKDOWNLINT=1")

    # A Makefile that stopped routing `ci` through the list would expand to
    # nothing, which would make the comparison below pass on empty sequences.
    assert "markdownlint" in gates, gates
    assert in_ci == [gate for gate in gates if gate != "markdownlint"], in_ci


def assert_names_discovered_markdown(
    arguments: Sequence[str],
    *leading: str,
) -> None:
    """Assert a tool was handed the repository's own Markdown files.

    Parameters
    ----------
    arguments
        Arguments the tool recorded, in order.
    *leading
        Arguments expected before the file list.

    Raises
    ------
    AssertionError
        If the arguments name no file, name something other than a Markdown
        file, name a glob, or reach into a tree the gate prunes.
    """
    assert list(arguments[: len(leading)]) == list(leading), arguments
    recorded = list(arguments[len(leading) :])
    assert recorded, (
        "the tool was invoked with no file at all, so a clean status reported "
        "on a tree it never read"
    )
    assert sorted(recorded) == recorded, f"the file list is not deterministic: {recorded}"
    assert all(argument.endswith(".md") for argument in recorded), recorded
    assert not any("*" in argument or "?" in argument for argument in recorded), (
        f"the gate must name files rather than a glob that can match none: {recorded}"
    )
    assert not any(
        directory in Path(argument).parts
        for argument in recorded
        for directory in PRUNED_DIRECTORIES
    ), f"a tree the gate prunes was linted anyway: {recorded}"
    assert {"AGENTS.md", "README.md"} <= set(recorded), recorded


def test_make_markdownlint_target_lints_every_discovered_file(tmp_path: Path) -> None:
    """The target hands the linter the files it discovered, not a glob."""
    stub = make_stub(tmp_path)
    record = tmp_path / "recorded-args.txt"

    completed = run_make(
        "markdownlint",
        f"MDLINT={stub.as_posix()}",
        environment={"STUB_ARGUMENT_RECORD": record.as_posix()},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_names_discovered_markdown(record.read_text(encoding="utf-8").split())


def test_make_nixie_target_validates_diagrams(tmp_path: Path) -> None:
    """The nixie target runs the configured binary over the diagram sources."""
    stub = make_stub(tmp_path, name="nixie")
    record = tmp_path / "recorded-args.txt"

    completed = run_make(
        "nixie",
        f"NIXIE={stub.as_posix()}",
        environment={"STUB_ARGUMENT_RECORD": record.as_posix()},
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert_names_discovered_markdown(
        record.read_text(encoding="utf-8").split(),
        "--no-sandbox",
    )


def test_make_gate_fails_when_its_tool_is_absent() -> None:
    """A gate whose tool is missing fails loudly instead of passing vacuously."""
    completed = run_make("markdownlint", "MDLINT=markdownlint-not-installed")

    assert completed.returncode != 0, "a missing tool must not pass the gate"
    assert "'markdownlint-not-installed' is required, but not installed" in (
        completed.stderr
    ), completed.stderr


def test_lint_config_adopts_the_template_rule_set() -> None:
    """Line lengths match the shared template and its rules are enabled."""
    config = load_lint_config()["config"]

    assert config["MD013"]["line_length"] == 80, config["MD013"]
    assert config["MD013"]["code_block_line_length"] == 120, config["MD013"]
    assert "MD040" not in config, "MD040 must stay enabled to fence code blocks"
    assert "MD041" not in config, "MD041 must stay enabled to require a heading"


def test_lint_config_records_why_it_deviates() -> None:
    """Every rule kept from the template's defaults holds its setting and rationale."""
    lines = LINT_CONFIG.read_text(encoding="utf-8").splitlines()
    config = load_lint_config()["config"]

    for rule, setting in DEVIATION_RULES.items():
        assert config[rule] == setting, f"{rule} is {config[rule]!r}, not {setting!r}"
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


def test_ci_workflow_lints_through_the_pinned_action() -> None:
    """CI lints Markdown with the upstream action, pinned, not an npm install.

    The action's release carries the linter and its whole dependency graph, so
    the version Dependabot manages is the version that runs. The ref must be an
    exact release tag: a branch, or a moving tag such as `v24`, could change the
    gate under a passing pull request.
    """
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    uses = re.search(rf"uses: {re.escape(MARKDOWNLINT_ACTION)}@(\S+)", workflow)
    assert uses, f"the CI workflow does not use {MARKDOWNLINT_ACTION}"
    assert re.fullmatch(r"v\d+\.\d+\.\d+", uses.group(1)), uses.group(1)
    assert "npm install" not in workflow, "CI still installs a linter of its own"
    assert workflow.index("actions/checkout") < workflow.index(MARKDOWNLINT_ACTION), (
        "the action lints the checked-out workspace, so checkout must come first"
    )
    globs = re.search(r'globs: "([^"]*)"', workflow)
    assert globs and globs.group(1) == DEFAULT_GLOB, globs
    assert "make ci CI_SKIP_MARKDOWNLINT=1" in workflow, (
        "CI does not run the gate sequence without the gate the action supplies"
    )


#: Argument chunks the widening property builds invocations from. Each chunk
#: carries the role its tokens play, so the expected widening is known by
#: construction rather than by restating the script's classification.
PLAIN_OPTIONS = ("--fix", "--no-globs")
CONFIG_OPTIONS = ("--config", "--configPointer")
CONFIG_OPERANDS = ("custom.jsonc", "pointer.json")
NAMED_TARGETS = ("docs/guide.md", "skills/example.md")
STDIN_TARGET = "-"


@pytest.fixture(scope="module")
def recording_stub(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A linter stub and the file it records its arguments to."""
    directory = tmp_path_factory.mktemp("markdown-gate")
    return make_stub(directory), directory / "recorded-args.txt"


@given(
    chunks=st.lists(
        st.one_of(
            st.tuples(st.sampled_from(PLAIN_OPTIONS)),
            st.tuples(st.sampled_from(CONFIG_OPTIONS), st.sampled_from(CONFIG_OPERANDS)),
            st.tuples(st.sampled_from(NAMED_TARGETS)),
            st.tuples(st.just(STDIN_TARGET)),
        ),
        max_size=4,
    )
)
@settings(deadline=None, max_examples=50)
def test_only_a_target_less_invocation_is_widened(
    chunks: list[tuple[str, ...]],
    recording_stub: tuple[Path, Path],
) -> None:
    """The default glob is appended exactly when no argument names a target."""
    stub, record = recording_stub
    arguments = [token for chunk in chunks for token in chunk]
    names_a_target = any(
        chunk[0] in NAMED_TARGETS or chunk[0] == STDIN_TARGET for chunk in chunks
    )

    forwarded = run_lint_script(stub, record, *arguments)

    expected = arguments if names_a_target else [*arguments, DEFAULT_GLOB]
    assert forwarded == expected


@pytest.mark.slow
def test_the_wrapper_lints_through_the_real_linter(tmp_path: Path) -> None:
    """End to end, the wrapper and its bundled configuration judge real files."""
    linter = shutil.which(REAL_LINTER) or (
        Path.home() / ".bun" / "bin" / REAL_LINTER
    ).as_posix()
    if not Path(linter).exists():
        pytest.skip(f"{REAL_LINTER} is not installed; no lint run is possible")

    document = tmp_path / "document.md"
    document.write_text(
        "# Title\n\nSee <https://example.com> for details.\n", encoding="utf-8"
    )

    def lint() -> subprocess.CompletedProcess[str]:
        """Lint the temporary directory through the wrapper."""
        return subprocess.run(  # noqa: S603,S607 - controlled args, shell=False.
            [LINT_SCRIPT.as_posix()],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )

    clean = lint()
    assert clean.returncode == 0, clean.stdout + clean.stderr

    document.write_text(
        "# Title\n\nSee https://example.com for details.\n", encoding="utf-8"
    )

    violating = lint()
    assert violating.returncode != 0, "a bare URL must fail the Markdown gate"
    # markdownlint-cli2 reports findings on stderr and the summary on stdout.
    assert "MD034" in violating.stdout + violating.stderr, (
        violating.stdout + violating.stderr
    )
