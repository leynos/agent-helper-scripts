"""Shared Markdown helpers for the comenq-coderabbit contract tests.

The skill under test is prose, so every contract test reads repository
Markdown and asserts on its structure or wording. This module holds the file
paths, the parsing regexes, and the mutation helper the negative controls
need, so the focused test modules share one definition of "read the section"
and "remove one passage" instead of re-deriving them.

Paths resolve from this file, so they identify the same repository files no
matter which test module imports the helper.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
SKILL_ROOT: Path = REPO_ROOT / "skills" / "comenq-coderabbit"
SKILL_PATH: Path = SKILL_ROOT / "SKILL.md"
FAILURE_MODES_PATH: Path = SKILL_ROOT / "references" / "failure-modes-and-recovery.md"
EVIDENCE_PATH: Path = SKILL_ROOT / "references" / "evidence-and-rehearsal.md"
USERS_GUIDE_PATH: Path = REPO_ROOT / "docs" / "users-guide.md"
MIGRATION_GUIDE_PATH: Path = REPO_ROOT / "docs" / "v0-2-0-migration-guide.md"
README_PATH: Path = REPO_ROOT / "README.md"

LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)\s]+)\)")
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
LEVEL_TWO_RE = re.compile(r"^## (?P<title>.+)$", re.MULTILINE)
SCENARIO_RE = re.compile(r"^(?P<number>\d+)\. \*\*", re.MULTILINE)
SCENARIO_BLOCK_RE = re.compile(
    r"^(?P<number>\d+)\. \*\*(?P<title>.*?)\*\*(?P<body>.*?)"
    r"(?=^\d+\. \*\*|\Z)",
    re.MULTILINE | re.DOTALL,
)


def read(path: Path) -> str:
    """Read one repository contract file.

    Parameters
    ----------
    path : Path
        File to read.

    Returns
    -------
    str
        The file's decoded contents.

    Raises
    ------
    OSError
        Raised when the file cannot be read.
    UnicodeDecodeError
        Raised when the file is not valid UTF-8.
    """
    return path.read_text(encoding="utf-8")


def normalize(markdown: str) -> str:
    """Collapse Markdown line wrapping before checking prose requirements.

    Parameters
    ----------
    markdown : str
        Document or fragment, possibly wrapped across lines.

    Returns
    -------
    str
        The text with every run of whitespace reduced to one space.
    """
    return " ".join(markdown.split())


def section(markdown: str, heading: str) -> str:
    """Return the body of one level-2 section, up to the next level-2 heading.

    Parameters
    ----------
    markdown : str
        Document to search.
    heading : str
        Exact level-2 heading line that opens the section.

    Returns
    -------
    str
        The section body.

    Raises
    ------
    AssertionError
        Raised when the document does not define the section.
    """
    _, separator, remainder = markdown.partition(f"{heading}\n")
    assert separator, f"the document must define the {heading!r} section"
    body, _, _ = remainder.partition("\n## ")
    return body


def slugify(heading: str) -> str:
    """Return the GitHub anchor for one Markdown heading.

    Parameters
    ----------
    heading : str
        Heading text without its leading hash marks.

    Returns
    -------
    str
        The anchor GitHub derives from the heading.
    """
    lowered = re.sub(r"[`*_]", "", heading.strip().lower())
    return re.sub(r"[^a-z0-9\- ]", "", lowered).replace(" ", "-")


def assert_links_resolve(markdown: str, source: Path, document_name: str) -> None:
    """Require every repository-relative link and anchor to resolve.

    Parameters
    ----------
    markdown : str
        Document whose links are checked.
    source : Path
        File the links are relative to.
    document_name : str
        Human-readable name used in failure messages.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when a link target or anchor does not resolve.
    OSError
        Raised when a linked file cannot be read.
    UnicodeDecodeError
        Raised when a linked file is not valid UTF-8.
    """
    for target in LINK_RE.findall(markdown):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, anchor = target.partition("#")
        resolved = source if not path_part else (source.parent / path_part).resolve()
        assert resolved.is_file(), (
            f"the {document_name} must link to an existing file: {target}"
        )
        if anchor:
            headings = {
                slugify(title)
                for title in HEADING_RE.findall(resolved.read_text(encoding="utf-8"))
            }
            assert anchor in headings, (
                f"the {document_name} anchor {anchor!r} must resolve in "
                f"{resolved.name}"
            )


def level_two_blocks(markdown: str) -> list[str]:
    """Return each level-2 section body, excluding any preamble.

    Parameters
    ----------
    markdown : str
        Document to split.

    Returns
    -------
    list of str
        One entry per level-2 section, in document order.
    """
    return re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]


def without(document: str, text: str) -> str:
    """Remove one wrapped prose passage, tolerating the document's line breaks.

    Parameters
    ----------
    document : str
        Document to mutate.
    text : str
        Passage to remove, matched with any run of whitespace between words.

    Returns
    -------
    str
        The document with the first matching passage removed.

    Raises
    ------
    AssertionError
        Raised when the passage does not occur, which would leave the
        negative control asserting against an unmodified document.
    """
    pattern = re.compile(r"\s+".join(map(re.escape, text.split())))
    mutated, replacements = pattern.subn("", document, count=1)
    assert replacements == 1, f"the negative control must find {text!r} to remove"
    return mutated
