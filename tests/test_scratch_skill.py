"""Contract tests for the repository scratch-sidecar skill.

The scratch skill defines a filesystem boundary and a reviewed deletion
procedure in prose. These tests pin the concrete sidecar paths, manifest
schema, retention rules, provenance requirements, and cleanup order so later
edits cannot silently weaken that contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import tomllib
from pathlib import Path

import pytest
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
CATEGORY_RETENTION = {
    "active": "active",
    "recovery": "recovery",
    "evidence": "evidence",
    "experiments": "experiment",
    "cache": "cache",
}
PROVENANCE_FIELDS = {"source_ref", "source_commit", "capture", "verification"}


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


def _assert_rfc3339_utc(value: object, field: str) -> None:
    """Require one manifest timestamp to use the documented UTC wire format."""
    assert isinstance(value, str), f"{field} must be a string"
    assert value.endswith("Z"), f"{field} must use the RFC 3339 UTC Z suffix"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is timezone.utc, f"{field} must carry UTC timezone data"


def _assert_recovery_provenance(manifest: dict[str, object]) -> None:
    """Apply the schema's conditional provenance requirement."""
    if manifest["retention"] != "recovery":
        return

    provenance = manifest.get("provenance")
    assert isinstance(provenance, dict), "recovery material must have provenance"
    assert set(provenance) == PROVENANCE_FIELDS, (
        "recovery provenance must use the documented structured fields"
    )
    for field in PROVENANCE_FIELDS:
        value = provenance[field]
        assert isinstance(value, str) and value.strip(), (
            f"recovery provenance.{field} must be a non-empty string"
        )


def _assert_complete_manifest(manifest: dict[str, object], category: str) -> None:
    """Validate the published example as a task in one sidecar category."""
    assert set(manifest) == REQUIRED_MANIFEST_FIELDS | OPTIONAL_MANIFEST_FIELDS
    assert type(manifest["schema_version"]) is int
    assert manifest["schema_version"] == 1
    for field in ("owner", "purpose", "source_repository"):
        assert isinstance(manifest[field], str) and manifest[field].strip(), (
            f"{field} must be a non-empty string"
        )
    _assert_rfc3339_utc(manifest["created_at"], "created_at")
    _assert_rfc3339_utc(manifest["expires_at"], "expires_at")
    assert manifest["retention"] in RETENTION_VALUES
    assert manifest["retention"] == CATEGORY_RETENTION[category], (
        f"{category} tasks must match CATEGORY_RETENTION"
    )
    assert type(manifest["reproducible"]) is bool
    for field in ("related_pull_requests", "related_issues"):
        assert isinstance(manifest[field], list) and all(
            type(identifier) is int for identifier in manifest[field]
        ), f"{field} must be a list of integer identifiers"
    _assert_recovery_provenance(manifest)


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


def test_manifest_example_is_a_complete_recovery_task(tmp_path: Path) -> None:
    """The example parses as the documented recovery task in a real sidecar."""
    task_dir = tmp_path / "Example.scratch" / "recovery" / "pr-123-rebase"
    task_dir.mkdir(parents=True)
    manifest_path = task_dir / "scratch.toml"
    example = re.search(r"```toml\n(?P<example>.*?)```", _read(LAYOUT_PATH), re.DOTALL)

    assert example, "the layout contract must contain a scratch.toml example"
    manifest_path.write_text(example.group("example"), encoding="utf-8")
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    _assert_complete_manifest(manifest, task_dir.parent.name)


def test_manifest_rejects_a_category_retention_mismatch() -> None:
    """A cache retention value cannot describe a recovery task directory."""
    manifest = _manifest_example()
    manifest["retention"] = "cache"

    with pytest.raises(AssertionError, match="CATEGORY_RETENTION"):
        _assert_complete_manifest(manifest, "recovery")


def test_non_recovery_manifest_may_omit_unneeded_provenance() -> None:
    """Provenance remains optional only outside the recovery retention class."""
    manifest = _manifest_example()
    manifest["retention"] = "cache"
    manifest.pop("provenance")

    _assert_recovery_provenance(manifest)


def test_manifest_contract_names_required_optional_and_conditional_rules() -> None:
    """The prose retains the schema boundaries that the parsed example exercises."""
    layout = _normalize(_read(LAYOUT_PATH))
    retention_start = layout.index("Allowed retention values are")
    retention_end = layout.index("The value should agree with the parent category.")
    retention_clause = layout[retention_start:retention_end]

    assert RETENTION_VALUES <= set(re.findall(r"`([^`]+)`", retention_clause))
    assert "Required fields are `schema_version`, `owner`, `purpose`, " in layout
    assert "The optional fields are `expires_at`, `related_pull_requests`, " in layout
    assert 'For `retention = "recovery"`, the structured `[provenance]` table ' in layout
    assert "is required and its `verification` field must be a non-empty string." in layout
    assert "For non-recovery material, `provenance` may be omitted when no " in layout
    assert "source-specific provenance is needed." in layout
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
