"""Process-level tests for the split Rust bootstrap entrypoints.

The tests execute the shell entrypoints through cuprum and intercept dangerous
external commands with cmd-mox. This keeps coverage close to the real scripts
without touching package-manager state, remote Git repositories, or the real
home directory.
"""

from __future__ import annotations

import shutil
from random import Random
from pathlib import Path

from cmd_mox import CmdMox, skip_if_unsupported
from cmd_mox.ipc import Invocation
from cuprum import ExecutionContext, Program, ProgramCatalogue, ProjectSettings, scoped, sh


skip_if_unsupported()

REPO_ROOT = Path(__file__).resolve().parents[1]
BASH_PATH = Path(shutil.which("bash") or "/usr/bin/bash").resolve()
BASH = Program(BASH_PATH.as_posix())
CATALOGUE = ProgramCatalogue(
    projects=(
        ProjectSettings(
            name="agent-helper-scripts-entrypoint-tests",
            programs=(BASH,),
            documentation_locations=("docs/cuprum-users-guide.md",),
            noise_rules=(),
        ),
    ),
)


def run_bash(
    *args: str,
    cwd: Path,
    env: dict[str, str],
):
    """Run a Bash command through the cuprum allowlist.

    Parameters
    ----------
    *args : str
        Command arguments passed to the Bash executable.
    cwd : Path
        Working directory for the process.
    env : dict[str, str]
        Environment variables for the process.

    Returns
    -------
    CommandResult
        Cuprum result object with exit code, stdout and stderr.

    Raises
    ------
    OSError
        Raised by process startup failures such as a missing executable.

    Notes
    -----
    The test catalogue allows only the configured Bash executable.
    """
    cmd = sh.make(BASH, catalogue=CATALOGUE)(*args)
    with scoped(allowlist=CATALOGUE.allowlist):
        return cmd.run_sync(context=ExecutionContext(cwd=cwd, env=env))


def write_script(path: Path, body: str) -> None:
    """Write an executable Bash helper script.

    Parameters
    ----------
    path : Path
        Destination script path.
    body : str
        Script body appended after the shebang and safety options.

    Returns
    -------
    None
        The function writes the file in place.

    Raises
    ------
    OSError
        Raised when the file cannot be written or chmod fails.

    Notes
    -----
    The generated script uses ``set -euo pipefail``.
    """
    path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n")
    path.chmod(0o755)


def copy_entrypoint_files(target: Path, *names: str) -> None:
    """Copy repository entrypoint files into a test workspace.

    Parameters
    ----------
    target : Path
        Directory that receives copied files.
    *names : str
        Repository-root file names to copy.

    Returns
    -------
    None
        Files are copied and made executable.

    Raises
    ------
    OSError
        Raised when copying or chmod fails.

    Notes
    -----
    Tests use copied scripts so each run can mutate an isolated workspace.
    """
    for name in names:
        shutil.copy2(REPO_ROOT / name, target / name)
        (target / name).chmod(0o755)


def selected_helper_names(*, include_ai: bool = False) -> list[str]:
    """Return helper script names selected by the default bootstrap.

    Parameters
    ----------
    include_ai : bool, optional
        Include ``get-ai-tooling`` when true.

    Returns
    -------
    list[str]
        Ordered helper names expected to run during the home phase.

    Notes
    -----
    The order mirrors ``bootstrap-common`` defaults used by the tests.
    """
    names = [
        "get-rust-tooling",
        "rust-setup",
        "get-markdown-tooling",
        "get-github-tooling",
        "get-python-tooling",
        "install-skills",
        "install-hooks",
        "install-sub-agents",
    ]
    if include_ai:
        names.append("get-ai-tooling")
    return names


def create_helper_checkout(
    path: Path,
    *,
    include_ai: bool = False,
    git_as_file: bool = False,
) -> None:
    """Create a mock managed helper checkout.

    Parameters
    ----------
    path : Path
        Checkout directory to create.
    include_ai : bool, optional
        Include a mock ``get-ai-tooling`` helper when true.
    git_as_file : bool, optional
        Write ``.git`` as a file to emulate Git worktree checkouts.

    Returns
    -------
    None
        The checkout directory and mock helper scripts are written in place.

    Raises
    ------
    OSError
        Raised when directories or helper scripts cannot be created.

    Notes
    -----
    Each mock helper appends its name to ``RUN_LOG`` when executed.
    """
    path.mkdir(parents=True)
    if git_as_file:
        (path / ".git").write_text("gitdir: ../real-git-dir\n")
    else:
        (path / ".git").mkdir()
    for helper_name in selected_helper_names(include_ai=include_ai):
        write_script(
            path / helper_name,
            f'printf "%s\\n" "{helper_name}" >> "${{RUN_LOG:?}}"',
        )


