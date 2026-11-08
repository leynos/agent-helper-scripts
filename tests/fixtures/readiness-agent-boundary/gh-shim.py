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


def posted_comment(facts: dict) -> dict:
    """Return a new comment body shaped like the API's response to a POST."""
    post = facts.get("posted_comment", {})
    return {
        "id": post.get("id", 9901),
        "html_url": post.get(
            "html_url",
            "https://github.com/leynos/agent-helper-scripts/pull/272#issuecomment-9901",
        ),
        "user": {"login": POOL_LOGIN, "type": "User"},
        "body": "<posted by the recorded stand-in>",
    }


def answer(argv: list[str]) -> int:
    """Answer one invocation from the recorded facts."""
    facts = read_facts()
    slurp = "--slurp" in argv
    if argv[:2] == ["pr", "view"]:
        return emit(facts["pr"])
    if argv[:2] == ["pr", "ready"]:
        STATE.write_text(json.dumps({"isDraft": False}), encoding="utf-8")
        return emit(facts["pr_ready_response"])
    if argv[:2] == ["pr", "checks"]:
        return emit(facts["pr_checks"])
    if argv[:1] == ["api"]:
        url = api_url(argv)
        # A POST with the fixture token stands in for the manual-comment route.
        # The token is honoured only here, so the follow-up is exercisable
        # without any real credential being reachable.
        if url == "user":
            return emit(POOL_LOGIN if os.environ.get("GH_TOKEN") == POOL_TOKEN else facts["login"])
        if "POST" in argv and re.fullmatch(r"repos/[^/]+/[^/]+/issues/\d+/comments", url or ""):
            posted = posted_comment(facts)
            # The posted comment is served back on its own route, so the
            # read-back after a post is a separate, independently observable
            # fact rather than an assumption about what the POST did.
            STATE.write_text(json.dumps({"isDraft": facts["pr"].get("isDraft", True),
                                         "posted": posted}), encoding="utf-8")
            return emit(posted["html_url"])
        if re.fullmatch(r"repos/[^/]+/[^/]+/issues/comments/\d+", url or ""):
            posted = read_facts().get("posted")
            if posted:
                return emit(posted)
            return fail("gh: Not Found (HTTP 404)")
        for pattern, payload in facts["api"].items():
            if re.search(pattern, url):
                # A posted comment is part of the discussion from then on, so
                # listing the comments reflects it without changing the facts.
                if re.search(r"/issues/\d+/comments", url) and isinstance(payload, list):
                    posted = facts.get("posted")
                    if posted:
                        payload = [*payload, posted]
                return emit(payload, slurp=slurp)
        return fail(f"gh: Not Found (HTTP 404)")
    if argv[:2] == ["auth", "status"]:
        return emit(f"Logged in to github.com as {facts['login']}")
    return fail(f"gh: unsupported invocation {argv}")


def main(argv: list[str]) -> int:
    """Record the invocation, then answer it."""
    record(argv)
    return answer(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
