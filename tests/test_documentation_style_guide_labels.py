"""Contract tests for the ADR and RFC section labels in the style guide.

The style guide's ``## Headings`` rule requires a bold label in a required or
conditional section list to use sentence case and to match a heading in the
corresponding template, treating a slash-separated label as one heading. These
tests load the shipped guide at the test boundary, pass its lines into pure
parsing helpers, and assert the exact label sets, that every label without an
alignment exemption resolves to a template heading, and that the rule keeps
each of its clauses, so a title-case regression, a list/template divergence,
or an inverted rule fails here rather than reaching a vendoring repository.
"""

from __future__ import annotations

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

#: The complete clauses the heading rule must state, with the line breaks
#: normalized to single spaces. Asserting whole clauses, rather than isolated
#: phrases, makes negated wording fail as well as missing wording.
HEADING_RULE_CLAUSES = (
    "Write headings in sentence case: capitalize only the first word and any "
    "proper nouns, acronyms, or other words that are always capitalized, for "
    "example `Context and problem statement` and `RFC number`.",
    "Treat a bold label in a list of required or conditional sections as a "
    "heading for this rule because readers write it as the section heading.",
    "Spell it in sentence case and match the corresponding template heading.",
    "Where such a label offers alternatives separated by a slash, for example "
    "`Proposed design / proposed change`, treat the whole label as one heading.",
    "Capitalize only its first word and any proper nouns or acronyms, and use "
    "one alternative consistently within the document.",
    "Labels that describe a metadata field or give guidance rather than name a "
    "heading, such as `Title` or `Opening section`, are prose and are exempt "
    "from this rule.",
    "Use Markdown headings (`#`, `##`, `###`, and so on) in order without "
    "skipping levels.",
)

#: Inverted versions of each clause, used to prove the assertions reject a
#: negated rule rather than merely matching a shared phrase.
NEGATED_HEADING_RULE_CLAUSES = (
    (
        HEADING_RULE_CLAUSES[0],
        "Write headings in title case: capitalize every significant word.",
    ),
    (
        HEADING_RULE_CLAUSES[1],
        "Do not treat a bold label in a list of required or conditional "
        "sections as a heading for this rule because readers write it as the "
        "section heading.",
    ),
    (
        HEADING_RULE_CLAUSES[2],
        "Spell it in title case and ignore the corresponding template heading.",
    ),
    (
        HEADING_RULE_CLAUSES[3],
        "Where such a label offers alternatives separated by a slash, for "
        "example `Proposed design / proposed change`, treat each alternative "
        "as its own heading.",
    ),
    (
        HEADING_RULE_CLAUSES[4],
        "Capitalize only its first word and any proper nouns or acronyms, and "
        "choose an alternative freely within the document.",
    ),
    (
        HEADING_RULE_CLAUSES[5],
        "Labels that describe a metadata field or give guidance rather than "
        "name a heading, such as `Title` or `Opening section`, are headings "
        "and are subject to this rule.",
    ),
    (
        HEADING_RULE_CLAUSES[6],
        "Use Markdown headings in any order, skipping levels where convenient.",
    ),
)

