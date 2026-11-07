"""Shared Markdown helpers for section-local skill contract tests.

Several skills are prose, so their contract tests read repository Markdown and
assert on structure or wording. Those tests need the same three operations:
`section` to isolate one heading's body, `mutate_one_clause` to seed a defect,
and `normalize` to compare prose across line wrapping.

Keeping one definition here means a contract cannot be checked by a stricter
or looser helper than its sibling, and a fix to the matching rule reaches
every caller. The helpers never touch the filesystem, so they are safe to call
from any test module.
"""

from __future__ import annotations

import re


def normalize(markdown: str) -> str:
    """Collapse prose line wrapping so a contract survives reflow.

    Parameters
    ----------
    markdown : str
        Document or fragment, possibly wrapped across lines.

    Returns
    -------
    str
        The text with every whitespace run reduced to one space.
    """
    return " ".join(markdown.split())


def raw_section(markdown: str, heading: str) -> str:
    """Return the body of one unique level-2 section, preserving its wrapping.

    The heading is plain text without the leading ``## ``. Requiring exactly
    one match means a guard cannot satisfy the contract by appearing in a
    second, unrelated section.

    Parameters
    ----------
    markdown : str
        Document to search.
    heading : str
        Level-2 heading text identifying the section.

    Returns
    -------
    str
        The section body, from after its heading to the next level-2 heading.

    Raises
    ------
    AssertionError
        Raised when no section, or more than one, carries the heading.
    """
    matches = re.findall(
        r"^## " + re.escape(heading) + r"[ \t]*\r?\n(.*?)(?=^## |\Z)",
        markdown,
        re.M | re.S,
    )
    assert len(matches) == 1, f"expected unique section: {heading}"
    return matches[0]


def section(markdown: str, heading: str) -> str:
    """Return one unique level-2 section with its wrapping already collapsed.

    Parameters
    ----------
    markdown : str
        Document to search.
    heading : str
        Level-2 heading text identifying the section.

    Returns
    -------
    str
        The section body, whitespace-normalized.
    """
    return normalize(raw_section(markdown, heading))


def mutate_one_clause(
    source: str, old: str, new: str, *, move: bool = False
) -> str:
    """Replace or relocate the one clause matching ``old``, ignoring wrapping.

    Matching on flexible whitespace means a reflow of the guarded prose does
    not break a fixture whose policy is unchanged. Exactly one match is
    required so a control cannot silently reach a similar clause.

    Parameters
    ----------
    source : str
        Document to mutate.
    old : str
        Clause to find. Any run of whitespace in it matches any other.
    new : str
        Replacement text. Use ``""`` to delete the clause.
    move : bool, optional
        When true, append the matched clause under an unrelated heading
        instead of deleting it, proving a section-local guard fails when its
        clause moves elsewhere. Defaults to false.

    Returns
    -------
    str
        The mutated document.

    Raises
    ------
    AssertionError
        Raised when ``old`` matches anything other than exactly once.
    """
    pattern = r"\s+".join(map(re.escape, old.split()))
    matches = list(re.finditer(pattern, source))
    assert len(matches) == 1, "mutation fixture must identify one actual clause"
    match = matches[0]
    mutated = source[: match.start()] + new + source[match.end() :]
    if move:
        mutated += "\n## Unrelated notes\n\n" + match.group() + "\n"
    return mutated
