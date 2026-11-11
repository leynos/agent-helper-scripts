"""Contract regressions for the readiness agent-boundary rehearsal.

The rehearsal runs a headless agent against the shipped `pr-babysitting` skill
inside a sandbox that replaces two clients with recorded stand-ins. The `gh`
stand-in serves the GitHub routes a readiness run reads and records every
invocation; because a route it answers wrongly changes the evidence a recording
provides rather than merely failing a command, each case here pins one route
against the behaviour the real client has: a write stays a write however its
flags are spelled, a filter is applied to JSON or refused outright, and a
`--json` list yields only the fields it names. The `cs` stand-in serves the
local CodeScene routes the same run reads — `delta` and a focused `check` —
answering each mode (`clean`, `finding`, `unavailable`) in the CLI's own shape
and exit status, disclosing in its own output that it is simulated, and keeping
a fixture fault (facts never served) distinct from a local result it cannot
evaluate.

The runner's checks are proved the same way. `sandboxed_run.sh` extracts each
heredoc probing a trace and runs it against constructed input, so `PROBE_PLAN`,
`PROBE_READBACK`, `PROBE_AUTHZ`, `PROBE_DELTA` and `PROBE_STATE` are exercised
by the sequences they must accept and refuse rather than by reading the
script's text. Extracting a probe proves what it decides, not that the runner
reaches it, so the two checks that are delinquent exactly when a run is
expected to transition also carry a source-text containment assertion; the
others have no equivalent wiring assertion.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType

import pytest


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "readiness-agent-boundary"
SHIM = FIXTURES / "gh-shim.py"
CS_SHIM = FIXTURES / "cs-shim.py"
SCENARIO = FIXTURES / "scenarios" / "current-whole-plan" / "facts.json"
POOL_TOKEN = "fixture-pool-token"


def place_shim(source: Path, name: str, directory: Path) -> Path:
    """Copy one stand-in into `directory` under `name`, then make it runnable.

    Both stand-ins derive their run directory from their own location, so a
    copy beside that directory's `facts.json` is what points them at this
    test's scenario; no environment variable can redirect them. Both fixtures
    share this routine rather than repeating it.
    """
    shim = directory / name
    shutil.copy2(source, shim)
    shim.chmod(0o755)
    return directory


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """Place a runnable copy of the `gh` stand-in beside one scenario's facts."""
    shutil.copy2(SCENARIO, tmp_path / "facts.json")
    return place_shim(SHIM, "gh", tmp_path)


def invoke(
    run: Path, *argv: str, token: str = "", stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the stand-in with one invocation and return its completed process."""
    env = {**os.environ, "GH_TOKEN": token, "GH_CONFIG_DIR": str(run / "gh-config")}
    return subprocess.run(
        [str(run / "gh"), *argv],
        capture_output=True,
        text=True,
        input=stdin,
        env=env,
        check=False,
    )


def posted(run: Path) -> list[dict]:
    """Return the comments the run recorded, failing clearly when none was.

    Reading `state.json` directly would report a missing file, which says
    nothing about the defect. Naming the absent record instead shows that the
    write was answered as a read.

    The record is a list because the real service assigns a new id to every
    accepted comment, and a run that renews two assessments posts twice.
    """
    state = run / "state.json"
    assert state.exists(), "no comment was recorded: the write was treated as a read"
    return json.loads(state.read_text(encoding="utf-8"))["posted"]


def last_posted(run: Path) -> dict:
    """Return the most recently recorded comment, asserting one exists.

    A single-post test reads the only entry; the caller that checks several
    posts reads `posted` directly. Naming the last one keeps a one-post test
    from indexing a list it never claimed was ordered.
    """
    comments = posted(run)
    assert comments, "no comment was recorded: the write was treated as a read"
    return comments[-1]


@pytest.mark.parametrize(
    ("method", "expected"),
    [("--method DELETE", "DELETE"), ("-X PATCH", "PATCH")],
    ids=["long-form", "short-form"],
)
def test_write_method_reaches_the_user_route(
    run: Path, method: str, expected: str
) -> None:
    """A write is refused even on a path that also has a read response.

    `gh api user --method DELETE` is a delete request, so answering it with a
    user object would record a mutation the stand-in never made.
    """
    done = invoke(run, "api", *method.split(), "user")
    assert done.returncode == 2, done.stdout
    assert f"unsupported {expected} user" in done.stderr, "expected the formatted refusal in done.stderr"


def test_explicit_read_method_still_serves_the_user_route(run: Path) -> None:
    """An explicit GET keeps the route readable, so the refusal is about method."""
    done = invoke(run, "api", "--method", "GET", "user", "--jq", ".login")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip(), "expected done.stdout.strip() to hold"


GRAPHQL_READ = (
    'query{repository(owner:"leynos",name:"agent-helper-scripts")'
    "{pullRequest(number:272){reviewThreads(first:100){nodes{isResolved}}}}}"
)


@pytest.mark.parametrize(
    "query",
    [
        'mutation{addComment(input:{body:"x"}){clientMutationId}}',
        'mutation{markPullRequestReadyForReview(input:{pullRequestId:"1"}){clientMutationId}}',
    ],
    ids=["add-comment", "mark-ready"],
)
def test_a_graphql_mutation_is_refused(run: Path, query: str) -> None:
    """A GraphQL document that writes is not answered from the recorded reads.

    `graphql` is a POST whenever the document carries fields, so the route name
    cannot separate a query from a mutation. Exempting the whole route would
    answer a mutation with the recorded review-thread state, which reports a
    write the stand-in never made — the same defect as accepting a refused POST.
    """
    done = invoke(run, "api", "graphql", "-f", f"query={query}")
    assert done.returncode == 2, done.stdout
    assert "unsupported POST graphql" in done.stderr, "expected 'unsupported POST graphql' in done.stderr"


def test_a_graphql_read_query_is_still_answered(run: Path) -> None:
    """The readiness run's review-thread query keeps working, so the test bites."""
    done = invoke(run, "api", "graphql", "-f", f"query={GRAPHQL_READ}")
    assert done.returncode == 0, done.stderr
    assert "reviewThreads" in done.stdout, "expected 'reviewThreads' in done.stdout"


@pytest.mark.parametrize(
    "argv",
    [
        ("-f", "query="),
        ("-f", "query=   "),
        ("-f", "queryName=query{prUpdated}"),
        ("--field", "queryBody={prUpdated}"),
        (),
    ],
    ids=["empty", "whitespace", "other-field", "other-long-field", "absent"],
)
def test_a_field_that_is_not_the_query_document_is_refused(
    run: Path, argv: tuple[str, ...]
) -> None:
    """Only a non-empty `query=` field is the read document.

    A value that merely starts with `query` belongs to another field, and an
    empty document carries nothing to read. Answering either from the recorded
    reads reports a query the run never sent — the same defect as answering a
    mutation, which is why the check is on the field name and its content
    rather than on a prefix.
    """
    done = invoke(run, "api", "graphql", *argv)
    assert done.returncode != 0, f"answered a non-document request: {done.stdout}"
    # A field-bearing call is a POST and an absent field makes it a GET, so the
    # refusal names the method the real service would have received. Either way
    # the request is refused rather than answered from the recorded reads.
    assert "unsupported" in done.stderr and "graphql" in done.stderr, done.stderr


def test_a_word_before_the_document_does_not_make_a_mutation_read(run: Path) -> None:
    """A `query` anywhere before the document is not the document being a query.

    Requiring only that some field looks like a query let `operationName=query`
    serve a following `mutation{...}` from the recorded reads, which reports a
    write the stand-in never made. The document has to be found in its own
    field, and a mutation in it has to win over that earlier word.
    """
    done = invoke(
        run,
        "api",
        "graphql",
        "-f",
        "operationName=query",
        "-f",
        'query=mutation{addComment(input:{body:"x"}){clientMutationId}}',
    )
    assert done.returncode == 2, done.stdout
    assert "unsupported POST graphql" in done.stderr, "expected 'unsupported POST graphql' in done.stderr"


def test_a_mutation_after_a_read_is_still_refused(run: Path) -> None:
    """Two documents are two operations, and one of them writes.

    The recorded trace is a list of invocations, and the first one that looks
    like a read must not end the scan: a run that sends its query first and its
    mutation second would otherwise have the mutation answered from the reads.
    """
    done = invoke(
        run,
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL_READ}",
        "-f",
        'query=mutation{markPullRequestReadyForReview(input:{pullRequestId:"1"}){clientMutationId}}',
    )
    assert done.returncode == 2, done.stdout
    assert "unsupported POST graphql" in done.stderr, "expected 'unsupported POST graphql' in done.stderr"


def test_a_subscription_is_not_answered_from_the_recorded_reads(run: Path) -> None:
    """A subscription is a request the stand-in cannot answer, so it must refuse.

    It is neither the recorded query nor a flat mutation, so treating anything
    that is not a mutation as readable would answer it from the read facts.
    """
    done = invoke(run, "api", "graphql", "-f", "query=subscription{prUpdated}")
    assert done.returncode == 2, done.stdout
    assert "unsupported POST graphql" in done.stderr, "expected 'unsupported POST graphql' in done.stderr"


@pytest.mark.parametrize(
    ("method", "expected"),
    [("--method DELETE", "DELETE"), ("-X PATCH", "PATCH"), ("--method PUT", "PUT")],
    ids=["delete", "patch", "put"],
)
def test_a_non_post_graphql_request_is_refused(
    run: Path, method: str, expected: str
) -> None:
    """Exempting the route by name alone would accept any verb on it.

    The real service answers `graphql` as a POST. A DELETE or PUT there is a
    request it would reject, so serving a recorded read for it reports a call
    the run did not make.
    """
    done = invoke(
        run, "api", "graphql", *method.split(), "-f", f"query={GRAPHQL_READ}"
    )
    assert done.returncode == 2, done.stdout
    assert f"unsupported {expected} graphql" in done.stderr, "expected the formatted refusal in done.stderr"


def test_an_explicit_get_graphql_read_is_refused(run: Path) -> None:
    """A GET is how the real client reads a REST path, not a GraphQL document.

    `gh api graphql` is a POST; a GET naming `graphql` with a query field is
    not a call the service supports, so the stand-in must not answer it as one.
    """
    done = invoke(
        run, "api", "--method", "GET", "graphql", "-f", f"query={GRAPHQL_READ}"
    )
    assert done.returncode == 2, done.stdout
    assert "unsupported GET graphql" in done.stderr, "expected 'unsupported GET graphql' in done.stderr"


@pytest.mark.parametrize(
    "flag",
    ["--raw-field=body=equals-form", "--field=body=equals-form"],
)
def test_equals_form_fields_still_post(run: Path, flag: str) -> None:
    """A field written as `--flag=value` is the same request as `--flag value`.

    Reading only the separated spelling would treat the call as a GET, answer
    a 404, and record no comment at all.
    """
    done = invoke(
        run,
        "api",
        "repos/leynos/agent-helper-scripts/issues/272/comments",
        flag,
        token=POOL_TOKEN,
    )
    assert done.returncode == 0, done.stderr
    record = last_posted(run)
    assert record["body"] == "equals-form", "expected record[\"body\"] to equal \"equals-form\""
    assert record["user"]["login"] == "fixture-commenter", "expected record[\"user\"][\"login\"] to equal \"fixture-commenter\""


def test_equals_form_input_still_posts(run: Path, tmp_path: Path) -> None:
    """`--input=FILE` is a mutation too, and its body is recorded."""
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps({"body": "from a file"}), encoding="utf-8")
    done = invoke(
        run,
        "api",
        "repos/leynos/agent-helper-scripts/issues/272/comments",
        f"--input={payload}",
        token=POOL_TOKEN,
    )
    assert done.returncode == 0, done.stderr
    assert last_posted(run)["body"] == "from a file", "expected posted(run)[\"body\"] to equal \"from a file\""


def test_pr_view_applies_a_filter(run: Path) -> None:
    """`gh pr view --jq` answers the filtered value, not the whole PR object."""
    done = invoke(run, "pr", "view", "272", "--json", "isDraft", "--jq", ".isDraft")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() in {"true", "false"}


#: Keys whose values are bound to one recording rather than to the route's
#: contract. The readiness runner reads these to judge a candidate, so a
#: snapshot that pinned them would fail on every re-recording while saying
#: nothing about whether the stand-in still serves the shape a run needs.
#: `sha` is redacted in place rather than along with `files` and `commits`:
#: those two are arrays the run iterates, so their element shape is contract.
CANDIDATE_BOUND = frozenset({"headRefOid", "baseRefOid", "url", "body", "sha"})

#: The checks payload is a tab-separated table whose rows name hosted checks.
#: Its shape is the contract; the check names and conclusions belong to the
#: facts being served.
CHECKS_ROW = "<check>\t<status>\t<conclusion>"


def recorded_rows(facts_path: Path) -> list[tuple[str, str, str]]:
    """Return the check rows ``facts_path`` records, as the route serves them.

    The `pr_checks` fact is the tab-separated table the route prints. Reading
    it back here is what lets the checks case compare served values with the
    recording rather than with a placeholder.

    Parameters
    ----------
    facts_path : Path
        A scenario's ``facts.json``.

    Returns
    -------
    list of tuple
        One ``(name, status, conclusion)`` per recorded row.
    """
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    table = facts["pr_checks"]
    rows = [line.split("\t") for line in table.splitlines() if line]
    # Unpacking into three names rejects a malformed row here, where the
    # message names the fixture, rather than letting a four- or two-field row
    # reach a test that fails somewhere less obvious. It also lets a type
    # checker see a fixed-width tuple instead of `tuple[str, ...]`.
    return [(name, status, conclusion) for name, status, conclusion in rows]


def redact(value: object) -> object:
    """Return `value` with candidate-bound fields replaced by placeholders.

    Parameters
    ----------
    value : object
        Any part of a served payload, recursed through mappings and sequences.

    Returns
    -------
    object
        The same structure with each candidate-bound value redacted, so the
        snapshot pins the served contract rather than one recording's facts.
    """
    if isinstance(value, dict):
        return {
            key: "<candidate-bound>" if key in CANDIDATE_BOUND else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


PR_VIEW_JSON = (
    "number,title,author,state,isDraft,headRefName,headRefOid,baseRefName,baseRefOid,"
    "headRepository,headRepositoryOwner,isCrossRepository,mergeable,mergeStateStatus,"
    "reviewDecision,statusCheckRollup,body,commits"
)
#: The listing route reads a narrower record than the view, and the semantic
#: assertions below check the same fields on both. Request them all: a route
#: the shim projected to a shorter list would otherwise be asked to prove
#: values it never served, which is evidence the real `gh` would not provide.
PR_LIST_JSON = (
    "number,state,isDraft,headRefName,baseRefName,statusCheckRollup"
)


@pytest.mark.parametrize(
    "argv",
    [
        ("pr", "view", "272", "--repo", "leynos/agent-helper-scripts", "--json", PR_VIEW_JSON),
        ("pr", "list", "--repo", "leynos/agent-helper-scripts", "--json", PR_LIST_JSON),
        ("pr", "checks", "272", "--repo", "leynos/agent-helper-scripts"),
    ],
    ids=["view", "list", "checks"],
)
def test_the_structured_pr_routes_keep_their_shape(
    run: Path, argv: tuple[str, ...], snapshot: object
) -> None:
    """The JSON and tabular routes a readiness run reads keep their contract.

    The runner parses these three answers to decide whether a candidate is
    ready, so a route that changed shape would change the verdict rather than
    merely fail a command. Pinning the shape here makes such a change visible
    as a diff instead of as a run that holds for an unexplained reason.

    Candidate-bound values are redacted, and the semantic assertions stay
    beside the snapshot: the snapshot shows the shape, and the assertions say
    which parts of it the run actually depends on.
    """
    done = invoke(run, *argv)
    assert done.returncode == 0, done.stderr
    if argv[:2] == ("pr", "checks"):
        # The route serves a table, not JSON, and a real `gh` ends it with a
        # newline, so the terminal empty string is part of the served text
        # rather than a row. Counting it as a row would fail every recording.
        rows = [row for row in done.stdout.splitlines() if row]
        assert rows, "the checks route served no rows"
        assert all(len(row.split("\t")) == 3 for row in rows), done.stdout
        assert done.stdout.endswith("\n"), "the checks route must end its table"
        assert snapshot == "\n".join([CHECKS_ROW] * len(rows)), (
            "the checks route changed its tabular contract"
        )
        # The placeholder snapshot proves the column count and nothing more.
        # A route that served the right number of empty columns would pass it
        # while giving the run no check name or result to read, so the served
        # values are compared with the facts they were recorded from.
        served = [tuple(row.split("\t")) for row in rows]
        assert served == recorded_rows(SCENARIO), (
            "the checks route did not serve the recorded check names and results:"
            f" {served}"
        )
        return
    payload = json.loads(done.stdout)
    redacted = redact(payload)
    assert snapshot == redacted, "the structured PR route changed its contract"
    # Read the same fields from the copy the run sees, not from the redacted
    # snapshot: the snapshot proves the shape, these prove the values are usable.
    view = payload[0] if isinstance(payload, list) else payload
    assert view["isDraft"] is True, "the recorded candidate must start in draft"
    assert view["state"] == "OPEN", view["state"]
    assert view["headRefName"], "the run needs a head branch to read a plan at"
    assert view["baseRefName"], "the run needs a base branch to bind a verdict"
    assert isinstance(view["statusCheckRollup"], list), view["statusCheckRollup"]


@pytest.mark.parametrize(
    ("argv", "shape"),
    [
        (("pr", "view", "272"), dict),
        (("pr", "list", "--repo", "leynos/agent-helper-scripts"), list),
    ],
    ids=["view-is-an-object", "list-is-a-list"],
)
def test_pr_listing_keeps_the_shape_its_filters_expect(
    run: Path, argv: tuple[str, ...], shape: type
) -> None:
    """A listing answers a list and a view an object, as the real client does.

    `pr list --jq '.[]'` fails on an object, so serving the one recorded PR as
    a bare object would silently break every list-shaped filter.
    """
    done = invoke(run, *argv)
    assert done.returncode == 0, done.stderr
    assert isinstance(json.loads(done.stdout), shape)


@pytest.mark.parametrize(
    "argv",
    [
        ("api", "repos/leynos/agent-helper-scripts/pulls/272"),
        ("api", "repos/leynos/agent-helper-scripts/pulls/272/files"),
        ("api", "repos/leynos/agent-helper-scripts/pulls/272/commits"),
        ("pr", "diff", "272", "--name-only"),
        # `graphql` is a POST, but a readiness run reads review-thread state
        # through it, so it must answer rather than be refused as a mutation.
        ("api", "graphql", "-f", "query={viewer{login}}"),
    ],
    ids=["pull", "files", "commits", "diff", "graphql-read"],
)
def test_a_readiness_read_is_answered(run: Path, argv: tuple[str, ...]) -> None:
    """Each read a readiness run makes answers from the recorded surface.

    A 404 here is a hole in the recording rather than a fact about the
    candidate, and it hides the diff and file list the decision rests on.
    """
    done = invoke(run, *argv)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip(), "expected done.stdout.strip() to hold"


def test_a_recorded_comment_is_served_on_its_own_route(run: Path) -> None:
    """A comment that exists only in the listing is still a comment.

    Reporting it missing would make the assessment reply look absent, which is
    the opposite of what the recorded listing shows.
    """
    listing = invoke(run, "api", "repos/leynos/agent-helper-scripts/issues/272/comments")
    ident = json.loads(listing.stdout)[0]["id"]
    done = invoke(
        run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{ident}"
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["id"] == ident, "expected json.loads(done.stdout)[\"id\"] to equal ident"


def test_a_passing_codescene_check_can_still_carry_findings(tmp_path: Path) -> None:
    """The CodeScene scenario's check passes while listing an outstanding issue.

    That pairing is the whole point of the scenario: the skill treats a passing
    check with advisory findings as still outstanding, so the recording only
    tests the rule while the conclusion stays `SUCCESS` and the output carries
    the finding. A fixture that failed the check instead would let a run block
    on the badge, which is the reasoning the rule exists to prevent.
    """
    shim = tmp_path / "gh"
    shutil.copy2(SHIM, shim)
    shutil.copy2(
        FIXTURES / "scenarios" / "codescene-advisory" / "facts.json",
        tmp_path / "facts.json",
    )
    shim.chmod(0o755)
    done = invoke(tmp_path, "api", "repos/leynos/agent-helper-scripts/commits/9999aaaa/check-runs")
    assert done.returncode == 0, done.stderr
    checks = {run["name"]: run for run in json.loads(done.stdout)["check_runs"]}
    scene = checks["CodeScene Code Health Review"]
    assert scene["conclusion"] == "SUCCESS", "the badge must not be what blocks the run"
    assert scene["output"]["annotations_count"] > 0, "expected scene[\"output\"][\"annotations_count\"] > 0 to hold"
    assert "Complex Method" in scene["output"]["summary"], "expected 'Complex Method' in scene[\"output\"][\"summary\"]"
    # The finding must name code this candidate changes, or it is evidence about
    # a different PR and the run would be reasoning about the wrong thing.
    changed = json.loads(
        invoke(tmp_path, "api", "repos/leynos/agent-helper-scripts/pulls/272/files").stdout
    )
    paths = {entry["filename"] for entry in changed}
    assert "skills/pr-babysitting/scripts/readiness_gate.py" in paths, "expected 'skills/pr-babysitting/scripts/readiness_gate.py' in paths"


def test_a_clone_fails_for_the_reason_the_sandbox_supplies(run: Path) -> None:
    """A clone is refused as unreachable, not as a command `gh` lacks.

    The sandbox has no route to GitHub, so a clone cannot succeed; reporting it
    as an unsupported invocation would say the client has no such command,
    which is a different and misleading fact about the environment.
    """
    done = invoke(run, "repo", "clone", "leynos/agent-helper-scripts")
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "Could not resolve host" in done.stderr, "expected 'Could not resolve host' in done.stderr"
    assert "unsupported invocation" not in done.stderr, "expected \"unsupported invocation\" not in done.stderr to hold"


@pytest.mark.parametrize(
    "argv",
    [
        ("pr", "checks", "272", "--jq", "length"),
        ("auth", "status", "--jq", ".login"),
    ],
    ids=["pr-checks", "auth-status"],
)
def test_a_filter_on_a_human_readable_route_is_refused(
    run: Path, argv: tuple[str, ...]
) -> None:
    """A text route takes no filter, so printing its text would fake a match.

    `gh pr checks` and `gh auth status` print human-readable lines rather than
    JSON. Applying nothing and returning the text would look like a filter that
    matched everything, which is the failure the recorded traces had.
    """
    done = invoke(run, *argv)
    assert done.returncode == 2, done.stdout
    assert "--jq is not supported on this route" in done.stderr, "expected '--jq is not supported on this route' in done.stderr"


@pytest.mark.parametrize(
    "argv",
    [("pr", "checks", "272"), ("auth", "status")],
    ids=["pr-checks", "auth-status"],
)
def test_an_unfiltered_human_readable_route_still_answers(
    run: Path, argv: tuple[str, ...]
) -> None:
    """The refusal is specific to a filter: the plain route keeps working."""
    done = invoke(run, *argv)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip(), "expected done.stdout.strip() to hold"


COMMENT_ROUTE = "repos/leynos/agent-helper-scripts/issues/272/comments"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (("--input", "/nonexistent/body.json"), "failed to open"),
        (("--input", "-"), "invalid JSON"),
        (("--input", "-"), "body is required"),
        (("--method", "POST"), "body is required"),
    ],
    ids=["unreadable-file", "malformed-json", "empty-body", "missing-body"],
)
def test_a_post_that_cannot_carry_a_body_is_refused_and_changes_nothing(
    run: Path, argv: tuple[str, ...], message: str
) -> None:
    """A request the service would reject must not be recorded as a success.

    Turning unreadable input, malformed JSON or an empty body into `""` and then
    writing `state.json` records a POST carrying nothing, which is evidence for
    a comment the run never sent. The refusal must also leave the record alone,
    so a later read cannot see a comment that was never created.
    """
    stdin = "" if "--input" in argv and argv[-1] == "-" else None
    if message == "body is required" and "--input" in argv:
        stdin = json.dumps({"not_body": "x"})
    done = invoke(run, "api", COMMENT_ROUTE, *argv, token=POOL_TOKEN, stdin=stdin)
    assert done.returncode != 0, done.stdout
    assert message in done.stderr, done.stderr
    assert not (run / "state.json").exists(), "a refused POST wrote state"


