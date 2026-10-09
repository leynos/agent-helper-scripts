"""Rehearse documented assessment reads without GitHub access or credentials."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/pr-babysitting/references/awaiting-coderabbit.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
WAIT_REQUIREMENTS = (
    "Before posting the question",
    "Immediately fetch the discussion before sleeping",
    "Fetch all pages",
    "body hash with the baseline",
    "an acknowledgement can become the answer through an edit",
    "Top-level issue comments have no review-thread `in_reply_to_id`",
    "Classify the complete response",
    "Re-fetch live base/head before accepting the result",
    "Set a monotonic deadline",
    "Report API failures as `observation-error`",
    "Do not end after a few empty polls while the observation budget remains",
)


def _wait_contract(text: str) -> None:
    """Keep response detection and acceptance distinct in the observer contract."""
    matches = re.findall(r"^## Bounded issue-comment observation\n(.*?)(?=^## |\Z)",
                         text, re.M | re.S)
    assert len(matches) == 1, "missing observation requirement: unique section"
    observation = matches[0]
    observation = " ".join(observation.split("## Formal review after readiness", 1)[0].split())
    for requirement in WAIT_REQUIREMENTS:
        assert requirement in observation, f"missing observation requirement: {requirement}"


def _observation_fence(marker: str) -> str:
    """Select the actual read example rather than duplicating its implementation."""
    fences = re.findall(r"^```bash\n(.*?)^```$", REFERENCE.read_text(), re.M | re.S)
    matches = [fence for fence in fences if marker in fence]
    assert len(matches) == 1, "the documented observation fence must be unique"
    return matches[0]


def test_readiness_orders_assessments_before_formal_review() -> None:
    """A posted question cannot jump the transition or trigger a duplicate review."""
    text = SKILL.read_text().split("## 5. ", 1)[1].split("## 6. ", 1)[0]
    stages = (
        "**Establish green gates.**", "**Ask and await assessments.**",
        "**Mark ready and verify.**", "**Inspect formal review status.**",
        "**Await formal review completion.**",
    )
    positions = [text.index(stage) for stage in stages]
    assert positions == sorted(positions), "readiness stages must retain their order"
    normalized = " ".join(text.split())
    for guard in (
        "Do not queue a formal review while the PR is draft",
        "read the full body",
        "Read back `isDraft=false`",
        "If the current-candidate review is `queued` or `in_progress`, await it",
        "Without a rate limit, await the automatic review",
        "an absent check is not proof of rate limiting",
    ):
        assert guard in normalized, f"missing readiness guard: {guard}"


def test_observation_contract_covers_response_races() -> None:
    """Fast replies, edited replies, stale heads and bounded waits stay explicit."""
    _wait_contract(REFERENCE.read_text())


@pytest.mark.parametrize("requirement", WAIT_REQUIREMENTS)
def test_observation_contract_rejects_missing_guard(requirement: str) -> None:
    """Each observer safeguard is an independent negative-control mutation."""
    text = " ".join(REFERENCE.read_text().split())
    assert requirement in text, "negative control must start from a real guard"
    # Preserve section headings while normalizing wrapping within each section.
    source = REFERENCE.read_text()
    sections = re.split(r"(^## .*\n)", source, flags=re.M)
    mutated = "".join(part if part.startswith("## ") else " ".join(part.split()) + "\n"
                      for part in sections)
    mutated = mutated.replace(requirement, "[guard removed]")
    with pytest.raises(AssertionError, match="missing observation requirement"):
        _wait_contract(mutated)


def _comment(comment_id: int, body: str, author: str = "coderabbitai[bot]",
             updated_at: str = "2026-10-09T15:01:00Z") -> dict[str, object]:
    """Build public-shaped fixture data, never a real GitHub request."""
    return {
        "id": comment_id, "user": {"login": author, "id": 42},
        "created_at": "2026-10-09T15:00:00Z", "updated_at": updated_at,
        "html_url": f"https://example.invalid/comment/{comment_id}", "body": body,
    }


def _run_read(tmp_path: Path, pages: list[list[dict[str, object]]], *,
              timestamp: str | None = "2026-10-09T15:00:00Z", failure: str = "",
              ) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Execute the documented Bash with a read-only fake gh and a private home."""
    data = tmp_path / "fixture.json"
    data.write_text(json.dumps({"pages": pages, "timestamp": timestamp, "failure": failure}))
    gh = tmp_path / "gh"
    gh.write_text(f"#!{sys.executable}\n" + '''import json, os, pathlib, sys
root = pathlib.Path(os.environ["state_dir"])
fixture = json.loads((root / "fixture.json").read_text())
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["api", "repos/owner/repo/issues/comments/100"]:
    print(json.dumps({"id": 100, "created_at": fixture["timestamp"]}))
elif args[:1] == ["api"] and "repos/owner/repo/issues/7/comments" in args:
    if fixture["failure"]:
        print("fixture read failure", file=sys.stderr)
        sys.exit(5)
    print(json.dumps(fixture["pages"]))
else:
    raise SystemExit("unexpected or mutating gh invocation")
''')
    gh.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", _observation_fence("since=$(")],
        cwd=tmp_path, env={
            "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "PATH": f"{tmp_path}:/usr/bin:/bin", "state_dir": str(tmp_path),
            "repo": "owner/repo", "pr": "7", "request_id": "100",
        }, text=True, capture_output=True, check=False, timeout=10,
    )
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    return result, calls


