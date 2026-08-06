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
    content = _read(SKILL_PATH)
    assert content.startswith("---\n"), (
        "the Weave skill must open with the YAML frontmatter delimiter, "
        "with no leading prose"
    )
    parts = content.split("---", maxsplit=2)
    assert len(parts) == 3, "the Weave skill must have YAML frontmatter"
    body = parts[2]
    assert body.lstrip("\n").startswith("# Use Weave with Git\n"), (
        "the level-1 title must immediately follow the closing frontmatter "
        "delimiter"
    )
    return _mapping(parts[1]), body


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

    assert frontmatter.get("name") == "weave-git-merge", (
        "the skill name must match its directory so discovery resolves it"
    )
    assert isinstance(description, str), "the skill must declare a description"
    assert "detecting structurally corrupt clean results" in description, (
        "discovery must advertise silent-corruption detection"
    )
    assert "bypassing Weave safely" in description, (
        "discovery must advertise the safe bypass route"
    )

    metadata = _mapping(_read(AGENT_METADATA_PATH))
    interface = metadata.get("interface")
    assert isinstance(interface, dict), "agent metadata must define interface"
    assert interface.get("display_name") == "Weave Git Merge", (
        "the OpenAI agent definition must expose the skill display name"
    )
    assert "$weave-git-merge" in str(interface.get("default_prompt")), (
        "the default prompt must invoke the weave-git-merge skill"
    )


def test_skill_requires_structural_checks_before_continue() -> None:
    """The workflow catches malformed output before Git records it."""
    _, skill = _skill_frontmatter()

    assert "python -m py_compile path/to/file.py" in skill, (
        "the workflow must show a per-file structural parse check"
    )
    assert "set -o pipefail" in skill, (
        "the piped check must fail when the producing command fails"
    )
    assert "ast.parse(sys.stdin.read())" in skill, (
        "the workflow must parse an index stage without touching the worktree"
    )
    assert "before `git add` or `git rebase --continue`" in skill, (
        "the check must be mandated before Git records the resolution"
    )


def test_skill_declares_bash_as_the_shell_for_every_example() -> None:
    """Bash-only syntax is covered by an explicit shell requirement."""
    _, skill = _skill_frontmatter()

    assert "Every shell example below requires Bash." in skill, (
        "the skill must state that its shell examples require Bash"
    )
    requirement, _, remainder = skill.partition(
        "Every shell example below requires Bash."
    )
    assert "```" not in requirement, (
        "the Bash requirement must precede every command block it governs"
    )
    assert "`set -o pipefail` is a Bash builtin option" in remainder, (
        "the requirement must call out the Bash-only stage-validation option"
    )

    fences = [line for line in skill.splitlines() if line.startswith("```")]
    opening_fences = fences[::2]
    assert opening_fences, "the skill must contain fenced command blocks"
    assert all(fence == "```bash" for fence in opening_fences), (
        f"every command fence must be labelled bash, found {sorted(set(opening_fences))}"
    )


def test_skill_preserves_all_three_stage_inspection_commands() -> None:
    """The workflow keeps non-mutating inspection for every index stage."""
    _, skill = _skill_frontmatter()

    for stage in (1, 2, 3):
        assert f"git show :{stage}:path/to/file.py" in skill, (
            f"index stage {stage} must have a non-mutating inspection command"
        )
    assert (
        "stage 2 can\nalready contain an earlier silently corrupted replay"
    ) in skill, "the workflow must warn that stage 2 is not a trusted baseline"


def test_skill_guards_each_commit_in_a_multi_commit_rebase() -> None:
    """The workflow prevents an early clean corruption from cascading."""
    _, skill = _skill_frontmatter()

    assert "## Guard a multi-commit rebase" in skill, (
        "the workflow must cover multi-commit rebases explicitly"
    )
    assert (
        "git rebase --exec 'python -m compileall -q -f path/to/package' origin/main"
    ) in skill, "each replayed commit must be checked by a rebase --exec guard"
    assert (
        "Do not rely solely on the full test suite after the final commit" in skill
    ), "the workflow must reject end-of-rebase-only validation"


