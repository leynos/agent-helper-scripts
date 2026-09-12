"""Generate shared en-GB-oxendict Typos policy through a stable facade.

The facade preserves the rollout helper's public import surface while cohesive
modules own policy validation, overlay merging, cache persistence, HTTPS
refresh, phrase checks, and Oxford-form harvesting.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import cast
from urllib.request import Request

import typos_rollout_cache
import typos_rollout_check
import typos_rollout_harvest
import typos_rollout_http
import typos_rollout_merge
import typos_rollout_policy
import typos_rollout_render

SCHEMA_VERSION = typos_rollout_policy.SCHEMA_VERSION
REQUIRED_AUTHORITY_FIELDS = typos_rollout_policy.REQUIRED_AUTHORITY_FIELDS
GENERIC_PROSE = typos_rollout_policy.GENERIC_PROSE
UNIVERSAL_FILE_GLOBS = typos_rollout_policy.UNIVERSAL_FILE_GLOBS
BACKREFERENCE = typos_rollout_policy.BACKREFERENCE
REPETITION = typos_rollout_policy.REPETITION
SHARED_DICTIONARY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "typos-oxendict-base.toml"
)
DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/leynos/agent-helper-scripts/"
    "refs/heads/main/data/typos-oxendict-base.toml"
)
SUFFIX_PAIRS = typos_rollout_render.SUFFIX_PAIRS

Dictionary = typos_rollout_policy.Dictionary
RefreshResult = typos_rollout_cache.RefreshResult
Response = typos_rollout_cache.Response
RefreshOptions = typos_rollout_http.RefreshOptions
NetworkUnavailableError = typos_rollout_http.NetworkUnavailableError
InsecureSourceError = typos_rollout_http.InsecureSourceError
PhraseFinding = typos_rollout_check.PhraseFinding
_GroupState = typos_rollout_policy._GroupState
_RepetitionScanner = typos_rollout_policy._RepetitionScanner
_HttpsRedirectHandler = typos_rollout_http._HttpsRedirectHandler
_HTTPS_OPENER = typos_rollout_http._HTTPS_OPENER
_atomic_write = typos_rollout_cache.atomic_write
_read_metadata = typos_rollout_cache.read_metadata
_remote_is_not_newer = typos_rollout_cache.remote_is_not_newer
_compile_ignore_patterns = typos_rollout_policy.compile_ignore_patterns
_merge_ignore_patterns = typos_rollout_merge._merge_ignore_patterns
_tracked_relative_paths = typos_rollout_harvest._tracked_relative_paths
_mask_ignored_text = typos_rollout_check._mask_ignored_text
OXFORD_FORM = typos_rollout_harvest.OXFORD_FORM
PHRASE_POLICY_PATHS = typos_rollout_check.PHRASE_POLICY_PATHS
tempfile = typos_rollout_cache.tempfile
generate_word_mappings = typos_rollout_render.generate_word_mappings
render_typos_config = typos_rollout_render.render_typos_config
harvest_oxford_forms = typos_rollout_harvest.harvest_oxford_forms
is_harvest_excluded = typos_rollout_harvest.is_harvest_excluded
check_phrase_corrections = typos_rollout_check.check_phrase_corrections
merge_dictionaries = typos_rollout_merge.merge_dictionaries


def _string_list(table: Mapping[str, object], key: str) -> tuple[str, ...]:
    """Read and validate a list of strings from a TOML table."""
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        message = f"{key!r} must be a list of strings"
        raise ValueError(message)
    return tuple(sorted(set(value)))


def _table(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    """Read and validate a TOML table."""
    value = document.get(key, {})
    if not isinstance(value, dict):
        message = f"{key!r} must be a table"
        raise ValueError(message)
    return cast("Mapping[str, object]", value)


def _string_mapping(
    table: Mapping[str, object],
    key: str,
    *,
    description: str,
) -> Mapping[str, str]:
    """Read and validate a string-to-string mapping from a TOML table."""
    value = _table(table, key)
    if not all(
        isinstance(item_key, str) and isinstance(item_value, str)
        for item_key, item_value in value.items()
    ):
        message = f"{description} must map strings to strings"
        raise ValueError(message)
    return cast("Mapping[str, str]", value)


def _dictionary_from_text(text: str, *, sparse: bool = False) -> Dictionary:
    """Parse and validate shared dictionary text."""
    document = tomllib.loads(text)
    typos_rollout_policy.validate_document(document, sparse=sparse)
    oxford = _table(document, "oxford")
    words = _table(document, "words")
    phrases = _table(document, "phrases")
    patterns = _table(document, "patterns")
    files = _table(document, "files")
    corrections = _string_mapping(
        words,
        "corrections",
        description="word corrections",
    )
    phrase_corrections = _string_mapping(
        phrases,
        "corrections",
        description="phrase corrections",
    )
    ignore_patterns = _string_list(patterns, "ignore")
    typos_rollout_policy.compile_ignore_patterns(ignore_patterns)
    return Dictionary(
        stems=_string_list(oxford, "stems"),
        accepted=_string_list(words, "accepted"),
        corrections=tuple(sorted(corrections.items())),
        phrase_corrections=tuple(sorted(phrase_corrections.items())),
        ignore_patterns=ignore_patterns,
        removed_patterns=_string_list(patterns, "remove"),
        excluded_files=_string_list(files, "exclude"),
    )


def load_dictionary(path: Path, *, local_overlay: bool = False) -> Dictionary:
    """Load a validated shared dictionary or explicit local overlay.

    Parameters
    ----------
    path
        UTF-8 TOML dictionary path.
    local_overlay
        Whether the document may omit complete-authority fields.

    Returns
    -------
    Dictionary
        Normalized and validated spelling policy.

    Raises
    ------
    OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError
        If the file cannot be read as UTF-8 or violates policy.
    """
    return _dictionary_from_text(path.read_text(encoding="utf-8"), sparse=local_overlay)


def write_config(path: Path, dictionary: Dictionary) -> None:
    """Atomically write validated generated configuration.

    Parameters
    ----------
    path
        Destination ``typos.toml`` path.
    dictionary
        Validated spelling policy to render and persist.
    """
    typos_rollout_render.write_config(path, dictionary, _atomic_write)


@dataclass(frozen=True)
class GeneratedConfig:
    """Describe one generation of a repository's tracked configuration.

    Attributes
    ----------
    status
        Stable refresh status reported for the shared base.
    dictionary
        Merged policy the generated configuration was rendered from.
    path
        Generated configuration path.
    """

    status: str
    dictionary: Dictionary
    path: Path


def generate_config(
    repository: Path,
    source: str | Path,
    *,
    offline: bool = False,
) -> GeneratedConfig:
    """Refresh the shared base and generate a repository's configuration.

    Both entrypoints that write ``typos.toml`` -- the rollout CLI and the gate
    runner -- compose the operation here, so the two cannot drift into
    generating different configuration from the same base.

    Parameters
    ----------
    repository
        Repository root receiving the cache and generated configuration.
    source
        Local path or HTTPS URL for the authoritative shared base.
    offline
        Reuse an existing valid cache without contacting the source.

    Returns
    -------
    GeneratedConfig
        Refresh status, merged policy, and the path that was written.

    Raises
    ------
    OSError, ValueError, tomllib.TOMLDecodeError
        If refreshing, merging, rendering or replacing the file fails.
    """
    cache = repository / ".typos-oxendict-base.toml"
    result = refresh_base(
        source,
        cache,
        RefreshOptions(
            metadata=repository / ".typos-oxendict-base.json",
            offline=offline,
        ),
    )
    dictionary = load_dictionary(cache)
    local_overlay = repository / "typos.local.toml"
    if local_overlay.exists():
        dictionary = merge_dictionaries(
            dictionary,
            load_dictionary(local_overlay, local_overlay=True),
        )
    path = repository / "typos.toml"
    write_config(path, dictionary)
    return GeneratedConfig(status=result.status, dictionary=dictionary, path=path)


def _valid_cache(cache: Path) -> bool:
    """Report whether a cache contains a valid shared dictionary."""
    return typos_rollout_cache.valid_cache(
        cache,
        lambda content: _dictionary_from_text(content.decode()),
    )


def refresh_base(
    source: str | Path,
    cache: Path,
    options: RefreshOptions,
) -> RefreshResult:
    """Refresh an untracked base cache from its authoritative copy.

    Parameters
    ----------
    source
        Local path or HTTPS URL for the shared authority.
    cache
        Untracked local cache destination.
    options
        Metadata, offline-mode and HTTP-opening options.

    Returns
    -------
    RefreshResult
        Stable refresh status and validated cache path.
    """
    return typos_rollout_http.refresh_base(
        source,
        cache,
        typos_rollout_http.RefreshContext(
            options=options,
            validate=lambda content: _dictionary_from_text(content.decode()),
            atomic_write=_atomic_write,
            guarded_open=_HTTPS_OPENER.open,
        ),
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
    """
    dictionary = load_dictionary(SHARED_DICTIONARY_PATH)
    local_overlay = repository / "typos.local.toml"
    if local_overlay.exists():
        dictionary = merge_dictionaries(
            dictionary,
            load_dictionary(local_overlay, local_overlay=True),
        )
    return typos_rollout_harvest.harvest_repository(repository, dictionary)
