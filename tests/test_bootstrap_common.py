"""Subprocess tests for shared bootstrap shell helpers."""

from __future__ import annotations

import os
import shlex
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_bootstrap_script(
    tmp_path: Path,
    body: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Source bootstrap-common in Bash and run body with an isolated HOME."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    script = tmp_path / "run-bootstrap-common.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"source {shlex.quote(str(REPO_ROOT / 'bootstrap-common'))}\n"
        f"{textwrap.dedent(body)}\n",
    )
    script.chmod(0o755)

    process_env = os.environ.copy()
    process_env.update(
        {
            "HOME": home.as_posix(),
            "PATH": os.environ["PATH"],
        },
    )
    if env:
        process_env.update(env)

    return subprocess.run(  # noqa: S603 - generated script path, no shell interpolation.
        [script.as_posix()],
        cwd=tmp_path,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


def source_replace_managed_block() -> str:
    """Return Bash code that sources canonical managed block replacement."""
    return (
        "replace_managed_block() {\n"
        "  replace_or_append_managed_block_with_sentinels \"$@\"\n"
        "}\n"
    )


def source_ensure_top_level_toml_setting() -> str:
    """Return Bash code that sources ensure_top_level_toml_setting."""
    return (
        "source <(awk '\n"
        "  /^function ensure_top_level_toml_setting[[:space:]]*[(][)]/ { emit=1 }\n"
        "  emit { print }\n"
        "  emit && /^}[[:space:]]*$/ { exit }\n"
        f"' {shlex.quote(str(REPO_ROOT / 'install-sub-agents'))})"
    )


def test_append_block_if_missing_is_idempotent(tmp_path: Path) -> None:
    """append_block_if_missing appends the requested block only once."""
    target = tmp_path / "home" / "target-profile"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        block=$'### BEGIN test block\\nexport EXAMPLE=1\\n### END test block'
        append_block_if_missing {str(target)!r} "${{block}}"
        append_block_if_missing {str(target)!r} "${{block}}"
        """,
    )

    assert result.returncode == 0, result.stderr
    contents = target.read_text()
    assert contents.count("### BEGIN test block") == 1, contents
    assert contents.count("### END test block") == 1, contents


def test_ensure_profile_path_is_idempotent(tmp_path: Path) -> None:
    """ensure_profile_path writes one PATH export block to ~/.bashrc."""
    tool_dir = tmp_path / "home" / ".local" / "bin"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        ensure_profile_path {str(tool_dir)!r}
        ensure_profile_path {str(tool_dir)!r}
        """,
    )

    assert result.returncode == 0, result.stderr
    bashrc = (tmp_path / "home" / ".bashrc").read_text()
    export_line = f'export PATH="{tool_dir}:$PATH"'
    assert bashrc.count(export_line) == 1, bashrc


def test_ensure_profile_sources_bashrc_is_idempotent(tmp_path: Path) -> None:
    """ensure_profile_sources_bashrc writes one source block to ~/.profile."""
    result = run_bootstrap_script(
        tmp_path,
        """
        ensure_profile_sources_bashrc
        ensure_profile_sources_bashrc
        """,
    )

    assert result.returncode == 0, result.stderr
    profile = (tmp_path / "home" / ".profile").read_text()
    source_line = '. "$HOME/.bashrc"'
    assert profile.count(source_line) == 1, profile


