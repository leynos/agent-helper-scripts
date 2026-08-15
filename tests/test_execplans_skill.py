"""Contract tests for the ExecPlans verification-planning documentation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "execplans" / "SKILL.md"
TEMPLATE_PATH = SKILL_PATH.parent / "references" / "execplan-template.md"
MANDATORY_SECTIONS_HEADING = "## Mandatory living sections (always present)"
VERIFICATION_PLAN = "Verification plan"
VERIFICATION_PLAN_REQUIREMENT = (
    "Every ExecPlan must contain a `Verification plan` that:"
)
MANDATORY_VERIFICATION_PLAN_REFERENCE = f"- `{VERIFICATION_PLAN}`"
VERIFICATION_PLAN_HEADING = f"## {VERIFICATION_PLAN}"
REQUIRED_OBLIGATION_FIELDS = (
    "Obligation",
    "Method",
    "Rationale",
    "Domain",
    "Artefact",
    "Evidence",
    "Non-vacuity",
)
NEGATIVE_CONTROL_REQUIREMENT = (
    "negative control, seeded fault, or representative mutation"
)
SECTION_REFERENCE_RE = re.compile(r"^- `(?P<section>[^`]+)`", re.MULTILINE)
TEMPLATE_HEADING_RE = re.compile(r"^## (?P<section>.+)$", re.MULTILINE)
VERIFICATION_PLAN_SECTION_RE = re.compile(
    rf"^{re.escape(VERIFICATION_PLAN_HEADING)}\n"
    r"(?P<section>.*?)(?=^## |\Z)",
    re.MULTILINE | re.DOTALL,
)

REQUIRED_SKILL_CONCEPTS = {
    "invariants": "states each invariant",
    "lemmas or intermediate contracts": "states each lemma or intermediate contract",
    "non-trivial axioms": "lists every non-trivial axiom",
    "verification methods": "a verification method, planned artefact",
    "commands and expected evidence": "command, expected evidence, and discharge condition",
    "bounds, abstractions, or residual gaps": (
        "any bound, abstraction, or residual gap"
    ),
    "non-vacuity checks": "Record the non-vacuity checks",
    "negative control": NEGATIVE_CONTROL_REQUIREMENT,
    "third-party interfaces as assumptions": "third-party interfaces;",
    "third-party proof boundary": "Treat their documented interfaces as axioms.",
    "repository-owned integration verification": (
        "verify the repository-owned logic against the real interface or a "
        "faithful contract-level boundary."
    ),
}
REQUIRED_TEMPLATE_CONCEPTS = {
    "invariants": "every invariant",
    "lemmas or intermediate contracts": "every lemma or intermediate contract",
    "non-trivial axioms": "non-trivial axioms",
    "proportionate verification methods": "why this method provides proportionate rigour",
    "verification artefacts": "repository-relative test, harness, model, or proof path",
    "commands and expected evidence": (
        "command, expected initial failure or counterexample, and discharge condition"
    ),
    "bounds, abstractions, or residual gaps": (
        "bounds, abstractions, and residual gaps"
    ),
    "non-vacuity checks": "Non-vacuity",
    "negative control": NEGATIVE_CONTROL_REQUIREMENT,
    "third-party interfaces as assumptions": "third-party interfaces.",
    "third-party proof boundary": "Do not attempt to verify third-party internals.",
    "repository-owned integration verification": (
        "plan verification against the real interface or a faithful "
        "contract-level boundary."
    ),
}


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _normalize(markdown: str) -> str:
    """Collapse Markdown line wrapping before checking prose requirements."""
    return " ".join(markdown.split())


def _mandatory_section_block(skill: str) -> str:
    """Return the canonical required-section list from a skill document."""
    _, separator, section_block = skill.partition(MANDATORY_SECTIONS_HEADING)
    assert separator, "the skill must define its mandatory-section list"
    section_block, _, _ = section_block.partition("\n## ")
    return section_block


def _verification_plan_section(template: str) -> str:
    """Return the template's exact Verification plan section body."""
    match = VERIFICATION_PLAN_SECTION_RE.search(template)
    assert match, "the template must contain an exact `## Verification plan` heading"
    return match.group("section")


