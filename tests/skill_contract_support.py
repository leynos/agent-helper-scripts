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


def fenced_request(markdown: str, heading: str) -> str:
    """Return the single fenced request block inside one level-2 section.

    A request template is a fence a human copies and posts. Its fields must
    live inside that fence: prose that mentions them elsewhere in the same
    section does not travel with the request. Extracting the fence keeps a
    contract on the posted text rather than on the surrounding commentary.

    Parameters
    ----------
    markdown : str
        Document to search.
    heading : str
        Level-2 heading text identifying the enclosing section.

    Returns
    -------
    str
        The fenced block's content, whitespace-normalized, without markers.

    Raises
    ------
    AssertionError
        Raised unless the section holds exactly one fenced block.
    """
    body = raw_section(markdown, heading)
    fences = re.findall(r"^```[^\n]*\n(.*?)^```", body, re.M | re.S)
    assert len(fences) == 1, f"expected one fenced request in section: {heading}"
    return normalize(fences[0])


def move_out_of_fence(markdown: str, heading: str, clause: str) -> str:
    """Relocate a clause from a section's fence to the prose around it.

    The clause stays inside the same level-2 section, so a section-wide
    assertion still matches. Only a request-local contract notices the move,
    which is exactly the defect this proves against.

    Parameters
    ----------
    markdown : str
        Document to mutate.
    heading : str
        Level-2 heading text identifying the enclosing section.
    clause : str
        Clause to lift out of the fence. Any whitespace run matches any other.

    Returns
    -------
    str
        The mutated document.

    Raises
    ------
    AssertionError
        Raised unless the clause matches exactly once in the section body.
    """
    body = raw_section(markdown, heading)
    mutated_body = mutate_one_clause(body, clause, "")
    return markdown.replace(body, mutated_body + "\n" + normalize(clause) + "\n", 1)


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
