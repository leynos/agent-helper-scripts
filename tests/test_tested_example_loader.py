"""Negative tests for the tested-example loader's contract enforcement.

Each test builds a small inline document string, rather than reading a real
library file, so the failure it targets is isolated from the two published
guides' content. Every assertion checks the specific diagnostic the loader
raises, not merely that some exception was raised, so a future change that
swaps one violation's error for another's is caught here rather than in a
downstream document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tested_example_test_support import TestedExampleError, load_tested_examples

DOCUMENT_NAME = "inline-document.md"


def _write_document(tmp_path: Path, content: str) -> Path:
    """Write ``content`` to a scratch Markdown file and return its path."""
    document_path = tmp_path / DOCUMENT_NAME
    document_path.write_text(content, encoding="utf-8")
    return document_path


def test_an_unmarked_executable_fence_is_rejected(tmp_path: Path) -> None:
    """A python fence with no preceding marker fails, naming its line."""
    document_path = _write_document(
        tmp_path,
        "# Heading\n\n```python\nprint('hi')\n```\n",
    )
    with pytest.raises(TestedExampleError) as excinfo:
        load_tested_examples(document_path)
    message = str(excinfo.value)
    assert f"{document_path}:3" in message, message
    assert "missing a `tested-example` marker" in message, message


def test_a_marker_with_a_missing_identifier_is_rejected(tmp_path: Path) -> None:
    """A marker comment with no identifier text fails, naming its fence's line."""
    document_path = _write_document(
        tmp_path,
        "<!-- tested-example:  -->\n```bash\necho hi\n```\n",
    )
    with pytest.raises(TestedExampleError) as excinfo:
        load_tested_examples(document_path)
    message = str(excinfo.value)
    assert f"{document_path}:2" in message, message
    assert "has no identifier" in message, message


def test_a_duplicate_identifier_is_rejected(tmp_path: Path) -> None:
    """Reusing an identifier within a document fails, naming both lines."""
    document_path = _write_document(
        tmp_path,
        (
            "<!-- tested-example: shared-name -->\n"
            "```bash\necho one\n```\n\n"
            "<!-- tested-example: shared-name -->\n"
            "```bash\necho two\n```\n"
        ),
    )
    with pytest.raises(TestedExampleError) as excinfo:
        load_tested_examples(document_path)
    message = str(excinfo.value)
    assert "duplicate tested-example identifier 'shared-name'" in message, message
    assert "first used at line 2" in message, message
    assert f"{document_path}:7" in message, message


def test_an_unterminated_fence_is_rejected(tmp_path: Path) -> None:
    """A fence with no closing delimiter fails, naming its opening line."""
    document_path = _write_document(
        tmp_path,
        "<!-- tested-example: never-closed -->\n```python\nprint('hi')\n",
    )
    with pytest.raises(TestedExampleError) as excinfo:
        load_tested_examples(document_path)
    message = str(excinfo.value)
    assert f"{document_path}:2" in message, message
    assert "is never closed" in message, message


def test_a_mermaid_fence_needs_no_marker_and_is_not_returned(
    tmp_path: Path,
) -> None:
    """An unmarked mermaid fence is accepted and excluded from the results."""
    document_path = _write_document(
        tmp_path,
        "```mermaid\nflowchart TD\n  A --> B\n```\n",
    )
    examples = load_tested_examples(document_path)
    assert examples == [], (
        "a mermaid fence must never be returned as a tested example, even "
        "when it carries no marker"
    )


def test_a_marked_mermaid_fence_is_also_accepted_and_not_returned(
    tmp_path: Path,
) -> None:
    """A mermaid fence carrying a marker is accepted but still excluded."""
    document_path = _write_document(
        tmp_path,
        "<!-- tested-example: diagram-that-is-not-tested -->\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n",
    )
    examples = load_tested_examples(document_path)
    assert examples == [], (
        "a marker before a mermaid fence must not cause it to be returned, "
        "since mermaid fences neither require nor reject a marker"
    )
