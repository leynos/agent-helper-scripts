"""Tests for the tag-pinned guide vendoring tool.

The conversion is deterministic and pure, so most of these tests compare
bytes: a link's label, title, angle delimiter, and fragment must survive, and a
second run over the same upstream tree must produce the same file. The one
process test at the end drives the real front end, `mdtablefix`, and the
repository's Markdown configuration from a separate consumer checkout.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
import dataclasses
import importlib
from pathlib import Path
import shutil
import subprocess
import sys
import types

from hypothesis import given, settings
from hypothesis import strategies as st
import pytest

from spelling_policy_support import REPOSITORY_ROOT, SCRIPTS_PATH

CLI_PATH = SCRIPTS_PATH / "vendor_tagged_guides_cli.py"
MARKDOWNLINT_CONFIG = REPOSITORY_ROOT / ".markdownlint-cli2.jsonc"
REAL_FORMATTER = "mdtablefix"
REAL_LINTER = "markdownlint-cli2"

#: Formatter arguments the shared Markdown baseline uses. ``--check`` and
#: ``--in-place`` are mutually exclusive, so the write mode is added by the
#: caller.
FORMATTER_ARGUMENTS = (
    "--wrap",
    "--renumber",
    "--breaks",
    "--ellipsis",
    "--fences",
)

SNAPSHOT_SOURCE = """\
# Cuprum users' guide

