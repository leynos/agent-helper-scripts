"""Hold the PR-readiness obligation mapping to the skills and to the suite.

``specs/pr-readiness/obligations.toml`` maps each behavioural obligation to
the shipped section that states it, the assertions of the FizzBee
specifications that express it, and the evidence kept outside the model. The
skills remain the normative contract; this mapping is how a reader gets from
a sentence of the contract to the property that checks it and back.

The retired Python decision model carried a citation for every reason it
could return, and a test that failed when a cited sentence left the shipped
documents. These tests keep that link in both directions for the model that
replaced it: an obligation whose sentence is gone fails here, and so does an
assertion or a run that no obligation accounts for.

A sentence that is still present shows only that the rule is still stated.
It does not show that the prose and the model mean the same thing; that is a
review question, and the mapping is what makes it reviewable.
"""

from __future__ import annotations

import ast
import tomllib

import pytest

from pr_readiness_spec_support import REPO_ROOT, SPEC_DIRECTORY, assertions, runs
from skill_contract_support import normalize, section

MAPPING = tomllib.loads(
    (SPEC_DIRECTORY / "obligations.toml").read_text(encoding="utf-8")
)
OBLIGATIONS = {entry["id"]: entry for entry in MAPPING["obligation"]}
DECLARED = {**assertions("readiness.fizz"), **assertions("stack.fizz")}
RUNS = runs()
#: The scenario builders a readiness run's scenario may call.
BUILDERS = ("scenario", "snapshot")
#: The ``scenario()`` expectations that an ``exists`` assertion reads, and the
#: values that switch each one on.
WITNESSES = {
    "expect_ready": ("reachable",),
    "expect_merge": ("reachable",),
    "expect_recovery": ("merged", "ready"),
    "expect_stale_ready": ("reachable",),
    "expect_reentry": ("reachable",),
}
#: Declared outcomes of a configuration rather than obligations with a guard:
#: each is failed by a property control, not by a mutation.
STRONG = {"StrongReadyFreshness", "StrongMergeFreshness"}


def failed_assertion(run: dict) -> str:
    """Return the assertion a run is required to fail, or nothing."""
    expect = run["expect"]
    return expect.get("assertion", "") if isinstance(expect, dict) else ""


def test_the_mapping_names_each_obligation_once() -> None:
    """An identifier is stable only if it is unique."""
    identifiers = [entry["id"] for entry in MAPPING["obligation"]]
    assert len(identifiers) == len(set(identifiers)), "an obligation id is repeated"


@pytest.mark.parametrize("identifier", sorted(OBLIGATIONS))
def test_each_obligation_cites_sentences_its_section_still_states(
    identifier: str,
) -> None:
    """No obligation may outlive the prose that states it.

    The anchors are looked for inside the named level-2 section, not the
    whole document, so a sentence moved under an unrelated heading no longer
    supports the obligation that cited it.
    """
    entry = OBLIGATIONS[identifier]
    document = REPO_ROOT / entry["document"]
    assert document.is_file(), f"{identifier} cites a missing document"
    stated = section(document.read_text(encoding="utf-8"), entry["section"])
    assert entry["anchors"], f"{identifier} cites no sentence"
    lost = [anchor for anchor in entry["anchors"] if normalize(anchor) not in stated]
    assert not lost, (
        f"{identifier}: the section {entry['section']!r} of {entry['document']}"
        f" no longer states: {lost}"
    )


@pytest.mark.parametrize("identifier", sorted(OBLIGATIONS))
def test_each_obligation_names_real_assertions_and_evidence(identifier: str) -> None:
    """Every reference an obligation makes resolves."""
    entry = OBLIGATIONS[identifier]
    assert entry["assertions"], f"{identifier} names no assertion"
    undeclared = sorted(set(entry["assertions"]) - set(DECLARED))
    assert not undeclared, f"{identifier} names undeclared assertions {undeclared}"
    assert entry["retained"], f"{identifier} names no evidence outside the model"
    missing = [path for path in entry["retained"] if not (REPO_ROOT / path).exists()]
    assert not missing, f"{identifier} names missing evidence {missing}"


@pytest.mark.parametrize("identifier", sorted(OBLIGATIONS))
def test_each_obligation_is_exercised_by_the_mandatory_suite(identifier: str) -> None:
    """An obligation is backed by a routine run of the right kind.

    A limitation is backed by an expected counterexample and by nothing that
    would read as assurance of the property it says the protocol lacks; every
    other obligation is backed by at least one assurance run.
    """
    routine = [run for run in RUNS.values() if run.get("tier", "routine") == "routine"]
    classes = {run["class"] for run in routine if identifier in run.get("obligations", ())}
    limitation = OBLIGATIONS[identifier].get("limitation", False)
    wanted = "expected-counterexample" if limitation else "assurance"
    assert wanted in classes, f"{identifier} has no routine {wanted} run"


