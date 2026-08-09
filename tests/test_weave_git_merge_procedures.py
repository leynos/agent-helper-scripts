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
_BETA_FEATURE = 'def beta() -> str:\n    return "feature"'
_GAMMA_TOPIC = 'def gamma() -> str:\n    return "topic"'

MAIN_SOURCE = BASE_SOURCE.replace(_ALPHA_BASE, _ALPHA_MAIN)
TOPIC_SOURCE = BASE_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)
MERGED_SOURCE = MAIN_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)
FEATURE_FIRST_SOURCE = BASE_SOURCE.replace(_BETA_BASE, _BETA_FEATURE)
FEATURE_SECOND_SOURCE = FEATURE_FIRST_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)

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

    `feature` carries two commits and only its tip is picked, so the merge base
    for the pick is the intervening commit rather than the branch point. The
    destination and that base then differ in two entities, which is what makes
    Git run a content merge for `example.py` instead of applying a patch.
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


def test_exec_guard_stops_a_multi_commit_rebase_at_the_first_bad_replay(
    diverged: tuple[Path, Path, Path],
) -> None:
    """`--exec` stops the rebase before a corrupt replay reaches later commits."""
    repository, source, attributes = diverged
    _select_scope(repository, "global", attributes)
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

    assert source.read_text(encoding="utf-8") == MERGED_SOURCE, (
        "Git's built-in merge must combine both non-overlapping changes"
    )
