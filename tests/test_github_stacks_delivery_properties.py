"""Bounded offline stateful checks of documented delivery obligations.

The model is a specification rehearsal, not executable skill enforcement or
live GitHub testing. Named traces and omitted-step mutations keep successful
delivery reachable and show that individual safeguards matter independently.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
import pytest

from github_stacks_delivery_model import Delivery


STEPS = ("replay", "gates", "lease", "push", "readback", "receipt", "tracking")


def complete(delivery: Delivery, index: int, omit: str = "") -> None:
    """Rehearse the documented happy path, optionally deleting one operation."""
    for action in STEPS:
        if action == omit:
            continue
        if action == "push":
            delivery.push(index)
            delivery.layers[index].github = delivery.layers[index].remote
        else:
            delivery.observe(index, action)


class DeliveryMachine(RuleBasedStateMachine):
    """Generate movements and interleavings across one to four stack layers."""

    @initialize(depth=st.integers(1, 4), prefix=st.integers(0, 3))
    def start(self, depth: int, prefix: int) -> None:
        """Vary stack depth and the initially selected merge frontier."""
        self.delivery = Delivery(depth, prefix % depth)
        self.serial = 10
        self.accepted: set[tuple[int, int]] = set()

    @rule(index=st.integers(0, 3), action=st.sampled_from(STEPS))
    def operation(self, index: int, action: str) -> None:
        """Attempt evidence and pushes in arbitrary, often premature order."""
        index %= len(self.delivery.layers)
        layer = self.delivery.layers[index]
        before = self.delivery.remote_heads()
        candidate = layer.candidate
        lease, gates, replay = layer.lease, layer.gates, layer.replay
        if action == "push":
            accepted = self.delivery.push(index)
            if accepted:
                assert index == self.delivery.frontier, "push bypassed the merge frontier"
                assert lease == before[index], "push accepted a stale explicit lease"
                assert gates == replay == candidate, "push lacked candidate-bound gates"
                assert layer.remote == layer.candidate, "push published a different SHA"
                self.accepted.add((index, layer.candidate))
            else:
                assert self.delivery.remote_heads() == before
            assert all(
                old == new for position, (old, new) in enumerate(
                    zip(before, self.delivery.remote_heads(), strict=True)
                ) if position != index
            )
        else:
            self.delivery.observe(index, action)

    @rule(index=st.integers(0, 3), field=st.sampled_from(
        ("candidate", "remote", "github", "github_base")
    ))
    def move(self, index: int, field: str) -> None:
        """Generate new candidates, competing pushes and server rewrites."""
        self.serial += 1
        layer = self.delivery.layers[index % len(self.delivery.layers)]
        setattr(layer, field, self.serial)

    @rule(mask=st.integers(0, 15))
    def partial_stack_result(self, mask: int) -> None:
        """Any subset of a stack-wide push may succeed, even after failure."""
        successes = {i for i in range(len(self.delivery.layers)) if mask & (1 << i)}
        before = self.delivery.remote_heads()
        self.delivery.stack_result(successes)
        self.accepted.update(
            (index, self.delivery.layers[index].candidate) for index in successes
        )
        for index, layer in enumerate(self.delivery.layers):
            assert layer.remote == (layer.candidate if index in successes else before[index])
            assert not self.delivery.delivered(index)

    @rule()
    def finish_frontier(self) -> None:
        """Ensure generated histories also reach a full successful receipt."""
        index = self.delivery.frontier
        if index == len(self.delivery.layers):
            return
        layer = self.delivery.layers[index]
        if self.delivery.tracking_required:
            self.delivery.observe(index, "tracking")
        layer.github_base = layer.base
        complete(self.delivery, index)
        self.accepted.add((index, layer.candidate))
        assert self.delivery.delivered(index)

    @rule(index=st.integers(0, 3))
    def hosted_stage(self, index: int) -> None:
        """Try hosted transitions independently of publication and receipts."""
        index %= len(self.delivery.layers)
        layer = self.delivery.layers[index]
        previous = layer.stage if layer.stage_candidate == layer.candidate else 0
        original_stage = layer.stage
        eligible = self.delivery.delivered(index)
        frontier = self.delivery.frontier
        if self.delivery.advance(index):
            assert eligible and index == frontier
            assert layer.stage == previous + 1
        else:
            assert layer.stage == original_stage

    @invariant()
    def receipt_is_current_and_from_an_accepted_candidate(self) -> None:
        """Audit evidence independently of the model's delivery predicate."""
        for index, layer in enumerate(self.delivery.layers):
            if self.delivery.delivered(index):
                assert (index, layer.candidate) in self.accepted
                assert {layer.candidate, layer.remote, layer.github,
                        layer.gates, layer.replay, layer.readback} == {layer.candidate}
                assert layer.github_base == layer.base
                assert layer.tracking == tuple(item.remote for item in self.delivery.layers)


