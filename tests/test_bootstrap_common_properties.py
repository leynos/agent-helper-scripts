"""Property tests for shared bootstrap shell helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from tests.test_bootstrap_common import run_bootstrap_script, source_replace_managed_block


def _tmp_path() -> Path:
    """Create a temporary directory path for one Hypothesis example."""
    return Path(tempfile.mkdtemp(prefix="bootstrap-common-properties-"))


def _valid_shell_text(value: str) -> bool:
    """Return true when text can round-trip through Bash command substitution."""
    return bool(value) and "\x00" not in value and not value.endswith("\n")


@settings(deadline=None, max_examples=50)
@given(st.text(), st.integers(min_value=1, max_value=5))
def test_append_block_if_missing_is_idempotent_for_any_block(
    block: str,
    call_count: int,
) -> None:
    """append_block_if_missing writes generated block text exactly once."""
    assume(_valid_shell_text(block))
    tmp_path = _tmp_path()
    block_path = tmp_path / "block.txt"
    target = tmp_path / "home" / "profile"
    block_path.write_text(block)
    calls = "\n".join(
        f'append_block_if_missing {str(target)!r} "${{block}}"'
        for _ in range(call_count)
    )
    result = run_bootstrap_script(
        tmp_path,
        f"""
        block=$(cat {str(block_path)!r})
        {calls}
        """,
    )

    assert result.returncode == 0, result.stderr
    contents = target.read_bytes().decode("utf-8")
    assert contents.count(block) == 1, (
        "append_block_if_missing should write generated block once: "
        f"block={block!r}; contents={contents!r}"
    )


@settings(deadline=None, max_examples=50)
@given(st.text(), st.text())
def test_replace_managed_block_preserves_one_sentinel_pair(
    before: str,
    after: str,
) -> None:
    """replace_managed_block keeps one BEGIN and END sentinel for valid files."""
    begin_sentinel = "### BEGIN managed marker"
    end_sentinel = "### END managed marker"
    assume("\x00" not in before and "\x00" not in after)
    assume(begin_sentinel not in before and begin_sentinel not in after)
    assume(end_sentinel not in before and end_sentinel not in after)
    tmp_path = _tmp_path()
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    target.write_text(
        f"{before}\n"
        f"{begin_sentinel}\n"
        "old = true\n"
        f"{end_sentinel}\n"
        f"{after}\n",
    )
    extracted = source_replace_managed_block()
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    assert result.returncode == 0, result.stderr
    contents = target.read_text()
    assert contents.count(begin_sentinel) == 1, contents
    assert contents.count(end_sentinel) == 1, contents


@settings(deadline=None, max_examples=50)
@given(st.integers(min_value=0, max_value=3), st.integers(min_value=0, max_value=3))
def test_replace_managed_block_rejects_unbalanced_or_duplicate_sentinels(
    begin_count: int,
    end_count: int,
) -> None:
    """replace_managed_block accepts one pair and rejects every other count."""
    begin_sentinel = "### BEGIN managed marker"
    end_sentinel = "### END managed marker"
    tmp_path = _tmp_path()
    target = tmp_path / "home" / ".codex" / "config.toml"
    target.parent.mkdir(parents=True)
    original = (
        "before = true\n"
        + "".join(f"{begin_sentinel}\nold = true\n" for _ in range(begin_count))
        + "".join(f"{end_sentinel}\nafter = true\n" for _ in range(end_count))
    )
    target.write_text(original)
    extracted = source_replace_managed_block()
    result = run_bootstrap_script(
        tmp_path,
        f"""
        {extracted}
        replace_managed_block {str(target)!r} "managed marker" $'new = true'
        """,
    )

    contents = target.read_text()
    if begin_count == end_count == 1:
        assert result.returncode == 0, result.stderr
        assert contents.count(begin_sentinel) == 1, contents
        assert contents.count(end_sentinel) == 1, contents
    elif begin_count == end_count == 0:
        assert result.returncode == 0, result.stderr
        assert contents.count(begin_sentinel) == 1, contents
        assert contents.count(end_sentinel) == 1, contents
    else:
        assert result.returncode != 0, (
            "invalid sentinel counts should fail: "
            f"begin_count={begin_count}; end_count={end_count}; stdout={result.stdout!r}; "
            f"stderr={result.stderr!r}"
        )
        assert contents == original, (
            "failed sentinel replacement should leave file unchanged: "
            f"expected={original!r}; got={contents!r}"
        )


@settings(deadline=None, max_examples=50)
@given(st.integers(min_value=1, max_value=10))
def test_ensure_profile_path_is_idempotent_for_repeated_calls(call_count: int) -> None:
    """ensure_profile_path writes one PATH export after repeated calls."""
    tmp_path = _tmp_path()
    tool_dir = tmp_path / "home" / ".local" / "bin"
    calls = "\n".join(f"ensure_profile_path {str(tool_dir)!r}" for _ in range(call_count))
    result = run_bootstrap_script(tmp_path, calls)

    assert result.returncode == 0, result.stderr
    bashrc = (tmp_path / "home" / ".bashrc").read_text()
    export_line = f'export PATH="{tool_dir}:$PATH"'
    assert bashrc.count(export_line) == 1, bashrc
