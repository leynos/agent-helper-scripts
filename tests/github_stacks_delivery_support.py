"""Execute the documented publication commands against isolated real Git refs.

This harness exercises Git mechanics, not hosted GitHub or stack reconciliation.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROCEDURE = ROOT / "skills/github-stacks/references/partial-delivery.md"


def publication_commands() -> tuple[str, str, str]:
    """Extract the actual read/push/read recipe, joining shell continuations."""
    blocks = re.findall(r"```bash\n(.*?)\n```", PROCEDURE.read_text(), re.DOTALL)
    block, = [block for block in blocks if "git push" in block]
    before, push, after = block.replace("\\\n", " ").splitlines()
    return before, push, after


def git(repository: Path, *args: str) -> str:
    """Run real Git with captured output and a bounded process lifetime."""
    return subprocess.run(
        ["git", *args], cwd=repository, text=True, capture_output=True,
        check=True, timeout=30,
    ).stdout.strip()


def commit(repository: Path, message: str) -> str:
    """Create a distinct commit without depending on wall-clock timing."""
    git(repository, "commit", "--quiet", "--allow-empty", "-m", message)
    return git(repository, "rev-parse", "HEAD")


@dataclass
class Delivery:
    """An owned candidate, original frontier receipt and untouched upper ref."""

    repository: Path
    remote: Path
    expected: str
    candidate: str
    upper: str

    def run(self, command: str) -> subprocess.CompletedProcess[str]:
        """Run one extracted command; callers must inspect each result."""
        return subprocess.run(
            ["bash", "-c", command], cwd=self.repository,
            env=dict(os.environ, REMOTE="origin", BRANCH="frontier",
                     EXPECTED_REMOTE_HEAD=self.expected, CANDIDATE=self.candidate),
            text=True, capture_output=True, check=False, timeout=30,
        )

    def read(self, command: str) -> str:
        """Read exactly the frontier ref and return its remote object identity."""
        result = self.run(command)
        assert result.returncode == 0, result.stderr
        sha, ref = result.stdout.strip().split()
        assert ref == "refs/heads/frontier"
        return sha

    def compete(self) -> str:
        """Publish sibling work directly, without updating local tracking refs."""
        git(self.repository, "switch", "--quiet", "--detach", self.expected)
        competing = commit(self.repository, "competing publication")
        # Both repositories already contain the original commit tree.
        git(self.repository, "push", str(self.remote),
            f"{competing}:refs/heads/frontier")
        return competing


def make_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Delivery:
    """Build a two-layer stack and a separately selected frontier candidate."""
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("BASH_ENV", raising=False)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    repository = tmp_path / "work"
    remote = tmp_path / "remote.git"
    repository.mkdir()
    git(repository, "init", "--quiet", "--initial-branch=frontier")
    git(repository, "config", "user.name", "Stack delivery test")
    git(repository, "config", "user.email", "stack@example.invalid")
    expected = commit(repository, "original frontier")
    git(repository, "switch", "--quiet", "-c", "upper")
    upper = commit(repository, "unvalidated upper layer")
    git(repository, "init", "--quiet", "--bare", str(remote))
    git(repository, "remote", "add", "origin", str(remote))
    git(repository, "push", "origin", "frontier", "upper")
    git(repository, "switch", "--quiet", "frontier")
    candidate = commit(repository, "validated candidate")
    return Delivery(repository, remote, expected, candidate, upper)