Cuprum helps Python applications run external programs. See the
[migration guide](v0-2-0-migration-guide.md#migrating-from-0-1) and the
[developers' guide](developers-guide.md).

![Architecture diagram](images/architecture.png)

Inline `[sample](examples/sample.py)` is code, but `[the guide](guide.md)` is a
link.

```markdown
[fenced](should-not-change.md)
```

[reference]: <reference-target.md> "Reference title"

A sentence with a footnote.[^1]

[^1]: A footnote with [a link](footnote-target.md).
"""


@pytest.fixture(name="vendor", scope="module")
def vendor_fixture() -> Iterator[types.ModuleType]:
    """Load the vendoring core from ``scripts/`` by path."""
    script_directory = str(SCRIPTS_PATH)
    sys.path.insert(0, script_directory)
    try:
        yield importlib.import_module("vendor_tagged_guides")
    finally:
        sys.path.remove(script_directory)


def write_upstream(root: Path, sources: dict[str, str]) -> Path:
    """Write an upstream ``docs/`` tree.

    Parameters
    ----------
    root
        Temporary directory that holds the tree.
    sources
        Source filename and content pairs.

    Returns
    -------
    pathlib.Path
        Directory the sources were written to.
    """
    directory = root / "upstream" / "docs"
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in sources.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    return directory


def make_config(
    vendor: types.ModuleType,
    tmp_path: Path,
    *,
    sources: dict[str, str] | None = None,
    mappings: tuple[tuple[str, str], ...] | None = None,
) -> types.SimpleNamespace:
    """Build a valid import description and its consumer directory.

    Parameters
    ----------
    vendor
        Loaded core module.
    tmp_path
        Temporary directory for the upstream and consumer trees.
    sources
        Upstream files, defaulting to two minimal guides.
    mappings
        Filename pairs, defaulting to the two minimal guides.

    Returns
    -------
    types.SimpleNamespace
        ``config`` and the ``consumer`` directory.
    """
    source_directory = write_upstream(
        tmp_path,
        sources
        if sources is not None
        else {
            "users-guide.md": "# Users' guide\n\nText.\n",
            "v0-2-0-migration-guide.md": "# Migration guide\n\nText.\n",
        },
    )
    consumer = tmp_path / "consumer" / "docs"
    consumer.mkdir(parents=True)
    config = vendor.VendorConfig(
        tag="v0.2.0-beta2",
        repository="leynos/cuprum",
        source_directory=source_directory,
        output_directory=consumer,
        mappings=mappings
        if mappings is not None
        else (
            ("users-guide.md", "cuprum-users-guide.md"),
            ("v0-2-0-migration-guide.md", "cuprum-v0-2-0-migration-guide.md"),
        ),
        source_path="docs",
    )
    return types.SimpleNamespace(config=config, consumer=consumer)


def convert_fragment(vendor: types.ModuleType, tmp_path: Path, markdown: str) -> str:
    """Convert one Markdown fragment under a valid configuration."""
    config = make_config(vendor, tmp_path, sources={"users-guide.md": "# Title\n"})
    return vendor.convert(f"# Title\n\n{markdown}\n", config.config, "users-guide.md")


def pinned(path: str, *, tag: str = "v0.2.0-beta2") -> str:
    """Build the blob URL the tool should emit for one source path."""
    return f"https://github.com/leynos/cuprum/blob/{tag}/{path}"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("[guide](other.md)", f"[guide]({pinned('docs/other.md')})"),
        (
            "[guide](other.md#part)",
            f"[guide]({pinned('docs/other.md')}#part)",
        ),
        (
            '[guide](./other.md "Title")',
            f'[guide]({pinned("docs/other.md")} "Title")',
        ),
        (
            "[guide](<other file.md>)",
            f"[guide](<{pinned('docs/other file.md')}>)",
        ),
        (
            "![diagram](images/diagram.png)",
            "![diagram](https://raw.githubusercontent.com/leynos/cuprum/"
            "v0.2.0-beta2/docs/images/diagram.png)",
        ),
        (
            "![diagram](<images/one two.png>)",
            "![diagram](<https://raw.githubusercontent.com/leynos/cuprum/"
            "v0.2.0-beta2/docs/images/one two.png>)",
        ),
        ("[root](/README.md)", f"[root]({pinned('README.md')})"),
        (
            "[directory](adr/)",
            "[directory](https://github.com/leynos/cuprum/tree/"
            "v0.2.0-beta2/docs/adr)",
        ),
        ("[parent](../README.md)", f"[parent]({pinned('README.md')})"),
        (
            "[migration](v0-2-0-migration-guide.md#moving)",
            "[migration](cuprum-v0-2-0-migration-guide.md#moving)",
        ),
        ("[anchor](#program-catalogue)", "[anchor](#program-catalogue)"),
        ("[web](https://example.com/x)", "[web](https://example.com/x)"),
        ("[mail](mailto:dev@example.org)", "[mail](mailto:dev@example.org)"),
        ("[cdn](//cdn.example.org/x)", "[cdn](//cdn.example.org/x)"),
        (
            "prefix[adjacent](other.md)",
            f"prefix[adjacent]({pinned('docs/other.md')})",
        ),
        (
            "[`code`](other.md)",
            f"[`code`]({pinned('docs/other.md')})",
        ),
    ],
)
def test_inline_link_forms_are_rewritten_without_touching_the_label(
    vendor: types.ModuleType,
    tmp_path: Path,
    markdown: str,
    expected: str,
) -> None:
    """Each inline form keeps its label, delimiter, title, and fragment."""
    converted = convert_fragment(vendor, tmp_path, markdown)

    assert expected in converted, converted


@pytest.mark.parametrize(
    "markdown",
    [
        "```markdown\n[guide](other.md)\n```",
        "~~~\n[guide](other.md)\n~~~",
        "Inline `[guide](other.md)` stays code.",
        "A sentence with a footnote.[^1]\n\n[^1]: [guide](other.md)",
        "<!-- [guide](other.md) -->",
    ],
)
def test_protected_text_is_left_byte_for_byte(
    vendor: types.ModuleType,
    tmp_path: Path,
    markdown: str,
) -> None:
    """Fences, inline code, footnotes, and comments carry no rewritten link."""
    converted = convert_fragment(vendor, tmp_path, markdown)

    assert markdown in converted, converted


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        (
            '[ref]: other.md "A title"',
            f'[ref]: {pinned("docs/other.md")} "A title"',
        ),
        (
            "[ref]: <other.md>",
            f"[ref]: <{pinned('docs/other.md')}>",
        ),
        (
            '[ref]:\n    other.md "A title"',
            f'[ref]:\n    {pinned("docs/other.md")} "A title"',
        ),
        (
            "[ref]:\n    <other.md>",
            f"[ref]:\n    <{pinned('docs/other.md')}>",
        ),
    ],
)
def test_link_reference_definitions_are_rewritten(
    vendor: types.ModuleType,
    tmp_path: Path,
    definition: str,
    expected: str,
) -> None:
    """Definitions keep their label, angle delimiter, and title."""
    converted = convert_fragment(vendor, tmp_path, definition)

    assert expected in converted, converted


def test_a_link_escaping_the_repository_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A relative link cannot resolve above the upstream repository root."""
    with pytest.raises(vendor.VendorError, match="escapes the upstream repository"):
        convert_fragment(vendor, tmp_path, "[outside](../../elsewhere.md)")


def test_converted_document_matches_the_snapshot(
    vendor: types.ModuleType, tmp_path: Path, snapshot: object
) -> None:
    """The whole conversion, note included, is pinned as one snapshot."""
    config = make_config(
        vendor,
        tmp_path,
        sources={"users-guide.md": SNAPSHOT_SOURCE},
        mappings=(("users-guide.md", "cuprum-users-guide.md"),),
    )

    converted = vendor.convert(
        SNAPSHOT_SOURCE, config.config, "users-guide.md"
    )

    assert converted == snapshot


def test_the_note_is_inserted_once_after_the_first_heading(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The canonical note follows the H1 with one blank line on each side."""
    config = make_config(
        vendor,
        tmp_path,
        sources={"users-guide.md": "# Title\n\n\nBody.\n"},
    )

    converted = vendor.convert(
        "# Title\n\n\nBody.\n", config.config, "users-guide.md"
    )
    note = vendor.NOTE_TEMPLATE.format(
        project="cuprum", tag="v0.2.0-beta2", repository="leynos/cuprum"
    )

    assert converted == f"# Title\n\n{note}\nBody.\n"


def test_a_source_carrying_the_note_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A second conversion of an already vendored file would stack notes."""
    config = make_config(vendor, tmp_path)

    with pytest.raises(vendor.VendorError, match="canonical import marker"):
        vendor.convert(
            f"# Title\n\n> {vendor.IMPORT_MARKER}cuprum `v1`.**\n",
            config.config,
            "users-guide.md",
        )


def test_a_source_without_a_heading_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The note has a fixed insertion point, so a heading is required."""
    config = make_config(vendor, tmp_path)

    with pytest.raises(vendor.VendorError, match="level-one heading"):
        vendor.convert("Body without a heading.\n", config.config, "users-guide.md")


def test_a_heading_inside_a_fence_does_not_receive_the_note(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The first ATX H1 outside fenced code is the insertion point."""
    config = make_config(vendor, tmp_path)
    source = "```markdown\n# Not a heading\n```\n\n# Title\n\nBody.\n"

    converted = vendor.convert(source, config.config, "users-guide.md")

    assert converted.index("```markdown") < converted.index("Imported from")
    assert converted.count("Imported from") == 1
    assert converted.index("Imported from") < converted.index("Body.")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"repository": "cuprum"}, "repository must be"),
        ({"repository": "https://github.com/leynos/cuprum"}, "repository must be"),
        ({"tag": ""}, "tag is not a valid"),
        ({"tag": "v1/../main"}, "tag is not a valid"),
        ({"line_length": 0}, "line length must be positive"),
        ({"code_line_length": 0}, "code line length must be positive"),
        ({"source_path": "../docs"}, "source path must stay inside"),
        ({"mappings": ()}, "at least one source/output mapping"),
        ({"mappings": (("missing.md", "out.md"),)}, "source file does not exist"),
        (
            {"mappings": (("users-guide.md", "sub/out.md"),)},
            "output name must be a bare filename",
        ),
        (
            {"mappings": (("users-guide.md", "out.txt"),)},
            "output name must end in '.md'",
        ),
        (
            {
                "mappings": (
                    ("users-guide.md", "one.md"),
                    ("users-guide.md", "two.md"),
                )
            },
            "source is mapped more than once",
        ),
        (
            {
                "mappings": (
                    ("users-guide.md", "same.md"),
                    ("v0-2-0-migration-guide.md", "same.md"),
                )
            },
            "output is mapped more than once",
        ),
    ],
)
def test_arguments_are_validated_before_any_file_is_written(
    vendor: types.ModuleType,
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    """An unusable argument produces a one-line refusal."""
    config = make_config(vendor, tmp_path).config
    candidate = dataclasses.replace(config, **change)

    with pytest.raises(vendor.VendorError, match=message):
        vendor.validate(candidate)


def test_a_missing_source_or_output_directory_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """Directories are checked before conversion starts."""
    config = make_config(vendor, tmp_path).config

    with pytest.raises(vendor.VendorError, match="source directory does not exist"):
        vendor.validate(
            dataclasses.replace(config, source_directory=tmp_path / "absent")
        )
    with pytest.raises(vendor.VendorError, match="output directory does not exist"):
        vendor.validate(
            dataclasses.replace(config, output_directory=tmp_path / "absent")
        )


def test_a_long_paragraph_is_bracketed_for_the_consumer_gate(
    vendor: types.ModuleType,
) -> None:
    """The smallest enclosing paragraph receives one disable/enable pair."""
    paragraph = (
        "A paragraph whose first line carries a great many words and keeps "
        "going past the limit.\nIt continues on a second line."
    )
    document = f"# Title\n\n{paragraph}\n\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    assert vendor.long_lines(document)
    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        f"{paragraph}\n\n"
        "<!-- markdownlint-enable MD013 -->"
    ) in converted


