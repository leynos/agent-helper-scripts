"""One control per rule of the applicability adapter.

``tests/readiness_applicability.py`` derives the readiness model's two
applicability inputs from recorded facts: the handoff packet, the candidate's
diff and the completeness request's proof inventory. Each rule here is paired
with the case that flips it, so a rule that is dropped or hard-coded fails a
row rather than agreeing with the facts by accident. The end-to-end cases in
``tests/test_readiness_handoff_boundary.py`` drive the same rules through the
shipped stand-in.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from readiness_applicability import (
    affects_a_proof,
    applicability,
    changes_a_proof,
    proof_inventory,
    stated_proofs,
)

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


@dataclass(frozen=True)
class Case:
    """One rule, the facts it is applied to, and the applicability it yields."""

    rule: str
    packet: dict[str, str]
    body: str
    proof_changed: bool
    expected: tuple[bool, bool]


CASES = (
    Case("the packet requires completeness", SHIPPED, NONE_AFFECTED, False, (True, False)),
    Case("a withdrawn packet line does not", WITHDRAWN, NONE_AFFECTED, False, (False, False)),
    Case("a changed proof makes its assessment apply", SHIPPED, NONE_AFFECTED, True, (True, True)),
    Case("the packet must condition the proof assessment", UNCONDITIONAL, NONE_AFFECTED, True, (True, False)),
    Case("the inventory can add a proof assessment", SHIPPED, NAMES_ONE, False, (True, True)),
    Case("an absent inventory line adds nothing", SHIPPED, "", False, (True, False)),
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
