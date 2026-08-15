"""Contract tests for the ExecPlans skill documentation."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "execplans" / "SKILL.md"
TEMPLATE_PATH = SKILL_PATH.parent / "references" / "execplan-template.md"
MANDATORY_SECTIONS_HEADING = "## Mandatory living sections (always present)"
SECTION_REFERENCE_RE = re.compile(r"^- `(?P<section>[^`]+)`", re.MULTILINE)
TEMPLATE_HEADING_RE = re.compile(r"^## (?P<section>.+)$", re.MULTILINE)


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def test_mandatory_skill_section_references_exist_in_template() -> None:
    """Every required ExecPlan section named by the skill has a template heading."""
    skill = _read(SKILL_PATH)
    _, separator, section_block = skill.partition(MANDATORY_SECTIONS_HEADING)
    assert separator, "the skill must define its mandatory-section list"
    section_block, _, _ = section_block.partition("\n## ")

    referenced_sections = SECTION_REFERENCE_RE.findall(section_block)
    assert referenced_sections, "the mandatory-section list must name sections"

    template_headings = set(TEMPLATE_HEADING_RE.findall(_read(TEMPLATE_PATH)))
    missing_sections = sorted(set(referenced_sections) - template_headings)
    assert not missing_sections, (
        "every mandatory section named by the skill must have an exact template "
        f"heading; missing: {missing_sections}"
    )
