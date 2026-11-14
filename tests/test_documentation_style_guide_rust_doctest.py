"""Contract tests for the Rust API doc comment example in the style guide.

The "API doc comments (Rust)" section ships an example that a reader copies
into a real crate. Rustdoc compiles a doctest as an external crate that
depends on the documented crate, so the example must import the documented
item before calling it, and a runnable example must not be marked ``no_run``.

These tests read the guide from its shipped path, select the section by
heading, and assert the static shape that makes the example resolvable. A
separate ``slow`` test writes the example into a dependency-free crate and
runs ``cargo test --doc``, so a resolution or execution regression fails here
rather than in a repository that vendors the guide verbatim.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from tested_example_test_support import _FENCE_OPEN_RE, _fence_close_pattern

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STYLE_GUIDE_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "documentation-style-guide.md"
)
API_DOC_HEADING = "API doc comments (Rust)"

#: The crate name shared by the hidden import and the execution fixture.
CRATE_NAME = "mycrate"

#: The hidden import line rustdoc compiles but omits from rendered output.
HIDDEN_IMPORT = f"/// # use {CRATE_NAME}::add;"

CARGO_TIMEOUT_SECONDS = 120

_HEADING_RE = re.compile(r"^(?P<hashes>#{2,4}) (?P<title>.+)$")

#: An inner doctest fence lives on a ``///`` doc-comment line. The closing
#: fence matches too, with an empty language, so callers toggle on each match
#: rather than treating every match as an opening fence.
_INNER_FENCE_RE = re.compile(
    r"^\s*///\s*(?P<fence>`{3,})(?P<language>[^\s`]*)\s*$"
)


@pytest.fixture(scope="module")
def guide_lines() -> list[str]:
    """Return the shipped guide's lines, or fail the test that needs them."""
    try:
        text = STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    except OSError as error:
        pytest.fail(f"cannot read the style guide at {STYLE_GUIDE_PATH}: {error}")
    return text.splitlines()


def _section_body(lines: list[str], heading: str) -> list[str]:
    """Return the lines under a heading, up to the next same-or-higher heading.

    A heading inside a fenced block is document content, not a section
    boundary, so fences are tracked and their lines always belong to the
    enclosing section.
    """
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match is None or match.group("title") != heading:
            continue
        level = len(match.group("hashes"))
        body: list[str] = []
        close_re: re.Pattern[str] | None = None
        for candidate in lines[index + 1 :]:
            if close_re is not None:
                body.append(candidate)
                if close_re.match(candidate):
                    close_re = None
                continue
            opening = _FENCE_OPEN_RE.match(candidate)
            if opening is not None:
                close_re = _fence_close_pattern(opening.group("fence"))
                body.append(candidate)
                continue
            nested = _HEADING_RE.match(candidate)
            if nested is not None and len(nested.group("hashes")) <= level:
                break
            body.append(candidate)
        return body
    raise AssertionError(f"the style guide has no {heading!r} heading")


