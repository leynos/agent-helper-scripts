"""Read the pinned FizzBee release's output and judge a run against it.

The pinned release reports a failed property on standard output and still
exits zero, drops liveness checking without comment when the ``liveness``
option is not a value it knows, stops at ``max_actions`` without saying so,
and prints its pass line for a replayed trace whose last step it refused.
This module therefore decides only from output it recognizes. It requires
the checker to echo the options it was given and to name every temporal
assertion it checked, counts a pass as exhaustive only when fewer nodes were
explored than the action bound allows, and counts the steps of a replay from
the nodes reported. Anything else is a gate failure: an unknown line is never
read as success, and a crash, a timeout or a syntax error is never read as a
control detecting its defect.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import re

from model_check_suite import Expectation, Run

PASS_LINE = "PASSED: Model checker completed successfully"
_DEADLOCK = "DEADLOCK detected"

#: Lines that state the outcome on their own, and the kind each states. A
#: bare failure line is a deadlock only when the deadlock line preceded it.
_EXACT_OUTCOMES = {
    PASS_LINE: "pass",
    "FAILED: Expected states never reached": "exists",
    "FAILED: Liveness check failed": "liveness",
    "FAILED: Model checker failed": "bare",
}

#: Failure lines that name their assertion in the same line.
_NAMED_OUTCOMES = (
    (re.compile(r"^FAILED: Model checker failed\. Invariant:\s+(\w+)$"), "always"),
    (
        re.compile(r"^FAILED: Model checker failed\. Transition Invariant:\s+(\w+)$"),
        "transition",
    ),
)

#: Failure kinds whose assertions are named on the lines that follow, with
#: how those lines look and how many of them there can be.
_NAMES_AFTER = {
    "exists": (re.compile(r"^Invariant \d+: (\w+)$"), None),
    "liveness": (re.compile(r"^Invariant: (\w+)$"), 1),
}

#: Lines that state a count or a configuration, the fields each fills, and
#: which group of the match fills each field.
_FACT_LINES = (
    (re.compile(r"^Nodes: (\d+), queued: (\d+)$"), (("nodes", 1), ("queued", 2))),
    (
        re.compile(r"^Valid Nodes: (\d+) Unique states: (\d+)$"),
        (("valid_nodes", 1), ("unique_states", 2)),
    ),
    (re.compile(r"^StateSpaceOptions: (.*)$"), (("options_echo", 1),)),
    (re.compile(r"^Loaded trace with (\d+) links$"), (("trace_loaded", 1),)),
    (
        re.compile(
            r"^WARNING: Trace execution incomplete\. Expected (\d+) links,"
            r" executed (\d+) links\.$"
        ),
        (("trace_executed", 2),),
    ),
)

_CHECKING = re.compile(r"^Checking (?:eventually always|always eventually) (\w+)$")
_TEMPORAL = re.compile(
    r"^(?:eventually always|always eventually) assertion (\w+)\s*:", re.MULTILINE
)


@dataclass(frozen=True)
class ProcessResult:
    """What the process boundary observed for one checker invocation.

    ``exit_code`` is ``None`` when the checker did not exit of its own accord:
    it was stopped at the timeout or by a signal.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    seconds: float = 0.0


@dataclass(frozen=True)
class Reading:
    """What one invocation's output says, before any expectation is applied."""

    passed: bool = False
    failure_kind: str = ""
    failed_assertions: tuple[str, ...] = ()
    nodes: int | None = None
    queued: int | None = None
    unique_states: int | None = None
    valid_nodes: int | None = None
    options_echo: str = ""
    checked_temporal: tuple[str, ...] = ()
    trace_loaded: int | None = None
    trace_executed: int | None = None
    problem: str = ""


#: A judgement: whether the run met its expectation, a one-word status, the
#: reason, and the facts read from the output.
Judgement = tuple[bool, str, str, Reading]


@dataclass
class _Scan:
    """The facts and outcomes gathered while reading one output."""

    facts: dict[str, object] = field(default_factory=dict)
    checked: list[str] = field(default_factory=list)
    outcomes: list[tuple[str, list[str]]] = field(default_factory=list)


