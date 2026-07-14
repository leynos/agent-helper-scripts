"""Behavioural tests for the shared en-GB-oxendict rollout helper."""

from pathlib import Path
import re
import subprocess
import tomllib
import types

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

PLAIN_BRITISH_ORGANIZE = "organi" + "se"
PLAIN_BRITISH_ORGANIZATIONS = "organi" + "sations"
PLAIN_BRITISH_ORGANIZING = "organi" + "sing"
PLAIN_BRITISH_OXIDIZED = "oxidi" + "sed"
PLAIN_BRITISH_ORGANIZATIONAL = "organi" + "sational"
PLAIN_BRITISH_ITALICIZED = "italici" + "sed"
PLAIN_BRITISH_UNDERUTILIZE = "underutili" + "se"
PLAIN_BRITISH_RECOGNIZABLY = "recogni" + "sably"
AMERICAN_ARTEFACT = "arti" + "fact"
AMERICAN_ARTEFACTS = AMERICAN_ARTEFACT + "s"
HYPHENATED_HANDWRITTEN = "hand" + "-written"


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
    assert mappings[PLAIN_BRITISH_ORGANIZE] == "organize", (
        "plain-British form was not corrected"
    )
    assert mappings["organizations"] == "organizations", "Oxford plural was not accepted"
    assert mappings[PLAIN_BRITISH_ORGANIZATIONS] == "organizations", (
        "plain-British plural was not corrected"
    )


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

    conflict_word = "t" + "eh"
    with pytest.raises(
        ValueError,
        match=rf"conflicting correction for '{conflict_word}'",
    ):
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
    assert parsed["default"]["extend-words"][PLAIN_BRITISH_ORGANIZE] == "organize", (
        "generated config omitted the Oxford correction"
    )
    assert first.endswith("\n"), "generated config lacks a trailing newline"
    assert not first.endswith("\n\n"), "generated config has multiple trailing newlines"


def test_harvest_finds_both_oxford_and_plain_british_forms(
    rollout: types.ModuleType,
) -> None:
    """Harvesting retains evidence for both sides of an Oxford mapping."""
    forms = rollout.harvest_oxford_forms(
        f"We organize releases after {PLAIN_BRITISH_ORGANIZING} fixtures and "
        "analyse results."
    )

    assert forms == (PLAIN_BRITISH_ORGANIZING, "organize"), (
        "harvest omitted or added Oxford candidates"
    )


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
        f"The fixture deliberately says {PLAIN_BRITISH_ORGANIZE}.\n",
        encoding="utf-8",
    )
    (repository / "kept.md").write_text(
        "The guide says organize.\n",
        encoding="utf-8",
    )
    (repository / "typos.local.toml").write_text(
        dictionary_text().replace(
            '[files]\nexclude = [".git"]', '[files]\nexclude = ["fixture.md"]'
        ),
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


def test_harvest_repository_propagates_file_read_failures(
    rollout: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Filesystem failures fail harvesting instead of hiding incomplete evidence."""
    repository = tmp_path / "repository"
    repository.mkdir()
    target = repository / "README.md"
    target.write_text("We organize releases.\n", encoding="utf-8")
    git = require_executable("git")
    subprocess.run([git, "init", "-q", repository], check=True, timeout=30)
    subprocess.run(
        [git, "-C", repository, "add", "README.md"],
        check=True,
        timeout=30,
    )
    read_text = Path.read_text

    def deny_target(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        """Deny only the tracked fixture while preserving authority reads."""
        if path == target:
            raise PermissionError("tracked fixture is unreadable")
        return read_text(path, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "read_text", deny_target)

    with pytest.raises(PermissionError, match="tracked fixture is unreadable"):
        rollout.harvest_repository(repository)


def test_harvest_repository_skips_non_utf8_files(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Binary tracked content remains outside Oxford-form harvesting."""
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "binary.dat").write_bytes(b"\xff")
    git = require_executable("git")
    subprocess.run([git, "init", "-q", repository], check=True, timeout=30)
    subprocess.run(
        [git, "-C", repository, "add", "binary.dat"],
        check=True,
        timeout=30,
    )

    assert rollout.harvest_repository(repository) == ()


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
            rollout.load_dictionary(LOCAL_DICTIONARY_PATH, local_overlay=True),
        )
    )

    assert COMMITTED_CONFIG_PATH.read_text(encoding="utf-8") == expected, (
        "committed config has drifted from shared and local dictionaries"
    )


