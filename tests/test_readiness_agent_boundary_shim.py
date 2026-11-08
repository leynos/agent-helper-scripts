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
SCENARIO = FIXTURES / "scenarios" / "current-whole-plan" / "facts.json"
POOL_TOKEN = "fixture-pool-token"


@pytest.fixture
def run(tmp_path: Path) -> Path:
    """Place a runnable copy of the stand-in beside one scenario's facts.

    The stand-in derives its run directory from its own location, so copying
    it here is enough to point it at this test's facts; no environment variable
    can redirect it.
    """
    shim = tmp_path / "gh"
    shutil.copy2(SHIM, shim)
    shutil.copy2(SCENARIO, tmp_path / "facts.json")
    shim.chmod(0o755)
    return tmp_path


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
