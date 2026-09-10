"""Behavioural test for the install-skills copy boundary.

The comenq-coderabbit skill reaches an agent's skill directory only through
the `install-skills` installer, so this module executes that installer's real
`copy_skills` function rather than re-deriving what it ought to do.

The function is extracted from the script with the same awk process
substitution `tests/test_bootstrap_common.py` uses for `install-sub-agents`.
The rest of the installer is deliberately not run: its other work clones
remote skill repositories. HOME is a temporary directory and the Codex and
Claude skill directories are the installer's own HOME-derived values, so the
real skill paths are never touched.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from comenq_coderabbit_support import REPO_ROOT, SKILL_ROOT

INSTALL_SKILLS_PATH = REPO_ROOT / "install-skills"
SKILL_NAME = "comenq-coderabbit"

#: Skill files the installer must deliver to both agents.
REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "references/failure-modes-and-recovery.md",
    "references/evidence-and-rehearsal.md",
)

CODEX_SKILLS_DIR = "CODEX_SKILLS_DIR"
CLAUDE_SKILLS_DIR = "CLAUDE_SKILLS_DIR"


def _fd_binary() -> str:
    """Return the file-finder binary the installer requires.

    Returns
    -------
    str
        An absolute path to `fd`, or to `fdfind` on Debian-derived systems.

    Raises
    ------
    pytest.skip.Exception
        Raised when neither binary is installed, because the installer itself
        refuses to run without one.
    """
    found = shutil.which("fd") or shutil.which("fdfind")
    if found is None:
        pytest.skip("install-skills requires fd or fdfind, which is not installed")
    return found


def source_copy_skills() -> str:
    """Return Bash code that sources `copy_skills` from the installer.

    Returns
    -------
    str
        A `source <(awk ...)` expression that extracts the single function,
        stopping at its closing brace so no other installer code runs.
    """
    return (
        "source <(awk '\n"
        "  /^function copy_skills[[:space:]]*[(][)]/ { emit=1 }\n"
        "  emit { print }\n"
        "  emit && /^}[[:space:]]*$/ { exit }\n"
        f"' {shlex.quote(str(INSTALL_SKILLS_PATH))})"
    )


def installer_assignment(name: str) -> str:
    """Return the installer's own HOME-derived assignment for one variable.

    Parameters
    ----------
    name : str
        Variable name the installer assigns, such as `CODEX_SKILLS_DIR`.

    Returns
    -------
    str
        The assignment line, extracted from the real script so the test
        follows the installer rather than restating its paths.

    Raises
    ------
    AssertionError
        Raised when the installer no longer derives the variable from HOME.
    """
    pattern = re.compile(rf'^{name}="\$\{{HOME\}}[^"]*"$', re.MULTILINE)
    match = pattern.search(INSTALL_SKILLS_PATH.read_text(encoding="utf-8"))
    assert match is not None, (
        f"install-skills must keep deriving {name} from HOME, so an install "
        f"cannot escape the temporary HOME under test"
    )
    return match.group(0)


def run_copy_skills(
    tmp_path: Path,
    skills_src: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the installer's real `copy_skills` against one skills directory.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory that holds the isolated HOME.
    skills_src : Path
        Directory the function copies immediate skill directories from.

    Returns
    -------
    subprocess.CompletedProcess
        Completed Bash process with its exit code, stdout and stderr.

    Raises
    ------
    OSError
        Raised when the Bash process cannot be started.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    process_env = os.environ.copy()
    process_env.update(
        {
            "HOME": home.as_posix(),
            "FD_BIN": _fd_binary(),
        },
    )
    body = "\n".join(
        (
            "set -euo pipefail",
            installer_assignment(CODEX_SKILLS_DIR),
            installer_assignment(CLAUDE_SKILLS_DIR),
            source_copy_skills(),
            f"copy_skills {shlex.quote(skills_src.as_posix())}",
        ),
    )
    return subprocess.run(
        ["bash", "--norc", "--noprofile"],
        input=body,
        cwd=tmp_path,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


def build_skills_source(tmp_path: Path) -> Path:
    """Build an isolated source tree holding the real skill directory.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory that receives the fixture.

    Returns
    -------
    Path
        A skills directory containing the repository's `comenq-coderabbit`
        skill and one unrelated neighbour.
    """
    skills_src = tmp_path / "checked-out" / "skills"
    skills_src.mkdir(parents=True)
    shutil.copytree(SKILL_ROOT, skills_src / SKILL_NAME)
    neighbour = skills_src / "neighbour-skill"
    neighbour.mkdir()
    (neighbour / "SKILL.md").write_text("---\nname: neighbour\n---\n", encoding="utf-8")
    (skills_src / "not-a-skill.md").write_text("loose file\n", encoding="utf-8")
    return skills_src


def test_copy_skills_installs_the_skill_for_both_agents(tmp_path: Path) -> None:
    """The installer delivers the skill and its references to both agents."""
    skills_src = build_skills_source(tmp_path)

    result = run_copy_skills(tmp_path, skills_src)

    assert result.returncode == 0, (
        "the installer's copy_skills must succeed for an existing skills "
        f"directory: expected exit 0 but got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    home = tmp_path / "home"
    for skills_dir, agent in (
        (home / ".codex" / "skills", "Codex"),
        (home / ".claude" / "skills", "Claude"),
    ):
        installed = skills_dir / SKILL_NAME
        assert installed.is_dir(), (
            f"the installer must copy {SKILL_NAME} into the {agent} skill path: "
            f"expected a directory at {installed}"
        )
        for relative in REQUIRED_SKILL_FILES:
            delivered = installed / relative
            assert delivered.is_file(), (
                f"the {agent} install must include {relative}: "
                f"expected a file at {delivered}"
            )
            assert delivered.read_bytes() == (SKILL_ROOT / relative).read_bytes(), (
                f"the {agent} install of {relative} must match the repository "
                f"copy byte for byte"
            )
        assert (skills_dir / "neighbour-skill" / "SKILL.md").is_file(), (
            f"the installer must copy every immediate skill directory into the "
            f"{agent} skill path"
        )
        assert not (skills_dir / "not-a-skill.md").exists(), (
            f"the installer must copy skill directories only, not loose files "
            f"into the {agent} skill path"
        )


def test_copy_skills_reports_a_missing_source_directory(tmp_path: Path) -> None:
    """A missing skills directory must fail loudly instead of copying nothing."""
    missing = tmp_path / "absent" / "skills"

    result = run_copy_skills(tmp_path, missing)

    assert result.returncode != 0, (
        "the installer must not report success when its skills directory is "
        f"missing: expected a non-zero exit but got 0; stdout={result.stdout!r}"
    )
    assert "Skills directory not found" in result.stderr, (
        "the installer must name the missing skills directory on stderr: "
        f"got {result.stderr!r}"
    )
