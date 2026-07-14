"""Refresh the shared spelling dictionary from local and HTTPS authorities.

This module owns freshness, source scoping, transport security and persistence
coordination.  Refresh diagnostics deliberately expose only bounded decision,
source-kind and error-class fields; authority URLs and local paths stay out of
logs.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import typos_rollout_cache as cache_support

RefreshResult = cache_support.RefreshResult
Response = cache_support.Response

ContentValidator = Callable[[bytes], None]
AtomicWriter = Callable[[Path, bytes], None]
Opener = Callable[..., Response]
HTTP_NOT_MODIFIED = 304
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshOptions:
    """Configure one shared-dictionary refresh operation.

    Attributes
    ----------
    metadata
        Sidecar path containing source identity and freshness validators.
    offline
        Whether to reuse a valid cache without contacting the authority.
    opener
        Optional injectable HTTPS opener for deterministic tests.
    """

    metadata: Path
    offline: bool = False
    opener: Opener | None = None


@dataclass(frozen=True, slots=True)
class RefreshContext:
    """Bind public refresh options to internal validation and I/O seams.

    Attributes
    ----------
    options
        Caller-selected metadata, offline and test-opener policy.
    validate
        Callback that rejects invalid dictionary bytes.
    atomic_write
        Callback that persists validated cache and metadata bytes.
    guarded_open
        HTTPS-only production opener, injectable through the facade.
    """

    options: RefreshOptions
    validate: ContentValidator
    atomic_write: AtomicWriter
    guarded_open: Opener


@dataclass(frozen=True, slots=True)
class _LocalSourceState:
    """Group local authority identity and freshness state."""

    name: str
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class _RemoteRequestState:
    """Group one remote authority with its cache and saved validators."""

    source: str
    cache: Path
    metadata: Path
    saved: Mapping[str, object]


class NetworkUnavailableError(OSError):
    """Report that the remote dictionary authority could not be reached."""


class InsecureSourceError(ValueError):
    """Report a dictionary source or redirect that does not use HTTPS."""


def _log_decision(
    decision: str,
    source_kind: str,
    *,
    error_class: str = "none",
    level: int = logging.DEBUG,
) -> None:
    """Emit one bounded structured refresh decision without source identity."""
    LOGGER.log(
        level,
        "Shared dictionary refresh decision",
        extra={
            "operation": "dictionary-refresh",
            "source_kind": source_kind,
            "error_class": error_class,
            "decision": decision,
        },
    )


def _local_cache_is_current(
    cache: Path,
    saved: Mapping[str, object],
    source: _LocalSourceState,
    validate: ContentValidator,
) -> bool:
    """Report whether metadata proves a local-source cache is current."""
    saved_mtime = saved.get("mtime_ns")
    return (
        cache_support.valid_cache(cache, validate)
        and saved.get("source") == source.name
        and isinstance(saved_mtime, int)
        and source.mtime_ns <= saved_mtime
    )


def _refresh_local(
    source: Path,
    cache: Path,
    context: RefreshContext,
) -> RefreshResult:
    """Refresh from a local authoritative copy when it is newer."""
    source_stat = source.stat()
    source_state = _LocalSourceState(
        name=str(source.resolve()),
        mtime_ns=source_stat.st_mtime_ns,
    )
    saved = cache_support.read_metadata(context.options.metadata)
    if _local_cache_is_current(cache, saved, source_state, context.validate):
        _log_decision("current", "local")
        return RefreshResult("current", cache)
    decision = (
        "source-mismatch" if saved.get("source") != source_state.name else "newer"
    )
    _log_decision(decision, "local")
    content = source.read_bytes()
    context.validate(content)
    context.atomic_write(cache, content)
    cache_support.write_metadata(
        context.options.metadata,
        {"source": source_state.name, "mtime_ns": source_state.mtime_ns},
        context.atomic_write,
    )
    return RefreshResult("refreshed", cache)


def _conditional_headers(saved: Mapping[str, object]) -> dict[str, str]:
    """Build conditional HTTP headers from persisted validators."""
    headers: dict[str, str] = {}
    etag = saved.get("etag")
    if isinstance(etag, str):
        headers["If-None-Match"] = etag
    last_modified = saved.get("last_modified")
    if isinstance(last_modified, str):
        headers["If-Modified-Since"] = last_modified
    return headers


def _write_remote_cache(
    state: _RemoteRequestState,
    response: Response,
    context: RefreshContext,
) -> RefreshResult:
    """Validate and atomically persist a remote dictionary response."""
    try:
        content = response.read()
    except URLError as error:
        message = f"shared dictionary authority is unavailable: {state.source}"
        raise NetworkUnavailableError(message) from error
    context.validate(content)
    context.atomic_write(state.cache, content)
    cache_support.write_metadata(
        state.metadata,
        {
            "source": state.source,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        },
        context.atomic_write,
    )
    _log_decision("refreshed", "https")
    return RefreshResult("refreshed", state.cache)


def _remote_response_result(
    state: _RemoteRequestState,
    response: Response,
    context: RefreshContext,
) -> RefreshResult:
    """Return the cache result for a successful HTTP response."""
    if cache_support.valid_cache(
        state.cache, context.validate
    ) and cache_support.remote_is_not_newer(
        state.saved, response.headers
    ):
        _log_decision("current", "https")
        return RefreshResult("current", state.cache)
    return _write_remote_cache(state, response, context)


def _stale_cache_or_raise(
    cache: Path,
    error: NetworkUnavailableError,
    context: RefreshContext,
    *,
    has_matching_source: bool,
) -> RefreshResult:
    """Return a source-scoped stale cache or propagate connectivity loss."""
    if has_matching_source and cache_support.valid_cache(cache, context.validate):
        _log_decision(
            "stale-cache",
            "https",
            error_class="network-unavailable",
            level=logging.INFO,
        )
        return RefreshResult("stale-cache", cache)
    _log_decision(
        "stale-cache-rejected",
        "https",
        error_class="network-unavailable",
        level=logging.WARNING,
    )
    raise error


def _http_error_result(
    cache: Path,
    error: HTTPError,
    context: RefreshContext,
    *,
    has_matching_source: bool,
) -> RefreshResult:
    """Translate HTTP 304 into a source-scoped current-cache result."""
    if (
        error.code == HTTP_NOT_MODIFIED
        and has_matching_source
        and cache_support.valid_cache(cache, context.validate)
    ):
        _log_decision(
            "not-modified",
            "https",
            error_class="http-not-modified",
        )
        return RefreshResult("current", cache)
    if error.code == HTTP_NOT_MODIFIED:
        _log_decision(
            "not-modified-rejected",
            "https",
            error_class="http-not-modified",
            level=logging.WARNING,
        )
    raise error


class _HttpsRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that leave the HTTPS transport boundary."""

    def redirect_request(
        self,
        request: Request,
        *redirect: object,
    ) -> Request | None:
        """Follow only redirects whose resolved target remains HTTPS."""
        file_pointer, code, message, headers, new_url = redirect
        if urlsplit(new_url).scheme != "https":
            error_message = f"shared dictionary redirect must use HTTPS: {new_url}"
            raise InsecureSourceError(error_message)
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


