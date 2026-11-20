"""Temporary migration aid: compare the Python decision model with FizzBee.

This script exists for one commit range only. It enumerates a bounded set of
equivalent snapshots, asks the retired Python decision model
(``tests/pr_readiness_model.py``) whether each may leave draft, and prints a
FizzBee snapshot table carrying those answers as expectations. Checking that
table with the model checker is the comparison: a row on which the two
disagree fails either ``BlockedAssignmentStaysDraft`` or
``ProgressWhenWarranted``.

The table it printed is kept in ``suite.toml`` as the
``snapshot-regression-table`` run. The script and the Python model are then
deleted together, so no second policy implementation remains.

Run from the repository root::

    python3 tests/pr_readiness_migration_compare.py
"""

from __future__ import annotations

import itertools
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pr_readiness_model import (  # noqa: E402
    CLEAR,
    DECLARED_SUBSET,
    NOT_APPLICABLE,
    NOT_CLEAR,
    PENDING,
    WHOLE_PLAN,
    Candidate,
    Verdict,
    readiness,
)

BASE, HEAD, REV = "base-0", "head-0", "rev-0"

#: The reply shapes of readiness.fizz, restated as the Python model's fields:
#: verdict, subject, echoes the candidate, how it echoes the revision, proofs
#: named.
SHAPES = {
    "sound-clear": (CLEAR, WHOLE_PLAN, True, "echoed", "all"),
    "subset-clear": (CLEAR, DECLARED_SUBSET, True, "echoed", "all"),
    "other-subject": (CLEAR, "this PR", True, "echoed", "all"),
    "partial-proofs": (CLEAR, WHOLE_PLAN, True, "echoed", "first"),
    "no-proofs": (CLEAR, WHOLE_PLAN, True, "echoed", "none"),
    "no-revision-echo": (CLEAR, WHOLE_PLAN, True, "absent", "all"),
    "superseded-revision-echo": (CLEAR, WHOLE_PLAN, True, "superseded", "all"),
    "other-candidate": (CLEAR, WHOLE_PLAN, False, "echoed", "all"),
    "not-applicable-claim": (NOT_APPLICABLE, WHOLE_PLAN, True, "echoed", "all"),
    "not-clear": (NOT_CLEAR, WHOLE_PLAN, True, "echoed", "all"),
    "acknowledgement": ("acknowledged", WHOLE_PLAN, True, "echoed", "all"),
}
COMPLETENESS_ONLY = {"subset-clear", "other-subject"}
PROOF_ONLY = {"partial-proofs", "no-proofs"}


def threads(kind: str, has_plan: bool, proofs: tuple[str, ...]) -> list[str]:
    """Return every thread state a snapshot may hold for one assessment."""
    found = ["none", "current:none", "another-candidate:sound-clear"]
    if has_plan:
        found.append("superseded-revision:sound-clear")
    for shape in SHAPES:
        if kind == "completeness" and shape in PROOF_ONLY:
            continue
        if kind == "proof" and shape in COMPLETENESS_ONLY:
            continue
        if shape == "partial-proofs" and len(proofs) < 2:
            continue
        if shape in ("no-revision-echo", "superseded-revision-echo") and not has_plan:
            continue
        found.append(f"current:{shape}")
    return found


def verdict(spec: str, *, applies: bool, has_plan: bool, justified: bool,
            proofs: tuple[str, ...], kind: str) -> Verdict:
    """Return the Python model's verdict for one thread state."""
    if not applies:
        return Verdict(NOT_APPLICABLE, BASE, HEAD,
                       justification="evidence" if justified else "")
    asked_rev = REV if has_plan else None
    if spec == "none" or spec.endswith(":none"):
        return Verdict(PENDING, "unobserved", "unobserved", plan_revision=asked_rev)
    request, shape = spec.split(":")
    head = HEAD
    if request == "superseded-revision":
        asked_rev = "rev-old"
    if request == "another-candidate":
        head = "head-old"
    word, subject, echoes_candidate, echoes_revision, named = SHAPES[shape]
    asked = proofs if kind == "proof" else ()
    # What the reply names is both what it echoes and what the verdict was
    # recorded against; a reply that names nothing was recorded against the
    # revision its request asked about.
    echoed = {"echoed": asked_rev, "absent": None, "superseded": "rev-older"}[
        echoes_revision
    ]
    recorded = asked_rev if echoed is None else echoed
    return Verdict(
        word,
        BASE,
        head if echoes_candidate else "head-elsewhere",
        plan_revision=recorded,
        echoed_revision=echoed,
        subject=subject,
        justification="claimed" if word == NOT_APPLICABLE else "",
        proofs={"all": asked, "first": asked[:1], "none": ()}[named],
    )


