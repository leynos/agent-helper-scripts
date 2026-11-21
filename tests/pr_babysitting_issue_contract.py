"""Check the original-issue assessment contract in the shipped text.

The ExecPlan assessment work added a third pre-readiness conversation. Its
guards live in `skills/pr-babysitting/references/execplan-assessment.md` and
are quoted by `tests/assessment_mutation_cases.py`. This module owns the
section-local assertions so that the main examples module and the issue
module can both apply them without duplicating the wording.
"""

from __future__ import annotations

from assessment_mutation_cases import (
    ISSUE_BODY,
    ISSUE_BODY_FIELD,
    ISSUE_HEADING,
    ISSUE_NOT_APPLICABLE,
    ISSUE_READINESS,
    ISSUE_REQUEST,
)
from skill_contract_support import fenced_request, section

ISSUE_REQUEST_FIELDS = (
    "@coderabbitai please assess the implementation in this PR for completeness and correctness against the original issue:",
    "Published head: <full head SHA>; comparison base: <full base SHA>.",
    'Original issue: <issue URL>. Incorporated comments: <each incorporated comment\'s URL and quoted text, or "none fed the requirements">.',
    "Assessment-ID: <unique request marker>.",
    "Please echo the Assessment-ID, the assessed base/head, and the issue text you assessed in your substantive reply.",
)


def issue_assessment_contract(assessment: str, skill: str) -> None:
    """Check the issue assessment's subject, request and gate wording."""
    issue = section(assessment, ISSUE_HEADING)
    assert (
        "An issue-derived PR must record the original issue body it was assessed"
        " against; without it there is no question to ask."
    ) in issue, ISSUE_BODY
    assert (
        "For an issue-derived PR, readiness also requires a clear original-issue"
        " completeness and correctness verdict for the same base/head; a clear"
        " ExecPlan or proof verdict alone does not satisfy the gate."
    ) in issue, ISSUE_READINESS
    assert (
        "An issue-derived PR cannot record the original-issue assessment as not"
        " applicable."
    ) in issue, ISSUE_NOT_APPLICABLE
    issue_request = fenced_request(assessment, ISSUE_HEADING)
    assert ISSUE_BODY_FIELD in issue_request, ISSUE_REQUEST
    for field in ISSUE_REQUEST_FIELDS:
        assert field in issue_request, f"issue request must name: {field}"
    readiness = section(assessment, "Readiness and later changes")
    assert "includes the original-issue assessment of an issue-derived PR" in readiness, (
        "readiness section must carry the issue assessment into the gate"
    )
    merge = section(skill, "10. End cosmetic review churn, then squash-merge safely")
    assert "Applicable ExecPlan completeness/correctness, proof-specific, and original-issue assessments cover the accepted candidate, with no unresolved substantive concern" in merge, "merge checklist must require candidate-bound assessments"