"""Document contract for the comenq-coderabbit skill.

The workflow is prose, so there is no runtime implementation to exercise and
no queue or GitHub behaviour is touched here. These tests hold the skill, its
references, the users' guide, the migration guide, and the README to the rules
the workflow depends on: routing, candidate evidence, surface retrieval,
disposition, convergence, delegation, and installation.

Each required rule, heading, and named role is paired with a negative control
that removes it in memory and asserts the contract fails, so a required passage
cannot quietly disappear. The document contract is complemented by the offline
decision cases in `test_comenq_coderabbit_rehearsal.py` and by the installer
boundary test in `test_comenq_coderabbit_install.py`.

These tests detect drift between the skill and the decisions the workflow
relies on. They do not prove that an agent follows the skill, and they make no
claim about live queue, reviewer, or integration behaviour.
"""

from __future__ import annotations

import re

import pytest
import yaml

from comenq_coderabbit_contract_data import (
    EVIDENCE_LINK,
    FAILURE_MODES_LINK,
    FAILURE_MODE_CASE_COUNT,
    FAILURE_MODE_MARKERS,
    MIGRATION_GUIDE_HEADING,
    QUEUE_EXAMPLES,
    QUEUE_INTERFACE,
    README_SIGNPOST,
    REHEARSAL_SCENARIO_COUNT,
    REQUIRED_AGENT_ROLES,
    REQUIRED_DESCRIPTION_TRIGGERS,
    REQUIRED_SKILL_HEADINGS,
    REQUIRED_SKILL_RULES,
    SKILL_LINK,
    SKILL_NAME,
    STATE_DIAGRAM,
    SUPPLIED_TEMPLATES,
    INCIDENT_LINKS,
    USERS_GUIDE_HEADING,
    USERS_GUIDE_LINK,
)
from comenq_coderabbit_support import (
    EVIDENCE_PATH,
    FAILURE_MODES_PATH,
    LEVEL_TWO_RE,
    MIGRATION_GUIDE_PATH,
    README_PATH,
    SCENARIO_RE,
    SKILL_PATH,
    USERS_GUIDE_PATH,
    assert_links_resolve,
    level_two_blocks,
    normalize,
    read,
    section,
    without,
)

DELEGATION_HEADING = "## Delegate verification, repair, and validation"


def _frontmatter(content: str) -> tuple[dict[str, object], str]:
    """Return the skill's YAML front matter and body.

    Parameters
    ----------
    content : str
        Full skill document.

    Returns
    -------
    tuple
        The parsed front matter mapping and the body that follows it.

    Raises
    ------
    AssertionError
        Raised when the document does not open with YAML front matter.
    """
    assert content.startswith("---\n"), (
        "the comenq-coderabbit skill must open with the YAML frontmatter "
        "delimiter, with no leading prose"
    )
    parts = content.split("---", maxsplit=2)
    assert len(parts) == 3, "the comenq-coderabbit skill must have YAML frontmatter"
    parsed = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), "the skill frontmatter must be a YAML mapping"
    return parsed, parts[2]


def validate_skill_contract(skill: str, failure_modes: str, evidence: str) -> None:
    """Validate the review workflow's document contract.

    Parameters
    ----------
    skill : str
        Contents of the skill document.
    failure_modes : str
        Contents of the failure-mode reference.
    evidence : str
        Contents of the evidence-and-rehearsal reference.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when a required rule, heading, link, or supplied value is
        missing.
    """
    frontmatter, _ = _frontmatter(skill)
    assert frontmatter.get("name") == SKILL_NAME, (
        "the skill name must match its directory so discovery resolves it"
    )
    description = frontmatter.get("description")
    assert isinstance(description, str), "the skill must declare a description"
    normalized_description = normalize(description)
    for trigger in REQUIRED_DESCRIPTION_TRIGGERS:
        assert trigger in normalized_description, (
            f"discovery metadata must advertise {trigger!r}"
        )

    for heading in REQUIRED_SKILL_HEADINGS:
        assert heading in skill, f"the skill must retain the {heading!r} section"

    normalized_skill = normalize(skill)
    for rule, sentence in REQUIRED_SKILL_RULES.items():
        assert normalize(sentence) in normalized_skill, (
            f"the skill must retain the {rule} rule: `{sentence}`"
        )

    assert QUEUE_INTERFACE in normalized_skill, (
        "the skill must name the managed queue interface it depends on"
    )
    for example in QUEUE_EXAMPLES:
        assert example in skill, f"the skill must document `{example}`"

    assert_links_resolve(skill, SKILL_PATH, "comenq-coderabbit skill")
    validate_failure_modes(failure_modes)
    validate_evidence(evidence)


def validate_delegation_contract(skill: str) -> None:
    """Require the delegation section to keep assigning each named role.

    Parameters
    ----------
    skill : str
        Contents of the skill document.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when the delegation section is missing or stops naming a role.
    """
    delegation = normalize(section(skill, DELEGATION_HEADING))
    for role, rule in REQUIRED_AGENT_ROLES.items():
        assert role in delegation, (
            f"the delegation section must assign work to the {role} role: "
            f"`{REQUIRED_SKILL_RULES[rule]}`"
        )


def validate_failure_modes(failure_modes: str) -> None:
    """Require every recovery case to keep its incident, recovery, and evidence.

    Parameters
    ----------
    failure_modes : str
        Contents of the failure-mode reference.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when a case count, marker, or link is missing.
    """
    titles = LEVEL_TWO_RE.findall(failure_modes)
    assert len(titles) == FAILURE_MODE_CASE_COUNT, (
        f"the recovery reference must keep {FAILURE_MODE_CASE_COUNT} cases, "
        f"found {len(titles)}: {titles}"
    )
    for block in level_two_blocks(failure_modes):
        for marker in FAILURE_MODE_MARKERS:
            assert marker in block, (
                f"every recovery case must keep its {marker} evidence"
            )
    assert_links_resolve(failure_modes, FAILURE_MODES_PATH, "failure-mode reference")


def validate_evidence(evidence: str) -> None:
    """Require the supplied templates, the scenarios, and the source links.

    Parameters
    ----------
    evidence : str
        Contents of the evidence-and-rehearsal reference.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when a supplied template, scenario, or incident link is
        missing.
    """
    for template in SUPPLIED_TEMPLATES:
        assert template in evidence, (
            "the evidence reference must preserve a supplied reconciliation "
            "template verbatim"
        )

    scenarios = [int(number) for number in SCENARIO_RE.findall(evidence)]
    assert scenarios == list(range(1, REHEARSAL_SCENARIO_COUNT + 1)), (
        "the offline rehearsal scenarios must stay a complete, sequential "
        f"1-{REHEARSAL_SCENARIO_COUNT} list, found {scenarios}"
    )

    for link in INCIDENT_LINKS:
        assert link in evidence, f"the incident sources must keep {link}"

    assert_links_resolve(evidence, EVIDENCE_PATH, "evidence reference")


def validate_users_guide(users_guide: str) -> None:
    """Require the user-facing entry, its links, and the captioned diagram.

    Parameters
    ----------
    users_guide : str
        Contents of the users' guide.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when the entry, its links, or the captioned diagram is
        missing.
    """
    content = section(users_guide, USERS_GUIDE_HEADING)
    normalized = normalize(content)

    for link in (SKILL_LINK, FAILURE_MODES_LINK, EVIDENCE_LINK):
        assert link in content, f"the users' guide must link to {link}"
    assert "install-skills" in normalized, (
        "the users' guide must state the skill's installation path"
    )
    for example in ("comenq list", "comenq put"):
        assert example in content, f"the users' guide must show `{example}`"
    assert "already authorized reply route" in normalized, (
        "the users' guide must state the authorized queue boundary"
    )

    diagram = f"```mermaid\n{STATE_DIAGRAM}```"
    assert diagram in content, (
        "the users' guide must carry the supplied review-lifecycle state diagram"
    )

    caption = content.partition("```\n\nFigure 1:")[2]
    assert caption, "the state diagram must be followed by its figure caption"
    normalized_caption = normalize(caption)
    assert "review lifecycle" in normalized_caption, (
        "the caption must name the lifecycle it describes"
    )
    assert "andon" in normalized_caption, (
        "the caption must describe the andon outcomes the diagram shows"
    )


def validate_migration_guide(migration_guide: str) -> None:
    """Require the migration entry to signpost the skill and its rollout rule.

    Parameters
    ----------
    migration_guide : str
        Contents of the migration guide.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when the entry, its link, or its rollout rule is missing.
    """
    content = section(migration_guide, MIGRATION_GUIDE_HEADING)
    normalized = normalize(content)

    assert SKILL_LINK in content, "the migration entry must link to the skill"
    assert "install-skills" in normalized, (
        "the migration entry must state why two copies can coexist"
    )
    assert "one authoritative version" in normalized, (
        "the migration entry must require choosing an authoritative version"
    )


def validate_readme(readme: str) -> None:
    """Require the README signpost and its link to the users' guide.

    Parameters
    ----------
    readme : str
        Contents of the README.

    Returns
    -------
    None
        The function asserts in place.

    Raises
    ------
    AssertionError
        Raised when the signpost or its users'-guide link is missing.
    """
    assert README_SIGNPOST in normalize(readme), (
        "the README must signpost the comenq-backed CodeRabbit review workflow"
    )
    assert USERS_GUIDE_LINK in readme, (
        "the README signpost must link to the users' guide"
    )


def test_skill_document_contract() -> None:
    """The skill, its references, and the guides keep the documented rules."""
    skill = read(SKILL_PATH)
    validate_skill_contract(skill, read(FAILURE_MODES_PATH), read(EVIDENCE_PATH))
    validate_delegation_contract(skill)
    validate_users_guide(read(USERS_GUIDE_PATH))
    validate_migration_guide(read(MIGRATION_GUIDE_PATH))
    validate_readme(read(README_PATH))


@pytest.mark.parametrize("rule", sorted(REQUIRED_SKILL_RULES))
def test_contract_rejects_missing_required_rule(rule: str) -> None:
    """Removing any required rule must fail the contract."""
    skill = without(read(SKILL_PATH), REQUIRED_SKILL_RULES[rule])

    with pytest.raises(AssertionError, match=re.escape(rule)):
        validate_skill_contract(skill, read(FAILURE_MODES_PATH), read(EVIDENCE_PATH))


@pytest.mark.parametrize("heading", REQUIRED_SKILL_HEADINGS)
def test_contract_rejects_missing_required_heading(heading: str) -> None:
    """Renaming any required section must fail the contract."""
    skill = read(SKILL_PATH).replace(heading, "## Retired", 1)

    with pytest.raises(AssertionError, match=re.escape(heading)):
        validate_skill_contract(skill, read(FAILURE_MODES_PATH), read(EVIDENCE_PATH))


@pytest.mark.parametrize("role", sorted(REQUIRED_AGENT_ROLES))
def test_contract_rejects_missing_agent_role(role: str) -> None:
    """Removing a named role from the delegation section must fail the contract."""
    skill = read(SKILL_PATH)
    delegation_heading_index = skill.index(DELEGATION_HEADING)
    delegation, separator, remainder = skill[delegation_heading_index:].partition(
        "\n## "
    )
    assert separator, "the delegation section must be followed by another section"
    assert role in delegation, f"the delegation section must name {role}"

    mutated = skill[:delegation_heading_index] + delegation.replace(
        role, "an unnamed worker"
    ) + separator + remainder

    with pytest.raises(AssertionError, match=re.escape(role)):
        validate_delegation_contract(mutated)


def test_contract_rejects_missing_installation_boundary() -> None:
    """Removing the installation boundary section must fail the contract."""
    skill = read(SKILL_PATH).replace("## Installation boundary", "## Deployment", 1)

    with pytest.raises(AssertionError, match=re.escape("## Installation boundary")):
        validate_skill_contract(skill, read(FAILURE_MODES_PATH), read(EVIDENCE_PATH))


def test_contract_rejects_missing_recovery_evidence() -> None:
    """Removing an exit-evidence marker must fail the contract."""
    failure_modes = read(FAILURE_MODES_PATH).replace("**Exit evidence:**", "", 1)

    with pytest.raises(AssertionError, match=re.escape("**Exit evidence:**")):
        validate_skill_contract(read(SKILL_PATH), failure_modes, read(EVIDENCE_PATH))


def test_contract_rejects_missing_rehearsal_scenario() -> None:
    """Renumbering the rehearsal scenarios must fail the contract."""
    evidence = read(EVIDENCE_PATH).replace(
        "17. **Uncertain comment", "18. **Uncertain comment", 1
    )

    with pytest.raises(AssertionError, match="sequential"):
        validate_skill_contract(read(SKILL_PATH), read(FAILURE_MODES_PATH), evidence)


def test_contract_rejects_missing_users_guide_section() -> None:
    """Removing the users' guide entry must fail the contract."""
    users_guide = read(USERS_GUIDE_PATH).replace(USERS_GUIDE_HEADING, "## Reviews", 1)

    with pytest.raises(AssertionError, match=re.escape(USERS_GUIDE_HEADING)):
        validate_users_guide(users_guide)


def test_contract_rejects_missing_state_diagram() -> None:
    """Removing the state diagram must fail the contract."""
    users_guide = read(USERS_GUIDE_PATH).replace(STATE_DIAGRAM, "", 1)

    with pytest.raises(AssertionError, match="state diagram"):
        validate_users_guide(users_guide)


def test_contract_rejects_missing_migration_entry() -> None:
    """Removing the migration entry's rollout rule must fail the contract."""
    migration_guide = read(MIGRATION_GUIDE_PATH).replace(
        "one authoritative version", "a version", 1
    )

    with pytest.raises(AssertionError, match="authoritative"):
        validate_migration_guide(migration_guide)


def test_contract_rejects_missing_readme_signpost() -> None:
    """Removing the README signpost must fail the contract."""
    readme = without(read(README_PATH), README_SIGNPOST)

    with pytest.raises(AssertionError, match="signpost"):
        validate_readme(readme)
