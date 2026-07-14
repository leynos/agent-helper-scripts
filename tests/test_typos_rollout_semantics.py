"""Security contracts for authority and local spelling policy."""

from email.message import Message
import json
from pathlib import Path
import re
import types
from urllib.error import HTTPError

import pytest

from typos_rollout_test_support import (
    LOCAL_DICTIONARY_PATH,
    dictionary_text,
)

AUTHORITY_SOURCE = "https://example.test/base"


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
        pytest.param(("[A-Za-z]+",), (), id="prose-word-substring-ignore"),
        pytest.param(("ordinary",), (), id="literal-prose-substring-ignore"),
        pytest.param((), ("*",), id="all-files-exclusion"),
        pytest.param((), ("**/*",), id="universal-exclusion"),
        pytest.param((), ("*.md",), id="top-level-markdown-exclusion"),
        pytest.param((), ("**.md",), id="path-match-universal-exclusion"),
        pytest.param((), ("**/*.md",), id="recursive-markdown-exclusion"),
        pytest.param((), (" ./**/*.MD ",), id="normalized-markdown-exclusion"),
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


@pytest.mark.parametrize(
    ("pattern", "message"),
    [
        pytest.param("[", "invalid", id="malformed"),
        pytest.param(r"(a)\1", "unsafe repetition", id="backreference"),
        pytest.param("(a+)+$", "unsafe repetition", id="nested-repetition"),
        pytest.param("(a|aa)+$", "unsafe repetition", id="repeated-alternation"),
        pytest.param("a*a*$", "unsafe repetition", id="adjacent-repetitions"),
        pytest.param("(a{,3})+$", "unsafe repetition", id="upper-bound-nested"),
        pytest.param("a{,2}a{,3}$", "unsafe repetition", id="upper-bound-adjacent"),
    ],
)
def test_authority_rejects_unsafe_ignore_patterns(
    rollout: types.ModuleType,
    tmp_path: Path,
    pattern: str,
    message: str,
) -> None:
    """Every authority regex must compile with bounded matching complexity."""
    authority = tmp_path / "base.toml"
    authority.write_text(
        dictionary_text().replace(
            "ignore = []",
            f"ignore = [{json.dumps(pattern)}]",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message) as raised:
        rollout.load_dictionary(authority)

    if pattern == "[":
        assert isinstance(raised.value.__cause__, re.error), (
            "malformed regex did not preserve its parser failure as the cause"
        )


def test_sparse_overlay_validates_regex_and_accepts_separated_repetitions(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Sparse overlays retain narrow separated repetitions and reject hazards."""
    overlay = tmp_path / "typos.local.toml"
    safe_pattern = r"GitHub\s+Flav" + r"ored\s+Markdown"
    overlay.write_text(
        "schema = 1\n\n[patterns]\n"
        f"ignore = [{json.dumps(safe_pattern)}]\n",
        encoding="utf-8",
    )

    assert rollout.load_dictionary(
        overlay,
        local_overlay=True,
    ).ignore_patterns == (safe_pattern,)

    overlay.write_text(
        "schema = 1\n\n[patterns]\nignore = ['(a+)+$']\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsafe repetition"):
        rollout.load_dictionary(overlay, local_overlay=True)


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
        AUTHORITY_SOURCE,
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
    metadata = tmp_path / "cache.json"
    metadata.write_text(
        json.dumps({"source": AUTHORITY_SOURCE}),
        encoding="utf-8",
    )
    not_modified = _not_modified_error()

    result = rollout.refresh_base(
        AUTHORITY_SOURCE,
        cache,
        rollout.RefreshOptions(
            metadata=metadata,
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(not_modified),
        ),
    )

    assert result.status == "current", "HTTP 304 did not preserve a valid cache"
    assert result.cache == cache, "HTTP 304 returned a different cache path"


@pytest.mark.parametrize(
    "case",
    [
        pytest.param((False, None, "missing cache"), id="missing-cache"),
        pytest.param(
            (True, "https://other.example.test/base", "another source's cache"),
            id="different-source",
        ),
        pytest.param((True, None, "unscoped cache"), id="missing-source-metadata"),
    ],
)
def test_http_304_rejects_invalid_cache_scope(
    rollout: types.ModuleType,
    tmp_path: Path,
    case: tuple[bool, str | None, str],
) -> None:
    """HTTP 304 cannot validate a missing cache or one outside its source."""
    has_cache, metadata_source, diagnostic = case
    cache = tmp_path / "cache.toml"
    if has_cache:
        cache.write_text(dictionary_text(), encoding="utf-8")
    metadata = tmp_path / "cache.json"
    if metadata_source is not None:
        metadata.write_text(
            json.dumps({"source": metadata_source}),
            encoding="utf-8",
        )
    not_modified = _not_modified_error()

    with pytest.raises(HTTPError) as raised:
        rollout.refresh_base(
            AUTHORITY_SOURCE,
            cache,
            rollout.RefreshOptions(
                metadata=metadata,
                opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    not_modified
                ),
            ),
        )

    assert raised.value is not_modified, f"HTTP 304 accepted {diagnostic}"
