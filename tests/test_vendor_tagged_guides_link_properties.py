"""Property tests for rewriting generated link and image destinations.

Every relative destination is pinned or made local, and every other byte is
left alone. A generated document mixes mapped and unmapped paths, images,
queries, fragments, and surrounding prose, so the property covers combinations
that a handwritten table would miss.
"""

from __future__ import annotations

from pathlib import Path
import types

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_TAG = "v0.2.0-beta2"
_REPOSITORY = "leynos/cuprum"
_MAPPED_SOURCE = "v0-2-0-migration-guide.md"

#: Destination kind, the Markdown destination, and its expected rewrite.
#: Expected values are written out rather than derived from the conversion, so
#: the property states the contract instead of repeating the implementation.
_DESTINATIONS = {
    "mapped": (_MAPPED_SOURCE, "cuprum-v0-2-0-migration-guide.md"),
    "link": (
        "other.md",
        f"https://github.com/{_REPOSITORY}/blob/{_TAG}/docs/other.md",
    ),
    "image": (
        "images/diagram.png",
        f"https://raw.githubusercontent.com/{_REPOSITORY}/{_TAG}/"
        "docs/images/diagram.png",
    ),
    "directory": (
        "adr/",
        f"https://github.com/{_REPOSITORY}/tree/{_TAG}/docs/adr",
    ),
}

#: Prose cannot open link syntax or a Markdown block of its own.
_PROSE = st.text(
    alphabet=st.characters(
        exclude_characters="[]()!<>`#*_|~+\\\r\n\t",
        exclude_categories=("Cs",),
    ),
    max_size=30,
)

_LINKS = st.lists(
    st.tuples(
        st.sampled_from(tuple(_DESTINATIONS)),
        st.booleans(),
        st.booleans(),
    ),
    min_size=2,
    max_size=4,
)


@given(links=_LINKS, prefix=_PROSE, suffix=_PROSE)
@settings(
    max_examples=50,
    deadline=None,
    # ``tmp_path`` only supplies a fixed directory for the config, so sharing
    # it across generated inputs cannot leak state between them.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_generated_destinations_are_rewritten_and_the_prose_is_unchanged(
    vendor: types.ModuleType,
    tmp_path: Path,
    links: list[tuple[str, bool, bool]],
    prefix: str,
    suffix: str,
) -> None:
    """Only destinations move; labels, queries, fragments, and prose do not."""
    # ``convert`` is pure, so the directories only have to describe a valid
    # import; nothing is created or read. A high line limit keeps the
    # exemption pass out of the generated prose.
    config = vendor.VendorConfig(
        tag=_TAG,
        repository=_REPOSITORY,
        source_directory=tmp_path / "upstream" / "docs",
        output_directory=tmp_path / "consumer" / "docs",
        mappings=(
            ("users-guide.md", "cuprum-users-guide.md"),
            (_MAPPED_SOURCE, "cuprum-v0-2-0-migration-guide.md"),
        ),
        source_path="docs",
        line_length=10_000,
        code_line_length=10_000,
    )
    body_lines: list[str] = []
    expected_lines: list[str] = []
    for index, (kind, query, fragment) in enumerate(links):
        destination, rewritten = _DESTINATIONS[kind]
        marker = "!" if kind == "image" else ""
        tail = f"{'?plain=1' if query else ''}{'#part' if fragment else ''}"
        body_lines.append(
            f"See {marker}[{kind} {index}]({destination}{tail}) "
            f"{prefix}{suffix}."
        )
        expected_lines.append(
            f"See {marker}[{kind} {index}]({rewritten}{tail}) "
            f"{prefix}{suffix}."
        )
    body = "\n\n".join(body_lines)
    expected_body = "\n\n".join(expected_lines)
    document = f"# Title\n\n{body}\n"

    converted = vendor.convert(document, config, "users-guide.md")

    note = vendor.NOTE_TEMPLATE.format(
        project="cuprum", tag=config.tag, repository=config.repository
    )
    head, separator, rest = converted.partition(note)
    assert separator, converted
    assert head == "# Title\n\n", converted
    assert rest == f"\n{expected_body}\n", converted