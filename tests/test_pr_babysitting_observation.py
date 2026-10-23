"""Rehearse documented assessment reads without GitHub access or credentials."""

from __future__ import annotations

import hashlib
import json
import os
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
        "If the current-candidate review is in progress (a `pending` status), await it",
        "Without a rate limit, await the automatic review",
        "an absent check is not proof of rate limiting",
        "CodeRabbit reports through a commit status, not a check run",
        "Read its description",
        "queue one `comenq-coderabbit` request for each rate-limited candidate",
        "Assessments apply only to an ExecPlan implementation assignment",
        "`Review completed`, or `Approve command performed` for an approved head",
        "Repeat steps 4 and 5 for the new head, with the same completion condition",
    ):
        assert guard in normalized, f"missing readiness guard: {guard}"
    assert normalized.index("**Await formal review completion.**") < normalized.index(
        "**Repeat after every push.**"
    ), "rate-limit recovery must be re-entered after every push"
    repeat = normalized.split("**Repeat after every push.**", 1)[1]
    assert "return to step 1 for the new head" in repeat, "a repair push must re-run gates, CI, and CodeScene"
    assert "The PR stays ready" in repeat, "the repair loop must not redraft the PR"


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
            "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}", "state_dir": str(tmp_path),
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


HEAD = "4aa285e510910e01c0d9360632d9876d27d6b890"
EARLIER = "2d5e46a6705e41dbd69f3aaea98cf6d6fffc1cc1"
SUMMARY = "<!-- This is an auto-generated comment: summarize by coderabbit.ai -->"
RATE_LIMITED = "<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->"
PAUSED = "<!-- This is an auto-generated comment: review paused by coderabbit.ai -->"


def _rate_limited_summary() -> str:
    """Mirror the live rate-limit notice edited into the summary comment."""
    return (
        f"{SUMMARY}\n{RATE_LIMITED}\n\n> [!WARNING]\n> ## Review limit reached\n>\n"
        "> **Next included review available in 53 minutes.**\n>\n"
        "> Reviewing files that changed from the base of the PR and between "
        f"{EARLIER} and {HEAD}.\n"
    )


def _status(description: str | None, state: str = "success") -> dict[str, object]:
    """Build a combined-status payload with an unrelated context alongside."""
    statuses: list[dict[str, object]] = [
        {"context": "ci/other", "state": "success", "description": "Review rate limited",
         "updated_at": "2026-10-09T15:00:00Z"},
    ]
    if description is not None:
        statuses.append({"context": "CodeRabbit", "state": state, "description": description,
                         "updated_at": "2026-10-09T15:02:00Z"})
    return {"sha": HEAD, "statuses": statuses}


