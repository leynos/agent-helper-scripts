"""Contract tests for the Biome TypeScript skill's documentation.

The skill's value rests on claims a reader cannot check at a glance: which
Biome release the examples target, which rule names exist at that release, and
from which version a feature is available. These tests read the live Markdown
so those claims cannot drift.

Behavioural coverage of the changed-file pipeline the skill documents lives in
`test_biome_typescript_procedures.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "biome-typescript"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
LINT_SOLUTIONS_PATH = SKILL_ROOT / "references" / "lint-solutions.md"
CI_HOOKS_PATH = SKILL_ROOT / "references" / "ci-hooks.md"
MIGRATION_PATH = SKILL_ROOT / "references" / "migration.md"
STRICT_RULES_PATH = SKILL_ROOT / "references" / "strict-rules.md"

# The release every configuration example in the skill is written against.
PINNED_VERSION = "1.9.4"
PINNED_SCHEMA = f"https://biomejs.dev/schemas/{PINNED_VERSION}/schema.json"

# The release that added nearest-tsconfig baseUrl and paths resolution.
PATH_RESOLUTION_VERSION = "Biome 2.3"

DOCUMENTATION_PATHS = (
    SKILL_PATH,
    LINT_SOLUTIONS_PATH,
    CI_HOOKS_PATH,
    MIGRATION_PATH,
    STRICT_RULES_PATH,
)

JSON_FENCE = re.compile(r"^```json\n(.*?)^```$", re.DOTALL | re.MULTILINE)
LEVEL_TWO_HEADING = re.compile(r"^## .*$", re.MULTILINE)

# The documented install command, matched as a command rather than as a
# version token that could appear anywhere in the document.
INSTALL_COMMAND = re.compile(
    rf"npm install --save-dev --save-exact @biomejs/biome@{re.escape(PINNED_VERSION)}\b"
)

# Read from the raw block so a commented (JSONC) example, which Biome 1.9.4
# accepts, is checked instead of raising a parse error.
SCHEMA_DECLARATION = re.compile(r'"\$schema"\s*:\s*"([^"]+)"')


def _read(path: Path) -> str:
    """Read one documentation contract file."""
    return path.read_text(encoding="utf-8")


def _relative(path: Path) -> str:
    """Render a documentation path for an assertion message."""
    return str(path.relative_to(REPO_ROOT))


def _json_blocks(path: Path) -> list[str]:
    """Return the raw bodies of the JSON-fenced blocks in one document."""
    return JSON_FENCE.findall(_read(path))


def _parsed_json_blocks(path: Path) -> list[object]:
    """Return every JSON-fenced block that parses, skipping commented ones.

    Several blocks are JSONC — a `tsconfig.json` fragment, or a config carrying
    explanatory comments — so a parse failure is not itself a defect. Tests
    needing configuration structure assert it on the blocks that do parse.
    """
    parsed = []
    for block in _json_blocks(path):
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return parsed


def _section_containing(document: str, fragment: str) -> str:
    """Return the level-2 section that contains a fragment of a document."""
    index = document.index(fragment)
    headings = list(LEVEL_TWO_HEADING.finditer(document))
    start = max(
        (match.start() for match in headings if match.start() <= index), default=0
    )
    end = next(
        (match.start() for match in headings if match.start() > index), len(document)
    )
    return document[start:end]


def test_install_command_pins_the_documented_release() -> None:
    """The quick start runs an install command pinned to the documented release."""
    assert INSTALL_COMMAND.search(_read(SKILL_PATH)), (
        f"the quick start must run the documented install command pinned to "
        f"{PINNED_VERSION}, because the configuration examples rely on that "
        "release's key spellings"
    )


def test_every_declared_schema_matches_the_pinned_release() -> None:
    """A `$schema` URL drifting from the pin invalidates editor validation."""
    declared = []
    for path in DOCUMENTATION_PATHS:
        for index, block in enumerate(_json_blocks(path), start=1):
            declared.extend(
                (path, index, url) for url in SCHEMA_DECLARATION.findall(block)
            )

    assert declared, "the skill must declare a $schema URL"
    for path, index, url in declared:
        assert url == PINNED_SCHEMA, (
            f"{_relative(path)} block {index} declares {url}, but the skill pins "
            f"Biome {PINNED_VERSION}; $schema must always match the installed "
            "version"
        )


def test_configuration_blocks_use_the_1_9_file_keys() -> None:
    """`files.include`/`files.ignore` are 1.9 spellings; `includes` is 2.0."""
    accepted = {"include", "ignore", "ignoreUnknown", "maxSize"}
    documented_includes = 0
    for path in DOCUMENTATION_PATHS:
        for parsed in _parsed_json_blocks(path):
            if not isinstance(parsed, dict):
                continue
            files = parsed.get("files")
            if not isinstance(files, dict):
                continue
            unexpected = set(files) - accepted
            assert not unexpected, (
                f"{_relative(path)} configures files.{sorted(unexpected)}, which "
                f"Biome {PINNED_VERSION} does not accept; Biome 2.0 renamed the "
                "keys to files.includes"
            )
            documented_includes += "include" in files

    assert documented_includes, (
        "the skill must document a files.include example, because that key "
        "spelling is what the 1.9.4 pin rests on"
    )


def test_configuration_blocks_avoid_the_pre_rename_console_rule() -> None:
    """`noConsoleLog` was renamed to `noConsole`; a stale key silently no-ops.

    The check reads the raw block rather than the parsed one, so a stale key
    inside a commented (JSONC) example is caught too.
    """
    stale_key = re.compile(r'"noConsoleLog"\s*:')
    for path in DOCUMENTATION_PATHS:
        for index, block in enumerate(_json_blocks(path), start=1):
            assert not stale_key.search(block), (
                f"{_relative(path)} block {index} configures the pre-rename rule "
                "name noConsoleLog; Biome ignores unknown rule keys, so the "
                "setting would not take effect"
            )


def test_migration_maps_no_console_to_the_biome_rule() -> None:
    """The ESLint mapping names the rule that actually exists."""
    migration = _read(MIGRATION_PATH)
    assert re.search(
        r"\|\s*`no-console`\s*\|\s*`suspicious/noConsole`\s*\|", migration
    ), "the ESLint migration table must map no-console to suspicious/noConsole"


def test_lint_solutions_documents_the_renamed_rule() -> None:
    """The rule is documented under its current name only."""
    solutions = _read(LINT_SOLUTIONS_PATH)
    assert re.search(r"^### noConsole$", solutions, re.MULTILINE), (
        "lint-solutions.md must document the rule under its current name"
    )
    assert not re.search(r"^### noConsoleLog$", solutions, re.MULTILINE), (
        "the pre-rename heading must not survive"
    )


def test_no_console_documents_that_nothing_is_exempt() -> None:
    """Readers must be told that console.error is not exempt on its own."""
    solutions = _read(LINT_SOLUTIONS_PATH)
    assert "nothing is exempt by default" in solutions, (
        "the reference must state that every console.* call is reported unless "
        "allow names the method"
    )


def test_no_console_allow_option_names_the_retained_methods() -> None:
    """The allow option is shown as a non-empty list of console methods."""
    allow_lists = []
    for parsed in _parsed_json_blocks(LINT_SOLUTIONS_PATH):
        if not isinstance(parsed, dict):
            continue
        rules = parsed.get("linter", {}).get("rules", {})
        rule = rules.get("suspicious", {}).get("noConsole") if isinstance(rules, dict) else None
        if isinstance(rule, dict):
            allow_lists.append(rule.get("options", {}).get("allow"))

    assert allow_lists, "the reference must show a noConsole allow configuration"
    for methods in allow_lists:
        assert isinstance(methods, list) and methods, (
            "the allow option must name at least one console method"
        )
        assert all(isinstance(method, str) for method in methods), (
            "every allowed method must be named as a string"
        )


def test_nullish_guidance_rejects_the_conditional_misuse() -> None:
    """`??` is not rejected outright; using it as a condition is.

    `value ?? defaultValue` preserves `false`, `0`, and `""`, so the operator
    itself is sound. The defect is testing the coalesced value: the branch then
    runs only when that value is truthy, so a falsy default is never applied.
    """
    solutions = _read(LINT_SOLUTIONS_PATH)
    assert not re.search(r"\bif\s*\(\s*value\s*\?\?\s*defaultValue\s*\)", solutions), (
        "`if (value ?? defaultValue)` is not equivalent to a null check, because "
        "the branch runs only when the coalesced value is truthy"
    )
    assert "value === null || value === undefined" in solutions, (
        "the explicit null and undefined check must be shown"
    )
    assert "are preserved" in solutions, (
        "the reference must state which values the explicit check preserves"
    )


def test_react_key_guidance_requires_identifiers_from_the_data() -> None:
    """Keys must come from the record, not from a value computed while rendering."""
    solutions = _read(LINT_SOLUTIONS_PATH)
    assert "written to storage, not in the component body" in solutions, (
        "the reference must say where identifiers are minted"
    )
    assert "unique among its siblings" in solutions, (
        "the reference must state the uniqueness requirement a key must satisfy"
    )


def test_tsconfig_guidance_names_the_version_that_adds_path_support() -> None:
    """baseUrl and paths support is version-gated, and the example must say so."""
    skill = _read(SKILL_PATH)
    tsconfig_blocks = [
        block for block in _json_blocks(SKILL_PATH) if "tsconfig.json" in block
    ]
    assert tsconfig_blocks, "the skill must show an applicable tsconfig.json example"

    example = tsconfig_blocks[-1]
    assert '"baseUrl"' in example and '"paths"' in example, (
        "the tsconfig example must show both baseUrl and paths, because the "
        "two work together"
    )
    assert PATH_RESOLUTION_VERSION in _section_containing(skill, example), (
        f"the section holding the example must name {PATH_RESOLUTION_VERSION}, "
        "the release that added nearest-tsconfig baseUrl and paths resolution; "
        "naming it elsewhere does not tell the reader whether this example "
        "applies to the pinned version"
    )


def test_jsx_runtime_and_globals_guidance_is_retained() -> None:
    """The JSX guidance is independent of path resolution and must survive."""
    skill = _read(SKILL_PATH)
    assert '"jsxRuntime": "reactClassic"' in skill, (
        "the classic runtime still needs the React global, so the example must "
        "show both keys together"
    )
    assert '"globals": ["React"]' in skill, (
        "the globals setting is what declares React for the classic runtime"
    )
