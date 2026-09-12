"""Property tests for the discovery contract the gate recipes depend on.

``markdown_paths`` walks a real directory tree, so a generated tree costs
nothing to check and needs no process double; the example tests beside this
file pin the Git-backed half of the contract. The properties state what must
hold for every tree rather than for the shapes a handwritten case happens to
name: discovery returns exactly the Markdown files that lie outside the pruned
directories, as repository-relative paths in sorted order, and never a path
inside a directory it was told to prune.

Each example builds its tree in a directory of its own. A ``tmp_path`` fixture
is function-scoped, and Hypothesis does not reset one between generated inputs;
that is a health check failure rather than a directory a single example might
happen to tolerate.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import tempfile
import typing as typ

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from gate_runner_test_support import GateModules

if typ.TYPE_CHECKING:
    from collections.abc import Iterable

# Walking a generated tree touches the filesystem, which is slower than the
# pure-function properties elsewhere in the suite.
SETTINGS = settings(
    deadline=None,
    max_examples=50,
    suppress_health_check=(HealthCheck.too_slow,),
)

# Directory components never contain a separator, so every generated path stays
# repository-relative and the expected set can be stated directly.
DIRECTORY = st.one_of(
    st.text(alphabet="abcde", min_size=1, max_size=4),
    st.sampled_from(
        ("target", "node_modules", "dist", ".venv", "build", "__pycache__")
    ),
)
# File names draw on an alphabet the directory components never use. A path
# cannot be both a file and a directory, so a shared alphabet would generate
# trees the filesystem refuses rather than trees discovery should walk.
FILENAME = st.builds(
    "{}{}".format,
    st.text(alphabet="uvwxyzUVW", min_size=1, max_size=6),
    st.sampled_from((".md", ".MD", ".Md", ".markdown", ".txt", ".m", "")),
)
# The directory components are a tuple so an entry stays hashable, which is
# what lets a generated tree ask for entries that do not repeat.
TREE = st.lists(
    st.tuples(st.lists(DIRECTORY, max_size=3).map(tuple), FILENAME),
    max_size=8,
    unique=True,
)


def is_discoverable(relative: Path, excludes: Iterable[str]) -> bool:
    """Return whether discovery should report a generated path.

    Parameters
    ----------
    relative
        Repository-relative path to classify.
    excludes
        Directory names the walk prunes at any depth.

    Returns
    -------
    bool
        True when the name is Markdown and no directory component is pruned.
    """
    pruned = set(excludes)
    return (
        relative.suffix.casefold() == ".md"
        and not any(part in pruned for part in relative.parts[:-1])
    )


def write_tree(root: Path, tree: list[tuple[tuple[str, ...], str]]) -> tuple[Path, ...]:
    """Create a generated tree on disk and return its repository-relative paths.

    Parameters
    ----------
    root
        Directory to create the tree under.
    tree
        Generated directory components and filename for each entry.

    Returns
    -------
    tuple[Path, ...]
        The paths that were written, repository-relative.
    """
    written: list[Path] = []
    for directories, filename in tree:
        relative = Path(*directories, filename)
        if relative in written:
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# heading\n", encoding="utf-8")
        written.append(relative)
    return tuple(written)


@contextmanager
def generated_tree(
    tree: list[tuple[tuple[str, ...], str]],
) -> Iterator[tuple[Path, tuple[Path, ...]]]:
    """Create a generated tree in a directory that belongs to one example.

    Parameters
    ----------
    tree
        Generated directory components and filename for each entry.

    Yields
    ------
    tuple[Path, tuple[Path, ...]]
        The tree's root, and the repository-relative paths written under it.
    """
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        yield root, write_tree(root, tree)


def add_readme(root: Path) -> None:
    """Write a Markdown file no exclusion can prune.

    Parameters
    ----------
    root
        Root of the generated tree.
    """
    (root / "README.md").write_text("# heading\n", encoding="utf-8")


@given(TREE)
@SETTINGS
def test_discovery_returns_exactly_the_markdown_outside_pruned_directories(
    gate: GateModules,
    tree: list[tuple[tuple[str, ...], str]],
) -> None:
    """Every Markdown file outside a pruned directory is reported, and no other.

    The expected set is built from the generated tree rather than from the
    walk, so a filter that dropped an uppercase ``.MD`` suffix or descended
    into a pruned directory fails here.
    """
    with generated_tree(tree) as (root, written):
        expected = {
            path
            for path in written
            if is_discoverable(path, gate.discovery.DEFAULT_DIRECTORY_EXCLUDES)
        }
        if not expected:
            # Without a discoverable file the gate refuses, which the example
            # tests cover; the property is about what a non-empty list holds.
            add_readme(root)
            expected = {Path("README.md")}

        discovered = gate.discovery.markdown_paths(root, gate="markdownlint")

        assert set(discovered) == expected, (
            "discovery reported a different set from the Markdown files that "
            "lie outside the pruned directories"
        )


@given(TREE)
@SETTINGS
def test_discovery_is_sorted_and_repository_relative(
    gate: GateModules,
    tree: list[tuple[tuple[str, ...], str]],
) -> None:
    """The list is deterministic and names files rather than the working tree.

    A sorted, relative list is what makes a gate's evidence reproducible in a
    log and comparable between two runs of the same revision.
    """
    with generated_tree(tree) as (root, written):
        add_readme(root)

        discovered = gate.discovery.markdown_paths(root, gate="markdownlint")

        assert len(discovered) == len(set(discovered)), (
            "discovery reported a file more than once"
        )
        assert set(discovered) <= {*written, Path("README.md")}, (
            "discovery reported a path the tree does not hold"
        )
        assert Path("README.md") in discovered, (
            "the walk dropped a file no exclusion covers"
        )
        assert list(discovered) == sorted(discovered), (
            "discovery returned its paths in an order a second run need not "
            "repeat"
        )
        for path in discovered:
            assert not path.is_absolute(), f"{path} names a location outside the tree"
            assert ".." not in path.parts, f"{path} escapes the tree it was given"


@given(TREE, st.lists(st.sampled_from(("target", "dist", "build")), max_size=2))
@SETTINGS
def test_every_pruned_directory_is_honoured_at_any_depth(
    gate: GateModules,
    tree: list[tuple[tuple[str, ...], str]],
    extra: list[str],
) -> None:
    """A caller's exclusions replace the defaults and reach every depth."""
    with generated_tree(tree) as (root, _written):
        add_readme(root)
        excludes = tuple(dict.fromkeys(extra)) or ("target",)

        discovered = gate.discovery.markdown_paths(
            root,
            gate="markdownlint",
            excludes=excludes,
        )

        assert Path("README.md") in discovered, (
            "the walk pruned a directory the caller did not name"
        )
        for path in discovered:
            assert not any(part in excludes for part in path.parts[:-1]), (
                f"{path} lies inside a directory the walk was told to prune"
            )
