"""Exercise the post-turn quality stop hook end to end and in pieces.

This module covers the hook's expected git-state decisions, environment
parsing, subprocess error handling, make-target discovery, and compush
follow-up behavior. The tests focus on observable inputs and outputs,
including successful checks, soft-failure paths that must stay silent,
and blocking/error conditions that should surface through the hook
contract.

Run the suite from the repository root with `pytest` or the repository's
test target. No external fixtures or environment setup are required
beyond a Python environment with `pytest` installed because the tests
mock subprocess-heavy interactions.

Example:
    python3 -m pytest hooks/test_post_turn_quality_stop_hook.py -v
"""

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
    assert spec is not None, "expected import spec to be created for hook module"
    assert spec.loader is not None, "expected import spec loader for hook module"
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
        args=["unit-test"], returncode=returncode, stdout=stdout, stderr=stderr
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
        assert dirty is False, f"expected dirty to be False but was {dirty!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_unstaged_changes(self) -> None:
        """git diff --quiet exits 1 -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(1)
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True, f"expected dirty to be True but was {dirty!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_staged_changes(self) -> None:
        """git diff --cached --quiet exits 1 -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),  # unstaged clean
                _completed(1),  # staged dirty
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True, f"expected dirty to be True but was {dirty!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_untracked_files(self) -> None:
        """ls-files returns output -> True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),
                _completed(0),
                _completed(0, stdout="newfile.py\n"),
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is True, f"expected dirty to be True but was {dirty!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_diff_error(self) -> None:
        """Non-0/1 exit from diff -> None + error."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="fatal: bad")
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is None, f"expected dirty to be None on error but was {dirty!r}"
        assert err is not None, "expected an error message from git diff failure"
        assert "fatal: bad" in err, f"expected fatal error in message but got {err!r}"

    def test_ls_files_error(self) -> None:
        """ls-files failure -> None + error."""
        with patch.object(hook, "run") as mock_run:
            mock_run.side_effect = [
                _completed(0),
                _completed(0),
                _completed(128, stderr="fatal: oops"),
            ]
            dirty, err = hook.has_uncommitted_changes(REPO)
        assert dirty is None, f"expected dirty to be None on error but was {dirty!r}"
        assert err is not None, "expected an error message from git ls-files failure"
        assert "git ls-files failed" in err, (
            f"expected ls-files failure in message but got {err!r}"
        )


# ---------------------------------------------------------------------------
# get_upstream_ref
# ---------------------------------------------------------------------------


