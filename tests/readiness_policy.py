"""The readiness rule for which assessments a candidate owes.

The pr-babysitting skill decides, from the handoff it accepted and the
candidate itself, whether the completeness and the proof assessment apply,
and which proofs a proof reply must cover. That is readiness policy, and this
module is its one statement. It takes facts, not text: no packet wording, no
path, no GitHub or CodeScene type. ``tests/readiness_applicability.py`` is the
adapter that extracts those facts from a recording.

The FizzBee model does not derive applicability. It takes the two results as
its assignment input, ``completeness_applies`` and ``proof_applies`` in
``specs/pr-readiness/readiness.fizz``, and checks readiness given them. The
snapshot rows the model is checked on state the same two facts, and the
handoff tests compute them with this rule, so a recording reaches the model
only through it. ``tests/test_readiness_applicability.py`` holds one control
per rule.

- The packet decides whether each assessment is required at all.
- The candidate's diff is the primary evidence for the proof assessment: a
  change to the recorded proof makes it apply whatever the inventory says.
- The inventory is secondary and can only add: naming a proof makes the
  assessment apply; ``none affected`` cannot remove one the diff requires.
- A posted proof question is not evidence either way, so it is not a fact
  here.
- Coverage follows applicability: a changed proof joins the inventory a
  reply must cover, even when the inventory names another proof.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicabilityFacts:
    """What the rule is decided on, each fact extracted from a recording.

    ``completeness_required`` and ``proof_conditional`` are what the handoff
    packet requires; ``proof_changed`` is whether the candidate's diff
    changes the recorded proof; ``inventory_names_a_proof`` is whether the
    completeness request's proof inventory names at least one proof.
    """

    completeness_required: bool
    proof_conditional: bool
    proof_changed: bool
    inventory_names_a_proof: bool


def assessments_that_apply(facts: ApplicabilityFacts) -> tuple[bool, bool]:
    """Return whether the completeness and the proof assessment apply.

    The completeness assessment applies when the packet requires it. The
    proof assessment applies when the packet requires it conditionally and
    the candidate affects a proof, by its diff or by its inventory.

    Parameters
    ----------
    facts : ApplicabilityFacts
        The packet's requirements and the candidate's proof evidence.

    Returns
    -------
    tuple of (bool, bool)
        The model's ``completeness_applies`` and ``proof_applies`` inputs.
    """
    affected = facts.proof_changed or facts.inventory_names_a_proof
    return facts.completeness_required, facts.proof_conditional and affected


def stated_proofs(
    inventory: tuple[str, ...], changed: bool, reference: str
) -> tuple[str, ...]:
    """Return the inventory a proof assessment must actually cover.

    Applicability and coverage are two facts that have to agree. The diff says
    the assessment applies; the inventory says what the reply will be compared
    against. An inventory that owes nothing to a changed proof — it names some
    other proof, or names none — would let a clear reply for that other proof
    discharge an assessment of the proof the candidate changed, so the changed
    proof is added to what the reply must cover.

    The addition is one-way. A non-empty inventory that already names the
    changed proof is left exactly as recorded, and an empty inventory over an
    unchanged candidate stays empty: the join only ever adds the proof the
    diff actually carries.

    Parameters
    ----------
    inventory : tuple of str
        The proofs the request's inventory names.
    changed : bool
        Whether the candidate's diff changes the proof the recording names.
    reference : str
        The named reference the recording's proof is assessed under.

    Returns
    -------
    tuple of str
        The inventory the reply's subject is compared against.
    """
    if not changed:
        return inventory
    return tuple(dict.fromkeys((*inventory, reference)))
