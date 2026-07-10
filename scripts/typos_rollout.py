"""Harvest and generate shared en-GB-oxendict ``typos`` configuration.

The module validates shared and repository-local dictionary data, refreshes an
untracked cache from local or HTTP sources, renders deterministic ``typos``
configuration, and harvests Oxford-form evidence from Git-tracked text.

Examples
--------
Load the shared base and render its generated configuration::

    base = load_dictionary(SHARED_DICTIONARY_PATH)
    rendered = render_typos_config(base)
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
SHARED_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "typos-oxendict-base.toml"
)
SUFFIX_PAIRS = (
    ("ise", "ize"),
    ("ises", "izes"),
    ("ised", "ized"),
    ("ising", "izing"),
    ("iser", "izer"),
    ("isers", "izers"),
    ("isable", "izable"),
    ("isation", "ization"),
    ("isations", "izations"),
)
OXFORD_FORM = re.compile(
    r"\b[A-Za-z]+(?:isations|izations|isation|ization|isable|izable|"
    r"isers|izers|ising|izing|ised|ized|ises|izes|iser|izer|ise|ize)\b"
)


@dataclass(frozen=True)
class Dictionary:
    """Curated words and exclusions used to generate a ``typos`` config.

    Attributes
    ----------
    stems, accepted, corrections, ignore_patterns, excluded_files
        Normalized dictionary data used by merging, rendering, and harvesting.
    """

    stems: tuple[str, ...] = ()
    accepted: tuple[str, ...] = ()
    corrections: tuple[tuple[str, str], ...] = ()
    ignore_patterns: tuple[str, ...] = ()
    excluded_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshResult:
    """Describe whether the untracked shared dictionary cache changed.

    Attributes
    ----------
    status
        Stable refresh outcome such as ``refreshed`` or ``current``.
    cache
        Path to the validated untracked base cache.
    """

    status: str
    cache: Path


class Response(Protocol):
    """Structural type for the HTTP response surface used by refreshes.

    Implementations provide status and headers, return response bytes from
    :meth:`read`, and support context-managed closure.
    """

    status: int
    headers: Mapping[str, str]

    def read(self) -> bytes:
        """Return the response body.

        Returns
        -------
        bytes
            Complete response payload.
        """

    def __enter__(self) -> "Response":
        """Enter the response context.

        Returns
        -------
        Response
            Open response object.
        """

    def __exit__(self, *args: object) -> None:
        """Leave the response context.

        Parameters
        ----------
        *args
            Optional exception context supplied by the context manager.
        """


def _string_list(table: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Read and validate a list of strings from a TOML table."""
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key!r} must be a list of strings")
    return tuple(sorted(set(value)))


