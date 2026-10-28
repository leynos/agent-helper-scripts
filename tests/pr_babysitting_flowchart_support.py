"""Parse and walk the users' guide PR-babysitting Mermaid flowcharts.

The contract tests use the parsed edges to check routing, and the trust
property tests walk the shipped decision graph with generated answers. Both
read the same parse, so a diagram the parser cannot read fails every consumer
rather than passing silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
USERS_GUIDE = ROOT / "docs/users-guide.md"
TRUST_CHART = "Candidate trust decision for PR babysitting"
LIFECYCLE_CHART = "PR babysitting path to equilibrium, merge, or impasse"

NODE = r'(\w+)(?:\["([^"]*)"\]|\[([^\]]*)\]|\{([^}]*)\})?'
EDGE = re.compile(rf"^\s*{NODE}\s*-->(?:\|([^|]*)\|)?\s*{NODE}\s*$")
LINK_SYNTAX = re.compile(r"-->|==>|-\.->|--\s|\s&\s")
ACC_DESCR = re.compile(r"accDescr \{\n(.*?)\n\s*\}", re.S)
FENCE_AND_CAPTION = re.compile(r"^```mermaid\n(.*?)^```\n(?:\n(\*[^*]*\*)\n)?", re.M | re.S)


@dataclass(frozen=True)
class Flowchart:
    """Node labels, labelled edges, and accessible text parsed from one Mermaid flowchart."""

    labels: dict[str, str]
    edges: frozenset[tuple[str, str, str]]
    description: str
    caption: str

    def node(self, label: str) -> str:
        """Return the unique node ID carrying ``label``."""
        ids = [node for node, text in self.labels.items() if text == label]
        assert len(ids) == 1, f"expected one node labelled {label!r}, found {ids}"
        return ids[0]

    def predecessors(self, label: str) -> set[tuple[str, str]]:
        """Return (source label, edge label) pairs for edges into ``label``."""
        target = self.node(label)
        return {(self.labels[src], text) for src, text, dst in self.edges if dst == target}

    def successors(self, node: str) -> list[tuple[str, str]]:
        """Return (edge label, destination ID) pairs for edges out of ``node``."""
        return sorted((text, dst) for src, text, dst in self.edges if src == node)


def _edge_labels(groups: tuple[str | None, ...]) -> dict[str, str]:
    """Return the node labels declared inline on one parsed edge."""
    declared = ((groups[0], groups[1:4]), (groups[5], groups[6:9]))
    return {
        str(node): text
        for node, texts in declared
        if (text := next((t for t in texts if t is not None), None)) is not None
    }


def parse_flowchart(block: str, caption: str = "") -> Flowchart:
    """Parse one Mermaid flowchart block and its italic caption."""
    lines = ACC_DESCR.sub("", block).splitlines()
    unparsed = [line for line in lines if LINK_SYNTAX.search(line) and not EDGE.match(line)]
    assert not unparsed, f"unparsed flowchart link syntax: {unparsed}"
    labels: dict[str, str] = {}
    edges: set[tuple[str, str, str]] = set()
    for found in filter(None, map(EDGE.match, lines)):
        groups = found.groups()
        labels.update(_edge_labels(groups))
        edges.add((str(groups[0]), groups[4] or "", str(groups[5])))
    described = ACC_DESCR.search(block)
    description = " ".join(described.group(1).split()) if described else ""
    return Flowchart(labels, frozenset(edges), description, " ".join(caption.strip("*").split()))


def flowchart_source(title: str, guide: Path = USERS_GUIDE) -> tuple[str, str]:
    """Return the flowchart block whose ``accTitle`` is ``title``, and its caption."""
    matches = [
        (block, caption)
        for block, caption in FENCE_AND_CAPTION.findall(guide.read_text())
        if f"accTitle: {title}\n" in block
    ]
    assert len(matches) == 1, f"expected unique flowchart: {title}"
    return matches[0]


def _next_node(chart: Flowchart, node: str, answers: Mapping[str, bool]) -> str | None:
    """Follow one step: the sole plain edge, or the decision edge matching its answer."""
    out = chart.successors(node)
    if not out:
        return None
    if [text for text, _ in out] == [""]:
        return out[0][1]
    label = chart.labels[node]
    assert label in answers, f"no answer supplied for decision {label!r}"
    wanted = "Yes" if answers[label] else "No"
    chosen = [dst for text, dst in out if text.split(",")[0] == wanted]
    assert len(chosen) == 1, f"decision {label!r} has no unique {wanted!r} edge: {out}"
    return chosen[0]


def walk(chart: Flowchart, start: str, answers: Mapping[str, bool]) -> str:
    """Return the label of the terminal node reached from ``start`` under ``answers``."""
    node: str | None = chart.node(start)
    visited: list[str] = []
    while node is not None:
        assert node not in visited, f"decision walk revisited {chart.labels[node]!r}"
        visited.append(node)
        node = _next_node(chart, node, answers)
    return chart.labels[visited[-1]]


def reachable(chart: Flowchart, start: str) -> set[str]:
    """Return the labels of every node reachable from ``start``, including itself."""
    pending, seen = [chart.node(start)], set()
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(dst for _, dst in chart.successors(node))
    return {chart.labels[node] for node in seen}