def create_system_helper_checkout(path: Path) -> None:
    """Create a mock temporary helper checkout for the system phase.

    Parameters
    ----------
    path : Path
        Temporary checkout directory to populate.

    Returns
    -------
    None
        System-phase helper scripts and package metadata are written in place.

    Raises
    ------
    OSError
        Raised when checkout files cannot be created.

    Notes
    -----
    The mock ``apt-update-if-stale`` records calls instead of touching APT.
    """
    path.mkdir(parents=True)
    (path / ".git").mkdir()
    write_script(
        path / "add-repositories",
        'printf "%s\\n" "add-repositories" >> "${RUN_LOG:?}"',
    )
    write_script(
        path / "apt-update-if-stale",
        'printf "%s\\n" "apt-update-if-stale" >> "${RUN_LOG:?}"',
    )
    write_script(
        path / "install-required-apt-packages",
        'printf "install-required" >> "${RUN_LOG:?}"\n'
        'for arg in "$@"; do printf " %s" "${arg##*/}" >> "${RUN_LOG:?}"; done\n'
        'printf "\\n" >> "${RUN_LOG:?}"',
    )
    for helper_name in selected_helper_names():
        (path / helper_name).write_text("# requires-apt-packages: test-package\n")


def test_rust_entrypoint_dispatches_selected_phase(tmp_path: Path) -> None:
    copy_entrypoint_files(tmp_path, "rust-entrypoint")
    run_log = tmp_path / "run.log"
    write_script(
        tmp_path / "rust-entrypoint-system",
        'printf "%s\\n" "system" >> "${RUN_LOG:?}"',
    )
    write_script(
        tmp_path / "rust-entrypoint-home",
        'printf "%s\\n" "home" >> "${RUN_LOG:?}"',
    )

    result = run_bash(
        str(tmp_path / "rust-entrypoint"),
        cwd=tmp_path,
        env={"RUN_LOG": run_log.as_posix(), "RUST_ENTRYPOINT_PHASE": "system"},
    )

    actual_lines = run_log.read_text().splitlines()
    assert result.exit_code == 0, (
        "system phase dispatch should succeed: "
        f"expected 0 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    assert actual_lines == ["system"], (
        "system phase dispatch should run only the system entrypoint: "
        f"expected ['system'] but got {actual_lines!r}"
    )


def test_rust_entrypoint_both_runs_system_then_home(tmp_path: Path) -> None:
    copy_entrypoint_files(tmp_path, "rust-entrypoint")
    run_log = tmp_path / "run.log"
    write_script(
        tmp_path / "rust-entrypoint-system",
        'printf "%s\\n" "system" >> "${RUN_LOG:?}"',
    )
    write_script(
        tmp_path / "rust-entrypoint-home",
        'printf "%s\\n" "home" >> "${RUN_LOG:?}"',
    )

    result = run_bash(
        str(tmp_path / "rust-entrypoint"),
        cwd=tmp_path,
        env={"RUN_LOG": run_log.as_posix()},
    )

    actual_lines = run_log.read_text().splitlines()
    assert result.exit_code == 0, (
        "both phase dispatch should succeed: "
        f"expected 0 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    assert actual_lines == ["system", "home"], (
        "both phase dispatch should run system then home: "
        f"expected ['system', 'home'] but got {actual_lines!r}"
    )


def test_rust_entrypoint_rejects_unknown_phase(tmp_path: Path) -> None:
    copy_entrypoint_files(tmp_path, "rust-entrypoint")

    result = run_bash(
        str(tmp_path / "rust-entrypoint"),
        cwd=tmp_path,
        env={"RUST_ENTRYPOINT_PHASE": "sideways"},
    )

    assert result.exit_code == 2, (
        "unknown phase should exit with usage error: "
        f"expected 2 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    assert "Unknown RUST_ENTRYPOINT_PHASE: sideways" in (result.stderr or ""), (
        "unknown phase should name the rejected value: "
        f"stderr was {result.stderr!r}"
    )


