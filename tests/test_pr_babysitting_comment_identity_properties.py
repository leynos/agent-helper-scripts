"""Property-test the shipped PR comment helper's routing and redaction invariant.

For generated pools, selections, identities, bodies, identifiers and service
failures, with or without wrapper noise on standard error, the helper must
select one token, read the lifecycle account without token variables, use only
the selected token for the identity check and post, never retry or fall back,
preserve the body exactly, and keep diagnostics free of credentials and account
names.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from hypothesis import given, settings, strategies as st
import pytest

from pr_babysitting_comment_test_support import (
    OWNER,
    URL,
    PostResult,
    Scenario,
    assert_bounded_diagnostics,
    assert_success_diagnostics,
    make_harness,
    run_post,
)


FAILURES = [("", 0)] + [(stage, code) for stage in ("GET", "POST") for code in (401, 403, 429)]
CATEGORIES = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}
BODIES = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1, max_size=200,
)


@st.composite
def pools(draw: st.DrawFn) -> tuple[tuple[str, ...], str]:
    """Draw unique tokens and render them with comments, blanks and CRLF endings."""
    tokens = tuple(draw(st.lists(
        st.from_regex(r"tok-[A-Za-z0-9_-]{4,16}", fullmatch=True),
        min_size=1, max_size=5, unique=True,
    )))
    lines: list[str] = []
    for token in tokens:
        lines.extend(draw(st.lists(st.sampled_from(["", "# note", "   # indented note"]), max_size=2)))
        lines.append(token)
    ending = draw(st.sampled_from(["\n", "\r\n"]))
    return tokens, ending.join(lines) + ending


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Draw one complete posting scenario."""
    tokens, pool = draw(pools())
    stage, code = draw(st.sampled_from(FAILURES))
    owner_case = draw(st.lists(st.booleans(), min_size=len(OWNER), max_size=len(OWNER)))
    pool_is_owner = draw(st.booleans())
    login = "".join(c.upper() if up else c for c, up in zip(OWNER, owner_case)) if pool_is_owner else None
    return Scenario(
        selected=draw(st.integers(0, len(tokens) - 1)),
        inline=draw(st.booleans()), login=login,
        failure_stage=stage, failure_code=code, pool=pool, tokens=tokens,
        inherited=draw(st.booleans()), stderr_noise=draw(st.booleans()), body=draw(BODIES),
        pr=draw(st.integers(1, 10**6)), comment_id=draw(st.integers(1, 10**12)),
    )


@dataclass(frozen=True)
class _Expectation:
    methods: list[str]
    returncode: int
    category: str | None


def _expect(scenario: Scenario) -> _Expectation:
    """Derive the single outcome the scenario's identity and failure settings allow."""
    if scenario.failure_stage == "GET":
        return _Expectation(["GET"], 1, CATEGORIES[scenario.failure_code])
    if scenario.login is not None:
        return _Expectation(["GET"], 2, "unexpected_owner_identity")
    if scenario.failure_stage == "POST":
        return _Expectation(["GET", "POST"], 1, CATEGORIES[scenario.failure_code])
    return _Expectation(["GET", "POST"], 0, None)


def _check(run: PostResult, scenario: Scenario) -> None:
    """Assert the routing, retry, body and redaction invariant for one run."""
    expected = _expect(scenario)
    assert run.choices == [{"count": len(scenario.tokens), "index": scenario.selected}], (
        "select exactly one token from the parsed pool records"
    )
    assert len(run.lifecycle) == 1, "read the lifecycle account exactly once, without token variables"
    assert [call["method"] for call in run.scoped] == expected.methods, "never retry or fall back"
    assert run.result.returncode == expected.returncode, run.result.stderr
    assert run.diagnostics()[-1]["failure_category"] == expected.category, "classify the outcome"
    if "POST" in expected.methods:
        assert run.scoped[-1]["args"][5] == scenario.endpoint, "post to the scenario's endpoint"
        assert run.scoped[-1]["payload"] == {"body": scenario.body}, "preserve the body exactly"
    if expected.returncode == 0:
        assert run.result.stdout == URL + "\n", "a successful post prints only the comment URL"
        assert_success_diagnostics(run, scenario)
    else:
        assert URL not in run.result.stdout, "a failed or blocked post must not report a comment"
    assert_bounded_diagnostics(run, scenario)


@pytest.mark.slow
@settings(max_examples=30, deadline=None)
@given(scenario=scenarios())
def test_helper_routes_one_selected_token_and_redacts_diagnostics(scenario: Scenario) -> None:
    """Every generated scenario satisfies the helper's routing and redaction invariant."""
    with tempfile.TemporaryDirectory() as root:
        harness = make_harness(Path(root))
        _check(run_post(harness, scenario), scenario)
