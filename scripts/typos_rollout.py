#!/usr/bin/env -S uv run python
# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4.3,<5", "plumbum>=1.9,<2"]
# ///
"""Harvest and generate shared en-GB-oxendict ``typos`` configuration."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
DEFAULT_BASE_URL = (
    "https://raw.githubusercontent.com/leynos/agent-helper-scripts/"
    "refs/heads/main/data/typos-oxendict-base.toml"
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
    """Curated words and exclusions used to generate a ``typos`` config."""

    stems: tuple[str, ...] = ()
    accepted: tuple[str, ...] = ()
    corrections: tuple[tuple[str, str], ...] = ()
    ignore_patterns: tuple[str, ...] = ()
    excluded_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshResult:
    """Describe whether the untracked shared dictionary cache changed."""

    status: str
    cache: Path


class Response(Protocol):
    """Structural type for the small HTTP response surface used here."""

    status: int
    headers: Mapping[str, str]

    def read(self) -> bytes:
        """Return the response body."""

    def __enter__(self) -> "Response":
        """Enter the response context."""

    def __exit__(self, *args: object) -> None:
        """Leave the response context."""


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
    return value


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
    return Dictionary(
        stems=_string_list(oxford, "stems"),
        accepted=_string_list(words, "accepted"),
        corrections=tuple(sorted(corrections_table.items())),
        ignore_patterns=_string_list(patterns, "ignore"),
        excluded_files=_string_list(files, "exclude"),
    )


def load_dictionary(path: Path) -> Dictionary:
    """Load a validated shared dictionary from *path*."""
    return _dictionary_from_text(path.read_text(encoding="utf-8"))


def merge_dictionaries(base: Dictionary, local: Dictionary) -> Dictionary:
    """Merge a shared dictionary with a non-conflicting local overlay."""
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
    """Expand Oxford stems and explicit words into deterministic mappings."""
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
    """Render a deterministic, parse-checked ``typos.toml`` document."""
    lines = [
        "# Generated from the shared en-GB-oxendict dictionary.",
        "# Regenerate with scripts/typos_rollout.py; do not edit by hand.",
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
    """Atomically write validated generated configuration to *path*."""
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
    if cache.exists() and source.stat().st_mtime_ns <= cache.stat().st_mtime_ns:
        if not _valid_cache(cache):
            raise ValueError(f"cached shared dictionary is invalid: {cache}")
        return RefreshResult("current", cache)
    content = source.read_bytes()
    _dictionary_from_text(content.decode())
    _atomic_write(cache, content)
    os.utime(cache, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
    _write_metadata(
        metadata,
        {"source": str(source.resolve()), "mtime_ns": source.stat().st_mtime_ns},
    )
    return RefreshResult("refreshed", cache)


def refresh_base(
    source: str | Path,
    cache: Path,
    *,
    metadata: Path,
    offline: bool = False,
    opener: Callable[..., Response] = urlopen,
) -> RefreshResult:
    """Refresh an untracked base cache when the authoritative copy is newer."""
    source_text = str(source)
    if offline:
        if not _valid_cache(cache):
            raise FileNotFoundError(f"no cached shared dictionary at {cache}")
        return RefreshResult("offline-cache", cache)
    if isinstance(source, Path) or "://" not in source_text:
        return _refresh_local(Path(source_text), cache, metadata)

    saved = _read_metadata(metadata)
    headers = {}
    if isinstance(saved.get("etag"), str):
        headers["If-None-Match"] = saved["etag"]
    if isinstance(saved.get("last_modified"), str):
        headers["If-Modified-Since"] = saved["last_modified"]
    request = Request(source_text, headers=headers)
    try:
        with opener(request, timeout=30.0) as response:
            if response.status == 304 and _valid_cache(cache):
                return RefreshResult("current", cache)
            if _valid_cache(cache) and _remote_is_not_newer(saved, response.headers):
                return RefreshResult("current", cache)
            content = response.read()
            _dictionary_from_text(content.decode())
            _atomic_write(cache, content)
            _write_metadata(
                metadata,
                {
                    "source": source_text,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                },
            )
    except HTTPError as error:
        if error.code == 304 and _valid_cache(cache):
            return RefreshResult("current", cache)
        if _valid_cache(cache):
            return RefreshResult("stale-cache", cache)
        raise
    except (OSError, URLError):
        if _valid_cache(cache):
            return RefreshResult("stale-cache", cache)
        raise
    return RefreshResult("refreshed", cache)


def harvest_oxford_forms(text: str) -> tuple[str, ...]:
    """Return normalized `-ise` and `-ize` candidates found in *text*."""
    return tuple(sorted({match.group(0).casefold() for match in OXFORD_FORM.finditer(text)}))


def harvest_repository(repository: Path) -> tuple[dict[str, object], ...]:
    """Harvest Oxford-form evidence from Git-tracked UTF-8 text files."""
    from plumbum import local

    with local.cwd(repository):
        tracked = local["git"]["ls-files", "-z"]()
    findings = []
    for relative in sorted(filter(None, tracked.split("\0"))):
        path = repository / relative
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(
            {"path": relative, "line": number, "forms": list(forms)}
            for number, line in enumerate(lines, start=1)
            if (forms := harvest_oxford_forms(line))
        )
    return tuple(findings)


def cli() -> None:
    """Run the environment-aware Cyclopts command-line interface."""
    import cyclopts
    from cyclopts import App

    app = App(config=cyclopts.config.Env("TYPOS_ROLLOUT_", command=False))

    @app.command
    def generate(
        repository: Path = Path.cwd(),
        source: str = DEFAULT_BASE_URL,
        offline: bool = False,
    ) -> None:
        """Refresh the shared base and generate a repository's typos.toml."""
        cache = repository / ".typos-oxendict-base.toml"
        result = refresh_base(
            source,
            cache,
            metadata=repository / ".typos-oxendict-base.json",
            offline=offline,
        )
        dictionary = load_dictionary(cache)
        local_overlay = repository / "typos.local.toml"
        if local_overlay.exists():
            dictionary = merge_dictionaries(dictionary, load_dictionary(local_overlay))
        write_config(repository / "typos.toml", dictionary)
        print(f"{result.status}: {repository / 'typos.toml'}")

    @app.command
    def harvest(repository: Path = Path.cwd()) -> None:
        """Print JSON Lines evidence for Oxford-form candidates."""
        for finding in harvest_repository(repository):
            print(json.dumps(finding, sort_keys=True))

    app()


if __name__ == "__main__":
    cli()
