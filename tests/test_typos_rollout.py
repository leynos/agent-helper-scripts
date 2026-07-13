"""Behavioural tests for the shared en-GB-oxendict rollout helper."""

from pathlib import Path
import subprocess
import tomllib
import types
import typing as typ

import pytest
from hypothesis import given
from hypothesis import strategies as st

from typos_rollout_test_support import (
    COMMITTED_CONFIG_PATH,
    LOCAL_DICTIONARY_PATH,
    SHARED_DICTIONARY_PATH,
    dictionary_text,
    require_executable,
)


def test_load_dictionary_rejects_unknown_schema(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Unknown dictionary schemas fail with an actionable message."""
    source = tmp_path / "base.toml"
    source.write_text(dictionary_text().replace("schema = 1", "schema = 2"))

    with pytest.raises(ValueError, match="unsupported dictionary schema 2"):
        rollout.load_dictionary(source)


def test_oxford_stem_generates_correct_and_incorrect_forms(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Each stem accepts Oxford forms and corrects plain-British forms."""
    source = tmp_path / "base.toml"
    source.write_text(dictionary_text(), encoding="utf-8")

    mappings = rollout.generate_word_mappings(rollout.load_dictionary(source))

    assert mappings["organize"] == "organize", "Oxford form was not accepted"
    assert mappings["organise"] == "organize", "plain-British form was not corrected"
    assert mappings["organizations"] == "organizations", "Oxford plural was not accepted"
    assert mappings["organisations"] == "organizations", "plain-British plural was not corrected"


@given(stem=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=16))
def test_oxford_mapping_property_covers_every_suffix_pair(
    rollout: types.ModuleType,
    stem: str,
) -> None:
    """Every safe stem expands to correction and identity entries."""
    mappings = rollout.generate_word_mappings(rollout.Dictionary(stems=(stem,)))

    for plain_british, oxford in rollout.SUFFIX_PAIRS:
        assert mappings[f"{stem}{plain_british}"] == f"{stem}{oxford}", (
            f"missing correction for {stem}{plain_british}"
        )
        assert mappings[f"{stem}{oxford}"] == f"{stem}{oxford}", (
            f"missing identity for {stem}{oxford}"
        )


