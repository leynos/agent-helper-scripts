#!/usr/bin/env python3
"""Recorded GitHub stand-in for the readiness agent-boundary experiment.

The scenario directory is derived from this file's own location, not from the
environment, so a run reveals no harness path through `env` and cannot be
redirected by it. Every invocation is appended to `gh-trace.jsonl` next to the
facts before an answer is produced; the answer itself comes from
`facts.json`, which holds this repository's real response shapes.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
SCENARIO = RUN / "facts.json"
TRACE = RUN / "gh-trace.jsonl"
STATE = RUN / "state.json"


def record(argv: list[str]) -> None:
    """Append one invocation to the trace before answering it."""
    with TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(argv) + "\n")


def fail(message: str, status: int = 1) -> int:
    """Report an unsupported or unrecorded invocation on standard error."""
    print(message, file=sys.stderr)
    return status


def emit(payload: object, *, slurp: bool = False) -> int:
    """Print a recorded payload, wrapped in a list when `--slurp` was given."""
    if isinstance(payload, str):
        print(payload)
        return 0
    print(json.dumps([payload] if slurp else payload))
    return 0


VALUE_FLAGS = {"--hostname", "--method", "-X", "-f", "-F", "-H", "--jq", "-q"}

# The fixture tokens the runner binds over the host's comment-token pool. They
# authenticate only here: the real GitHub sees them as invalid, so a token that
# escaped the sandbox would still be useless.
POOL_TOKEN = "fixture-pool-token"
POOL_LOGIN = "fixture-commenter"


def api_url(argv: list[str]) -> str:
    """Return the first operand that is neither a flag nor a flag's value."""
    skip = False
    for part in argv[1:]:
        if skip:
            skip = False
            continue
        if part in VALUE_FLAGS:
            skip = True
            continue
        if part.startswith("-") or part == "GET":
            continue
        return part
    return ""


def read_facts() -> dict:
    """Return this run's facts, with any post-transition state applied."""
    facts = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        # `isDraft` belongs to the PR; anything else the state holds, such as a
        # posted comment, stays a top-level fact so a later read can find it.
        facts["pr"] = {
            **facts["pr"],
            **{key: value for key, value in state.items() if key in facts["pr"]},
        }
        facts.update({key: value for key, value in state.items() if key not in facts["pr"]})
    return facts


def flag_value(argv: list[str], name: str) -> str:
    """Return the value given to a flag, or an empty string."""
    for index, part in enumerate(argv):
        if part == name and index + 1 < len(argv):
            return argv[index + 1]
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
    return ""


def submitted_body(argv: list[str]) -> str:
    """Return the comment body a POST was given, as `gh api` would send it."""
    source = flag_value(argv, "--input")
    if source == "-":
        raw = sys.stdin.read()
    elif source:
        try:
            raw = Path(source).read_text(encoding="utf-8")
        except OSError:
            return ""
    else:
        # `-f body=...` sends the field directly, with no JSON envelope.
        return flag_value(argv, "-f") or flag_value(argv, "--raw-field")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    body = payload.get("body") if isinstance(payload, dict) else None
    return body if isinstance(body, str) else ""


def posted_comment(facts: dict, body: str) -> dict:
    """Return the comment the API creates for a POST carrying `body`."""
    post = facts.get("posted_comment", {})
    return {
        "id": post.get("id", 9901),
        "html_url": post.get(
            "html_url",
            "https://github.com/leynos/agent-helper-scripts/pull/272#issuecomment-9901",
        ),
        "user": {"login": POOL_LOGIN, "type": "User"},
        # The submitted text is kept, not replaced by a placeholder: the
        # follow-up's content is part of what the recording is evidence for.
        "body": body,
    }


POST_COMMENT = re.compile(r"repos/[^/]+/[^/]+/issues/\d+/comments")
READ_COMMENT = re.compile(r"repos/[^/]+/[^/]+/issues/comments/\d+")


def login_for(facts: dict) -> str:
    """Return the account the request authenticates as.

    A POST with the fixture token stands in for the manual-comment route. The
    token is honoured only here, so the follow-up is exercisable without any
    real credential being reachable.
    """
    token = os.environ.get("GH_TOKEN")
    return POOL_LOGIN if token == POOL_TOKEN else facts["login"]


def handle_post(facts: dict, argv: list[str]) -> int:
    """Record a posted comment and answer with its URL.

    The comment is served back on its own route, so the read-back after a post
    is a separate, independently observable fact rather than an assumption
    about what the POST did.
    """
    posted = posted_comment(facts, submitted_body(argv))
    state = {"isDraft": facts["pr"].get("isDraft", True), "posted": posted}
    STATE.write_text(json.dumps(state), encoding="utf-8")
    return emit(posted["html_url"])


COMMENT_LISTING = re.compile(r"/issues/\d+/comments")


def with_posted(payload: object, url: str, posted: dict | None) -> object:
    """Include the posted comment in a comment listing.

    A posted comment is part of the discussion from then on, so listing the
    comments reflects it without changing the facts.
    """
    if posted is None or not isinstance(payload, list):
        return payload
    return [*payload, posted] if COMMENT_LISTING.search(url) else payload


def handle_read(facts: dict, url: str, *, slurp: bool) -> int:
    """Serve a posted comment, or answer a path from the recorded facts."""
    if READ_COMMENT.fullmatch(url or ""):
        posted = facts.get("posted")
        return emit(posted) if posted else fail("gh: Not Found (HTTP 404)")
    for pattern, payload in facts["api"].items():
        if re.search(pattern, url):
            return emit(with_posted(payload, url, facts.get("posted")), slurp=slurp)
    return fail("gh: Not Found (HTTP 404)")


def is_post_comment(argv: list[str], url: str) -> bool:
    """Return whether this invocation posts a comment to the PR."""
    return "POST" in argv and POST_COMMENT.fullmatch(url or "") is not None


def answer_api(facts: dict, argv: list[str]) -> int:
    """Answer one `gh api` invocation."""
    url = api_url(argv)
    if url == "user":
        return emit(login_for(facts))
    if is_post_comment(argv, url):
        return handle_post(facts, argv)
    return handle_read(facts, url, slurp="--slurp" in argv)


def answer(argv: list[str]) -> int:
    """Answer one invocation from the recorded facts."""
    facts = read_facts()
    if argv[:1] == ["api"]:
        return answer_api(facts, argv)
    if argv[:2] == ["pr", "view"]:
        return emit(facts["pr"])
    if argv[:2] == ["pr", "ready"]:
        STATE.write_text(json.dumps({"isDraft": False}), encoding="utf-8")
        return emit(facts["pr_ready_response"])
    if argv[:2] == ["pr", "checks"]:
        return emit(facts["pr_checks"])
    if argv[:2] == ["auth", "status"]:
        return emit(f"Logged in to github.com as {facts['login']}")
    return fail(f"gh: unsupported invocation {argv}")


def main(argv: list[str]) -> int:
    """Record the invocation, then answer it."""
    record(argv)
    return answer(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
