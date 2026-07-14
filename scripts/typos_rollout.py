"""Generate shared en-GB-oxendict Typos policy through a stable facade.

The facade preserves the rollout helper's public import surface while cohesive
modules own policy validation, cache persistence, HTTPS refresh, phrase checks,
and Oxford-form harvesting.
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
SUFFIX_PAIRS = typos_rollout_render.SUFFIX_PAIRS

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


@dataclass(frozen=True)
class Dictionary:
    """Curated words and exclusions used to generate a Typos config.

    Attributes
    ----------
    stems
        Oxford ``-ize`` stems expanded through supported suffix pairs.
    accepted
        Words accepted exactly as written.
    corrections
        Explicit source-to-correction word pairs.
    phrase_corrections
        Punctuation-separated phrase corrections checked outside Typos.
    ignore_patterns
        Bounded regular expressions used to mask upstream text.
    excluded_files
        Repository-relative components and globs omitted from spelling scans.
    """

    stems: tuple[str, ...] = ()
    accepted: tuple[str, ...] = ()
    corrections: tuple[tuple[str, str], ...] = ()
    phrase_corrections: tuple[tuple[str, str], ...] = ()
    ignore_patterns: tuple[str, ...] = ()
    excluded_files: tuple[str, ...] = ()


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


def _merge_correction_items(
    base: tuple[tuple[str, str], ...],
    local: tuple[tuple[str, str], ...],
    *,
    label: str,
) -> tuple[tuple[str, str], ...]:
    """Merge corrections while rejecting conflicting replacements."""
    merged = dict(base)
    for source, correction in local:
        existing = merged.get(source)
        if existing is not None and existing != correction:
            message = (
                f"conflicting {label} for {source!r}: "
                f"{existing!r} != {correction!r}"
            )
            raise ValueError(message)
        merged[source] = correction
    return tuple(sorted(merged.items()))


def merge_dictionaries(base: Dictionary, local: Dictionary) -> Dictionary:
    """Merge a shared dictionary with a non-conflicting local overlay.

    Parameters
    ----------
    base
        Complete shared spelling policy.
    local
        Sparse repository-specific policy additions.

    Returns
    -------
    Dictionary
        Deterministically ordered union of both policies.

    Raises
    ------
    ValueError
        If corrections conflict or local exceptions weaken shared policy.
    """
    typos_rollout_policy.validate_local_exceptions(
        local.ignore_patterns,
        local.excluded_files,
    )
    return Dictionary(
        stems=tuple(sorted(set(base.stems) | set(local.stems))),
        accepted=tuple(sorted(set(base.accepted) | set(local.accepted))),
        corrections=_merge_correction_items(
            base.corrections,
            local.corrections,
            label="correction",
        ),
        phrase_corrections=_merge_correction_items(
            base.phrase_corrections,
            local.phrase_corrections,
            label="phrase correction",
        ),
        ignore_patterns=tuple(
            sorted(set(base.ignore_patterns) | set(local.ignore_patterns))
        ),
        excluded_files=tuple(
            sorted(set(base.excluded_files) | set(local.excluded_files))
        ),
    )


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
