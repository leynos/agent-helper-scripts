"""Contract regressions for the readiness agent-boundary stand-in.

The stand-in stands in for `gh` inside the rehearsal sandbox, so a route it
answers wrongly changes the evidence a recording provides rather than merely
failing a command. Each case here pins one such route against the behaviour
the real client has: a write stays a write however its flags are spelled, and a
filter is applied to JSON or refused outright.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

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


def posted(run: Path) -> dict:
    """Return the comment the run recorded, failing clearly when none was.

    Reading `state.json` directly would report a missing file, which says
    nothing about the defect. Naming the absent record instead shows that the
    write was answered as a read.
    """
    state = run / "state.json"
    assert state.exists(), "no comment was recorded: the write was treated as a read"
    return json.loads(state.read_text(encoding="utf-8"))["posted"]


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
    assert f"unsupported {expected} user" in done.stderr


def test_explicit_read_method_still_serves_the_user_route(run: Path) -> None:
    """An explicit GET keeps the route readable, so the refusal is about method."""
    done = invoke(run, "api", "--method", "GET", "user", "--jq", ".login")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip()


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
    assert "unsupported POST graphql" in done.stderr


def test_a_graphql_read_query_is_still_answered(run: Path) -> None:
    """The readiness run's review-thread query keeps working, so the test bites."""
    done = invoke(run, "api", "graphql", "-f", f"query={GRAPHQL_READ}")
    assert done.returncode == 0, done.stderr
    assert "reviewThreads" in done.stdout


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
    assert "unsupported POST graphql" in done.stderr


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
    assert "unsupported POST graphql" in done.stderr


def test_a_subscription_is_not_answered_from_the_recorded_reads(run: Path) -> None:
    """A subscription is a request the stand-in cannot answer, so it must refuse.

    It is neither the recorded query nor a flat mutation, so treating anything
    that is not a mutation as readable would answer it from the read facts.
    """
    done = invoke(run, "api", "graphql", "-f", "query=subscription{prUpdated}")
    assert done.returncode == 2, done.stdout
    assert "unsupported POST graphql" in done.stderr


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
    assert f"unsupported {expected} graphql" in done.stderr


def test_an_explicit_get_graphql_read_is_refused(run: Path) -> None:
    """A GET is how the real client reads a REST path, not a GraphQL document.

    `gh api graphql` is a POST; a GET naming `graphql` with a query field is
    not a call the service supports, so the stand-in must not answer it as one.
    """
    done = invoke(
        run, "api", "--method", "GET", "graphql", "-f", f"query={GRAPHQL_READ}"
    )
    assert done.returncode == 2, done.stdout
    assert "unsupported GET graphql" in done.stderr


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
    record = posted(run)
    assert record["body"] == "equals-form"
    assert record["user"]["login"] == "fixture-commenter"


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
    assert posted(run)["body"] == "from a file"


def test_pr_view_applies_a_filter(run: Path) -> None:
    """`gh pr view --jq` answers the filtered value, not the whole PR object."""
    done = invoke(run, "pr", "view", "272", "--json", "isDraft", "--jq", ".isDraft")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() in {"true", "false"}


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
    assert done.stdout.strip()


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
    assert json.loads(done.stdout)["id"] == ident


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
    assert scene["output"]["annotations_count"] > 0
    assert "Complex Method" in scene["output"]["summary"]
    # The finding must name code this candidate changes, or it is evidence about
    # a different PR and the run would be reasoning about the wrong thing.
    changed = json.loads(
        invoke(tmp_path, "api", "repos/leynos/agent-helper-scripts/pulls/272/files").stdout
    )
    paths = {entry["filename"] for entry in changed}
    assert "skills/pr-babysitting/scripts/readiness_gate.py" in paths


def test_a_clone_fails_for_the_reason_the_sandbox_supplies(run: Path) -> None:
    """A clone is refused as unreachable, not as a command `gh` lacks.

    The sandbox has no route to GitHub, so a clone cannot succeed; reporting it
    as an unsupported invocation would say the client has no such command,
    which is a different and misleading fact about the environment.
    """
    done = invoke(run, "repo", "clone", "leynos/agent-helper-scripts")
    assert done.returncode != 0
    assert "Could not resolve host" in done.stderr
    assert "unsupported invocation" not in done.stderr


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
    assert "--jq is not supported on this route" in done.stderr


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
    assert done.stdout.strip()


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
    assert done.returncode != 0
    assert "401" in done.stderr
    assert not (run / "state.json").exists()


def test_a_refused_post_does_not_displace_an_earlier_one(run: Path) -> None:
    """A rejected follow-up must not erase the comment that was accepted.

    `state.json` is the record of what the run posted. Writing an empty body
    over it would lose the earlier comment and present the run as having posted
    nothing, which misstates its own trace.
    """
    first = invoke(run, "api", COMMENT_ROUTE, "-f", "body=first", token=POOL_TOKEN)
    assert first.returncode == 0, first.stderr
    refused = invoke(run, "api", COMMENT_ROUTE, "-f", "body=", token=POOL_TOKEN)
    assert refused.returncode != 0
    assert posted(run)["body"] == "first"


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
    assert refused.returncode != 0
    assert "401" in refused.stderr
    assert posted(run) == before, "a refused POST rewrote the accepted comment"
    ident = before["id"]
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
    ident = posted(run)["id"]
    url = f"repos/leynos/agent-helper-scripts/issues/comments/{ident}"
    single = invoke(run, "api", url)
    assert single.returncode == 0, single.stderr
    assert json.loads(single.stdout)["body"] == "hello"
    listing = invoke(run, "api", COMMENT_ROUTE)
    assert any(
        item["id"] == ident and item["body"] == "hello"
        for item in json.loads(listing.stdout)
    )
    assert invoke(run, "pr", "ready", "272").returncode == 0
    assert posted(run)["body"] == "hello", "the transition dropped the comment"
    assert json.loads((run / "state.json").read_text())["isDraft"] is False
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


