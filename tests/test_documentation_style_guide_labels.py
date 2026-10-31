"""Contract tests for the ADR and RFC section labels in the style guide.

The style guide's ``## Headings`` rule requires a bold label in a required or
conditional section list to use sentence case and to match a heading in the
corresponding template, treating a slash-separated label as one heading. These
tests read the shipped guide and assert the exact label sets, that every
non-exempt label resolves to a template heading, and that the rule keeps its
slash, exemption, and metadata wording, so a title-case regression or a
list/template divergence fails here rather than reaching a vendoring
repository.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
import re
from typing import NamedTuple

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STYLE_GUIDE_PATH = (
    REPOSITORY_ROOT / "documentation-library" / "documentation-style-guide.md"
)

#: Bold labels that describe a metadata field or give guidance rather than
#: name a heading. The heading rule exempts them from sentence case. This is
#: wider than the template-alignment exemptions: a metadata label may still
#: appear as a template heading, as ADR ``Status`` and ``Date`` do.
SENTENCE_CASE_EXEMPT_LABELS = frozenset(
    {"Title", "RFC number", "Status", "Created", "Date", "Opening section"}
)

RFC_REQUIRED_LABELS = (
    "Title",
    "Preamble",
    "RFC number",
    "Status",
    "Created",
    "Opening section",
)
RFC_CONDITIONAL_LABELS = (
    "Problem",
    "Current state",
    "Goals and non-goals",
    "Proposed design / proposed change",
    "Requirements",
    "Compatibility and migration",
    "Alternatives considered",
    "Open questions / outstanding decisions",
    "Recommendation",
)
ADR_REQUIRED_LABELS = ("Status", "Date", "Context and problem statement")
ADR_CONDITIONAL_LABELS = (
    "Decision drivers",
    "Requirements",
    "Options considered",
    "Decision outcome / proposed direction",
    "Goals and non-goals",
    "Migration plan",
    "Known risks and limitations",
    "Outstanding decisions",
    "Architectural rationale",
)

class SectionList(NamedTuple):
    """One section list and the template it must match."""

    heading: str
    template: str
    labels: tuple[str, ...]
    #: Labels with no template heading of their own. ``Status`` is metadata in
    #: the RFC template but a heading in the ADR template, so this exemption
    #: is per list rather than global.
    alignment_exempt: frozenset[str]


#: Each section list, the template it must match, and its exact labels.
LISTS = (
    SectionList(
        "RFC required sections",
        "RFC template",
        RFC_REQUIRED_LABELS,
        frozenset({"Title", "RFC number", "Status", "Created", "Opening section"}),
    ),
    SectionList(
        "RFC conditional sections",
        "RFC template",
        RFC_CONDITIONAL_LABELS,
        frozenset(),
    ),
    SectionList("Required sections", "ADR template", ADR_REQUIRED_LABELS, frozenset()),
    SectionList(
        "Conditional sections", "ADR template", ADR_CONDITIONAL_LABELS, frozenset()
    ),
)

_HEADING_RE = re.compile(r"^(?P<hashes>#{2,4}) (?P<title>.+)$")
_LABEL_RE = re.compile(r"^- \*\*(?P<label>[^*]+?):\*\*")
_TEMPLATE_HEADING_RE = re.compile(r"^## (?P<title>.+)$")
_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,})(?P<language>[^\s`]*)\s*$")


def _is_fence_close(line: str, fence: str) -> bool:
    """Return whether a line closes a fence opened with ``fence`` backticks."""
    stripped = line.strip()
    return len(stripped) >= len(fence) and set(stripped) == {"`"}


@cache
def _guide_text() -> str:
    """Return the shipped style guide's text."""
    return STYLE_GUIDE_PATH.read_text(encoding="utf-8")


def _section_body(heading: str) -> list[str]:
    """Return the lines under a heading, up to the next same-or-higher heading.

    A heading inside a fenced block is template content, not a section
    boundary, so fences are tracked and their lines always belong to the
    enclosing section.
    """
    lines = _guide_text().splitlines()
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match is None or match.group("title") != heading:
            continue
        level = len(match.group("hashes"))
        body: list[str] = []
        fence = ""
        for candidate in lines[index + 1 :]:
            if fence:
                body.append(candidate)
                if _is_fence_close(candidate, fence):
                    fence = ""
                continue
            opening = _FENCE_OPEN_RE.match(candidate)
            if opening is not None:
                fence = opening.group("fence")
                body.append(candidate)
                continue
            nested = _HEADING_RE.match(candidate)
            if nested is not None and len(nested.group("hashes")) <= level:
                break
            body.append(candidate)
        return body
    raise AssertionError(f"the style guide has no {heading!r} heading")