def _outer_rust_fences(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Return the section's top-level fences whose language starts with rust."""
    body = _section_body(lines, API_DOC_HEADING)
    fences: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(body):
        opening = _FENCE_OPEN_RE.match(body[index])
        if opening is None:
            index += 1
            continue
        close_re = _fence_close_pattern(opening.group("fence"))
        fence_body: list[str] = []
        cursor = index + 1
        while cursor < len(body) and not close_re.match(body[cursor]):
            fence_body.append(body[cursor])
            cursor += 1
        assert cursor < len(body), (
            "the API doc example's outer fence is never closed"
        )
        language = opening.group("language")
        if language.startswith("rust"):
            fences.append((language, fence_body))
        index = cursor + 1
    return fences


def _outer_fence(lines: list[str]) -> tuple[str, list[str]]:
    """Return the section's single outer Rust fence, or fail with a diagnostic."""
    fences = _outer_rust_fences(lines)
    assert len(fences) == 1, (
        f"the {API_DOC_HEADING!r} section must contain exactly one outer Rust "
        f"fence, found {len(fences)}"
    )
    return fences[0]


def _inner_fence_languages(body: list[str]) -> list[str]:
    """Return the language of each doctest fence inside the outer fence body."""
    languages: list[str] = []
    inside_fence = False
    for line in body:
        match = _INNER_FENCE_RE.match(line)
        if match is None:
            continue
        if inside_fence:
            inside_fence = False
        else:
            languages.append(match.group("language"))
            inside_fence = True
    return languages


def _line_index(lines: list[str], expected: str) -> int:
    """Return the index of the one line equal to ``expected`` after stripping."""
    matches = [
        index for index, line in enumerate(lines) if line.strip() == expected
    ]
    assert len(matches) == 1, (
        f"expected exactly one {expected!r} line, found {len(matches)}"
    )
    return matches[0]


def test_the_section_has_one_outer_rust_fence(guide_lines: list[str]) -> None:
    """The API doc example is the section's only outer Rust fence."""
    _outer_fence(guide_lines)


def test_the_outer_fence_is_no_run_because_the_snippet_is_a_fragment(
    guide_lines: list[str],
) -> None:
    """The outer fence demonstrates a fragment, so it is marked ``no_run``."""
    language, _ = _outer_fence(guide_lines)
    assert language == "rust,no_run", (
        f"the outer fence is {language!r}, expected 'rust,no_run'"
    )


def test_the_inner_doctest_is_not_marked_no_run(guide_lines: list[str]) -> None:
    """The example's single inner doctest is an unmarked ``rust`` fence."""
    _, body = _outer_fence(guide_lines)
    languages = _inner_fence_languages(body)
    assert languages == ["rust"], (
        "the API doc example must contain exactly one rust inner doctest "
        f"without `no_run`; found {languages!r}"
    )


def test_the_doctest_imports_the_documented_item_before_calling_it(
    guide_lines: list[str],
) -> None:
    """A hidden ``use`` line puts the documented item in the doctest's scope."""
    _, body = _outer_fence(guide_lines)
    import_index = _line_index(body, HIDDEN_IMPORT)
    call_index = _line_index(body, "/// assert_eq!(add(2, 3), 5);")
    assert import_index < call_index, (
        "the hidden import must precede the assertion that calls `add`"
    )


def test_the_example_keeps_its_documented_section_order(
    guide_lines: list[str],
) -> None:
    """The example documents parameters, then returns, then examples."""
    _, body = _outer_fence(guide_lines)
    positions = [
        _line_index(body, f"/// # {heading}")
        for heading in ("Parameters", "Returns", "Examples")
    ]
    assert positions == sorted(positions), (
        f"the documentation sections are out of order: {positions!r}"
    )


def test_the_inline_attribute_follows_the_doc_comment(guide_lines: list[str]) -> None:
    """``#[inline]`` sits after the doc comment and before the function."""
    _, body = _outer_fence(guide_lines)
    doc_indexes = [
        index for index, line in enumerate(body) if line.strip().startswith("///")
    ]
    inline_index = _line_index(body, "#[inline]")
    function_index = _line_index(body, "pub fn add(a: i32, b: i32) -> i32 {")
    assert doc_indexes, "the example has no doc comment lines"
    assert max(doc_indexes) < inline_index < function_index, (
        "`#[inline]` must follow the doc comment and precede the function"
    )


@pytest.mark.slow
def test_the_api_doc_example_executes_as_a_doctest(
    tmp_path: Path, guide_lines: list[str]
) -> None:
    """The shipped example compiles and runs as a rustdoc doctest."""
    _, body = _outer_fence(guide_lines)
    cargo = shutil.which("cargo")
    prerequisite = (
        "cargo is required to execute the style guide's Rust example; "
        "install a stable Rust toolchain"
    )
    if cargo is None:
        if os.environ.get("CI"):
            pytest.fail(prerequisite)
        pytest.skip(prerequisite)

    crate_dir = tmp_path / CRATE_NAME
    (crate_dir / "src").mkdir(parents=True)
    (crate_dir / "Cargo.toml").write_text(
        f'[package]\nname = "{CRATE_NAME}"\nversion = "0.0.0"\n'
        'edition = "2021"\n\n[dependencies]\n',
        encoding="utf-8",
    )
    (crate_dir / "src" / "lib.rs").write_text(
        "\n".join(body) + "\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(crate_dir / "target")
    env.setdefault("CARGO_TERM_COLOR", "never")
    result = subprocess.run(
        [cargo, "test", "--doc", "--offline"],
        cwd=crate_dir,
        env=env,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=CARGO_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        "cargo test --doc failed for the style guide's Rust example\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "running 1 test" in result.stdout, result.stdout
    assert re.search(r"\b1 passed\b", result.stdout) is not None, result.stdout