"""Behavioural tests for the procedures the Weave skill documents.

These exercise Git's merge-driver boundary with cmd-mox doubles so the skill's
detection, inspection, guard, and bypass recipes are executable rather than
merely asserted as prose. Nothing here tests Weave, and the wiring makes that
structural rather than incidental: Git is pointed at the shim's absolute path
under `EnvironmentManager.shim_dir`, not at a bare command name, so resolution
never consults `PATH` and cannot fall through to a real Weave installation.
The double is named `stub-merge-driver` as a second guard. No assertion depends
on Weave's merge quality. The doubles stand in for any driver with a given exit
status, which is the only part of the contract the documented procedures rely
on.

Two details of this boundary are easy to get wrong:

- A cmd-mox shim reads its standard input, so every Git call passes
  `stdin=DEVNULL`. Inheriting pytest's stdin wedges the shim, and the Git
  process waiting on it.
- Git passes the driver *repository-relative* temporary paths, while a handler
  runs in the pytest process. Handlers therefore resolve `%A` against the
  repository; otherwise they silently write outside it and Git records
  whatever it had already placed in `%A`.

Every repository is isolated from ambient Git state. `GIT_CONFIG_GLOBAL` and
`GIT_CONFIG_SYSTEM` are neutralized, and `core.attributesFile` is pinned to a
per-test file. That last pin matters on its own: the attributes path is not
config-controlled, so a developer's `~/.config/git/attributes` would otherwise
supply `merge=weave` and let a scope assertion pass without the scope under
test contributing anything.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import typing as typ
from pathlib import Path

import pytest
from cmd_mox import CmdMox, EnvironmentManager, skip_if_unsupported

if typ.TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from cmd_mox.ipc import Invocation

GIT = shutil.which("git")

if GIT is None:  # pragma: no cover - Git is a repository test prerequisite.
    raise RuntimeError("git is required to run the Weave procedure tests")

# Deliberately not `weave-driver`. Git is given the shim's absolute path, so
# PATH is never consulted, but the name is kept distinct as a second guard.
DRIVER_NAME = "stub-merge-driver"

BASE_SOURCE = '''\
def alpha() -> str:
    return "base"


def beta() -> str:
    return "base"


def gamma() -> str:
    return "base"
'''

_ALPHA_BASE = 'def alpha() -> str:\n    return "base"'
_BETA_BASE = 'def beta() -> str:\n    return "base"'
_GAMMA_BASE = 'def gamma() -> str:\n    return "base"'
_ALPHA_MAIN = 'def alpha() -> str:\n    return "main"'
_ALPHA_TOPIC = 'def alpha() -> str:\n    return "topic"'
_BETA_FEATURE = 'def beta() -> str:\n    return "feature"'
_GAMMA_TOPIC = 'def gamma() -> str:\n    return "topic"'

MAIN_SOURCE = BASE_SOURCE.replace(_ALPHA_BASE, _ALPHA_MAIN)
TOPIC_SOURCE = BASE_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)
MERGED_SOURCE = MAIN_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)
FEATURE_FIRST_SOURCE = BASE_SOURCE.replace(_BETA_BASE, _BETA_FEATURE)
FEATURE_SECOND_SOURCE = FEATURE_FIRST_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)

# Cherry-pick merges against the picked commit's parent, not the branch point,
# so its outcome is derived from its own three-way inputs rather than reused
# from the merge and rebase expectation. The two values coincide here by
# construction: `main` supplies `alpha`, the picked commit supplies `gamma`,
# and `beta` returns to `base` because the destination never carried the
# groundwork commit and the picked commit did not touch `beta` again.
CHERRY_PICK_SOURCE = BASE_SOURCE.replace(_ALPHA_BASE, _ALPHA_MAIN).replace(
    _GAMMA_BASE, _GAMMA_TOPIC
)

EXPECTED_AFTER_BYPASS = {
    "rebase": MERGED_SOURCE,
    "merge": MERGED_SOURCE,
    "cherry-pick": CHERRY_PICK_SOURCE,
}

CORRUPT_OUTPUT = 'def alpha() -> str:\n    return "main"\n\ndef gamma( -> str:\n'
CONFLICTED_OUTPUT = "<<<<<<< ours\nours\n=======\ntheirs\n>>>>>>> theirs\n"

SCOPES = ("global", "tracked", "clone-local")
OPERATIONS = ("rebase", "merge", "cherry-pick")


def _git(
    repository: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository, isolated from ambient Git state.

    The environment is rebuilt per call so a cmd-mox shim directory added to
    `PATH` during replay is visible to Git.
    """
    return subprocess.run(  # noqa: S603 - absolute executable and controlled arguments.
        [GIT, *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=check,
        timeout=60,
        stdin=subprocess.DEVNULL,
        env=os.environ
        | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )


def _writing_handler(
    repository: Path, content: str, exit_code: int
) -> Callable[[Invocation], tuple[str, str, int]]:
    """Build a driver handler that writes `%A` and reports `exit_code`."""

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        _ancestor, current, _other, _marker_size, _pathname = invocation.args
        # `%A` arrives repository-relative and this handler runs in the pytest
        # process, so it must be resolved before writing.
        (repository / current).write_text(content, encoding="utf-8")
        return ("", "", exit_code)

    return handler


def _conflict_handler() -> Callable[[Invocation], tuple[str, str, int]]:
    """Build a driver handler that only reports an unresolved conflict."""

    def handler(_invocation: Invocation) -> tuple[str, str, int]:
        return ("", "", 1)

    return handler


def _select_scope(repository: Path, scope: str, attributes: Path) -> None:
    """Select `merge=weave` for `*.py` through one attribute scope."""
    rule = "*.py merge=weave\n"
    if scope == "global":
        attributes.write_text(rule, encoding="utf-8")
    elif scope == "clone-local":
        (repository / ".git" / "info" / "attributes").write_text(rule, encoding="utf-8")
    else:  # tracked
        (repository / ".gitattributes").write_text(rule, encoding="utf-8")
        _git(repository, "add", ".gitattributes")


def _wire_driver(repository: Path, environment: EnvironmentManager) -> None:
    """Point `merge.weave.driver` at the shim by absolute path.

    Addressing the shim directly keeps `PATH` out of the resolution, so no
    lookup failure can reach a real driver of the same name.
    """
    assert environment.shim_dir is not None, "cmd-mox must be in replay"
    shim = environment.shim_dir / DRIVER_NAME
    assert shim.exists(), f"cmd-mox must have created a shim at {shim}"
    _git(repository, "config", "merge.weave.name", "stub driver")
    _git(
        repository,
        "config",
        "merge.weave.driver",
        f"{shlex.quote(str(shim))} %O %A %B %L %P",
    )


def _bypass_prefix(repository: Path, scope: str, path: str) -> list[str]:
    """Apply the documented bypass for one scope; return extra Git arguments.

    The global scope is overridden per command with `-c`. The other two scopes
    need a later, path-specific `!merge` rule in `.git/info/attributes`, which
    outranks a tracked rule and outranks earlier lines in the same file.
    """
    if scope == "global":
        return ["-c", "core.attributesFile=/dev/null"]
    info = repository / ".git" / "info" / "attributes"
    existing = info.read_text(encoding="utf-8") if info.exists() else ""
    info.write_text(f"{existing}{path} !merge\n", encoding="utf-8")
    return []


@pytest.fixture
def diverged(tmp_path: Path) -> Iterator[tuple[Path, Path, Path]]:
    """Build a repository ready to diverge, with no merge driver selected.

    The empty pinned attributes file is what keeps the scope assertions honest:
    without it Git falls back to the developer's own global attributes file.
    """
    skip_if_unsupported()
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "example.py"
    attributes = tmp_path / "global-attributes"
    attributes.write_text("", encoding="utf-8")

    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "Weave Skill Test")
    _git(repository, "config", "user.email", "weave-skill@example.invalid")
    _git(repository, "config", "core.attributesFile", str(attributes))
    unselected = _git(repository, "check-attr", "merge", "--", "example.py")
    assert unselected.stdout.rstrip().endswith("merge: unspecified"), (
        "the fixture must start with no merge driver selected from any source"
    )
    source.write_text(BASE_SOURCE, encoding="utf-8")
    _git(repository, "add", "example.py")
    yield repository, source, attributes


