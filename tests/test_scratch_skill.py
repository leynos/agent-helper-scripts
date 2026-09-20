"""Contract tests for the repository scratch-sidecar skill.

The scratch skill defines a filesystem boundary and a reviewed deletion
procedure in prose. These tests pin the concrete sidecar paths, manifest
schema, retention rules, provenance requirements, and cleanup order so later
edits cannot silently weaken that contract.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "scratch"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
LAYOUT_PATH = SKILL_ROOT / "references" / "layout.md"
INTERFACE_PATH = SKILL_ROOT / "agents" / "openai.yaml"
USERS_GUIDE_PATH = REPO_ROOT / "docs" / "users-guide.md"
MIGRATION_GUIDE_PATH = REPO_ROOT / "docs" / "v0-3-0-migration-guide.md"
DEVELOPERS_GUIDE_PATH = REPO_ROOT / "docs" / "developers-guide.md"

REQUIRED_MANIFEST_FIELDS = {
    "schema_version",
    "owner",
    "purpose",
    "source_repository",
    "created_at",
    "retention",
    "reproducible",
}
OPTIONAL_MANIFEST_FIELDS = {
    "expires_at",
    "related_pull_requests",
    "related_issues",
    "provenance",
}
RETENTION_VALUES = {"active", "recovery", "evidence", "experiment", "cache"}


def _read(path: Path) -> str:
    """Read one scratch-sidecar contract document."""
    return path.read_text(encoding="utf-8")


def _normalize(markdown: str) -> str:
    """Collapse Markdown line wrapping before checking prose requirements."""
    return " ".join(markdown.split())


def _frontmatter_and_body() -> tuple[dict[str, object], str]:
    """Return the scratch skill's parsed frontmatter and body."""
    content = _read(SKILL_PATH)
    assert content.startswith("---\n"), "the scratch skill must open with frontmatter"
    _, frontmatter, body = content.split("---", maxsplit=2)
    parsed = yaml.safe_load(frontmatter)
    assert isinstance(parsed, dict), "the scratch skill frontmatter must be a mapping"
    return parsed, body


def _manifest_example() -> dict[str, object]:
    """Parse the authoritative ``scratch.toml`` example."""
    match = re.search(r"```toml\n(?P<example>.*?)```", _read(LAYOUT_PATH), re.DOTALL)
    assert match, "the layout contract must contain a scratch.toml example"
    return tomllib.loads(match.group("example"))


def test_scratch_discovery_advertises_the_complete_lifecycle() -> None:
    """Discovery exposes creation, audit, migration, retirement, and boundaries."""
    frontmatter, _ = _frontmatter_and_body()
    description = frontmatter.get("description")

    assert frontmatter.get("name") == "scratch", "discovery must use the scratch name"
    assert isinstance(description, str), "the scratch skill must declare a description"
    normalized = " ".join(description.split())
    assert len(normalized) <= 120, "the description must fit Codex discovery"
    for term in ("Create", "audit", "migrate", "retire", "worktrees", "temporary"):
        assert term in normalized, f"discovery must advertise {term!r}"


def test_scratch_interface_routes_audit_requests_to_the_skill() -> None:
    """OpenAI interface metadata exposes the audit-capable discovery name."""
    interface = yaml.safe_load(_read(INTERFACE_PATH))

    assert isinstance(interface, dict), "the scratch interface metadata must be a mapping"
    prompt = interface["interface"]["default_prompt"]
    assert "$scratch" in prompt, "the interface prompt must invoke the scratch skill"
    assert "audit" in prompt, "the interface prompt must advertise audit requests"


def test_sidecars_keep_worktrees_scratch_categories_and_system_temp_separate() -> None:
    """Placement rules preserve the worktree, scratch, and temporary boundaries."""
    _, skill = _frontmatter_and_body()
    layout = _read(LAYOUT_PATH)

    assert "<repository>.worktrees/" in skill
    for category in ("experiments", "recovery", "evidence", "cache"):
        assert f"<repository>.scratch/{category}/" in skill
    for category in ("active", "recovery", "evidence", "experiments", "cache"):
        assert f"|-- {category}/" in layout or f"`-- {category}/" in layout
    assert "system temporary directory" in skill


def test_manifest_contract_names_required_optional_retention_and_provenance_rules() -> None:
    """The example and prose define the task manifest's durable schema."""
    manifest = _manifest_example()
    layout = _normalize(_read(LAYOUT_PATH))
    retention_start = layout.index("Allowed retention values are")
    retention_end = layout.index("The value should agree with the parent category.")
    retention_clause = layout[retention_start:retention_end]

    assert REQUIRED_MANIFEST_FIELDS <= manifest.keys()
    assert OPTIONAL_MANIFEST_FIELDS <= manifest.keys()
    assert RETENTION_VALUES <= set(re.findall(r"`([^`]+)`", retention_clause))
    assert "Required fields are `schema_version`, `owner`, `purpose`, " in layout
    assert "The optional fields are `expires_at`, `related_pull_requests`, " in layout
    assert "`provenance` may be omitted only when no source-specific provenance is needed." in layout
    assert "Recovery material must describe how its contents were verified." in layout
    assert "Reproducible data should name the command or source needed to rebuild it." in layout


def test_retention_and_cleanup_preserve_owned_and_unique_recovery_data() -> None:
    """Deletion decisions check safety before expiry and require exact approval."""
    _, skill = _frontmatter_and_body()
    layout = _read(LAYOUT_PATH)

    ordered_checks = ("**Ownership:**", "**Classification:**", "**Uniqueness:**", "**Expiry:**")
    positions = [layout.index(check) for check in ordered_checks]
    assert positions == sorted(positions), "retention checks must protect ownership before expiry"
    assert "Detect processes whose current directory, open workspace or watcher" in skill
    assert "Inspect Git repositories and recovery artefacts for unpublished or unique" in skill
    assert "Produce an exact dry-run list with path, category, size and deletion reason." in skill
    assert "without explicit authorization\nfor those exact recovery items" in skill


def test_guides_keep_the_sidecar_migration_and_cleanup_contract_visible() -> None:
    """User, migration, and developer guides retain the published boundary."""
    users_guide = _normalize(_read(USERS_GUIDE_PATH))
    migration_guide = _normalize(_read(MIGRATION_GUIDE_PATH))
    developers_guide = _normalize(_read(DEVELOPERS_GUIDE_PATH))

    for required in (
        "ownership and process state",
        "unpublished or unique work",
        "exact dry-run inventory",
        "each recovery item to delete",
    ):
        assert required in users_guide, f"users' cleanup guidance must retain {required!r}"
    for required in ("<repository>.scratch", "<repository>.worktrees", "Migrating a flat projects directory"):
        assert required in migration_guide, f"migration guide must retain {required!r}"
    for required in (
        "primary checkout",
        "<repository>.worktrees",
        "<repository>.scratch",
        "system temporary directory",
        "scratch layout contract",
    ):
        assert required in developers_guide, f"developers' guide must retain {required!r}"
