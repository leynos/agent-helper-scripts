"""Real, isolated Git graphs and recorded gh responses for rebase tests."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import pytest
    from cmd_mox import CmdMox
    from cmd_mox.expectations import Expectation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/rebase/scripts/plan_restack.py"
FIXTURES = ROOT / "tests/fixtures/rebase-gh"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
PARENT_REPOSITORY = "leynos/agent-helper-scripts"
PARENT_PR = 50

spec = importlib.util.spec_from_file_location("rebase_plan_under_test", SCRIPT)
assert spec is not None, f"No import spec for the planner at {SCRIPT}"
assert spec.loader is not None, f"Import spec for {SCRIPT} has no loader"
planner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = planner
spec.loader.exec_module(planner)


def git(
    repository: Path, *argv: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Execute real Git; no Git command doubles participate in these tests.

    Parameters
    ----------
    repository : Path
        Working directory for the Git process.
    *argv : str
        Git subcommand and arguments.
    check : bool
        Raise when Git exits non-zero. Pass ``False`` to assert on the status.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed Git process, with text stdout and stderr captured.
    """
    return subprocess.run(
        ["git", *argv],
        cwd=repository,
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def oid(repository: Path, ref: str = "HEAD") -> str:
    """Resolve a ref to its full object ID.

    Parameters
    ----------
    repository : Path
        Repository to resolve the ref in.
    ref : str
        Ref or object name to resolve.

    Returns
    -------
    str
        The full object ID.
    """
    return git(repository, "rev-parse", ref).stdout.strip()


def change(repository: Path, message: str, filename: str, content: str) -> str:
    """Write one file and commit it, returning the new commit's object ID.

    Parameters
    ----------
    repository : Path
        Repository to commit in.
    message : str
        Commit subject.
    filename : str
        File to write, relative to the repository root.
    content : str
        Full new contents of that file.

    Returns
    -------
    str
        The object ID of the new commit.
    """
    (repository / filename).write_text(content)
    git(repository, "add", "--", filename)
    git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", message)
    return oid(repository)


@dataclasses.dataclass
class Graph:
    """Identities of one built test graph and the fixtures bound to it.

    Attributes
    ----------
    repository : Path
        Working repository holding the child branch and the fetched target.
    remote : Path
        Bare repository standing in for GitHub over the file transport.
    trunk, a, b, c, d : str
        Commits M, A, B, C and D of the M-A-B-C-D graph.
    parent : str
        Parent PR head exposed as ``refs/pull/<PR>/head`` in ``remote``.
    landed : str
        Squash landing commit on the target.
    target : str
        Target tip, one commit beyond ``landed``.
    """

    repository: Path
    remote: Path
    trunk: str
    a: str
    b: str
    c: str
    d: str
    parent: str
    landed: str
    target: str

    # The planner is loaded from a path outside any package, so its Request
    # type is not importable at type-check time; `object` keeps the boundary
    # honest rather than claiming a type checkers cannot resolve.
    def request(self, **overrides: object) -> object:
        """Build a planner request against this graph.

        Parameters
        ----------
        **overrides : object
            Fields replacing the defaults for this graph.

        Returns
        -------
        planner.Request
            The request the planner under test will consume.
        """
        values: dict[str, object] = {
            "repository": self.repository,
            "branch": "child",
            "target_ref": "refs/remotes/origin/main",
            "parent_repository": PARENT_REPOSITORY,
            "parent_pr": PARENT_PR,
        }
        values.update(overrides)
        return planner.Request(**values)

    def receipt(self, boundary: str | None = None) -> str:
        """Record a maintained boundary receipt and its parent identity.

        Parameters
        ----------
        boundary : str | None
            Commit the receipt names; defaults to the true boundary ``B``.

        Returns
        -------
        str
            The receipt ref name.
        """
        ref = "refs/stack-bases/child"
        git(self.repository, "update-ref", ref, boundary or self.b)
        git(
            self.repository,
            "config",
            "branch.child.stackParent",
            f"{PARENT_REPOSITORY}#{PARENT_PR}",
        )
        return ref

    def capture(self, **changes: object) -> str:
        """Return the recorded gh capture rebound to this graph's identities.

        Parameters
        ----------
        **changes : object
            Further fields to alter, for negative scenarios only.

        Returns
        -------
        str
            The stdout a mocked ``gh`` should produce, newline-terminated.
        """
        # Only object identities vary in ordinary graph scenarios. Negative
        # scenarios explicitly override further fields; the stored capture stays
        # byte-for-byte intact and never pretends synthetic SHAs came from GitHub.
        data = json.loads((FIXTURES / "merged-parent.stdout").read_text())
        data.update(head_sha=self.parent, landed=self.landed)
        data.update(changes)
        return json.dumps(data) + "\n"


def _parent_for_mode(repository: Path, trunk: str, b: str, mode: str) -> str:
    """Advance, rewrite, or keep the parent head according to ``mode``.

    Parameters
    ----------
    repository : Path
        Repository with ``old-parent`` checked out at ``b``.
    trunk : str
        Commit M, the root of the graph.
    b : str
        Commit B, the parent head in the ordinary mode.
    mode : str
        One of ``ordinary``, ``advanced`` or ``rewritten``.

    Returns
    -------
    str
        The resulting parent head.

    Raises
    ------
    ValueError
        If ``mode`` is not a supported graph mode.
    """
    match mode:
        case "ordinary":
            return b
        case "advanced":
            return change(repository, "E", "late.txt", "late parent work\n")
        case "rewritten":
            git(repository, "reset", "--hard", trunk)
            return change(
                repository, "rewritten parent", "parent.txt", "parent step two\n"
            )
        case _:
            raise ValueError(mode)


def make_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "ordinary"
) -> Graph:
    """Build M-A-B-C-D plus a squash target; expose only the parent's PR head.

    Parameters
    ----------
    tmp_path : Path
        Directory holding the working repository and the bare stand-in remote.
    monkeypatch : pytest.MonkeyPatch
        Used to isolate the Git environment from the ambient configuration.
    mode : str
        One of ``ordinary``, ``advanced`` or ``rewritten``.

    Returns
    -------
    Graph
        The identities of the built graph.
    """
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_EDITOR", "true")
    monkeypatch.setenv("GIT_SEQUENCE_EDITOR", "true")
    repository = tmp_path / "work"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    git(repository, "init", "--quiet", "--initial-branch=main")
    git(repository, "config", "user.name", "Rebase test")
    git(repository, "config", "user.email", "rebase@example.invalid")
    trunk = change(repository, "M", "parent.txt", "base\n")
    git(repository, "switch", "--quiet", "-c", "old-parent")
    a = change(repository, "A", "parent.txt", "parent step one\n")
    b = change(repository, "B", "parent.txt", "parent step two\n")
    git(repository, "switch", "--quiet", "-c", "child")
    c = change(repository, "C", "first.txt", "first child change\n")
    d = change(repository, "D", "second.txt", "second child change\n")
    git(repository, "switch", "--quiet", "old-parent")
    parent = _parent_for_mode(repository, trunk, b, mode)
    git(repository, "switch", "--quiet", "main")
    git(repository, "merge", "--squash", "old-parent")
    git(repository, "commit", "--quiet", "-m", "S")
    landed = oid(repository)
    target = change(repository, "T", "target-only.txt", "retain target work\n")
    git(repository, "update-ref", "refs/remotes/origin/main", target)
    git(repository, "init", "--bare", "--quiet", str(remote))
    git(repository, "push", str(remote), f"{parent}:refs/pull/{PARENT_PR}/head")
    # Git itself handles transport, but only to this local bare repository.
    git(
        repository,
        "config",
        f"url.{remote.as_uri()}.insteadOf",
        f"https://github.com/{PARENT_REPOSITORY}.git",
    )
    git(repository, "switch", "--quiet", "child")
    git(repository, "branch", "-D", "old-parent")
    return Graph(repository, remote, trunk, a, b, c, d, parent, landed, target)