TestDeliveryStateMachine = DeliveryMachine.TestCase
TestDeliveryStateMachine.settings = settings(max_examples=100, stateful_step_count=35)


@pytest.mark.parametrize("omitted", STEPS)
def test_each_missing_obligation_blocks_delivery(omitted: str) -> None:
    """Delete one operation from a valid trace; no omission may be delivered."""
    delivery = Delivery(2)
    complete(delivery, 0, omitted)
    assert not delivery.delivered(0)
    assert not delivery.advance(0)


@given(depth=st.integers(2, 4), prefix=st.integers(0, 2))
def test_frontier_receipt_leaves_descendants_pending(depth: int, prefix: int) -> None:
    """A frontier receipt neither publishes nor completes an upper layer."""
    frontier = prefix % (depth - 1)
    delivery = Delivery(depth, frontier)
    complete(delivery, frontier)
    assert delivery.delivered(frontier)
    for index in range(frontier + 1, depth):
        assert delivery.layers[index].remote == 0
        assert not delivery.delivered(index)


def test_stale_lease_rejects_competing_remote_update() -> None:
    """A stale lease protects competing remote work until candidate reassessment."""
    delivery = Delivery(1)
    for action in ("replay", "gates", "lease"):
        delivery.observe(0, action)
    layer = delivery.layers[0]
    layer.remote = 200
    assert not delivery.push(0)
    assert layer.remote == 200
    # Reassessment is explicit; a rejected push never silently renews the lease.
    assert layer.lease == 0
    delivery.observe(0, "lease")
    assert not delivery.push(0)
    for action in ("replay", "gates"):
        delivery.observe(0, action)
    assert delivery.push(0)
    assert layer.remote == 1


def test_next_write_waits_for_tracking_reconciliation() -> None:
    """A successful push cannot be followed blindly by another write."""
    delivery = Delivery(1)
    complete(delivery, 0, "tracking")
    delivery.observe(0, "lease")
    assert not delivery.push(0)
    delivery.observe(0, "tracking")
    assert delivery.push(0)
    delivery.stack_result(set())
    assert not delivery.push(0)
    delivery.observe(0, "tracking")
    assert delivery.push(0)


def test_new_candidate_cannot_inherit_completed_review() -> None:
    """A replacement SHA must start its hosted lifecycle again."""
    delivery = Delivery(1)
    complete(delivery, 0)
    for _ in range(3):
        assert delivery.advance(0)
    delivery.layers[0].candidate = 100
    complete(delivery, 0)
    assert delivery.advance(0)
    assert delivery.layers[0].stage == 1


def test_hosted_stages_and_parent_merge_require_fresh_child_gates() -> None:
    """Publication, readiness, review and merge remain distinct transitions."""
    delivery = Delivery(2)
    complete(delivery, 0)
    for stage in (1, 2, 3, 4):
        assert delivery.advance(0)
        assert delivery.layers[0].stage == stage
    assert delivery.frontier == 1
    assert delivery.layers[1].gates is None
    assert not delivery.push(1)


@pytest.mark.parametrize("field", ("candidate", "remote", "github", "github_base"))
def test_receipt_cannot_survive_candidate_or_server_rewrite(field: str) -> None:
    """Changed candidate identity, remote head or GitHub base blocks closeout."""
    delivery = Delivery(2)
    complete(delivery, 0)
    assert delivery.delivered(0)
    setattr(delivery.layers[0], field, 100)
    assert not delivery.delivered(0)
    assert not delivery.advance(0)


def test_descendant_rewrite_requires_tracking_reconciliation() -> None:
    """An unchanged frontier does not excuse a stale descendant observation."""
    delivery = Delivery(2)
    complete(delivery, 0)
    delivery.layers[1].remote = 100
    assert not delivery.delivered(0)
    delivery.observe(0, "tracking")
    assert delivery.delivered(0)
    assert not delivery.delivered(1)


def test_model_obligations_remain_linked_to_documented_clauses() -> None:
    """Text contracts require an explicit model review when guidance changes."""
    root = Path(__file__).resolve().parents[1] / "skills/github-stacks"
    skill = " ".join((root / "SKILL.md").read_text().split())
    partial = " ".join((root / "references/partial-delivery.md").read_text().split())
    assert "Prioritize the merge frontier: the lowest unmerged layer" in skill
    assert "required candidate-bound gates" in skill
    for clause in (
        "Verify that the final remote SHA equals `CANDIDATE`",
        "read the PR's `headRefOid` and base from GitHub",
        "before the next managed write",
        "the operation is not atomic and some leases may have succeeded",
        "readiness, review request delivery, completed review and merge are separate",
    ):
        assert clause in partial