def _labels(lines: list[str]) -> tuple[str, ...]:
    """Return the bold labels of a section list, in document order."""
    return tuple(
        match.group("label")
        for line in lines
        if (match := _LABEL_RE.match(line)) is not None
    )


def _template_headings(heading: str) -> tuple[str, ...]:
    """Return the level-two headings of a fenced Markdown template."""
    lines = _section_body(heading)
    opener = next(
        (
            (index, match)
            for index, line in enumerate(lines)
            if (match := _FENCE_OPEN_RE.match(line)) is not None
            and match.group("language") == "markdown"
        ),
        None,
    )
    if opener is None:
        raise AssertionError(f"{heading!r} has no Markdown fence")
    opener_index, opener_match = opener
    headings: list[str] = []
    for line in lines[opener_index + 1 :]:
        if _is_fence_close(line, opener_match.group("fence")):
            break
        match = _TEMPLATE_HEADING_RE.match(line)
        if match is not None:
            headings.append(match.group("title"))
    return tuple(headings)


def _is_sentence_case(label: str) -> bool:
    """Return whether a label capitalizes its first word and no others.

    Proper nouns and acronyms are not modelled; the exact label assertions
    above cover the shipped set, and this generic check guards against a
    title-case or lower-case label being added later.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", label)
    return bool(words) and words[0][0].isupper() and all(
        word.islower() for word in words[1:]
    )


def _matches_template_heading(label: str, headings: set[str]) -> bool:
    """Return whether a label or one of its alternatives is a template heading.

    A slash-separated label is one heading whose alternatives the template may
    spell with either choice, so both the whole label and each alternative,
    capitalized as a heading, are accepted.
    """
    if label in headings:
        return True
    alternatives = (part.strip() for part in label.split(" / "))
    return any(
        alternative[:1].upper() + alternative[1:] in headings
        for alternative in alternatives
    )


@pytest.mark.parametrize(("list_heading", "_template", "expected", "_exempt"), LISTS)
def test_section_list_labels_are_spelled_exactly(
    list_heading: str,
    _template: str,
    expected: tuple[str, ...],
    _exempt: frozenset[str],
) -> None:
    """Each section list carries exactly its sentence-case labels."""
    assert _labels(_section_body(list_heading)) == expected


@pytest.mark.parametrize(("list_heading", "_template", "expected", "_exempt"), LISTS)
def test_section_labels_use_sentence_case(
    list_heading: str,
    _template: str,
    expected: tuple[str, ...],
    _exempt: frozenset[str],
) -> None:
    """Every non-exempt label capitalizes only its first word."""
    offenders = [
        label
        for label in expected
        if label not in SENTENCE_CASE_EXEMPT_LABELS and not _is_sentence_case(label)
    ]
    assert not offenders, f"{list_heading} has title-case labels: {offenders!r}"


@pytest.mark.parametrize(
    ("list_heading", "template_heading", "expected", "exempt"), LISTS
)
def test_every_section_label_matches_a_template_heading(
    list_heading: str,
    template_heading: str,
    expected: tuple[str, ...],
    exempt: frozenset[str],
) -> None:
    """Every label without an alignment exemption resolves to a template heading."""
    headings = set(_template_headings(template_heading))
    missing = [
        label
        for label in expected
        if label not in exempt and not _matches_template_heading(label, headings)
    ]
    assert not missing, (
        f"{list_heading} labels without a {template_heading} heading: "
        f"{missing!r}; template headings are {sorted(headings)!r}"
    )


def test_heading_rule_names_the_slash_rule_and_exempt_labels() -> None:
    """The heading rule states the slash treatment and the exemptions."""
    rule = "\n".join(_section_body("Headings"))
    assert "treat the whole label as one heading" in rule
    assert "`Proposed design / proposed change`" in rule
    for label in ("`Title`", "`Opening section`"):
        assert label in rule, f"the heading rule does not exempt {label}"