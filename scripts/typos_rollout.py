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
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA_VERSION = 1
REQUIRED_AUTHORITY_FIELDS = (
    ("oxford", "stems"),
    ("words", "accepted"),
    ("words", "corrections"),
    ("phrases", "corrections"),
    ("patterns", "ignore"),
    ("files", "exclude"),
)
GENERIC_PROSE = ("ordinary prose", "unrelated_identifier")
UNIVERSAL_FILE_GLOBS = frozenset({"*", "**", "**/*", "*.md", "**/*.md"})
SHARED_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "typos-oxendict-base.toml"
)
SUFFIX_PAIRS = (
    ("isably", "izably"),
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
    r"\b[A-Za-z]+(?:isations|izations|isation|ization|isably|izably|isable|izable|"
    r"isers|izers|ising|izing|ised|ized|ises|izes|iser|izer|ise|ize)\b"
)
PHRASE_POLICY_PATHS = frozenset(
    {
        Path("data/typos-oxendict-base.toml"),
        Path("typos.local.toml"),
    }
)


@dataclass(frozen=True)
class Dictionary:
    """Curated words and exclusions used to generate a ``typos`` config.

    Attributes
    ----------
    stems, accepted, corrections, phrase_corrections, ignore_patterns,
    excluded_files
        Normalized dictionary data used by merging, rendering, and harvesting.
    """

    stems: tuple[str, ...] = ()
    accepted: tuple[str, ...] = ()
    corrections: tuple[tuple[str, str], ...] = ()
    phrase_corrections: tuple[tuple[str, str], ...] = ()
    ignore_patterns: tuple[str, ...] = ()
    excluded_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhraseFinding:
    """Describe one prohibited phrase found in tracked text.

    Attributes
    ----------
    path, line, column
        Repository-relative location of the finding.
    phrase, correction
        Observed prohibited phrase and its canonical replacement.
    """

    path: Path
    line: int
    column: int
    phrase: str
    correction: str


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