def _record_fact(scan: _Scan, line: str) -> bool:
    """Record a count, configuration or checked-assertion line, if it is one."""
    for pattern, fields in _FACT_LINES:
        if match := pattern.match(line):
            scan.facts.update(
                {name: _value(match[group]) for name, group in fields}
            )
            return True
    if match := _CHECKING.match(line):
        scan.checked.append(match[1])
        return True
    return False


def _value(text: str) -> object:
    """Return a captured group as an ``int`` when it is digits, else text."""
    return int(text) if text.isdigit() else text


def _names_after(lines: Sequence[str], index: int, kind: str) -> list[str]:
    """Return the assertion names the lines after a failure line carry."""
    pattern, limit = _NAMES_AFTER[kind]
    names: list[str] = []
    for later in lines[index + 1 :]:
        match = pattern.match(later)
        if match is None or len(names) == limit:
            break
        names.append(match[1])
    return names


def _exact_outcome(lines: Sequence[str], index: int, kind: str) -> tuple[str, list[str]]:
    """Return the outcome a line that states it whole reports.

    A bare failure line is a deadlock only when the deadlock line preceded
    it; otherwise it is a failure that names nothing.
    """
    if kind == "bare":
        return ("deadlock" if _DEADLOCK in lines[:index] else "unnamed"), []
    if kind in _NAMES_AFTER:
        return kind, _names_after(lines, index, kind)
    return kind, []


def _patterned_outcome(line: str) -> tuple[str, list[str]] | None:
    """Return the outcome a failure line naming its assertion reports.

    Any other line that starts ``FAILED`` is a failure this module does not
    know, and is reported as such rather than skipped.
    """
    for pattern, named in _NAMED_OUTCOMES:
        if match := pattern.match(line):
            return named, [match[1]]
    return ("unknown", []) if line.startswith("FAILED") else None


def _outcome(lines: Sequence[str], index: int) -> tuple[str, list[str]] | None:
    """Return the outcome one line states, with the assertions it names."""
    kind = _EXACT_OUTCOMES.get(lines[index])
    if kind is None:
        return _patterned_outcome(lines[index])
    return _exact_outcome(lines, index, kind)


def _failure_problem(failures: Sequence[str], names: Sequence[str]) -> str:
    """Return why the reported failures cannot be judged, or nothing.

    Exactly one recognized failure is judgeable, and it must name its
    assertion unless it is a deadlock, which has none.
    """
    if len(failures) != 1 or failures[0] in ("unknown", "unnamed"):
        return "output reports no recognized pass or failure"
    if failures[0] != "deadlock" and not names:
        return "a failure names no assertion"
    return ""


def _conclude(scan: _Scan) -> Reading:
    """Turn the gathered outcomes into one reading, or name the problem."""
    facts: dict = {**scan.facts, "checked_temporal": tuple(scan.checked)}
    failures = [kind for kind, _ in scan.outcomes if kind != "pass"]
    names = tuple(name for _, found in scan.outcomes for name in found)
    if len(failures) < len(scan.outcomes):
        problem = "output reports both a pass and a failure" if failures else ""
        return Reading(passed=not failures, problem=problem, **facts)
    if not failures and facts.get("trace_executed") is not None:
        return Reading(failure_kind="blocked", **facts)
    problem = _failure_problem(failures, names)
    if problem:
        return Reading(problem=problem, **facts)
    return Reading(failure_kind=failures[0], failed_assertions=names, **facts)


def read_output(stdout: str) -> Reading:
    """Read one invocation's standard output into facts.

    Parameters
    ----------
    stdout : str
        Everything the checker printed.

    Returns
    -------
    Reading
        The pass or failure it reports, the assertions it names, its
        counts, the options it echoed and the temporal assertions it says it
        checked. ``problem`` is set when the output reports neither or both
        outcomes, or reports a failure without naming it.
    """
    lines = [line.rstrip() for line in stdout.splitlines()]
    scan = _Scan()
    for index, line in enumerate(lines):
        if _record_fact(scan, line):
            continue
        if (found := _outcome(lines, index)) is not None:
            scan.outcomes.append(found)
    return _conclude(scan)


