"""Security contracts for authority and local spelling policy."""

from email.message import Message
from pathlib import Path
import types
from urllib.error import HTTPError

import pytest

from typos_rollout_test_support import (
    LOCAL_DICTIONARY_PATH,
    dictionary_text,
)


@pytest.mark.parametrize("schema", ["true", "1.0"])
def test_authority_requires_integer_schema(
    rollout: types.ModuleType,
    tmp_path: Path,
    schema: str,
) -> None:
    """Boolean and floating-point schemas cannot validate as version one."""
    authority = tmp_path / "base.toml"
    authority.write_text(
        dictionary_text().replace("schema = 1", f"schema = {schema}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported dictionary schema"):
        rollout.load_dictionary(authority)


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ("[phrases.corrections]\n\n", "missing required table 'phrases'"),
        ('exclude = [".git"]\n', "missing required field files.exclude"),
    ],
)
def test_authority_requires_complete_policy(
    rollout: types.ModuleType,
    tmp_path: Path,
    fragment: str,
    message: str,
) -> None:
    """Every authority table and expected field is mandatory."""
    authority = tmp_path / "base.toml"
    authority.write_text(dictionary_text().replace(fragment, ""), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        rollout.load_dictionary(authority)


def test_explicit_sparse_local_overlay_remains_valid(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Only explicit local loads may omit unrelated policy tables."""
    overlay = tmp_path / "typos.local.toml"
    overlay.write_text(
        'schema = 1\n\n[words]\naccepted = ["Foundation"]\n',
        encoding="utf-8",
    )

    parsed = rollout.load_dictionary(overlay, local_overlay=True)

    assert parsed.accepted == ("Foundation",), "sparse local vocabulary was lost"
    assert parsed.stems == (), "sparse local load invented authority policy"


@pytest.mark.parametrize(
    ("ignore_patterns", "excluded_files"),
    [
        pytest.param((".*",), (), id="empty-matching-ignore"),
        pytest.param((".+",), (), id="generic-prose-ignore"),
        pytest.param((), ("*",), id="all-files-exclusion"),
        pytest.param((), ("**/*",), id="universal-exclusion"),
        pytest.param((), ("*.md",), id="top-level-markdown-exclusion"),
        pytest.param((), ("**/*.md",), id="recursive-markdown-exclusion"),
    ],
)
def test_merge_rejects_broad_local_exceptions(
    rollout: types.ModuleType,
    ignore_patterns: tuple[str, ...],
    excluded_files: tuple[str, ...],
) -> None:
    """Local exceptions cannot disable estate policy broadly."""
    local = rollout.Dictionary(
        ignore_patterns=ignore_patterns,
        excluded_files=excluded_files,
    )

    with pytest.raises(ValueError, match="too broad"):
        rollout.merge_dictionaries(rollout.Dictionary(), local)


def test_merge_accepts_existing_local_exceptions(
    rollout: types.ModuleType,
) -> None:
    """Existing exact identifiers and fixture paths remain narrow exceptions."""
    local = rollout.load_dictionary(LOCAL_DICTIONARY_PATH, local_overlay=True)

    merged = rollout.merge_dictionaries(rollout.Dictionary(), local)

    assert merged.ignore_patterns == local.ignore_patterns, (
        "narrow local ignore patterns changed during merge"
    )
    assert merged.excluded_files == local.excluded_files, (
        "narrow local file exclusions changed during merge"
    )


def _not_modified_error() -> HTTPError:
    """Build the production representation of an HTTP 304 response."""
    return HTTPError(
        "https://example.test/base",
        304,
        "not modified",
        Message(),
        None,
    )


def test_http_304_requires_valid_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """The HTTPError 304 path cannot accept a missing cache."""
    not_modified = _not_modified_error()

    with pytest.raises(HTTPError) as raised:
        rollout.refresh_base(
            "https://example.test/base",
            tmp_path / "cache.toml",
            rollout.RefreshOptions(
                metadata=tmp_path / "cache.json",
                opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(not_modified),
            ),
        )

    assert raised.value is not_modified, "HTTP 304 accepted a missing cache"


def test_http_304_preserves_valid_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """The HTTPError 304 path reports a validated cache as current."""
    cache = tmp_path / "cache.toml"
    cache.write_text(dictionary_text(), encoding="utf-8")
    not_modified = _not_modified_error()

    result = rollout.refresh_base(
        "https://example.test/base",
        cache,
        rollout.RefreshOptions(
            metadata=tmp_path / "cache.json",
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(not_modified),
        ),
    )

    assert result.status == "current", "HTTP 304 did not preserve a valid cache"
    assert result.cache == cache, "HTTP 304 returned a different cache path"