def test_an_unauthorized_post_leaves_state_unchanged(run: Path) -> None:
    """A POST without the fixture token fails before any comment is recorded."""
    done = invoke(
        run, "api", COMMENT_ROUTE, "-f", "body=unauthorized", token="wrong-token"
    )
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "401" in done.stderr, "expected \"401\" in done.stderr to hold"
    assert not (run / "state.json").exists(), "expected not (run / \"state.json\").exists() to hold"


def test_a_refused_post_does_not_displace_an_earlier_one(run: Path) -> None:
    """A rejected follow-up must not erase the comment that was accepted.

    `state.json` is the record of what the run posted. Writing an empty body
    over it would lose the earlier comment and present the run as having posted
    nothing, which misstates its own trace.
    """
    first = invoke(run, "api", COMMENT_ROUTE, "-f", "body=first", token=POOL_TOKEN)
    assert first.returncode == 0, first.stderr
    refused = invoke(run, "api", COMMENT_ROUTE, "-f", "body=", token=POOL_TOKEN)
    assert refused.returncode != 0, "expected refused.returncode not to equal 0"
    assert last_posted(run)["body"] == "first", "expected posted(run)[\"body\"] to equal \"first\""


def test_an_unauthorized_post_after_an_accepted_one_changes_nothing(run: Path) -> None:
    """A wrong token is refused on its own merits, not only on a clean slate.

    The earlier refusal test starts with no state, so a stand-in that recorded
    the comment before checking the token would write over nothing and look the
    same. Here a comment is already accepted: the refused POST must leave it,
    and every route that serves it, exactly as it was.
    """
    accepted = invoke(run, "api", COMMENT_ROUTE, "-f", "body=accepted", token=POOL_TOKEN)
    assert accepted.returncode == 0, accepted.stderr
    before = posted(run)
    refused = invoke(run, "api", COMMENT_ROUTE, "-f", "body=injected", token="wrong-token")
    assert refused.returncode != 0, "expected refused.returncode not to equal 0"
    assert "401" in refused.stderr, "expected \"401\" in refused.stderr to hold"
    assert posted(run) == before, "a refused POST rewrote the accepted comment"
    ident = before[-1]["id"]
    single = invoke(run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{ident}")
    assert single.returncode == 0, single.stderr
    assert json.loads(single.stdout)["body"] == "accepted", (
        "the single-comment route served the refused body"
    )
    listing = invoke(run, "api", COMMENT_ROUTE)
    assert [item["body"] for item in json.loads(listing.stdout) if item["id"] == ident] == [
        "accepted"
    ], "the discussion listing served the refused body"


def test_an_authorized_post_is_readable_listed_and_read_back(run: Path) -> None:
    """The accepted comment survives every surface the skill reads after a POST.

    A reply is only evidence if the run that posted it, and a later readiness
    check, can see it again: in the POST response, on its own route, in the
    discussion listing, and on both read routes again after `pr ready` has
    changed the same state file. Checking an ID alone would pass on a listing
    that carries the right comment with the wrong text, which is the exact
    defect the read-back exists to catch.
    """
    done = invoke(run, "api", COMMENT_ROUTE, "-f", "body=hello", token=POOL_TOKEN)
    assert done.returncode == 0, done.stderr
    # The response is the created comment, so the body that was sent comes back
    # on the call itself rather than only from a later read.
    assert json.loads(done.stdout)["body"] == "hello", "the POST response lost the body"
    ident = last_posted(run)["id"]
    url = f"repos/leynos/agent-helper-scripts/issues/comments/{ident}"
    single = invoke(run, "api", url)
    assert single.returncode == 0, single.stderr
    assert json.loads(single.stdout)["body"] == "hello", "expected json.loads(single.stdout)[\"body\"] to equal \"hello\""
    listing = invoke(run, "api", COMMENT_ROUTE)
    assert any(
        item["id"] == ident and item["body"] == "hello"
        for item in json.loads(listing.stdout)
    )
    assert invoke(run, "pr", "ready", "272").returncode == 0
    assert last_posted(run)["body"] == "hello", "the transition dropped the comment"
    assert json.loads((run / "state.json").read_text())["isDraft"] is False, "expected json.loads((run / \"state.json\").read_text())[\"isDraft\"] is False to hold"
    # The transition rewrites the same state file, so both read routes are
    # exercised again: a fix that preserved the comment in the record but
    # served an empty one afterwards would otherwise go unnoticed.
    after_single = invoke(run, "api", url)
    assert after_single.returncode == 0, after_single.stderr
    assert json.loads(after_single.stdout)["body"] == "hello", (
        "the single-comment route lost the body after the transition"
    )
    after_listing = invoke(run, "api", COMMENT_ROUTE)
    assert any(
        item["id"] == ident and item["body"] == "hello"
        for item in json.loads(after_listing.stdout)
    ), "the discussion listing lost the body after the transition"


@pytest.fixture
def cs_run(tmp_path: Path) -> Path:
    """Place a runnable copy of the simulated `cs` beside a facts file."""
    return place_shim(CS_SHIM, "cs", tmp_path)


def test_two_accepted_posts_are_two_readable_comments(run: Path) -> None:
    """A second accepted POST adds a comment; it does not replace the first.

    The real service assigns a new id to every accepted comment. A stand-in
    that held one posted comment made the second look like it had overwritten
    the first: the stale-revision rehearsal renewed both assessments, and its
    outcome reported that the PR's discussion showed only one of the two
    requests. That is a fixture artefact, and an agent cannot tell it apart
    from a service that lost a comment.

    Both must remain readable afterwards, through the route that serves one
    comment and the listing that serves the discussion, because a run reads
    back what it posted through both.
    """
    first = invoke(run, "api", COMMENT_ROUTE, "-f", "body=first", token=POOL_TOKEN)
    assert first.returncode == 0, first.stderr
    second = invoke(run, "api", COMMENT_ROUTE, "-f", "body=second", token=POOL_TOKEN)
    assert second.returncode == 0, second.stderr
    first_id = json.loads(first.stdout)["id"]
    second_id = json.loads(second.stdout)["id"]
    assert first_id != second_id, (
        "two accepted comments shared one id, so the second overwrote the first"
    )
    for ident, body in ((first_id, "first"), (second_id, "second")):
        single = invoke(
            run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{ident}"
        )
        assert single.returncode == 0, f"{body} is no longer readable: {single.stderr}"
        assert json.loads(single.stdout)["body"] == body
    listing = json.loads(invoke(run, "api", COMMENT_ROUTE).stdout)
    bodies = {item["id"]: item["body"] for item in listing}
    assert bodies.get(first_id) == "first", "the listing dropped the first comment"
    assert bodies.get(second_id) == "second", "the listing dropped the second comment"


def test_a_posted_comment_is_stamped_after_the_discussion(run: Path) -> None:
    """A posted comment carries a stamp that sorts after the discussion.

    `gh` filters a discussion by `created_at` when it polls for a fresh reply,
    and a comment with no stamp cannot be selected by such a filter. The
    candidate-mismatch rehearsal posted a follow-up and read it back with
    `created_at: null`, then reported that as a defect in the service; the
    superseded-revision recording said the same. Both are this stand-in's
    omission, and an agent cannot tell one from a service that accepted a
    comment without recording when.

    The value is derived — the latest stamp the facts record, plus a minute —
    not the instant of the POST, which a stand-in with no clock cannot know.
    The property asserted is the one a poll depends on: it sorts after the
    thread it was posted into, so a poll asking for comments newer than the
    last recorded reply still sees the comment the run had just added.
    """
    done = invoke(run, "api", COMMENT_ROUTE, "-f", "body=stamped", token=POOL_TOKEN)
    assert done.returncode == 0, done.stderr
    created = json.loads(done.stdout)["created_at"]
    assert created, "an accepted POST was served without a created_at"
    assert created == json.loads(done.stdout)["updated_at"], (
        "a just-posted comment's created_at and updated_at disagreed"
    )
    single = invoke(run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{last_posted(run)['id']}")
    assert single.returncode == 0, single.stderr
    assert json.loads(single.stdout)["created_at"] == created, (
        "the comment's own route served a different stamp from the POST"
    )
    discussed = max(
        item["updated_at"]
        for item in json.loads((run / "facts.json").read_text(encoding="utf-8"))["api"][
            "/issues/\\d+/comments"
        ]
    )
    assert created > discussed, (
        f"the posted comment is stamped {created}, not after the discussion's "
        f"latest entry {discussed}, so a time-filtered poll would skip it"
    )


def test_each_post_in_a_run_is_stamped_later_than_the_one_before(run: Path) -> None:
    """Two follow-ups in one run are distinguishable by time.

    A run that renews both assessments posts twice, and a stand-in that gave
    both the same stamp would make a time-filtered poll unable to tell the
    second from the first. The stand-in has no clock, so the stamp is derived
    from the facts; the property that has to hold is not that it equals the
    instant of the POST but that it strictly increases with each post.
    """
    first = invoke(run, "api", COMMENT_ROUTE, "-f", "body=first", token=POOL_TOKEN)
    assert first.returncode == 0, first.stderr
    second = invoke(run, "api", COMMENT_ROUTE, "-f", "body=second", token=POOL_TOKEN)
    assert second.returncode == 0, second.stderr
    earlier = json.loads(first.stdout)["created_at"]
    later = json.loads(second.stdout)["created_at"]
    assert earlier, "the first post was served without a created_at"
    assert later, "the second post was served without a created_at"
    assert later > earlier, (
        f"the second post is stamped {later}, not later than the first at "
        f"{earlier}, so two posts in one run share a stamp"
    )


#: The finding a test records for a `finding` mode. The stand-in has no
#: built-in text, so every scenario that asks for a finding must record one.
TEST_FINDING = (
    "skills/pr-babysitting/scripts/readiness_gate.py\n"
    "  🚩 New issue: Large Method\n"
    "     Function: _assess_gate at line 7\n"
)


def write_mode(directory: Path, mode: str) -> None:
    """Record the local CodeScene mode the run should answer with.

    A `finding` mode also records the finding text. The stand-in refuses to
    invent one, because a built-in description would name a file the scenario
    may not serve — the incoherence the recorded-finding rule exists to stop.
    """
    facts: dict[str, object] = {"cs_mode": mode}
    if mode == "finding":
        facts["cs_finding"] = TEST_FINDING
    (directory / "facts.json").write_text(json.dumps(facts), encoding="utf-8")


def test_the_simulated_cs_discloses_itself_on_every_answer(cs_run: Path) -> None:
    """No answer can be mistaken for a real CodeScene analysis.

    The stand-in fabricates its output, so a recording that quoted it without
    the disclosure would be evidence for a result no service produced.
    """
    write_mode(cs_run, "clean")
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    assert "simulated output for rehearsal" in done.stderr, "expected 'simulated output for rehearsal' in done.stderr"
    assert "not a CodeScene analysis" in done.stderr, "expected 'not a CodeScene analysis' in done.stderr"


def test_a_finding_mode_without_a_recorded_finding_is_refused(cs_run: Path) -> None:
    """The stand-in may not invent a finding the scenario never recorded.

    A built-in description names a path and a line count, so serving it would
    report a defect in code this scenario does not contain. That is the same
    incoherence as a stale served stub, reached by a different path: the run
    would hold on evidence that does not describe its own candidate.
    """
    (cs_run / "facts.json").write_text(
        json.dumps({"cs_mode": "finding"}), encoding="utf-8"
    )
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    assert done.returncode == 2, done.stdout
    assert "record none" in done.stderr, done.stderr
    assert "New issue" not in done.stdout, "the stand-in served an invented finding"


def test_every_recorded_finding_scenario_records_its_finding() -> None:
    """A recorded scenario that answers with a finding must carry its text.

    The stand-in now refuses instead of inventing, so a scenario that answered
    a finding from a built-in default would fail at the boundary. This is the
    fixture-side check: no recorded `finding` scenario may rely on that.
    """
    checked = 0
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        if facts.get("cs_mode") != "finding":
            continue
        checked += 1
        assert isinstance(facts.get("cs_finding"), str) and facts["cs_finding"], (
            f"{facts_path.parent.name} requests a finding but records none"
        )
    assert checked, "no scenario exercises a recorded finding"


def invoke_cs(directory: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run the simulated `cs` with one invocation."""
    return subprocess.run(
        [str(directory / "cs"), *argv], capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    ("mode", "needle", "status"),
    [
        ("clean", "No issues found in checked changes.", 0),
        ("finding", "New issue: Large Method", 0),
        ("unavailable", "License check failed", 1),
    ],
    ids=["clean", "finding", "unavailable"],
)
def test_the_simulated_cs_answers_each_mode_in_the_cli_shape(
    cs_run: Path, mode: str, needle: str, status: int
) -> None:
    """Each mode answers as `cs delta` would, including its exit status.

    The unavailable case is the one that matters most: the real binary exits
    non-zero when it cannot reach its licence service, and a run that read only
    stdout would take a failed check for a clean one.
    """
    write_mode(cs_run, mode)
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    assert done.returncode == status, "expected done.returncode to equal status"
    assert needle in done.stdout, "expected needle in done.stdout to hold"


#: A sentinel for the case whose facts file must not be decodable as UTF-8. The
#: parametrization carries it as text so one test can cover every unusable
#: facts file, and the body writes raw bytes when it sees this value.
NON_UTF8_FACTS = "non-utf8-facts-sentinel"


@pytest.mark.parametrize(
    "setup",
    [
        None,
        "not json",
        json.dumps([]),
        json.dumps({"cs_mode": "invented"}),
        NON_UTF8_FACTS,
    ],
    ids=["no-facts", "malformed", "not-an-object", "unknown-mode", "undecodable"],
)
def test_the_simulated_cs_fails_closed_without_a_usable_mode(
    cs_run: Path, setup: str | None
) -> None:
    """No usable mode yields an unevaluable answer, never a clean one.

    The two cases are answered differently on purpose, and both are refusals:

    * A facts file that was never served — missing, malformed, undecodable, or
      not an object — is a fixture fault. The stand-in cannot say the licence
      check failed, because no recorded fact establishes that the CLI was
      present at all. It exits 3 with its own diagnostic, and nothing reaches
      the trace. The undecodable case is here because `UnicodeDecodeError` is a
      `ValueError` rather than an `OSError`: without its own clause it escaped
      the fault boundary and exited 1, which is the `unavailable` answer, so a
      run could not tell an unreadable fixture from a real licence failure.
    * A served file whose mode is unknown is an `unavailable` answer: the facts
      exist and record something this scenario cannot evaluate, which is the
      situation the real CLI reports with a non-zero licence failure.

    Defaulting either to `clean` would let a broken fixture manufacture the
    clearance the rehearsal exists to check.
    """
    if setup is not None:
        (cs_run / "facts.json").write_text(setup, encoding="utf-8")
    if setup == NON_UTF8_FACTS:
        # Bytes, not text: this case exists to make `read_text` fail to decode,
        # which `write_text(encoding="utf-8")` cannot express.
        (cs_run / "facts.json").write_bytes(b"\xff\xfe{\x00}\x00")
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    if setup != json.dumps({"cs_mode": "invented"}):
        assert done.returncode == 3, done.stdout
        assert "fixture fault" in done.stderr, done.stderr
        assert "not a CodeScene result" in done.stderr, done.stderr
        assert "License check failed" not in done.stdout, (
            "a fixture fault was reported as a licence failure"
        )
        assert not (cs_run / "cs-trace.jsonl").exists(), (
            "a fixture fault was recorded as a local CodeScene answer"
        )
    else:
        assert done.returncode == 1, done.stdout
        assert "License check failed" in done.stdout, done.stdout


def test_the_simulated_cs_records_each_invocation(cs_run: Path) -> None:
    """The trace is how a recording shows the local gate was consulted at all."""
    write_mode(cs_run, "clean")
    invoke_cs(cs_run, "delta", "base", "HEAD")
    entries = [
        json.loads(line)
        for line in (cs_run / "cs-trace.jsonl").read_text().splitlines()
    ]
    assert entries == [{"argv": ["delta", "base", "HEAD"], "mode": "clean"}]


RUNNER = FIXTURES / "sandboxed_run.sh"


def probe_body(marker: str) -> str:
    """Return the Python the runner runs from the heredoc named `marker`.

    Extracting the body rather than reimplementing it means a negative control
    exercises the bytes the runner actually executes. Copying the logic into
    the test would let the two drift, and the test would then prove something
    about the test.
    """
    text = RUNNER.read_text()
    opening = f"<<'{marker}'\n"
    start = text.index(opening) + len(opening)
    end = text.index(f"\n{marker}\n", start)
    return text[start:end]


def run_probe(marker: str, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run one of the runner's Python probes over the given arguments."""
    return subprocess.run(
        ["python3", "-", *argv],
        input=probe_body(marker),
        capture_output=True,
        text=True,
        check=False,
    )


def write_lines(path: Path, entries: list[object]) -> Path:
    """Write one JSON document per line, as the trace and answer files are."""
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path


READY_INVOCATION = ["pr", "ready", "272", "--repo", "leynos/agent-helper-scripts"]

FLAGGED = "skills/pr-babysitting/scripts/readiness_gate.py"
FINDING_SCENARIO = FIXTURES / "scenarios" / "local-codescene-finding" / "facts.json"


def served_files(facts: dict) -> dict[str, str]:
    """Return every file body the recorded API surface serves, by path.

    The routes are recorded as patterns, so the served path is the reliable key:
    matching the pattern text would tie the test to one spelling of a route.
    """
    served: dict[str, str] = {}
    for value in facts["api"].values():
        if isinstance(value, dict) and "content" in value and "path" in value:
            served[str(value["path"])] = str(value["content"])
    return served


def test_the_recorded_local_finding_is_true_of_the_recorded_file() -> None:
    """The simulated `cs` may not report what the recorded file contradicts.

    A local finding is evidence only if it describes the code this candidate
    serves. Claiming a Large Method for a function the fixture shows at a third
    of the stated size produces a run that holds because the evidence does not
    cohere, not because the rule fired — the scenario would pass while proving
    nothing.
    """
    facts = json.loads(FINDING_SCENARIO.read_text(encoding="utf-8"))
    finding = facts["cs_finding"]
    assert finding, "the finding scenario records no local finding"
    served = served_files(facts)
    assert FLAGGED in served, "the finding names a file the surface does not serve"
    lines = served[FLAGGED].splitlines()
    start = next(
        index
        for index, line in enumerate(lines, 1)
        if line.startswith("def _assess_gate")
    )
    # The real CLI reports a function's body, excluding its signature. Captured
    # from `cs delta` on this stub: a function at line 10 of a 97-line file is
    # reported as 87 lines, and the scenario must quote that same count.
    reported = len(lines) - start
    assert f"at line {start}" in finding, finding
    assert f"has {reported} lines" in finding, finding
    assert "threshold = 70" in finding, "the threshold must be CodeScene's own"


def test_the_local_finding_names_a_file_the_candidate_changes() -> None:
    """A finding about code outside the diff is evidence about another PR.

    The run would be reasoning about a file this candidate never touched, so
    the hold it produces would not be about this change.
    """
    facts = json.loads(FINDING_SCENARIO.read_text(encoding="utf-8"))
    changed = facts["pr_diff"].split()
    assert FLAGGED in changed, f"{FLAGGED} is not in the recorded diff: {changed}"


CODESCENE_ADVISORY = FIXTURES / "scenarios" / "codescene-advisory" / "facts.json"


def test_the_two_sources_describe_the_same_finding() -> None:
    """The hosted check and the local delta must not disagree about one file.

    A scenario that records a hosted warning beside a locally clean result
    manufactures a contradiction the skill does not describe. The run then
    holds on the mismatch rather than on the rule, and the recording stops
    showing whether the rule fires.
    """
    facts = json.loads(CODESCENE_ADVISORY.read_text(encoding="utf-8"))
    assert facts["cs_mode"] == "finding", "a hosted finding needs a local one"
    local = facts["cs_finding"]
    annotations = facts["api"]["/check-runs/\\d+/annotations(?:[?#]|$)"]
    hosted = " ".join(str(entry["message"]) for entry in annotations)
    # Both sources quote the real CLI's metrics for the served stub, so a
    # drift in either number shows up here rather than in a re-record.
    for number in ("87 lines", "threshold = 70"):
        assert number in local, local
        assert number in hosted, hosted


def test_every_served_stub_matches_the_data_file_it_came_from() -> None:
    """The stub is generated into the facts, so it can go stale.

    While the text was a literal in the generator, the served body and the
    finding measured against it could not disagree. Reading it from a data file
    separates them: editing the file without regenerating leaves every
    `facts.json` serving the old text, and the finding then describes a
    function the fixture no longer serves.
    """
    stub = (FIXTURES / "flagged_gate_stub.txt").read_text(encoding="utf-8")
    served_routes = 0
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        for path, body in served_files(facts).items():
            if not path.startswith("skills/"):
                continue
            served_routes += 1
            assert body == stub, (
                f"{facts_path.parent.name} serves a stale {path};"
                " regenerate with `python3 -I make_scenarios.py`"
            )
    assert served_routes, "no scenario serves the flagged stub, so nothing was checked"


def test_the_hosted_summary_agrees_with_the_hosted_annotations() -> None:
    """One analysis has one set of numbers, on every route that serves it.

    The check's summary and its annotations are two readings of a single
    CodeScene run. A handwritten summary drifted from the annotations, and the
    run then stopped to reconcile a mismatch that was a fixture defect rather
    than a fact about the candidate.
    """
    facts = json.loads(CODESCENE_ADVISORY.read_text(encoding="utf-8"))
    scene = next(
        check
        for check in facts["pr"]["statusCheckRollup"]
        if "CodeScene" in str(check["name"])
    )
    summary = str(scene["output"]["summary"])
    annotations = facts["api"]["/check-runs/\\d+/annotations(?:[?#]|$)"]
    for entry in annotations:
        assert str(entry["message"]) in summary, (
            f"the summary omits or contradicts an annotation: {entry['message']}"
        )
    assert "complexity of 12" not in summary, "the summary carries a stale metric"


def test_every_recorded_scenario_declares_a_local_codescene_mode() -> None:
    """A run cannot answer the local gate from facts that never name a mode.

    The stand-in fails closed to `unavailable`, so a scenario that forgot the
    key would record a hold for a reason it does not describe.
    """
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        assert facts.get("cs_mode") in {"clean", "finding", "unavailable"}, (
            f"{facts_path.parent.name} declares no usable local CodeScene mode"
        )


def test_the_runner_checks_the_read_back_after_the_transition() -> None:
    """The read-back assertion must be ordered, or it proves nothing.

    An initial `pr view` also carries `isDraft`, so a bare search of the whole
    trace passes even when the post-transition read is removed. The runner has
    to examine only what follows the last `pr ready`.
    """
    runner = RUNNER.read_text()
    assert "grep -n '\"pr\", \"ready\"'" in runner, (
        "the read-back must locate the transition rather than search the trace"
    )
    assert 'tail -n "+$((after + 1))"' in runner, (
        "the read-back must be searched only after the transition"
    )


def test_the_runner_requires_the_served_state_to_read_ready() -> None:
    """Ordering is not the whole claim: the answer must be ready, not a draft.

    The trace records argv, so the read-back above shows the state was asked
    for. A run whose post-transition read returned `"isDraft": true` would
    satisfy it while showing the opposite of the transition claimed. The stand-in
    serves from `state.json`, so the runner checks the value it served.
    """
    runner = RUNNER.read_text()
    assert 'state.get("isDraft") is False' in runner, (
        "the read-back must check the served value, not only that it was read"
    )
    assert "the served state still reads draft" in runner, "expected 'the served state still reads draft' in runner"


def test_the_runner_requires_the_local_codescene_result_before_readiness() -> None:
    """A permitting run that never invoked `cs` has waived the local gate.

    The rule says an unevaluable source is not a clear one, so the runner has to
    fail a run that marked ready without consulting the local result at all.
    """
    runner = RUNNER.read_text()
    assert '[ "$EXPECT_READY" = yes ] && [ ! -s "$CS_TRACE" ]' in runner, "expected '[ \"$EXPECT_READY\" = yes ] && [ ! -s \"$CS_TRACE\" ]' in runner to hold"
    assert "marked the PR ready without invoking the local CodeScene check" in runner, "expected 'marked the PR ready without invoking the local CodeScene check' in runner"


def test_the_runner_requires_the_plan_read_before_the_transition() -> None:
    """The revision is reconciled against the plan file, so the read comes first.

    Accepting the verdict's own echo would clear a revision the reviewer never
    saw, which is the superseded-revision defect the rule exists to prevent.
    """
    runner = RUNNER.read_text()
    assert 'grep -nF "contents/$plan_path?" "$TRACE"' in runner, (
        "the shell-level ordering check no longer names the approved path, or "
        "no longer asks grep for line numbers"
    )
    assert "read the plan after the transition, not before it" in runner


def plan_line_command() -> str:
    """Return the shell command the runner uses to locate the plan read.

    Extracted from the runner rather than restated, so the control below runs
    the bytes that actually execute.
    """
    for line in RUNNER.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("plan_line=$(grep"):
            return stripped[len("plan_line=$(") : -1]
    raise AssertionError("the runner has no plan_line command")


def run_plan_line(trace_text: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the runner's own `plan_line` command over a constructed trace."""
    trace = tmp_path / "trace.jsonl"
    trace.write_text(trace_text, encoding="utf-8")
    return subprocess.run(
        [
            "bash",
            "-c",
            plan_line_command(),
            "plan_line",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "TRACE": str(trace),
            "plan_path": "docs/execplans/issue-271-readiness-handoff.md",
        },
        check=False,
    )


def test_the_shell_level_ordering_check_yields_a_line_number(
    tmp_path: Path,
) -> None:
    """`plan_line` has to be a number, or the ordering comparison decides nothing.

    The check compares `plan_line` against `ready_line` with `-gt`. Without
    `grep -n` the variable holds the matched trace line — the JSON array the
    stand-in recorded — and the comparison fails with `integer expression
    expected` while the surrounding `if` reports only its own branch. The run
    then passes the ordering check without ever having made it.

    Running the command rather than matching its text is what catches that:
    the flag is present or absent, and only the output says which variable the
    rest of the script receives.
    """
    trace = "".join(
        json.dumps(argv) + "\n"
        for argv in (
            ["pr", "view", "272", "--json", "isDraft"],
            [
                "api",
                "repos/leynos/agent-helper-scripts/contents/"
                "docs/execplans/issue-271-readiness-handoff.md?ref=4444eeee",
            ],
            ["pr", "ready", "272"],
        )
    )
    done = run_plan_line(trace, tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "2", (
        f"expected the plan read's line number, got {done.stdout.strip()!r}"
    )


def test_the_ordering_check_yields_nothing_without_a_plan_read(
    tmp_path: Path,
) -> None:
    """An empty value is what makes the missing-read branch fire.

    The runner treats an empty `plan_line` as "the plan was never read" and
    aborts. A command that matched the directory listing, or a bare
    `contents/docs/execplans` route, would hand that branch a line number and
    report a read that never happened.
    """
    trace = "".join(
        json.dumps(argv) + "\n"
        for argv in (
            [
                "api",
                "repos/leynos/agent-helper-scripts/contents/docs/execplans",
            ],
            [
                "api",
                "repos/leynos/agent-helper-scripts/contents/"
                "docs/execplans/issue-271-readiness-handoff.md.bak?ref=4444eeee",
            ],
            ["pr", "ready", "272"],
        )
    )
    done = run_plan_line(trace, tmp_path)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "", (
        f"a non-read produced a line number: {done.stdout.strip()!r}"
    )


def test_every_route_counts_the_files_the_diff_names() -> None:
    """One PR has one file list, on every route that reports its size.

    `changed_files` is what a run compares the delivered diff against. A
    hard-coded 1 contradicted the file-list route for the two scenarios that
    change two paths, and a careful run held on the fixture's own disagreement
    rather than on the rule under test.
    """
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        named = len(facts["pr_diff"].split())
        # Two routes report the size: the bare `pulls/N` object and the
        # `pr view --json files` list. Both must agree with the diff.
        pull = facts["api"][r"/pulls/\d+$"]
        assert pull["changed_files"] == named, (
            f"{facts_path.parent.name} reports {pull['changed_files']} "
            f"changed files but its diff names {named}"
        )
        served = facts["pr"]["files"]
        assert len(served) == named, (
            f"{facts_path.parent.name} serves {len(served)} files for a diff of {named}"
        )


def test_every_route_serving_the_commit_gives_the_same_message() -> None:
    """`pr view`, `pulls/N/commits` and `commits/<sha>` describe one commit.

    Two texts for one head read as two commits, and a run counting commits to
    see whether a reviewed head is still the tip would then be comparing
    against a message the PR never carried.
    """
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        view = facts["pr"]["commits"][0]["messageHeadline"]
        pulls = facts["api"][r"/pulls/\d+/commits(?:[?#]|$)"][0]["commit"]["message"]
        single = facts["api"][commit_object_route(facts)]["commit"]["message"]
        assert view == pulls == single, (
            f"{facts_path.parent.name} gives three messages for one head: "
            f"{view!r}, {pulls!r}, {single!r}"
        )


def commit_object_route(facts: dict) -> str:
    """Return the `commits/<sha>` route key for this scenario's own head.

    The route is pinned to the head rather than matching any hex SHA, so the
    key carries that SHA instead of a character class. Looking the key up by a
    fixed literal would only find a fixture that still answers any commit.
    """
    head = facts["pr"]["headRefOid"]
    route = rf"/commits/{head}$"
    assert route in facts["api"], (
        f"the commit route is not pinned to the head: found"
        f" {[key for key in facts['api'] if 'commits' in key]}"
    )
    return route


def test_every_commit_route_answers_only_its_own_head() -> None:
    """A route keyed on any SHA answers about a commit the fixture never saw.

    A run that checks commit identity would then be handed this head's
    metadata for whatever SHA it asked about, which is false evidence rather
    than a 404. The three head-derived routes are pinned together because the
    defect was one of a kind, not one instance.
    """
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        head = facts["pr"]["headRefOid"]
        commit_routes = [key for key in facts["api"] if "/commits/" in key]
        assert commit_routes, f"{facts_path.parent.name} records no commit routes"
        for route in commit_routes:
            assert head in route, (
                f"{facts_path.parent.name} answers any commit at {route!r}"
            )


def test_the_runner_requires_the_plan_read_at_the_candidate_head() -> None:
    """Reading the plan at any ref is not reading the revision in force.

    `?ref=main` serves the base branch's copy of the plan, so a run that read
    it and found a revision would be reconciling the verdict's echo against a
    file from outside the candidate. The check must name the head. An earlier
    version selected the line with `grep '...ref='` and then re-tested it for
    `ref=`, which can never fail; this asserts the replacement distinguishes a
    candidate read from one at the base.
    """
    runner = RUNNER.read_text()
    assert "PROBE_PLAN" in runner, "expected 'PROBE_PLAN' in runner"
    assert "did not read the plan at the head it is judging" in runner, "expected 'did not read the plan at the head it is judging' in runner"
    assert "candidate_refs" in runner, "expected 'candidate_refs' in runner"
    # The head is what makes a read candidate-bound, so the probe has to name
    # it rather than accept whatever ref the trace carries.
    assert 'pr.get("headRefOid", "")' in runner


#: The approved plan's own route. The probe binds a read to this path, so a
#: literal that differed from the recorded `plan_path` would make every case
#: here refuse for the wrong reason — including the permitting one that exists
#: to show the probe is not simply rejecting everything.
PLAN_ROUTE = (
    "repos/leynos/agent-helper-scripts/contents/"
    + json.loads(SCENARIO.read_text(encoding="utf-8"))["plan_path"]
)

#: Another ExecPlan in the same directory. A read of it is not a read of the
#: approved file, and the fixture route does not serve it.
OTHER_PLAN_ROUTE = "repos/leynos/agent-helper-scripts/contents/docs/execplans/271-plan.md"


def plan_read(ref: str, route: str = PLAN_ROUTE) -> list[str]:
    """Return the argv of a plan read at one ref."""
    return ["api", "-H", "Accept: application/vnd.github.raw", f"{route}?ref={ref}"]


#: What a revision-bearing plan read returns. The plan file is the surface that
#: states the revision in force, so a successful read of it is only usable
#: evidence when the text names one.
PLAN_TEXT = "# Readiness handoff\n\nPlan revision: rev-7\n"


def answer(argv: list[str], status: int = 0, stdout: str = PLAN_TEXT) -> dict:
    """Return one line of the stand-in's answer record.

    The default text states a revision because the recorded plan file does, and
    a probe that cannot tell those apart would accept a read that established
    nothing. Cases that need a different text pass one.
    """
    return {"argv": argv, "status": status, "stdout": stdout}


@pytest.fixture
def whole_plan(tmp_path: Path) -> Path:
    """Return the recorded facts for the scenario that reconciles a plan."""
    facts = tmp_path / "facts.json"
    facts.write_text(SCENARIO.read_text(encoding="utf-8"), encoding="utf-8")
    return facts


def test_the_plan_probe_accepts_a_candidate_read_before_the_transition(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The probe must pass the recording it was written for, or it proves nothing.

    Without this the negative controls below would pass against a probe that
    refuses everything, which is a broken gate reported as a strict one.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl",
        [plan_read("cccc3333"), READY_INVOCATION, plan_read("cccc3333")],
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [
            answer(plan_read("cccc3333")),
            answer(READY_INVOCATION, 0, ""),
            answer(plan_read("cccc3333")),
        ],
    )
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode == 0, done.stderr


def test_the_plan_probe_refuses_a_base_read_then_a_candidate_read(
    tmp_path: Path, whole_plan: Path
) -> None:
    """Two reads, each satisfying one condition, are not one satisfying both.

    A read at `main` before the transition and one at the head after it passed
    an earlier pair of checks: the plan read came first, and the candidate was
    read. They were about different files, so the revision the decision used
    was never the revision the check compared.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl",
        [plan_read("main"), READY_INVOCATION, plan_read("cccc3333")],
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [
            answer(plan_read("main")),
            answer(READY_INVOCATION, 0, ""),
            answer(plan_read("cccc3333")),
        ],
    )
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode != 0, "a base read was accepted as the candidate's plan"
    assert "no usable candidate-bound plan read before the transition" in done.stderr, (
        "expected 'no usable candidate-bound plan read before the transition'"
        f" in done.stderr: {done.stderr}"
    )


def test_the_plan_probe_refuses_a_candidate_read_that_failed(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The trace records an attempt; a 404 is not the text the revision was read from.

    The read is candidate-bound and precedes the decision, so the ordering
    check alone would accept it. The answer record is what separates a read the
    agent could reconcile from one that returned an error.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333"), 1, ""), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode != 0, "a failed candidate read was accepted"
    assert "candidate-bound plan read failed" in done.stderr, "expected 'candidate-bound plan read failed' in done.stderr"


def test_the_plan_probe_keeps_scanning_after_a_failed_candidate_read(
    tmp_path: Path, whole_plan: Path
) -> None:
    """A failed read must not mask a later one that succeeded.

    The rule is that one usable read satisfies it. Exiting on the first
    candidate-bound attempt whether or not it worked reported a run as having
    never read the plan, when it had read the plan on the retry. That abort
    discards a costly rehearsal for a fault the run had already recovered from.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl",
        [plan_read("cccc3333"), plan_read("cccc3333"), READY_INVOCATION],
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [
            answer(plan_read("cccc3333"), 1, ""),
            answer(plan_read("cccc3333")),
            answer(READY_INVOCATION, 0, ""),
        ],
    )
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode == 0, (
        "a failed read followed by a successful one was still refused:"
        f" {done.stderr}"
    )


def test_the_plan_probe_refuses_a_candidate_read_that_returned_nothing(
    tmp_path: Path, whole_plan: Path
) -> None:
    """A zero exit with an empty body is not a revision either.

    The stand-in answers an unrecorded ref with an empty 200 in some routes, so
    the status alone does not establish that there was a plan to compare.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333"), 0, ""), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode != 0, "an empty candidate read was accepted"
    assert "candidate-bound plan read returned nothing" in done.stderr, "expected 'candidate-bound plan read returned nothing' in done.stderr"


def test_the_plan_probe_refuses_a_candidate_read_that_names_no_revision(
    tmp_path: Path, whole_plan: Path
) -> None:
    """A successful read of some text is not a read of the revision in force.

    The probe exists to tie the verdict to the revision the plan file states.
    Text that never states one leaves nothing to reconcile, and accepting it
    would record the read as evidence for a binding the run could not have
    made. The two shapes here are what a 200 carries when the route answers
    something other than the plan. An empty body is refused earlier, by the
    "returned nothing" clause, and has its own test above.
    """
    for served in ("# Readiness handoff\n", "{}\n", "no revision here\n"):
        trace = write_lines(
            tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
        )
        answers = write_lines(
            tmp_path / "answers.jsonl",
            [
                answer(plan_read("cccc3333"), 0, served),
                answer(READY_INVOCATION, 0, ""),
            ],
        )
        done = run_probe(
            "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
        )
        assert done.returncode != 0, f"a revision-less read was accepted: {served!r}"
        assert "names no plan revision" in done.stderr, (
            f"a revision-less read was refused for another reason: {done.stderr}"
        )


def test_the_plan_probe_refuses_a_read_of_another_revision(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The read must carry the revision in force, not merely a revision.

    The check previously required only that a revision was named, so a read of
    any file stating any revision cleared a rule whose subject is the revision
    the plan route serves. A run that read a stale copy of the plan would then
    be recorded as having established the current one.
    """
    served = "# Readiness handoff\n\nPlan revision: rev-6\n"
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333"), 0, served), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes")
    assert done.returncode != 0, "a read of another revision was accepted"
    assert "not the 'rev-7' the route serves" in done.stderr, done.stderr


def test_the_plan_probe_reads_the_revision_out_of_a_contents_payload(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The recorded answer is the route's JSON, not the file's bare text.

    The stand-in returns the GitHub contents payload, so the revision sits
    inside `content` next to the file's metadata. A probe that searched only the
    raw envelope would find no revision in a perfectly good read, and refusing
    it would fail every rehearsal for a defect in the check.
    """
    served = json.dumps(
        {
            "name": "issue-271-readiness-handoff.md",
            "path": json.loads(SCENARIO.read_text(encoding="utf-8"))["plan_path"],
            "encoding": "utf-8",
            "content": PLAN_TEXT,
        }
    )
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333"), 0, served), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes")
    assert done.returncode == 0, done.stderr


def test_the_plan_probe_refuses_a_read_of_another_execplan(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The approved plan is named. A sibling ExecPlan is not it.

    The route and the probe both accepted any file below `execplans/`, so a
    run that asked for another plan and was served the approved payload
    cleared a check whose subject is the revision in force in the approved
    file. Its revision would then have been reconciled against a file it never
    asked for, which is the claim the check is supposed to make false.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl",
        [plan_read("cccc3333", OTHER_PLAN_ROUTE), READY_INVOCATION],
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [
            answer(plan_read("cccc3333", OTHER_PLAN_ROUTE)),
            answer(READY_INVOCATION, 0, ""),
        ],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes")
    assert done.returncode != 0, "a read of another ExecPlan was accepted"
    assert "no usable candidate-bound plan read" in done.stderr, done.stderr


def test_the_plan_probe_refuses_an_answer_naming_another_path(
    tmp_path: Path, whole_plan: Path
) -> None:
    """The request and the answer are two different claims.

    The trace shows the approved path was asked for; the answer says which file
    was served. A route that answered the request with another file's metadata
    would pass on the request alone, and the revision read would then be the
    wrong file's. The name is checked when the answer carries one.
    """
    served = json.dumps(
        {
            "name": "271-plan.md",
            "path": "docs/execplans/271-plan.md",
            "encoding": "utf-8",
            "content": PLAN_TEXT,
        }
    )
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333"), 0, served), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes")
    assert done.returncode != 0, "an answer naming another file was accepted"
    assert "not the approved" in done.stderr, done.stderr


def test_a_scenario_without_a_named_plan_path_is_refused(tmp_path: Path) -> None:
    """The approved path is the premise the read is judged against.

    A fixture that names none leaves nothing to bind the read to, and a probe
    that skipped the binding there would accept any `execplans/` read in
    exactly the scenarios whose premise was edited last. It is refused instead.
    """
    facts = json.loads(SCENARIO.read_text(encoding="utf-8"))
    del facts["plan_path"]
    bare = tmp_path / "facts.json"
    bare.write_text(json.dumps(facts), encoding="utf-8")
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333")), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(bare), "yes")
    assert done.returncode != 0, "a scenario naming no approved path was accepted"
    assert "names no approved plan path" in done.stderr, done.stderr


def test_the_plan_probe_names_the_revision_the_route_serves(
    tmp_path: Path,
) -> None:
    """A premise that states no revision is refused rather than assumed.

    Reading the expected revision from the facts is what makes the comparison
    possible. A premise whose plan route states none leaves nothing to compare
    against, and a probe that silently skipped the comparison would accept every
    read — the gap this rule closes, reintroduced through the facts.
    """
    facts = json.loads(SCENARIO.read_text(encoding="utf-8"))
    route = (
        "repos/leynos/agent-helper-scripts/contents/" + facts["plan_path"]
    )
    for pattern, payload in facts["api"].items():
        if re.search(pattern, route) and isinstance(payload, dict):
            payload["content"] = "# Readiness handoff\n"
    bare = tmp_path / "facts.json"
    bare.write_text(json.dumps(facts), encoding="utf-8")
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(plan_read("cccc3333")), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(bare), "yes")
    assert done.returncode != 0, "a revision-less premise was accepted"
    assert "expected exactly one revision to reconcile against" in done.stderr, done.stderr


def test_the_plan_probe_refuses_an_answer_record_that_disagrees(
    tmp_path: Path, whole_plan: Path
) -> None:
    """Indexed pairing assumes both files hold the same invocations.

    A truncated answer record would line its entries up against the wrong argv,
    so a failure would be attributed to a call that succeeded. Refusing the
    mismatch is what keeps the index a pairing rather than a guess.
    """
    trace = write_lines(
        tmp_path / "trace.jsonl", [plan_read("cccc3333"), READY_INVOCATION]
    )
    answers = write_lines(tmp_path / "answers.jsonl", [answer(plan_read("cccc3333"))])
    done = run_probe(
        "PROBE_PLAN", str(trace), str(answers), str(whole_plan), "yes"
    )
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "disagree in length" in done.stderr, "expected 'disagree in length' in done.stderr"


def proof_read(ref: str, path: str = "proofs/refinement/Theorem.lean") -> list[str]:
    """Return the argv of a read of the assessed proof at one ref."""
    return [
        "api",
        "-H",
        "Accept: application/vnd.github.raw",
        f"repos/leynos/agent-helper-scripts/contents/{path}?ref={ref}",
    ]


#: What a usable read of the assessed proof returns. The probe requires the
#: whole served text: the assessed subject is the theorem *and* the body that
#: discharges it, so the two are written here exactly as the route serves them.
PROOF_TEXT = (
    "theorem refinement_sound :\n"
    "  forall (s : State), refine s = s → sound s := by\n"
    "  intro s h\n"
    "  exact sound_of_refine s h\n"
)

#: The declaration header alone. The route's first line, and what a filtered
#: read reduced to the theorem statement returns. It carries no discharge, so
#: it is not a read of the proof the assessment is about.
PROOF_HEADER = "theorem refinement_sound :\n"

#: The shipped assessment template, read rather than copied. Every placeholder
#: the controls use is extracted from this text, so a template edit reaches the
#: controls instead of leaving them asserting against a wording the skill no
#: longer sends. An earlier revision hard-coded the strings and drifted: it
#: checked `<evidential limits only>`, a fragment the template's own line does
#: not contain, so a request carrying the whole unfilled template passed.
TEMPLATE = (
    FIXTURES.parent.parent.parent / "skills" / "pr-babysitting" / "references"
    / "execplan-assessment.md"
)


def template_field(label: str) -> str:
    """Return the value the shipped template gives one labelled field.

    The field runs to the end of its line. A template that stops naming the
    field raises here rather than letting a control substitute an empty string
    that the probe would accept, which is the drift this extraction prevents.
    """
    stated = re.search(rf"^{re.escape(label)}:[^\n]*", TEMPLATE.read_text(encoding="utf-8"), re.MULTILINE)
    assert stated, f"the shipped template no longer names {label!r}"
    return stated.group(0).removeprefix(f"{label}:").strip()


#: The `Known limitations:` placeholder exactly as the shipped template prints
#: it. A shorter fragment is not a substring of this text, which is how an
#: earlier control came to pass on a request that carried the whole unfilled
#: template: it searched for `<evidential limits only>` alone, and the template
#: continues past that phrase. The control substitutes the extracted value, so
#: it exercises the placeholder a real run would actually leave in place.
LIMITATIONS_PLACEHOLDER = template_field("Known limitations")



@pytest.fixture
def combined_facts(tmp_path: Path) -> Path:
    """Return the recorded facts for the combined scenario, which has a proof."""
    source = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
    facts = tmp_path / "facts.json"
    facts.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return facts


def proof_answer(argv: list[str], status: int = 0, stdout: str = PROOF_TEXT) -> dict:
    """Return one answer-record line for a proof read."""
    return {"argv": argv, "status": status, "stdout": stdout}


def test_the_proof_read_probe_accepts_a_candidate_read_before_the_transition(
    tmp_path: Path, combined_facts: Path
) -> None:
    """The probe must pass the read it was written for, or it proves nothing.

    Without this, the controls below would pass against a probe that refuses
    everything, which is a broken gate reported as a strict one.
    """
    reads = [proof_read("3333dddd")]
    trace = write_lines(
        tmp_path / "trace.jsonl",
        [*reads, READY_INVOCATION],
    )
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0]), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode == 0, done.stderr


def test_the_proof_read_probe_refuses_a_read_of_another_ref(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A read of some other ref is not the read that judged this candidate.

    The first version of this check searched the trace for any proof route with
    a `ref`, so a read of the base branch satisfied it and the claim that the
    run inspected the proof at head was never tested.
    """
    reads = [proof_read("main")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0]), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a read at another ref was accepted"
    assert "no usable candidate-bound proof read" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_a_read_of_another_proof(
    tmp_path: Path, combined_facts: Path
) -> None:
    """The assessed subject is named. A neighbouring proof file is not it.

    The route is served by a wildcard, so a probe that accepted any
    `contents/proofs/` read would clear a run that inspected a different file
    than the one its verdict covers.
    """
    reads = [proof_read("3333dddd", "proofs/refinement/Other.lean")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0]), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a read of another proof file was accepted"
    assert "no usable candidate-bound proof read" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_a_failed_read(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A read the agent could not use is not the read it judged.

    The trace records the attempt whether or not it succeeded, so accepting the
    route alone would clear a run whose proof read was a 404.
    """
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0], 1, ""), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a failed proof read was accepted"
    assert "candidate-bound proof read failed" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_an_empty_read(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A 200 with no text established nothing about the proof."""
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0], 0, ""), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "an empty proof read was accepted"
    assert "returned nothing" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_a_read_after_the_transition(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A read after `pr ready` cannot have informed the decision.

    The permitting run clears the candidate and then reads the proof; the
    verdict was reached on something else.
    """
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [READY_INVOCATION, *reads])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(READY_INVOCATION, 0, ""), proof_answer(reads[0])],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a proof read after the transition was accepted"
    assert "no usable candidate-bound proof read" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_a_metadata_only_answer(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A hash is not the theorem.

    `--jq .sha` exits zero and prints the file's hash, which is what a run
    that located the route without reading it produces. Accepting any
    non-empty answer made that indistinguishable from a read of the proof, and
    the clear verdict it was evidence for would rest on the route having been
    named rather than the theorem having been seen.
    """
    sha = json.loads(
        (
            FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
        ).read_text(encoding="utf-8")
    )
    metadata = next(
        str(payload["sha"])
        for pattern, payload in sha["api"].items()
        if "proofs" in pattern and isinstance(payload, dict)
    )
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0], 0, metadata), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a hash-only proof read was accepted"
    assert "does not carry the assessed proof" in done.stderr, done.stderr


