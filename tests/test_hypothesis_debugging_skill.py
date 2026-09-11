"""Contract tests for the hypothesis-debugging skill's output-document rules.

The skill names the file a planning agent must write, so the filename is part
of its contract rather than an incidental detail. These tests pin the dated,
problem-specific form, reject the superseded opaque-timestamp form, and require
the users' guide to advertise the same convention.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "hypothesis-debugging"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
USERS_GUIDE_PATH = REPO_ROOT / "docs" / "users-guide.md"
MIGRATION_GUIDE_PATH: Path = REPO_ROOT / "docs" / "v0-2-0-migration-guide.md"

OUTPUT_SECTION_HEADING = "### 4. Output Document"
PLAN_DIRECTORY = "docs/debugging/"
FILENAME_TEMPLATE = "debugging-plan-<year>-<month>-<day>-<problem-slug>.md"

# The concrete form a planning agent must produce: an ISO-ordered date followed
# by a lower-case, hyphen-separated problem slug of at least one word.
CONCRETE_FILENAME = re.compile(
    r"debugging-plan-(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md"
)

# Forms the convention replaced. An opaque timestamp is not sortable by problem
# and carries no indication of what was being debugged.
SUPERSEDED_FILENAME = "debugging-plan-{timestamp}.md"

CODE_SPAN = re.compile(r"`([^`]+)`")


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _skill_frontmatter_and_body() -> tuple[dict[str, object], str]:
    """Return the hypothesis-debugging skill frontmatter and body."""
    content = _read(SKILL_PATH)
    assert content.startswith("---\n"), (
        "the hypothesis-debugging skill must open with the YAML frontmatter "
        "delimiter, with no leading prose"
    )
    parts = content.split("---", maxsplit=2)
    assert len(parts) == 3, "the hypothesis-debugging skill must have frontmatter"
    parsed = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), "skill frontmatter must be a YAML mapping"
    return parsed, parts[2]


def _output_document_section() -> str:
    """Return the body of the skill's output-document instructions."""
    _, body = _skill_frontmatter_and_body()
    _, separator, remainder = body.partition(OUTPUT_SECTION_HEADING)
    assert separator, (
        f"the skill must keep a {OUTPUT_SECTION_HEADING!r} section so the "
        "filename contract has a single documented home"
    )
    section, _, _ = remainder.partition("\n## ")
    return section


def _code_spans(section: str) -> list[str]:
    """Return the code spans in a section with line wrapping removed."""
    return CODE_SPAN.findall(" ".join(section.split()))


@pytest.fixture(name="output_section")
def output_section_fixture() -> str:
    """Provide the skill's output-document section to each test."""
    return _output_document_section()


def test_skill_name_matches_directory() -> None:
    """Discovery resolves the skill by its directory name."""
    frontmatter, _ = _skill_frontmatter_and_body()

    assert frontmatter.get("name") == "hypothesis-debugging", (
        "the skill name must match its directory so discovery resolves it"
    )


def test_output_document_requires_dated_problem_specific_filename(
    output_section: str,
) -> None:
    """The skill states the directory and the dated, slugged filename form."""
    spans = _code_spans(output_section)

    assert PLAN_DIRECTORY in spans, (
        f"the skill must name {PLAN_DIRECTORY!r} as the plan directory"
    )
    assert FILENAME_TEMPLATE in spans, (
        "the skill must require the filename form "
        f"{FILENAME_TEMPLATE!r} so plans stay sortable and identifiable"
    )


def test_output_document_gives_a_conforming_dated_example(
    output_section: str,
) -> None:
    """The worked example is a real date followed by a problem slug."""
    examples = [
        match
        for span in _code_spans(output_section)
        if (match := CONCRETE_FILENAME.fullmatch(span)) is not None
    ]

    assert examples, (
        "the skill must show a concrete example matching "
        f"{FILENAME_TEMPLATE!r}; a template alone leaves the slug ambiguous"
    )

    for example in examples:
        dt.date(
            int(example["year"]),
            int(example["month"]),
            int(example["day"]),
        )
        assert "-" in example["slug"] or example["slug"].isalnum(), (
            "the example slug must be lower-case and hyphen-separated"
        )


def test_output_document_still_requires_delegated_falsification(
    output_section: str,
) -> None:
    """Renaming the plan file did not drop the delegation requirement."""
    collapsed = " ".join(output_section.split())

    assert "assets/debugging-plan.md" in collapsed, (
        "the skill must still point at the plan template"
    )
    assert "`alchemist`" in collapsed, (
        "the skill must still prefer the alchemist sub-agent for execution"
    )
    assert "planning agent is not the execution agent" in collapsed, (
        "the skill must still separate planning from execution"
    )


def test_superseded_timestamp_filename_is_absent() -> None:
    """No skill file may reinstate the opaque-timestamp filename."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in sorted(SKILL_ROOT.rglob("*.md"))
        if SUPERSEDED_FILENAME in _read(path)
    ]

    assert not offenders, (
        f"{SUPERSEDED_FILENAME!r} was replaced by {FILENAME_TEMPLATE!r}; "
        f"still present in: {offenders}"
    )


def test_users_guide_documents_the_filename_convention() -> None:
    """The users' guide advertises the same path and filename contract."""
    guide = " ".join(_read(USERS_GUIDE_PATH).split())

    assert "skills/hypothesis-debugging/SKILL.md" in guide, (
        "the users' guide must link the hypothesis-debugging skill"
    )
    assert PLAN_DIRECTORY in guide, (
        "the users' guide must name the plan output directory"
    )
    assert FILENAME_TEMPLATE in guide, (
        "the users' guide must state the dated, problem-specific filename form"
    )
    assert CONCRETE_FILENAME.search(guide), (
        "the users' guide must show a conforming example filename"
    )


def test_migration_guide_records_the_filename_change() -> None:
    """Existing plans need a documented route to the new convention."""
    migration = " ".join(_read(MIGRATION_GUIDE_PATH).split())

    assert "hypothesis-debugging" in migration, (
        "the migration guide must name the skill whose output changed"
    )
    assert FILENAME_TEMPLATE in migration, (
        "the migration guide must state the replacement filename form"
    )
    assert SUPERSEDED_FILENAME in migration, (
        "the migration guide must name the superseded filename form so "
        "readers can identify plans that need renaming"
    )