def _echo_disagreement(echo: str, options: Mapping[str, object]) -> str:
    """Return how the echoed options differ from the requested ones, if at all.

    The checker prints protobuf text, whose spacing is deliberately unstable,
    so each field is matched on its own.
    """
    wanted = {
        "max_actions": str(options["max_actions"]),
        "max_concurrent_actions": str(options["max_concurrent_actions"]),
        "crash_on_yield": str(options["crash_on_yield"]).lower(),
        "deadlock_detection": str(options["deadlock_detection"]).lower(),
        "liveness": f'"{options["liveness"]}"',
    }
    for name, value in wanted.items():
        found = re.search(rf"\b{name}:\s*(\"[^\"]*\"|\w+)", echo)
        echoed = found[1] if found else None
        if echoed != value:
            return f"the checker did not echo {name}:{value}"
    return ""


def _process_refusal(run: Run, result: ProcessResult) -> tuple[str, str] | None:
    """Return why the process itself gives no result, if it gives none."""
    if result.timed_out:
        return "inconclusive", f"the checker did not finish within {run.timeout_seconds}s"
    if result.exit_code is None:
        return "interrupted", "the checker was stopped by a signal"
    if result.exit_code != 0:
        last = result.stderr.strip() or result.stdout.strip() or "no output"
        return "error", (
            f"the checker exited with status {result.exit_code}:"
            f" {last.splitlines()[-1]}"
        )
    return None


def _reading_refusal(run: Run, reading: Reading) -> tuple[str, str] | None:
    """Return why the output cannot be judged against this run, if it cannot."""
    if reading.problem:
        return "unrecognized", reading.problem
    if run.trace:
        return None
    if reading.failure_kind == "blocked" or reading.trace_loaded is not None:
        return "unrecognized", "trace output from an exploration"
    disagreement = _echo_disagreement(reading.options_echo, run.options)
    return ("misconfigured", disagreement) if disagreement else None


def judge(run: Run, result: ProcessResult, spec_text: str) -> Judgement:
    """Judge one invocation against its run's expectation.

    Parameters
    ----------
    run : Run
        The run and the outcome it must have.
    result : ProcessResult
        What the process boundary observed.
    spec_text : str
        The specification as it was checked, after any mutation.

    Returns
    -------
    tuple of (bool, str, str, Reading)
        Whether the run met its expectation, a one-word status, the reason,
        and the facts read from the output.
    """
    reading = read_output(result.stdout)
    refusal = _process_refusal(run, result) or _reading_refusal(run, reading)
    if refusal is not None:
        return False, refusal[0], refusal[1], reading
    if run.trace:
        return _judge_trace(run, reading)
    if run.expectation.passes:
        return _judge_pass(run, reading, spec_text)
    return _judge_failure(run.expectation, reading)


def _executed_steps(reading: Reading, steps: int) -> int | None:
    """Return how many steps of a replay ran, or ``None`` when unknowable.

    A replay that printed the pass line reports its count only through the
    nodes it explored: one for the initial state and one per step. A
    warning beside a pass line contradicts it, so neither is believed.
    """
    executed = reading.trace_executed
    if reading.passed:
        executed = None if executed is not None else _steps_from_nodes(reading)
    in_range = executed is not None and 0 <= executed <= steps
    return executed if in_range else None


def _steps_from_nodes(reading: Reading) -> int | None:
    """Return the steps a passing replay ran, from the nodes it reported."""
    return None if reading.valid_nodes is None else reading.valid_nodes - 1


