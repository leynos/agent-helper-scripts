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
result; ``model_check_report`` renders outcomes as the JSON report and the
summary; ``model_check_checker`` finds, verifies and installs the pinned
release; and this module executes runs. It
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
from typing import Protocol

from model_check_checker import (
    CheckerAbsentError,
    Fetcher,
    checker_launcher,
    install_checker,
    remove_tree,
    verify_checker,
)
from model_check_judge import (
    PASS_LINE,
    Judgement,
    ProcessResult,
    Reading,
    judge,
    missing_steps,
    read_output,
)
from model_check_report import (
    PARTIAL_STATUS,
    exit_status,
    gate_document,
    report,
    run_line,
    summarize,
    write_report,
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
    unknown_trace_steps,
)

__all__ = (
    "CLASSES",
    "DEFAULT_REPORT",
    "FAILURE_KINDS",
    "PARTIAL_STATUS",
    "SUPPORTED_PLATFORM",
    "PASS_LINE",
    "REQUIRED_OPTIONS",
    "TIERS",
    "CheckOptions",
    "Checker",
    "CheckerAbsentError",
    "Expectation",
    "Fetcher",
    "Host",
    "Judgement",
    "ModelCheckError",
    "Outcome",
    "ProcessResult",
    "Reading",
    "Run",
    "RunDirectory",
    "RunFiles",
    "Runner",
    "Session",
    "Suite",
    "execute",
    "exit_status",
    "gate_document",
    "checker_launcher",
    "install_checker",
    "judge",
    "judge_run",
    "load_session",
    "load_suite",
    "missing_steps",
    "mutate",
    "prepare_inputs",
    "read_output",
    "read_source",
    "read_trace",
    "record_artefacts",
    "remove_tree",
    "render_options",
    "report",
    "require_platform",
    "reset_report",
    "run_line",
    "run_suite",
    "select",
    "summarize",
    "unknown_assertions",
    "unknown_trace_steps",
    "verify_checker",
    "workers",
    "write_artefact",
    "write_report",
)

#: Runs one checker invocation: ``(argv, cwd, timeout_seconds)``.
Runner = Callable[[Sequence[str], Path, int], ProcessResult]

#: The one platform the pinned archive supports.
SUPPORTED_PLATFORM = ("Linux", "x86_64")

#: Where run directories, traces and the report are written. ``build`` is
#: ignored by Git and pruned by the repository's discovery walks.
DEFAULT_REPORT = Path("build") / "model-check"



class RunFiles(Protocol):
    """Where one run's inputs and artefacts are kept: its filesystem boundary.

    ``prepare_inputs`` and ``record_artefacts`` write only through this, so a
    test can hand them an in-memory implementation.
    """

    @property
    def path(self) -> Path:
        """Return the directory the checker runs in."""
        ...

    def create(self) -> None:
        """Create the run's directory."""
        ...

    def write(self, name: str, text: str) -> None:
        """Keep ``text`` as the run file ``name``."""
        ...

    def trace(self) -> tuple[str, ...]:
        """Return the action names of the checker's error trace, if any."""
        ...


