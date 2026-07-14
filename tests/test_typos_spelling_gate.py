"""Behavioural tests for the generated typos spelling gate."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import types

import pytest

from typos_rollout_test_support import (
    LOCAL_DICTIONARY_PATH,
    REPOSITORY_ROOT,
    SHARED_DICTIONARY_PATH,
    require_executable,
)


def test_makefile_spelling_gate_uses_pinned_typos() -> None:
    """The CI entrypoint generates config and runs a pinned typos binary."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ci: check-fmt lint typecheck test" in makefile, "CI prerequisites changed"
    assert "+$(MAKE) spelling" in makefile, "CI does not serialize spelling after tests"
    assert re.search(r"^TYPOS_VERSION\s*\?=\s*\S+", makefile, re.MULTILINE), (
        "Makefile does not pin typos"
    )
    assert "scripts/typos_rollout_cli.py generate" in makefile, (
        "spelling target does not generate configuration"
    )
    assert "scripts/typos_rollout_cli.py check" in makefile, (
        "spelling target does not enforce exact phrase corrections"
    )
    assert "typos@$(TYPOS_VERSION)" in makefile, "spelling target bypasses the version pin"
    assert "--config typos.toml --force-exclude ." in makefile, (
        "spelling target does not apply generated configuration and exclusions"
    )


def prepare_spelling_gate_repository(tmp_path: Path) -> Path:
    """Create an indexed consumer fixture for behavioural Makefile checks."""
    repository = tmp_path / "consumer"
    repository.mkdir()
    for path in ("Makefile", "typos.local.toml", "typos.toml"):
        shutil.copy2(REPOSITORY_ROOT / path, repository / path)
    shutil.copytree(REPOSITORY_ROOT / "data", repository / "data")
    shutil.copytree(REPOSITORY_ROOT / "scripts", repository / "scripts")
    git = require_executable("git")
    subprocess.run(
        [git, "init", "--quiet"],
        cwd=repository,
        check=True,
        timeout=30,
    )
    subprocess.run(
        [git, "add", "."],
        cwd=repository,
        check=True,
        timeout=30,
    )
    return repository


def run_spelling_gate(repository: Path) -> subprocess.CompletedProcess[str]:
    """Run generation and drift validation without invoking the real scanner."""
    make = require_executable("make")
    return subprocess.run(
        [make, "spelling", "TYPOS=true"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_spelling_gate_rejects_stale_generated_config(tmp_path: Path) -> None:
    """The spelling target fails when indexed policy outpaces its config."""
    repository = prepare_spelling_gate_repository(tmp_path)
    local_policy = repository / "typos.local.toml"
    original_policy = local_policy.read_text(encoding="utf-8")
    updated_policy = original_policy.replace(
        '  "mold",\n',
        '  "mold",\n  "reviewfixtureword",\n',
    )
    assert updated_policy != original_policy, "fixture did not change local spelling policy"
    local_policy.write_text(updated_policy, encoding="utf-8")
    git = require_executable("git")
    subprocess.run(
        [git, "add", "typos.local.toml"],
        cwd=repository,
        check=True,
        timeout=30,
    )

    result = run_spelling_gate(repository)

    assert result.returncode != 0, "spelling gate accepted stale generated configuration"
    assert '"reviewfixtureword" = "reviewfixtureword"' in result.stdout, (
        "failure output did not show generated configuration drift"
    )


def test_spelling_gate_rejects_untracked_generated_config(tmp_path: Path) -> None:
    """The spelling target fails when its generated config is not indexed."""
    repository = prepare_spelling_gate_repository(tmp_path)
    git = require_executable("git")
    subprocess.run(
        [git, "rm", "--cached", "--quiet", "typos.toml"],
        cwd=repository,
        check=True,
        timeout=30,
    )

    result = run_spelling_gate(repository)

    assert result.returncode != 0, "spelling gate accepted an untracked generated config"


def test_phrase_checker_respects_boundaries_and_ignored_text(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Exact phrase policy checks prose without broad substring matches."""
    repository = tmp_path / "consumer"
    repository.mkdir()
    (repository / "README.md").write_text(
        "hand-written\n"
        "Hand-written prose\n"
        "handwritten\n"
        "hand-writtenness\n"
        "pre-hand-written\n"
        "`hand-written`\n",
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True, timeout=30)
    subprocess.run([git, "add", "."], cwd=repository, check=True, timeout=30)
    dictionary = rollout.Dictionary(
        phrase_corrections=(("hand-written", "handwritten"),),
        ignore_patterns=(r"`[^`\n]+`",),
    )

    findings = rollout.check_phrase_corrections(repository, dictionary)

    assert [(finding.line, finding.phrase) for finding in findings] == [
        (1, "hand-written"),
        (2, "Hand-written"),
    ], "phrase checker did not preserve exact compound boundaries"


def test_spelling_gate_rejects_hyphenated_hand_written(tmp_path: Path) -> None:
    """The complete spelling gate rejects the prohibited hyphenated compound."""
    repository = prepare_spelling_gate_repository(tmp_path)
    readme = repository / "README.md"
    readme.write_text("Prefer hand-written notes.\n", encoding="utf-8")
    git = require_executable("git")
    subprocess.run([git, "add", "README.md"], cwd=repository, check=True, timeout=30)

    result = run_spelling_gate(repository)

    assert result.returncode != 0, "spelling gate accepted hand-written prose"
    assert "README.md:1:8: hand-written -> handwritten" in result.stdout, (
        "spelling gate did not report the canonical handwritten replacement"
    )


@pytest.mark.slow
def test_generated_config_loads_in_pinned_typos(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """The real consumer enforces Oxford and British sample spellings."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the pinned typos binary")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TYPOS_VERSION\s*\?=\s*(\S+)", makefile, re.MULTILINE)
    assert match is not None, "TYPOS_VERSION not found in Makefile"
    config = tmp_path / "typos.toml"
    rollout.write_config(
        config,
        rollout.merge_dictionaries(
            rollout.load_dictionary(SHARED_DICTIONARY_PATH),
            rollout.load_dictionary(LOCAL_DICTIONARY_PATH, local_overlay=True),
        ),
    )
    sample = tmp_path / "sample.md"
    sample.write_text(
        "We organise color output but analyse valid results.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            uv,
            "tool",
            "run",
            f"typos@{match.group(1)}",
            "--config",
            str(config),
            "--format",
            "json",
            str(sample),
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=90,
    )
    corrections = {
        entry["typo"]: entry.get("corrections", [])
        for line in result.stdout.splitlines()
        for entry in (json.loads(line),)
        if entry.get("type") == "typo"
    }

    assert corrections.get("organise") == ["organize"], (
        "Oxford correction was not enforced"
    )
    assert corrections.get("color") == ["colour"], (
        "British colour spelling was not enforced"
    )
    assert "analyse" not in corrections, "valid -yse spelling was rejected"
