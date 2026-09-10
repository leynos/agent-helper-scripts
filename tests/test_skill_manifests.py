"""Contract tests for shipped Agent Skills manifests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_MANIFESTS = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))


def _run_make(target: str, *skill_dirs: Path) -> subprocess.CompletedProcess[str]:
    """Run a Makefile manifest target over shipped skills or given fixtures."""
    arguments = ["make", target]
    if skill_dirs:
        arguments.append("SKILL_DIRS=" + " ".join(f"{directory}/" for directory in skill_dirs))
    return subprocess.run(
        arguments,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_manifest_check(skill_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the Makefile contract check for shipped skills or one fixture."""
    return _run_make("skill-manifest-check", *([skill_dir] if skill_dir is not None else []))


def _frontmatter(manifest: Path) -> dict[str, object]:
    """Parse the YAML frontmatter block of a skill manifest."""
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{manifest} does not open with a frontmatter fence"
    closing = lines.index("---", 1)
    return yaml.safe_load("\n".join(lines[1:closing])) or {}


def _write_manifest(skill_dir: Path, body: str) -> Path:
    """Create a skill directory containing the given manifest text."""
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


def test_shipped_skill_manifests_satisfy_the_contract() -> None:
    """Every shipped skill passes YAML and Agent Skills schema validation."""
    result = _run_manifest_check()

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("case", "frontmatter"),
    [
        ("missing", "description: A fixture that lacks the required discovery name.\n"),
        ("empty", 'name: ""\ndescription: A fixture whose discovery name is empty.\n'),
    ],
)
def test_manifest_check_rejects_an_unusable_name(tmp_path: Path, case: str, frontmatter: str) -> None:
    """A strict loader cannot discover a skill without a usable discovery name.

    An absent `name` and an empty `name` fail discovery identically, so the
    contract must reject both rather than only the absent case.
    """
    skill_dir = _write_manifest(
        tmp_path / f"{case}-name",
        f"---\n{frontmatter}---\n\n# Fixture\n",
    )

    result = _run_manifest_check(skill_dir)

    assert result.returncode != 0, result.stdout + result.stderr


@pytest.mark.parametrize("manifest", SHIPPED_MANIFESTS, ids=lambda path: path.parent.name)
def test_shipped_metadata_values_are_strings(manifest: Path) -> None:
    """Metadata carries only string values, which `skills-ref` silently coerces.

    `skills_ref.parser` rewrites every metadata value with `str(v)`, so a YAML
    sequence survives validation but reaches consumers as a Python repr.  The
    specification permits string keys and string values only, so reject the
    non-conformant shapes here rather than shipping a silently mangled value.
    """
    metadata = _frontmatter(manifest).get("metadata", {})

    assert isinstance(metadata, dict), f"metadata must be a mapping, got {type(metadata).__name__}"
    non_strings = {key: value for key, value in metadata.items() if not isinstance(value, str)}
    assert not non_strings, f"metadata values must be strings: {non_strings}"


def test_frontmatter_lint_reports_an_early_failure(tmp_path: Path) -> None:
    """A failure in any skill fails the target, not just one in the final skill.

    The shell `for` loop otherwise exits with the status of its last iteration,
    letting a conformant trailing skill mask a malformed earlier one.
    """
    broken = _write_manifest(tmp_path / "a-broken", "---\nname: [unclosed\n---\n\n# Broken\n")
    valid = _write_manifest(
        tmp_path / "z-valid",
        "---\nname: z-valid\ndescription: A conformant trailing fixture.\n---\n\n# Valid\n",
    )

    result = _run_make("skill-frontmatter-lint", broken, valid)

    assert result.returncode != 0, result.stdout + result.stderr


def test_lint_runs_the_manifest_contract(tmp_path: Path) -> None:
    """`make lint` fails on a malformed manifest, proving the targets are wired in.

    The contract is only enforced because `lint` depends on
    `skill-manifest-check`; without this test, dropping that prerequisite would
    silently disable manifest validation while every other test still passed.
    """
    skill_dir = _write_manifest(
        tmp_path / "unlintable",
        "---\ndescription: A fixture that lacks the required discovery name.\n---\n\n# Fixture\n",
    )

    result = _run_make("lint", skill_dir)

    assert result.returncode != 0, result.stdout + result.stderr


def test_frontmatter_lint_reports_an_unreadable_manifest(tmp_path: Path) -> None:
    """A manifest that cannot be read fails the target rather than being skipped.

    `awk` fails to read a missing `SKILL.md`, a distinct failure path from
    `yamllint` rejecting parsed content, and one that only `pipefail` surfaces.
    """
    absent = tmp_path / "absent"
    absent.mkdir()
    valid = _write_manifest(
        tmp_path / "z-valid",
        "---\nname: z-valid\ndescription: A conformant trailing fixture.\n---\n\n# Valid\n",
    )

    result = _run_make("skill-frontmatter-lint", absent, valid)

    assert result.returncode != 0, result.stdout + result.stderr
