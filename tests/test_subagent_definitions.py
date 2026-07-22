"""Regression tests for the subagent definitions in agents/subagents.yml.

These tests pin the deployment contracts of each managed subagent —
models, sandbox modes, tool grants, and the load-bearing prose in the
instruction bodies — so an edit that weakens a directive fails here
rather than silently degrading the provisioned agents.
"""

from __future__ import annotations

from typing import cast

import pytest
from subagent_manifest import (
    load_provider,
    load_subagent_entries,
    load_subagent_entry,
)

# Every managed subagent that ships a Claude Code provider block. The shared
# enabled/model contract is asserted once, parametrized over this tuple; the
# per-subagent tool grants are pinned by the dedicated tests below.
CLAUDE_SUBAGENTS = ("wyvern", "scribe", "alchemist", "scrutineer")


@pytest.mark.parametrize("name", CLAUDE_SUBAGENTS)
def test_claude_subagent_is_enabled_on_sonnet(name: str) -> None:
    """Each managed subagent is enabled on Claude Code and pinned to sonnet.

    Codex model selection is independent of the Claude provider; enabling the
    provider is what causes the agent definition to be rendered at all.
    """
    claude = load_provider(name, "claude")

    assert claude["enabled"] is True, f"{name} must be enabled on Claude Code"
    assert claude["model"] == "sonnet", (
        f"{name} must use sonnet on Claude Code"
    )


@pytest.mark.parametrize(
    ("name", "sandbox_mode"),
    (("wyvern", "read-only"), ("scribe", "workspace-write")),
)
def test_codex_subagent_uses_luna_model(
    name: str,
    sandbox_mode: str,
) -> None:
    """Wyvern and Scribe must request Luna with high effort on Codex."""
    codex = load_provider(name, "codex")

    assert codex["model"] == "gpt-5.6-luna", (
        f"{name} must use the Luna Codex model"
    )
    assert codex["reasoning_effort"] == "high", (
        f"{name} must use high reasoning effort"
    )
    assert codex["sandbox_mode"] == sandbox_mode, (
        f"{name} must retain {sandbox_mode} access"
    )


def test_scribe_claude_subagent_tools_are_exact() -> None:
    """Scribe's Claude tools must be exactly its documentation-editing set.

    Exact-set matching, rather than a subset check, ensures an unexpected
    extra Claude tool (for example ``Bash``) fails the test instead of
    slipping through untested.
    """
    claude = load_provider("scribe", "claude")

    tools = cast("list[str]", claude["tools"])
    assert set(tools) == {"Read", "Edit", "Write", "Grep", "Glob"}, (
        "Scribe's Claude tools must be exactly Read, Edit, Write, Grep, Glob "
        "so it can edit and navigate documentation but gains no other grants"
    )


def test_wyvern_claude_subagent_is_read_only() -> None:
    """Wyvern's Claude tooling must remain read-only to mirror the Codex sandbox."""
    claude = load_provider("wyvern", "claude")

    tools = cast("list[str]", claude["tools"])
    assert {"Read", "Grep", "Glob"} == set(tools), (
        "Wyvern's Claude tools must stay read-only (Read, Grep, Glob) to "
        "match the Codex read-only sandbox"
    )


def test_alchemist_codex_subagent_uses_terra_model_and_context_pack() -> None:
    """Alchemist's Codex entry must request Terra and the context pack MCP."""
    codex = load_provider("alchemist", "codex")

    assert codex["model"] == "gpt-5.6-terra", (
        "Alchemist must use the Terra Codex model for falsification work"
    )
    assert codex["reasoning_effort"] == "medium", (
        "Alchemist must keep medium reasoning effort"
    )
    assert codex["sandbox_mode"] == "workspace-write", (
        "Alchemist must retain workspace-write access for instrumentation"
    )
    mcp_servers = cast("list[str]", codex["mcp_servers"])
    assert "context_pack" in mcp_servers, (
        "Alchemist must expose context_pack as the canonical handoff channel "
        "between planning agents and subagents"
    )
    nicknames = cast("list[str]", codex["nickname_candidates"])
    assert nicknames, "Alchemist must ship an alchemy-themed nickname pool"
    assert "flamel" in nicknames, (
        "Alchemist's nickname pool must draw from the alchemist tradition"
    )


def test_alchemist_claude_subagent_tools_are_exact() -> None:
    """Alchemist's Claude tools must be exactly its instrumentation set.

    Exact-set matching guards against an unexpected extra Claude tool
    slipping through untested, while still confirming Edit and Write are
    present so the subagent can add tests, fixtures, or scratch
    instrumentation.
    """
    claude = load_provider("alchemist", "claude")

    tools = cast("list[str]", claude["tools"])
    assert set(tools) == {"Bash", "Read", "Grep", "Glob", "Edit", "Write"}, (
        "Alchemist's Claude tools must be exactly Bash, Read, Grep, Glob, "
        "Edit, Write so it can instrument and run experiments but gains no "
        "other grants"
    )


