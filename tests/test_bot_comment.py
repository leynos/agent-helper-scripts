"""Process-level tests for `bin/bot-comment.sh`.

Most tests replace the pr-babysitting posting helper with a stub, through
`BOT_COMMENT_HELPER`, that records the arguments and body it receives. They
assert how each mode maps onto the helper and what the wrapper refuses before
anything is posted. One end-to-end test runs the real helper against a stub
`gh` and a temporary token pool, to show that the wrapper inherits the skill's
manual-comment identity contract. Nothing touches the network or the real home
directory.
"""

from __future__ import annotations

import os
import subprocess
import typing as typ
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "bin" / "bot-comment.sh"

#: Records its arguments and the body file's contents, prints a URL and exits
#: with `HELPER_STATUS` (default 0).
_HELPER_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" > "$STUB_LOG_DIR/helper.args"
cat -- "$3" > "$STUB_LOG_DIR/helper.body"
printf '%s\\n' 'https://github.com/example/repo/pull/1#issuecomment-9'
exit "${HELPER_STATUS:-0}"
"""

#: A `gh` stand-in for the real helper: `api user` reports the pool account
#: when a token is scoped to the call and the lifecycle account otherwise; a
#: POST records its endpoint, token and payload and prints a URL.
_GH_STUB = """#!/usr/bin/env bash
args="$*"
if [[ $args == *" user "* ]]; then
  if [[ -n ${GH_TOKEN:-} ]]; then echo "${POOL_LOGIN:-pool-bot}"; else echo owner; fi
  exit 0