def _run_review_signal(
    tmp_path: Path, status: dict[str, object], pages: list[list[dict[str, object]]],
    *, failure: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Execute the documented formal-review read with a read-only fake gh."""
    (tmp_path / "fixture.json").write_text(
        json.dumps({"status": status, "pages": pages, "failure": failure})
    )
    gh = tmp_path / "gh"
    gh.write_text(f"#!{sys.executable}\n" + f'''import json, os, pathlib, sys
root = pathlib.Path(os.environ["state_dir"])
fixture = json.loads((root / "fixture.json").read_text())
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["api", "repos/owner/repo/commits/{HEAD}/status"]:
    if fixture["failure"] == "status":
        print("fixture read failure", file=sys.stderr)
        sys.exit(5)
    print(json.dumps(fixture["status"]))
elif args == ["api", "--method", "GET", "--paginate", "--slurp",
              "repos/owner/repo/issues/7/comments", "-F", "per_page=100"]:
    if fixture["failure"] == "comments":
        print("fixture read failure", file=sys.stderr)
        sys.exit(5)
    print(json.dumps(fixture["pages"]))
else:
    raise SystemExit("unexpected or mutating gh invocation")
''')
    gh.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", _observation_fence("review-signal.json")],
        cwd=tmp_path, env={
            "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}", "state_dir": str(tmp_path),
            "repo": "owner/repo", "pr": "7", "head": HEAD,
        }, text=True, capture_output=True, check=False, timeout=10,
    )
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    return result, calls


def _signal(tmp_path: Path) -> dict[str, object]:
    """Load the classification the documented read wrote."""
    return json.loads((tmp_path / "review-signal.json").read_text())


def test_review_signal_reads_rate_limit_from_status_and_summary(tmp_path: Path) -> None:
    """A green status can still mean rate-limited; the summary supplies wait and range."""
    pages = [[_comment(50, "Unrelated bot note")], [_comment(60, _rate_limited_summary())]]
    result, calls = _run_review_signal(tmp_path, _status("Review rate limited"), pages)
    assert result.returncode == 0, result.stderr
    signal = _signal(tmp_path)
    assert signal["classification"] == "rate-limited", "read the description, not the success state"
    assert signal["status"]["state"] == "success", "the CodeRabbit status stays green while rate-limited"
    summary = signal["summary"]
    assert summary["id"] == 60, "select CodeRabbit's summary comment, not an unrelated bot note"
    assert summary["rate_limited"] is True, "the summary's rate-limit marker must be detected"
    assert summary["paused"] is False, "a rate limit is not a pause"
    assert summary["wait_minutes"] == 53, "the stated wait must be kept as the ETA"
    assert summary["range_head"] == HEAD, "the notice's reviewed head must be compared with the candidate"
    assert len(calls) == 2, "observation must not post, enqueue, or retry"


@pytest.mark.parametrize(
    ("description", "state", "expected"),
    [
        ("Review completed", "success", "completed"),
        ("Review paused", "success", "paused"),
        ("Review skipped: draft pull request", "success", "skipped"),
        ("Review skipped: bot user not eligible for review", "success", "skipped"),
        ("Approve command performed: Review threads unchanged. Approval completed", "success", "approve-performed"),
        ("Review in progress", "pending", "in-progress"),
        ("Something new", "success", "unknown"),
        (None, "success", "status-absent"),
    ],
    ids=["completed", "paused", "draft-skip", "bot-skip", "approved", "pending", "unknown", "absent"],
)
def test_review_signal_classifies_status_descriptions(
    tmp_path: Path, description: str | None, state: str, expected: str,
) -> None:
    """Every observed description maps to a distinct state; unknown text stays unknown."""
    pages = [[_comment(60, f"{SUMMARY}\n\nWalkthrough only.")]]
    result, _ = _run_review_signal(tmp_path, _status(description, state), pages)
    assert result.returncode == 0, result.stderr
    signal = _signal(tmp_path)
    assert signal["classification"] == expected, f"description {description!r} must classify as {expected}"
    assert signal["summary"]["rate_limited"] is False, "a walkthrough-only summary is not rate-limited"
    assert signal["summary"]["wait_minutes"] is None, "no wait is reported without a rate-limit notice"
    assert (signal["status"] is None) == (description is None), "an absent status must not be invented"


def test_review_signal_ignores_spoofed_summary_and_selects_first_bot_comment(tmp_path: Path) -> None:
    """Only CodeRabbit's own earliest summary counts, not a pasted marker or a later copy."""
    pages = [[
        _comment(40, _rate_limited_summary(), author="unrelated-user"),
        _comment(70, f"{SUMMARY}\n{PAUSED}\nLater copy."),
        _comment(60, f"{SUMMARY}\n\nWalkthrough only."),
    ]]
    result, _ = _run_review_signal(tmp_path, _status("Review completed"), pages)
    assert result.returncode == 0, result.stderr
    summary = _signal(tmp_path)["summary"]
    assert summary["id"] == 60, "select the first comment by verified bot identity"
    assert summary["rate_limited"] is False, "a spoofed rate-limit marker from another author is ignored"
    assert summary["paused"] is False, "a later copy's pause marker is ignored"
    assert summary["range_head"] is None, "no reviewed range comes from a spoofed or later comment"


def test_review_signal_flags_notice_for_an_earlier_head(tmp_path: Path) -> None:
    """A rate-limit notice whose range ends at an older head is not current evidence."""
    body = _rate_limited_summary().replace(f"and {HEAD}", f"and {EARLIER}").replace(
        f"between {EARLIER}", "between " + "0" * 40)
    result, _ = _run_review_signal(tmp_path, _status("Review completed"), [[_comment(60, body)]])
    assert result.returncode == 0, result.stderr
    signal = _signal(tmp_path)
    assert signal["summary"]["rate_limited"] is True, "the stale notice is still reported as a rate limit"
    assert signal["summary"]["range_head"] == EARLIER != HEAD, "the stale range must be visible to the supervisor"
    assert signal["classification"] == "completed", "the head-bound status decides the current state"


@pytest.mark.parametrize("failure", ["status", "comments"])
def test_review_signal_fails_closed_on_read_errors(tmp_path: Path, failure: str) -> None:
    """A failed read must not become an absent-status or clean classification."""
    result, calls = _run_review_signal(tmp_path, _status("Review completed"), [[]], failure=failure)
    assert result.returncode != 0, "read failures must propagate"
    assert not (tmp_path / "review-signal.json").exists(), "no classification without both surfaces"
    assert len(calls) == (1 if failure == "status" else 2), "never retry or fall back"


SIGNAL_PLACEHOLDERS = {"updated_at": "<timestamp>", "html_url": "<url>", "range_head": "<sha>"}


def _normalize_signal(signal: dict[str, object]) -> dict[str, object]:
    """Replace timestamps, URLs and commit hashes with stable placeholders.

    Parameters
    ----------
    signal : dict[str, object]
        Parsed `review-signal.json`.

    Returns
    -------
    dict[str, object]
        The same structure with each present variable field replaced, so the
        snapshot pins shape and classification rather than fixture values.
    """
    def scrub(section: object) -> object:
        if not isinstance(section, dict):
            return section
        return {key: SIGNAL_PLACEHOLDERS[key] if key in SIGNAL_PLACEHOLDERS and value is not None else value
                for key, value in section.items()}
    return {key: scrub(value) for key, value in signal.items()}


SIGNAL_SNAPSHOTS = {
    "rate-limited": (_status("Review rate limited"), [[_comment(60, _rate_limited_summary())]]),
    "completed": (_status("Review completed"), [[_comment(60, f"{SUMMARY}\n\nWalkthrough only.")]]),
    "paused": (_status("Review paused"), [[_comment(60, f"{SUMMARY}\n{PAUSED}\nPaused.")]]),
    "draft-skip": (_status("Review skipped: draft pull request"), [[_comment(60, f"{SUMMARY}\n")]]),
    "approve": (_status("Approve command performed: Review threads unchanged. Approval completed"),
                [[_comment(60, f"{SUMMARY}\n")]]),
    "in-progress": (_status("Review in progress", "pending"), [[_comment(60, f"{SUMMARY}\n")]]),
    "status-absent": (_status(None), [[]]),
    "unknown": (_status("Something new from CodeRabbit"), [[_comment(60, f"{SUMMARY}\n")]]),
}


@pytest.mark.parametrize("name", list(SIGNAL_SNAPSHOTS))
def test_review_signal_output_contract_snapshot(tmp_path: Path, name: str, snapshot: object) -> None:
    """The documented review-signal JSON for each classification stays stable."""
    status, pages = SIGNAL_SNAPSHOTS[name]
    result, _ = _run_review_signal(tmp_path, status, pages)
    assert result.returncode == 0, result.stderr
    assert _normalize_signal(_signal(tmp_path)) == snapshot, f"review-signal output contract changed for {name}"
