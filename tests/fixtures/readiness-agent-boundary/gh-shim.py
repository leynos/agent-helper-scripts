#!/usr/bin/env python3
"""Recorded GitHub stand-in for the readiness agent-boundary experiment.

The scenario directory is derived from this file's own location, not from the
environment, so a run reveals no harness path through `env` and cannot be
redirected by it. Every invocation is appended to `gh-trace.jsonl` next to the
facts before an answer is produced; the answer itself comes from
`facts.json`, which holds this repository's real response shapes.
"""

from __future__ import annotations

import contextlib
import io
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
#: The simulated `cs` writes this file. The transition marker is appended here
#: rather than to the `gh` trace so one ordered record holds both the local
#: check and the transition: two files written by two processes cannot say
#: which came first.
CS_TRACE = RUN / "cs-trace.jsonl"
#: One line per invocation with the status it was answered with and the text the
#: agent actually received. The argv trace records that a read was attempted, and
#: the status records that it returned zero. Neither shows the value: a filtered
#: `pr view --json isDraft --jq 'null'` exits 0 and prints `null`. The answer text
#: is what the agent could act on, so it is recorded rather than inferred from the
#: payload the stand-in meant to serve.
ANSWERS = RUN / "gh-answers.jsonl"


def record(argv: list[str]) -> None:
    """Append one invocation to the trace before answering it."""
    with TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(argv) + "\n")


def record_answer(argv: list[str], status: int, stdout: str) -> None:
    """Append the status and the text an invocation was answered with.

    The text is what the agent received, captured from this process's own
    standard output rather than re-derived from the payload. A `--jq` filter
    can turn a correct payload into `null` while still exiting zero, and
    re-deriving the answer would record the intent instead of the result.
    """
    with ANSWERS.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"argv": argv, "status": status, "stdout": stdout}) + "\n"
        )


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


def has_flag(argv: list[str], name: str) -> bool:
    """Return whether a flag appears, in either its separated or equals form.

    `gh api` accepts `--raw-field body=x` and `--raw-field=body=x` as the same
    request, so a reader that looks only for the bare flag misses a mutation
    written the other way and answers it as a read.
    """
    return any(part == name or part.startswith(name + "=") for part in argv)


def field_values(argv: list[str]) -> list[str]:
    """Return the value of every body-carrying field, in argument order."""
    values = []
    for index, part in enumerate(argv):
        for flag in FIELD_FLAGS:
            if part == flag and index + 1 < len(argv):
                values.append(argv[index + 1])
                break
            if part.startswith(flag + "="):
                values.append(part.split("=", 1)[1])
                break
    return values


def field_body(argv: list[str]) -> str:
    """Return the `body=` field of a request, or an empty string.

    Every field is scanned, not just the first: a request that sends another
    field before `body=` still carries its comment, and recording it as empty
    would lose the very text the recording is evidence for. Both the separated
    and the equals form are read, so either spelling of a POST is recorded.
    """
    for value in field_values(argv):
        if value.startswith("body="):
            return value.removeprefix("body=")
    return ""


class Refused(Exception):
    """A request the real service would reject, rather than answer empty.

    Returning an empty body instead would turn an unreadable or malformed
    request into a successful POST carrying nothing, which is evidence for a
    comment the client never sent.
    """

    def __init__(self, message: str, status: int = 1) -> None:
        """Carry the client's message and exit status through to the caller."""
        super().__init__(message)
        self.message = message
        self.status = status


def input_text(argv: list[str]) -> str | None:
    """Return the raw `--input` payload, or None when the flag is absent.

    A file that cannot be read is a failed request. Reporting it as an empty
    body would let the run record a comment whose text was never supplied.
    """
    source = flag_value(argv, "--input")
    if not source:
        return None
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except OSError as error:
        raise Refused(f"gh: failed to open {source}: {error.strerror}") from error