def test_rust_entrypoint_enables_trace_when_requested(tmp_path: Path) -> None:
    """WITH_TRACE enables Bash xtrace in the wrapper without changing dispatch."""
    copy_entrypoint_files(tmp_path, "rust-entrypoint")
    run_log = tmp_path / "run.log"
    write_script(
        tmp_path / "rust-entrypoint-system",
        'printf "%s\\n" "system" >> "${RUN_LOG:?}"',
    )

    result = run_bash(
        str(tmp_path / "rust-entrypoint"),
        cwd=tmp_path,
        env={
            "RUN_LOG": run_log.as_posix(),
            "RUST_ENTRYPOINT_PHASE": "system",
            "WITH_TRACE": "1",
        },
    )

    actual_lines = run_log.read_text().splitlines()
    assert result.exit_code == 0, (
        "traced system phase dispatch should succeed: "
        f"expected 0 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    assert actual_lines == ["system"], (
        "traced system phase dispatch should still run the selected phase: "
        f"expected ['system'] but got {actual_lines!r}"
    )
    assert "+ exec bash" in (result.stderr or ""), (
        "WITH_TRACE should enable xtrace output: "
        f"stderr was {result.stderr!r}"
    )


def test_home_phase_runs_selected_helpers_without_system_commands(tmp_path: Path) -> None:
    copy_entrypoint_files(tmp_path, "bootstrap-common", "rust-entrypoint-home")
    home = tmp_path / "home"
    helper_checkout = tmp_path / "helpers"
    run_log = tmp_path / "run.log"
    home.mkdir()
    create_helper_checkout(helper_checkout, include_ai=True, git_as_file=True)

    with CmdMox() as mox:
        mox.stub("git").runs(git_home_handler)
        mox.stub("uv").returns()
        mox.stub("bun").returns()
        mox.stub("rustup").returns()
        for forbidden in (
            "apt-get",
            "apt-update-if-stale",
            "install",
            "update-ca-certificates",
            "realpath",
            "ln",
        ):
            mox.register_command(forbidden)
        mox.replay()
        result = run_bash(
            str(tmp_path / "rust-entrypoint-home"),
            cwd=tmp_path,
            env={
                "HOME": home.as_posix(),
                "HELPER_TOOLS_REPO_DIR": helper_checkout.as_posix(),
                "RUN_LOG": run_log.as_posix(),
                "WITH_AI_TOOLING": "1",
            },
        )

    actual_lines = run_log.read_text().splitlines()
    expected_lines = selected_helper_names(include_ai=True)
    bashrc_text = (home / ".bashrc").read_text()
    profile_text = (home / ".profile").read_text()
    forbidden_calls = forbidden_invocations(mox.journal)
    assert result.exit_code == 0, (
        "home phase should succeed: "
        f"expected 0 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    assert actual_lines == expected_lines, (
        "home phase should run selected helpers in order: "
        f"expected {expected_lines!r} but got {actual_lines!r}"
    )
    assert 'export PATH="' in bashrc_text, (
        "home phase should write PATH export block to .bashrc: "
        f".bashrc content was {bashrc_text!r}"
    )
    assert ".bashrc" in profile_text, (
        "home phase should make .profile source .bashrc: "
        f".profile content was {profile_text!r}"
    )
    assert not forbidden_calls, (
        "home phase should not invoke system commands: "
        f"forbidden calls were {forbidden_calls!r}"
    )


