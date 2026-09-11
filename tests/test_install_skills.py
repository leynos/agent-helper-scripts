"""Behavioural tests for the install-skills installer orchestration.

`install-skills` must install the nextest and vidai-mock skills from the
managed `agent-helper-scripts` checkout. The retired standalone
`nextest-skill` and `vidai-mock-skill` repositories are no longer contacted,
so an implementation that restored their clone or copy calls would break the
skills' provenance without failing any narrower test:
`tests/test_comenq_coderabbit_install.py` extracts and exercises `copy_skills`
alone and deliberately never runs the installer's orchestration.

These tests run the real script as a subprocess with a fake `git` first on
PATH, a temporary HOME, and the real `fd` binary. The fake `git` never touches
the network; it records its argv and creates plausible checkouts so
`copy_skills` has real directories to copy. HOME and FD_BIN keep every side
effect inside `tmp_path`, so the real skill directories are never touched.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SKILLS_PATH = REPO_ROOT / "install-skills"
BASH_PATH = Path(shutil.which("bash") or "/usr/bin/bash")

HELPER_REPO_URL = "https://github.com/leynos/agent-helper-scripts.git"
RUST_SKILL_REPO_URL = "https://github.com/leynos/rust-skill.git"

#: Skill directories the managed checkout must deliver to both agents.
MANAGED_SKILLS = ("nextest", "vidai-mock")

#: Directories of the retired standalone repositories, whose skills are now
#: imported into the managed checkout.
RETIRED_REPO_DIRS = ("nextest-skill", "vidai-mock-skill")

#: Marker written into a stale standalone checkout; it must never reach an
#: installed skill path.
STALE_SENTINEL = "stale-standalone-checkout-sentinel"

#: Fake `git` body: log the argv, then create a checkout for clone calls.
#: Every non-clone call (fetch, reset, sparse-checkout) succeeds without
#: touching the network, as the real commands would for an existing checkout.
FAKE_GIT_BODY = """\
printf 'git %s\\n' "$*" >> "${GIT_LOG:?}"

if [[ "${1:-}" != clone ]]; then
  exit 0
fi

repo_url=""
for argument in "$@"; do
  if [[ "${argument}" == *://* ]]; then
    repo_url="${argument}"
  fi
done
checkout_dir="${!#}"

mkdir -p "${checkout_dir}/.git"
case "${repo_url}" in
  *agent-helper-scripts*)
    cp -a "${FAKE_GIT_FIXTURES:?}/agent-helper-scripts/skills" "${checkout_dir}/"
    ;;
  *rust-skill*)
    cp -a "${FAKE_GIT_FIXTURES:?}/rust-skill/skills" "${checkout_dir}/"
    ;;
  *)
    cp -a "${FAKE_GIT_FIXTURES:?}/standalone/skills" "${checkout_dir}/"
    ;;
