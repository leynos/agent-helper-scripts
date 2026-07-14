"""Provide cache support types and atomic writes for spelling policy."""

from collections.abc import Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import tempfile
from typing import Callable, Protocol

ContentValidator = Callable[[bytes], None]
AtomicWriter = Callable[[Path, bytes], None]


@dataclass(frozen=True)
class RefreshResult:
    """Describe whether the untracked shared dictionary cache changed.

    Attributes
    ----------
    status
        Stable outcome such as ``refreshed``, ``current`` or ``stale-cache``.
    cache
        Path to the validated untracked dictionary cache.
    """

    status: str
    cache: Path


class Response(Protocol):
    """Expose the HTTP response surface used by cache refresh.

    Attributes
    ----------
    headers
        Response validators persisted with the source identity.
    """

    headers: Mapping[str, str]

    def read(self) -> bytes:
        """Read and return the complete response body."""

    def __enter__(self) -> "Response":
        """Enter the response context and return the open response."""

    def __exit__(self, *args: object) -> None:
        """Close the response after optional exception context."""


def atomic_write(path: Path, content: bytes) -> None:
    """Write content beside a path and atomically replace the destination.

    Parameters
    ----------
    path
        Destination whose parent directory is created when absent.
    content
        Bytes to persist.

    Raises
    ------
    OSError
        If directory creation, writing, closing or replacement fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = tempfile.NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary = Path(stream.name)
    try:
        with stream:
            stream.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_metadata(path: Path) -> dict[str, object]:
    """Read best-effort freshness metadata from a sidecar."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_metadata(
    path: Path,
    metadata: Mapping[str, object],
    writer: AtomicWriter,
) -> None:
    """Atomically write freshness metadata with an injected writer."""
    content = (json.dumps(metadata, sort_keys=True) + "\n").encode()
    writer(path, content)


def valid_cache(cache: Path, validate: ContentValidator) -> bool:
    """Report whether a cache contains a valid shared dictionary."""
    try:
        validate(cache.read_bytes())
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        return False
    return True


def remote_is_not_newer(
    saved: Mapping[str, object],
    headers: Mapping[str, str],
) -> bool:
    """Report whether HTTP validators prove a response is not newer."""
    etag = headers.get("ETag")
    saved_etag = saved.get("etag")
    if isinstance(etag, str) and isinstance(saved_etag, str):
        return etag == saved_etag
    modified = headers.get("Last-Modified")
    saved_modified = saved.get("last_modified")
    if not isinstance(modified, str) or not isinstance(saved_modified, str):
        return False
    try:
        return parsedate_to_datetime(modified) <= parsedate_to_datetime(saved_modified)
    except (TypeError, ValueError):
        return modified == saved_modified
