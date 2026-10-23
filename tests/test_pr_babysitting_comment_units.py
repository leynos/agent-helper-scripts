"""Exercise the comment helper's units by sourcing it with injected dependencies.

Sourcing the helper defines its units without running `main`. Each test then
replaces the GitHub client (`gh`), the clock (`now_ms`) or the run-ID source
(`new_run_id`) with a Bash function, so queries, decisions and publication are
tested separately and deterministically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from pr_babysitting_comment_test_support import HELPER


def _source_and_run(script: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Source the helper in a private Bash and run `script` against its units.

    Parameters
    ----------
    script : str
        Bash statements to run after the helper is sourced.
    tmp_path : Path
        Private directory used as the working directory and home.
    **env : str
        Extra environment variables for the script.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The finished Bash process with captured output.
    """
    prelude = 'set -uo pipefail\nsource "$HELPER"\n'
    return subprocess.run(
        ["/bin/bash", "-c", prelude + script], cwd=tmp_path,
        env={"HOME": str(tmp_path), "PATH": os.environ.get("PATH", ""), "HELPER": str(HELPER), **env},
        text=True, capture_output=True, check=False, timeout=10,
    )


def test_runner_keeps_caller_tool_directories_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tools such as jq installed outside /usr/bin stay reachable from the units."""
    tools = tmp_path / "caller-tools"
    tools.mkdir()
    marker = tools / "caller-only-tool"
    marker.write_text("#!/bin/sh\nprintf found\n")
    marker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}:{os.environ.get('PATH', '')}")
    result = _source_and_run("caller-only-tool", tmp_path)
    assert result.stdout == "found", "the runner must preserve the caller's PATH entries"


def test_sourcing_defines_units_without_running_main(tmp_path: Path) -> None:
    """Sourcing must not post, read the pool, or require arguments."""
    result = _source_and_run(
        "for unit in select_token query_login resolve_lifecycle_login verify_pool_identity "
        "publish_comment now_ms new_run_id token_pool_path main; do declare -F \"$unit\" >/dev/null || exit 3; done",
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "" and result.stderr == "", "sourcing must have no side effects"


def test_select_token_reads_only_the_explicit_pool_path(tmp_path: Path) -> None:
    """The pool path is an input; the unit never consults HOME."""
    pool = tmp_path / "elsewhere" / "pool"
    pool.parent.mkdir()
    pool.write_text("# comment\n\nonly-token\r\n")
    result = _source_and_run(
        'shuf() { head -n 1; }\nselect_token "$POOL" token && printf "%s" "$token"',
        tmp_path, POOL=str(pool),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "only-token", "select the single record, stripping CR and comments"


@pytest.mark.parametrize(
    ("pool_text", "category"),
    [(None, "token_pool_unavailable"), ("# only a comment\n\n", "token_not_selected")],
    ids=["missing", "empty"],
)
def test_select_token_classifies_unusable_pools(tmp_path: Path, pool_text: str | None, category: str) -> None:
    """An unusable pool returns status 2 and a category, never a token."""
    pool = tmp_path / "pool"
    if pool_text is not None:
        pool.write_text(pool_text)
    result = _source_and_run(
        'shuf() { head -n 1; }\nselect_token "$POOL" token; status=$?\n'
        'printf "%s %s %s" "$status" "$FAILURE_CATEGORY" "${token:-}"',
        tmp_path, POOL=str(pool),
    )
    assert result.stdout == f"2 {category} ", "report the category without selecting a token"


def test_lifecycle_lookup_is_a_query_without_publication(tmp_path: Path) -> None:
    """Resolving the lifecycle login reads identity with token variables removed and never posts."""
    result = _source_and_run(
        'gh() { printf "%s|%s\\n" "${GH_TOKEN-unset}" "$*" >> "$CALLS"; printf "%s\\n" stored-owner; }\n'
        'resolve_lifecycle_login "" "$PWD/err" login && printf "%s" "$login"',
        tmp_path, CALLS=str(tmp_path / "calls"), GH_TOKEN="ambient",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "stored-owner", "return the stored login"
    calls = (tmp_path / "calls").read_text().splitlines()
    assert calls == ["unset|api --hostname github.com user --jq .login"], (
        "exactly one identity query, with the ambient token removed and no POST"
    )


def test_publish_comment_uses_the_injected_client_once(tmp_path: Path) -> None:
    """Publication is the only write and sends the body through the supplied token."""
    body = tmp_path / "body.md"
    body.write_text("literal $(body)\n")
    result = _source_and_run(
        'gh() { printf "%s|%s|%s\\n" "$GH_TOKEN" "$GITHUB_TOKEN" "$*" >> "$CALLS"; cat > "$PAYLOAD"; '
        'printf "%s\\n" https://example.invalid/c/1; }\n'
        'publish_comment pool-token repos/o/r/issues/7/comments "$BODY" "$PWD/err" url && printf "%s" "$url"',
        tmp_path, CALLS=str(tmp_path / "calls"), PAYLOAD=str(tmp_path / "payload"), BODY=str(body),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "https://example.invalid/c/1", "return the new comment URL"
    assert (tmp_path / "calls").read_text().splitlines() == [
        "pool-token|pool-token|api --hostname github.com --method POST "
        "repos/o/r/issues/7/comments --input - --jq .html_url",
    ], "post once with both token variables scoped to the selected token"
    assert json.loads((tmp_path / "payload").read_text()) == {"body": "literal $(body)\n"}, (
        "encode the body literally"
    )


@pytest.mark.parametrize(
    ("stderr", "category", "http_status"),
    [
        ("HTTP 401: Bad credentials", "authentication_failed", "401"),
        ("HTTP 403: Resource not accessible", "permission_denied", "403"),
        ("HTTP 403: API rate limit exceeded", "rate_limited", "403"),
        ("HTTP 429: Too Many Requests", "rate_limited", "429"),
        ("HTTP 500: Internal Server Error", "server_error", "500"),
        ("HTTP 502: Bad Gateway", "server_error", "502"),
        ("dial tcp: lookup api.github.com: no such host", "network_error", ""),
        ("Post \"https://api.github.com\": unexpected EOF", "network_error", ""),
        ("net/http: TLS handshake timeout", "network_error", ""),
        ("error connecting to api.github.com\ncheck your internet connection or https://githubstatus.com",
         "network_error", ""),
        ("HTTP 422: Validation Failed", "github_api_failed", "422"),
        ("something else entirely", "github_api_failed", ""),
    ],
)
def test_failures_are_classified_without_raw_output(
    tmp_path: Path, stderr: str, category: str, http_status: str,
) -> None:
    """Authentication, permission, rate-limit, server, network and other failures stay distinct."""
    (tmp_path / "err").write_text(stderr + "\n")
    result = _source_and_run(
        'record_gh_failure "$PWD/err"; printf "%s|%s" "$FAILURE_CATEGORY" "$FAILURE_HTTP_STATUS"',
        tmp_path,
    )
    assert result.stdout == f"{category}|{http_status}", f"classify {stderr!r}"


def test_injected_clock_and_run_id_make_diagnostics_deterministic(tmp_path: Path) -> None:
    """Replacing now_ms and new_run_id fixes every diagnostic's run ID and elapsed time."""
    result = _source_and_run(
        'now_ms() { printf "%s\\n" 1000; }\nnew_run_id() { printf "%s\\n" 0123456789abcdef; }\n'
        'DIAG_RUN_ID=$(new_run_id) DIAG_SURFACE=issue_comment DIAG_REPOSITORY=o/r DIAG_PR=7\n'
        'log_diagnostic post "" 0 "$(now_ms)" ""',
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stderr) == {
        "operation": "manual_pr_comment", "run_id": "0123456789abcdef",
        "surface": "issue_comment", "repository": "o/r", "pr": "7", "stage": "post",
        "failure_category": None, "exit_status": 0, "elapsed_ms": 0, "http_status": None,
    }, "the injected clock and run-ID source fully determine the diagnostic"
