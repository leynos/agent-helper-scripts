"""Exercise the shipped comment helper with dummy principals and no network."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess

import pytest

from pr_babysitting_comment_test_support import (
    HELPER,
    OWNER,
    ROOT,
    URL,
    BODY,
    CommentHarness,
    Scenario,
    assert_bounded_diagnostics,
    assert_success_diagnostics,
    make_harness,
    run_post,
)


COMMENTS = ROOT / "skills/pr-babysitting/references/comments.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"


@pytest.fixture
def manual_comment_harness(tmp_path: Path) -> CommentHarness:
    """Provision a private home, token pool and executable doubles per test."""
    return make_harness(tmp_path)


@pytest.mark.parametrize("selected", range(3), ids=["first-account", "second-account", "third-account"])
@pytest.mark.parametrize("inline", [False, True], ids=["issue-comment", "inline-reply"])
@pytest.mark.parametrize("inherited", [False, True], ids=["stored-owner", "environment-owner"])
def test_non_owner_pool_principal_posts_without_changing_lifecycle_identity(
    manual_comment_harness: CommentHarness, selected: int, inline: bool, inherited: bool,
) -> None:
    """All three authorized non-owner accounts work for both comment surfaces."""
    scenario = Scenario(selected=selected, inline=inline, inherited=inherited)
    run = run_post(manual_comment_harness, scenario)
    assert run.result.returncode == 0, run.result.stderr
    assert run.result.stdout == URL + "\n", "posting must return the comment URL"
    assert len(run.lifecycle) == 1, "look up the lifecycle account once"
    assert [call["method"] for call in run.scoped] == ["GET", "POST"], "verify selected identity then post once"
    assert all(call["principal"] == f"comment-agent-{selected}" for call in run.scoped), "check and post must use the same non-owner identity"
    assert run.scoped[-1]["args"][5] == scenario.endpoint, "use the correct comment endpoint"
    assert run.scoped[-1]["payload"] == {"body": BODY}, "preserve the complete literal Markdown body"
    assert run.choices == [{"count": 3, "index": selected}], "choose once, not by searching for the owner"
    assert_success_diagnostics(run, scenario)


@pytest.mark.parametrize("inline", [False, True], ids=["issue-comment", "inline-reply"])
def test_gh_standard_error_noise_does_not_corrupt_logins_or_urls(
    manual_comment_harness: CommentHarness, inline: bool,
) -> None:
    """Wrapper diagnostics on standard error leave the logins, checks, and URL intact."""
    scenario = Scenario(inline=inline, stderr_noise=True)
    run = run_post(manual_comment_harness, scenario)
    assert run.result.returncode == 0, run.result.stderr
    assert run.result.stdout == URL + "\n", "only the comment URL reaches standard output"
    assert_success_diagnostics(run, scenario)


def test_each_invocation_has_its_own_run_id(manual_comment_harness: CommentHarness) -> None:
    """Run IDs correlate one invocation's diagnostics without colliding across runs."""
    first = run_post(manual_comment_harness)
    second = run_post(manual_comment_harness)
    assert first.result.returncode == second.result.returncode == 0, "both fixture posts must succeed"
    assert first.diagnostics()[0]["run_id"] != second.diagnostics()[0]["run_id"], (
        "separate invocations must not share a run ID"
    )


@pytest.mark.parametrize("login", [OWNER, OWNER.upper(), "", "bad login"], ids=["owner", "owner-case", "empty", "malformed"])
def test_unexpected_identity_blocks_before_posting(
    manual_comment_harness: CommentHarness, login: str,
) -> None:
    """Owner or invalid identity results are configuration errors, not fallback triggers."""
    scenario = Scenario(login=login)
    run = run_post(manual_comment_harness, scenario)
    assert run.result.returncode != 0, "unexpected identity must stop the operation"
    assert [call["method"] for call in run.scoped] == ["GET"], "no POST after an invalid identity"
    assert len(run.choices) == 1, "do not search for another token after rejection"
    assert URL not in run.result.stdout, "blocked operation must not report a comment"
    diagnostic = run.diagnostic("identity_preflight")
    expected_category = (
        "unexpected_owner_identity"
        if login and login.lower() == OWNER
        else "invalid_identity_response"
    )
    assert diagnostic["failure_category"] == expected_category, "classify the identity failure"
    assert diagnostic["exit_status"] == 2, "identity configuration errors exit with status 2"
    assert "login" not in diagnostic and "identity" not in diagnostic, (
        "diagnostics must not include the verified account identity"
    )
    assert_bounded_diagnostics(run, scenario)


