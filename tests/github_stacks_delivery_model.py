"""Offline model of the GitHub-stacks delivery documentation, not a CLI mock.

The delivery contract supplies frontier priority and candidate-bound gates;
``references/partial-delivery.md`` supplies leases, receipts and reconciliation.
Integers represent distinct object IDs. This model cannot validate GitHub or
managed stack integration; the companion bare-remote tests exercise real Git.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Layer:
    """One PR's candidate and independently observed delivery evidence."""

    candidate: int
    remote: int = 0
    github: int = 0
    base: int = -1
    github_base: int = -1
    replay: int | None = None
    gates: int | None = None
    lease: int | None = None
    published: int | None = None
    readback: int | None = None
    receipt: tuple[int, int] | None = None
    tracking: tuple[int, ...] | None = None
    stage: int = 0
    stage_candidate: int | None = None


class Delivery:
    """Model an authorized linear stack with an already merged lower prefix.

    ``stage`` separates publication (0), ready (1), review request (2),
    completed review (3), and merge (4). Hosting approval/protection decisions
    are an external premise, not inferred from publication evidence.
    """

    def __init__(self, depth: int, merged: int = 0) -> None:
        self.layers = [
            Layer(candidate=i + 1, base=i - 1, github_base=i - 1)
            for i in range(depth)
        ]
        self.frontier = merged
        self.tracking_required = False
        for layer in self.layers[:merged]:
            layer.stage = 4

    def remote_heads(self) -> tuple[int, ...]:
        """Return the complete remote observation used for reconciliation."""
        return tuple(layer.remote for layer in self.layers)

    def observe(self, index: int, action: str) -> None:
        """Collect one piece of evidence without advancing hosted lifecycle."""
        layer = self.layers[index]
        if action == "replay":
            layer.replay = layer.candidate
        elif action == "gates" and layer.replay == layer.candidate:
            layer.gates = layer.candidate
        elif action == "lease":
            layer.lease = layer.remote
        elif action == "readback" and layer.published == layer.candidate:
            layer.readback = layer.remote
        elif action == "receipt" and layer.readback == layer.candidate:
            layer.receipt = (layer.github, layer.github_base)
        elif action == "tracking":
            # Re-read every remote head before reconciling, even if an earlier
            # write published a different candidate or succeeded only partly.
            layer.tracking = self.remote_heads()
            self.tracking_required = False

    def push(self, index: int) -> bool:
        """Publish exactly the selected SHA using the previously read lease."""
        layer = self.layers[index]
        if (
            index != self.frontier
            or self.tracking_required
            or layer.gates != layer.candidate
            or layer.lease != layer.remote
        ):
            if layer.lease is not None and layer.lease != layer.remote:
                layer.replay = layer.gates = None
            return False
        layer.remote = layer.candidate
        layer.published = layer.candidate
        layer.readback = None
        layer.receipt = None
        layer.tracking = None
        self.tracking_required = True
        return True

    def delivered(self, index: int) -> bool:
        """Require current exact-candidate receipts before a managed write."""
        layer = self.layers[index]
        return (
            layer.replay == layer.gates == layer.published == layer.candidate
            and layer.readback == layer.remote == layer.candidate
            and layer.receipt == (layer.candidate, layer.base)
            and (layer.github, layer.github_base) == layer.receipt
            and layer.tracking == self.remote_heads()
        )

    def advance(self, index: int) -> bool:
        """Advance one authorized hosted stage, never infer review from push."""
        layer = self.layers[index]
        if index != self.frontier or not self.delivered(index) or layer.stage == 4:
            return False
        if layer.stage_candidate != layer.candidate:
            layer.stage = 0
            layer.stage_candidate = layer.candidate
        layer.stage += 1
        if layer.stage == 4:
            self.frontier += 1
            if self.frontier < len(self.layers):
                child = self.layers[self.frontier]
                child.base = -1
                child.replay = child.gates = None
        return True

    def stack_result(self, successes: set[int]) -> None:
        """Observe non-atomic stack publication; exit status supplies no receipt.

        This models an external outcome, not authorization for this recovery
        owner to publish descendants. Every affected ref needs fresh readback.
        """
        for index, layer in enumerate(self.layers):
            if index in successes:
                layer.remote = layer.candidate
                layer.published = layer.candidate
            layer.readback = None
            layer.receipt = None
            layer.tracking = None
        self.tracking_required = True
