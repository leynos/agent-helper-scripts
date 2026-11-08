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
import subprocess
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


def emit(payload: object, *, slurp: bool = False, jq: str = "") -> int:
    """Print a recorded payload, wrapped in a list when `--slurp` was given.

    A `--jq` or `-q` expression is applied with the real `jq`, so the agent sees
    what `gh` would print rather than the unfiltered payload. Without `jq` the
    call fails instead of quietly answering a different question.
    """
    if isinstance(payload, str):
        # A human-readable route has no JSON to filter, and the real command
        # does not accept one. Answering with the raw text would look like a
        # filter that matched everything, so refuse instead.
        if jq:
            return fail(f"gh: --jq is not supported on this route: {jq}", 2)
        print(payload)
        return 0
    text = json.dumps([payload] if slurp else payload)
    if not jq:
        print(text)
        return 0
    return apply_jq(text, jq)


def apply_jq(text: str, expression: str) -> int:
    """Run ``jq`` over ``text`` and forward its output and status."""
    try:
        done = subprocess.run(
            ["jq", "-r", expression],
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return fail("gh: jq is required to apply --jq; install jq", 127)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


# Flags whose following operand is a value rather than the endpoint.
VALUE_FLAGS = {
    "--hostname",
    "--method",
    "-X",
    "-f",
    "-F",
    "--field",
    "--raw-field",
    "-H",
    "--header",
    "--input",
    "--template",
    "-t",
    "--jq",
    "-q",
}

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


def jq_expression(argv: list[str]) -> str:
    """Return the filter `--jq` or `-q` asked for, or an empty string."""
    return flag_value(argv, "--jq") or flag_value(argv, "-q")


# Flags that send one field of a request body.
FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field")


def field_body(argv: list[str]) -> str:
    """Return the `body=` field of a request, or an empty string.

    Every field is scanned, not just the first: a request that sends another
    field before `body=` still carries its comment, and recording it as empty
    would lose the very text the recording is evidence for.
    """
    for index, part in enumerate(argv):
        if part not in FIELD_FLAGS or index + 1 >= len(argv):
            continue
        value = argv[index + 1]
        if value.startswith("body="):
            return value.removeprefix("body=")
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
        # `-f body=...` sends the field directly, with no JSON envelope, so the
        # body is the value after the field name and not the whole expression.
        return field_body(argv)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    body = payload.get("body") if isinstance(payload, dict) else None
    return body if isinstance(body, str) else ""


def posted_comment(facts: dict, body: str, login: str) -> dict:
    """Return the comment the API creates for an authorized POST carrying `body`.

    The author is the account the request authenticated as, not the pool's
    expected login: a POST that presented no token, or the wrong one, must not
    record itself as the pool account and so appear authorized.
    """
    post = facts.get("posted_comment", {})
    return {
        "id": post.get("id", 9901),
        "html_url": post.get(
            "html_url",
            "https://github.com/leynos/agent-helper-scripts/pull/272#issuecomment-9901",
        ),
        "user": {"login": login, "type": "User"},
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
    about what the POST did. A POST without the fixture token is refused: the
    manual-comment route is authorized by that token, so accepting a request
    that lacks it would record a success the real service would not grant.
    """
    login = login_for(facts)
    if login != POOL_LOGIN:
        return fail("gh: HTTP 401: Bad credentials")
    posted = posted_comment(facts, submitted_body(argv), login)
    state = {"isDraft": facts["pr"].get("isDraft", True), "posted": posted}
    STATE.write_text(json.dumps(state), encoding="utf-8")
    # The response is the created comment, so a `--jq .html_url` filter applies
    # to it exactly as it would against the real service.
    return emit(posted, jq=jq_expression(argv))


COMMENT_LISTING = re.compile(r"/issues/\d+/comments")


def with_posted(payload: object, url: str, posted: dict | None) -> object:
    """Include the posted comment in a comment listing.

    A posted comment is part of the discussion from then on, so listing the
    comments reflects it without changing the facts.
    """
    if posted is None or not isinstance(payload, list):
        return payload
    return [*payload, posted] if COMMENT_LISTING.search(url) else payload


def handle_read(facts: dict, argv: list[str], url: str) -> int:
    """Serve a posted comment, or answer a path from the recorded facts."""
    jq = jq_expression(argv)
    if READ_COMMENT.fullmatch((url or "").lstrip("/")):
        posted = facts.get("posted")
        return emit(posted, jq=jq) if posted else fail("gh: Not Found (HTTP 404)")
    for pattern, payload in facts["api"].items():
        if re.search(pattern, url.lstrip("/")):
            return emit(
                with_posted(payload, url, facts.get("posted")),
                slurp="--slurp" in argv,
                jq=jq,
            )
    return fail("gh: Not Found (HTTP 404)")


def request_method(argv: list[str]) -> str:
    """Return the method `gh api` would send for this invocation.

    `gh api` sends POST whenever a field or `--input` is present and defaults to
    GET otherwise, so a field-bearing call without an explicit `--method` is a
    mutation. Reading it as a GET would answer a write with a listing and
    record nothing.
    """
    explicit = flag_value(argv, "--method") or flag_value(argv, "-X")
    if explicit:
        return explicit.upper()
    mutation = any(flag in argv for flag in FIELD_FLAGS) or "--input" in argv
    return "POST" if mutation else "GET"


def is_post_comment(argv: list[str], url: str) -> bool:
    """Return whether this invocation posts a comment to the PR."""
    return (
        request_method(argv) == "POST"
        and POST_COMMENT.fullmatch((url or "").lstrip("/")) is not None
    )


def answer_api(facts: dict, argv: list[str]) -> int:
    """Answer one `gh api` invocation."""
    url = api_url(argv)
    if url == "user":
        # The routing record holds only the login, so serve a user object with
        # that field. A `--jq .login` filter then resolves through the same
        # path as every other payload instead of returning the raw string.
        return emit({"login": login_for(facts)}, jq=jq_expression(argv))
    if is_post_comment(argv, url):
        return handle_post(facts, argv)
    if request_method(argv) != "GET":
        return fail(f"gh: unsupported {request_method(argv)} {url}", 2)
    return handle_read(facts, argv, url)


def answer_pr(facts: dict, argv: list[str]) -> int:
    """Answer one `gh pr` invocation.

    `pr view` and `pr checks` serve JSON, so a `--jq` filter is applied to them.
    `pr ready` answers with a fixed response and takes no filter.
    """
    if argv[:2] == ["pr", "view"]:
        return emit(facts["pr"], jq=jq_expression(argv))
    if argv[:2] == ["pr", "ready"]:
        # Record the transition without dropping what the state already holds:
        # a run can post a follow-up and then mark the PR ready, and the
        # posted comment is still evidence after the second transition.
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        STATE.write_text(json.dumps({**state, "isDraft": False}), encoding="utf-8")
        return emit(facts["pr_ready_response"])
    if argv[:2] == ["pr", "checks"]:
        return emit(facts["pr_checks"], jq=jq_expression(argv))
    return fail(f"gh: unsupported invocation {argv}")


def answer(argv: list[str]) -> int:
    """Answer one invocation from the recorded facts."""
    facts = read_facts()
    if argv[:1] == ["api"]:
        return answer_api(facts, argv)
    if argv[:1] == ["pr"]:
        return answer_pr(facts, argv)
    if argv[:2] == ["auth", "status"]:
        # The real command prints a human-readable line rather than JSON, so a
        # filter on it is refused by `emit` instead of silently ignored.
        return emit(
            f"Logged in to github.com as {facts['login']}",
            jq=jq_expression(argv),
        )
    return fail(f"gh: unsupported invocation {argv}")


def main(argv: list[str]) -> int:
    """Record the invocation, then answer it."""
    record(argv)
    return answer(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
