"""Exercise the shipped comment helper with dummy principals and no network."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMMENTS = ROOT / "skills/pr-babysitting/references/comments.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
HELPER = ROOT / "skills/pr-babysitting/scripts/post-manual-comment.sh"
BODY = '@coderabbitai Please check "this".\n\n£ and $(not-a-command) stay literal.\n'
URL = "https://example.invalid/comments/101"
TOKENS = [f"fixture-pool-{index}" for index in range(3)]
OWNER = "fixture-owner"
REPO = "example-owner/example"


GH_DOUBLE = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
config = json.loads((root / "fixture.json").read_text())
args = sys.argv[1:]
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
tokens = [f"fixture-pool-{index}" for index in range(3)]
scoped = token in tokens
principal = f"comment-agent-{tokens.index(token)}" if scoped else config["owner"]
if scoped and config["login"] is not None:
    principal = config["login"]
identity = args in (["api", "user", "--jq", ".login"],
                   ["api", "--hostname", "github.com", "user", "--jq", ".login"])
post = (len(args) == 10 and args[:5] ==
        ["api", "--hostname", "github.com", "--method", "POST"] and
        args[6:] == ["--input", "-", "--jq", ".html_url"])
if not identity and not post:
    raise SystemExit("unexpected operation; account switches and reviews forbidden")
method = "GET" if identity else "POST"
event = {"method": method, "principal": principal, "args": args, "scoped": scoped,
         "both_overridden": scoped and os.environ.get("GITHUB_TOKEN") == token,
         "token_env_absent": "GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ,
         "debug": os.environ.get("GH_DEBUG")}
if post:
    event["payload"] = json.load(sys.stdin)
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(event) + "\\n")
if scoped and config["failure_stage"] == method:
    print(f"HTTP {config['failure_code']}: fixture service failure", file=sys.stderr)
    raise SystemExit(1)
if not scoped and event["token_env_absent"] and config["lifecycle_failure"]:
    print("HTTP 401: fixture stored-login failure", file=sys.stderr)
    raise SystemExit(1)
print(principal if identity else "https://example.invalid/comments/101")
'''

SHUF_DOUBLE = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
config = json.loads((root / "fixture.json").read_text())
assert sys.argv[1:] == ["-n", "1"], "select exactly one pool token"
records = sys.stdin.read().splitlines()
with (root / "selections.jsonl").open("a") as log:
    log.write(json.dumps({"count": len(records), "index": config["selected"]}) + "\\n")
if records:
    print(records[config["selected"]])
'''


@dataclass(frozen=True)
class _CommentHarness:
    root: Path
    bin_dir: Path
    config_file: Path
    body_file: Path
    pool_file: Path


@dataclass(frozen=True)
class _PostResult:
    result: subprocess.CompletedProcess[str]
    lifecycle: list[dict[str, object]]
    scoped: list[dict[str, object]]
    choices: list[dict[str, object]]

    def diagnostics(self) -> list[dict[str, object]]:
        """Return the structured diagnostic lines from standard error."""
        return [
            json.loads(line) for line in self.result.stderr.splitlines() if line.startswith("{")
        ]

    def diagnostic(self, stage: str) -> dict[str, object]:
        """Return the single diagnostic emitted for one stage."""
        matches = [event for event in self.diagnostics() if event["stage"] == stage]
        assert len(matches) == 1, f"expected one {stage} diagnostic"
        return matches[0]


@pytest.fixture
def manual_comment_harness(tmp_path: Path) -> _CommentHarness:
    """Provision a private home, token pool and executable doubles per test."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, source in (("gh", GH_DOUBLE), ("shuf", SHUF_DOUBLE)):
        executable = bin_dir / name
        executable.write_text(f"#!{sys.executable} -S\n{source}")
        executable.chmod(0o755)

    pool_file = tmp_path / ".local/share/github-tokens"
    pool_file.parent.mkdir(parents=True)
    pool_file.write_text("# fixture credentials only\n\n" + "\n".join(TOKENS) + "\n")
    body_file = tmp_path / "body.md"
    body_file.write_text(BODY)
    return _CommentHarness(
        root=tmp_path,
        bin_dir=bin_dir,
        config_file=tmp_path / "fixture.json",
        body_file=body_file,
        pool_file=pool_file,
    )