def input_body(raw: str) -> str:
    """Return the `body` of a JSON `--input` envelope, or refuse the request."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise Refused(f"gh: invalid JSON in --input: {error.msg}") from error
    body = payload.get("body") if isinstance(payload, dict) else None
    if not isinstance(body, str) or not body:
        raise Refused("gh: HTTP 422: body is required")
    return body


def submitted_body(argv: list[str]) -> str:
    """Return the comment body a POST was given, as `gh api` would send it.

    Every failure mode here is one the real service rejects, so the stand-in
    refuses it before any state is written rather than recording an empty
    comment. `gh api` exits non-zero for each of them.
    """
    raw = input_text(argv)
    if raw is not None:
        return input_body(raw)
    # `-f body=...` sends the field directly, with no JSON envelope, so the
    # body is the value after the field name and not the whole expression.
    body = field_body(argv)
    if not body:
        raise Refused("gh: HTTP 422: body is required")
    return body


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
READ_COMMENT = re.compile(r"repos/[^/]+/[^/]+/issues/comments/(\d+)")


def head_ref(facts: dict) -> str:
    """Return the head the PR is on, as the transition marker records it.

    The boundary line names a head so the runner can tell a delta for the
    candidate under test from one for any other revision.
    """
    return str(facts["pr"].get("headRefOid", ""))


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
    try:
        body = submitted_body(argv)
    except Refused as refused:
        # The refusal happens before `state.json` is written, so a request the
        # service would reject leaves the record exactly as it was.
        return fail(refused.message, refused.status)
    posted = posted_comment(facts, body, login)
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


def comments_in(payload: object) -> list[dict]:
    """Return the comment objects a recorded route carries, ignoring the rest.

    A route holds either a single object or a list, and the list may carry
    non-comment entries. Flattening both shapes here keeps the lookup below
    free of type tests.
    """
    items = payload if isinstance(payload, list) else [payload]
    return [
        item for item in items if isinstance(item, dict) and "id" in item
    ]


def recorded_comment(facts: dict, url: str) -> dict | None:
    """Return the issue comment a single-comment route names, if recorded.

    A posted comment is served ahead of the listing it was added to. A
    comment that exists only in the recorded listing is still a real comment
    the agent asked for, so it is served from there rather than reported
    missing.
    """
    ident = int(READ_COMMENT.fullmatch(url).group(1))
    routes = [facts.get("posted"), *facts["api"].values()]
    for item in (entry for route in routes for entry in comments_in(route)):
        if item["id"] == ident:
            return item
    return None


def handle_read(facts: dict, argv: list[str], url: str) -> int:
    """Serve a posted comment, or answer a path from the recorded facts."""
    jq = jq_expression(argv)
    path = (url or "").lstrip("/")
    if READ_COMMENT.fullmatch(path):
        found = recorded_comment(facts, path)
        return emit(found, jq=jq) if found else fail("gh: Not Found (HTTP 404)")
    for pattern, payload in facts["api"].items():
        if re.search(pattern, path):
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
    mutation = any(has_flag(argv, flag) for flag in FIELD_FLAGS) or has_flag(
        argv, "--input"
    )
    return "POST" if mutation else "GET"


def is_post_comment(argv: list[str], url: str) -> bool:
    """Return whether this invocation posts a comment to the PR."""
    return (
        request_method(argv) == "POST"
        and POST_COMMENT.fullmatch((url or "").lstrip("/")) is not None
    )


def is_graphql_read(argv: list[str]) -> bool:
    """Return whether this `graphql` invocation is a read, not a mutation.

    A GraphQL document is a POST whenever it carries a field, so the method
    alone cannot separate a query from a mutation. The recorded readiness runs
    ask one read query — the review-thread state — and nothing else. Exempting
    the whole route would answer a `mutation{...}` with a recorded read and
    report a write the stand-in never made, which is the same defect as
    accepting a POST it refused.

    Only the `query` field carries the document. Scanning every field let an
    `operationName=query` sent ahead of a mutation document make the mutation
    read as a query, and returning on the first match meant the document was
    never reached. The document is therefore read from its own field, and a
    mutation anywhere in it wins over a `query` keyword in its operation text.
    """
    documents = [
        value for value in field_values(argv)
        if value.lstrip().startswith(("query", "mutation", "subscription", "{", "#"))
    ]
    if not documents:
        return False
    if any(re.search(r"\bmutation\b", document) for document in documents):
        return False
    if any(re.search(r"\bsubscription\b", document) for document in documents):
        return False
    return all(re.search(r"\bquery\b", document) or "{" in document
               for document in documents)


def answer_api(facts: dict, argv: list[str]) -> int:
    """Answer one `gh api` invocation.

    The method is resolved before any read route is considered. `gh api` sends
    a write for a field-bearing or `--method` invocation whatever the path is,
    so answering `gh api user --method DELETE` with a user object would report
    a mutation the stand-in never made.
    """
    url = api_url(argv)
    method = request_method(argv)
    if method == "POST" and is_post_comment(argv, url):
        return handle_post(facts, argv)
    # `graphql` is a POST whether the document reads or writes, so it is
    # exempted only when the method is POST and its own text is a query. Any
    # other verb on that route is a request the real service would reject, not
    # a read the stand-in may answer. A GET is no exception: the GraphQL
    # endpoint takes only POST, so letting GET fall through to the REST read
    # routes would serve a document the service would have refused.
    if url == "graphql":
        if method != "POST" or not is_graphql_read(argv):
            return fail(f"gh: unsupported {method} {url}", 2)
    elif method != "GET":
        return fail(f"gh: unsupported {method} {url}", 2)
    if url == "user":
        # The routing record holds only the login, so serve a user object with
        # that field. A `--jq .login` filter then resolves through the same
        # path as every other payload instead of returning the raw string.
        return emit({"login": login_for(facts)}, jq=jq_expression(argv))
    return handle_read(facts, argv, url)


def answer_pr(facts: dict, argv: list[str]) -> int:
    """Answer one `gh pr` invocation.

    `pr view` and `pr checks` serve JSON, so a `--jq` filter is applied to them.
    `pr ready` answers with a fixed response and takes no filter.
    """
    # A listing of one PR is the same PR. Serving it as a single object would
    # break every filter written for a list, so it stays a list.
    if argv[:2] == ["pr", "view"]:
        return emit(facts["pr"], jq=jq_expression(argv))
    if argv[:2] == ["pr", "list"]:
        return emit([facts["pr"]], jq=jq_expression(argv))
    if argv[:2] == ["pr", "diff"]:
        return emit(facts["pr_diff"])
    if argv[:2] == ["pr", "ready"]:
        # Record the transition without dropping what the state already holds:
        # a run can post a follow-up and then mark the PR ready, and the
        # posted comment is still evidence after the second transition.
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        STATE.write_text(json.dumps({**state, "isDraft": False}), encoding="utf-8")
        # The same instant is recorded in the local-check trace, so the runner
        # can tell a `cs delta` read before the decision from one run after it.
        # Appending at the transition is what makes that ordering observable;
        # two files on their own can only show that both happened.
        with CS_TRACE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": "pr-ready", "head": head_ref(facts)}) + "\n")
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
    if argv[:2] == ["repo", "clone"]:
        # A clone reaches GitHub over the network, which this sandbox drops, so
        # it fails here for the reason it would really fail rather than being
        # reported as a command the client does not have.
        return fail(
            "fatal: unable to access 'https://github.com/': "
            "Could not resolve host: github.com"
        )
    if argv[:2] == ["auth", "status"]:
        # The real command prints a human-readable line rather than JSON, so a
        # filter on it is refused by `emit` instead of silently ignored.
        return emit(
            f"Logged in to github.com as {facts['login']}",
            jq=jq_expression(argv),
        )
    return fail(f"gh: unsupported invocation {argv}")


def main(argv: list[str]) -> int:
    """Record the invocation and its result, then answer it.

    The answer is captured by redirecting this process's own standard output
    into a buffer, so what is recorded is the bytes the agent received —
    including whatever a `--jq` filter made of them — and not a second
    rendering of the payload. Standard error stays on the real stream, so the
    agent still sees a refusal.
    """
    record(argv)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = answer(argv)
    sys.stdout.write(buffer.getvalue())
    record_answer(argv, status, buffer.getvalue())
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
