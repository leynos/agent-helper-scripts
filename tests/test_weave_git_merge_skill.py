"""Contract and behavioural tests for the Weave Git merge skill."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "weave-git-merge"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
BEHAVIOUR_PATH = SKILL_ROOT / "references" / "behaviour.md"
AGENT_METADATA_PATH = SKILL_ROOT / "agents" / "openai.yaml"
REBASE_SKILL_PATH = REPO_ROOT / "skills" / "rebase" / "SKILL.md"
GIT = shutil.which("git")

if GIT is None:  # pragma: no cover - Git is a repository test prerequisite.
    raise RuntimeError("git is required to run the Weave skill tests")


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _mapping(document: str) -> dict[str, object]:
    """Parse a YAML document and require a mapping root."""
    parsed = yaml.safe_load(document)
    assert isinstance(parsed, dict), "expected a YAML mapping"
    return parsed


def _skill_frontmatter() -> tuple[dict[str, object], str]:
    """Return the Weave skill frontmatter and body."""
    parts = _read(SKILL_PATH).split("---", maxsplit=2)
    assert len(parts) == 3, "the Weave skill must have YAML frontmatter"
    return _mapping(parts[1]), parts[2]


def _git(
    repository: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in a temporary repository with captured output."""
    return subprocess.run(  # noqa: S603 - absolute executable and controlled arguments.
        [GIT, *args],
        cwd=repository,
        text=True,
        capture_output=True,
        check=check,
        timeout=30,
    )


def test_skill_discovery_metadata_describes_corruption_recovery() -> None:
    """Discovery metadata exposes the skill and its recovery purpose."""
    frontmatter, _ = _skill_frontmatter()
    description = frontmatter.get("description")

    assert frontmatter.get("name") == "weave-git-merge"
    assert isinstance(description, str)
    assert "detecting structurally corrupt clean results" in description
    assert "bypassing Weave safely" in description

    metadata = _mapping(_read(AGENT_METADATA_PATH))
    interface = metadata.get("interface")
    assert isinstance(interface, dict), "agent metadata must define interface"
    assert interface.get("display_name") == "Weave Git Merge"
    assert "$weave-git-merge" in str(interface.get("default_prompt"))


def test_skill_requires_structural_checks_before_continue() -> None:
    """The workflow catches malformed output before Git records it."""
    _, skill = _skill_frontmatter()

    assert "python -m py_compile path/to/file.py" in skill
    assert "set -o pipefail" in skill
    assert "ast.parse(sys.stdin.read())" in skill
    assert "before `git add` or `git rebase --continue`" in skill


def test_skill_preserves_all_three_stage_inspection_commands() -> None:
    """The workflow keeps non-mutating inspection for every index stage."""
    _, skill = _skill_frontmatter()

    for stage in (1, 2, 3):
        assert f"git show :{stage}:path/to/file.py" in skill
    assert "stage 2 can\nalready contain an earlier silently corrupted replay" in skill


def test_skill_guards_each_commit_in_a_multi_commit_rebase() -> None:
    """The workflow prevents an early clean corruption from cascading."""
    _, skill = _skill_frontmatter()

    assert "## Guard a multi-commit rebase" in skill
    assert (
        "git rebase --exec 'python -m compileall -q -f path/to/package' "
        "origin/main"
    ) in skill
    assert "Do not rely solely on the full test suite after the final commit" in skill


def test_skill_keeps_operation_specific_global_fallbacks() -> None:
    """Each interrupted Git operation is aborted before its retry."""
    _, skill = _skill_frontmatter()

    required_commands = (
        "git rebase --abort",
        "git -c core.attributesFile=/dev/null rebase origin/main",
        "git merge --abort",
        "git -c core.attributesFile=/dev/null merge <same-original-arguments>",
        "git cherry-pick --abort",
        "git -c core.attributesFile=/dev/null cherry-pick "
        "<same-original-arguments>",
    )
    for command in required_commands:
        assert command in skill


def test_skill_distinguishes_attribute_sources_and_bypass_scopes() -> None:
    """The scope matrix preserves the distinct Git attribute levers."""
    _, skill = _skill_frontmatter()

    assert "reports only effective attribute values" in skill
    assert "`git config --path --get core.attributesFile`" in skill
    assert "| Global | Configured global attributes file" in skill
    assert "| Tracked | Repository `.gitattributes`" in skill
    assert "| Clone-local | `.git/info/attributes`" in skill
    assert "path/to/file.py !merge" in skill
    assert "restore `.git/info/attributes` only after the operation completes" in skill
    assert "`/dev/null` alone cannot override those rules" in skill


def test_rebase_skill_routes_garbled_results_to_weave_recovery() -> None:
    """The general rebase workflow points failures to the detailed fallback."""
    rebase_skill = _read(REBASE_SKILL_PATH)

    assert "# Rebase the current branch" in rebase_skill
    assert (
        "[weave-git-merge recovery and built-in-merge fallback]"
        "(../weave-git-merge/SKILL.md#recover-safely)"
    ) in rebase_skill
    assert "before continuing the rebase" in rebase_skill


def test_behaviour_reference_records_the_known_import_risk() -> None:
    """The behavioural reference retains the observed unsafe reconstruction."""
    behaviour = _read(BEHAVIOUR_PATH)

    assert "conflict-free replicated data type (CRDT)" in behaviour
    assert "Do not generalize the import-addition case to import relocation" in behaviour
    assert "non-parsing Python despite a clean exit" in behaviour
    assert "belongs on the line-level-fallback path" in behaviour


def test_global_attribute_bypass_recovers_a_rebase(tmp_path: Path) -> None:
    """The documented override retries a rebase with Git's built-in merge."""
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "example.py"
    attributes = tmp_path / "global-attributes"

    _git(repository, "init", "--quiet", "--initial-branch=main")
    _git(repository, "config", "user.name", "Weave Skill Test")
    _git(repository, "config", "user.email", "weave-skill@example.invalid")
    source.write_text("base one\nbase two\nbase three\n", encoding="utf-8")
    _git(repository, "add", "example.py")
    _git(repository, "commit", "--quiet", "-m", "base")

    _git(repository, "switch", "--quiet", "--create", "topic")
    source.write_text("base one\nbase two\ntopic three\n", encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "topic change")

    _git(repository, "switch", "--quiet", "main")
    source.write_text("main one\nbase two\nbase three\n", encoding="utf-8")
    _git(repository, "commit", "--quiet", "--all", "-m", "main change")
    _git(repository, "switch", "--quiet", "topic")

    attributes.write_text("*.py merge=weave\n", encoding="utf-8")
    _git(repository, "config", "core.attributesFile", str(attributes))
    _git(repository, "config", "merge.weave.name", "failing test driver")
    _git(repository, "config", "merge.weave.driver", "false")

    selected = _git(repository, "check-attr", "merge", "--", "example.py")
    assert selected.stdout.rstrip().endswith("merge: weave")

    failed_rebase = _git(repository, "rebase", "main", check=False)
    assert failed_rebase.returncode != 0, "custom merge driver should stop rebase"
    _git(repository, "rebase", "--abort")

    bypassed = _git(
        repository,
        "-c",
        "core.attributesFile=/dev/null",
        "check-attr",
        "merge",
        "--",
        "example.py",
    )
    assert bypassed.stdout.rstrip().endswith("merge: unspecified")

    _git(
        repository,
        "-c",
        "core.attributesFile=/dev/null",
        "rebase",
        "main",
    )
    assert source.read_text(encoding="utf-8") == (
        "main one\nbase two\ntopic three\n"
    )
