"""Pin the Natural Philosopher's deployment and step-design contracts.

These are manifest regression tests, not live-model behavioural evaluations.
The scenario checks in ADR 004 describe the additional review boundary.
"""

from __future__ import annotations

from typing import cast

import pytest
from subagent_manifest import (
    load_provider,
    load_subagent_entries,
    load_subagent_entry,
)

NAME = "natural-philosopher"


def test_natural_philosopher_is_unique_and_present() -> None:
    """Provision exactly one unambiguous definition using the existing schema."""
    entries = [entry for entry in load_subagent_entries() if entry["name"] == NAME]

    assert len(entries) == 1, (
        f"expected exactly one {NAME} definition, found {len(entries)}"
    )
    entry = entries[0]
    assert entry["state"] == "present", f"{NAME} is not provisioned as present"
    assert set(entry) == {
        "name", "state", "description", "instructions", "providers"
    }, f"{NAME} does not match the manifest entry schema"
    assert "before task-level ExecPlan planning" in " ".join(
        cast("str", entry["description"]).split()
    ), f"{NAME} description dropped its pre-ExecPlan boundary contract"


@pytest.mark.parametrize("provider_name", ["codex", "claude", "goose"])
def test_natural_philosopher_enables_each_provider(provider_name: str) -> None:
    """Enable the role for every provider supported by the manifest."""
    provider = load_provider(NAME, provider_name)

    assert provider["enabled"] is True, (
        f"{NAME} is not enabled for the {provider_name} provider"
    )
    if provider_name != "goose":
        assert provider["scope"] == "user", (
            f"{NAME} is not scoped to the user for the {provider_name} provider"
        )


def test_natural_philosopher_codex_contract() -> None:
    """Use the Terra planning tier, inherit MCPs, and name the role fittingly."""
    codex = load_provider(NAME, "codex")

    assert codex["model"] == "gpt-5.6-terra", (
        "the Codex contract no longer pins the repository's Terra planning tier"
    )
    assert codex["reasoning_effort"] == "high", (
        "the Codex contract no longer pins the high reasoning tier"
    )
    assert codex["sandbox_mode"] == "workspace-write", (
        "the Codex contract no longer pins workspace-write sandboxing"
    )
    assert "mcp_servers" not in codex, (
        "the Codex contract must inherit the parent's credentialed MCP registry"
    )
    nicknames = cast("list[str]", codex["nickname_candidates"])
    assert nicknames, (
        "the Codex contract must ship a natural-philosopher nickname pool"
    )
    assert "faraday" in nicknames, (
        "the nickname pool must draw from the natural philosophers"
    )


def test_natural_philosopher_claude_contract() -> None:
    """Allow document work and bounded research delegation, but no Bash grant."""
    claude = load_provider(NAME, "claude")
    extra = cast("dict[str, object]", claude["extra_frontmatter"])

    assert claude["model"] == "opus", (
        "the Claude contract no longer pins the opus planning model"
    )
    assert extra["effort"] == "high", (
        "the Claude contract no longer pins the high effort tier"
    )
    assert set(cast("list[str]", claude["tools"])) == {
        "Read", "Grep", "Glob", "Edit", "Write", "Task"
    }, "the Claude tool grant drifted from document work plus bounded delegation"
    assert set(cast("list[str]", extra["mcpServers"])) == {
        "context_pack", "firecrawl", "deepwiki", "codegraph"
    }, "the Claude MCP allow-list drifted from the research contract"


def test_natural_philosopher_goose_inherits_extensions() -> None:
    """Do not replace the parent's credentialed extension registry."""
    assert "extensions" not in load_provider(NAME, "goose"), (
        "the goose contract must inherit the parent's extension registry"
    )


@pytest.mark.parametrize(
    "required",
    [
        "Goal: the parent-owned outcome",
        "Idea = roadmap phase: a falsifiable bet",
        "Step = workstream: one coherent delivery objective",
        "Task = execution unit",
        "A step is not a task or an ExecPlan milestone",
        "one selected idea to proposed steps",
        "GitHub tracks the work; Linear tracks the programme",
        "never mirror every GitHub issue or PR into a Linear issue",
        "Load roadmap-doc and read its references/conventions.md",
        "Record the revision used",
        "Uncertainty about how the system works is your subject of inquiry",
        "including retaining the current behaviour",
        "baseline or comparator",
        "correctness and safety invariants",
        "Define thresholds and decision rules before observing trial results",
        "Do not invent baseline measurements or move the goalposts",
        "untested | falsified | not-falsified | inconclusive",
        "Prefer usable vertical slices",
        "Keep dependencies acyclic",
        "preserve existing IDs, completion evidence, and unrelated status",
        "Weave unit and behavioural tests, property tests, and formal verification",
        "Dedicated E2E/combinatorial suites are legitimate tasks",
        "Account for every relevant source obligation",
        "Do not promise dates or durations",
        "Absent experiment authority means design only",
        "only with explicit experiment authority",
        "Do not delegate to another natural-philosopher",
        "or commission journeyman or artisan implementation",
        "uncompletable exit clauses",
        "Children may not redelegate",
        "Inspect returned evidence yourself",
        "pack ID and a short summary",
        "Edit only explicitly assigned roadmap or design-document paths",
        "Tool availability is not permission",
        "Research recommendations do not approve themselves",
        "Never mark a step, idea, or goal complete merely because",
        "Stop and escalate when",
        "Stop affected work safely",
        "Return a Step Design Report",
        "status: ready-for-review | escalated",
    ],
)
def test_natural_philosopher_retains_load_bearing_contract(required: str) -> None:
    """Catch accidental removal of a boundary while tolerating prose wrapping."""
    entry = load_subagent_entry(NAME)
    instructions = " ".join(cast("str", entry["instructions"]).split())

    assert required in instructions, f"Missing Natural Philosopher contract: {required}"