def _diverge(repository: Path, source: Path) -> None:
    """Commit the base, then one change on each of `main` and `topic`."""
    _git(repository, "commit", "--quiet", "-m", "base")
    _git(repository, "switch", "--quiet", "--create", "topic")
    source.write_text(TOPIC_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "topic change")
    _git(repository, "switch", "--quiet", "main")
    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main change")


def _diverge_for_cherry_pick(repository: Path, source: Path) -> None:
    """Build a history where cherry-picking forces a three-way merge.

    `git cherry-pick` does not apply a patch; it runs the merge machinery with
    the picked commit's parent as the merge base. `feature` therefore carries
    two commits and only its tip is picked, so that base is the groundwork
    commit rather than the branch point:

        base ── main change (alpha)                     <- ours
          └──── F1 groundwork (beta) ── F2 to pick (gamma)
                        ^ merge base                     ^ theirs

    Both sides then differ from that base — `ours` in `alpha` and `beta`,
    `theirs` in `gamma` — so `example.py` needs a content merge and Git hands
    it to `merge.weave.driver`. The driver invocation is asserted directly by
    the spy's call count, so a history that stopped forcing a merge would fail
    rather than pass quietly.
    """
    _git(repository, "commit", "--quiet", "-m", "base")
    _git(repository, "switch", "--quiet", "--create", "feature")
    source.write_text(FEATURE_FIRST_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "feature groundwork")
    source.write_text(FEATURE_SECOND_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "feature change to pick")
    _git(repository, "switch", "--quiet", "main")
    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main change")