@dataclass(frozen=True)
class RunDirectory:
    """A run's files on disk, under its own directory of the report."""

    path: Path

    def create(self) -> None:
        """Create the run's directory, naming it when that fails.

        Raises
        ------
        ModelCheckError
            Raised, naming the directory, when it cannot be created.
        """
        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ModelCheckError(f"cannot create {self.path}: {error}") from error

    def write(self, name: str, text: str) -> None:
        """Write one run file, naming it when that fails."""
        write_artefact(self.path / name, text)

    def trace(self) -> tuple[str, ...]:
        """Return the checker's error trace from the run's ``out`` directory."""
        return read_trace(self.path / "out")


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
    the verified checker launcher; ``runner`` is the process boundary; and
    ``run_files`` makes the filesystem boundary for one run's directory.
    """

    suite: Suite
    fizz: Path
    report: Path
    runner: Runner
    run_files: Callable[[Path], RunFiles] = RunDirectory


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
    problems = unknown_assertions(loaded) + unknown_trace_steps(loaded)
    if problems:
        raise ModelCheckError("; ".join(problems))
    fizz = verify_checker(options.home or host.home, loaded.checker)
    runs = select(loaded, options.tier, options.only)
    session = Session(
        suite=loaded, fizz=fizz, report=options.report.resolve(), runner=runner
    )
    return session, runs


def write_artefact(path: Path, text: str) -> None:
    """Write one run input or artefact, or say why it cannot be written.

    Raises
    ------
    ModelCheckError
        Raised, naming the file, when it cannot be written.
    """
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as error:
        raise ModelCheckError(f"cannot write {path}: {error}") from error


def reset_report(directory: Path) -> None:
    """Delete the report directory and create it empty.

    A stale run directory would otherwise be read as part of this
    invocation's evidence, so a directory that cannot be removed or created
    stops the invocation rather than being reused.

    Raises
    ------
    ModelCheckError
        Raised, naming the directory, when it cannot be removed or created.
    """
    remove_tree(directory)
    try:
        directory.mkdir(parents=True)
    except OSError as error:
        raise ModelCheckError(f"cannot create {directory}: {error}") from error


def run_suite(
    session: Session,
    runs: Sequence[Run],
    jobs: int,
    *,
    cancel: Callable[[], None] | None = None,
) -> list[Outcome]:
    """Execute every run, ``jobs`` at a time, and return their outcomes in order.

    An interrupt arrives on the calling thread only, while the runs execute on
    worker threads whose checkers sit in their own process groups. So on an
    interrupt this calls ``cancel``, which tells the runner to stop the
    checkers it is running, drops the runs not yet started, waits for every
    worker to finish stopping, and then re-raises the interrupt.
    """
    pool = ThreadPoolExecutor(max_workers=jobs)
    futures = [pool.submit(execute, run, session) for run in runs]
    try:
        return [future.result() for future in futures]
    except KeyboardInterrupt:
        # Drop the queued runs before telling the active ones to stop, so a
        # worker that frees up cannot start another checker in between.
        pool.shutdown(wait=False, cancel_futures=True)
        if cancel is not None:
            cancel()
        pool.shutdown(wait=True)
        raise
    finally:
        pool.shutdown(wait=True)


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


def read_trace(output: Path) -> tuple[str, ...]:
    """Return the action names of the checker's error trace.

    The checker writes ``error-graph.json`` only for a counterexample, so an
    absent file is no trace. A file that is present and cannot be read, is
    not UTF-8 text, is not JSON, or is not a list of steps is not an empty
    trace: treating it as
    one would judge a control on a counterexample nobody could read.

    Raises
    ------
    ModelCheckError
        Raised, naming the file, when it exists but cannot be read or parsed.
    """
    graph = output / "error-graph.json"
    text = _graph_text(graph)
    if text is None:
        return ()
    return tuple(name for name in map(_step_name, _graph_steps(graph, text)) if name)


def _graph_text(graph: Path) -> str | None:
    """Return an error graph's text, or None when the checker wrote none.

    Raises
    ------
    ModelCheckError
        Raised, naming ``graph``, when it exists but cannot be read or is not
        UTF-8 text.
    """
    try:
        return graph.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as error:
        raise ModelCheckError(f"the error trace {graph} is not UTF-8 text: {error}") from error
    except OSError as error:
        raise ModelCheckError(f"cannot read the error trace {graph}: {error}") from error


def _graph_steps(graph: Path, text: str) -> list[object]:
    """Return the steps of an error graph's text, which must be a JSON list.

    Raises
    ------
    ModelCheckError
        Raised, naming ``graph``, when the text is not JSON or not a list.
    """
    try:
        steps = json.loads(text)
    except ValueError as error:
        raise ModelCheckError(f"the error trace {graph} is not JSON: {error}") from error
    if not isinstance(steps, list):
        raise ModelCheckError(f"the error trace {graph} is not a list of steps")
    return steps


def record_artefacts(files: RunFiles, result: ProcessResult) -> tuple[str, ...]:
    """Keep one run's output in its run files and return its error trace.

    The checker's standard output and error are kept as they were, and the
    trace's action names, when there is a trace, beside them.

    Raises
    ------
    ModelCheckError
        Raised when an artefact cannot be written or the trace cannot be read.
    """
    files.write("stdout.txt", result.stdout)
    files.write("stderr.txt", result.stderr)
    trace = files.trace()
    if trace:
        files.write("trace.txt", "\n".join(trace) + "\n")
    return trace


def judge_run(
    run: Run, result: ProcessResult, text: str, trace: tuple[str, ...]
) -> Judgement:
    """Judge one run's output, then require its counterexample's named steps.

    This is the whole verdict and does no I/O: the output and the trace are
    handed in.
    """
    ok, status, detail, reading = judge(run, result, text)
    absent = missing_steps(run.expectation, trace) if ok else []
    if absent:
        ok, status = False, "wrong-reason"
        detail = "the counterexample does not pass through: " + ", ".join(absent)
    return ok, status, detail, reading


def read_source(run: Run, suite: Suite) -> str:
    """Return the text of the specification a run names, unmutated.

    Raises
    ------
    ModelCheckError
        Raised, naming the run and the file, when it cannot be read as text.
    """
    source = suite.directory / run.spec
    try:
        return source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ModelCheckError(f"run `{run.id}`: cannot read {source}: {error}") from error


def prepare_inputs(run: Run, original: str, files: RunFiles) -> tuple[str, list[str]]:
    """Write one run's inputs into its run files; return its text and argv.

    The checker writes beside the specification it is given, so the
    specification is copied into the run's own directory and the source tree
    is never written to.

    Raises
    ------
    ModelCheckError
        Raised when a mutation anchor does not match exactly once, or an
        input cannot be written.
    """
    text = mutate(original, run.mutations, run.id)
    files.create()
    files.write("spec.fizz", text)
    files.write("fizz.yaml", render_options(run.options))
    command = ["--test", "--output-dir", "out"]
    inputs = (
        ("scenario.cfg", run.scenario if run.scenario.strip() else "", "--preinit-hook-file"),
        ("replay.txt", "".join(f"{step}\n" for step in run.trace), "--trace-file"),
    )
    for name, content, flag in inputs:
        if content:
            files.write(name, content)
            command += [flag, name]
    return text, [*command, "spec.fizz"]


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
        Raised when the specification is unreadable, a mutation anchor does
        not match exactly once, an input or artefact cannot be written, or
        the checker's error trace cannot be read.
    """
    files = session.run_files(session.report / run.id)
    original = read_source(run, session.suite)
    text, arguments = prepare_inputs(run, original, files)
    command = (str(session.fizz), *arguments)
    result = session.runner(command, files.path, run.timeout_seconds)
    trace = record_artefacts(files, result)
    ok, status, detail, reading = judge_run(run, result, text, trace)
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
        artefacts={"directory": str(files.path)},
    )