def test_the_proof_read_probe_refuses_a_declaration_only_answer(
    tmp_path: Path, combined_facts: Path
) -> None:
    """The header is not the proof either.

    Anchoring on `theorem <name> :` admitted the file's first line on its own,
    so an answer that showed the statement and stopped — a filtered read, or a
    `--jq .content` reduced to one line — passed a check whose subject is the
    discharge as much as the claim. The body is now required, and this control
    supplies the exact header the file starts with.
    """
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0], 0, PROOF_HEADER), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a declaration-only proof read was accepted"
    assert "does not carry the assessed proof" in done.stderr, done.stderr


def test_the_proof_read_probe_reads_the_proof_out_of_a_contents_payload(
    tmp_path: Path, combined_facts: Path
) -> None:
    """A wrapped answer is the file's text inside its metadata.

    The stand-in normally serves the bare text, and a run that asks for the
    contents payload receives `content` instead. Both are a read of the proof,
    so both are accepted; only an answer carrying neither is refused.
    """
    served = json.dumps(
        {
            "name": "Theorem.lean",
            "path": "proofs/refinement/Theorem.lean",
            "encoding": "utf-8",
            "content": PROOF_TEXT,
        }
    )
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", [*reads, READY_INVOCATION])
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [proof_answer(reads[0], 0, served), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode == 0, done.stderr


def test_the_proof_read_probe_refuses_a_holding_run(
    tmp_path: Path, combined_facts: Path
) -> None:
    """This check is scoped to the run that transitions, and says so.

    A holding run has no transition to order a read against; applying the arm
    to one would abort it for having nothing to order, which is the defect the
    plan-read arm already had to correct.
    """
    reads = [proof_read("3333dddd")]
    trace = write_lines(tmp_path / "trace.jsonl", reads)
    answers = write_lines(tmp_path / "answers.jsonl", [proof_answer(reads[0])])
    done = run_probe(
        "PROBE_PROOF_READ", str(trace), str(answers), str(combined_facts)
    )
    assert done.returncode != 0, "a run with no transition was accepted"
    assert "no transition to order the proof read against" in done.stderr, (
        done.stderr
    )


READ_BACK = ["pr", "view", "272", "--repo", "leynos/agent-helper-scripts",
             "--json", "isDraft,headRefOid,baseRefOid"]


def read_back_answer(status: int = 0, stdout: str = '{"isDraft": false}') -> dict:
    """Return an answer record for the post-transition read-back."""
    return answer(READ_BACK, status, stdout)


def test_the_read_back_probe_accepts_the_recorded_shapes(tmp_path: Path) -> None:
    """Every shape a run may legitimately print reads as the same observation.

    The real client prints the object, `--jq .isDraft` prints `false`, and a
    template prints `false <ref>`. Refusing any of them would fail a run that
    observed the transition, so each must be accepted before the refusals below
    can mean anything.
    """
    for stdout in ('{"isDraft": false, "headRefOid": "c"}', "false", "false cccc3333"):
        answers = write_lines(
            tmp_path / "answers.jsonl",
            [answer(READY_INVOCATION, 0, ""), read_back_answer(stdout=stdout)],
        )
        done = run_probe("PROBE_READBACK", str(answers))
        assert done.returncode == 0, f"{stdout!r} was refused: {done.stderr}"


def test_the_read_back_probe_refuses_a_read_before_the_transition(tmp_path: Path) -> None:
    """Only the reads after the decision observe it.

    An initial `pr view` carries `isDraft` too, so a probe that scanned the
    whole record would pass on a draft state read before `pr ready` was ever
    called.
    """
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [read_back_answer(), answer(READY_INVOCATION, 0, "")],
    )
    done = run_probe("PROBE_READBACK", str(answers))
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "no isDraft read after the transition" in done.stderr, "expected 'no isDraft read after the transition' in done.stderr"