class TestGetUpstreamRef:
    """Tests for get_upstream_ref()."""

    def test_returns_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="origin/main\n")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref == "origin/main", f"expected upstream ref origin/main but got {ref!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_no_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="no upstream")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None, f"expected no upstream ref but got {ref!r}"
        assert "no upstream" in (err or ""), (
            f"expected no-upstream message but got {err!r}"
        )

    def test_empty_stdout(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None, f"expected no upstream ref but got {ref!r}"
        assert err is not None, "expected an error when upstream stdout is empty"


# ---------------------------------------------------------------------------
# has_unpushed_commits
# ---------------------------------------------------------------------------


class TestHasUnpushedCommits:
    """Tests for has_unpushed_commits()."""

    def test_ahead_of_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="2\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is True, f"expected ahead to be True but was {ahead!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_not_ahead_of_upstream(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="0\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is False, f"expected ahead to be False but was {ahead!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_rev_list_error(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="fatal: bad revision")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is None, f"expected ahead to be None on error but was {ahead!r}"
        assert err is not None, "expected an error message from rev-list failure"
        assert "fatal: bad revision" in err, (
            f"expected bad revision error in message but got {err!r}"
        )

    def test_empty_output(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is None, f"expected ahead to be None for empty output but was {ahead!r}"
        assert "empty output" in (err or ""), (
            f"expected empty output error but got {err!r}"
        )

    def test_non_integer_output(self) -> None:
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="two\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is None, (
            f"expected ahead to be None for non-integer output but was {ahead!r}"
        )
        assert "non-integer" in (err or ""), (
            f"expected non-integer error but got {err!r}"
        )


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
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block", (
            f"expected block decision but got {out['decision']!r}"
        )
        assert "Please commit and push to origin/feature" in out["reason"], (
            f"expected commit/push reminder but got {out['reason']!r}"
        )

    def test_dirty_no_upstream(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Dirty tree + no upstream -> block with fallback text."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(True, None)), \
             patch.object(hook, "get_upstream_ref", return_value=(None, "no upstream")):
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block", (
            f"expected block decision but got {out['decision']!r}"
        )
        assert "origin (upstream not configured)" in out["reason"], (
            f"expected upstream fallback in reason but got {out['reason']!r}"
        )

    def test_clean_tree(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Clean tree -> no output, exit 0."""
        with patch.object(hook, "get_upstream_ref", return_value=("origin/feature", None)), \
             patch.object(hook, "has_uncommitted_changes", return_value=(False, None)), \
             patch.object(hook, "has_unpushed_commits", return_value=(False, None)):
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        assert capsys.readouterr().out == "", "expected no hook output for clean tree"

    def test_error_checking_changes(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Error from has_uncommitted_changes -> silent exit 0."""
        with patch.object(hook, "has_uncommitted_changes", return_value=(None, "oops")):
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        assert capsys.readouterr().out == "", (
            "expected no hook output when change check errors are suppressed"
        )

    def test_clean_tree_with_unpushed_commits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Clean tree + ahead of upstream -> block with push-only message."""
        with patch.object(hook, "get_upstream_ref", return_value=("origin/feature", None)), \
             patch.object(hook, "has_uncommitted_changes", return_value=(False, None)), \
             patch.object(hook, "has_unpushed_commits", return_value=(True, None)):
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block", (
            f"expected block decision but got {out['decision']!r}"
        )
        assert "Please push committed changes to origin/feature" in out["reason"], (
            f"expected push reminder but got {out['reason']!r}"
        )

    def test_clean_tree_no_upstream(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Clean tree + no upstream -> no ahead check and no output."""
        with patch.object(hook, "get_upstream_ref", return_value=(None, "no upstream")), \
             patch.object(hook, "has_uncommitted_changes", return_value=(False, None)), \
             patch.object(hook, "has_unpushed_commits") as mock_ahead:
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        mock_ahead.assert_not_called()
        assert capsys.readouterr().out == "", (
            "expected no hook output when upstream is unavailable"
        )

    def test_error_checking_unpushed_commits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Ahead check errors stay silent to preserve hook contract."""
        with patch.object(hook, "get_upstream_ref", return_value=("origin/feature", None)), \
             patch.object(hook, "has_uncommitted_changes", return_value=(False, None)), \
             patch.object(hook, "has_unpushed_commits", return_value=(None, "oops")):
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        assert capsys.readouterr().out == "", (
            "expected no hook output when ahead check errors are suppressed"
        )


# ---------------------------------------------------------------------------
# parse_env - compush flag
# ---------------------------------------------------------------------------


class TestParseEnvCompush:
    """Tests for the compush flag in parse_env()."""

    def test_compush_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POST_TURN_COMPUSH", "1")
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is True, f"expected compush to be True but was {compush!r}"

    def test_compush_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POST_TURN_COMPUSH", raising=False)
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is False, f"expected compush to be False but was {compush!r}"

    def test_compush_truthy_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POST_TURN_COMPUSH", "yes")
        _base, _fetch, _max, compush = hook.parse_env()
        assert compush is True, f"expected compush to be True but was {compush!r}"


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
        assert rc == 0, f"expected run_stop_checks rc 0 but got {rc!r}"
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

    def test_compush_runs_when_no_files_changed(self) -> None:
        """compush=True still runs when there are no changed files to lint."""
        with patch.object(hook, "repo_root", return_value=(REPO, None)), \
             patch.object(hook, "ensure_base_ref", return_value=(True, None, False)), \
             patch.object(hook, "merge_base", return_value=("abc123", None)), \
             patch.object(hook, "changed_files", return_value=([], None)), \
             patch.object(hook, "evaluate_changes") as mock_evaluate, \
             patch.object(hook, "compush_check", return_value=0) as mock_compush, \
             patch("shutil.which", return_value="/usr/bin/git"):
            rc = hook.run_stop_checks(
                REPO, "origin/main", always_fetch=False, max_out=12000, compush=True
            )
        assert rc == 0, f"expected run_stop_checks rc 0 but got {rc!r}"
        mock_evaluate.assert_not_called()
        mock_compush.assert_called_once_with(REPO)

# ---------------------------------------------------------------------------
# run() - OSError resilience
# ---------------------------------------------------------------------------


class TestRunOSError:
    """Tests for run() handling of OSError (e.g. missing cwd)."""

    def test_nonexistent_cwd_returns_error(self) -> None:
        """run() with a nonexistent cwd returns rc=1 instead of raising."""
        missing_path = Path("/nonexistent/path")
        result = hook.run(["git", "status"], missing_path)
        assert result.returncode == 1, (
            f"expected returncode 1 for missing cwd but got {result.returncode!r}"
        )
        assert result.stderr, "expected stderr to describe missing cwd"
        assert str(missing_path) in result.stderr, (
            f"expected missing path in stderr but got {result.stderr!r}"
        )

    def test_run_stop_checks_nonexistent_cwd(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Full pipeline exits cleanly when start_cwd does not exist."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            rc = hook.run_stop_checks(
                Path("/nonexistent/path"),
                "origin/main",
                always_fetch=False,
                max_out=12000,
            )
        assert rc == 0, f"expected run_stop_checks rc 0 but got {rc!r}"
        assert capsys.readouterr().out == "", (
            "expected no hook output when start_cwd does not exist"
        )


class TestGetMakeTargets:
    """Tests for make target enumeration."""

    def test_missing_make_returns_error(self) -> None:
        """Missing `make` surfaces as an enumeration error."""
        with patch.object(
            hook,
            "run",
            side_effect=FileNotFoundError(2, "No such file or directory", "make"),
        ):
            targets, err = hook.get_make_targets(REPO)
        assert targets is None, (
            f"expected no make targets when make is missing but got {targets!r}"
        )
        assert err == "make not found on PATH", (
            f"expected make-not-found error but got {err!r}"
        )
