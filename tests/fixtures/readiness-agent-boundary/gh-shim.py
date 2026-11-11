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
from datetime import UTC, datetime, timedelta
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
#: The key under which `read_facts` carries the state it observed, so a step
#: that needs it again reads that observation rather than the file a second
#: time. A premise that happened to use this name would be overwritten by the
#: observation, which is intended: the file is the authority once it exists.
STATE_OBSERVATION = "state"


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


class StateFault(Exception):
    """A run's own record could not be read, rather than simply not existing.

    A first invocation has no `state.json`, and that is a real state: the
    fixture premises answer every question on its own. A `state.json` that
    exists but cannot be parsed is not that state — it is a recording this run
    wrote and can no longer read. Treating it as absent would let the run answer
    from the premise alone and hide the lost write, so it is reported instead.
    """


def read_facts() -> dict:
    """Return this run's facts, with any post-transition state applied.

    The state this returns is the one observation of `state.json` the
    invocation makes. A later step that needs the state again reads it from
    the facts rather than opening the file a second time, because two reads
    can disagree: a file removed between them would take the earlier
    observation with it, and a POST that continued from the second read would
    restart its comment numbering and drop the comments the first read saw.

    Raises
    ------
    StateFault
        Raised when the state file exists but cannot be read as a JSON object.
        A missing file is not a fault: it means no transition has happened yet.
    """
    facts = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as fault:
            raise StateFault(f"cannot read {STATE.name}: {fault}") from fault
        if not isinstance(state, dict):
            raise StateFault(f"{STATE.name} is not a JSON object")
        # `isDraft` belongs to the PR; anything else the state holds, such as a
        # posted comment, stays a top-level fact so a later read can find it.
        facts["pr"] = {
            **facts["pr"],
            **{key: value for key, value in state.items() if key in facts["pr"]},
        }
        facts.update(
            {key: value for key, value in state.items() if key not in facts["pr"]}
        )
        # The same state is carried under its own key, so a step that needs it
        # reads what this observation saw. Taking it from the facts rather than
        # from the file is what keeps a POST from losing the comments a first
        # read recorded when the file is gone by the time it looks again.
        facts[STATE_OBSERVATION] = state
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


#: The stamp a posted comment takes when the facts carry no discussion to sort
#: after. It is the epoch, so it is visibly a fixture value rather than a
#: plausible-looking date that could be mistaken for a recorded one.
FALLBACK_POSTED_AT = "1970-01-01T00:00:00Z"

STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def posted_at(facts: dict) -> str:
    """Return the timestamp a comment posted now would carry.

    The real service stamps a POST with the instant it is accepted, which a
    stand-in cannot know: it replays recorded answers and has no clock. What it
    can reproduce is the property a polling run depends on. A run that should
    poll for a fresh reply filters the discussion by time, so the stamp must
    sort after every comment already in the thread.

    It is therefore one minute past the latest time the facts record. This is
    a derived fixture value, not the instant of the POST: it is deterministic,
    so a replay records the same value, and it always sorts after the thread
    the comment was posted into.

    A second post in the same run also gets a later stamp, because `read_facts`
    folds the state of earlier posts back into the facts this reads. That is
    what keeps two posts distinguishable by time rather than sharing a stamp.

    Parameters
    ----------
    facts : dict
        The run's recorded facts, whose discussion supplies the latest stamp.

    Returns
    -------
    str
        An RFC 3339 UTC timestamp later than everything the facts record.
    """
    stamps = STAMP.findall(json.dumps(facts))
    if not stamps:
        return FALLBACK_POSTED_AT
    latest = max(
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        for stamp in stamps
    )
    return (latest + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def posted_comment(facts: dict, body: str, login: str, ident: int) -> dict:
    """Return the comment the API creates for an authorized POST carrying `body`.

    The author is the account the request authenticated as, not the pool's
    expected login: a POST that presented no token, or the wrong one, must not
    record itself as the pool account and so appear authorized.

    `ident` is the id this POST is assigned. The real service assigns a new one
    to every accepted comment, so a run that posts two follow-ups — which the
    superseded-revision and stale-revision cases do when both assessments must
    be renewed — sees two comments rather than one that keeps overwriting
    itself. A stand-in with a single fixed id made the second POST look like it
    had replaced the first, and a run reported that as a defect in the service
    rather than in this fixture.
    """
    post = facts.get("posted_comment", {})
    return {
        "id": post.get("id", ident),
        "html_url": post.get(
            "html_url",
            f"https://github.com/leynos/agent-helper-scripts/pull/272#issuecomment-{ident}",
        ),
        "user": {"login": login, "type": "User"},
        # The submitted text is kept, not replaced by a placeholder: the
        # follow-up's content is part of what the recording is evidence for.
        "body": body,
        # The real service stamps every comment, and a run that should poll for
        # a fresh reply filters the listing by time. Omitting the timestamps
        # made a posted comment read back with `created_at: null`, and a
        # recording then reported that the service had not stamped it — a
        # fixture artefact the agent cannot tell from a comment the service
        # accepted without recording when. The stand-in has no clock, so the
        # stamp is derived: it sorts after the discussion the comment was
        # posted into and after any earlier post in this run, which is what a
        # time-filtered poll needs. It is not claimed to be the instant of the
        # POST.
        "created_at": post.get("created_at", posted_at(facts)),
        "updated_at": post.get("updated_at", posted_at(facts)),
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

    Each accepted POST is appended under an id of its own. A readiness run may
    renew two assessments at once when both are invalidated, and a stand-in
    that kept only the latest would report the first as missing — a fixture
    artefact the agent cannot tell from a service that lost it. Each post also
    takes its own derived stamp, later than the one before it, so the two are
    distinguishable by time and a time-filtered poll sees both.

    The prior comments come from the state `read_facts` already observed, not
    from a second read of the file. A POST that reopened `state.json` would
    find a file deleted in between indistinguishable from never having posted,
    and would then reuse the first comment id and report the run's earlier
    comments as absent — a lost write answered as a first one.
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
    observed = facts.get(STATE_OBSERVATION) or {}
    prior = observed.get("posted") or []
    posted = posted_comment(facts, body, login, POSTED_ID + len(prior))
    state = {
        "isDraft": facts["pr"].get("isDraft", True),
        "posted": [*prior, posted],
    }
    STATE.write_text(json.dumps(state), encoding="utf-8")
    # The response is the created comment, so a `--jq .html_url` filter applies
    # to it exactly as it would against the real service.
    return emit(posted, jq=jq_expression(argv))


#: The id the first accepted POST is assigned. Successive posts take the ids
#: above it, so two follow-ups in one run are two distinct comments.
POSTED_ID = 9901


# `state_value` used to sit here and re-open `state.json` for the POST. Two
# reads of one file can disagree — a file removed between them reads as "never
# posted" — so the POST now takes the state `read_facts` observed. The helper
# is gone rather than left unused, because a second read path is the defect.




COMMENT_LISTING = re.compile(r"/issues/\d+/comments")


def with_posted(payload: object, url: str, posted: object) -> object:
    """Include every posted comment in a comment listing.

    A posted comment is part of the discussion from then on, so listing the
    comments reflects it without changing the facts. All of them are included:
    a run that renewed two assessments reads the discussion back to find both,
    and a listing carrying only the latest would strand the other.
    """
    if not isinstance(payload, list) or not isinstance(posted, list):
        return payload
    return [*payload, *posted] if COMMENT_LISTING.search(url) else payload


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

    The document is taken from `query=` itself rather than from any value that
    merely starts with `query`, so a differently named field such as
    `queryName=query` cannot supply one. An empty or whitespace-only document
    is no document: answering it with the recorded read would report a query
    the run never sent, which is the same defect as answering a mutation.
    """
    documents = [
        value.removeprefix("query=")
        for value in field_values(argv)
        if value.startswith("query=")
    ]
    if not documents or any(not document.strip() for document in documents):
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
    match request_method(argv):
        case "POST" if is_post_comment(argv, url):
            return handle_post(facts, argv)
        # `graphql` is a POST whether the document reads or writes, so it is
        # exempted only when its own text is a query. A GET is no exception:
        # the GraphQL endpoint takes only POST, so letting GET fall through to
        # the REST read routes would serve a document the service refused.
        case "POST" if url == "graphql" and is_graphql_read(argv):
            pass
        case "GET" if url != "graphql":
            pass
        case method:
            return fail(f"gh: unsupported {method} {url}", 2)
    if url == "user":
        # The routing record holds only the login, so serve a user object with
        # that field. A `--jq .login` filter then resolves through the same
        # path as every other payload instead of returning the raw string.
        return emit({"login": login_for(facts)}, jq=jq_expression(argv))
    return handle_read(facts, argv, url)


def project(payload: object, argv: list[str]) -> object:
    """Return only the fields `--json` asked for, as `gh` does.

    The real client serves the named fields alone and refuses a name it does
    not know. Serving the whole record instead would let a run read a field it
    never requested, so a recording could show evidence that the real command
    would not have provided.
    """
    asked = [name for name in flag_value(argv, "--json").split(",") if name]
    if not asked:
        return payload
    if isinstance(payload, list):
        return [project(item, argv) for item in payload]
    if not isinstance(payload, dict):
        return payload
    unknown = [name for name in asked if name not in payload]
    if unknown:
        raise Refused(f"gh: Unknown JSON field: {unknown[0]!r}")
    return {name: payload[name] for name in asked}


def answer_pr(facts: dict, argv: list[str]) -> int:
    """Answer one `gh pr` invocation.

    `pr view` and `pr checks` serve JSON, so a `--jq` filter is applied to them.
    `pr ready` answers with a fixed response and takes no filter.
    """
    match argv[:2]:
        # A listing of one PR is the same PR. Serving it as a single object
        # would break every filter written for a list, so it stays a list.
        case ["pr", "view"]:
            return emit(project(facts["pr"], argv), jq=jq_expression(argv))
        case ["pr", "list"]:
            return emit(project([facts["pr"]], argv), jq=jq_expression(argv))
        case ["pr", "diff"]:
            return emit(facts["pr_diff"])
        case ["pr", "ready"]:
            return mark_ready(facts)
        case ["pr", "checks"]:
            return emit(facts["pr_checks"], jq=jq_expression(argv))
    return fail(f"gh: unsupported invocation {argv}")


def mark_ready(facts: dict) -> int:
    """Record the draft-to-ready transition and answer it.

    The transition is written without dropping what the state already holds: a
    run can post a follow-up and then mark the PR ready, and the posted comment
    is still evidence after the second transition.
    """
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    STATE.write_text(json.dumps({**state, "isDraft": False}), encoding="utf-8")
    # The same instant is recorded in the local-check trace, so the runner can
    # tell a `cs delta` read before the decision from one run after it.
    # Appending at the transition is what makes that ordering observable; two
    # files on their own can only show that both happened.
    with CS_TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "pr-ready", "head": head_ref(facts)}) + "\n")
    return emit(facts["pr_ready_response"])


def answer(argv: list[str]) -> int:
    """Answer one invocation from the recorded facts."""
    # A route may refuse what the real client would refuse — an unknown
    # `--json` field, a malformed body — and a refusal is an answer with a
    # non-zero status, not a crash. Letting it escape would report a traceback
    # where the agent should see the client's own message.
    #
    # The state read is inside this boundary too. A run that cannot read back
    # the comments it posted has lost a write of its own; answering from the
    # premise as though it had not posted would report success for an
    # observation that never happened. It sits inside the `try` rather than
    # above it because `read_facts` is what raises the fault.
    try:
        # Each case is a prefix, not the whole argument list: the trailing
        # words are the command's own arguments, and a case that matched only
        # an exact length would turn every invocation carrying them into
        # "unsupported".
        facts = read_facts()
        match argv:
            case ["api", *_]:
                return answer_api(facts, argv)
            case ["pr", *_]:
                return answer_pr(facts, argv)
            case ["repo", "clone", *_]:
                # A clone reaches GitHub over the network, which this sandbox
                # drops, so it fails here for the reason it would really fail
                # rather than being reported as a command the client lacks.
                return fail(
                    "fatal: unable to access 'https://github.com/': "
                    "Could not resolve host: github.com"
                )
            case ["auth", "status", *_]:
                # The real command prints a human-readable line rather than
                # JSON, so a filter on it is refused by `emit` instead of
                # silently ignored.
                return emit(
                    f"Logged in to github.com as {facts['login']}",
                    jq=jq_expression(argv),
                )
        return fail(f"gh: unsupported invocation {argv}")
    except Refused as refused:
        return fail(refused.message, refused.status)
    except StateFault as fault:
        return fail(f"gh: fixture state fault: {fault}", 1)


def run_recorded(argv: list[str]) -> int:
    """Answer one invocation inside the recording boundary.

    The boundary is the whole of `main`'s work around `answer`: the argv is
    written before the answer is computed, so an invocation that crashes is
    still visible in the trace, and the bytes the agent received are captured
    from this process's own standard output rather than re-derived, so a `--jq`
    filter that yields `null` while exiting zero is recorded as `null`.

    Keeping this in one function is what makes the trace trustworthy. A route
    that answered *outside* the boundary would leave a command the agent ran
    with no entry, and a recording would then under-report what the run read.
    Everything reachable from `answer` is inside it.

    Parameters
    ----------
    argv : list of str
        The invocation, exactly as the agent spelled it.

    Returns
    -------
    int
        The exit status the agent sees.
    """
    record(argv)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = answer(argv)
    sys.stdout.write(buffer.getvalue())
    record_answer(argv, status, buffer.getvalue())
    return status


def main(argv: list[str]) -> int:
    """Route this process's invocation through the recording boundary."""
    return run_recorded(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