def test_ensure_runtime_path_adds_directory_to_subprocess_path(
    tmp_path: Path,
) -> None:
    """ensure_runtime_path prepends the requested directory to PATH."""
    tool_dir = tmp_path / "home" / ".local" / "bin"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        ensure_runtime_path {str(tool_dir)!r}
        printf '%s\\n' "${{PATH}}"
        """,
    )

    assert result.returncode == 0, result.stderr
    runtime_path = result.stdout.strip().splitlines()[-1]
    assert runtime_path.split(":", 1)[0] == tool_dir.as_posix(), runtime_path


def test_replace_managed_block_replaces_existing_block(tmp_path: Path) -> None:
    """replace_managed_block replaces one managed block without duplicates."""
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text(
        "before = true\n"
        "### BEGIN managed marker\n"
        "old = true\n"
        "### END managed marker\n"
        "after = true\n",
    )
    extracted = source_replace_managed_block()
    assert extracted, "source_replace_managed_block() returned empty code"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    assert result.returncode == 0, result.stderr
    contents = target.read_text()
    expected = (
        "before = true\n"
        "after = true\n"
        "### BEGIN managed marker\n"
        "new = true\n"
        "### END managed marker\n"
    )
    assert contents == expected, contents
    assert contents.count("### BEGIN managed marker") == 1, contents
    assert contents.count("### END managed marker") == 1, contents


def test_replace_managed_block_rejects_unclosed_sentinel(tmp_path: Path) -> None:
    """replace_managed_block fails without changing an unclosed managed block."""
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    original = "before = true\n### BEGIN managed marker\nold = true\n"
    target.write_text(original)
    extracted = source_replace_managed_block()
    assert extracted, "source_replace_managed_block() returned empty code"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    assert result.returncode != 0, result.stderr
    assert "unbalanced sentinels" in result.stderr, result.stderr
    assert target.read_text() == original, target.read_text()


def test_replace_managed_block_rejects_duplicate_blocks(tmp_path: Path) -> None:
    """replace_managed_block fails without changing duplicate managed blocks."""
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    original = (
        "before = true\n"
        "### BEGIN managed marker\n"
        "old = true\n"
        "### END managed marker\n"
        "middle = true\n"
        "### BEGIN managed marker\n"
        "older = true\n"
        "### END managed marker\n"
        "after = true\n"
    )
    target.write_text(original)
    extracted = source_replace_managed_block()
    assert extracted, "source_replace_managed_block() returned empty code"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    assert result.returncode != 0, result.stderr
    assert "duplicate managed block" in result.stderr, result.stderr
    assert target.read_text() == original, target.read_text()


def test_replace_managed_block_rejects_end_before_begin(tmp_path: Path) -> None:
    """replace_managed_block fails when an end sentinel precedes its begin."""
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    original = (
        "before = true\n"
        "### END managed marker\n"
        "old = true\n"
        "### BEGIN managed marker\n"
        "after = true\n"
    )
    target.write_text(original)
    extracted = source_replace_managed_block()
    assert extracted, "source_replace_managed_block() returned empty code"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    assert result.returncode != 0, result.stderr
    assert "end sentinel appears before begin sentinel" in result.stderr, result.stderr
    assert target.read_text() == original, target.read_text()


def test_ensure_top_level_toml_setting_treats_key_as_literal(
    tmp_path: Path,
) -> None:
    """ensure_top_level_toml_setting does not treat key text as a regex."""
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text("suppressXunstable_features_warning = false\n")
    extracted = source_ensure_top_level_toml_setting()
    assert extracted, "source_ensure_top_level_toml_setting() returned empty code"
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        ensure_top_level_toml_setting {str(target)!r} 'suppress.unstable_features_warning' true
        """,
    )

    assert result.returncode == 0, result.stderr
    contents = target.read_text()
    assert contents.startswith(
        "suppress.unstable_features_warning = true\n",
    ), contents
    assert "suppressXunstable_features_warning = false" in contents, contents


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    (
        pytest.param(None, "", "MISSING", id="empty-dir"),
        pytest.param("lock", "locked", "MISSING", id="lock-file"),
        pytest.param(
            "archive.ubuntu.com_ubuntu_dists_noble_main_binary-amd64_Packages",
            "Package: bash\n",
            "OK",
            id="packages-index",
        ),
        pytest.param(
            "archive.ubuntu.com_ubuntu_dists_noble_InRelease",
            "Suite: noble\n",
            "OK",
            id="inrelease-index",
        ),
        pytest.param("Packages", "Package: bash\n", "MISSING", id="bare-packages"),
    ),
)
def test_apt_lists_exist_matches_only_real_index_files(
    tmp_path: Path,
    filename: str | None,
    content: str,
    expected: str,
) -> None:
    """apt_lists_exist recognises only underscore-anchored APT index files."""
    lists_dir = tmp_path / "apt" / "lists"
    lists_dir.mkdir(parents=True)
    if filename is not None:
        (lists_dir / filename).write_text(content)
    result = run_bootstrap_script(
        tmp_path,
        f"""
        APT_LISTS_DIR={shlex.quote(str(lists_dir))}
        apt_lists_exist() {{
          find "${{APT_LISTS_DIR}}" \\
            -mindepth 1 \\
            -maxdepth 1 \\
            -type f \\
            -size +0c \\
            ! -name lock \\
            ! -path '*/partial/*' \\
            \\( \\
              -name '*_Packages' \\
              -o -name '*_Packages.*' \\
              -o -name '*_Sources' \\
              -o -name '*_Sources.*' \\
              -o -name '*_Release' \\
              -o -name '*_InRelease' \\
              -o -name 'Release' \\
            \\) \\
            -print \\
            -quit \\
            2>/dev/null | grep -q .
        }}
        apt_lists_exist && echo OK || echo MISSING
        """,
    )

    assert result.returncode == 0, result.stderr
    assert expected in result.stdout.splitlines(), (
        f"expected apt_lists_exist to report {expected}, got {result.stdout!r}"
    )


def test_needs_reports_missing_commands(tmp_path: Path) -> None:
    """needs succeeds when a command is absent and fails when it is present."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    present = bin_dir / "present-tool"
    present.write_text("#!/usr/bin/env bash\nexit 0\n")
    present.chmod(0o755)
    result = run_bootstrap_script(
        tmp_path,
        """
        if needs present-tool; then
          printf 'present=missing\\n'
        else
          printf 'present=available\\n'
        fi
        if needs absent-tool; then
          printf 'absent=missing\\n'
        else
          printf 'absent=available\\n'
        fi
        """,
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    assert "present=available" in result.stdout, result.stdout
    assert "absent=missing" in result.stdout, result.stdout


def test_build_selected_tools_adds_ai_tooling_when_enabled(
    tmp_path: Path,
) -> None:
    """build_selected_tools includes get-ai-tooling when WITH_AI_TOOLING=1."""
    result = run_bootstrap_script(
        tmp_path,
        """
        build_selected_tools
        printf '%s\\n' "${SELECTED_TOOLS[@]}"
        """,
        env={"WITH_AI_TOOLING": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert "get-ai-tooling" in result.stdout.splitlines(), result.stdout


def test_build_selected_tools_omits_ai_tooling_by_default(tmp_path: Path) -> None:
    """build_selected_tools omits get-ai-tooling when WITH_AI_TOOLING is unset."""
    result = run_bootstrap_script(
        tmp_path,
        """
        build_selected_tools
        printf '%s\\n' "${SELECTED_TOOLS[@]}"
        """,
    )

    assert result.returncode == 0, result.stderr
    assert "get-ai-tooling" not in result.stdout.splitlines(), result.stdout
