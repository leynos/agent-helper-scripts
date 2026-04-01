"""Tests for post-turn-quality-stop-hook.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


def _load_hook_module() -> ModuleType:
    """Load the hook script as a module despite the dashes in the filename."""
    hook_path = Path(__file__).parent / "post-turn-quality-stop-hook.py"
    spec = importlib.util.spec_from_file_location("post_turn_quality_stop_hook", hook_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


REPO = Path("/fake/repo")


# ---------------------------------------------------------------------------
# has_uncommitted_changes
# ---------------------------------------------------------------------------


class TestHasUncommittedChanges:
    """Tests for has_uncommitted_changes()."""

    def test_clean_working_tree(self) -> None:
        """All three checks pass -> False."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),  # git diff --quiet
                _completed(0),  # git diff --cached --quiet
                _completed(0, stdout=""),  # git ls-files
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is False
        assert err is None

    def test_unstaged_changes(self) -> None:
        """git diff --quiet exits 1 -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(1)
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True
        assert err is None

    def test_staged_changes(self) -> None:
        """git diff --cached --quiet exits 1 -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),  # unstaged clean
                _completed(1),  # staged dirty
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True
        assert err is None

    def test_untracked_files(self) -> None:
        """ls-files returns output -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),
                _completed(0),
                _completed(0, stdout="newfile.py\n"),
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True
        assert err is None

    def test_diff_error(self) -> None:
        """Non-0/1 exit from diff -> None + error."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="fatal: bad")
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is None
        assert err is not None
        assert "fatal: bad" in err

    def test_ls_files_error(self) -> None:
        """ls-files failure -> None + error."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),
                _completed(0),
                _completed(128, stderr="fatal: oops"),
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is None
        assert err is not None
        assert "git ls-files failed" in err


# ---------------------------------------------------------------------------
# get_upstream_ref
# ---------------------------------------------------------------------------


class TestGetUpstreamRef:
    """Tests for get_upstream_ref()."""

    def test_returns_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="origin/main\n")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref == "origin/main"
        assert err is None

    def test_no_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="no upstream")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None
        assert "no upstream" in (err or "")

    def test_empty_stdout(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None
        assert err is not None


# ---------------------------------------------------------------------------
# compush_check
# ---------------------------------------------------------------------------


class TestCompushCheck:
    """Tests for compush_check()."""

    def test_dirty_with_upstream(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Dirty tree + upstream -> block with push message."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(True, None)), \
             patch.object(hook, "get_upstream_ref", return_value=("origin/feature", None)):
            rc = hook.compush_check(REPO)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert "Please commit and push to origin/feature" in out["reason"]

    def test_dirty_no_upstream(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Dirty tree + no upstream -> block with fallback text."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(True, None)), \
             patch.object(hook, "get_upstream_ref", return_value=(None, "no upstream")):
            rc = hook.compush_check(REPO)
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert "origin (upstream not configured)" in out["reason"]

    def test_clean_tree(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Clean tree -> no output, exit 0."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(False, None)):
            rc = hook.compush_check(REPO)
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_error_checking_changes(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Error from has_uncommitted_changes -> silent exit 0."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(None, "oops")):
            rc = hook.compush_check(REPO)
        assert rc == 0
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# parse_env - compush flag
# ---------------------------------------------------------------------------


class TestParseEnvCompush:
    """Tests for the compush flag in parse_env()."""

    def test_compush_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POST_TURN_COMPUSH", "1")
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is True

    def test_compush_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POST_TURN_COMPUSH", raising=False)
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is False

    def test_compush_other_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POST_TURN_COMPUSH", "yes")
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is False


# ---------------------------------------------------------------------------
# run_stop_checks - compush integration
# ---------------------------------------------------------------------------


class TestRunStopChecksCompush:
    """Integration-level tests for compush in run_stop_checks()."""

    def test_compush_triggers_after_success(self) -> None:
        """compush=True + quality pass + dirty -> compush_check called."""
        with patch.object(hook, "repo_root", return_value=(REPO, None)), \
             patch.object(hook, "ensure_base_ref", return_value=(True, None, False)), \
             patch.object(hook, "merge_base", return_value=("abc123", None)), \
             patch.object(hook, "changed_files", return_value=(["src/foo.py"], None)), \
             patch.object(hook, "evaluate_changes", return_value=0), \
             patch.object(hook, "compush_check", return_value=0) as mock_compush, \
             patch("shutil.which", return_value="/usr/bin/git"):
            rc = hook.run_stop_checks(
                REPO, "origin/main", always_fetch=False, max_out=12000, compush=True
            )
        assert rc == 0
        mock_compush.assert_called_once_with(REPO)

    def test_compush_skipped_when_disabled(self) -> None:
        """compush=False -> compush_check not called."""
        with patch.object(hook, "repo_root", return_value=(REPO, None)), \
             patch.object(hook, "ensure_base_ref", return_value=(True, None, False)), \
             patch.object(hook, "merge_base", return_value=("abc123", None)), \
             patch.object(hook, "changed_files", return_value=(["src/foo.py"], None)), \
             patch.object(hook, "evaluate_changes", return_value=0), \
             patch.object(hook, "compush_check") as mock_compush, \
             patch("shutil.which", return_value="/usr/bin/git"):
            hook.run_stop_checks(
                REPO, "origin/main", always_fetch=False, max_out=12000, compush=False
            )
        mock_compush.assert_not_called()

    def test_compush_skipped_on_quality_failure(self) -> None:
        """Quality check failure (nonzero rc) -> compush_check not called."""
        with patch.object(hook, "repo_root", return_value=(REPO, None)), \
             patch.object(hook, "ensure_base_ref", return_value=(True, None, False)), \
             patch.object(hook, "merge_base", return_value=("abc123", None)), \
             patch.object(hook, "changed_files", return_value=(["src/foo.py"], None)), \
             patch.object(hook, "evaluate_changes", return_value=1), \
             patch.object(hook, "compush_check") as mock_compush, \
             patch("shutil.which", return_value="/usr/bin/git"):
            hook.run_stop_checks(
                REPO, "origin/main", always_fetch=False, max_out=12000, compush=True
            )
        mock_compush.assert_not_called()

    def test_compush_skipped_when_state_not_ok(self) -> None:
        """evaluate_changes returns 0 but sets state.ok=False -> compush_check not called."""

        def eval_side_effect(state: hook.HookState, repo: Path, max_out: int) -> int:
            state.ok = False
            return 0

        with patch.object(hook, "repo_root", return_value=(REPO, None)), \
             patch.object(hook, "ensure_base_ref", return_value=(True, None, False)), \
             patch.object(hook, "merge_base", return_value=("abc123", None)), \
             patch.object(hook, "changed_files", return_value=(["src/foo.py"], None)), \
             patch.object(hook, "evaluate_changes", side_effect=eval_side_effect), \
             patch.object(hook, "compush_check") as mock_compush, \
             patch("shutil.which", return_value="/usr/bin/git"):
            hook.run_stop_checks(
                REPO, "origin/main", always_fetch=False, max_out=12000, compush=True
            )
        mock_compush.assert_not_called()


# ---------------------------------------------------------------------------
# run() – OSError resilience
# ---------------------------------------------------------------------------


class TestRunOSError:
    """Tests for run() handling of OSError (e.g. missing cwd)."""

    def test_nonexistent_cwd_returns_error(self) -> None:
        """run() with a nonexistent cwd returns rc=1 instead of raising."""
        result = hook.run(["git", "status"], Path("/nonexistent/path"))
        assert result.returncode == 1
        assert "No such file or directory" in result.stderr

    def test_run_stop_checks_nonexistent_cwd(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Full pipeline exits cleanly when start_cwd does not exist."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            rc = hook.run_stop_checks(
                Path("/nonexistent/path"),
                "origin/main",
                always_fetch=False,
                max_out=12000,
            )
        assert rc == 0
        assert capsys.readouterr().out == ""