def decide(row: dict) -> bool:
    """Ask the Python decision model whether one snapshot may leave draft."""
    candidate = Candidate(
        BASE,
        HEAD,
        approved_plan_revision=REV if row["has_plan"] else None,
        ci_green=row["ci"] == "green",
        # The Python model has one CodeScene fact; the FizzBee model keeps the
        # hosted findings and the local delta apart. Both must be clear.
        codescene_clear=row["hosted"] == "clear" and row["local"] == "clear",
        required_proofs=row["proofs"],
    )
    common = {"has_plan": row["has_plan"], "justified": row["na_justified"],
              "proofs": row["proofs"]}
    return readiness(
        candidate,
        verdict(row["completeness"], applies=row["completeness_applies"],
                kind="completeness", **common),
        verdict(row["proof"], applies=row["proof_applies"], kind="proof", **common),
        completeness_applies=row["completeness_applies"],
        proof_applies=row["proof_applies"],
    ).ready


def rows() -> list[dict]:
    """Return the bounded snapshot set.

    Four assignments, each with every thread state of each applicable
    assessment crossed with each other, plus every single delivery-gate
    failure against the all-clear thread, plus the scope errors.
    """
    assignments = [
        {"completeness_applies": True, "proof_applies": False, "has_plan": True, "proofs": ()},
        {"completeness_applies": True, "proof_applies": True, "has_plan": True, "proofs": ("p1", "p2")},
        {"completeness_applies": False, "proof_applies": True, "has_plan": False, "proofs": ("p1", "p2")},
        {"completeness_applies": False, "proof_applies": False, "has_plan": False, "proofs": ()},
    ]
    delivery = {"ci": "green", "hosted": "clear", "local": "clear"}
    found: list[dict] = []
    for assignment in assignments:
        kinds = {
            "completeness": threads("completeness", assignment["has_plan"], assignment["proofs"])
            if assignment["completeness_applies"] else ["none"],
            "proof": threads("proof", assignment["has_plan"], assignment["proofs"])
            if assignment["proof_applies"] else ["none"],
        }
        for completeness, proof in itertools.product(kinds["completeness"], kinds["proof"]):
            found.append({**assignment, **delivery, "na_justified": True,
                          "completeness": completeness, "proof": proof})
        clear = {
            "completeness": "current:sound-clear" if assignment["completeness_applies"] else "none",
            "proof": "current:sound-clear" if assignment["proof_applies"] else "none",
        }
        for broken in ({"ci": "red"}, {"hosted": "findings"}, {"local": "findings"},
                       {"local": "unavailable"}):
            found.append({**assignment, **delivery, **broken, "na_justified": True, **clear})
        if not (assignment["completeness_applies"] and assignment["proof_applies"]):
            found.append({**assignment, **delivery, "na_justified": False, **clear})
    scope_errors = [
        {"completeness_applies": True, "proof_applies": False, "has_plan": False,
         "proofs": (), "completeness": "current:sound-clear", "proof": "none"},
        {"completeness_applies": False, "proof_applies": True, "has_plan": False,
         "proofs": (), "completeness": "none", "proof": "current:sound-clear"},
        {"completeness_applies": True, "proof_applies": True, "has_plan": True,
         "proofs": (), "completeness": "current:sound-clear", "proof": "current:sound-clear"},
    ]
    for error in scope_errors:
        found.append({**error, **delivery, "na_justified": True})
    return found


DEFAULTS = {"completeness_applies": True, "proof_applies": False, "has_plan": True,
            "na_justified": True, "proofs": (), "ci": "green", "hosted": "clear",
            "local": "clear", "completeness": "none", "proof": "none"}


def render(index: int, row: dict, ready: bool) -> str:
    """Return one snapshot() call, omitting arguments left at their default."""
    stated = ", ".join(f"{key}={value!r}" for key, value in row.items()
                       if DEFAULTS[key] != value).replace("'", '"')
    expect = "ready" if ready else "draft"
    return f'    snapshot("s{index:03d}", "{expect}"' + (f", {stated}" if stated else "") + "),"


def deviations(row: dict) -> int:
    """Count how many facts of a row differ from its all-clear snapshot."""
    clear = {
        "completeness": "current:sound-clear" if row["completeness_applies"] else "none",
        "proof": "current:sound-clear" if row["proof_applies"] else "none",
        "ci": "green", "hosted": "clear", "local": "clear", "na_justified": True,
    }
    return sum(row[key] != value for key, value in clear.items())


def main() -> None:
    """Print the snapshot table and a one-line tally on standard error.

    ``--single`` keeps the snapshots that differ from an all-clear one in at
    most one fact, which is the routine regression table; without it the
    whole bounded set is printed.
    """
    table = rows()
    if "--single" in sys.argv[1:]:
        table = [row for row in table if deviations(row) <= 1]
    decisions = [decide(row) for row in table]
    print("SCENARIOS = [")
    for index, (row, ready) in enumerate(zip(table, decisions, strict=True)):
        print(render(index, row, ready))
    print("]")
    print(f"{len(table)} snapshots; the Python model permits {sum(decisions)}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
