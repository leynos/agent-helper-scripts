"""Extract the facts the readiness applicability rule is decided on.

The FizzBee readiness model takes applicability as an input: the accepted
assignment says whether the completeness and the proof assessment apply, and
the model checks readiness given that. A recorded agent-boundary scenario
does not state those two facts directly. The rule that decides them is
readiness policy, stated once in ``tests/readiness_policy.py``; this module is
the adapter that reads, from the recording, the facts the rule takes.

- What the handoff packet requires, read from its two assessment lines.
- Whether the candidate's own diff changes the recorded proof.
- What the completeness request's ``Proof inventory:`` line names, and the
  named references a proof reply will be compared against.

It decides nothing: ``applicability`` hands the extracted facts to the policy
unit and returns its answer. ``tests/test_readiness_applicability.py`` holds
one control per extraction and per rule.
"""

from __future__ import annotations

import re

from readiness_policy import ApplicabilityFacts, assessments_that_apply

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


def affects_a_proof(body: str) -> bool:
    """Return whether a completeness request says the candidate affects a proof.

    The sender records the candidate's affected-proof inventory on the
    `Proof inventory:` line, which is the handoff's own statement of what the
    proof assessment would be about. An inventory that says `none affected` is
    empty; one that names proofs is not. A request carrying no such line
    establishes nothing, and is read as neither.

    This is the inventory fact only. How it combines with the diff is the
    policy unit's rule, under which the inventory can add applicability and
    never remove it. The proof question is a different fact again: it says
    the assessment was asked for, not whether it applies, so it is not read
    here.

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


def packet_requires_completeness(packet: dict[str, str]) -> bool:
    """Return whether the handoff packet requires the completeness assessment."""
    return "required" in packet["assessment"].casefold()


def packet_conditions_proof(packet: dict[str, str]) -> bool:
    """Return whether the packet requires the proof assessment when applicable.

    An unconditional or optional line is not the conditional requirement the
    shipped handoff states, so it is read as not requiring the assessment.
    """
    return "required when applicable" in packet["proof"].casefold()


def applicability_facts(
    packet: dict[str, str], completeness_body: str, proof_changed: bool
) -> ApplicabilityFacts:
    """Return the facts the applicability rule takes, read from a recording.

    Parameters
    ----------
    packet : dict
        The shipped handoff packet's lines, keyed by field; ``assessment``
        and ``proof`` state the two requirements.
    completeness_body : str
        The completeness request's body, whose `Proof inventory:` line may
        name an affected proof.
    proof_changed : bool
        Whether the candidate's own diff changes the recorded proof.
    """
    return ApplicabilityFacts(
        completeness_required=packet_requires_completeness(packet),
        proof_conditional=packet_conditions_proof(packet),
        proof_changed=proof_changed,
        inventory_names_a_proof=affects_a_proof(completeness_body),
    )


def applicability(
    packet: dict[str, str], completeness_body: str, proof_changed: bool
) -> tuple[bool, bool, bool]:
    """Return whether the three assessments apply, by the policy unit's rule.

    The facts are extracted here and decided by
    ``readiness_policy.assessments_that_apply``. The handoff packet states no
    derivation, so the recorded scenarios leave the original-issue assessment
    inapplicable; the `issue-derived` model scenarios exercise it.

    Returns
    -------
    tuple of (bool, bool, bool)
        Whether the completeness assessment applies, whether the proof
        assessment does, and whether the PR is derived from an issue.
    """
    return assessments_that_apply(applicability_facts(packet, completeness_body, proof_changed))
