"""Property-based checks for the changed-file pipeline's filename safety.

`test_biome_typescript_procedures.py` fixes the filenames so each test names
one behaviour a reader can recognize. This module checks the invariant
underneath those examples: a changed path reaches Biome as exactly one
argument, whatever it contains. The generated names carry whitespace, shell
metacharacters, and leading dashes — the cases a handwritten table is least
likely to think of, and the ones a shell pipeline is most likely to mangle.

Git and Bash do the work, so each example costs a few processes. The example
count stays modest and the repository is shared across the examples of one
run, which is deliberate rather than incidental: every example adds a path to
the same change set, so the pipeline is exercised against an argument list
that grows as the property runs.

Paths Git cannot track are out of scope, because they would fail the setup
rather than the invariant. NUL bytes and `/` can never appear in a path
component, and `\\` and `:` are not valid on every filesystem this repository
may be checked out on, so generating them would make the property depend on
where it runs.

No test requires Biome to be installed.
"""

from __future__ import annotations

from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
import pytest

from biome_typescript_pipeline_support import (
    PATH_CHARACTERS,
    SUPPORTED_EXTENSIONS,
    PipelineRepository,
)

#: One path component, before the extension is appended.
PATH_STEMS = st.text(
    alphabet=PATH_CHARACTERS,
    min_size=1,
    max_size=20,
)


@pytest.mark.slow
@settings(
    max_examples=25,
    deadline=None,
    # The `pipeline` fixture is function scoped but deliberately not reset
    # between generated examples: each example adds one path to the same change
    # set, so the pipeline is exercised against a growing argument list rather
    # than a single path. Rebuilding the repository per example would only make
    # the same assertion slower.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(stem=PATH_STEMS, extension=st.sampled_from(SUPPORTED_EXTENSIONS))
def test_every_generated_path_reaches_biome_as_one_argument(
    pipeline: PipelineRepository,
    stem: str,
    extension: str,
) -> None:
    """A changed path is handed to Biome whole, whatever characters it holds."""
    name = f"src/{stem}{extension}"
    # Unique content so an example that regenerates a previous name still
    # produces a commit, rather than failing the setup on an empty one.
    pipeline.write(name, content=f"export const value = {uuid4().hex!r};\n")
    pipeline.commit()

    result = pipeline.run()

    assert result.returncode == 0, result.stderr
    assert name in pipeline.arguments(), (
        f"the generated path {name!r} did not arrive as a single argument, so "
        "the pipeline split it before Biome saw it"
    )
