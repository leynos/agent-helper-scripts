"""Expand Oxford spellings and render deterministic Typos configuration."""

from collections.abc import Callable
import json
from pathlib import Path
import tomllib
from typing import Protocol

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


class RenderPolicy(Protocol):
    """Expose dictionary fields consumed by deterministic rendering.

    Attributes
    ----------
    stems, accepted, corrections
        Oxford families, accepted vocabulary and explicit corrections.
    ignore_patterns, excluded_files
        Generated Typos masking and file-exclusion policy.
    """

    stems: tuple[str, ...]
    accepted: tuple[str, ...]
    corrections: tuple[tuple[str, str], ...]
    ignore_patterns: tuple[str, ...]
    excluded_files: tuple[str, ...]


def generate_word_mappings(dictionary: RenderPolicy) -> dict[str, str]:
    """Expand Oxford stems and explicit words into deterministic mappings.

    Parameters
    ----------
    dictionary
        Spelling policy to expand.

    Returns
    -------
    dict[str, str]
        Sorted source-word-to-correction mappings for Typos.

    Raises
    ------
    ValueError
        If generated and explicit corrections conflict.
    """
    mappings = {word: word for word in dictionary.accepted}

    def add(word: str, correction: str) -> None:
        existing = mappings.get(word)
        if existing is not None and existing != correction:
            message = (
                f"conflicting generated correction for {word!r}: "
                f"{existing!r} != {correction!r}"
            )
            raise ValueError(message)
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
    return [f"{name} = [", *(f"    {_toml_string(value)}," for value in values), "]"]


def render_typos_config(dictionary: RenderPolicy) -> str:
    """Render a deterministic, parse-checked ``typos.toml`` document.

    Parameters
    ----------
    dictionary
        Validated spelling policy to render.

    Returns
    -------
    str
        Complete generated TOML document ending in one newline.

    Raises
    ------
    ValueError, tomllib.TOMLDecodeError
        If mappings conflict or the generated document does not parse.
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


def write_config(
    path: Path,
    dictionary: RenderPolicy,
    atomic_write: Callable[[Path, bytes], None],
) -> None:
    """Atomically write validated generated configuration.

    Parameters
    ----------
    path
        Destination ``typos.toml`` path.
    dictionary
        Validated spelling policy to render.
    atomic_write
        Persistence callback supplied by the stable facade.

    Raises
    ------
    OSError, ValueError, tomllib.TOMLDecodeError
        If rendering, writing or atomic replacement fails.
    """
    atomic_write(path, render_typos_config(dictionary).encode())