def test_merge_rejects_conflicting_corrections(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """A local overlay cannot silently weaken a shared correction."""
    base_path = tmp_path / "base.toml"
    base_path.write_text(
        dictionary_text().replace(
            "[words.corrections]\n",
            '[words.corrections]\nteh = "the"\n',
        ),
        encoding="utf-8",
    )
    local_path = tmp_path / "local.toml"
    local_path.write_text(
        dictionary_text(stem="custom", accepted="localword").replace(
            "[words.corrections]\n",
            '[words.corrections]\nteh = "ten"\n',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting correction for 'teh'"):
        rollout.merge_dictionaries(
            rollout.load_dictionary(base_path),
            rollout.load_dictionary(local_path),
        )


def test_rendered_config_is_deterministic_valid_toml(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Rendered config has stable ordering and no duplicate TOML keys."""
    source = tmp_path / "base.toml"
    source.write_text(dictionary_text(), encoding="utf-8")
    dictionary = rollout.load_dictionary(source)

    first = rollout.render_typos_config(dictionary)
    second = rollout.render_typos_config(dictionary)
    parsed = tomllib.loads(first)

    assert first == second, "renderer output changed between identical calls"
    assert parsed["default"]["locale"] == "en-gb", "generated locale is not en-gb"
    assert parsed["default"]["extend-words"]["organise"] == "organize", (
        "generated config omitted the Oxford correction"
    )
    assert first.endswith("\n"), "generated config lacks a trailing newline"
    assert not first.endswith("\n\n"), "generated config has multiple trailing newlines"


def test_harvest_finds_both_oxford_and_plain_british_forms(
    rollout: types.ModuleType,
) -> None:
    """Harvesting retains evidence for both sides of an Oxford mapping."""
    forms = rollout.harvest_oxford_forms(
        "We organize releases after organising fixtures and analyse results."
    )

    assert forms == ("organising", "organize"), "harvest omitted or added Oxford candidates"


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("typos.toml"),
        Path("nested/.terraform/providers/upstream/CHANGELOG.md"),
        Path("nested/target/generated.rs"),
        Path("data/typos-oxendict-base.toml"),
    ],
)
def test_harvest_excludes_dictionary_managed_paths(
    rollout: types.ModuleType,
    relative_path: Path,
) -> None:
    """Harvesting omits generated and dependency-managed spelling evidence."""
    dictionary = rollout.load_dictionary(SHARED_DICTIONARY_PATH)

    assert rollout.is_harvest_excluded(relative_path, dictionary), (
        f"managed path was not excluded: {relative_path}"
    )


def test_harvest_repository_merges_local_exclusions(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Repository-local excluded fixtures do not enter harvest evidence."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "fixture.md").write_text(
        "The fixture deliberately says organise.\n",
        encoding="utf-8",
    )
    (repository / "kept.md").write_text(
        "The guide says organize.\n",
        encoding="utf-8",
    )
    (repository / "typos.local.toml").write_text(
        dictionary_text().replace('[files]\nexclude = [".git"]', '[files]\nexclude = ["fixture.md"]'),
        encoding="utf-8",
    )
    git = require_executable("git")
    subprocess.run(
        [git, "init", "-q", repository],
        check=True,
        timeout=30,
    )
    subprocess.run(
        [git, "-C", repository, "add", "fixture.md", "kept.md", "typos.local.toml"],
        check=True,
        timeout=30,
    )

    findings = rollout.harvest_repository(repository)

    assert {finding["path"] for finding in findings} == {"kept.md"}, (
        "harvest included a repository-local excluded fixture"
    )


def test_write_config_is_atomic_and_matches_renderer(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Generated tracked output is validated and atomically installed."""
    source = tmp_path / "base.toml"
    output = tmp_path / "typos.toml"
    source.write_text(dictionary_text(), encoding="utf-8")
    dictionary = rollout.load_dictionary(source)

    rollout.write_config(output, dictionary)

    assert output.read_text(encoding="utf-8") == rollout.render_typos_config(dictionary), (
        "written config differs from rendered config"
    )
    assert list(tmp_path.glob(".typos.toml.*")) == [], "atomic-write temporary file remains"


@pytest.mark.parametrize("failure_stage", ["write", "close", "replace"])
def test_atomic_write_cleans_temporary_file_after_failure(
    rollout: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_stage: str,
) -> None:
    """Write, close, and replacement failures all remove the temporary file."""
    temporary = tmp_path / ".typos.toml.failure"
    temporary.touch()

    class FailingStream:
        """Model a named temporary stream with one selected failure."""

        name = str(temporary)

        def __enter__(self) -> "FailingStream":
            """Enter the fake stream context."""
            return self

        def write(self, content: bytes) -> None:
            """Write bytes unless this case models a write failure."""
            if failure_stage == "write":
                raise OSError("write failure")
            temporary.write_bytes(content)

        def __exit__(self, *_args: object) -> None:
            """Close unless this case models a close failure."""
            if failure_stage == "close":
                raise OSError("close failure")

    monkeypatch.setattr(
        rollout.tempfile,
        "NamedTemporaryFile",
        lambda **_kwargs: FailingStream(),
    )
    if failure_stage == "replace":

        def fail_replace(_path: Path, _destination: Path) -> None:
            """Model an atomic replacement failure."""
            raise OSError("replace failure")

        monkeypatch.setattr(rollout.Path, "replace", fail_replace)

    with pytest.raises(OSError, match=f"{failure_stage} failure"):
        rollout._atomic_write(tmp_path / "typos.toml", b"content")

    assert not temporary.exists(), f"temporary file survived {failure_stage} failure"


def test_committed_config_matches_shared_dictionary(
    rollout: types.ModuleType,
) -> None:
    """The committed config cannot drift from the curated shared dictionary."""
    expected = rollout.render_typos_config(
        rollout.merge_dictionaries(
            rollout.load_dictionary(SHARED_DICTIONARY_PATH),
            rollout.load_dictionary(LOCAL_DICTIONARY_PATH),
        )
    )

    assert COMMITTED_CONFIG_PATH.read_text(encoding="utf-8") == expected, (
        "committed config has drifted from shared and local dictionaries"
    )


def test_shared_dictionary_preserves_generic_technical_terms(
    rollout: types.ModuleType,
) -> None:
    """Generic UI, CI, and Oxford terms remain valid across consumers."""
    mappings = rollout.generate_word_mappings(
        rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    )

    assert mappings["oxidized"] == "oxidized", "Oxford spelling was not accepted"
    assert mappings["oxidised"] == "oxidized", "plain-British spelling was not corrected"
    assert mappings["dialogs"] == "dialogs", "UI terminology was not accepted"
    assert mappings["artifacts"] == "artifacts", "CI terminology was not accepted"
    assert mappings["organizational"] == "organizational", (
        "Oxford adjective was not accepted"
    )
    assert mappings["organisational"] == "organizational", (
        "plain-British adjective was not corrected"
    )
    assert mappings["italicized"] == "italicized", "Oxford spelling was not accepted"
    assert mappings["italicised"] == "italicized", (
        "plain-British spelling was not corrected"
    )
    assert mappings["underutilize"] == "underutilize", "Oxford spelling was not accepted"
    assert mappings["underutilise"] == "underutilize", (
        "plain-British spelling was not corrected"
    )
    assert mappings["recognizably"] == "recognizably", (
        "Oxford adverb was not accepted"
    )
    assert mappings["recognisably"] == "recognizably", (
        "plain-British adverb was not corrected"
    )