@dataclass(frozen=True)
class _Scenario:
    """One posting scenario: fixture behaviour and the helper's environment."""

    selected: int = 0
    inline: bool = False
    login: str | None = None
    failure_stage: str = ""
    failure_code: int = 0
    pool_state: str = "valid"
    inherited: bool = True
    lifecycle_failure: bool = False
    lifecycle_override: str | None = None

    def fixture_config(self) -> dict[str, object]:
        """Return the settings the gh and shuf doubles read."""
        return {
            "selected": self.selected, "login": self.login,
            "failure_stage": self.failure_stage, "failure_code": self.failure_code,
            "owner": OWNER, "lifecycle_failure": self.lifecycle_failure,
        }

    def environment(self, harness: _CommentHarness) -> dict[str, str]:
        """Return a private environment, optionally inheriting owner tokens."""
        env = {
            "HOME": str(harness.root), "XDG_CONFIG_HOME": str(harness.root / "config"),
            "PATH": f"{harness.bin_dir}:/usr/bin:/bin", "FIXTURE_ROOT": str(harness.root),
            "BODY_FILE": str(harness.body_file),
            "ROOT_COMMENT_ID": SURFACES[self.inline]["root_comment_id"],
            "GH_DEBUG": "api", "HELPER": str(HELPER), "REPO": REPO, "OWNER": OWNER,
        }
        if self.inherited:
            env.update(GH_TOKEN="fixture-owner-gh", GITHUB_TOKEN="fixture-owner-github")
        if self.lifecycle_override is not None:
            env["PR_BABYSITTING_LIFECYCLE_LOGIN"] = self.lifecycle_override
        return env


SURFACES: dict[bool, dict[str, str]] = {
    False: {"root_comment_id": "", "surface": "issue_comment", "endpoint": "issues/7/comments"},
    True: {"root_comment_id": "456", "surface": "inline_reply", "endpoint": "pulls/7/comments/456/replies"},
}
POOL_CONTENTS = {
    "valid": "# fixture credentials only\n\n" + "\n".join(TOKENS) + "\n",
    "empty": "# fixture credentials only\n\n\n",
}
POST_SCRIPT = '''
before=$(gh api user --jq '.login')
/bin/bash -x "$HELPER" "$REPO" 7 "$BODY_FILE" ${ROOT_COMMENT_ID:+"$ROOT_COMMENT_ID"}
result=$?
after=$(gh api user --jq '.login')
[[ "$before" == "$OWNER" && "$after" == "$OWNER" ]] || exit 90
exit "$result"
'''


def _write_pool(harness: _CommentHarness, pool_state: str) -> None:
    """Install the requested pool contents, or remove the pool entirely."""
    harness.pool_file.unlink()
    if pool_state in POOL_CONTENTS:
        harness.pool_file.write_text(POOL_CONTENTS[pool_state])


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read one JSON record per line, treating an absent log as empty."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _split_helper_calls(
    calls: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Separate the helper's lifecycle lookup from its pool-token calls."""
    assert calls[0]["principal"] == calls[-1]["principal"] == OWNER, "normal identity must survive"
    assert not calls[0]["scoped"] and not calls[-1]["scoped"], "normal reads must not inherit pool credentials"
    helper_calls = calls[1:-1]
    assert all(call["debug"] is None for call in helper_calls), "helper calls must not enable debug output"
    lifecycle = [call for call in helper_calls if not call["scoped"]]
    scoped = [call for call in helper_calls if call["scoped"]]
    assert all(call["token_env_absent"] for call in lifecycle), (
        "the lifecycle lookup must read stored authentication with token variables removed"
    )
    assert all(call["method"] == "GET" for call in lifecycle), "the lifecycle lookup is read-only"
    assert all(call["both_overridden"] for call in scoped), "each pool call must use both scoped credentials"
    return lifecycle, scoped


def _run_post(harness: _CommentHarness, scenario: _Scenario = _Scenario()) -> _PostResult:
    """Configure one scenario and invoke the shipped helper under tracing."""
    harness.config_file.write_text(json.dumps(scenario.fixture_config()))
    _write_pool(harness, scenario.pool_state)
    result = subprocess.run(
        ["/bin/bash", "-c", POST_SCRIPT], cwd=harness.root, env=scenario.environment(harness),
        text=True, capture_output=True, check=False, timeout=10,
    )
    assert not any(token in result.stdout + result.stderr for token in TOKENS), "tracing must never expose pool tokens"
    lifecycle, scoped = _split_helper_calls(_read_jsonl(harness.root / "calls.jsonl"))
    return _PostResult(result, lifecycle, scoped, _read_jsonl(harness.root / "selections.jsonl"))


