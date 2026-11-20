"""Run a pinned FizzBee model-checking suite and judge it fail-closed.

A suite is a TOML manifest beside its specifications. It pins one checker
release by digest and lists runs. Each run names a specification, the checker
options, a scenario the specification is configured with, and the one outcome
that run must have:

``assurance``
    The unmodified specification must pass, exhaustively.
``negative-control``
    A textual mutation of the specification must fail one named assertion.
    Its ``of`` run is the unmutated twin, so the failure is the mutation's.
``property-control``
    The unmodified specification must fail one named assertion under a
    scenario built to defeat it, which shows the assertion is evaluated.
``expected-counterexample``
    The unmodified specification must fail one named assertion that states a
    property the modelled protocol is known not to have. These record a
    limitation and are reported apart from assurance.
``scenario-trace``
    A named sequence of events is replayed through the unmodified
    specification. It must either run to its end, which shows the sequence
    is a behaviour of the model, or be refused after a stated number of
    steps, which shows the model does not permit the step that follows.

The launcher has three layers. ``model_check_suite`` loads and validates the
manifest; ``model_check_judge`` reads the checker's output and judges a run
against it, because the pinned release cannot be trusted to report its own
result; and this module installs the release, executes runs and reports. It
re-exports the names the command line and the tests use, so they import one
module.

The process boundary is injected. The sibling ``model_check_cli`` module
supplies the Cuprum-backed runner and the downloader; tests supply doubles.

Examples
--------
Run the mandatory suite::

    uv run --script scripts/model_check_cli.py check \\
        --suite specs/pr-readiness/suite.toml
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

from model_check_judge import (
    PASS_LINE,
    Judgement,
    ProcessResult,
    Reading,
    judge,
    missing_steps,
    read_output,
)
from model_check_suite import (
    CLASSES,
    FAILURE_KINDS,
    REQUIRED_OPTIONS,
    TIERS,
    Checker,
    Expectation,
    ModelCheckError,
    Run,
    Suite,
    load_suite,
    select,
    unknown_assertions,
)

__all__ = (
    "CLASSES",
    "DEFAULT_REPORT",
    "FAILURE_KINDS",
    "SUPPORTED_PLATFORM",
    "PASS_LINE",
    "REQUIRED_OPTIONS",
    "TIERS",
    "CheckOptions",
    "Checker",
    "Expectation",
    "Fetcher",
    "Host",
    "Judgement",
    "ModelCheckError",
    "Outcome",
    "ProcessResult",
    "Reading",
    "Run",
    "Runner",
    "Session",
    "Suite",
    "execute",
    "install_checker",
    "judge",
    "load_session",
    "load_suite",
    "locate_checker",
    "missing_steps",
    "mutate",
    "read_output",
    "render_options",
    "report",
    "require_platform",
    "reset_report",
    "run_line",
    "run_suite",
    "select",
    "summarize",
    "unknown_assertions",
    "workers",
    "write_report",
)

#: Runs one checker invocation: ``(argv, cwd, timeout_seconds)``.
Runner = Callable[[Sequence[str], Path, int], ProcessResult]

#: Fetches ``url`` to ``destination``.
Fetcher = Callable[[str, Path], None]

#: The one platform the pinned archive supports.
SUPPORTED_PLATFORM = ("Linux", "x86_64")

#: Where run directories, traces and the report are written. ``build`` is
#: ignored by Git and pruned by the repository's discovery walks.
DEFAULT_REPORT = Path("build") / "model-check"

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


@dataclass(frozen=True)
class Outcome:
    """The judgement on one run, with the facts it rests on."""

    run: Run
    ok: bool
    status: str
    detail: str
    reading: Reading
    seconds: float
    spec_sha256: str
    command: tuple[str, ...]
    trace: tuple[str, ...] = ()
    artefacts: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Session:
    """What every run of one invocation shares.

    ``report`` is the directory each run gets a subdirectory of; ``fizz`` is
    the verified checker launcher; ``runner`` is the process boundary.
    """

    suite: Suite
    fizz: Path
    report: Path
    runner: Runner


@dataclass(frozen=True)
class Host:
    """The facts about the machine the commands read, supplied by the caller.

    The command line builds one from the running host at its edge; a test
    builds one for a host it describes. ``home`` is where the pinned release
    is unpacked unless the options name another directory; ``clock`` is a
    monotonic clock in seconds; ``peak_child_rss_kib`` reports the
    high-water mark over every child process waited for so far.
    """

    platform: tuple[str, str]
    cpu_count: int
    home: Path
    clock: Callable[[], float]
    peak_child_rss_kib: Callable[[], int]


@dataclass(kw_only=True)
class CheckOptions:
    """What one ``check`` invocation runs, and where.

    The command line flattens these fields into the command's own flags and
    ``MODEL_CHECK_*`` variables, so ``--suite`` and ``--only`` are spelled as
    if they were separate parameters.

    Attributes
    ----------
    suite
        The suite manifest.
    tier
        ``routine`` runs the mandatory checks. ``extended`` runs those and
        the larger explorations.
    only
        Run identifiers to restrict the run to while iterating. A subset is
        reported as partial and is not a gate result.
    home
        Directory the pinned release was unpacked into; by default the
        host's checker home.
    report
        Directory for run directories, traces and ``report.json``.
    jobs
        Checker processes to run at once; zero selects up to four, bounded
        by the available processors.
    """

    suite: Path
    tier: str = "routine"
    only: list[str] = field(default_factory=list)
    home: Path | None = None
    report: Path = DEFAULT_REPORT
    jobs: int = 0


def require_platform(host: Host) -> None:
    """Refuse a host the pinned archive was not built for.

    Raises
    ------
    ModelCheckError
        Raised for any platform other than ``SUPPORTED_PLATFORM``.
    """
    if host.platform != SUPPORTED_PLATFORM:
        raise ModelCheckError(
            f"the pinned FizzBee archive supports {SUPPORTED_PLATFORM[0]}"
            f" {SUPPORTED_PLATFORM[1]} only; this is {host.platform[0]}"
            f" {host.platform[1]}. The model-check gate is unsupported here."
        )


def workers(jobs: int, host: Host) -> int:
    """Return how many checker processes to run at once."""
    return jobs or max(1, min(4, host.cpu_count))


def load_session(
    options: CheckOptions, host: Host, runner: Runner
) -> tuple[Session, tuple[Run, ...]]:
    """Load the suite, verify the checker, and return the runs to execute.

    Nothing is written: the report directory is resolved but neither
    created nor emptied. ``reset_report`` does that, at the caller.

    Raises
    ------
    ModelCheckError
        Raised for an invalid suite, an expectation naming an undeclared
        assertion, a missing or altered checker, or an unknown run.
    """
    loaded = load_suite(options.suite)
    problems = unknown_assertions(loaded)
    if problems:
        raise ModelCheckError("; ".join(problems))
    fizz = locate_checker(options.home or host.home, loaded.checker)
    runs = select(loaded, options.tier, options.only)
    session = Session(
        suite=loaded, fizz=fizz, report=options.report.resolve(), runner=runner
    )
    return session, runs


def reset_report(directory: Path) -> None:
    """Delete the report directory and create it empty.

    A stale run directory would otherwise be read as part of this
    invocation's evidence.
    """
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)


def run_suite(session: Session, runs: Sequence[Run], jobs: int) -> list[Outcome]:
    """Execute every run, ``jobs`` at a time, and return their outcomes in order."""
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(lambda run: execute(run, session), runs))


def write_report(document: Mapping[str, object], directory: Path) -> Path:
    """Write ``report.json`` into the report directory and return its path."""
    target = directory / "report.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target


def run_line(document: Mapping[str, object], target: Path) -> str:
    """Return the one-line account of an invocation: checker, tier, cost, report."""
    checker = document["checker"]
    peak = int(document["peak_child_rss_kib"]) // 1024  # type: ignore[call-overload]
    return (
        f"FizzBee {checker['version']}; tier {document['tier']};"  # type: ignore[index]
        f" {document['jobs']} at a time; {document['wall_seconds']}s;"
        f" peak checker RSS {peak} MiB; report in {target}"
    )


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file, read in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_checker(home: Path, checker: Checker) -> Path:
    """Return the pinned ``fizz`` launcher, verified file by file.

    Parameters
    ----------
    home : Path
        The directory the release was unpacked into.
    checker : Checker
        The pin the unpacked files must match.

    Returns
    -------
    Path
        The ``fizz`` launcher inside the unpacked release.

    Raises
    ------
    ModelCheckError
        Raised when a pinned file is absent, which is a missing checker, or
        has another digest, which is an incompatible one.
    """
    root = home / checker.root
    for name, expected in checker.files.items():
        candidate = root / name
        if not candidate.is_file():
            raise ModelCheckError(
                f"FizzBee {checker.version} is not installed: {candidate} is"
                " missing. Run `make fizzbee` to fetch the pinned release."
            )
        actual = _sha256(candidate)
        if actual != expected:
            raise ModelCheckError(
                f"FizzBee at {root} is not the pinned {checker.version}:"
                f" {name} has SHA-256 {actual}, expected {expected}"
            )
    return root / "fizz"


def install_checker(home: Path, checker: Checker, fetch: Fetcher) -> Path:
    """Fetch, verify and unpack the pinned release unless it is present.

    Parameters
    ----------
    home : Path
        The directory to unpack into. It is created when absent.
    checker : Checker
        The release to install and the digests it must have.
    fetch : Fetcher
        Downloads the archive. This is the only step that uses the network.

    Returns
    -------
    Path
        The verified ``fizz`` launcher.

    Raises
    ------
    ModelCheckError
        Raised when the downloaded archive has another digest, or the
        unpacked files do not match the pin.
    """
    try:
        return locate_checker(home, checker)
    except ModelCheckError:
        pass
    home.mkdir(parents=True, exist_ok=True)
    archive = home / f"{checker.root}.tar.gz.partial"
    try:
        fetch(checker.url, archive)
        actual = _sha256(archive)
        if actual != checker.archive_sha256:
            raise ModelCheckError(
                f"downloaded FizzBee archive has SHA-256 {actual}, expected"
                f" {checker.archive_sha256}; nothing was unpacked"
            )
        shutil.rmtree(home / checker.root, ignore_errors=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(home, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise ModelCheckError(f"cannot install FizzBee: {error}") from error
    finally:
        archive.unlink(missing_ok=True)
    return locate_checker(home, checker)


def mutate(source: str, mutations: Sequence[tuple[str, str]], run_id: str) -> str:
    """Apply each textual mutation, which must match exactly once.

    Parameters
    ----------
    source : str
        The specification text.
    mutations : sequence of (str, str)
        ``(old, new)`` pairs applied in order.
    run_id : str
        Names the run in a refusal.

    Returns
    -------
    str
        The mutated specification.

    Raises
    ------
    ModelCheckError
        Raised when an anchor matches nowhere or more than once. A control
        whose anchor has drifted would otherwise run the unmutated text and
        prove nothing.
    """
    for old, new in mutations:
        found = source.count(old)
        if found != 1:
            raise ModelCheckError(
                f"run `{run_id}`: a mutation anchor matches {found} times,"
                f" expected exactly once: {old.strip().splitlines()[0]!r}"
            )
        source = source.replace(old, new)
    return source


def render_options(options: Mapping[str, object]) -> str:
    """Return the ``fizz.yaml`` that states every checker option."""
    flag = {True: "true", False: "false"}
    return (
        f"deadlock_detection: {flag[bool(options['deadlock_detection'])]}\n"
        f'liveness: "{options["liveness"]}"\n'
        "options:\n"
        f"  max_actions: {options['max_actions']}\n"
        f"  max_concurrent_actions: {options['max_concurrent_actions']}\n"
        f"  crash_on_yield: {flag[bool(options['crash_on_yield'])]}\n"
    )


def _step_name(step: object) -> str:
    """Return one error-trace step's action name, or nothing for a non-step.

    The scenario choice in Init prints the whole scenario record; one word
    says as much.
    """
    name = step.get("Name") if isinstance(step, dict) else None
    if not isinstance(name, str):
        return ""
    return "Any:cfg" if name.startswith("Any:cfg=") else name


def _trace(output: Path) -> tuple[str, ...]:
    """Return the action names of the checker's error trace, if it wrote one."""
    try:
        steps = json.loads((output / "error-graph.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(steps, list):
        return ()
    return tuple(name for name in map(_step_name, steps) if name)


def _prepare(run: Run, suite: Suite, work: Path) -> tuple[str, str, list[str]]:
    """Write one run's inputs into ``work``; return its source, text and argv.

    The checker writes beside the specification it is given, so the
    specification is copied into the run's own directory and the source tree
    is never written to.
    """
    source = suite.directory / run.spec
    try:
        original = source.read_text(encoding="utf-8")
    except OSError as error:
        raise ModelCheckError(f"run `{run.id}`: cannot read {source}: {error}") from error
    text = mutate(original, run.mutations, run.id)
    work.mkdir(parents=True, exist_ok=True)
    (work / "spec.fizz").write_text(text, encoding="utf-8")
    (work / "fizz.yaml").write_text(render_options(run.options), encoding="utf-8")
    command = ["--test", "--output-dir", "out"]
    inputs = (
        ("scenario.cfg", run.scenario if run.scenario.strip() else "", "--preinit-hook-file"),
        ("replay.txt", "".join(f"{step}\n" for step in run.trace), "--trace-file"),
    )
    for name, content, flag in inputs:
        if content:
            (work / name).write_text(content, encoding="utf-8")
            command += [flag, name]
    return original, text, [*command, "spec.fizz"]


def execute(run: Run, session: Session) -> Outcome:
    """Prepare, run and judge one run in its own working directory.

    Parameters
    ----------
    run : Run
        The run to execute.
    session : Session
        The suite, the verified checker, the report directory the run's own
        directory is made in, and the process boundary.

    Returns
    -------
    Outcome
        The judgement, its facts, and the artefacts kept for inspection.

    Raises
    ------
    ModelCheckError
        Raised when the specification is unreadable or a mutation anchor
        does not match exactly once.
    """
    work = session.report / run.id
    original, text, arguments = _prepare(run, session.suite, work)
    command = (str(session.fizz), *arguments)
    result = session.runner(command, work, run.timeout_seconds)
    (work / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (work / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    ok, status, detail, reading = judge(run, result, text)
    trace = _trace(work / "out")
    if trace:
        (work / "trace.txt").write_text("\n".join(trace) + "\n", encoding="utf-8")
    absent = missing_steps(run.expectation, trace) if ok else []
    if absent:
        ok, status = False, "wrong-reason"
        detail = "the counterexample does not pass through: " + ", ".join(absent)
    return Outcome(
        run=run,
        ok=ok,
        status=status,
        detail=detail,
        reading=reading,
        seconds=result.seconds,
        spec_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        command=command,
        trace=trace,
        artefacts={"directory": str(work)},
    )


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