def test_every_run_names_obligations_that_exist() -> None:
    """A run is evidence of something the mapping defines."""
    silent = [run["id"] for run in RUNS.values() if not run.get("obligations")]
    assert not silent, f"runs naming no obligation: {silent}"
    named = {name for run in RUNS.values() for name in run.get("obligations", ())}
    unknown = sorted(named - set(OBLIGATIONS))
    assert not unknown, f"runs name unknown obligations {unknown}"


def test_every_assertion_is_accounted_for_by_an_obligation() -> None:
    """No property is checked without a contract sentence behind it."""
    cited = {name for entry in OBLIGATIONS.values() for name in entry["assertions"]}
    orphaned = sorted(set(DECLARED) - cited)
    assert not orphaned, f"assertions no obligation cites: {orphaned}"


def test_every_assertion_can_be_seen_to_fail_or_says_why_not() -> None:
    """Each assertion has a control that must fail it, or a stated reason.

    A property that nothing is required to break has not been shown to
    discriminate. The suite's controls and expected counterexamples are the
    demonstrations; the mapping lists the few assertions that have none, and
    a listed assertion that acquires a control must be removed from the list.
    """
    failed = {failed_assertion(run) for run in RUNS.values()} - {""}
    excused = {entry["assertion"]: entry["reason"] for entry in MAPPING["uncontrolled"]}
    assert all(reason.strip() for reason in excused.values())
    assert set(excused) <= set(DECLARED), "an excused assertion is not declared"
    assert not failed & set(excused), (
        f"now controlled, so no longer excused: {sorted(failed & set(excused))}"
    )
    bare = sorted(set(DECLARED) - failed - set(excused))
    assert not bare, f"assertions nothing is required to fail: {bare}"


def test_the_strong_properties_are_never_reported_as_assurance() -> None:
    """A recorded limitation stays visibly apart from a passing claim.

    The strong freshness properties are expected to fail wherever the
    environment can move inside the command window. They may be named as
    failing only by runs of the expected-counterexample class, and every
    such run must name one of them.
    """
    mixed = [
        run["id"]
        for run in RUNS.values()
        if (failed_assertion(run) in STRONG) != (run["class"] == "expected-counterexample")
    ]
    assert not mixed, f"runs mixing a recorded limitation with another class: {mixed}"
    limited = {
        name
        for entry in OBLIGATIONS.values()
        if entry.get("limitation")
        for name in entry["assertions"]
    }
    assert STRONG <= limited, "a strong property is not mapped to a limitation"


def scenario_calls(run: dict) -> list[ast.Call]:
    """Return the ``scenario()`` and ``snapshot()`` calls of a readiness run.

    A run of another specification, or one with no scenario, has none.
    """
    if run.get("spec", "readiness.fizz") != "readiness.fizz" or "scenario" not in run:
        return []
    return [
        node
        for node in ast.walk(ast.parse(run["scenario"]))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in BUILDERS
    ]


def reachability_problems(run_id: str, call: ast.Call) -> list[str]:
    """Return how one ``scenario()`` call relies on reachability.

    A ``snapshot()`` row states its expectations through the invariants and
    the progress property by construction, so it has none.
    """
    if getattr(call.func, "id", "") == "snapshot":
        return []
    stated = {key.arg: ast.literal_eval(key.value) for key in call.keywords}
    defaulted = [
        f"run {run_id} leaves {name} at its reachable default"
        for name in ("expect_ready", "expect_merge")
        if name not in stated
    ]
    switched = [
        f"run {run_id} asks for {name}={stated[name]!r}"
        for name, switched_on in WITNESSES.items()
        if stated.get(name, "unchecked") in switched_on
    ]
    return defaulted + switched


def test_a_run_with_several_scenarios_declares_nothing_reachable() -> None:
    """A reachability assertion covers the whole explored graph, not one row.

    Init chooses among the scenarios of a run, and an ``exists`` assertion is
    satisfied by any state anywhere. One scenario that does not ask for
    reachability would therefore satisfy it for every other scenario of the
    same run. A run with more than one scenario must state its per-scenario
    outcomes through the invariants and the progress property instead, which
    are checked on every path: each ``scenario()`` call states
    ``expect_ready`` and ``expect_merge`` explicitly, and no expectation that
    an ``exists`` assertion reads is switched on. ``snapshot()`` rows do this
    by construction.
    """
    problems = [
        problem
        for run in RUNS.values()
        if len(calls := scenario_calls(run)) > 1
        for call in calls
        for problem in reachability_problems(run["id"], call)
    ]
    assert not problems, (
        "another scenario of the same run would satisfy these: " + "; ".join(problems)
    )
