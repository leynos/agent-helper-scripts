"""Behavioural tests for the procedures the Weave skill documents.

These exercise Git's merge-driver boundary with stub drivers so the skill's
detection, inspection, guard, and bypass recipes are executable rather than
merely asserted as prose. Nothing here tests Weave: no test invokes
`weave-driver`, and no assertion depends on Weave's merge quality. The stubs
stand in for any driver that exits with a given status, which is the only part
of the contract the documented procedures rely on.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    from collections.abc import Iterator

GIT = shutil.which("git")

if GIT is None:  # pragma: no cover - Git is a repository test prerequisite.
    raise RuntimeError("git is required to run the Weave procedure tests")

BASE_SOURCE = '''\
def alpha() -> str:
    return "base"


def beta() -> str:
    return "base"


def gamma() -> str:
    return "base"
'''

_ALPHA_BASE = 'def alpha() -> str:\n    return "base"'
_GAMMA_BASE = 'def gamma() -> str:\n    return "base"'
_ALPHA_MAIN = 'def alpha() -> str:\n    return "main"'
_GAMMA_TOPIC = 'def gamma() -> str:\n    return "topic"'

MAIN_SOURCE = BASE_SOURCE.replace(_ALPHA_BASE, _ALPHA_MAIN)
TOPIC_SOURCE = BASE_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)
MERGED_SOURCE = MAIN_SOURCE.replace(_GAMMA_BASE, _GAMMA_TOPIC)

# Writes syntactically invalid Python to %A and reports a clean merge. This is
# the shape of failure the skill exists to catch: Git records the result without
# complaint because the driver said it was fine.
CORRUPT_CLEAN_DRIVER = '''\
import sys

_ancestor, current, _other, _marker_size, _pathname = sys.argv[1:6]
with open(current, "w", encoding="utf-8") as handle:
    handle.write("def alpha() -> str:\\n    return \\"main\\"\\n\\ndef gamma( -> str:\\n")
sys.exit(0)
'''

# Writes a partially merged result and reports a conflict, leaving the path
# unmerged so the three index stages remain readable.
CONFLICTING_DRIVER = '''\
import sys

_ancestor, current, _other, _marker_size, _pathname = sys.argv[1:6]
with open(current, "w", encoding="utf-8") as handle:
    handle.write("<<<<<<< ours\\nours\\n=======\\ntheirs\\n>>>>>>> theirs\\n")
sys.exit(1)
'''

SCOPES = ("global", "tracked", "clone-local")
OPERATIONS = ("rebase", "merge", "cherry-pick")


def _git(
    repository: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository with captured output."""
    return subprocess.run(  # noqa: S603 - absolute executable and controlled arguments.
        [GIT, *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=check,
        timeout=60,
    )


def _write_driver(directory: Path, name: str, body: str) -> str:
    """Write a stub merge driver and return the command Git should run."""
    script = directory / name
    script.write_text(body, encoding="utf-8")
    interpreter = shlex.quote(sys.executable)
    return f"{interpreter} {shlex.quote(str(script))} %O %A %B %L %P"


def _select_driver(
    repository: Path, command: str, scope: str, attributes: Path
) -> None:
    """Point `merge=weave` at a stub driver through one attribute scope."""
    _git(repository, "config", "merge.weave.name", "stub driver")
    _git(repository, "config", "merge.weave.driver", command)
    rule = "*.py merge=weave\n"
    if scope == "global":
        attributes.write_text(rule, encoding="utf-8")
        _git(repository, "config", "core.attributesFile", str(attributes))
    elif scope == "clone-local":
        info = repository / ".git" / "info" / "attributes"
        info.write_text(rule, encoding="utf-8")
    else:  # tracked
        (repository / ".gitattributes").write_text(rule, encoding="utf-8")
        _git(repository, "add", ".gitattributes")


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
def diverged(tmp_path: Path) -> Iterator[tuple[Path, Path]]:
    """Build a repository whose branches need a three-way merge of one file."""
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "example.py"

    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "Weave Skill Test")
    _git(repository, "config", "user.email", "weave-skill@example.invalid")
    source.write_text(BASE_SOURCE, encoding="utf-8")
    _git(repository, "add", "example.py")
    yield repository, source


def _diverge(repository: Path, source: Path) -> None:
    """Commit the base, then one conflicting change on each branch."""
    _git(repository, "commit", "--quiet", "-m", "base")
    _git(repository, "switch", "--quiet", "--create", "topic")
    source.write_text(TOPIC_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "topic change")
    _git(repository, "switch", "--quiet", "main")
    source.write_text(MAIN_SOURCE, encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main change")


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
    return _git(repository, *prefix, "cherry-pick", "topic", check=False)


def _abort(repository: Path, operation: str) -> None:
    """Abort the interrupted operation, as the skill's fallback block does."""
    _git(repository, operation, "--abort")


def test_clean_driver_exit_hides_structural_damage_from_git(
    tmp_path: Path, diverged: tuple[Path, Path]
) -> None:
    """A driver exiting `0` makes Git record unparsable output without complaint."""
    repository, source = diverged
    _select_driver(
        repository,
        _write_driver(tmp_path, "corrupt.py", CORRUPT_CLEAN_DRIVER),
        "global",
        tmp_path / "global-attributes",
    )
    _diverge(repository, source)

    rebased = _start_operation(repository, "rebase")

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
    tmp_path: Path, diverged: tuple[Path, Path]
) -> None:
    """The documented stage inspection works while a path stays unmerged."""
    repository, source = diverged
    _select_driver(
        repository,
        _write_driver(tmp_path, "conflict.py", CONFLICTING_DRIVER),
        "global",
        tmp_path / "global-attributes",
    )
    _diverge(repository, source)

    merged = _start_operation(repository, "merge")
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
    tmp_path: Path, diverged: tuple[Path, Path]
) -> None:
    """`--exec` stops the rebase before a corrupt replay reaches later commits."""
    repository, source = diverged
    _select_driver(
        repository,
        _write_driver(tmp_path, "corrupt.py", CORRUPT_CLEAN_DRIVER),
        "global",
        tmp_path / "global-attributes",
    )
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

    guard = f"{shlex.quote(sys.executable)} -m py_compile example.py"
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
    tmp_path: Path, diverged: tuple[Path, Path], scope: str, operation: str
) -> None:
    """Each matrix row makes `merge` unspecified and lets the retry succeed."""
    repository, source = diverged
    _select_driver(repository, "false", scope, tmp_path / "global-attributes")
    _diverge(repository, source)

    selected = _git(repository, "check-attr", "merge", "--", "example.py")
    assert selected.stdout.rstrip().endswith("merge: weave"), (
        f"the {scope} scope must select the stub driver before the bypass"
    )

    interrupted = _start_operation(repository, operation)
    assert interrupted.returncode != 0, (
        f"the failing driver must interrupt the {operation}"
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
    assert source.read_text(encoding="utf-8") == MERGED_SOURCE, (
        "Git's built-in merge must combine both non-overlapping changes"
    )