@pytest.mark.parametrize("stage", ["GET", "POST"], ids=["identity-read", "comment-post"])
@pytest.mark.parametrize("code", [401, 403, 429], ids=["unauthenticated", "forbidden", "rate-limited"])
def test_service_failure_never_changes_identity_or_retries(
    manual_comment_harness: CommentHarness, stage: str, code: int,
) -> None:
    """Real authentication, permission and rate-limit failures remain visible."""
    run = run_post(manual_comment_harness, Scenario(failure_stage=stage, failure_code=code))
    assert run.result.returncode != 0, "service failure must propagate"
    expected = ["GET"] if stage == "GET" else ["GET", "POST"]
    assert [call["method"] for call in run.scoped] == expected, "never retry or fall back to normal authentication"
    assert len(run.lifecycle) == 1, "the lifecycle lookup is never a posting fallback"
    assert len(run.choices) == 1, "never cycle identities after a service failure"
    assert URL not in run.result.stdout, "failed posting must not claim success"
    diagnostic = run.diagnostics()[-1]
    expected_category = {401: "authentication_failed", 403: "permission_denied", 429: "rate_limited"}[code]
    assert diagnostic["stage"] == ("identity_preflight" if stage == "GET" else "post"), "report the failing stage"
    assert diagnostic["failure_category"] == expected_category, "classify the service failure"
    assert diagnostic["http_status"] == code, "keep the recognized HTTP status"
    assert diagnostic["exit_status"] == 1, "propagate the gh exit status"
    assert "fixture service failure" not in run.result.stderr, "do not echo raw service text"


@pytest.mark.parametrize("pool_state", ["missing", "empty"])
def test_unavailable_pool_does_not_use_normal_credentials(
    manual_comment_harness: CommentHarness, pool_state: str,
) -> None:
    """The normally authenticated owner cannot substitute for unavailable pool data."""
    pool = None if pool_state == "missing" else "# fixture credentials only\n\n\n"
    run = run_post(manual_comment_harness, Scenario(pool=pool))
    assert run.result.returncode != 0, "unavailable pool must fail"
    assert run.scoped == [] and run.lifecycle == [], "no GitHub request without a selected pool token"
    diagnostic = run.diagnostic("token_selection")
    assert diagnostic["failure_category"] in {
        "token_pool_unavailable", "token_not_selected",
    }, "classify the unavailable pool"
    assert diagnostic["exit_status"] == 2, "an unavailable pool exits with status 2"


def test_stored_login_failure_without_override_is_classified(
    manual_comment_harness: CommentHarness,
) -> None:
    """A failed lookup with no fallback stops before any pool request, with its category."""
    run = run_post(manual_comment_harness, Scenario(lifecycle_failure=True))
    assert run.result.returncode == 1, "propagate the lookup's exit status"
    assert len(run.lifecycle) == 1 and run.scoped == [], "no pool request before the lifecycle account is known"
    diagnostic = run.diagnostic("lifecycle_identity")
    assert diagnostic["failure_category"] == "authentication_failed", "classify the lookup failure"
    assert diagnostic["http_status"] == 401, "keep the lookup's HTTP status"
    assert diagnostic["exit_status"] == 1, "record the lookup's exit status"
    assert "fixture stored-login failure" not in run.result.stderr, "do not echo raw service text"


def test_malformed_override_is_rejected_before_any_lookup(
    manual_comment_harness: CommentHarness,
) -> None:
    """An invalid override is a configuration error, never a reason to guess."""
    run = run_post(manual_comment_harness, Scenario(lifecycle_override="bad login"))
    assert run.result.returncode == 2, "an invalid override exits with status 2"
    assert run.lifecycle == [] and run.scoped == [], "validate the override before any GitHub request"
    assert run.diagnostic("lifecycle_identity")["failure_category"] == "invalid_lifecycle_override", (
        "classify the invalid override"
    )


def test_override_disagreeing_with_stored_login_fails_closed(
    manual_comment_harness: CommentHarness,
) -> None:
    """A stale override cannot redefine the lifecycle account the stored login names."""
    run = run_post(manual_comment_harness, Scenario(lifecycle_override="someone-else"))
    assert run.result.returncode == 2, "a lifecycle mismatch exits with status 2"
    assert len(run.lifecycle) == 1 and run.scoped == [], "stop before using any pool token"
    assert run.diagnostic("lifecycle_identity")["failure_category"] == "lifecycle_identity_mismatch", (
        "classify the disagreement"
    )


def test_override_agreeing_with_stored_login_posts(manual_comment_harness: CommentHarness) -> None:
    """An override that names the stored login, in any case, does not block posting."""
    run = run_post(manual_comment_harness, Scenario(lifecycle_override=OWNER.upper()))
    assert run.result.returncode == 0, run.result.stderr
    assert [call["method"] for call in run.scoped] == ["GET", "POST"], "post once after the identity check"


def test_override_is_a_fallback_for_an_unavailable_stored_login(
    manual_comment_harness: CommentHarness,
) -> None:
    """When the lookup fails, the override supplies the lifecycle account and still guards the pool."""
    run = run_post(
        manual_comment_harness,
        Scenario(login="override-owner", lifecycle_failure=True, lifecycle_override="Override-Owner"),
    )
    assert run.result.returncode != 0, "a pool token matching the override must be rejected"
    assert len(run.lifecycle) == 1, "the stored lookup runs before the override is used"
    assert run.diagnostic("lifecycle_identity")["failure_category"] is None, "the fallback succeeds"
    assert run.diagnostic("identity_preflight")["failure_category"] == "unexpected_owner_identity", (
        "the pool token must differ from the fallback lifecycle account"
    )