def write_mode(directory: Path, mode: str) -> None:
    """Record the local CodeScene mode the run should answer with."""
    (directory / "facts.json").write_text(
        json.dumps({"cs_mode": mode}), encoding="utf-8"
    )


def test_the_simulated_cs_discloses_itself_on_every_answer(cs_run: Path) -> None:
    """No answer can be mistaken for a real CodeScene analysis.

    The stand-in fabricates its output, so a recording that quoted it without
    the disclosure would be evidence for a result no service produced.
    """
    write_mode(cs_run, "clean")
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    assert "simulated output for rehearsal" in done.stderr
    assert "not a CodeScene analysis" in done.stderr


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
    assert done.returncode == status
    assert needle in done.stdout


@pytest.mark.parametrize(
    "setup", [None, "not json", json.dumps({"cs_mode": "invented"})],
    ids=["no-facts", "malformed", "unknown-mode"],
)
def test_the_simulated_cs_fails_closed_without_a_recorded_mode(
    cs_run: Path, setup: str | None
) -> None:
    """A missing or unrecognized mode reports unavailable, never clean.

    Defaulting to `clean` would let a broken fixture manufacture the clearance
    the rehearsal exists to check, which is the failure mode the rule names.
    """
    if setup is not None:
        (cs_run / "facts.json").write_text(setup, encoding="utf-8")
    done = invoke_cs(cs_run, "delta", "base", "HEAD")
    assert done.returncode == 1
    assert "License check failed" in done.stdout


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
    assert "the served state still reads draft" in runner


def test_the_runner_requires_the_local_codescene_result_before_readiness() -> None:
    """A permitting run that never invoked `cs` has waived the local gate.

    The rule says an unevaluable source is not a clear one, so the runner has to
    fail a run that marked ready without consulting the local result at all.
    """
    runner = RUNNER.read_text()
    assert '[ "$EXPECT_READY" = yes ] && [ ! -s "$CS_TRACE" ]' in runner
    assert "marked the PR ready without invoking the local CodeScene check" in runner


def test_the_runner_requires_the_plan_read_before_the_transition() -> None:
    """The revision is reconciled against the plan file, so the read comes first.

    Accepting the verdict's own echo would clear a revision the reviewer never
    saw, which is the superseded-revision defect the rule exists to prevent.
    """
    runner = RUNNER.read_text()
    assert "contents/docs/execplans/.*ref=" in runner
    assert "read the plan after the transition, not before it" in runner


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
        single = facts["api"][r"/commits/[0-9a-f]+$"]["commit"]["message"]
        assert view == pulls == single, (
            f"{facts_path.parent.name} gives three messages for one head: "
            f"{view!r}, {pulls!r}, {single!r}"
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
    assert "PROBE_PLAN" in runner
    assert "did not read the plan at the head it is judging" in runner
    assert "candidate_refs" in runner
    # The head is what makes a read candidate-bound, so the probe has to name
    # it rather than accept whatever ref the trace carries.
    assert 'pr.get("headRefOid", "")' in runner


PLAN_ROUTE = "repos/leynos/agent-helper-scripts/contents/docs/execplans/271-plan.md"


def plan_read(ref: str) -> list[str]:
    """Return the argv of a plan read at one ref."""
    return ["api", "-H", "Accept: application/vnd.github.raw", f"{PLAN_ROUTE}?ref={ref}"]


def answer(argv: list[str], status: int = 0, stdout: str = "the plan\n") -> dict:
    """Return one line of the stand-in's answer record."""
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
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan))
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
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan))
    assert done.returncode != 0, "a base read was accepted as the candidate's plan"
    assert "no candidate-bound plan read before the transition" in done.stderr


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
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan))
    assert done.returncode != 0, "a failed candidate read was accepted"
    assert "candidate-bound plan read failed" in done.stderr


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
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan))
    assert done.returncode != 0, "an empty candidate read was accepted"
    assert "candidate-bound plan read returned nothing" in done.stderr


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
    done = run_probe("PROBE_PLAN", str(trace), str(answers), str(whole_plan))
    assert done.returncode != 0
    assert "disagree in length" in done.stderr


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
    assert done.returncode != 0
    assert "no isDraft read after the transition" in done.stderr


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
    assert done.returncode != 0
    assert "no read-back returned a ready state" in done.stderr


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
    assert done.returncode != 0
    assert "failed" in done.stderr


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
        json.dumps({"isDraft": True, "posted": {"id": 1, "body": "probe"}}),
        encoding="utf-8",
    )
    kept = run_probe("PROBE_AUTHZ", str(state))
    assert kept.returncode == 0, kept.stderr
    state.write_text(
        json.dumps({"isDraft": True, "posted": {"id": 1, "body": "injected"}}),
        encoding="utf-8",
    )
    overwritten = run_probe("PROBE_AUTHZ", str(state))
    assert overwritten.returncode != 0, "a rewritten comment was accepted as refused"
    assert "changed the recorded comment" in overwritten.stderr


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
    assert "stand-in for the local CodeScene check" in runner
    assert "Treat its answer as the local result for this" in runner
    for answer in ("No issues found", "License check failed", "New issue"):
        assert answer not in runner, (
            "the prompt must not reveal which local result the run will get"
        )
    """A scenario written to permit cannot carry a finding or unavailable mode.

    Recording that pairing would file, as evidence, a run whose facts
    contradict the decision the runner is checking for.
    """
    runner = RUNNER.read_text()
    for mode in ("unavailable", "finding"):
        assert f'"$CS_MODE" = {mode}' in runner