def _prepare(repository: Path, source: Path, operation: str) -> None:
    """Build the history the given operation needs."""
    if operation == "cherry-pick":
        _diverge_for_cherry_pick(repository, source)
    else:
        _diverge(repository, source)


def _start_operation(
    repository: Path, operation: str, prefix: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one of the three operations the skill's fallback table covers."""
    prefix = prefix or []
    if operation == "rebase":
        _git(repository, "switch", "--quiet", "topic")
        return _git(repository, *prefix, "rebase", "main", check=False)
    _git(repository, "switch", "--quiet", "main")
    if operation == "merge":
        return _git(repository, *prefix, "merge", "--no-edit", "topic", check=False)
    return _git(repository, *prefix, "cherry-pick", "feature", check=False)


def _abort(repository: Path, operation: str) -> None:
    """Abort the interrupted operation, as the skill's fallback block does."""
    _git(repository, operation, "--abort")


def test_clean_driver_exit_hides_structural_damage_from_git(
    diverged: tuple[Path, Path, Path],
) -> None:
    """A driver exiting `0` makes Git record unparsable output without complaint."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(_writing_handler(repository, CORRUPT_OUTPUT, 0))
        mox.replay()
        _wire_driver(repository, environment)
        rebased = _start_operation(repository, "rebase")
        assert spy.call_count == 1, "Git must have run the driver for the rebase"

    assert rebased.returncode == 0, (
        "a driver exiting 0 must let Git complete the rebase; the skill's premise "
        f"is that Git raises nothing here, got: {rebased.stderr}"
    )
    assert not _git(repository, "status", "--porcelain").stdout.strip(), (
        "Git must consider the corrupted result fully resolved"
    )

    compiled = subprocess.run(  # noqa: S603 - interpreter path and fixed arguments.
        [sys.executable, "-m", "py_compile", str(source)],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert compiled.returncode != 0, (
        "the documented `python -m py_compile` check must catch what Git did not"
    )


def test_conflicting_driver_leaves_all_three_index_stages_readable(
    diverged: tuple[Path, Path, Path],
) -> None:
    """The documented stage inspection works while a path stays unmerged."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(
            _writing_handler(repository, CONFLICTED_OUTPUT, 1)
        )
        mox.replay()
        _wire_driver(repository, environment)
        merged = _start_operation(repository, "merge")
        assert spy.call_count == 1, "Git must have run the driver for the merge"

    assert merged.returncode != 0, "a driver exiting 1 must leave the merge unresolved"
    unmerged = _git(repository, "diff", "--name-only", "--diff-filter=U")
    assert unmerged.stdout.strip() == "example.py", (
        "the path must remain unmerged so its stages survive"
    )

    stages = {
        stage: _git(repository, "show", f":{stage}:example.py").stdout
        for stage in (1, 2, 3)
    }
    assert stages[1] == BASE_SOURCE, "stage 1 must hold the merge base"
    assert stages[2] == MAIN_SOURCE, "stage 2 must hold the branch being merged into"
    assert stages[3] == TOPIC_SOURCE, "stage 3 must hold the branch being merged in"
    assert source.read_text(encoding="utf-8").startswith("<<<<<<<"), (
        "the driver's partial result must stay in the working file"
    )


