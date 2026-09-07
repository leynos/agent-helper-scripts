"""Contract tests for shipped Agent Skills manifests."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_manifest_check(skill_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the Makefile contract check for shipped skills or one fixture."""
    arguments = ["make", "skill-manifest-check"]
    if skill_dir is not None:
        arguments.append(f"SKILL_DIRS={skill_dir}")
    return subprocess.run(
        arguments,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_shipped_skill_manifests_satisfy_the_contract() -> None:
    """Every shipped skill passes YAML and Agent Skills schema validation."""
    result = _run_manifest_check()

    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_check_rejects_a_missing_name(tmp_path: Path) -> None:
    """A strict loader cannot discover a skill whose manifest omits its name."""
    skill_dir = tmp_path / "missing-name"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "description: A fixture that lacks the required discovery name.\n"
        "---\n\n"
        "# Missing name\n",
        encoding="utf-8",
    )

    result = _run_manifest_check(skill_dir)

    assert result.returncode != 0
    assert "Missing required field in frontmatter: name" in result.stdout + result.stderr
