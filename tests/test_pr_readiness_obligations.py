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
#: Declared outcomes of a configuration rather than obligations with a guard:
#: each is failed by a property control, not by a mutation.
STRONG = {"StrongReadyFreshness", "StrongMergeFreshness"}


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
    for anchor in entry["anchors"]:
        assert normalize(anchor) in stated, (
            f"{identifier}: the section {entry['section']!r} of"
            f" {entry['document']} no longer states: {anchor}"
        )


@pytest.mark.parametrize("identifier", sorted(OBLIGATIONS))
def test_each_obligation_names_real_assertions_and_evidence(identifier: str) -> None:
    """Every reference an obligation makes resolves."""
    entry = OBLIGATIONS[identifier]
    assert entry["assertions"], f"{identifier} names no assertion"
    for name in entry["assertions"]:
        assert name in DECLARED, f"{identifier} names an undeclared assertion {name}"
    assert entry["retained"], f"{identifier} names no evidence outside the model"
    for path in entry["retained"]:
        assert (REPO_ROOT / path).exists(), f"{identifier} names a missing {path}"


@pytest.mark.parametrize("identifier", sorted(OBLIGATIONS))
def test_each_obligation_is_exercised_by_the_mandatory_suite(identifier: str) -> None:
    """An obligation is backed by a routine run of the right kind.

    A limitation is backed by an expected counterexample and by nothing that
    would read as assurance of the property it says the protocol lacks; every
    other obligation is backed by at least one assurance run.
    """
    backing = [
        run
        for run in RUNS.values()
        if identifier in run.get("obligations", ())
        and run.get("tier", "routine") == "routine"
    ]
    classes = {run["class"] for run in backing}
    if OBLIGATIONS[identifier].get("limitation"):
        assert "expected-counterexample" in classes, (
            f"{identifier} is a limitation with no reproducing counterexample"
        )
    else:
        assert "assurance" in classes, f"{identifier} has no routine assurance run"


def test_every_run_names_obligations_that_exist() -> None:
    """A run is evidence of something the mapping defines."""
    for run in RUNS.values():
        named = run.get("obligations", ())
        assert named, f"run {run['id']} names no obligation"
        unknown = sorted(set(named) - set(OBLIGATIONS))
        assert not unknown, f"run {run['id']} names unknown obligations {unknown}"


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
    failed = {
        run["expect"]["assertion"]
        for run in RUNS.values()
        if isinstance(run["expect"], dict) and "assertion" in run["expect"]
    }
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
    for run in RUNS.values():
        expect = run["expect"]
        names_strong = isinstance(expect, dict) and expect.get("assertion") in STRONG
        assert names_strong == (run["class"] == "expected-counterexample"), (
            f"run {run['id']} mixes a recorded limitation with another class"
        )
    limited = {
        name
        for entry in OBLIGATIONS.values()
        if entry.get("limitation")
        for name in entry["assertions"]
    }
    assert STRONG <= limited, "a strong property is not mapped to a limitation"


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
    witnesses = {
        "expect_ready": ("reachable",),
        "expect_merge": ("reachable",),
        "expect_recovery": ("merged", "ready"),
        "expect_stale_ready": ("reachable",),
        "expect_reentry": ("reachable",),
    }
    for run in RUNS.values():
        if run.get("spec", "readiness.fizz") != "readiness.fizz" or "scenario" not in run:
            continue
        calls = [
            node
            for node in ast.walk(ast.parse(run["scenario"]))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("scenario", "snapshot")
        ]
        if len(calls) < 2:
            continue
        for call in calls:
            if call.func.id == "snapshot":
                continue
            stated = {key.arg: ast.literal_eval(key.value) for key in call.keywords}
            for name in ("expect_ready", "expect_merge"):
                assert name in stated, (
                    f"run {run['id']} leaves {name} at its reachable default in"
                    " a run with several scenarios"
                )
            for name, switched_on in witnesses.items():
                assert stated.get(name, "unchecked") not in switched_on, (
                    f"run {run['id']} asks for {name}={stated.get(name)!r}, which"
                    " another scenario of the same run would satisfy"
                )
