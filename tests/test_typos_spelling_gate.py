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
    MISSPELLED_DRIFT_FORMS,
    REPOSITORY_ROOT,
    SHARED_DICTIONARY_PATH,
    deny_path_reads,
    require_executable,
)

HYPHENATED_HANDWRITTEN = "hand" + "-written"
TITLE_HYPHENATED_HANDWRITTEN = "Hand" + "-written"
PLAIN_BRITISH_ORGANIZE = "organi" + "se"
AMERICAN_COLOUR = "col" + "or"
MISSPELLED_ARTICLE = "t" + "eh"


def test_makefile_spelling_gate_uses_pinned_typos() -> None:
    """The CI entrypoint runs the shared gate runner with a pinned typos binary."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "CI_GATES := check-fmt markdownlint lint typecheck test" in makefile, (
        "CI prerequisites changed"
    )
    assert "ci: $(CI_GATES)" in makefile, "CI ignores the declared gate sequence"
    assert "+$(MAKE) spelling" in makefile, "CI does not serialize spelling after tests"
    assert re.search(r"^TYPOS_VERSION\s*\?=\s*\S+", makefile, re.MULTILINE), (
        "Makefile does not pin typos"
    )
    assert "scripts/gate_runner_cli.py spelling" in makefile, (
        "spelling target does not run the shared gate runner, which generates "
        "the configuration, enforces phrase corrections, and discovers the files"
    )
    assert "typos@$(TYPOS_VERSION)" in makefile, "spelling target bypasses the version pin"
    assert "data/typos-oxendict-base.toml" in makefile, (
        "spelling target does not take its policy from the shared base"
    )
    assert "--typos" in makefile, (
        "the spelling target does not hand its scanner to the gate runner"
    )
    # Checked apart rather than as one ordered substring, so a recipe that
    # reorders the flags, or writes them as ``--config=x``, is still caught.
    for flag in ("--config", "--force-exclude"):
        assert flag not in makefile, (
            f"the target passes {flag} itself; the runner owns that invocation"
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


def run_spelling_gate(
    repository: Path,
    scanner: str = "true",
) -> subprocess.CompletedProcess[str]:
    """Run the spelling target, doubling the scanner unless one is named."""
    make = require_executable("make")
    return subprocess.run(
        [make, "spelling", f"TYPOS={scanner}"],
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
        f"{HYPHENATED_HANDWRITTEN}\n"
        f"{TITLE_HYPHENATED_HANDWRITTEN} prose\n"
        "handwritten\n"
        f"{HYPHENATED_HANDWRITTEN}ness\n"
        f"pre-{HYPHENATED_HANDWRITTEN}\n"
        f"`{HYPHENATED_HANDWRITTEN}`\n",
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True, timeout=30)
    subprocess.run([git, "add", "."], cwd=repository, check=True, timeout=30)
    dictionary = rollout.Dictionary(
        phrase_corrections=((HYPHENATED_HANDWRITTEN, "handwritten"),),
        ignore_patterns=(r"`[^`\n]+`",),
    )

    findings = rollout.check_phrase_corrections(repository, dictionary)

    assert [(finding.line, finding.phrase) for finding in findings] == [
        (1, HYPHENATED_HANDWRITTEN),
        (2, TITLE_HYPHENATED_HANDWRITTEN),
    ], "phrase checker did not preserve exact compound boundaries"


def test_phrase_checker_rejects_unsafe_masking_patterns(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Policy regexes cannot introduce unbounded backtracking in the scanner."""
    repository = tmp_path / "consumer"
    repository.mkdir()
    (repository / "README.md").write_text("safe prose\n", encoding="utf-8")
    git = require_executable("git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True, timeout=30)
    subprocess.run([git, "add", "."], cwd=repository, check=True, timeout=30)

    with pytest.raises(ValueError, match="unsafe repetition"):
        rollout.check_phrase_corrections(
            repository,
            rollout.Dictionary(ignore_patterns=("(a+)+$",)),
        )


def test_phrase_checker_propagates_file_read_failures(
    rollout: types.ModuleType,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Filesystem failures fail the gate instead of silently skipping a file."""
    repository = tmp_path / "consumer"
    repository.mkdir()
    target = repository / "README.md"
    target.write_text("safe prose\n", encoding="utf-8")
    git = require_executable("git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True, timeout=30)
    subprocess.run([git, "add", "."], cwd=repository, check=True, timeout=30)
    monkeypatch.setattr(
        Path,
        "read_text",
        deny_path_reads(target, message="tracked fixture is unreadable"),
    )
    with pytest.raises(PermissionError, match="tracked fixture is unreadable"):
        rollout.check_phrase_corrections(repository, rollout.Dictionary())

    failure = next(record for record in caplog.records if record.levelname == "ERROR")
    assert getattr(failure, "operation", None) == "tracked-file-read"
    assert getattr(failure, "source_kind", None) == "repository-file"
    assert getattr(failure, "error_class", None) == "os-error"
    assert str(target) not in failure.getMessage(), (
        "tracked-file diagnostic exposed the repository path"
    )


def test_phrase_checker_skips_non_utf8_files(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Binary tracked content remains outside phrase enforcement."""
    repository = tmp_path / "consumer"
    repository.mkdir()
    (repository / "binary.dat").write_bytes(b"\xff")
    git = require_executable("git")
    subprocess.run([git, "init", "--quiet"], cwd=repository, check=True, timeout=30)
    subprocess.run([git, "add", "."], cwd=repository, check=True, timeout=30)

    assert rollout.check_phrase_corrections(repository, rollout.Dictionary()) == ()


def test_spelling_gate_rejects_hyphenated_hand_written(tmp_path: Path) -> None:
    """The complete spelling gate rejects the prohibited hyphenated compound."""
    repository = prepare_spelling_gate_repository(tmp_path)
    readme = repository / "README.md"
    readme.write_text(
        f"Prefer {HYPHENATED_HANDWRITTEN} notes.\n",
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run([git, "add", "README.md"], cwd=repository, check=True, timeout=30)

    result = run_spelling_gate(repository)

    assert result.returncode != 0, (
        f"spelling gate accepted {HYPHENATED_HANDWRITTEN} prose"
    )
    expected_diagnostic = (
        f"README.md:1:8: {HYPHENATED_HANDWRITTEN} -> handwritten"
    )
    assert expected_diagnostic in result.stdout, (
        "spelling gate did not report the canonical handwritten replacement"
    )


@pytest.mark.slow
def test_the_scan_ignores_policy_the_gate_did_not_generate(tmp_path: Path) -> None:
    """The generated configuration alone decides the gate's verdict.

    typos merges a ``typos.toml`` it finds beside the files it reads. Without
    isolation a nested policy, which the gate never generated, never required
    to be tracked as its configuration, and never checked for drift, could
    soften the verdict the gate reports as its own configuration's.
    """
    repository = prepare_spelling_gate_repository(tmp_path)
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is unavailable to run the pinned typos binary")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^TYPOS_VERSION\s*\?=\s*(\S+)", makefile, re.MULTILINE)
    assert match is not None, "TYPOS_VERSION not found in Makefile"
    docs = repository / "docs"
    docs.mkdir()
    (docs / "typos.toml").write_text(
        f'[default]\nextend-ignore-re = ["{MISSPELLED_ARTICLE}"]\n',
        encoding="utf-8",
    )
    (docs / "guide.md").write_text(
        f"The {MISSPELLED_ARTICLE} marker.\n",
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run([git, "add", "docs"], cwd=repository, check=True, timeout=30)

    result = run_spelling_gate(repository, f"uv tool run typos@{match.group(1)}")

    assert result.returncode != 0, (
        "the gate passed, so policy beside the scanned files decided the "
        f"verdict: {result.stdout}"
    )
    assert "docs/guide.md" in result.stdout + result.stderr, (
        "the gate failed without naming the file its own policy rejects"
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
    misspelled_article = "t" + "eh"
    misspelled_receive = "rec" + "ieve"
    sample.write_text(
        f"We {PLAIN_BRITISH_ORGANIZE} {AMERICAN_COLOUR} output but analyse "
        f"valid results. `{misspelled_article} {misspelled_receive}`\n"
        f"{' '.join(form for form, _correction in MISSPELLED_DRIFT_FORMS)}\n",
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

    assert corrections.get(PLAIN_BRITISH_ORGANIZE) == ["organize"], (
        "Oxford correction was not enforced"
    )
    assert corrections.get(AMERICAN_COLOUR) == ["colour"], (
        "British colour spelling was not enforced"
    )
    assert "analyse" not in corrections, "valid -yse spelling was rejected"
    assert misspelled_article in corrections, "inline-code typo was not reported"
    assert misspelled_receive in corrections, "inline-code typo was not reported"
    for form, canonical in MISSPELLED_DRIFT_FORMS:
        assert corrections.get(form) == [canonical], (
            f"{form} did not resolve to the single canonical correction"
        )
