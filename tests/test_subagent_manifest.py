"""Error-path tests for the subagent_manifest helper module.

The happy paths are exercised by the definition regression suite in
``test_subagent_definitions.py``; these tests pin the fallibility
documented in the ``load_subagent_entry`` and ``load_provider`` docstrings
so the ``TypeError`` and ``LookupError`` contracts cannot regress silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import subagent_manifest
from subagent_manifest import load_provider, load_subagent_entry


def _point_manifest_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: str
) -> None:
    """Redirect the module's manifest path at a temporary file holding *content*."""
    manifest = tmp_path / "subagents.yml"
    manifest.write_text(content, encoding="utf-8")
    monkeypatch.setattr(subagent_manifest, "SUBAGENT_MANIFEST", manifest)


def test_load_subagent_entry_rejects_non_mapping_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest whose root is not a mapping fails with a clear TypeError."""
    _point_manifest_at(monkeypatch, tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(TypeError, match="manifest must be a mapping"):
        load_subagent_entry("wyvern")


def test_load_subagent_entry_rejects_non_list_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A non-list ``agent_tools_subagents`` value fails with a clear TypeError."""
    _point_manifest_at(monkeypatch, tmp_path, "agent_tools_subagents: not-a-list\n")
    with pytest.raises(TypeError, match="'agent_tools_subagents' must be a list"):
        load_subagent_entry("wyvern")


def test_load_subagent_entry_rejects_non_mapping_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A list item that is not a mapping fails with a clear TypeError."""
    _point_manifest_at(
        monkeypatch, tmp_path, "agent_tools_subagents:\n  - just-a-string\n"
    )
    with pytest.raises(TypeError, match="entry must be a mapping"):
        load_subagent_entry("wyvern")


def test_load_subagent_entry_raises_lookup_error_for_unknown_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An absent subagent name surfaces as a LookupError naming the slug."""
    _point_manifest_at(
        monkeypatch, tmp_path, "agent_tools_subagents:\n  - name: wyvern\n"
    )
    with pytest.raises(LookupError, match="no subagent entry named 'ghost'"):
        load_subagent_entry("ghost")


def test_load_provider_rejects_entry_without_providers_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry lacking a providers mapping fails with a clear TypeError."""
    _point_manifest_at(
        monkeypatch, tmp_path, "agent_tools_subagents:\n  - name: wyvern\n"
    )
    with pytest.raises(TypeError, match="must carry a 'providers' mapping"):
        load_provider("wyvern", "claude")


def test_load_provider_raises_lookup_error_for_missing_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing provider key surfaces as a LookupError naming the provider."""
    content = (
        "agent_tools_subagents:\n"
        "  - name: wyvern\n"
        "    providers:\n"
        "      codex:\n"
        "        enabled: true\n"
    )
    _point_manifest_at(monkeypatch, tmp_path, content)
    with pytest.raises(LookupError, match="has no 'claude' provider block"):
        load_provider("wyvern", "claude")


def test_load_provider_rejects_non_mapping_provider_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A provider block that is not a mapping fails with a clear TypeError."""
    content = (
        "agent_tools_subagents:\n"
        "  - name: wyvern\n"
        "    providers:\n"
        "      claude: not-a-mapping\n"
    )
    _point_manifest_at(monkeypatch, tmp_path, content)
    with pytest.raises(TypeError, match="provider block must be a mapping"):
        load_provider("wyvern", "claude")
