"""Shared access to the subagent manifest for the definition tests.

The manifest at ``agents/subagents.yml`` is the public source of truth for
the managed subagent definitions. The regression tests source each entry's
``description``, ``instructions``, and provider blocks through this module
so a future edit that weakens a directive surfaces as a test failure rather
than silently diverging from a hard-coded copy.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import yaml

SUBAGENT_MANIFEST: Path = (
    Path(__file__).resolve().parents[1] / "agents" / "subagents.yml"
)


def _load_manifest_entries() -> list[object]:
    """Read and structurally validate the manifest, returning the raw entries list.

    Raises
    ------
    OSError
        If the manifest file cannot be read (for example
        ``FileNotFoundError`` when it is absent or ``PermissionError`` on
        insufficient rights).
    yaml.YAMLError
        If the manifest file does not contain valid YAML.
    TypeError
        If the manifest root is not a mapping or ``agent_tools_subagents``
        is missing or not a list.
    """
    data = yaml.safe_load(SUBAGENT_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "manifest must be a mapping"
        raise TypeError(msg)
    raw_entries = data.get("agent_tools_subagents")
    if not isinstance(raw_entries, list):
        msg = "'agent_tools_subagents' must be a list"
        raise TypeError(msg)
    return typ.cast("list[object]", raw_entries)


def _validated_entry(raw_entry: object) -> dict[str, object]:
    """Assert *raw_entry* is a mapping and return it as a typed dict.

    Raises
    ------
    TypeError
        If *raw_entry* is not a mapping.
    """
    if not isinstance(raw_entry, dict):
        msg = (
            "each 'agent_tools_subagents' entry must be a mapping, got "
            f"{type(raw_entry).__name__}"
        )
        raise TypeError(msg)
    return typ.cast("dict[str, object]", raw_entry)


def load_subagent_entries() -> list[dict[str, object]]:
    """Return every manifest entry as a validated mapping.

    Raises
    ------
    OSError
        If the manifest file cannot be read (propagated from
        :func:`_load_manifest_entries`).
    yaml.YAMLError
        If the manifest file does not contain valid YAML (propagated from
        :func:`_load_manifest_entries`).
    TypeError
        If the manifest root is not a mapping, its ``agent_tools_subagents``
        value is missing or not a list, or any entry in that list is not a
        mapping.
    """
    return [_validated_entry(raw_entry) for raw_entry in _load_manifest_entries()]


def load_subagent_entry(name: str) -> dict[str, object]:
    """Return the manifest entry whose ``name`` matches the supplied value.

    Raises
    ------
    OSError
        If the manifest file cannot be read (propagated from
        :func:`_load_manifest_entries`).
    yaml.YAMLError
        If the manifest file does not contain valid YAML (propagated from
        :func:`_load_manifest_entries`).
    TypeError
        If the manifest root is not a mapping, its ``agent_tools_subagents``
        value is missing or not a list, or any entry in that list is not a
        mapping.
    LookupError
        If no entry in the manifest has a ``name`` field equal to ``name``.
    """
    for entry in load_subagent_entries():
        if entry.get("name") == name:
            return entry
    msg = f"no subagent entry named {name!r}"
    raise LookupError(msg)


def load_provider(name: str, provider: str) -> dict[str, object]:
    """Return the named subagent's provider sub-mapping from the manifest.

    Raises
    ------
    OSError
        If the manifest file cannot be read (propagated from
        :func:`load_subagent_entry`).
    yaml.YAMLError
        If the manifest file does not contain valid YAML (propagated from
        :func:`load_subagent_entry`).
    TypeError
        If the entry has no ``providers`` mapping or the named provider
        value is not a mapping. Also propagates the ``TypeError`` raised by
        :func:`load_subagent_entry` for a malformed manifest root.
    LookupError
        If the entry has no ``provider`` block. Also propagates the
        no-such-entry ``LookupError`` from :func:`load_subagent_entry`.
    """
    entry = load_subagent_entry(name)
    raw_providers = entry.get("providers")
    if not isinstance(raw_providers, dict):
        msg = f"subagent {name!r} must carry a 'providers' mapping"
        raise TypeError(msg)
    providers = typ.cast("dict[str, object]", raw_providers)
    if provider not in providers:
        msg = f"subagent {name!r} has no {provider!r} provider block"
        raise LookupError(msg)
    provider_block = providers[provider]
    if not isinstance(provider_block, dict):
        msg = f"subagent {name!r} {provider!r} provider block must be a mapping"
        raise TypeError(msg)
    return typ.cast("dict[str, object]", provider_block)