def test_system_phase_uses_temporary_checkout_and_installs_system_packages(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "bootstrap-common", "rust-entrypoint-system")
    home = tmp_path / "home"
    run_log = tmp_path / "run.log"
    home.mkdir()

    with CmdMox() as mox:
        mox.stub("git").runs(lambda invocation: git_system_handler(invocation, run_log))
        mox.stub("sudo").runs(lambda invocation: sudo_system_handler(invocation, run_log))
        mox.stub("install").returns()
        mox.stub("apt-get").runs(lambda invocation: log_invocation(invocation, run_log))
        mox.stub("mv").runs(lambda invocation: log_invocation(invocation, run_log))
        mox.stub("sh").returns()
        mox.stub("update-ca-certificates").runs(
            lambda invocation: log_invocation(invocation, run_log)
        )
        mox.stub("realpath").returns(stdout="/usr/bin/ld.bfd\n")
        mox.stub("ln").runs(lambda invocation: log_invocation(invocation, run_log))
        mox.replay()
        result = run_bash(
            str(tmp_path / "rust-entrypoint-system"),
            cwd=tmp_path,
            env={
                "HOME": home.as_posix(),
                "RUN_LOG": run_log.as_posix(),
                "WITH_MOLD_LD_OVERRIDE": "1",
                "UBUNTU_APT_MIRROR": "https://mirror.example.invalid/ubuntu/",
            },
        )

    assert result.exit_code == 0, (
        "system phase should succeed: "
        f"expected 0 but got {result.exit_code}; stderr={result.stderr!r}"
    )
    log_lines = run_log.read_text().splitlines()
    clone_lines = [line for line in log_lines if line.startswith("git clone ")]
    assert "add-repositories" in log_lines, (
        "system phase should run add-repositories: "
        f"log lines were {log_lines!r}"
    )
    assert any(
        line.startswith("install-required get-rust-tooling get-markdown-tooling")
        for line in log_lines
    ), (
        "system phase should install packages for selected helpers: "
        f"log lines were {log_lines!r}"
    )
    assert any(
        line == "apt-get install -y -- linux-tools-common" for line in log_lines
    ), (
        "system phase should best-effort install linux-tools-common: "
        f"log lines were {log_lines!r}"
    )
    assert any(
        line == "apt-get install -y -- linux-tools-generic" for line in log_lines
    ), (
        "system phase should best-effort install linux-tools-generic: "
        f"log lines were {log_lines!r}"
    )
    assert "update-ca-certificates" in log_lines, (
        "system phase should update CA certificates: "
        f"log lines were {log_lines!r}"
    )
    assert log_lines.count("apt-update-if-stale") == 2, (
        "system phase should refresh APT through the stamp-aware helper: "
        f"log lines were {log_lines!r}"
    )
    assert "clone-target-preexisting false" in log_lines, (
        "system phase should clone into a non-pre-existing temp checkout: "
        f"log lines were {log_lines!r}"
    )
    assert clone_lines, (
        "system phase should log the git clone invocation: "
        f"log lines were {log_lines!r}"
    )
    cloned_checkout = Path(clone_lines[0].split()[-1])
    assert not cloned_checkout.exists(), (
        "temporary system helper checkout should be cleaned up: "
        f"found checkout at {cloned_checkout}"
    )


def test_install_sub_agents_preserves_user_config_before_legacy_block(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "bootstrap-common", "install-sub-agents")
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    config_path = codex_dir / "config.toml"
    home.mkdir()
    codex_dir.mkdir()
    config_path.write_text(
        """[features]
user_feature = true

[profiles.default]
model = "gpt-5.5"

[agents.custom]
config_file = "agents/custom.toml"

[features]
child_agents_md = true
sqlite = true
memories = true
js_repl = true
multi_agent = true

[agents]
max_threads = 6
max_depth = 1

[agents.wyvern]
config_file = "agents/wyvern.toml"
nickname_candidates = [
  "LegacyWyvernNick",
]

[agents.scribe]
config_file = "agents/scribe.toml"
nickname_candidates = [
  "LegacyScribeNick",
]

[profiles.after]
approval_policy = "never"
"""
    )

    with CmdMox() as mox:
        mox.stub("vendcurl").runs(vendcurl_context_pack_handler)
        mox.stub("tar").runs(tar_context_pack_handler)
        mox.stub("install").returns()
        mox.replay()
        result = run_bash(
            str(tmp_path / "install-sub-agents"),
            cwd=tmp_path,
            env={"HOME": home.as_posix()},
        )

    assert result.exit_code == 0, result.stderr
    updated_config = config_path.read_text()
    assert "[features]\nuser_feature = true" in updated_config, (
        "user-owned features section should be preserved: "
        f"config was {updated_config!r}"
    )
    assert '[profiles.default]\nmodel = "gpt-5.5"' in updated_config, (
        "user-owned profile section should be preserved: "
        f"config was {updated_config!r}"
    )
    assert '[agents.custom]\nconfig_file = "agents/custom.toml"' in updated_config, (
        "user-owned custom agent section should be preserved: "
        f"config was {updated_config!r}"
    )
    assert '[profiles.after]\napproval_policy = "never"' in updated_config, (
        "config after the legacy block should be preserved: "
        f"config was {updated_config!r}"
    )
    assert "LegacyWyvernNick" not in updated_config, (
        "legacy wyvern nickname block should be removed: "
        f"config was {updated_config!r}"
    )
    assert "LegacyScribeNick" not in updated_config, (
        "legacy scribe nickname block should be removed: "
        f"config was {updated_config!r}"
    )
    assert "### BEGIN agent-helper-scripts sub-agent config" in updated_config, (
        "managed sub-agent config block should be appended: "
        f"config was {updated_config!r}"
    )
    assert "gpt-5.5" not in result.stdout, (
        "install-sub-agents should not print user config values: "
        f"stdout was {result.stdout!r}"
    )
    assert "Updated Codex sub-agent config at" in result.stdout, (
        "install-sub-agents should print a non-sensitive update message: "
        f"stdout was {result.stdout!r}"
    )


