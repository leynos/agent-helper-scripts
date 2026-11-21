"""Check the original-issue assessment contract in the shipped text.

`tests/pr_babysitting_issue_contract.py` holds the section-local assertions;
this module reads the shipped documents and applies them. The mutation
controls stay in `tests/test_pr_babysitting_examples.py`, which applies the
same contract to every mutated copy.
"""

from __future__ import annotations

from pathlib import Path

from pr_babysitting_issue_contract import issue_assessment_contract

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "skills/pr-babysitting/references/execplan-assessment.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"


def test_issue_assessment_guards_control_the_shipped_sections() -> None:
    """The parent skill and assessment reference carry the third gate."""
    issue_assessment_contract(ASSESSMENT.read_text(), SKILL.read_text())