def _assert_success_diagnostics(run: _PostResult, surface: str) -> None:
    """Success diagnostics are structured and carry only bounded context."""
    diagnostics = run.diagnostics()
    assert [event["stage"] for event in diagnostics] == [
        "token_selection", "lifecycle_identity", "identity_preflight", "post",
    ]
    expected = {
        "operation": "manual_pr_comment", "surface": surface, "repository": REPO,
        "pr": "7", "failure_category": None, "exit_status": 0,
    }
    assert [{key: event[key] for key in expected} for event in diagnostics] == [expected] * 4, (
        "success diagnostics must be structured and contain only bounded context"
    )
    assert all(isinstance(event["elapsed_ms"], int) for event in diagnostics)
    assert min(event["elapsed_ms"] for event in diagnostics) >= 0
    diagnostic_text = json.dumps(diagnostics)
    assert not any(token in diagnostic_text for token in TOKENS)
    assert "comment-agent-" not in diagnostic_text
    assert OWNER not in diagnostic_text


@pytest.mark.parametrize("selected", range(3), ids=["first-account", "second-account", "third-account"])
@pytest.mark.parametrize("inline", [False, True], ids=["issue-comment", "inline-reply"])
@pytest.mark.parametrize("inherited", [False, True], ids=["stored-owner", "environment-owner"])
def test_non_owner_pool_principal_posts_without_changing_lifecycle_identity(
    manual_comment_harness: _CommentHarness, selected: int, inline: bool, inherited: bool,
) -> None:
    """All three authorized non-owner accounts work for both comment surfaces."""
    run = _run_post(
        manual_comment_harness, _Scenario(selected=selected, inline=inline, inherited=inherited),
    )
    assert run.result.returncode == 0, run.result.stderr
    assert run.result.stdout == URL + "\n", "posting must return the comment URL"
    assert len(run.lifecycle) == 1, "look up the lifecycle account once"
    assert [call["method"] for call in run.scoped] == ["GET", "POST"], "verify selected identity then post once"
    assert all(call["principal"] == f"comment-agent-{selected}" for call in run.scoped), "check and post must use the same non-owner identity"
    surface = SURFACES[inline]
    assert run.scoped[-1]["args"][5] == f"repos/{REPO}/{surface['endpoint']}", "use the correct comment endpoint"
    assert run.scoped[-1]["payload"] == {"body": BODY}, "preserve the complete literal Markdown body"
    assert run.choices == [{"count": 3, "index": selected}], "choose once, not by searching for the owner"
    _assert_success_diagnostics(run, surface["surface"])


@pytest.mark.parametrize("login", [OWNER, OWNER.upper(), "", "bad login"], ids=["owner", "owner-case", "empty", "malformed"])
def test_unexpected_identity_blocks_before_posting(
    manual_comment_harness: _CommentHarness, login: str,
) -> None:
    """Owner or invalid identity results are configuration errors, not fallback triggers."""
    run = _run_post(manual_comment_harness, _Scenario(login=login))
    assert run.result.returncode != 0, "unexpected identity must stop the operation"
    assert [call["method"] for call in run.scoped] == ["GET"], "no POST after an invalid identity"
    assert len(run.choices) == 1, "do not search for another token after rejection"
    assert URL not in run.result.stdout, "blocked operation must not report a comment"
    diagnostic = run.diagnostic("identity_preflight")
    expected_category = (
        "unexpected_owner_identity"
        if login and login.lower() == OWNER
        else "invalid_identity_response"
    )
    assert diagnostic["failure_category"] == expected_category
    assert diagnostic["exit_status"] == 2
    assert "login" not in diagnostic and "identity" not in diagnostic, (
        "diagnostics must not include the verified account identity"
    )


@pytest.mark.parametrize("stage", ["GET", "POST"], ids=["identity-read", "comment-post"])
@pytest.mark.parametrize("code", [401, 403, 429], ids=["unauthenticated", "forbidden", "rate-limited"])
def test_service_failure_never_changes_identity_or_retries(
    manual_comment_harness: _CommentHarness, stage: str, code: int,
) -> None:
    """Real authentication, permission and rate-limit failures remain visible."""
    run = _run_post(manual_comment_harness, _Scenario(failure_stage=stage, failure_code=code))
    assert run.result.returncode != 0, "service failure must propagate"
    expected = ["GET"] if stage == "GET" else ["GET", "POST"]
    assert [call["method"] for call in run.scoped] == expected, "never retry or fall back to normal authentication"
    assert len(run.lifecycle) == 1, "the lifecycle lookup is never a posting fallback"
    assert len(run.choices) == 1, "never cycle identities after a service failure"
    assert URL not in run.result.stdout, "failed posting must not claim success"
    diagnostic = run.diagnostics()[-1]
    expected_category = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}[code]
    assert diagnostic["stage"] == ("identity_preflight" if stage == "GET" else "post")
    assert diagnostic["failure_category"] == expected_category
    assert diagnostic["http_status"] == code
    assert diagnostic["exit_status"] == 1
    assert "fixture service failure" not in run.result.stderr, "do not echo raw service text"


