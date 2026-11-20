"""Behavioural tests for the model-checking report and summary.

``scripts/model_check_report.py`` is what a person and a later tool read
after a gate run: the summary groups runs by class and states the verdict,
and the JSON report keeps each run's facts. These tests build outcomes
directly, without running the checker, and assert what each rendering must
say: an expected counterexample is never listed as assurance, an empty run
list is never a pass, and each run's evidence reaches the report.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
import importlib
from pathlib import Path
import sys
import types

import pytest

from spelling_policy_support import SCRIPTS_PATH

EXPECTED_HEADING = "Expected counterexamples (recorded limitations, not assurance)"
ASSURANCE_HEADING = "Assurance (must pass)"


@pytest.fixture(name="modules", scope="module")
def launcher_modules() -> Iterator[types.SimpleNamespace]:
    """Load the launcher's record and report modules through the runtime path."""
    directory = str(SCRIPTS_PATH)
    sys.path.insert(0, directory)
    try:
        yield types.SimpleNamespace(
            mc=importlib.import_module("model_check"),
            judge=importlib.import_module("model_check_judge"),
            report=importlib.import_module("model_check_report"),
            suite=importlib.import_module("model_check_suite"),
        )
    finally:
        sys.path.remove(directory)


def make_run(modules: types.SimpleNamespace, run_id: str, kind: str, **fields: object) -> object:
    """Return a run of one class with every other field at a plain value."""
    run = modules.suite.Run(
        id=run_id,
        tier="routine",
        kind=kind,
        purpose="a behavioural test",
        spec="readiness.fizz",
        options={"max_actions": 1000},
        scenario="",
        mutations=(),
        expectation=modules.suite.Expectation(passes=True),
        obligations=(),
        timeout_seconds=60,
    )
    return replace(run, **fields)


def make_outcome(
    modules: types.SimpleNamespace, run: object, *, ok: bool = True, **reading: object
) -> object:
    """Return a judged outcome for ``run`` with the given checker reading."""
    return modules.mc.Outcome(
        run=run,
        ok=ok,
        status="passed" if ok else "wrong-outcome",
        detail="as expected" if ok else "not as expected",
        reading=modules.judge.Reading(**reading),
        seconds=1.25,
        spec_sha256="0" * 64,
        command=("fizz", "readiness.fizz"),
    )


def make_suite(modules: types.SimpleNamespace) -> object:
    """Return a suite carrying a known checker pin and no runs."""
    checker = modules.suite.Checker(
        version="v0.5.4", url="https://example.invalid/f.tar.gz", archive_sha256="ab" * 32,
        root="fizzbee", files={},
    )
    return modules.suite.Suite(path=Path("specs/suite.toml"), checker=checker, runs=())


def sections(summary: str) -> dict[str, list[str]]:
    """Return the summary's lines grouped under the heading they follow."""
    grouped: dict[str, list[str]] = {}
    current = ""
    for line in summary.splitlines():
        if not line.startswith(" ") and not line.startswith("model-check:"):
            current = line
            grouped[current] = []
        else:
            grouped.setdefault(current, []).append(line)
    return grouped


def test_an_expected_counterexample_is_listed_only_as_a_limitation(
    modules: types.SimpleNamespace,
) -> None:
    """A recorded limitation appears under its own heading, never as assurance."""
    outcomes = [
        make_outcome(modules, make_run(modules, "permitted-path", "assurance")),
        make_outcome(modules, make_run(modules, "stale-ready", "expected-counterexample")),
    ]
    grouped = sections(modules.report.summarize(outcomes, partial=False))
    assert any("stale-ready" in line for line in grouped[EXPECTED_HEADING])
    assert not any("stale-ready" in line for line in grouped[ASSURANCE_HEADING])
    assert any("permitted-path" in line for line in grouped[ASSURANCE_HEADING])


def test_an_empty_run_list_is_never_a_pass(modules: types.SimpleNamespace) -> None:
    """Running nothing fails both the summary verdict and the report."""
    summary = modules.report.summarize([], partial=False)
    assert summary.splitlines()[-1] == "model-check: FAILED (0 of 0 runs)"
    document = modules.report.report(make_suite(modules), [], tier="routine", partial=False)
    assert document["ok"] is False
    assert document["runs"] == []


def test_a_failed_run_fails_the_verdict_and_a_subset_says_so(
    modules: types.SimpleNamespace,
) -> None:
    """One failed run fails the verdict, and a named subset is never a gate result."""
    failed = make_outcome(modules, make_run(modules, "broken", "assurance"), ok=False)
    lines = modules.report.summarize([failed], partial=True).splitlines()
    assert lines[-2:] == [
        "PARTIAL: a named subset was run; this is not a gate result.",
        "model-check: FAILED (1 of 1 runs)",
    ]


def test_the_report_keeps_each_runs_evidence(modules: types.SimpleNamespace) -> None:
    """Each run's replayed steps, temporal checks, expectation and obligations are kept."""
    expectation = modules.suite.Expectation(
        passes=False, kind="transition", assertion="ReadyNeedsCurrentEvidence"
    )
    run = make_run(
        modules,
        "trace-current-whole-plan",
        "scenario-trace",
        trace=("Init", "AgentInspectsDiscussion", "AgentDecides"),
        expectation=expectation,
        obligations=("PRR-ELIG-01", "PRR-ORDER-01"),
    )
    outcome = make_outcome(modules, run, checked_temporal=("ProgressWhenWarranted",))
    document = modules.report.report(make_suite(modules), [outcome], tier="routine", partial=False)
    [record] = document["runs"]
    assert record["id"] == "trace-current-whole-plan"
    assert record["replayed_steps"] == 3
    assert record["temporal_checked"] == ["ProgressWhenWarranted"]
    assert record["expected"] == "fail: transition ReadyNeedsCurrentEvidence"
    assert record["obligations"] == ["PRR-ELIG-01", "PRR-ORDER-01"]
    assert document["ok"] is True
    assert document["checker"]["version"] == "v0.5.4"


def test_the_run_line_names_checker_tier_jobs_time_and_memory(
    modules: types.SimpleNamespace,
) -> None:
    """The one-line account states what ran, how widely, how long and how large."""
    document = {
        "checker": {"version": "v0.5.4"},
        "tier": "routine",
        "jobs": 4,
        "wall_seconds": 72.2,
        "peak_child_rss_kib": 2_028_544,
    }
    line = modules.report.run_line(document, Path("build/model-check/report.json"))
    assert line == (
        "FizzBee v0.5.4; tier routine; 4 at a time; 72.2s;"
        " peak checker RSS 1981 MiB; report in build/model-check/report.json"
    )