def test_install_sub_agents_rejects_unclosed_legacy_config_block(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "bootstrap-common", "install-sub-agents")
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    config_path = codex_dir / "config.toml"
    home.mkdir()
    codex_dir.mkdir()
    original_config = """[features]
child_agents_md = true
sqlite = true
memories = true
js_repl = true
multi_agent = true

[agents]
max_threads = 6
max_depth = 1

[agents.wyvern]
config_file = "agents/wyvern.toml"
nickname_candidates = [
  "LegacyWyvernNick",
]

[agents.scribe]
config_file = "agents/scribe.toml"
nickname_candidates = [
  "LegacyScribeNick",
"""
    config_path.write_text(original_config)

    with CmdMox() as mox:
        mox.stub("vendcurl").runs(vendcurl_context_pack_handler)
        mox.stub("tar").runs(tar_context_pack_handler)
        mox.stub("install").returns()
        mox.replay()
        result = run_bash(
            str(tmp_path / "install-sub-agents"),
            cwd=tmp_path,
            env={"HOME": home.as_posix()},
        )

    assert result.exit_code != 0, (
        "unclosed legacy config should fail: "
        f"exit code was {result.exit_code}; stderr was {result.stderr!r}"
    )
    assert "legacy Codex config block was not closed" in result.stderr, (
        "failure should explain the unclosed legacy block: "
        f"stderr was {result.stderr!r}"
    )
    rewritten_config = config_path.read_text()
    assert rewritten_config == original_config, (
        "unclosed legacy config should not be rewritten: "
        f"expected {original_config!r} but got {rewritten_config!r}"
    )
    assert "### BEGIN agent-helper-scripts sub-agent config" not in rewritten_config, (
        "managed block should not be appended after parse failure: "
        f"config was {rewritten_config!r}"
    )


def test_install_sub_agents_preserves_randomized_nonlegacy_candidates(
    tmp_path: Path,
) -> None:
    """Legacy cleanup ignores partial and interleaved candidate sections."""
    copy_entrypoint_files(tmp_path, "bootstrap-common", "install-sub-agents")
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    config_path = codex_dir / "config.toml"
    home.mkdir()
    codex_dir.mkdir()
    preserved_sections = [
        "[features]\nchild_agents_m = true\nsqlite = true\n",
        "[features]\nchild_agents_md = true\nuser_owned = true\n",
        "[agents]\nmax_threads = 6\nuser_line = true\n",
        "[agents.wyvern]\nconfig_file = \"agents/not-wyvern.toml\"\n",
        "[agents.scribe]\nconfig_file = \"agents/not-scribe.toml\"\n",
        "[profiles.interleaved]\nmodel = \"gpt-5.5\"\n",
    ]
    Random(20260426).shuffle(preserved_sections)
    original_config = "\n".join(preserved_sections)
    config_path.write_text(original_config)

    with CmdMox() as mox:
        mox.stub("vendcurl").runs(vendcurl_context_pack_handler)
        mox.stub("tar").runs(tar_context_pack_handler)
        mox.stub("install").returns()
        mox.replay()
        result = run_bash(
            str(tmp_path / "install-sub-agents"),
            cwd=tmp_path,
            env={"HOME": home.as_posix()},
        )

    assert result.exit_code == 0, result.stderr
    updated_config = config_path.read_text()
    for section in preserved_sections:
        assert section.strip() in updated_config, (
            "partial legacy-like candidate should be preserved: "
            f"missing {section!r} from {updated_config!r}"
        )
    assert "gpt-5.5" not in result.stdout, (
        "install-sub-agents should not print randomized user config values: "
        f"stdout was {result.stdout!r}"
    )