def test_the_read_back_probe_refuses_a_filtered_null(tmp_path: Path) -> None:
    """`--jq 'null'` exits zero and prints nothing usable.

    The exit status says the call was answered; the value says what it
    answered. A read-back judged on the status alone passes here while showing
    the agent nothing about the draft state.
    """
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [
            answer(READY_INVOCATION, 0, ""),
            read_back_answer(stdout="null"),
        ],
    )
    done = run_probe("PROBE_READBACK", str(answers))
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "no read-back returned a ready state" in done.stderr, "expected 'no read-back returned a ready state' in done.stderr"


@pytest.mark.parametrize(
    "stdout",
    ['{"isDraft": true}', "true", '"ready"', "", "falsey"],
    ids=["object-true", "filtered-true", "wrong-string", "empty", "truncated"],
)
def test_the_read_back_probe_refuses_every_not_ready_value(
    tmp_path: Path, stdout: str
) -> None:
    """A value that does not state the ready state is not the observation.

    Each shape here exits zero. Accepting any of them would let a run whose
    read-back showed a draft, a string, or nothing at all count as having
    observed the transition.
    """
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(READY_INVOCATION, 0, ""), read_back_answer(stdout=stdout)],
    )
    done = run_probe("PROBE_READBACK", str(answers))
    assert done.returncode != 0, f"{stdout!r} was accepted as a ready read-back"


def test_the_read_back_probe_refuses_a_failed_read(tmp_path: Path) -> None:
    """A failed read-back is not an observation, whatever it printed.

    The value check alone would pass on a body the client printed while
    exiting non-zero, which is not a read the agent could rely on.
    """
    answers = write_lines(
        tmp_path / "answers.jsonl",
        [answer(READY_INVOCATION, 0, ""), read_back_answer(status=1)],
    )
    done = run_probe("PROBE_READBACK", str(answers))
    assert done.returncode != 0, "expected done.returncode not to equal 0"
    assert "failed" in done.stderr, "expected 'failed' in done.stderr"


def test_the_preflight_refuses_a_wrong_token_after_an_accepted_post(
    tmp_path: Path,
) -> None:
    """The preflight's own POST control has to start from a recorded comment.

    The two preflight POSTs prove a token is refused and the fixture token is
    accepted, but the refusal ran against an empty record: a stand-in that
    wrote the comment before checking the credential passed both and would
    have overwritten an accepted comment in the real run. The probe is
    exercised here against the state a wrong-token POST leaves behind.
    """
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"isDraft": True, "posted": [{"id": 1, "body": "probe"}]}),
        encoding="utf-8",
    )
    kept = run_probe("PROBE_AUTHZ", str(state))
    assert kept.returncode == 0, kept.stderr
    state.write_text(
        json.dumps({"isDraft": True, "posted": [{"id": 1, "body": "injected"}]}),
        encoding="utf-8",
    )
    overwritten = run_probe("PROBE_AUTHZ", str(state))
    assert overwritten.returncode != 0, "a rewritten comment was accepted as refused"
    assert "changed the recorded comments" in overwritten.stderr, "expected 'changed the recorded comments' in overwritten.stderr"


def cs_entry(argv: list[str]) -> dict:
    """Return one line of the `cs` trace, in the shape the stand-in writes."""
    return {"argv": argv, "mode": "clean"}


CS_BOUNDARY = {"event": "pr-ready", "head": "cccc3333"}


@pytest.fixture
def recorded_facts(tmp_path: Path) -> Path:
    """Return the recorded facts whose base and head the delta must name."""
    facts = tmp_path / "facts.json"
    facts.write_text(SCENARIO.read_text(encoding="utf-8"), encoding="utf-8")
    return facts


@pytest.mark.parametrize(
    "separators",
    [(None, None), (",", ":")],
    ids=["default-separators", "compact-separators"],
)
def test_the_delta_probe_reads_the_boundary_from_parsed_entries(
    tmp_path: Path, recorded_facts: Path, separators: tuple
) -> None:
    """The boundary is found by its parsed event, not by its file text.

    The runner used to locate it with `grep '"event": "pr-ready"'`, which
    agrees with `json.dumps` defaults only. Under compact separators the same
    trace has no line matching that pattern, so the probe would report a run
    that never transitioned. Reading parsed entries makes the check independent
    of how the stand-in happens to serialize its line.
    """
    trace = tmp_path / "cs-trace.jsonl"
    facts = json.loads(recorded_facts.read_text(encoding="utf-8"))
    base, head = facts["pr"]["baseRefOid"], facts["pr"]["headRefOid"]
    entries = [cs_entry(["delta", base, head]), CS_BOUNDARY]
    kwargs = {} if separators == (None, None) else {"separators": separators}
    trace.write_text(
        "".join(json.dumps(entry, **kwargs) + "\n" for entry in entries),
        encoding="utf-8",
    )
    if separators == (",", ":"):
        assert '"event": "pr-ready"' not in trace.read_text(encoding="utf-8"), (
            "the compact trace still matches the old grep, so this case is vacuous"
        )
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip() == "yes", done.stdout


def test_the_delta_probe_counts_the_boundary_rather_than_searching_for_it(
    tmp_path: Path, recorded_facts: Path
) -> None:
    """No boundary and two boundaries are distinct refusals, both from the probe.

    The shell used two `grep` calls to tell these apart. Counting parsed
    entries makes the distinction part of what the probe decides, so the
    shell's messages report a value instead of re-reading the file.
    """
    facts = json.loads(recorded_facts.read_text(encoding="utf-8"))
    base, head = facts["pr"]["baseRefOid"], facts["pr"]["headRefOid"]
    delta = cs_entry(["delta", base, head])

    none_trace = write_lines(tmp_path / "none.jsonl", [delta])
    none_done = run_probe("PROBE_DELTA", str(none_trace), str(recorded_facts))
    assert none_done.returncode != 0
    assert none_done.stdout.strip() == "boundaries=0", none_done.stdout

    two_trace = write_lines(tmp_path / "two.jsonl", [delta, CS_BOUNDARY, CS_BOUNDARY])
    two_done = run_probe("PROBE_DELTA", str(two_trace), str(recorded_facts))
    assert two_done.returncode != 0
    assert two_done.stdout.strip() == "boundaries=2", two_done.stdout


def test_the_delta_probe_accepts_a_candidate_bound_delta_before_the_boundary(
    tmp_path: Path, recorded_facts: Path
) -> None:
    """The probe must pass the recording it was written for.

    Without an accepting case the refusal tests below would pass against a
    probe that rejects everything, which is a broken check reported as a strict
    one.
    """
    trace = write_lines(
        tmp_path / "cs-trace.jsonl",
        [
            cs_entry(["delta", "73d32981c7b7e8f52590a074873e28a9f369f0f9", "cccc3333"]),
            CS_BOUNDARY,
        ],
    )
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "yes", done.stdout


def test_the_delta_probe_refuses_a_missing_delta(
    tmp_path: Path, recorded_facts: Path
) -> None:
    """A run that marked the PR ready without any local delta is refused.

    The local CodeScene result is a documented prerequisite, so a transition
    with no candidate-bound `cs delta` before it has skipped the gate.
    """
    trace = write_lines(tmp_path / "cs-trace.jsonl", [CS_BOUNDARY])
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode != 0, "a transition with no local delta was accepted"
    assert done.stdout.strip() == "no", done.stdout


def test_the_delta_probe_refuses_a_delta_after_the_boundary(
    tmp_path: Path, recorded_facts: Path
) -> None:
    """A delta read after the transition cannot justify it.

    Ordering is the whole claim: the same call recorded on the wrong side of
    the boundary is a check performed after the decision it was supposed to
    inform.
    """
    trace = write_lines(
        tmp_path / "cs-trace.jsonl",
        [
            CS_BOUNDARY,
            cs_entry(["delta", "73d32981c7b7e8f52590a074873e28a9f369f0f9", "cccc3333"]),
        ],
    )
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode != 0, "a delta read after the transition was accepted"
    assert done.stdout.strip() == "no", done.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["delta"],
        ["delta", "cccc3333"],
        ["delta", "73d32981c7b7e8f52590a074873e28a9f369f0f9", "eeee5555"],
    ],
    ids=["bare", "head-only", "wrong-head"],
)
def test_the_delta_probe_requires_both_endpoints(
    tmp_path: Path, recorded_facts: Path, argv: list[str]
) -> None:
    """A delta is candidate-bound only when its argv names both endpoints.

    A bare `cs delta` reads the working tree, which this sandbox does not have,
    and a delta naming another head is about another candidate. Both are
    consultations that cannot clear the gate, so neither counts as the one the
    decision rests on.
    """
    trace = write_lines(tmp_path / "cs-trace.jsonl", [cs_entry(argv), CS_BOUNDARY])
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode != 0, done.stdout
    assert done.stdout.strip() == "no", done.stdout


def test_the_delta_probe_refuses_a_malformed_trace_line(
    tmp_path: Path, recorded_facts: Path
) -> None:
    """An unreadable trace is not a clean one.

    A truncated or corrupt line could be the delta itself, so treating it as
    absent and carrying on would accept a recording whose evidence the probe
    never actually read.
    """
    trace = tmp_path / "cs-trace.jsonl"
    trace.write_text("{not json}\n", encoding="utf-8")
    done = run_probe("PROBE_DELTA", str(trace), str(recorded_facts))
    assert done.returncode == 2, done.stdout
    assert "malformed trace line" in done.stderr, done.stderr


def test_the_state_probe_accepts_a_ready_served_state(tmp_path: Path) -> None:
    """The probe passes the state a completed transition actually serves."""
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"isDraft": False}), encoding="utf-8")
    done = run_probe("PROBE_STATE", str(state))
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"isDraft": True}),
        json.dumps({}),
        json.dumps({"isDraft": None}),
        json.dumps({"isDraft": "false"}),
        json.dumps({"draft": False}),
        json.dumps({"isDraft": 0}),
    ],
    ids=["draft", "absent", "null", "string-false", "other-key", "zero"],
)
def test_the_state_probe_refuses_anything_but_a_ready_boolean(
    tmp_path: Path, content: str
) -> None:
    """Only the boolean `false` is the served ready state.

    `isDraft is False` is a value check, not a truthiness check: a missing key
    yields None and a string or zero is not the boolean the service sends. Each
    of those would otherwise read as "not draft" and hide a transition that
    never happened.
    """
    state = tmp_path / "state.json"
    state.write_text(content, encoding="utf-8")
    done = run_probe("PROBE_STATE", str(state))
    assert done.returncode != 0, f"accepted {content} as a ready served state"


def _enclosing_branch(runner: str, offset: int) -> int:
    """Return the offset of the column-zero `fi` closing the branch at ``offset``.

    A shell branch opened at column zero is closed by the first `fi` at column
    zero after it; deeper `fi` lines close nested blocks. Tracking that alone is
    enough here: the runner's permitting branches hold no nested `if` whose
    terminator sits at column zero.
    """
    closing = re.compile(r"^fi$", re.MULTILINE).search(runner, offset)
    assert closing, "the branch containing this probe is never closed"
    return closing.end()


