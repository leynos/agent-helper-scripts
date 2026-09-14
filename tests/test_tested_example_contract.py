"""Contract tests for the tested-example markers in the published guides.

These tests read the two published, user-facing documents named in the
style guide's "Tested correctness" bullet directly from their shipped paths,
never from a copied fixture, and assert that each satisfies the contract in
full: every executable fence carries a marker, every identifier is unique
within its document, and no fence is left unterminated. A regression in
either document's markers, or a bug in the loader itself, fails one of these
tests rather than surfacing only when a downstream example-execution test
silently stops running.
"""

from __future__ import annotations

from pathlib import Path

from tested_example_test_support import TestedExample, load_tested_examples

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DAISYUI_GUIDE_PATH = REPOSITORY_ROOT / "documentation-library" / "daisyui-v5-guide.md"
FEMTOLOGGING_GUIDE_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "femtologging-users-guide.md"
)

#: Measured fence counts for each guide, kept here so a change to either
#: document's example count is a deliberate, reviewed edit to this test
#: rather than a silent drift.
DAISYUI_EXPECTED_EXAMPLE_COUNT = 93
FEMTOLOGGING_EXPECTED_EXAMPLE_COUNT = 14


def _assert_contract_satisfied(
    examples: list[TestedExample], *, expected_count: int
) -> None:
    """Assert a loaded document's examples satisfy the tested-example contract."""
    assert len(examples) == expected_count, (
        f"expected {expected_count} tested examples, found {len(examples)}"
    )
    identifiers = [example.identifier for example in examples]
    assert len(identifiers) == len(set(identifiers)), (
        "tested-example identifiers must be unique within a document, "
        f"found duplicates in {identifiers!r}"
    )
    for example in examples:
        assert example.identifier, "an identifier must not be empty"
        assert example.language, (
            f"tested example {example.identifier!r} at line {example.line} "
            "has no fence language"
        )


def test_the_daisyui_guide_marks_every_html_and_css_fence() -> None:
    """The daisyUI guide's 87 html and 6 css fences are all marked and unique."""
    examples = load_tested_examples(DAISYUI_GUIDE_PATH)
    _assert_contract_satisfied(
        examples, expected_count=DAISYUI_EXPECTED_EXAMPLE_COUNT
    )
    languages = {example.language for example in examples}
    assert languages == {"html", "css"}, (
        f"expected only html and css fences, found languages {languages!r}"
    )


def test_the_femtologging_guide_marks_every_executable_fence_but_not_mermaid() -> None:
    """The femtologging guide marks its 14 code fences and skips its 2 diagrams."""
    examples = load_tested_examples(FEMTOLOGGING_GUIDE_PATH)
    _assert_contract_satisfied(
        examples, expected_count=FEMTOLOGGING_EXPECTED_EXAMPLE_COUNT
    )
    languages = {example.language for example in examples}
    assert languages == {"python", "bash", "rust"}, (
        f"expected python, bash and rust fences only, found {languages!r}"
    )
    assert "mermaid" not in languages, (
        "mermaid fences are outside the tested-example contract and must "
        "never be returned as tested examples"
    )