@pytest.mark.parametrize("reply_id", [101, 90], ids=["new-reply-id", "older-reply-id"])
def test_actual_read_example_retains_full_replies_across_pages(tmp_path: Path, reply_id: int) -> None:
    """The transport keeps late-page answers for semantic inspection."""
    body = "Assessment-ID: request-1\n\nSubstantially complete, but fix the defect.\n" + "Evidence.\n" * 100
    pages = [[_comment(80, "Earlier notice")], [
        _comment(102, "@coderabbitai approved", author="unrelated-user"),
        _comment(reply_id, body),
    ]]
    result, calls = _run_read(tmp_path, pages)
    assert result.returncode == 0, result.stderr
    replies = json.loads((tmp_path / "candidate-replies.json").read_text())
    assert [reply["id"] for reply in replies] == [80, reply_id], "all bot replies must survive pagination"
    assert replies[-1]["body"] == body, "substantive response bodies must not be truncated"
    assert json.loads((tmp_path / "comments-now.json").read_text()) == pages, "raw pages must remain available"
    assert len(calls) == 2, "one observation must not retry, post, or dispatch"
    assert calls[1][1:5] == ["--method", "GET", "--paginate", "--slurp"], "query fields must remain GET with all pages"
    assert "since=2026-10-09T14:59:59Z" in calls[1], "server timestamp needs an overlap, not a local-clock cursor"


def test_read_example_detects_edited_reply_revision(tmp_path: Path) -> None:
    """An acknowledgement edited into the answer must read as a changed revision."""
    baseline = _comment(90, "Assessment-ID: request-1\n\nI will investigate.")
    answer = "Assessment-ID: request-1\n\nSubstantially complete, but fix the defect.\n" + "Evidence.\n" * 100
    edited = _comment(90, answer, updated_at="2026-10-09T15:30:00Z")
    (tmp_path / "comments-before.json").write_text(json.dumps([[baseline]]))

    def revision(reply: dict[str, object]) -> tuple[str, str]:
        return str(reply["updated_at"]), hashlib.sha256(str(reply["body"]).encode()).hexdigest()

    before = {str(reply["id"]): revision(reply)
              for page in json.loads((tmp_path / "comments-before.json").read_text()) for reply in page}
    result, calls = _run_read(tmp_path, [[edited]])
    assert result.returncode == 0, result.stderr
    replies = json.loads((tmp_path / "candidate-replies.json").read_text())
    changed = [reply for reply in replies if before.get(str(reply["id"])) != revision(reply)]
    assert [reply["id"] for reply in changed] == [90], "the edited revision must differ from its baseline"
    assert changed[0]["body"] == answer, "the updated substantive answer must be retained, not the acknowledgement"
    assert before["90"] != revision(edited), "a bare ID match must not count as the newer revision"
    assert len(calls) == 2, "revision comparison must not repost or dispatch"


@pytest.mark.parametrize("body", [None, "I will investigate"], ids=["empty", "acknowledgement"])
def test_read_example_does_not_label_transport_as_clearance(tmp_path: Path, body: str | None) -> None:
    """An empty read or acknowledgement remains data, not an approval result."""
    pages = [[]] if body is None else [[_comment(101, body)]]
    result, calls = _run_read(tmp_path, pages)
    assert result.returncode == 0, result.stderr
    replies = json.loads((tmp_path / "candidate-replies.json").read_text())
    assert len(replies) == (0 if body is None else 1), "read output must preserve the actual observation"
    assert not result.stdout, "the read primitive must not announce approval or readiness"
    assert len(calls) == 2, "empty reads must not trigger automatic reposting"


@pytest.mark.parametrize("timestamp,failure", [(None, ""), ("bad-time", ""),
                                               ("2026-10-09T15:00:00Z", "api")],
                         ids=["missing-time", "invalid-time", "read-failure"])
def test_read_example_fails_closed_on_incomplete_observation(
    tmp_path: Path, timestamp: str | None, failure: str
) -> None:
    """Timestamp and API errors must not become successful empty observations."""
    result, calls = _run_read(tmp_path, [[]], timestamp=timestamp, failure=failure)
    assert result.returncode != 0, "invalid observations must fail"
    assert not (tmp_path / "candidate-replies.json").exists(), "failed reads must not publish accepted reply data"
    assert len(calls) == (2 if failure else 1), "failures must propagate without retries or fallback clocks"
