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
from unittest.mock import call, patch

import pytest


def _load_hook_module() -> ModuleType:
    """Load the hook script as a module despite the dashes in the filename."""
    hook_path = Path(__file__).parent / "post-turn-quality-stop-hook.py"
    # The module name must match the path-derived name mutmut assigns
    # ("hooks.<file stem>"), so mutation runs can attribute trampoline
    # hits recorded by this suite to the mutants it generates.
    spec = importlib.util.spec_from_file_location(
        "hooks.post-turn-quality-stop-hook", hook_path
    )
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
    """Build a ``CompletedProcess`` stub with the given return code and output."""
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
        assert mock_run.call_args_list == [
            call(["git", "diff", "--quiet"], REPO),
            call(["git", "diff", "--cached", "--quiet"], REPO),
            call(["git", "ls-files", "--others", "--exclude-standard"], REPO),
        ], f"unexpected git commands: {mock_run.call_args_list!r}"

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
        assert err == "git diff --quiet failed: fatal: bad", (
            f"expected exact diff failure message but got {err!r}"
        )

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
        assert err == "git ls-files failed: fatal: oops", (
            f"expected exact ls-files failure message but got {err!r}"
        )


# ---------------------------------------------------------------------------
# get_upstream_ref
# ---------------------------------------------------------------------------


class TestGetUpstreamRef:
    """Tests for get_upstream_ref()."""

    def test_returns_upstream(self) -> None:
        """Successful rev-parse --abbrev-ref returns the tracking ref."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="origin/main\n")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref == "origin/main", f"expected upstream ref origin/main but got {ref!r}"
        assert err is None, f"expected no error but got {err!r}"
        assert mock_run.call_args_list == [
            call(
                ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                REPO,
            ),
        ], f"unexpected git commands: {mock_run.call_args_list!r}"

    def test_no_upstream(self) -> None:
        """Non-zero rev-parse exit returns None."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="no upstream")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None, f"expected no upstream ref but got {ref!r}"
        assert err == "no upstream", (
            f"expected the exact stderr message but got {err!r}"
        )

    def test_empty_stdout(self) -> None:
        """Empty stdout from rev-parse returns None."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="")
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None, f"expected no upstream ref but got {ref!r}"
        assert err == "git rev-parse returned empty upstream", (
            f"expected exact empty-upstream message but got {err!r}"
        )

    def test_error_fallback_message(self) -> None:
        """Failure with silent stderr/stdout uses the fallback message."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128)
            ref, err = hook.get_upstream_ref(REPO)
        assert ref is None, f"expected no upstream ref but got {ref!r}"
        assert err == "no upstream configured", (
            f"expected exact fallback message but got {err!r}"
        )


# ---------------------------------------------------------------------------
# has_unpushed_commits
# ---------------------------------------------------------------------------


