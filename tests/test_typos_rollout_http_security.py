"""Security and failure-boundary tests for remote dictionary refreshes."""

from pathlib import Path
import json
import types
from urllib.error import HTTPError, URLError

import pytest

from typos_rollout_test_support import ValidResponse, dictionary_text


def test_http_status_propagates_even_with_a_valid_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """An HTTP status is never converted into a stale-cache success."""
    cache = tmp_path / ".typos-base.toml"
    cache.write_text(dictionary_text(), encoding="utf-8")
    error = HTTPError(
        "https://example.test/missing.toml",
        404,
        "Not Found",
        hdrs=None,
        fp=None,
    )

    def missing(*_args: object, **_kwargs: object) -> ValidResponse:
        """Raise the authority's HTTP response."""
        raise error

    with pytest.raises(HTTPError) as raised:
        rollout.refresh_base(
            "https://example.test/missing.toml",
            cache,
            rollout.RefreshOptions(
                metadata=tmp_path / ".typos-base.json",
                opener=missing,
            ),
        )

    assert raised.value is error, "HTTP status was replaced by a fallback result"


def test_persistence_error_propagates_even_with_a_valid_cache(
    rollout: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A local write failure is never classified as network unavailability."""
    cache = tmp_path / ".typos-base.toml"
    cache.write_text(dictionary_text(stem="original"), encoding="utf-8")

    def denied(*_args: object, **_kwargs: object) -> None:
        """Model denied persistence at the atomic-write boundary."""
        raise PermissionError("cache is read-only")

    monkeypatch.setattr(rollout, "_atomic_write", denied)

    with pytest.raises(PermissionError, match="cache is read-only"):
        rollout.refresh_base(
            "https://example.test/base.toml",
            cache,
            rollout.RefreshOptions(
                metadata=tmp_path / ".typos-base.json",
                opener=lambda *_args, **_kwargs: ValidResponse(stem="replacement"),
            ),
        )


def test_connectivity_failure_uses_only_a_valid_stale_cache(
    rollout: types.ModuleType,
    tmp_path: Path,
) -> None:
    """Connectivity loss raises its domain error unless a valid cache exists."""
    cache = tmp_path / ".typos-base.toml"
    metadata = tmp_path / ".typos-base.json"

    def unavailable(*_args: object, **_kwargs: object) -> ValidResponse:
        """Model a network-unavailable authority."""
        raise URLError("offline")

    with pytest.raises(rollout.NetworkUnavailableError) as raised:
        rollout.refresh_base(
            "https://example.test/base.toml",
            cache,
            rollout.RefreshOptions(metadata=metadata, opener=unavailable),
        )
    assert isinstance(raised.value.__context__, URLError), (
        "connectivity error did not retain the URL failure context"
    )

    cache.write_text(dictionary_text(), encoding="utf-8")
    metadata.write_text(
        json.dumps({"source": "https://example.test/base.toml"}),
        encoding="utf-8",
    )
    result = rollout.refresh_base(
        "https://example.test/base.toml",
        cache,
        rollout.RefreshOptions(metadata=metadata, opener=unavailable),
    )

    assert result.status == "stale-cache", "valid stale cache was not reused offline"

    with pytest.raises(rollout.NetworkUnavailableError):
        rollout.refresh_base(
            "https://example.test/replacement.toml",
            cache,
            rollout.RefreshOptions(metadata=metadata, opener=unavailable),
        )


@pytest.mark.parametrize(
    "source",
    ["http://example.test/base.toml", "ftp://example.test/base.toml"],
)
def test_remote_source_requires_https(
    rollout: types.ModuleType,
    tmp_path: Path,
    source: str,
) -> None:
    """Remote dictionary authorities cannot bypass HTTPS."""
    with pytest.raises(rollout.InsecureSourceError, match="URL must use HTTPS"):
        rollout.refresh_base(
            source,
            tmp_path / ".typos-base.toml",
            rollout.RefreshOptions(
                metadata=tmp_path / ".typos-base.json",
                opener=lambda *_args, **_kwargs: ValidResponse(),
            ),
        )


@pytest.mark.parametrize(
    "target",
    ["http://example.test/base.toml", "ftp://example.test/base.toml"],
)
def test_redirect_target_requires_https(
    rollout: types.ModuleType,
    target: str,
) -> None:
    """Redirects cannot downgrade or leave HTTPS transport."""
    handler = rollout._HttpsRedirectHandler()

    with pytest.raises(rollout.InsecureSourceError, match="redirect must use HTTPS"):
        handler.redirect_request(
            rollout.Request("https://example.test/base.toml"),
            None,
            302,
            "Found",
            {},
            target,
        )


def test_default_refresh_uses_guarded_https_opener(
    rollout: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The production path delegates to the opener with guarded redirects."""
    requests: list[object] = []

    class GuardedOpener:
        """Capture calls through the configured HTTPS-only opener."""

        def open(self, request: object, *, timeout: float) -> ValidResponse:
            """Return a valid response after recording the guarded call."""
            del timeout
            requests.append(request)
            return ValidResponse()

    monkeypatch.setattr(rollout, "_HTTPS_OPENER", GuardedOpener())

    result = rollout.refresh_base(
        "https://example.test/base.toml",
        tmp_path / ".typos-base.toml",
        rollout.RefreshOptions(metadata=tmp_path / ".typos-base.json"),
    )

    assert result.status == "refreshed", "guarded production opener did not refresh"
    assert len(requests) == 1, "production refresh bypassed the guarded opener"