def test_a_whole_list_is_bracketed_rather_than_one_item(
    vendor: types.ModuleType,
) -> None:
    """A long list item must not split the list into separately judged items."""
    listing = (
        "- A first item with a great many words that runs well past the "
        "eighty column limit and keeps going for another few words.\n"
        "- A second, short item.\n"
    )
    document = f"# Title\n\n{listing}\nAfter.\n"

    converted = vendor.insert_exemptions(document)

    disabled = converted.index("<!-- markdownlint-disable MD013 -->")
    enabled = converted.index("<!-- markdownlint-enable MD013 -->")
    assert converted.index("- A first item") > disabled
    assert converted.index("- A second, short item.") < enabled


def test_a_blockquote_is_bracketed_as_a_whole(
    vendor: types.ModuleType,
) -> None:
    """A long line inside a blockquote exempts the quote, not its neighbours."""
    document = (
        "# Title\n\n"
        "> A quoted sentence with a great many words that runs past the "
        "eighty column limit and keeps going.\n"
        "> A second quoted line.\n\n"
        "After.\n"
    )

    converted = vendor.insert_exemptions(document)

    assert (
        "<!-- markdownlint-disable MD013 -->\n\n"
        "> A quoted sentence"
    ) in converted
    assert converted.index("> A second quoted line.") < converted.index(
        "<!-- markdownlint-enable MD013 -->"
    )


