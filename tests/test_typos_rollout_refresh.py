"""Tests for refreshing the shared en-GB-oxendict dictionary cache."""

import json
import os
from pathlib import Path
import tomllib
import types

import pytest

from typos_rollout_test_support import ValidResponse, dictionary_text


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
    options = rollout.RefreshOptions(metadata=metadata)

    first = rollout.refresh_base(source, cache, options)
    cache.write_text(dictionary_text(stem="local"), encoding="utf-8")
    os.utime(cache, ns=(2_000_000_000, 2_000_000_000))
    unchanged = rollout.refresh_base(source, cache, options)
    source.write_text(dictionary_text(stem="newer"), encoding="utf-8")
    os.utime(source, ns=(3_000_000_000, 3_000_000_000))
    refreshed = rollout.refresh_base(source, cache, options)

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
    options = rollout.RefreshOptions(metadata=metadata)
    rollout.refresh_base(first_source, cache, options)

    result = rollout.refresh_base(second_source, cache, options)

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
            rollout.RefreshOptions(metadata=metadata, offline=True),
        )

    cache.write_text(dictionary_text(), encoding="utf-8")
    result = rollout.refresh_base(
        "https://example.invalid/base.toml",
        cache,
        rollout.RefreshOptions(metadata=metadata, offline=True),
    )

    assert result.status == "offline-cache", "offline mode did not reuse the valid cache"


def test_refresh_options_are_immutable(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Refresh policy cannot change after it is bound to an operation."""
    options = rollout.RefreshOptions(metadata=tmp_path / ".typos-base.json")

    with pytest.raises(AttributeError):
        setattr(options, "offline", True)

    assert options.offline is False, "failed mutation changed refresh policy"


def test_http_refresh_uses_saved_etag(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Remote refreshes use conditional metadata on subsequent requests."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    requests: list[object] = []

    class Response:
        """Minimal context-managed HTTP response for the refresh boundary."""

        status = 200
        headers = {
            "ETag": '"estate-v1"',
            "Last-Modified": "Fri, 10 Jul 2026 08:00:00 GMT",
        }

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
        rollout.RefreshOptions(metadata=metadata, opener=opener),
    )
    second = rollout.refresh_base(
        "https://example.test/base.toml",
        cache,
        rollout.RefreshOptions(metadata=metadata, opener=opener),
    )

    assert requests[1].get_header("If-none-match") == '"estate-v1"', (
        "subsequent request omitted the saved ETag"
    )
    assert json.loads(metadata.read_text())["etag"] == '"estate-v1"', (
        "refresh metadata omitted the response ETag"
    )
    assert first.status == "refreshed", "first HTTP response did not populate the cache"
    assert second.status == "current", "unchanged HTTP response refreshed the cache"


def test_http_refresh_drops_validators_for_a_different_source(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Conditional metadata is scoped to the source that supplied it."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    requests: list[object] = []

    class Response:
        """Minimal context-managed response from the replacement source."""

        status = 200

        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def read(self) -> bytes:
            """Return a valid replacement dictionary."""
            return dictionary_text(stem="replacement").encode()

        def __enter__(self) -> "Response":
            """Enter the fake response context."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Leave the fake response context."""

    def opener(request: object, *, timeout: float) -> Response:
        """Capture the request sent to the replacement source."""
        del timeout
        requests.append(request)
        return Response()

    cache.write_text(dictionary_text(stem="original"), encoding="utf-8")
    metadata.write_text(
        json.dumps(
            {
                "etag": '"original-v1"',
                "last_modified": "Fri, 10 Jul 2026 08:00:00 GMT",
                "source": "https://example.test/original.toml",
            }
        ),
        encoding="utf-8",
    )

    result = rollout.refresh_base(
        "https://example.test/replacement.toml",
        cache,
        rollout.RefreshOptions(metadata=metadata, opener=opener),
    )

    assert requests[0].get_header("If-none-match") is None, (
        "replacement source inherited the previous source's ETag"
    )
    assert requests[0].get_header("If-modified-since") is None, (
        "replacement source inherited the previous source's modification time"
    )
    assert result.status == "refreshed", "replacement source did not refresh the cache"
    assert rollout.load_dictionary(cache).stems == ("replacement",), (
        "replacement dictionary was not persisted"
    )
    assert json.loads(metadata.read_text(encoding="utf-8"))["source"] == (
        "https://example.test/replacement.toml"
    ), "replacement source metadata was not persisted"


def test_changed_etag_is_authoritative_over_unchanged_date(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """A changed ETag refreshes even when Last-Modified is unchanged."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"
    source = "https://example.test/base.toml"
    modified = "Fri, 10 Jul 2026 08:00:00 GMT"
    cache.write_text(dictionary_text(stem="original"), encoding="utf-8")
    metadata.write_text(
        json.dumps(
            {
                "etag": '"estate-v1"',
                "last_modified": modified,
                "source": source,
            }
        ),
        encoding="utf-8",
    )
    response = ValidResponse(
        stem="replacement",
        headers={"ETag": '"estate-v2"', "Last-Modified": modified},
    )

    result = rollout.refresh_base(
        source,
        cache,
        rollout.RefreshOptions(
            metadata=metadata,
            opener=lambda *_args, **_kwargs: response,
        ),
    )

    assert result.status == "refreshed", "changed ETag did not refresh the cache"
    assert rollout.load_dictionary(cache).stems == ("replacement",), (
        "changed ETag response was discarded by the date validator"
    )


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
            rollout.RefreshOptions(
                metadata=tmp_path / ".typos-base.json",
                opener=lambda *_args, **_kwargs: InvalidResponse(),
            ),
        )

    assert cache.read_bytes() == original, "invalid download replaced the valid cache"
