"""Error-path tests for the subagent_manifest helper module.

The happy paths are exercised by the definition regression suite in
``test_subagent_definitions.py``; these tests pin the fallibility
documented in the ``load_subagent_entry`` and ``load_provider`` docstrings
so the ``TypeError`` and ``LookupError`` contracts cannot regress silently.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import subagent_manifest
from subagent_manifest import load_provider, load_subagent_entry


@pytest.fixture
def point_manifest_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[[str], None]:
    """Return a helper that points the module manifest at a temporary file.

    Every test in this module redirects
    :data:`subagent_manifest.SUBAGENT_MANIFEST` at a temporary
    ``subagents.yml`` holding a bespoke payload, so the shared setup lives
    here as a fixture factory. The returned callable writes *content* to the
    temporary manifest and monkeypatches the module-level path to match.
    """

    def _redirect(content: str) -> None:
        manifest = tmp_path / "subagents.yml"
        manifest.write_text(content, encoding="utf-8")
        monkeypatch.setattr(subagent_manifest, "SUBAGENT_MANIFEST", manifest)

    return _redirect


@pytest.mark.parametrize(
    ("content", "call", "exc_type", "match"),
    [
        pytest.param(
            "- just\n- a\n- list\n",
            lambda: load_subagent_entry("wyvern"),
            TypeError,
            "manifest must be a mapping",
            id="non-mapping-root",
        ),
        pytest.param(
            "agent_tools_subagents: not-a-list\n",
            lambda: load_subagent_entry("wyvern"),
            TypeError,
            "'agent_tools_subagents' must be a list",
            id="non-list-entries",
        ),
        pytest.param(
            "agent_tools_subagents:\n  - just-a-string\n",
            lambda: load_subagent_entry("wyvern"),
            TypeError,
            "entry must be a mapping",
            id="non-mapping-entry",
        ),
        pytest.param(
            "agent_tools_subagents:\n  - name: wyvern\n",
            lambda: load_subagent_entry("ghost"),
            LookupError,
            "no subagent entry named 'ghost'",
            id="unknown-name",
        ),
        pytest.param(
            "agent_tools_subagents:\n  - name: wyvern\n",
            lambda: load_provider("wyvern", "claude"),
            TypeError,
            "must carry a 'providers' mapping",
            id="missing-providers-mapping",
        ),
        pytest.param(
            "agent_tools_subagents:\n"
            "  - name: wyvern\n"
            "    providers:\n"
            "      codex:\n"
            "        enabled: true\n",
            lambda: load_provider("wyvern", "claude"),
            LookupError,
            "has no 'claude' provider block",
            id="missing-provider-block",
        ),
        pytest.param(
            "agent_tools_subagents:\n"
            "  - name: wyvern\n"
            "    providers:\n"
            "      claude: not-a-mapping\n",
            lambda: load_provider("wyvern", "claude"),
            TypeError,
            "provider block must be a mapping",
            id="non-mapping-provider-block",
        ),
    ],
)
def test_loader_rejects_malformed_manifest(
    point_manifest_at: Callable[[str], None],
    content: str,
    call: Callable[[], object],
    exc_type: type[Exception],
    match: str,
) -> None:
    """A malformed manifest raises the documented error with a clear message.

    Each case pins one clause of the ``load_subagent_entry`` /
    ``load_provider`` fallibility contract: the raised exception type and
    the human-facing message a maintainer would see.
    """
    point_manifest_at(content)
    with pytest.raises(exc_type, match=match):
        call()