_HEADING_RE = re.compile(r"^(?P<hashes>#{2,4}) (?P<title>.+)$")
_LABEL_RE = re.compile(r"^- \*\*(?P<label>[^*]+?):\*\*")
_TEMPLATE_HEADING_RE = re.compile(r"^## (?P<title>.+)$")
_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,})(?P<language>[^\s`]*)\s*$")


@pytest.fixture(scope="module")
def guide_lines() -> list[str]:
    """Return the shipped guide's lines, or fail the test that needs them."""
    try:
        text = STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    except OSError as error:
        pytest.fail(f"cannot read the style guide at {STYLE_GUIDE_PATH}: {error}")
    return text.splitlines()


def _is_fence_close(line: str, fence: str) -> bool:
    """Return whether a line closes a fence opened with ``fence`` backticks."""
    stripped = line.strip()
    return len(stripped) >= len(fence) and set(stripped) == {"`"}


def _section_body(lines: list[str], heading: str) -> list[str]:
    """Return the lines under a heading, up to the next same-or-higher heading.

    A heading inside a fenced block is template content, not a section
    boundary, so fences are tracked and their lines always belong to the
    enclosing section.
    """
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


def _template_headings(lines: list[str], heading: str) -> tuple[str, ...]:
    """Return the level-two headings of a fenced Markdown template."""
    body = _section_body(lines, heading)
    opener = next(
        (
            (index, match)
            for index, line in enumerate(body)
            if (match := _FENCE_OPEN_RE.match(line)) is not None
            and match.group("language") == "markdown"
        ),
        None,
    )
    if opener is None:
        raise AssertionError(f"{heading!r} has no Markdown fence")
    opener_index, opener_match = opener
    headings: list[str] = []
    for line in body[opener_index + 1 :]:
        if _is_fence_close(line, opener_match.group("fence")):
            break
        match = _TEMPLATE_HEADING_RE.match(line)
        if match is not None:
            headings.append(match.group("title"))
    return tuple(headings)


def _is_sentence_case(label: str) -> bool:
    """Return whether a label capitalizes its first word and no others.

    Proper nouns and acronyms are not modelled; the exact label assertions
    cover the shipped set, and this generic check guards against a title-case,
    lower-case, or shouted label being added later.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", label)
    return (
        bool(words)
        and words[0][0].isupper()
        and words[0][1:] == words[0][1:].lower()
        and all(word.islower() for word in words[1:])
    )


def _template_heading_matches(label: str, headings: set[str]) -> list[str]:
    """Return the template headings a label may be written as.

    A slash-separated label is one heading whose alternatives the template may
    spell with either choice, so both the whole label and each alternative,
    capitalized as a heading, are accepted.
    """
    alternatives = [part.strip() for part in label.split(" / ")]
    candidates = [label]
    candidates.extend(
        alternative[:1].upper() + alternative[1:] for alternative in alternatives
    )
    return sorted({candidate for candidate in candidates if candidate in headings})


def _normalize(lines: list[str]) -> str:
    """Join lines into one space-separated string."""
    return re.sub(r"\s+", " ", " ".join(line.strip() for line in lines)).strip()


def _assert_heading_rule(rule: str) -> None:
    """Assert the heading rule states each expected clause."""
    for clause in HEADING_RULE_CLAUSES:
        assert clause in rule, f"the heading rule is missing {clause!r}"


@pytest.mark.parametrize(("list_heading", "_template", "expected", "_exempt"), LISTS)
def test_section_list_labels_are_spelled_exactly(
    guide_lines: list[str],
    list_heading: str,
    _template: str,
    expected: tuple[str, ...],
    _exempt: frozenset[str],
) -> None:
    """Each section list carries exactly its sentence-case labels."""
    actual = _labels(_section_body(guide_lines, list_heading))
    assert actual == expected, (
        f"{list_heading} labels are {actual!r}, expected {expected!r}"
    )


@pytest.mark.parametrize(("list_heading", "_template", "expected", "_exempt"), LISTS)
def test_section_labels_use_sentence_case(
    guide_lines: list[str],
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
    guide_lines: list[str],
    list_heading: str,
    template_heading: str,
    expected: tuple[str, ...],
    exempt: frozenset[str],
) -> None:
    """Every label without an alignment exemption resolves to a template heading."""
    headings = set(_template_headings(guide_lines, template_heading))
    missing = [
        label
        for label in expected
        if label not in exempt and not _template_heading_matches(label, headings)
    ]
    assert not missing, (
        f"{list_heading} labels without a {template_heading} heading: "
        f"{missing!r}; template headings are {sorted(headings)!r}"
    )


@pytest.mark.parametrize(
    ("list_heading", "template_heading", "expected", "_exempt"), LISTS
)
def test_slash_labels_use_one_template_alternative(
    guide_lines: list[str],
    list_heading: str,
    template_heading: str,
    expected: tuple[str, ...],
    _exempt: frozenset[str],
) -> None:
    """A slash-separated label uses only one alternative in its template."""
    headings = set(_template_headings(guide_lines, template_heading))
    offenders = [
        label
        for label in expected
        if " / " in label and len(_template_heading_matches(label, headings)) > 1
    ]
    assert not offenders, (
        f"{list_heading} labels with more than one {template_heading} heading: "
        f"{offenders!r}"
    )


def test_heading_rule_states_each_clause(guide_lines: list[str]) -> None:
    """The heading rule states every required clause in full."""
    _assert_heading_rule(_normalize(_section_body(guide_lines, "Headings")))


@pytest.mark.parametrize(("clause", "inverted"), NEGATED_HEADING_RULE_CLAUSES)
def test_inverted_heading_rule_clause_is_rejected(
    guide_lines: list[str], clause: str, inverted: str
) -> None:
    """Replacing a clause with its inversion makes the rule assertion fail."""
    rule = _normalize(_section_body(guide_lines, "Headings"))
    assert clause in rule, f"the heading rule is missing {clause!r}"
    with pytest.raises(AssertionError):
        _assert_heading_rule(rule.replace(clause, inverted))


def test_sentence_case_exemptions_are_documented(guide_lines: list[str]) -> None:
    """Every exempt label is listed by the guide and named by its rule."""
    rule = _normalize(_section_body(guide_lines, "Headings"))
    assert "such as `Title` or `Opening section`" in rule, (
        "the heading rule does not document the `Title` and "
        "`Opening section` exemptions"
    )
    documented = {
        label
        for section in LISTS
        for label in _labels(_section_body(guide_lines, section.heading))
    }
    undocumented = SENTENCE_CASE_EXEMPT_LABELS - documented
    assert not undocumented, (
        f"the tests exempt labels the guide never lists: {sorted(undocumented)!r}"
    )