def _table(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Read and validate a TOML table."""
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{key!r} must be a table")
    return cast(Mapping[str, object], value)


def _dictionary_from_text(text: str) -> Dictionary:
    """Parse and validate shared dictionary text."""
    document = tomllib.loads(text)
    schema = document.get("schema")
    if schema != SCHEMA_VERSION:
        raise ValueError(f"unsupported dictionary schema {schema!r}")
    oxford = _table(document, "oxford")
    words = _table(document, "words")
    patterns = _table(document, "patterns")
    files = _table(document, "files")
    corrections_table = _table(words, "corrections")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in corrections_table.items()
    ):
        raise ValueError("word corrections must map strings to strings")
    corrections = cast(Mapping[str, str], corrections_table)
    return Dictionary(
        stems=_string_list(oxford, "stems"),
        accepted=_string_list(words, "accepted"),
        corrections=tuple(sorted(corrections.items())),
        ignore_patterns=_string_list(patterns, "ignore"),
        excluded_files=_string_list(files, "exclude"),
    )


def load_dictionary(path: Path) -> Dictionary:
    """Load a validated shared dictionary from a TOML file.

    Parameters
    ----------
    path
        Dictionary file to parse.

    Returns
    -------
    Dictionary
        Normalized validated dictionary data.

    Raises
    ------
    ValueError, tomllib.TOMLDecodeError
        If the schema or TOML content is invalid.
    """
    return _dictionary_from_text(path.read_text(encoding="utf-8"))


def merge_dictionaries(base: Dictionary, local: Dictionary) -> Dictionary:
    """Merge a shared dictionary with a non-conflicting local overlay.

    Parameters
    ----------
    base, local
        Shared policy and repository-local additions.

    Returns
    -------
    Dictionary
        Deterministically merged policy.

    Raises
    ------
    ValueError
        If both inputs define different corrections for one word.
    """
    corrections = dict(base.corrections)
    for word, correction in local.corrections:
        existing = corrections.get(word)
        if existing is not None and existing != correction:
            raise ValueError(
                f"conflicting correction for {word!r}: {existing!r} != {correction!r}"
            )
        corrections[word] = correction
    return Dictionary(
        stems=tuple(sorted(set(base.stems) | set(local.stems))),
        accepted=tuple(sorted(set(base.accepted) | set(local.accepted))),
        corrections=tuple(sorted(corrections.items())),
        ignore_patterns=tuple(
            sorted(set(base.ignore_patterns) | set(local.ignore_patterns))
        ),
        excluded_files=tuple(
            sorted(set(base.excluded_files) | set(local.excluded_files))
        ),
    )


def generate_word_mappings(dictionary: Dictionary) -> dict[str, str]:
    """Expand Oxford stems and explicit words into deterministic mappings.

    Parameters
    ----------
    dictionary
        Curated Oxford stems, accepted words, and explicit corrections.

    Returns
    -------
    dict[str, str]
        Sorted spelling-to-correction mappings.

    Raises
    ------
    ValueError
        If generated and explicit entries conflict.
    """
    mappings = {word: word for word in dictionary.accepted}

    def add(word: str, correction: str) -> None:
        existing = mappings.get(word)
        if existing is not None and existing != correction:
            raise ValueError(
                f"conflicting generated correction for {word!r}: "
                f"{existing!r} != {correction!r}"
            )
        mappings[word] = correction

    for word, correction in dictionary.corrections:
        add(word, correction)
    for stem in dictionary.stems:
        for plain_british, oxford in SUFFIX_PAIRS:
            add(f"{stem}{plain_british}", f"{stem}{oxford}")
            add(f"{stem}{oxford}", f"{stem}{oxford}")
    return dict(sorted(mappings.items()))


def _toml_string(value: str) -> str:
    """Render a string using TOML-compatible JSON quoting."""
    return json.dumps(value, ensure_ascii=False)


def _render_array(name: str, values: tuple[str, ...]) -> list[str]:
    """Render a deterministic TOML string array."""
    lines = [f"{name} = ["]
    lines.extend(f"    {_toml_string(value)}," for value in values)
    lines.append("]")
    return lines


def render_typos_config(dictionary: Dictionary) -> str:
    """Render a deterministic, parse-checked ``typos.toml`` document.

    Parameters
    ----------
    dictionary
        Merged spelling policy to render.

    Returns
    -------
    str
        Valid TOML ending in one newline.

    Raises
    ------
    ValueError, tomllib.TOMLDecodeError
        If mappings conflict or rendered TOML is invalid.
    """
    lines = [
        "# Generated from the shared en-GB-oxendict dictionary.",
        "# Regenerate with scripts/typos_rollout_cli.py generate; do not edit by hand.",
        "",
        "[files]",
        *_render_array("extend-exclude", dictionary.excluded_files),
        "",
        "[default]",
        'locale = "en-gb"',
        *_render_array("extend-ignore-re", dictionary.ignore_patterns),
        "",
        "[default.extend-words]",
    ]
    lines.extend(
        f"{_toml_string(word)} = {_toml_string(correction)}"
        for word, correction in generate_word_mappings(dictionary).items()
    )
    rendered = "\n".join(lines) + "\n"
    tomllib.loads(rendered)
    return rendered


def _atomic_write(path: Path, content: bytes) -> None:
    """Write *content* beside *path* and atomically replace the destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=path.parent, prefix=f".{path.name}.") as stream:
        stream.write(content)
        temporary = Path(stream.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_config(path: Path, dictionary: Dictionary) -> None:
    """Atomically write validated generated configuration.

    Parameters
    ----------
    path
        Destination ``typos.toml`` path.
    dictionary
        Merged spelling policy to render.

    Returns
    -------
    None
        The function writes the destination as its only result.
    """
    _atomic_write(path, render_typos_config(dictionary).encode())


def _read_metadata(path: Path) -> dict[str, object]:
    """Read best-effort HTTP freshness metadata."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_metadata(path: Path, metadata: Mapping[str, object]) -> None:
    """Atomically write HTTP freshness metadata."""
    _atomic_write(path, (json.dumps(metadata, sort_keys=True) + "\n").encode())


def _valid_cache(cache: Path) -> bool:
    """Return whether *cache* contains a valid shared dictionary."""
    try:
        load_dictionary(cache)
    except (FileNotFoundError, OSError, ValueError, tomllib.TOMLDecodeError):
        return False
    return True


def _remote_is_not_newer(
    saved: Mapping[str, object],
    headers: Mapping[str, str],
) -> bool:
    """Return whether HTTP validators prove the response is not newer."""
    etag = headers.get("ETag")
    if etag is not None and etag == saved.get("etag"):
        return True
    modified = headers.get("Last-Modified")
    saved_modified = saved.get("last_modified")
    if not isinstance(modified, str) or not isinstance(saved_modified, str):
        return False
    try:
        return parsedate_to_datetime(modified) <= parsedate_to_datetime(saved_modified)
    except (TypeError, ValueError):
        return modified == saved_modified


def _refresh_local(source: Path, cache: Path, metadata: Path) -> RefreshResult:
    """Refresh from a local authoritative copy when it is newer."""
    source_stat = source.stat()
    source_name = str(source.resolve())
    saved = _read_metadata(metadata)
    saved_mtime = saved.get("mtime_ns")
    if (
        _valid_cache(cache)
        and saved.get("source") == source_name
        and isinstance(saved_mtime, int)
        and source_stat.st_mtime_ns <= saved_mtime
    ):
        return RefreshResult("current", cache)
    content = source.read_bytes()
    _dictionary_from_text(content.decode())
    _atomic_write(cache, content)
    _write_metadata(
        metadata,
        {"source": source_name, "mtime_ns": source_stat.st_mtime_ns},
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
    source: str,
    cache: Path,
    metadata: Path,
    response: Response,
) -> RefreshResult:
    """Validate and atomically persist a remote dictionary response."""
    content = response.read()
    _dictionary_from_text(content.decode())
    _atomic_write(cache, content)
    _write_metadata(
        metadata,
        {
            "source": source,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        },
    )
    return RefreshResult("refreshed", cache)


def _remote_response_result(
    source: str,
    cache: Path,
    metadata: Path,
    saved: Mapping[str, object],
    response: Response,
) -> RefreshResult:
    """Return the cache result for a successful HTTP response."""
    if response.status == 304 and _valid_cache(cache):
        return RefreshResult("current", cache)
    if _valid_cache(cache) and _remote_is_not_newer(saved, response.headers):
        return RefreshResult("current", cache)
    return _write_remote_cache(source, cache, metadata, response)


def _stale_cache_or_raise(cache: Path, error: OSError | URLError) -> RefreshResult:
    """Return a valid stale cache or propagate the download failure."""
    if _valid_cache(cache):
        return RefreshResult("stale-cache", cache)
    raise error


def _http_error_result(cache: Path, error: HTTPError) -> RefreshResult:
    """Translate an HTTP failure into the available cache result."""
    if error.code == 304 and _valid_cache(cache):
        return RefreshResult("current", cache)
    return _stale_cache_or_raise(cache, error)


def _refresh_http(
    source: str,
    cache: Path,
    metadata: Path,
    opener: Callable[..., Response],
) -> RefreshResult:
    """Refresh a cache from a remote source with validated stale fallback."""
    saved = _read_metadata(metadata)
    request = Request(source, headers=_conditional_headers(saved))
    try:
        with opener(request, timeout=30.0) as response:
            return _remote_response_result(source, cache, metadata, saved, response)
    except HTTPError as error:
        return _http_error_result(cache, error)
    except (OSError, URLError) as error:
        return _stale_cache_or_raise(cache, error)


def refresh_base(
    source: str | Path,
    cache: Path,
    *,
    metadata: Path,
    offline: bool = False,
    opener: Callable[..., Response] = urlopen,
) -> RefreshResult:
    """Refresh an untracked base cache when its authority is newer.

    Parameters
    ----------
    source
        Local path or HTTP URL for the authoritative shared dictionary.
    cache
        Untracked local cache destination.
    metadata
        Sidecar path for source identity and HTTP validators.
    offline
        Reuse a valid cache without contacting the source.
    opener
        Injectable HTTP opener used for deterministic tests.

    Returns
    -------
    RefreshResult
        Refresh status and validated cache path.

    Raises
    ------
    FileNotFoundError
        If offline mode has no valid cache.
    ValueError, tomllib.TOMLDecodeError
        If downloaded or cached dictionary content is invalid.
    OSError, URLError, HTTPError
        If the source cannot be read and no valid stale cache exists.
    """
    source_text = str(source)
    if offline:
        if not _valid_cache(cache):
            raise FileNotFoundError(f"no cached shared dictionary at {cache}")
        return RefreshResult("offline-cache", cache)
    if isinstance(source, Path) or "://" not in source_text:
        return _refresh_local(Path(source_text), cache, metadata)
    return _refresh_http(source_text, cache, metadata, opener)


def harvest_oxford_forms(text: str) -> tuple[str, ...]:
    """Return normalized ``-ise`` and ``-ize`` candidates in text.

    Parameters
    ----------
    text
        UTF-8 text line or document to inspect.

    Returns
    -------
    tuple[str, ...]
        Sorted unique case-folded candidate forms.
    """
    return tuple(sorted({match.group(0).casefold() for match in OXFORD_FORM.finditer(text)}))


def is_harvest_excluded(relative: Path, dictionary: Dictionary) -> bool:
    """Return whether merged dictionary policy excludes a relative path.

    Parameters
    ----------
    relative
        Repository-relative path under consideration.
    dictionary
        Merged policy containing file exclusions.

    Returns
    -------
    bool
        ``True`` when an exclusion component or pattern matches.
    """
    return any(
        excluded in relative.parts or relative.match(excluded)
        for excluded in dictionary.excluded_files
    )


def harvest_repository(repository: Path) -> tuple[dict[str, object], ...]:
    """Harvest Oxford-form evidence from Git-tracked UTF-8 text files.

    Parameters
    ----------
    repository
        Git worktree whose tracked files should be inspected.

    Returns
    -------
    tuple[dict[str, object], ...]
        JSON-serializable path, line, and candidate-form records.

    Raises
    ------
    ValueError, tomllib.TOMLDecodeError
        If shared or local dictionary policy is invalid.
    """
    dictionary = load_dictionary(SHARED_DICTIONARY_PATH)
    local_overlay = repository / "typos.local.toml"
    if local_overlay.exists():
        dictionary = merge_dictionaries(
            dictionary,
            load_dictionary(local_overlay),
        )
    tracked = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    findings: list[dict[str, object]] = []
    for relative in sorted(filter(None, tracked.split("\0"))):
        relative_path = Path(relative)
        if is_harvest_excluded(relative_path, dictionary):
            continue
        path = repository / relative_path
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            forms = harvest_oxford_forms(line)
            if forms:
                findings.append(
                    {"path": relative, "line": number, "forms": list(forms)}
                )
    return tuple(findings)
