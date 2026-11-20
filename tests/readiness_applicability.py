"""Derive which readiness assessments a recorded candidate makes applicable.

The FizzBee readiness model takes applicability as an input: the accepted
assignment says whether the completeness and the proof assessment apply, and
the model checks readiness given that. A recorded agent-boundary scenario
does not state those two facts directly. They have to be derived from the
handoff packet the receiver was given, the candidate's own diff, and the
proof inventory the completeness request states.

This module is that derivation, and nothing else. Its rules are adapter
rules, not readiness policy: they map recorded facts to the model's inputs,
and ``tests/test_readiness_applicability.py`` holds one control per rule.

- The packet decides whether each assessment is required at all.
- The candidate's diff is the primary evidence for the proof assessment: a
  change to the recorded proof makes it apply whatever the inventory says.
- The inventory is secondary and can only add: naming a proof makes the
  assessment apply; ``none affected`` cannot remove one the diff requires.
- A posted proof question is not evidence either way.
- Coverage follows applicability: a changed proof joins the inventory a
  reply must cover, even when the inventory names another proof.
"""

from __future__ import annotations

import re

PROOF_INVENTORY = re.compile(r"^Proof inventory:[^\n]*", re.MULTILINE)


def proof_reference(entry: str) -> str:
    """Return the named proof reference from a `path#reference` inventory entry.

    The shipped proof template asks about "proof file paths with named proof
    references", so its inventory entry carries both. The recorded replies
    name the reference alone, which is the same proof and is how the template's
    own subject line asks for it. An entry with no separator is already a
    reference, so it is returned unchanged.
    """
    return entry.rsplit("#", 1)[-1].strip()


def proof_inventory(
    proof_ask: dict | None, completeness_body: str
) -> tuple[str, ...]:
    """Return the named proof references this candidate's inventory holds.

    The completeness request's `Proof inventory:` line is the sender's own
    statement of what the candidate affects, and it is available whether or
    not the proof question was ever posted. A missing question is a missing
    assessment, not a missing inventory, so the line is what a pending proof
    assessment is pending *about*. Reading the question alone made the two
    facts the same one: a proof-changing candidate with no question had no
    inventory either, and the gate then held on `proof-inventory-empty`
    rather than on the unanswered assessment.

    A proof-only assignment has no completeness request to carry that line, so
    its inventory comes from the question's opening, which is the shipped
    template's `(proof file paths with named proof references)`, filled with
    the proofs the request asks about.

    Parameters
    ----------
    proof_ask : dict or None
        The recorded proof question, when the discussion has one.
    completeness_body : str
        The completeness request's body, whose `Proof inventory:` line names
        the affected proofs.

    Returns
    -------
    tuple of str
        The named references the reply's subject is compared against.
    """
    stated = PROOF_INVENTORY.search(completeness_body)
    if stated is not None:
        listed = stated.group(0)
        if "none affected" in listed.casefold():
            return ()
        # Each entry is a backticked path and a backticked reference; the path
        # contains a separator and the reference does not, so the references
        # are the backticked names without one.
        named = tuple(
            name for name in re.findall(r"`([^`]+)`", listed) if "/" not in name
        )
        if named:
            return named
    if proof_ask is None:
        return ()
    opening = re.search(
        r"introduced proof\(s\)\s*\(([^)]*)\)", str(proof_ask["body"])
    )
    assert opening, "the proof request names no inventory"
    return tuple(
        proof_reference(name)
        for name in opening.group(1).split(",")
        if name.strip()
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


def affects_a_proof(body: str) -> bool:
    """Return whether a completeness request says the candidate affects a proof.

    The sender records the candidate's affected-proof inventory on the
    `Proof inventory:` line, which is the handoff's own statement of what the
    proof assessment would be about. An inventory that says `none affected` is
    empty; one that names proofs is not. A request carrying no such line
    establishes nothing, and is read as neither.

    This is the secondary read, and it can only *add* applicability. The
    candidate's diff is the primary evidence, so an inventory that names a
    proof the diff does not carry still makes the assessment apply, while an
    inventory that says `none affected` over a changed proof cannot unmake it.
    A sender that writes that sentence over its own changed proof has recorded
    a contradiction, and taking the sentence as authoritative is what let a
    proof-changing candidate clear on the completeness reply alone.

    The proof question is a different fact again. It says the assessment was
    asked for, not whether it applies: a candidate that changes a proof and
    never has its question posted is a candidate with a missing assessment.
    Reading applicability from the question alone made that state look
    inapplicable, which cleared the gate on the completeness reply.

    Parameters
    ----------
    body : str
        The completeness request's recorded body.

    Returns
    -------
    bool
        Whether the recorded inventory names at least one affected proof.
    """
    stated = PROOF_INVENTORY.search(body)
    if stated is None:
        return False
    return "none affected" not in stated.group(0).casefold()


def changes_a_proof(changed: list[str], proof: str) -> bool:
    """Return whether the candidate's own diff carries the proof it names.

    Parameters
    ----------
    changed : list of str
        The paths the candidate changes, as its diff reports them.
    proof : str
        The repository-relative proof path the recording names.

    Returns
    -------
    bool
        Whether that proof is among the changed paths.
    """
    return bool(proof) and proof in changed


def applicability(
    packet: dict[str, str], completeness_body: str, proof_changed: bool
) -> tuple[bool, bool]:
    """Return whether the completeness and the proof assessment apply.

    Parameters
    ----------
    packet : dict
        The shipped handoff packet's lines, keyed by field; ``assessment``
        and ``proof`` state the two applicability rules.
    completeness_body : str
        The completeness request's body, whose `Proof inventory:` line can
        add a proof assessment.
    proof_changed : bool
        Whether the candidate's own diff changes the recorded proof.

    Returns
    -------
    tuple of (bool, bool)
        Whether the completeness assessment applies, and whether the proof
        assessment does.
    """
    completeness = "required" in packet["assessment"].casefold()
    conditional = "required when applicable" in packet["proof"].casefold()
    affected = proof_changed or affects_a_proof(completeness_body)
    return completeness, conditional and affected