fi
printf '%s\\n' "$args" > "$STUB_LOG_DIR/gh.args"
printf '%s' "${GH_TOKEN:-}" > "$STUB_LOG_DIR/gh.token"
cat > "$STUB_LOG_DIR/gh.stdin"
echo 'https://github.com/example/repo/pull/1#issuecomment-9'
"""

BODY = "@coderabbitai is this fixed?\n"
POOL_TOKEN = "pool-secret-token-value"


class Run(typ.NamedTuple):
    """One run of the script and what its stubs recorded."""

    completed: subprocess.CompletedProcess[str]
    log_dir: Path

    def recorded(self, name: str) -> str | None:
        """Return a stub record, or `None` if that stub never ran."""
        path = self.log_dir / name
        return path.read_text(encoding="utf-8") if path.exists() else None


def _stub(directory: Path, name: str, source: str) -> Path:
    """Write an executable stub called *name* into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run(
    tmp_path: Path,
    args: list[str],
    body: str | None = BODY,
    env: dict[str, str] | None = None,
    *,
    real_helper: bool = False,
) -> Run:
    """Run the script with stubbed collaborators and *body*."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    stubs = tmp_path / "stubs"
    _stub(stubs, "gh", _GH_STUB)
    body_file = tmp_path / "body.md"
    if body is not None:
        body_file.write_text(body, encoding="utf-8")
    full_env = {
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(home),
        "STUB_LOG_DIR": str(log_dir),
    }
    if real_helper:
        pool = home / ".local" / "share" / "github-tokens"
        pool.parent.mkdir(parents=True)
        pool.write_text(f"# comment-token pool\n{POOL_TOKEN}\n", encoding="utf-8")
    else:
        helper = _stub(tmp_path / "helper", "post-manual-comment.sh", _HELPER_STUB)
        full_env["BOT_COMMENT_HELPER"] = str(helper)
    full_env.update(env or {})
    argv = [str(SCRIPT), *[str(body_file) if a == "BODY" else a for a in args]]
    completed = subprocess.run(  # noqa: S603 - fixed script path, test argv
        argv, capture_output=True, text=True, env=full_env, check=False
    )
    return Run(completed, log_dir)


@pytest.mark.parametrize(
    ("args", "helper_args"),
    [
        (["pr", "example/repo", "12", "BODY"], "example/repo 12 {body}"),
        (["issue", "example/repo", "7", "BODY"], "example/repo 7 {body}"),
        (["reply", "example/repo", "12", "345", "BODY"], "example/repo 12 {body} 345"),
    ],
)
def test_modes_map_onto_the_skill_helper(
    tmp_path: Path, args: list[str], helper_args: str
) -> None:
    """Each mode calls the pr-babysitting helper with its argument order."""
    run = _run(tmp_path, args)
    assert run.completed.returncode == 0, run.completed.stderr
    body_path = tmp_path / "body.md"
    assert run.recorded("helper.args") == helper_args.format(body=body_path) + "\n"
    assert run.recorded("helper.body") == BODY
    assert run.completed.stdout == (
        "https://github.com/example/repo/pull/1#issuecomment-9\n"
    )


def test_helper_failure_status_is_returned(tmp_path: Path) -> None:
    """A helper failure (for example a lifecycle-account token) propagates."""
    run = _run(
        tmp_path, ["issue", "example/repo", "7", "BODY"], env={"HELPER_STATUS": "7"}
    )
    assert run.completed.returncode == 7


@pytest.mark.parametrize(
    "body",
    ["@coderabbitai review\n", "Please, @CodeRabbitAI  full review this.\n"],
)
def test_refuses_review_requests(tmp_path: Path, body: str) -> None:
    """Review requests belong to comenq-coderabbit and are never posted."""
    run = _run(tmp_path, ["issue", "example/repo", "7", "BODY"], body=body)
    assert run.completed.returncode == 3
    assert "comenq" in run.completed.stderr
    assert run.recorded("helper.args") is None


def test_pr_comment_needs_the_mention(tmp_path: Path) -> None:
    """A PR-level comment must open with the mention unless opted out."""
    refused = _run(tmp_path / "a", ["pr", "example/repo", "1", "BODY"], body="Hi\n")
    assert refused.completed.returncode == 4
    assert refused.recorded("helper.args") is None

    allowed = _run(
        tmp_path / "b",
        ["pr", "example/repo", "1", "BODY"],
        body="Hi\n",
        env={"BOT_COMMENT_NO_MENTION": "1"},
    )
    assert allowed.completed.returncode == 0, allowed.completed.stderr


@pytest.mark.parametrize("mode_args", [["issue", "1"], ["reply", "1", "2"]])
def test_issue_comments_and_replies_need_no_mention(
    tmp_path: Path, mode_args: list[str]
) -> None:
    """Only top-level PR comments are held to the mention rule."""
    mode, *rest = mode_args
    run = _run(tmp_path, [mode, "example/repo", *rest, "BODY"], body="Fixed.\n")
    assert run.completed.returncode == 0, run.completed.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["pr", "example/repo;id", "1", "BODY"],
        ["pr", "example/repo", "1;id", "BODY"],
        ["pr", "example/repo", "$(id)", "BODY"],
        ["pr", "example/repo", "0", "BODY"],
        ["reply", "example/repo", "1", "2x", "BODY"],
        ["pr", "example/repo", "1"],
        ["merge", "example/repo", "1", "BODY"],
        [],
    ],
)
def test_rejects_bad_arguments(tmp_path: Path, args: list[str]) -> None:
    """Malformed arguments fail with status 2 before the helper runs."""
    run = _run(tmp_path, args)
    assert run.completed.returncode == 2
    assert run.recorded("helper.args") is None


def test_rejects_an_empty_body(tmp_path: Path) -> None:
    """An empty body file is refused."""
    run = _run(tmp_path, ["issue", "example/repo", "1", "BODY"], body="")
    assert run.completed.returncode == 2
    assert run.recorded("helper.args") is None


def test_fails_when_the_helper_is_missing(tmp_path: Path) -> None:
    """A missing helper fails before anything is posted."""
    run = _run(
        tmp_path,
        ["issue", "example/repo", "1", "BODY"],
        env={"BOT_COMMENT_HELPER": str(tmp_path / "absent.sh")},
    )
    assert run.completed.returncode != 0
    assert run.recorded("helper.args") is None


def test_real_helper_posts_with_a_pool_token(tmp_path: Path) -> None:
    """Through the real helper, a pool token posts and is never printed."""
    run = _run(tmp_path, ["pr", "example/repo", "12", "BODY"], real_helper=True)
    assert run.completed.returncode == 0, run.completed.stderr
    assert run.recorded("gh.args") == (
        "api --hostname github.com --method POST"
        " repos/example/repo/issues/12/comments --input - --jq .html_url\n"
    )
    assert run.recorded("gh.token") == POOL_TOKEN
    assert '"body": "@coderabbitai is this fixed?\\n"' in (run.recorded("gh.stdin") or "")
    assert run.completed.stdout == (
        "https://github.com/example/repo/pull/1#issuecomment-9\n"
    )
    assert POOL_TOKEN not in run.completed.stdout + run.completed.stderr


def test_real_helper_refuses_a_lifecycle_account_token(tmp_path: Path) -> None:
    """A pool token that authenticates as the lifecycle account never posts."""
    run = _run(
        tmp_path,
        ["issue", "example/repo", "7", "BODY"],
        env={"POOL_LOGIN": "owner"},
        real_helper=True,
    )
    assert run.completed.returncode != 0
    assert "unexpected_owner_identity" in run.completed.stderr
    assert run.recorded("gh.args") is None