esac
"""


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


def installer_home_relative_repo_dir() -> Path:
    """Return the managed checkout path the installer derives from HOME.

    Returns
    -------
    Path
        The HOME-relative default of `REPO_DIR`, such as
        `git/agent-helper-scripts`.

    Raises
    ------
    AssertionError
        Raised when the installer no longer derives `REPO_DIR` from HOME, so
        an install could escape the temporary HOME under test.
    """
    pattern = re.compile(
        r'^REPO_DIR="\$\{REPO_DIR:-\$\{HELPER_TOOLS_REPO_DIR:-\$\{HOME\}'
        r'(?P<relative>[^"]*)\}\}"$',
        re.MULTILINE,
    )
    match = pattern.search(INSTALL_SKILLS_PATH.read_text(encoding="utf-8"))
    assert match is not None, (
        "install-skills must keep deriving REPO_DIR from HOME, so the managed "
        "checkout under test stays inside the temporary HOME"
    )
    return Path(match.group("relative").lstrip("/"))


def agent_skill_dirs(home: Path) -> tuple[tuple[Path, str], ...]:
    """Return each agent's installed skill root and its display name.

    Parameters
    ----------
    home : Path
        Temporary HOME the installer writes its skill directories under.

    Returns
    -------
    tuple of tuple of (Path, str)
        One entry per agent, pairing the skill root with its display name.
    """
    return (
        (home / ".codex" / "skills", "Codex"),
        (home / ".claude" / "skills", "Claude"),
    )


def write_script(path: Path, body: str) -> None:
    """Write an executable Bash helper script.

    Parameters
    ----------
    path : Path
        Destination script path; its parent directory must exist.
    body : str
        Script body appended after the shebang and safety options.

    Returns
    -------
    None
        The function writes the file in place.

    Raises
    ------
    OSError
        Raised when the file cannot be written or chmod fails.
    """
    path.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n")
    path.chmod(0o755)


def build_fixtures(fixtures: Path) -> None:
    """Populate the checkout contents the fake `git` creates.

    Parameters
    ----------
    fixtures : Path
        Directory that receives one tree per repository the fake `git` can be
        asked to clone. The managed checkout carries nextest and vidai-mock,
        the rust-skill checkout carries a distinguishable rust-router skill,
        and the standalone tree carries the sentinel content a stale
        standalone checkout would hold.

    Returns
    -------
    None
        Trees are written in place.

    Raises
    ------
    OSError
        Raised when a fixture file cannot be written.
    """
    helper_skills = fixtures / "agent-helper-scripts" / "skills"
    for skill in MANAGED_SKILLS:
        skill_dir = helper_skills / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill}\n---\n"
            f"agent-helper-scripts checkout copy of {skill}\n",
            encoding="utf-8",
        )
    rust_skill = fixtures / "rust-skill" / "skills" / "rust-router"
    rust_skill.mkdir(parents=True)
    (rust_skill / "SKILL.md").write_text(
        "---\nname: rust-router\n---\nrust-skill checkout copy\n",
        encoding="utf-8",
    )
    standalone_skills = fixtures / "standalone" / "skills"
    for skill in MANAGED_SKILLS:
        skill_dir = standalone_skills / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"{STALE_SENTINEL}\n",
            encoding="utf-8",
        )


def run_installer(
    tmp_path: Path,
    home: Path,
    *,
    git_log: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the real installer against a temporary HOME and a fake `git`.

    Parameters
    ----------
    tmp_path : Path
        Temporary directory that holds the fake `git` and its fixtures.
    home : Path
        Temporary HOME the installer derives every path from.
    git_log : Path
        File the fake `git` appends its argv to.

    Returns
    -------
    subprocess.CompletedProcess
        Completed Bash process with its exit code, stdout and stderr.

    Raises
    ------
    OSError
        Raised when the Bash process cannot be started.

    Notes
    -----
    The environment is built from scratch so an ambient REPO_DIR,
    HELPER_TOOLS_REPO_DIR or HELPER_TOOLS_REPO_BRANCH cannot redirect the
    installer outside the temporary HOME.
    """
    bin_dir = tmp_path / "bin"
    fixtures = tmp_path / "fixtures"
    bin_dir.mkdir(parents=True)
    build_fixtures(fixtures)
    write_script(bin_dir / "git", FAKE_GIT_BODY)
    home.mkdir(parents=True, exist_ok=True)
    process_env = {
        "HOME": home.as_posix(),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "FD_BIN": _fd_binary(),
        "FAKE_GIT_FIXTURES": fixtures.as_posix(),
        "GIT_LOG": git_log.as_posix(),
    }
    return subprocess.run(
        [str(BASH_PATH), "--norc", "--noprofile", str(INSTALL_SKILLS_PATH)],
        cwd=home,
        env=process_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_installer_contacts_only_the_managed_repositories(tmp_path: Path) -> None:
    """The installer clones agent-helper-scripts and rust-skill exactly once."""
    home = tmp_path / "home"
    git_log = tmp_path / "git.log"

    result = run_installer(tmp_path, home, git_log=git_log)

    assert result.returncode == 0, (
        "install-skills must succeed with a fake git on PATH: "
        f"expected exit 0 but got {result.returncode}; stderr={result.stderr!r}"
    )
    lines = git_log.read_text(encoding="utf-8").splitlines()
    clone_lines = [line for line in lines if line.startswith("git clone")]
    assert len(clone_lines) == 2, (
        "install-skills must clone exactly the two managed repositories: "
        f"expected 2 clone commands but got {clone_lines!r}"
    )
    assert sum(HELPER_REPO_URL in line for line in clone_lines) == 1, (
        "install-skills must clone agent-helper-scripts exactly once: "
        f"got {clone_lines!r}"
    )
    assert sum(RUST_SKILL_REPO_URL in line for line in clone_lines) == 1, (
        "install-skills must clone rust-skill exactly once: "
        f"got {clone_lines!r}"
    )
    retired_lines = [
        line for line in lines if any(name in line for name in RETIRED_REPO_DIRS)
    ]
    assert retired_lines == [], (
        "install-skills must not clone, fetch, or reset the retired standalone "
        f"repositories nextest-skill and vidai-mock-skill: {retired_lines!r}"
    )


def test_installer_delivers_both_imported_skills_from_the_managed_checkout(
    tmp_path: Path,
) -> None:
    """nextest and vidai-mock reach both agents from the managed checkout."""
    home = tmp_path / "home"

    result = run_installer(tmp_path, home, git_log=tmp_path / "git.log")

    assert result.returncode == 0, (
        "install-skills must succeed with a fake git on PATH: "
        f"expected exit 0 but got {result.returncode}; stderr={result.stderr!r}"
    )
    managed_skills = home / installer_home_relative_repo_dir() / "skills"
    for skills_dir, agent in agent_skill_dirs(home):
        for skill in MANAGED_SKILLS:
            expected = managed_skills / skill / "SKILL.md"
            installed = skills_dir / skill / "SKILL.md"
            assert installed.is_file(), (
                f"the installer must copy {skill} into the {agent} skill path: "
                f"expected a file at {installed}"
            )
            assert installed.read_bytes() == expected.read_bytes(), (
                f"the {agent} install of {skill} must match the managed "
                f"checkout's own copy at {expected}"
            )


def test_stale_standalone_checkout_cannot_supply_the_installed_skills(
    tmp_path: Path,
) -> None:
    """Stale standalone checkouts are ignored: managed content wins."""
    home = tmp_path / "home"
    repo_parent = installer_home_relative_repo_dir().parent
    for repo_dir, skill in zip(RETIRED_REPO_DIRS, MANAGED_SKILLS, strict=True):
        stale_skill = home / repo_parent / repo_dir / "skills" / skill
        stale_skill.mkdir(parents=True)
        (stale_skill / "SKILL.md").write_text(
            f"{STALE_SENTINEL}\n",
            encoding="utf-8",
        )

    result = run_installer(tmp_path, home, git_log=tmp_path / "git.log")

    assert result.returncode == 0, (
        "install-skills must succeed with stale standalone checkouts on disk: "
        f"expected exit 0 but got {result.returncode}; stderr={result.stderr!r}"
    )
    for skills_dir, agent in agent_skill_dirs(home):
        for skill in MANAGED_SKILLS:
            installed = skills_dir / skill / "SKILL.md"
            assert installed.is_file(), (
                f"the installer must copy {skill} into the {agent} skill path: "
                f"expected a file at {installed}"
            )
            assert STALE_SENTINEL not in installed.read_text(encoding="utf-8"), (
                f"the {agent} install of {skill} must come from the managed "
                f"checkout, not a stale standalone one: {installed}"
            )
        stale_copies = sorted(
            path
            for path in skills_dir.rglob("*.md")
            if STALE_SENTINEL in path.read_text(encoding="utf-8")
        )
        assert stale_copies == [], (
            f"no stale standalone content may be installed into the {agent} "
            f"skill path: found it in {stale_copies!r}"
        )


def test_installer_reports_a_managed_checkout_without_a_skills_directory(
    tmp_path: Path,
) -> None:
    """A checkout missing its skills directory fails loudly, naming the path."""
    home = tmp_path / "home"
    managed_checkout = home / installer_home_relative_repo_dir()
    managed_checkout.mkdir(parents=True)

    result = run_installer(tmp_path, home, git_log=tmp_path / "git.log")

    assert result.returncode != 0, (
        "install-skills must fail when the managed checkout has no skills "
        f"directory: expected a non-zero exit but got 0; stdout={result.stdout!r}"
    )
    assert "Skills directory not found" in result.stderr, (
        "install-skills must report the missing skills directory on stderr: "
        f"got {result.stderr!r}"
    )
    missing = managed_checkout / "skills"
    assert str(missing) in result.stderr, (
        f"install-skills must name the missing directory {missing}: "
        f"got {result.stderr!r}"
    )
