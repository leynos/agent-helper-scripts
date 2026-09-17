"""Behavioural tests for the Oxford-form harvesting tool.

Harvesting is the one spelling tool this repository still owns: it gathers the
evidence a curator reads before adding a stem to the shared dictionary. The
tests pin what that evidence may contain, because a harvest that silently skips
a file reads as a repository with nothing to propose.
"""

from pathlib import Path
import collections.abc as cabc
import importlib.util
import subprocess
import sys
import tempfile
import types
import typing as typ

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from spelling_policy_support import (
    REPOSITORY_ROOT,
    SCRIPTS_PATH,
    require_executable,
)

HARVEST_PATH = SCRIPTS_PATH / "oxford_form_harvest.py"
# Split so the repository's own spelling gate does not flag these fixtures: the
# plain-British forms are exactly what the shared policy corrects.
PLAIN_BRITISH_ORGANIZE = "organi" + "se"
PLAIN_BRITISH_ORGANIZING = "organi" + "sing"
EXCLUDED_OVERLAY = (
    "schema = 1\n\n[oxford]\nstems = []\n\n[words]\naccepted = []\n\n"
    '[patterns]\nignore = []\n\n[files]\nexclude = ["fixture.md"]\n'
)
UNIVERSAL_OVERLAY_TEMPLATE = (
    "schema = 1\n\n[oxford]\nstems = []\n\n[words]\naccepted = []\n\n"
    '[patterns]\nignore = []\n\n[files]\nexclude = ["{glob}"]\n'
)
#: Exclusion entries a generated policy document may carry: plain, quotable
#: names that are never one of the universal globs an overlay may not use.
EXCLUSION_NAMES = st.sampled_from(
    ("target", "vendor", "fixture.md", "build", "node_modules", "docs/generated")
)


def exclusion_document(excluded: cabc.Sequence[str]) -> str:
    """Render a minimal policy document carrying only file exclusions.

    Parameters
    ----------
    excluded
        Repository-relative entries for the document's ``[files] exclude``.

    Returns
    -------
    str
        TOML text the harvesting tool can read as a policy document.
    """
    entries = ", ".join(f'"{entry}"' for entry in excluded)
    return (
        "schema = 1\n\n[oxford]\nstems = []\n\n[words]\naccepted = []\n\n"
        f"[patterns]\nignore = []\n\n[files]\nexclude = [{entries}]\n"
    )


@pytest.fixture(name="harvest", scope="module")
def harvest_fixture() -> cabc.Iterator[types.ModuleType]:
    """Load the harvesting tool from ``scripts/`` by path.

    That directory is not a package on the import path, so the module is loaded
    the way the ``uv run --script`` front end reaches it.
    """
    spec = importlib.util.spec_from_file_location("oxford_form_harvest", HARVEST_PATH)
    assert spec is not None, "could not create a module specification"
    assert spec.loader is not None, "module specification has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        del sys.modules[spec.name]


def deny_path_reads(
    target: Path,
    *,
    message: str,
) -> cabc.Callable[[Path, str | None, str | None, str | None], str]:
    """Return a ``Path.read_text`` replacement that denies one target path.

    Parameters
    ----------
    target
        Path whose reads must fail.
    message
        Diagnostic carried by the raised error.

    Returns
    -------
    Callable
        Replacement that denies the target and passes every other read through.
    """
    read_text = Path.read_text

    def deny_target(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        """Deny the target while preserving reads from all other paths."""
        if path == target:
            raise PermissionError(message)
        return read_text(path, encoding=encoding, errors=errors, newline=newline)

    return deny_target


def initialize_repository(repository: Path, *tracked: str) -> None:
    """Create a Git repository and stage the named files.

    Parameters
    ----------
    repository
        Directory to initialize; it must already exist.
    *tracked
        Repository-relative names to stage.
    """
    git = require_executable("git")
    subprocess.run([git, "init", "-q", repository], check=True, timeout=30)
    subprocess.run(
        [git, "-C", str(repository), "add", *tracked],
        check=True,
        timeout=30,
    )


def test_harvest_finds_both_oxford_and_plain_british_forms(
    harvest: types.ModuleType,
) -> None:
    """Harvesting retains evidence for both sides of an Oxford mapping."""
    forms = harvest.harvest_oxford_forms(
        f"We organize releases after {PLAIN_BRITISH_ORGANIZING} fixtures and "
        "analyse results."
    )

    assert forms == (PLAIN_BRITISH_ORGANIZING, "organize"), (
        "harvest omitted or added Oxford candidates"
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("typos.toml"),
        Path("nested/.terraform/providers/upstream/CHANGELOG.md"),
        Path("nested/target/generated.rs"),
        Path("data/typos-oxendict-base.toml"),
    ],
)
def test_harvest_excludes_dictionary_managed_paths(
    harvest: types.ModuleType,
    relative_path: Path,
) -> None:
    """Harvesting omits generated and dependency-managed spelling evidence."""
    policy = harvest.load_exclusion_policy(REPOSITORY_ROOT)

    assert harvest.is_harvest_excluded(relative_path, policy), (
        f"managed path was not excluded: {relative_path}"
    )


