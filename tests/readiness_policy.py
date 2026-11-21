"""The readiness rule for which assessments a candidate owes.

The pr-babysitting skill decides, from the handoff it accepted and the
candidate itself, whether the completeness, proof and original-issue
assessments apply, and which proofs a proof reply must cover. That is
readiness policy, and this module is the one statement of that applicability
rule. Which replies clear is also readiness policy, and it is stated only in
the model: ``readiness.fizz`` maps each reply shape to its fields and its
``shortfalls`` decides which clear, so restating it here would make a second
implementation. It takes facts, not text: no packet wording, no
path, no GitHub or CodeScene type. ``tests/readiness_applicability.py`` is the
adapter that extracts those facts from a recording.

The FizzBee model does not derive applicability. It takes the three results as
its assignment input, ``completeness_applies``, ``proof_applies`` and
``issue_derived`` in ``specs/pr-readiness/readiness.fizz``, and checks
readiness given them. The snapshot rows the model is checked on state the same
three facts, and the handoff tests compute the first two with this rule, so a
recording reaches the model only through it.
``tests/test_readiness_applicability.py`` holds one control per rule.

- The packet decides whether the completeness and proof assessments are
  required at all.
- The accepted scope decides the original-issue assessment: a PR derived from
  a GitHub issue owes it, with no not-applicable route. The handoff packet
  carries no derivation fact, so an adapter reading a recording that states
  none supplies False.
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
    ``issue_derived`` is whether the accepted scope says the PR delivers a
    GitHub issue. A recording that states no derivation leaves it False.
    """

    completeness_required: bool
    proof_conditional: bool
    proof_changed: bool
    inventory_names_a_proof: bool
    issue_derived: bool = False


def assessments_that_apply(facts: ApplicabilityFacts) -> tuple[bool, bool, bool]:
    """Return whether each of the three assessments applies.

    The completeness assessment applies when the packet requires it. The
    proof assessment applies when the packet requires it conditionally and
    the candidate affects a proof, by its diff or by its inventory. The
    original-issue assessment applies exactly when the accepted scope says
    the PR delivers an issue; nothing can waive it.

    Parameters
    ----------
    facts : ApplicabilityFacts
        The packet's requirements, the candidate's proof evidence, and
        whether the PR is derived from an issue.

    Returns
    -------
    tuple of (bool, bool, bool)
        The model's ``completeness_applies``, ``proof_applies`` and
        ``issue_derived`` inputs.
    """
    affected = facts.proof_changed or facts.inventory_names_a_proof
    return (
        facts.completeness_required,
        facts.proof_conditional and affected,
        facts.issue_derived,
    )


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