def test_scrutineer_codex_subagent_has_context_pack_mcp() -> None:
    """Scrutineer's Codex entry must wire the context_pack MCP server."""
    codex = load_provider("scrutineer", "codex")

    assert codex["model"] == "gpt-5.6-luna", (
        "Scrutineer must use the Luna Codex model for gate runs"
    )
    assert codex["reasoning_effort"] == "medium", (
        "Scrutineer must use medium reasoning effort"
    )
    assert codex["sandbox_mode"] == "workspace-write", (
        "Scrutineer needs workspace-write so gate caches can be written"
    )
    mcp_servers = cast("list[str]", codex["mcp_servers"])
    assert "context_pack" in mcp_servers, (
        "Scrutineer must expose the context_pack MCP server so it can hand "
        "structured artefacts back to a connected planning agent"
    )
    nicknames = cast("list[str]", codex["nickname_candidates"])
    assert nicknames, "Scrutineer must ship an engineer/scientist nickname pool"
    assert "turing" in nicknames, (
        "Scrutineer's nickname pool must draw from engineers and scientists"
    )


def test_scrutineer_claude_subagent_is_read_only() -> None:
    """Scrutineer's Claude tooling must stay read-only: no Edit or Write."""
    claude = load_provider("scrutineer", "claude")

    tools = cast("list[str]", claude["tools"])
    assert {"Bash", "Read", "Grep", "Glob"} == set(tools), (
        "Scrutineer's Claude tools must be exactly Bash, Read, Grep, Glob so "
        "the subagent can run and inspect gates but never edit tracked files"
    )


def test_every_subagent_enables_the_goose_provider() -> None:
    """Every subagent manifest entry enables the goose provider."""
    for entry in load_subagent_entries():
        providers = cast("dict[str, object]", entry["providers"])
        goose = cast("dict[str, object]", providers.get("goose", {}))
        assert goose.get("enabled") is True, (
            f"subagent {entry.get('name')!r} must enable the goose provider so "
            "its recipe is rendered"
        )


def _normalized(text: str) -> str:
    """Collapse all whitespace runs in *text* to single spaces.

    Prose contracts must survive re-wrapping of hard-wrapped Markdown and
    YAML blocks, so phrase assertions run against a whitespace-normalized
    view rather than the raw text.
    """
    return " ".join(text.split())


def _scrutineer_instructions() -> str:
    """Return scrutineer's provider-neutral instructions body."""
    entry = load_subagent_entry("scrutineer")
    return cast("str", entry["instructions"])


def test_scrutineer_scopes_docs_only_changes_to_markdown_gates() -> None:
    """Scrutineer must scope docs-only diffs to the Markdown gates.

    Running the code gates on a diff that touches only Markdown wastes
    wall-clock time and planner tokens without changing the verdict, so the
    instructions must carry an explicit docs-only scoping rule with a
    planner override.
    """
    instructions = _normalized(_scrutineer_instructions())

    assert "Docs-only scoping" in instructions, (
        "Scrutineer's gate selection must name a docs-only scoping rule so "
        "documentation diffs do not trigger the full code-gate set"
    )
    assert "every changed path ends in `.md`" in instructions, (
        "The docs-only rule must be triggered only when every changed path "
        "ends in `.md`, so a mixed diff still runs the full gate set"
    )
    assert "`make markdownlint` and `make nixie`" in instructions, (
        "The docs-only rule must still run both documentation gates"
    )
    assert "overrides this scoping" in instructions, (
        "The docs-only rule must state that an explicit planner instruction "
        "overrides the scoping so the planner can always demand a full run"
    )


def test_scrutineer_report_marks_logs_as_canonical_evidence() -> None:
    """Scrutineer's report must direct the planner to the captured logs.

    The token saving from delegating gate runs is lost if the planning
    agent re-runs a gate to see its output, so the fixed report structure
    must carry a line telling the planner to read the cited log files
    instead.
    """
    raw = _scrutineer_instructions()
    instructions = _normalized(raw)

    assert "- Gate scope:" in raw, (
        "The Gate Run Report header must record the gate scope so the "
        "planner can see whether a docs-only or planner-directed scoping "
        "was applied"
    )
    assert "- Logs: canonical evidence under `/tmp`" in raw, (
        "The Gate Run Report header must mark the /tmp logs as canonical evidence"
    )
    assert "read the cited files instead of re-running gates" in instructions, (
        "The report must tell the planner to read the cited log files "
        "rather than re-running gates, or the delegation saves nothing"
    )
