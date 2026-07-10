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

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "typos_rollout.py"
SHARED_DICTIONARY_PATH = REPOSITORY_ROOT / "data" / "typos-oxendict-base.toml"
LOCAL_DICTIONARY_PATH = REPOSITORY_ROOT / "typos.local.toml"
COMMITTED_CONFIG_PATH = REPOSITORY_ROOT / "typos.toml"


@pytest.fixture(name="rollout", scope="module")
def rollout_fixture() -> types.ModuleType:
    """Load the executable script as a module for focused unit tests."""
    spec = importlib.util.spec_from_file_location("typos_rollout", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
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

    assert mappings["organize"] == "organize"
    assert mappings["organise"] == "organize"
    assert mappings["organizations"] == "organizations"
    assert mappings["organisations"] == "organizations"


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

    assert first == second
    assert parsed["default"]["locale"] == "en-gb"
    assert parsed["default"]["extend-words"]["organise"] == "organize"
    assert first.endswith("\n") and not first.endswith("\n\n")


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

    assert first.status == "refreshed"
    assert unchanged.status == "current"
    assert refreshed.status == "refreshed"
    assert rollout.load_dictionary(cache).stems == ("newer",)


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

    assert result.status == "offline-cache"


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

    assert requests[1].get_header("If-none-match") == '"estate-v1"'
    assert json.loads(metadata.read_text())["etag"] == '"estate-v1"'
    assert first.status == "refreshed"
    assert second.status == "current"


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

    assert cache.read_bytes() == original


def test_harvest_finds_both_oxford_and_plain_british_forms(
    rollout: types.ModuleType,
) -> None:
    """Harvesting retains evidence for both sides of an Oxford mapping."""
    forms = rollout.harvest_oxford_forms(
        "We organize releases after organising fixtures and analyse results."
    )

    assert forms == ("organising", "organize")


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

    assert output.read_text(encoding="utf-8") == rollout.render_typos_config(dictionary)
    assert list(tmp_path.glob(".typos.toml.*")) == []


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

    assert COMMITTED_CONFIG_PATH.read_text(encoding="utf-8") == expected


def test_makefile_spelling_gate_uses_pinned_typos() -> None:
    """The CI entrypoint generates config and runs a pinned typos binary."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "ci: check-fmt lint typecheck test spelling" in makefile
    assert re.search(r"^TYPOS_VERSION\s*\?=\s*\S+", makefile, re.MULTILINE)
    assert "scripts/typos_rollout.py generate" in makefile
    assert "typos@$(TYPOS_VERSION)" in makefile


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
    assert match is not None
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

    assert corrections.get("organise") == ["organize"]
    assert corrections.get("color") == ["colour"]
    assert "analyse" not in corrections
