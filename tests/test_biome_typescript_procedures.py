"""Behavioural tests for the changed-file pipeline the Biome skill documents.

The pipeline in `references/ci-hooks.md` is the one part of the skill that runs
in a shell, and its correctness rests on details prose cannot verify: NUL
delimiting, the diff filter, and `xargs` declining to run on an empty list.
These tests extract the documented `run:` body and execute it in a temporary
repository with a stub `biome` first on `PATH`, so the documentation itself is
what is exercised rather than a copy of it.

The filenames here are fixed so each test names one behaviour a reader can
recognize. The same invariant across generated filenames is checked by
`test_biome_typescript_procedures_properties.py`; the repository the tests run
against, and the extraction of the documented step, come from
`biome_typescript_pipeline_support.py`.

No test requires Biome to be installed. The documented command is POSIX shell,
so the tests that execute it are POSIX-only: the `pipeline` fixture skips a
host that is not POSIX, and `biome_typescript_pipeline_support.py` records the
scope.
"""

from __future__ import annotations

from biome_typescript_pipeline_support import (
    PipelineRepository,
    documented_pipeline,
)


def test_documented_pipeline_carries_the_guarded_flags() -> None:
    """The example itself must declare the flags the behaviour relies on."""
    body = documented_pipeline()
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