class Response(Protocol):
    """Structural type for the HTTP response surface used by refreshes.

    Implementations provide headers, return response bytes from :meth:`read`,
    and support context-managed closure.
    """

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

    Examples
    --------
    >>> RefreshOptions(metadata=Path(".typos-base.json")).offline
    False
    """

    metadata: Path
    offline: bool = False
    opener: Callable[..., Response] | None = None


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
    return cast("Mapping[str, object]", value)


def _is_supported_schema(schema: object) -> bool:
    """Return whether *schema* is the exact supported integer version."""
    return (
        isinstance(schema, int)
        and not isinstance(schema, bool)
        and schema == SCHEMA_VERSION
    )


def _validate_required_field(
    document: Mapping[str, object],
    table_name: str,
    field_name: str,
) -> None:
    """Require one shared-authority table and field."""
    if table_name not in document:
        raise ValueError(f"missing required table {table_name!r}")
    table = document[table_name]
    if isinstance(table, dict) and field_name not in table:
        raise ValueError(f"missing required field {table_name}.{field_name}")


def _validate_document(document: Mapping[str, object], *, sparse: bool) -> None:
    """Validate schema identity and required shared-authority fields."""
    schema = document.get("schema")
    if not _is_supported_schema(schema):
        raise ValueError(f"unsupported dictionary schema {schema!r}")
    if sparse:
        return
    for table_name, field_name in REQUIRED_AUTHORITY_FIELDS:
        _validate_required_field(document, table_name, field_name)


def _ignore_pattern_is_broad(pattern: str) -> bool:
    """Return whether *pattern* can suppress empty or generic prose."""
    compiled = re.compile(pattern)
    return compiled.search("") is not None or any(
        compiled.fullmatch(probe) for probe in GENERIC_PROSE
    )


def _validate_ignore_pattern(pattern: str) -> None:
    """Reject one ignore pattern that can suppress generic text."""
    if _ignore_pattern_is_broad(pattern):
        raise ValueError(f"local ignore pattern is too broad: {pattern!r}")


def _validate_file_exclusion(pattern: str) -> None:
    """Reject one file glob that can suppress the whole documentation set."""
    if pattern in UNIVERSAL_FILE_GLOBS:
        raise ValueError(f"local file exclusion is too broad: {pattern!r}")


def _validate_local_exceptions(
    ignore_patterns: tuple[str, ...],
    excluded_files: tuple[str, ...],
) -> None:
    """Reject local exceptions that can match generic prose or all Markdown."""
    for pattern in ignore_patterns:
        _validate_ignore_pattern(pattern)
    for pattern in excluded_files:
        _validate_file_exclusion(pattern)


def _dictionary_from_text(text: str, *, sparse: bool = False) -> Dictionary:
    """Parse and validate shared dictionary text."""
    document = tomllib.loads(text)
    _validate_document(document, sparse=sparse)
    oxford = _table(document, "oxford")
    words = _table(document, "words")
    phrases = _table(document, "phrases")
    patterns = _table(document, "patterns")
    files = _table(document, "files")
    corrections_table = _table(words, "corrections")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in corrections_table.items()
    ):
        raise ValueError("word corrections must map strings to strings")
    phrase_corrections_table = _table(phrases, "corrections")
    if not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in phrase_corrections_table.items()
    ):
        raise ValueError("phrase corrections must map strings to strings")
    corrections = cast("Mapping[str, str]", corrections_table)
    phrase_corrections = cast("Mapping[str, str]", phrase_corrections_table)
    return Dictionary(
        stems=_string_list(oxford, "stems"),
        accepted=_string_list(words, "accepted"),
        corrections=tuple(sorted(corrections.items())),
        phrase_corrections=tuple(sorted(phrase_corrections.items())),
        ignore_patterns=_string_list(patterns, "ignore"),
        excluded_files=_string_list(files, "exclude"),
    )


def load_dictionary(path: Path, *, local_overlay: bool = False) -> Dictionary:
    """Load a validated shared dictionary from a TOML file.

    Parameters
    ----------
    path
        Dictionary file to parse.
    local_overlay
        Permit omitted fields only for an explicitly local overlay.

    Returns
    -------
    Dictionary
        Normalized validated dictionary data.

    Raises
    ------
    ValueError, tomllib.TOMLDecodeError
        If the schema or TOML content is invalid.
    """
    return _dictionary_from_text(path.read_text(encoding="utf-8"), sparse=local_overlay)


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
        If corrections conflict or local exceptions are too broad.
    """
    _validate_local_exceptions(local.ignore_patterns, local.excluded_files)
    corrections = dict(base.corrections)
    for word, correction in local.corrections:
        existing = corrections.get(word)
        if existing is not None and existing != correction:
            raise ValueError(
                f"conflicting correction for {word!r}: {existing!r} != {correction!r}"
            )
        corrections[word] = correction
    phrase_corrections = dict(base.phrase_corrections)
    for phrase, correction in local.phrase_corrections:
        existing = phrase_corrections.get(phrase)
        if existing is not None and existing != correction:
            raise ValueError(
                f"conflicting phrase correction for {phrase!r}: "
                f"{existing!r} != {correction!r}"
            )
        phrase_corrections[phrase] = correction
    return Dictionary(
        stems=tuple(sorted(set(base.stems) | set(local.stems))),
        accepted=tuple(sorted(set(base.accepted) | set(local.accepted))),
        corrections=tuple(sorted(corrections.items())),
        phrase_corrections=tuple(sorted(phrase_corrections.items())),
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


def _local_cache_is_current(
    cache: Path,
    saved: Mapping[str, object],
    source: _LocalSourceState,
) -> bool:
    """Return whether metadata proves a valid local-source cache is current."""
    saved_mtime = saved.get("mtime_ns")
    return (
        _valid_cache(cache)
        and saved.get("source") == source.name
        and isinstance(saved_mtime, int)
        and source.mtime_ns <= saved_mtime
    )


def _refresh_local(
    source: Path,
    cache: Path,
    options: RefreshOptions,
) -> RefreshResult:
    """Refresh from a local authoritative copy when it is newer."""
    source_stat = source.stat()
    source_state = _LocalSourceState(
        name=str(source.resolve()),
        mtime_ns=source_stat.st_mtime_ns,
    )
    saved = _read_metadata(options.metadata)
    if _local_cache_is_current(cache, saved, source_state):
        return RefreshResult("current", cache)
    content = source.read_bytes()
    _dictionary_from_text(content.decode())
    _atomic_write(cache, content)
    _write_metadata(
        options.metadata,
        {"source": source_state.name, "mtime_ns": source_state.mtime_ns},
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
) -> RefreshResult:
    """Validate and atomically persist a remote dictionary response."""
    try:
        content = response.read()
    except URLError as error:
        message = f"shared dictionary authority is unavailable: {state.source}"
        raise NetworkUnavailableError(message) from error
    _dictionary_from_text(content.decode())
    _atomic_write(state.cache, content)
    _write_metadata(
        state.metadata,
        {
            "source": state.source,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        },
    )
    return RefreshResult("refreshed", state.cache)


def _remote_response_result(
    state: _RemoteRequestState,
    response: Response,
) -> RefreshResult:
    """Return the cache result for a successful HTTP response."""
    if _valid_cache(state.cache) and _remote_is_not_newer(
        state.saved, response.headers
    ):
        return RefreshResult("current", state.cache)
    return _write_remote_cache(state, response)


def _stale_cache_or_raise(
    cache: Path,
    error: NetworkUnavailableError,
) -> RefreshResult:
    """Return a valid stale cache or propagate the download failure."""
    if _valid_cache(cache):
        return RefreshResult("stale-cache", cache)
    raise error


def _http_error_result(cache: Path, error: HTTPError) -> RefreshResult:
    """Translate an HTTP failure into the available cache result."""
    if error.code == 304 and _valid_cache(cache):
        return RefreshResult("current", cache)
    raise error


class _HttpsRedirectHandler(HTTPRedirectHandler):
    """Reject redirects that leave the HTTPS transport boundary."""

    def redirect_request(
        self,
        request: Request,
        *redirect: object,
    ) -> Request | None:
        """Follow only redirects whose resolved target remains HTTPS.

        The variadic tail preserves the standard library's positional override
        contract without making transport-library parameters part of this
        helper's domain-facing interface.
        """
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


def _refresh_http(
    source: str,
    cache: Path,
    options: RefreshOptions,
) -> RefreshResult:
    """Refresh a cache from a remote source with validated stale fallback."""
    saved = _read_metadata(options.metadata)
    if saved.get("source") != source:
        saved = {}
    request = _https_request(source, _conditional_headers(saved))
    open_remote = _HTTPS_OPENER.open if options.opener is None else options.opener
    try:
        response_context = open_remote(request, timeout=30.0)
    except HTTPError as error:
        return _http_error_result(cache, error)
    except URLError:
        message = f"shared dictionary authority is unavailable: {source}"
        unavailable = NetworkUnavailableError(message)
        return _stale_cache_or_raise(cache, unavailable)
    with response_context as response:
        try:
            return _remote_response_result(
                _RemoteRequestState(source, cache, options.metadata, saved),
                response,
            )
        except NetworkUnavailableError as error:
            return _stale_cache_or_raise(cache, error)


def refresh_base(
    source: str | Path,
    cache: Path,
    options: RefreshOptions,
) -> RefreshResult:
    """Refresh an untracked base cache when its authority is newer.

    Parameters
    ----------
    source
        Local path or HTTP URL for the authoritative shared dictionary.
    cache
        Untracked local cache destination.
    options
        Metadata destination, offline mode and optional injectable HTTP opener.

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
    NetworkUnavailableError
        If the remote authority is unavailable and no valid stale cache exists.
    InsecureSourceError
        If a remote authority or redirect does not use HTTPS.
    OSError, HTTPError
        If local persistence fails or the authority returns an HTTP error.
    """
    source_text = str(source)
    if options.offline:
        if not _valid_cache(cache):
            raise FileNotFoundError(f"no cached shared dictionary at {cache}")
        return RefreshResult("offline-cache", cache)
    if isinstance(source, Path) or "://" not in source_text:
        return _refresh_local(Path(source_text), cache, options)
    return _refresh_http(source_text, cache, options)


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
    return tuple(
        sorted({match.group(0).casefold() for match in OXFORD_FORM.finditer(text)})
    )


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


def _tracked_relative_paths(repository: Path) -> tuple[Path, ...]:
    """Return the repository's Git-tracked paths in deterministic order."""
    tracked = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return tuple(
        Path(relative) for relative in sorted(filter(None, tracked.split("\0")))
    )


def _mask_ignored_text(text: str, patterns: tuple[str, ...]) -> str:
    """Blank ignored text while preserving line and column positions."""

    def blank(match: re.Match[str]) -> str:
        return "".join(
            "\n" if character == "\n" else " " for character in match.group()
        )

    for pattern in patterns:
        text = re.sub(pattern, blank, text)
    return text


def check_phrase_corrections(
    repository: Path,
    dictionary: Dictionary,
) -> tuple[PhraseFinding, ...]:
    """Find prohibited exact phrases in tracked UTF-8 text.

    Typos tokenizes punctuation-separated compounds into individual words, so
    it cannot enforce a correction such as ``hand-written`` to ``handwritten``.
    This companion check applies only curated phrase corrections, after masking
    the same ignored spans and excluded paths as the generated Typos policy.

    Parameters
    ----------
    repository
        Git worktree whose tracked text should be checked.
    dictionary
        Merged shared and repository-local spelling policy.

    Returns
    -------
    tuple[PhraseFinding, ...]
        Findings ordered by path, phrase, and source position.
    """
    findings: list[PhraseFinding] = []
    for relative_path in _tracked_relative_paths(repository):
        if (
            relative_path in PHRASE_POLICY_PATHS
            or is_harvest_excluded(relative_path, dictionary)
        ):
            continue
        path = repository / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        masked = _mask_ignored_text(text, dictionary.ignore_patterns)
        for phrase, correction in dictionary.phrase_corrections:
            matcher = re.compile(
                rf"(?<![\w-]){re.escape(phrase)}(?![\w-])",
                re.IGNORECASE,
            )
            for match in matcher.finditer(masked):
                line = masked.count("\n", 0, match.start()) + 1
                previous_newline = masked.rfind("\n", 0, match.start())
                findings.append(
                    PhraseFinding(
                        path=relative_path,
                        line=line,
                        column=match.start() - previous_newline,
                        phrase=text[match.start() : match.end()],
                        correction=correction,
                    )
                )
    return tuple(findings)


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
            load_dictionary(local_overlay, local_overlay=True),
        )
    findings: list[dict[str, object]] = []
    for relative_path in _tracked_relative_paths(repository):
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
                    {
                        "path": str(relative_path),
                        "line": number,
                        "forms": list(forms),
                    }
                )
    return tuple(findings)
