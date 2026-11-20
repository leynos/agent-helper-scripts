"""Render model-checking outcomes as the JSON report and the text summary.

``model_check`` executes runs and returns ``Outcome`` records; this module
only presents them. The report is the machine-readable evidence a gate run
leaves behind, and the summary is what a person reads. Expected
counterexamples get their own heading in the summary, so a recorded
limitation is never read as a passing assurance claim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import TYPE_CHECKING

from model_check_suite import CLASSES, Suite

if TYPE_CHECKING:
    from model_check import Outcome

#: Summary headings, one per class. Expected counterexamples have their own,
#: so a recorded limitation is never read as a passing assurance claim.
_HEADINGS = {
    "assurance": "Assurance (must pass)",
    "negative-control": "Negative controls (a mutation must fail its assertion)",
    "property-control": "Property controls (the assertion must be able to fail)",
    "expected-counterexample": (
        "Expected counterexamples (recorded limitations, not assurance)"
    ),
    "scenario-trace": "Scenario traces (one named event sequence each)",
}


def run_line(document: Mapping[str, object], target: Path) -> str:
    """Return the one-line account of an invocation: checker, tier, cost, report."""
    checker = document["checker"]
    peak = int(document["peak_child_rss_kib"]) // 1024  # type: ignore[call-overload]
    return (
        f"FizzBee {checker['version']}; tier {document['tier']};"  # type: ignore[index]
        f" {document['jobs']} at a time; {document['wall_seconds']}s;"
        f" peak checker RSS {peak} MiB; report in {target}"
    )


def write_report(document: Mapping[str, object], directory: Path) -> Path:
    """Write ``report.json`` into the report directory and return its path."""
    target = directory / "report.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target


def _run_record(outcome: Outcome) -> dict:
    """Return one run's entry in the report."""
    run, reading = outcome.run, outcome.reading
    return {
        "id": run.id,
        "class": run.kind,
        "tier": run.tier,
        "spec": run.spec,
        "spec_sha256": outcome.spec_sha256,
        "mutated": bool(run.mutations),
        "replayed_steps": len(run.trace),
        "options": dict(run.options),
        "command": list(outcome.command),
        "expected": run.expectation.describe(),
        "status": outcome.status,
        "ok": outcome.ok,
        "detail": outcome.detail,
        "nodes": reading.nodes,
        "queued": reading.queued,
        "unique_states": reading.unique_states,
        "temporal_checked": list(reading.checked_temporal),
        "seconds": round(outcome.seconds, 2),
        "obligations": list(run.obligations),
        "trace": list(outcome.trace),
    }


def report(suite: Suite, outcomes: Sequence[Outcome], *, tier: str, partial: bool) -> dict:
    """Return the run metadata as a JSON-serializable report.

    Parameters
    ----------
    suite : Suite
        The suite that was run.
    outcomes : sequence of Outcome
        One judgement per executed run.
    tier : str
        The tier that was selected.
    partial : bool
        Whether a named subset was run, which is never a gate result.

    Returns
    -------
    dict
        Checker identity, selection, completion status and per-run facts.
    """
    return {
        "checker": {
            "name": "FizzBee",
            "version": suite.checker.version,
            "archive_sha256": suite.checker.archive_sha256,
        },
        "suite": str(suite.path),
        "tier": tier,
        "partial": partial,
        "exploration": "exhaustive breadth-first search of a finite model",
        "ok": bool(outcomes) and all(outcome.ok for outcome in outcomes),
        "runs": [_run_record(outcome) for outcome in outcomes],
    }


def _outcome_lines(outcome: Outcome) -> list[str]:
    """Return one run's lines in the summary, with its trace when it failed."""
    counts = ""
    if outcome.reading.unique_states is not None:
        counts = f" [{outcome.reading.unique_states} states, {outcome.seconds:.1f}s]"
    mark = "ok  " if outcome.ok else "FAIL"
    lines = [f"  {mark} {outcome.run.id}: {outcome.status} ({outcome.detail}){counts}"]
    if not outcome.ok and outcome.trace:
        lines.append("       trace: " + " -> ".join(outcome.trace))
        lines.append(f"       kept in {outcome.artefacts['directory']}")
    return lines


def _verdict_lines(outcomes: Sequence[Outcome], *, partial: bool) -> list[str]:
    """Return the closing lines: whether this was a gate result, and its verdict."""
    failed = sum(not outcome.ok for outcome in outcomes)
    lines = ["PARTIAL: a named subset was run; this is not a gate result."] if partial else []
    if failed or not outcomes:
        return [*lines, f"model-check: FAILED ({failed} of {len(outcomes)} runs)"]
    return [*lines, f"model-check: {len(outcomes)} runs met their expectations"]


def summarize(outcomes: Sequence[Outcome], *, partial: bool) -> str:
    """Return the human-readable summary, one section per run class.

    Expected counterexamples are listed under their own heading so that a
    recorded limitation is never read as a passing assurance claim.
    """
    lines: list[str] = []
    for kind in CLASSES:
        group = [outcome for outcome in outcomes if outcome.run.kind == kind]
        if group:
            lines.append(_HEADINGS[kind])
            lines.extend(line for outcome in group for line in _outcome_lines(outcome))
    lines.extend(_verdict_lines(outcomes, partial=partial))
    return "\n".join(lines)
