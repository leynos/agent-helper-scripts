"""Shared loader for the tested-example contract.

The documentation style guide's "Tested correctness" bullet
(``documentation-library/documentation-style-guide.md``) requires every
executable fenced example in a published, user-facing document to carry a
``<!-- tested-example: <identifier> -->`` marker on the line immediately
before its fence, so a shared loader can pull the example straight out of the
shipped Markdown and hand it to a test.

This module is that loader. It reads a Markdown file from disk, by path, and
returns the fenced examples the contract covers, or raises with a message
naming the file and line for every violation the contract forbids: an
executable fence with no marker, a marker with an empty identifier, a
duplicate identifier within the document, and a fence that is never closed.

Executable-language decision
-----------------------------
The guide names Mermaid diagrams as outside the contract; they are checked by
the separate diagram-rendering gate instead. Every other fence language,
including an empty (missing) language tag, is treated as executable and so
requires a marker. Two consequences follow from treating a missing language
as executable rather than silently exempting it:

* the style guide already requires every fence to declare a language, so a
  fence with none is far more likely to be an overlooked code sample than a
  deliberate diagram; and
* failing closed on it turns the omission into a test failure that names the
  file and line, rather than an example quietly falling outside the
  contract's coverage.

Only Mermaid is carved out, because it is the one language the guide
explicitly assigns to a different gate; nothing else gets a free pass.

Identifier scheme
------------------
This module does not derive identifiers; it only validates and reports the
ones already written in the document (see the two published guides for the
identifiers actually used, for example ``daisyui-avatar-basic`` and
``femtologging-handler-flush``). Callers are expected to name each marker
after the surrounding section or component, rather than a positional counter,
so that reordering a document does not renumber unrelated markers.

Marker placement
-----------------
The guide says a marker must sit "immediately" before its fence, and does
not say blank lines between the two are permitted, so this loader requires
strict adjacency: the marker comment must be the line directly above the
fence's opening line (matching indentation is not required, since a marker
may sit inside a list item at a different apparent depth than the source
line it decorates). A marker separated from its fence by a blank line, or by
any other content, does not count as marking that fence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

__all__ = (
    "NON_EXECUTABLE_LANGUAGES",
    "TestedExample",
    "TestedExampleError",
    "load_tested_examples",
)

#: Languages the tested-example contract does not cover. Mermaid fences are
#: diagrams, checked by the repository's separate diagram-rendering gate, so
#: they neither require nor reject a ``tested-example`` marker.
NON_EXECUTABLE_LANGUAGES: frozenset[str] = frozenset({"mermaid"})

#: Matches a marker comment line, capturing its identifier text verbatim
#: (including the case where it is empty, which is rejected downstream with
#: a specific error rather than silently treating the line as prose).
_MARKER_RE = re.compile(
    r"^[ \t]*<!--\s*tested-example:\s*(?P<identifier>.*?)\s*-->\s*$"
)

#: Matches a fence's opening line, capturing its language tag (which may be
#: empty when the author omitted one).
_FENCE_OPEN_RE = re.compile(r"^[ \t]*```(?P<language>[^\s`]*)\s*$")

#: Matches a fence's closing line. Fences in both published documents, and in
#: the inline documents this module's negative tests construct, always use
#: exactly three backticks, so this loader does not need to track the longer
#: backtick runs CommonMark allows for a fence that itself contains a
#: fenced example.
_FENCE_CLOSE_RE = re.compile(r"^[ \t]*```\s*$")


@dataclass(frozen=True, slots=True)
class TestedExample:
    """One fenced example the tested-example contract covers.

    Attributes
    ----------
    identifier
        The stable identifier carried by the example's marker comment.
    language
        The fence's language tag, for example ``python`` or ``html``.
    body
        The fence's content, excluding the fence delimiters themselves.
    line
        The 1-indexed line number of the fence's opening line, for
        diagnostics.
    """

    #: Not a pytest test class; the name matches the contract it models, so
    #: this stops pytest's collector from mistaking it for one.
    __test__ = False

    identifier: str
    language: str
    body: str
    line: int


class TestedExampleError(ValueError):
    """Raised when a document violates the tested-example contract."""

    #: Not a pytest test class; see the note on ``TestedExample`` above.
    __test__ = False


def load_tested_examples(path: Path) -> list[TestedExample]:
    """Load every tested example from a published Markdown file.

    Parameters
    ----------
    path
        The Markdown file to read, from the document as shipped rather than
        a copied fixture.

    Returns
    -------
    list[TestedExample]
        One entry per executable fence, in document order.

    Raises
    ------
    TestedExampleError
        If any executable fence lacks a marker, a marker has an empty
        identifier, an identifier is reused within the document, or a fence
        is never closed. The message names ``path`` and the offending line.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    examples: list[TestedExample] = []
    seen_at: dict[str, int] = {}

    index = 0
    total = len(lines)
    while index < total:
        fence_match = _FENCE_OPEN_RE.match(lines[index])
        if fence_match is None:
            index += 1
            continue

        fence_line = index + 1
        language = fence_match.group("language")
        marker_identifier = _marker_identifier_before(lines, index, path, fence_line)

        body_lines, body_end_index = _read_fence_body(lines, index, path, fence_line)

        if language in NON_EXECUTABLE_LANGUAGES:
            index = body_end_index + 1
            continue

        if marker_identifier is None:
            raise TestedExampleError(
                f"{path}:{fence_line}: executable fence (language "
                f"{language!r}) is missing a `tested-example` marker "
                "immediately before it"
            )

        first_seen = seen_at.get(marker_identifier)
        if first_seen is not None:
            raise TestedExampleError(
                f"{path}:{fence_line}: duplicate tested-example identifier "
                f"{marker_identifier!r} (first used at line {first_seen})"
            )
        seen_at[marker_identifier] = fence_line

        examples.append(
            TestedExample(
                identifier=marker_identifier,
                language=language,
                body="\n".join(body_lines),
                line=fence_line,
            )
        )
        index = body_end_index + 1

    return examples


def _marker_identifier_before(
    lines: list[str], fence_index: int, path: Path, fence_line: int
) -> str | None:
    """Return the identifier of the marker immediately above a fence.

    Returns ``None`` when no marker line sits directly above the fence.
    Raises when a marker is present but its identifier is empty.
    """
    if fence_index == 0:
        return None
    marker_match = _MARKER_RE.match(lines[fence_index - 1])
    if marker_match is None:
        return None
    identifier = marker_match.group("identifier")
    if not identifier:
        raise TestedExampleError(
            f"{path}:{fence_line}: `tested-example` marker has no identifier"
        )
    return identifier


def _read_fence_body(
    lines: list[str], fence_index: int, path: Path, fence_line: int
) -> tuple[list[str], int]:
    """Return a fence's body lines and the index of its closing line.

    Raises when the fence is never closed before the document ends.
    """
    cursor = fence_index + 1
    total = len(lines)
    while cursor < total:
        if _FENCE_CLOSE_RE.match(lines[cursor]):
            return lines[fence_index + 1 : cursor], cursor
        cursor += 1
    raise TestedExampleError(
        f"{path}:{fence_line}: fence opened here is never closed"
    )