def _diverge_two_topic_commits(repository: Path, source: Path) -> None:
    """Commit the base, then two topic commits, before diverging `main`.

    Both topic commits touch `example.py`, so Git hands each of their replays
    to the merge driver in turn.
    """
    _git(repository, "commit", "--quiet", "-m", "base")
    _git(repository, "switch", "--quiet", "--create", "topic")
    source.write_text(TOPIC_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "topic change")
    later = f'{TOPIC_SOURCE}\n\ndef delta() -> str:\n    return "topic"\n'
    source.write_text(later, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "later topic commit")
    _git(repository, "switch", "--quiet", "main")
    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main change")
    _git(repository, "switch", "--quiet", "topic")


def test_exec_guard_stops_a_multi_commit_rebase_at_the_first_bad_replay(
    diverged: tuple[Path, Path, Path],
) -> None:
    """`--exec` stops the rebase before a corrupt replay reaches later commits."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge_two_topic_commits(repository, source)

    guard = f"{sys.executable} -m py_compile example.py"
    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        mox.spy(DRIVER_NAME).runs(_writing_handler(repository, CORRUPT_OUTPUT, 0))
        mox.replay()
        _wire_driver(repository, environment)
        rebased = _git(repository, "rebase", "--exec", guard, "main", check=False)

    assert rebased.returncode != 0, (
        "the structural guard must fail the rebase at the corrupted replay"
    )
    assert (repository / ".git" / "rebase-merge").exists(), (
        "the rebase must remain stopped rather than running to completion"
    )
    assert "def delta" not in _git(repository, "show", "HEAD:example.py").stdout, (
        "the later commit must not be replayed on top of a corrupted result"
    )

    _abort(repository, "rebase")


def test_a_corrupt_early_replay_becomes_the_ours_stage_of_the_next_replay(
    diverged: tuple[Path, Path, Path],
) -> None:
    """A cleanly returned but corrupted replay feeds straight into the next one.

    With no `--exec` guard, Git keeps replaying on top of whatever the driver
    last wrote. The second replay's `%A` (current/ours) is therefore exactly
    the first replay's corrupted `%A` output, not the original topic content.
    """
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge_two_topic_commits(repository, source)

    second_output = f'{MERGED_SOURCE}\n\ndef delta() -> str:\n    return "topic"\n'
    captured: dict[str, str] = {}
    calls = 0

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        nonlocal calls
        calls += 1
        ancestor, current, _other, _marker_size, _pathname = invocation.args
        if calls == 1:
            (repository / current).write_text(CORRUPT_OUTPUT, encoding="utf-8")
            return ("", "", 0)
        # Read before writing: Git may reuse the same temporary path for `%A`
        # across replays, so the prior content must be captured now.
        captured["ours"] = (repository / current).read_text(encoding="utf-8")
        captured["ancestor"] = (repository / ancestor).read_text(encoding="utf-8")
        (repository / current).write_text(second_output, encoding="utf-8")
        return ("", "", 0)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(handler)
        mox.replay()
        _wire_driver(repository, environment)
        rebased = _git(repository, "rebase", "main", check=False)

    assert spy.call_count == 2, "both replays must invoke the driver"
    assert rebased.returncode == 0, (
        f"a clean exit each time must let the rebase complete: {rebased.stderr}"
    )
    assert captured["ours"] == CORRUPT_OUTPUT, (
        "the corrupt first replay must be exactly the ours input of the second "
        "replay; the second invocation's `%A` must equal the first invocation's "
        "written output"
    )
    assert captured["ancestor"] == TOPIC_SOURCE, (
        "the second replay's ancestor must be the pre-corruption topic content, "
        "as recorded before the first replay's original commit was rewritten"
    )

    rewritten_first = _git(repository, "show", "HEAD~1:example.py").stdout
    assert rewritten_first == CORRUPT_OUTPUT, (
        "Git must have recorded the corrupted first replay in the rewritten "
        "intermediate commit"
    )
    assert source.read_text(encoding="utf-8") == second_output, (
        "the working file at HEAD must hold the valid second replay's output"
    )

    assert spy.invocations[0].args[-1] == "example.py", (
        "the first invocation's `%P` must name the conflicting path"
    )
    assert spy.invocations[1].args[-1] == "example.py", (
        "the second invocation's `%P` must name the conflicting path"
    )

    copy = repository / "intermediate.py"
    copy.write_text(rewritten_first, encoding="utf-8")
    compiled = subprocess.run(  # noqa: S603 - interpreter path and fixed arguments.
        [sys.executable, "-m", "py_compile", str(copy)],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert compiled.returncode != 0, (
        "the intermediate replay is structurally broken; only a per-replay "
        "guard such as `--exec` would have caught it before it became input "
        "to the next replay"
    )


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("operation", OPERATIONS)
def test_documented_bypass_recovers_each_operation_for_each_scope(
    diverged: tuple[Path, Path, Path], scope: str, operation: str
) -> None:
    """Each matrix row makes `merge` unspecified and lets the retry succeed."""
    repository, source, attributes = diverged
    _select_scope(repository, scope, attributes)
    _prepare(repository, source, operation)

    selected = _git(repository, "check-attr", "merge", "--", "example.py")
    assert selected.stdout.rstrip().endswith("merge: weave"), (
        f"the {scope} scope must select the stub driver before the bypass"
    )

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(_conflict_handler())
        mox.replay()
        _wire_driver(repository, environment)

        interrupted = _start_operation(repository, operation)
        assert interrupted.returncode != 0, (
            f"the failing driver must interrupt the {operation}"
        )
        assert spy.call_count == 1, (
            f"Git must have invoked the driver for the {operation}; a non-zero "
            "exit alone would not distinguish that from a textual conflict"
        )
        _abort(repository, operation)

        prefix = _bypass_prefix(repository, scope, "example.py")

        bypassed = _git(repository, *prefix, "check-attr", "merge", "--", "example.py")
        assert bypassed.stdout.rstrip().endswith("merge: unspecified"), (
            f"the documented {scope} bypass must make merge unspecified, got "
            f"{bypassed.stdout.rstrip()!r}"
        )

        retried = _start_operation(repository, operation, prefix)
        assert retried.returncode == 0, (
            f"the {operation} must succeed under the {scope} bypass: {retried.stderr}"
        )
        assert spy.call_count == 1, (
            f"the {scope} bypass must stop Git invoking the driver on the retry"
        )

    assert source.read_text(encoding="utf-8") == EXPECTED_AFTER_BYPASS[operation], (
        f"Git's built-in merge must produce the {operation} result exactly"
    )


# --- Hardened unattended workflow ------------------------------------------
#
# The procedures below were added after a `weave-driver 0.3.6` clean exit
# produced semantically corrupt output that parsed, compiled, and passed tests.
# Each test executes one documented policy rather than asserting its wording;
# the wording is pinned separately by `test_weave_git_merge_skill.py`.

UNATTENDED_PREFIX = (
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "merge.conflictStyle=zdiff3",
)

AUTO_RESOLVED_LINE = "weave: 5 entities auto-resolved (conflict confidence)"
EVENT_LINE = 'weave-event: {"path":"example.py","entities":5}'
# Emitted by the driver but deliberately outside the evidence grammar, so a
# parse that swept up every stderr line would be caught rather than passing.
DECOY_LINE = "weave: skipping binary path assets/logo.png"


def _record_identities(repository: Path, target: str) -> dict[str, str]:
    """Record the candidate, target, and merge base before a history rewrite.

    This is the skill's pre-rewrite receipt. Resolving `target` to a commit is
    the point: a later retry must use this value rather than re-reading a
    mutable remote ref that may have moved.
    """
    old_head = _git(repository, "rev-parse", "HEAD").stdout.strip()
    target_commit = _git(repository, "rev-parse", target).stdout.strip()
    merge_base = _git(
        repository, "merge-base", old_head, target_commit
    ).stdout.strip()
    return {
        "old_head": old_head,
        "target": target_commit,
        "merge_base": merge_base,
    }


def _target_only_audit(repository: Path, identities: dict[str, str]) -> tuple[int, str]:
    """Run the skill's first semantic audit check and return status and stderr.

    This is a transcription of the documented Bash, kept executable so the
    policy is verified rather than merely described. The `$path` binding is the
    part that matters: an unbound variable would widen every comparison to the
    whole tree and fail on legitimate branch changes.
    """
    script = """
