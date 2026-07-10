"""Behavioural tests for the shared en-GB-oxendict rollout helper."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import types
import typing as typ

import pytest
from hypothesis import given
from hypothesis import strategies as st

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "typos_rollout.py"
SHARED_DICTIONARY_PATH = REPOSITORY_ROOT / "data" / "typos-oxendict-base.toml"
LOCAL_DICTIONARY_PATH = REPOSITORY_ROOT / "typos.local.toml"
COMMITTED_CONFIG_PATH = REPOSITORY_ROOT / "typos.toml"


@pytest.fixture(name="rollout", scope="module")
def rollout_fixture() -> types.ModuleType:
    """Load the executable script as a module for focused unit tests."""
    spec = importlib.util.spec_from_file_location("typos_rollout", SCRIPT_PATH)
    assert spec is not None, "could not create a module specification"
    assert spec.loader is not None, "module specification has no loader"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dictionary_text(*, stem: str = "organ", accepted: str = "oxendict") -> str:
    """Return a minimal valid shared dictionary document."""
    return (
        'schema = 1\n\n[oxford]\n'
        f'stems = ["{stem}"]\n\n'
        f'[words]\naccepted = ["{accepted}"]\n\n'
        '[words.corrections]\n\n[patterns]\nignore = []\n\n'
        '[files]\nexclude = [".git"]\n'
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


def test_refresh_base_copies_only_newer_local_source(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """A local shared source replaces the untracked cache only when newer."""
    source = tmp_path / "shared.toml"
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    source.write_text(dictionary_text(stem="organ"), encoding="utf-8")
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))

    first = rollout.refresh_base(source, cache, metadata=metadata)
    cache.write_text(dictionary_text(stem="local"), encoding="utf-8")
    os.utime(cache, ns=(2_000_000_000, 2_000_000_000))
    unchanged = rollout.refresh_base(source, cache, metadata=metadata)
    source.write_text(dictionary_text(stem="newer"), encoding="utf-8")
    os.utime(source, ns=(3_000_000_000, 3_000_000_000))
    refreshed = rollout.refresh_base(source, cache, metadata=metadata)

    assert first.status == "refreshed", "first local refresh did not populate the cache"
    assert unchanged.status == "current", "older local source replaced a newer cache"
    assert refreshed.status == "refreshed", "newer local source did not refresh the cache"
    assert rollout.load_dictionary(cache).stems == ("newer",), (
        "cache does not contain the newest local source"
    )


def test_local_refresh_replaces_cache_from_different_source(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """An explicit local authority replaces a cache populated elsewhere."""
    first_source = tmp_path / "first.toml"
    second_source = tmp_path / "second.toml"
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    first_source.write_text(dictionary_text(stem="first"), encoding="utf-8")
    second_source.write_text(dictionary_text(stem="second"), encoding="utf-8")
    os.utime(first_source, ns=(3_000_000_000, 3_000_000_000))
    os.utime(second_source, ns=(1_000_000_000, 1_000_000_000))
    rollout.refresh_base(first_source, cache, metadata=metadata)

    result = rollout.refresh_base(second_source, cache, metadata=metadata)

    assert result.status == "refreshed", "different explicit source reused stale cache"
    assert rollout.load_dictionary(cache).stems == ("second",), (
        "cache did not switch to the explicit authoritative source"
    )


def test_refresh_base_offline_requires_valid_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Offline generation reuses a valid cache and rejects a missing one."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"

    with pytest.raises(FileNotFoundError, match="no cached shared dictionary"):
        rollout.refresh_base(
            "https://example.invalid/base.toml",
            cache,
            metadata=metadata,
            offline=True,
        )

    cache.write_text(dictionary_text(), encoding="utf-8")
    result = rollout.refresh_base(
        "https://example.invalid/base.toml",
        cache,
        metadata=metadata,
        offline=True,
    )

    assert result.status == "offline-cache", "offline mode did not reuse the valid cache"


def test_http_refresh_uses_saved_etag(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Remote refreshes use conditional metadata on subsequent requests."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    requests = []

    class Response:
        """Minimal context-managed HTTP response for the refresh boundary."""

        status = 200
        headers = {"ETag": '"estate-v1"', "Last-Modified": "Fri, 10 Jul 2026 08:00:00 GMT"}

        def read(self) -> bytes:
            """Return valid shared dictionary bytes."""
            return dictionary_text().encode()

        def __enter__(self) -> "Response":
            """Enter the fake response context."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the fake response context."""

    def opener(request: object, *, timeout: float) -> Response:
        """Capture the request passed to the HTTP boundary."""
        del timeout
        requests.append(request)
        return Response()

    first = rollout.refresh_base(
        "https://example.test/base.toml",
        cache,
        metadata=metadata,
        opener=opener,
    )
    second = rollout.refresh_base(
        "https://example.test/base.toml",
        cache,
        metadata=metadata,
        opener=opener,
    )

    assert requests[1].get_header("If-none-match") == '"estate-v1"', (
        "subsequent request omitted the saved ETag"
    )
    assert json.loads(metadata.read_text())["etag"] == '"estate-v1"', (
        "refresh metadata omitted the response ETag"
    )
    assert first.status == "refreshed", "first HTTP response did not populate the cache"
    assert second.status == "current", "unchanged HTTP response refreshed the cache"


def test_invalid_download_does_not_replace_valid_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Downloaded data is validated before the cache is replaced."""
    cache = tmp_path / ".typos-base.toml"
    cache.write_text(dictionary_text(), encoding="utf-8")
    original = cache.read_bytes()

    class InvalidResponse:
        """Return malformed TOML from the HTTP boundary."""

        status = 200
        headers: dict[str, str] = {}

        def read(self) -> bytes:
            """Return malformed bytes."""
            return b"not = [valid"

        def __enter__(self) -> "InvalidResponse":
            """Enter the fake response context."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the fake response context."""

    with pytest.raises(tomllib.TOMLDecodeError):
        rollout.refresh_base(
            "https://example.test/base.toml",
            cache,
            metadata=tmp_path / ".typos-base.json",
            opener=lambda *_args, **_kwargs: InvalidResponse(),
        )

    assert cache.read_bytes() == original, "invalid download replaced the valid cache"


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
    subprocess.run(["git", "init", "-q", repository], check=True)
    subprocess.run(
        ["git", "-C", repository, "add", "fixture.md", "kept.md", "typos.local.toml"],
        check=True,
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
    assert "typos@$(TYPOS_VERSION)" in makefile, "spelling target bypasses the version pin"
    assert "--config typos.toml --force-exclude ." in makefile, (
        "spelling target does not apply generated configuration and exclusions"
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
            rollout.load_dictionary(LOCAL_DICTIONARY_PATH),
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

    assert corrections.get("organise") == ["organize"], "Oxford correction was not enforced"
    assert corrections.get("color") == ["colour"], "British colour spelling was not enforced"
    assert "analyse" not in corrections, "valid -yse spelling was rejected"
