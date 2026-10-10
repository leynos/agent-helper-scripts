"""Exercise the documented comment route with dummy principals and no network."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMMENTS = ROOT / "skills/pr-babysitting/references/comments.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
BODY = '@coderabbitai Please check "this".\n\n£ and $(not-a-command) stay literal.\n'
URL = "https://example.invalid/comments/101"
TOKENS = [f"fixture-pool-{index}" for index in range(3)]


def _posting_example() -> str:
    """Extract the actual Bash example, not a separately maintained copy."""
    fences = re.findall(r"^```bash\n(.*?)^```$", COMMENTS.read_text(), re.M | re.S)
    matches = [fence for fence in fences if "post_manual_comment()" in fence]
    assert len(matches) == 1, "expected one documented posting helper"
    return matches[0]


GH_DOUBLE = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
config = json.loads((root / "fixture.json").read_text())
args = sys.argv[1:]
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
tokens = [f"fixture-pool-{index}" for index in range(3)]
scoped = token in tokens
principal = f"comment-agent-{tokens.index(token)}" if scoped else "leynos"
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
         "debug": os.environ.get("GH_DEBUG")}
if post:
    event["payload"] = json.load(sys.stdin)
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(event) + "\\n")
if scoped and config["failure_stage"] == method:
    print(f"HTTP {config['failure_code']}: fixture service failure", file=sys.stderr)
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


def _run_post(
    harness: _CommentHarness, *, selected: int = 0, inline: bool = False,
    login: str | None = None, failure_stage: str = "", failure_code: int = 0,
    pool_state: str = "valid", inherited: bool = True,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]], list[dict[str, object]]]:
    """Configure one scenario and invoke the documented helper in Bash."""
    harness.config_file.write_text(json.dumps({
        "selected": selected, "login": login, "failure_stage": failure_stage,
        "failure_code": failure_code,
    }))
    if pool_state != "missing":
        harness.pool_file.write_text(
            "# fixture credentials only\n\n"
            + ("\n".join(TOKENS) + "\n" if pool_state == "valid" else "\n")
        )
    else:
        harness.pool_file.unlink()
    script = _posting_example() + '''
before=$(gh api user --jq '.login')
post_manual_comment leynos/example 7 "$BODY_FILE" "$ROOT_COMMENT_ID"
result=$?
after=$(gh api user --jq '.login')
[[ "$before" == leynos && "$after" == leynos ]] || exit 90
exit "$result"
'''
    env = {
        "HOME": str(harness.root), "XDG_CONFIG_HOME": str(harness.root / "config"),
        "PATH": f"{harness.bin_dir}:/usr/bin:/bin", "FIXTURE_ROOT": str(harness.root),
        "BODY_FILE": str(harness.body_file), "ROOT_COMMENT_ID": "456" if inline else "",
        "GH_DEBUG": "api",
    }
    if inherited:
        env.update(GH_TOKEN="fixture-owner-gh", GITHUB_TOKEN="fixture-owner-github")
    result = subprocess.run(
        ["/bin/bash", "-x", "-c", script], cwd=harness.root, env=env,
        text=True, capture_output=True, check=False, timeout=10,
    )
    calls = [json.loads(line) for line in (harness.root / "calls.jsonl").read_text().splitlines()]
    selections = harness.root / "selections.jsonl"
    choices = [json.loads(line) for line in selections.read_text().splitlines()] if selections.exists() else []
    assert calls[0]["principal"] == calls[-1]["principal"] == "leynos", "normal identity must survive"
    assert not calls[0]["scoped"] and not calls[-1]["scoped"], "normal reads must not inherit pool credentials"
    assert all(call["both_overridden"] and call["debug"] is None for call in calls[1:-1]), "each helper call must use both scoped credentials without debug output"
    assert not any(token in result.stdout + result.stderr for token in TOKENS), "tracing must never expose pool tokens"
    return result, calls[1:-1], choices


@pytest.mark.parametrize("selected", range(3), ids=["first-account", "second-account", "third-account"])
@pytest.mark.parametrize("inline", [False, True], ids=["issue-comment", "inline-reply"])
@pytest.mark.parametrize("inherited", [False, True], ids=["stored-owner", "environment-owner"])
def test_non_owner_pool_principal_posts_without_changing_lifecycle_identity(
    manual_comment_harness: _CommentHarness, selected: int, inline: bool, inherited: bool,
) -> None:
    """All three authorized non-owner accounts work for both comment surfaces."""
    result, calls, choices = _run_post(
        manual_comment_harness, selected=selected, inline=inline, inherited=inherited,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == URL + "\n", "posting must return the comment URL"
    assert [call["method"] for call in calls] == ["GET", "POST"], "verify selected identity then post once"
    assert all(call["principal"] == f"comment-agent-{selected}" for call in calls), "check and post must use the same non-owner identity"
    endpoint = "pulls/7/comments/456/replies" if inline else "issues/7/comments"
    assert calls[-1]["args"][5] == f"repos/leynos/example/{endpoint}", "use the correct comment endpoint"
    assert calls[-1]["payload"] == {"body": BODY}, "preserve the complete literal Markdown body"
    assert choices == [{"count": 3, "index": selected}], "choose once, not by searching for leynos"
    diagnostics = [
        json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")
    ]
    assert [event["stage"] for event in diagnostics] == [
        "token_selection", "identity_preflight", "post",
    ]
    assert all(
        event["operation"] == "manual_pr_comment"
        and event["surface"] == ("inline_reply" if inline else "issue_comment")
        and event["repository"] == "leynos/example"
        and event["pr"] == "7"
        and event["failure_category"] is None
        and event["exit_status"] == 0
        and isinstance(event["elapsed_ms"], int)
        and event["elapsed_ms"] >= 0
        for event in diagnostics
    ), "success diagnostics must be structured and contain only bounded context"
    diagnostic_text = json.dumps(diagnostics)
    assert not any(token in diagnostic_text for token in TOKENS)
    assert "comment-agent-" not in diagnostic_text


@pytest.mark.parametrize("login", ["leynos", "LEYNOS", "", "bad login"], ids=["owner", "owner-case", "empty", "malformed"])
def test_unexpected_identity_blocks_before_posting(
    manual_comment_harness: _CommentHarness, login: str,
) -> None:
    """Owner or invalid identity results are configuration errors, not fallback triggers."""
    result, calls, choices = _run_post(manual_comment_harness, login=login)
    assert result.returncode != 0, "unexpected identity must stop the operation"
    assert [call["method"] for call in calls] == ["GET"], "no POST after an invalid identity"
    assert len(choices) == 1, "do not search for another token after rejection"
    assert URL not in result.stdout, "blocked operation must not report a comment"
    diagnostic = json.loads(
        next(line for line in result.stderr.splitlines() if line.startswith("{") and '"stage":"identity_preflight"' in line)
    )
    expected_category = (
        "unexpected_owner_identity"
        if login and login.lower() == "leynos"
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
    result, calls, choices = _run_post(
        manual_comment_harness, failure_stage=stage, failure_code=code,
    )
    assert result.returncode != 0, "service failure must propagate"
    expected = ["GET"] if stage == "GET" else ["GET", "POST"]
    assert [call["method"] for call in calls] == expected, "never retry or fall back to normal authentication"
    assert len(choices) == 1, "never cycle identities after a service failure"
    assert URL not in result.stdout, "failed posting must not claim success"
    diagnostics = [
        json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")
    ]
    diagnostic = diagnostics[-1]
    expected_category = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}[code]
    assert diagnostic["stage"] == ("identity_preflight" if stage == "GET" else "post")
    assert diagnostic["failure_category"] == expected_category
    assert diagnostic["http_status"] == code
    assert diagnostic["exit_status"] == 1
    assert "fixture service failure" not in result.stderr, "do not echo raw service text"


@pytest.mark.parametrize("pool_state", ["missing", "empty"])
def test_unavailable_pool_does_not_use_normal_credentials(
    manual_comment_harness: _CommentHarness, pool_state: str,
) -> None:
    """The normally authenticated owner cannot substitute for unavailable pool data."""
    result, calls, _ = _run_post(manual_comment_harness, pool_state=pool_state)
    assert result.returncode != 0, "unavailable pool must fail"
    assert calls == [], "no authenticated helper request without a selected pool token"
    diagnostic = json.loads(
        next(line for line in result.stderr.splitlines() if line.startswith("{") and '"stage":"token_selection"' in line)
    )
    assert diagnostic["failure_category"] in {
        "token_pool_unavailable", "token_not_selected",
    }
    assert diagnostic["exit_status"] == 2


def test_identity_contract_is_explicit_at_each_entrypoint() -> None:
    """Discovery, posting and queue guidance agree about the authorized principal."""
    skill = " ".join(SKILL.read_text().split())
    comments = " ".join(COMMENTS.read_text().split())
    queue = " ".join((ROOT / "skills/comenq-coderabbit/SKILL.md").read_text().split())
    for requirement in (
        "Pool accounts deliberately authenticate as identities other than `leynos`",
        "Do not require a pool account to match the repository owner",
        "Do not ask for another confirmation solely because",
        "merges use the normal authorized lifecycle identity",
        "cycling identities after a rate-limit response is not",
    ):
        assert requirement in skill, f"missing primary identity contract: {requirement}"
    assert "Do not search the pool for a `leynos` token" in comments, "posting guidance must reject owner-matching"
    assert "pool of non-`leynos` accounts is authorized for in-scope manual comments" in queue, "queue guidance must recognize the configured reply route"


def test_documented_helper_is_valid_bash() -> None:
    """Check the syntax of the actual example without executing any request."""
    result = subprocess.run(["/bin/bash", "-n"], input=_posting_example(), text=True,
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr
