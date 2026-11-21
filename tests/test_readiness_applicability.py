"""One control per rule of the readiness policy and its adapters.

``tests/readiness_policy.py`` states which assessments a candidate owes, over
facts. ``tests/readiness_applicability.py`` extracts those facts from a
recording: the handoff packet, the candidate's diff and the completeness
request's proof inventory. Each rule here is paired with the case that flips
it, so a rule that is dropped or hard-coded fails a row rather than agreeing
with the facts by accident. The policy rules are tested on facts directly;
the composed cases then drive extraction and policy together, and the
end-to-end cases in ``tests/test_readiness_handoff_boundary.py`` drive both
through the shipped stand-in.

The same holds for the two adapters that sit either side of the snapshot
lookup: ``tests/readiness_snapshot_support.py``, which turns a recorded thread
into a model thread state, and the table readers of
``tests/pr_readiness_spec_support.py``, which must refuse a table they cannot
read rather than skip it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

import pytest

import pr_readiness_spec_support
from pr_readiness_spec_support import SNAPSHOT_DEFAULTS, checked_expectation, snapshot_rows
from readiness_applicability import (
    affects_a_proof,
    applicability,
    applicability_facts,
    changes_a_proof,
    proof_inventory,
)
from readiness_policy import ApplicabilityFacts, assessments_that_apply, stated_proofs
from readiness_snapshot_support import COMPLETENESS, PROOF, Bounds, reply_shape, thread_state

#: The packet lines as the shipped handoff states them.
SHIPPED = {
    "assessment": (
        "ExecPlan completeness/correctness assessment: required against the whole"
        " approved plan"
    ),
    "proof": "Proof-specific assessment: required when applicable",
}
WITHDRAWN = {**SHIPPED, "assessment": "ExecPlan completeness/correctness assessment: optional"}
UNCONDITIONAL = {**SHIPPED, "proof": "Proof-specific assessment: optional"}
NONE_AFFECTED = "Proof inventory: none affected.\n"
NAMES_ONE = "Proof inventory: `proofs/refinement/Theorem.lean` (`refinement_sound`).\n"


#: Facts under which the completeness assessment applies and no proof is affected.
BASE_FACTS = ApplicabilityFacts(
    completeness_required=True,
    proof_conditional=True,
    proof_changed=False,
    inventory_names_a_proof=False,
)

#: One policy rule each: the facts it is decided on and the answer it gives.
POLICY_RULES = (
    ("the packet requires completeness", {}, (True, False, False)),
    ("an unrequired completeness assessment does not apply", {"completeness_required": False}, (False, False, False)),
    ("a changed proof makes its assessment apply", {"proof_changed": True}, (True, True, False)),
    ("an inventory naming a proof makes it apply", {"inventory_names_a_proof": True}, (True, True, False)),
    (
        "the packet must condition the proof assessment",
        {"proof_conditional": False, "proof_changed": True, "inventory_names_a_proof": True},
        (True, False, False),
    ),
    (
        "an empty inventory cannot remove what the diff requires",
        {"proof_changed": True, "inventory_names_a_proof": False},
        (True, True, False),
    ),
    (
        "an issue-derived PR owes the original-issue assessment",
        {"issue_derived": True},
        (True, False, True),
    ),
)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [(changes, expected) for _, changes, expected in POLICY_RULES],
    ids=[rule for rule, _, _ in POLICY_RULES],
)
def test_each_policy_rule_decides_on_facts(changes: dict, expected: tuple[bool, bool, bool]) -> None:
    """The policy unit answers from the facts alone, one rule per row."""
    facts = ApplicabilityFacts(**{**BASE_FACTS.__dict__, **changes})
    assert assessments_that_apply(facts) == expected


def test_the_adapter_extracts_the_facts_the_policy_takes() -> None:
    """Packet lines, the diff and the inventory become the policy's facts."""
    assert applicability_facts(SHIPPED, NAMES_ONE, False) == ApplicabilityFacts(
        completeness_required=True,
        proof_conditional=True,
        proof_changed=False,
        inventory_names_a_proof=True,
    )
    assert applicability_facts(WITHDRAWN, NONE_AFFECTED, True) == ApplicabilityFacts(
        completeness_required=False,
        proof_conditional=True,
        proof_changed=True,
        inventory_names_a_proof=False,
    )
    assert applicability_facts(UNCONDITIONAL, "", False).proof_conditional is False


@dataclass(frozen=True)
class Case:
    """One rule, the facts it is applied to, and the applicability it yields."""

    rule: str
    packet: dict[str, str]
    body: str
    proof_changed: bool
    expected: tuple[bool, bool, bool]


CASES = (
    Case("the packet requires completeness", SHIPPED, NONE_AFFECTED, False, (True, False, False)),
    Case("a withdrawn packet line does not", WITHDRAWN, NONE_AFFECTED, False, (False, False, False)),
    Case("a changed proof makes its assessment apply", SHIPPED, NONE_AFFECTED, True, (True, True, False)),
    Case("the packet must condition the proof assessment", UNCONDITIONAL, NONE_AFFECTED, True, (True, False, False)),
    Case("the inventory can add a proof assessment", SHIPPED, NAMES_ONE, False, (True, True, False)),
    Case("an absent inventory line adds nothing", SHIPPED, "", False, (True, False, False)),
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule)
def test_each_applicability_rule_and_its_control(case: Case) -> None:
    """Each rule yields its applicability, and its pair yields the other."""
    assert applicability(case.packet, case.body, case.proof_changed) == case.expected


def test_the_inventory_cannot_remove_what_the_diff_requires() -> None:
    """``none affected`` over a changed proof is a contradiction, not a waiver.

    The control is the same sentence over an unchanged candidate, which the
    rule leaves inapplicable.
    """
    assert applicability(SHIPPED, NONE_AFFECTED, True)[1] is True
    assert applicability(SHIPPED, NONE_AFFECTED, False)[1] is False


def test_a_change_is_read_from_the_diff_not_the_name() -> None:
    """The recorded proof applies only when the diff carries that path."""
    proof = "proofs/refinement/Theorem.lean"
    assert changes_a_proof(["docs/plan.md", proof], proof)
    assert not changes_a_proof(["docs/plan.md"], proof)
    assert not changes_a_proof([proof], "")


def test_the_inventory_line_is_read_only_when_it_names_a_proof() -> None:
    """Naming a proof affects one; `none affected` and silence do not."""
    assert (affects_a_proof(NAMES_ONE), affects_a_proof(NONE_AFFECTED), affects_a_proof("")) == (
        True,
        False,
        False,
    )


def test_a_changed_proof_joins_the_inventory_a_reply_must_cover() -> None:
    """Coverage follows applicability, and the join only ever adds.

    An inventory naming another proof still owes the changed one; an
    inventory already naming it is unchanged; an unchanged candidate's
    inventory is left as recorded.
    """
    assert stated_proofs(("other_sound",), True, "refinement_sound") == (
        "other_sound",
        "refinement_sound",
    )
    assert stated_proofs(("refinement_sound",), True, "refinement_sound") == ("refinement_sound",)
    assert stated_proofs(("other_sound",), False, "refinement_sound") == ("other_sound",)


def test_the_inventory_names_references_not_paths() -> None:
    """The inventory a reply is compared with holds named references.

    Without an inventory line, a proof question's opening supplies it; with
    neither, the inventory is empty.
    """
    assert proof_inventory(None, NAMES_ONE) == ("refinement_sound",)
    assert proof_inventory(None, NONE_AFFECTED) == ()
    question = {
        "body": "@coderabbitai are you satisfied that the introduced proof(s)"
        " (proofs/refinement/Theorem.lean#refinement_sound) is substantive"
    }
    assert proof_inventory(question, "") == ("refinement_sound",)
    assert proof_inventory(None, "") == ()


#: The candidate the snapshot-adapter cases are judged against.
BOUNDS = Bounds(base="b0", head="h1", in_force="rev-2", required=("refinement_sound",))


def proof_reply(subject: str, head: str = "h1") -> str:
    """Return a clear proof reply, for ``base...head``, naming ``subject``."""
    return (
        "**Verdict: clear**\n"
        f"**Assessed base/head:** b0...{head}\n"
        "**Plan revision:** rev-2\n"
        f"**Assessed subject:** {subject}\n"
    )


def test_a_proof_reply_naming_no_required_proof_covers_nothing() -> None:
    """Naming none of the required proofs is ``no-proofs``; naming them all clears."""
    assert reply_shape(PROOF, proof_reply("`other_sound`"), BOUNDS, "rev-2") == "no-proofs"
    assert reply_shape(PROOF, proof_reply("`refinement_sound`"), BOUNDS, "rev-2") == "sound-clear"


def test_a_reply_for_another_head_says_nothing_about_this_one() -> None:
    """A clear reply naming another head is ``other-candidate``."""
    reply = proof_reply("`refinement_sound`", head="h0")
    assert reply_shape(PROOF, reply, BOUNDS, "rev-2") == "other-candidate"


def test_a_request_naming_another_head_asks_about_another_candidate() -> None:
    """The request's own head decides its state; this head's request is current."""
    stale = {"body": "Published head: h0; Plan revision: rev-2\nAssessment-ID: p-1"}
    current = {"body": "Published head: h1; Plan revision: rev-2\nAssessment-ID: p-1"}
    assert thread_state(PROOF, [], stale, BOUNDS) == "another-candidate:none"
    assert thread_state(PROOF, [], current, BOUNDS) == "current:none"


def scenario(*rows: str) -> str:
    """Return a scenario assigning ``SCENARIOS`` the given row expressions."""
    return "SCENARIOS = [" + ", ".join(rows) + "]"


@pytest.mark.parametrize(
    ("run", "refusal"),
    [
        ({"tier": "extended", "scenario": scenario("snapshot('a', 'ready')")}, "not checked"),
        ({"scenario": scenario("other('a', 'ready')")}, "not a snapshot() call"),
        ({"scenario": scenario("snapshot('a', 'ready', colour='red')")}, "unknown fact"),
        ({"scenario": scenario("snapshot('a', 'ready')", "snapshot('a', 'draft')")}, "twice"),
        ({"scenario": "SCENARIOS = []"}, "no snapshot rows"),
    ],
    ids=["extended-tier", "not-a-snapshot", "unknown-fact", "duplicate-row", "empty-table"],
)
def test_a_table_the_reader_cannot_read_is_refused(
    monkeypatch: pytest.MonkeyPatch, run: dict, refusal: str
) -> None:
    """Each malformed table raises, naming why, rather than yielding fewer rows."""
    monkeypatch.setattr(pr_readiness_spec_support, "runs", lambda: {"table": run})
    with pytest.raises(AssertionError, match=re.escape(refusal)):
        snapshot_rows("table")


def test_a_readable_table_fills_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row states only what differs; the reader supplies the rest."""
    table = {"table": {"scenario": scenario("snapshot('a', 'draft', ci='red')")}}
    monkeypatch.setattr(pr_readiness_spec_support, "runs", lambda: table)
    assert snapshot_rows("table") == {"a": ("draft", {**SNAPSHOT_DEFAULTS, "ci": "red"})}


def test_a_lookup_answers_only_from_one_agreeing_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown facts and disagreeing tables raise; one agreeing answer is returned."""
    tables = {
        "one": {"scenario": scenario("snapshot('a', 'ready')")},
        "two": {"scenario": scenario("snapshot('b', 'draft')")},
        "same": {"scenario": scenario("snapshot('c', 'ready')")},
    }
    monkeypatch.setattr(pr_readiness_spec_support, "runs", lambda: tables)
    facts = dict(SNAPSHOT_DEFAULTS)
    assert checked_expectation(facts, ("one", "same")) == "ready"
    with pytest.raises(AssertionError, match="disagree"):
        checked_expectation(facts, ("one", "two"))
    with pytest.raises(AssertionError, match="no model-checked snapshot"):
        checked_expectation({**facts, "ci": "red"}, ("one",))


def reply(verdict: str, subject: str, *, head: str = "h1", revision: str | None = "rev-2") -> str:
    """Return a recorded reply body stating a verdict, candidate, revision and subject."""
    stated = f"**Verdict: {verdict}**\n**Assessed base/head:** b0...{head}\n"
    if revision is not None:
        stated += f"**Plan revision:** {revision}\n"
    return stated + f"**Assessed subject:** {subject}\n"


WHOLE = "the whole approved plan"
SHAPES = (
    ("not-applicable-claim", COMPLETENESS, reply("not applicable", WHOLE)),
    ("not-clear", COMPLETENESS, reply("not clear", WHOLE)),
    ("acknowledgement", COMPLETENESS, reply("noted", WHOLE)),
    ("other-candidate", COMPLETENESS, reply("clear", WHOLE, head="h0")),
    ("no-revision-echo", COMPLETENESS, reply("clear", WHOLE, revision=None)),
    ("superseded-revision-echo", COMPLETENESS, reply("clear", WHOLE, revision="rev-1")),
    ("sound-clear", COMPLETENESS, reply("clear", WHOLE)),
    ("subset-clear", COMPLETENESS, reply("clear", "a declared subset of the plan")),
    ("partial-proofs", PROOF, reply("clear", "`refinement_sound`")),
    ("no-proofs", PROOF, reply("clear", "`other_sound`")),
    ("sound-clear", PROOF, reply("clear", "`refinement_sound`, `stack_sound`")),
)


@pytest.mark.parametrize(
    ("shape", "kind", "body"), SHAPES, ids=[f"{kind}-{shape}" for shape, kind, _ in SHAPES]
)
def test_each_reply_is_named_by_the_shape_its_fields_match(shape: str, kind: str, body: str) -> None:
    """One control per shape name the adapter can give a reply.

    The adapter names the shape; ``readiness.fizz`` decides whether it clears.
    """
    bounds = replace(BOUNDS, required=("refinement_sound", "stack_sound"))
    assert reply_shape(kind, body, bounds, "rev-2") == shape


REQUESTS = (
    ("current", COMPLETENESS, "Published head: h1; Plan revision: rev-2"),
    ("another-candidate", COMPLETENESS, "Published head: h0; Plan revision: rev-2"),
    ("superseded-revision", COMPLETENESS, "Published head: h1; Plan revision: rev-1"),
    ("unnamed-revision", COMPLETENESS, "Published head: h1; nothing else"),
    ("current", PROOF, "Published head: h1; nothing else"),
)


@pytest.mark.parametrize(
    ("state", "kind", "body"), REQUESTS, ids=[f"{kind}-{state}" for state, kind, _ in REQUESTS]
)
def test_each_request_is_named_by_what_it_asks_about(state: str, kind: str, body: str) -> None:
    """One control per request state; only completeness must name a revision."""
    request = {"body": body + "\nAssessment-ID: a-1"}
    assert thread_state(kind, [], request, BOUNDS) == f"{state}:none"