def test_shared_dictionary_preserves_generic_terms_without_american_artefacts(
    rollout: types.ModuleType,
) -> None:
    """Generic UI and Oxford terms must not admit American artefact spellings."""
    mappings = rollout.generate_word_mappings(
        rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    )

    assert mappings["oxidized"] == "oxidized", "Oxford spelling was not accepted"
    assert mappings[PLAIN_BRITISH_OXIDIZED] == "oxidized", (
        "plain-British spelling was not corrected"
    )
    assert mappings["dialogs"] == "dialogs", "UI terminology was not accepted"
    assert AMERICAN_ARTEFACT not in mappings, (
        "American artefact spelling was accepted"
    )
    assert AMERICAN_ARTEFACTS not in mappings, (
        "American artefact plural was accepted"
    )
    assert mappings["organizational"] == "organizational", (
        "Oxford adjective was not accepted"
    )
    assert mappings[PLAIN_BRITISH_ORGANIZATIONAL] == "organizational", (
        "plain-British adjective was not corrected"
    )
    assert mappings["italicized"] == "italicized", "Oxford spelling was not accepted"
    assert mappings[PLAIN_BRITISH_ITALICIZED] == "italicized", (
        "plain-British spelling was not corrected"
    )
    assert mappings["underutilize"] == "underutilize", "Oxford spelling was not accepted"
    assert mappings[PLAIN_BRITISH_UNDERUTILIZE] == "underutilize", (
        "plain-British spelling was not corrected"
    )
    assert mappings["recognizably"] == "recognizably", (
        "Oxford adverb was not accepted"
    )
    assert mappings[PLAIN_BRITISH_RECOGNIZABLY] == "recognizably", (
        "plain-British adverb was not corrected"
    )


def test_shared_dictionary_accepts_aso_formal_acronym(
    rollout: types.ModuleType,
) -> None:
    """The formal ASO acronym remains an exact accepted identity mapping."""
    mappings = rollout.generate_word_mappings(
        rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    )
    generated_words = tomllib.loads(COMMITTED_CONFIG_PATH.read_text(encoding="utf-8"))[
        "default"
    ]["extend-words"]

    assert mappings["ASO"] == "ASO", "shared policy did not accept the ASO acronym"
    assert generated_words["ASO"] == "ASO", "generated config omitted the ASO acronym"


def test_shared_dictionary_canonicalizes_handwritten(
    rollout: types.ModuleType,
) -> None:
    """The closed compound is accepted and its hyphenated form is prohibited."""
    dictionary = rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    mappings = rollout.generate_word_mappings(dictionary)

    assert mappings["handwritten"] == "handwritten", (
        "closed handwritten compound was not accepted"
    )
    assert HYPHENATED_HANDWRITTEN not in mappings, (
        "ineffective hyphenated word mapping was rendered for Typos"
    )
    assert dict(dictionary.phrase_corrections)[HYPHENATED_HANDWRITTEN] == "handwritten", (
        "hyphenated form was not assigned to the phrase-policy checker"
    )


def test_shared_dictionary_protects_exact_rust_analyzer_name(
    rollout: types.ModuleType,
) -> None:
    """Only the hyphenated formal rust-analyzer tool name is ignored."""
    pattern = r"\brust-analyzer\b"
    dictionary = rollout.load_dictionary(SHARED_DICTIONARY_PATH)
    generated = tomllib.loads(rollout.render_typos_config(dictionary))["default"]
    generated_patterns = generated["extend-ignore-re"]
    generated_words = generated["extend-words"]
    matcher = re.compile(pattern)

    assert pattern in dictionary.ignore_patterns, "shared policy omitted rust-analyzer"
    assert pattern in generated_patterns, "generated config omitted rust-analyzer"
    assert "analyzer" not in generated_words, "shared config accepted ordinary analyzer"
    assert "analyser" not in generated_words, "shared config accepted ordinary analyser"
    assert matcher.fullmatch("rust-analyzer"), "formal tool name was not matched"
    assert not matcher.search("analyzer"), "ordinary analyzer prose was ignored"
    assert not matcher.search("analyser"), "ordinary analyser prose was ignored"
    assert not matcher.search("rust analyzer"), "unhyphenated prose was ignored"