def test_identity_contract_is_explicit_at_each_entrypoint() -> None:
    """Discovery, posting and queue guidance agree about the authorized principal."""
    skill = " ".join(SKILL.read_text().split())
    comments = " ".join(COMMENTS.read_text().split())
    queue = " ".join((ROOT / "skills/comenq-coderabbit/SKILL.md").read_text().split())
    for requirement in (
        "Pool accounts deliberately authenticate as identities other than the lifecycle account",
        "Do not require a pool account to match the repository owner",
        "Do not ask for another confirmation solely because",
        "merges use the normal authorized lifecycle identity",
        "cycling identities after a rate-limit response is not",
        "CodeRabbit rate-limits conversations per commenting account",
        "`scripts/post-manual-comment.sh`",
    ):
        assert requirement in skill, f"missing primary identity contract: {requirement}"
    assert "Do not search the pool for the lifecycle account's token" in comments, "posting guidance must reject owner-matching"
    assert "`scripts/post-manual-comment.sh`" in comments, "posting guidance must name the shipped helper"
    assert "only when that lookup is unavailable" in comments, "posting guidance must describe the override as a fallback"
    assert "pool of accounts other than the lifecycle account is authorized for in-scope manual comments" in queue, "queue guidance must recognize the configured reply route"


def test_lifecycle_identity_contract_names_no_account() -> None:
    """Readiness and merges use stored authentication, verified without naming an owner."""
    skill = " ".join(SKILL.read_text().split())
    for requirement in (
        "as the currently logged-in Linux user with that user's normal `gh` authentication",
        "with `GH_TOKEN` and `GITHUB_TOKEN` removed",
        "is not an account from the comment-token pool",
    ):
        assert requirement in skill, f"missing lifecycle identity contract: {requirement}"
    for document in (SKILL, COMMENTS, HELPER, ROOT / "skills/comenq-coderabbit/SKILL.md"):
        text = document.read_text()
        assert "`leynos`" not in text and "!= leynos" not in text, (
            f"{document.name} must describe the lifecycle account by role, not by name"
        )


def test_helper_is_executable_valid_bash() -> None:
    """Check the shipped helper's mode and syntax without executing any request."""
    assert HELPER.stat().st_mode & 0o111, "the helper must be executable"
    result = subprocess.run(["/bin/bash", "-n", str(HELPER)], text=True,
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 0, result.stderr


SNAPSHOT_SCENARIOS = {
    "issue-comment-success": Scenario(),
    "inline-reply-success": Scenario(inline=True),
    "pool-token-is-owner": Scenario(login=OWNER),
    "identity-read-unauthenticated": Scenario(failure_stage="GET", failure_code=401),
    "post-rate-limited": Scenario(failure_stage="POST", failure_code=429),
    "post-server-error": Scenario(failure_stage="POST", failure_code=500),
    "post-network-error": Scenario(failure_stage="POST", failure_code=0),
    "pool-missing": Scenario(pool=None),
    "stored-login-failure": Scenario(lifecycle_failure=True),
    "invalid-override": Scenario(lifecycle_override="bad login"),
    "override-mismatch": Scenario(lifecycle_override="someone-else"),
}


@pytest.mark.parametrize("name", list(SNAPSHOT_SCENARIOS))
def test_diagnostic_output_contract_snapshot(
    manual_comment_harness: CommentHarness, name: str, snapshot: object,
) -> None:
    """The helper's exit status, output, and diagnostics for each outcome stay stable.

    The clock and run-ID source are replaced, so the snapshot needs no
    placeholders; the semantic assertions below still check redaction.
    """
    scenario = replace(SNAPSHOT_SCENARIOS[name], deterministic=True)
    run = run_post(manual_comment_harness, scenario)
    assert_bounded_diagnostics(run, scenario)
    assert {
        "exit_status": run.result.returncode,
        "stdout": run.result.stdout,
        "diagnostics": run.diagnostics(),
    } == snapshot


@pytest.mark.parametrize(
    ("code", "category", "http_status"),
    [(500, "server_error", 500), (0, "network_error", None)],
    ids=["server-error", "network-error"],
)
def test_post_server_and_network_failures_are_distinguished(
    manual_comment_harness: CommentHarness, code: int, category: str, http_status: int | None,
) -> None:
    """Server and transport failures get their own categories, not a generic one."""
    run = run_post(manual_comment_harness, Scenario(failure_stage="POST", failure_code=code))
    assert run.result.returncode == 1, "propagate the gh exit status"
    diagnostic = run.diagnostic("post")
    assert diagnostic["failure_category"] == category, "classify the failure"
    assert diagnostic["http_status"] == http_status, "keep only a recognized HTTP status"