set -eu
branch=$(mktemp); target=$(mktemp); only=$(mktemp)
git diff --name-only -z "$MERGE_BASE..$OLD_HEAD" | sort -z > "$branch"
git diff --name-only -z "$MERGE_BASE..$TARGET" | sort -z > "$target"
comm -z -13 "$branch" "$target" > "$only"
status=0
while IFS= read -r -d '' path; do
  if ! git diff --quiet "$TARGET" HEAD -- "$path"; then
    printf 'andon: target-only path is not byte-identical: %s\\n' "$path" >&2
    status=1
  fi
done < "$only"
exit "$status"
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script.
        ["/bin/bash", "-c", script],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        stdin=subprocess.DEVNULL,
        env=os.environ
        | {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "OLD_HEAD": identities["old_head"],
            "TARGET": identities["target"],
            "MERGE_BASE": identities["merge_base"],
        },
    )
    return completed.returncode, completed.stderr


def test_unattended_prefix_keeps_an_ambient_global_rule_out_of_the_rebase(
    diverged: tuple[Path, Path, Path],
) -> None:
    """Weave selected only by ambient global config is bypassed by default."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(_writing_handler(repository, CORRUPT_OUTPUT, 0))
        mox.replay()
        _wire_driver(repository, environment)
        _git(repository, "switch", "--quiet", "topic")
        rebased = _git(repository, *UNATTENDED_PREFIX, "rebase", "main", check=False)

        assert spy.call_count == 0, (
            "an ambient global rule is not repository consent for an unattended "
            "replay; the documented prefix must keep the driver out entirely"
        )

    assert rebased.returncode == 0, f"the built-in rebase must succeed: {rebased.stderr}"
    assert source.read_text(encoding="utf-8") == MERGED_SOURCE, (
        "Git's built-in merge must produce the result, not the corrupt driver output"
    )


def test_unattended_prefix_still_honours_a_tracked_repository_opt_in(
    diverged: tuple[Path, Path, Path],
) -> None:
    """A tracked `.gitattributes` rule is explicit consent and is not bypassed."""
    repository, source, attributes = diverged
    _select_scope(repository, "tracked", attributes)
    _diverge(repository, source)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(_conflict_handler())
        mox.replay()
        _wire_driver(repository, environment)
        _git(repository, "switch", "--quiet", "topic")
        _git(repository, *UNATTENDED_PREFIX, "rebase", "main", check=False)

        assert spy.call_count == 1, (
            "`core.attributesFile=/dev/null` must not silently discard a tracked "
            "repository opt-in; only the scope matrix's own row may do that"
        )
        _abort(repository, "rebase")


def test_unattended_prefix_records_the_merge_base_in_conflict_markers(
    diverged: tuple[Path, Path, Path],
) -> None:
    """`zdiff3` keeps the base section a reviewer needs to explain a deletion."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    # Both sides edit the same function, so the built-in merge cannot resolve it.
    _git(repository, "commit", "--quiet", "-m", "base")
    _git(repository, "switch", "--quiet", "--create", "topic")
    source.write_text(BASE_SOURCE.replace(_ALPHA_BASE, _ALPHA_TOPIC), encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "topic alpha")
    _git(repository, "switch", "--quiet", "main")
    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main alpha")
    _git(repository, "switch", "--quiet", "topic")

    conflicted = _git(repository, *UNATTENDED_PREFIX, "rebase", "main", check=False)
    assert conflicted.returncode != 0, "the competing edits must conflict"

    markers = source.read_text(encoding="utf-8")
    assert "|||||||" in markers, (
        "`merge.conflictStyle=zdiff3` must emit the base section; without it a "
        "reviewer cannot tell an intended deletion from a reconstruction artefact"
    )
    assert '"base"' in markers, "the base section must carry the merge-base content"

    _abort(repository, "rebase")


