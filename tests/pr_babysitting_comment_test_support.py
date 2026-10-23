"""Run the shipped PR comment helper against offline `gh` and `shuf` doubles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/pr-babysitting/scripts/post-manual-comment.sh"
BODY = '@coderabbitai Please check "this".\n\n£ and $(not-a-command) stay literal.\n'
URL = "https://example.invalid/comments/101"
TOKENS = tuple(f"fixture-pool-{index}" for index in range(3))
OWNER = "fixture-owner"
REPO = "example-owner/example"
RUN_ID = re.compile(r"^[0-9a-f]{16}$")
STAGES = ["token_selection", "lifecycle_identity", "identity_preflight", "post"]


GH_DOUBLE = '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
config = json.loads((root / "fixture.json").read_text())
args = sys.argv[1:]
token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
tokens = config["tokens"]
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

# Read the normal identity before and after the helper, proving it survives.
POST_SCRIPT = '''
before=$(gh api user --jq '.login')
/bin/bash -x "$HELPER" "$REPO" "$PR" "$BODY_FILE" ${ROOT_COMMENT_ID:+"$ROOT_COMMENT_ID"}
result=$?
after=$(gh api user --jq '.login')
[[ "$before" == "$OWNER" && "$after" == "$OWNER" ]] || exit 90
exit "$result"
'''


@dataclass(frozen=True)
class CommentHarness:
    """A private home with a token pool, a body file, and executable doubles."""

    root: Path
    bin_dir: Path
    config_file: Path
    body_file: Path
    pool_file: Path


def make_harness(root: Path) -> CommentHarness:
    """Provision the doubles and private paths under one empty directory."""
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for name, source in (("gh", GH_DOUBLE), ("shuf", SHUF_DOUBLE)):
        executable = bin_dir / name
        executable.write_text(f"#!{sys.executable} -S\n{source}")
        executable.chmod(0o755)
    pool_file = root / ".local/share/github-tokens"
    pool_file.parent.mkdir(parents=True)
    return CommentHarness(
        root=root, bin_dir=bin_dir, config_file=root / "fixture.json",
        body_file=root / "body.md", pool_file=pool_file,
    )


def pool_text(tokens: tuple[str, ...]) -> str:
    """Render a pool file with a comment, a blank line, and one token per line."""
    return "# fixture credentials only\n\n" + "\n".join(tokens) + "\n"


@dataclass(frozen=True)
class Scenario:
    """One posting scenario: fixture behaviour and the helper's environment."""

    selected: int = 0
    inline: bool = False
    login: str | None = None
    failure_stage: str = ""
    failure_code: int = 0
    pool: str | None = field(default_factory=lambda: pool_text(TOKENS))
    tokens: tuple[str, ...] = TOKENS
    inherited: bool = True
    lifecycle_failure: bool = False
    lifecycle_override: str | None = None
    body: str = BODY
    pr: int = 7
    comment_id: int = 456

    @property
    def surface(self) -> str:
        """Return the diagnostic surface name for this scenario."""
        return "inline_reply" if self.inline else "issue_comment"

    @property
    def endpoint(self) -> str:
        """Return the REST endpoint the helper must post to."""
        if self.inline:
            return f"repos/{REPO}/pulls/{self.pr}/comments/{self.comment_id}/replies"
        return f"repos/{REPO}/issues/{self.pr}/comments"

    def fixture_config(self) -> dict[str, object]:
        """Return the settings the gh and shuf doubles read."""
        return {
            "selected": self.selected, "login": self.login, "tokens": list(self.tokens),
            "failure_stage": self.failure_stage, "failure_code": self.failure_code,
            "owner": OWNER, "lifecycle_failure": self.lifecycle_failure,
        }

    def environment(self, harness: CommentHarness) -> dict[str, str]:
        """Return a private environment, optionally inheriting owner tokens."""
        env = {
            "HOME": str(harness.root), "XDG_CONFIG_HOME": str(harness.root / "config"),
            "PATH": f"{harness.bin_dir}:/usr/bin:/bin", "FIXTURE_ROOT": str(harness.root),
            "BODY_FILE": str(harness.body_file), "PR": str(self.pr),
            "ROOT_COMMENT_ID": str(self.comment_id) if self.inline else "",
            "GH_DEBUG": "api", "HELPER": str(HELPER), "REPO": REPO, "OWNER": OWNER,
        }
        if self.inherited:
            env.update(GH_TOKEN="fixture-owner-gh", GITHUB_TOKEN="fixture-owner-github")
        if self.lifecycle_override is not None:
            env["PR_BABYSITTING_LIFECYCLE_LOGIN"] = self.lifecycle_override
        return env


@dataclass(frozen=True)
class PostResult:
    """The helper's process result and the calls the doubles recorded."""

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


def run_post(harness: CommentHarness, scenario: Scenario = Scenario()) -> PostResult:
    """Configure one scenario and invoke the shipped helper under tracing."""
    for log in ("calls.jsonl", "selections.jsonl"):
        (harness.root / log).unlink(missing_ok=True)
    harness.config_file.write_text(json.dumps(scenario.fixture_config()))
    harness.body_file.write_text(scenario.body)
    harness.pool_file.unlink(missing_ok=True)
    if scenario.pool is not None:
        harness.pool_file.write_text(scenario.pool)
    result = subprocess.run(
        ["/bin/bash", "-c", POST_SCRIPT], cwd=harness.root, env=scenario.environment(harness),
        text=True, capture_output=True, check=False, timeout=20,
    )
    assert not any(token in result.stdout + result.stderr for token in scenario.tokens), (
        "tracing must never expose pool tokens"
    )
    lifecycle, scoped = _split_helper_calls(_read_jsonl(harness.root / "calls.jsonl"))
    return PostResult(result, lifecycle, scoped, _read_jsonl(harness.root / "selections.jsonl"))


def assert_bounded_diagnostics(run: PostResult, scenario: Scenario) -> None:
    """Every diagnostic shares one run ID and omits credentials and account names."""
    diagnostics = run.diagnostics()
    assert diagnostics, "the helper must emit at least one structured diagnostic"
    run_ids = {event["run_id"] for event in diagnostics}
    assert len(run_ids) == 1, "all diagnostics from one invocation must share a run ID"
    assert RUN_ID.match(str(next(iter(run_ids)))), "the run ID must be 16 lowercase hex digits"
    assert all(isinstance(event["elapsed_ms"], int) for event in diagnostics), (
        "each stage must report an integer elapsed time"
    )
    assert min(event["elapsed_ms"] for event in diagnostics) >= 0, "elapsed times cannot be negative"
    diagnostic_text = json.dumps(diagnostics)
    assert not any(token in diagnostic_text for token in scenario.tokens), (
        "diagnostics must never contain pool tokens"
    )
    assert "comment-agent-" not in diagnostic_text, "diagnostics must not name the pool account"
    assert OWNER not in diagnostic_text, "diagnostics must not name the lifecycle account"


def assert_success_diagnostics(run: PostResult, scenario: Scenario) -> None:
    """Success diagnostics cover every stage with only bounded context."""
    diagnostics = run.diagnostics()
    assert [event["stage"] for event in diagnostics] == STAGES, (
        "a successful post must report every stage once, in order"
    )
    expected = {
        "operation": "manual_pr_comment", "surface": scenario.surface, "repository": REPO,
        "pr": str(scenario.pr), "failure_category": None, "exit_status": 0,
    }
    assert [{key: event[key] for key in expected} for event in diagnostics] == [expected] * 4, (
        "success diagnostics must be structured and contain only bounded context"
    )
    assert_bounded_diagnostics(run, scenario)