def test_install_sub_agents_rejects_unclosed_legacy_config_after_scribe_file(
    tmp_path: Path,
) -> None:
    """Legacy cleanup fails safely when EOF occurs after scribe config."""
    copy_entrypoint_files(tmp_path, "bootstrap-common", "install-sub-agents")
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    config_path = codex_dir / "config.toml"
    home.mkdir()
    codex_dir.mkdir()
    original_config = """[features]
child_agents_md = true
sqlite = true
memories = true
js_repl = true
multi_agent = true

[agents]
max_threads = 6
max_depth = 1

[agents.wyvern]
config_file = "agents/wyvern.toml"

[agents.scribe]
config_file = "agents/scribe.toml"
"""
    config_path.write_text(original_config)

    with CmdMox() as mox:
        mox.stub("vendcurl").runs(vendcurl_context_pack_handler)
        mox.stub("tar").runs(tar_context_pack_handler)
        mox.stub("install").returns()
        mox.replay()
        result = run_bash(
            str(tmp_path / "install-sub-agents"),
            cwd=tmp_path,
            env={"HOME": home.as_posix()},
        )

    assert result.exit_code != 0, (
        "unclosed legacy config should fail after scribe config_file: "
        f"exit code was {result.exit_code}; stderr was {result.stderr!r}"
    )
    assert "legacy Codex config block was not closed" in result.stderr, (
        "failure should explain the unclosed legacy block: "
        f"stderr was {result.stderr!r}"
    )
    assert config_path.read_text() == original_config, config_path.read_text()


def git_home_handler(invocation: Invocation) -> tuple[str, str, int]:
    """Stub git for home-phase tests: handles version and rev-parse."""
    if invocation.args == ["version"]:
        return ("git version 2.45.0\n", "", 0)
    if "rev-parse" in invocation.args:
        return ("true\n", "", 0)
    return ("", "", 0)


def git_system_handler(invocation: Invocation, run_log: Path) -> tuple[str, str, int]:
    """Stub git for system-phase tests: logs invocations and handles clone."""
    if invocation.args == ["version"]:
        return ("git version 2.45.0\n", "", 0)
    if invocation.args and invocation.args[0] == "clone":
        checkout_target = Path(invocation.args[-1])
        preexisting = str(checkout_target.exists()).lower()
        with run_log.open("a") as handle:
            handle.write(f"clone-target-preexisting {preexisting}\n")
        create_system_helper_checkout(checkout_target)
    return log_invocation(invocation, run_log)


def log_invocation(invocation: Invocation, run_log: Path) -> tuple[str, str, int]:
    """Record a command invocation to run_log and return success."""
    argv = " ".join([invocation.command, *invocation.args])
    with run_log.open("a") as handle:
        handle.write(f"{argv}\n")
    return ("", "", 0)


def sudo_system_handler(invocation: Invocation, run_log: Path) -> tuple[str, str, int]:
    """Stub sudo by logging the privileged command it would execute."""
    args = list(invocation.args)
    if not args:
        return ("", "", 0)
    if args[0] == "env":
        args = [arg for arg in args[1:] if "=" not in arg]
    command = args[0]
    if command == "bash" and len(args) > 1:
        with run_log.open("a") as handle:
            handle.write(f"{Path(args[1]).name}\n")
        return ("", "", 0)
    argv = " ".join([command, *args[1:]])
    with run_log.open("a") as handle:
        handle.write(f"{argv}\n")
    return ("", "", 0)


def vendcurl_context_pack_handler(invocation: Invocation) -> tuple[str, str, int]:
    """Stub vendcurl to write a fake context-pack archive to the destination."""
    destination = Path(invocation.args[-1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.name == "checksums.sha256":
        destination.write_text(
            "0 mcp-context-pack-x86_64-unknown-linux-gnu.tar.gz\n",
        )
    else:
        destination.write_text("")
    return ("", "", 0)


def tar_context_pack_handler(invocation: Invocation) -> tuple[str, str, int]:
    """Stub tar to unpack a fake mcp-context-pack into the -C directory."""
    output_dir = Path(invocation.args[invocation.args.index("-C") + 1])
    (output_dir / "mcp-context-pack").write_text("mock context pack")
    return ("", "", 0)


def forbidden_invocations(journal: list[Invocation]) -> list[Invocation]:
    forbidden = {
        "apt-get",
        "apt-update-if-stale",
        "sudo",
        "install",
        "update-ca-certificates",
        "realpath",
        "ln",
    }
    return [invocation for invocation in journal if invocation.command in forbidden]