def test_the_exclusion_policy_reads_only_the_shared_and_local_documents(
    harvest: types.ModuleType,
    tmp_path: Path,
) -> None:
    """A repository's overlay extends the shared exclusions rather than replacing them."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "typos.local.toml").write_text(EXCLUDED_OVERLAY, encoding="utf-8")

    policy = harvest.load_exclusion_policy(repository)

    assert "fixture.md" in policy.excluded_files, "the overlay exclusion was dropped"
    assert ".git" in policy.excluded_files, (
        "the overlay replaced the shared exclusions instead of extending them"
    )


@pytest.mark.parametrize(
    "universal_glob",
    ["*", "**/*", "*.md", "**/*.MD"],
)
def test_the_exclusion_policy_rejects_universal_overlay_globs(
    harvest: types.ModuleType,
    tmp_path: Path,
    universal_glob: str,
) -> None:
    """An overlay may not exclude everything, or all Markdown, from harvesting."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "typos.local.toml").write_text(
        UNIVERSAL_OVERLAY_TEMPLATE.format(glob=universal_glob),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local file exclusion is too broad"):
        harvest.load_exclusion_policy(repository)


def test_harvest_repository_merges_local_exclusions(
    harvest: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Repository-local excluded fixtures do not enter harvest evidence."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "fixture.md").write_text(
        f"The fixture deliberately says {PLAIN_BRITISH_ORGANIZE}.\n",
        encoding="utf-8",
    )
    (repository / "kept.md").write_text(
        "The guide says organize.\n",
        encoding="utf-8",
    )
    (repository / "typos.local.toml").write_text(EXCLUDED_OVERLAY, encoding="utf-8")
    initialize_repository(repository, "fixture.md", "kept.md", "typos.local.toml")

    findings = harvest.harvest(repository)

    assert {typ.cast("str", finding["path"]) for finding in findings} == {"kept.md"}, (
        "harvest included a repository-local excluded fixture"
    )


def test_harvest_repository_propagates_file_read_failures(
    harvest: types.ModuleType,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Filesystem failures fail harvesting instead of hiding incomplete evidence."""
    repository = tmp_path / "repository"
    repository.mkdir()
    target = repository / "README.md"
    target.write_text("We organize releases.\n", encoding="utf-8")
    initialize_repository(repository, "README.md")
    policy = harvest.load_exclusion_policy(repository)
    monkeypatch.setattr(
        Path,
        "read_text",
        deny_path_reads(target, message="tracked fixture is unreadable"),
    )

    with pytest.raises(PermissionError, match="tracked fixture is unreadable"):
        harvest.harvest_repository(repository, policy)

    failure = next(record for record in caplog.records if record.levelname == "ERROR")
    assert getattr(failure, "operation", None) == "tracked-file-read"
    assert getattr(failure, "source_kind", None) == "repository-file"
    assert getattr(failure, "error_class", None) == "os-error"
    assert str(target) not in failure.getMessage(), (
        "tracked-file diagnostic exposed the repository path"
    )


def test_harvest_repository_skips_non_utf8_files(
    harvest: types.ModuleType,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Binary tracked content remains outside Oxford-form harvesting."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "binary.dat").write_bytes(b"\xff")
    initialize_repository(repository, "binary.dat")

    with caplog.at_level("INFO", logger="oxford_form_harvest"):
        assert harvest.harvest(repository) == ()
    skipped = next(
        record
        for record in caplog.records
        if getattr(record, "error_class", None) == "unicode-decode"
    )
    assert getattr(skipped, "operation", None) == "tracked-file-read"
    assert getattr(skipped, "source_kind", None) == "repository-file"
    assert str(repository / "binary.dat") not in skipped.getMessage(), (
        "non-UTF-8 diagnostic exposed the repository path"
    )


@given(
    shared_exclusions=st.lists(EXCLUSION_NAMES, max_size=6),
    local_exclusions=st.lists(EXCLUSION_NAMES, max_size=6),
)
@settings(deadline=None, max_examples=50)
def test_the_exclusion_policy_is_the_sorted_union_of_both_documents(
    harvest: types.ModuleType,
    shared_exclusions: list[str],
    local_exclusions: list[str],
) -> None:
    """Merging is set union: deduplicated, sorted, and order-independent.

    The harvest decides what it may skip from this tuple, so a duplicate or an
    input ordering must not change which paths survive.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repository = root / "repository"
        repository.mkdir()
        shared = root / "shared.toml"
        shared.write_text(exclusion_document(shared_exclusions), encoding="utf-8")
        (repository / "typos.local.toml").write_text(
            exclusion_document(local_exclusions),
            encoding="utf-8",
        )

        policy = harvest.load_exclusion_policy(repository, shared=shared)

    expected = tuple(sorted(set(shared_exclusions) | set(local_exclusions)))
    assert policy.excluded_files == expected, (
        "the merged exclusions are not the sorted union of both documents"
    )


@pytest.mark.slow
def test_the_command_line_prints_one_json_object_per_matching_line(
    tmp_path: Path,
) -> None:
    """The front end's JSON Lines output is stable evidence a curator can diff."""
    uv = require_executable("uv")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "guide.md").write_text(
        f"We organize releases.\nThe fixture says {PLAIN_BRITISH_ORGANIZE}.\n"
        "Nothing here matches.\n",
        encoding="utf-8",
    )
    initialize_repository(repository, "guide.md")

    completed = subprocess.run(
        [
            uv,
            "run",
            "--script",
            str(SCRIPTS_PATH / "oxford_form_harvest_cli.py"),
            "--repository",
            str(repository),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
        timeout=300,
    )

    assert completed.stdout == (
        '{"forms": ["organize"], "line": 1, "path": "guide.md"}\n'
        f'{{"forms": ["{PLAIN_BRITISH_ORGANIZE}"], "line": 2, "path": "guide.md"}}\n'
    ), f"the command line changed its evidence format: {completed.stdout!r}"
