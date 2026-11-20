"""Read the PR-readiness model-checking suite without evaluating it.

The suite under ``specs/pr-readiness`` is checked by FizzBee, not by Python.
The contract tests still need to know what it says: which assertions the
specifications declare, which runs exist, and what each frozen snapshot row
states and expects. This module reads those as data. A snapshot table is
FizzBee source whose ``snapshot(...)`` calls take literal arguments only, so
it is parsed with ``ast`` and never executed.

Nothing here decides readiness. A snapshot's expectation is whatever the
suite records, and the model checker is what holds the suite to it.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIRECTORY = REPO_ROOT / "specs" / "pr-readiness"
SUITE = SPEC_DIRECTORY / "suite.toml"

#: The ``snapshot()`` defaults in ``readiness.fizz``. A row states only what
#: differs, so rows and observations are compared after filling these in.
SNAPSHOT_DEFAULTS = {
    "completeness_applies": True,
    "proof_applies": False,
    "issue_derived": False,
    "has_issue_body": True,
    "has_plan": True,
    "na_justified": True,
    "proofs": (),
    "ci": "green",
    "hosted": "clear",
    "local": "clear",
    "completeness": "none",
    "proof": "none",
    "issue": "none",
}

_ASSERTION = re.compile(
    r"^(always|exists|transition|eventually always|always eventually)"
    r" assertion (\w+)",
    re.MULTILINE,
)
_ACTION = re.compile(r"^(?:atomic )?(?:fair )?action (\w+):", re.MULTILINE)


def suite() -> dict:
    """Return the suite manifest as parsed TOML."""
    return tomllib.loads(SUITE.read_text(encoding="utf-8"))


def runs() -> dict[str, dict]:
    """Return every run of the suite, keyed by its identifier."""
    return {str(run["id"]): run for run in suite()["run"]}


def specification(name: str) -> str:
    """Return one specification's source text."""
    return (SPEC_DIRECTORY / name).read_text(encoding="utf-8")


def assertions(name: str) -> dict[str, str]:
    """Return each assertion a specification declares, with its kind."""
    return {found[1]: found[0] for found in _ASSERTION.findall(specification(name))}


def actions(name: str) -> set[str]:
    """Return the names of the actions a specification declares."""
    return set(_ACTION.findall(specification(name)))


def snapshot_rows(run_id: str) -> dict[str, tuple[str, dict]]:
    """Return a snapshot table's rows as ``name -> (expectation, facts)``.

    Parameters
    ----------
    run_id : str
        A run whose scenario assigns ``SCENARIOS`` a list of ``snapshot()``
        calls.

    Returns
    -------
    dict
        Each row's expectation, ``ready`` or ``draft``, and its facts with
        the ``snapshot()`` defaults filled in.

    Raises
    ------
    AssertionError
        Raised when the run is not routine, or a row is not a ``snapshot()``
        call with a literal name, expectation and keyword arguments. A row
        this function cannot read is one a test would otherwise skip.
    """
    run = runs()[run_id]
    assert run.get("tier", "routine") == "routine", (
        f"{run_id} is not checked by the mandatory gate"
    )
    tree = ast.parse(str(run["scenario"]))
    rows: dict[str, tuple[str, dict]] = {}
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        assert isinstance(call.func, ast.Name) and call.func.id == "snapshot", (
            f"{run_id} holds a row that is not a snapshot() call"
        )
        name, expect = (ast.literal_eval(argument) for argument in call.args)
        facts = dict(SNAPSHOT_DEFAULTS)
        for keyword in call.keywords:
            assert keyword.arg in SNAPSHOT_DEFAULTS, (
                f"{run_id} row {name} states an unknown fact {keyword.arg!r}"
            )
            facts[keyword.arg] = ast.literal_eval(keyword.value)
        assert name not in rows, f"{run_id} names the row {name} twice"
        rows[name] = (expect, facts)
    assert rows, f"{run_id} holds no snapshot rows"
    return rows


def checked_expectation(facts: dict, run_ids: tuple[str, ...]) -> str:
    """Return what the model-checked tables expect for one set of facts.

    This is a lookup, not a decision: the answer is the expectation of the
    row whose facts equal ``facts``, and the mandatory gate is what verified
    that expectation against the model.

    Raises
    ------
    AssertionError
        Raised when no row states these facts, so an observation the model
        was never asked about cannot be given an answer.
    """
    found = {
        expect
        for run_id in run_ids
        for expect, row in snapshot_rows(run_id).values()
        if row == facts
    }
    assert found, f"no model-checked snapshot states these facts: {facts}"
    assert len(found) == 1, f"the tables disagree about {facts}: {sorted(found)}"
    return found.pop()
