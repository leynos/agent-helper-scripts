"""Shared plumbing for the Biome skill's changed-file pipeline tests.

The pipeline in `references/ci-hooks.md` is the one part of the skill that runs
in a shell. `test_biome_typescript_procedures.py` covers it with fixed
filenames and `test_biome_typescript_procedures_properties.py` with generated
ones, so extracting the documented `run:` body, building a temporary
repository, and standing in a stub `biome` for the real one all live here
rather than in either module.

No test requires Biome to be installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
import typing as typ
from dataclasses import dataclass
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    from collections.abc import Iterator

GIT = shutil.which("git")
BASH = shutil.which("bash")

if GIT is None:  # pragma: no cover - Git is a repository test prerequisite.
    raise RuntimeError("git is required to run the Biome procedure tests")

if BASH is None:  # pragma: no cover - Bash runs the documented step.
    raise RuntimeError("bash is required to run the Biome procedure tests")


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CI_HOOKS_PATH = (
    REPOSITORY_ROOT / "skills" / "biome-typescript" / "references" / "ci-hooks.md"
)

YAML_FENCE = re.compile(r"^```yaml\n(.*?)^```$", re.DOTALL | re.MULTILINE)

#: The branch the workflow compares against; GitHub supplies this to the step.
BASE_REF = "main"

#: The extensions the documented pipeline hands to Biome. A path carrying any
#: other extension is filtered out by the diff command itself.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx")

#: Characters a generated path component may carry: printable ASCII plus the
#: whitespace characters, because a shell pipeline is most likely to split on
#: whitespace and to interpret a shell metacharacter. NUL and `/` cannot appear
#: in a path component at all; `\` and `:` are left out because they are not
#: valid in a path on every filesystem this repository may be checked out on,
#: so generating them would make a test depend on where it runs.
PATH_CHARACTERS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " \t\n"
    "!\"#$%&'()*+,-.;<=>?@[]^_`{|}~"
)

# Records separate one stub invocation from the next. Both separators are
# control characters so a filename containing spaces or newlines cannot be
# mistaken for an argument or call boundary.
RECORD_SEPARATOR = "\x1e"
NUL = "\x00"

STUB_BIOME = r"""#!/usr/bin/env bash
set -euo pipefail
{
  printf '\036'
  if [ "$#" -gt 0 ]; then
    printf '%s\000' "$@"
  fi
} >> "${STUB_BIOME_LOG}"
exit "${STUB_BIOME_STATUS:-0}"
"""


def git_environment() -> dict[str, str]:
    """Return an environment that ignores the host's Git configuration.

    The tests must not depend on the machine's difftool, signing, or identity
    settings, so global and system configuration are switched off.
    """
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Biome Skill Test",
            "GIT_AUTHOR_EMAIL": "biome-skill@example.invalid",
            "GIT_COMMITTER_NAME": "Biome Skill Test",
            "GIT_COMMITTER_EMAIL": "biome-skill@example.invalid",
        }
    )
    return environment


def run_git(
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
        env=git_environment(),
    )


def run_body(block: str) -> str:
    """Extract and dedent the `run: |` block scalar from a workflow step."""
    lines = block.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(r"^\s*run: \|\s*$", line)
    )
    indent = len(lines[start]) - len(lines[start].lstrip())
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


def documented_pipeline() -> str:
    """Return the changed-file pipeline exactly as the skill documents it.

    The block is selected by the command it runs rather than by any of the
    flags under test, so dropping a flag fails the test that covers it instead
    of failing every test with an extraction error.
    """
    document = CI_HOOKS_PATH.read_text(encoding="utf-8")
    blocks = [
        block
        for block in YAML_FENCE.findall(document)
        if "git diff --name-only" in block
    ]
    assert len(blocks) == 1, (
        "expected exactly one changed-file pipeline example in ci-hooks.md, so "
        "these tests exercise the documented command and no other"
    )
    return run_body(blocks[0]).replace("${{ github.base_ref }}", BASE_REF)


@dataclass(frozen=True)
class PipelineRepository:
    """A repository wired to a stub Biome, running the documented pipeline."""

    repository: Path
    stub_directory: Path
    log_path: Path

    def write(
        self, relative_path: str, content: str = "export const value = 1;\n"
    ) -> str:
        """Write a file, creating any missing parent directory."""
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return relative_path

    def remove(self, relative_path: str) -> None:
        """Delete a tracked file."""
        (self.repository / relative_path).unlink()

    def rename(self, source: str, destination: str) -> None:
        """Rename a tracked file through Git."""
        run_git(self.repository, "mv", source, destination)

    def commit(self, message: str = "change") -> None:
        """Stage and commit everything in the working tree."""
        run_git(self.repository, "add", "--all")
        run_git(self.repository, "commit", "--quiet", "--message", message)

    def run(self, *, biome_status: int = 0) -> subprocess.CompletedProcess[str]:
        """Run the documented pipeline with the stub Biome first on `PATH`."""
        environment = git_environment()
        environment["PATH"] = os.pathsep.join(
            (str(self.stub_directory), environment["PATH"])
        )
        environment["STUB_BIOME_LOG"] = str(self.log_path)
        environment["STUB_BIOME_STATUS"] = str(biome_status)
        return subprocess.run(  # noqa: S603 - fixed interpreter, documented body.
            [BASH, "-c", documented_pipeline()],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
            env=environment,
        )

    def biome_calls(self) -> list[list[str]]:
        """Return each stubbed Biome invocation as its argument list."""
        if not self.log_path.exists():
            return []
        records = self.log_path.read_text(encoding="utf-8").split(RECORD_SEPARATOR)
        return [
            [argument for argument in record.split(NUL) if argument]
            for record in records
            if record
        ]

    def arguments(self) -> set[str]:
        """Return every argument passed to Biome across all invocations."""
        return {argument for call in self.biome_calls() for argument in call}


@pytest.fixture(name="pipeline")
def pipeline_fixture(tmp_path: Path) -> Iterator[PipelineRepository]:
    """Build a repository whose `origin/main` precedes the feature branch."""
    repository = tmp_path / "repository"
    repository.mkdir()
    stub_directory = tmp_path / "stub-bin"
    stub_directory.mkdir()
    stub = stub_directory / "biome"
    stub.write_text(STUB_BIOME, encoding="utf-8")
    stub.chmod(0o755)

    built = PipelineRepository(
        repository=repository,
        stub_directory=stub_directory,
        log_path=tmp_path / "biome-calls.bin",
    )

    run_git(repository, "init", "--quiet", "--initial-branch=main")
    built.write("src/app.ts", "export const app = 1;\n")
    built.write("src/kept.ts", "export const kept = 1;\n")
    built.write("src/gone.ts", "export const gone = 1;\n")
    built.write("README.md", "# example\n")
    built.commit("base")
    base = run_git(repository, "rev-parse", "HEAD").stdout.strip()
    run_git(repository, "update-ref", "refs/remotes/origin/main", base)
    run_git(repository, "checkout", "--quiet", "-b", "feature")
    yield built