def test_a_replay_makes_evidence_bound_to_the_old_candidate_stale(
    diverged: tuple[Path, Path, Path],
) -> None:
    """The rebase creates a new candidate, so old-head evidence cannot carry over."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)
    _git(repository, "switch", "--quiet", "topic")

    identities = _record_identities(repository, "main")
    assert identities["merge_base"] not in {identities["old_head"], identities["target"]}, (
        "the fixture must genuinely diverge, or staleness could not be observed"
    )

    rebased = _git(repository, *UNATTENDED_PREFIX, "rebase", "main", check=False)
    assert rebased.returncode == 0, f"the rebase must complete: {rebased.stderr}"

    new_head = _git(repository, "rev-parse", "HEAD").stdout.strip()
    assert new_head != identities["old_head"], (
        "the replay must produce a new candidate commit"
    )
    ancestry = _git(
        repository,
        "merge-base",
        "--is-ancestor",
        identities["old_head"],
        new_head,
        check=False,
    )
    assert ancestry.returncode != 0, (
        "the old candidate must not be an ancestor of the new head; gate and "
        "review evidence tied to it therefore describes no commit being accepted"
    )
    assert (
        _git(repository, "merge-base", "--is-ancestor", identities["target"], new_head)
    ).returncode == 0, "the recorded target must be an ancestor of the new candidate"


def test_semantic_audit_flags_a_target_only_path_a_structural_gate_accepts(
    diverged: tuple[Path, Path, Path],
) -> None:
    """A target-only path altered at HEAD is caught even though it parses."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    sibling = repository / "sibling.py"
    sibling.write_text(BASE_SOURCE, encoding="utf-8")
    _git(repository, "add", "sibling.py")
    _diverge(repository, source)
    _git(repository, "switch", "--quiet", "main")
    # `sibling.py` is changed by the target only; the branch never touches it.
    sibling.write_text(BASE_SOURCE.replace(_BETA_BASE, _BETA_FEATURE), encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main sibling change")
    _git(repository, "switch", "--quiet", "topic")

    identities = _record_identities(repository, "main")
    rebased = _git(repository, *UNATTENDED_PREFIX, "rebase", "main", check=False)
    assert rebased.returncode == 0, f"the rebase must complete: {rebased.stderr}"

    status, _ = _target_only_audit(repository, identities)
    assert status == 0, (
        "a faithful replay must pass the audit; a false positive here would "
        "mean the check compares an unbound path and inspects the whole tree"
    )

    # Now stand in for a driver that reconstructed a path it had no branch-side
    # change to reconcile. The result still parses, so no structural gate fires.
    sibling.write_text(
        BASE_SOURCE.replace(_BETA_BASE, _BETA_FEATURE).replace(_GAMMA_BASE, _GAMMA_TOPIC),
        encoding="utf-8",
    )
    _git(repository, "commit", "--quiet", "--all", "-m", "reconstructed sibling")

    compiled = subprocess.run(  # noqa: S603 - interpreter path and fixed arguments.
        [sys.executable, "-m", "py_compile", str(sibling)],
        cwd=repository,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert compiled.returncode == 0, (
        "the corrupted sibling must still parse, or the audit would be redundant"
    )

    status, stderr = _target_only_audit(repository, identities)
    assert status != 0, (
        "the semantic audit must fail on a target-only path that is not "
        "byte-identical, independently of any parser or compiler being green"
    )
    assert "sibling.py" in stderr, "the audit must name the offending path"
    assert "example.py" not in stderr, (
        "a branch-touched path must not be reported; it is expected to differ "
        "from the target and is covered by the deletion-explanation check"
    )


def test_driver_stderr_capture_preserves_auto_resolution_and_event_lines(
    diverged: tuple[Path, Path, Path],
) -> None:
    """Command-scoped `WEAVE_EVENT=1` reaches the driver and its stderr survives."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)
    capture = repository / "driver.stderr"

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        assert invocation.env.get("WEAVE_EVENT") == "1", (
            "the command-scoped override must reach the driver process"
        )
        _ancestor, current, _other, _marker_size, _pathname = invocation.args
        (repository / current).write_text(MERGED_SOURCE, encoding="utf-8")
        return ("", f"{DECOY_LINE}\n{AUTO_RESOLVED_LINE}\n{EVENT_LINE}\n", 0)

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        spy = mox.spy(DRIVER_NAME).runs(handler)
        mox.replay()
        _wire_driver(repository, environment)
        _git(repository, "switch", "--quiet", "topic")
        with capture.open("w", encoding="utf-8") as stream:
            rebased = subprocess.run(  # noqa: S603 - absolute executable.
                [GIT, "rebase", "main"],
                cwd=repository,
                text=True,
                stdout=subprocess.PIPE,
                stderr=stream,
                check=False,
                timeout=60,
                stdin=subprocess.DEVNULL,
                env=os.environ
                | {
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                    "WEAVE_EVENT": "1",
                },
            )
        assert spy.call_count == 1, "Git must have run the driver"

    assert rebased.returncode == 0, "the driver's clean exit must complete the rebase"
    captured = capture.read_text(encoding="utf-8")
    assert AUTO_RESOLVED_LINE in captured, (
        "the auto-resolution summary must survive the operation; it names the "
        "reconstruction work the semantic audit has to cover"
    )
    assert EVENT_LINE in captured, "structured events must reach the operation receipt"

    matched = subprocess.run(  # noqa: S603 - fixed executable and arguments.
        ["/usr/bin/env", "grep", "-E", "auto-resolved|^weave-event: ", str(capture)],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert DECOY_LINE in captured, "the decoy must reach the capture file"
    assert matched.returncode == 0, (
        "the documented parse must find both lines; a fail-open `|| true` would "
        "have hidden an empty or unreadable capture here"
    )
    assert AUTO_RESOLVED_LINE in matched.stdout, (
        "the auto-resolution summary must be reported by the parse"
    )
    assert EVENT_LINE in matched.stdout, "the event line must be reported by the parse"
    assert DECOY_LINE not in matched.stdout, (
        "the parse must be selective; reporting every stderr line would give an "
        "agent no way to tell auto-resolution evidence from ordinary chatter"
    )


def test_a_completed_operation_cannot_be_aborted_and_needs_the_recorded_head(
    diverged: tuple[Path, Path, Path],
) -> None:
    """A clean driver exit removes the state `--abort` needs, so recovery resets."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
    _diverge(repository, source)
    _git(repository, "switch", "--quiet", "topic")
    identities = _record_identities(repository, "main")

    environment = EnvironmentManager()
    with CmdMox(environment=environment) as mox:
        mox.spy(DRIVER_NAME).runs(_writing_handler(repository, CORRUPT_OUTPUT, 0))
        mox.replay()
        _wire_driver(repository, environment)
        rebased = _git(repository, "rebase", "main", check=False)

    assert rebased.returncode == 0, "the clean exit must let the rebase complete"
    assert not (repository / ".git" / "rebase-merge").exists(), (
        "no rebase state may remain, which is exactly why `--abort` cannot help"
    )

    aborted = _git(repository, "rebase", "--abort", check=False)
    assert aborted.returncode != 0, (
        "`git rebase --abort` must fail on a completed rebase; documenting it as "
        "the only recovery would strand an agent holding a corrupt candidate"
    )

    _git(repository, "reset", "--hard", identities["old_head"])
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == identities["old_head"], (
        "resetting to the recorded candidate must restore the pre-replay state"
    )
    assert source.read_text(encoding="utf-8") == TOPIC_SOURCE, (
        "the corrupt driver output must be gone from the working tree"
    )


def test_recovery_evidence_must_cover_staged_unstaged_and_untracked_work(
    diverged: tuple[Path, Path, Path],
) -> None:
    """Partial evidence silently loses work a destructive reset discards."""
    repository, source, attributes = diverged
    del attributes
    _git(repository, "commit", "--quiet", "-m", "base")

    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "add", "example.py")
    staged_only = _git(
        repository, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary"
    ).stdout
    source.write_text(MERGED_SOURCE, encoding="utf-8")
    unstaged_only = _git(
        repository, "diff", "--no-ext-diff", "--no-textconv", "--binary"
    ).stdout
    untracked = repository / "intended.py"
    untracked.write_text(BASE_SOURCE, encoding="utf-8")

    assert staged_only and unstaged_only, "the fixture must produce both diffs"

    def restore(patches: tuple[str, ...], keep_untracked: bool) -> None:
        _git(repository, "reset", "--hard", "--quiet", "HEAD")
        if not keep_untracked:
            untracked.unlink(missing_ok=True)
        for patch in patches:
            subprocess.run(  # noqa: S603 - absolute executable, piped patch.
                [GIT, "apply", "-"],
                cwd=repository,
                text=True,
                input=patch,
                capture_output=True,
                check=True,
                timeout=60,
                env=os.environ
                | {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
            )

    # Evidence that omits the staged diff reconstructs the wrong content.
    restore((unstaged_only,), keep_untracked=True)
    assert source.read_text(encoding="utf-8") != MERGED_SOURCE, (
        "an unstaged-only capture must not silently appear to restore the tree; "
        "the staged change it was layered on is missing"
    )

    # Complete evidence for all three categories restores the tree exactly.
    restore((staged_only, unstaged_only), keep_untracked=True)
    assert source.read_text(encoding="utf-8") == MERGED_SOURCE, (
        "staged and unstaged diffs together must reproduce the working file"
    )
    assert untracked.read_text(encoding="utf-8") == BASE_SOURCE, (
        "intended untracked work is not in any diff and needs its own evidence"
    )

    # A reset without untracked evidence loses the intended untracked file.
    restore((staged_only, unstaged_only), keep_untracked=False)
    assert not untracked.exists(), (
        "this is the loss the recovery-completeness rule exists to prevent"
    )