class TestHasUnpushedCommits:
    """Tests for has_unpushed_commits()."""

    def test_ahead_of_upstream(self) -> None:
        """Positive rev-list count returns True."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="2\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is True, f"expected ahead to be True but was {ahead!r}"
        assert err is None, f"expected no error but got {err!r}"
        assert mock_run.call_args_list == [
            call(["git", "rev-list", "--count", "origin/main..HEAD"], REPO),
        ], f"unexpected git commands: {mock_run.call_args_list!r}"

    def test_ahead_by_exactly_one(self) -> None:
        """A rev-list count of exactly 1 is still ahead."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="1\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is True, f"expected ahead to be True for count 1 but was {ahead!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_not_ahead_of_upstream(self) -> None:
        """Zero rev-list count returns False."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="0\n")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is False, f"expected ahead to be False but was {ahead!r}"
        assert err is None, f"expected no error but got {err!r}"

    def test_rev_list_error(self) -> None:
        """Non-zero rev-list exit returns None."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(128, stderr="fatal: bad revision")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is None, f"expected ahead to be None on error but was {ahead!r}"
        assert err is not None, "expected an error message from rev-list failure"
        assert "fatal: bad revision" in err, (
            f"expected bad revision error in message but got {err!r}"
        )

    def test_empty_output(self) -> None:
        """Empty rev-list output returns None with an error message."""
        with patch.object(hook, "run") as mock_run:
            mock_run.return_value = _completed(0, stdout="")
            ahead, err = hook.has_unpushed_commits(REPO, "origin/main")
        assert ahead is None, f"expected ahead to be None for empty output but was {ahead!r}"
        assert err == "git rev-list --count returned empty output", (
            f"expected exact empty-output message but got {err!r}"
        )

    def test_non_integer_output(self) -> None:
        """Non-integer rev-list output returns None."""
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
        with patch.object(hook, "has_uncommitted_changes", return_value=(True, None)) as mock_dirty, \
             patch.object(hook, "get_upstream_ref", return_value=("origin/feature", None)) as mock_upstream:
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        mock_upstream.assert_called_once_with(REPO)
        mock_dirty.assert_called_once_with(REPO)
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block", (
            f"expected block decision but got {out['decision']!r}"
        )
        assert out["reason"] == "Please commit and push to origin/feature", (
            f"expected exact commit/push reminder but got {out['reason']!r}"
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
        assert out["reason"] == (
            "Please commit and push to origin (upstream not configured)"
        ), f"expected exact upstream fallback reason but got {out['reason']!r}"

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
             patch.object(hook, "has_unpushed_commits", return_value=(True, None)) as mock_ahead:
            rc = hook.compush_check(REPO)
        assert rc == 0, f"expected compush_check rc 0 but got {rc!r}"
        mock_ahead.assert_called_once_with(REPO, "origin/feature")
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block", (
            f"expected block decision but got {out['decision']!r}"
        )
        assert out["reason"] == "Please push committed changes to origin/feature", (
            f"expected exact push reminder but got {out['reason']!r}"
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
        assert result.args == ["git", "status"], (
            f"expected fallback args to echo the command but got {result.args!r}"
        )
        assert result.stdout == "", (
            f"expected empty fallback stdout but got {result.stdout!r}"
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

    def test_real_command_captures_text_output(self, tmp_path: Path) -> None:
        """run() captures decoded stdout/stderr and the real exit code."""
        result = hook.run(["sh", "-c", "echo out; echo err >&2; exit 3"], tmp_path)
        assert result.returncode == 3, (
            f"expected returncode 3 but got {result.returncode!r}"
        )
        assert result.stdout == "out\n", (
            f"expected decoded stdout 'out\\n' but got {result.stdout!r}"
        )
        assert result.stderr == "err\n", (
            f"expected decoded stderr 'err\\n' but got {result.stderr!r}"
        )

    def test_file_as_cwd_returns_error(self, tmp_path: Path) -> None:
        """run() with a file as cwd returns the NotADirectoryError fallback."""
        file_cwd = tmp_path / "not-a-dir"
        file_cwd.write_text("plain file\n")
        cmd = ["git", "status"]
        result = hook.run(cmd, file_cwd)
        assert result.returncode == 1, (
            f"expected returncode 1 for file cwd but got {result.returncode!r}"
        )
        assert result.args == cmd, (
            f"expected fallback args to echo the command but got {result.args!r}"
        )
        assert result.stdout == "", (
            f"expected empty fallback stdout but got {result.stdout!r}"
        )
        assert "director" in result.stderr.lower(), (
            f"expected stderr to describe the directory error but got {result.stderr!r}"
        )

    def test_filename_less_file_not_found_uses_fallback(self) -> None:
        """A FileNotFoundError without a filename maps to the cwd fallback."""
        exc = FileNotFoundError(2, "No such file or directory")
        with patch.object(hook.subprocess, "run", side_effect=exc):
            result = hook.run(["git", "status"], Path("."))
        assert result.returncode == 1, (
            f"expected fallback returncode 1 but got {result.returncode!r}"
        )
        assert result.args == ["git", "status"], (
            f"expected fallback args to echo the command but got {result.args!r}"
        )


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------


TRUNCATE_MARKER = "\n... (output truncated) ...\n"


class TestTruncate:
    """Tests for truncate()."""

    @pytest.mark.parametrize(
        ("text", "max_chars", "expected"),
        [
            ("abc", 0, ""),
            ("abc", -1, ""),
            ("abc", 3, "abc"),
            ("abc", 10, "abc"),
            ("A" * 100, len(TRUNCATE_MARKER), "A" * len(TRUNCATE_MARKER)),
            ("A" * 100, 5, "AAAAA"),
            ("A" * 100, 1, "A"),
            # remaining = 50 - 28 = 22 -> head 11, tail 11
            ("A" * 40 + "B" * 40, 50, "A" * 11 + TRUNCATE_MARKER + "B" * 11),
            # remaining = 51 - 28 = 23 -> head 11, tail 12
            ("A" * 40 + "B" * 40, 51, "A" * 11 + TRUNCATE_MARKER + "B" * 12),
        ],
    )
    def test_truncation(self, text: str, max_chars: int, expected: str) -> None:
        """truncate() keeps boundaries and the exact head/tail split."""
        result = hook.truncate(text, max_chars)
        assert result == expected, (
            f"truncate({len(text)} chars, {max_chars}) returned {result!r}, "
            f"expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# parse_make_targets / is_missing_makefile
# ---------------------------------------------------------------------------


class TestParseMakeTargets:
    """Tests for parse_make_targets()."""

    def test_parses_representative_output(self) -> None:
        """Targets are extracted; comments, recipes, and patterns are not."""
        make_stdout = "\n".join(
            [
                "# comment: not-a-target",
                "FOO = bar",
                "all: dep1 dep2",
                "\trecipe: ignored",
                " indented: ignored",
                "",
                "build install: common",
                "%.o: %.c",
                "tmpl-% cleanup: dep",
                "check:: double-colon",
                "no-colon-line",
            ]
        )
        targets = hook.parse_make_targets(make_stdout)
        assert targets == {"all", "build", "install", "cleanup", "check"}, (
            f"unexpected parsed targets: {targets!r}"
        )


class TestIsMissingMakefile:
    """Tests for is_missing_makefile()."""

    @pytest.mark.parametrize(
        ("output", "expected"),
        [
            ("make: *** No makefile found.  Stop.", True),
            ("MAKE: *** NO MAKEFILE FOUND.  STOP.", True),
            ("make: *** missing separator.  Stop.", False),
            ("", False),
        ],
    )
    def test_detection(self, output: str, expected: bool) -> None:
        """Missing-makefile detection is case-insensitive and literal."""
        result = hook.is_missing_makefile(output)
        assert result is expected, (
            f"is_missing_makefile({output!r}) returned {result!r}, "
            f"expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# detect_categories / default_categories / targets_for_categories
# ---------------------------------------------------------------------------


class TestDefaultCategories:
    """Tests for default_categories()."""

    def test_exact_mapping(self) -> None:
        """The default mapping names every category, disabled."""
        assert hook.default_categories() == {
            "python_ts": False,
            "rust": False,
            "markdown": False,
        }, f"unexpected default categories: {hook.default_categories()!r}"


class TestDetectCategories:
    """Tests for detect_categories()."""

    @pytest.mark.parametrize(
        ("files", "expected"),
        [
            ([], {"python_ts": False, "rust": False, "markdown": False}),
            (["a.py"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.pyi"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.ts"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.tsx"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.mts"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.cts"], {"python_ts": True, "rust": False, "markdown": False}),
            (["a.RS"], {"python_ts": False, "rust": True, "markdown": False}),
            (["b.md"], {"python_ts": False, "rust": False, "markdown": True}),
            (["b.mdx"], {"python_ts": False, "rust": False, "markdown": True}),
            (["b.markdown"], {"python_ts": False, "rust": False, "markdown": True}),
            (["c.txt", "Makefile"], {"python_ts": False, "rust": False, "markdown": False}),
            (
                ["a.py", "b.rs", "c.md"],
                {"python_ts": True, "rust": True, "markdown": True},
            ),
        ],
    )
    def test_mapping(self, files: list[str], expected: dict[str, bool]) -> None:
        """Each extension group maps to exactly its category."""
        result = hook.detect_categories(files)
        assert result == expected, (
            f"detect_categories({files!r}) returned {result!r}, expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# format_reason
# ---------------------------------------------------------------------------


class TestFormatReason:
    """Tests for format_reason()."""

    def test_error_only_state(self) -> None:
        """An error with no base ref or changes renders placeholders exactly."""
        state = hook.HookState(base_ref="")
        state.error = "boom"
        expected = "\n".join(
            [
                "Post-turn checks failed.",
                "",
                "Error: boom",
                "",
                "Diff base: ? (?)",
                "",
                "Changed files vs ?: 0",
                "",
                "Fix the failures above. The checks will re-run at the end of"
                " the next turn.",
            ]
        )
        assert hook.format_reason(state) == expected, (
            f"unexpected minimal reason: {hook.format_reason(state)!r}"
        )

    def test_full_state(self) -> None:
        """Categories, targets, and failing commands render exactly."""
        state = hook.HookState(base_ref="origin/dev")
        state.base_commit = "abc123"
        state.changed_files = ["a.py", "b.rs", "c.md"]
        state.categories = {"python_ts": True, "rust": True, "markdown": True}
        state.make_targets_requested = [
            "check-fmt", "lint", "typecheck", "markdownlint",
        ]
        state.make_targets_run = ["check-fmt", "lint"]
        state.make_targets_skipped = ["typecheck", "markdownlint"]
        state.commands = [
            {"cmd": "make check-fmt lint", "exit_code": 0, "stdout": "ok", "stderr": ""},
            {
                "cmd": "make markdownlint",
                "exit_code": 2,
                "stdout": "bad heading",
                "stderr": "lint error",
            },
            {"cmd": "make mystery", "exit_code": 1, "stdout": "", "stderr": ""},
            {"exit_code": 3},
        ]
        expected = "\n".join(
            [
                "Post-turn checks failed.",
                "",
                "Diff base: origin/dev (abc123)",
                "",
                "Changed files vs origin/dev: 3",
                "- a.py",
                "- b.rs",
                "- c.md",
                "",
                "Detected change types: Python/TypeScript, Rust, Markdown",
                "",
                "Requested make targets: check-fmt lint typecheck markdownlint",
                "Targets run: check-fmt lint",
                "Targets skipped (missing): typecheck markdownlint",
                "",
                "Command failed (exit 2): make markdownlint",
                "```",
                "bad heading\nlint error",
                "```",
                "",
                "Command failed (exit 1): make mystery",
                "```",
                "(no output captured)",
                "```",
                "",
                "Command failed (exit 3): ",
                "```",
                "(no output captured)",
                "```",
                "",
                "Fix the failures above. The checks will re-run at the end of"
                " the next turn.",
            ]
        )
        assert hook.format_reason(state) == expected, (
            f"unexpected full reason: {hook.format_reason(state)!r}"
        )

    def test_file_list_truncation_boundary(self) -> None:
        """Exactly 60 files list fully; 61 files elide the last one."""
        state = hook.HookState()
        state.changed_files = [f"f{i:03d}.txt" for i in range(60)]
        reason = hook.format_reason(state)
        assert "- f059.txt" in reason, "expected the 60th file to be listed"
        assert "(+" not in reason, "expected no elision marker for 60 files"

        state.changed_files = [f"f{i:03d}.txt" for i in range(61)]
        reason = hook.format_reason(state)
        assert "Changed files vs origin/main: 61" in reason, (
            "expected the changed-file count to be reported"
        )
        assert "- f059.txt" in reason, "expected the 60th file to be listed"
        assert "- f060.txt" not in reason, "expected the 61st file to be elided"
        assert "- … (+1 more)" in reason, "expected the exact elision marker"

    def test_missing_exit_code_defaults_to_success(self) -> None:
        """A command without an exit code is not reported as a failure."""
        state = hook.HookState()
        state.commands = [{"cmd": "make quiet", "stdout": "", "stderr": ""}]
        assert "Command failed" not in hook.format_reason(state), (
            "expected commands without exit codes to be treated as successes"
        )


# ---------------------------------------------------------------------------
# parse_env / parse_max_output
# ---------------------------------------------------------------------------


ENV_VARS = (
    "POST_TURN_BASE_REF",
    "POST_TURN_ALWAYS_FETCH",
    "POST_TURN_MAX_OUTPUT_CHARS",
    "POST_TURN_COMPUSH",
)


class TestParseEnv:
    """Tests for the full parse_env() tuple."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no variables set, every default is returned exactly."""
        for name in ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        assert hook.parse_env() == ("origin/main", False, 12000, False), (
            f"unexpected parse_env defaults: {hook.parse_env()!r}"
        )

    def test_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each variable overrides its element of the tuple."""
        monkeypatch.setenv("POST_TURN_BASE_REF", "origin/develop")
        monkeypatch.setenv("POST_TURN_ALWAYS_FETCH", "1")
        monkeypatch.setenv("POST_TURN_MAX_OUTPUT_CHARS", "500")
        monkeypatch.setenv("POST_TURN_COMPUSH", "true")
        assert hook.parse_env() == ("origin/develop", True, 500, True), (
            f"unexpected parse_env overrides: {hook.parse_env()!r}"
        )


class TestParseMaxOutput:
    """Tests for parse_max_output()."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("7", 7), ("not-a-number", 12000), ("", 12000)],
    )
    def test_parse(self, value: str, expected: int) -> None:
        """Valid integers parse; anything else yields the default."""
        result = hook.parse_max_output(value)
        assert result == expected, (
            f"parse_max_output({value!r}) returned {result!r}, expected {expected!r}"
        )