def test_the_runner_reaches_the_delta_and_state_checks() -> None:
    """A probe that is correct but never wired in proves nothing.

    Executing an extracted heredoc tests the probe's logic; it does not show
    the runner calls it, nor that the call is guarded by the permitting branch.
    Both checks are delinquent only for a run expected to transition, so each
    probe and its own refusal must sit *inside* the branch that opens on
    `EXPECT_READY = yes` — not merely somewhere later in the file, which a
    probe moved past the closing `fi` would also satisfy.

    The probe and its refusal must share *one* permitting branch, not merely
    be enclosed by permitting branches of their own. Two independent
    containment tests let a refusal moved into a different permitting branch
    pass: the probe is still called, and the message still fails the run, but
    it fails for the wrong reason and at the wrong point.
    """
    runner = RUNNER.read_text()
    guards = [m for m in re.finditer(r'^if .*EXPECT_READY.*= yes.*then$', runner, re.MULTILINE)]
    assert guards, "the runner no longer opens a permitting branch"
    for probe, message in (
        (
            "PROBE_DELTA",
            "marked ready without a candidate-bound 'cs delta' before the transition",
        ),
        ("PROBE_STATE", "transitioned but the served state still reads draft"),
    ):
        invocation = runner.index(f"<<'{probe}'")
        # The refusal must be the one this probe's failure emits, and the `rc=1`
        # that turns it into a failing run must be the line directly after it.
        # Searching the whole script for the text finds some other check's
        # message, and searching the tail for any `rc=1` finds a later block's,
        # so neither ties the failure to this probe.
        # The search runs on a slice, so its offsets are relative to
        # `invocation`; rebasing is what makes the containment test below
        # compare the refusal against the guard's absolute position.
        refusal = re.search(
            re.escape(message) + r"[^\n]*\n\s*rc=1", runner[invocation:]
        )
        assert refusal, f"{probe}'s refusal no longer sets rc=1 directly"
        refusal_at = invocation + refusal.start()
        # One branch must hold both ends. Checking them against the guard list
        # separately would accept a probe in one permitting branch and its
        # refusal in another.
        enclosing = [
            guard
            for guard in guards
            if guard.start() < invocation < _enclosing_branch(runner, guard.start())
        ]
        assert enclosing, f"{probe} is not invoked inside a permitting branch"
        assert any(
            refusal_at < _enclosing_branch(runner, guard.start())
            for guard in enclosing
        ), (
            f"{probe}'s refusal sits outside the permitting branch that invokes"
            " the probe"
        )


def test_the_combined_scenario_is_held_to_every_permitting_check() -> None:
    """The combined case transitions, so every permitting check must reach it.

    A scenario listed as permitting but left out of the plan-read branch, the
    delta check, or the read-back would be filed as a recording of the combined
    gate while proving less than the plan-only case does. Each of those checks
    is selected by scenario name, so a new name is exactly what silently
    escapes them.
    """
    runner = RUNNER.read_text()
    # The permitting list is what sets EXPECT_READY for the outcome assertions.
    # It is a case arm naming the scenarios, so the arm's own pattern is what
    # has to carry the new name.
    permitting = re.search(
        r"^case \$SCENARIO in\n(?P<arm>.*?)\)\n\s+EXPECT_READY=yes",
        runner,
        re.DOTALL | re.MULTILINE,
    )
    assert permitting, "the runner's permitting list is no longer recognizable"
    assert "combined-plan-and-proof" in permitting.group("arm"), (
        "the combined scenario is not permitted, so its transition would fail"
    )
    # The plan-read probe is gated by its own scenario case, so the combined
    # case needs a name there too: without it the transition is accepted with
    # no evidence that the revision was reconciled against the plan file.
    # The arm is bounded by `esac`, so the match cannot run back into an
    # earlier scenario case and pick its names up. Without that bound the
    # search spans from the first `case $SCENARIO in` in the file and the
    # assertion passes whatever the plan-read branch actually says.
    plan_branch = re.search(
        r"case \$SCENARIO in\n(?P<names>(?:(?!esac).)*?)\)\n(?:\s*#[^\n]*\n)*\s*plan_line=",
        runner,
        re.DOTALL,
    )
    assert plan_branch, "the plan-read branch is no longer recognizable"
    assert "combined-plan-and-proof" in plan_branch.group("names"), (
        "the combined scenario transitions without the plan-read check"
    )


def test_a_holding_combined_case_is_held_to_the_plan_read_it_claims() -> None:
    """A holding combined case decided by the plan file must have read it.

    Three of the six exist because a verdict is unusable as given for a reason
    the plan file records: a stale plan revision (in both verdicts, or in the
    proof verdict alone) or an unbound one. Every one of those grounds is
    established from the plan file, so a run that held without reading the plan
    would be filed as evidence for a rule it never applied.

    The other three are decided by the state of the proof verdict alone, and are
    asserted to be OUT of this arm: a pending verdict cannot clear at any
    revision, and a clear verdict assessed against a head that is not this
    candidate's is disqualified by the assessed head itself. Requiring the read
    there would demand evidence those decisions do not rest on. The last two
    share that premise, so admitting one and not the other would make the check
    a property of how a run investigated rather than of what its hold rests on.
    """
    runner = RUNNER.read_text()
    plan_branch = re.search(
        r"case \$SCENARIO in\n(?P<names>(?:(?!esac).)*?)\)\n(?:\s*#[^\n]*\n)*\s*plan_line=",
        runner,
        re.DOTALL,
    )
    assert plan_branch, "the plan-read branch is no longer recognizable"
    for name in (
        "combined-proof-stale-plan-revision",
        "combined-proof-stale-revision",
        "combined-proof-unbound-revision",
    ):
        assert name in plan_branch.group("names"), (
            f"{name} holds without being held to the plan read, so its hold"
            " could be for a reason the scenario does not name"
        )
    for name in (
        "combined-proof-pending",
        "combined-proof-stale-verdict",
        "combined-proof-candidate-mismatch",
    ):
        assert name not in plan_branch.group("names"), (
            f"{name} is held to a plan read its verdict's state does not depend"
            " on, which would demand evidence the decision never rests on"
        )


def test_the_plan_probe_accepts_a_holding_run() -> None:
    """The plan probe must run for a hold, which has no transition to order by.

    The probe originally required a `pr ready` to order the plan read against.
    A holding run issues none, so extending the plan-read arm to the holding
    combined cases without this would abort every one of them at the probe
    rather than recording the hold. The requirement still applies to a
    permitting run, or a permitting rehearsal could be recorded with its plan
    read after the transition.
    """
    runner = RUNNER.read_text()
    assert 'if ready is None and expect_ready != "no":' in runner, (
        "the plan probe no longer distinguishes a holding run's missing"
        " transition from a permitting run's"
    )
    assert "if ready is None:\n    ready = len(trace)" in runner, (
        "a holding run's plan read is not ordered against the end of its trace"
    )
    assert '"$EXPECT_READY" <<\'PROBE_PLAN\'' in runner, (
        "the plan probe is not given the expectation it now branches on"
    )


def test_a_holding_combined_case_asserts_the_defect_it_demonstrates() -> None:
    """Each holding combined case must still record the defect it names.

    The premise is a property of the facts, not of the recording. If a later
    edit moved the plan file back to the revision the replies echo, or gave the
    unbound proof reply a revision, or pointed the mismatch at the real head,
    the run would hold on nothing and still be filed under the scenario's name.
    """
    runner = RUNNER.read_text()
    # The heredoc marker is on the `if ! python3` line, so the match must not
    # run past it: a lax `.*?` would skip over the intervening `esac` and bind
    # whichever earlier case arm happened to precede the premise probe.
    premise = re.search(
        r"case \$SCENARIO in\n(?P<names>(?:(?!esac).)*?)\)\n\s+if ! python3"
        r"[^\n]*<<'PROBE_PREMISE'",
        runner,
    )
    assert premise, "the premise assertion is no longer recognizable"
    for name in (
        "combined-proof-pending",
        "combined-proof-stale-verdict",
        "combined-proof-stale-plan-revision",
        "combined-proof-stale-revision",
        "combined-proof-unbound-revision",
        "combined-proof-candidate-mismatch",
    ):
        assert name in premise.group("names"), f"{name} is not held to its premise"


