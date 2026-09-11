"""Behavioural tests for the changed-file pipeline the Biome skill documents.

The pipeline in `references/ci-hooks.md` is the one part of the skill that runs
in a shell, and its correctness rests on details prose cannot verify: NUL
delimiting, the diff filter, and `xargs` declining to run on an empty list.
These tests extract the documented `run:` body and execute it in a temporary
repository with a stub `biome` first on `PATH`, so the documentation itself is
what is exercised rather than a copy of it.

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


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_HOOKS_PATH = REPO_ROOT / "skills" / "biome-typescript" / "references" / "ci-hooks.md"

YAML_FENCE = re.compile(r"^```yaml\n(.*?)^```$", re.DOTALL | re.MULTILINE)

# The branch the workflow compares against; GitHub supplies this to the step.
BASE_REF = "main"

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
        env=_git_environment(),
    )


def _git_environment() -> dict[str, str]:
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


def _run_body(block: str) -> str:
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


def _documented_pipeline() -> str:
    """Return the changed-file pipeline exactly as the skill documents it.

    The block is selected by the command it runs rather than by any of the
    flags under test, so dropping a flag fails the test that covers it instead
    of failing every test with an extraction error.
    """
    document = CI_HOOKS_PATH.read_text(encoding="utf-8")
    blocks = [
        block for block in YAML_FENCE.findall(document) if "git diff --name-only" in block
    ]
    assert len(blocks) == 1, (
        "expected exactly one changed-file pipeline example in ci-hooks.md, so "
        "these tests exercise the documented command and no other"
    )
    return _run_body(blocks[0]).replace("${{ github.base_ref }}", BASE_REF)


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
        _git(self.repository, "mv", source, destination)

    def commit(self, message: str = "change") -> None:
        """Stage and commit everything in the working tree."""
        _git(self.repository, "add", "--all")
        _git(self.repository, "commit", "--quiet", "--message", message)

    def run(self, *, biome_status: int = 0) -> subprocess.CompletedProcess[str]:
        """Run the documented pipeline with the stub Biome first on `PATH`."""
        environment = _git_environment()
        environment["PATH"] = os.pathsep.join(
            (str(self.stub_directory), environment["PATH"])
        )
        environment["STUB_BIOME_LOG"] = str(self.log_path)
        environment["STUB_BIOME_STATUS"] = str(biome_status)
        return subprocess.run(  # noqa: S603 - fixed interpreter, documented body.
            [BASH, "-c", _documented_pipeline()],
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


@pytest.fixture
def pipeline(tmp_path: Path) -> Iterator[PipelineRepository]:
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

    _git(repository, "init", "--quiet", "--initial-branch=main")
    built.write("src/app.ts", "export const app = 1;\n")
    built.write("src/kept.ts", "export const kept = 1;\n")
    built.write("src/gone.ts", "export const gone = 1;\n")
    built.write("README.md", "# example\n")
    built.commit("base")
    base = _git(repository, "rev-parse", "HEAD").stdout.strip()
    _git(repository, "update-ref", "refs/remotes/origin/main", base)
    _git(repository, "checkout", "--quiet", "-b", "feature")
    yield built


def test_documented_pipeline_carries_the_guarded_flags() -> None:
    """The example itself must declare the flags the behaviour relies on."""
    body = _documented_pipeline()
    assert "--diff-filter=ACMR" in body, (
        "deleted paths must be filtered out before Biome is asked to read them"
    )
    assert "-z" in body, "the diff output must be NUL delimited"
    assert "xargs -0 -r -- biome check" in body, (
        "the pipeline must read NUL-delimited input, skip an empty list, and "
        "end the argument list before naming the command"
    )


def test_filenames_with_spaces_reach_biome_as_one_argument(
    pipeline: PipelineRepository,
) -> None:
    """NUL delimiting keeps a filename containing a space intact."""
    pipeline.write("src/has space.ts")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    arguments = pipeline.arguments()
    assert "src/has space.ts" in arguments, (
        "a filename containing a space must arrive as a single argument"
    )
    assert "src/has" not in arguments, (
        "the filename was split on whitespace, which means the fix regressed"
    )


def test_filenames_with_newlines_reach_biome_as_one_argument(
    pipeline: PipelineRepository,
) -> None:
    """A newline in a filename survives the same pipeline."""
    name = "src/line\nbreak.ts"
    pipeline.write(name)
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert name in pipeline.arguments(), (
        "a filename containing a newline must arrive as a single argument"
    )


def test_javascript_and_jsx_paths_are_checked(pipeline: PipelineRepository) -> None:
    """The documented patterns cover JavaScript as well as TypeScript."""
    pipeline.write("src/component.jsx")
    pipeline.write("src/legacy.js")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert pipeline.arguments() >= {"check", "src/component.jsx", "src/legacy.js"}


def test_deleted_paths_are_not_passed_to_biome(pipeline: PipelineRepository) -> None:
    """A deleted file no longer exists, so Biome must not be asked to read it."""
    pipeline.remove("src/gone.ts")
    pipeline.write("src/app.ts", "export const app = 2;\n")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    arguments = pipeline.arguments()
    assert "src/app.ts" in arguments, "the modified file must still be checked"
    assert "src/gone.ts" not in arguments, (
        "the deleted path was passed to Biome, which would fail on a missing file"
    )


def test_renamed_paths_are_checked(pipeline: PipelineRepository) -> None:
    """Renames survive the diff filter, so the new path is checked."""
    pipeline.rename("src/kept.ts", "src/renamed.ts")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert "src/renamed.ts" in pipeline.arguments()


def test_an_empty_change_set_does_not_invoke_biome(
    pipeline: PipelineRepository,
) -> None:
    """`xargs -r` skips the invocation entirely when nothing changed."""
    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert pipeline.biome_calls() == [], (
        "Biome must not be invoked at all for an empty change set, because a "
        "bare xargs would run it with no files and exit non-zero"
    )


def test_changes_outside_the_documented_patterns_are_ignored(
    pipeline: PipelineRepository,
) -> None:
    """Only the documented extensions reach Biome."""
    pipeline.write("README.md", "# changed\n")
    pipeline.write("scripts/tool.py", "value = 1\n")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert pipeline.biome_calls() == [], (
        "a documentation-only or Python-only change must not invoke Biome"
    )


def test_a_biome_failure_fails_the_step(pipeline: PipelineRepository) -> None:
    """A non-zero Biome exit must fail the CI step rather than be swallowed."""
    pipeline.write("src/app.ts", "export const app = 3;\n")
    pipeline.commit()

    result = pipeline.run(biome_status=1)

    assert result.returncode != 0, (
        "the pipeline must propagate a Biome failure to the surrounding step"
    )