_HTTPS_OPENER = build_opener(_HttpsRedirectHandler())


def _https_request(source: str, headers: Mapping[str, str]) -> Request:
    """Build a request after constraining the shared source to HTTPS."""
    if urlsplit(source).scheme != "https":
        message = f"shared dictionary URL must use HTTPS: {source}"
        raise InsecureSourceError(message)
    return Request(source, headers=dict(headers))


def _refresh_http(source: str, cache: Path, context: RefreshContext) -> RefreshResult:
    """Refresh a cache from HTTPS with source-scoped stale fallback."""
    saved = cache_support.read_metadata(context.options.metadata)
    has_matching_source = saved.get("source") == source
    if not has_matching_source:
        saved = {}
        _log_decision("source-mismatch", "https")
    request = _https_request(source, _conditional_headers(saved))
    open_remote = (
        context.guarded_open
        if context.options.opener is None
        else context.options.opener
    )
    try:
        response_context = open_remote(request, timeout=30.0)
    except HTTPError as error:
        return _http_error_result(
            cache,
            error,
            context,
            has_matching_source=has_matching_source,
        )
    except URLError:
        message = f"shared dictionary authority is unavailable: {source}"
        unavailable = NetworkUnavailableError(message)
        return _stale_cache_or_raise(
            cache,
            unavailable,
            context,
            has_matching_source=has_matching_source,
        )
    with response_context as response:
        try:
            return _remote_response_result(
                _RemoteRequestState(source, cache, context.options.metadata, saved),
                response,
                context,
            )
        except NetworkUnavailableError as error:
            return _stale_cache_or_raise(
                cache,
                error,
                context,
                has_matching_source=has_matching_source,
            )


def refresh_base(
    source: str | Path,
    cache: Path,
    context: RefreshContext,
) -> RefreshResult:
    """Refresh an untracked cache when its authoritative copy is newer.

    Parameters
    ----------
    source
        Local path or HTTPS URL for the authoritative shared dictionary.
    cache
        Untracked local cache destination.
    context
        Public options and private validation and persistence callbacks.

    Returns
    -------
    RefreshResult
        Stable refresh status and validated cache path.

    Raises
    ------
    FileNotFoundError, NetworkUnavailableError, InsecureSourceError
        If policy cannot be obtained securely from the selected authority.
    OSError, HTTPError, UnicodeDecodeError, TypeError, ValueError
        If retrieval, persistence or dictionary validation fails.
    """
    options = context.options
    if options.offline:
        if not cache_support.valid_cache(cache, context.validate):
            message = f"no cached shared dictionary at {cache}"
            raise FileNotFoundError(message)
        _log_decision("offline-cache", "cache")
        return RefreshResult("offline-cache", cache)
    source_text = str(source)
    if isinstance(source, Path) or "://" not in source_text:
        return _refresh_local(Path(source_text), cache, context)
    return _refresh_http(source_text, cache, context)