def _judge_trace(run: Run, reading: Reading) -> Judgement:
    """Judge a replayed event sequence: run to its end, or refused where stated.

    The pinned checker stops a replay at a step the model does not enable or
    that would break an assertion. It warns, with the number of steps it
    executed, when it stops early, but it prints its pass line with no
    warning when the step it could not take was the last one. A replay
    explores nothing else, so this is evidence about one sequence only.
    """
    steps = len(run.trace)
    if reading.trace_loaded != steps:
        return False, "unrecognized", (
            f"the checker loaded {reading.trace_loaded} trace steps, not {steps}"
        ), reading
    executed = _executed_steps(reading, steps)
    if executed is None:
        return False, "unrecognized", "a replay without a usable step count", reading
    if run.expectation.passes:
        return _replayed(executed, steps, reading)
    return _refused(run.expectation, executed, steps, reading)


def _replayed(executed: int, steps: int, reading: Reading) -> Judgement:
    """Judge a replay that must run to its end."""
    if executed == steps:
        return True, "replayed", f"all {steps} steps are a behaviour", reading
    return False, "refused", (
        f"the model refused the trace after {executed} of {steps} steps"
    ), reading


def _refused(expected: Expectation, executed: int, steps: int, reading: Reading) -> Judgement:
    """Judge a replay that must be refused after a stated number of steps."""
    if executed == steps:
        return False, "undetected", (
            f"expected {expected.describe()}; the trace ran to its end"
        ), reading
    if executed != expected.executed:
        return False, "wrong-failure", (
            f"expected {expected.describe()}; refused after {executed}"
        ), reading
    return True, "refused-as-expected", expected.describe(), reading


def _incomplete(run: Run, reading: Reading, spec_text: str) -> tuple[str, str] | None:
    """Return why a pass is not an exhaustive, liveness-checked one, if not."""
    if None in (reading.nodes, reading.queued, reading.unique_states):
        return "unrecognized", "a pass without state counts"
    if reading.queued != 0:
        return "inconclusive", f"{reading.queued} nodes were still queued"
    bound = run.options["max_actions"]
    if reading.nodes >= bound:  # type: ignore[operator]
        return "inconclusive", (
            f"{reading.nodes} nodes reached the max_actions bound of {bound};"
            " exploration may have been cut short"
        )
    missing = sorted(set(_TEMPORAL.findall(spec_text)) - set(reading.checked_temporal))
    if missing:
        return "unchecked", "the checker did not report checking: " + ", ".join(missing)
    return None


def _judge_pass(run: Run, reading: Reading, spec_text: str) -> Judgement:
    """Judge a run that must pass, exhaustively and with liveness checked."""
    if not reading.passed:
        named = ", ".join(reading.failed_assertions) or reading.failure_kind
        return False, "failed", (
            f"expected a pass; the checker reports {reading.failure_kind}: {named}"
        ), reading
    incomplete = _incomplete(run, reading, spec_text)
    if incomplete is not None:
        return False, incomplete[0], incomplete[1], reading
    return True, "passed", "exhaustive", reading


def _judge_failure(expected: Expectation, reading: Reading) -> Judgement:
    """Judge a run that must fail one named assertion and no other."""
    if reading.passed:
        return False, "undetected", (
            f"expected {expected.describe()}; the checker passed"
        ), reading
    wanted = () if expected.kind == "deadlock" else (expected.assertion,)
    if (reading.failure_kind, reading.failed_assertions) != (expected.kind, wanted):
        named = ", ".join(reading.failed_assertions) or "no assertion"
        return False, "wrong-failure", (
            f"expected {expected.describe()}; got {reading.failure_kind}: {named}"
        ), reading
    return True, "failed-as-expected", expected.describe(), reading


def missing_steps(expected: Expectation, trace: Sequence[str]) -> list[str]:
    """Return the `via` steps the counterexample does not pass through in order.

    A control fails for its intended reason only when its counterexample
    uses the behaviour the control was written about: the reply shape it
    names, or the environment event it names. The steps are matched as an
    ordered subsequence, so "the head moves, then the command runs" is not
    satisfied by a trace in which the command ran first.
    """
    remaining = iter(trace)
    return [step for step in expected.via if step not in remaining]