def test_tables_headings_and_short_code_are_left_alone(
    vendor: types.ModuleType,
) -> None:
    """The shared configuration exempts tables and headings; code has 120."""
    document = (
        "# A heading whose text is comfortably longer than eighty characters "
        "but is exempt\n\n"
        "| Column one | Column two |\n"
        "| --- | --- |\n"
        "| A table cell whose row is deliberately long enough to exceed the "
        "prose limit | Value |\n\n"
        "```text\n"
        + "x" * 110
        + "\n```\n"
    )

    converted = vendor.insert_exemptions(document)

    assert "markdownlint" not in converted
    assert vendor.long_lines(document) == ()


def test_exemption_insertion_is_idempotent(vendor: types.ModuleType) -> None:
    """A second pass sees the first pass's bounded exemptions and adds none."""
    document = (
        "# Title\n\nA paragraph with enough words to exceed the configured "
        "prose line limit by a comfortable margin and keep going.\n"
    )

    once = vendor.insert_exemptions(document)
    twice = vendor.insert_exemptions(once)

    assert once == twice


def test_vendor_writes_in_mapping_order_and_is_reproducible(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """The same tag, sources, and deterministic formatter produce the same bytes."""
    mappings = (
        ("v0-2-0-migration-guide.md", "zzz-migration.md"),
        ("users-guide.md", "aaa-users.md"),
    )
    config = make_config(vendor, tmp_path, mappings=mappings).config

    def deterministic_format(paths: Sequence[Path]) -> None:
        """Rewrite every file with its own content, changing nothing."""
        for path in paths:
            path.write_bytes(path.read_bytes())

    first = vendor.vendor(config, format_files=deterministic_format)
    first_bytes = {path.name: path.read_bytes() for path in first}
    second = vendor.vendor(config, format_files=deterministic_format)
    second_bytes = {path.name: path.read_bytes() for path in second}

    assert [path.name for path in first] == [
        "zzz-migration.md",
        "aaa-users.md",
    ]
    assert first_bytes == second_bytes


def test_a_formatter_that_does_not_reach_a_fixed_point_is_refused(
    vendor: types.ModuleType, tmp_path: Path
) -> None:
    """A formatter that changes its own output on every pass fails loudly."""
    config = make_config(vendor, tmp_path).config

    def drifting_format(paths: Sequence[Path]) -> None:
        """Append one line on every invocation."""
        for path in paths:
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\nformatter noise\n")

    with pytest.raises(vendor.VendorError, match="did not reach a fixed point"):
        vendor.vendor(config, format_files=drifting_format)


FENCE_BODY = st.text(
    alphabet=st.characters(blacklist_characters="`\r"),
    max_size=60,
)


@given(body=FENCE_BODY)
@settings(max_examples=30, deadline=None)
def test_fenced_code_is_preserved_under_generated_content(
    vendor: types.ModuleType, body: str
) -> None:
    """No generated fence body has a byte rewritten by link conversion."""
    config = vendor.VendorConfig(
        tag="v1.0.0",
        repository="owner/project",
        source_directory=Path("/unused"),
        output_directory=Path("/unused"),
        mappings=(("users-guide.md", "out.md"),),
    )
    document = f"# Title\n\n```text\n{body}\n```\n"

    converted = vendor.convert(document, config, "users-guide.md")

    assert f"```text\n{body}\n```" in converted


@given(document=st.text(max_size=200))
@settings(max_examples=30, deadline=None)
def test_exemption_insertion_is_idempotent_for_generated_documents(
    vendor: types.ModuleType, document: str
) -> None:
    """Any input reaches a fixed point after one exemption pass."""
    once = vendor.insert_exemptions(document)

    assert vendor.insert_exemptions(once) == once


def test_the_command_line_reports_an_invalid_mapping_without_a_traceback(
    tmp_path: Path,
) -> None:
    """A declared input error is one diagnostic line and status one."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the command line")

    result = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
        [
            uv,
            "run",
            "--script",
            str(CLI_PATH),
            "--tag",
            "v0.2.0-beta2",
            "--repository",
            "leynos/cuprum",
            "--source",
            str(tmp_path),
            "--output",
            str(tmp_path),
            "--map",
            "not-a-pair",
            "--no-format",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "vendor_tagged_guides: error: --map expects SRC=OUT" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.slow
def test_the_real_command_line_and_markdown_gates_reach_a_fixed_point(
    tmp_path: Path,
) -> None:
    """A consumer checkout converts twice with no diff and passes both gates."""
    tools = {
        name: shutil.which(name) or str(Path.home() / ".bun" / "bin" / name)
        for name in ("uv", REAL_FORMATTER, REAL_LINTER)
    }
    for name, path in tools.items():
        if not Path(path).exists():
            pytest.skip(f"{name} is unavailable; the end-to-end run is skipped")

    source_directory = write_upstream(
        tmp_path,
        {
            "users-guide.md": (
                "# Users' guide\n\n"
                "## Program catalogue\n\n"
                "See the [migration guide](v0-2-0-migration-guide.md#moving)\n"
                "and the [developers' guide](developers-guide.md).\n\n"
                "A line with two adjacent links that the formatter rejoins: "
                "[the first guide](https://example.com/one) and "
                "[the second guide](https://example.com/two) are both useful.\n"
            ),
            "v0-2-0-migration-guide.md": (
                "# Migration guide\n\n"
                "## Moving from 0.1\n\n"
                "Start with the [users' guide](users-guide.md#program-catalogue).\n"
            ),
        },
    )
    consumer = tmp_path / "consumer"
    (consumer / "docs").mkdir(parents=True)
    (consumer / ".markdownlint-cli2.jsonc").write_bytes(
        MARKDOWNLINT_CONFIG.read_bytes()
    )

    def invoke(*, expect: int = 0) -> subprocess.CompletedProcess[str]:
        """Run the vendoring front end from the consumer checkout."""
        result = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
            [
                tools["uv"],
                "run",
                "--script",
                str(CLI_PATH),
                "--tag",
                "v0.2.0-beta2",
                "--repository",
                "leynos/cuprum",
                "--source",
                str(source_directory),
                "--output",
                "docs",
                "--map",
                "users-guide.md=cuprum-users-guide.md",
                "--map",
                "v0-2-0-migration-guide.md=cuprum-v0-2-0-migration-guide.md",
            ],
            cwd=consumer,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
        assert result.returncode == expect, result.stdout + result.stderr
        return result

    invoke()
    written = sorted((consumer / "docs").glob("*.md"))
    first = {path.name: path.read_bytes() for path in written}
    invoke()
    second = {path.name: path.read_bytes() for path in written}

    assert first == second

    formatter = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
        [tools[REAL_FORMATTER], "--check", *FORMATTER_ARGUMENTS, *map(str, written)],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert formatter.returncode == 0, formatter.stdout + formatter.stderr

    linter = subprocess.run(  # noqa: S603 - controlled arguments, no shell.
        [tools[REAL_LINTER], *map(str, written)],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert linter.returncode == 0, linter.stdout + linter.stderr