@pytest.mark.parametrize("pool_state", ["missing", "empty"])
def test_unavailable_pool_does_not_use_normal_credentials(
    manual_comment_harness: _CommentHarness, pool_state: str,
) -> None:
    """The normally authenticated owner cannot substitute for unavailable pool data."""
    run = _run_post(manual_comment_harness, _Scenario(pool_state=pool_state))
    assert run.result.returncode != 0, "unavailable pool must fail"
    assert run.scoped == [] and run.lifecycle == [], "no GitHub request without a selected pool token"
    diagnostic = run.diagnostic("token_selection")
    assert diagnostic["failure_category"] in {
        "token_pool_unavailable", "token_not_selected",
    }
    assert diagnostic["exit_status"] == 2


@pytest.mark.parametrize("override", [None, "bad login"], ids=["stored-login-failure", "malformed-override"])
def test_unknown_lifecycle_account_blocks_before_pool_identity(
    manual_comment_harness: _CommentHarness, override: str | None,
) -> None:
    """Without a known lifecycle account the pool token cannot be checked, so stop."""
    run = _run_post(
        manual_comment_harness, _Scenario(lifecycle_failure=True, lifecycle_override=override),
    )
    assert run.result.returncode != 0, "an unknown lifecycle account must fail closed"
    assert run.scoped == [], "no pool request before the lifecycle account is known"
    diagnostic = run.diagnostic("lifecycle_identity")
    assert diagnostic["failure_category"] == "lifecycle_identity_unavailable"
    assert diagnostic["exit_status"] == 2
    assert "fixture stored-login failure" not in run.result.stderr, "do not echo raw service text"


def test_lifecycle_override_replaces_the_stored_login_lookup(
    manual_comment_harness: _CommentHarness,
) -> None:
    """An explicit lifecycle login skips the lookup and still guards the pool token."""
    run = _run_post(
        manual_comment_harness,
        _Scenario(login="override-owner", lifecycle_failure=True, lifecycle_override="Override-Owner"),
    )
    assert run.result.returncode != 0, "a pool token matching the override must be rejected"
    assert run.lifecycle == [], "the override replaces the stored-login lookup"
    assert run.diagnostic("identity_preflight")["failure_category"] == "unexpected_owner_identity"


def test_identity_contract_is_explicit_at_each_entrypoint() -> None:
    """Discovery, posting and queue guidance agree about the authorized principal."""
    skill = " ".join(SKILL.read_text().split())
    comments = " ".join(COMMENTS.read_text().split())
    queue = " ".join((ROOT / "skills/comenq-coderabbit/SKILL.md").read_text().split())
    for requirement in (
        "Pool accounts deliberately authenticate as identities other than the lifecycle account",
        "Do not require a pool account to match the repository owner",
        "Do not ask for another confirmation solely because",
        "merges use the normal authorized lifecycle identity",
        "cycling identities after a rate-limit response is not",
        "CodeRabbit rate-limits conversations per commenting account",
        "`scripts/post-manual-comment.sh`",
    ):
        assert requirement in skill, f"missing primary identity contract: {requirement}"
    assert "Do not search the pool for the lifecycle account's token" in comments, "posting guidance must reject owner-matching"
    assert "`scripts/post-manual-comment.sh`" in comments, "posting guidance must name the shipped helper"
    assert "pool of accounts other than the lifecycle account is authorized for in-scope manual comments" in queue, "queue guidance must recognize the configured reply route"


def test_lifecycle_identity_contract_names_no_account() -> None:
    """Readiness and merges use stored authentication, verified without naming an owner."""
    skill = " ".join(SKILL.read_text().split())
    for requirement in (
        "as the currently logged-in Linux user with that user's normal `gh` authentication",
        "with `GH_TOKEN` and `GITHUB_TOKEN` removed",
        "is not an account from the comment-token pool",
    ):
        assert requirement in skill, f"missing lifecycle identity contract: {requirement}"
    for document in (SKILL, COMMENTS, HELPER, ROOT / "skills/comenq-coderabbit/SKILL.md"):
        text = document.read_text()
        assert "`leynos`" not in text and "!= leynos" not in text, (
            f"{document.name} must describe the lifecycle account by role, not by name"
        )


def test_helper_is_executable_valid_bash() -> None:
    """Check the shipped helper's mode and syntax without executing any request."""
    assert HELPER.stat().st_mode & 0o111, "the helper must be executable"
    result = subprocess.run(["/bin/bash", "-n", str(HELPER)], text=True,
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr
