"""Contract tests for the Ansible testing skill's scheduling documentation.

The skill restates one set of scheduling rules twice: as the closing bullet of
section 3f ("Molecule test isolation on shared hosts") and as the closing bullet
of item 7 in section 3g ("Molecule performance guidance"). The two restatements
are only useful while the terms match, so the wording is part of the contract
rather than an incidental detail. These tests detect drift between the skill and
the rules the shared-workspace guidance relies on, including the fact-cache
isolation the example scenario configuration itself must apply. They do not
prove that an agent follows the skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "ansible-testing" / "SKILL.md"
USERS_GUIDE_PATH = REPO_ROOT / "docs" / "users-guide.md"

ISOLATION_HEADING = "### 3f. Molecule test isolation on shared hosts"
PERFORMANCE_HEADING = "### 3g. Molecule performance guidance"
USERS_GUIDE_HEADING = "## Ansible testing"

RECONCILIATION_INTRO = "with these reconciliation rules:"
RESTATEMENT_INTRO = "restated here in the same terms:"
USERS_GUIDE_RULES_INTRO = (
    "For shared agent workspaces the skill's scheduling rules are:"
)

EXTERNAL_PARALLELISM_PROHIBITION = (
    "Agents must not apply external parallelism to repository gates."
)
OVERLAPPING_GATES_PROHIBITION = (
    "Agents must not run overlapping repository gates."
)
INTERNAL_PARALLELISM_PERMISSION = (
    "A repository may own bounded internal scenario parallelism through its own "
    "documented test target and repository-defined concurrency controls."
)
INTERNAL_PARALLELISM_CONDITION = (
    "Agents use that internal parallelism only when that repository's guidance "
    "explicitly documents it."
)
INTERNAL_PARALLELISM_CONDITION_CLAUSE = (
    "only when that repository's guidance explicitly documents it"
)
SEQUENTIAL_DEFAULT = (
    "All other scenario commands and overlapping gates stay sequential by default."
)
SUFFIX_MANDATE = (
    "`MOLECULE_INSTANCE_SUFFIX` and fact-cache isolation stay mandatory "
    "regardless of the scheduling mode."
)
SCHEDULING_RULES = (
    EXTERNAL_PARALLELISM_PROHIBITION,
    OVERLAPPING_GATES_PROHIBITION,
    INTERNAL_PARALLELISM_PERMISSION,
    INTERNAL_PARALLELISM_CONDITION,
    SEQUENTIAL_DEFAULT,
    SUFFIX_MANDATE,
)

MOLECULE_FLOOR_PIN = '"molecule>=26.3.0"'
MOLECULE_FLOOR_SITES = 2
WORKER_MODE_REQUIREMENTS = {
    "dedicated-runner scope": (
        "Treat native worker mode as a CI or dedicated-runner path."
    ),
    "experimental status": "Native worker mode is experimental",
    "version floor": "`--workers` needs Molecule 26.3.0 or newer",
    "collection mode requirement": (
        "`--workers` requires collection mode with `galaxy.yml`"
    ),
    "shared state requirement": "Use `shared_state: true` in scenario configs",
    "destroy-never incompatibility": (
        "Do not combine `--workers > 1` with `--destroy=never`"
    ),
    "sequential fallback": "Fall back to `molecule test --all`",
    "per-scenario fact-cache scoping": (
        "Add `${MOLECULE_SCENARIO_NAME}` to `fact_caching_connection`"
    ),
}

INSTANCE_SUFFIX_VAR = "${MOLECULE_INSTANCE_SUFFIX}"
SCENARIO_NAME_VAR = "${MOLECULE_SCENARIO_NAME}"
FACT_CACHING_CONNECTION_RE = re.compile(
    r"^\s*fact_caching_connection:\s*(?:>-\s*\n\s*)?(?P<path>\S+)\s*$",
    re.MULTILINE,
)

MISSING_ISOLATION_RULES = (
    "the section 3f restatement must state the six scheduling rules in order"
)
MISSING_PERFORMANCE_RULES = (
    "the section 3g restatement must state the six scheduling rules in order"
)
USERS_GUIDE_MISSING = "must contain the `## Ansible testing` heading"
USER_GUIDE_RULE_MISSING = "the users' guide must restate the scheduling rule"
WORKER_MODE_MISSING = "the skill must document the native worker mode constraint"
FACT_CACHE_PATH_MISSING = (
    "every fact_caching_connection path must keep concurrent runs apart"
)


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _normalize(markdown: str) -> str:
    """Collapse Markdown line wrapping before checking prose requirements."""
    return " ".join(markdown.split())


def _section(markdown: str, heading: str) -> str:
    """Return one heading's body, up to the next heading of the same or higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    _, separator, remainder = markdown.partition(f"{heading}\n")
    assert separator, f"the document must contain the `{heading}` heading"
    next_heading = re.search(rf"^#{{1,{level}}} ", remainder, re.MULTILINE)
    return remainder[: next_heading.start()] if next_heading else remainder


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Match a phrase across Markdown line wrapping."""
    return re.compile(r"\s+".join(re.escape(word) for word in phrase.split()))


def _without_phrase(markdown: str, phrase: str) -> str:
    """Return an in-memory mutation with one wrapped phrase removed."""
    mutated, replacements = _phrase_pattern(phrase).subn("", markdown, count=1)
    assert replacements == 1, f"test fixture must contain `{phrase}`"
    return mutated


def _rule_block(section: str, intro: str) -> list[str]:
    """Return the rule bullets a section introduces, unwrapped one string each.

    The block is anchored on the sentence that introduces the rules, so the
    bullets are compared by their own wording rather than by the indentation or
    wrapping the surrounding document happens to use.
    """
    match = _phrase_pattern(intro).search(section)
    assert match, f"the section must introduce its rules with `{intro}`"

    consumed = section[: match.end()].count("\n")
    body = section.splitlines()[consumed + 1 :]
    while body and not body[0].strip().startswith("- "):
        body.pop(0)
    assert body, "the section must list the scheduling rules after that introduction"

    indent = len(body[0]) - len(body[0].lstrip())
    items: list[str] = []
    for line in body:
        stripped = line.strip()
        if not stripped:
            break
        current_indent = len(line) - len(line.lstrip())
        if current_indent < indent:
            break
        if current_indent == indent:
            items.append(stripped.removeprefix("- "))
        else:
            items[-1] = f"{items[-1]} {stripped}"
    return [" ".join(item.split()) for item in items]


def _fact_cache_paths(skill: str) -> list[str]:
    """Return every fact cache path the skill's example configurations set.

    Both plain and folded YAML scalars are read, so the assertion holds however
    the examples are wrapped.
    """
    return [
        match.group("path") for match in FACT_CACHING_CONNECTION_RE.finditer(skill)
    ]


def _assert_fact_cache_isolation(skill: str) -> None:
    """Every example cache path must separate concurrent runs, not just branches."""
    paths = _fact_cache_paths(skill)
    assert paths, (
        "the skill must show at least one fact_caching_connection example"
    )
    for path in paths:
        for variable in (INSTANCE_SUFFIX_VAR, SCENARIO_NAME_VAR):
            assert variable in path, (
                f"{FACT_CACHE_PATH_MISSING}: `{path}` must carry `{variable}`"
            )


def _validate_scheduling_contract(skill: str, users_guide: str) -> None:
    """Validate the scheduling rules and both of their restatements."""
    isolation_rules = _rule_block(
        _section(skill, ISOLATION_HEADING), RECONCILIATION_INTRO
    )
    performance_rules = _rule_block(
        _section(skill, PERFORMANCE_HEADING), RESTATEMENT_INTRO
    )

    assert tuple(isolation_rules) == SCHEDULING_RULES, MISSING_ISOLATION_RULES
    assert tuple(performance_rules) == SCHEDULING_RULES, MISSING_PERFORMANCE_RULES
    assert isolation_rules == performance_rules, (
        "both restatements must state the scheduling rules in identical terms"
    )

    normalized_skill = _normalize(skill)
    for concept, required_text in WORKER_MODE_REQUIREMENTS.items():
        assert required_text in normalized_skill, (
            f"{WORKER_MODE_MISSING} on {concept}: `{required_text}`"
        )

    _assert_fact_cache_isolation(skill)

    assert skill.count(MOLECULE_FLOOR_PIN) >= MOLECULE_FLOOR_SITES, (
        "every install site, including the CI workflow, must pin the Molecule "
        f"floor with {MOLECULE_FLOOR_PIN}"
    )

    guide_section = _section(users_guide, USERS_GUIDE_HEADING)
    normalized_guide = _normalize(users_guide)
    assert "skills/ansible-testing/SKILL.md" in normalized_guide, (
        "the users' guide must link the skill that carries the full rules"
    )
    assert USERS_GUIDE_RULES_INTRO in normalized_guide, (
        "the users' guide must introduce its summary as the skill's rules"
    )

    guide_rules = _rule_block(guide_section, USERS_GUIDE_RULES_INTRO)
    for rule in (
        EXTERNAL_PARALLELISM_PROHIBITION,
        OVERLAPPING_GATES_PROHIBITION,
        SEQUENTIAL_DEFAULT,
        SUFFIX_MANDATE,
    ):
        assert rule in guide_rules, f"{USER_GUIDE_RULE_MISSING}: `{rule}`"
    assert INTERNAL_PARALLELISM_CONDITION_CLAUSE in " ".join(guide_rules), (
        f"{USER_GUIDE_RULE_MISSING}: `{INTERNAL_PARALLELISM_CONDITION_CLAUSE}`"
    )


def _without_users_guide_section(users_guide: str) -> str:
    """Return an in-memory guide mutation with the whole section removed."""
    _, separator, remainder = users_guide.partition(f"{USERS_GUIDE_HEADING}\n")
    assert separator, "test fixture must contain the users' guide section"
    _, next_separator, tail = remainder.partition("\n## ")
    assert next_separator, "test fixture must contain a heading after the guide section"
    return users_guide.replace(
        f"{USERS_GUIDE_HEADING}\n{remainder}", f"\n## {tail}", 1
    )


def test_ansible_testing_scheduling_contract() -> None:
    """The live skill and users' guide retain the complete scheduling contract."""
    _validate_scheduling_contract(_read(SKILL_PATH), _read(USERS_GUIDE_PATH))


def test_rules_prohibit_external_and_overlapping_gate_parallelism() -> None:
    """Both prohibitions are stated for agents, not merely implied."""
    skill = _read(SKILL_PATH)
    for heading, intro in (
        (ISOLATION_HEADING, RECONCILIATION_INTRO),
        (PERFORMANCE_HEADING, RESTATEMENT_INTRO),
    ):
        rules = _rule_block(_section(skill, heading), intro)
        assert EXTERNAL_PARALLELISM_PROHIBITION in rules, (
            f"{heading} must prohibit external parallelism on repository gates"
        )
        assert OVERLAPPING_GATES_PROHIBITION in rules, (
            f"{heading} must prohibit overlapping repository gates"
        )


def test_internal_parallelism_stays_conditional_on_repository_guidance() -> None:
    """Repository-owned parallel targets are usable only when documented."""
    rules = _rule_block(
        _section(_read(SKILL_PATH), ISOLATION_HEADING), RECONCILIATION_INTRO
    )
    assert rules.index(INTERNAL_PARALLELISM_PERMISSION) == 2, (
        "the permission for repository-owned parallelism must follow both "
        "prohibitions"
    )
    assert rules.index(INTERNAL_PARALLELISM_CONDITION) == 3, (
        "the permission must be immediately qualified by its documentation "
        "condition"
    )


def test_example_configs_scope_the_fact_cache_per_instance_and_scenario() -> None:
    """The shipped examples must not let concurrent runs share a cache file.

    A scenario-scoped path is what lets native worker mode run scenarios with
    `gather_facts` enabled without one worker overwriting another's cache.
    """
    _assert_fact_cache_isolation(_read(SKILL_PATH))


def test_contract_rejects_shared_fact_cache_path() -> None:
    """Dropping the scenario component from an example path must fail."""
    skill = _read(SKILL_PATH)
    mutated = skill.replace(f"-{SCENARIO_NAME_VAR}", "", 1)
    assert mutated != skill, "test fixture must contain a scenario-scoped cache path"

    with pytest.raises(AssertionError, match=re.escape(FACT_CACHE_PATH_MISSING)):
        _assert_fact_cache_isolation(mutated)


def test_contract_rejects_weakened_external_parallelism_prohibition() -> None:
    """Relaxing a prohibition from a hard rule to a permission must fail."""
    skill = _read(SKILL_PATH).replace(
        "must not apply external parallelism", "may apply external parallelism", 1
    )

    with pytest.raises(AssertionError, match=re.escape(MISSING_ISOLATION_RULES)):
        _validate_scheduling_contract(skill, _read(USERS_GUIDE_PATH))


def test_contract_rejects_drift_between_restatements() -> None:
    """Rewording one restatement and not the other must fail."""
    skill = _read(SKILL_PATH)
    head, separator, performance = skill.partition(f"{PERFORMANCE_HEADING}\n")
    assert separator, "test fixture must contain the section 3g heading"
    performance = performance.replace(
        "must not run overlapping repository gates",
        "must not run overlapping test runs",
        1,
    )

    with pytest.raises(AssertionError, match=re.escape(MISSING_PERFORMANCE_RULES)):
        _validate_scheduling_contract(
            f"{head}{PERFORMANCE_HEADING}\n{performance}", _read(USERS_GUIDE_PATH)
        )


def test_contract_rejects_missing_worker_mode_constraint() -> None:
    """Dropping a native worker mode constraint must fail."""
    skill = _without_phrase(
        _read(SKILL_PATH), "Do not combine `--workers > 1` with `--destroy=never`."
    )

    with pytest.raises(AssertionError, match=re.escape(WORKER_MODE_MISSING)):
        _validate_scheduling_contract(skill, _read(USERS_GUIDE_PATH))


def test_contract_rejects_users_guide_losing_a_rule() -> None:
    """Removing a rule from the users' guide summary must fail."""
    users_guide = _without_phrase(_read(USERS_GUIDE_PATH), SEQUENTIAL_DEFAULT)

    with pytest.raises(AssertionError, match=re.escape(USER_GUIDE_RULE_MISSING)):
        _validate_scheduling_contract(_read(SKILL_PATH), users_guide)


def test_contract_rejects_missing_users_guide_section() -> None:
    """Removing the users' guide signpost altogether must fail."""
    users_guide = _without_users_guide_section(_read(USERS_GUIDE_PATH))

    with pytest.raises(AssertionError, match=re.escape(USERS_GUIDE_MISSING)):
        _validate_scheduling_contract(_read(SKILL_PATH), users_guide)
