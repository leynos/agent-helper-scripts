"""Real, isolated Git graphs and recorded gh responses for rebase tests."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/rebase/scripts/plan_restack.py"
FIXTURES = ROOT / "tests/fixtures/rebase-gh"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
PARENT_REPOSITORY = "leynos/agent-helper-scripts"
PARENT_PR = 50

spec = importlib.util.spec_from_file_location("rebase_plan_under_test", SCRIPT)
assert spec and spec.loader
planner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = planner
spec.loader.exec_module(planner)


def git(repository: Path, *argv: str, check: bool = True):
    """Execute real Git; no Git command doubles participate in these tests."""
    return subprocess.run(
        ["git", *argv],
        cwd=repository,
        capture_output=True,
        text=True,
        check=check,
        timeout=30,
    )


def oid(repository: Path, ref: str = "HEAD") -> str:
    return git(repository, "rev-parse", ref).stdout.strip()


def change(repository: Path, message: str, filename: str, content: str) -> str:
    (repository / filename).write_text(content)
    git(repository, "add", "--", filename)
    git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", message)
    return oid(repository)


@dataclasses.dataclass
class Graph:
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

    def request(self, **overrides):
        values = {
            "repository": self.repository,
            "branch": "child",
            "target_ref": "refs/remotes/origin/main",
            "parent_repository": PARENT_REPOSITORY,
            "parent_pr": PARENT_PR,
        }
        values.update(overrides)
        return planner.Request(**values)

    def receipt(self, boundary: str | None = None) -> str:
        ref = "refs/stack-bases/child"
        git(self.repository, "update-ref", ref, boundary or self.b)
        git(
            self.repository,
            "config",
            "branch.child.stackParent",
            f"{PARENT_REPOSITORY}#{PARENT_PR}",
        )
        return ref

    def capture(self, **changes) -> str:
        # Only object identities vary in ordinary graph scenarios. Negative
        # scenarios explicitly override further fields; the stored capture stays
        # byte-for-byte intact and never pretends synthetic SHAs came from GitHub.
        data = json.loads((FIXTURES / "merged-parent.stdout").read_text())
        data.update(head_sha=self.parent, landed=self.landed)
        data.update(changes)
        return json.dumps(data) + "\n"


def make_graph(tmp_path: Path, monkeypatch, mode: str = "ordinary") -> Graph:
    """Build M-A-B-C-D plus a squash target; expose only the parent's PR head."""
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
    parent = b
    if mode == "advanced":
        parent = change(repository, "E", "late.txt", "late parent work\n")
    elif mode == "rewritten":
        git(repository, "reset", "--hard", trunk)
        parent = change(
            repository, "rewritten parent", "parent.txt", "parent step two\n"
        )
    elif mode != "ordinary":
        raise ValueError(mode)
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


def expect_parent(cmd_mox, graph: Graph, *, stdout: str | None = None):
    """Match the exact argv recorded by the real CLI, independently of code."""
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
    """Track protected refs, the index/worktree and FETCH_HEAD around discovery."""
    fetch_head = repository / ".git/FETCH_HEAD"
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
