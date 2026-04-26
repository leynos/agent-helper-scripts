"""Process-level tests for the split Rust bootstrap entrypoints.

The tests execute the shell entrypoints through cuprum and intercept dangerous
external commands with cmd-mox. This keeps coverage close to the real scripts
without touching package-manager state, remote Git repositories, or the real
home directory.
"""

from __future__ import annotations

import shutil
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
    cmd = sh.make(BASH, catalogue=CATALOGUE)(*args)
    with scoped(allowlist=CATALOGUE.allowlist):
        return cmd.run_sync(context=ExecutionContext(cwd=cwd, env=env))


def write_script(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n")
    path.chmod(0o755)


def copy_entrypoint_files(target: Path, *names: str) -> None:
    for name in names:
        shutil.copy2(REPO_ROOT / name, target / name)
        (target / name).chmod(0o755)


def selected_helper_names(*, include_ai: bool = False) -> list[str]:
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

    assert result.exit_code == 0, result.stderr
    assert run_log.read_text().splitlines() == ["system"]


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

    assert result.exit_code == 0, result.stderr
    assert run_log.read_text().splitlines() == ["system", "home"]


def test_rust_entrypoint_rejects_unknown_phase(tmp_path: Path) -> None:
    copy_entrypoint_files(tmp_path, "rust-entrypoint")

    result = run_bash(
        str(tmp_path / "rust-entrypoint"),
        cwd=tmp_path,
        env={"RUST_ENTRYPOINT_PHASE": "sideways"},
    )

    assert result.exit_code == 2
    assert "Unknown RUST_ENTRYPOINT_PHASE: sideways" in (result.stderr or "")


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
            "sudo",
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

    assert result.exit_code == 0, result.stderr
    assert run_log.read_text().splitlines() == selected_helper_names(include_ai=True)
    assert 'export PATH="' in (home / ".bashrc").read_text()
    assert ".bashrc" in (home / ".profile").read_text()
    assert not forbidden_invocations(mox.journal)


def test_system_phase_uses_temporary_checkout_and_installs_system_packages(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "bootstrap-common", "rust-entrypoint-system")
    home = tmp_path / "home"
    managed_checkout = home / "git" / "agent-helper-scripts"
    run_log = tmp_path / "run.log"
    home.mkdir()

    with CmdMox() as mox:
        mox.stub("whoami").returns(stdout="root\n")
        mox.stub("git").runs(lambda invocation: git_system_handler(invocation, run_log))
        mox.stub("install").returns()
        mox.stub("apt-get").runs(lambda invocation: log_invocation(invocation, run_log))
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

    assert result.exit_code == 0, result.stderr
    log_lines = run_log.read_text().splitlines()
    assert "add-repositories" in log_lines
    assert any(
        line.startswith("install-required get-rust-tooling get-markdown-tooling")
        for line in log_lines
    )
    assert any(
        line == "apt-get install -y -- linux-tools-common" for line in log_lines
    )
    assert any(line == "apt-get install -y -- linux-tools-generic" for line in log_lines)
    assert "update-ca-certificates" in log_lines
    assert log_lines.count("apt-update-if-stale") == 1
    assert "clone-target-preexisting false" in log_lines
    assert not managed_checkout.exists()


def test_install_sub_agents_preserves_user_config_before_legacy_block(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "install-sub-agents")
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
    assert "[features]\nuser_feature = true" in updated_config
    assert '[profiles.default]\nmodel = "gpt-5.5"' in updated_config
    assert '[agents.custom]\nconfig_file = "agents/custom.toml"' in updated_config
    assert '[profiles.after]\napproval_policy = "never"' in updated_config
    assert "LegacyWyvernNick" not in updated_config
    assert "LegacyScribeNick" not in updated_config
    assert "### BEGIN agent-helper-scripts sub-agent config" in updated_config
    assert "gpt-5.5" not in result.stdout
    assert "Updated Codex sub-agent config at" in result.stdout


def test_install_sub_agents_rejects_unclosed_legacy_config_block(
    tmp_path: Path,
) -> None:
    copy_entrypoint_files(tmp_path, "install-sub-agents")
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

    assert result.exit_code != 0
    assert "legacy Codex config block was not closed" in result.stderr
    assert config_path.read_text() == original_config
    assert "### BEGIN agent-helper-scripts sub-agent config" not in config_path.read_text()


def git_home_handler(invocation: Invocation) -> tuple[str, str, int]:
    if invocation.args == ["version"]:
        return ("git version 2.45.0\n", "", 0)
    if "rev-parse" in invocation.args:
        return ("true\n", "", 0)
    return ("", "", 0)


def git_system_handler(invocation: Invocation, run_log: Path) -> tuple[str, str, int]:
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
    argv = " ".join([invocation.command, *invocation.args])
    with run_log.open("a") as handle:
        handle.write(f"{argv}\n")
    return ("", "", 0)


def vendcurl_context_pack_handler(invocation: Invocation) -> tuple[str, str, int]:
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
    output_dir = Path(invocation.args[invocation.args.index("-C") + 1])
    (output_dir / "mcp-context-pack").write_text("mock context pack")
    return ("", "", 0)


def forbidden_invocations(journal) -> list[Invocation]:
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