def expect_parent(
    cmd_mox: CmdMox, graph: Graph, *, stdout: str | None = None
) -> Expectation:
    """Match the exact argv recorded by the real CLI, independently of code.

    Parameters
    ----------
    cmd_mox : CmdMox
        The cmd-mox controller supplying the ``gh`` process shim.
    graph : Graph
        Graph whose identities the recorded capture is rebound to.
    stdout : str | None
        Replacement stdout for negative scenarios; defaults to the rebound
        recorded capture.

    Returns
    -------
    Expectation
        The configured ``gh`` expectation, so callers can attach a handler.
    """
    captured = MANIFEST["commands"]["merged-parent"]
    return (
        cmd_mox.mock("gh")
        .with_args(*captured["argv"][1:])
        .returns(
            stdout=graph.capture() if stdout is None else stdout,
            stderr=(FIXTURES / "merged-parent.stderr").read_text(),
            exit_code=captured["exit_code"],
        )
    )


def snapshot(repository: Path) -> tuple[str, str, str, bytes | None]:
    """Track protected refs, the index/worktree and FETCH_HEAD around discovery.

    Parameters
    ----------
    repository : Path
        Repository to snapshot.

    Returns
    -------
    tuple[str, str, str, bytes | None]
        The protected ref listing, porcelain status, working-tree diff, and the
        raw ``FETCH_HEAD`` contents, or ``None`` when that file does not exist.
    """
    fetch_head = Path(
        git(repository, "rev-parse", "--git-path", "FETCH_HEAD").stdout.strip()
    )
    if not fetch_head.is_absolute():
        fetch_head = repository / fetch_head
    return (
        git(
            repository,
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads",
            "refs/remotes",
            "refs/stack-bases",
        ).stdout,
        git(repository, "status", "--porcelain=v1").stdout,
        git(repository, "diff", "HEAD", "--no-ext-diff", "--binary").stdout,
        fetch_head.read_bytes() if fetch_head.exists() else None,
    )