def test_each_holding_combined_premise_holds_for_its_recorded_facts(
    tmp_path: Path,
) -> None:
    """The premise probe accepts every recorded holding case as it stands.

    Reading the scenario names out of the runner shows the case is wired to a
    check; it does not show the check passes for the facts the recording was
    made from. Running the probe over each case's committed `facts.json` does,
    which is what makes "held for the named reason" a property of the evidence
    rather than of the script.
    """
    runner = RUNNER.read_text()
    body = re.search(
        r"case \$SCENARIO in\n(?P<names>(?:(?!esac).)*?)\)\n\s+if ! python3"
        r"[^\n]*<<'PROBE_PREMISE'\n(?P<probe>.*?)\nPROBE_PREMISE\n",
        runner,
        re.DOTALL,
    )
    assert body, "the premise assertion is no longer recognizable"
    probe = tmp_path / "premise.py"
    probe.write_text(body.group("probe"), encoding="utf-8")
    names = [
        name.strip()
        for name in body.group("names").replace("\n", " ").split("|")
        if name.strip()
    ]
    assert len(names) == 6, f"the premise arm holds {len(names)} cases, expected 6"
    for name in names:
        facts = FIXTURES / "scenarios" / name / "facts.json"
        done = subprocess.run(
            [sys.executable, str(probe), name, str(facts)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, (
            f"{name} no longer records the defect it exists to demonstrate: "
            f"{done.stderr.strip()}"
        )


def test_a_holding_proof_case_isolates_the_proof_assessment() -> None:
    """The isolated cases must break the proof side only.

    `combined-proof-stale-revision` has both verdicts stale, so its hold does
    not show which assessment held it. The pending, stale-verdict and
    stale-plan-revision cases exist to close that gap; each is only meaningful
    if the completeness reply really is clear and current.
    """
    runner = RUNNER.read_text()
    body = re.search(
        r"<<'PROBE_PREMISE'\n(?P<probe>.*?)\nPROBE_PREMISE\n", runner, re.DOTALL
    )
    assert body, "the premise probe is no longer recognizable"
    probe = body.group("probe")
    for name in (
        "combined-proof-pending",
        "combined-proof-stale-verdict",
        "combined-proof-stale-plan-revision",
    ):
        assert f'name == "{name}"' in probe, (
            f"the premise probe no longer distinguishes {name}"
        )
    for needed in (
        "the proof reply does not record a pending verdict",
        "the completeness reply is not clear",
        "the proof verdict assesses the PR's current head",
        "the proof reply echoes the revision in force",
    ):
        assert needed in probe, f"the premise probe no longer asserts {needed!r}"


#: The runs whose committed answer records hold `{argv, status}` and no
#: `stdout`, because they were captured before the stand-in recorded the text it
#: printed. They are listed rather than tolerated silently: a new recording that
#: lost `stdout` is a regression, while these five are a known, stated limit of
#: evidence gathered earlier. Removing a name here means the file gained
#: `stdout`, which is an improvement.
ANSWERS_WITHOUT_STDOUT = frozenset({
    "codescene-advisory.jsonl",
    "local-codescene-finding.jsonl",
    "local-codescene-unavailable.jsonl",
    "proof-only-pending.jsonl",
    "subset-clear.jsonl",
})


def test_every_committed_answer_record_belongs_to_a_committed_trace() -> None:
    """An answer record is only evidence beside the trace it was produced with.

    The record holds the status and, for the later runs, the stdout of each
    invocation, which the argv trace cannot show. Committing one from a
    different run would answer a trace that is not beside it, so the pairing is
    asserted rather than trusted.
    """
    answers = sorted((FIXTURES / "answers").glob("*.jsonl"))
    assert answers, "no committed answer records"
    for path in answers:
        trace = FIXTURES / "traces" / path.name
        assert trace.exists(), f"{path.name} has no committed trace beside it"
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        trace_argv = [
            json.loads(line)
            for line in trace.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == len(trace_argv), (
            f"{path.name} records {len(records)} answers for {len(trace_argv)}"
            " invocations, so one of them is from a different run"
        )
        for index, record in enumerate(records):
            assert record["argv"] == trace_argv[index], (
                f"{path.name} answers invocation {index} with a different argv"
                " from the trace's, so the two are not the same run"
            )
        # A record without `stdout` can show that a call ran and how it exited,
        # but not what the agent received. The five files that lack it are named
        # rather than skipped, so the set cannot grow unnoticed: a new recording
        # that loses the field fails here, and a listed file that gains it fails
        # too, prompting its removal from the list.
        carrying = any("stdout" in record for record in records)
        listed = path.name in ANSWERS_WITHOUT_STDOUT
        assert carrying is not listed, (
            f"{path.name} {'carries' if carrying else 'lacks'} a stdout field"
            f" but is {'named' if listed else 'not named'} in"
            " ANSWERS_WITHOUT_STDOUT, so the list and the committed records"
            " disagree about what this answer record evidences"
        )


#: What a live service answer or a pasted request header looks like. Kept
#: module-level so the guard below and the test of its failure message read
#: one pattern rather than two that could drift apart.
CREDENTIAL = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{16,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|(?i:authorization)\s*:\s*\S+"
    r"|(?i:bearer)\s+[A-Za-z0-9._-]{16,})"
)

#: How much of a match the message test treats as a leak in its own right. The
#: full match being absent says nothing about a truncated copy, and a prefix is
#: as identifying as the token it was cut from.
PREFIX_CHARS = 12


def credential_failure(name: str, found: re.Match[str]) -> str:
    """Compose the failure message for a credential-shaped match.

    The message names the file and the byte offset and withholds the match
    itself. CI logs are published, so quoting even a prefix of a real token
    would copy part of the very secret this test exists to keep out of the
    repository; the file and offset are enough to locate it by hand.

    It is a function of its arguments, and separate from the test that uses it,
    so the withholding can be checked directly: an assertion's own rewritten
    report is a second channel the message cannot control.

    Parameters
    ----------
    name : str
        The file the match was found in, named so a reader can open it.
    found : re.Match of str
        The credential-shaped match to report without quoting.

    Returns
    -------
    str
        A message naming the file and the offset, with the matched text
        withheld.
    """
    return (
        f"{name} carries something credential-shaped at offset"
        f" {found.start()}; the match is withheld from this output"
    )


def test_a_committed_answer_record_carries_no_credential() -> None:
    """A committed record holds fixture answers, never a credential.

    The stand-in answers from `facts.json`, and the sandbox hands it only the
    fixture pool token, so nothing here should look like a secret. The check is
    a guard on future recordings: committing a real answer record by mistake
    would publish whatever the live service returned.

    The failure is raised through `pytest.fail(..., pytrace=False)` rather than
    an `assert`. At the pinned pytest 9.1.1, assertion rewriting appends
    `assert not <re.Match ... match='...'>` and a locals line to the report, so
    a bare `assert` would print the matched text however carefully its message
    withheld it. A traceback-free failure prints the message alone, which is
    what makes the withholding hold under `--showlocals` too.
    """
    for path in sorted((FIXTURES / "answers").glob("*.jsonl")):
        text = path.read_text(encoding="utf-8")
        found = CREDENTIAL.search(text)
        if found:
            pytest.fail(credential_failure(path.name, found), pytrace=False)


def test_the_credential_failure_message_withholds_the_match() -> None:
    """The failure report cannot be the place a committed secret escapes.

    The guard above only ever reports a match it found in a committed record,
    so its message is read exactly when there is a real secret in the tree. A
    message that quoted the match, or any prefix of it, would then publish part
    of that secret to every reader of the CI log. Both halves matter: the
    offset has to survive, because it is what locates the match by hand once
    the text itself is withheld.
    """
    found = CREDENTIAL.search(
        "token ghp_0123456789abcdefghij reserved for this test only"
    )
    assert found is not None, "the pattern no longer matches a shaped token"
    message = credential_failure("answers/example.jsonl", found)
    assert found.group(0) not in message, (
        "the failure message quotes the match it is reporting:"
        f" {message!r}"
    )
    # A prefix is a leak too, and the full-match assertion cannot see one: a
    # message that truncated the match would pass it while publishing the part
    # of a real token that identifies it. Twelve characters covers the
    # distinguishing stem of every pattern above.
    prefix = found.group(0)[:PREFIX_CHARS]
    assert prefix not in message, (
        f"the failure message quotes the first {PREFIX_CHARS} characters of the"
        f" match it is reporting: {message!r}"
    )
    assert str(found.start()) in message, (
        f"the failure message drops the offset that locates the match: {message!r}"
    )


def test_the_assignment_names_the_stand_in_as_the_local_source() -> None:
    """The prompt must not leave the stand-in's identity as the variable.

    An earlier prompt said nothing about `cs`, and the stand-in discloses that
    it is simulated. Two runs of the same scenario then diverged: one accepted
    the clean result and transitioned, the other read the disclosure as "the
    local source is unverified" and stayed in draft. The disclosure is honest
    and must stay, so the prompt says which source this environment means —
    without saying what it answered, which is the variable under test.
    """
    runner = RUNNER.read_text()
    assert "stand-in for the local CodeScene check" in runner, "expected 'stand-in for the local CodeScene check' in runner"
    assert "Treat its answer as the local result for this" in runner, "expected 'Treat its answer as the local result for this' in runner"
    for answer in ("No issues found", "License check failed", "New issue"):
        assert answer not in runner, (
            "the prompt must not reveal which local result the run will get"
        )


def test_a_permitting_scenario_cannot_carry_an_unusable_local_mode() -> None:
    """A scenario written to permit cannot carry a finding or unavailable mode.

    Recording that pairing would file, as evidence, a run whose facts
    contradict the decision the runner is checking for.
    """
    runner = RUNNER.read_text()
    for mode in ("unavailable", "finding"):
        assert f'"$CS_MODE" = {mode}' in runner, "expected f'\"$CS_MODE\" = {mode}' in runner to hold"


PERMITTING = ("current-whole-plan", "proof-only-cleared", "combined-plan-and-proof")


def _scenario_names() -> tuple[str, ...]:
    """Return every scenario the fixture serves, in a stable order."""
    return tuple(
        path.parent.name
        for path in sorted(FIXTURES.glob("scenarios/*/facts.json"))
    )


#: Every scenario, because the request text is a premise for a holding run as
#: much as for a permitting one: a hold has to rest on the defect the case
#: names, not on a question that contradicts itself.
ALL_SCENARIOS = _scenario_names()


def facts_with_bodies(facts: dict, mutate: object) -> dict:
    """Return `facts` with each discussion body passed through `mutate`."""
    changed = json.loads(json.dumps(facts))
    for entry in changed["api"][r"/issues/\d+/comments"]:
        entry["body"] = mutate(entry["body"])
    return changed


SUBMITTED = FIXTURES / "submitted"

#: Every recorded posted body, one file per posting run. These are the requests
#: a run actually composed, so they are the closest thing the fixture has to a
#: question the skill sends without the fixture having written it first.
RECORDED_REQUESTS = tuple(sorted(SUBMITTED.glob("*.txt")))


def recorded_posts(path: Path) -> list[str]:
    """Return each comment body a recorded `submitted/` file holds, in order.

    The runner writes one bare body for a single-post run and a
    `--- posted comment N of M ---` header before each body when a run posted
    more than once, so the separator is what splits them. Splitting on the
    header keeps a body that merely mentions "posted comment" intact.
    """
    parts = re.split(
        r"^--- posted comment \d+ of \d+ ---\n",
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    return [part.rstrip("\n") for part in parts if part.strip()]


def request_state(tmp_path: Path, bodies: list[str]) -> Path:
    """Write the state a run that posted `bodies` leaves behind, and return it.

    The probe reads the run's persisted `posted` comments from this file in the
    shape the `gh` stand-in writes it, so a control here exercises the same
    path the runner does after a real run.
    """
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "isDraft": False,
                "posted": [
                    {"id": index, "body": body}
                    for index, body in enumerate(bodies, start=1)
                ],
            }
        ),
        encoding="utf-8",
    )
    return state


@pytest.mark.parametrize("name", ALL_SCENARIOS)
def test_each_scenario_seeds_the_question_the_skill_posts(
    name: str, tmp_path: Path
) -> None:
    """No run may be filed against a question the skill would not actually send.

    The seeded question is a premise rather than a recording, so it is the one
    part of the fixture that can be corrected. What it must not be is a
    shorthand: a request naming a revision but not the plan file's blob SHA, or
    carrying the template's own placeholder for `Known limitations`, is a
    question the skill does not post. A run that cleared it would then be
    evidence about a question nobody asked `—` and the recordings made from it
    would inherit that, because a recording is verbatim and cannot be edited
    afterwards.

    Every scenario is checked, not only the permitting three. The runner applies
    the probe to the runs it expects to transition, because for those a bad
    question changes the verdict. A holding run is evidence too, and its
    question has to be one the skill would send for the same reason: the six
    holding `combined-*` cases all ask a proof question while their sibling
    completeness request claimed no proof was affected, and a run reading both
    held on that contradiction rather than on the defect the case exists to
    demonstrate. The probe was right about that and simply never reached them.
    """
    facts = json.loads(
        (FIXTURES / "scenarios" / name / "facts.json").read_text(encoding="utf-8")
    )
    state = tmp_path / "state.json"
    done = run_probe(
        "PROBE_REQUESTS",
        str(FIXTURES / "scenarios" / name / "facts.json"),
        str(state),
        name,
    )
    if facts.get("scripted_replies"):
        # This case seeds no question on purpose, so the runner has nothing to
        # check until a run posts one. What it does check is that the exemption
        # is not silence: with no run behind it, the probe refuses, and the
        # refusal names the scenario. The request a real run posts is covered
        # by `test_each_recorded_request_passes_the_checks_the_runner_applies`.
        assert done.returncode != 0, f"{name} seeded no question and was accepted"
        assert (
            f"{name}: scripts an answer but the run posted no assessment question"
            in done.stderr
        ), done.stderr
        return
    assert done.returncode == 0, f"{name} seeds an incomplete question: {done.stderr}"
    assert facts["api"][r"/issues/\d+/comments"], f"{name} records no discussion"


@pytest.mark.parametrize("path", RECORDED_REQUESTS, ids=lambda path: path.stem)
def test_each_recorded_request_passes_the_checks_the_runner_applies(
    path: Path, tmp_path: Path
) -> None:
    """A run's own request is held to the template, and the recorded ones pass.

    The probe applies the same field checks to the comments a run posted that
    it applies to the question a scenario seeded, because the request a run
    composes is exactly where a missing field would go unnoticed: the
    recording beside it is written from the same body, so it cannot contradict
    it. The bodies under `submitted/` are those requests, verbatim.

    `posted-then-answered` is the case this check exists for. Its scenario
    seeds no question at all, so before the probe read the run's own posts
    there was nothing to check there, and the one request the whole case turns
    on went unexamined.

    The first form of this check was too strict about wording rather than
    content: it matched `blob SHA at this head: <sha>` and so refused the
    recorded `posted-then-answered` request, which cites the same value as
    `plan file blob <sha> at this head`. The template asks for the blob, not
    for a sentence, so the probe now reads the SHA from the request's
    `Plan revision:` line.
    """
    name = path.stem
    facts = FIXTURES / "scenarios" / name / "facts.json"
    assert facts.exists(), f"{name} has a recorded post but no scenario"
    state = request_state(tmp_path, recorded_posts(path))
    done = run_probe("PROBE_REQUESTS", str(facts), str(state), name)
    assert done.returncode == 0, f"{name} posted an incomplete request: {done.stderr}"


def test_a_recorded_request_missing_a_field_is_refused_on_its_own_post(
    tmp_path: Path,
) -> None:
    """The posted-body check refuses a defect that is only in the run's post.

    `superseded-revision` seeds a complete question and its run posted a
    second, follow-up one. That makes it the case where a defect in the posted
    body cannot be blamed on the seed: the seeded request still passes, so a
    probe that only checked the premise would accept the run. Each control
    damages one field of the posted body alone and requires the probe to name
    it.
    """
    facts = FIXTURES / "scenarios" / "superseded-revision" / "facts.json"
    body = recorded_posts(SUBMITTED / "superseded-revision.txt")[0]

    def without_blob(text: str) -> str:
        """Drop the cited SHA, leaving the revision with no blob beside it."""
        return re.sub(r"Plan revision:[^\n]*", "Plan revision: rev-7.", text)

    def with_a_placeholder(text: str) -> str:
        """Leave `Known limitations:` holding the template's placeholder."""
        return re.sub(
            r"Known limitations:[^\n]*",
            "Known limitations: " + LIMITATIONS_PLACEHOLDER,
            text,
        )

    def with_an_unserved_blob(text: str) -> str:
        """Cite a blob the scenario's head never served."""
        return re.sub(r"[0-9a-f]{40}", "0" * 40, text)

    for mutate, expected in (
        (without_blob, "states no plan file blob SHA"),
        (with_a_placeholder, "leaves the limitations placeholder unfilled"),
        (with_an_unserved_blob, "but this head serves"),
    ):
        posted = mutate(body)
        assert posted != body, "the control did not change the recorded request"
        state = request_state(tmp_path, [posted])
        done = run_probe(
            "PROBE_REQUESTS", str(facts), str(state), "superseded-revision"
        )
        assert done.returncode != 0, f"a posted request {expected} was accepted"
        assert expected in done.stderr, done.stderr


@pytest.mark.parametrize(
    ("field", "mutate", "expected"),
    [
        (
            "blob",
            lambda body: re.sub(
                r" plan file blob SHA at this head: [0-9a-f]{40}", "", body
            ),
            "states no plan file blob SHA",
        ),
        (
            "revision",
            lambda body: re.sub(r"Plan revision: rev-7[^\n]*\n", "", body),
            "states no plan revision",
        ),
        (
            "limitations",
            lambda body: re.sub(
                r"Known limitations:[^\n]*", "Known limitations: " + LIMITATIONS_PLACEHOLDER, body
            ),
            "leaves the limitations placeholder unfilled",
        ),
        (
            "subject",
            lambda body: re.sub(
                r"Assessed subject:[^\n]*",
                "Assessed subject: " + template_field("Assessed subject"),
                body,
            ),
            "leaves the subject placeholder unfilled",
        ),
        (
            "acceptance",
            lambda body: re.sub(r"Acceptance evidence:[^\n]*\n", "", body),
            "states no acceptance evidence",
        ),
        (
            "acceptance-placeholder",
            lambda body: re.sub(
                r"Acceptance evidence:[^\n]*",
                "Acceptance evidence: " + template_field("Acceptance evidence"),
                body,
            ),
            "leaves the acceptance placeholder unfilled",
        ),
        (
            "proof-blob",
            # Scoped to the proof request. Removing the blob from both requests
            # would fail on the completeness one and leave the proof rule
            # untested, which is what the earlier control did.
            lambda body: (
                re.sub(r" plan file blob SHA at this head: [0-9a-f]{40}", "", body)
                if "are you satisfied that the introduced proof" in body
                else body
            ),
            "states no plan file blob SHA",
        ),
        (
            "inventory",
            lambda body: re.sub(
                r"Proof inventory:[^\n]*",
                "Proof inventory: none affected.",
                body,
            ),
            "says no proof is affected but the run asks for a proof assessment",
        ),
        *(
            (
                f"proof-{slug}",
                lambda body, _field=field: (
                    re.sub(rf"{re.escape(_field)}:[^\n]*\n", "", body)
                    if "are you satisfied that the introduced proof" in body
                    else body
                ),
                f"states no {field.lower()}",
            )
            for slug, field in (
                ("inventory", "Proof inventory and claims"),
                ("correspondence", "Production correspondence"),
                ("assumptions", "Assumptions, trusted boundaries, domain, and bounds"),
                ("verifier", "Verifier evidence"),
                ("non-vacuity", "Non-vacuity and limitations"),
            )
        ),
    ],
    ids=[
        "blob",
        "revision",
        "limitations",
        "subject",
        "acceptance",
        "acceptance-placeholder",
        "proof-blob",
        "inventory",
        "proof-inventory",
        "proof-correspondence",
        "proof-assumptions",
        "proof-verifier",
        "proof-non-vacuity",
    ],
)
def test_the_request_probe_refuses_a_question_missing_a_required_field(
    field: str, mutate: object, expected: str, tmp_path: Path
) -> None:
    """Every required field has a control that removes it and is caught.

    The positive test above shows the recorded requests pass; on its own that
    is also what a probe accepting everything would report. Each case here
    removes exactly one field from the combined scenario, which carries both
    question kinds, and requires the probe to name that field.

    The five `proof-*` rows remove a field from the proof request alone. An
    earlier `proof-blob` row removed the blob from both requests, so it failed
    on the completeness request and never exercised the proof rule it was named
    for; scoping the mutation to the proof body is what makes each row test the
    field in its own name.
    """
    combined = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
    facts = facts_with_bodies(
        json.loads(combined.read_text(encoding="utf-8")), mutate
    )
    mutated = tmp_path / "facts.json"
    mutated.write_text(json.dumps(facts), encoding="utf-8")
    # The scenario is not one that scripts an answer, so it has no run state
    # and the probe's posted list is empty; the field checks it exercises are
    # the ones applied to the seeded requests.
    done = run_probe(
        "PROBE_REQUESTS",
        str(mutated),
        str(tmp_path / "state.json"),
        "combined-plan-and-proof",
    )
    assert done.returncode != 0, f"removing the {field} field was not detected"
    assert expected in done.stderr, done.stderr


#: Each proof-template field with the placeholder the shipped template prints
#: for it. Both halves are extracted rather than copied: a template edit that
#: rewords a placeholder or renames a field then changes these controls, and
#: a control cannot pass by asserting against a wording nothing sends.
PROOF_PLACEHOLDERS = tuple(
    (slug, field, template_field(field))
    for slug, field in (
        ("inventory", "Proof inventory and claims"),
        ("correspondence", "Production correspondence"),
        ("assumptions", "Assumptions, trusted boundaries, domain, and bounds"),
        ("verifier", "Verifier evidence"),
        ("non-vacuity", "Non-vacuity and limitations"),
    )
)


@pytest.mark.parametrize(("slug", "field", "placeholder"), PROOF_PLACEHOLDERS)
def test_each_proof_field_placeholder_is_refused_on_its_own(
    slug: str, field: str, placeholder: str, tmp_path: Path
) -> None:
    """A proof request carrying a template placeholder is a question nobody asked.

    The template says not to post unresolved placeholders, and each of the
    proof request's five fields has one. A probe that only refused unfilled
    completeness fields would accept a proof question whose inventory,
    correspondence, boundaries, verifier evidence and non-vacuity were never
    stated, and the verdict that followed would cover a subject that was never
    put to it.

    Each case substitutes exactly one field's placeholder and requires the
    probe to name that field, so a control cannot pass on a sibling's defect.
    """
    combined = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"

    def leave_that_field_unfilled(body: str) -> str:
        """Replace one proof field's value with the template's placeholder."""
        if "are you satisfied that the introduced proof" not in body:
            return body
        return re.sub(
            rf"{re.escape(field)}:[^\n]*", f"{field}: {placeholder}", body
        )

    facts = facts_with_bodies(
        json.loads(combined.read_text(encoding="utf-8")), leave_that_field_unfilled
    )
    mutated = tmp_path / "facts.json"
    mutated.write_text(json.dumps(facts), encoding="utf-8")
    done = run_probe(
        "PROBE_REQUESTS",
        str(mutated),
        str(tmp_path / "state.json"),
        "combined-plan-and-proof",
    )
    assert done.returncode != 0, (
        f"the {slug} placeholder was accepted as a stated value"
    )
    assert f"leaves the {field.lower()} placeholder unfilled" in done.stderr, done.stderr


def test_the_controls_hold_the_placeholders_the_template_actually_prints() -> None:
    """The controls and the template cannot drift apart.

    Every other case here substitutes a placeholder this module extracted from
    `execplan-assessment.md`, so those cases follow the template wherever it
    goes. This one pins the extraction itself: it requires each extracted value
    to be the angle-bracketed form the probe refuses, so a template edit that
    drops the brackets, empties a field or renames a label fails here by name
    instead of quietly making a control substitute a value that proves nothing.

    The template opening is checked separately. It carries
    `<proof file paths with named proof references>` in its first line, and a
    request that pasted the template through would leave that one unfilled too;
    it is not a labelled field, so `template_field` cannot reach it.
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "@coderabbitai please assess the implementation" in text
    assert "<proof file paths with named proof references>" in text
    for label in (
        "Assessed subject",
        "Acceptance evidence",
        "Known limitations",
        *(
            field
            for _, field, _ in PROOF_PLACEHOLDERS
        ),
    ):
        value = template_field(label)
        # The template writes a full stop after the closing bracket, which is
        # the same trailing punctuation the probe strips before deciding.
        bracketed = value.removesuffix(".").rstrip()
        assert bracketed.startswith("<") and bracketed.endswith(">"), (
            f"the template's {label!r} value is no longer a placeholder:"
            f" {value!r}"
        )


def test_the_none_affected_claim_is_checked_against_the_candidate(
    tmp_path: Path,
) -> None:
    """"none affected" is contradicted by the diff, not only by a sibling ask.

    The combined cases trigger the contradiction through their proof question
    as well, so a probe that only compared the claim with the sibling request
    would pass every one of them. A candidate that changes the proof file
    contradicts the claim on its own: there is no question to point at, and
    the diff still shows the proof in it. This control rewrites the
    completeness request to claim no proof is affected, removes the proof
    question, and leaves the diff as the only fact that disagrees: the
    candidate still changes `proofs/refinement/Theorem.lean`.
    """
    source = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
    facts = json.loads(source.read_text(encoding="utf-8"))
    discussion = facts["api"][r"/issues/\d+/comments"]
    kept = [
        {
            **entry,
            "body": re.sub(
                r"Proof inventory:[^\n]*",
                "Proof inventory: none affected.",
                str(entry.get("body", "")),
            ),
        }
        for entry in discussion
        if "are you satisfied that the introduced proof"
        not in str(entry.get("body", ""))
    ]
    assert len(kept) < len(discussion), "the scenario asks no proof question"
    assert any(
        "Proof inventory: none affected." in str(entry["body"]) for entry in kept
    ), "the completeness request states no proof inventory to rewrite"
    facts["api"][r"/issues/\d+/comments"] = kept
    changed = {
        str(entry.get("filename", ""))
        for entry in facts["api"][r"/pulls/\d+/files(?:[?#]|$)"]
        if isinstance(entry, dict)
    }
    assert str(facts.get("proof_path", "")) in changed, (
        "the scenario changes no proof, so the diff cannot contradict the claim"
    )
    scratch = tmp_path / "facts.json"
    scratch.write_text(json.dumps(facts), encoding="utf-8")
    refused = run_probe(
        "PROBE_REQUESTS",
        str(scratch),
        str(tmp_path / "state.json"),
        "combined-plan-and-proof",
    )
    assert refused.returncode != 0, "a claim the diff contradicts was accepted"
    assert "says no proof is affected" in refused.stderr, refused.stderr


def test_a_proof_only_question_states_no_revision_and_needs_no_blob(
    tmp_path: Path,
) -> None:
    """The no-ExecPlan case must stay recordable.

    A proof-only candidate has no approved revision, and its question says so
    rather than naming one. Requiring a blob there would make the one shape the
    skill describes for that case impossible to record, and a probe that did so
    would be wrong about the template rather than strict about it.
    """
    source = FIXTURES / "scenarios" / "proof-only-cleared" / "facts.json"
    facts = json.loads(source.read_text(encoding="utf-8"))
    state = tmp_path / "state.json"
    done = run_probe("PROBE_REQUESTS", str(source), str(state), "proof-only-cleared")
    assert done.returncode == 0, done.stderr
    bodies = " ".join(str(entry["body"]) for entry in facts["api"][r"/issues/\d+/comments"])
    assert "no ExecPlan applies" in bodies, "the proof-only question claims a revision"

    # And the control: give it a revision without a blob and the probe must
    # object, so the exemption above is the omitted form and not silence.
    def claim_revision(body: str, revision: str = "rev-7") -> str:
        """Replace the omitted-revision line with a bare revision claim."""
        return body.replace(
            "Plan revision: <omitted; no ExecPlan applies>.", f"Plan revision: {revision}."
        )

    mutated = facts_with_bodies(facts, claim_revision)
    assert mutated != facts, "the proof-only question does not use the omitted form"
    scratch = tmp_path / "facts.json"
    scratch.write_text(json.dumps(mutated), encoding="utf-8")
    refused = run_probe(
        "PROBE_REQUESTS", str(scratch), str(state), "proof-only-cleared"
    )
    assert refused.returncode != 0, "a revision without its blob was accepted"
    assert "states no plan file blob SHA" in refused.stderr, refused.stderr


def test_a_request_citing_a_blob_the_head_does_not_serve_is_refused(
    tmp_path: Path,
) -> None:
    """The cited blob is the file's at the head, not the named revision's.

    The template asks for ``the plan file's blob SHA at this head``, so a
    request cites whichever file the published head serves, beside whatever
    revision was approved at the time. The two coincide until an approval moves
    under a fixed head, which is the premise of the two stale cases: there a
    request has to cite the served blob beside the older approval.

    Citing the older revision's own blob instead describes a file that head
    never carried. That is a contradiction in the premise rather than the stale
    approval the case exists to rehearse, and a run reading it holds on the
    contradiction. The control substitutes such a blob into the combined
    scenario, whose head serves a single file.
    """
    source = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
    facts = json.loads(source.read_text(encoding="utf-8"))

    def cite_an_unserved_blob(body: str) -> str:
        """Replace the cited served blob with one no route answers."""
        return re.sub(
            r" blob SHA at this head: [0-9a-f]{40}",
            " blob SHA at this head: " + "0" * 40,
            body,
        )

    mutated = facts_with_bodies(facts, cite_an_unserved_blob)
    assert mutated != facts, "the scenario's requests cite no served blob"
    scratch = tmp_path / "facts.json"
    scratch.write_text(json.dumps(mutated), encoding="utf-8")
    refused = run_probe(
        "PROBE_REQUESTS",
        str(scratch),
        str(tmp_path / "state.json"),
        "combined-plan-and-proof",
    )
    assert refused.returncode != 0, "a blob the head does not serve was accepted"
    assert "but this head serves" in refused.stderr, refused.stderr


#: The read-only invocations a readiness run makes, each of which must appear
#: in the trace with the answer it was given. They are read routes the skill
#: depends on, chosen to span the three answering mechanisms: a `--json`
#: projection, a `--jq` filter and a REST read.
READS = (
    (
        "pr-view",
        ("pr", "view", "272", "--repo", "leynos/agent-helper-scripts", "--json", PR_VIEW_JSON),
    ),
    ("pr-checks", ("pr", "checks", "272", "--repo", "leynos/agent-helper-scripts")),
    ("user", ("api", "user", "--jq", ".login")),
    ("issue-comments", ("api", "repos/leynos/agent-helper-scripts/issues/272/comments")),
)


@pytest.mark.parametrize(
    "corrupt",
    ["{not json", "[]", '"a string"', ""],
    ids=["truncated", "list", "string", "empty"],
)
def test_a_read_that_cannot_read_back_its_state_faults(
    run: Path, corrupt: str
) -> None:
    """A lost write must be reported, not answered around.

    `state.json` is the run's own record. Falling back to the premise when it
    exists but cannot be parsed turns a run that wrote a comment and then lost
    the file into one that never posted, and reports success for an observation
    that never happened. A missing file stays a real state — the first
    invocation has none — so only the unreadable case is a fault.
    """
    (run / "state.json").write_text(corrupt, encoding="utf-8")
    done = invoke(run, "api", "repos/leynos/agent-helper-scripts/issues/272/comments")
    assert done.returncode != 0, done.stdout
    assert "fixture state fault" in done.stderr, done.stderr
    assert (run / "state.json").read_text(encoding="utf-8") == corrupt, (
        "the faulting read rewrote the state it could not read"
    )


def test_a_post_that_cannot_read_its_prior_state_faults(run: Path) -> None:
    """A POST reads the id sequence from state, so it faults like any read.

    Continuing from an unreadable record would restart the comment ids at 9901
    and report the run's earlier comments as absent, which is the same lost
    write the plain read refuses.
    """
    (run / "state.json").write_text("{not json", encoding="utf-8")
    done = invoke(
        run, "api", COMMENT_ROUTE, "-f", "body=follow-up", token=POOL_TOKEN
    )
    assert done.returncode != 0, done.stdout
    assert "fixture state fault" in done.stderr, done.stderr
    assert (run / "state.json").read_text(encoding="utf-8") == "{not json", (
        "the faulting POST overwrote the state it could not read"
    )


def load_shim(directory: Path) -> ModuleType:
    """Load the `gh` stand-in beside `directory` as an in-process module.

    The stand-in derives its run directory from its own location, so the copy
    in `directory` points at that directory's facts and state. Loading it as a
    module rather than running it as a subprocess lets a test act *between* its
    reads, which is the only way to reproduce a file that disappears after the
    first read and before the second.

    The copy is named `gh` with no extension, so the loader is named rather
    than inferred from a suffix that is not there.
    """
    path = directory / "gh"
    loader = importlib.machinery.SourceFileLoader("gh_shim_under_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_a_state_file_removed_after_the_first_read_does_not_lose_the_history(
    run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The POST continues from the state the invocation already observed.

    The stand-in used to load `state.json` in `read_facts` and then reopen it
    through `state_value`, so a file deleted between those two reads was
    indistinguishable from one that had never existed: the POST restarted the
    comment ids at 9901 and wrote a history holding only the new comment, and
    the run's earlier comments were reported as absent. A deletion between the
    reads is a lost observation, not a first post, and the write that follows
    one must not discard what was already read.

    The file is removed after the first read by replacing `Path.read_text`,
    which is the only path the first read takes. Both invocations run in this
    process, so the second one is the one whose POST finds the file gone.
    """
    shim = load_shim(run)
    monkeypatch.setenv("GH_TOKEN", POOL_TOKEN)
    first = shim.main(["api", COMMENT_ROUTE, "-f", "body=first"])
    assert first == 0, "the first POST was refused"
    before = posted(run)
    state = run / "state.json"

    real_read_text = Path.read_text

    def read_then_remove(path: Path, *args: object, **kwargs: object) -> str:
        """Return the state's text, deleting the file after that one read."""
        text = real_read_text(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == state:
            path.unlink()
        return text

    monkeypatch.setattr(Path, "read_text", read_then_remove)
    second = shim.main(["api", COMMENT_ROUTE, "-f", "body=second"])
    monkeypatch.undo()

    assert second == 0, "the POST after the lost state file was refused"
    history = posted(run)
    assert history[: len(before)] == before, (
        "the POST lost the comment the first read observed:"
        f" {history} does not start with {before}"
    )
    assert last_posted(run)["body"] == "second", last_posted(run)


def test_a_ready_transition_reuses_the_state_the_invocation_observed(
    run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transition keeps the history its own observation already carries.

    The POST path was fixed to continue from the state `read_facts` observed,
    but `mark_ready` still reopened `state.json`. A file removed after the
    first read was then rewritten as `{"isDraft": false}` alone, and the
    comments the run had posted vanished from a history this call had itself
    truncated. The transition is a write, so it continues from what the
    invocation observed rather than from a second look at the file.
    """
    shim = load_shim(run)
    monkeypatch.setenv("GH_TOKEN", POOL_TOKEN)
    first = shim.main(["api", COMMENT_ROUTE, "-f", "body=before-ready"])
    assert first == 0, "the POST was refused"
    before = posted(run)
    state = run / "state.json"

    real_read_text = Path.read_text

    def read_then_remove(path: Path, *args: object, **kwargs: object) -> str:
        """Return the state's text, deleting the file after that one read."""
        text = real_read_text(path, *args, **kwargs)  # type: ignore[arg-type]
        if path == state:
            path.unlink()
        return text

    monkeypatch.setattr(Path, "read_text", read_then_remove)
    ready = shim.main(["pr", "ready", "272", "--repo", "leynos/agent-helper-scripts"])
    monkeypatch.undo()

    assert ready == 0, "the transition after the lost state file was refused"
    assert json.loads(state.read_text(encoding="utf-8"))["isDraft"] is False
    assert posted(run) == before, (
        "the transition dropped the comments the first read observed:"
        f" {posted(run)} does not equal {before}"
    )


@pytest.mark.parametrize(("name", "argv"), READS, ids=[name for name, _ in READS])
def test_a_read_only_query_is_answered_inside_the_recording_boundary(
    run: Path, name: str, argv: tuple[str, ...]
) -> None:
    """Every read leaves one trace entry and one answer record, in step.

    The trace is how a recording shows what the agent read. A route answered
    outside the boundary would leave an invocation the agent made with no
    entry, so the trace would under-report the run's reads and a probe could
    not tell an unread source from an unrecorded one.

    The two files are checked together: a trace entry with no matching answer
    record would show the call but not what it returned, which is the half of
    the evidence a readiness decision rests on.
    """
    done = invoke(run, *argv)
    assert done.returncode == 0, done.stderr

    traced = [
        json.loads(line)
        for line in (run / "gh-trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    recorded = [
        json.loads(line)
        for line in (run / "gh-answers.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert traced == [list(argv)], f"{name} was answered outside the boundary: {traced}"
    assert [entry["argv"] for entry in recorded] == [list(argv)], (
        f"{name} left no answer record: {recorded}"
    )
    answered = recorded[0]
    assert answered["status"] == 0, f"{name} recorded status {answered['status']}"
    assert answered["stdout"] == done.stdout, (
        f"{name} recorded {answered['stdout']!r}, not what the agent received"
    )
    assert answered["stdout"].strip(), f"{name} recorded an empty answer"


@pytest.mark.parametrize(
    ("name", "argv"),
    READS,
    ids=[f"{name}-preserves-state" for name, _ in READS],
)
def test_a_read_only_query_leaves_the_command_state_alone(
    run: Path, name: str, argv: tuple[str, ...]
) -> None:
    """A read is not a write, and `state.json` is where a write would land.

    The stand-in keeps the commands it has performed in `state.json`, and every
    read merges that file into the facts it answers from. The merge is what
    makes a read-only command able to change the record: a key it did not mean
    to carry, or a default it filled in, would be written back as if the run
    had performed it. Both cases are checked because they fail differently —
    an absent file must stay absent, and a file holding command state must come
    back byte-identical. The trace and answer records are excluded on purpose:
    recording is the boundary's own output, not the service's state.
    """
    state = run / "state.json"
    assert not state.exists(), f"{name} started from a file the fixture did not write"
    answered = invoke(run, *argv)
    assert answered.returncode == 0, answered.stderr
    assert not state.exists(), (
        f"{name} created command state, so a read was recorded as a write"
    )

    # A run that has already posted or transitioned carries state. The read
    # must answer around it without rewriting it: a merge that defaulted a
    # missing key, or dropped one it did not recognize, would show up here and
    # nowhere else, because the answer itself is unchanged.
    recorded = json.dumps(
        {"isDraft": True, "posted": [{"id": 9901, "body": "@coderabbitai …"}]}
    )
    state.write_text(recorded, encoding="utf-8")
    answered = invoke(run, *argv)
    assert answered.returncode == 0, answered.stderr
    assert state.read_text(encoding="utf-8") == recorded, (
        f"{name} rewrote the command state it read through:"
        f" {state.read_text(encoding='utf-8')!r}"
    )


#: A completeness request as the skill posts it, with the marker the run mints.
#: The marker is the run's own choice, so this stands in for any; the stand-in
#: answers by the question's kind and echoes whatever marker the request
#: carries, which is what a scenario cannot predict and must not hard-code.
SCRIPTED_REQUEST = (
    "@coderabbitai please assess the implementation in this PR for\n"
    "completeness and correctness against the execplan:\n\n"
    "> `docs/execplans/issue-271-readiness-handoff.md`\n\n"
    "Assessed subject: the whole approved plan.\n"
    "Published head: eeee5555; comparison base: "
    "73d32981c7b7e8f52590a074873e28a9f369f0f9.\n"
    "Plan revision: rev-7 (approved revision in force); plan file blob SHA at"
    " this head: 5a1c9e4d7b3f28a06c5e1d9b4f7a2c8e6d0b3f15.\n"
    "Acceptance evidence: the hosted checks recorded for this head.\n"
    "Known limitations: the local result is the stand-in's.\n"
    "Proof inventory: none affected.\n"
    "Assessment-ID: 271-ab-minted-by-the-run.\n\n"
    "Please echo the Assessment-ID.\n"
    "This is an assessment conversation, not a request to start a formal PR"
    " review."
)


def scripted_scenario(tmp_path: Path) -> Path:
    """Place the scripted-answer scenario's stand-in in its own directory."""
    source = FIXTURES / "scenarios" / "posted-then-answered" / "facts.json"
    shutil.copy2(source, tmp_path / "facts.json")
    return place_shim(SHIM, "gh", tmp_path)


def post_scripted(run: Path) -> subprocess.CompletedProcess[str]:
    """Post the readiness request the scripted scenario is built to answer."""
    return invoke(
        run,
        "api",
        "--method",
        "POST",
        "repos/leynos/agent-helper-scripts/issues/272/comments",
        "-f",
        "body=" + SCRIPTED_REQUEST,
        token=POOL_TOKEN,
    )


def test_a_scripted_answer_echoes_the_marker_the_run_minted(
    tmp_path: Path,
) -> None:
    """The one case where a run both asks and clears needs an answer to its ask.

    The marker is chosen by the agent, so a fixture cannot key a verdict on it.
    The stand-in answers by the question's kind and echoes the marker the
    request carried, which is also what the observation protocol correlates on:
    an answer naming a different marker would not be attributable to the
    question, and the run would be right to keep waiting.
    """
    run = scripted_scenario(tmp_path)
    done = post_scripted(run)
    assert done.returncode == 0, done.stderr
    answers = json.loads((run / "state.json").read_text(encoding="utf-8"))[
        "scripted"
    ]
    assert len(answers) == 1, answers
    body = answers[0]["body"]
    assert "271-ab-minted-by-the-run" in body, body
    assert "**Verdict: clear**" in body, body


def test_a_scripted_answer_discloses_in_its_own_text_that_it_is_scripted(
    tmp_path: Path,
) -> None:
    """A recording must not need the README to say what answered the run.

    The `cs` stand-in prints its disclosure on every answer, and this one does
    the same. The text is what a reader of `answers/` and the discussion
    listing actually sees; a disclosure held only in prose beside the fixture
    would leave the recording itself claiming a service reply.
    """
    run = scripted_scenario(tmp_path)
    assert post_scripted(run).returncode == 0
    body = json.loads((run / "state.json").read_text(encoding="utf-8"))[
        "scripted"
    ][0]["body"]
    assert "not a CodeRabbit answer" in body, body


def test_a_scripted_answer_is_listed_and_readable_by_its_own_route(
    tmp_path: Path,
) -> None:
    """The answer is a comment in the discussion, not a private side channel.

    A run finds a reply by listing the discussion and filtering it by time; it
    then fetches the comment it selected. An answer that only `state.json` held
    would be invisible to the first and 404 on the second, so the scripted case
    would behave exactly like the unscripted one.
    """
    run = scripted_scenario(tmp_path)
    assert post_scripted(run).returncode == 0
    listed = json.loads(
        invoke(
            run, "api", "repos/leynos/agent-helper-scripts/issues/272/comments"
        ).stdout
    )
    bot = [entry for entry in listed if entry["user"]["login"] == "coderabbitai[bot]"]
    assert len(bot) == 1, bot
    answer = bot[0]
    fetched = invoke(
        run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{answer['id']}"
    )
    assert fetched.returncode == 0, fetched.stderr
    assert json.loads(fetched.stdout)["id"] == answer["id"]


def test_a_scripted_answer_is_stamped_after_its_own_request(
    tmp_path: Path,
) -> None:
    """A time-filtered poll must see the answer, not filter it away.

    The observation protocol fetches the discussion updated since the request's
    timestamp. An answer carrying the same stamp, or an earlier one, would be
    excluded by that filter, and the run would report silence for a question it
    had just had answered.
    """
    run = scripted_scenario(tmp_path)
    assert post_scripted(run).returncode == 0
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    request = state["posted"][0]["created_at"]
    answer = state["scripted"][0]["created_at"]
    assert answer > request, f"answer {answer} does not sort after {request}"


def test_an_unscripted_scenario_still_answers_no_question_it_did_not_record(
    run: Path,
) -> None:
    """Scripting is opt-in per scenario, and silence stays silence.

    The default `current-whole-plan` fixture records its answer in the thread
    and scripts nothing. A POST it did not record must therefore be answered
    with the request alone: inventing a verdict here would let a holding case
    clear itself, which is the failure the whole fixture exists to prevent.
    """
    done = invoke(
        run,
        "api",
        "--method",
        "POST",
        "repos/leynos/agent-helper-scripts/issues/272/comments",
        "-f",
        "body=@coderabbitai please assess the implementation.\n\n"
        "Assessment-ID: 271-ab-unrecorded.\n",
        token=POOL_TOKEN,
    )
    assert done.returncode == 0, done.stderr
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    # The key is always written now, so that a POST which answers nothing
    # cannot drop an answer an earlier one recorded. What this case pins is
    # that the list stays empty: an invented verdict is the defect.
    assert state.get("scripted") == [], state
    assert len(state["posted"]) == 1, state


def test_a_request_posted_after_a_scripted_reply_takes_a_new_id(
    tmp_path: Path,
) -> None:
    """Every comment in the discussion has its own id, whatever created it.

    The stand-in numbered requests from `posted` alone and gave each scripted
    reply `request id + 1`. Once an answer exists, the two sequences overlap:
    the next request is assigned the id the answer already holds, the listing
    carries two different comments under one id, and an id-based read returns
    whichever of them it reaches first. The real service numbers comments from
    one sequence, so the stand-in has to as well.
    """
    run = scripted_scenario(tmp_path)
    assert post_scripted(run).returncode == 0
    second = invoke(
        run,
        "api",
        "--method",
        "POST",
        COMMENT_ROUTE,
        "-f",
        "body=An ordinary comment with no Assessment-ID.",
        token=POOL_TOKEN,
    )
    assert second.returncode == 0, second.stderr
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    ids = [entry["id"] for entry in state["posted"]]
    ids += [entry["id"] for entry in state.get("scripted") or []]
    assert len(ids) == len(set(ids)), f"two comments share an id: {ids}"

    listed = json.loads(
        invoke(
            run, "api", "repos/leynos/agent-helper-scripts/issues/272/comments"
        ).stdout
    )
    listed_ids = [entry["id"] for entry in listed]
    assert len(listed_ids) == len(set(listed_ids)), (
        f"the listing repeats an id: {listed_ids}"
    )
    # An id-based read has to return the comment it names. The second request
    # is the one that collided, so it is the read that exposes the defect.
    answered = json.loads(second.stdout)
    fetched = invoke(
        run, "api", f"repos/leynos/agent-helper-scripts/issues/comments/{answered['id']}"
    )
    assert fetched.returncode == 0, fetched.stderr
    assert "no Assessment-ID" in json.loads(fetched.stdout)["body"], (
        "the id read returned the scripted reply instead of the request"
    )


def test_a_later_post_keeps_the_scripted_replies_the_run_already_has(
    tmp_path: Path,
) -> None:
    """Adding to the discussion must not truncate it.

    A scenario's scripted answer is written into `state.json` when the request
    is posted. A later comment that the stand-in does not answer produced no
    new reply, and the state was written without a `scripted` key at all, so
    the answer the run had already received disappeared from the listing and
    from every id-based read. The reply is a comment in the discussion; a post
    that is not an answer to it does not remove it.
    """
    run = scripted_scenario(tmp_path)
    assert post_scripted(run).returncode == 0
    reply = json.loads((run / "state.json").read_text(encoding="utf-8"))[
        "scripted"
    ][0]
    later = invoke(
        run,
        "api",
        "--method",
        "POST",
        COMMENT_ROUTE,
        "-f",
        "body=A remark that asks no assessment question.",
        token=POOL_TOKEN,
    )
    assert later.returncode == 0, later.stderr
    state = json.loads((run / "state.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in state.get("scripted") or []] == [reply["id"]], (
        f"the later post dropped the scripted reply: {state}"
    )
    listed = json.loads(
        invoke(
            run, "api", "repos/leynos/agent-helper-scripts/issues/272/comments"
        ).stdout
    )
    assert reply["id"] in [entry["id"] for entry in listed], (
        f"the listing no longer carries the scripted reply: {listed}"
    )


#: The scenarios that rehearse the implementation handoff: the run starts at
#: `sdlc-implementation`, produces the packet and carries it into
#: `pr-babysitting`. Everything else starts at the receiver.
CROSSING = ("crossing-whole-plan", "crossing-subset-clear")

#: The sender the handoff probe reads its packet from. Named once so the probe
#: tests and any future crossing case point at the shipped skill.
IMPLEMENTATION_SKILL = (
    FIXTURES.parent.parent.parent / "skills" / "sdlc-implementation" / "SKILL.md"
)


def _start_skill(facts: dict) -> str:
    """Return the skill a scenario says its run starts at, or the default."""
    return str(facts.get("start_skill", "pr-babysitting"))


def test_every_crossing_scenario_states_its_start_and_no_other_does() -> None:
    """The crossing is a property of the scenario, not of the runner's mood.

    A scenario whose facts named no start skill would get the receiver-only
    prompt, and a rehearsal meant to cross the handoff would then record a run
    that never opened the sender. The converse matters too: a receiver-only
    case that gained the key would be re-run under a prompt its committed
    recording was never made with, so the seventeen existing cases are held to
    stating nothing.
    """
    found = set()
    for facts_path in sorted((FIXTURES / "scenarios").glob("*/facts.json")):
        facts = json.loads(facts_path.read_text(encoding="utf-8"))
        name = facts_path.parent.name
        if "start_skill" in facts:
            found.add(name)
            assert facts["start_skill"] == "sdlc-implementation", (
                f"{name} names an unknown start skill {facts['start_skill']!r}"
            )
    assert found == set(CROSSING), (
        f"the crossing scenarios and the named ones disagree: {found}"
    )


def test_a_crossing_scenario_reuses_a_recorded_readiness_decision() -> None:
    """The crossing must be the only variable a crossing run adds.

    Each crossing case is one of the two decisions the readiness rule already
    turns on — the hole is in the assessment evidence, not in the handoff — so
    its facts are the existing case's facts plus the start skill. A run of it
    is therefore evidence about whether the crossing preserves the decision,
    not about whether a handwritten scenario reached the intended verdict.
    If the two facts had drifted, a divergence could be attributed to either.
    """
    pairs = {
        "crossing-whole-plan": "current-whole-plan",
        "crossing-subset-clear": "subset-clear",
    }
    for crossing, recorded in pairs.items():
        left = json.loads(
            (FIXTURES / "scenarios" / crossing / "facts.json").read_text(
                encoding="utf-8"
            )
        )
        right = json.loads(
            (FIXTURES / "scenarios" / recorded / "facts.json").read_text(
                encoding="utf-8"
            )
        )
        assert left.pop("start_skill") == "sdlc-implementation"
        assert left == right, (
            f"{crossing} differs from {recorded} beyond its start skill, so a"
            " difference in outcome cannot be attributed to the crossing"
        )


def test_the_runner_selects_the_crossing_prompt_from_the_scenario() -> None:
    """The start skill is read, validated, and branched on by the runner.

    An unvalidated value would fall through to the receiver prompt silently,
    which is the failure the crossing checks exist to prevent: the run would
    look like a crossed rehearsal and be a receiver-only one. The staged skill
    list has to follow the same value, or a crossing run would be asked for a
    handoff from a skill the sandbox never copied.
    """
    runner = RUNNER.read_text()
    assert 'facts.get("start_skill", "pr-babysitting")' in runner, (
        "the runner no longer reads the scenario's start skill"
    )
    assert "unknown start_skill" in runner, (
        "the runner accepts a start skill it does not know"
    )
    assert 'STAGED_SKILLS="sdlc-implementation pr-babysitting"' in runner, (
        "a crossing run is not given both shipped skills"
    )
    assert "STAGED_SKILLS=pr-babysitting" in runner, (
        "a receiver-only run is no longer given the receiver alone"
    )
    for skill in ("sdlc-implementation", "pr-babysitting"):
        assert f"`{skill}/SKILL.md`" in runner or f"{skill}/SKILL.md" in runner, (
            f"the crossing prompt no longer names {skill}/SKILL.md"
        )
    assert "HANDOFF PACKET" in runner, (
        "the crossing prompt no longer asks for the packet"
    )


def test_the_receiver_prompt_is_the_one_the_recordings_were_made_under() -> None:
    """Seventeen recordings must stay attached to a prompt that still exists.

    The crossing was added by giving those scenarios a branch, not by editing
    the prompt every existing recording was made under. Re-wording it here
    would leave each one describing a run nobody can reproduce, and nothing in
    the suite would notice, because the prompt is not part of any recording.
    """
    runner = RUNNER.read_text()
    recorded = runner[
        runner.index("You are the PR lifecycle supervisor for leynos/agent-helper-scripts pull")
        :
    ]
    recorded = recorded[: recorded.index("\nPROMPT\n")]
    assert "Start at `pr-babysitting/SKILL.md`" in recorded, (
        "the receiver prompt no longer sends the run to the receiver skill"
    )
    assert "sdlc-implementation" not in recorded, (
        "the receiver prompt now names the sender, so the existing recordings"
        " were made under a prompt the runner no longer sends"
    )


def handoff_packet() -> str:
    """Build the shipped packet, as the message that hands delivery over."""
    fields = {
        "Repository, PR, worktree, target, and verified base/head":
            "leynos/agent-helper-scripts#272 at cccc3333, base 73d32981",
        "Approved ExecPlan path and revision; accepted scope and tolerances":
            "docs/execplans/issue-271-readiness-handoff.md at rev-7",
        "Implementation status and acceptance evidence; remaining in-scope work":
            "delivered; the change is under test; nothing in scope remains",
        "Local gate and milestone CLI results with candidate identities and logs":
            "make test at cccc3333 in /tmp/gates.out",
        "Proof inventory and verifier evidence, or justified not applicable":
            "none affected; no proof changed",
        "ExecPlan completeness/correctness assessment":
            "required against the whole approved plan, not the declared PR"
            " scope; evidence or pending: clear for rev-7",
        "Proof-specific assessment": "required when applicable; not applicable",
        "Roadmap association/status; PR description and Lody references":
            "no roadmap item; description names the plan",
        "Observed CI/review state, existing requests, and current lifecycle owner":
            "all checks green; the supervisor owns delivery",
        "Authorized publication/merge actions, stopping point, and concrete"
        " blockers": "no publication; stop at readiness; no blockers",
    }
    lines = ["HANDOFF PACKET", ""]
    for label, value in fields.items():
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


#: The sentence a run closes with. It follows the packet as the decision the
#: packet informed: a closing message that is only a courtesy ("packet above,
#: nothing more to say") would say nothing about what the receiver did with it.
HANDOFF_CLOSING = "I marked the PR ready because the whole approved plan cleared."


def handoff_outcome() -> str:
    """Build the closing message that follows the packet."""
    return HANDOFF_CLOSING


CLASSIFYING_CALL = {
    "type": "assistant",
    "message": {
        "content": [
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "python3 classify.py --readiness"},
            }
        ]
    },
}


def tool_call(name: str, payload: dict) -> dict:
    """Return one assistant event carrying a single tool call.

    The call has no id yet. A run's calls are identified and answered by
    `recorded`, which is the only place that knows a call's position in the
    run; stamping an id here would give two identical calls one identity and
    let a result stand for a call that was never recorded.
    """
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": name, "input": payload}]
        },
    }


def recorded(
    events: list[dict], outcomes: dict[int, bool | None] | None = None
) -> list[dict]:
    """Return the run's events with each call identified and answered.

    The handoff probe reads a call's outcome from the result carrying its id,
    so a constructed run has to look like the CLI's: every `tool_use` has an
    id, and the `tool_result` that answered it follows as a user message of
    its own. Pairing them here keeps the tests describing a run rather than
    repeating the bookkeeping in every case.

    A call with no entry in `outcomes` succeeded, which is the ordinary case.
    `False` is a call that exited non-zero — a `cat` with the wrong path — and
    `None` leaves the call without a result at all. Both are needed: the probe
    has to be able to refuse a run whose only open failed, and one whose
    transition was never recorded.

    Parameters
    ----------
    events : list of dict
        The run's assistant messages, in the order they were emitted.
    outcomes : dict, optional
        Call index, counted across the whole run, mapped to its result.

    Returns
    -------
    list of dict
        The same messages, with ids, interleaved with their results.
    """
    answers = {} if outcomes is None else outcomes
    stream: list[dict] = []
    index = 0
    for event in events:
        content = event["message"]["content"]
        calls = [part for part in content if part.get("type") == "tool_use"]
        if not calls:
            stream.append(event)
            continue
        stamped: list[dict] = []
        results: list[dict] = []
        for part in content:
            if part.get("type") != "tool_use":
                stamped.append(part)
                continue
            call_id = f"toolu_{index:03d}"
            answered = answers.get(index, True)
            index += 1
            stamped.append({**part, "id": call_id})
            if answered is not None:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "is_error": not answered,
                    }
                )
        stream.append({"type": "assistant", "message": {"content": stamped}})
        if results:
            stream.append({"type": "user", "message": {"content": results}})
    return stream


def handoff_message(text: str) -> dict:
    """Return one assistant event carrying only text, as the packet is."""
    return {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": text}]},
    }


def handoff_run(
    tmp_path: Path,
    outcome: str,
    opens: tuple[str, ...] = (),
    trace: list[object] | None = None,
    decide: bool = True,
    packet: str | None = None,
    packet_after_decision: bool = False,
    outcomes: dict[int, bool | None] | None = None,
) -> Path:
    """Write one crossing run's skill, outcome, event stream and trace.

    `opens` are calls that read a skill's manifest. A classifying call follows
    them, so a run has a tool call that is not the transition and the decision
    check has something to be wrong about, and, when `decide` is set, the run
    ends by running the transition. The packet is a message of its own before
    the transition, as the prompt asks; `packet_after_decision` places it
    after the transition instead, which is the negative control for the
    ordering check. `trace` is the stand-in's record of what `gh` actually
    ran, which is what the decision has to match. `outcomes` answers the calls
    by index as `recorded` does, so a case can make an open fail or leave the
    transition unanswered; every call succeeds by default.
    """
    skill = tmp_path / "SKILL.md"
    shutil.copy2(IMPLEMENTATION_SKILL, skill)
    message = tmp_path / "outcome.txt"
    message.write_text(outcome + "\n", encoding="utf-8")
    packet = handoff_packet() if packet is None else packet
    events = [
        tool_call("Read", {"file_path": f"/run/work/{name}"}) for name in opens
    ]
    if events:
        events.append(CLASSIFYING_CALL)
    if not packet_after_decision:
        events.append(handoff_message(packet))
    if decide:
        events.append(
            tool_call(
                "Bash",
                {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"},
            )
        )
    if packet_after_decision:
        events.append(handoff_message(packet))
    write_lines(tmp_path / "events.jsonl", recorded(events, outcomes))
    write_lines(tmp_path / "trace.jsonl", trace or [])
    return tmp_path



def test_the_handoff_probe_accepts_a_run_that_crossed(tmp_path: Path) -> None:
    """The probe must pass the run the prompt asks for.

    Without this the refusals below would pass against a probe that rejects
    everything, which is a broken check reported as a strict one.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "10 shipped fields" in done.stdout, done.stdout


def test_the_handoff_probe_refuses_a_run_that_never_opened_the_sender(
    tmp_path: Path,
) -> None:
    """Reaching the right decision is not evidence that the handoff crossed.

    A receiver-only run reaches the same readiness verdict, so an outcome-only
    check would accept it as a crossing. The event stream is what separates
    them.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("pr-babysitting/SKILL.md",),
        decide=False,
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "never opened sdlc-implementation" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_packet_missing_a_shipped_field(
    tmp_path: Path,
) -> None:
    """The packet is the shipped one, not a summary the agent preferred.

    The fields are read from the candidate's own skill, so a packet that drops
    a line is refused even if every line it kept is correct.
    """
    packet = handoff_packet().replace(
        "Proof-specific assessment: required when applicable; not applicable\n", ""
    )
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        packet=packet,
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "Proof-specific assessment" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_completeness_line_without_the_subject(
    tmp_path: Path,
) -> None:
    """The completeness line is what the subset case turns on.

    A crossing that carried an assessment line which no longer named the whole
    approved plan would leave the receiver refusing a subset for a reason its
    own handoff did not state, and the subset run's hold would be attributed to
    a rule the crossing had removed.
    """
    packet = handoff_packet().replace(
        "required against the whole approved plan, not the declared PR scope;",
        "required against the declared PR scope;",
    )
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        packet=packet,
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "whole approved plan" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_packet_printed_only_after_the_decision(
    tmp_path: Path,
) -> None:
    """The packet has to be recorded before the readiness decision.

    This is the negative control: the run opens both skills, prints the
    shipped packet, and reaches the right readiness decision — every part the
    positive run has — but records the packet only after `gh pr ready` ran.
    The receiver cannot apply a packet that did not exist when the decision
    was taken, so this run has to be refused even though its final message
    reads exactly like a crossed one.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        packet_after_decision=True,
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0, done.stdout + done.stderr
    assert "printed the handoff packet after the decision" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_decision_taken_before_the_sender_was_opened(
    tmp_path: Path,
) -> None:
    """The packet has to inform the decision, not follow it.

    The opens are ordered against the `pr ready` call rather than against each
    other: an agent may mention the receiver while exploring, but a transition
    that happened before the sender was read cannot have been informed by the
    packet it produced.
    """
    # Both skills are read, the packet is recorded before the transition, and
    # the transition is issued, so the run is complete except for the order:
    # the sender is read after the decision it is supposed to inform. A run
    # that merely failed to open the sender would be refused by the coverage
    # check instead, and a packet recorded after the decision would be refused
    # by the ordering check below, so neither can stand in for this case.
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        tool_call("Read", {"file_path": "/run/work/pr-babysitting/SKILL.md"}),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
        tool_call("Read", {"file_path": "/run/work/sdlc-implementation/SKILL.md"}),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "decided before opening sdlc-implementation" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_decision_taken_before_the_receiver_was_opened(
    tmp_path: Path,
) -> None:
    """The readiness rules have to be read before the transition is taken.

    A run may explore the receiver early, so the two opens are not ordered
    against each other. The decision is what orders them: a transition issued
    before `pr-babysitting` was opened was not taken under the rules it
    carries, even though the sender's packet was read first.
    """
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        tool_call("Read", {"file_path": "/run/work/sdlc-implementation/SKILL.md"}),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
        tool_call("Read", {"file_path": "/run/work/pr-babysitting/SKILL.md"}),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "decided before opening pr-babysitting" in done.stderr, done.stderr


def test_the_handoff_probe_takes_a_mention_of_the_command_as_no_decision(
    tmp_path: Path,
) -> None:
    """A ledger line describing a command the run declined is not that command.

    A refusing run records its decision in prose: "do not run gh pr ready; PR
    stays draft". When the decision was found by searching the event stream for
    that text, the record was read as the invocation, and the ordering check
    then compared the skills against a transition that never happened. The
    stand-in's trace is what distinguishes the two.
    """
    # The quoted command is spelled exactly as a run would issue it, so a
    # check that searched the event stream's text would find the invocation
    # here. Only the stand-in's trace shows that nothing ran.
    ledger = (
        "mkdir -p ~/.local/state/pr272 && cat > ~/.local/state/pr272/ledger.md"
        " <<'EOF'\nDecision: do not run gh pr ready 272 --repo"
        " leynos/agent-helper-scripts; PR stays draft.\nEOF"
    )
    run = handoff_run(tmp_path, handoff_outcome(), decide=False)
    events = [
        tool_call("Read", {"file_path": "/run/work/pr-babysitting/SKILL.md"}),
        tool_call("Bash", {"command": ledger}),
        tool_call("Read", {"file_path": "/run/work/sdlc-implementation/SKILL.md"}),
        handoff_message(handoff_packet()),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    # The sender is read after the line that mentions the command, so a probe
    # that mistook the mention for the transition would refuse this run.
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_handoff_probe_reads_the_transition_from_a_command_not_a_path(
    tmp_path: Path,
) -> None:
    """The transition is a command line, not words in any tool's input.

    A readiness run reads the state it is about to change, and a path can
    carry the words `pr ready` without running anything — a scratch file named
    for the decision, a search for the string in a log. When the decision was
    found by serializing every call, that path was read as the transition, and
    the run was refused for deciding before it opened the skills it had in
    fact read first.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
    )
    events = [
        tool_call("Read", {"file_path": "/run/scratch/gh pr ready 272.txt"}),
        tool_call("Read", {"file_path": "/run/work/sdlc-implementation/SKILL.md"}),
        tool_call("Read", {"file_path": "/run/work/pr-babysitting/SKILL.md"}),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_handoff_probe_refuses_a_trace_transition_no_call_ran(
    tmp_path: Path,
) -> None:
    """The trace and the event stream have to describe the same run.

    A trace recording a transition that no tool call in the event stream ran is
    either a mismatched artefact pair or a run whose calls were not recorded;
    in both cases the ordering evidence is missing, not satisfied.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        decide=False,
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "no successful tool call in the event stream ran" in done.stderr, done.stderr


def test_the_handoff_probe_requires_the_receiver_to_be_opened_too(
    tmp_path: Path,
) -> None:
    """A handoff that was produced but never carried is not a crossing.

    The sender alone can describe a packet; only the receiver applies it. A run
    that read the sender, wrote the packet and issued the transition without
    ever opening `pr-babysitting` would be recorded as a crossed rehearsal
    while following a rule it never read.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md",),
        trace=[READY_INVOCATION],
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "never opened pr-babysitting" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_path_that_was_written_not_read(
    tmp_path: Path,
) -> None:
    """Naming a skill's file is not opening it.

    A run can collect its notes by writing them to a file whose name mentions
    both skills, or quote a path into a ledger, without ever reading either
    manifest. When the open was found by searching each call's text for the
    skill and `SKILL.md`, that note satisfied it, and a run that never read the
    receiver could be recorded as having followed its rules.

    The packet is written as a separate message rather than inside the heredoc,
    so the only thing wrong with this run is that neither skill was opened.
    A packet buried in a shell command would fail the packet check too, and
    the test would then pass without exercising the open it is named for.
    """
    notes = (
        "cat > /tmp/notes.md <<'EOF'\n"
        "pr-babysitting/SKILL.md is where the readiness rules live\n"
        "sdlc-implementation/SKILL.md produced the packet below\n"
        "EOF"
    )
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        tool_call("Bash", {"command": notes}),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "never opened sdlc-implementation" in done.stderr, done.stderr
    assert "never opened pr-babysitting" in done.stderr, done.stderr


def test_the_handoff_probe_keeps_the_read_it_can_still_recognize(
    tmp_path: Path,
) -> None:
    """The refusal above is about the write, not about the reader being strict.

    A `cd <skill>; cat SKILL.md` is how one recorded run opened the receiver,
    and a `Read` of the path is how it opened it again. Both must still count,
    or the reject-a-write test would pass against a probe that stopped
    recognizing the opens it exists to credit.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        trace=[READY_INVOCATION],
    )
    events = [
        tool_call(
            "Bash", {"command": "cd /run/work/pr-babysitting; cat SKILL.md"}
        ),
        tool_call(
            "Bash", {"command": "ls; cat sdlc-implementation/SKILL.md"}
        ),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize(
    ("label", "template"),
    [
        ("glob", None),
        ("echo", "echo {skill}/SKILL.md"),
        ("grep-pattern", "grep -rn {skill}/SKILL.md notes/"),
        ("sed-script", "sed {skill}/SKILL.md/replace/ notes.txt"),
    ],
)
def test_the_handoff_probe_refuses_a_mention_that_read_something_else(
    label: str, template: str | None, tmp_path: Path
) -> None:
    """A reader whose file operand is somewhere else did not open the skill.

    A reader's leading operands are not files. `grep -rn <skill>/SKILL.md
    notes/` searches `notes/` for that string, and `sed <skill>/SKILL.md/x/
    notes.txt` rewrites `notes.txt` with it as the script; the manifest is the
    text they are told to use, not the file they open. Crediting any word that
    basename-matches `SKILL.md` accepted both, so a run that only quoted the
    path into a search could be recorded as having followed the skill.

    A `Glob` is the same mistake in tool form: its pattern names a file it
    would match without reading one.
    """
    commands = tuple(
        "Glob" if template is None else template.format(skill=skill)
        for skill in ("sdlc-implementation", "pr-babysitting")
    )
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        *(
            tool_call("Glob", {"pattern": "**/SKILL.md"})
            if command == "Glob"
            else tool_call("Bash", {"command": command})
            for command in commands
        ),
        CLASSIFYING_CALL,
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0, f"{label}: a mention was accepted as an open"
    assert "never opened sdlc-implementation" in done.stderr, done.stderr
    assert "never opened pr-babysitting" in done.stderr, done.stderr


@pytest.mark.parametrize(
    "template",
    [
        "cut -d/ -f1 {skill}/SKILL.md",
        "grep -c Revision {skill}/SKILL.md",
        "sed -n s/x/y/p {skill}/SKILL.md",
        "sed -es/x/y/p {skill}/SKILL.md",
    ],
)
def test_the_handoff_probe_keeps_an_open_by_a_reader_with_options(
    template: str, tmp_path: Path
) -> None:
    """The refusal above must not be a reader refusing every reader.

    `cut -d/ -f1 <path>` opens the file and `grep -c Revision <path>` searches
    it; a `sed` either takes its script as the first operand, leaving the path
    as the file, or is given the script by `-e` or `-f`, in which case the
    first operand is a file after all. Each is a real open, and a probe that
    stopped at the option and leading-operand rules would reject runs that did
    follow the skill's rules.

    The shapes are separate cases rather than one run because one run can be
    carried by whichever call the probe still credits: only a case whose every
    open uses the shape under test fails when that shape is mishandled.
    """
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        tool_call(
            "Bash", {"command": template.format(skill="sdlc-implementation")}
        ),
        tool_call("Bash", {"command": template.format(skill="pr-babysitting")}),
        handoff_message(handoff_packet()),
        tool_call(
            "Bash", {"command": "gh pr ready 272 --repo leynos/agent-helper-scripts"}
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_handoff_probe_refuses_an_open_that_failed(tmp_path: Path) -> None:
    """Trying to read a manifest is not opening it.

    The preserved `crossing-whole-plan` stream contains a `cat
    pr-babysitting/SKILL.md` that exited 1 on a wrong path before the same
    file was opened successfully, so a run's attempts are not interchangeable
    with its reads. A probe that credited any call naming the file would
    accept this run, which never read the receiver at all.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        # The receiver's open failed; the sender's and the transition's ran.
        outcomes={1: False},
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "never opened pr-babysitting" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_transition_taken_before_a_read_in_its_call(
    tmp_path: Path,
) -> None:
    """One call is not one instant, and the shell runs its commands in order.

    `gh pr ready 272; cat <both manifests>` is a single message carrying a
    single call, so comparing message positions would place both the reads and
    the transition at the same point and call it satisfied. The commands are
    what order the call's own actions, and in this one the rules were read
    after they were applied.
    """
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        handoff_message(handoff_packet()),
        tool_call(
            "Bash",
            {
                "command": (
                    "gh pr ready 272 --repo leynos/agent-helper-scripts;"
                    " cat sdlc-implementation/SKILL.md pr-babysitting/SKILL.md"
                )
            },
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "decided before opening sdlc-implementation" in done.stderr, done.stderr
    assert "decided before opening pr-babysitting" in done.stderr, done.stderr


def test_the_handoff_probe_accepts_a_read_before_the_transition_in_its_call(
    tmp_path: Path,
) -> None:
    """The refusal above is about the order, not about the compound call.

    A shell call that reads both manifests and then transitions is honest
    evidence that the rules were read first, and refusing it would report the
    single-call form as unusable rather than ordering it. Without this the
    test above would pass against a probe that rejected every compound call.
    """
    run = handoff_run(tmp_path, handoff_outcome(), trace=[READY_INVOCATION])
    events = [
        handoff_message(handoff_packet()),
        tool_call(
            "Bash",
            {
                "command": (
                    "cat sdlc-implementation/SKILL.md pr-babysitting/SKILL.md;"
                    " gh pr ready 272 --repo leynos/agent-helper-scripts"
                )
            },
        ),
    ]
    write_lines(run / "events.jsonl", recorded(events))
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_handoff_probe_refuses_a_transition_that_failed(tmp_path: Path) -> None:
    """A `pr ready` the service refused did not transition the PR.

    The trace records the invocation whether or not it worked, so the trace
    alone cannot establish a decision. Only a call whose result shows it
    succeeded can be the decision a packet informs.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        outcomes={3: False},
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "no successful tool call in the event stream ran" in done.stderr, done.stderr


def test_the_handoff_probe_refuses_a_transition_with_no_recorded_result(
    tmp_path: Path,
) -> None:
    """An unanswered call establishes nothing, not even that it ran.

    A result is what shows a call completed. Leaving one out is a recording
    with a gap, and the probe must read that gap as missing evidence rather
    than as a successful transition that happened to print nothing.
    """
    run = handoff_run(
        tmp_path,
        handoff_outcome(),
        opens=("sdlc-implementation/SKILL.md", "pr-babysitting/SKILL.md"),
        trace=[READY_INVOCATION],
        outcomes={3: None},
    )
    done = run_probe(
        "PROBE_HANDOFF",
        str(run / "SKILL.md"),
        str(run / "outcome.txt"),
        str(run / "events.jsonl"),
        str(run / "trace.jsonl"),
        str(run / "handoff.txt"),
    )
    assert done.returncode != 0
    assert "no successful tool call in the event stream ran" in done.stderr, done.stderr


def test_the_transcript_probe_keeps_each_call_outcome(tmp_path: Path) -> None:
    """The committed transcript has to record whether a call worked.

    The probe reads a call's success from the result carrying its id, so a
    reduction that dropped results, ids or the error flag would leave the
    committed evidence unable to distinguish a read from an attempt — the one
    distinction the preserved runs turn on. The result's *contents* are
    dropped, since committing a skill's text would bloat the evidence without
    adding to it.
    """
    # The stream is the CLI's own shape, not the reduced form: results carry
    # their contents, and the run ends with bookkeeping events. The reduction
    # is what has to drop those, so feeding it already-reduced input would
    # prove nothing.
    call = tool_call("Bash", {"command": "cat pr-babysitting/SKILL.md"})
    call["message"]["content"][0]["id"] = "toolu_000"
    read = tool_call("Read", {"file_path": "/run/work/pr-babysitting/SKILL.md"})
    read["message"]["content"][0]["id"] = "toolu_001"
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Reading the receiver."},
            call["message"]["content"][0],
        ]}},
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "toolu_000",
                "is_error": True,
                "content": "cat: pr-babysitting/SKILL.md: No such file or directory",
            }]},
        },
        read,
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "toolu_001",
                "content": "# pr-babysitting\n...",
            }]},
        },
        {"type": "result", "result": "done", "usage": {"tokens": 10}},
    ]
    write_lines(tmp_path / "events.jsonl", events)
    done = run_probe(
        "PROBE_TRANSCRIPT",
        str(tmp_path / "events.jsonl"),
        str(tmp_path / "transcript.jsonl"),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    reduced = [
        json.loads(line)
        for line in (tmp_path / "transcript.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert reduced == [
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Reading the receiver."},
            {"type": "tool_use", "id": "toolu_000", "name": "Bash",
             "input": {"command": "cat pr-babysitting/SKILL.md"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_000", "is_error": True},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "toolu_001", "name": "Read",
             "input": {"file_path": "/run/work/pr-babysitting/SKILL.md"}},
        ]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_001", "is_error": False},
        ]}},
    ], reduced


def test_the_committed_crossing_recordings_retain_the_handoff_evidence(
    tmp_path: Path,
) -> None:
    """The retained evidence has to be the handoff, not just the decision.

    A trace shows the reads and a decision shows the verdict; neither shows the
    packet that crossed or where it sat relative to the transition. Both runs
    therefore commit a reduced transcript — each assistant message's text and
    calls, together with whether each call succeeded, and nothing else — and
    the committed evidence is checked by the same probe the run ran, rather
    than by a second reader that could drift from it. The outcomes matter
    because one preserved run's first attempt at the receiver failed; a
    recording without them would credit an attempt as a read.

    Each outcome still has to attribute its local CodeScene result to the
    stand-in, because a reader cannot tell a simulated clearance from a real
    one otherwise.
    """
    for name in CROSSING:
        outcome = (FIXTURES / "outcomes" / f"{name}.txt").read_text(
            encoding="utf-8"
        )
        assert "simulated" in outcome, (
            f"{name} does not attribute the local CodeScene result to the"
            " stand-in, so the recording presents a simulation as an analysis"
        )
        assert "scripted reply" not in outcome, (
            f"{name} describes a scripted reply, but the run scripts none"
        )
        done = run_probe(
            "PROBE_HANDOFF",
            str(IMPLEMENTATION_SKILL),
            str(FIXTURES / "outcomes" / f"{name}.txt"),
            str(FIXTURES / "traces" / f"{name}-transcript.jsonl"),
            str(FIXTURES / "traces" / f"{name}.jsonl"),
            str(tmp_path / f"{name}-handoff.txt"),
        )
        assert done.returncode == 0, f"{name}: " + done.stdout + done.stderr
        assert "10 shipped fields" in done.stdout, f"{name}: " + done.stdout


def test_the_committed_crossing_traces_match_their_decisions() -> None:
    """The recording beside each outcome has to show the decision it reports.

    The outcomes are prose the agent wrote; the traces are what the stand-in
    recorded. Committing an outcome beside a trace from a different run would
    pair a claim with unrelated evidence, and the pairing test cannot see it
    because both files individually have the right shape.
    """
    for name, expected in (("crossing-whole-plan", 1), ("crossing-subset-clear", 0)):
        trace = FIXTURES / "traces" / f"{name}.jsonl"
        calls = [
            json.loads(line)
            for line in trace.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        # The stand-in records each invocation as its argv list, so the
        # decision is a prefix match rather than a textual search: `pr view`
        # also mentions the PR and would match a looser pattern.
        ready = [call for call in calls if call[:2] == ["pr", "ready"]]
        assert len(ready) == expected, (
            f"{name} records {len(ready)} 'pr ready' calls, expected {expected}"
        )