def _assert_concepts(
    markdown: str, requirements: dict[str, str], document_name: str
) -> None:
    """Require every fixed verification concept from one contract document."""
    normalized_markdown = _normalize(markdown)
    for concept, required_text in requirements.items():
        assert required_text in normalized_markdown, (
            f"the {document_name} must retain {concept}: `{required_text}`"
        )


def _validate_verification_planning_contract(skill: str, template: str) -> None:
    """Validate the non-optional ExecPlan verification-planning contract."""
    normalized_skill = _normalize(skill)
    assert VERIFICATION_PLAN_REQUIREMENT in normalized_skill, (
        "the skill must explicitly require `Verification plan` for every ExecPlan"
    )

    mandatory_sections = _mandatory_section_block(skill)
    assert MANDATORY_VERIFICATION_PLAN_REFERENCE in mandatory_sections, (
        "the mandatory-section list must explicitly include `Verification plan`"
    )

    verification_section = _verification_plan_section(template)
    template_headings = set(TEMPLATE_HEADING_RE.findall(template))
    referenced_sections = SECTION_REFERENCE_RE.findall(mandatory_sections)
    missing_sections = sorted(set(referenced_sections) - template_headings)
    assert not missing_sections, (
        "every mandatory section named by the skill must have an exact template "
        f"heading; missing: {missing_sections}"
    )

    for field in REQUIRED_OBLIGATION_FIELDS:
        assert re.search(rf"^- {re.escape(field)}:", verification_section, re.MULTILINE), (
            "the template verification plan must include required field "
            f"`{field}`"
        )

    assert NEGATIVE_CONTROL_REQUIREMENT in _normalize(verification_section), (
        "the template verification plan must require a negative control, seeded "
        "fault, or representative mutation"
    )
    _assert_concepts(skill, REQUIRED_SKILL_CONCEPTS, "skill")
    _assert_concepts(template, REQUIRED_TEMPLATE_CONCEPTS, "template")


def _remove_obligation_field(template: str, field: str) -> str:
    """Return an in-memory template mutation with one required field removed."""
    pattern = rf"^- {re.escape(field)}:.*\n(?:  .*\n)*"
    mutated_template, replacements = re.subn(pattern, "", template, count=1, flags=re.MULTILINE)
    assert replacements == 1, f"test fixture must contain the `{field}` field"
    return mutated_template


def test_execplan_verification_planning_contract() -> None:
    """The live skill and template retain the complete verification contract."""
    _validate_verification_planning_contract(_read(SKILL_PATH), _read(TEMPLATE_PATH))


def test_contract_rejects_missing_mandatory_verification_plan() -> None:
    """Removing the mandatory Verification plan reference must fail the contract."""
    skill = _read(SKILL_PATH).replace(MANDATORY_VERIFICATION_PLAN_REFERENCE, "", 1)

    with pytest.raises(
        AssertionError,
        match=re.escape(
            "the mandatory-section list must explicitly include `Verification plan`"
        ),
    ):
        _validate_verification_planning_contract(skill, _read(TEMPLATE_PATH))


def test_contract_rejects_missing_verification_plan_heading() -> None:
    """Removing the exact template heading must fail the contract."""
    template = _read(TEMPLATE_PATH).replace(VERIFICATION_PLAN_HEADING, "", 1)

    with pytest.raises(
        AssertionError,
        match=re.escape(
            "the template must contain an exact `## Verification plan` heading"
        ),
    ):
        _validate_verification_planning_contract(_read(SKILL_PATH), template)


def test_contract_rejects_missing_non_vacuity_field() -> None:
    """Removing a required per-obligation field must fail the contract."""
    template = _remove_obligation_field(_read(TEMPLATE_PATH), "Non-vacuity")

    with pytest.raises(
        AssertionError,
        match=re.escape(
            "the template verification plan must include required field `Non-vacuity`"
        ),
    ):
        _validate_verification_planning_contract(_read(SKILL_PATH), template)


def test_contract_rejects_missing_negative_control_requirement() -> None:
    """Removing the negative-control requirement must fail the contract."""
    template = _read(TEMPLATE_PATH).replace(NEGATIVE_CONTROL_REQUIREMENT, "", 1)

    with pytest.raises(
        AssertionError,
        match=re.escape(
            "the template verification plan must require a negative control, seeded "
            "fault, or representative mutation"
        ),
    ):
        _validate_verification_planning_contract(_read(SKILL_PATH), template)