def test_skill_keeps_operation_specific_global_fallbacks() -> None:
    """Each interrupted Git operation is aborted before its retry."""
    _, skill = _skill_frontmatter()

    required_commands = (
        "git rebase --abort",
        "git -c core.attributesFile=/dev/null rebase origin/main",
        "git merge --abort",
        "git -c core.attributesFile=/dev/null merge <same-original-arguments>",
        "git cherry-pick --abort",
        "git -c core.attributesFile=/dev/null cherry-pick <same-original-arguments>",
    )
    for command in required_commands:
        assert command in skill, (
            f"the fallback must document `{command}` so each operation is "
            "aborted before its own retry"
        )


def test_skill_distinguishes_attribute_sources_and_bypass_scopes() -> None:
    """The scope matrix preserves the distinct Git attribute levers."""
    _, skill = _skill_frontmatter()

    assert "reports only effective attribute values" in skill, (
        "the workflow must warn that check-attr hides the attribute source"
    )
    assert "`git config --path --get core.attributesFile`" in skill, (
        "the workflow must show how to locate the global attributes file"
    )
    assert "| Global | Configured global attributes file" in skill, (
        "the scope matrix must cover the global attributes file"
    )
    assert "| Tracked | Repository `.gitattributes`" in skill, (
        "the scope matrix must cover tracked repository attributes"
    )
    assert "| Clone-local | `.git/info/attributes`" in skill, (
        "the scope matrix must cover clone-local attributes"
    )
    assert "path/to/file.py !merge" in skill, (
        "the workflow must show the per-path merge-driver opt-out"
    )
    assert (
        "restore `.git/info/attributes` only after the operation completes" in skill
    ), "the clone-local bypass must not be reverted mid-operation"
    assert "`/dev/null` alone cannot override those rules" in skill, (
        "the workflow must state the limits of the global-file override"
    )


def test_rebase_skill_routes_garbled_results_to_weave_recovery() -> None:
    """The general rebase workflow points failures to the detailed fallback."""
    rebase_skill = _read(REBASE_SKILL_PATH)

    assert "# Rebase the current branch" in rebase_skill, (
        "the rebase skill must keep its level-1 title"
    )
    assert (
        "[weave-git-merge recovery and built-in-merge fallback]"
        "(../weave-git-merge/SKILL.md#recover-safely)"
    ) in rebase_skill, "the rebase skill must link to the Weave recovery section"
    assert "before continuing the rebase" in rebase_skill, (
        "recovery must happen before the rebase is allowed to continue"
    )


def test_behaviour_reference_records_the_known_import_risk() -> None:
    """The behavioural reference retains the observed unsafe reconstruction."""
    behaviour = _read(BEHAVIOUR_PATH)

    assert "conflict-free replicated data type (CRDT)" in behaviour, (
        "the reference must expand CRDT on first use"
    )
    assert (
        "Do not generalize the import-addition case to import relocation" in behaviour
    ), "the reference must scope the safe import case narrowly"
    assert "non-parsing Python despite a clean exit" in behaviour, (
        "the reference must record the observed silent corruption"
    )
    assert "belongs on the line-level-fallback path" in behaviour, (
        "the reference must state where import relocation should be handled"
    )


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
    assert selected.stdout.rstrip().endswith("merge: weave"), (
        "the global attributes file must select the Weave driver"
    )

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
    assert bypassed.stdout.rstrip().endswith("merge: unspecified"), (
        "ignoring the global attributes file must deselect the Weave driver"
    )

    _git(
        repository,
        "-c",
        "core.attributesFile=/dev/null",
        "rebase",
        "main",
    )
    assert source.read_text(encoding="utf-8") == (
        "main one\nbase two\ntopic three\n"
    ), "the built-in merge must combine both non-overlapping changes"
